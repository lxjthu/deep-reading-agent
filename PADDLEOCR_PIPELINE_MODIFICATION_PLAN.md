# PaddleOCR Pipeline 修改方案

基于 PP-StructureV3 API 官方文档，对比当前实现，列出问题和修改方案。

---

## 一、问题分析

### P0：PDF 页数限制（功能缺陷）

API 服务端默认只处理前 10 页。解除需在服务端配置 `max_num_input_imgs: null`，但我们不一定控制服务端。当前代码对此毫无处理——25 页论文会静默丢失后 15 页内容。

### P0：图片处理逻辑错误（功能缺陷）

API 返回 `markdown.images` 格式为 `{"relative_path": "base64_string"}`，但 `extractor.py:265` 用 `requests.get(img_url)` 把 base64 字符串当 URL 下载，必然失败。失败后 fallback 保留原始 base64 字符串作为"路径"，导致图片完全不可用。

### P1：API 参数不完整

当前 payload（`extractor.py:193-200`）缺少 `useTableRecognition`、`useFormulaRecognition`、`useRegionDetection` 等参数。虽然 API 有默认值，但未显式设置意味着无法控制行为。

### P2：prunedResult 未利用

API 返回的结构化版面信息被完全忽略，丢失了区域类型统计等有价值的元数据。

---

## 二、具体修改

### 2.1 PDF 分片处理

**文件**：`paddleocr_extractor/extractor.py`

**思路**：用 `pypdf` 在内存中将长 PDF 切成每 10 页一片，逐片调 API，合并结果。

**新增方法**：

```python
def _split_pdf_bytes(self, pdf_path: str) -> List[bytes]:
    """将 PDF 按 max_pages_per_chunk 切分，返回每片的 bytes"""
    from pypdf import PdfReader, PdfWriter
    from io import BytesIO

    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    if total <= self.max_pages_per_chunk:
        with open(pdf_path, "rb") as f:
            return [f.read()]

    chunks = []
    for start in range(0, total, self.max_pages_per_chunk):
        writer = PdfWriter()
        for i in range(start, min(start + self.max_pages_per_chunk, total)):
            writer.add_page(reader.pages[i])
        buf = BytesIO()
        writer.write(buf)
        chunks.append(buf.getvalue())
    return chunks
```

**修改 `_call_api`**：拆为 `_call_api_single`（单次请求）和 `_call_api`（分片+合并）：

```python
def _call_api(self, pdf_path: str) -> Tuple[str, Dict[str, str]]:
    chunks = self._split_pdf_bytes(pdf_path)
    all_markdown = []
    all_images = {}

    for idx, chunk_bytes in enumerate(chunks):
        if len(chunks) > 1:
            print(f"  处理分片 {idx+1}/{len(chunks)}")
        file_data = base64.b64encode(chunk_bytes).decode("ascii")
        md, imgs = self._call_api_single(file_data, 0)
        # 分片 >1 时给图片 key 加前缀避免冲突
        if len(chunks) > 1:
            imgs = {f"chunk{idx}_{k}": v for k, v in imgs.items()}
        all_markdown.append(md)
        all_images.update(imgs)

    return "\n\n".join(all_markdown), all_images
```

`_call_api_single` 就是现在 `_call_api` 中从构建 payload 到解析 response 的那段逻辑，入参改为 `file_data_b64` 和 `file_type`。

**构造函数新增参数**：`max_pages_per_chunk: int = 10`

### 2.2 修复图片保存逻辑

**文件**：`paddleocr_extractor/extractor.py`，`_download_images` 方法（第 248-278 行）

**修改核心**：判断 value 是 URL 还是 Base64，分别处理：

```python
def _download_images(self, images: Dict[str, str], out_dir: Path) -> Dict[str, str]:
    imgs_dir = out_dir / "imgs"
    imgs_dir.mkdir(parents=True, exist_ok=True)
    downloaded = {}
    print(f"正在保存 {len(images)} 张图片...")

    for img_name, img_value in images.items():
        try:
            safe_name = img_name.replace("/", "_").replace("\\", "_")
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-")
            if not safe_name:
                safe_name = f"img_{len(downloaded)}.jpg"
            local_path = imgs_dir / safe_name

            if img_value.startswith(("http://", "https://")):
                # URL 模式：HTTP 下载
                resp = requests.get(img_value, timeout=30)
                resp.raise_for_status()
                img_data = resp.content
            else:
                # Base64 模式：直接解码
                img_data = base64.b64decode(img_value)

            with open(local_path, "wb") as f:
                f.write(img_data)

            downloaded[img_name] = f"imgs/{safe_name}"
        except Exception as e:
            print(f"  [FAIL] {img_name}: {e}")

    print(f"成功保存 {len(downloaded)} 张图片")
    return downloaded
```

同时 `_update_image_paths` 需要改为按 `img_name`（key）替换，而不是按 `img_url`（value）替换，因为 markdown 文本中引用的是 key（相对路径）。

### 2.3 补全 API 参数

**文件**：`paddleocr_extractor/extractor.py`

**构造函数新增参数**（均有默认值，向后兼容）：

```python
def __init__(
    self,
    remote_url=None,
    remote_token=None,
    timeout=600,
    only_original_images=True,
    # --- 新增 ---
    use_table_recognition=True,
    use_formula_recognition=True,
    use_chart_recognition=False,
    use_seal_recognition=False,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    use_region_detection=True,
    max_pages_per_chunk=10,
):
```

**payload 构建**改为使用实例属性：

```python
payload = {
    "file": file_data,
    "fileType": file_type,
    "useDocOrientationClassify": self.use_doc_orientation_classify,
    "useDocUnwarping": self.use_doc_unwarping,
    "useTextlineOrientation": self.use_textline_orientation,
    "useChartRecognition": self.use_chart_recognition,
    "useTableRecognition": self.use_table_recognition,
    "useFormulaRecognition": self.use_formula_recognition,
    "useSealRecognition": self.use_seal_recognition,
    "useRegionDetection": self.use_region_detection,
}
```

### 2.4 更新 paddleocr_pipeline.py CLI

**文件**：`paddleocr_pipeline.py`

新增 CLI 参数并传递给 `PaddleOCRPDFExtractor`：

```python
parser.add_argument("--no_table", action="store_true", help="禁用表格识别")
parser.add_argument("--no_formula", action="store_true", help="禁用公式识别")
parser.add_argument("--chart", action="store_true", help="启用图表解析")
parser.add_argument("--orientation", action="store_true", help="启用文档方向矫正")
parser.add_argument("--max_pages", type=int, default=10,
                    help="每次 API 调用最大页数（默认 10）")
```

`extract_pdf_with_paddleocr` 函数签名相应扩展，将参数传给 `PaddleOCRPDFExtractor()`。

### 2.5 prunedResult 统计（P2，可选）

在 `_call_api_single` 解析响应时，从 `prunedResult` 中提取区域类型统计，附加到返回值中。具体结构取决于 API 实际返回内容，可在测试中确认后再实现。

---

## 三、修改文件清单

| 文件 | 改动点 | 行数估计 |
|------|--------|---------|
| `paddleocr_extractor/extractor.py` | 构造函数扩展、`_split_pdf_bytes`、`_call_api` 拆分重构、`_download_images` 重写、`_update_image_paths` 修复 | ~120 行改动 |
| `paddleocr_pipeline.py` | CLI 参数、`extract_pdf_with_paddleocr` 参数传递 | ~20 行改动 |

**不需要修改**：`run_full_pipeline.py`、`run_batch_pipeline.py`、`paddleocr_segment.py`、`smart_scholar_lib.py`——它们通过 `paddleocr_pipeline.py` 间接调用，接口不变。

---

## 四、测试计划

使用 `E:\pdf\002` 下的测试文件：

| 测试项 | 文件 | 验证点 |
|--------|------|--------|
| 分片功能 | `25页长论文.pdf` (3.2MB) | 全部 25 页内容被提取，日志显示 3 个分片 |
| 短文档回归 | `6页短论文.pdf` (200KB) | 不触发分片，行为与改动前一致 |
| 图片保存 | 两个文件 | Base64 图片正确解码保存为本地文件 |
| 参数传递 | 任意文件 | `--no_table`、`--no_formula` 等参数生效 |
| Fallback | 断开 API 后测试 | 自动回退到 pdfplumber，不报错 |

---

## 五、向后兼容性

- 所有新增参数都有默认值，现有调用方无需任何修改
- 分片仅在 PDF > 10 页时触发
- 图片处理同时兼容 URL 和 Base64 两种格式

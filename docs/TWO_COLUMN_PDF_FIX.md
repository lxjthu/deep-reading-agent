# 双栏 PDF 参考文献提取修复

> 日期：2026-05-20

## 问题

双栏排版论文使用参考文献梳理功能时，仅能提取 2-3 条参考文献（实际应有 10-50 条），而单栏论文不受影响。

## 根因

`pdfplumber` 的 `page.extract_text()` 按**从上到下、从左到右**的顺序输出字符，对双栏 PDF 会产生**左右栏交错**的文本流：

```
实际布局：          extract_text() 输出：
┌─────┬─────┐      左1 右1
│ 左1 │ 右1 │      左2 右2
│ 左2 │ 右2 │      左3 右3
│ 左3 │ 右3 │      ...
└─────┴─────┘
```

参考文献区通常在论文最后几页（全页双栏），左右栏按行交错后文本完全乱序。例如 `[1] 牛若峰．农业...` 被拆成 `牛若峰．农业...` + `论 ［Ｊ］．农业经济问题...` + 右栏无关内容，DeepSeek 无法识别。

## 方案：列感知文本提取

### 核心思路

对检测为双栏的页面，从页面中间位置 crop 为左、右两个半区，分别提取文本后拼接，还原正确的阅读顺序。

### 检测算法

```python
def _is_two_column_page(page) -> bool:
    chars = page.chars
    if len(chars) < 50:
        return False
    mid_x = page.width / 2
    left_count = sum(1 for c in chars if c["x0"] < mid_x)
    ratio = left_count / len(chars)
    return 0.25 < ratio < 0.75
```

**判断逻辑**：统计页面字符在左半/右半的分布。双栏页面两列宽度相近，字符分布接近 50:50；单栏页面字符集中在中间或左半，比例失衡。

**阈值选择**：`0.25 < ratio < 0.75` 对标准双栏（比例约 0.4-0.6）有效，同时容忍页眉页脚等不对称元素。

### 提取逻辑

```python
def _extract_page_text_column_aware(page) -> str:
    if not _is_two_column_page(page):
        return page.extract_text() or ""    # 单栏：默认行为
    mid_x = page.width / 2
    left_crop = page.crop((0, 0, mid_x, page.height))
    right_crop = page.crop((mid_x, 0, page.width, page.height))
    left_text = left_crop.extract_text() or ""
    right_text = right_crop.extract_text() or ""
    return left_text + "\n" + right_text     # 先左后右拼接
```

单栏页面无额外开销（直接 `return`）；双栏页面多一次 crop + extract_text。

## 改动文件

| 文件 | 改动 |
|------|------|
| `backend/services/deepseek_refs.py` | 新增 `_is_two_column_page`、`_extract_page_text_column_aware`；`extract_candidate_text`、`extract_body_text`、`trace_citations_deepseek` 三处 `page.extract_text()` 替换为列感知版本；加强噪音行过滤 |

### 噪音过滤增强

双栏 crop 提取会带入页脚、页眉、编辑信息等噪音，新增以下过滤模式：

| 模式 | 示例 | 说明 |
|------|------|------|
| `^[—\-·…\s]+$` | `————`、`····` | 分隔线 |
| `^·\d+·$` | `·136·` | 页码标记 |
| `^\d+\s*·$` | `63 ·` | 尾页页码 |
| `^责任编辑` | `责任编辑：` | 编辑信息 |
| `^校\s*对` | `校 对：` | 校对信息 |

## 效果

以用户提供的双栏论文（8 页全双栏）测试：

| 指标 | 改造前 | 改造后 |
|------|--------|--------|
| 候选文本行数 | 8 | 38 |
| 候选文本字符数 | 127 | 1027 |
| 可识别参考文献 | 2 | 13（全部） |
| 正文提取质量 | 交错乱序 | 列序正确 |

对单栏 PDF 无影响：检测函数返回 `False`，直接走原有逻辑。

## 边界情况

- **混合排版**（正文双栏、参考文献单栏）：逐页检测，每页独立选择提取策略
- **三栏或非对称双栏**：比例阈值 `0.25-0.75` 对三栏不适用，但学术论文极少三栏
- **跨栏标题/图表**：crop 后标题被截断到左半区，但不影响参考文献区（通常在文末、无跨栏元素）
- **全角数字编号**：`〔１〕`、`［Ｊ］` 等全角字符不影响 DeepSeek 识别

## 附带修复：DeepSeek API 连接错误重试

### 问题

双栏修复后，参考文献提取（`extract_references_deepseek`）成功返回 16 条，但正文引用追踪（`trace_citations_deepseek`）报 `Connection error` 直接失败，未进入重试。

### 根因

`call_deepseek_json` 的 except 只捕获了 `APITimeoutError` 和 `httpx.ConnectTimeout`，未捕获 `httpx.ConnectError` 和 `openai.APIConnectionError`。第二次 API 调用碰上网络瞬断时，异常未被 retry 循环处理，直接抛出导致任务失败。

### 修复

扩大 catch 范围，所有连接类错误（`ConnectError`、`APIConnectionError` 等）都进入 retry 循环（最多 3 次），非连接类错误正常 raise。

```python
except (APITimeoutError, httpx.ConnectTimeout, httpx.ConnectError) as exc:
    logger.warning("DeepSeek connection error (attempt %d/%d): %s", ...)
    continue
except Exception as exc:
    if "connection" in type(exc).__name__.lower() or "connect" in str(exc).lower():
        continue
    raise
```

# 双栏 PDF 参考文献提取修复方案

> 状态：**已规划，待实施**  
> 适用范围：`P0 参考文献梳理标签页 + 引用关系入库` 的文本提取链路修复  
> 分析日期：2026-05-03  
> 分析 PDF：`"双碳"目标下乡村生态振兴的内在逻辑、重点任务及实践路径.pdf`（8 页双栏中文论文）

## 1. 问题描述

### 1.1 现象

对于该双栏中文论文 PDF，`deepseek_refs.py` 的参考文献提取**完全失败**：

- `extract_candidate_text()` 返回仅 647 字符、28 行（正常应有 2000+ 字符）
- 中文字符全部乱码（`�`），无法被 DeepSeek LLM 识别
- 最终结果：0 条参考文献被提取

### 1.2 根因分析

`backend/services/deepseek_refs.py` 的文本提取链路**只依赖 pypdf**，而 pypdf 对此类 PDF 存在两个致命缺陷：

| 问题 | 原因 | 影响 |
|------|------|------|
| **中文乱码** | PDF 使用自定义 CMap/ToUnicode 编码（CJK 字体），pypdf 无法解码 | 中文字符全部变成 `�` |
| **双栏顺序错乱** | pypdf 按物理坐标逐行提取，不识别逻辑列 | 左右栏文本交叠，参考文献条目被切碎 |

### 1.3 对比验证

| 提取工具 | 中文可读性 | 文本长度 | 参考文献结构 | 双栏处理 |
|----------|-----------|----------|-------------|----------|
| **pypdf**（当前） | 全部乱码 | 647 字符 | 不可识别 | 无 |
| **pdfplumber**（不使用 flow） | 大部分可读 | 2008 字符 | 条目头尾断裂 | 无 |
| **pdfplumber**（`use_text_flow=True`） | 大部分可读 | 2008 字符 | 条目结构完整，顺序正确 | 自动处理 |

关键发现：**pdfplumber 在启用 `use_text_flow=True` 时，能正确按阅读顺序提取双栏文本**，且中文可读性远优于 pypdf。

## 2. 影响范围

### 2.1 受影响的调用路径

参考文献提取链路与深度阅读主链路**完全独立**，不共享文本提取结果：

```
PDF → PaddleOCR/pypdf → MD → DeepSeek(deep reading) → 分析结果  ✅ 不受影响

PDF → pypdf → extract_candidate_text() → DeepSeek(ref extraction) → 参考文献  ❌ 失败
                 ↑
              问题所在（deepseek_refs.py:173-228）
```

调用方：

- `backend/routers/reading.py:544` — 深度阅读完成后自动触发
- `backend/routers/references.py:736` — 用户在参考文献标签页手动触发

### 2.2 受影响的 PDF 类型

- 所有使用 CMap/ToUnicode 自定义编码的中文 CJK 字体 PDF（大量中文学术期刊）
- 双栏排版的论文 PDF（期刊标准格式）
- 两问题叠加的 PDF 影响最严重

### 2.3 不受影响的部分

- 深度阅读主流程（使用 PaddleOCR 独立提取）
- 正文引用追踪中的 LLM 调用逻辑（只需切换文本源）
- 数据库存储逻辑（`bib_references` / `bib_reference_citations` 表结构无需改动）
- 前端展示逻辑

## 3. 修复方案

### 3.1 方案选择

**方案：pypdf → pdfplumber**

将 `extract_candidate_text()` 和 `extract_body_text()` 的文本提取从 pypdf 改为 pdfplumber。后续不再引入 PaddleOCR 复用，保持参考文献提取链路独立。

- 优点：改动最小（仅一个文件），pdfplumber 对 CJK 字体和双栏布局支持远好于 pypdf
- 缺点：pdfplumber 对扫描版 PDF（纯图片无文本层）同样无法提取文本，但此类 PDF 本就需要 PaddleOCR 预处理

### 3.2 具体改动

改动范围仅限 `backend/services/deepseek_refs.py`：

1. `extract_candidate_text()`（行 173-228）：
   - 将 `from pypdf import PdfReader` 替换为 `import pdfplumber`
   - 使用 `pdfplumber.open()` 逐页读取，`page.extract_text(use_text_flow=True)` 提取文本
   - 保持现有的 `_is_ref_heading`、`_looks_like_ref_entry`、过滤逻辑不变
   - 新增双栏检测：通过 `page.chars` 的 x0 分布判断是否为双栏布局，若是则强制 `use_text_flow=True`

2. `extract_body_text()`（行 231-285）：
   - 同样切换为 pdfplumber + `use_text_flow=True`
   - 段落分割逻辑（`re.split(r"\n\s*\n", text)`）保持不变

3. `extract_references_deepseek()`（行 323-381）：
   - fallback 逻辑（候选文本过短时取最后 5 页）改为 pdfplumber 实现

### 3.3 实施步骤

| 步骤 | 内容 | 文件 |
|------|------|------|
| 1 | 将 `extract_candidate_text()` 从 pypdf 改为 pdfplumber | `backend/services/deepseek_refs.py` |
| 2 | 将 `extract_body_text()` 从 pypdf 改为 pdfplumber | `backend/services/deepseek_refs.py` |
| 3 | fallback 逻辑改为 pdfplumber | `backend/services/deepseek_refs.py` |
| 4 | 新增双栏检测辅助函数 `_is_two_column()` | `backend/services/deepseek_refs.py` |
| 5 | 在 `requirements.txt` 中确认 pdfplumber 已安装 | `requirements.txt` |
| 6 | 用测试集中的 4 个已验证 PDF 回归验证 | `test_deepseek_references.py` |
| 7 | 用本文分析的双栏 PDF 验证修复效果 | 手动测试 |

## 4. 双栏检测算法

```python
def _is_two_column(chars: list[dict], threshold: float = 0.2) -> bool:
    """通过字符 x0 分布判断是否为双栏布局。"""
    if len(chars) < 100:
        return False
    x0s = [c["x0"] for c in chars if c.get("x0", 0) > 0]
    if not x0s:
        return False
    
    # 取中位数左右两侧的字符数
    median = sorted(x0s)[len(x0s) // 2]
    left = sum(1 for x in x0s if x < median - 50)
    right = sum(1 for x in x0s if x > median + 50)
    total = len(x0s)
    
    # 两侧字符数都超过阈值比例，认为是双栏
    return left / total > threshold and right / total > threshold
```

## 5. 风险与注意事项

### 5.1 pdfplumber 的已知局限

- 对扫描版 PDF（纯图片无文本层）同样无法提取文本，需要 PaddleOCR
- `use_text_flow=True` 在处理复杂表格、公式、脚注时可能产生错误排序
- 某些 PDF 的 CMap 编码 pdfplumber 也无法完全解码（但远好于 pypdf）

### 5.2 回归风险

- 已有 4 个验证 PDF（`test_deepseek_references.py` 中的测试集）需要通过回归验证
- 英文 PDF 通常不受 CJK 编码问题影响，但双栏问题同样适用
- `char_start` / `char_end` 的计算依赖 `body_text.find(quote)`，切换文本源后需要验证 quote 匹配率

### 5.3 性能影响

- pdfplumber 比 pypdf 稍慢（约 1.5-2x），但对于参考文献提取这一异步后台任务，影响可接受
- `use_text_flow=True` 会增加额外处理时间，建议仅对检测为双栏的页面启用

## 6. 验证标准

修复完成后，对本次分析的双栏 PDF 期望结果：

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| `extract_candidate_text()` 返回长度 | 647 字符 | >2000 字符 |
| 中文可读性 | 全部乱码 | 基本可读（90%+ 字符正确） |
| 参考文献条目提取 | 0 条 | 32 条（该论文实际有 32 条参考文献） |
| `_looks_like_ref_entry` 命中 | 0 | 32 |
| 正文引用追踪 `quote` 可匹配 | N/A | 至少 50% 引用可定位 |

对已有 4 个验证 PDF 期望：回归通过，提取数不下降。

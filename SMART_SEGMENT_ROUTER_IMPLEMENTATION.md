# Smart Segment Router 实施文档

**创建时间**: 2026-02-02  
**核心文件**: `smart_segment_router.py`  
**状态**: ✅ 核心逻辑完成，待集成到流水线

---

## 一、背景与问题

### 旧方案的问题
1. **LLM 直接输出完整文本** → API 截断风险，长论文内容丢失
2. **分段不完整** → 只能提取前部分章节，后续章节被截断
3. **单步骤映射** → 一个章节只能映射到一个分析步骤，无法处理混合章节

### 新方案优势
| 维度 | 旧方案 | 新方案 |
|------|--------|--------|
| LLM 职责 | 切分+返回文本 | 只分类标题（轻量） |
| 内容完整性 | ❌ API 截断 | ✅ 代码直接切分原文 |
| 多步骤映射 | ❌ 不支持 | ✅ 支持 |
| 空步骤处理 | ❌ 丢失 | ✅ 自动填充 |
| Token 消耗 | 高 | 极低 |

---

## 二、核心逻辑

### 2.1 工作流程

```
PaddleOCR MD (带 ##/### 标题)
        ↓
[1. extract_headings()] 
    - 只提取 ## 一级标题
    - ### 子章节作为父章节内容的一部分
    - 记录每个标题的 start_pos / end_pos
        ↓
[2. classify_headings()]
    - 发送标题列表给 LLM (deepseek-chat)
    - LLM 返回 {step_id: [title1, title2, ...]} 映射
    - 支持 multi_assign: {title: [step1, step2, ...]}
        ↓
[3. segment_by_routing()]
    - 根据映射从原文直接提取内容
    - 100% 完整，不经过 LLM
        ↓
[4. _fill_empty_steps()]
    - 检查每个步骤是否有内容
    - 空步骤从前/后步骤复制填充
        ↓
[5. save_segmented_md()]
    - 输出兼容格式的 segmented.md
```

### 2.2 关键设计

#### A. 多步骤映射
```python
# 一个章节可以同时属于多个步骤
multi_assign = {
    "研究设计": ["3", "4", "5"],      # Data + Variables + Identification
    "实证设计": ["3", "4", "5"],
    "Methodology": ["3", "4", "5"]
}
```

#### B. 空步骤填充策略
```python
# QUANT: 7步
order = ["1", "2", "3", "4", "5", "6", "7"]
# 如果 Step 4 为空，从 Step 3 或 Step 5 复制

# QUAL: 4层
order = ["L1", "L2", "L3", "L4"]
# 如果 L2 为空，从 L1 或 L3 复制
```

#### C. 层级包含
```
## 1. 引言                    ← 父章节（提取这个）
### 1.1 研究背景             ← 子章节（自动包含）
### 1.2 问题提出             ← 子章节（自动包含）
## 2. 文献综述
```

---

## 三、输出格式

### 3.1 定量论文 (QUANT)

```markdown
# 论文原文结构化分段（Smart Router）

- Source: paddleocr_md/xxx_paddleocr.md
- Mode: quant
- Generated: 2026-02-02Txx:xx:xx

## 路由映射

- 1: Overview (全景扫描)
- 2: Theory (理论与假说)
- 3: Data (数据考古)
- 4: Variables (变量与测量)
- 5: Identification (识别策略)
- 6: Results (结果解读)
- 7: Critique (专家批判)

## 1. Overview (全景扫描)

```text
【原文：一、引言】
...
```

## 2. Theory (理论与假说)

```text
【原文：二、理论框架】
...
---
【原文：（一）数理模型】
...
```

... (其他步骤)
```

### 3.2 定性论文 (QUAL)

```markdown
## 路由映射

- L1: L1_Context (背景层)
- L2: L2_Theory (理论层)
- L3: L3_Logic (逻辑层)
- L4: L4_Value (价值层)

## L1. L1_Context (背景层)

```text
【原文：0引言】
...
```

## L2. L2_Theory (理论层)

```text
【此部分无独立章节，从相邻部分提取】
...
```

... (其他层级)
```

---

## 四、待完成的集成工作

### 4.1 替换批量流水线中的分段调用

**文件**: `run_batch_pipeline.py`

**当前代码**:
```python
# 第 81 行左右
seg_md_path = scholar.ensure_segmented_md(pdf_path)
```

**需要修改**:
1. 在 `smart_scholar_lib.py` 中添加新方法 `ensure_segmented_md_v2()`
2. 或者直接在 `run_batch_pipeline.py` 中调用 `smart_segment_router.py`

**建议方案**:
```python
# 在 run_batch_pipeline.py 顶部导入
from smart_segment_router import SmartSegmentRouter

# 在 main() 中
router = SmartSegmentRouter()

# 替换 ensure_segmented_md 调用
seg_md_path = router.process(pdf_path, "pdf_segmented_md", mode="auto")
```

### 4.2 更新定量分析模块

**文件**: `deep_reading_steps/common.py`

**函数**: `load_segmented_md()`

**当前逻辑**: 解析 `## 章节名` 格式的 segmented.md

**需要增强**:
```python
def load_segmented_md(md_path):
    """
    增强版：兼容新格式（步骤标签作为 key）
    """
    # 检测是新格式还是旧格式
    # 新格式：## 1. Overview, ## 2. Theory 等
    # 返回 {step_id: content} 字典
```

**已有兼容代码位置**: `deep_read_pipeline.py` 第 64-76 行有 `generate_semantic_index`，可能需要调整优先级。

### 4.3 更新定性分析模块

**文件**: `social_science_analyzer.py`

**函数**: `load_segmented_md()`

**当前逻辑**: 通过关键词匹配章节

**新逻辑**: 直接读取 L1-L4 映射

**建议修改**:
```python
def load_segmented_md(path: str) -> dict:
    """
    增强版：直接返回 L1-L4 映射
    """
    # 检测 Smart Router 格式
    # 返回 {"L1_Context": content, "L2_Theory": content, ...}
```

### 4.4 添加 CLI 入口（可选）

**文件**: `smart_segment_router.py` 已有 `main()` 函数

**使用方式**:
```bash
# 单文件处理
python smart_segment_router.py "paddleocr_md/xxx_paddleocr.md" --out_dir pdf_segmented_md --mode auto

# 参数说明
# --mode auto: 自动检测 quant/qual
# --mode quant: 强制 7步精读
# --mode qual: 强制 4层金字塔
```

---

## 五、测试验证清单

### 5.1 单元测试
- [ ] 中文论文（定量）
- [ ] 中文论文（定性）
- [ ] 英文论文（定量）
- [ ] 英文论文（定性）
- [ ] 混合章节论文（研究设计类）

### 5.2 集成测试
- [ ] 批量流水线完整跑通
- [ ] 7步精读输出正确
- [ ] 4层金字塔输出正确
- [ ] Dataview 摘要注入正常
- [ ] Obsidian 元数据注入正常

### 5.3 边界情况
- [ ] 无章节标题的论文
- [ ] 超长论文（>100页）
- [ ] 缺失某些章节的论文

---

## 六、关键代码片段

### 6.1 快速测试命令

```powershell
# 定量论文测试
cd D:\code\deepagent\deep-reading-agent
.\venv\Scripts\python.exe smart_segment_router.py `
    "paddleocr_md\人工智能、人力资本结构与灵活用工——来自在线招聘大数据的经验证据_刘行_paddleocr.md" `
    --out_dir test_segmented --mode quant

# 定性论文测试
.\venv\Scripts\python.exe smart_segment_router.py `
    "paddleocr_md\类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径_paddleocr.md" `
    --out_dir test_segmented --mode qual
```

### 6.2 检查分段结果

```python
# check_segments.py
import re

with open('test_segmented/xxx_segmented.md', 'r', encoding='utf-8') as f:
    content = f.read()

# QUANT: 检查7步
steps = re.findall(r'## (\d+)\.\s+', content)
print(f"Found steps: {steps}")

# QUAL: 检查4层
layers = re.findall(r'## (L\d+)\.\s+', content)
print(f"Found layers: {layers}")
```

---

## 七、注意事项

1. **API Key**: 需要 `DEEPSEEK_API_KEY` 环境变量
2. **编码**: Windows 控制台有编码问题，但不影响文件输出
3. **速率限制**: LLM 调用频率受 DeepSeek API 限制
4. **回退机制**: 如果 LLM 失败，会使用基于规则的分段

---

## 八、下一步行动

### 优先级 P0（今天完成）
- [ ] 将 `smart_segment_router.py` 集成到 `run_batch_pipeline.py`
- [ ] 测试批量处理 3-5 篇论文

### 优先级 P1（明天完成）
- [ ] 更新 `deep_reading_steps/common.py` 的 `load_segmented_md`
- [ ] 更新 `social_science_analyzer.py` 的 `load_segmented_md`
- [ ] 验证下游精读模块正常工作

### 优先级 P2（本周完成）
- [ ] 批量测试 20+ 篇论文
- [ ] 对比旧方案和新方案的分段质量
- [ ] 删除旧的 `paddleocr_segment.py` 和 `deepseek_segment_raw_md.py`

---

*文档版本: v1.0*  
*最后更新: 2026-02-02*

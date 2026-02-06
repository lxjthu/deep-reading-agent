# 修改总结 - 动态加载提示词功能实现

**创建时间**: 2026-02-03
**版本**: v2.0 (动态加载完成)

---

## 修改内容

### 1. 新增 `_load_prompt_from_file()` 方法

**位置**: `SocialScienceAnalyzer` 类，第 26-63 行
```python
def _load_prompt_from_file(self, layer: str) -> str:
    prompts_dir = os.path.join(os.path.dirname(__file__), "prompts", "qual_analysis")
    prompt_file = os.path.join(prompts_dir, f"{layer}_Prompt.md")
    
    if not os.path.exists(prompt_file):
        logger.warning(f"Prompt file not found: {prompt_file}, using fallback")
        return None
    
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # 提取 ```text ... ``` 代码块
            start_idx = content.find("```text") + 8
            end_idx = content.find("```", start_idx)
            
            if start_idx != -1 and end_idx != -1:
                prompt_text = content[start_idx:end_idx].strip()
                logger.info(f"Loaded prompt from file: {layer}")
                return prompt_text
            else:
                logger.warning(f"Failed to extract code block from: {prompt_file}")
                return None
                
        except Exception as e:
            logger.error(f"Error loading prompt file: {e}")
            return None
```

### 2. 修改 4 个分析方法以使用动态加载

**L1_Context**: 第 41-46 行，传递 `fallback_prompt="L1_Context (FALLBACK)"`
**L2_Theory**: 第 147-147 行，传递 `fallback_prompt="L2_Theory (FALLBACK)"`
**L3_Logic**: 第 180-212 行，传递 `fallback_prompt="L3_Logic (FALLBACK)"`
**L4_Value**: 第 224-261 行，传递 `fallback_prompt="L4_Value (FALLBACK)"`

### 3. 修复 `_call_llm()` 方法

**位置**: 第 197-256 行
```python
def _call_llm(self, system_prompt: str, user_content: str, fallback_prompt: str = None) -> dict:
```

**新增**: 接受 `fallback_prompt` 参数，用于记录日志

```python
    # 如果使用了备用提示词，记录日志
    if fallback_prompt:
        logger.info(f"Using fallback prompt for: {fallback_prompt}")
```

---

## 提示词文件结构

### 目录结构

```
prompts/qual_analysis/
├── L1_Context_Prompt.md
├── L2_Theory_Prompt.md
├── L3_Logic_Prompt.md
└── L4_Value_Prompt.md
```

每个文件包含：
- 完整提示词（可直接用于 LLM）
- 字段详解（metadata、policy_context、status_data/detailed_analysis 等）
- 使用说明（Python 调用示例）
- 常见问题解答
- 修改建议
- 版本历史

---

## 核心特性

| 特性 | 说明 |
|------|------|------|
| **动态加载** | 从外部 `.md` 文件读取提示词，不再硬编码 |
| **灵活修改** | 提示词修改只需改 `.md` 文件，无需改 Python 代码 |
| **版本控制** | Git 可追踪提示词变更历史 |
| **团队协作** | 团队成员可独立编辑提示词文件 |

---

## 下一步建议

1. **测试完整流程**：
```bash
# 测试提示词加载
python social_science_analyzer.py "pdf_segmented_md/xxx_segmented.md"

# 测试 L1-L4 完整分析
python social_science_analyzer.py "pdf_segmented_md/ChatGPT人工智能技术赋能乡村文化振兴_segmented.md"
```

2. **批量测试**：
```bash
python run_batch_pipeline.py "E:\pdf\001"
```

3. **监控日志**：
- 查看是否正确记录 "Loaded prompt from file" 日志
- 查看是否正确记录 "Using fallback prompt for: ..." 日志

---

**修改完成！** 🎉

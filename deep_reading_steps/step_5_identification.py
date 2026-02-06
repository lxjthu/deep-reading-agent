from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是剖析"识别策略与实证"，回答以下问题：

### **17. 计量模型**
写出核心回归方程（Y_it = alpha + beta X_it + ...）。

### **18. 识别挑战**
核心解释变量 X 是外生的吗？潜在的内生性来源是什么？（遗漏变量？反向因果？测量误差？）

### **19. 解决策略**
作者用了什么招数解决内生性？（IV, DID, RDD, Bunching?）

### **20. 机制检验**
绘制**影响机制图谱** (Mechanism Map)（使用 Mermaid 代码），说明 X -> M -> Y 的传导路径。

### **21. 稳健性检验 (Robustness)**
- *识别假设检验*：平行趋势、安慰剂检验、排他性约束检验。
- *替代性解释排除*：是否排除了其他竞争性假说？
- *异质性分析*：结果在不同子样本中是否稳健？

**格式要求**：
- 必须使用 `### **` 作为带编号小标题的标记
- 子项目使用 `-` 列表标记
- 使用专业、严谨的学术中文回答
"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 5):
    """
    Args:
        sections: The full dictionary of paper sections
        assigned_titles: List of titles assigned to this step
        output_dir: Directory to save results
        step_id: The ID of this step (1-7) for semantic retrieval
    """
    combined = get_combined_text_for_step(sections, assigned_titles, output_dir, step_id)
    
    # 智能分块
    chunks = smart_chunk(combined, max_tokens=10000)
    prompt = f"请根据以下论文内容（实证策略部分），完成【第五部分：识别策略与实证】的分析：\n\n{chunks[0]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("5_Identification", result, output_dir)
    return result

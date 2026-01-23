from .common import call_deepseek, save_step_result

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是剖析“识别策略与实证”，回答以下问题：
17. **计量模型**：写出核心回归方程（Y_it = alpha + beta X_it + ...）。
18. **识别挑战**：核心解释变量 X 是外生的吗？潜在的内生性来源是什么？（遗漏变量？反向因果？测量误差？）
19. **解决策略**：作者用了什么招数解决内生性？（IV, DID, RDD, Bunching?）
20. **机制检验**：绘制**影响机制图谱** (Mechanism Map)（使用 Mermaid 代码），说明 X -> M -> Y 的传导路径。
21. **稳健性检验 (Robustness)**：
    *   *识别假设检验*：平行趋势、安慰剂检验、排他性约束检验。
    *   *替代性解释排除*：是否排除了其他竞争性假说？
    *   *异质性分析*：结果在不同子样本中是否稳健？

请使用专业、严谨的学术中文回答。
"""

def run(sections):
    # Empirical / Identification sections
    context_text = ""
    for title, text in sections.items():
        if any(kw in title for kw in ["Empirical", "Identification", "Strategy", "Model", "Robustness", "实证", "识别", "模型", "稳健"]):
            context_text += f"【{title}】\n{text}\n\n"

    prompt = f"请根据以下论文内容（实证策略部分），完成【第五部分：识别策略与实证】的分析：\n\n{context_text[:30000]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("5_Identification", result)
    return result

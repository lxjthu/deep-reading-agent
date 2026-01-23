from .common import call_deepseek, save_step_result

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是分析“变量与测量”，回答以下问题：
13. **核心变量定义**：Y 和 X 具体是什么？
14. **衡量方式**：直接观测还是代理变量（Proxy）？如果是构建指标（如 TFP），具体指标构成要素和算法是什么？
15. **控制变量**：选择了哪些 Z？选择依据是什么？（是为了控制需求冲击，还是供给冲击？）
16. **特殊处理**：是否进行了对数化、去通胀、标准化等处理？

请使用专业、严谨的学术中文回答。
"""

def run(sections):
    # Variables usually in Data or Empirical Strategy
    context_text = ""
    for title, text in sections.items():
        if any(kw in title for kw in ["Variable", "Measure", "Statistic", "变量", "测量", "统计"]):
            context_text += f"【{title}】\n{text}\n\n"

    prompt = f"请根据以下论文内容（变量与测量部分），完成【第四部分：变量与测量】的分析：\n\n{context_text[:30000]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("4_Variables", result)
    return result

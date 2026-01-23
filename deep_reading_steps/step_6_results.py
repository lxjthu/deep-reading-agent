from .common import call_deepseek, save_step_result

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是进行“结果解读与评价”，回答以下问题：
22. **结果解读**：实证结果是什么？哪些系数显著？哪些不显著？不显著的原因是什么？
23. **评价**：结果是否与理论一致？是否满足**实证假设**？
24. **讨论**：结果与其他文献的结果相比如何？有何一致或矛盾之处？
25. **政策含义**：结果具有哪些政策或者实践上的指导意义？

请使用专业、严谨的学术中文回答。
"""

def run(sections):
    # Results and Discussion sections
    context_text = ""
    for title, text in sections.items():
        if any(kw in title for kw in ["Result", "Discussion", "Finding", "结果", "讨论", "发现"]):
            context_text += f"【{title}】\n{text}\n\n"

    prompt = f"请根据以下论文内容（结果与讨论部分），完成【第六部分：结果解读与评价】的分析：\n\n{context_text[:30000]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("6_Results", result)
    return result

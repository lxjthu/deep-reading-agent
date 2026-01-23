from .common import call_deepseek, save_step_result

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是进行“专家批判与展望”，回答以下问题：
26. **致命伤 (The Achilles' Heel)**：这篇文章最大的弱点是什么？（如：IV 的相关性太弱？外部有效性存疑？）
27. **未来选题**：基于本文的不足或未尽之处，提出 1-2 个具体的、可执行的新选题方向。

请使用专业、严谨的学术中文回答。
"""

def run(sections):
    # Conclusion and full text context (summary)
    # We might need to look at "Limitations" if explicitly mentioned
    context_text = ""
    for title, text in sections.items():
        if any(kw in title for kw in ["Conclusion", "Discussion", "Limitation", "结论", "讨论", "局限"]):
            context_text += f"【{title}】\n{text}\n\n"

    prompt = f"请根据以下论文内容（结论与讨论部分），完成【第七部分：专家批判与展望】的分析：\n\n{context_text[:30000]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("7_Critique", result)
    return result

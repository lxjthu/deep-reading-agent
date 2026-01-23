from .common import call_deepseek, save_step_result

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是分析论文的“理论与假说”，回答以下问题：
5. **文献谱系**：这篇论文是站在哪些巨人的肩膀上？（列出 3-5 篇关键参考文献）
6. **理论基础**：核心理论框架是什么？（如：人力资本理论、委托代理理论）
7. **待检验假说**：具体的 H1, H2 是什么？
8. **创新点**：这些假说与前人相比，新在哪里？
9. **逻辑推演**：假说背后的微观机制是什么？（为什么 A 会导致 B？）

请使用专业、严谨的学术中文回答。
"""

def run(sections):
    # Literature review and Theory sections
    context_text = ""
    for title, text in sections.items():
        # Heuristics for relevant sections
        if any(kw in title for kw in ["Literature", "Theory", "Hypothesis", "Background", "文献", "理论", "假说", "背景"]):
            context_text += f"【{title}】\n{text}\n\n"
            
    if not context_text:
        context_text = "未找到明确的理论或文献章节，请尝试从全文其他部分推断（此处略）。"

    prompt = f"请根据以下论文内容（文献与理论部分），完成【第二部分：理论与假说】的分析：\n\n{context_text[:30000]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("2_Theory", result)
    return result

from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是分析论文的"理论与假说"，回答以下问题：
5. **文献谱系**：这篇论文是站在哪些巨人的肩膀上？请分别找到作为本文研究起点的文献（1-3篇）、作为本文核心理论框架来源的文献(2-3篇）、为本文的分析视角合理性提供依据的文献（1-3篇）、为本文提供重要机制参考的文献（2-3篇）、为本文提供重要的实证方法借鉴的文献（列出 3 篇以上）
6. **理论基础**：核心理论基础是什么？（如：人力资本理论、委托代理理论）该理论在本文是如何应用的？包括哪些关键要素、分类维度和因果关系作用机制？
7. **待检验假说**：具体的 H1, H2 是什么？
8. **创新点**：这些假说与前人相比，新在哪里？具体是对前人哪些文献的哪个理论或假说做出了怎样的改进？比如维度的增加？视角的转换？新要素的引入？
9. **逻辑推演**：假说背后的微观机制是什么？（为什么 A 会导致 B？）

请使用专业、严谨的学术中文回答，只需针对每一个问题给出尽可能详细的解读，无需任何寒暄，不要添加任何前言。。
"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 2):
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
    
    if len(chunks) == 1:
        prompt = f"请根据以下论文内容（文献与理论部分），完成【第二部分：理论与假说】的分析：\n\n{chunks[0]}"
    else:
        # 多块处理：取前部分
        prompt = f"请根据以下论文内容（文献与理论部分），完成【第二部分：理论与假说】的分析：\n\n{chunks[0][:20000]}\n\n...（内容较长，已展示核心部分）"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("2_Theory", result, output_dir)
    return result

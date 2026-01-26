from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是进行"专家批判与展望"，回答以下问题：
26. **致命伤 (The Achilles' Heel)**：这篇文章最大的弱点是什么？（如：IV 的相关性太弱？外部有效性存疑？）
27. **未来选题**：基于本文的不足或未尽之处，提出 1-2 个具体的、可执行的新选题方向。

请使用专业、严谨的学术中文回答。
"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 7):
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
    prompt = f"请根据以下论文内容（结论与讨论部分），完成【第七部分：专家批判与展望】的分析：\n\n{chunks[0]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("7_Critique", result, output_dir)
    return result

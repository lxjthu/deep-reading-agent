from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step, load_prompt_from_file

SYSTEM_PROMPT = load_prompt_from_file("step_6_results", "quant")
if not SYSTEM_PROMPT:
    SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。进行结果解读与评价。"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 6):
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
    prompt = f"请根据以下论文内容（结果与讨论部分），完成【第六部分：结果解读与评价】的分析：\n\n{chunks[0]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("6_Results", result, output_dir)
    return result

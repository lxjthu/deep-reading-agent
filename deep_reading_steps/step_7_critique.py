from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step, load_prompt_from_file
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt_from_file("step_7_critique", "quant")
if not SYSTEM_PROMPT:
    SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。进行专家批判与展望。"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 7):
    """
    Args:
        sections: The full dictionary of paper sections
        assigned_titles: List of titles assigned to this step
        output_dir: Directory to save results
        step_id: The ID of this step (1-7) for semantic retrieval
    """
    combined = get_combined_text_for_step(sections, assigned_titles, output_dir, step_id)
    
    # Step 7 回退策略：如果内容不足，从 Step 1 (引言/概述) 和 Step 6/7 (结论) 获取
    if len(combined.strip()) < 200:
        logger.info("Step 7 content insufficient, falling back to Step 1 and conclusion sections")
        text_step1 = get_combined_text_for_step(sections, [], output_dir, step_id=1)
        text_step6 = get_combined_text_for_step(sections, [], output_dir, step_id=6)
        # 优先使用 Step 1 的内容，辅以 Step 6 的结果部分（通常包含总结和讨论）
        combined = f"【Step 1 引言/概述部分内容】\n\n{text_step1}\n\n【Step 6 结果解读部分内容（含总结讨论）】\n\n{text_step6}"
        logger.info(f"Combined fallback content length: {len(combined)}")
    
    # 智能分块
    chunks = smart_chunk(combined, max_tokens=10000)
    prompt = f"请根据以下论文内容（结论与讨论部分，或从引言/概述、结果部分提取的相关内容），完成【第七部分：专家批判与展望】的分析：\n\n{chunks[0]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("7_Critique", result, output_dir)
    return result

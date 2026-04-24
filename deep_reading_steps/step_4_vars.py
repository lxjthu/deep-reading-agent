from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step, load_prompt_from_file
import logging
import os

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt_from_file("step_4_vars", "quant")
if not SYSTEM_PROMPT:
    SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。分析变量与测量。"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 4):
    """
    Args:
        sections: The full dictionary of paper sections
        assigned_titles: List of titles assigned to this step
        output_dir: Directory to save results
        step_id: The ID of this step (1-7) for semantic retrieval
    """
    combined = get_combined_text_for_step(sections, assigned_titles, output_dir, step_id)
    
    # Step 4 回退策略：如果内容不足，从 Step 3 和 Step 5 获取
    if len(combined.strip()) < 200:
        logger.info("Step 4 content insufficient, falling back to Step 3 and Step 5")
        text_step3 = get_combined_text_for_step(sections, [], output_dir, step_id=3)
        text_step5 = get_combined_text_for_step(sections, [], output_dir, step_id=5)
        combined = f"【Step 3 数据考古部分内容】\n\n{text_step3}\n\n【Step 5 识别策略部分内容】\n\n{text_step5}"
        logger.info(f"Combined fallback content length: {len(combined)}")
    
    # 智能分块
    chunks = smart_chunk(combined, max_tokens=12000)
    
    if len(chunks) == 1:
        prompt = f"请根据以下论文内容（变量与测量部分，或从数据/识别策略部分提取的相关内容），完成【第四部分：变量与测量】的分析：\n\n{chunks[0]}"
    else:
        # 多块处理：取前两块拼接
        logger.info(f"Content split into {len(chunks)} chunks, using first 2 blocks")
        prompt = f"请根据以下论文内容（变量与测量部分，或从数据/识别策略部分提取的相关内容），完成【第四部分：变量与测量】的分析：\n\n{chunks[0]}\n\n...\n\n{chunks[1] if len(chunks) > 1 else ''}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("4_Variables", result, output_dir)
    return result

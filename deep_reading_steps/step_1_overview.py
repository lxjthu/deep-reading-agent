from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step, load_prompt_from_file

SYSTEM_PROMPT = load_prompt_from_file("step_1_overview", "quant")
if not SYSTEM_PROMPT:
    # Fallback default prompt
    SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。对论文进行全景扫描分析。"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 1):
    """
    Args:
        sections: The full dictionary of paper sections
        assigned_titles: List of titles assigned to this step
        output_dir: Directory to save results
        step_id: The ID of this step (1-7) for semantic retrieval
    """
    # Use the new robust text retrieval with semantic fallback
    combined = get_combined_text_for_step(sections, assigned_titles, output_dir, step_id)
    
    # 智能分块
    chunks = smart_chunk(combined, max_tokens=10000)
    
    if len(chunks) == 1:
        # 单块：直接发送
        prompt = f"请根据以下论文内容（路由分配的章节），完成【第一部分：全景扫描】的分析：\n\n{chunks[0]}"
    else:
        # 多块：分批处理后合并
        chunk_results = []
        for i, chunk in enumerate(chunks):
            part_prompt = f"请分析以下论文片段（第 {i+1}/{len(chunks)} 部分）：\n\n{chunk}\n\n提取关键信息，重点关注：研究主题、问题意识、贡献。"
            part_result = call_deepseek(part_prompt, SYSTEM_PROMPT)
            if part_result:
                chunk_results.append(f"=== 片段 {i+1} ===\n{part_result}\n")
        
        # 合并分析
        merged = "\n".join(chunk_results)
        prompt = f"以下是对论文的分段分析。请综合这些信息，完成【第一部分：全景扫描】：\n\n{merged}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("1_Overview", result, output_dir)
    return result

from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是分析"变量与测量"，回答以下问题：
13. **核心变量定义**：Y 和 X 具体是什么？其选择有何文献上的来源或依据？
14. **衡量方式**：直接观测还是代理变量（Proxy）？如果是构建指标（如 TFP），具体指标构成要素和算法是什么？
15. **控制变量**：选择了哪些 Z？选择依据是什么？（是为了控制需求冲击，还是供给冲击？）
16-1. **机制分析变量**：选择什么变量来做机制分析？具体是如何衡量的？是否使用了中介变量？中介变量具体是什么？是否使用了调节变量？调节变量具体是什么？是否使用了异质性分析？具体如何做的？是否有门槛分析？门槛变量是什么？
16-2. **特殊处理**：是否进行了对数化、去通胀、标准化等处理？

请使用专业、严谨的学术中文回答。
如果提供的文本中没有找到相关信息，请明确说明"未找到相关信息"，严禁根据已有知识编造。
"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 4):
    """
    Args:
        sections: The full dictionary of paper sections
        assigned_titles: List of titles assigned to this step
        output_dir: Directory to save results
        step_id: The ID of this step (1-7) for semantic retrieval
    """
    combined = get_combined_text_for_step(sections, assigned_titles, output_dir, step_id)
    
    # 智能分块
    chunks = smart_chunk(combined, max_tokens=12000)
    
    if len(chunks) == 1:
        prompt = f"请根据以下论文内容（变量与测量部分），完成【第四部分：变量与测量】的分析：\n\n{chunks[0]}"
    else:
        # 多块处理：取前两块拼接
        logger.info(f"Content split into {len(chunks)} chunks, using first 2 blocks")
        prompt = f"请根据以下论文内容（变量与测量部分），完成【第四部分：变量与测量】的分析：\n\n{chunks[0]}\n\n...\n\n{chunks[1] if len(chunks) > 1 else ''}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("4_Variables", result, output_dir)
    return result

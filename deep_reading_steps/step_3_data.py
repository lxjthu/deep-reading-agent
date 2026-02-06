from .common import call_deepseek, save_step_result, smart_chunk, get_combined_text_for_step

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是进行"数据考古"，回答以下问题：

### **10. 数据来源**
是公开数据（如 Census, World Bank）还是独家调研？

### **11. 获取与清洗**
- *公开数据*：具体获取方式、下载路径、清洗步骤（如去重、缩尾）。如果来源于某个数据库、统计年鉴、政府公报等请详细说明
- *调研数据*：抽样框是什么？样本量多少？如何保证代表性？
- *文本分析*：是否使用了一些工具进行文本分析来获取数据？如果使用，请详细说明

### **12. 数据生成的微观结构 (DGP)**
数据生成过程中是否存在系统性偏差？（如：幸存者偏差、自选择问题）

**格式要求**：
- 必须使用 `### **` 作为带编号小标题的标记
- 子项目使用 `-` 列表标记
- 使用专业、严谨的学术中文回答
"""

def run(sections: dict, assigned_titles: list, output_dir: str, step_id: int = 3):
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
    prompt = f"请根据以下论文内容（数据部分），完成【第三部分：数据考古】的分析：\n\n{chunks[0]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("3_Data", result, output_dir)
    return result

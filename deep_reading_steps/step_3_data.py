from .common import call_deepseek, save_step_result

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是进行“数据考古”，回答以下问题：
10. **数据来源**：是公开数据（如 Census, World Bank）还是独家调研？
11. **获取与清洗**：
    *   *公开数据*：具体下载路径、清洗步骤（如去重、缩尾）。
    *   *调研数据*：抽样框是什么？样本量多少？如何保证代表性？
12. **数据生成的微观结构 (DGP)**：数据生成过程中是否存在系统性偏差？（如：幸存者偏差、自选择问题）

请使用专业、严谨的学术中文回答。
"""

def run(sections):
    # Data sections
    context_text = ""
    for title, text in sections.items():
        if any(kw in title for kw in ["Data", "Sample", "数据", "样本"]):
            context_text += f"【{title}】\n{text}\n\n"

    prompt = f"请根据以下论文内容（数据部分），完成【第三部分：数据考古】的分析：\n\n{context_text[:30000]}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("3_Data", result)
    return result

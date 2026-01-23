from .common import call_deepseek, save_step_result

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是对论文进行“全景扫描”，回答以下问题：
1. **研究主题与核心结论**：用一句话概括这篇文章在讲什么，发现了什么？
2. **问题意识**：这篇文章解决了什么具体的科学问题？
3. **重要性 (The "So What?" Question)**：为什么这个问题值得研究？如果不解决它，我们会失去什么？
4. **贡献定位**：
    *   **理论贡献**：修正了哪个模型？填补了哪个空白？
    *   **实践贡献**：对政策制定或商业实践有何具体指导？

请使用专业、严谨的学术中文回答。
"""

def run(sections):
    # Combine Intro and Conclusion for overview
    # Trying to find sections that match "Introduction" or "Conclusion"
    intro_text = ""
    conclusion_text = ""
    
    for title, text in sections.items():
        if "Introduction" in title or "引言" in title:
            intro_text += text + "\n"
        if "Conclusion" in title or "结论" in title:
            conclusion_text += text + "\n"
            
    # If no specific sections found, use the whole text (fallback, though less efficient)
    # But usually segmentation should work.
    
    context = f"""
    【Introduction / 引言部分】
    {intro_text[:15000]} ... (truncated)
    
    【Conclusion / 结论部分】
    {conclusion_text[:15000]} ... (truncated)
    """
    
    prompt = f"请根据以下论文内容（引言和结论），完成【第一部分：全景扫描】的分析：\n\n{context}"
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("1_Overview", result)
    return result

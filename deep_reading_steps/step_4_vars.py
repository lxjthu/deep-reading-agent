from .common import call_deepseek, save_step_result

SYSTEM_PROMPT = """你是一位 Daron Acemoglu 级别的顶级计量经济学家。
你的任务是分析“变量与测量”，回答以下问题：
13. **核心变量定义**：Y 和 X 具体是什么？
14. **衡量方式**：直接观测还是代理变量（Proxy）？如果是构建指标（如 TFP），具体指标构成要素和算法是什么？
15. **控制变量**：选择了哪些 Z？选择依据是什么？（是为了控制需求冲击，还是供给冲击？）
16. **特殊处理**：是否进行了对数化、去通胀、标准化等处理？

请使用专业、严谨的学术中文回答。
如果提供的文本中没有找到相关信息，请明确说明“未找到相关信息”，严禁根据已有知识编造。
"""

def run(sections):
    # Variables usually in Data or Empirical Strategy
    # Expanded keywords to ensure we catch the right section
    keywords = [
        "Variable", "Measure", "Statistic", "Data", "Empirical", "Model", "Method", 
        "变量", "测量", "统计", "数据", "实证", "模型", "方法"
    ]
    
    context_text = ""
    found_sections = []
    
    for title, text in sections.items():
        if any(kw in title for kw in keywords):
            context_text += f"【{title}】\n{text}\n\n"
            found_sections.append(title)

    # Fallback Mechanism:
    # If no section matched the keywords, or context is too short, use a heuristic fallback.
    # Heuristic: Use all sections except Abstract, Intro, Conclusion, Refs.
    if not context_text or len(context_text) < 500:
        print("Warning: No specific 'Variables' sections found. Using Fallback Strategy.")
        context_text = "" # Reset
        exclude_keywords = ["Abstract", "Introduction", "Conclusion", "Reference", "Bibliography", "Appendix", "Acknowledgement", "摘要", "引言", "结论", "参考文献", "致谢"]
        
        for title, text in sections.items():
            # Check if title contains any exclude keywords
            if any(ex in title for ex in exclude_keywords):
                continue
            
            # Use this section
            context_text += f"【{title}】\n{text}\n\n"
            found_sections.append(title)

    print(f"Step 4 Context used sections: {found_sections}")

    prompt = f"请根据以下论文内容（变量与测量部分），完成【第四部分：变量与测量】的分析：\n\n{context_text[:50000]}" # Increased limit for V3
    
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    if result:
        save_step_result("4_Variables", result)
    return result

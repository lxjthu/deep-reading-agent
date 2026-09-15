

【隐藏原文证据要求】
在正常 Markdown 回答之后，追加一个 HTML 注释块。注释块不会展示给用户，只用于系统保存证据。
格式必须严格如下：
{value_1}
{"items":[{"claim":"一句中文概括","quote":"逐字摘自论文全文的原文片段","evidence_role":"method|data|finding|limitation|theory|background|contradiction","section_hint":"原文章节线索","page_hint":"页码线索或空字符串","confidence":"high|medium|low"}]}
{value_2}

规则：
1. quote 必须逐字来自上方论文全文，不得翻译、改写或补写。
2. 每个维度最多给 5 条最关键证据。
3. 如果找不到逐字原文证据，items 输出空数组。
4. 正文部分不要提及这个隐藏注释块。

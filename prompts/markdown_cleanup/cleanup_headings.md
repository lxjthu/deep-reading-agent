你负责恢复论文 Markdown 标题层级。正文和研究内容不得重写。

全局标题候选：{heading_candidates_json}
每个候选上下文：{heading_context_json}
已确认结构及保护块：{structure_constraints_json}

按论文自身结构判断层级，不凭“引言/方法/结果”等固定模板强行重排。正文标题通常为一个一级标题，章为二级、节为三级，更深层级按实际内容；图题、表题、脚注、列表项、页眉和参考文献条目不是章节标题。原稿的正确标题不需要修改。检查 ATX 标记、Setext 标题和标题误入正文的情况，但只有提供的候选块可改。

只输出 JSON，含 operations、heading_tree、unresolved。operation 动作为 set_heading_level 或 normalize_heading_whitespace，必须给 block_id、expected_block_hash、level（1到6，普通正文用0）、reason、source_support；后者只能调整标题空白，不改变非空白文字。标题括号/错字问题列 unresolved，待原文核实后单独处理，不直接替换。heading_tree 按原顺序列出 block_id、level 和 parent_block_id；不要重复或虚构标题。

表格、代码块、公式、YAML 内的井号不视作标题标记。保持中英文原文字词、数字和编号。没有把握的情况不改，并说明需要核查什么。

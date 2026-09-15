你负责核查 Markdown 结构清洗的修改依据，不重写正文。

修改清单和前后片段：{changes_with_context_json}
确定性检查结果：{deterministic_checks_json}
来源/分页映射摘要：{source_mapping_summary_json}

逐项检查是否只是可证明的分页、版面噪声、段落边界或标题层级修复；是否误删正文、遗漏脚注/表题/本文摘要、改变数字或公式、错合双栏、切断参考文献。看不到原页时，不声称已核对 PDF。确定性检查失败不能凭你的判断变为通过。

只输出 JSON，含 checks 数组，每项 change_id、supported 布尔值、reason 和需人工检查的位置；以及 unresolved 数组。必须覆盖每个 change_id 一次。不要输出“整体无误”替代逐项检查，不评分排名，不补写论文内容。无法支持的修改拒绝采纳。

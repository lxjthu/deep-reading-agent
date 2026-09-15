# 公共输入与盲评

benchmark prepare --task qa --workspace ... --entry-id ... --question ... --output common-plan.json 只保存公共输入、步骤和提示词哈希。API任务使用相同输入/options，记录provider、返回model、usage、elapsed_seconds、attempts和finish_reason。各模型只读取自身历史，不读取其他模型答案。

原生Codex不需要API Key。由平台支持的型号选择运行Luna；LUNA_TARGET_MODEL只是目标设置。记录平台选择证据与实际能得到的型号回执；未核实的型号明确标注。用量和费用缺失为null/unknown。

scripts/blind_review.py --runs <API-run-folder> ... --output <new-folder> 生成随机候选、独立映射和评分表；--native <answer.json> 可加入原生结果，但不推断其型号。评分项包括事实/数字/证据、任务/翻译完整与术语、格式可用性，初始为空，依据原文及人工抽查填写。

参评模型自己的核验不能决定胜负。原生与API上下文和计时不同；小样本不作稳定排名。保留失败、重试、无正文和截断记录。

原生完整任务使用 --provider native，由宿主按 native next/submit 逐轮推进，见 native.md。比较工具保留原生 elapsed_seconds=null；交接耗时不当作模型推理时间。原生型号为宿主声明或未知，不自动验证为 Luna。

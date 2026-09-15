# 使用命令

从技能目录执行；其他位置将 scripts/dra.py 换成绝对路径。工作区与技能目录分开。

```powershell
python scripts/dra.py doctor
python scripts/dra.py ingest folder --workspace D:/Research/workspace --input D:/Research/input
python scripts/dra.py library list --workspace D:/Research/workspace
python scripts/dra.py read --mode quant --workspace D:/Research/workspace --input D:/Research/paper.pdf --dry-run
python scripts/dra.py read --mode quant --workspace D:/Research/workspace --input D:/Research/paper.pdf --provider deepseek
python scripts/dra.py qa --workspace D:/Research/workspace --entry-id <id> --question "样本与研究方法是什么？"
```

| 任务 | 命令 |
|---|---|
| 导入提取 | ingest file/folder、extract；--input 文件或目录；PDF/MD/CNKI/WoS TXT；排除 .source.md |
| 精读 | read --mode quant/qual/long；默认 7/4/12 步；long 可选 --dimensions overview,theory |
| 筛选 | filter --mode explorer/reviewer/empiricist --topic ... --entry-id ...；原提示词 1–10 分 |
| 翻译 | translate --mode pdf-fulltext/md-chunks/abstract；摘要模式要求已有题录摘要 |
| 参考文献 | references extract/trace/style-analyze/format；规则用 --variables rules.json；references presets --input preset.json |
| 文献库 | library list/show/search/edit/tags/attachments/delete；search 用 --question，edit 用 --input JSON，tags 用 --text；软删除 |
| 元数据 | metadata extract/match/apply；匹配建议独立；apply 使用 --entry-id 和 --input JSON |
| 问答 | qa --question ...；原文证据回答后逐项核验；有未支持的条目时最多纠错并重核一次 |
| 卡片 | cards create/from-qa/list/edit/export；--selection 选段MD；edit 新建用户版；export --output 目录 |
| 跨文献 | compare / synthesize --topic ...；重复 --entry-id 或 --input 指定多篇 |
| 写作风格 | writing-style --mode single/batch |
| 研究 | research evidence/prioritize/constructs/gaps/ideas/session --topic ...；沿用源码确定性规则，输出候选 |
| 维度模板 | dimensions/templates list/import/export --name ...；templates generate 调用模型 |
| 库助手 | library ask/report/comment --question ...；ask 输出查询候选，不执行任意数据库语句 |
| 批量 | batch --task read.quant --entry-id id1 --entry-id id2 --limit 2；默认只运行1篇，串行；batch resume --run-id <batch_id> 继续未完成项 |
| 历史恢复 | jobs list/status/resume/cancel --run-id ...；resume 使用相同 provider |
| 提示词 | prompts list/show/check/set；--name quant.step_1；set --input MD |
| 数据 | data export --output backup.zip；data inspect/import --input backup.zip；导入目录必须为空 |
| 分发 | package --output 新目录；不复制 .env、test/、工作区和源码迁移脚本 |

--variables 接收普通 JSON 对象；模板只替换声明的 {name}，保留 JSON 示例括号。--prompt-overrides 是槽位 ID 到显式 MD 路径的映射。优先级：显式 MD > 工作区 prompts/<slot>.md > 内置 MD。

assets/workflows.json 是实际步骤定义。自定义维度通过 dimensions import --name <name> --input <definition.json> 明确采纳，read --mode long --dimension-set <name> 执行。代码中动态指令的迁移存档不代表已经执行。

返回码：0 成功或准备完成，2 输入/结构错误，3 缺配置，4 远端失败，6 批量部分失败。quality_status 独立于执行状态。

综述可用 --variables JSON 中的 secondary_references 数组提供候选二次文献，生成后核验实际引用编号。该步骤不证明引文事实正确，也不自动编造 GB/T 目录。

纯图片 PDF 可用 extract --tessdata <目录> --ocr-language eng 执行本地 OCR；目录须含 eng.traineddata。中文使用 chi_sim+eng，须具备两种语言数据。仅对无文字层页识别，记录语言数据哈希与物理页号；不会上传文件或覆盖 PDF。

模型任务统一支持 --provider native/deepseek/mimo。native 返回 waiting_for_native，由宿主按 native.md 完成消息交接；详细功能和完整命令示例见 ../README.md。

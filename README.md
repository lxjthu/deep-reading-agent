# Deep Reading Agent

独立的论文研究技能，支持 **DeepSeek / MiMo API** 和 **当前 Agent 原生模型** 两种入口。共用提示词、业务步骤、校验与工作区，不依赖原网站、前端或生产数据库。

## 1. 安装与选择入口

需要 Python 3.10+。解压到新目录后执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/dra.py doctor
```

下文 `python` 指安装了依赖的解释器；Windows 可以直接换成 `.venv/Scripts/python.exe`。其他系统使用其虚拟环境解释器。

| 入口 | 参数 | 配置 |
|---|---|---|
| 当前 Agent 模型 | `--provider native` | 不读 `.env`，不调用模型 API；需要宿主 Agent 读取文件、运行脚本并生成回答 |
| DeepSeek | `--provider deepseek` | `.env` 中填写 `DEEPSEEK_API_KEY` |
| MiMo | `--provider mimo` | `.env` 中填写 `MIMO_API_KEY` |

API 模式将 `.env.example` 复制为 `.env` 后填写对应密钥，不要覆盖已有配置。也可用 `--env <文件>`。原生模式跳过密钥配置。完整配置见 [configuration.md](references/configuration.md)。

`native` 使用宿主实际运行的模型，**不会自动切换成 Luna**。已知型号以宿主声明记录；未知时为空，不能凭配置文件声称使用了 Luna。原生用量和模型耗时未知时为空，交接等待时间单独记录。

技能目录只保存代码和内置提示词。用户材料、覆盖与结果放到显式 `--workspace` 指定的其他目录。以下示例使用 `D:/Research/workspace`，请按实际位置替换；`ENTRY_ID` 和 `RUN_ID` 使用命令返回的值。

## 2. 最简单的使用方式

把技能交给支持本地技能的 Agent，让它读取 [SKILL.md](SKILL.md)，直接提出任务：

> 使用 Deep Reading Agent 原生模式，对 D:/Research/paper.pdf 做七步精读，工作区使用 D:/Research/workspace。使用当前模型，保留证据和所有步骤结果。

Agent 按 [原生执行协议](references/native.md) 完成整个交接循环，用户无需逐轮复制提示词或整理 JSON。也可以指定「改用 DeepSeek API」或「用 MiMo 翻译全文」。普通终端不能自行提供原生模型回答。

```powershell
# 准备并检查，不调用模型
python scripts/dra.py read --mode quant --input D:/Research/paper.pdf --workspace D:/Research/workspace --dry-run

# API 模式自动执行全部步骤
python scripts/dra.py read --mode quant --input D:/Research/paper.pdf --workspace D:/Research/workspace --provider deepseek

# 原生模式准备首轮，后续由宿主 Agent 完成
python scripts/dra.py read --mode quant --input D:/Research/paper.pdf --workspace D:/Research/workspace --provider native
```

省略 provider 时默认 DeepSeek；用户选择当前 Agent 时必须显式传 `native`。所有模型工作流都可选择这些入口；本地导入、管理和迁移本身不调用模型。

## 3. 导入、原文与题录关联

支持 PDF、Markdown、CNKI/WoS TXT。导入保留原件副本，生成带物理页码、段落及字符偏移的提取结果。识别重复记录；原始题录仍保存。`*.source.md` 来源说明不作为论文正文。

```powershell
python scripts/dra.py ingest folder --input D:/Research/input --workspace D:/Research/workspace
python scripts/dra.py library list --workspace D:/Research/workspace
python scripts/dra.py extract --input D:/Research/paper.pdf --workspace D:/Research/workspace
```

先导入题录再导入全文，有唯一、严格标题匹配时自动关联，否则保留候选。重新 `extract` 会保存新提取版本，不覆盖论文。`metadata match` 只给匹配建议，`metadata apply` 修改题录元数据，不等于采纳全文关联。

纯图片页默认提示需要 OCR；可显式使用本地 Tesseract 语言数据：

```powershell
python scripts/dra.py extract --input D:/Research/scan.pdf --workspace D:/Research/workspace --tessdata D:/OCR/tessdata --ocr-language eng
```

语言目录须含 `eng.traineddata`；中文可用 `chi_sim+eng`，须同时安装两种语言数据。仅对无文字层页识别，记录数据哈希，不上传文件。含文字层不等于本次执行过 OCR。

末页混有其他论文摘要时，须先核对提取 JSON 的 `pages[].text`，准备排除数组并传 `--exclusions exclusions.json`：

```json
[{"page": 10, "start": 1200, "end": 1800, "reason": "经核对属于另一篇论文的摘要"}]
```

上述数字仅示范结构，必须改为实际物理页号和字符范围。被排除文字仍留存；检测到多篇摘要但没有排除记录时，研究任务会拒绝继续。

## 4. 筛选与三种精读

筛选模式：`explorer`、`reviewer`、`empiricist`，使用原业务提示词的 1–10 分与理由。缺摘要不虚构正文。

```powershell
python scripts/dra.py filter --mode explorer --topic "生态产品价值实现" --entry-id ENTRY_ID --workspace D:/Research/workspace --provider native
python scripts/dra.py read --mode qual --entry-id ENTRY_ID --workspace D:/Research/workspace --provider deepseek
python scripts/dra.py read --mode long --dimensions overview,methodology --entry-id ENTRY_ID --workspace D:/Research/workspace --provider native
```

`quant` 七步、`qual` 四步、`long` 默认十二个维度，保留必要历史。`--dimensions` 选择已有维度，`--dimension-set` 使用采纳的自定义维度。精读保存引文定位结果，未定位的引句会标记待核查。大多数任务超过 150,000 字符报错，不静默截断。

## 5. 全文及摘要翻译

`md-chunks`：术语表后按长度/段落分片，按原顺序合并；`pdf-fulltext`：全文术语表与重述两步；`abstract`：仅使用题录摘要，要求该字段存在。输入 PDF 时先提取正文。

```powershell
python scripts/dra.py translate --mode md-chunks --input D:/Research/paper.pdf --workspace D:/Research/workspace --provider mimo
python scripts/dra.py translate --mode abstract --entry-id ENTRY_ID --workspace D:/Research/workspace --provider native
```

原文、术语表、各分片和最终译文分别保存。数字与残留英文检查只是提示，不能证明逐句完整性。当前分片是本地长度/段落策略，不声称完整复刻原网站的章节检测流程。

## 6. 原文问答与卡片

问答以原文证据生成陈述并逐项核验，区分原文摘述、综合、知识拓展和推断。核验拒绝时最多纠错并重核一次；仍不支持的陈述不进入最终正文。`--continue-run` 保留历史。

```powershell
python scripts/dra.py qa --entry-id ENTRY_ID --question "研究方法、样本和数据年份是什么？" --workspace D:/Research/workspace --provider native
python scripts/dra.py qa --continue-run RUN_ID --question "作者如何检验稳健性？" --workspace D:/Research/workspace --provider native
python scripts/dra.py cards create --entry-id ENTRY_ID --selection D:/Research/selection.md --workspace D:/Research/workspace --provider deepseek
python scripts/dra.py cards from-qa --entry-id ENTRY_ID --run-id QA_RUN_ID --workspace D:/Research/workspace --provider native
python scripts/dra.py cards edit --entry-id ENTRY_ID --input D:/Research/edited-card.md --workspace D:/Research/workspace
python scripts/dra.py cards export --output D:/Research/cards --workspace D:/Research/workspace
```

选段是 Markdown 文件；省略选段时使用输入正文。问答转卡片创建新任务，不覆盖 QA。人工编辑新建用户版本。原生回答与核验通常由同一宿主完成，不是独立模型盲评。

## 7. 参考文献、引用追踪与格式

```powershell
python scripts/dra.py references extract --entry-id ENTRY_ID --workspace D:/Research/workspace --provider native
python scripts/dra.py references trace --entry-id ENTRY_ID --workspace D:/Research/workspace --provider deepseek
python scripts/dra.py references style-analyze --input D:/Research/style-example.md --workspace D:/Research/workspace --provider native
python scripts/dra.py references format --entry-id ENTRY_ID --variables D:/Research/format.json --workspace D:/Research/workspace --provider native
```

追踪先提取文献，再检查每条编号、正文引句及定位；不能把模型补写引句当作原文。格式化参数文件示例：

```json
{
  "rules": "此处填写或采纳目标期刊的实际格式规则",
  "references": [{"title": "文献标题", "authors": ["作者"], "year": 2024, "journal": "期刊"}]
}
```

没有 `rules` 会报错。省略 `references` 时使用选中文献的题录。`references presets --input preset.json` 保存含 `rules` 的规则；再次格式化须显式通过变量文件传入，不会自动采用最近预设。`--variables` 接收 JSON 文件路径，不是直接传 JSON 字符串。

## 8. 对比、综述与写作风格

```powershell
python scripts/dra.py compare --entry-id ID1 --entry-id ID2 --workspace D:/Research/workspace --provider native
python scripts/dra.py synthesize --entry-id ID1 --entry-id ID2 --entry-id ID3 --topic "生态产品价值实现机制" --workspace D:/Research/workspace --provider deepseek
python scripts/dra.py writing-style --mode single --entry-id ID1 --workspace D:/Research/workspace --provider native
python scripts/dra.py writing-style --mode batch --entry-id ID1 --entry-id ID2 --workspace D:/Research/workspace --provider native
```

对比/综述至少两篇；综述每次围绕一个主题或 `variables.dim_label`。批量写作风格先逐篇分析，再生成模仿建议、比较与报告。单篇模式使用完整正文，要求有可读原文。

综述可通过 `--variables` 中的 `secondary_references` 数组提供候选二次文献，之后核验实际引用的 S 编号。此步骤不自动生成完整 GB/T 7714 目录，也不证明引用事实正确。

## 9. 文献库与元数据

```powershell
python scripts/dra.py library search --question "生态产品" --workspace D:/Research/workspace
python scripts/dra.py library show --entry-id ENTRY_ID --workspace D:/Research/workspace
python scripts/dra.py library tags --entry-id ENTRY_ID --text "精读,生态" --workspace D:/Research/workspace
python scripts/dra.py library edit --entry-id ENTRY_ID --input D:/Research/entry-edit.json --workspace D:/Research/workspace
python scripts/dra.py metadata extract --entry-id ENTRY_ID --workspace D:/Research/workspace --provider native
python scripts/dra.py metadata apply --entry-id ENTRY_ID --input D:/Research/metadata.json --workspace D:/Research/workspace
```

`library edit` 允许 `title`、`metadata`、`notes`；传入的 `metadata` 对象会替换原对象。`metadata apply` 合并元数据字段，并保存改前记录。`library attachments` 显示附件记录；`library delete` 为软删除，保留源文件。

库助手 `library ask/report/comment --entry-id ... --question ... --provider native` 分别生成查询候选、报告和评论候选。查询候选不会变成任意数据库语句执行，评论也不会自动覆盖用户笔记。

## 10. 研究构思、维度和提示词

```powershell
python scripts/dra.py research ideas --entry-id ID1 --entry-id ID2 --topic "生态价值转化" --workspace D:/Research/workspace
python scripts/dra.py research session --entry-id ID1 --topic "生态价值转化" --workspace D:/Research/workspace
python scripts/dra.py dimensions list --workspace D:/Research/workspace
python scripts/dra.py dimensions import --name my-dims --input D:/Research/dimensions.json --workspace D:/Research/workspace
python scripts/dra.py read --mode long --dimension-set my-dims --entry-id ID1 --workspace D:/Research/workspace --provider native
python scripts/dra.py templates generate --entry-id ID1 --topic "研究框架" --workspace D:/Research/workspace --provider native
python scripts/dra.py prompts set --name quant.step_1 --input D:/Research/my-prompt.md --workspace D:/Research/workspace
python scripts/dra.py prompts check --workspace D:/Research/workspace
```

研究动作包括 `evidence/prioritize/constructs/gaps/ideas/session`，沿用源码确定性规则，输出候选，不是自动检索全领域的模型循环。session 保存证据准备状态，不代表完整网页提案状态机。

自定义维度文件使用 `dimensions` 数组，每项提供 `dim_name` 和 `prompt_content`（也接受已支持的 name/instruction 字段）；生成模板后，应审阅 `result.json` 中对应步骤的 `parsed`，取出定义保存为文件，再明确导入采纳。`templates import/export` 为模板存取。

提示词优先级：显式 `--prompt-overrides` 映射文件 > 工作区 `prompts/<slot>.md` > 内置 Markdown。缺模板或变量报错。`prompts show --name ...` 读取指定槽位；含变量时需 `--variables`。运行中修改模板会拒绝继续原检查点，应恢复原模板或另建任务。

## 11. 原生步骤、批量与恢复

原生启动返回 `waiting_for_native` 和 `native_request.request_path`。宿主 Agent 完整读取消息、生成回答并提交：

```powershell
python scripts/dra.py native next --workspace D:/Research/workspace --run-id RUN_ID
python scripts/dra.py native submit --workspace D:/Research/workspace --run-id RUN_ID --input D:/Research/response.json
python scripts/dra.py jobs status --workspace D:/Research/workspace --run-id RUN_ID
python scripts/dra.py jobs cancel --workspace D:/Research/workspace --run-id RUN_ID
python scripts/dra.py jobs resume --workspace D:/Research/workspace --run-id RUN_ID
python scripts/dra.py batch --task read.quant --entry-id ID1 --entry-id ID2 --limit 2 --workspace D:/Research/workspace --provider native
python scripts/dra.py batch resume --run-id BATCH_ID --workspace D:/Research/workspace --provider native
```

响应协议见 [native.md](references/native.md)。过期响应拒绝；无效回答可修正重交，历史提交保留。`jobs resume` 自动识别原生任务；API 恢复需同一 provider 和配置。原生批次的各论文请求由 Agent 依次处理，再恢复批次汇总状态。

批量默认仅 1 篇、串行处理，`--limit` 显式扩大。已完成论文和步骤不重复调用。没有分布式队列或后台自动唤醒；宿主上下文不足时必须说明限制，不能静默删减原文。

## 12. 数据、导出和在线依赖

```powershell
python scripts/dra.py artifacts list --workspace D:/Research/workspace
python scripts/dra.py artifacts export --output D:/Research/results.xlsx --workspace D:/Research/workspace
python scripts/dra.py data export --output D:/Research/backup.zip --workspace D:/Research/workspace
python scripts/dra.py data inspect --input D:/Research/backup.zip
python scripts/dra.py data import --input D:/Research/backup.zip --workspace D:/Research/restored
python scripts/dra.py search cnki --question "生态产品价值实现"
```

XLSX 导出结构化步骤字段；Markdown 结果在 `artifacts/`，运行和提示词记录在 `runs/`。备份输出放在工作区之外，导入目标须为空。支持本地包及网站 `.dra` 的受限导入；未知字段保留，部分嵌套 JSON ID 不重映射，不能当作生产数据库恢复。

搜索目前生成 CNKI/WoS/全文检索链接，不返回已检索到的文献。账号、共享和管理依赖外部网站，必须显式配置服务及令牌；没有生产默认值。用法和迁移限制见 [online.md](references/online.md)。

## 13. 输出状态与验证边界

`completed` 只代表执行完成，`quality_status` 单独记录。JSON 结构、引用编号、截断、提示词变化会检查；研究事实、完整翻译和术语仍需原文抽查。原生的 `waiting_for_native` 是正常交接状态。返回码：0 成功/准备/等待，2 输入或结构错误，3 缺配置，4 API 失败，6 部分失败。

已有真实材料导入、DeepSeek 核心任务和一页英文图片 OCR 测试；原生入口由当前宿主完成一条真实 WoS 摘要翻译。模型可能生成未定位引文和不受原文支持的解释，模型自检并不保证正确。当前 MiMo 测试曾返回 401，真实用户 `.dra`、在线服务与用户验收仍待验证。完整逐项状态见 [capabilities.json](assets/capabilities.json)，比较规则见 [comparison.md](references/comparison.md)。

```powershell
python -m unittest discover -s tests
python scripts/dra.py package --output ../deep-reading-agent-copy
```

分发包含 README，排除 `.env`、用户 `test/`、工作区和源码迁移工具。当前为可运行候选，尚无用户验收结论。


## 本地阅读与 OCR Markdown 清洗（新增）

新增功能完全位于本技能目录，不依赖 online 代码、数据库或部署。完成模型任务后可生成离线阅读快照：

```powershell
python scripts/dra.py reader build --workspace D:/Research/workspace
python scripts/dra.py reader build --entry-id ENTRY_ID --include-pdf --workspace D:/Research/workspace
```

双击返回的 `index.html`，使用文献搜索、报告类型筛选、目录、版本切换、证据、原稿对照、MD 下载和打印。默认不复制 PDF；`--include-pdf` 明确加入。每次构建新目录，可整体移动。详见 [离线阅读命令、输出与边界](references/reader.md)。

```powershell
python scripts/dra.py ocr guide --input paper.pdf --workspace D:/Research/workspace
python scripts/dra.py markdown import --input paddle-export --entry-id ENTRY_ID --source-url https://aistudio.baidu.com/paddleocr --workspace D:/Research/workspace
python scripts/dra.py markdown inspect --entry-id ENTRY_ID --workspace D:/Research/workspace
python scripts/dra.py markdown clean --entry-id ENTRY_ID --provider native --workspace D:/Research/workspace
python scripts/dra.py markdown adopt --run-id RUN_ID --workspace D:/Research/workspace
```

导入保留外部原件、图片和来源信息。原生/API 共用边界提案、标题提案和逐项核查，程序只应用允许的结构操作，生成 `clean.md`、修改清单、来源映射和校验记录。未知页码不推测；待核查、过期或被编辑的候选不能采纳。采纳后新研究使用清洗版本，旧任务来源冻结。详细参数、错误处理与恢复见 [Markdown 清洗](references/markdown-cleanup.md)。

PaddleOCR 网页由用户自行登录、转换和下载；技能不会上传论文或购买服务。本轮真实网站转换与新增清洗的真实 DeepSeek/MiMo 调用应与原生、本地、模拟和浏览器验收分开看，不能互相替代。功能仍需用户在自己的材料上验收。

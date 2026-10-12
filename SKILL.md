---
name: deep-reading-agent
description: 使用当前 Agent 原生模型或 DeepSeek/MiMo API，通过独立 Python 工作区导入论文与 CNKI/WoS 题录，执行多轮精读、翻译、证据问答、卡片及文献研究；完成读文献、逐篇方法与变量解析、已有数据核对和复现报告闭环；适用于本地研究及指定账号数据迁移。
---

# Deep Reading Agent

使用包内脚本执行任务。安装目录保存代码和内置提示词，用户原文、覆盖和产物放在显式指定的独立工作区。无需原网站代码、前端或数据库。

先运行 `python <skill>/scripts/dra.py doctor`。首次安装：`python -m pip install -r <skill>/requirements.txt`。Python 3.10+。

按需读取：

- 本机 OCR：处理本机 PDF/扫描件时，若存在 `references/paddleocr.local.md`，先读取该本地说明，使用已验证的升级入口；该配置仅适用于指定电脑，不随通用技能包分发。

- 用户说“我想看和某主题相关论文的精读对比”或要求打开原文、报告时，按 [离线阅读](references/reader.md) 的检索与展示流程定位已有产物，生成对应页面并用宿主浏览器打开。查看请求优先展示已有报告；缺失精读明确列出。缺少全文时，按该文档的下载交接流程提供候选题录、原文接收目录和续办指引，保存原问题以便下载后继续。

- [数据复现闭环](references/reproduction.md)：根据已核验论文方法检查用户数据、生成并实际运行 Stata/Python 程序、保存诊断，展示可下载代码与结果。缺软件或数据时交付可运行程序和缺项，明确未执行边界。

- [逐篇变量与方法](references/variables-and-methods.md)：提取各篇变量选择、测算/研究方法和具体复现步骤时使用；附原页证据、明确代码来源及未披露项，并可对接用户数据检查缺项。

- [离线阅读](references/reader.md)：构建可双击打开的文献与报告快照，PDF 仅按显式选项加入。
- [Markdown 清洗](references/markdown-cleanup.md)：接回外部 OCR、检查结构、生成候选及显式采纳；保留原稿与证据映射。
- [命令与流程](references/workflows.md)：选择任务与参数。
- [原生执行](references/native.md)：选择当前 Agent 时以 `--provider native` 启动，执行领取、回答、提交校验的循环直到完成，不需要 API Key。
- [配置](references/configuration.md)：模型、凭据及依赖。
- [输入输出](references/inputs-outputs.md)：证据、版本及恢复。
- [在线连接](references/online.md)：指定账号与数据迁移。
- [比较测试](references/comparison.md)：公共输入、原生模型和盲评。

统一入口：`python <skill>/scripts/dra.py <command> [action] --workspace <workspace> ...`。脚本按步骤读取 prompts/catalog.json 中的 Markdown，不必把整套提示词送入宿主上下文。模型任务可用 --dry-run 检查输入、步骤与缺项。

仅在已授权的服务及材料范围内调用模型。MiMo 和 DeepSeek 使用独立配置；.env 不会切换 Codex 型号。原生 Luna 必须由平台提供的执行方式指定并保留可获得的型号证据，不能冒充。

按命令返回的产物路径交付。精读保留前序轮次；超长输入、缺模板、变量错误和截断报错。AI 产物为候选，人工编辑创建新版本，不覆盖原件。

当前覆盖见 assets/capabilities.json；源码端点和工具映射见 assets/source_inventory.json。资源迁移、离线/模拟测试、真实调用、OCR/检索、数据迁移及用户验收分别判断。动态指令已存档不代表已绑定执行，模型调用成功不代表研究事实已通过验收。

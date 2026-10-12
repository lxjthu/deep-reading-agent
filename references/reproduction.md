# 读文献—方法解析—已有数据复现

用户要求按论文方法复现、检验手头数据、跑通指标测算或在前端展示代码时使用。论文和数据是每次任务的输入；不依赖作者电脑的路径、既有演示页面或其他已安装 Skill。

## 从证据到可运行方案

1. 用本技能导入/精读全文，按 [逐篇变量与方法](variables-and-methods.md) 核读公式、变量、单位、样本和估计设定。为每项方法记录文献 ID、物理页/行及作者披露程度，区分基准与稳健性方法。没有全文时给下载交接，不直接声称复现。
2. 只读用户数据与构造程序。检查工作表、Stata 标签、字段、年份、样本键唯一性、金额单位、缺失和有效值；大表先看表头与所需列。`scripts/reproduce.py inspect` 可输出 .dta/.xlsx/.csv 的字段与缺失字典，不向模型服务自动上传整份数据。
3. 在工作区 `replication/<研究主题>/` 保存字段映射、来源摘要、核读证据、口径选择、数据准备脚本和估计程序。配置和路径来自本次用户输入，以工作区为根或通过参数传入；禁止把机器路径写入通用 Skill。备份原数据，准备结果写新文件。
4. 缺项优先区分“字段不存在”“部分记录缺失”“需外部序列”“需口径选择”。用户允许先替代时再执行替代，保留原值、替代值、规则及覆盖数。指数 0 值、其他缺失、尾部年份分别处理；若没有有效前值，应记录替代/排除，不能虚构前一年。沿用同比指数与冻结价格水平的含义不同。不能把一个项目的 0 值规则设为所有未来项目默认。
5. 生成能独立重跑的 Stata `.do` 或 Python 程序。标明作者原代码、改编或 Agent 新写；注明依赖、字段与执行命令。不要把包内 TFP 模板套用到所有研究方法。逐步核对生产函数、代理变量、时序、分行业、缩尾、价格基期与样本筛选。软件接口按当前安装的官方/作者文档核对。
6. 本机有软件与必要数据时执行，不停在代码草稿。Stata 可以用本页包装器保存日志与退出状态；其他软件按同等规范运行。先小样本/低重复次数测试再按任务要求扩大，明确试跑与正式估计的区别。失败定位修复；小行业、矩阵奇异或无有效滞后等保留状态，不以 0 冒充结果。
7. 检验合并、筛选计数、价格正值、结果有限性与输出公式一致性。查看收敛日志、异常系数、敏感性和与论文描述统计的差异。程序返回 0 只代表执行，不能证明估计可信。未执行、部分完成、替代试跑和正式复现分别说明。
8. 交付前端报告、完整代码下载、数据结果和日志。报告说明方法来源、变量、转换、样本流失、替代、软件、实际参数、诊断及限制；代码必须可见，不只有下载链接。保留原文证据新窗口和原件页定位；不要把跨行业尺度不同的 TFP 直接用于统一排名。

## 可移植工具

安装可选依赖：`python -m pip install -r requirements-reproduction.txt`。Stata 需用户另行安装并拥有可用许可；本工具不下载或破解 Stata。执行文件由 `--stata` 或 `STATA_BIN` 指定；缺软件时交付程序、数据准备与报告，明确没有执行估计。

```sh
python scripts/reproduce.py inspect --input .../research/data/raw/company.dta --output .../research/workspace/replication/fields.json
python scripts/reproduce.py inspect --input .../research/data/prices/indices.xlsx --sheet 原始数据 --output .../research/workspace/replication/price-fields.json
python scripts/reproduce.py run-stata --stata <stata-executable> --code .../research/workspace/replication/analysis.do --input .../research/workspace/replication/firm_panel.dta --output .../research/workspace/replication/run-001
```

`run-stata` 只在新的输出目录执行可信的、经 Agent 核对的程序；显式输入文件复制进去，程序使用相对路径。它不是运行任意论文附件的安全沙箱。不要在传入程序里关闭包装器日志或 `exit, clear`；错误须传回。完成状态同时要求进程结束和日志中的实际 Stata 返回码为 0。输出名应区分不同运行，避免覆盖。包装器超时停止其启动的进程并保留部分结果。

对于 TFP，可从 `assets/reproduction/tfp_lp.do` 开始；先按文献准备 `firm_panel.dta`：firm_id/year/industry、ln_Y/ln_K/ln_L/ln_M、eligible 及来源标记。所有对数必须来自核对后的实际产出/投入，价格调整在准备程序中显式完成。模板采用 LP 总产出 Cobb–Douglas 与 OLS；行业门槛是示例，默认 100 次重复抽样。OP/增加值/ACF/其他方法需要另写匹配论文的程序。prodest 不随包分发，在 Stata 运行 `ssc install prodest`，记录版本并检查预测接口；作者源码：https://github.com/GabrieleRovigatti/prodest 。

## 前端报告和代码

将 Agent 撰写的 report.md、代码和需要交付的结果放在同一研究工作区，执行：

```sh
python scripts/reproduce.py report --workspace .../research/workspace --markdown .../research/workspace/replication/report.md --code .../research/workspace/replication/analysis.do --result .../research/workspace/replication/run-001/industry_diagnostics.csv --evidence .../research/workspace/replication/evidence.json
```

`--code`、`--result` 可重复，`--evidence` 可省略。证据 JSON 示例：

```json
[{"label":"论文方法：原 PDF 第4页","path":"sources/paper-id/original.pdf","fragment":"page=4"}]
```

证据文件必须在工作区内；仅将用户已要求展示的 PDF/原页图片显式加入报告。生成器构建新的文献库快照，首页导航加入“数据复现”，页面保留目录、表格、公式、完整代码块和下载。小附件内嵌下载数据，较大结果保留本地文件入口；必要时用本技能 reader serve 通过本地服务下载大文件。原文证据独立窗口打开；PDF 显示指定物理页的原页图像，并保留原 PDF 对应页链接。构建目录整体复制后仍可阅读；需要 rerun 时带上输入数据、字段映射和相对路径程序，只有页面快照不等于可复现的数据包。

浏览器验收至少检查代码可见、文件下载、原文新窗口页定位和窄屏表格。报告 Markdown 经过原有安全清洗，可信证据另由受限本地映射加入，不放宽任意 HTML 或链接。

每次收尾明确材料覆盖、运行软件、实际结果、替代范围和下一步。上传、发表或分享用户数据仍需用户针对该目的地授权；发布通用 Skill 只包含代码/模板/指引，排除用户材料、执行记录和本机配置。

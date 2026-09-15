# OCR Markdown 导入与结构清洗

本地命令不调用生产网站、数据库或 OCR 云服务。清洗复用原有 pipeline、检查点和 native / DeepSeek / MiMo 客户端；模型仅提议结构操作，程序生成候选正文。

## 导入与检查

```powershell
python scripts/dra.py ocr guide --input paper.pdf --workspace D:/Research/workspace
python scripts/dra.py ingest --input paper.pdf --workspace D:/Research/workspace
python scripts/dra.py markdown import --input paddle-export --entry-id ENTRY_ID --source-url https://aistudio.baidu.com/paddleocr --workspace D:/Research/workspace
python scripts/dra.py markdown inspect --entry-id ENTRY_ID --workspace D:/Research/workspace
```

`ENTRY_ID` 使用已有文献 ID。只有 Markdown 时也可先 `ingest --input paper.md` 创建条目，再用 `markdown import` 登记外部来源。输入支持单 MD 或解压目录；多页文件需明确命名 `page_1.md`、`page_2.md` 等，按数字排序。未知顺序会拒绝导入，请根据原始导出页信息整理命名；不要猜页码。当前不接受任意 ZIP。单个普通文件页码为未知。印刷页与物理页分开存储，未提供时为空。

原下载文件按字节保存，规范文本记录解码和换行归一化方式。仅复制所引用的本地图片，越界路径和符号链接拒绝；外部图片不请求，缺图、缺页和重复页会列为问题。不要把本地 PDF 提取的派生文件声明为 PaddleOCR 网站导出。来源 URL 是用户声明，不能证明网站实际转换过该论文。

`ocr guide` 检查文字层和明显乱码，给出本地 OCR 配置状态。文字层存在不能证明双栏顺序、公式或识别文字可靠。需要重新识别时可自行打开 [PaddleOCR](https://aistudio.baidu.com/paddleocr)，转换后保留 Markdown、图片和分页元信息。技能不会自动登录、上传或购买服务；网页按钮位置、额度和费用尚未验证。

## 清洗与采纳

```powershell
python scripts/dra.py markdown clean --entry-id ENTRY_ID --provider native --workspace D:/Research/workspace --dry-run
python scripts/dra.py markdown clean --entry-id ENTRY_ID --provider native --workspace D:/Research/workspace
python scripts/dra.py markdown adopt --run-id RUN_ID --workspace D:/Research/workspace
```

原生执行遵循 [native.md](native.md)，宿主 Agent 完成三次 next/submit 交接：边界提案、全局标题提案、逐项核查。普通终端不会自动生成原生回答。API 使用 `--provider deepseek` 或 `--provider mimo`，沿用 `.env` / `--env` 配置。原生入口不读取密钥。`--dry-run` 返回计划，不创建成功产物。

允许动作：`join_blocks`、`normalize_boundary_whitespace`、`remove_layout_block`、`set_heading_level`、`normalize_heading_whitespace`。操作包含原块 ID、预期哈希、理由及来源依据；边界合并只能指定 empty / space / newline 分隔符，不能传任意替换正文。标题操作保留非空白文字。表格、公式、代码、脚注、图题等保护块不得直接改写。无法确定的英文断词、括号、OCR 错字、表格错位保留原样并列为待核查。

输出位于 `sources/ENTRY_ID/versions/clean-RUN_ID/`：

- `clean.md`：清洗候选正文。
- `changes.json`：修改前后片段、类型、理由与原范围。
- `source-map.json`：清洗位置到原稿块范围及页信息的映射。
- `validation.json`：确定性检查、逐项模型核查和待核查问题。
- `manifest.json`、`document.json`：来源版本、父稿哈希、附件哈希和下游证据。

任务 completed 表示候选已持久化，不表示已采纳或论文事实正确。含 unresolved 或校验失败的候选拒绝采纳。通过全部检查且任务已授权使用清洗稿时，Agent 可执行 adopt；无需对每项结构改动重复提问。采纳比对当前父版本和哈希，拒绝过期候选。原始文件、人工稿、旧 run 冻结的来源不覆盖。

中断后使用 `native next` 或 `jobs resume`；截断、错误 JSON、虚构块 ID、重叠修改、缺少逐项核查均不能完成。修正当前响应重交，保留历史提交。完整候选再次执行不重复应用修改。人工编辑父稿后，应基于新稿新建任务。

## 边界

这是一套保守的结构清洗工具。它不纠正研究结论、数字、公式或 OCR 表格内容，也不保证恢复所有复杂排版。未知页码保持未知；清洗后的引句明确注明清洗版本与原范围，不声称是 PDF 逐字原句。缺页、缺图、表格错位等问题需要重新识别或核对原文。`.dra` 工作区导出/导入保留全部来源版本、采纳状态与映射。

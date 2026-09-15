# 配置

将 .env.example 复制为技能目录 .env，填写 MIMO_API_KEY、DEEPSEEK_API_KEY。也可 --env 指定文件。只读该配置，不向上寻找仓库/生产配置；同名环境变量优先。相对路径基于配置文件所在目录。

密钥在创建模型客户端时读取，不能写入命令行、提示词或产物。doctor 不调用网络。运行清单只记录配置来源、服务地址、型号与限额。

MiMo auto：tp- 使用 Token Plan，其他 Key 使用 PAYG；显式模式为 payg/token-plan。独立使用两家 Key。401/403 不重试；429/5xx/网络错误按上限重试。网络中断可能已发生远端用量。

默认串行、重试1次、超时180秒、单次输出8000 tokens；批量默认1篇，扩大用 --limit。DRA_API_THINKING=disabled 沿用原系统业务调用方式，不控制原生 Codex。API model 以配置和实际响应分别记录。

核心依赖 PyMuPDF/httpx/openpyxl。PDF 提取读取文字层，含图提示不等于 OCR。纯图页报告 ocr_required；可显式指定 --tessdata 和 --ocr-language 执行 PyMuPDF/Tesseract 本地 OCR。语言数据由用户安装（tesseract-ocr/tessdata_fast），不随技能分发。未配置时不会静默发往外部 OCR 服务。

使用 package 生成不含密钥和用户输入的分发目录。

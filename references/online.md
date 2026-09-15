# 可选在线连接

search cnki/wos/fulltext/crossref --question ... 返回检索入口，未取得实际检索结果或全文。

online --base-url <server> --endpoint /api/... --method GET 使用固定路径，凭据从 DRA_ONLINE_TOKEN 读取。没有生产默认地址；远程认证要求HTTPS，禁止认证跳转。写请求要显式 --allow-write，并在用户授权内。通用连接器不代表账号/管理/分享/部署契约已经验收。

prompts export-online --base-url ... --workspace ... 逐槽读取指定账号的用户、系统、有效版本，保存独立JSON，不自动覆盖本地。没有导出时仅迁移仓库内置提示词。

data inspect/import 识别网站 format_version=1，字段映射源版本027。拒绝危险路径、链接、重复路径和混合owner。原始表、字段和附件保留；普通外键在 imports/mapped 重映射，本地索引关联原文。JSON业务字段内ID、部分网页状态仍保留原值并记录边界。真实 .dra 未提供时，只能验收合成样本，不得宣称真实账号迁移通过。

不连接生产库，不发起部署。在线业务使用远端有效提示词，除非其接口明确支持单次覆盖。

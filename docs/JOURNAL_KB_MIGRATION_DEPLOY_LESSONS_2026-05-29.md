# AI 助手顶刊名录改动的数据库迁移与部署经验教训

> 相关入口：
> - 返回总入口：[../AGENTS.md](../AGENTS.md)
> - 手动部署 Runbook：[MANUAL_DEPLOY_AFTER_CODE_CHANGES.md](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md)
> - 部署架构说明：[DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md)

## 背景

本次改动为 AI 文献助手新增：

- 独立 `journal_kb` prompt type
- `top_tier_registry` 顶刊名录槽位
- AI 助手页可编辑顶刊名录
- 运行时按顶刊名录解析期刊层级并参与优先排序

上线过程中同时踩到了前端静态资源、后端代码覆盖、Alembic 实际连接库、以及生产 PostgreSQL 约束未升级等一串问题，值得单独记录。

## 现象

上线后先后出现了几类问题：

- 线上 AI 助手页仍显示旧布局，左边栏没有按预期出现
- 顶刊名录接口先返回 `400 invalid prompt slot: journal_kb.top_tier_registry`
- 之后又返回 `500 Internal Server Error`
- 日志里出现：
  - `prompt_templates` 的 `ck_prompt_templates_type` CHECK 约束违反
  - `journal_kb` 无法插入系统默认 prompt

## 根因拆解

### 1. 前端 `dist` 实际没有覆盖到线上最新版本

表现：

- 首页仍在引用旧资源文件名
- 浏览器拿到的是旧版 `index.html`
- 即使后端代码更新了，前端 UI 仍表现为旧样式

原因：

- 前一次部署中，静态资源覆盖不完整
- 浏览器缓存又进一步放大了“看起来没生效”的错觉

结论：

- 部署前端时，必须明确检查线上 `frontend/dist/index.html`
- 必须确认它引用的是本次构建出的最新 `assets/index-*.js` 与 `assets/index-*.css`

### 2. 服务器磁盘上的 `backend/prompt_registry.py` 仍是旧版

表现：

- `/api/prompts/item?type=journal_kb&key=top_tier_registry` 返回 `400`
- 错误为 `invalid prompt slot`

原因：

- 生产机上的 `backend/prompt_registry.py` 实际没有包含 `journal_kb`
- 前端已经开始请求新槽位，但后端槽位注册文件没有同步覆盖

结论：

- 涉及新增 prompt slot 时，必须把以下文件视为一组原子变更一起部署：
  - `backend/prompt_registry.py`
  - `backend/prompt_service.py`
  - `backend/routers/prompts.py`
  - 对应 prompt 文件目录

### 3. Alembic 在服务器上“成功执行”，但实际连的是 SQLite

表现：

- `alembic current`/`upgrade head` 看起来成功
- 版本也显示升到了最新
- 但生产接口仍然因为 PostgreSQL CHECK 约束报错

原因：

- 服务器上直接执行 `cd backend && alembic -c alembic.ini ...` 时，`backend/db/session.py` 读取的是当前 shell 环境
- 如果没有显式加载 `.env.production`，`DATABASE_URL` 会回退到本地 SQLite
- 于是 Alembic 实际升级的是 SQLite，而不是 systemd 运行中的 PostgreSQL

结论：

- 在本项目中，**“Alembic 成功”不等于“生产 PostgreSQL 已升级”**
- 运行迁移前，必须先确认当前 shell 已加载 `.env.production`
- 更稳妥的核验方式是：
  - 查看 `.env.production` 中的 `DATABASE_URL`
  - 升级后直接连生产 PostgreSQL 检查 `alembic_version`
  - 或直接验证关键约束/字段是否真的存在

### 4. systemd 启动正常，不代表数据库 schema 已正确

表现：

- 服务可以 `active`
- 健康检查 `/api/deploy/runtime` 返回 `200`
- 但业务接口仍然 `500`

原因：

- 本次错误出在“懒加载顶刊名录时写入默认 prompt”这条业务链路
- 启动阶段虽然打印了 `[prompt-seed] skipped`，但服务没有崩
- 所以健康检查通过，只能说明 API 进程活着，不能说明业务 schema 正确

结论：

- 部署验证必须分三层：
  - 进程层：`systemctl is-active`
  - 页面层：`GET /` 与静态资源
  - 业务层：点实际新功能接口

## 本次最终修复方式

最终采取了下面几步，问题才彻底闭环：

1. 单独覆盖最新前端 `frontend/dist`
2. 直接核对线上 `index.html` 引用的资源文件名
3. 单独覆盖后端关键文件，而不是只相信之前的压缩包
4. 补齐 `prompts/journal_kb/top_tier_registry.md`
5. 明确识别出 Alembic 实际跑到了 SQLite
6. 直接对生产 PostgreSQL 修正 `ck_prompt_templates_type`
7. 将 `alembic_version` 同步到 `024_add_journal_kb_prompt_type`
8. `systemctl restart deepreading-api`
9. 再检查顶刊名录真实接口是否恢复

## 以后同类改动的部署检查清单

### A. 新增 prompt type / prompt slot 时

- 同步修改：
  - `backend/db/models.py`
  - Alembic migration
  - `backend/prompt_registry.py`
  - `backend/prompt_service.py`
  - `backend/routers/prompts.py`
  - 对应 `prompts/.../*.md`
- 本地先验证：
  - `/api/prompts/item`
  - `/api/prompts/my`
  - `/api/prompts/system`

### B. 部署到生产前

- `npm run build`
- 准备最小上传文件集
- 如果有 schema 变更，明确标记“需要迁移”

### C. 服务器执行迁移时

- 不要只执行裸 `alembic`
- 必须先让当前 shell 使用 `.env.production`
- 迁移后不要只看命令退出码，要继续核验：
  - 目标库是不是 PostgreSQL
  - `alembic_version` 是否已变更
  - 新增约束/字段是否真的存在

### D. 部署完成后

- 检查 `systemctl is-active deepreading-api`
- 检查 `GET /api/deploy/runtime`
- 检查 `GET /`
- 检查线上 `frontend/dist/index.html`
- 检查新业务接口，不要只看首页能打开

## 建议固化为团队约定

- 约定 1：凡是生产库为 PostgreSQL、而本地默认可回退 SQLite 的脚本，执行时必须先确认当前 shell 环境
- 约定 2：新增 prompt type 视为“数据库变更 + 后端注册表变更 + prompt 文件变更”的组合改动，禁止只传其中一部分
- 约定 3：部署验收至少包含一个“命中新功能接口”的真实请求
- 约定 4：遇到“前端看起来没生效”，优先查线上 `index.html` 和静态资源文件名，不要先怀疑 React 代码本身

## 对 AGENTS.md 的反向链接说明

本复盘文档已经在 [../AGENTS.md](../AGENTS.md) 的部署说明与文档导航中登记，后续涉及：

- 新增 prompt type
- 数据库 CHECK 约束
- SQLite / PostgreSQL 环境切换
- 手动部署后页面与接口不一致

优先回看本文，再执行实际修复。

---

## 2026-05-31：双 routers/ 目录导致部署改动不生效

### 现象

连续多次部署 `backend/routers/translation.py` 的改动（新增 `has_translation` 查询、嵌入 `artifacts`），线上始终返回旧数据。用 `compileall` 检查无语法错误，服务重启正常，但 API 响应不变。

### 排查过程

1. 在代码中加入 `logger.warning(...)` 调试日志 → 部署后日志**不出现**
2. 用 `python -c "from routers.translation import router; ..."` 在服务器上测试 → 路由存在但代码是旧版
3. 发现服务器上存在**两个** `routers/` 目录：
   - `/root/deep-reading-agent/routers/`（项目根，旧副本）
   - `/root/deep-reading-agent/backend/routers/`（一直在更新的）
4. 检查 `backend/main.py`：
   ```python
   sys.path.insert(0, str(Path(__file__).parent.parent))
   ```
   项目根目录被插入 `sys.path[0]`，优先级高于 `backend/` 目录。

### 根因

`main.py` 将项目根目录 `/root/deep-reading-agent` 插入 `sys.path[0]`，使 Python 的模块搜索顺序变为：

1. `/root/deep-reading-agent`（项目根）
2. `/root/deep-reading-agent/backend`（uvicorn 工作目录）

`from routers import translation` 时，Python 先找到根目录的 `routers/translation.py`（旧副本），直接使用，不再查找 `backend/routers/translation.py`。

**受影响文件**（根目录存在旧副本）：`filter.py`、`reading.py`、`references.py`、`translation.py`

其他 router（如 `admin.py`、`upload.py`）只存在于 `backend/routers/`，不受影响。

### 修复

部署时必须同步到根目录：

```bash
cp backend/routers/translation.py routers/translation.py
rm -f routers/__pycache__/*.pyc backend/routers/__pycache__/*.pyc
```

### 教训

- `sys.path.insert` 可以静默改变模块加载顺序，导致看似正确的部署实际运行旧代码
- **调试日志不出现**是判断「代码未被加载」的关键信号（不是代码有 bug，是代码没被执行）
- `.pyc` 缓存可能掩盖 `.py` 文件的更新，部署时应清除 `__pycache__/`
- 部署 checklist 应包含「检查是否有同名模块在其他路径下」

---

## 2026-06-01：PostgreSQL 时区类型不匹配导致文献库挂载 Markdown 500

### 现象

文献库页面点击"挂载 Markdown"上传文件后，接口返回 `500 Internal Server Error`。

日志报错：
```
sqlalchemy.exc.DBAPIError: can't subtract offset-naive and offset-aware datetimes
```

### 排查过程

1. 查看服务器错误日志 `/var/log/deepreading/api-error.log`
2. 定位到 `backend/routers/library.py` 第 974 行 `await db.commit()`
3. 分析 SQL 参数：`updated_at` 字段传入了 `datetime.datetime(2026, 6, 1, 7, 31, 19, tzinfo=datetime.timezone.utc)`
4. PostgreSQL 的 `TIMESTAMP WITHOUT TIME ZONE` 列不接受带时区的 datetime

### 根因

`upload_entry_markdown` 函数使用了 `datetime.now(UTC)` 创建带时区的 datetime，但数据库字段定义为 `TIMESTAMP WITHOUT TIME ZONE`。

项目中其他地方都使用 `utcnow_naive()` 函数（返回不带时区的 datetime），唯独此处遗漏。

```python
# 错误写法（带时区）
entry.updated_at = datetime.now(UTC)

# 正确写法（不带时区）
entry.updated_at = utcnow_naive()
```

### 修复

1. `backend/routers/library.py` 第 973 行：`datetime.now(UTC)` → `utcnow_naive()`
2. `backend/routers/library.py` 第 1190 行：同样修复（AI 评论更新）
3. `backend/routers/compare.py` 第 1945、2050 行：同样修复（阅读笔记编辑、批注更新）

### 教训

- PostgreSQL 的 `TIMESTAMP WITHOUT TIME ZONE` 和 `TIMESTAMP WITH TIME ZONE` 是不同类型，不能混用
- 项目中应统一使用 `utcnow_naive()` 函数，避免直接使用 `datetime.now(UTC)`
- 本地 SQLite 对时区不敏感，无法发现此类问题；只有在 PostgreSQL 生产环境才会暴露
- 建议：代码审查时检查所有 `datetime.now(UTC)` 的使用场景，确认是否需要 `.replace(tzinfo=None)`

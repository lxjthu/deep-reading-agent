# 新服务器与 SQL 数据库维护指南

> 适用服务器：`http://8.162.14.154:18080/`  
> 适用分支：`codex/deepreading-empty-postgres-deploy`，可作为这台服务器的专用维护分支  
> 最后更新：2026-05-26

## 1. 当前部署形态

这台服务器是新的线上环境，不再沿用旧文档里的 `/root/.openclaw/workspace/deep-reading-agent` 路径和 Webhook 自动部署链路。

| 项目 | 当前值 |
|------|--------|
| 外网入口 | `http://8.162.14.154:18080/` |
| SSH | `ssh root@8.162.14.154` |
| 项目目录 | `/root/deep-reading-agent` |
| 后端监听 | `127.0.0.1:18000` |
| Nginx 监听 | `18080` |
| 后端 venv | `/root/deep-reading-agent/venv` |
| 当前日志 | `/var/log/deepreading/api.log` 和 `/var/log/deepreading/api-error.log` |
| 数据库 | 通过 `DATABASE_URL` 指向 SQL 数据库（`.env.production` 配置），生产环境不要回退到 SQLite |
| 服务管理 | `systemctl restart deepreading-api`（systemd 管理，service 文件：`/etc/systemd/system/deepreading-api.service`） |

Nginx 通过 `/etc/nginx/conf.d/deepreading-18080.conf` 将 `18080` 反代到 `127.0.0.1:18000`。SSE 相关接口需要保持 `proxy_buffering off`，否则任务进度流式返回会被缓冲。

## 2. 这条分支能否设为服务器专用

可以。建议把 `codex/deepreading-empty-postgres-deploy` 定位为这台新服务器的环境维护分支。

适合放在这条分支里的内容：

- 新服务器适配代码；
- PostgreSQL/SQL 数据库兼容修复；
- Nginx/SSE、启动方式、日志路径等部署文档；
- 只对这台服务器有效的运维脚本模板，但不包含密钥。

不应该放进分支的内容：

- `.env`、明文 `DATABASE_URL`、数据库密码、API Key；
- 生产数据库导出文件、用户上传文件、日志大文件；
- 未验证的一次性临时改动；
- 会破坏通用主线的服务器私有假设。

推荐工作流：

```powershell
# 日常在服务器专用分支维护
git switch codex/deepreading-empty-postgres-deploy

# 从主线同步通用功能时，优先 merge 或 rebase，再本地验证
git fetch origin
git merge origin/main

# 推送前运行必要检查
python -m unittest backend.tests.test_queue_manager
cd frontend
npm run lint
npm run build
```

如果这条分支会长期服务生产环境，建议在 GitHub 上保护它，至少要求：

- 禁止 force push；
- 合并前检查构建或人工确认；
- 数据库 migration 必须随 `backend/db/models.py` 和 `docs/DATABASE_SCHEMA.md` 一起更新。

## 3. 手动部署流程

当前没有可靠的 Webhook 自动部署记录，按手动部署维护。

### 3.1 上传单个或少量文件

适合小修小补，例如只修改后端 router：

```powershell
scp backend\routers\filter.py backend\routers\reading.py backend\routers\references.py backend\routers\translation.py root@8.162.14.154:/root/deep-reading-agent/routers/
```

注意：远端当前运行目录是 `/root/deep-reading-agent`，其中 router 文件位于 `/root/deep-reading-agent/routers/`，不是本地的 `backend/routers/` 结构。

### 3.2 重启后端

使用 systemd 管理后端服务，**必须用 systemctl 重启，不要手动 nohup uvicorn**，否则会丢失 PostgreSQL 配置：

```bash
ssh root@8.162.14.154
systemctl restart deepreading-api
```

systemd service 文件路径：`/etc/systemd/system/deepreading-api.service`

启动命令和环境变量（含 `DATABASE_URL`）均由 service 文件管理。`.env.production` 位于 `/root/deep-reading-agent/.env.production`，systemd 启动时自动加载。

如果使用旧命令把日志写到 `/tmp/fastapi.log`，可能和当前进程实际日志路径不一致。优先查看 `/var/log/deepreading/`。

## 4. 部署后验证

每次部署后至少做以下检查。

### 4.1 进程和端口

```bash
ssh root@8.162.14.154
ps -ef | grep 'uvicorn main:app' | grep -v grep
ss -ltnp | grep 18000
```

正常状态应看到 uvicorn 进程，并且 `127.0.0.1:18000` 正在监听。

### 4.2 后端本机 HTTP

```bash
curl -sS -o /tmp/health.out -w '%{http_code} %{time_total}\n' http://127.0.0.1:18000/
```

正常返回应为 `200`。

### 4.3 外网 Nginx

```powershell
curl.exe -sS -o NUL -w "%{http_code} %{time_total}\n" http://8.162.14.154:18080/
```

正常返回应为 `200`。

### 4.4 日志

```bash
tail -n 100 /var/log/deepreading/api.log
tail -n 100 /var/log/deepreading/api-error.log
```

如果看到旧进程关闭时的异常栈，要结合日志中的 `Started server process`、`Application startup complete` 和时间顺序判断是否仍是当前问题。

## 5. SQL 数据库维护

应用通过 `backend/db/session.py` 读取 `DATABASE_URL`：

- 如果设置了 `DATABASE_URL`，后端使用对应 SQL 数据库；
- 如果没有设置，会回退到 `db/app.sqlite`；
- 生产环境必须确保 `DATABASE_URL` 存在，避免误写 SQLite。

### 5.1 数据库 URL 约定

异步应用使用：

```text
postgresql+asyncpg://...
```

Alembic migration 会在 `backend/migrations/env.py` 中自动转换为同步驱动：

```text
postgresql+psycopg2://...
```

不要把完整 `DATABASE_URL` 写入文档、提交到 Git，或粘贴到聊天记录。排查时只记录数据库类型、主机和库名等脱敏信息。

### 5.2 数据库变更流程

凡是改表、字段、约束、索引或用户数据结构，必须同步修改：

- `backend/db/models.py`
- `backend/migrations/versions/*.py`
- `docs/DATABASE_SCHEMA.md`
- 如涉及用户数据导入导出，还要检查 `backend/services/data_portability.py`

检查点：

- `CURRENT_SCHEMA_VERSION` 是否与最新 migration 编号一致；
- 新用户数据表是否加入 `.dra` 导出/导入顺序；
- 自增主键和跨表引用是否有 id remap 逻辑。

### 5.3 运行 migration

在服务器执行：

```bash
cd /root/deep-reading-agent/backend
source ../venv/bin/activate
python -m alembic upgrade head
```

运行前建议先备份数据库。不要在没有备份的情况下执行破坏性 migration。

## 6. 本次部署修复记录

2026-05-26 本分支已部署以下后台线程事件循环修复：

- `routers/references.py`：`run_reference_trace_task`
- `routers/reading.py`：`run_long_context_task`、`run_quant_task`、`run_qual_task`、`_try_extract_references`
- `routers/translation.py`：`_run_translation_task`
- `routers/filter.py`：`run_filter_task`

修复目标：避免后台线程中反复使用 `asyncio.run()`，改为在线程内创建独立 event loop 并用 `loop.run_until_complete(...)` 执行异步数据库操作。

部署后验证结果：

- 本地指定文件无 `asyncio.run(` 残留；
- 远端已部署的 `filter.py`、`reading.py`、`references.py`、`translation.py` 无 `asyncio.run` 残留；
- 远端 uvicorn 已重启；
- `http://127.0.0.1:18000/` 返回 `200`；
- `http://8.162.14.154:18080/` 返回 `200`。

## 7. 常见风险

### 7.1 本地结构和远端结构不同

本地 router 文件位于：

```text
backend/routers/*.py
```

远端当前部署路径为：

```text
/root/deep-reading-agent/routers/*.py
```

上传文件前务必确认目标路径，避免把文件传到不会被 uvicorn 加载的位置。

### 7.1.1 已知问题：远端存在两套 router 路径

2026-05-26 排查发现，当前服务器同时存在：

```text
/root/deep-reading-agent/backend/routers/reading.py
/root/deep-reading-agent/routers/reading.py
```

当前 uvicorn 进程命令显示为：

```text
python -m uvicorn main:app --host 127.0.0.1 --port 18000
```

但进程工作目录实际是：

```text
/root/deep-reading-agent/backend
```

因此 `main:app` 实际加载的是：

```text
/root/deep-reading-agent/backend/main.py
```

而 `backend/main.py` 里有：

```python
sys.path.insert(0, str(Path(__file__).parent.parent))
from routers import reading
```

这会让 Python 优先从项目根目录导入 `routers/reading.py`。也就是说，虽然 FastAPI 入口在 `backend/main.py`，实际 `from routers import reading` 大概率使用的是根目录 `routers/reading.py`，不是 `backend/routers/reading.py`。

当前临时维护策略：

- 涉及 `reading.py` 的线上热修，必须同时同步到两处；
- 当前两份 `reading.py` 已用 `cmp` 确认一致；
- 不要在功能验证过程中删除任意一份，避免线上导入路径变化导致服务不可用。

后续应单独做一次“部署结构归一化”：

1. 将启动命令改为从项目根目录运行 `uvicorn backend.main:app`；
2. 将 `backend/main.py` 中的 router 导入改成明确的 `from backend.routers import ...`；
3. 检查 `db`、`services`、`routers` 等导入路径，统一使用 `backend.*` 或在启动脚本中固定 `PYTHONPATH`；
4. 验证所有 API 路由注册完整；
5. 删除或归档根目录兼容副本 `routers/`，避免以后部署混淆。

### 7.2 生产环境误回退 SQLite

如果 `DATABASE_URL` 丢失，代码会按默认逻辑使用：

```text
db/app.sqlite
```

这会导致生产数据写入错误位置。排查数据库异常时，第一步确认当前进程是否加载了正确的数据库配置，但不要输出明文密码。

### 7.3 日志路径和旧文档不一致

旧文档提到 `/tmp/fastapi.log`。当前进程实际 stdout/stderr 指向：

```text
/var/log/deepreading/api.log
/var/log/deepreading/api-error.log
```

后续如果调整启动脚本，要同步更新本文档。

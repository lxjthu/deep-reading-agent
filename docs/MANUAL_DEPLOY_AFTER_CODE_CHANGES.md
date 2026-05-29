# 手动上传、部署、重启与验证指南

本文记录每次本地改完代码后，手动部署到线上服务 `http://8.162.14.154:18080/` 的推荐流程。

适用场景：没有自动 Webhook，需要通过 SSH/SCP 把本地改动同步到服务器，并重启 FastAPI 服务。

## 服务器信息

| 项目 | 值 |
|------|----|
| 线上访问地址 | `http://8.162.14.154:18080/` |
| SSH | `ssh root@8.162.14.154` |
| 服务器项目目录 | `/root/deep-reading-agent` |
| 后端 venv | `/root/deep-reading-agent/venv` |
| FastAPI 监听 | `127.0.0.1:18000` |
| Nginx 对外端口 | `18080` |
| FastAPI 日志 | `/tmp/fastapi.log` |

注意：当前线上服务从 `/root/deep-reading-agent/backend` 目录启动，命令是 `uvicorn main:app ...`。不要在项目根目录执行同样命令，否则可能加载到根目录的 `main.py`，导致 `Attribute "app" not found`。

## 1. 本地确认改动范围

在本地项目根目录执行：

```powershell
git status --short
git diff --name-only
```

只上传和本次改动相关的文件。不要上传：

- `.env`、API Key、密钥文件
- `venv/`、`node_modules/`
- 本地数据库、用户上传文件、缓存目录
- 临时压缩包和测试产物

如果前端代码有改动，需要先构建并上传 `frontend/dist`，不能只上传 `frontend/src`。

## 2. 本地验证

后端通用验证：

```powershell
python -m unittest backend.tests.test_queue_manager
python -m compileall backend new_architecture smart_literature_filter.py translation_pipeline.py
```

前端有改动时：

```powershell
cd frontend
npm run build
cd ..
```

如果改了 migration，先用临时 SQLite 从空库跑到 head：

```powershell
$env:DATABASE_URL="sqlite+aiosqlite:///D:/code/deepagent/deep-reading-agent-online/deep-reading-agent/tmp_migration_check.sqlite"
cd backend
python -m alembic upgrade head
cd ..
Remove-Item Env:DATABASE_URL
Remove-Item .\tmp_migration_check.sqlite -ErrorAction SilentlyContinue
```

SQLite migration 改表约束时，优先使用 Alembic batch mode；SQLAlchemy 2 下执行原生 SQL 时使用 `exec_driver_sql()`，不要直接 `execute("...")` 字符串。

## 3. 打包本次改动

在本地项目根目录创建压缩包。示例：

```powershell
tar -czf deploy-changes.tgz `
  backend/utils/llm_provider.py `
  backend/utils/api_key.py `
  backend/routers `
  backend/services `
  new_architecture `
  smart_literature_filter.py `
  translation_pipeline.py `
  frontend/dist
```

实际文件列表以 `git diff --name-only` 和本次修改为准。改了数据库迁移时，要包含对应的 `backend/migrations/versions/*.py`。

上传到服务器：

```powershell
scp deploy-changes.tgz root@8.162.14.154:/tmp/deploy-changes.tgz
```

## 4. 服务器解包

登录服务器：

```powershell
ssh root@8.162.14.154
```

在服务器上执行：

```bash
cd /root/deep-reading-agent
tar -xzf /tmp/deploy-changes.tgz
```

## 5. 服务器验证与迁移

先做语法编译检查：

```bash
cd /root/deep-reading-agent
source venv/bin/activate
python -m compileall backend new_architecture smart_literature_filter.py translation_pipeline.py
```

如果包含 Alembic migration，执行：

```bash
cd /root/deep-reading-agent/backend
source ../venv/bin/activate
python -m alembic upgrade head
python -m alembic current
```

`alembic current` 应显示当前最新 migration，并带有 `(head)`。

## 6. 重启 FastAPI

**必须通过 systemd 重启**，不要手动 `nohup uvicorn`。手动启动会丢失 `EnvironmentFile` 中的 `DATABASE_URL`（PostgreSQL），导致服务回退到空的 SQLite 数据库。

```bash
systemctl restart deepreading-api
sleep 5
```

服务配置文件：`/etc/systemd/system/deepreading-api.service`
环境变量：`/root/deep-reading-agent/.env.production`（含 PostgreSQL DATABASE_URL）
日志：`/var/log/deepreading/api.log`、`/var/log/deepreading/api-error.log`

如果本次改动包含 normal 用户零点清理相关文件，还需要同步安装/刷新独立定时器：

```bash
install -D -m 644 deploy/systemd/deepreading-cleanup-normal-users.service \
  /etc/systemd/system/deepreading-cleanup-normal-users.service
install -D -m 644 deploy/systemd/deepreading-cleanup-normal-users.timer \
  /etc/systemd/system/deepreading-cleanup-normal-users.timer
systemctl daemon-reload
systemctl enable --now deepreading-cleanup-normal-users.timer
systemctl list-timers deepreading-cleanup-normal-users.timer
systemctl status deepreading-cleanup-normal-users.timer
```

建议同时确认 `deepreading-api` 服务环境中未开启 `ENABLE_IN_PROCESS_CLEANUP_SCHEDULER=1`，避免与 `systemd timer` 双跑。

> **⚠️ 历史事故（2026-05-27）**：手动启动 uvicorn 未加载 `.env.production`，服务回退到空 SQLite，
> 用户看到"数据丢失"。实际 PostgreSQL 数据完好，只是连错了数据库。详见 `DIAGNOSIS_2026-05-26_MULTI_SYSTEM_FAILURE.md`。

查看服务状态：

```bash
systemctl status deepreading-api
```

查看日志：

```bash
tail -100 /var/log/deepreading/api.log
tail -100 /var/log/deepreading/api-error.log
```

健康检查脚本 `health_check.py` 已部署到服务器（cron 每 5 分钟），同样使用 `systemctl restart`。

## 7. 验证线上服务

在服务器上检查进程和工作目录：

```bash
ss -tlnp | grep ':18000 '
ps -ef | grep '[u]vicorn'
readlink /proc/$(ss -tlnp | sed -n "s/.*127.0.0.1:18000.*pid=\([0-9]\+\).*/\1/p" | head -1)/cwd
```

期望工作目录为：

```text
/root/deep-reading-agent/backend
```

检查 HTTP 状态：

```bash
curl -sS -o /tmp/site.out -w "%{http_code}\n" http://127.0.0.1:18080/
curl -sS -o /tmp/runtime.out -w "%{http_code}\n" http://127.0.0.1:18080/api/deploy/runtime
```

期望都返回 `200`。

查看最近日志：

```bash
tail -100 /tmp/fastapi.log
```

如果前端有改动，额外确认 `frontend/dist/index.html` 已更新，且页面引用的 assets 存在：

```bash
head -30 /root/deep-reading-agent/frontend/dist/index.html
ls -lt /root/deep-reading-agent/frontend/dist/assets | head
```

最后在浏览器打开：

```text
http://8.162.14.154:18080/
```

至少验证：

- 首页能打开
- 登录/注册入口正常
- 本次改动影响的页面或接口正常
- 浏览器 Network 中没有明显 404/500

## 8. 清理临时文件

本地：

```powershell
Remove-Item .\deploy-changes.tgz -ErrorAction SilentlyContinue
```

服务器：

```bash
rm -f /tmp/deploy-changes.tgz
```

## 常见问题

### 启动时报 `Attribute "app" not found`

通常是启动目录错了。必须从 `/root/deep-reading-agent/backend` 启动：

```bash
cd /root/deep-reading-agent/backend
source ../venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 18000
```

### 端口没有起来

检查日志：

```bash
tail -200 /tmp/fastapi.log
```

同时检查是否还有旧进程占用端口：

```bash
ss -tlnp | grep ':18000 '
```

### Alembic 在 SQLite 上失败

常见原因：

- 修改 CHECK/UNIQUE 等约束时没有使用 batch recreate
- SQLAlchemy 2 下直接 `execute("SQL 字符串")`
- migration 依赖的表或列顺序与线上库状态不一致

处理顺序：

1. 本地用临时 SQLite 从空库跑 `alembic upgrade head`
2. 必要时在服务器备份数据库
3. 修复 migration 后重新上传并执行 `python -m alembic upgrade head`

### 首页返回 200，但前端还是旧版本

确认本地已执行 `npm run build`，并上传了完整 `frontend/dist`。服务器上查看：

```bash
head -30 /root/deep-reading-agent/frontend/dist/index.html
ls -lt /root/deep-reading-agent/frontend/dist/assets | head
```

浏览器侧可强制刷新或清缓存后再测。

## 部署检查清单

- [ ] 本地 `git diff --name-only` 已确认
- [ ] 未上传密钥、本地数据库、venv、node_modules、用户文件
- [ ] 后端语法/单测已跑
- [ ] 前端改动已执行 `npm run build`
- [ ] migration 改动已在本地临时 SQLite 验证
- [ ] 压缩包已 SCP 到 `/tmp/deploy-changes.tgz`
- [ ] 服务器已解包到 `/root/deep-reading-agent`
- [ ] 服务器 `compileall` 通过
- [ ] 必要时 `alembic upgrade head` 通过
- [ ] FastAPI 从 `/root/deep-reading-agent/backend` 重启
- [ ] `18080` 首页和关键 API 返回 `200`
- [ ] `/tmp/fastapi.log` 没有启动期异常
- [ ] 本次改动对应功能已在浏览器验证

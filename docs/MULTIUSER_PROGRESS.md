# 多用户系统 实施进度

> **更新时间**：2026-04-26  
> **当前分支**：`online`  
> **关联文档**：[DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)、[MULTI_USER_PLAN.md](./MULTI_USER_PLAN.md)

## 1. 总览

| 阶段 | 状态 | 备注 |
|---|:-:|---|
| 需求 & 数据库设计讨论 | ✅ | 三层模型 + `bib_entries` 枢纽方案确定 |
| `DATABASE_SCHEMA.md` 定稿 | ✅ | 9 张业务表 + 1 张 alembic_version |
| `MULTI_USER_PLAN.md` 定稿 | ✅ | API Key 不入库（保持前端 localStorage） |
| **P0 — DB schema + Alembic + admin seed** | ✅ | 本地一次性 venv 已跑通，本地代码就绪 |
| P1 — `/api/auth/*` + JWT 中间件 | ⏳ 下次 | 注册/登录/me/refresh + 邀请码校验 |
| P2 — `/api/upload/*` + `files` 表 + 按用户分目录 | ⏳ | |
| P3 — `/api/filter/*` + `bib_entries` 入库 | ⏳ | |
| P4 — `/api/reading/*` + `jobs/job_bib_entries/artifacts` | ⏳ | |
| P5 — `/api/compare/*`、`synthesis` 改造 | ⏳ | |
| P6 — `/api/history/*`、`download/*` 加权限校验 | ⏳ | |
| P7 — 邀请码 + VIP 升降级 + APScheduler 24h 清理 | ⏳ | |
| P8 — 历史无主文件迁移到 admin 名下 | ⏳ | |
| P9 — 前端 react-router + 登录/注册页 | ⏳ | |
| P10 — 前端顶栏 + 24h 警告横幅 | ⏳ | |
| P11 — 前端"我的文献库"页面 | ⏳ | |
| P12 — 前端管理员后台 | ⏳ | |
| P13 — Playwright E2E + 部署验收 | ⏳ | |

## 2. P0 已交付

### 2.1 文件清单

```
docs/
  DATABASE_SCHEMA.md            # 数据库设计（已定稿）
  MULTI_USER_PLAN.md            # 多用户方案（已定稿）
  MULTIUSER_PROGRESS.md         # 本进度文档

backend/
  alembic.ini                   # Alembic 主配置
  requirements.txt              # 已加 sqlalchemy/aiosqlite/alembic/passlib/bcrypt 等
  db/
    __init__.py                 # 公共出口
    base.py                     # DeclarativeBase
    session.py                  # async engine / AsyncSessionLocal / get_db
    models.py                   # 9 个 ORM 模型
    utils.py                    # compute_dedup_key
  migrations/
    env.py                      # alembic 环境（用 SYNC_DATABASE_URL 跑迁移）
    script.py.mako              # 迁移模板
    versions/
      001_initial_schema.py     # 全表初始迁移
  scripts/
    __init__.py
    seed_admin.py               # 幂等 admin 账号 seed

.gitignore                      # 加了 /db/（用前导 / 锚定仓库根）
```

### 2.2 9 张业务表

| 表 | 角色 |
|---|---|
| `users` | 用户（admin/vip/normal） |
| `invite_codes` | VIP 邀请码 |
| `user_settings` | 用户偏好（v1 暂不启用） |
| `upload_batches` | 批量上传（文件夹场景预留） |
| `files` | 物理文件（pdf/bibliography/markdown/docx/txt） |
| `bib_entries` ⭐ | 文献档案（枢纽） |
| `bib_filter_links` | 文献 ↔ 筛选任务 多对多 |
| `jobs` | 任务（filter/reading_*/compare/synthesis） |
| `job_bib_entries` | 任务 ↔ 文献 多对多 |
| `artifacts` | 任务产物文件 |

### 2.3 本地验收记录

```
$ alembic upgrade head
INFO  Running upgrade  -> 001_initial, initial schema (multi-user system)

$ python -m scripts.seed_admin
[seed_admin] created admin 'admin' (id=1)

$ python -m scripts.seed_admin                # 幂等
[seed_admin] admin 'admin' already exists (id=1); skipping.

$ sqlite3 db/app.sqlite '.tables'
alembic_version  bib_filter_links  invite_codes      upload_batches
artifacts        files             job_bib_entries   user_settings
bib_entries      jobs              users

users 表: id=1, username='admin', role='admin', is_active=1, password_hash 长度=60
passlib.verify('XIAojuan@0618wenxian', hash) == True   ✅
passlib.verify('wrongpass', hash)             == False ✅
```

本地用临时 venv 验证完毕已清理；`db/app.sqlite` 也已删除（部署服务器会自行生成）。

### 2.4 当前 git 状态（未 commit、未 push）

```
M  .gitignore
M  backend/requirements.txt
?? backend/alembic.ini
?? backend/db/
?? backend/migrations/
?? backend/scripts/
?? docs/DATABASE_SCHEMA.md
?? docs/MULTI_USER_PLAN.md
?? docs/MULTIUSER_PROGRESS.md
```

## 3. 服务器手动部署指引（首次）⭐

> **注意**：项目的自动部署机制是 — push 到 `online` 分支后服务器自动跑 `deploy.sh` —— 它会执行 `git pull → pip install → start.sh`。  
> 但**首次**部署多用户系统额外需要：① 跑数据库迁移；② seed admin。这两步**没有**自动化，必须手动一次。

### 3.1 推荐方式：先 ssh 准备好 DB，再 push 触发部署

适合 P0 这次"基础设施改动但还没启用"的场景：先把 DB 建好，新代码 push 后业务路由还没接入，最稳。

```bash
# 1. 本地：commit 但暂不 push
cd D:/code/deepagent/deep-reading-agent-online/deep-reading-agent
git add .gitignore backend/requirements.txt backend/alembic.ini \
        backend/db/ backend/migrations/ backend/scripts/ docs/
git commit -m "feat(p0): 多用户系统数据库 schema + admin seed

- 新增 SQLAlchemy 2.0 ORM (10 张表) + Alembic 迁移
- 新增 backend/db/ 模块 + backend/scripts/seed_admin.py
- requirements.txt 增加多用户相关依赖
- 文档落地：DATABASE_SCHEMA / MULTI_USER_PLAN / MULTIUSER_PROGRESS"

# 2. ssh 到服务器，先装依赖 + 建库 + seed admin
ssh root@<服务器>          # 用你常用的 ssh 入口

cd /root/.openclaw/workspace/deep-reading-agent

# 拉取本次 commit 之前的代码（保持服务先不变）—— 也可跳过这步直接等 push 后再装
git fetch origin online
# 暂不 reset，先在当前 working tree 上预装依赖：
source venv/bin/activate
pip install 'sqlalchemy>=2.0.0' 'aiosqlite>=0.19.0' 'alembic>=1.13.0' \
            'passlib[bcrypt]>=1.7.4' 'bcrypt<4.1.0' \
            'python-jose[cryptography]>=3.3.0' 'apscheduler>=3.10.0' \
            'email-validator>=2.0.0'

# 3. 本地：push 触发自动部署（deploy.sh 会跑 git reset --hard + pip install + start.sh）
git push origin online

# 4. 等 30 秒后再回到服务器，跑迁移和 seed
ssh root@<服务器>
cd /root/.openclaw/workspace/deep-reading-agent
source venv/bin/activate
cd backend
alembic upgrade head                                   # 创建 db/app.sqlite + 全部表
python -m scripts.seed_admin                           # seed admin 账号
sqlite3 ../db/app.sqlite "SELECT id, username, role FROM users;"
# 期望输出：1|admin|admin

# 5. 健康检查（deploy.sh 已经重启过服务了，但 P0 没接路由，行为应保持原状）
curl -s http://localhost:8000/health
curl -s -o /dev/null -w '%{http_code}\n' https://deepreading.qzz.io/
```

### 3.2 备选方式：直接 push，等部署后再补 DB 操作

```bash
# 本地
git push origin online

# 等 deploy.sh 跑完（pip install 会自动装新依赖），ssh 上去
ssh root@<服务器>
cd /root/.openclaw/workspace/deep-reading-agent
source venv/bin/activate
cd backend
alembic upgrade head
python -m scripts.seed_admin
```

风险：若 deploy.sh 触发的服务重启过程中有路由依赖了 `backend/db`（P0 没接，所以**没有**），可能瞬时 502。P0 阶段不会发生。

### 3.3 数据库文件位置

服务器上：

```
/root/.openclaw/workspace/deep-reading-agent/
├── db/
│   ├── app.sqlite                 # ← 主库，被 .gitignore 忽略
│   └── (将来会有 backups/、cleanup.log)
├── backend/
└── _uploads/、deep_reading_results/   # 现存无主文件，待 P8 迁移
```

### 3.4 后续部署（P1 起每次都跑）

为简化，建议**之后**把"装依赖 + 迁移"两条加到 `deploy.sh` 里。比如：

```bash
# deploy.sh 推荐增量
echo "[2/4] 安装依赖..."
source venv/bin/activate
pip install -q -r requirements.txt 2>/dev/null || true

echo "[3/4] 数据库迁移..."
cd backend && alembic upgrade head && cd ..

echo "[4/4] 重启服务..."
bash start.sh
```

P0 阶段先不改，等 P1 实装好 auth 路由再一并改 `deploy.sh` 落上线。

## 4. 下次开工（P1）入口

下午回来直接做以下事情：

### 4.1 启动本地环境

```bash
cd D:/code/deepagent/deep-reading-agent-online/deep-reading-agent

# 重建本地 venv（之前的临时 .venv_p0 已删）
python -m venv venv
venv/Scripts/activate    # Windows bash
pip install -r backend/requirements.txt

# 跑迁移建本地库（用于 P1 单测和调试）
cd backend
alembic upgrade head
python -m scripts.seed_admin
```

### 4.2 P1 工作清单

> 目标：JWT 鉴权打通；Postman 跑通 注册→登录→`/me`→refresh 全流程

- [ ] 新增 `.env` 字段：`JWT_SECRET_KEY`、`JWT_ALGORITHM=HS256`、`ACCESS_TOKEN_EXPIRE_MINUTES=60`、`REFRESH_TOKEN_EXPIRE_DAYS=30`
- [ ] `backend/auth/` 新模块：
  - `auth/security.py` — passlib 包装 + JWT encode/decode
  - `auth/dependencies.py` — `current_user` / `require_admin` / `require_vip_or_admin`
  - `auth/schemas.py` — Pydantic 请求/响应模型
- [ ] `backend/routers/auth.py` 新路由：
  - `POST /api/auth/register`（含可选邀请码校验 → role=vip）
  - `POST /api/auth/login`（OAuth2PasswordRequestForm 兼容）
  - `POST /api/auth/refresh`
  - `GET /api/auth/me`
  - `POST /api/auth/change_password`
  - `POST /api/auth/logout`（撤销 refresh，可选 v1 简化跳过）
- [ ] `main.py` include `auth` router
- [ ] 单元测试 `backend/tests/test_auth.py`：
  - 注册成功 / 重名失败
  - 邀请码：有效/过期/超额/无效
  - 登录成功 / 错误密码 / 不存在用户
  - JWT 有效 / 篡改 / 过期 → 401
  - me 返回当前用户 + role
- [ ] Postman/curl 手动跑通 happy path

### 4.3 P1 验收

```bash
# 注册
curl -X POST http://localhost:8000/api/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"username":"alice","password":"pwd12345"}'

# 登录拿 token
curl -X POST http://localhost:8000/api/auth/login \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d 'username=alice&password=pwd12345'

# /me
curl http://localhost:8000/api/auth/me \
     -H "Authorization: Bearer <access_token>"
# 应返回 { "id": 2, "username": "alice", "role": "normal", ... }
```

## 5. 已知问题与待办

| 问题 | 说明 | 处理时机 |
|---|---|---|
| `.gitignore` 之前的 `db/` 误伤 `backend/db/` | 已改成 `/db/` 锚定仓库根 | 已修 |
| `seed_admin.py` 用 `datetime.utcnow()` 触发弃用警告 | Python 3.12+ 警告，3.13 仍可用 | P1 顺手改成 `datetime.now(UTC)` |
| `deploy.sh` 没有自动跑 alembic | 首次部署需手动 | P1 上线时一并改 |
| 部署服务器还没装新依赖 | 需要按 §3 手动 ssh 装一次 | 首次部署时 |

## 6. 联系点

- Cloudflare Tunnel 域名：https://deepreading.qzz.io/
- 服务器路径：`/root/.openclaw/workspace/deep-reading-agent`
- 自动部署触发：push 到 `online` 分支
- 主分支：`main`（PR 目标），当前工作分支：`online`

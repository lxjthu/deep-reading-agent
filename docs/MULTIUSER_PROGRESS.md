# 多用户系统 实施进度

> **更新时间**：2026-04-26（P1 本地完成）  
> **当前分支**：`online`  
> **关联文档**：[DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)、[MULTI_USER_PLAN.md](./MULTI_USER_PLAN.md)

## 1. 总览

| 阶段 | 状态 | 备注 |
|---|:-:|---|
| 需求 & 数据库设计讨论 | ✅ | 三层模型 + `bib_entries` 枢纽方案确定 |
| `DATABASE_SCHEMA.md` 定稿 | ✅ | 9 张业务表 + 1 张 alembic_version |
| `MULTI_USER_PLAN.md` 定稿 | ✅ | API Key 不入库（保持前端 localStorage） |
| **P0 — DB schema + Alembic + admin seed** | ✅ | 本地一次性 venv 已跑通，本地代码就绪 |
| P1 — `/api/auth/*` + JWT 中间件 | ✅ 本地完成 | 已实现并本地验证：注册/登录/me/refresh/logout + 邀请码校验 + `token_version` |
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

### 3.4 后续部署（当前策略）

当前决定：**暂不**把 `alembic upgrade head` 接入 `deploy.sh`。  
原因：本地库与服务器库分开使用；现阶段优先保持部署流程简单，涉及 schema 变更时手动执行迁移更稳。

后续统一采用：

```bash
# 1. 本地开发、自测、提交、push
git push origin online

# 2. 若本次包含 Alembic 新迁移，再手动上服务器执行
ssh root@<服务器>
cd /root/.openclaw/workspace/deep-reading-agent
source venv/bin/activate
cd backend
alembic upgrade head
```

纯代码改动可只依赖自动部署；只有涉及数据库迁移时才额外 SSH 执行 `alembic upgrade head`。

## 4. 阶段记录与下步入口

P1 已在本地实现并验证，当前状态如下：

### 4.1 本地已完成内容

```bash
$ py -3.12 -m venv venv
$ venv/Scripts/python -m pip install -r backend/requirements.txt
$ cd backend
$ ../venv/Scripts/python -m alembic upgrade head
INFO  Running upgrade  -> 001_initial, initial schema (multi-user system)
INFO  Running upgrade 001_initial -> 002_add_users_token_version, add users.token_version for refresh-token revocation

$ ../venv/Scripts/python -m scripts.seed_admin
[seed_admin] created admin 'admin' (id=1)

$ ../venv/Scripts/python -c "import sqlite3; conn=sqlite3.connect(r'../db/app.sqlite'); print(conn.execute('SELECT id, username, role, token_version FROM users').fetchall()); conn.close()"
[(1, 'admin', 'admin', 0)]

$ venv/Scripts/python -m unittest backend.tests.test_auth -v
Ran 6 tests in 9.xxs
OK
```

### 4.2 P1 工作清单

> 目标已达成：JWT 鉴权已打通；本地自动化测试已覆盖注册→登录→`/me`→refresh→logout 主流程

- [x] 新增 `.env` 字段约定：`JWT_SECRET_KEY`、`JWT_ALGORITHM=HS256`、`ACCESS_TOKEN_EXPIRE_MINUTES=60`、`REFRESH_TOKEN_EXPIRE_DAYS=30`
- [x] 新增 Alembic 迁移：给 `users` 表增加 `token_version INTEGER NOT NULL DEFAULT 0`
- [x] `backend/auth/` 新模块：
  - `auth/security.py` — passlib 包装 + JWT encode/decode（含 refresh token version 校验）
  - `auth/dependencies.py` — `current_user` / `require_admin` / `require_vip_or_admin`
  - `auth/schemas.py` — Pydantic 请求/响应模型
- [x] `backend/routers/auth.py` 新路由：
  - `POST /api/auth/register`（含可选邀请码校验 → role=vip）
  - `POST /api/auth/login`（OAuth2PasswordRequestForm 兼容）
  - `POST /api/auth/refresh`
  - `GET /api/auth/me`
  - `POST /api/auth/change_password`
  - `POST /api/auth/logout`（递增 `users.token_version`，严格撤销 refresh）
- [x] `main.py` include `auth` router
- [x] 单元测试 `backend/tests/test_auth.py`：
  - 注册成功 / 重名失败
  - 邀请码：有效/过期/超额/无效
  - 登录成功 / 错误密码 / 不存在用户
  - JWT 有效 / 篡改 / 过期 → 401
  - me 返回当前用户 + role
  - logout 后旧 refresh token 再调 `/api/auth/refresh` → 401
- [x] 本地自动化测试跑通 happy path

### 4.3 当前 git 状态

```bash
$ git rev-parse --short HEAD
476a8e1e

$ git status --short
# 无输出（working tree clean）
```

说明：
- P1 改动已 **本地 commit**
- 当前按约定 **未 push**
- 等后续阶段全部完成并再次验证后再统一 push

### 4.4 P1 验收

```bash
已通过本地自动化测试覆盖以下验收点：
- 注册成功 / 重名失败
- 邀请码有效 / 过期 / 超额 / 无效
- 登录成功 / 错误密码 / 不存在用户
- `/me` 返回当前用户和 role
- JWT 篡改 / 过期返回 401
- logout 后旧 refresh token 调 `/api/auth/refresh` 返回 401
```

### 4.5 P2 规划

> 目标：把现有 `/api/upload/*` 从“匿名平铺上传”改造成“按用户隔离的上传入口”，让文件第一次真正进入多用户数据模型。

#### P2 要达成的结果

- 上传接口接入 `current_user`
- 物理文件落到 `_uploads/{owner_user_id}/`
- 每次上传写入 `files` 表，而不再只返回内存/临时 `file_id`
- 按用户角色写入 `expires_at`
  - `normal` = `created_at + 24h`
  - `vip/admin` = `NULL`
- `GET /api/upload/{file_id}/info` 仅允许查询当前用户自己的文件
- 为后续 P3 / P4 铺路：上传得到的 `file_id` 将成为 `filter`、`reading`、`bib_entries` 串联入口

#### P2 工作清单

- [ ] 改造 `backend/routers/upload.py`
  - `POST /api/upload/` 增加 `Depends(current_user)`
  - 上传后写入 `files` 表而不是只落磁盘
  - 返回值补齐 DB 中的 `id / file_type / storage_path / expires_at`
- [ ] 上传目录改造
  - 旧逻辑：根目录 `_uploads/` 平铺文件
  - 新逻辑：`_uploads/{uid}/{file_id}.{ext}`
  - 若用户目录不存在则自动创建
- [ ] 文件类型映射落库
  - `pdf`
  - `bibliography`
  - `markdown`
  - `docx`
  - `txt`
- [ ] 计算文件元信息
  - `original_name`
  - `size_bytes`
  - `md5`
  - `storage_path`
  - `owner_user_id`
- [ ] 实现同用户内 MD5 去重
  - 命中 `UNIQUE(owner_user_id, md5)` 时，返回已有文件记录
  - 不同用户之间允许同一文件内容各自存在
- [ ] 实现 `expires_at` 规则
  - `normal` 用户上传时自动写入 24h 过期时间
  - `vip/admin` 用户为 `NULL`
- [ ] 改造 `GET /api/upload/{file_id}/info`
  - 查 `files` 表
  - 只允许访问当前用户自己的文件
  - 为后续 admin 特例预留空间，但 P2 暂不开放跨用户查询
- [ ] 评估是否在 P2 直接接入 metadata 提取
  - 若实现成本低，可在上传 PDF/MD 后预留调用 metadata_extractor 的挂点
  - 若耦合过大，可先只写 `files` 表，把自动创建 `bib_entries` 留到 P3 衔接
- [ ] 增加测试
  - 用户 A / 用户 B 上传后物理路径不同
  - `files` 表记录正确
  - `normal` / `vip` 的 `expires_at` 不同
  - 用户 A 无法读取用户 B 的 `/info`

#### P2 验收

```bash
# 用户 A 上传 PDF
curl -X POST http://localhost:8000/api/upload/ \
     -H "Authorization: Bearer <user_a_access_token>" \
     -F "file=@paper_a.pdf"

# 用户 B 上传同一个 PDF
curl -X POST http://localhost:8000/api/upload/ \
     -H "Authorization: Bearer <user_b_access_token>" \
     -F "file=@paper_a.pdf"

# 期望：
# 1. 两次返回的 file_id 不同
# 2. 物理文件分别位于 _uploads/<uid_a>/ 和 _uploads/<uid_b>/
# 3. files 表中有两条 owner_user_id 不同的记录
# 4. 若同一用户重复上传同一文件，则返回已有 file 记录而不是重复写入
```

#### P2 测试用例规划

- [ ] `test_upload_creates_file_record_for_normal_user`
  - normal 用户上传 PDF 成功
  - `files` 表新增 1 条记录
  - `owner_user_id` 正确
  - `expires_at` 非空，且约为创建后 24h
- [ ] `test_upload_creates_file_record_for_vip_user`
  - vip 用户上传成功
  - `files.expires_at` 为 `NULL`
- [ ] `test_upload_creates_file_record_for_admin_user`
  - admin 用户上传成功
  - `files.expires_at` 为 `NULL`
- [ ] `test_upload_stores_file_under_user_directory`
  - 用户 A 上传后，`storage_path` 位于 `_uploads/{uid_a}/`
  - 磁盘上对应文件真实存在
- [ ] `test_same_user_same_md5_returns_existing_record`
  - 同一用户重复上传同一文件内容
  - 返回已有 `file_id`
  - `files` 表记录数不增加
- [ ] `test_different_users_same_md5_create_separate_records`
  - 用户 A / B 上传同一文件内容
  - 返回不同 `file_id`
  - `files` 表中保留两条不同 `owner_user_id` 记录
- [ ] `test_upload_info_only_visible_to_owner`
  - 用户 A 上传文件后能访问 `/api/upload/{file_id}/info`
  - 用户 B 访问同一路径返回 `403` 或 `404`
- [ ] `test_upload_requires_authentication`
  - 未带 access token 调 `/api/upload/` 返回 `401`
  - 未带 access token 调 `/api/upload/{file_id}/info` 返回 `401`
- [ ] `test_upload_rejects_unsupported_extension`
  - 上传不支持的扩展名时返回 `400`
  - 磁盘不残留文件
  - DB 不残留 `files` 记录
- [ ] `test_upload_rollback_when_db_write_fails`
  - mock DB commit 失败
  - 已写入的物理文件被删除
  - 不留下脏记录
- [ ] `test_upload_supports_expected_file_types`
  - 至少覆盖 `pdf / txt / docx`
  - `file_type` 映射正确

建议：
- P2 结束时至少保留 1 个自动化测试文件，例如 `backend/tests/test_upload_authz.py`
- 若时间紧，可优先保证前 8 条；其中“跨用户隔离”“同用户去重”“未登录拒绝访问”是最低优先级之外的必测项
- 若 P2 暂不接 metadata_extractor，则测试只聚焦 `files` 表与物理路径，不把 `bib_entries` 自动创建混进本阶段
- 若 P2 顺手接入 metadata_extractor，相关联动测试放到 P3 一并收口，避免 P2 测试范围过宽

#### P2 注意点

- 现有 `upload.py` 仍是“落盘 + `.meta` 文件映射”的单用户旧逻辑，P2 要彻底切到 DB 驱动，避免后续 P3/P4 同时维护两套 file_id 语义。
- 文件落盘与 DB 写入必须保持一致：若 DB commit 失败，要删除已写入的物理文件；若磁盘写入失败，不得残留半条 DB 记录。
- P2 完成后，`filter` 和 `reading` 仍可能暂时使用旧查文件方式；进入 P3/P4 时要统一改为从 `files` 表取路径。
- 如果 P2 引入新的 Alembic 迁移，继续沿用当前策略：本地验证后先 commit、不 push；最终统一 push 时再手动到服务器执行 `alembic upgrade head`。
- 若上传接口改动较大，建议在 P2 结束时补一轮最小手工验证：PDF / txt / docx 至少各测一条。

## 5. 已知问题与待办

| 问题 | 说明 | 处理时机 |
|---|---|---|
| `.gitignore` 之前的 `db/` 误伤 `backend/db/` | 已改成 `/db/` 锚定仓库根 | 已修 |
| `seed_admin.py` 用 `datetime.utcnow()` 触发弃用警告 | 已在 P1 顺手改成 `datetime.now(UTC)` | 已修 |
| `deploy.sh` 没有自动跑 alembic | 当前决定继续手动迁移，只有 schema 变更时 SSH 执行 `alembic upgrade head` | 暂按此流程 |
| `backend/requirements.txt` 原先缺少 `markdown` | 本地导入 `main.py` 时发现 `history.py` 依赖未声明，已补 `markdown>=3.6` | 已修 |
| 部署服务器还没装 P1 新依赖 | 等最终统一 push 后，服务器自动部署会装依赖；若含迁移仍需手动跑 alembic | P1/P2 上线时 |

## 6. 联系点

- Cloudflare Tunnel 域名：https://deepreading.qzz.io/
- 服务器路径：`/root/.openclaw/workspace/deep-reading-agent`
- 自动部署触发：push 到 `online` 分支
- 主分支：`main`（PR 目标），当前工作分支：`online`

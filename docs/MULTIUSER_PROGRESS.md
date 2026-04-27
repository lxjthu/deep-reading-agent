# 多用户系统 实施进度

> **更新时间**：2026-04-27（P5 本地完成）  
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
| P2 — `/api/upload/*` + `files` 表 + 按用户分目录 | ✅ 本地完成 | 已实现并本地验证：鉴权上传、`files` 入库、按用户目录落盘、同用户 MD5 去重、`/info` 权限隔离 |
| P3 — `/api/filter/*` + `bib_entries` 入库 | ✅ 本地完成 | 已实现并本地验证：筛选鉴权、`jobs` 入库、`bib_entries` 去重入库、`bib_filter_links` 写入、`filter_excel` 产物落 `artifacts` |
| P4 — `/api/reading/*` + `jobs/job_bib_entries/artifacts` | ✅ 本地完成 | 已实现并本地验证：精读鉴权、`jobs` 入库、`job_bib_entries(target)`、`artifacts(reading_final/step)`、`reading_status` 流转 |
| P5 — `/api/compare/*`、`synthesis` 改造 | ✅ 本地完成 | 已实现并本地验证：compare 鉴权、`jobs(compare)`、`job_bib_entries(compare_member)`、`artifacts(compare_md)`、synthesis 保存/历史按用户隔离 |
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

### 4.3 当前本地状态

```bash
P1 / P2 / P3 / P4 已本地实现并验证完成。
当前仍按约定：先继续本地迭代与提交，暂不 push。
```

说明：
- P1 改动已 **本地 commit**
- P2 改动已 **本地 commit**
- P3 改动已 **本地 commit**
- P4 改动会与本轮文档同步一起进入 **本地 commit**
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

### 4.5 P2 已交付

> 目标已达成：现有 `/api/upload/*` 已从“匿名平铺上传”改造成“按用户隔离的上传入口”，文件已正式进入多用户数据模型。

#### P2 已达成的结果

- 上传接口接入 `current_user`
- 物理文件落到 `_uploads/{owner_user_id}/`
- 每次上传写入 `files` 表，而不再只返回内存/临时 `file_id`
- 按用户角色写入 `expires_at`
  - `normal` = `created_at + 24h`
  - `vip/admin` = `NULL`
- `GET /api/upload/{file_id}/info` 仅允许查询当前用户自己的文件
- 为后续 P3 / P4 铺路：上传得到的 `file_id` 将成为 `filter`、`reading`、`bib_entries` 串联入口

#### P2 工作清单

- [x] 改造 `backend/routers/upload.py`
  - `POST /api/upload/` 增加 `Depends(current_user)`
  - 上传后写入 `files` 表而不是只落磁盘
  - 返回值补齐 DB 中的 `id / file_type / storage_path / expires_at`
- [x] 上传目录改造
  - 旧逻辑：根目录 `_uploads/` 平铺文件
  - 新逻辑：`_uploads/{uid}/{file_id}.{ext}`
  - 若用户目录不存在则自动创建
- [x] 文件类型映射落库
  - `pdf`
  - `bibliography`
  - `markdown`
  - `docx`
  - `txt`
- [x] 计算文件元信息
  - `original_name`
  - `size_bytes`
  - `md5`
  - `storage_path`
  - `owner_user_id`
- [x] 实现同用户内 MD5 去重
  - 命中 `UNIQUE(owner_user_id, md5)` 时，返回已有文件记录
  - 不同用户之间允许同一文件内容各自存在
- [x] 实现 `expires_at` 规则
  - `normal` 用户上传时自动写入 24h 过期时间
  - `vip/admin` 用户为 `NULL`
- [x] 改造 `GET /api/upload/{file_id}/info`
  - 查 `files` 表
  - 只允许访问当前用户自己的文件
  - 为后续 admin 特例预留空间，但 P2 暂不开放跨用户查询
- [x] 增加共享存储辅助模块 `backend/upload_storage.py`
  - 统一上传根目录解析
  - 统一 `storage_path` 解析
  - 为 `filter.py` / `reading.py` 提供兼容读取入口
- [x] 兼容现有 `filter.py` / `reading.py`
  - 旧流程仍可通过 `file_id` 找到用户子目录中的文件
  - `reading.py` 读取原始文件名时优先走 `files` 表
- [x] 评估是否在 P2 直接接入 metadata 提取
  - 结论：本阶段先不把 PDF/MD 自动建档接进上传路由
  - 原因：避免 P2 范围膨胀，`bib_entries` 自动创建留到 P3 衔接
- [x] 增加测试
  - 用户 A / 用户 B 上传后物理路径不同
  - `files` 表记录正确
  - `normal` / `vip/admin` 的 `expires_at` 不同
  - 用户 A 无法读取用户 B 的 `/info`
  - 同用户重复上传同内容返回已有记录
  - `docx / txt / bibliography` 类型映射可用

#### P2 验收

```bash
$ venv/Scripts/python -m unittest backend.tests.test_upload -v
Ran 8 tests in 16.xxs
OK

$ venv/Scripts/python -m unittest backend.tests.test_auth -v
Ran 6 tests in 9.xxs
OK

$ venv/Scripts/python -c "import sys; sys.path.insert(0, r'D:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend'); import main; print('main import ok')"
main import ok
```

#### P2 已落地测试

- [x] `test_upload_requires_authentication`
  - 未带 access token 调 `/api/upload/` 返回 `401`
- [x] `test_normal_user_upload_creates_record_with_expiry`
  - normal 用户上传后 `files` 表有记录，且 `expires_at` 非空
- [x] `test_vip_and_admin_uploads_do_not_expire`
  - vip/admin 上传后 `expires_at` 为 `NULL`
- [x] `test_same_user_same_md5_returns_existing_record`
  - 同一用户重复上传同内容返回已有 `file_id`
- [x] `test_different_users_same_md5_create_separate_records`
  - 不同用户上传同内容时各自保留独立记录
- [x] `test_upload_info_only_visible_to_owner`
  - `/api/upload/{file_id}/info` 只对 owner 可见
- [x] `test_rejects_unsupported_extension`
  - 不支持的扩展名返回 `400`
- [x] `test_supports_docx_txt_and_bibliography_detection`
  - `docx / txt / bibliography` 文件类型映射可用

#### P2 注意点

- `upload.py` 已切到 DB 驱动；后续若再扩展上传元信息，应以 `files` 表为准，避免重新引入 `.meta` 依赖。
- 文件落盘与 DB 写入已做基本清理保护：若 DB commit 失败，会删除已写入的目标文件；若磁盘写入失败，不保留 DB 脏记录。
- `filter.py` 和 `reading.py` 已通过共享 helper 兼容新的用户子目录；进入 P3/P4 时仍建议进一步改为显式从 `files` 表取路径，而不是继续依赖按 `file_id` 查询 helper。
- 如果 P2 引入新的 Alembic 迁移，继续沿用当前策略：本地验证后先 commit、不 push；最终统一 push 时再手动到服务器执行 `alembic upgrade head`。
- 本次 P2 **未**在上传阶段自动创建 `bib_entries`；该衔接点留给 P3，届时再把 metadata 抽取和文献档案落库一起收口。

### 4.6 P3 已交付

> 目标已达成：现有 `/api/filter/*` 已从“匿名内存任务 + 仅导出 Excel”改造成“有用户归属的筛选任务入口”，筛选过程会把题录正式沉淀到 `jobs` / `bib_entries` / `bib_filter_links` / `artifacts`。

#### P3 已达成的结果

- `POST /api/filter/start`、`GET /api/filter/task/{task_id}/status`、`POST /api/filter/task/{task_id}/cancel` 全部接入 `current_user`
- 启动筛选时校验 `file_id` 属于当前用户，且输入文件类型仅允许 `bibliography/txt`
- 每次筛选创建一条 `jobs(job_type='filter')`
  - `owner_user_id` = 当前用户
  - `input_file_id` = 题录文件
  - `params_json` 写入 `mode / topic / min_year / keywords`
  - `status / progress / current_stage / error_msg` 跟运行态同步
  - `expires_at` 跟随当前用户角色（normal=24h，vip/admin=NULL）
- 题录解析结果写入 `bib_entries`
  - `owner_user_id` = 当前用户
  - `source_db` 从解析结果映射为 `wos / cnki / other`
  - `source_filter_job_id` 首次入库时记录本次 filter job
  - `source_file_id` 在 P3 阶段通常保持 `NULL`（题录不是可读正文文件）
  - `reading_status` 初始为 `none`
  - `metadata_completeness` 按 title/authors/year 等字段计算
  - `expires_at` 跟随 owner
- 为本次筛选写入 `bib_filter_links`
  - `filter_job_id` = 本次 job
  - `bib_entry_id` = 对应文献档案
  - `passed` 标记是否进入最终筛选结果
  - `score / reason` 存 LLM 评估结果（如有）
- 同一用户重复筛选同一篇文献时，复用既有 `bib_entries`
  - 通过 `compute_dedup_key()` 去重
  - 只新增新的 `bib_filter_links`
- 不同用户筛选到同一篇文献时，各自拥有独立 `bib_entries`
- 筛选产物 Excel 已落入 `artifacts(filter_excel)`，并写到 `deep_reading_results/{uid}/{job_id}/`

#### P3 工作清单

- [x] 改造 `backend/routers/filter.py`
  - `POST /start` 增加 `Depends(current_user)`
  - `GET /task/{task_id}/status` 增加 owner 校验
  - `POST /task/{task_id}/cancel` 增加 owner 校验
- [x] 统一筛选任务主键
  - 继续复用现有 `task_id` 作为 `jobs.id`
  - 内存 `tasks` 保留运行态缓存；数据库中的 `jobs` 作为可追踪记录
- [x] 启动任务前校验输入文件
  - `file_id` 必须存在
  - 文件必须属于当前用户
  - 文件类型限制为 `bibliography/txt`
- [x] 创建 `jobs(type='filter')`
  - 写入 `owner_user_id / input_file_id / params_json / expires_at`
  - 状态流转覆盖 `pending / running / success / failed / canceled`
- [x] 解析题录并标准化字段
  - 标题、作者、年份、DOI、期刊、摘要、关键词
  - 统一空值处理，避免把 `NaN` / 空字符串直接写库
- [x] 计算并应用 `dedup_key`
  - 优先 DOI
  - 否则 `first_author + year + normalized_title`
  - 命中同用户唯一约束时复用已有 `bib_entries`
- [x] 写入 `bib_entries`
  - `source_db` 从解析器来源决定
  - `source_filter_job_id` 仅首次创建时写入
  - `metadata_completeness` 与 `reading_status` 正确初始化
  - `updated_at` 在重复命中时刷新
- [x] 写入 `bib_filter_links`
  - 同一篇文献在同一 filter job 下仅保留 1 条 link
  - `score / reason / passed` 与筛选结果同步
- [x] 写入 `artifacts(filter_excel)`
  - 产物路径采用 `deep_reading_results/{uid}/{job_id}/{filename}`
  - `output_path` 与 `/api/download/*` 的相对路径约定保持兼容
- [x] 增加测试文件 `backend/tests/test_filter.py`
  - 覆盖鉴权、owner 校验、`jobs` 入库、`bib_entries` 去重、`bib_filter_links` 写入、artifact 落库

#### P3 验收

```bash
$ venv/Scripts/python -m unittest backend.tests.test_filter -v
Ran 8 tests in 18.xxs
OK

$ venv/Scripts/python -m unittest backend.tests.test_auth backend.tests.test_upload -v
Ran 14 tests in 25.xxs
OK
```

#### P3 已落地测试

- [x] `test_filter_start_requires_authentication`
  - 未登录调用 `/api/filter/start` 返回 `401`
- [x] `test_filter_rejects_non_owned_file`
  - 当前用户不能用他人的 `file_id` 发起筛选
- [x] `test_filter_rejects_non_bibliography_file`
  - `pdf` 不能直接作为 filter 输入
- [x] `test_filter_creates_job_bib_links_and_artifact`
  - `jobs / bib_entries / bib_filter_links / artifacts` 都正确落库
- [x] `test_filter_reuses_existing_bib_entry_for_same_user`
  - 同一用户重复筛选同一文献时复用 `bib_entries`
- [x] `test_filter_creates_separate_bib_entries_for_different_users`
  - 不同用户筛到同一文献时，各自产生独立档案
- [x] `test_filter_status_and_cancel_require_owner`
  - 任务状态查询和取消都做 owner 隔离
- [x] `test_filter_empty_after_basic_filter_marks_job_failed`
  - 过滤后为空时任务置 `failed`，不留下半成品 link/artifact

#### P3 注意点

- `filter.py` 已从“匿名路由 + 纯内存任务”改成“运行态内存缓存 + DB 持久记录”；后续不要再回退到只写内存不写库的模式。
- `source_file_id` 在 `bib_entries` 中表示可读正文文件（PDF/MD），不是题录输入文件；P3 不要把 bibliography 文件误绑到 `source_file_id`。
- `source_filter_job_id` 表示文献第一次进入系统的筛选任务；若命中去重的旧档案，后续筛选不应覆盖这个“首次来源”。
- `bib_filter_links.passed` 当前按“最终筛选结果中保留”来记，后续前端/历史页按这个语义读取。
- `jobs.id` 与内存 `task_id` 已统一；后续若接 WebSocket/历史页，继续沿用这一映射。
- 本次实现额外暴露出一个真实依赖缺口：`filter.py` 的 `pandas/openpyxl` 之前未写进 `backend/requirements.txt`，现已补齐。

### 4.7 P4 已交付

> 目标已达成：现有 `/api/reading/*` 已从“匿名精读任务 + 平铺输出文件”改造成“有用户归属的精读任务入口”，执行过程中会把任务、目标文献和产物统一沉淀到 `jobs` / `job_bib_entries` / `artifacts`，并同步更新 `bib_entries.reading_status`。

#### P4 已达成的结果

- `POST /api/reading/long/start`、`POST /api/reading/quant/start`、`POST /api/reading/qual/start` 全部接入 `current_user`
- `GET /api/reading/task/{task_id}/status`、`POST /api/reading/task/{task_id}/cancel` 增加 owner 校验
- 启动精读时校验：
  - `file_id` 必须属于当前用户
  - 文件类型仅允许 `pdf/markdown`
  - 若已有 `bib_entries.source_file_id = file_id`，优先复用该文献档案
  - 若未绑定文献档案，则根据文件名创建或匹配新的 `bib_entries`
- 每次精读创建一条 `jobs`
  - `job_type` 分别为 `reading_long / reading_quant / reading_qual`
  - `owner_user_id` = 当前用户
  - `params_json` 写入分析维度、提取方式、自定义问题等
  - `progress / current_stage / error_msg` 与运行态同步
  - `expires_at` 跟随用户角色
- 每次精读写一条 `job_bib_entries(role='target')`
  - 目标文献只允许绑定 1 篇 `bib_entry`
  - 若重复点击同一文献开启新精读，可生成新 job，但同一 job 不应重复插入 target link
- 精读产物写入 `artifacts`
  - 长文本报告写 `reading_final`
  - 七步精读测试已覆盖 `reading_step + reading_final`
  - 最终报告统一写 `reading_final`
  - `storage_path` 使用 `deep_reading_results/{uid}/{job_id}/...`
- `bib_entries.reading_status` 状态流转生效
  - 启动精读时 `has_pdf -> reading`
  - 完成时 `reading -> read`
  - 失败时回退到 `has_pdf`

#### P4 工作清单

- [x] 改造 `backend/routers/reading.py`
  - 三个 start 路由接入 `Depends(current_user)`
  - status / cancel 路由接入 owner 校验
- [x] 统一 reading 任务主键
  - 继续复用现有 `task_id` 作为 `jobs.id`
  - 内存 `tasks` 保留运行态缓存；数据库中的 `jobs` 作为可追踪记录
- [x] 启动任务前校验输入文件
  - `file_id` 必须存在
  - 文件必须属于当前用户
  - 文件类型错误时明确返回 `400`
- [x] 建立或复用目标 `bib_entry`
  - 先查 `source_file_id == file_id`
  - 查不到时根据文件名创建或匹配档案
  - 创建成功后，将 `source_file_id` 绑定到文献档案
  - `reading_status` 至少进入 `has_pdf`
- [x] 创建 `jobs(type='reading_*')`
  - 写入 `owner_user_id / params_json / expires_at`
  - 状态流转覆盖 `pending / running / success / failed / canceled`
- [x] 写入 `job_bib_entries`
  - 每个 job 为目标文献写 1 条 `role='target'`
  - `sort_order = 0`
- [x] 改造产物输出目录
  - 旧逻辑：`deep_reading_results/{safe_name}_*.md`
  - 新逻辑：`deep_reading_results/{uid}/{job_id}/...`
- [x] 写入 `artifacts`
  - 长文本 / 四步报告写 `reading_final`
  - 七步精读支持 `reading_step + reading_final`
  - `filename / storage_path / size_bytes / expires_at` 正确
- [x] 同步 `bib_entries.reading_status`
  - 有可读文件但未开始时 `has_pdf`
  - 运行中 `reading`
  - 成功后 `read`
  - 失败或取消时回退 `has_pdf`
- [x] 增加测试文件 `backend/tests/test_reading.py`
  - 覆盖鉴权、owner 校验、`jobs` 入库、`job_bib_entries`、`artifacts`、`reading_status`
  - 模型调用与 PDF 提取通过 fake worker/mock 替代

#### P4 验收

```bash
$ venv/Scripts/python -m unittest backend.tests.test_reading -v
Ran 10 tests in 19.xxs
OK

$ venv/Scripts/python -m unittest backend.tests.test_auth backend.tests.test_upload backend.tests.test_filter -v
Ran 22 tests in 42.xxs
OK
```

#### P4 已落地测试

- [x] `test_reading_long_requires_authentication`
  - 未登录调用 `/api/reading/long/start` 返回 `401`
- [x] `test_reading_quant_requires_authentication`
  - 未登录调用 `/api/reading/quant/start` 返回 `401`
- [x] `test_reading_qual_requires_authentication`
  - 未登录调用 `/api/reading/qual/start` 返回 `401`
- [x] `test_reading_rejects_non_owned_file`
  - 用户 A 不能对用户 B 的 `file_id` 发起精读
- [x] `test_reading_rejects_unsupported_file_type`
  - `bibliography/txt` 不能直接作为 reading 输入
- [x] `test_reading_long_creates_job_target_link_and_artifact`
  - `jobs / job_bib_entries / artifacts / reading_status` 都正确落库
- [x] `test_reading_reuses_existing_bib_entry_for_source_file`
  - 同一 `source_file_id` 多次精读时复用已有文献档案
- [x] `test_quant_writes_step_and_final_artifacts`
  - 七步精读的步骤产物与最终报告都能入 `artifacts`
- [x] `test_reading_status_and_cancel_require_owner`
  - status / cancel 接口做 owner 隔离
- [x] `test_reading_status_endpoint_replays_db_result`
  - 运行态缓存缺失时，仍能从 DB 重建任务结果

#### P4 注意点

- `reading.py` 现在仍是“匿名路由 + 平铺输出文件”的旧模型；P4 要避免出现“文件写盘成功，但 DB 中没有 job/artifact 记录”的双轨状态。
- `reading.py` 已切到“运行态内存缓存 + DB 持久记录”的模式；后续不要再回退到只写磁盘、不写 job/artifact 的实现。
- `source_file_id` 代表可读正文文件，P4 已优先围绕它把 PDF/MD 与 `bib_entries` 绑定起来，避免后面历史页再倒推。
- `job_bib_entries.role` 目前只需用 `target`；不要提前把 compare/synthesis 的多文献语义混进来。
- `artifacts.artifact_type` 已按约束使用：中间步骤用 `reading_step`，最终报告用 `reading_final`，后续继续沿用。
- 当前 long/quant/qual 的 markdown 模板仍然不同；P4 先统一了“DB 记录形态”和“输出目录规则”，模板差异可后续再收敛。

### 4.8 P5 已交付

> 目标已达成：现有 `/api/compare/*` 和 `/api/history/synthesis/*` 已从“匿名即时生成 + 单独写磁盘文件”改造成“有用户归属的多文献任务入口”，compare/synthesis 现已正式进入 `jobs` / `job_bib_entries` / `artifacts` 多用户模型。

#### P5 已达成的结果

- `POST /api/compare/analyze`、`POST /api/compare/analyze_long` 全部接入 `current_user`
- compare 输入正式支持 `bib_entry_ids`
  - 每个 id 都要求属于当前用户
  - compare 至少要求 2 篇文献
  - 继续兼容当前前端传入的 `paperData`，但服务端成员解析与权限判断优先以 `bib_entry_ids` 为准
- 每次 compare 创建一条 `jobs(job_type='compare')`
  - `owner_user_id` = 当前用户
  - `params_json` 写入 step/dimension/mode/subQuestions
  - `status` 覆盖 `pending -> running -> success`
- 每次 compare 写多条 `job_bib_entries(role='compare_member')`
  - `sort_order` 保持前端所选顺序
  - 同一 job 内重复成员会自动去重
- compare 输出写入 `artifacts(compare_md)`
  - 结果路径采用 `deep_reading_results/{uid}/{job_id}/compare_*.md`
  - 返回体继续保留 `synthesis` 文本，兼容当前 compare 页面展示
- `POST /api/history/synthesis/` 已改造成有鉴权的“保存综述”
  - 创建 `jobs(job_type='synthesis')`
  - 对传入成员写 `job_bib_entries(role='synthesis_member')`
  - 综述文件写 `artifacts(synthesis_md)`
- `GET /api/history/synthesis/` 已改为基于 `artifacts + jobs` 按当前用户列出
  - 首版仅返回当前用户
  - admin 跨用户查询继续留到 P6

#### P5 工作清单

- [x] 改造 `backend/routers/compare.py`
  - compare 接口接入 `Depends(current_user)`
  - 入参增加 `bib_entry_ids`
  - 根据 `bib_entry_ids` 校验 owner，并构造 compare 成员列表
  - 创建 `jobs(type='compare')`
  - 写入 `job_bib_entries(role='compare_member')`
  - 生成 compare 结果 markdown，并写入 `artifacts(compare_md)`
- [x] 兼容当前 compare 页面
  - 返回体继续包含 `synthesis`
  - 短期保留 `paperData` 兼容，但服务端优先信任 `bib_entry_ids`
- [x] 改造 `backend/routers/history.py` 中的 synthesis 部分
  - `POST /api/history/synthesis/` 接入 `current_user`
  - 保存时创建 `jobs(type='synthesis')`
  - 写入 `job_bib_entries(role='synthesis_member')`
  - 产物落 `artifacts(synthesis_md)`
  - `GET /api/history/synthesis/` 按当前用户读取 DB 记录
- [x] 统一 synthesis 路径
  - 旧逻辑：`deep_reading_results/synthesis/*.md`
  - 新逻辑：`deep_reading_results/{uid}/{job_id}/synthesis_*.md`
- [x] 增加测试文件 `backend/tests/test_compare.py`
  - 覆盖鉴权、owner 校验、`jobs` 入库、`job_bib_entries(compare_member/synthesis_member)`、artifact 落库
  - LLM 调用使用 fake OpenAI/mock 替代

#### P5 验收

```bash
$ venv/Scripts/python -m unittest backend.tests.test_compare -v
Ran 9 tests in 17.xxs
OK

$ venv/Scripts/python -m unittest backend.tests.test_auth backend.tests.test_upload backend.tests.test_filter backend.tests.test_reading -v
Ran 32 tests in 61.xxs
OK
```

#### P5 已落地测试

- [x] `test_compare_requires_authentication`
  - 未登录调用 compare 返回 `401`
- [x] `test_compare_rejects_non_owned_bib_entry`
  - 用户 A 不能拿用户 B 的 `bib_entry_id` 参与 compare
- [x] `test_compare_requires_at_least_two_members`
  - compare 成员少于 2 篇返回 `400`
- [x] `test_compare_creates_job_and_compare_members`
  - `jobs(type='compare')` 正确写入
  - `job_bib_entries(role='compare_member')` 多条写入成功
- [x] `test_compare_keeps_response_text_for_frontend`
  - 返回体继续包含 `synthesis`
- [x] `test_save_synthesis_requires_authentication`
  - 未登录调用 `/api/history/synthesis/` 返回 `401`
- [x] `test_save_synthesis_creates_job_members_and_artifact`
  - 保存综述时创建 `jobs(type='synthesis')`
  - 写入 `job_bib_entries(role='synthesis_member')`
  - 写入 `artifacts(synthesis_md)`
- [x] `test_list_synthesis_only_returns_current_user_records`
  - A 看不到 B 的 synthesis 历史
- [x] `test_synthesis_paths_use_uid_jobid_layout`
  - 综述产物路径采用 `deep_reading_results/{uid}/{job_id}/`

#### P5 注意点

- compare 前端当前仍会传 `paperData`；后端现已兼容旧载荷，但持久化与权限判断必须继续以 `bib_entry_ids` 为准。
- `job_bib_entries.role` 在 P5 已新增使用 `compare_member` 和 `synthesis_member`，后续不要与 P4 的 `target` 语义混用。
- `compare` 与 `synthesis` 都会产出 markdown，但 `artifact_type` 已分别固定为 `compare_md` 与 `synthesis_md`。
- `/api/history/` 总列表和 `/api/download/*` 的细粒度权限校验仍留给 P6；P5 先把 synthesis 子路由切成 DB 驱动并限制为“仅当前用户”。

### 4.9 P6 规划

> 目标：把现有 `/api/history/*` 和 `/api/download/*` 从“匿名按磁盘扫目录/按路径取文件”改造成“基于 `jobs + artifacts` 的用户隔离历史入口”，补齐列表、预览、删除、下载四类权限校验。

#### P6 要达成的结果

- `GET /api/history/` 接入 `current_user`
  - 仅返回当前用户自己的历史产物
  - 数据源改为 `artifacts + jobs`，不再直接扫全局目录
  - 需要按前端当前结构继续返回 `reading / filter / all`
- `GET /api/history/{filename}/preview` 接入 `current_user`
  - 只能预览当前用户自己的 artifact
  - markdown 继续渲染 HTML，其它类型继续给下载提示页
  - 下载链接仍保持 `/api/download/{filename}` 兼容现有前端
- `DELETE /api/history/{filename}` 接入 `current_user`
  - 仅允许删除当前用户自己的 artifact
  - 删除物理文件后同步删除 `artifacts` 记录
  - 若该 job 已无任何 artifact，可保留 job 本身，后续历史页按 artifact 驱动自然不可见
- `GET /api/download/{file_path}` 接入 `current_user`
  - 常规用户仅可下载自己的 artifact
  - admin 允许跨用户下载
  - 继续兼容当前前端传 `filename` 或相对 `storage_path`
- 为前端兼容保留现有 URL 形状
  - `frontend/src/App.tsx` 和现有 compare HTML 仍在传 `filename`
  - 因此服务端需要支持“先按 `storage_path` 精确匹配，再按 `filename` 在当前用户范围内查 artifact”

#### P6 工作清单

- [ ] 改造 `backend/routers/history.py`
  - `GET /api/history/` 接入 `Depends(current_user)`
  - 历史列表改为从 `artifacts + jobs` 查询，而不是 `_list_files()` 扫目录
  - `GET /{filename}/preview` 做 owner 校验
  - `DELETE /{filename}` 做 owner 校验，并同步删除对应 `artifacts` 记录
- [ ] 改造 `backend/routers/download.py`
  - 接入 `Depends(current_user)`
  - 先按传入值匹配 `Artifact.storage_path`
  - 若不是相对路径，再回退到按 `Artifact.filename` 匹配当前用户可见记录
  - admin 允许跨用户访问；normal/vip 仅允许访问自己的 artifact
- [ ] 统一历史数据来源
  - `reading` 分类：`reading_step / reading_final`
  - `filter` 分类：`filter_excel`
  - `synthesis` 已在 P5 独立改造，P6 不回退其 DB 驱动模式
- [ ] 保持前端兼容
  - 不修改现有前端请求路径
  - 后端继续返回 `filename / path / download_path / type / modified`
- [ ] 增加测试文件 `backend/tests/test_history.py`
  - 覆盖鉴权、owner 校验、admin 例外、列表隔离、预览/下载/删除权限

#### P6 当前测试设计是否需要补充

结论：**需要单独新增一组 history/download 测试**。目前自动化测试覆盖了 upload/filter/reading/compare/synthesis 的 owner 隔离，但还没有锁住以下高风险路径：
- 未登录直接调 `/api/history/`
- 用户 A 预览或删除用户 B 的 artifact
- 用户 A 直接拼 `/api/download/{filename}` 下载用户 B 的文件
- 历史列表是否会混入他人 `reading_final` / `filter_excel`
- admin 是否能按设计例外访问跨用户 artifact

#### P6 测试用例规划

- [ ] `test_history_list_requires_authentication`
  - 未登录调用 `/api/history/` 返回 `401`
- [ ] `test_history_list_only_returns_current_user_artifacts`
  - A 的历史列表中不出现 B 的 `reading/filter` 产物
- [ ] `test_history_preview_requires_owner`
  - 用户 A 不能预览用户 B 的 markdown artifact
- [ ] `test_history_delete_requires_owner`
  - 用户 A 不能删除用户 B 的 artifact
- [ ] `test_history_delete_removes_artifact_record_and_file`
  - 删除自己的历史文件时，物理文件与 `artifacts` 记录同时消失
- [ ] `test_download_requires_authentication`
  - 未登录调用 `/api/download/*` 返回 `401`
- [ ] `test_download_rejects_non_owned_artifact`
  - 用户 A 不能下载用户 B 的 artifact
- [ ] `test_download_accepts_storage_path_for_owner`
  - 当前用户可通过 `storage_path` 下载自己的 artifact
- [ ] `test_download_accepts_filename_for_owner`
  - 当前用户可继续通过 `filename` 下载自己的 artifact，兼容旧前端
- [ ] `test_admin_can_download_other_users_artifact`
  - admin 可以下载其他用户 artifact

#### P6 注意点

- 前端当前并未统一传 `storage_path`，仍大量使用 `filename`；P6 后端必须兼容两种输入，避免先改后端把现有页面打坏。
- `history.py` 和 `download.py` 在 P6 之后应以 `artifacts` 为唯一可信来源，不再把“磁盘里恰好有文件”视为可直接访问的依据。
- `DELETE /api/history/{filename}` 的语义是“删除当前用户的一条历史产物”，不是“按文件名全局删除所有同名文件”；实现时必须限定在用户可见范围内匹配。
- `synthesis` 子路由在 P5 已切到 DB 驱动；P6 只是在总历史和下载链路上把剩余匿名入口补齐，不要回退 P5 的实现。

## 5. 已知问题与待办

| 问题 | 说明 | 处理时机 |
|---|---|---|
| `.gitignore` 之前的 `db/` 误伤 `backend/db/` | 已改成 `/db/` 锚定仓库根 | 已修 |
| `seed_admin.py` 用 `datetime.utcnow()` 触发弃用警告 | 已在 P1 顺手改成 `datetime.now(UTC)` | 已修 |
| `deploy.sh` 没有自动跑 alembic | 当前决定继续手动迁移，只有 schema 变更时 SSH 执行 `alembic upgrade head` | 暂按此流程 |
| `backend/requirements.txt` 原先缺少 `markdown` | 本地导入 `main.py` 时发现 `history.py` 依赖未声明，已补 `markdown>=3.6` | 已修 |
| `backend/requirements.txt` 原先缺少 `pandas/openpyxl` | P3 跑 `filter` 测试时发现筛选链路和 Excel 导出依赖未声明，已补齐 | 已修 |
| 部署服务器还没装 P1 新依赖 | 等最终统一 push 后，服务器自动部署会装依赖；若含迁移仍需手动跑 alembic | P1/P2 上线时 |

## 6. 联系点

- Cloudflare Tunnel 域名：https://deepreading.qzz.io/
- 服务器路径：`/root/.openclaw/workspace/deep-reading-agent`
- 自动部署触发：push 到 `online` 分支
- 主分支：`main`（PR 目标），当前工作分支：`online`

# 多用户系统 实施进度

> **更新时间**：2026-04-26（P2 本地完成）  
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

### 4.3 当前本地状态

```bash
P1 已本地 commit；P2 已本地实现并验证完成。
当前仍按约定：先继续本地迭代与提交，暂不 push。
```

说明：
- P1 改动已 **本地 commit**
- P2 改动会与本轮文档同步一起进入 **本地 commit**
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

### 4.6 P3 规划

> 目标：把现有 `/api/filter/*` 从“匿名内存任务 + 仅导出 Excel”改造成“有用户归属的筛选任务入口”，并在筛选过程中把题录正式沉淀到 `bib_entries` / `bib_filter_links` / `jobs`。

#### P3 要达成的结果

- `POST /api/filter/start`、`GET /api/filter/task/{task_id}/status`、`POST /api/filter/task/{task_id}/cancel` 全部接入 `current_user`
- 启动筛选时校验 `file_id` 属于当前用户，且输入文件类型必须是 `bibliography`（必要时兼容内容嗅探为题录的 `txt`）
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
- P3 完成后，应能在 DB 中回答两个问题：
  - “这次筛选输出了哪些文献？”
  - “这篇文献被哪几次筛选打过分？”

#### P3 工作清单

- [ ] 改造 `backend/routers/filter.py`
  - `POST /start` 增加 `Depends(current_user)`
  - `GET /task/{task_id}/status` 增加 owner 校验
  - `POST /task/{task_id}/cancel` 增加 owner 校验
- [ ] 统一筛选任务主键
  - 继续复用现有 `task_id` 作为 `jobs.id`
  - 内存 `tasks` 仅保留运行态缓存；数据库中的 `jobs` 作为可追踪记录
- [ ] 启动任务前校验输入文件
  - `file_id` 必须存在
  - 文件必须属于当前用户
  - 文件类型应为 `bibliography`；若仍是旧数据中的 `txt`，需按内容再次嗅探
- [ ] 创建 `jobs(type='filter')`
  - 写入 `owner_user_id / input_file_id / params_json / expires_at`
  - 初始状态 `pending`
  - 启动线程后切到 `running`
  - 成功时更新为 `success`
  - 失败时更新为 `failed`
  - 取消时更新为 `canceled`
- [ ] 解析题录并标准化字段
  - 标题、作者、年份、DOI、期刊、摘要、关键词
  - 统一空值处理，避免把 `NaN` / 空字符串直接写库
- [ ] 计算并应用 `dedup_key`
  - 优先 DOI
  - 否则 `first_author + year + normalized_title`
  - 命中同用户唯一约束时复用已有 `bib_entries`
- [ ] 写入 `bib_entries`
  - `source_db` 从解析器来源决定
  - `source_filter_job_id` 仅首次创建时写入
  - `metadata_completeness` 与 `reading_status` 正确初始化
  - `updated_at` 在重复命中时刷新
- [ ] 写入 `bib_filter_links`
  - 至少为“进入本次筛选链路的文献”建立链接
  - 对最终入选结果标记 `passed=1`
  - 对未通过记录保留 `passed=0`
  - `score / reason` 与导出结果一致
- [ ] 评估是否在 P3 同步写 `artifacts(filter_excel)`
  - 按总 schema，筛选 Excel 最终应归入 `artifacts`
  - 若本次不做，需在文档中明确为 P3.5/P5 前的补口项，避免历史接口再次出现双轨状态
- [ ] 增加测试文件 `backend/tests/test_filter.py`
  - 先覆盖鉴权、owner 校验、`jobs` 入库、`bib_entries` 去重、`bib_filter_links` 写入
  - AI 调用与解析器输出可用 mock/fixture 固定

#### P3 当前测试设计是否需要补充

结论：**需要明显补充**。当前后端自动化测试只有：
- `test_auth.py`
- `test_upload.py`

这意味着与 P3 直接相关的内容目前全部没有自动化保护：
- `filter` 路由的鉴权与 owner 校验
- `jobs` 表写入与状态流转
- `bib_entries` 的去重 / 复用
- `bib_filter_links` 的 `passed / score / reason`
- 不同用户之间的文献隔离

因此，P3 开工前应把测试设计从“只有方向”补成明确用例清单。

#### P3 测试用例规划

- [ ] `test_filter_start_requires_authentication`
  - 未登录调用 `/api/filter/start` 返回 `401`
- [ ] `test_filter_status_requires_owner`
  - 用户 A 发起的筛选任务，用户 B 查询 `/task/{task_id}/status` 返回 `404` 或 `403`
- [ ] `test_filter_cancel_requires_owner`
  - 用户 B 不可取消用户 A 的筛选任务
- [ ] `test_filter_rejects_non_owned_file`
  - 当前用户传入他人 `file_id` 时返回 `404` 或 `403`
- [ ] `test_filter_rejects_non_bibliography_file`
  - 拿 `pdf/docx/markdown` 文件调用筛选返回 `400`
- [ ] `test_filter_creates_job_record`
  - 启动筛选后 `jobs` 表新增 `job_type='filter'` 记录
  - `owner_user_id / input_file_id / params_json / expires_at` 正确
- [ ] `test_filter_job_status_transitions`
  - `pending -> running -> success`
  - 异常场景写入 `failed + error_msg`
- [ ] `test_filter_creates_bib_entries_from_parsed_rows`
  - 解析出的文献写入 `bib_entries`
  - `title / authors_json / year / source_db / metadata_completeness` 正确
- [ ] `test_filter_reuses_existing_bib_entry_for_same_user`
  - 同一用户第二次筛到同一文献时不新增 `bib_entries`
  - 只新增新的 `bib_filter_links`
- [ ] `test_filter_creates_separate_bib_entries_for_different_users`
  - 不同用户筛到同一文献时，各自产生自己的档案
- [ ] `test_filter_writes_bib_filter_links_with_passed_and_score`
  - `passed / score / reason` 正确落库
- [ ] `test_filter_sets_normal_user_expiry`
  - normal 用户创建的 `jobs / bib_entries` 带 24h `expires_at`
- [ ] `test_filter_vip_user_records_do_not_expire`
  - vip/admin 创建的 `jobs / bib_entries` 为 `NULL`
- [ ] `test_filter_handles_duplicate_rows_in_single_input`
  - 同一个题录文件里重复文献不会产生重复 `bib_entries`
  - 同一 job 下也不会违反 `UNIQUE (bib_entry_id, filter_job_id)`
- [ ] `test_filter_empty_after_basic_filter_marks_job_failed`
  - 基础过滤后无记录时，job 状态更新为 `failed`
  - 不留下半成品 link 记录

建议：
- `backend/tests/test_filter.py` 采用“mock 解析器 + mock AI evaluator”的方式，避免依赖外部 API。
- 先把“路由鉴权 / job 入库 / bib 去重 / link 写入 / 用户隔离”作为必测最小集；Excel 内容细节可放到次级测试。
- 若 P3 顺手把 `filter_excel` 写入 `artifacts`，应再补：
  - `test_filter_creates_filter_excel_artifact`
  - `test_filter_artifact_owner_matches_job_owner`

#### P3 注意点

- 当前 `filter.py` 仍是“匿名路由 + 内存 tasks + 导出 Excel”的旧模型；P3 需要避免出现“前端看到成功，但 DB 没有 job / bib / link 记录”的双轨状态。
- `source_file_id` 在 `bib_entries` 中表示可读正文文件（PDF/MD），不是题录输入文件；P3 不要把 bibliography 文件误绑到 `source_file_id`。
- `source_filter_job_id` 表示文献第一次进入系统的筛选任务；若命中去重的旧档案，后续筛选不应覆盖这个“首次来源”。
- `bib_filter_links` 的 `passed` 需要语义固定：建议以“最终导出结果中是否保留”为准，而不是“是否进入 AI 评估阶段”。
- 目前 `filter.py` 的状态接口按 `task_id` 查内存；P3 实现时最好让 DB `jobs.id` 与内存 `task_id` 保持一致，减少状态映射复杂度。
- 若 P3 本次不落 `artifacts(filter_excel)`，必须在下一阶段文档中明确补口；否则历史/下载改造时会再次面对“文件在磁盘但 DB 无记录”的问题。

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

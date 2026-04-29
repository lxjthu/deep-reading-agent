# 多用户管理 实施计划

> **版本**: v1.1  
> **日期**: 2026-04-26  
> **关联文档**: [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)

## 1. 总体目标

把当前"单机无认证"的 Deep Reading Agent 改造成"多用户 SaaS 风格"系统，部署地址保持 `https://deepreading.qzz.io/`：

1. 注册 / 登录 / JWT 鉴权
2. 三种角色：admin / vip / normal
3. 普通用户 24h 数据自动清理；VIP 永久；admin 永久
4. 全部业务数据按用户隔离，并通过 `bib_entries` 串联文献档案
5. 管理员后台：用户管理 + 邀请码管理
6. 为"MD 上传"和"文件夹批量上传"预留扩展点

## 2. 角色与权限矩阵

| 能力 | normal | vip | admin |
|---|:-:|:-:|:-:|
| 自由注册登录 | ✓ | 注册需邀请码 | 内置 |
| 上传 PDF/题录/MD | ✓ | ✓ | ✓ |
| 文献筛选 | ✓ | ✓ | ✓ |
| 长文本/七步/四步精读 | ✓ | ✓ | ✓ |
| 对比分析 | ✓ | ✓ | ✓ |
| AI 综述 | ✓ | ✓ | ✓ |
| **数据保留** | **24h** | 永久 | 永久 |
| 看其他用户数据 | ✗ | ✗ | ✓（只读） |
| 生成邀请码 | ✗ | ✗ | ✓ |
| 升降级用户 | ✗ | ✗ | ✓ |
| 重置用户密码 | ✗ | ✗ | ✓ |

## 3. 后端 API 改造

### 3.1 新增路由

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/auth/register` | POST | 注册（可选邀请码） |
| `/api/auth/login` | POST | 登录，返回 access + refresh token |
| `/api/auth/refresh` | POST | 用 refresh 换新 access |
| `/api/auth/me` | GET | 当前用户信息（含 role、warning_msg） |
| `/api/auth/logout` | POST | 递增 `users.token_version`，撤销该用户现有 refresh token |
| `/api/auth/change_password` | POST | 修改密码 |
| `/api/admin/users` | GET | 用户列表 |
| `/api/admin/users/{id}` | PATCH | 改 role、重置密码、停用 |
| `/api/admin/invite_codes` | GET/POST | 邀请码列表 / 生成 |
| `/api/admin/invite_codes/{id}` | DELETE | 撤销邀请码 |
| `/api/admin/stats` | GET | 用户量、文件量、任务量 |
| `/api/bib/` | GET | 当前用户的文献列表（含筛选/排序/搜索） |
| `/api/bib/{id}` | GET/PATCH/DELETE | 文献档案详情 / 修改元数据 / 删除 |
| `/api/bib/{id}/pdf` | POST | 给文献绑定 PDF（上传新文件或选已有） |
| `/api/bib/manual` | POST | 手动新建文献档案 |
| `/api/bib/{id}/timeline` | GET | 文献的事件链（所有 jobs + artifacts） |

### 3.2 现有路由改造清单

所有现有路由都加 `Depends(current_user)`，并按 `owner_user_id` 过滤。

| 路由 | 改造点 |
|---|---|
| `/api/upload/` | ① file 写到 `_uploads/{uid}/`；② 写入 `files` 表；③ 计算 `expires_at`；④ PDF/MD 自动调用 metadata_extractor 创建/匹配 `bib_entries` |
| `/api/upload/{file_id}/info` | 仅查当前用户的 file |
| `/api/filter/` | ① 题录解析后写入 `bib_entries`（source_db='wos'/'cnki'）；② 创建 `jobs(type='filter')`；③ 写入 `bib_filter_links` |
| `/api/reading/long` `/quant` `/qual` | ① 创建 `jobs(type='reading_*')`；② 写 `job_bib_entries(role='target')`；③ 产物落库 `artifacts`；④ 结构化结果落库 `reading_items`；⑤ 完成时更新 `bib_entries.reading_status='read'` |
| `/api/compare/` | ① 输入改成 bib_entry_ids；② 创建 `jobs(type='compare')`；③ 写多条 `job_bib_entries(role='compare_member')`；④ 直接从 `reading_items` 聚合对比数据 |
| `/api/history/` | 仅列当前用户的 jobs/artifacts；admin 可加 `?owner_user_id=` |
| `/api/history/synthesis/` | 仅列当前用户的 synthesis；写入时创建 `jobs(type='synthesis')` + `artifacts` |
| `/api/download/{filename}` | 校验 filename 对应 artifact 的 owner_user_id；admin 例外 |
| `/api/prompts/` | 提示词全局共享（不按用户隔离） |
| `/api/deploy/` | 仅 admin 可用（加 `Depends(require_admin)`） |

### 3.3 鉴权中间件

```python
# backend/auth/dependencies.py
async def current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)) -> User:
    """从 JWT 解析 user，注入到路由"""

async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    return user

async def require_vip_or_admin(user: User = Depends(current_user)) -> User:
    if user.role not in ("admin", "vip"):
        raise HTTPException(403, "VIP required")
    return user
```

### 3.4 JWT 配置

| 项 | 值 |
|---|---|
| 算法 | HS256 |
| 密钥 | `JWT_SECRET_KEY`（.env） |
| access TTL | 1 小时 |
| refresh TTL | 30 天 |
| 存放 | access 在前端 memory + localStorage；refresh 也在 localStorage（v1）。后续再改为 HttpOnly cookie |

补充约定（P1）：
- 严格 logout 采用 `users.token_version` 方案，不单独维护 `refresh_tokens` 表。
- 签发 refresh token 时，将当前 `token_version` 写入 JWT claim。
- `/api/auth/refresh` 必须校验 token 内版本号与数据库当前 `users.token_version` 一致。
- `/api/auth/logout` 和 `/api/auth/change_password` 都递增 `users.token_version`，使旧 refresh token 全部失效。
- 该方案为用户级撤销：一个设备 logout 后，该用户其他设备上的旧 refresh token 也会失效。

## 4. 前端改造

### 4.1 路由（引入 react-router-dom）

```
/                  → 登录后重定向到 /workspace
/login             → 登录页
/register          → 注册页（含邀请码输入框）
/workspace         → 主工作台（现有 7 个 tab）
/workspace/library → 我的文献库（基于 bib_entries 的新页面）⭐
/admin             → 管理员后台（仅 admin 可见）
```

路由守卫：
- 未登录访问 `/workspace*` → 跳 `/login`
- 非 admin 访问 `/admin` → 403 提示

### 4.2 顶栏改造

```
┌──────────────────────────────────────────────────────────────┐
│ ❤️‍🔥 Deep Reading Agent    [Tab1][Tab2]...   👤 张三 [VIP] ▼ │
└──────────────────────────────────────────────────────────────┘
                                                       │
                                                       └─ 个人设置
                                                          API Key
                                                          切换账号
                                                          退出登录
```

`[VIP]` 徽章颜色：admin=紫、vip=金、normal=灰。

### 4.3 普通用户警告横幅 ⭐

登录后**永久顶栏横幅**（不可关闭）：

```
⚠️  您是免费试用账户，所有上传文件、文献档案、精读结果将在 24 小时后自动清空。
   请及时下载您的产出文件，或联系管理员升级 VIP（永久保存）。
   提示：DeepSeek API Key 保存在您的浏览器本地，不受清理影响。
```

API Key 设置面板继续沿用现有"localStorage 保存"逻辑，**服务端不存储 key**。

### 4.4 我的文献库（新页面 `/workspace/library`）

这是文献追踪功能的承载页：

```
┌─────────────────────────────────────────────────────────────────┐
│ 我的文献库                              [+ 手动添加] [批量上传 PDF]│
│ 筛选: [全部 ▼] [已下载 PDF] [已精读] [来自筛选 J1 ▼] 搜索: [___]│
├─────────────────────────────────────────────────────────────────┤
│ ☆ 标题............................. │作者│年│状态│操作          │
│ ★ Effect of X on Y................... 张三 2024 [已精读] [查看]│
│ ☆ A Study of Z....................... 李四 2023 [仅PDF] [开始精读]│
│ ☆ The Impact of W.................... 王五 2025 [题录] [上传PDF]│
└─────────────────────────────────────────────────────────────────┘
```

点击一篇文献 → 抽屉式详情页：
- 元数据（可编辑：title/authors/year/doi/journal/abstract/keywords/tags/note）
- 文件区：PDF（缺则提示上传）
- 事件时间线：所有 reading/compare/synthesis job 及其产物
- "缺失字段补全"提示条（当 metadata_completeness != 'full'）

### 4.5 管理员后台 `/admin`

| 子页 | 功能 |
|---|---|
| 用户管理 | 列表 / 改 role / 重置密码 / 停用 |
| 邀请码 | 生成（指定用途/有效期/可用次数） / 列表 / 撤销 |
| 系统统计 | 用户数（按角色）、文件总量、任务总量、清理日志 |

## 5. 实施阶段

| 阶段 | 范围 | 预估工时 | 验收标准 |
|---|---|:-:|---|
| **P0** | DB schema + Alembic 初始化 + admin seed | 0.5d | `alembic upgrade head` 成功，`users` 表有 admin |
| **P1** | `/api/auth/*` + JWT 中间件 + `users.token_version` | 1d | Postman 跑通注册/登录/me/refresh/logout 全流程 |
| **P2** | `/api/upload/*` 改造 + `files` 表 + 按用户分目录 | 0.5d | 两个用户分别上传，文件物理隔离 |
| **P3** | `/api/filter/*` 改造 + `bib_entries` + `bib_filter_links` 写入 | 1d | 上传题录跑筛选后，`bib_entries` 表里看到 100+ 条记录 |
| **P4** | `/api/reading/*` 改造 + `jobs` + `job_bib_entries` + `reading_items` + `artifacts` | 1d | 跑一次精读后，结构化结果和 Markdown 产物都正确落库 |
| **P5** | `/api/compare/*` `/api/history/synthesis/*` 改造 | 0.5d | 对比 / 综述按 bib_entry_ids 输入跑通，compare 直接读取 `reading_items` |
| **P6** | `/api/history/*` `/api/download/*` 加权限校验 | 0.5d | 用户 A 无法下载用户 B 的文件 |
| **P7** | 邀请码 + VIP 升降级 + 24h 清理任务（APScheduler） | 1d | 模拟 24h 后普通用户服务端全部数据消失（前端 localStorage 不动） |
| **P8** | 历史数据迁移脚本（无主文件归 admin） | 0.5d | 跑完后 `_uploads/1/` 下有原 `yaojiaquan.pdf`，DB 有对应 file 记录 |
| **P9** | 前端 react-router 接入 + 登录/注册页 | 1d | 浏览器访问跳登录页，注册成功跳工作台 |
| **P10** | 前端顶栏改造 + 24h 警告横幅（API Key 仍走前端 localStorage） | 0.5d | normal 用户登录看到红色警告横幅 |
| **P11** | 前端"我的文献库"页面（v1：列表 + 详情抽屉 + 元数据补全） | 2d | 能看到所有文献、点开看时间线、缺失字段补全 |
| **P12** | 前端管理员后台（用户列表 + 邀请码管理） | 1d | admin 能生成邀请码、改用户角色 |
| **P13** | E2E 测试 + 手动验收 + 部署到 online 分支 | 1d | Playwright 跑通注册→上传→精读→24h 清理 |

**总计：约 11 个工作日**

**预留扩展（不计入本期）**：
- MD 文档作为精读输入（schema 已支持，前端实现 0.5d）
- 文件夹批量上传（schema 已支持，前后端实现 1.5d）
- 批量精读（0.5d）

## 6. 文件目录改造前后对照

**改造前**：
```
_uploads/yaojiaquan.pdf
deep_reading_results/yaojiaquan/Final_Deep_Reading_Report.md
deep_reading_results/literature_filter/filtered_xxx.xlsx
deep_reading_results/synthesis/synthesis_xxx.md
```

**改造后**：
```
_uploads/
  1/                                       # admin (uid=1)
    {file_id_uuid}.pdf
    {file_id_uuid}.txt                     # 题录
  2/                                       # 某 vip
    {file_id_uuid}.pdf
deep_reading_results/
  1/
    {job_id_uuid}/
      Step_1_xxx.md
      Step_2_xxx.md
      Final_Deep_Reading_Report.md
    {job_id_uuid_filter}/
      filtered_screened.xlsx
    {job_id_uuid_synthesis}/
      synthesis_xxx.md
db/
  app.sqlite
  backups/
    2026-04-26.sqlite
  cleanup.log
```

## 7. 配置与密钥

`.env` 新增：

```bash
# 多用户系统
JWT_SECRET_KEY=<openssl rand -hex 32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# 数据库
DATABASE_URL=sqlite+aiosqlite:///./db/app.sqlite

# 清理任务
CLEANUP_INTERVAL_MINUTES=60
CLEANUP_DRY_RUN=false                  # 上线前先 true 跑几轮看日志

# 管理员账号 seed（可选，仅初次部署用）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=XIAojuan@0618wenxian
```

## 8. 依赖更新

`backend/requirements.txt` 新增：

```
sqlalchemy>=2.0.0
aiosqlite>=0.19.0
alembic>=1.13.0
passlib[bcrypt]>=1.7.4
python-jose[cryptography]>=3.3.0
apscheduler>=3.10.0
email-validator>=2.0.0
```

`frontend/package.json` 新增：

```json
{
  "react-router-dom": "^6.22.0",
  "zustand": "^4.5.0",
  "axios": "^1.6.0"
}
```

> 说明：`zustand` 用作轻量全局状态（user / token），`axios` 替代 fetch 便于统一注入 Authorization header。

## 9. 测试策略

### 9.1 后端单元测试（pytest）

| 模块 | 覆盖点 |
|---|---|
| `auth/` | 注册（含邀请码校验）、登录、JWT 签发/验证、过期处理、`token_version` 撤销逻辑 |
| `db/models.py` | 唯一约束、级联删除、`compute_dedup_key` |
| `cleanup.py` | mock 时间到 25h，验证清理生效；mock 5h 不动 |
| `routers/upload.py` | 跨用户上传隔离 |
| `routers/filter.py` | 题录解析 → `bib_entries` 入库 + `bib_filter_links` |
| `routers/reading.py` | reading job 完成后 `bib_entries.reading_status='read'` |

### 9.2 E2E 测试（Playwright）

关键 journey：
1. 注册 normal → 看到警告横幅
2. 注册 vip（带邀请码）→ 看不到警告横幅
3. 上传 PDF → 在文献库看到自动创建的档案 → 提示补全元数据
4. 跑精读 → 产物列在文献时间线
5. admin 登录 → 进 `/admin` → 改某用户为 vip → 该用户 `expires_at` 全部清空
6. 模拟时间快进 24h → normal 用户服务端数据全部清空（前端 localStorage 内的 API Key 不动）

### 9.3 安全测试清单

- [ ] 用户 A 调用 API 加载用户 B 的 file → 401/403
- [ ] 直接拼 URL `/api/download/{file_belonging_to_other}` → 403
- [ ] SQL 注入：所有 LIKE 查询参数化
- [ ] JWT 过期/篡改 → 401
- [ ] logout 后旧 refresh token 再调用 `/api/auth/refresh` → 401
- [ ] 注册接口防爆破（rate limit）
- [ ] 密码强度校验（≥8 位，含字母数字）
- [ ] 邀请码限次防滥用

## 10. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 历史数据迁移失败 | 迁移脚本支持 `--dry-run`，先在备份库上跑；保留原文件 7 天 |
| 24h 清理误删 admin/vip 数据 | `cleanup.py` 在删除前打印 dry-run 日志，确认 `expires_at IS NOT NULL`，用 unit test 锁死 |
| JWT 密钥泄漏 | 一旦怀疑泄漏：轮换 `JWT_SECRET_KEY` → 所有用户被迫重新登录 |
| 用户 API Key 误用 | 服务端不存 key，泄漏面只剩用户浏览器；登录页提示用户使用独立配额或临时 key |
| SQLite 单文件损坏 | 每日备份 + WAL 模式 + 冷备脚本 |
| 部署后旧 URL 被外部直链 | 旧前端单页路径 `/?tab=...` 仍兼容；登录后引导到工作台 |

回滚：保留 P0 之前的 git tag `pre-multiuser-v3.0`，紧急时 `git reset --hard pre-multiuser-v3.0` + 删除 `db/app.sqlite`。

## 11. 上线前 Checklist

- [ ] `.env` 中所有新密钥已生成并备份
- [ ] `db/app.sqlite` 已通过 alembic 创建并 seed admin
- [ ] `db/backups/` 目录已创建，cron 已注册
- [ ] APScheduler 清理任务已启动（dry-run 跑 24h 看日志正常）
- [ ] 历史数据迁移脚本已成功跑完
- [ ] 前端构建通过、route guard 验证 OK
- [ ] Playwright E2E 全部通过
- [ ] 安全测试清单全部通过
- [ ] CHANGELOG.md 更新到 v4.0.0（多用户版本）
- [ ] README 更新登录/注册说明
- [ ] cloudflared tunnel 配置不变，部署到 online 分支验证

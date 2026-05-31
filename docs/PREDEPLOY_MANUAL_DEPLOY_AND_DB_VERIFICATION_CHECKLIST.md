# 上线前手动部署与数据库验证清单

> 类型：运维清单  
> 状态：可执行  
> 适用环境：`8.162.14.154:18080` / `codex/deepreading-empty-postgres-deploy`  
> 最后更新：2026-05-31  
> 关联文档：`MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`、`NEW_SERVER_SQL_MAINTENANCE.md`、`JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md`、`RESEARCH_AGENT_IMPLEMENTATION_ROADMAP_2026_05_31.md`

---

## 1. 使用范围

这份清单用于**每次准备把本地代码手动上线到 `8.162.14.154:18080` 前**做最终核对。

它不是完整部署手册，而是一个“上线前必须逐项勾选”的执行清单，重点覆盖：

- 本地改动是否已验证
- 上传包是否完整
- PostgreSQL 迁移是否真的打到了生产库
- systemd 重启方式是否正确
- 前端静态资源是否同步
- 上线后数据库和业务接口是否真实可用

---

## 2. 基本事实确认

上线前先确认本次操作的环境前提没有搞错。

- [ ] 当前目标服务器是 `http://8.162.14.154:18080/`
- [ ] 当前 SSH 入口是 `ssh root@8.162.14.154`
- [ ] 当前服务器项目目录是 `/root/deep-reading-agent`
- [ ] 当前后端服务由 `systemd` 管理，服务名为 `deepreading-api`
- [ ] 当前生产数据库应为 PostgreSQL，由 `/root/deep-reading-agent/.env.production` 中的 `DATABASE_URL` 提供
- [ ] 本次不会使用手动 `nohup uvicorn` 启动服务
- [ ] 本次不会把本地 `db/app.sqlite`、本地 `_uploads`、本地 `deep_reading_results` 上传到服务器

---

## 3. 本地代码范围检查

上线前先确认你要传什么，不要“顺手把整个目录都传上去”。

### 3.1 改动范围

- [ ] 已执行 `git status --short`
- [ ] 已执行 `git diff --name-only`
- [ ] 已确认本次改动文件列表
- [ ] 未把无关临时文件、压缩包、日志、缓存目录混进部署包

### 3.2 高风险改动识别

如果命中以下任一项，必须额外做数据库和业务验证：

- [ ] 改了 `backend/db/models.py`
- [ ] 改了 `backend/migrations/versions/*.py`
- [ ] 改了 `backend/services/data_portability.py`
- [ ] 改了 `backend/prompt_registry.py` / `backend/prompt_service.py` / `backend/routers/prompts.py`
- [ ] 改了 `frontend/src/*` 且需要重新构建 `frontend/dist`
- [ ] 改了与上传、导入导出、任务队列、精读、提示词、Research Agent 相关核心链路

### 3.3 明确禁止上传

- [ ] 不上传 `.env`、`.env.production`、密钥、API Key
- [ ] 不上传 `venv/`、`node_modules/`
- [ ] 不上传本地数据库文件
- [ ] 不上传本地用户文件、缓存目录、临时导出包

---

## 4. 本地验证清单

### 4.1 后端最低验证

- [ ] 已跑与本次改动直接相关的后端单测
- [ ] 至少跑过一次语法编译检查：

```powershell
python -m compileall backend new_architecture smart_literature_filter.py translation_pipeline.py
```

### 4.2 前端最低验证

如果改了前端：

- [ ] 已在 `frontend/` 下执行 `npm run build`
- [ ] 构建成功，无 TypeScript 阻塞错误
- [ ] 明确准备上传的是 `frontend/dist`，不是只传 `frontend/src`

### 4.3 数据库改动额外验证

如果改了 schema / migration / portability：

- [ ] 已在本地临时 SQLite 上从空库执行过 `alembic upgrade head`
- [ ] 已确认 `CURRENT_SCHEMA_VERSION` 与最新 migration 对齐
- [ ] 已确认新增用户数据表已同步考虑 `backend/services/data_portability.py`
- [ ] 已确认新增自增主键或跨表引用存在导入 remap 逻辑

建议命令：

```powershell
$env:DATABASE_URL="sqlite+aiosqlite:///D:/code/deepagent/deep-reading-agent-online/deep-reading-agent/tmp_migration_check.sqlite"
cd backend
python -m alembic upgrade head
python -m alembic current
cd ..
Remove-Item Env:DATABASE_URL
Remove-Item .\tmp_migration_check.sqlite -ErrorAction SilentlyContinue
```

---

## 5. 部署包准备清单

### 5.1 上传前确认

- [ ] 已根据 `git diff --name-only` 生成最小上传文件集
- [ ] 若有前端改动，已包含 `frontend/dist`
- [ ] 若有 migration 改动，已包含对应 `backend/migrations/versions/*.py`
- [ ] 若有 prompt type / prompt slot 改动，已包含：
  - `backend/prompt_registry.py`
  - `backend/prompt_service.py`
  - `backend/routers/prompts.py`
  - 对应 `prompts/.../*.md`

### 5.2 SCP 上传

- [ ] 已把部署包上传到服务器，例如 `/tmp/deploy-changes.tgz`

示例：

```powershell
scp deploy-changes.tgz root@8.162.14.154:/tmp/deploy-changes.tgz
```

---

## 6. 服务器解包前检查

登录服务器后，先确认操作位置和目标目录。

- [ ] 已 `ssh root@8.162.14.154`
- [ ] 当前操作目录确认是 `/root/deep-reading-agent`
- [ ] 不是旧路径 `/root/.openclaw/workspace/...`
- [ ] 未在错误目录执行覆盖或解包

解包示例：

```bash
cd /root/deep-reading-agent
tar -xzf /tmp/deploy-changes.tgz
```

---

## 7. 服务器端代码与静态资源检查

### 7.1 后端文件到位

- [ ] 已确认关键后端文件已覆盖到服务器
- [ ] 若改了 prompt / portability / router，已重点检查对应文件内容不是旧版

### 7.2 前端资源到位

如果改了前端：

- [ ] 已确认 `frontend/dist/index.html` 已更新
- [ ] 已确认 `frontend/dist/assets/` 中存在本次构建对应的新资源文件
- [ ] 没有出现“后端已更新但前端还是旧版”的情况

建议检查：

```bash
head -30 /root/deep-reading-agent/frontend/dist/index.html
ls -lt /root/deep-reading-agent/frontend/dist/assets | head
```

---

## 8. 服务器端数据库迁移前检查

这是最关键的一段。历史上最容易踩坑的是：**Alembic 看起来执行成功，但实际升级的是 SQLite，不是生产 PostgreSQL。**

### 8.1 环境确认

- [ ] 已激活 `/root/deep-reading-agent/venv`
- [ ] 已确认当前 shell 可读取生产环境变量
- [ ] 已确认 `.env.production` 存在
- [ ] 已确认当前目标库应是 PostgreSQL，而不是默认回退 SQLite

### 8.2 迁移执行前核验

执行 migration 前，至少做一项环境确认：

- [ ] 检查 `.env.production` 中 `DATABASE_URL` 指向 PostgreSQL
- [ ] 或用当前 shell 打印脱敏后的数据库连接信息，确认不是 SQLite
- [ ] 或通过业务配置确认 `systemd` 会加载 `.env.production`

### 8.3 migration 执行

如果本次包含 schema 变更：

- [ ] 已执行：

```bash
cd /root/deep-reading-agent/backend
source ../venv/bin/activate
python -m alembic upgrade head
python -m alembic current
```

- [ ] `alembic current` 显示的是最新 revision 且带 `(head)`

### 8.4 migration 后数据库真实性核验

不要只看 Alembic 退出码，至少再做一项真实性验证：

- [ ] 验证生产库中的 `alembic_version` 已更新
- [ ] 验证本次新增列 / CHECK / UNIQUE / 索引真实存在
- [ ] 验证新业务对象可真实插入，不会因旧约束报错

对高风险 schema 改动，建议至少做一条真实 SQL 或业务接口验证，而不是只看命令成功。

---

## 9. systemd 重启前检查

### 9.1 重启方式

- [ ] 本次将使用 `systemctl restart deepreading-api`
- [ ] 不会手动执行 `uvicorn`
- [ ] 不会手动 `nohup` 启动后台进程

### 9.2 为什么必须这样做

因为手动启动极易丢失 `EnvironmentFile` 中的 `DATABASE_URL`，服务会回退到空 SQLite，看起来像“数据没了”，但其实是连错库。

---

## 10. 服务重启与进程层验证

### 10.1 重启

- [ ] 已执行：

```bash
systemctl restart deepreading-api
sleep 5
```

### 10.2 状态与日志

- [ ] `systemctl status deepreading-api` 显示 active
- [ ] `/var/log/deepreading/api.log` 无明显启动异常
- [ ] `/var/log/deepreading/api-error.log` 无新的致命错误

建议检查：

```bash
systemctl status deepreading-api
tail -100 /var/log/deepreading/api.log
tail -100 /var/log/deepreading/api-error.log
```

### 10.3 进程工作目录与监听端口

- [ ] `127.0.0.1:18000` 已监听
- [ ] 当前 uvicorn 进程工作目录正确
- [ ] 没有旧进程残留占端口

建议检查：

```bash
ss -tlnp | grep ':18000 '
ps -ef | grep '[u]vicorn'
```

---

## 11. HTTP 层验证

### 11.1 本机回环验证

- [ ] `http://127.0.0.1:18000/` 返回 `200`

### 11.2 Nginx 对外验证

- [ ] `http://127.0.0.1:18080/` 或公网入口返回 `200`
- [ ] `/api/deploy/runtime` 返回 `200`

建议命令：

```bash
curl -sS -o /tmp/site.out -w "%{http_code}\n" http://127.0.0.1:18080/
curl -sS -o /tmp/runtime.out -w "%{http_code}\n" http://127.0.0.1:18080/api/deploy/runtime
```

---

## 12. 数据库与业务层验证

这是上线验收中最容易被忽略、但最重要的一层。

仅仅满足：

- 服务 active
- 首页打开
- 健康检查 200

并不等于数据库 schema 和业务功能真的正常。

### 12.1 通用数据库验证

- [ ] 至少命中一个会真实读写数据库的新功能接口
- [ ] 至少验证一个本次改动影响的数据写入动作
- [ ] 至少验证一个本次改动影响的数据读取动作

### 12.2 如果本次涉及数据库改动

- [ ] 验证新增字段真实参与业务
- [ ] 验证新增枚举值 / CHECK 约束不会报错
- [ ] 验证旧数据读写不受影响

### 12.3 如果本次涉及 `.dra` 导入导出

- [ ] 验证导出接口可正常生成 `.dra`
- [ ] 验证导入接口可正常执行
- [ ] 验证 PostgreSQL 下不会再出现 FK 删除冲突
- [ ] 验证历史 SQLite 导出包仍能导入

### 12.4 如果本次涉及 prompt type / slot

- [ ] 验证 `/api/prompts/item`
- [ ] 验证 `/api/prompts/my`
- [ ] 验证新 slot 对应的真实业务入口

### 12.5 如果本次涉及前端页面

- [ ] 浏览器已强刷或清缓存
- [ ] 页面引用的是新 `index.html` 和新 assets
- [ ] 浏览器 Network 中无明显 `404/500`

---

## 13. 上线后最终勾选清单

把下面这段当成真正的最终勾选区。

### 13.1 本地侧

- [ ] 改动范围已确认
- [ ] 后端验证已完成
- [ ] 前端构建已完成
- [ ] migration 本地检查已完成

### 13.2 服务器侧

- [ ] 文件已上传并正确解包
- [ ] 关键代码已确认覆盖
- [ ] 前端 `dist` 已确认更新
- [ ] 如有 schema 变更，migration 已执行
- [ ] migration 目标库已确认是 PostgreSQL
- [ ] migration 后关键约束/字段已真实存在

### 13.3 服务侧

- [ ] `systemctl restart deepreading-api` 已执行
- [ ] 服务 active
- [ ] 端口监听正常
- [ ] 日志无启动期异常

### 13.4 访问与业务侧

- [ ] 首页返回 `200`
- [ ] `/api/deploy/runtime` 返回 `200`
- [ ] 本次改动的真实业务接口已验证
- [ ] 前端页面已确认是最新版本
- [ ] 没有“首页正常但业务接口 500”的假阳性

---

## 14. 常见红旗信号

如果看到下面任一情况，不要继续往下假设“应该已经上线成功”。

### 红旗 1：Alembic 成功，但业务接口仍报约束错误

含义：

- 大概率 migration 跑错库了
- 或生产 PostgreSQL 没真正升级

### 红旗 2：首页 200，但新功能接口 400/500

含义：

- 可能只是进程活着
- 后端注册文件、prompt 文件、schema 其中一环没同步

### 红旗 3：服务正常，但数据像“突然没了”

含义：

- 先怀疑回退到了 SQLite
- 先查 `DATABASE_URL` 和 systemd 环境，不要先怀疑数据被删

### 红旗 4：前端看起来没生效

含义：

- 先查线上 `frontend/dist/index.html`
- 再查 `assets/index-*.js/css`
- 最后再怀疑浏览器缓存或前端代码

---

## 15. 推荐执行顺序

如果你只想按最短路径执行，建议照下面顺序走：

1. 本地确认改动范围
2. 本地跑后端验证 / 前端构建 / migration 检查
3. 打包并上传最小文件集
4. 服务器解包
5. 服务器 compileall
6. 如有 schema 改动，先确认目标库是 PostgreSQL，再跑 migration
7. 核验关键 schema 真实生效
8. `systemctl restart deepreading-api`
9. 看日志、看端口、看 runtime
10. 打开首页
11. 命中新功能真实业务接口
12. 确认前端资源和业务链路都正确

---

## 16. 备注

如果本次上线包含：

- 数据库 schema 变更
- `.dra` 导入导出改造
- prompt type / prompt slot 增加
- Research Agent 新持久化表

建议不要只依赖本清单，必须同时回看：

- `docs/MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`
- `docs/NEW_SERVER_SQL_MAINTENANCE.md`
- `docs/JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md`

它们分别覆盖：

- 手动上传与重启 Runbook
- 新服务器 SQL / systemd / 路径约定
- Alembic 跑错 SQLite、前端静态资源未覆盖、后端注册文件未同步等真实踩坑

---

## 17. Research Agent 改动专项验证

如果本次上线涉及 Research Agent（AI 助手）相关改动，需额外验证以下项：

### 17.1 Runtime 与状态机

- [ ] 如改了 `research_agent_runtime.py`，已确认 `build_task_frame`、`resolve_context_refs`、`enforce_tool_policy`、`normalize_tool_args`、`update_state_after_tool` 均可正常 import
- [ ] 已跑 `python -m unittest backend.tests.test_research_agent_runtime` 通过
- [ ] 已确认状态迁移不会导致死循环（有 budget_guard 安全阀）

### 17.2 工具注册表

- [ ] 如改了 `agent_tool_registry.py`，已确认 `TOOL_SCHEMAS` 可正常生成
- [ ] 已跑 `python -m unittest backend.tests.test_agent_tool_registry` 通过
- [ ] 已确认新增工具的 handler 在 `execute_tool` 中有对应分发

### 17.3 分层检索

- [ ] 如改了 `research_retrieval.py`，已跑 `python -m unittest backend.tests.test_research_retrieval` 通过
- [ ] 已确认 P0 > P1 > P2 排序未被破坏

### 17.4 前端 AI 助手

- [ ] 如改了前端 AI 助手相关组件，已确认 SSE 事件流正常（session / tool_call / tool_result / proposal / answer / error / done）
- [ ] 已确认工作记忆面板正常展示 result_set / evidence_pack / tool_trace / budget_snapshot
- [ ] 已确认 proposal 确认/拒绝按钮正常工作

### 17.5 线上冒烟测试

上线后，在浏览器中执行以下 AI 助手冒烟测试：

- [ ] 发送"库里有多少论文" → 应调用 count_library 并返回数量
- [ ] 发送"帮我找关于 XX 的文献" → 应调用 search_library/research_search 并返回结果
- [ ] 发送"继续分析刚才这些" → 应复用上一轮结果集，不应重新搜全库
- [ ] 发送"去知网搜一下" → 应请求联网授权，不应直接执行
- [ ] proposal 确认 → 应正常执行并返回 job_id
- [ ] proposal 拒绝 → 应正常取消


# 部署架构说明

> 适用项目：`deep-reading-agent`  
> 最后更新：2026-05-03

## 1. 三者关系总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ① 本地目录 (开发环境)                                                     │
│   D:\code\deepagent\deep-reading-agent-online\deep-reading-agent           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ - 代码开发、测试                                                      │   │
│   │ - `git push origin online` 推送到 GitHub                            │   │
│   │ - 本地 db/app.sqlite (测试数据，不上传)                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                             │
│                              │ git push                                    │
│                              ▼                                             │
│   ② GitHub 远端                                                             │
│   https://github.com/lxjthu/deep-reading-agent.git                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ - 代码仓库 (online 分支)                                             │   │
│   │ - 触发 Webhook → 通知服务器 "有新代码了"                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                             │
│                              │ Webhook POST /deploy                        │
│                              ▼                                             │
│   ③ 服务器 (生产环境)                                                       │
│   /root/.openclaw/workspace/deep-reading-agent                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ - deploy.py 接收 Webhook，验证签名                                   │   │
│   │ - 执行 deploy.sh:                                                   │   │
│   │     1. git fetch origin online                                      │   │
│   │     2. git reset --hard origin/online (拉取最新代码)                 │   │
│   │     3. pip install requirements.txt                                 │   │
│   │     4. bash start.sh (重启服务)                                     │   │
│   │ - db/app.sqlite (线上真实数据，不覆盖)                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 各环节职责

| 环节 | 位置 | 主要职责 | 备注 |
|------|------|----------|------|
| **本地** | `D:\code\deepagent\...` | 代码开发、测试、提交 | 本机数据库仅用于测试 |
| **GitHub** | `origin/online` | 代码中转、触发 Webhook | 不存储数据库文件 |
| **服务器** | `/root/.openclaw/workspace/...` | 运行服务、承载真实数据 | 线上数据库独立管理 |

---

## 3. 自动部署触发链路

```
本地 git push origin online
        ↓
GitHub 收到 push 事件
        ↓
GitHub 发送 Webhook (POST /deploy)
        ↓
服务器 deploy.py 验证签名
        ↓
执行 deploy.sh (后台运行)
        ↓
服务器代码更新 + 服务重启
```

---

## 4. 关键文件说明

### 4.1 部署相关文件

| 文件 | 位置 | 作用 |
|------|------|------|
| `deploy.sh` | 项目根目录 | 服务器部署脚本，负责拉代码、装依赖、重启服务 |
| `deploy.py` | `backend/routers/` | Webhook 接收端，验证 GitHub 签名后触发部署 |

### 4.2 数据库相关文件

| 文件 | 位置 | 作用 |
|------|------|------|
| `models.py` | `backend/db/` | ORM 模型定义，告诉代码数据库结构 |
| `migrations/versions/*.py` | `backend/migrations/` | Alembic 迁移脚本，告诉数据库如何升级 |
| `db/app.sqlite` | 项目根目录下的 `db/` | SQLite 数据库文件（本地和服务器各自独立） |

---

## 5. 数据库处理原则

### 5.1 核心原则

- **代码部署是自动的**：push 到 GitHub 后，服务器自动拉取并重启
- **数据库迁移是手动的**：服务器需要手动执行 `alembic upgrade head`
- **数据库文件不互传**：本地和服务器的 `db/app.sqlite` 各自独立，不互相覆盖

### 5.2 数据库变更上线流程

```
本机开发
  ├─ 更新 docs/DATABASE_SCHEMA.md (设计文档)
  ├─ 更新 backend/db/models.py (ORM 模型)
  └─ 生成 backend/migrations/versions/*.py (迁移脚本)
        ↓
git push origin online
        ↓
服务器自动部署代码
        ↓
SSH 登录服务器
  ├─ cd /root/.openclaw/workspace/deep-reading-agent/backend
  ├─ source ../venv/bin/activate
  └─ python -m alembic upgrade head
        ↓
验证服务正常
```

---

## 6. 当前 Git 配置

- **远程仓库**: `origin` → `https://github.com/lxjthu/deep-reading-agent.git`
- **当前分支**: `online`
- **跟踪关系**: `online` → `origin/online`

---

## 7. 常见操作

### 7.1 推送代码到远程

```bash
git add .
git commit -m "feat: 描述"
git push origin online
```

### 7.2 拉取远程最新代码

```bash
git pull origin online
```

### 7.3 服务器手动迁移数据库

```bash
# SSH 登录服务器后执行
cd /root/.openclaw/workspace/deep-reading-agent/backend
source ../venv/bin/activate
python -m alembic upgrade head
```

---

## 8. 注意事项

1. **不要上传 `.venv/` 和 `db/app.sqlite`** - 这两个文件已在 `.gitignore` 中
2. **推送前确保本地测试通过** - 自动部署会直接上线代码
3. **数据库变更必须有迁移脚本** - 只改 `models.py` 不会自动更新服务器数据库
4. **不要用本机数据库覆盖服务器数据库** - 会导致线上数据丢失

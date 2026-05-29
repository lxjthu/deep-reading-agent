# 运维实践：服务器健康检查与自动恢复

> 日期：2026-05-06（2026-05-27 更新为当前架构）  
> 背景：文献库 502 故障后，建立自动监控与恢复机制  
> 相关故障记录：`INCIDENT_2026-05-06_LIBRARY_502.md`

---

## 1. 问题背景

2026-05-06 文献库故障排查发现，Nginx 已停止运行 6 天但无人察觉。服务器上没有自动检测和恢复机制，服务中断完全依赖人工发现。

当前已建立两层防护：
- **systemd**：管理后端服务，开机自启，崩溃自动重启
- **health_check.py + cron**：每 5 分钟自动检测，发现问题记录日志

---

## 2. 当前架构

```
用户浏览器
    │
    ▼
Nginx (端口 18080, 反代到 127.0.0.1:18000)
    ├── /api/  → FastAPI (18000)
    └── /      → 静态前端文件（npm run build 产物）
```

- **后端服务**：通过 `systemctl` 管理 `deepreading-api.service`
- **前端**：已 build 为静态文件，由 Nginx 直接服务，不再有 Vite dev server
- **数据库**：PostgreSQL（`deepreading` 库），通过 `.env.production` 配置

---

## 3. 健康检查脚本

### 3.1 health_check.py

位于 `/root/deep-reading-agent/health_check.py`，由 cron 每 5 分钟执行。

检测内容：
| 检查项 | 方式 | 失败动作 |
|--------|------|----------|
| 后端进程 | `systemctl is-active deepreading-api` | 记录日志 |
| API 可用性 | `curl http://127.0.0.1:18000/health` | 记录日志 |

日志写入 `/var/log/deepreading/`。

### 3.2 设置 cron

```bash
# 每 5 分钟执行健康检查
crontab -e
# 添加：
*/5 * * * * /root/deep-reading-agent/venv/bin/python /root/deep-reading-agent/health_check.py >> /var/log/deepreading/healthcheck.log 2>&1
```

---

## 4. 服务器部署步骤

### 4.1 日常部署（代码更新后）

推送代码后，服务器执行：

```bash
cd /root/deep-reading-agent
git fetch origin online && git reset --hard origin/online

# 前端构建（如有前端改动）
cd frontend && npm install && npm run build && cd ..

# 重启后端
systemctl restart deepreading-api
```

### 4.2 首次部署

```bash
cd /root/deep-reading-agent
git fetch origin online && git reset --hard origin/online

# 后端依赖
source venv/bin/activate
pip install -r requirements.txt

# 数据库迁移
cd backend && alembic upgrade head && cd ..

# 前端构建
cd frontend && npm install && npm run build && cd ..

# 启动服务
systemctl restart deepreading-api

# 设置健康检查 cron
crontab -e
# 添加：*/5 * * * * /root/deep-reading-agent/venv/bin/python /root/deep-reading-agent/health_check.py >> /var/log/deepreading/healthcheck.log 2>&1
```

---

## 5. 运维命令速查

### 查看服务状态

```bash
# 后端服务状态
systemctl status deepreading-api

# 检查端口监听
ss -tlnp | grep ':18000 '
ss -tlnp | grep ':18080 '
```

### 查看日志

| 日志 | 命令 |
|------|------|
| 后端日志 | `tail -100 /var/log/deepreading/api.log` |
| 后端错误日志 | `tail -100 /var/log/deepreading/api-error.log` |
| 健康检查日志 | `tail -100 /var/log/deepreading/healthcheck.log` |
| Nginx 错误日志 | `tail -30 /var/log/nginx/error.log` |

### 手动重启服务

```bash
# 重启后端
systemctl restart deepreading-api

# 重启 Nginx
systemctl restart nginx

# 查看后端日志（实时）
journalctl -u deepreading-api -f
```

### 移除健康检查 cron（如需停用）

```bash
crontab -e
# 删除 health_check.py 那一行
```

---

## 6. 注意事项

1. **健康检查日志需要定期清理**：日志只追加不轮转，建议每月手动清理或添加 logrotate
2. **必须使用 systemctl 管理后端**：不要手动 `nohup uvicorn`，否则会丢失 `.env.production` 中的 PostgreSQL 配置
3. **服务器重启后**：Nginx 和 deepreading-api 均已设为 `enabled`，会自动启动
4. **前端改动后需重新 build**：`cd frontend && npm run build`，静态文件由 Nginx 直接服务

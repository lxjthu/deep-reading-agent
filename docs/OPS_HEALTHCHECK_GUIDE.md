# 运维实践：服务器健康检查与自动恢复

> 日期：2026-05-06  
> 背景：文献库 502 故障后，建立自动监控与恢复机制  
> 相关故障记录：`INCIDENT_2026-05-06_LIBRARY_502.md`

---

## 1. 问题背景

2026-05-06 文献库故障排查发现，Nginx 已停止运行 6 天但无人察觉。服务器上没有自动检测和恢复机制，服务中断完全依赖人工发现。

本次建立了两层防护：
- **start.sh**：部署重启时自动启动所有服务（含 Nginx）
- **healthcheck.sh + cron**：每分钟自动检测，挂了自动拉起

---

## 2. 新增文件

### 2.1 scripts/healthcheck.sh

每分钟由 cron 调用，检测 4 个关键服务：

| 服务 | 检测方式 | 恢复动作 |
|------|----------|----------|
| Nginx | `systemctl is-active nginx` | `systemctl start nginx` |
| FastAPI | `ss -tlnp` 检查端口 8000 | 执行 `bash start.sh` |
| Cloudflare Tunnel | `pgrep -f "cloudflared tunnel"` | 重新启动 tunnel |
| Vite | `ss -tlnp` 检查端口 5173 | 重新启动 `npm run dev` |

恢复日志写入 `/tmp/healthcheck.log`。

### 2.2 start.sh 更新

在启动 FastAPI 之前增加 Nginx 启动：

```bash
echo "=== 启动 Nginx ==="
systemctl start nginx 2>/dev/null || true
```

确保每次部署重启时，Nginx 不会被遗漏。

---

## 3. 服务器部署步骤

### 3.1 首次部署健康检查

```bash
# 拉取代码
cd /root/.openclaw/workspace/deep-reading-agent
git fetch origin online && git reset --hard origin/online

# 添加执行权限
chmod +x scripts/healthcheck.sh

# 设置 cron（每分钟执行）
(crontab -l 2>/dev/null; echo "* * * * * /root/.openclaw/workspace/deep-reading-agent/scripts/healthcheck.sh") | crontab -

# 确认
crontab -l
```

### 3.2 日常部署（代码更新后）

推送代码后，服务器执行：

```bash
cd /root/.openclaw/workspace/deep-reading-agent
git fetch origin online && git reset --hard origin/online
bash start.sh
```

`start.sh` 会自动拉起 Nginx + FastAPI + Vite + Cloudflare Tunnel。

---

## 4. 运维命令速查

### 查看服务状态

```bash
# 一键检查所有服务
echo "Nginx: $(systemctl is-active nginx)" && \
echo "FastAPI: $(ss -tlnp | grep -c ':8000 ' | sed 's/1/running/;s/0/down/')" && \
echo "Vite: $(ss -tlnp | grep -c ':5173 ' | sed 's/1/running/;s/0/down/')" && \
echo "Tunnel: $(pgrep -f 'cloudflared tunnel' > /dev/null && echo running || echo down)"
```

### 查看日志

| 日志 | 命令 |
|------|------|
| 健康检查恢复日志 | `tail -20 /tmp/healthcheck.log` |
| 后端日志 | `tail -100 /tmp/fastapi.log` |
| 前端日志 | `tail -100 /tmp/vite.log` |
| Tunnel 日志 | `tail -100 /tmp/cloudflared.log` |
| Nginx 错误日志 | `tail -30 /var/log/nginx/error.log` |

### 手动重启单个服务

```bash
# Nginx
systemctl restart nginx

# FastAPI + Vite + Tunnel（全部重启）
cd /root/.openclaw/workspace/deep-reading-agent && bash start.sh

# 仅 Tunnel
pkill -f "cloudflared tunnel"
nohup cloudflared tunnel --config /root/.cloudflared/config.yml run > /tmp/cloudflared.log 2>&1 &
```

### 移除 cron（如需停用）

```bash
crontab -e
# 删除 healthcheck.sh 那一行
```

---

## 5. 请求链路与服务依赖

```
用户浏览器
    │
    ▼
Cloudflare Tunnel (HTTPS → HTTP)    ← healthcheck 检测进程
    │
    ▼
Nginx (端口 80)                      ← healthcheck 检测 systemctl
    ├── /api/  → FastAPI (8000)      ← healthcheck 检测端口
    ├── /ws/   → FastAPI (8000)
    └── /      → Vite (5173)         ← healthcheck 检测端口
```

任何一层断裂，healthcheck 会在 1 分钟内自动恢复并记录日志。

---

## 6. 注意事项

1. **healthcheck.log 需要定期清理**：脚本只追加不轮转，建议每月手动清理或添加 logrotate
2. **start.sh 重启 FastAPI 会连带重启所有服务**（先 kill 再启动），如果只想重启单个服务，用手动命令
3. **cron 环境变量有限**：healthcheck.sh 中路径全部使用绝对路径，避免环境变量缺失
4. **服务器重启后**：Nginx 已设为 `enabled`，会自启；但 FastAPI、Vite、Cloudflare 需要 start.sh 或 healthcheck 拉起

# 故障记录：文献库 502 错误（2026-05-06）

> 日期：2026-05-06  
> 影响：所有用户访问"我的文献库"页面时显示请求失败  
> 根因：两个独立问题叠加  
> 恢复时间：约 20 分钟  

---

## 1. 故障现象

用户打开"我的文献库"标签页，前端报错，页面无数据。浏览器开发者工具显示 `GET /api/library/entries` 返回 **502 Bad Gateway**。

---

## 2. 排查过程

### 2.1 第一步：查看后端日志

```bash
tail -100 /var/log/deepreading/api.log
```

发现关键错误：

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) near "DESC": syntax error
[SQL: ... ORDER BY bib_entries.is_pinned DESC DESC, bib_entries.updated_at DESC, ...]
```

**结论**：后端存在 `DESC DESC` 双重降序 SQL 语法错误。

### 2.2 第二步：确认本地代码状态

```bash
git log --oneline -5
```

本地已有修复提交 `4f85c91 fix: library entries 500 error caused by double DESC in ORDER BY clause`，但未推送到远端。

### 2.3 第三步：推送修复并手动更新服务器

```bash
git push origin online
```

服务器手动拉取：

```bash
cd /root/deep-reading-agent
git fetch origin online && git reset --hard origin/online && systemctl restart deepreading-api
```

### 2.4 第四步：推送后仍报 502

FastAPI 重启后，浏览器仍然 502。开始排查请求链路。

### 2.5 第五步：检查各层服务状态

| 检查项 | 命令 | 结果 |
|--------|------|------|
| FastAPI 进程 | `ps aux \| grep uvicorn` | ✅ 运行中 |
| FastAPI 端口 | `ss -tlnp \| grep 8000` | ✅ 监听 8000 |
| 直接测试 API | `curl http://127.0.0.1:8000/api/library/entries` | ✅ 返回 401（token 无效，说明 API 通） |
| Vite 进程 | `ss -tlnp \| grep 5173` | ✅ 监听 5173 |
| Cloudflare Tunnel | `ps aux \| grep cloudflared` | ✅ 运行中 |
| **Nginx** | `systemctl status nginx` | ❌ **inactive (dead)，已于 4月30日停止** |

### 2.6 第六步：定位根因

```bash
systemctl status nginx
```

输出：

```
Active: inactive (dead) since Thu 2026-04-30 11:38:33 CST; 5 days ago
```

**Nginx 已停止 6 天**，而 Cloudflare Tunnel 配置指向 `http://127.0.0.1:80`（Nginx），导致整个链路断裂：

```
Cloudflare Tunnel → 127.0.0.1:80 (Nginx 已停) → ❌ 连接拒绝 → 502
```

### 2.7 第七步：恢复 Nginx

```bash
systemctl start nginx
```

Nginx 启动后，验证链路：

```bash
curl -s -w "\nHTTP_CODE: %{http_code}\n" http://127.0.0.1:80/api/library/entries -H "Authorization: Bearer test"
# 返回 401，链路全通
```

---

## 3. 根因分析

本次故障由**两个独立问题叠加**导致：

### 问题 A：SQL 排序 bug（`DESC DESC`）

- **位置**：`backend/routers/library.py` 的 `list_entries` 函数
- **原因**：`order_cols` 列表中先对 `BibEntry.is_pinned` 调用了 `.desc()`，然后又用 `desc()` 二次包装，产生 `DESC DESC`
- **影响**：文献库默认排序必然触发，每次打开都 500
- **修复**：改为显式 if/else 分支处理每种 `sort_by`

### 问题 B：Nginx 意外停止

- **现象**：Nginx 于 4月30日停止，此后所有外部请求都无法到达后端
- **原因**：未知（可能是系统资源不足、手动停止、或 OOM killer）
- **影响**：Cloudflare Tunnel → Nginx 这一层断裂，所有页面都返回 502

### 叠加效果

| 时间段 | 问题 A | 问题 B | 用户体验 |
|--------|--------|--------|----------|
| 4/30 之前 | 可能存在 | 未发生 | 正常 |
| 4/30 ~ 5/6 | 存在 | Nginx 停止 | 502（Nginx 不通） |
| 5/6 推送修复后 | 已修复 | Nginx 停止 | 仍然 502 |
| 5/6 启动 Nginx 后 | 已修复 | 已恢复 | ✅ 正常 |

---

## 4. 预防措施

### 4.1 防止 Nginx 意外停止

**方案 A：systemd 自动恢复 + 健康检查脚本**

当前架构下，后端通过 `systemctl` 管理（`deepreading-api.service`），已配置 `Restart=on-failure`，进程崩溃会自动重启。

健康检查脚本 `/root/deep-reading-agent/health_check.py` 由 cron 每 5 分钟执行，检测服务状态和 API 可用性：

```bash
# 设置 cron
crontab -e
# 添加：
*/5 * * * * /root/deep-reading-agent/venv/bin/python /root/deep-reading-agent/health_check.py >> /var/log/deepreading/healthcheck.log 2>&1
```

**方案 B：确保 Nginx 开机自启**

```bash
systemctl enable nginx
```

### 4.2 防止 SQL 排序 bug

- SQLAlchemy 排序逻辑应显式处理每种 `sort_by` 分支，不要混用原始列和 `.desc()` 列对象后统一包装
- 新增排序维度时，必须用真实数据库测试，而非只看 ORM 输出

### 4.3 防止修复未推送

- 本地修复后应立即推送并确认自动部署成功
- 可在 CI 或 `deploy.sh` 中添加冒烟测试，自动验证关键接口是否返回非 500

### 4.4 监控建议

| 监控项 | 方式 | 告警条件 |
|--------|------|----------|
| 外部可访问性 | 外部定时 curl 域名 | 非 200 超过 2 分钟 |
| Nginx 状态 | systemctl is-active | inactive |
| FastAPI 端口 | ss -tlnp | 端口不监听 |
| 后端日志错误 | grep error /var/log/deepreading/api.log | 出现 OperationalError |

---

## 5. 服务器请求链路（更新）

```
用户浏览器
    │
    ▼
Cloudflare Tunnel (HTTPS → HTTP)
    │
    ▼
Nginx (端口 80)              ← 本次故障点
    ├── /api/  → FastAPI (8000)  ← DESC DESC bug 点
    ├── /ws/   → FastAPI (8000)
    └── /      → Vite (5173)
```

任何一层断裂都会导致用户无法访问，需要有健康检查和自动恢复机制。

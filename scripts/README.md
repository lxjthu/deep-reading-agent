# Deep Reading Agent - SRE 运维体系

## 📁 脚本文件

| 脚本 | 功能 | 执行频率 |
|------|------|----------|
| `daily_health_check.sh` | 生成结构化JSON检查报告 | 每日 |
| `generate_report.py` | 读取JSON报告，生成Markdown运维报告 | 每日（后于health_check） |
| `auto_fix.sh` | 根据报告自动执行修复（重启服务、清理磁盘等） | 按需/自动 |
| `health_check.sh` | 快速检查并重启异常服务 | 实时监控 |

## 📊 报告文件

- `reports/daily_YYYYMMDD.json` - 结构化数据报告
- `reports/report_YYYYMMDD.md` - 人类可读运维报告

## 🔄 执行流程

```
daily_health_check.sh → [生成 daily_YYYYMMDD.json]
         ↓
generate_report.py → [生成 report_YYYYMMDD.md]
         ↓
auto_fix.sh → [根据问题自动修复]
```

## ⚡ 自动修复能力

| 问题 | 自动修复动作 |
|------|-------------|
| 后端服务异常 (P0) | 自动重启 uvicorn |
| 公网隧道异常 (P0) | 自动重启 cloudflared |
| 磁盘空间不足 (P1) | 清理/tmp、旧结果文件、旧日志 |
| 后端错误日志 (P2) | 记录并通知，建议人工检查 |

## 🔧 手动执行

```bash
# 生成当日报告
bash scripts/daily_health_check.sh

# 生成可读报告
python3 scripts/generate_report.py

# 执行自动修复
bash scripts/auto_fix.sh

# 查看历史报告
ls -la reports/
```

## ⏰ 定时任务

建议添加到 crontab（需要用户手动配置）：

```bash
# 每天上午9点执行健康检查并生成报告
0 9 * * * bash /root/.openclaw/workspace/deep-reading-agent/scripts/daily_health_check.sh > /tmp/deepread_cron.log 2>&1 && python3 /root/.openclaw/workspace/deep-reading-agent/scripts/generate_report.py >> /tmp/deepread_cron.log 2>&1
```

## 📈 报告内容

生成的报告包含：
- 系统状态摘要（后端/前端/隧道）
- 资源使用（磁盘/内存/数据库）
- 用户与任务统计
- 异常与报错分析
- 待修复问题（按P0-P3分级）
- 修复方案（含步骤、时间、风险、回滚）
- 今日建议操作清单

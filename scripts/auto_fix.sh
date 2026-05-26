#!/bin/bash
# Deep Reading Agent - 自动修复脚本
# 根据报告中的问题自动执行修复

PROJECT_DIR="/root/.openclaw/workspace/deep-reading-agent"
REPORT_DIR="$PROJECT_DIR/reports"
LOG_FILE="/tmp/auto_fix.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 检查是否有报告文件
LATEST_REPORT=$(ls -t "$REPORT_DIR"/daily_*.json 2>/dev/null | head -1)
if [ -z "$LATEST_REPORT" ]; then
    log "错误: 未找到报告文件"
    exit 1
fi

# 锁文件防止并发执行
LOCK_FILE="/tmp/auto_fix.lock"
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if ps -p "$PID" > /dev/null 2>&1; then
        log "另一个 auto_fix 实例正在运行 (PID: $PID)，退出"
        exit 0
    else
        rm -f "$LOCK_FILE"
    fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

log "读取报告: $LATEST_REPORT"

# 解析JSON获取问题
# 使用Python解析JSON，因为bash处理JSON很困难
python3 << PYTHON
import json
import sys
import subprocess

report_file = "$LATEST_REPORT"
with open(report_file, 'r') as f:
    data = json.load(f)

checks = data.get('checks', {})
errors = data.get('errors', {})
resources = data.get('resources', {})

issues = []

# 检查服务状态
if checks.get('backend', {}).get('status_code') != 200:
    issues.append(('P0', 'backend_down', '后端服务返回非200'))
if checks.get('tunnel', {}).get('status_code') != 200:
    issues.append(('P0', 'tunnel_down', '公网隧道返回非200'))

# 检查资源
disk_pct = resources.get('disk_usage_percent', 0)
if isinstance(disk_pct, str):
    disk_pct = int(disk_pct) if disk_pct.isdigit() else 0
if disk_pct > 80:
    issues.append(('P1', 'disk_full', f'磁盘使用率{disk_pct}%'))

# 检查错误日志
backend_err = errors.get('backend_error_count_200lines', 0)
if isinstance(backend_err, str):
    backend_err = int(backend_err) if backend_err.isdigit() else 0
if backend_err > 0:
    issues.append(('P2', 'backend_errors', f'后端{backend_err}条错误'))

# 输出问题列表
for severity, issue_type, desc in issues:
    print(f"{severity}|{issue_type}|{desc}")
PYTHON

# 读取Python输出并执行修复
while IFS='|' read -r SEVERITY ISSUE_TYPE DESC; do
    log "发现 [$SEVERITY] 问题: $ISSUE_TYPE - $DESC"
    
    case "$ISSUE_TYPE" in
        "backend_down")
            log "执行: 重启后端服务..."
            pkill -f "uvicorn main:app" 2>/dev/null
            sleep 2
            cd "$PROJECT_DIR" && nohup uvicorn main:app --host 0.0.0.0 --port 8000 --reload > /tmp/fastapi.log 2>&1 &
            sleep 3
            # 验证
            if curl -s http://localhost:8000/api/health > /dev/null; then
                log "✅ 后端服务已恢复"
            else
                log "❌ 后端服务重启失败"
            fi
            ;;
            
        "tunnel_down")
            log "执行: 重启 Cloudflare Tunnel..."
            # 先检查是否已有 tunnel 在运行（healthcheck.sh 可能已经重启了）
            if pgrep -f "cloudflared tunnel" > /dev/null; then
                log "Tunnel 已在运行，跳过重启"
            else
                pkill -f "cloudflared tunnel" 2>/dev/null
                sleep 2
                # 从 start.sh 获取 tunnel 启动命令
                TUNNEL_CMD=$(grep -A2 "cloudflared tunnel" "$PROJECT_DIR/start.sh" | grep -v "^#" | head -1)
                if [ -n "$TUNNEL_CMD" ]; then
                    eval "$TUNNEL_CMD" > /tmp/cloudflared.log 2>&1 &
                    log "✅ Tunnel 已重启"
                else
                    log "❌ 无法找到 tunnel 启动命令"
                fi
            fi
            ;;
            
        "disk_full")
            log "执行: 清理磁盘空间..."
            # 清理临时文件
            find /tmp -type f -atime +7 -delete 2>/dev/null
            # 清理旧的结果文件（保留30天）
            find "$PROJECT_DIR/deep_reading_results" -type f -mtime +30 -delete 2>/dev/null
            # 清理旧的日志
            find "$PROJECT_DIR/db" -name "*.log" -mtime +7 -delete 2>/dev/null
            log "✅ 磁盘清理完成"
            ;;
            
        "backend_errors")
            log "发现后端错误，建议人工检查: tail -f /tmp/fastapi.log"
            # 发送通知（如果有配置）
            ;;
            
        *)
            log "未知问题类型: $ISSUE_TYPE"
            ;;
    esac
done < <(python3 << PYTHON
import json

with open("$LATEST_REPORT", 'r') as f:
    data = json.load(f)

checks = data.get('checks', {})
errors = data.get('errors', {})
resources = data.get('resources', {})

issues = []

if checks.get('backend', {}).get('status_code') != 200:
    issues.append(('P0', 'backend_down', '后端服务返回非200'))
if checks.get('tunnel', {}).get('status_code') != 200:
    issues.append(('P0', 'tunnel_down', '公网隧道返回非200'))

disk_pct = resources.get('disk_usage_percent', 0)
if isinstance(disk_pct, str):
    disk_pct = int(disk_pct) if disk_pct.isdigit() else 0
if disk_pct > 80:
    issues.append(('P1', 'disk_full', f'磁盘使用率{disk_pct}%'))

backend_err = errors.get('backend_error_count_200lines', 0)
if isinstance(backend_err, str):
    backend_err = int(backend_err) if backend_err.isdigit() else 0
if backend_err > 0:
    issues.append(('P2', 'backend_errors', f'后端{backend_err}条错误'))

for severity, issue_type, desc in issues:
    print(f"{severity}|{issue_type}|{desc}")
PYTHON
)

log "自动修复完成"

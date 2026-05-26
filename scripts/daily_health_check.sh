#!/bin/bash
# Deep Reading Agent - 每日运维检查脚本
# 生成结构化报告供AI分析

PROJECT_DIR="/root/.openclaw/workspace/deep-reading-agent"
DB="$PROJECT_DIR/db/app.sqlite"
REPORT_DIR="$PROJECT_DIR/reports"
REPORT_FILE="$REPORT_DIR/daily_$(date +%Y%m%d).json"

echo "=== Deep Reading Agent 每日运维检查 ==="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"

# 1. 服务健康检查
echo "[1/6] 检查服务状态..."
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null)
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ 2>/dev/null)
TUNNEL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://deepreading.qzz.io/health 2>/dev/null)

BACKEND_HEALTH=""
if [ "$BACKEND_STATUS" = "200" ]; then
    BACKEND_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null)
fi

# 2. 进程检查
echo "[2/6] 检查进程..."
UVICORN_PID=$(pgrep -f "uvicorn main:app" | head -1)
VITE_PID=$(pgrep -f "vite" | head -1)
TUNNEL_PID=$(pgrep -f "cloudflared tunnel" | head -1)

UVICORN_UPTIME=""
if [ -n "$UVICORN_PID" ]; then
    UVICORN_UPTIME=$(ps -o etime= -p "$UVICORN_PID" 2>/dev/null | tr -d ' ')
fi

# 3. 资源使用
echo "[3/6] 检查资源..."
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}')
MEM_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
DB_SIZE=$(du -sh "$DB" 2>/dev/null | cut -f1)
UPLOAD_SIZE=$(du -sh "$PROJECT_DIR/_uploads" 2>/dev/null | cut -f1)
RESULTS_SIZE=$(du -sh "$PROJECT_DIR/deep_reading_results" 2>/dev/null | cut -f1)

# 4. 数据库统计
echo "[4/6] 查询数据库..."
USER_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM users;" 2>/dev/null)
JOB_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM jobs;" 2>/dev/null)
JOB_STATUS=$(sqlite3 "$DB" "SELECT status, COUNT(*) FROM jobs GROUP BY status;" 2>/dev/null)
FEEDBACK_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM user_feedback;" 2>/dev/null)
FEEDBACK_OPEN=$(sqlite3 "$DB" "SELECT COUNT(*) FROM user_feedback WHERE status IN ('open','triaged','in_progress','reopened');" 2>/dev/null)
RECENT_JOBS=$(sqlite3 "$DB" "SELECT id, job_type, status, created_at FROM jobs ORDER BY created_at DESC LIMIT 5;" 2>/dev/null)
AGENT_SESSIONS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM agent_sessions;" 2>/dev/null)
AGENT_MESSAGES=$(sqlite3 "$DB" "SELECT COUNT(*) FROM agent_messages;" 2>/dev/null)

# 5. 日志检查
echo "[5/6] 检查日志..."
BACKEND_ERRORS=$(tail -200 /tmp/fastapi.log 2>/dev/null | grep -c "ERROR\|Exception\|Traceback" 2>/dev/null || echo "0")
TUNNEL_ERRORS=$(tail -50 /tmp/cloudflared.log 2>/dev/null | grep -c "ERR\|error" 2>/dev/null || echo "0")
CLEANUP_LOG=$(tail -5 "$PROJECT_DIR/db/cleanup.log" 2>/dev/null)

# 6. 生成JSON报告
echo "[6/6] 生成报告..."
mkdir -p "$REPORT_DIR"

cat > "$REPORT_FILE" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "checks": {
    "backend": {
      "status_code": $BACKEND_STATUS,
      "health_response": $(echo "$BACKEND_HEALTH" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))' 2>/dev/null || echo '"unknown"'),
      "pid": $(echo "$UVICORN_PID" | sed 's/^$/null/'),
      "uptime": $(echo "$UVICORN_UPTIME" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))' 2>/dev/null || echo '"unknown"')
    },
    "frontend": {
      "status_code": $FRONTEND_STATUS,
      "pid": $(echo "$VITE_PID" | sed 's/^$/null/')
    },
    "tunnel": {
      "status_code": $TUNNEL_STATUS,
      "pid": $(echo "$TUNNEL_PID" | sed 's/^$/null/')
    }
  },
  "resources": {
    "disk_usage_percent": $(echo "$DISK_USAGE" | sed 's/%//'),
    "memory_usage_percent": $MEM_USAGE,
    "db_size": $(echo "$DB_SIZE" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))' 2>/dev/null || echo '"unknown"'),
    "uploads_size": $(echo "$UPLOAD_SIZE" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))' 2>/dev/null || echo '"unknown"'),
    "results_size": $(echo "$RESULTS_SIZE" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))' 2>/dev/null || echo '"unknown"')
  },
  "database": {
    "users": $USER_COUNT,
    "jobs": $JOB_COUNT,
    "job_statuses": $(echo "$JOB_STATUS" | python3 -c 'import sys,json; lines=[l.strip().split("|") for l in sys.stdin if "|" in l]; print(json.dumps({l[0]: int(l[1]) for l in lines}))' 2>/dev/null || echo '{}'),
    "feedback_total": $FEEDBACK_COUNT,
    "feedback_open": $FEEDBACK_OPEN,
    "agent_sessions": $AGENT_SESSIONS,
    "agent_messages": $AGENT_MESSAGES,
    "recent_jobs": $(echo "$RECENT_JOBS" | python3 -c '
import sys,json
jobs=[]
for line in sys.stdin:
    parts=line.strip().split("|")
    if len(parts)>=4:
        jobs.append({"id": parts[0], "type": parts[1], "status": parts[2], "created_at": parts[3]})
print(json.dumps(jobs))
' 2>/dev/null || echo '[]')
  },
  "errors": {
    "backend_error_count_200lines": $(echo "$BACKEND_ERRORS" | head -1),
    "tunnel_error_count_50lines": $(echo "$TUNNEL_ERRORS" | head -1)
  },
  "cleanup_log": $(echo "$CLEANUP_LOG" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))' 2>/dev/null || echo '""')
}
EOF

echo ""
echo "=== 报告已生成: $REPORT_FILE ==="
echo ""
cat "$REPORT_FILE" | python3 -m json.tool 2>/dev/null || cat "$REPORT_FILE"

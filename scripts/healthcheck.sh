#!/bin/bash
# 服务器健康检查脚本 - 由 cron 每分钟执行
# 用法: * * * * * /root/.openclaw/workspace/deep-reading-agent/scripts/healthcheck.sh

LOG=/tmp/healthcheck.log
PROJECT=/root/.openclaw/workspace/deep-reading-agent

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

if ! systemctl is-active --quiet nginx; then
    log "Nginx down, restarting..."
    systemctl start nginx >> "$LOG" 2>&1
fi

if ! ss -tlnp | grep -q ':8000 '; then
    log "FastAPI down, restarting..."
    cd "$PROJECT" && bash start.sh >> "$LOG" 2>&1
fi

if ! pgrep -f "cloudflared tunnel" > /dev/null; then
    log "Cloudflared down, restarting..."
    nohup cloudflared tunnel --config /root/.cloudflared/config.yml run >> /tmp/cloudflared.log 2>&1 &
fi

if ! ss -tlnp | grep -q ':5173 '; then
    log "Vite down, restarting..."
    cd "$PROJECT/frontend" && nohup npm run dev >> /tmp/vite.log 2>&1 &
fi

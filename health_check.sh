#!/bin/bash
# Deep Reading Agent 健康监控脚本

LOG="/tmp/deepread_health.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"
}

check_and_restart() {
    # Check backend
    if ! curl -s http://localhost:8000/health >/dev/null 2>&1; then
        log "❌ Backend down, restarting..."
        pkill -f "uvicorn main:app" 2>/dev/null || true
        cd /root/.openclaw/workspace/deep-reading-agent/backend
        source ../venv/bin/activate
        nohup uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 > /tmp/fastapi.log 2>&1 &
        sleep 2
        if curl -s http://localhost:8000/health >/dev/null 2>&1; then
            log "✅ Backend restarted"
        else
            log "❌ Backend restart failed"
        fi
    fi

    # Check frontend
    if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ | grep -q "200"; then
        log "❌ Frontend down, restarting..."
        pkill -f "vite" 2>/dev/null || true
        cd /root/.openclaw/workspace/deep-reading-agent/frontend
        nohup npm run dev > /tmp/vite.log 2>&1 &
        sleep 2
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ | grep -q "200"; then
            log "✅ Frontend restarted"
        else
            log "❌ Frontend restart failed"
        fi
    fi

    # Check tunnel
    if ! pgrep -f "cloudflared tunnel" >/dev/null 2>&1; then
        log "❌ Tunnel down, restarting..."
        nohup cloudflared tunnel --config /root/.cloudflared/config.yml run > /tmp/cloudflared.log 2>&1 &
        sleep 5
        if pgrep -f "cloudflared tunnel" >/dev/null 2>&1; then
            log "✅ Tunnel restarted"
        else
            log "❌ Tunnel restart failed"
        fi
    fi
}

# Run check
check_and_restart
log "Health check completed"

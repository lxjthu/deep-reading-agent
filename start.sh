#!/bin/bash
# Deep Reading Agent 启动脚本
set -e

echo "=== 停止旧进程 ==="
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 2

echo "=== 启动后端 (FastAPI) ==="
cd /root/.openclaw/workspace/deep-reading-agent/backend
source ../venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 > /tmp/fastapi.log 2>&1 &
echo "Backend PID: $!"

echo "=== 启动前端 (Vite) ==="
cd /root/.openclaw/workspace/deep-reading-agent/frontend
nohup npm run dev > /tmp/vite.log 2>&1 &
echo "Frontend PID: $!"

echo "=== 启动 Tunnel ==="
nohup cloudflared tunnel --config /root/.cloudflared/config.yml run > /tmp/cloudflared.log 2>&1 &
echo "Tunnel PID: $!"

sleep 3
echo ""
echo "=== 健康检查 ==="
curl -s http://localhost:8000/health && echo " ✅ Backend"
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ && echo " ✅ Frontend"
curl -s -o /dev/null -w "%{http_code}" https://deepreading.qzz.io/ && echo " ✅ Tunnel"
echo ""
echo "全部启动完成。日志: /tmp/fastapi.log /tmp/vite.log /tmp/cloudflared.log"

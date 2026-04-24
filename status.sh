#!/bin/bash
# Deep Reading Agent 状态查看脚本

echo "=== 进程状态 ==="
echo "Backend:"
pgrep -f "uvicorn main:app" 2>/dev/null && echo "  ✅ Running" || echo "  ❌ Down"

echo "Frontend:"
pgrep -f "vite" 2>/dev/null && echo "  ✅ Running" || echo "  ❌ Down"

echo "Tunnel:"
pgrep -f "cloudflared tunnel" 2>/dev/null && echo "  ✅ Running" || echo "  ❌ Down"

echo ""
echo "=== 端口检查 ==="
curl -s http://localhost:8000/health 2>/dev/null && echo "  Backend: ✅" || echo "  Backend: ❌"
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ 2>/dev/null | grep -q "200" && echo "  Frontend: ✅" || echo "  Frontend: ❌"
curl -s -o /dev/null -w "%{http_code}" https://deepreading.qzz.io/ 2>/dev/null | grep -q "200" && echo "  Website: ✅" || echo "  Website: ❌"

echo ""
echo "=== 日志状态 ==="
ls -lh /tmp/fastapi.log /tmp/vite.log /tmp/cloudflared.log /tmp/deepread_health.log 2>/dev/null | awk '{print "  " $9 " " $5}'

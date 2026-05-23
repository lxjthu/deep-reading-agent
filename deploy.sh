#!/bin/bash
# Auto deploy script for deep-reading-agent
# Pulls online branch and restarts services

set -e

echo "=== $(date) 开始部署 ==="

cd /root/.openclaw/workspace/deep-reading-agent

# Configure git to use deploy key
export GIT_SSH_COMMAND="ssh -i /root/.ssh/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"

# Fetch latest online branch
echo "[1/4] 拉取 online 分支..."
git fetch origin online
git checkout online
git reset --hard origin/online

echo "[2/4] 安装依赖..."
source venv/bin/activate
pip install -q -r requirements.txt 2>/dev/null || true
cd frontend
npm install
npm run build
cd ..

echo "[3/4] 更新数据库结构..."
cd backend
alembic upgrade head || echo "警告：数据库迁移失败，请手动检查"
cd ..

echo "[4/4] 重启服务..."
bash start.sh

echo "=== 部署完成 ==="

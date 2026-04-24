#!/bin/bash
# Auto deploy script for deep-reading-agent
# Pulls online branch and restarts services

set -e

echo "=== $(date) 开始部署 ==="

cd /root/.openclaw/workspace/deep-reading-agent

# Configure git to use deploy key
export GIT_SSH_COMMAND="ssh -i /root/.ssh/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"

# Fetch latest online branch
echo "[1/3] 拉取 online 分支..."
git fetch origin online
git checkout online
git reset --hard origin/online

echo "[2/3] 安装依赖..."
source venv/bin/activate
pip install -q -r requirements.txt 2>/dev/null || true

echo "[3/3] 重启服务..."
bash start.sh

echo "=== 部署完成 ==="

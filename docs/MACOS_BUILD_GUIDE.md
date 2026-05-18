# macOS 打包指南

> 适用项目：`deep-reading-agent`
> 最后更新：2026-05-18

## 前提条件

- PyInstaller **不支持交叉编译**，必须在 macOS 上执行打包
- 产物仅限 macOS 运行，Windows 版需在 Windows 上另行打包

## 1. 准备 macOS 环境

```bash
# 安装 Python 3.12 + Node.js
brew install python@3.12 node

# 克隆代码
git clone https://github.com/lxjthu/deep-reading-agent.git
cd deep-reading-agent
git checkout packaging  # 或 online

# 创建虚拟环境并安装依赖
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller
```

## 2. 构建前端

```bash
cd frontend && npm install && npm run build && cd ..
```

## 3. 执行 PyInstaller 打包

macOS 的 `--add-data` 分隔符是 **`:`**（Windows 是 `;`）。

```bash
python -m PyInstaller --onedir \
  --name=DeepReadingAgent \
  --noconsole \
  --paths=backend \
  --add-data="frontend/dist:frontend/dist" \
  --add-data="prompts:prompts" \
  --add-data="new_architecture:new_architecture" \
  --add-data="backend:backend" \
  --add-data=".env.example:." \
  --hidden-import=uvicorn \
  --hidden-import=uvicorn.logging \
  --hidden-import=uvicorn.loops.auto \
  --hidden-import=uvicorn.protocols.http.auto \
  --hidden-import=uvicorn.protocols.websockets.auto \
  --hidden-import=uvicorn.lifespan.on \
  --hidden-import=sqlalchemy.dialects.sqlite \
  --hidden-import=aiosqlite \
  --hidden-import=passlib.handlers.bcrypt \
  --hidden-import=apscheduler.schedulers.asyncio \
  --hidden-import=apscheduler.triggers.interval \
  --hidden-import=pdfminer.high_level \
  --hidden-import=openpyxl \
  --collect-submodules=pdfminer \
  --collect-submodules=pdfplumber \
  --collect-submodules=openpyxl \
  run_web.py
```

## 4. 制作 macOS 启动器

```bash
cat > dist/启动DeepReadingAgent.command << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
echo "正在启动 Deep Reading Agent..."
./DeepReadingAgent/DeepReadingAgent
EOF
chmod +x dist/启动DeepReadingAgent.command
```

## 5. 打包为 ZIP

```bash
cd dist
zip -r DeepReadingAgent-macOS.zip DeepReadingAgent 启动DeepReadingAgent.command
```

## 注意事项

- **macOS 安全限制**：首次双击 `.command` 或 exe 会触发 Gatekeeper 拦截，用户需在「系统设置 → 隐私与安全性」中手动允许
- **Apple Silicon (M1/M4)**：当前依赖是 x86 架构，M 芯片 Mac 可通过 Rosetta 2 运行；如需原生 ARM 需在 M 芯片 Mac 上打包
- **`--noconsole`**：macOS 上终端窗口不像 Windows 那样突兀，如想让用户看到日志输出可去掉此参数
- **日志位置**：`data/logs/startup.log`（`run_web.py` 在 frozen 模式下自动重定向 stdout/stderr）

## Windows 与 macOS 打包差异速查

| 项目 | Windows | macOS |
|------|---------|-------|
| `--add-data` 分隔符 | `;` | `:` |
| 启动器格式 | `.bat` | `.command` |
| PyInstaller bootloader | `runw.exe` / `run.exe` | `runw` / `run` |
| 控制台隐藏 | `--noconsole` 必需 | 可选 |
| 安全限制 | 无 | Gatekeeper 需手动允许 |
| 架构 | x64 | x64 或 ARM（取决于打包机） |

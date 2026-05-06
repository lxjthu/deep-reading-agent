# Windows 可执行文件打包实施规划

> **For agentic workers:** 使用 superpowers:executing-plans 执行此规划。

**Goal:** 将 Deep Reading Agent 项目打包成 Windows 可执行文件，用户解压后即可运行，无需安装 Python 环境。

**Architecture:** 使用 PyInstaller 将 Python 后端打包成独立可执行文件，前端已构建（dist目录）直接包含，创建一键启动脚本。

**Tech Stack:** PyInstaller, Python 3.10+, FastAPI, React (已构建), SQLite

---

## 项目分析

### 当前结构
```
deep-reading-agent/
├── app.py                    # Gradio GUI 主入口
├── main.py                   # 命令行工具入口
├── backend/                  # FastAPI 后端
│   ├── main.py              # FastAPI 入口
│   ├── db/                  # SQLite 数据库
│   ├── routers/             # API 路由
│   └── services/            # 业务逻辑
├── frontend/dist/            # React 前端（已构建）
├── deep_reading_steps/       # 深度阅读步骤
├── requirements.txt          # Python 依赖
└── .env.example             # 配置模板
```

### 打包目标
1. **单文件可执行**：包含 Python 解释器和所有依赖
2. **解压即用**：用户无需安装 Python 或依赖
3. **配置简单**：提供 .env 配置向导
4. **启动方便**：双击即可运行

---

## 打包方案选择

### 方案 A：PyInstaller 单文件打包（推荐）
- **优点**：单个 .exe 文件，分发简单
- **缺点**：文件较大（约 200-300MB），启动稍慢
- **适用**：需要最简分发的场景

### 方案 B：PyInstaller 目录打包
- **优点**：启动快，可更新部分文件
- **缺点**：需要整个目录分发
- **适用**：需要快速启动的场景

### 方案 C：嵌入式 Python + 批处理
- **优点**：完全透明，可自定义
- **缺点**：文件较多，配置复杂
- **适用**：需要完全控制的场景

**推荐方案 A**：PyInstaller 单文件打包，配合启动脚本。

---

## 实施任务

### Task 1: 创建 PyInstaller 配置文件

**Files:**
- Create: `deep-reading-agent.spec`

```python
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

# 项目根目录
root_dir = Path(SPECPATH)

# 收集所有 Python 模块
a = Analysis(
    ['app.py'],  # 主入口
    pathex=[str(root_dir)],
    binaries=[],
    datas=[
        # 前端构建文件
        (str(root_dir / 'frontend' / 'dist'), 'frontend/dist'),
        # 后端代码
        (str(root_dir / 'backend'), 'backend'),
        # 深度阅读步骤
        (str(root_dir / 'deep_reading_steps'), 'deep_reading_steps'),
        # 配置文件
        (str(root_dir / '.env.example'), '.'),
        (str(root_dir / 'requirements.txt'), '.'),
        # 其他必要文件
        (str(root_dir / 'prompts'), 'prompts'),
        (str(root_dir / 'paddleocr_extractor'), 'paddleocr_extractor'),
    ],
    hiddenimports=[
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'sqlalchemy',
        'aiosqlite',
        'alembic',
        'passlib',
        'bcrypt',
        'python_jose',
        'apscheduler',
        'email_validator',
        'gradio',
        'pdfplumber',
        'pypdf',
        'pymupdf',
        'openai',
        'pandas',
        'openpyxl',
        'tqdm',
        'pyyaml',
        'json_repair',
        'requests',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 收集数据文件
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 单文件模式
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DeepReadingAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 显示控制台以便查看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',  # 可选：应用图标
)
```

### Task 2: 创建打包脚本

**Files:**
- Create: `build_windows.py`

```python
#!/usr/bin/env python3
"""
Windows 可执行文件打包脚本
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

def clean_build():
    """清理构建目录"""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"Cleaned: {dir_name}")

def check_dependencies():
    """检查打包依赖"""
    required = ['pyinstaller', 'upx']
    for pkg in required:
        try:
            __import__(pkg)
            print(f"✓ {pkg} installed")
        except ImportError:
            print(f"✗ {pkg} not found, installing...")
            subprocess.run([sys.executable, '-m', 'pip', 'install', pkg], check=True)

def create_icon():
    """创建应用图标（如果不存在）"""
    if not os.path.exists('icon.ico'):
        print("Note: No icon.ico found, using default icon")
        # 可以在这里生成一个简单的图标

def build_executable():
    """构建可执行文件"""
    print("\n=== Building Windows Executable ===")
    print("This may take 10-20 minutes...\n")

    # 使用 PyInstaller 构建
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--onefile',  # 单文件模式
        '--name=DeepReadingAgent',
        '--add-data=frontend/dist;frontend/dist',
        '--add-data=backend;backend',
        '--add-data=deep_reading_steps;deep_reading_steps',
        '--add-data=.env.example;.',
        '--add-data=requirements.txt;.',
        '--add-data=prompts;prompts',
        '--add-data=paddleocr_extractor;paddleocr_extractor',
        '--hidden-import=uvicorn',
        '--hidden-import=uvicorn.logging',
        '--hidden-import=uvicorn.loops',
        '--hidden-import=uvicorn.loops.auto',
        '--hidden-import=uvicorn.protocols',
        '--hidden-import=uvicorn.protocols.http',
        '--hidden-import=uvicorn.protocols.http.auto',
        '--hidden-import=uvicorn.protocols.websockets',
        '--hidden-import=uvicorn.protocols.websockets.auto',
        '--hidden-import=uvicorn.lifespan',
        '--hidden-import=uvicorn.lifespan.on',
        '--hidden-import=fastapi',
        '--hidden-import=sqlalchemy',
        '--hidden-import=aiosqlite',
        '--hidden-import=alembic',
        '--hidden-import=passlib',
        '--hidden-import=bcrypt',
        '--hidden-import=python_jose',
        '--hidden-import=apscheduler',
        '--hidden-import=email_validator',
        '--hidden-import=gradio',
        '--hidden-import=pdfplumber',
        '--hidden-import=pypdf',
        '--hidden-import=pymupdf',
        '--hidden-import=openai',
        '--hidden-import=pandas',
        '--hidden-import=openpyxl',
        '--hidden-import=tqdm',
        '--hidden-import=pyyaml',
        '--hidden-import=json_repair',
        '--hidden-import=requests',
        '--hidden-import=dotenv',
        'app.py'
    ]

    subprocess.run(cmd, check=True)

def create_launcher():
    """创建启动脚本"""
    launcher_content = '''@echo off
chcp 65001 >nul 2>&1
title Deep Reading Agent

echo ============================================
echo   Deep Reading Agent - Windows Edition
echo ============================================
echo.

:: 检查配置文件
if not exist ".env" (
    echo [INFO] First run detected.
    echo [INFO] Creating configuration file from template...
    copy ".env.example" ".env" >nul 2>&1
    echo.
    echo [ACTION REQUIRED] Please edit .env file and add your API keys:
    echo   1. DEEPSEEK_API_KEY (required)
    echo   2. PADDLEOCR_REMOTE_URL (optional, recommended)
    echo   3. PADDLEOCR_REMOTE_TOKEN (optional, recommended)
    echo.
    echo Press any key to open .env file for editing...
    pause >nul
    notepad .env
    echo.
    echo Please restart the application after configuring .env
    pause
    exit /b 0
)

:: 启动应用
echo Starting Deep Reading Agent...
echo.
echo Access URL: http://127.0.0.1:7860
echo Press Ctrl+C to stop the server.
echo ============================================
echo.

:: 打开浏览器
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:7860"

:: 启动应用
DeepReadingAgent.exe

echo.
echo Deep Reading Agent stopped.
pause
'''

    with open('dist/启动DeepReadingAgent.bat', 'w', encoding='utf-8') as f:
        f.write(launcher_content)
    print("Created: dist/启动DeepReadingAgent.bat")

def create_readme():
    """创建使用说明"""
    readme_content = '''# Deep Reading Agent - Windows 便携版

## 快速开始

1. **解压文件**：将整个文件夹解压到任意位置
2. **首次运行**：双击 `启动DeepReadingAgent.bat`
3. **配置 API**：按提示编辑 `.env` 文件，填入你的 API 密钥
4. **访问应用**：浏览器会自动打开 http://127.0.0.1:7860

## 系统要求

- Windows 10/11 (64位)
- 至少 4GB 内存
- 500MB 磁盘空间
- 网络连接（用于 API 调用）

## 必需配置

在 `.env` 文件中配置以下密钥：

```
# 必须配置
DEEPSEEK_API_KEY=sk-你的密钥

# 推荐配置（提升 PDF 提取质量）
PADDLEOCR_REMOTE_URL=你的PaddleOCR地址
PADDLEOCR_REMOTE_TOKEN=你的Token
```

## 获取 API 密钥

1. **DeepSeek API**：https://platform.deepseek.com/
2. **PaddleOCR**（可选）：自建或使用云服务

## 功能说明

- **PDF 分析**：上传 PDF 文件进行深度阅读分析
- **批量处理**：支持文件夹批量处理
- **多种分析**：支持定量研究（7步）和定性研究（4层）
- **Obsidian 输出**：生成兼容 Obsidian 的 Markdown 报告

## 常见问题

### Q: 启动后无法访问？
A: 检查防火墙设置，确保 7860 端口未被占用。

### Q: API 调用失败？
A: 检查 `.env` 中的 API 密钥是否正确，网络是否正常。

### Q: 如何更新？
A: 下载新版本，保留 `.env` 文件，替换其他文件即可。

## 文件说明

- `DeepReadingAgent.exe` - 主程序
- `启动DeepReadingAgent.bat` - 启动脚本
- `.env` - 配置文件（首次运行自动创建）
- `deep_reading_results/` - 分析结果输出目录
- `_uploads/` - 上传文件临时目录
'''

    with open('dist/使用说明.txt', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print("Created: dist/使用说明.txt")

def create_distribution():
    """创建分发包"""
    print("\n=== Creating Distribution Package ===")

    # 创建分发目录
    dist_dir = Path('dist')
    package_dir = dist_dir / 'DeepReadingAgent-Windows'
    package_dir.mkdir(exist_ok=True)

    # 复制文件
    files_to_copy = [
        ('dist/DeepReadingAgent.exe', package_dir / 'DeepReadingAgent.exe'),
        ('dist/启动DeepReadingAgent.bat', package_dir / '启动DeepReadingAgent.bat'),
        ('dist/使用说明.txt', package_dir / '使用说明.txt'),
        ('.env.example', package_dir / '.env.example'),
    ]

    for src, dst in files_to_copy:
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"Copied: {dst.name}")

    # 创建空目录
    dirs_to_create = ['deep_reading_results', '_uploads', 'logs']
    for dir_name in dirs_to_create:
        (package_dir / dir_name).mkdir(exist_ok=True)
        print(f"Created dir: {dir_name}/")

    # 创建 ZIP 压缩包
    zip_path = dist_dir / 'DeepReadingAgent-Windows.zip'
    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', dist_dir, package_dir.name)
    print(f"\nCreated: {zip_path}")
    print(f"Size: {zip_path.stat().st_size / 1024 / 1024:.1f} MB")

def main():
    """主函数"""
    print("=== Deep Reading Agent - Windows Packager ===\n")

    # 切换到项目根目录
    os.chdir(Path(__file__).parent)

    # 清理旧构建
    clean_build()

    # 检查依赖
    check_dependencies()

    # 创建图标
    create_icon()

    # 构建可执行文件
    build_executable()

    # 创建启动脚本
    create_launcher()

    # 创建说明文档
    create_readme()

    # 创建分发包
    create_distribution()

    print("\n=== Build Complete! ===")
    print("Distribution package created in: dist/DeepReadingAgent-Windows.zip")
    print("\nNext steps:")
    print("1. Test the executable on a clean Windows machine")
    print("2. Verify all features work correctly")
    print("3. Distribute the ZIP file to users")

if __name__ == '__main__':
    main()
```

### Task 3: 创建简化版启动器

**Files:**
- Create: `launcher.py`

```python
#!/usr/bin/env python3
"""
Deep Reading Agent 启动器
提供配置向导和启动管理
"""
import os
import sys
import webbrowser
import subprocess
from pathlib import Path
from dotenv import load_dotenv

def check_env():
    """检查环境配置"""
    env_path = Path('.env')
    env_example = Path('.env.example')

    if not env_path.exists():
        if env_example.exists():
            print("首次运行，创建配置文件...")
            env_path.write_text(env_example.read_text(encoding='utf-8'), encoding='utf-8')
            print("\n请编辑 .env 文件配置 API 密钥：")
            print("1. DEEPSEEK_API_KEY (必须)")
            print("2. PADDLEOCR_REMOTE_URL (推荐)")
            print("3. PADDLEOCR_REMOTE_TOKEN (推荐)")
            print("\n按 Enter 键打开配置文件...")
            input()
            os.startfile(str(env_path))
            print("配置完成后，请重新运行程序。")
            sys.exit(0)
        else:
            print("错误：找不到配置模板文件 .env.example")
            sys.exit(1)

    load_dotenv(env_path)

    # 检查必需配置
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key or api_key.startswith('sk-xxx'):
        print("错误：DEEPSEEK_API_KEY 未配置或配置无效")
        print("请编辑 .env 文件，填入有效的 API 密钥")
        os.startfile(str(env_path))
        sys.exit(1)

    return True

def find_free_port():
    """查找可用端口"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def start_app():
    """启动应用"""
    print("\n" + "="*50)
    print("  Deep Reading Agent - 启动中...")
    print("="*50 + "\n")

    # 检查配置
    check_env()

    # 查找可用端口
    port = find_free_port()
    print(f"使用端口: {port}")

    # 设置环境变量
    os.environ['PORT'] = str(port)

    # 启动应用
    print("\n正在启动应用，请稍候...")
    print(f"访问地址: http://127.0.0.1:{port}")
    print("按 Ctrl+C 停止服务\n")

    # 延迟打开浏览器
    import threading
    def open_browser():
        import time
        time.sleep(3)
        webbrowser.open(f'http://127.0.0.1:{port}')

    threading.Thread(target=open_browser, daemon=True).start()

    # 启动 FastAPI 应用
    try:
        from backend.main import app
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n\n应用已停止。")
    except Exception as e:
        print(f"\n启动失败: {e}")
        print("请检查配置和依赖是否正确。")
        input("按 Enter 键退出...")

def main():
    """主函数"""
    try:
        start_app()
    except Exception as e:
        print(f"发生错误: {e}")
        input("按 Enter 键退出...")

if __name__ == '__main__':
    main()
```

### Task 4: 更新 PyInstaller 配置

**Files:**
- Modify: `app.py` (添加打包支持)

```python
# 在 app.py 开头添加打包支持代码
import sys
import os

def get_resource_path(relative_path):
    """获取资源文件路径（支持打包后的路径）"""
    if getattr(sys, 'frozen', False):
        # 打包后的路径
        base_path = sys._MEIPASS
    else:
        # 开发环境路径
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# 修改静态文件路径
STATIC_DIR = get_resource_path('frontend/dist')
if os.path.exists(STATIC_DIR):
    # 配置静态文件服务
    pass
```

### Task 5: 创建构建和测试脚本

**Files:**
- Create: `build_and_test.ps1`

```powershell
# Deep Reading Agent - Windows 打包和测试脚本

Write-Host "=== Deep Reading Agent - Build and Test ===" -ForegroundColor Cyan
Write-Host ""

# 检查 Python 版本
Write-Host "[1/6] Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Python not found" -ForegroundColor Red
    exit 1
}
Write-Host "  Found: $pythonVersion" -ForegroundColor Green

# 检查依赖
Write-Host "[2/6] Checking dependencies..." -ForegroundColor Yellow
pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Failed to install PyInstaller" -ForegroundColor Red
    exit 1
}
Write-Host "  PyInstaller installed" -ForegroundColor Green

# 清理旧构建
Write-Host "[3/6] Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
Write-Host "  Cleaned" -ForegroundColor Green

# 构建可执行文件
Write-Host "[4/6] Building executable (this may take 10-20 minutes)..." -ForegroundColor Yellow
python build_windows.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Build failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Build complete" -ForegroundColor Green

# 测试可执行文件
Write-Host "[5/6] Testing executable..." -ForegroundColor Yellow
$testExe = "dist\DeepReadingAgent.exe"
if (Test-Path $testExe) {
    Write-Host "  Executable created: $testExe" -ForegroundColor Green
    $size = (Get-Item $testExe).Length / 1MB
    Write-Host "  Size: $([math]::Round($size, 1)) MB" -ForegroundColor Green
} else {
    Write-Host "  Error: Executable not found" -ForegroundColor Red
    exit 1
}

# 创建分发包
Write-Host "[6/6] Creating distribution package..." -ForegroundColor Yellow
if (Test-Path "dist\DeepReadingAgent-Windows.zip") {
    $zipSize = (Get-Item "dist\DeepReadingAgent-Windows.zip").Length / 1MB
    Write-Host "  Package created: dist\DeepReadingAgent-Windows.zip" -ForegroundColor Green
    Write-Host "  Size: $([math]::Round($zipSize, 1)) MB" -ForegroundColor Green
} else {
    Write-Host "  Warning: ZIP package not created" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Build Complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Test on a clean Windows machine" -ForegroundColor White
Write-Host "2. Verify all features work" -ForegroundColor White
Write-Host "3. Distribute DeepReadingAgent-Windows.zip" -ForegroundColor White
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
```

### Task 6: 创建安装和更新脚本

**Files:**
- Create: `install.bat`

```batch
@echo off
chcp 65001 >nul 2>&1
title Deep Reading Agent - 安装程序

echo ============================================
echo   Deep Reading Agent - 安装程序
echo ============================================
echo.

:: 检查是否已安装
if exist "DeepReadingAgent.exe" (
    echo [INFO] 检测到已安装的版本。
    echo [INFO] 如需更新，请先卸载旧版本。
    echo.
    pause
    exit /b 0
)

:: 解压文件
echo [1/3] 正在解压文件...
if not exist "DeepReadingAgent-Windows.zip" (
    echo [ERROR] 找不到安装包 DeepReadingAgent-Windows.zip
    pause
    exit /b 1
)

:: 使用 PowerShell 解压
powershell -Command "Expand-Archive -Path 'DeepReadingAgent-Windows.zip' -DestinationPath '.' -Force"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 解压失败
    pause
    exit /b 1
)
echo [OK] 文件解压完成

:: 创建快捷方式
echo [2/3] 创建桌面快捷方式...
set SCRIPT_DIR=%~dp0
set SHORTCUT_PATH=%USERPROFILE%\Desktop\Deep Reading Agent.lnk

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%SCRIPT_DIR%启动DeepReadingAgent.bat'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'Deep Reading Agent - 学术论文深度阅读工具'; $s.Save()"
echo [OK] 桌面快捷方式已创建

:: 完成安装
echo [3/3] 安装完成
echo.
echo ============================================
echo   安装成功！
echo ============================================
echo.
echo 使用方法：
echo 1. 双击桌面上的 "Deep Reading Agent" 快捷方式
echo 2. 或者进入安装目录，双击 "启动DeepReadingAgent.bat"
echo.
echo 首次运行需要配置 API 密钥，请按提示操作。
echo.
pause
```

---

## 测试验证

### 测试清单
1. **构建测试**：在干净的 Windows 环境构建
2. **功能测试**：验证所有核心功能
3. **兼容性测试**：在不同 Windows 版本测试
4. **性能测试**：检查启动时间和内存占用

### 测试步骤
```powershell
# 1. 构建测试
.\build_and_test.ps1

# 2. 在干净环境测试
# 使用虚拟机或干净的 Windows 系统
# 解压 DeepReadingAgent-Windows.zip
# 双击 启动DeepReadingAgent.bat

# 3. 功能验证
# - 配置 .env 文件
# - 上传 PDF 文件
# - 执行深度阅读分析
# - 检查输出结果
```

---

## 分发方式

### 1. 直接分发
- 提供 ZIP 压缩包
- 用户解压后运行

### 2. 安装程序
- 使用 Inno Setup 或 NSIS 创建安装程序
- 自动创建快捷方式和卸载程序

### 3. 云存储分发
- 上传到网盘（百度网盘、阿里云盘等）
- 提供下载链接

---

## 维护和更新

### 更新流程
1. 修复 bug 或添加功能
2. 运行构建脚本
3. 测试新版本
4. 发布新版本 ZIP

### 版本管理
- 使用语义化版本号
- 维护更新日志
- 提供升级说明

---

## 注意事项

### 1. 文件大小
- 预计最终 ZIP 包：200-300MB
- 主要来自 Python 解释器和依赖库

### 2. 启动时间
- 首次启动：10-30 秒（解压临时文件）
- 后续启动：5-10 秒

### 3. 杀毒软件
- PyInstaller 打包的文件可能被误报
- 需要添加白名单或签名

### 4. 系统要求
- Windows 10/11 64位
- 至少 4GB 内存
- 500MB 磁盘空间

---

## 优化建议

### 1. 减小文件大小
- 使用 UPX 压缩
- 排除不必要的模块
- 使用虚拟环境精简依赖

### 2. 提高启动速度
- 使用目录模式而非单文件模式
- 预编译 Python 字节码
- 优化导入顺序

### 3. 改善用户体验
- 添加进度条
- 提供配置向导
- 自动检查更新

---

## 执行选项

**规划已保存到 `docs/superpowers/plans/2026-05-03-windows-executable-packaging.md`**

两种执行方式：

1. **子代理驱动（推荐）** - 每个任务分发给独立子代理执行，任务间进行审查
2. **内联执行** - 在当前会话中执行所有任务，设置检查点进行审查

**选择哪种方式？**

#!/usr/bin/env python3
"""
Deep Reading Agent - Web Edition Launcher
Entry point for standalone distribution.
"""
import os
import sys
import webbrowser
import time
import threading
from pathlib import Path

# Determine project root (handles both dev and PyInstaller)
if getattr(sys, 'frozen', False):
    # PyInstaller creates a temp folder and stores path in _MEIPASS
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).parent.resolve()

# Ensure backend modules can be imported
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

# Create user data directory
if sys.platform == 'win32':
    DATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'DeepReadingAgent'
else:
    DATA_DIR = Path.home() / '.local' / 'share' / 'DeepReadingAgent'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Create subdirectories
(DATA_DIR / '_uploads').mkdir(exist_ok=True)
(DATA_DIR / 'deep_reading_results').mkdir(exist_ok=True)
(DATA_DIR / 'logs').mkdir(exist_ok=True)

# Set data dir environment variable
os.environ['DEEP_READING_DATA_DIR'] = str(DATA_DIR)

# Check for .env file
env_file = PROJECT_ROOT / '.env'
env_example = PROJECT_ROOT / '.env.example'

if not env_file.exists() and env_example.exists():
    print("[首次运行] 未检测到 .env 配置文件，正在从模板创建...")
    import shutil
    shutil.copy2(env_example, env_file)
    print("已创建 .env 文件。请按以下步骤配置：")
    print("  1. 用记事本打开 .env 文件")
    print("  2. 将 DEEPSEEK_API_KEY=sk-xxx 中的 sk-xxx 替换为你的 API 密钥")
    print("  3. 保存并关闭文件")
    print("  获取 API 密钥：https://platform.deepseek.com/")
    print("")
    input("按回车键继续启动...")

print("=" * 50)
print("  Deep Reading Agent 正在启动...")
print("=" * 50)
print(f"  数据目录: {DATA_DIR}")
print(f"  前端地址: http://localhost:8000")
print("=" * 50)
print("")

def open_browser():
    """Open browser after server starts."""
    time.sleep(3)
    webbrowser.open('http://localhost:8000')

# Start browser in background
browser_thread = threading.Thread(target=open_browser, daemon=True)
browser_thread.start()

# Import and run the FastAPI app
import uvicorn
from backend.main import app

if __name__ == "__main__":
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n[shutdown] 服务已停止")
    except Exception as e:
        print(f"\n[error] 启动失败: {e}")
        input("按回车键退出...")

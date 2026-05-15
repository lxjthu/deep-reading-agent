#!/usr/bin/env python3
"""
Deep Reading Agent - Web Edition Launcher
Entry point for standalone distribution (PyInstaller).
"""
import os
import sys
import webbrowser
import time
import threading
from pathlib import Path

if getattr(sys, 'frozen', False):
    BUNDLE_ROOT = Path(sys._MEIPASS)
    EXE_DIR = Path(sys.executable).parent
else:
    BUNDLE_ROOT = Path(__file__).parent.resolve()
    EXE_DIR = BUNDLE_ROOT

sys.path.insert(0, str(BUNDLE_ROOT))
sys.path.insert(0, str(BUNDLE_ROOT / "backend"))

if sys.platform == 'win32':
    DATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'DeepReadingAgent'
else:
    DATA_DIR = Path.home() / '.local' / 'share' / 'DeepReadingAgent'
DATA_DIR.mkdir(parents=True, exist_ok=True)
for sub in ['_uploads', 'deep_reading_results', 'logs', 'db']:
    (DATA_DIR / sub).mkdir(exist_ok=True)

env_file = DATA_DIR / '.env'
env_example = BUNDLE_ROOT / '.env.example'
if not env_file.exists() and env_example.exists():
    import shutil
    shutil.copy2(env_example, env_file)
    print("=" * 50)
    print("  [首次运行] 已创建配置文件")
    print("=" * 50)
    print(f"  配置文件: {env_file}")
    print()
    print("  请用记事本打开该文件，将 DEEPSEEK_API_KEY=sk-xxx")
    print("  中的 sk-xxx 替换为你的 API 密钥")
    print("  获取密钥: https://platform.deepseek.com/")
    print()
    input("  配置完成后按回车键启动...")

from dotenv import load_dotenv
load_dotenv(str(env_file))

db_path = DATA_DIR / 'db' / 'app.sqlite'
os.environ['DATABASE_URL'] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
os.environ['DEEP_READING_DATA_DIR'] = str(DATA_DIR)
os.environ['UPLOAD_DIR'] = str(DATA_DIR / '_uploads')
os.environ['RESULTS_DIR'] = str(DATA_DIR / 'deep_reading_results')

print("=" * 50)
print("  Deep Reading Agent 正在启动...")
print("=" * 50)
print(f"  数据目录: {DATA_DIR}")
print(f"  数据库:   {db_path}")
print(f"  前端地址: http://localhost:8000")
print("=" * 50)
print("  按 Ctrl+C 可停止服务")
print("=" * 50)
print()

def open_browser():
    time.sleep(3)
    webbrowser.open('http://localhost:8000')

threading.Thread(target=open_browser, daemon=True).start()

import uvicorn
from backend.main import app

try:
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
except KeyboardInterrupt:
    print("\n[shutdown] 服务已停止")
except Exception as e:
    print(f"\n[error] 启动失败: {e}")
    input("按回车键退出...")

#!/usr/bin/env python3
"""
Deep Reading Agent - Web Edition Launcher
Entry point for standalone distribution (PyInstaller).

启动流程：
  1. 确定数据目录（解压目录/data）
  2. 创建子目录 + 空的 .env
  3. 建表（Base.metadata.create_all）
  4. 自动 seed admin 账户（admin / admin12345）
  5. 启动 uvicorn，前端静态文件由 FastAPI FileResponse 托管
  6. 3 秒后自动打开浏览器
"""
import os
import sys
import webbrowser
import time
import threading
import asyncio
from pathlib import Path

if getattr(sys, 'frozen', False):
    BUNDLE_ROOT = Path(sys._MEIPASS)
    EXE_DIR = Path(sys.executable).parent
else:
    BUNDLE_ROOT = Path(__file__).parent.resolve()
    EXE_DIR = BUNDLE_ROOT

sys.path.insert(0, str(BUNDLE_ROOT))
sys.path.insert(0, str(BUNDLE_ROOT / "backend"))

DATA_DIR = EXE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
for sub in ['_uploads', 'deep_reading_results', 'logs', 'db']:
    (DATA_DIR / sub).mkdir(exist_ok=True)

if getattr(sys, 'frozen', False):
    LOG_FILE = DATA_DIR / 'logs' / 'startup.log'
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _log = open(LOG_FILE, 'a', encoding='utf-8')
    sys.stdout = _log
    sys.stderr = _log

env_file = DATA_DIR / '.env'
if not env_file.exists():
    env_file.write_text(
        "# Deep Reading Agent 配置文件\n"
        "# Web 模式下无需在此填写 DEEPSEEK_API_KEY，在浏览器登录后设置即可。\n"
        "# 获取密钥: https://platform.deepseek.com/\n",
        encoding='utf-8',
    )

from dotenv import load_dotenv
load_dotenv(str(env_file), override=False)

db_path = DATA_DIR / 'db' / 'app.sqlite'
os.environ.setdefault('DATABASE_URL', f"sqlite+aiosqlite:///{db_path.as_posix()}")
os.environ.setdefault('DEEP_READING_DATA_DIR', str(DATA_DIR))
os.environ.setdefault('UPLOAD_DIR', str(DATA_DIR / '_uploads'))
os.environ.setdefault('UPLOAD_ROOT_DIR', str(DATA_DIR / '_uploads'))
os.environ.setdefault('RESULTS_DIR', str(DATA_DIR / 'deep_reading_results'))
os.environ.setdefault('RESULTS_ROOT_DIR', str(DATA_DIR / 'deep_reading_results'))
os.environ.setdefault('DRA_PACKAGED_APP', '1')
os.environ.setdefault('DRA_ALLOW_LOCAL_SHUTDOWN', '1')

print("=" * 55)
print("  Deep Reading Agent  学术论文深度精读系统")
print("=" * 55)
print(f"  数据目录 : {DATA_DIR}")
print(f"  数据库   : {db_path}")
print(f"  访问地址 : http://localhost:8000")
print(f"  管理员账号: admin / admin12345")
print("=" * 55)
print("  按 Ctrl+C 停止服务")
print("=" * 55)
print()


def _init_db():
    from db.base import Base
    from db import models
    from sqlalchemy import create_engine
    sync_url = os.environ['DATABASE_URL'].replace('+aiosqlite', '')
    engine = create_engine(sync_url)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    print("[startup] 数据库初始化完成")


def _seed_admin():
    from passlib.context import CryptContext
    from sqlalchemy import select
    from db import AsyncSessionLocal
    from db.models import User

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    async def _do():
        async with AsyncSessionLocal() as session:
            existing = (
                await session.execute(select(User).where(User.username == "admin"))
            ).scalar_one_or_none()
            if existing is not None:
                print("[startup] 管理员账户已存在")
                return
            user = User(
                username="admin",
                password_hash=pwd_context.hash("admin12345"),
                role="admin",
                is_active=1,
                token_version=0,
                created_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).replace(tzinfo=None),
            )
            session.add(user)
            await session.commit()
            print("[startup] 已创建管理员账户 admin / admin12345")

    asyncio.run(_do())


_init_db()
_seed_admin()


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

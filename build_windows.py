# -*- coding: utf-8 -*-
"""Automated build script for packaging Deep Reading Agent as a Windows distribution."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
PKG_NAME = "DeepReadingAgent-Windows"
PKG_DIR = DIST_DIR / PKG_NAME
EXE_NAME = "DeepReadingAgent"


def clean_build():
    """Remove build/, dist/, and __pycache__/ directories."""
    for d in [BUILD_DIR, DIST_DIR, PROJECT_ROOT / "__pycache__"]:
        if d.exists():
            print(f"Removing {d} ...")
            shutil.rmtree(d)
    print("Clean complete.")


def check_dependencies():
    """Verify pyinstaller is installed; install if missing."""
    try:
        import PyInstaller  # noqa: F401
        print(f"PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("PyInstaller not found. Installing ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def create_icon():
    """Note if icon.ico is missing (no-op)."""
    icon_path = PROJECT_ROOT / "icon.ico"
    if icon_path.exists():
        print(f"Icon found: {icon_path}")
    else:
        print("icon.ico not found — using default icon.")


def build_executable():
    """Run PyInstaller to create a single-file executable."""
    sep = ";"
    datas = [
        ("frontend/dist", "frontend/dist"),
        (".env.example", "."),
        ("requirements.txt", "."),
        ("prompts", "prompts"),
        ("paddleocr_extractor", "paddleocr_extractor"),
        ("new_architecture", "new_architecture"),
        ("paddleocr_pipeline.py", "."),
        ("paddleocr_local.py", "."),
        ("parsers.py", "."),
        ("smart_literature_filter.py", "."),
    ]
    add_data_args = []
    for src, dst in datas:
        add_data_args.append(f"--add-data={src}{sep}{dst}")

    hidden_imports = [
        # Uvicorn
        "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        # FastAPI & ecosystem
        "fastapi", "sqlalchemy", "sqlalchemy.dialects.sqlite", "aiosqlite",
        "alembic", "passlib", "passlib.handlers.bcrypt", "bcrypt",
        "jose", "jose.jwt", "apscheduler", "apscheduler.schedulers.background",
        "apscheduler.triggers.interval", "email_validator",
        # Gradio
        "gradio",
        # PDF extraction
        "pdfplumber", "pypdf", "fitz",
        # LLM & data
        "openai", "pandas", "openpyxl", "tqdm",
        "yaml", "json_repair", "requests", "dotenv",
    ]
    hidden_args = []
    for mod in hidden_imports:
        hidden_args.append(f"--hidden-import={mod}")

    icon_path = PROJECT_ROOT / "icon.ico"
    icon_arg = [f"--icon={icon_path}"] if icon_path.exists() else []

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        f"--name={EXE_NAME}",
        *add_data_args,
        *hidden_args,
        *icon_arg,
        "app.py",
    ]

    print(f"Running PyInstaller ...")
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))
    print("Build complete.")


def create_launcher():
    """Create dist/启动DeepReadingAgent.bat with first-run setup and auto-open browser."""
    bat_content = r"""@echo off
chcp 65001 >nul 2>&1
title Deep Reading Agent

echo ============================================
echo   Deep Reading Agent - 深度阅读智能体
echo ============================================
echo.

if not exist ".env" (
    echo [首次运行] 未检测到 .env 配置文件，正在从模板创建 ...
    copy /y .env.example .env >nul
    echo.
    echo 已创建 .env 文件。请按以下步骤配置：
    echo.
    echo   1. 用记事本打开 .env 文件
    echo   2. 将 DEEPSEEK_API_KEY=sk-xxx 中的 sk-xxx 替换为你的 API 密钥
    echo   3. （可选）配置 PADDLEOCR_REMOTE_URL 和 PADDLEOCR_REMOTE_TOKEN
    echo   4. 保存并关闭文件
    echo.
    echo 获取 API 密钥：https://platform.deepseek.com/
    echo.
    pause
)

echo 正在启动 Deep Reading Agent ...
echo 启动后将自动打开浏览器访问 http://localhost:7860
echo.

start "" /b DeepReadingAgent.exe
timeout /t 3 /nobreak >nul
start http://localhost:7860

echo Deep Reading Agent 已启动！
echo 按 Ctrl+C 可停止程序。
pause >nul
"""
    bat_path = DIST_DIR / "启动DeepReadingAgent.bat"
    bat_path.parent.mkdir(parents=True, exist_ok=True)
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"Launcher created: {bat_path}")


def create_readme():
    """Create dist/使用说明.txt with user guide."""
    readme_content = """============================================
Deep Reading Agent - 深度阅读智能体 使用说明
============================================

一、启动方法
-----------
1. 双击 "启动DeepReadingAgent.bat"
2. 首次运行会自动创建 .env 配置文件
3. 按提示填写 DeepSeek API 密钥
4. 等待浏览器自动打开 http://localhost:7860

二、获取 API 密钥
-----------------
DeepSeek API 密钥（必须）：
  https://platform.deepseek.com/

PaddleOCR 远程 API（推荐，提升 PDF 提取质量）：
  请参考项目文档获取 PaddleOCR 服务地址和 Token

三、使用步骤
-----------
1. 在浏览器中打开的页面上传 PDF 论文
2. 系统自动进行论文分类（定量/定性）
3. 等待深度阅读分析完成
4. 查看生成的 Markdown 分析报告

四、输出文件
-----------
- deep_reading_results/  — 深度阅读分析结果
- _uploads/              — 上传的 PDF 文件
- logs/                  — 运行日志

五、常见问题
-----------
Q: 启动后浏览器没有自动打开？
A: 手动访问 http://localhost:7860

Q: 提示 API 密钥错误？
A: 检查 .env 文件中的 DEEPSEEK_API_KEY 是否正确

Q: 分析速度很慢？
A: DeepSeek Reasoner 模型需要较长思考时间，请耐心等待

Q: 如何停止程序？
A: 在命令行窗口按 Ctrl+C
"""
    readme_path = DIST_DIR / "使用说明.txt"
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"Readme created: {readme_path}")


def create_distribution():
    """Assemble final package and create ZIP archive."""
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)

    exe_src = DIST_DIR / f"{EXE_NAME}.exe"
    if exe_src.exists():
        shutil.copy2(exe_src, PKG_DIR / f"{EXE_NAME}.exe")
    else:
        print(f"WARNING: {exe_src} not found!")

    for fname in ["启动DeepReadingAgent.bat", "使用说明.txt"]:
        src = DIST_DIR / fname
        if src.exists():
            shutil.copy2(src, PKG_DIR / fname)

    env_example = PROJECT_ROOT / ".env.example"
    if env_example.exists():
        shutil.copy2(env_example, PKG_DIR / ".env.example")

    for d in ["deep_reading_results", "_uploads", "logs"]:
        (PKG_DIR / d).mkdir(exist_ok=True)
        (PKG_DIR / d / ".gitkeep").touch()

    zip_path = DIST_DIR / f"{PKG_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    print(f"Creating {zip_path} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PKG_DIR):
            for f in files:
                file_path = Path(root) / f
                arcname = file_path.relative_to(DIST_DIR)
                zf.write(file_path, arcname)
    print(f"Distribution archive created: {zip_path}")


def main():
    """Orchestrate all build steps."""
    print("=" * 50)
    print("  Deep Reading Agent — Windows Build Script")
    print("=" * 50)

    clean_build()
    check_dependencies()
    create_icon()
    build_executable()
    create_launcher()
    create_readme()
    create_distribution()

    print()
    print("=" * 50)
    print("  Build finished!")
    print(f"  Package: {DIST_DIR / f'{PKG_NAME}.zip'}")
    print("=" * 50)


if __name__ == "__main__":
    main()

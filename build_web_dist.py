#!/usr/bin/env python3
"""
Build script for Deep Reading Agent Web Edition — Windows Standalone Distribution.

Usage:
    python build_web_dist.py

Outputs:
    dist/DeepReadingAgent-Web.zip   — 解压后双击 bat 即可运行

Prerequisites:
    1. 前端已构建: cd frontend && npm run build
    2. pip install pyinstaller
"""
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
PKG_NAME = "DeepReadingAgent-Web"
PKG_DIR = DIST_DIR / PKG_NAME
EXE_NAME = "DeepReadingAgent"


def step(label: str) -> None:
    print(f"\n{'='*55}\n  {label}\n{'='*55}")


def clean_build():
    for d in [BUILD_DIR, DIST_DIR]:
        if d.exists():
            print(f"  Removing {d} ...")
            for attempt in range(5):
                try:
                    shutil.rmtree(d)
                    break
                except PermissionError:
                    if attempt == 4:
                        remaining = list(d.iterdir()) if d.exists() else []
                        if d == DIST_DIR and not remaining:
                            print(f"  WARNING: {d} is locked but empty; reusing it.")
                            break
                        raise
                    time.sleep(1)
    print("  Clean complete.")


def check_frontend_dist():
    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    print("  Building fresh frontend/dist ...")
    npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
    if npm_cmd is None:
        raise RuntimeError("npm not found. Please install Node.js and ensure npm is on PATH.")
    subprocess.check_call(
        [npm_cmd, "run", "build"],
        cwd=str(PROJECT_ROOT / "frontend"),
    )
    print(f"  frontend/dist OK ({sum(1 for _ in frontend_dist.rglob('*'))} files)")


def check_dependencies():
    try:
        import PyInstaller
        print(f"  PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_executable():
    sep = ";"

    datas = [
        ("frontend/dist", "frontend/dist"),
        (".env.example", "."),
        ("prompts", "prompts"),
        ("new_architecture", "new_architecture"),
        ("backend", "backend"),
        ("parsers.py", "."),
        ("smart_literature_filter.py", "."),
        ("extractor.py", "."),
    ]

    add_data_args = []
    for src, dst in datas:
        src_path = PROJECT_ROOT / src
        if src_path.exists():
            add_data_args.append(f"--add-data={src}{sep}{dst}")
        else:
            print(f"  WARNING: {src} not found, skipping")

    hidden_imports = [
        "extractor",
        "parsers",
        "smart_literature_filter",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "sqlalchemy",
        "sqlalchemy.dialects.sqlite",
        "aiosqlite",
        "passlib",
        "passlib.handlers.bcrypt",
        "bcrypt",
        "jose",
        "jose.jwt",
        "apscheduler",
        "apscheduler.schedulers.background",
        "apscheduler.schedulers.asyncio",
        "apscheduler.triggers.interval",
        "email_validator",
        "python_multipart",
        "multipart",
        "pdfplumber",
        "pdfminer",
        "pdfminer.high_level",
        "pdfminer.layout",
        "pdfminer.converter",
        "pdfminer.pdfinterp",
        "pdfminer.pdfpage",
        "pdfminer.pdfdocument",
        "pdfminer.psparser",
        "pdfminer.pdftypes",
        "pdfminer.cmapdb",
        "pdfminer.encodingdb",
        "pdfminer.image",
        "pypdf",
        "PyPDF2",
        "fitz",
        "openai",
        "httpx",
        "pandas",
        "openpyxl",
        "tqdm",
        "yaml",
        "json_repair",
        "requests",
        "dotenv",
        "markdown",
        "services.ai_template_generator",
        "services.crossref_source",
        "services.data_portability",
        "services.deepseek_refs",
        "services.document_parser",
        "services.metadata_match_service",
        "services.metadata_sources",
        "services.openalex_source",
        "services.pdf_metadata_extract",
        "services.pdf_metadata_llm",
        "services.queue_manager",
    ]

    hidden_args = [f"--hidden-import={m}" for m in hidden_imports]
    collect_submodules = [
        "pdfminer",
        "pdfplumber",
        "pypdf",
        "PyPDF2",
        "fitz",
        "openpyxl",
    ]
    collect_args = [f"--collect-submodules={m}" for m in collect_submodules]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        f"--name={EXE_NAME}",
        "--clean",
        "--noconfirm",
        "--paths=backend",
        *add_data_args,
        *hidden_args,
        *collect_args,
        "run_web.py",
    ]

    print("  Running PyInstaller...")
    print("  " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))
    print("  Build complete.")


def create_launcher():
    bat_content = r"""@echo off
chcp 65001 >nul 2>&1
title Deep Reading Agent

echo ======================================================
echo   Deep Reading Agent  学术论文深度精读系统
echo ======================================================
echo.

DeepReadingAgent\DeepReadingAgent.exe
if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序异常退出，错误代码: %errorlevel%
)
pause
"""
    bat_path = DIST_DIR / "启动DeepReadingAgent.bat"
    bat_path.parent.mkdir(parents=True, exist_ok=True)
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"  Launcher: {bat_path}")


def create_readme():
    readme = """======================================================
Deep Reading Agent  学术论文深度精读系统 使用说明
======================================================

一、启动方式
-----------
1. 解压压缩包到任意目录
2. 双击 "启动DeepReadingAgent.bat"
3. 等待浏览器自动打开 http://localhost:8000
4. 首次使用请先注册账号，或用管理员账号登录:
   用户名: admin
   密码:   admin12345

二、配置 API 密钥
----------------
登录后在浏览器界面中设置 DeepSeek API Key 即可，无需手动编辑配置文件。
获取密钥: https://platform.deepseek.com/

三、使用步骤
-----------
1. 注册/登录账号
2. 在设置中填入 DeepSeek API Key
3. 上传 PDF 论文
4. 选择精读模式（长文本/七步/四步）
5. 查看分析结果和文献库

四、功能说明
-----------
- 文献筛选：上传文献题录，AI 智能筛选
- 长文本精读：一次性精读整篇论文
- 七步精读（定量）：按步骤深度分析
- 四步精读（定性）：定性分析框架
- 对比综述：多篇论文对比分析
- AI 综述：自动生成文献综述
- 文献库：管理所有已读论文
- 参考文献提取：自动提取引用文献
- 批量精读：文件夹批量处理

五、常见问题
-----------
Q: 启动后浏览器没有自动打开？
A: 手动访问 http://localhost:8000

Q: 分析速度很慢？
A: DeepSeek Reasoner 模型需要较长思考时间，请耐心等待

Q: 如何停止程序？
A: 关闭命令行窗口或按 Ctrl+C

六、数据目录
-----------
用户数据保存在解压目录中:
  DeepReadingAgent\\data\\

包括: 数据库、上传的 PDF、分析结果、日志
"""
    readme_path = DIST_DIR / "使用说明.txt"
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(readme, encoding="utf-8")
    print(f"  README: {readme_path}")


def create_distribution():
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)

    exe_dir = DIST_DIR / EXE_NAME
    if exe_dir.exists():
        shutil.copytree(exe_dir, PKG_DIR / EXE_NAME)
    else:
        print(f"  WARNING: {exe_dir} not found!")
        return

    for fname in ["启动DeepReadingAgent.bat", "使用说明.txt"]:
        src = DIST_DIR / fname
        if src.exists():
            shutil.copy2(src, PKG_DIR / fname)

    zip_path = DIST_DIR / f"{PKG_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"  Creating {zip_path} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PKG_DIR):
            for f in files:
                file_path = Path(root) / f
                arcname = file_path.relative_to(DIST_DIR)
                zf.write(file_path, arcname)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  Package: {zip_path} ({size_mb:.1f} MB)")


def main():
    step("Deep Reading Agent — Web Edition Build")
    clean_build()
    step("Step 1/6: Check frontend dist")
    check_frontend_dist()
    step("Step 2/6: Check dependencies")
    check_dependencies()
    step("Step 3/6: Build executable (PyInstaller)")
    build_executable()
    step("Step 4/6: Create launcher")
    create_launcher()
    step("Step 5/6: Create readme")
    create_readme()
    step("Step 6/6: Package ZIP")
    create_distribution()

    print()
    step("Build finished!")
    print(f"  Package: {DIST_DIR / f'{PKG_NAME}.zip'}")


if __name__ == "__main__":
    main()

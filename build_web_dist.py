#!/usr/bin/env python3
"""
Build script for Deep Reading Agent Web Edition - Windows Distribution
Creates a standalone executable + frontend bundle.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
PKG_NAME = "DeepReadingAgent-Web"
PKG_DIR = DIST_DIR / PKG_NAME
EXE_NAME = "DeepReadingAgent"

def clean_build():
    """Clean previous build artifacts."""
    for d in [BUILD_DIR, DIST_DIR]:
        if d.exists():
            print(f"Removing {d} ...")
            shutil.rmtree(d)
    print("Clean complete.")

def check_dependencies():
    """Verify pyinstaller is installed."""
    try:
        import PyInstaller
        print(f"PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def build_executable():
    """Build executable with PyInstaller (onedir mode for better performance)."""
    sep = ";" if sys.platform == "win32" else ":"
    
    # Data files to include
    datas = [
        ("frontend/dist", "frontend/dist"),
        (".env.example", "."),
        ("prompts", "prompts"),
        ("new_architecture", "new_architecture"),
        ("backend", "backend"),
    ]
    
    add_data_args = []
    for src, dst in datas:
        src_path = PROJECT_ROOT / src
        if src_path.exists():
            add_data_args.append(f"--add-data={src}{sep}{dst}")
    
    # Hidden imports
    hidden_imports = [
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
        "alembic",
        "passlib",
        "passlib.handlers.bcrypt",
        "bcrypt",
        "jose",
        "jose.jwt",
        "apscheduler",
        "apscheduler.schedulers.background",
        "apscheduler.triggers.interval",
        "email_validator",
        "pdfplumber",
        "pypdf",
        "fitz",
        "openai",
        "pandas",
        "openpyxl",
        "tqdm",
        "yaml",
        "json_repair",
        "requests",
        "dotenv",
        "backend.main",
        "backend.cleanup",
        "backend.db",
        "backend.db.models",
        "backend.db.session",
        "backend.db.utils",
        "backend.dimension_seed",
        "backend.prompt_service",
        "backend.template_seed",
        "backend.prompt_registry",
        "backend.upload_storage",
        "backend.auth",
        "backend.auth.dependencies",
        "backend.auth.security",
        "backend.auth.schemas",
        "backend.routers.admin",
        "backend.routers.auth",
        "backend.routers.upload",
        "backend.routers.filter",
        "backend.routers.reading",
        "backend.routers.prompts",
        "backend.routers.download",
        "backend.routers.history",
        "backend.routers.compare",
        "backend.routers.deploy",
        "backend.routers.library",
        "backend.routers.references",
        "backend.routers.data",
        "backend.routers.dimensions",
        "backend.services.queue_manager",
        "backend.services.deepseek_refs",
        "backend.services.data_portability",
        "backend.services.metadata_match_service",
        "backend.services.metadata_sources",
        "backend.services.crossref_source",
        "backend.services.openalex_source",
        "backend.services.pdf_metadata_extract",
        "backend.services.pdf_metadata_llm",
        "backend.services.ai_template_generator",
        "backend.utils.api_key",
        "new_architecture.config",
        "new_architecture.paper_cache",
        "new_architecture.conversation_engine",
        "new_architecture.analysis_dimensions",
    ]
    
    hidden_args = []
    for mod in hidden_imports:
        hidden_args.append(f"--hidden-import={mod}")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",  # Directory mode for faster startup
        f"--name={EXE_NAME}",
        "--clean",
        "--noconfirm",
        *add_data_args,
        *hidden_args,
        "run_web.py",
    ]
    
    print(f"Running PyInstaller...")
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))
    print("Build complete.")

def create_launcher():
    """Create launcher batch file."""
    bat_content = """@echo off
chcp 65001 >nul 2>&1
title Deep Reading Agent

echo ============================================
echo   Deep Reading Agent - 学术论文深度精读系统
echo ============================================
echo.

DeepReadingAgent\\DeepReadingAgent.exe
if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序异常退出，错误代码: %errorlevel%
)
pause
"""
    bat_path = DIST_DIR / "启动DeepReadingAgent.bat"
    bat_path.parent.mkdir(parents=True, exist_ok=True)
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"Launcher created: {bat_path}")

def create_readme():
    """Create user guide."""
    readme_content = """============================================
Deep Reading Agent - 学术论文深度精读系统
使用说明
============================================

一、启动方式
-----------
1. 解压压缩包到任意目录
2. 双击 "启动DeepReadingAgent.bat"
3. 首次运行会自动创建 .env 配置文件
4. 按提示填写 DeepSeek API 密钥
5. 等待浏览器自动打开 http://localhost:8000

二、获取 API 密钥
-----------------
DeepSeek API 密钥（必须）：https://platform.deepseek.com/

三、使用步骤
-----------
1. 在浏览器中注册/登录账号
2. 设置 API Key
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
- 文献库：管理所有已读论文
- 参考文献提取：自动提取引用文献

五、常见问题
-----------
Q: 启动后浏览器没有自动打开？
A: 手动访问 http://localhost:8000

Q: 提示 API 密钥错误？
A: 检查 .env 文件中的 DEEPSEEK_API_KEY 是否正确

Q: 分析速度很慢？
A: DeepSeek Reasoner 模型需要较长思考时间，请耐心等待

Q: 如何停止程序？
A: 关闭命令行窗口或按 Ctrl+C

六、数据目录
-----------
用户数据保存在：
  C:\\Users\\<用户名>\\AppData\\Local\\DeepReadingAgent\\

包括：
- 数据库文件
- 上传的 PDF
- 分析结果
- 日志文件
"""
    readme_path = DIST_DIR / "使用说明.txt"
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"Readme created: {readme_path}")

def create_distribution():
    """Package everything into a ZIP archive."""
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)
    
    # Copy executable directory
    exe_dir = DIST_DIR / EXE_NAME
    if exe_dir.exists():
        shutil.copytree(exe_dir, PKG_DIR / EXE_NAME)
    else:
        print(f"WARNING: {exe_dir} not found!")
        return
    
    # Copy launcher and readme
    for fname in ["启动DeepReadingAgent.bat", "使用说明.txt"]:
        src = DIST_DIR / fname
        if src.exists():
            shutil.copy2(src, PKG_DIR / fname)
    
    # Create empty directories for user data
    for d in ["deep_reading_results", "_uploads", "logs"]:
        (PKG_DIR / d).mkdir(exist_ok=True)
        (PKG_DIR / d / ".gitkeep").write_text("")
    
    # Create ZIP
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
    print(f"Size: {zip_path.stat().st_size / 1024 / 1024:.1f} MB")

def main():
    print("=" * 50)
    print("  Deep Reading Agent - Web Edition Build")
    print("=" * 50)
    
    clean_build()
    check_dependencies()
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

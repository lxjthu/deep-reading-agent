#!/usr/bin/env python3
"""
Deep Reading Agent — 简化启动器
提供首次运行配置向导和安全的本地启动管理。
"""

import os
import sys
import shutil
import threading
import time
import webbrowser

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE = BASE_DIR / ".env.example"


def check_env():
    """检查 .env 配置，首次运行时从 .env.example 复制模板并提示用户填写。"""
    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            shutil.copy(ENV_EXAMPLE, ENV_FILE)
            print("=" * 50)
            print("首次运行：已生成 .env 配置文件")
            print("=" * 50)
            print(f"\n请编辑以下文件并填写 DEEPSEEK_API_KEY：\n  {ENV_FILE}\n")
            try:
                os.startfile(str(ENV_FILE))
            except AttributeError:
                print("（请手动用编辑器打开 .env 文件）")
            sys.exit(0)
        else:
            print("错误：未找到 .env 和 .env.example，无法继续。")
            sys.exit(1)

    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key == "sk-xxx" or api_key.startswith("sk-xxxx"):
        print("=" * 50)
        print("配置错误：DEEPSEEK_API_KEY 未填写或为占位符")
        print("=" * 50)
        print(f"\n请编辑 .env 文件，填入真实的 API Key：\n  {ENV_FILE}\n")
        try:
            os.startfile(str(ENV_FILE))
        except AttributeError:
            print("（请手动用编辑器打开 .env 文件）")
        sys.exit(1)


PORT = 7860


def _open_browser(url, delay=3):
    """延迟后打开浏览器。"""
    time.sleep(delay)
    webbrowser.open(url)


def start_app():
    """启动 Deep Reading Agent 应用。"""
    check_env()

    os.environ["PORT"] = str(PORT)
    url = f"http://127.0.0.1:{PORT}"

    print("=" * 50)
    print("  Deep Reading Agent — 启动中...")
    print("=" * 50)
    print(f"\n  访问地址：{url}")
    print("  按 Ctrl+C 停止服务\n")

    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    try:
        from app import build_ui
        app = build_ui()
        app.queue(max_size=20)
        app.launch(
            server_name="127.0.0.1",
            server_port=PORT,
            share=False,
            show_error=True,
        )
    except KeyboardInterrupt:
        print("\n已停止。")
        sys.exit(0)


def main():
    """入口函数，统一异常处理。"""
    try:
        start_app()
    except KeyboardInterrupt:
        print("\n已停止。")
        sys.exit(0)
    except Exception as e:
        print(f"\n启动失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

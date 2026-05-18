#!/usr/bin/env python3
"""
Create a self-extracting archive for Deep Reading Agent.
Uses appended ZIP data approach (like real SFX).
"""
import os
import sys
import struct
import zipfile
import tempfile
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
ZIP_FILE = PROJECT_ROOT / "dist" / "DeepReadingAgent-Web.zip"
OUTPUT_EXE = PROJECT_ROOT / "dist" / "DeepReadingAgent-Setup.exe"

def create_sfx():
    """Create self-extracting executable."""
    if not ZIP_FILE.exists():
        print(f"ERROR: {ZIP_FILE} not found!")
        return False

    # Create extraction script
    script_content = r'''
import os
import sys
import struct
import zipfile
import tempfile
import subprocess
from pathlib import Path

MARKER = b'DEEPREADINGAGENT_SFX_DATA_BEGIN'

def find_zip_offset(exe_path):
    """Find the offset where ZIP data starts in the EXE."""
    with open(exe_path, 'rb') as f:
        data = f.read()

    marker_pos = data.find(MARKER)
    if marker_pos == -1:
        return None

    # After marker, there's a 8-byte length prefix
    length_start = marker_pos + len(MARKER)
    zip_length = struct.unpack('<Q', data[length_start:length_start + 8])[0]
    zip_start = length_start + 8

    return zip_start, zip_length

def get_install_dir():
    """Get installation directory from user."""
    default_dir = os.path.join(os.path.expanduser("~"), "DeepReadingAgent")

    print("=" * 50)
    print("  Deep Reading Agent - 安装程序")
    print("=" * 50)
    print()
    print(f"默认安装目录: {default_dir}")
    user_input = input("按回车使用默认目录，或输入自定义路径: ").strip()

    if user_input:
        install_dir = user_input
    else:
        install_dir = default_dir

    os.makedirs(install_dir, exist_ok=True)
    return install_dir

def main():
    exe_path = sys.executable

    result = find_zip_offset(exe_path)
    if not result:
        print("错误: 无法找到安装数据!")
        input("按回车键退出...")
        return

    zip_start, zip_length = result

    try:
        install_dir = get_install_dir()

        print()
        print("正在解压文件...")

        # Read ZIP data from EXE
        with open(exe_path, 'rb') as f:
            f.seek(zip_start)
            zip_data = f.read(zip_length)

        # Extract to temp first, then move
        temp_dir = tempfile.mkdtemp(prefix="dra_install_")

        with zipfile.ZipFile(temp_dir + ".zip", 'w') as zf_ref:
            pass

        zip_path = Path(temp_dir) / "package.zip"
        zip_path.write_bytes(zip_data)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(install_dir)

        # Cleanup temp
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

        print("✓ 解压完成!")
        print()

        print("=" * 50)
        print("  安装完成!")
        print("=" * 50)
        print()
        print(f"安装目录: {install_dir}")
        print()

        # Ask to launch
        launch = input("是否立即启动 Deep Reading Agent? (Y/n): ").strip().lower()
        if launch in ('', 'y', 'yes'):
            launcher = os.path.join(install_dir, "启动DeepReadingAgent.bat")
            if os.path.exists(launcher):
                subprocess.Popen(launcher, cwd=install_dir, shell=True)
            else:
                print(f"启动文件未找到: {launcher}")

        print()
        input("按回车键退出...")

    except Exception as e:
        print(f"错误: {e}")
        input("按回车键退出...")

if __name__ == "__main__":
    main()
'''

    # Write temp script
    temp_dir = tempfile.mkdtemp()
    script_path = Path(temp_dir) / "sfx_script.py"
    script_path.write_text(script_content, encoding='utf-8')

    # Build with PyInstaller
    print("Building extractor executable...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name=DeepReadingAgent-Setup",
        "--noconfirm",
        "--console",
        str(script_path),
    ]

    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))

    # Append ZIP data to EXE
    exe_path = PROJECT_ROOT / "dist" / "DeepReadingAgent-Setup" / "DeepReadingAgent-Setup.exe"
    if not exe_path.exists():
        exe_path = PROJECT_ROOT / "dist" / "DeepReadingAgent-Setup.exe"

    if not exe_path.exists():
        print("ERROR: Extractor EXE not found!")
        return False

    print("Appending ZIP data...")
    with open(exe_path, 'ab') as f:
        f.write(b'DEEPREADINGAGENT_SFX_DATA_BEGIN')

        zip_data = ZIP_FILE.read_bytes()
        f.write(struct.pack('<Q', len(zip_data)))
        f.write(zip_data)

    # The exe is already at the correct location (dist/DeepReadingAgent-Setup.exe)
    final_exe = PROJECT_ROOT / "dist" / "DeepReadingAgent-Setup.exe"

    if not final_exe.exists():
        print(f"ERROR: Expected EXE not found at {final_exe}")
        return False

    print(f"Self-extracting archive created: {final_exe}")
    print(f"Size: {final_exe.stat().st_size / 1024 / 1024:.1f} MB")
    return True

if __name__ == "__main__":
    import shutil
    create_sfx()

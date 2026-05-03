@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════╗
echo ║   Deep Reading Agent - 安装程序              ║
echo ║   学术论文深度阅读工具                        ║
echo ╚══════════════════════════════════════════════╝
echo.

REM Check if already installed
if exist "%~dp0DeepReadingAgent.exe" (
    echo [!] 检测到 DeepReadingAgent.exe 已存在，可能已经安装。
    echo [!] 如需重新安装，请先删除当前安装目录。
    echo.
    pause
    exit /b 1
)

REM Step 1/3: Extract ZIP
echo [1/3] 正在解压文件...

set "ZIP_FILE="
for %%f in ("%~dp0*.zip") do (
    set "ZIP_FILE=%%f"
)

if not defined ZIP_FILE (
    echo [!] 未找到 ZIP 文件，请确保 install.bat 与 ZIP 文件在同一目录。
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%~dp0' -Force"
if errorlevel 1 (
    echo [!] 解压失败，请检查 ZIP 文件是否完整。
    echo.
    pause
    exit /b 1
)

echo [√] 文件解压完成

REM Step 2/3: Create desktop shortcut
echo [2/3] 正在创建桌面快捷方式...

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; ^
    $shortcut = $ws.CreateShortcut([System.IO.Path]::Combine([System.Environment]::GetFolderPath('Desktop'), 'Deep Reading Agent.lnk')); ^
    $shortcut.TargetPath = '%~dp0启动DeepReadingAgent.bat'; ^
    $shortcut.WorkingDirectory = '%~dp0'; ^
    $shortcut.Description = 'Deep Reading Agent - 学术论文深度阅读工具'; ^
    $shortcut.Save()"

if errorlevel 1 (
    echo [!] 创建快捷方式失败。
    echo.
    pause
    exit /b 1
)

echo [√] 桌面快捷方式已创建

REM Step 3/3: Success
echo [3/3] 安装完成
echo.
echo ╔══════════════════════════════════════════════╗
echo ║            安装成功！                         ║
echo ╚══════════════════════════════════════════════╝
echo.
echo 使用方法：
echo   1. 双击桌面上的 "Deep Reading Agent" 快捷方式启动
echo   2. 或运行安装目录下的 "启动DeepReadingAgent.bat"
echo.
echo 首次运行时，启动脚本会自动创建 .env 配置文件。
echo.

pause

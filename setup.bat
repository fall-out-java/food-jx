@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================
echo   food-jx 一键安装脚本
echo ================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 创建虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境 ...
    python -m venv .venv
) else (
    echo [1/3] 虚拟环境已存在，跳过
)

:: 安装依赖
echo [2/3] 安装 Python 依赖 ...
.venv\Scripts\pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: 安装 Playwright 浏览器
echo [3/3] 安装 Playwright 浏览器 ...
.venv\Scripts\python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [警告] Playwright 浏览器安装失败，可手动执行: .venv\Scripts\python -m playwright install chromium
)

echo.
echo ================================
echo   安装完成！
echo ================================
echo.
echo 下一步：配置 config\config.json
echo   参考 config.example.json 填入你的 API Key
echo.
echo 启动：双击 main.py 或运行 run.bat
echo.
pause

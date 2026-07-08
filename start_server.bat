@echo off
chcp 65001 >nul
cd /d "%~dp0backend"

echo ==========================================
echo   微博音乐演出文案生成器 - 启动中...
echo ==========================================
echo.
echo 后端服务: http://localhost:5050
echo 前端页面: ../index.html
echo.
echo 按 Ctrl+C 停止后端服务
echo ==========================================
echo.

REM 检查依赖
python -c "import flask" 2>nul
if %errorlevel% neq 0 (
    echo [安装依赖...]
    pip install -r requirements.txt
)

REM 启动后端服务器
python server.py

pause

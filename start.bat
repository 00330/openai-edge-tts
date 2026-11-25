@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo   openai-edge-tts  (Edge TTS -> OpenAI API)
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] 虚拟环境不存在，请先运行 setup.bat
    pause
    exit /b 1
)

echo 正在启动...  端口见 .env 中的 PORT
echo 停止服务按 Ctrl+C
echo.

cd app
..\.venv\Scripts\python.exe server.py

echo.
echo 服务已退出。
pause

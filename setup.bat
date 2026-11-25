@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo   环境安装 / 修复
echo ==========================================
echo.

set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe

if not exist "%PY%" (
    echo [ERROR] 找不到 Python: %PY%
    echo 请修改本文件里的 PY 变量为你的 python.exe 路径
    pause
    exit /b 1
)

echo [1/3] 创建虚拟环境 .venv
if not exist ".venv\Scripts\python.exe" (
    "%PY%" -m venv .venv
) else (
    echo     已存在，跳过
)

echo [2/3] 安装依赖
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo [3/3] 生成 .env（若不存在）
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo     已从 .env.example 复制，请编辑 API_KEY 和 PORT
) else (
    echo     .env 已存在，跳过
)

echo.
echo 完成。运行 start.bat 启动服务。
pause

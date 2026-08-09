@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   教学过程智能分析与预警平台
echo ============================================================
echo.

set ADMIN_USERNAME = "admin"
set ADMIN_PASSWORD_HASH = "JrFFjb1jk0mzUOZKmf2R-XYphgJmzFPAkgQuwtQ_mlVUob9DWfN-oaxfjrUX84ZL"
:: $env:FLASK_ENV = "prod"
:: $env:SECRET_KEY = "粘贴生成的随机密钥"
:: $env:SESSION_COOKIE_SECURE = "true"
set MYSQL_USER = "root"

:: 必需的登录凭据必须在任何数据库访问之前检查。
if not defined ADMIN_USERNAME (
    echo [错误] 缺少 ADMIN_USERNAME。请先设置管理员用户名。
    exit /b 2
)
if not defined ADMIN_PASSWORD_HASH (
    echo [错误] 缺少 ADMIN_PASSWORD_HASH。请使用 Werkzeug 生成密码哈希后设置。
    exit /b 2
)
if not defined MYSQL_USER (
    echo [错误] 缺少 MYSQL_USER。请设置专用数据库用户名。
    exit /b 2
)
if not defined MYSQL_PASSWORD (
    echo [错误] 缺少 MYSQL_PASSWORD。请设置数据库密码。
    exit /b 2
)

:: 生产环境必须提供持久、高熵密钥；HTTPS 会话 Cookie 强制仅通过安全连接发送。
if /I "%FLASK_ENV%"=="prod" (
    if not defined SECRET_KEY (
        echo [错误] 生产环境缺少 SECRET_KEY。请设置独立的高熵随机密钥。
        exit /b 2
    )
    set "SESSION_COOKIE_SECURE=true"
)

set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PYTHON_CMD=venv\Scripts\python.exe"

"%PYTHON_CMD%" -c "from config import validate_database_environment; validate_database_environment()" 2>nul
if errorlevel 1 (
    echo [错误] MYSQL_USER 和 MYSQL_PASSWORD 必须是非空白值，MYSQL_PORT 必须有效。
    exit /b 2
)

echo [1/3] 检查 MySQL 连接...
"%PYTHON_CMD%" -c "import pymysql; from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD; pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD, charset='utf8mb4').close(); print('      MySQL 连接正常')"
if errorlevel 1 (
    echo [错误] MySQL 连接失败。请检查 MYSQL_HOST、MYSQL_PORT、MYSQL_USER 和 MYSQL_PASSWORD。
    exit /b 1
)

echo [2/3] 创建缺失的数据库表（不会删除或重建数据库）...
"%PYTHON_CMD%" init_database.py --tables-only
if errorlevel 1 (
    echo [错误] 数据库表初始化失败。
    exit /b 1
)

echo [3/3] 启动 Web 服务...
echo       服务地址: http://localhost:5000
if /I "%FLASK_ENV%"=="prod" (
    echo       使用 Waitress 生产 WSGI 服务器
    "%PYTHON_CMD%" -m waitress --listen=0.0.0.0:5000 app:app
) else (
    echo       使用 Flask 开发服务器
    "%PYTHON_CMD%" app.py
)
exit /b %errorlevel%

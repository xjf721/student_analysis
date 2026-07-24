@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
::  教学过程智能分析与预警平台 - 一键启动脚本
::  功能：激活虚拟环境 → 检查数据库 → 初始化 → 启动服务
:: ============================================================

title 学生画像分析平台 - 启动中...

echo.
echo ============================================================
echo   教学过程智能分析与预警平台
echo ============================================================
echo.

:: ---- 1. 定位虚拟环境 ----
set VENV_DIR=venv
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [1/4] 激活虚拟环境...
    call "%VENV_DIR%\Scripts\activate.bat"
    echo       虚拟环境已激活: %VENV_DIR%
) else (
    echo [1/4] 未找到虚拟环境，使用系统 Python
    echo       提示: 运行 python -m venv venv 可创建虚拟环境
)

:: ---- 2. 检查 MySQL 连接 ----
echo.
echo [2/4] 检查 MySQL 数据库连接...
python -c "import pymysql; pymysql.connect(host='127.0.0.1', port=3306, user='root', password='Root@123456', charset='utf8mb4').close(); print('       MySQL 连接正常')" 2>nul
if %errorlevel% neq 0 (
    echo       [警告] MySQL 连接失败，请确保 MySQL 服务已启动
    echo       Docker 用户请运行: docker start mysql-container
    echo.
    choice /c yn /m "是否继续启动（跳过数据库检查）"
    if errorlevel 2 exit /b 1
) else (
    :: ---- 3. 初始化数据库（如果需要） ----
    echo.
    echo [3/4] 初始化数据库表结构...
    python init_database.py --tables-only 2>nul
    if %errorlevel% equ 0 (
        echo       数据库表结构就绪
    ) else (
        echo       表结构可能已存在，跳过
    )
)

:: ---- 4. 启动 Flask 开发服务器 ----
echo.
echo [4/4] 启动 Flask 开发服务器...
echo.
echo ============================================================
echo   服务地址: http://localhost:5000
echo   按 Ctrl+C 停止服务
echo ============================================================
echo.

python app.py

:: 如果异常退出，暂停以便查看错误信息
if %errorlevel% neq 0 (
    echo.
    echo [错误] 服务异常退出，错误码: %errorlevel%
    pause
)

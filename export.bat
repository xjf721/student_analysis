@echo off
setlocal

set "PROJECT_DIR=%~dp0"
pushd "%PROJECT_DIR%" >nul || (
    echo [ERROR] Cannot enter project directory: %PROJECT_DIR%
    exit /b 1
)

set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE where python >nul 2>nul && set "PYTHON_EXE=python"
if not defined PYTHON_EXE where py >nul 2>nul && (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
)

if not defined PYTHON_EXE (
    echo [ERROR] Python 3 was not found. Install Python or create .venv first.
    popd >nul
    exit /b 1
)

"%PYTHON_EXE%" %PYTHON_ARGS% scripts\export_release.py %*
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
exit /b %EXIT_CODE%

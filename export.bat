@echo off
setlocal enabledelayedexpansion

:: Student Analysis Platform - Export Script
:: Double-click to run, generates timestamped .zip in export\

title Exporting package...

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "EXPORT_DIR=%PROJECT_DIR%\export"
set "TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"
set "OUTPUT_FILE=%EXPORT_DIR%\student_analysis_%TIMESTAMP%.zip"

echo.
echo ============================================================
echo   Export Package
echo ============================================================
echo.

if not exist "%EXPORT_DIR%" mkdir "%EXPORT_DIR%"

echo [1/3] Cleaning temp files...
for /r "%PROJECT_DIR%" %%f in (*.pyc) do del /q "%%f" 2>nul
for /d /r "%PROJECT_DIR%" %%d in (__pycache__) do if exist "%%d" rd /s /q "%%d" 2>nul
echo       Done

echo.
echo [2/3] Packaging...

set "PS_FILE=%TEMP%\stu_export.ps1"

(
echo $source   = '%PROJECT_DIR%'
echo $dest     = '%OUTPUT_FILE%'
echo $excludeDirs   = @('__pycache__', 'venv', '.venv', '.git', '.idea', '.vscode', 'uploads', 'logs', 'export', 'new-datas', '---bak---', 'dist', 'build', 'node_modules')
echo $excludePatterns = @('*.pyc', '*.zip', '*.tar.gz', '*.rar', '*.7z', '*.log', 'Thumbs.db', 'desktop.ini')
echo.
echo function ShouldInclude($item^) {
echo     $rel = $item.FullName.Substring($source.Length + 1^)
echo     foreach ($d in $excludeDirs^) {
echo         if ($rel -match ('(^|\\^)' + [regex]::Escape($d^) + '($|\\^)'^)^) { return $false }
echo     }
echo     foreach ($p in $excludePatterns^) {
echo         if ($item.Name -like $p^) { return $false }
echo     }
echo     return $true
echo }
echo.
echo $all     = Get-ChildItem -Path $source -Recurse -Force
echo $items   = $all ^| Where-Object { ShouldInclude $_ }
echo Write-Host ('       Scanned ' + $all.Count + ' files, packing ' + $items.Count + ' ...'^)
echo.
echo $tmpDir  = Join-Path ([System.IO.Path]::GetTempPath(^)^) ('stu_export_' + [System.Guid]::NewGuid(^).ToString(^).Substring(0, 8^)^)
echo New-Item -ItemType Directory -Path $tmpDir -Force ^| Out-Null
echo foreach ($item in $items^) {
echo     $relPath   = $item.FullName.Substring($source.Length + 1^)
echo     $target    = Join-Path $tmpDir $relPath
echo     $targetDir = Split-Path $target -Parent
echo     if (-not (Test-Path $targetDir^)^) { New-Item -ItemType Directory -Path $targetDir -Force ^| Out-Null }
echo     Copy-Item -Path $item.FullName -Destination $target -Force
echo }
echo Compress-Archive -Path (Join-Path $tmpDir '*'^) -DestinationPath $dest -CompressionLevel Optimal -Force
echo Remove-Item -Path $tmpDir -Recurse -Force
echo Write-Host ('       Done: ' + $dest^)
) > "%PS_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_FILE%"
del "%PS_FILE%" 2>nul

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Packaging failed
    pause
    exit /b 1
)

echo.
echo [3/3] Complete
echo.
echo ============================================================
echo   Package: %OUTPUT_FILE%
echo ============================================================
echo.

powershell -NoProfile -Command "[math]::Round((Get-Item '%OUTPUT_FILE%').Length / 1KB, 1)" > "%TEMP%\filesize.tmp" 2>nul
set /p FILESIZE=<"%TEMP%\filesize.tmp"
del "%TEMP%\filesize.tmp" 2>nul

echo   Size: %FILESIZE% KB

explorer "%EXPORT_DIR%"

echo.
pause

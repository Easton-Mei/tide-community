@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 tide.py web
) else (
  python tide.py web
)
echo.
echo 潮汐已停止。如提示找不到 Python，请安装 Python 3.11 或更新版本。
pause

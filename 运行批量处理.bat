@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  py mfl_analysis.py
) else (
  python mfl_analysis.py
)
pause

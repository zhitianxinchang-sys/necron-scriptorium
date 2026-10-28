@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON="
where python >nul 2>nul
if not errorlevel 1 set "PYTHON=python"
if not defined PYTHON (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON=py -3"
)
if not defined PYTHON (
  echo 没有找到 Python，所以太空死灵作家助手暂时打不开。
  echo 请先安装 Python 3，安装时勾选 Add Python to PATH，再双击本文件。
  pause
  exit /b 1
)
%PYTHON% app.py
if errorlevel 1 (
  echo.
  echo 太空死灵作家助手没有正常启动。请把这个窗口拍下来发给帮助你安装的人。
  pause
)

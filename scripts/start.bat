@echo off
title Stock Supply Chain Dashboard
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d %~dp0..
conda run --no-capture-output -n env_reactAgent python scripts\launcher.py
pause

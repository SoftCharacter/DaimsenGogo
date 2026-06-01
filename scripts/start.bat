@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Stock Supply Chain Dashboard
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
set "ROOT=%CD%"
popd
set "BACKEND_DIR=%ROOT%\backend"
set "FRONTEND_DIR=%ROOT%\frontend"
set "VENV_DIR=%ROOT%\.venv"
set "CONDA_ENV_NAME=env_reactAgent"
set "CONDA_BASE="
set "PYTHON_BIN="
set "NEED_BACKEND_DEPS_INSTALL=0"

echo ========================================
echo   Stock Supply Chain Dashboard
echo ========================================
echo.
echo [prepare] Checking runtime environment...
echo.

call :ensure_python || goto :fail
call :install_backend_deps || goto :fail
call :install_frontend_deps || goto :fail

echo.
echo [start] Launching backend and frontend...
echo.
cd /d "%ROOT%"
call "%PYTHON_BIN%" scripts\launcher.py
if errorlevel 1 goto :fail

goto :end

:ensure_python
where conda >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%I in ('call conda info --base') do set "CONDA_BASE=%%I"
    if exist "%CONDA_BASE%\envs\%CONDA_ENV_NAME%\python.exe" (
        set "PYTHON_BIN=%CONDA_BASE%\envs\%CONDA_ENV_NAME%\python.exe"
        exit /b 0
    )
    echo [env] Creating conda env %CONDA_ENV_NAME%...
    call conda create -n %CONDA_ENV_NAME% python=3.11 -y
    if errorlevel 1 exit /b 1
    set "NEED_BACKEND_DEPS_INSTALL=1"
    if not defined CONDA_BASE (
        for /f "delims=" %%I in ('call conda info --base') do set "CONDA_BASE=%%I"
    )
    set "PYTHON_BIN=!CONDA_BASE!\envs\!CONDA_ENV_NAME!\python.exe"
    if not exist "!PYTHON_BIN!" exit /b 1
    exit /b 0
)

if exist "%VENV_DIR%\Scripts\python.exe" (
    set "PYTHON_BIN=%VENV_DIR%\Scripts\python.exe"
    exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
    echo [env] Creating local Python virtual environment .venv ...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 exit /b 1
    set "NEED_BACKEND_DEPS_INSTALL=1"
    set "PYTHON_BIN=%VENV_DIR%\Scripts\python.exe"
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    echo [env] Creating local Python virtual environment .venv ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 exit /b 1
    set "NEED_BACKEND_DEPS_INSTALL=1"
    set "PYTHON_BIN=%VENV_DIR%\Scripts\python.exe"
    exit /b 0
)

echo [error] conda, py, or python was not found. Please install Python or Anaconda first.
exit /b 1

:install_backend_deps
if not "%NEED_BACKEND_DEPS_INSTALL%"=="1" (
    echo [deps] Existing Python environment found, skipping backend dependency install.
    exit /b 0
)
echo [deps] Installing backend Python dependencies...
call "%PYTHON_BIN%" -m pip install -r "%BACKEND_DIR%\requirements.txt"
exit /b !errorlevel!

:install_frontend_deps
if not exist "%FRONTEND_DIR%\node_modules" (
    where npm >nul 2>nul
    if errorlevel 1 (
        echo [error] npm was not found. Please install Node.js first.
        exit /b 1
    )
    echo [deps] Installing frontend dependencies...
    pushd "%FRONTEND_DIR%"
    if exist package-lock.json (
        call npm ci
    ) else (
        call npm install
    )
    set "NPM_STATUS=!errorlevel!"
    popd
    if not "!NPM_STATUS!"=="0" exit /b !NPM_STATUS!
)
exit /b 0

:fail
echo.
echo Startup failed. Please check the errors above.
pause
exit /b 1

:end
echo.
pause
endlocal

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
set "CONDA_ENV_NAME=env_reactAgent"
set "DEPS_DIR=%ROOT%\.runlogs\deps"
set "BACKEND_DEPS_MARKER=%DEPS_DIR%\backend.requirements.sha"
set "FRONTEND_DEPS_MARKER=%DEPS_DIR%\frontend.package.sha"
set "CONDA_BASE="
set "PYTHON_BIN="

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
if errorlevel 1 (
    echo [error] conda was not found. Please install Anaconda first.
    exit /b 1
)

for /f "delims=" %%I in ('call conda info --base') do set "CONDA_BASE=%%I"
set "PYTHON_BIN=%CONDA_BASE%\envs\%CONDA_ENV_NAME%\python.exe"

if exist "%PYTHON_BIN%" exit /b 0

echo [env] Creating conda env %CONDA_ENV_NAME%...
call conda create -n %CONDA_ENV_NAME% python=3.11 -y
if errorlevel 1 exit /b 1

if not exist "%PYTHON_BIN%" (
    echo [error] Failed to find Python in conda env %CONDA_ENV_NAME%.
    exit /b 1
)
exit /b 0

:install_backend_deps
call :file_hash "%BACKEND_DIR%\requirements.txt" BACKEND_DEPS_HASH || exit /b 1
set "INSTALLED_BACKEND_DEPS_HASH="
if exist "%BACKEND_DEPS_MARKER%" set /p INSTALLED_BACKEND_DEPS_HASH=<"%BACKEND_DEPS_MARKER%"
if "!INSTALLED_BACKEND_DEPS_HASH!"=="!BACKEND_DEPS_HASH!" (
    echo [deps] Backend dependencies unchanged, skipping install.
    exit /b 0
)
echo [deps] Installing or updating backend Python dependencies...
call "%PYTHON_BIN%" -m pip install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 exit /b !errorlevel!
if not exist "%DEPS_DIR%" mkdir "%DEPS_DIR%"
> "%BACKEND_DEPS_MARKER%" echo(!BACKEND_DEPS_HASH!
exit /b 0

:install_frontend_deps
where npm >nul 2>nul
if errorlevel 1 (
    echo [error] npm was not found. Please install Node.js first.
    exit /b 1
)
call :file_hash "%FRONTEND_DIR%\package.json" FRONTEND_PACKAGE_HASH || exit /b 1
set "FRONTEND_DEPS_HASH=!FRONTEND_PACKAGE_HASH!"
if exist "%FRONTEND_DIR%\package-lock.json" (
    call :file_hash "%FRONTEND_DIR%\package-lock.json" FRONTEND_LOCK_HASH || exit /b 1
    set "FRONTEND_DEPS_HASH=!FRONTEND_PACKAGE_HASH!-!FRONTEND_LOCK_HASH!"
)
set "INSTALLED_FRONTEND_DEPS_HASH="
if exist "%FRONTEND_DEPS_MARKER%" set /p INSTALLED_FRONTEND_DEPS_HASH=<"%FRONTEND_DEPS_MARKER%"
if exist "%FRONTEND_DIR%\node_modules" if "!INSTALLED_FRONTEND_DEPS_HASH!"=="!FRONTEND_DEPS_HASH!" (
    echo [deps] Frontend dependencies unchanged, skipping install.
    exit /b 0
)
echo [deps] Installing or updating frontend dependencies...
pushd "%FRONTEND_DIR%"
if exist package-lock.json (
    call npm ci
) else (
    call npm install
)
set "NPM_STATUS=!errorlevel!"
popd
if not "!NPM_STATUS!"=="0" exit /b !NPM_STATUS!
if not exist "%DEPS_DIR%" mkdir "%DEPS_DIR%"
> "%FRONTEND_DEPS_MARKER%" echo(!FRONTEND_DEPS_HASH!
exit /b 0

:file_hash
set "%~2="
for /f "skip=1 tokens=1" %%H in ('certutil -hashfile "%~1" SHA256') do (
    if not defined %~2 set "%~2=%%H"
)
if not defined %~2 (
    echo [error] Failed to calculate file hash: %~1
    exit /b 1
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

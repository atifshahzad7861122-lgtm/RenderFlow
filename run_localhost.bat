@echo off
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
title RenderFlow by AI With Atif

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo   [ERROR] Python is not installed or not found on PATH.
    echo   Please install Python 3.10+ to run RenderFlow.
    echo ============================================================
    echo.
    pause
    exit /b 1
)

python web\server.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Server exited with code %ERRORLEVEL%.
    pause
)

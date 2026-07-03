@echo off
setlocal EnableDelayedExpansion

chcp 65001 >nul
title SentryVision AI

rem Always run from the folder this script lives in, regardless of where
rem it was double-clicked from.
cd /d "%~dp0"

echo ============================================
echo   SentryVision AI - Local Launcher
echo ============================================
echo.

where uv >nul 2>nul
if !errorlevel! neq 0 (
    echo [1/4] "uv" not found - installing it now...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if !errorlevel! neq 0 (
        echo.
        echo Could not install uv automatically. Please install it manually from:
        echo   https://docs.astral.sh/uv/getting-started/installation/
        echo then re-run this script.
        pause
        exit /b 1
    )
    rem The installer updates the registry PATH for future sessions, but this
    rem window needs it right now too.
    set "PATH=!USERPROFILE!\.local\bin;!PATH!"
    echo       uv installed.
) else (
    echo [1/4] uv found.
)

echo.
echo [2/4] Checking for updates...
if not exist ".git" (
    echo       Not a git clone - skipping update check.
) else (
    where git >nul 2>nul
    if !errorlevel! neq 0 (
        echo       git not found - skipping update check.
        echo       Install git from https://git-scm.com/downloads to enable auto-updates.
    ) else (
        git pull --ff-only
        if !errorlevel! neq 0 (
            echo.
            echo       Could not fast-forward to the latest version ^(no connection,
            echo       local changes, or diverged history^). Continuing with the
            echo       code currently on disk - run "git pull" manually to investigate.
        ) else (
            echo       Up to date.
        )
    )
)

echo.
echo [3/4] Installing/updating dependencies (first run may take a few minutes)...
uv sync
if !errorlevel! neq 0 (
    echo.
    echo Dependency installation failed - see the error above.
    pause
    exit /b 1
)

echo.
echo [4/4] Starting SentryVision AI...
echo       Opening at http://localhost:8501 - your browser should launch automatically.
echo       Leave this window open while using the app. Press Ctrl+C here to stop it.
echo.

uv run streamlit run streamlit_app.py

echo.
echo SentryVision AI has stopped.
pause

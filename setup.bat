@echo off
cd /d "%~dp0"
title Intelligence Screening — Setup

echo.
echo  Intelligence Screening — First-time Setup
echo  ==========================================
echo.

:: Check Python 3.12
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.12 not found.
    echo  Download it from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo  [1/3] Installing dependencies...
py -3.12 -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo         Done.
echo.

:: Create .env if it doesn't exist (first run)
if not exist .env (
    echo  [2/3] Creating .env from template...
    copy .env.example .env >nul
) else (
    echo  [2/3] .env already exists — skipping.
)
echo.

echo  [3/3] Seeding question bank...
py -3.12 seed_questions.py
echo.

echo  ==========================================
echo.
echo  NEXT STEPS — edit .env and fill in:
echo.
echo    DISCORD_TOKEN     — bot token from discord.com/developers
echo    DISCORD_GUILD_ID  — right-click your server, Copy Server ID
echo    API_SECRET_KEY    — run: py -c "import secrets; print(secrets.token_hex(32))"
echo    ADMIN_PASSWORD    — password for the web UI at http://127.0.0.1:8000
echo    JWT_SECRET        — run: py -c "import secrets; print(secrets.token_hex(32))"
echo.
echo  Then start everything with:
echo    py launcher.py
echo.
pause

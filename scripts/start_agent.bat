@echo off
REM AI Trader Agent ko shuru karta hai: Telegram bot + live loop, do alag windows mein.
REM Windows Task Scheduler se session se pehle chalayein (docs/LIVE.md dekhein).
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
start "AI Trader - Telegram bot" cmd /k python -m trader_agent.notifier.telegram_bot
start "AI Trader - Live" cmd /k python scripts\run_live.py %*

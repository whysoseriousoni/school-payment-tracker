@echo off
REM Weekly backup for Windows Task Scheduler (runs only if the last weekly backup is 7+ days old).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m backup_and_restore --if-due >> logs\scheduled_backup.log 2>&1

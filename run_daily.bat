@echo off
REM Launcher for Windows Task Scheduler. Activates the project's
REM virtual environment and runs one daily pipeline pass.
REM
REM This file is intentionally simple -- it does not itself implement
REM logging (Module 6 will add proper logging inside the Python code).
REM The >> redirect below just captures stdout/stderr to a plain text
REM file so a run can be inspected after the fact, until Module 6
REM replaces this with real logging.

cd /d "%~dp0"

if not exist logs mkdir logs

call .venv\Scripts\activate.bat
python main.py >> logs\run_daily.log 2>&1
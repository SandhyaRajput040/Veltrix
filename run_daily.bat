@echo off
REM Launcher for Windows Task Scheduler. Activates the project's
REM virtual environment and runs one daily pipeline pass.
REM
REM As of Module 6, main.py does its own proper logging to
REM logs\veltrix.log (a rotating file) and sends an email summary --
REM this batch file's redirect below is now just a safety net that
REM catches anything that goes wrong BEFORE Python's own logging can
REM start (e.g. a broken .venv, a missing python.exe). Check
REM logs\veltrix.log first; only check logs\run_daily_raw_output.log
REM if veltrix.log is empty/missing entirely.

cd /d "%~dp0"

if not exist logs mkdir logs

call .venv\Scripts\activate.bat
python main.py >> logs\run_daily_raw_output.log 2>&1
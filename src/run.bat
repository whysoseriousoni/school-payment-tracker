@echo off
REM Start the School Fee Tracker on Windows. First run creates .venv and installs packages.
cd /d "%~dp0"
if not exist .venv (
    py -3.10 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
streamlit run app.py

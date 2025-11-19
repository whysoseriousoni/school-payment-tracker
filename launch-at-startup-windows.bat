@echo off
REM Change to the directory containing your Streamlit app
cd "S:\git_repo\school-payment-tracker" 

REM Activate your Python environment if you're using one (e.g., Anaconda)
call .school/Scripts/activate.bat

REM Run your Streamlit app
streamlit run main.py --server.port 8505 --server.enableCORS false --server.enableXsrfProtection false
@echo off
cd /d "%~dp0.."
echo Starting Job Bot UI...
python -m streamlit run app.py --server.headless false
pause

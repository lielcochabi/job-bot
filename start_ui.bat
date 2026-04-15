@echo off
cd /d "%~dp0"
echo Starting Job Bot UI...
C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe -m streamlit run app.py --server.headless false
pause

@echo off
:: Creates a Windows Task Scheduler task that runs the job bot daily at 8:00 AM
:: Run this file ONCE as Administrator to set it up

set TASK_NAME=JobBotDailyRun
set BOT_DIR=%~dp0..
set PYTHON=python
set SCRIPT=%BOT_DIR%\main.py

echo Setting up daily Job Bot task at 8:00 AM...

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\" run --auto" ^
  /sc DAILY ^
  /st 08:00 ^
  /sd TODAY ^
  /rl HIGHEST ^
  /f ^
  /it

if %ERRORLEVEL% == 0 (
    echo.
    echo [OK] Task "%TASK_NAME%" created successfully!
    echo      The bot will run every day at 8:00 AM automatically.
    echo.
    echo To change the time:  schtasks /change /tn "%TASK_NAME%" /st HH:MM
    echo To run it now:       schtasks /run /tn "%TASK_NAME%"
    echo To delete it:        schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo [ERROR] Failed to create task. Try running this file as Administrator.
    echo Right-click schedule_daily.bat and choose "Run as administrator"
)

pause

@echo off
setlocal

set PROFILE=%1
if "%PROFILE%"=="" set PROFILE=LOW

set DURATION=%2
if "%DURATION%"=="" set DURATION=60

if /I "%PROFILE%"=="HIGH" (
    set USERS=100
    set SPAWN=10
) else if /I "%PROFILE%"=="MEDIUM" (
    set USERS=50
    set SPAWN=5
) else (
    set PROFILE=LOW
    set USERS=10
    set SPAWN=2
)

echo Starting %PROFILE% workload simulation for %DURATION% seconds (%USERS% users)...
set WORKLOAD_PROFILE=%PROFILE%

python -m locust -f client/locustfile.py --headless -u %USERS% -r %SPAWN% -t %DURATION%s --host http://localhost:8000 --html client/report_%PROFILE%.html

echo Simulation complete. Report saved to client/report_%PROFILE%.html

@echo off
color 0A
echo ===================================================
echo 🦅 PHOENIX V6.4 - CLOUD SYNC PROTOCOL
echo ===================================================

:: 1. Activate the Iron Shield
call venv\Scripts\activate

:: 2. Freeze current dependencies
echo [1/3] Updating requirements.txt...
pip freeze > requirements.txt

:: 3. Stage all files
echo [2/3] Staging files for Git...
git add .

:: 4. Get the commit message
echo.
set /p msg="Enter update note (or press Enter for Auto-Timestamp): "
if "%msg%"=="" set msg=Automated Sync: %date% @ %time%

:: 5. Commit and Push
echo.
echo [3/3] Pushing to GitHub...
git commit -m "%msg%"
git push origin main

echo ===================================================
echo ✅ ARCHITECTURE SUCCESSFULLY IMMORTALIZED
echo ===================================================
pause
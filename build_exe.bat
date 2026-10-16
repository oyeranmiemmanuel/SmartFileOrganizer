@echo off
setlocal
cd /d "%~dp0"

rem Builds dist\SmartFileOrganizer.exe (one file). Add "skip-tests" to skip the test run.
set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo The .venv folder was not found. Create it first:
    echo     python -m venv .venv
    goto :fail
)

echo === Installing build tools ===
"%PY%" -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail

if not exist "assets\icon.ico" (
    echo === Creating the application icon ===
    "%PY%" tools\make_icon.py
    if errorlevel 1 goto :fail
)

if /i "%~1"=="skip-tests" goto :build
echo === Running the tests ===
"%PY%" -m pytest -q
if errorlevel 1 goto :fail

:build
echo === Building dist\SmartFileOrganizer.exe ===
"%PY%" -m PyInstaller --noconfirm --clean SmartFileOrganizer.spec
if errorlevel 1 goto :fail

echo.
echo Build finished: dist\SmartFileOrganizer.exe
echo Test it with docs\TESTING_CHECKLIST.md before sharing it.
pause
exit /b 0

:fail
echo.
echo The build stopped because of an error. See the messages above and docs\PACKAGING.md.
pause
exit /b 1
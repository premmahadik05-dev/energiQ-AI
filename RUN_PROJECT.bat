@echo off
setlocal EnableExtensions DisableDelayedExpansion
title EnergiQ AI
rem ===========================================================================================================
rem  RUN_PROJECT.bat - starts EnergiQ AI with one double-click.
rem
rem  This file only finds a suitable Python and hands over to run_energiq.py, which does the real work:
rem  checks Python and Node.js, creates .venv, installs packages (only when they changed), prepares the
rem  database, starts the backend and the web app, waits until both really answer, then opens the browser.
rem  Extra options are passed through, for example:  RUN_PROJECT.bat --no-browser
rem
rem  No administrator rights are needed. Everything is written inside this folder.
rem  Written without ( ) blocks on purpose: a folder name such as "Programs (x86)" must not break it.
rem ===========================================================================================================

cd /d "%~dp0" >nul 2>nul
if errorlevel 1 goto :badfolder

echo.
echo  ================================================================
echo    EnergiQ AI - one-click start
echo  ================================================================

if not exist "%~dp0run_energiq.py" goto :notextracted

rem ---- find a supported Python (3.11, 3.12 or 3.13) ----
set "PY="
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3.11"
if defined PY goto :havepython
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3.12"
if defined PY goto :havepython
py -3.13 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3.13"
if defined PY goto :havepython
python -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :havepython
goto :nopython

:havepython
rem UTF-8 for Python and the tools it starts, so odd characters in file names or messages cannot crash a step.
set "PYTHONUTF8=1"
%PY% "%~dp0run_energiq.py" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto :endedok
if "%RC%"=="130" goto :cancelled
goto :endederror

:endedok
echo  EnergiQ AI is not running in this window any more.
echo.
echo    - To start it again, double-click RUN_PROJECT.bat.
echo    - If the message above says a copy is already running, use that copy,
echo      or double-click STOP_PROJECT.bat and then RUN_PROJECT.bat.
goto :done

:cancelled
echo  Cancelled. Double-click RUN_PROJECT.bat again; setup continues where it stopped.
goto :done

:endederror
echo  EnergiQ AI could not start, or stopped with an error ^(code %RC%^).
echo.
echo  If you stopped it yourself with STOP_PROJECT.bat during the first-time setup,
echo  this is expected and nothing is wrong.
echo.
echo    1. Read the message above: it says what failed and what to do.
echo    2. Run CHECK_ENVIRONMENT.bat to see what is missing on this computer.
echo    3. The full log is in this folder:
echo         "%~dp0.energiq-run"
echo       ^(launcher.log, backend.log, frontend.log^). It never contains passwords.
echo    4. START_HERE.md lists the common problems and their fixes.
goto :done

:nopython
echo.
echo  Python 3.11, 3.12 or 3.13 was not found on this computer.
python --version >nul 2>nul
if not errorlevel 1 echo  Another Python version is installed, but EnergiQ AI needs 3.11, 3.12 or 3.13:
if not errorlevel 1 python --version
echo.
echo    1. Download Python 3.11 from https://www.python.org/downloads/
echo    2. In the installer, tick "Add python.exe to PATH", then click Install.
echo    3. Double-click RUN_PROJECT.bat again.
echo.
echo  If Windows opened the Microsoft Store when you tried Python, install it from
echo  python.org as above instead of from the Store.
goto :doneerror

:notextracted
echo.
echo  run_energiq.py was not found next to this file.
echo  If you opened this from inside the ZIP, close it, right-click the ZIP,
echo  choose "Extract All", and run RUN_PROJECT.bat from the extracted folder.
goto :doneerror

:badfolder
echo.
echo  This folder cannot be used as a working folder. That usually means it is on a
echo  network location ^(\\server\share^). Copy the whole EnergiQ-AI folder to a
echo  local drive, for example C:\EnergiQ, and run RUN_PROJECT.bat from there.
goto :doneerror

:doneerror
set "RC=1"
:done
echo.
rem Set ENERGIQ_NO_PAUSE=1 to skip the final pause (for automated runs only).
if defined ENERGIQ_NO_PAUSE exit /b %RC%
pause
exit /b %RC%

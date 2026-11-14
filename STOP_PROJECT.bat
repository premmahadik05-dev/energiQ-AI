@echo off
setlocal EnableExtensions DisableDelayedExpansion
title EnergiQ AI - Stop
rem ===========================================================================================================
rem  STOP_PROJECT.bat - safely stops the EnergiQ AI that RUN_PROJECT.bat started.
rem
rem  It reads the record of the running copy (.energiq-run\state.json) and ends exactly the backend, the web
rem  app and the launcher that were started from this folder. It never ends a process just because of its
rem  name, and it leaves alone a recorded process number that no longer answers as EnergiQ.
rem  No administrator rights are needed. Your data in data\energiq.db is kept.
rem ===========================================================================================================

cd /d "%~dp0" >nul 2>nul
if errorlevel 1 goto :badfolder

echo.
echo  ================================================================
echo    EnergiQ AI - stop
echo  ================================================================
echo.

if not exist "%~dp0run_energiq.py" goto :notextracted

rem Stopping needs no particular Python version, so any Python 3 will do.
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
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :havepython
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :havepython
goto :nopython

:havepython
set "PYTHONUTF8=1"
%PY% "%~dp0run_energiq.py" --stop
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto :done
echo  Something could not be stopped. Close the EnergiQ AI window, or end the
echo  listed processes in Task Manager ^(Ctrl+Shift+Esc^).
goto :done

:nopython
echo  Python was not found, so the running copy cannot be looked up.
echo  Click into the EnergiQ AI window and press Ctrl+C, or simply close that window.
goto :doneerror

:notextracted
echo  run_energiq.py was not found next to this file.
echo  Run STOP_PROJECT.bat from the extracted EnergiQ-AI folder.
goto :doneerror

:badfolder
echo.
echo  This folder cannot be used as a working folder ^(a network location?^).
echo  Run STOP_PROJECT.bat from the local EnergiQ-AI folder.
goto :doneerror

:doneerror
set "RC=1"
:done
echo.
rem Set ENERGIQ_NO_PAUSE=1 to skip the final pause (for automated runs only).
if defined ENERGIQ_NO_PAUSE exit /b %RC%
pause
exit /b %RC%

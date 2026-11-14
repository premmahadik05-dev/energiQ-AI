@echo off
setlocal EnableExtensions DisableDelayedExpansion
title EnergiQ AI - Check environment
rem ===========================================================================================================
rem  CHECK_ENVIRONMENT.bat - looks at this computer and reports what is present and what is missing.
rem  It installs nothing, changes nothing and needs no administrator rights.
rem ===========================================================================================================

cd /d "%~dp0" >nul 2>nul
if errorlevel 1 goto :badfolder

echo.
echo  ================================================================
echo    EnergiQ AI - check this computer ^(nothing is installed or changed^)
echo  ================================================================
echo.

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
if not exist "%~dp0run_energiq.py" goto :notextracted
set "PYTHONUTF8=1"
%PY% "%~dp0run_energiq.py" --doctor
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto :fixthem
echo  Everything needed is present. Double-click RUN_PROJECT.bat to start EnergiQ AI.
goto :done

:fixthem
echo  Fix the items marked MISSING, then run this check again. START_HERE.md explains each one.
goto :done

:nopython
echo  [MISSING] Python 3.11, 3.12 or 3.13
echo            Download Python 3.11 from https://www.python.org/downloads/
echo            and tick "Add python.exe to PATH" in the installer.
python --version >nul 2>nul
if not errorlevel 1 echo  [NOTE   ] Another Python is installed, but it is not 3.11, 3.12 or 3.13:
if not errorlevel 1 python --version
where node >nul 2>nul
if errorlevel 1 goto :nonode
for /f "delims=" %%N in ('node --version') do echo  [FOUND  ] Node.js %%N ^(needs 20.19 or newer^)
goto :checknpm
:nonode
echo  [MISSING] Node.js - install the LTS version from https://nodejs.org/
:checknpm
where npm >nul 2>nul
if errorlevel 1 echo  [MISSING] npm - it comes with Node.js
if not errorlevel 1 echo  [FOUND  ] npm
echo.
echo  Fix the items marked MISSING, then run this check again.
goto :doneerror

:notextracted
echo  run_energiq.py was not found next to this file. Run this from the extracted EnergiQ-AI folder.
goto :doneerror

:badfolder
echo.
echo  This folder cannot be used as a working folder ^(a network location?^).
echo  Copy the EnergiQ-AI folder to a local drive, for example C:\EnergiQ, and run this again.
goto :doneerror

:doneerror
set "RC=1"
:done
echo.
rem Set ENERGIQ_NO_PAUSE=1 to skip the final pause (for automated runs only).
if defined ENERGIQ_NO_PAUSE exit /b %RC%
pause
exit /b %RC%

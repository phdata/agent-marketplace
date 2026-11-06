@echo off
rem
rem toolkit-check.cmd - the Windows half of the launcher, and the one check that cannot be
rem written in Python: whether a Python 3 exists at all.
rem
rem This mirrors the POSIX `toolkit-check` and holds no logic of its own. It resolves an
rem interpreter and hands every argument to toolkit_check.py, which does all the work.
rem Native cmd.exe and PowerShell cannot run the sh launcher, so without this file the
rem SessionStart hook never fires on Windows and nothing tells the skills where the
rem scripts are.
rem
rem Usage: identical to toolkit_check.py - every argument is passed straight through.
rem
rem Exit codes: toolkit_check.py's own, plus 15 when no Python 3 could be found.
rem
rem Written with labels rather than parenthesised if-blocks on purpose: inside a block,
rem %ERRORLEVEL% and any variable set in that same block expand at parse time, not at run
rem time, which would silently swallow toolkit_check.py's exit code - and the exit code is
rem this script's whole contract.
rem
rem NOTE: authored on macOS and not executed on Windows. It mirrors the sh launcher step for
rem step; if it misbehaves, that is what to compare against.

setlocal EnableExtensions

rem %~dp0 is this script's directory, with a trailing backslash.
set "SCRIPT_DIR=%~dp0"
set "TARGET=%SCRIPT_DIR%toolkit_check.py"

rem Mode flags, read without consuming: every argument is forwarded as given.
set "HOOK=0"
set "QUIET=0"
for %%A in (%*) do (
    if "%%~A"=="--hook" set "HOOK=1"
    if "%%~A"=="--quiet" set "QUIET=1"
)

rem First interpreter that is actually Python 3. `py -3` is the Windows launcher and the
rem most reliable when several versions are installed; `python` is the usual PATH name;
rem `python3` comes last because on Windows it is often only a Store alias stub.
set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto :run

python -c "import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :run

python3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=python3"
if defined PY goto :run

goto :nopython

:run
%PY% "%TARGET%" %*
exit /b %ERRORLEVEL%

rem ---------- no Python 3 on this machine ----------

:nopython
if "%HOOK%"=="1" goto :hook_advisory
if "%QUIET%"=="1" exit /b 15
echo fail python: no py -3, python, or python3 found on PATH
echo hint: install Python 3.8 or newer from https://www.python.org/downloads/ -- every phData plugin script needs it
exit /b 15

:hook_advisory
rem Announce the paths anyway: the session is usable, the scripts are not.
set "ANNOUNCE=%SCRIPT_DIR:~0,-1%"
if defined CLAUDE_PLUGIN_ROOT set "ANNOUNCE=%CLAUDE_PLUGIN_ROOT%\scripts"
echo phData toolkit-core scripts -- not on PATH, invoke by absolute path with python: %ANNOUNCE%\toolkit_check.py, %ANNOUNCE%\toolkit_setup.py
echo python: NOT FOUND -- no py -3, python, or python3 on PATH.
echo Every phData plugin script - preflight checks, Informatica corpus and plan readers,
echo the data-contract review queue - is Python 3 stdlib only, so none of them can run
echo until a Python 3.8+ interpreter is installed. The Toolkit CLI itself is unaffected:
echo it is a JVM application, so plain 'toolkit' commands still work. Tell the user that,
echo and point them at https://www.python.org/downloads/ or the Microsoft Store.
exit /b 0

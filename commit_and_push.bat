@echo off
setlocal enabledelayedexpansion

set /p commitMsg="Enter commit message: "

:askScale
set /p scale="Enter update scale (b=big, m=medium, s=small): "
if /I "%scale%"=="b" goto validScale
if /I "%scale%"=="m" goto validScale
if /I "%scale%"=="s" goto validScale
echo Invalid input. Please enter b, m, or s.
goto askScale

:validScale
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bump_version.ps1" -Scale %scale%
if errorlevel 1 (
    echo.
    echo Failed to update version_info.json. Aborting commit.
    exit /b 1
)

git add -A
git commit -m "%commitMsg%"
git push

echo.
echo Done.
endlocal

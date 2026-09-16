@echo off
setlocal enabledelayedexpansion

rem --- Anchor everything to this script's own folder, regardless of how/where it was launched from ---
pushd "%~dp0"

set OUTPUT_DIR=%cd%\output\main
set STAGING_DIR=%cd%\output\main_new
set BUILD_DISTPATH=%cd%\output_staging

echo Script folder : %cd%
echo Output dir    : %OUTPUT_DIR%

echo Closing any running main.exe...
taskkill /F /IM main.exe /T >nul 2>&1

rem --- Clean any leftover staging folder from a previous failed run ---
if exist "%STAGING_DIR%" (
    attrib -r "%STAGING_DIR%\*" /s /d >nul 2>&1
    rmdir /s /q "%STAGING_DIR%" 2>nul
)
if exist "%BUILD_DISTPATH%" (
    rmdir /s /q "%BUILD_DISTPATH%" 2>nul
)

rem --- Build into a FRESH folder every time - PyInstaller never has to touch
rem     the existing output\main, so nothing there ever needs to be deleted
rem     by PyInstaller itself ---
echo.
echo Building...
pyinstaller --onedir --name main --distpath "%BUILD_DISTPATH%" --workpath ./build --noconfirm ^
  --add-data ".env;." ^
  --add-data "CLibs.py;." ^
  --add-data "client.py;." ^
  --add-data "fileCheck.py;." ^
  --add-data "protocol.py;." ^
  --add-data "server.py;." ^
  --add-data "version_info.json;." ^
  main.py

set BUILD_RESULT=%ERRORLEVEL%

if not "%BUILD_RESULT%"=="0" (
    echo.
    echo Build FAILED with exit code %BUILD_RESULT%. Nothing in %OUTPUT_DIR% was touched.
    popd
    exit /b %BUILD_RESULT%
)

rem --- Move the freshly built output into place as "main_new", carry .git over,
rem     then swap it with the live output\main ---
move "%BUILD_DISTPATH%\main" "%STAGING_DIR%" >nul
if errorlevel 1 (
    echo ERROR: Could not move build output into staging folder.
    popd
    exit /b 1
)
rmdir "%BUILD_DISTPATH%" 2>nul

if exist "%OUTPUT_DIR%\.git" (
    echo Carrying over existing .git into the new build...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0move_git.ps1" -Source "%OUTPUT_DIR%\.git" -Destination "%STAGING_DIR%\.git"
    if errorlevel 1 (
        echo ERROR: Could not move .git into the new build. Your old %OUTPUT_DIR% is untouched.
        echo The new build is sitting in %STAGING_DIR% - move .git there yourself, then
        echo swap the folders manually if you want to proceed.
        popd
        exit /b 1
    )
)

rem --- Now replace the old output\main with the new one ---
set OLD_DIR=%cd%\output\main_old
if exist "%OLD_DIR%" (
    echo Cleaning up leftover main_old from a previous run...
    attrib -r "%OLD_DIR%\*" /s /d >nul 2>&1
    rmdir /s /q "%OLD_DIR%" 2>nul
    if exist "%OLD_DIR%" (
        echo ERROR: Could not remove leftover %OLD_DIR%.
        echo Close any Explorer window or terminal that has it open, then run this script again.
        popd
        exit /b 1
    )
)

if exist "%OUTPUT_DIR%" (
    echo Retiring previous build...
    ren "%OUTPUT_DIR%" main_old
    if errorlevel 1 (
        echo ERROR: Could not rename existing %OUTPUT_DIR% out of the way.
        echo This means something still has that exact folder open right now
        echo ^(not just a file inside it^). Check for:
        echo   - An open File Explorer window showing that folder
        echo   - A terminal / PowerShell / IDE with that folder as its working directory
        echo Your new build is safely sitting in %STAGING_DIR% - nothing was lost.
        popd
        exit /b 1
    )
)

ren "%STAGING_DIR%" main
if errorlevel 1 (
    echo ERROR: Could not rename staging folder into place.
    echo Your new build is at %STAGING_DIR%, old build was renamed to %OUTPUT_DIR%\..\main_old
    popd
    exit /b 1
)

if exist "%cd%\output\main_old" (
    attrib -r "%cd%\output\main_old\*" /s /d >nul 2>&1
    rmdir /s /q "%cd%\output\main_old" 2>nul
)

echo.
echo Build complete: %OUTPUT_DIR%
popd
endlocal
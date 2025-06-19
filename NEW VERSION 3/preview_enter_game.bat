@echo off
setlocal enabledelayedexpansion

:: =============================================================================
:: MAME Controls Game Preview Launcher
:: =============================================================================
:: This batch file prompts for a game name and launches the preview
:: =============================================================================

title MAME Controls Game Preview

:: Change to the directory where this batch file is located
cd /d "%~dp0"

echo.
echo ================================================================================
echo  MAME Controls Game Preview Launcher
echo ================================================================================
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found or not in PATH
    echo.
    echo Please make sure Python is installed and added to your system PATH.
    echo You can download Python from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: Check if main script exists
if not exist "mame_controls_main.py" (
    echo [ERROR] mame_controls_main.py not found in current directory
    echo.
    echo Current directory: %CD%
    echo.
    pause
    exit /b 1
)

echo [OK] All required files found
echo.

:: Prompt for game name
echo Enter the ROM name you want to preview:
echo Examples: sf2, pacman, galaga, mk, frogger
echo.
set /p "game_name=Game name: "

:: Check if user entered something
if "%game_name%"=="" (
    echo.
    echo [ERROR] No game name entered. Exiting.
    echo.
    pause
    exit /b 1
)

:: Remove any quotes or spaces that might cause issues
set "game_name=%game_name:"=%"
set "game_name=%game_name: =%"

echo.
echo [INFO] Launching preview for: %game_name%
echo [INFO] Using clean preview mode (no buttons/UI)
echo.

:: Run the preview command
python.exe mame_controls_main.py --preview-only --game %game_name% --clean-preview

:: Capture the exit code
set preview_result=%errorlevel%

echo.
if %preview_result%==0 (
    echo [SUCCESS] Preview completed successfully
) else (
    echo [ERROR] Preview failed or was closed
    echo.
    echo Common issues:
    echo   - Game name not found in database/cache
    echo   - Missing cache file (try running precache first)
    echo   - Invalid ROM name
    echo.
    echo Try running: python mame_controls_main.py --precache --game %game_name%
)

echo.
echo Press any key to exit...
pause >nul
exit /b %preview_result%
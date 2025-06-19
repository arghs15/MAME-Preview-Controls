@echo off
setlocal enabledelayedexpansion

:: =============================================================================
:: MAME Controls Release Build Launcher
:: =============================================================================
:: This batch file allows you to run the release build script by simply
:: double-clicking it, without needing to open a terminal manually.
:: =============================================================================

title MAME Controls Release Build

:: Change to the directory where this batch file is located
cd /d "%~dp0"

echo.
echo ================================================================================
echo  MAME Controls Release Build Launcher
echo ================================================================================
echo.
echo This will automatically build a release version of MAME Controls with:
echo   - PERFORMANCE_MODE set to True
echo   - Complete PyInstaller packaging  
echo   - All settings files included
echo   - Your development files safely restored
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python is not found or not in PATH
    echo.
    echo Please make sure Python is installed and added to your system PATH.
    echo You can download Python from: https://www.python.org/downloads/
    echo.
    echo When installing Python, make sure to check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: Show Python version
echo [PYTHON] Python found:
python --version
echo.

:: Check if the release build script exists
if not exist "release_build_script.py" (
    echo.
    echo [ERROR] release_build_script.py not found in current directory
    echo.
    echo Current directory: %CD%
    echo.
    echo Please make sure this batch file is in the same directory as:
    echo   - release_build_script.py
    echo   - mame_controls_main.py
    echo.
    pause
    exit /b 1
)

:: Check if main script exists
if not exist "mame_controls_main.py" (
    echo.
    echo [ERROR] mame_controls_main.py not found in current directory
    echo.
    echo Current directory: %CD%
    echo.
    echo Please make sure this batch file is in the same directory as your MAME Controls source files.
    echo.
    pause
    exit /b 1
)

echo [OK] All required files found
echo.
echo [INFO] Working directory: %CD%
echo.
echo [BUILD] Starting release build...
echo.

:: Run the Python script with no-pause flag
python release_build_script.py --no-pause

:: Capture the exit code
set build_result=%errorlevel%

echo.
if %build_result%==0 (
    echo.
    echo ================================================================================
    echo  [SUCCESS] BUILD COMPLETED SUCCESSFULLY!
    echo ================================================================================
    echo.
    echo Your release files are ready in: dist\preview\
    echo.
    echo You can now:
    echo   1. Test the built application: dist\preview\MAME Controls.exe
    echo   2. Distribute the entire "preview" folder to users
    echo   3. Create a ZIP file of the "preview" folder for easy sharing
    echo.
) else (
    echo.
    echo ================================================================================
    echo  [FAILED] BUILD FAILED
    echo ================================================================================
    echo.
    echo The build process encountered errors. Please review the output above.
    echo.
    echo Common solutions:
    echo   - Make sure all Python dependencies are installed
    echo   - Check that PyInstaller is installed: pip install pyinstaller
    echo   - Ensure all source files are present
    echo.
)

echo Press any key to exit...
pause >nul
exit /b %build_result%
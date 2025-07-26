"""
Build script for PyInstaller packaging of Fightstick Mapper
Includes gamedata.json bundled within the executable
"""

import os
import subprocess
import shutil
import sys
import json

def main():
    print("Starting PyInstaller packaging for Fightstick Mapper...")
    
    # Output directories
    build_dir = "build"
    dist_dir = "dist"
    
    # Clean up existing directories
    if os.path.exists(build_dir):
        print(f"Cleaning up existing build directory: {build_dir}")
        shutil.rmtree(build_dir)
    
    if os.path.exists(dist_dir):
        print(f"Cleaning up existing dist directory: {dist_dir}")
        shutil.rmtree(dist_dir)
    
    # Check for gamedata.json in various locations
    gamedata_paths = [
        "gamedata.json",
        "settings/gamedata.json",
        "../gamedata.json",
        "../settings/gamedata.json",
        "preview/settings/gamedata.json"
    ]
    
    gamedata_file = None
    for path in gamedata_paths:
        if os.path.exists(path):
            gamedata_file = path
            print(f"Found gamedata.json at: {path}")
            break
    
    if not gamedata_file:
        print("ERROR: gamedata.json not found in any of the expected locations:")
        for path in gamedata_paths:
            print(f"  - {path}")
        print("\nThe fightstick mapper requires gamedata.json to function properly.")
        print("Please ensure gamedata.json is available in one of the above locations.")
        return False
    
    # Validate gamedata.json
    try:
        with open(gamedata_file, 'r', encoding='utf-8') as f:
            gamedata = json.load(f)
        print(f"Validated gamedata.json: {len(gamedata)} games found")
    except Exception as e:
        print(f"ERROR: Invalid gamedata.json file: {e}")
        return False
    
    # Build the PyInstaller command
    cmd = [
        "pyinstaller",
        "--name=MAME_Fightstick_Mapper",
        "--onefile",  # Single executable file
        "--windowed",  # No console window
        "--noconfirm",  # Overwrite without asking
        f"--add-data={gamedata_file};data",  # Include gamedata.json in the executable
        "--hidden-import=xml.etree.ElementTree",
        "--hidden-import=datetime",
        "--hidden-import=shutil",
        "fightstick_mapper.py"
    ]
    
    # Add icon if available
    icon_filename = "fightstick.ico"  # You can change this name
    icon_paths = [
        icon_filename,
        "P1.ico",  # Fallback to your existing icon
        os.path.join("assets", icon_filename),
        os.path.join("assets", "P1.ico"),
        os.path.join("..", icon_filename),
        os.path.join("..", "P1.ico")
    ]
    
    icon_path = None
    for path in icon_paths:
        if os.path.exists(path):
            icon_path = path
            print(f"Found icon file at: {path}")
            break
    
    if icon_path:
        cmd.insert(-1, f"--icon={icon_path}")  # Insert before the script name
    else:
        print("Warning: No icon file found. Executable will use default icon.")
    
    print("Running PyInstaller command:")
    print(" ".join(cmd))
    print()
    
    # Run PyInstaller
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        exe_name = "MAME_Fightstick_Mapper.exe" if sys.platform == "win32" else "MAME_Fightstick_Mapper"
        exe_path = os.path.join(dist_dir, exe_name)
        
        if os.path.exists(exe_path):
            file_size = os.path.getsize(exe_path) / (1024 * 1024)  # Size in MB
            print(f"\n✅ SUCCESS! Fightstick Mapper packaged successfully!")
            print(f"📁 Executable location: {exe_path}")
            print(f"📦 File size: {file_size:.1f} MB")
            print(f"🎮 Includes gamedata.json with {len(gamedata)} games")
            print(f"\nThe executable is completely portable and includes all required data.")
            print(f"Users can place it anywhere and it will work independently.")
            return True
        else:
            print(f"\n❌ ERROR: Executable not found at expected location: {exe_path}")
            return False
    else:
        print(f"\n❌ ERROR: PyInstaller failed with return code {result.returncode}")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        input("\nPress Enter to exit...")
        sys.exit(1)
"""
Build script for PyInstaller packaging of MAME Controls with hidden scripts
and optimized directory structure. Properly handles default settings files.
"""

import os
import subprocess
import shutil
import sys
import json

def main():
    print("Starting PyInstaller packaging for MAME Controls...")
    
    # Output directories
    build_dir = "build"
    dist_dir = "dist"
    preview_dir = os.path.join(dist_dir, "preview")
    settings_dir = os.path.join(preview_dir, "settings")
    
    # Clean up existing directories
    if os.path.exists(preview_dir):
        print(f"Cleaning up existing preview directory: {preview_dir}")
        shutil.rmtree(preview_dir)
    
    # Create settings directory
    os.makedirs(settings_dir, exist_ok=True)
    
    # SIMPLIFIED: Look for settings directory in current directory
    source_settings_dir = "settings"
    if not os.path.exists(source_settings_dir):
        os.makedirs(source_settings_dir, exist_ok=True)
        print(f"Created source settings directory: {source_settings_dir}")
    
    # Check for default global positions file
    global_positions_file = os.path.join(source_settings_dir, "global_positions.json")
    if os.path.exists(global_positions_file):
        print(f"Found global positions file: {global_positions_file}")
        print(f"Copying to output settings directory: {settings_dir}")
        shutil.copy(global_positions_file, os.path.join(settings_dir, "global_positions.json"))
    else:
        print(f"Warning: Default global positions file not found: {global_positions_file}")
        print("No default positions will be included in the package.")
    
    # NEW: Check for gamedata.json
    gamedata_file = os.path.join(source_settings_dir, "gamedata.json")
    if os.path.exists(gamedata_file):
        print(f"Found gamedata file: {gamedata_file}")
        print(f"Copying to output settings directory: {settings_dir}")
        shutil.copy(gamedata_file, os.path.join(settings_dir, "gamedata.json"))
    else:
        print(f"Warning: gamedata.json file not found in current directory")
        print("No game data will be included in the package.")
    
    # Check for other default settings files
    default_files = [
        "text_appearance_settings.json",
        "bezel_settings.json",
        "logo_settings.json",
        "grid_settings.json",
        "snapping_settings.json",
        "cache_settings.json",
        "control_config_settings.json",
        "global_text_settings.json"

    ]
    
    for default_file in default_files:
        source_file = os.path.join(source_settings_dir, default_file)
        if os.path.exists(source_file):
            print(f"Found settings file: {source_file}")
            dest_file = os.path.join(settings_dir, default_file)
            shutil.copy(source_file, dest_file)
            print(f"Copied to: {dest_file}")
    
    # Build the command - using temporary name to avoid confusion
    cmd = [
        "pyinstaller",
        "--name=temp_app",  # Temporary name that will be moved
        "--onedir",         # Create a directory with all files
        "--contents-directory=data",  # Hide implementation details
        "--windowed",
        "--hidden-import=preview_bridge",
        "--hidden-import=mame_controls_tkinter", 
        "--hidden-import=mame_controls_preview",
        "--collect-all=psutil",  # Ensure psutil is included
        "mame_controls_main.py"
    ]
    
    # Add icon with more flexible options
    icon_filename = "P1.ico"  # Default icon name
    icon_paths = [
        icon_filename,  # Current directory
        os.path.join("assets", icon_filename),  # assets subdirectory
        os.path.join("..", icon_filename)  # Parent directory
    ]

    # Try each possible location
    icon_path = None
    for path in icon_paths:
        if os.path.exists(path):
            icon_path = path
            print(f"Found icon file at: {path}")
            break

    # Add to PyInstaller command if found
    if icon_path:
        cmd.insert(2, f"--icon={icon_path}")
    else:
        print("Warning: No icon file found. Executable will use default icon.")
    
    print("Running command:", " ".join(cmd))
    subprocess.run(cmd)
    
    # Temp app directory created by PyInstaller
    temp_app_dir = os.path.join(dist_dir, "temp_app")
    
    if os.path.exists(temp_app_dir):
        print(f"Moving contents from {temp_app_dir} to {preview_dir}")
        
        # Move all contents from temp_app directory to preview directory
        for item in os.listdir(temp_app_dir):
            src_path = os.path.join(temp_app_dir, item)
            dst_path = os.path.join(preview_dir, item)
            
            if os.path.exists(dst_path) and os.path.isdir(dst_path):
                # If directory with same name exists, merge contents
                for subitem in os.listdir(src_path):
                    shutil.move(
                        os.path.join(src_path, subitem),
                        os.path.join(dst_path, subitem)
                    )
            else:
                # Otherwise just move the item
                shutil.move(src_path, dst_path)
        
        # Remove the temporary directory
        if os.path.exists(temp_app_dir):
            shutil.rmtree(temp_app_dir)
            
        print(f"Removed temporary directory: {temp_app_dir}")
    else:
        print(f"Error: Temporary app directory {temp_app_dir} not found")
    
    print(f"\nSuccessfully created distribution in {dist_dir}")
    print(f"The application is located in the preview folder: {preview_dir}")
    print("Final directory structure:")
    print(f"  {dist_dir}/")
    print(f"  └── preview/")
    print(f"      ├── MAME Controls.exe")
    print(f"      ├── data/")
    print(f"      └── settings/")
    
    # Print details of included settings files
    if os.path.exists(settings_dir):
        settings_files = os.listdir(settings_dir)
        if settings_files:
            for setting_file in settings_files:
                print(f"          └── {setting_file}")
                
                # If it's the global positions file, print a count of positions
                if setting_file == "global_positions.json":
                    try:
                        with open(os.path.join(settings_dir, setting_file), 'r') as f:
                            positions = json.load(f)
                            print(f"              ({len(positions)} control positions included)")
                    except:
                        pass
                
                # If it's gamedata.json, print the count of games
                if setting_file == "gamedata.json":
                    try:
                        with open(os.path.join(settings_dir, setting_file), 'r') as f:
                            gamedata = json.load(f)
                            print(f"              ({len(gamedata)} games included)")
                    except:
                        pass
    
    # Rename the executable if necessary
    exe_ext = ".exe" if sys.platform == "win32" else ""
    src_exe = os.path.join(preview_dir, f"temp_app{exe_ext}")
    dst_exe = os.path.join(preview_dir, f"MAME Controls{exe_ext}")
    
    if os.path.exists(src_exe) and src_exe != dst_exe:
        print(f"Renaming executable from {src_exe} to {dst_exe}")
        shutil.move(src_exe, dst_exe)

if __name__ == "__main__":
    main()
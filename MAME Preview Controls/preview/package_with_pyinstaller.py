"""
Build script for PyInstaller packaging of MAME Controls with hidden scripts
and optimized directory structure
"""

import os
import subprocess
import shutil
import sys

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
    
    # Build the command - using temporary name to avoid confusion
    cmd = [
        "pyinstaller",
        "--name=temp_app",  # Temporary name that will be moved
        "--onedir",         # Create a directory with all files
        "--contents-directory=myData",  # Hide implementation details
        "--windowed",
        "--hidden-import=mame_controls_pyqt",
        "--hidden-import=mame_controls_tkinter", 
        "--hidden-import=mame_controls_preview",
        "--collect-all=psutil",  # Ensure psutil is included
        "mame_controls_main.py"
    ]
    
    # Add icon if available
    icon_path = "mame.ico"
    if os.path.exists(icon_path):
        cmd.insert(2, f"--icon={icon_path}")
    
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
    print(f"      ├── temp_app.exe")
    print(f"      ├── myData/")
    print(f"      └── settings/")
    
    # Rename the executable if necessary
    exe_ext = ".exe" if sys.platform == "win32" else ""
    src_exe = os.path.join(preview_dir, f"temp_app{exe_ext}")
    dst_exe = os.path.join(preview_dir, f"MAME_Controls{exe_ext}")
    
    if os.path.exists(src_exe) and src_exe != dst_exe:
        print(f"Renaming executable from {src_exe} to {dst_exe}")
        shutil.move(src_exe, dst_exe)

if __name__ == "__main__":
    main()
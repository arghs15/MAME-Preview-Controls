#!/usr/bin/env python3
"""
Simple Release Build Script for MAME Controls

This script:
1. Sets PERFORMANCE_MODE = True in mame_controls_main.py
2. Runs PyInstaller packaging with all necessary options
3. That's it - simple and direct!

Usage:
    python release_build_script.py
"""

import os
import shutil
import subprocess
import sys
import re
import time
import json
from datetime import datetime

def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def print_step(step_num, total_steps, description):
    """Print a formatted step indicator"""
    print(f"\n[{step_num}/{total_steps}] {description}")
    print("-" * 40)

def set_performance_mode_true(file_path):
    """Set PERFORMANCE_MODE = True in the file"""
    try:
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check current setting
        match = re.search(r'PERFORMANCE_MODE\s*=\s*(True|False)', content)
        if match:
            current_value = match.group(1)
            print(f"📊 Current PERFORMANCE_MODE: {current_value}")
            
            if current_value == 'False':
                # Replace False with True
                new_content = re.sub(
                    r'PERFORMANCE_MODE\s*=\s*False',
                    'PERFORMANCE_MODE = True',
                    content
                )
                
                # Write the updated content
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print("✅ PERFORMANCE_MODE changed from False to True")
                return True
            else:
                print("✅ PERFORMANCE_MODE is already True")
                return True
        else:
            print("⚠️  PERFORMANCE_MODE not found in file - proceeding anyway")
            return True
            
    except Exception as e:
        print(f"❌ Error setting performance mode: {e}")
        return False

def prepare_settings_directory():
    """Prepare settings directory and copy settings files"""
    print("🔧 Preparing settings directory...")
    
    # Output directories
    build_dir = "build"
    dist_dir = "dist"
    preview_dir = os.path.join(dist_dir, "preview")
    settings_dir = os.path.join(preview_dir, "settings")
    
    # Clean up existing preview directory
    if os.path.exists(preview_dir):
        print(f"🧹 Cleaning up existing preview directory: {preview_dir}")
        shutil.rmtree(preview_dir)
    
    # Create settings directory
    os.makedirs(settings_dir, exist_ok=True)
    print(f"📁 Created settings directory: {settings_dir}")
    
    # Look for settings directory in current directory
    source_settings_dir = "settings"
    if not os.path.exists(source_settings_dir):
        os.makedirs(source_settings_dir, exist_ok=True)
        print(f"📁 Created source settings directory: {source_settings_dir}")
    
    # Copy settings files
    settings_files_copied = 0
    
    # Check for default global positions file
    global_positions_file = os.path.join(source_settings_dir, "global_positions.json")
    if os.path.exists(global_positions_file):
        print(f"📋 Found global positions file: {global_positions_file}")
        shutil.copy(global_positions_file, os.path.join(settings_dir, "global_positions.json"))
        settings_files_copied += 1
        
        # Print count of positions
        try:
            with open(global_positions_file, 'r') as f:
                positions = json.load(f)
                print(f"   └─ {len(positions)} control positions included")
        except:
            pass
    else:
        print(f"⚠️  Warning: Default global positions file not found: {global_positions_file}")
    
    # Check for gamedata.json
    gamedata_file = os.path.join(source_settings_dir, "gamedata.json")
    if os.path.exists(gamedata_file):
        print(f"📋 Found gamedata file: {gamedata_file}")
        shutil.copy(gamedata_file, os.path.join(settings_dir, "gamedata.json"))
        settings_files_copied += 1
        
        # Print count of games
        try:
            with open(gamedata_file, 'r') as f:
                gamedata = json.load(f)
                print(f"   └─ {len(gamedata)} games included")
        except:
            pass
    else:
        print(f"⚠️  Warning: gamedata.json file not found")
    
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
            print(f"📋 Found settings file: {default_file}")
            dest_file = os.path.join(settings_dir, default_file)
            shutil.copy(source_file, dest_file)
            settings_files_copied += 1
    
    print(f"✅ Settings preparation complete: {settings_files_copied} files copied")
    return preview_dir, settings_dir

def find_icon_file():
    """Find the icon file in various locations"""
    icon_filename = "P1.ico"
    icon_paths = [
        icon_filename,  # Current directory
        os.path.join("assets", icon_filename),  # assets subdirectory
        os.path.join("..", icon_filename)  # Parent directory
    ]

    for path in icon_paths:
        if os.path.exists(path):
            print(f"🎨 Found icon file at: {path}")
            return path

    print("⚠️  Warning: No icon file found. Executable will use default icon.")
    return None

def run_pyinstaller_packaging():
    """Run PyInstaller with all the necessary options"""
    try:
        print("🚀 Running PyInstaller packaging...")
        
        # Check if main script exists
        main_script = "mame_controls_main.py"
        if not os.path.exists(main_script):
            print(f"❌ Main script not found: {main_script}")
            return False
        
        # Prepare settings directory first
        preview_dir, settings_dir = prepare_settings_directory()
        
        # Build the PyInstaller command
        cmd = [
            "pyinstaller",
            "--name=temp_app",  # Temporary name that will be moved
            "--onedir",         # Create a directory with all files
            "--contents-directory=data",  # Hide implementation details
            "--windowed",
            "--hidden-import=mame_controls_pyqt",
            "--hidden-import=mame_controls_tkinter", 
            "--hidden-import=mame_controls_preview",
            "--hidden-import=mame_data_utils",
            "--hidden-import=mame_utils",
            "--collect-all=psutil",  # Ensure psutil is included
            main_script
        ]
        
        # Add icon if found
        icon_path = find_icon_file()
        if icon_path:
            cmd.insert(2, f"--icon={icon_path}")
        
        print("📜 PyInstaller command:")
        print("   " + " ".join(cmd))
        
        # Run PyInstaller
        print("\n🔄 Running PyInstaller (this may take a few minutes)...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("❌ PyInstaller failed")
            if result.stderr:
                print(f"🔥 Error: {result.stderr}")
            if result.stdout:
                print(f"📋 Output: {result.stdout}")
            return False
        
        print("✅ PyInstaller completed successfully")
        
        # Move and rename the output
        dist_dir = "dist"
        temp_app_dir = os.path.join(dist_dir, "temp_app")
        
        if os.path.exists(temp_app_dir):
            print(f"📁 Moving contents from {temp_app_dir} to {preview_dir}")
            
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
                print(f"🗑️  Removed temporary directory: {temp_app_dir}")
        else:
            print(f"❌ Error: Temporary app directory {temp_app_dir} not found")
            return False
        
        # Rename the executable
        exe_ext = ".exe" if sys.platform == "win32" else ""
        src_exe = os.path.join(preview_dir, f"temp_app{exe_ext}")
        dst_exe = os.path.join(preview_dir, f"MAME Controls{exe_ext}")
        
        if os.path.exists(src_exe) and src_exe != dst_exe:
            print(f"📝 Renaming executable: temp_app{exe_ext} → MAME Controls{exe_ext}")
            shutil.move(src_exe, dst_exe)
        
        # Print final structure
        print(f"\n✅ Successfully created distribution in {dist_dir}")
        print(f"📁 The application is located in: {preview_dir}")
        print("\n📋 Final directory structure:")
        print(f"  {dist_dir}/")
        print(f"  └── preview/")
        print(f"      ├── MAME Controls{exe_ext}")
        print(f"      ├── data/")
        print(f"      └── settings/")
        
        # Print details of included settings files
        if os.path.exists(settings_dir):
            settings_files = os.listdir(settings_dir)
            if settings_files:
                print(f"          Settings files included:")
                for setting_file in sorted(settings_files):
                    print(f"          ├── {setting_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in PyInstaller packaging: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function to orchestrate the release build process"""
    print_header("MAME Controls Simple Release Build")
    
    start_time = time.time()
    
    # Configuration
    main_file = "mame_controls_main.py"
    
    # Check if main file exists
    if not os.path.exists(main_file):
        print(f"❌ ERROR: {main_file} not found in current directory")
        print(f"📁 Current directory: {os.getcwd()}")
        return 1
    
    print(f"📁 Working directory: {os.getcwd()}")
    print(f"📄 Target file: {main_file}")
    
    try:
        # Step 1: Set performance mode to True
        print_step(1, 2, "Setting PERFORMANCE_MODE = True")
        if not set_performance_mode_true(main_file):
            return 1
        
        # Step 2: Run PyInstaller packaging
        print_step(2, 2, "Running PyInstaller packaging")
        if not run_pyinstaller_packaging():
            return 1
        
        # Final status
        end_time = time.time()
        duration = end_time - start_time
        
        print_header("BUILD SUMMARY")
        print(f"⏱️  Duration: {duration:.1f} seconds")
        print(f"📅 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("🎉 SUCCESS: Release build completed successfully!")
        print("📦 Check the 'dist/preview' directory for your release files")
        
        # Show dist directory contents if it exists
        dist_dir = os.path.join("dist", "preview")
        if os.path.exists(dist_dir):
            print(f"\n📁 Release files in {dist_dir}:")
            try:
                for item in sorted(os.listdir(dist_dir)):
                    item_path = os.path.join(dist_dir, item)
                    if os.path.isfile(item_path):
                        size = os.path.getsize(item_path)
                        if size > 1024*1024:
                            size_str = f"{size/(1024*1024):.1f} MB"
                        elif size > 1024:
                            size_str = f"{size/1024:.1f} KB"
                        else:
                            size_str = f"{size} B"
                        print(f"   📄 {item} ({size_str})")
                    elif os.path.isdir(item_path):
                        print(f"   📁 {item}/")
            except Exception as e:
                print(f"   ❌ Error listing directory: {e}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Build interrupted by user (Ctrl+C)")
        return 1
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    # Check if we should suppress the pause (when called from batch file)
    suppress_pause = len(sys.argv) > 1 and sys.argv[1] == "--no-pause"
    
    exit_code = main()
    
    # Only pause if not suppressed
    if not suppress_pause:
        try:
            input("\nPress Enter to exit...")
        except KeyboardInterrupt:
            pass
    
    sys.exit(exit_code)
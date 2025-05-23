# mame_utils.py
import os
import sys
import json
import shutil
from typing import Optional, List, Union

def get_application_path():
    """Get the base path for the application (handles PyInstaller bundling)"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = os.path.dirname(sys.executable)
        # If executable is in preview folder, use base_path
        # Otherwise, create preview subfolder
        if os.path.basename(base_path) != "preview":
            base_path = os.path.join(base_path, "preview")
        return base_path
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))

def get_mame_parent_dir(app_path=None):
    """
    Get the parent directory where MAME, ROMs, and artwork are located.
    If we're in the preview folder, the parent is the MAME directory.
    """
    if app_path is None:
        app_path = get_application_path()
    
    # If we're in the preview folder, the parent is the MAME directory
    if os.path.basename(app_path) == "preview":
        return os.path.dirname(app_path)
    else:
        # We're already in the MAME directory
        return app_path

def find_file_in_standard_locations(filename: str, 
                                  subdirs: Optional[List[Union[str, List[str]]]] = None,
                                  app_dir: Optional[str] = None,
                                  mame_dir: Optional[str] = None,
                                  copy_to: Optional[str] = None) -> Optional[str]:
    """
    Find a file in standard MAME locations with optional subdirectories.
    
    Args:
        filename: Name of file to find
        subdirs: List of subdirectories to check
        app_dir: Application directory (if not provided, will be determined)
        mame_dir: MAME directory (if not provided, will be determined)
        copy_to: If provided, copy found file to this location
        
    Returns:
        Path to found file, or None if not found
    """
    if subdirs is None:
        subdirs = []
    
    # Get directories if not provided
    if app_dir is None:
        app_dir = get_application_path()
    if mame_dir is None:
        mame_dir = get_mame_parent_dir(app_dir)
    
    # Define search order
    search_bases = [
        app_dir,
        mame_dir,
        os.path.join(mame_dir, "preview"),
        os.path.join(app_dir, "preview"),
    ]
    
    # Build all possible paths
    search_paths = []
    for base in search_bases:
        # Add base path
        search_paths.append(os.path.join(base, filename))
        
        # Add paths with subdirectories
        for subdir_list in subdirs:
            if isinstance(subdir_list, str):
                subdir_list = [subdir_list]
            subdir_path = os.path.join(base, *subdir_list, filename)
            search_paths.append(subdir_path)
    
    # Search for file
    for path in search_paths:
        if os.path.exists(path):
            print(f"Found {filename} at: {path}")
            
            # Copy to destination if requested
            if copy_to and path != copy_to:
                try:
                    os.makedirs(os.path.dirname(copy_to), exist_ok=True)
                    shutil.copy2(path, copy_to)
                    print(f"Copied {filename} to {copy_to}")
                    return copy_to
                except Exception as e:
                    print(f"Error copying to {copy_to}: {e}")
            
            return path
    
    print(f"File {filename} not found in any standard location")
    return None

def ensure_file_exists(filepath: str, default_content: str = "") -> bool:
    """Ensure a file exists, creating it with default content if needed"""
    try:
        if not os.path.exists(filepath):
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(default_content)
            print(f"Created file: {filepath}")
        return True
    except Exception as e:
        print(f"Error ensuring file exists: {e}")
        return False

def load_json_file(filepath: str, default: dict = None) -> dict:
    """Load JSON file with error handling and default fallback"""
    if default is None:
        default = {}
    
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading JSON from {filepath}: {e}")
    
    return default

def save_json_file(filepath: str, data: dict) -> bool:
    """Save JSON file with error handling"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving JSON to {filepath}: {e}")
        return False
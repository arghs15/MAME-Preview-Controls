import builtins
import datetime
import sqlite3
import sys
import os
import json
import re
import subprocess
import time
import traceback
from typing import Dict, Optional, Set, List, Tuple
import xml.etree.ElementTree as ET
import customtkinter as ctk
from tkinter import messagebox, StringVar, scrolledtext, Frame, Label, PhotoImage, TclError

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

# Set theme and appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Add these helper functions if not already present
def get_application_path():
    """Get the base path for the application (handles PyInstaller bundling)"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
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
    if os.path.basename(app_path).lower() == "preview":
        return os.path.dirname(app_path)
    else:
        # We're already in the MAME directory
        return app_path

# Global debug flag
DEBUG_MODE = False  # Set to False to disable all debug output

def debug_print(message):
    """Print debug message with timestamp only if DEBUG_MODE is True"""
    if not DEBUG_MODE:
        return
    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[DEBUG {timestamp}] {message}")

def debug_path_info():
    """Print path debugging information only if DEBUG_MODE is True"""
    if not DEBUG_MODE:
        return
    debug_print("=== PATH DEBUGGING ===")
    debug_print(f"Current working directory: {os.getcwd()}")
    debug_print(f"Script location: {os.path.dirname(os.path.abspath(__file__))}")
    debug_print(f"Python path: {sys.path}")
    debug_print(f"OS environment PATH: {os.environ.get('PATH', '')}")
    debug_print("====== MODULES ======")
    for name, module in sorted(sys.modules.items()):
        if hasattr(module, '__file__') and module.__file__:
            debug_print(f"{name}: {module.__file__}")
    debug_print("====================")

class PositionManager:
    """Handles storage, normalization, and application of text positions"""
    
    def __init__(self, parent):
        """Initialize the position manager"""
        self.parent = parent  # Reference to the main app
        self.positions = {}   # Store for in-memory positions
    
    def normalize(self, x, y, y_offset=None):
        """Convert a display position to a normalized position (without y-offset)"""
        if y_offset is None:
            # Get from settings if not provided
            settings = self.parent.load_text_appearance_settings()  # Use direct method call
            y_offset = settings.get("y_offset", -40)
        
        # Remove y-offset
        normalized_y = y - y_offset
        return x, normalized_y
    
    def apply_offset(self, x, normalized_y, y_offset=None):
        """Apply y-offset to a normalized position for display"""
        if y_offset is None:
            # Get from settings if not provided
            settings = self.parent.load_text_appearance_settings()  # Use direct method call
            y_offset = settings.get("y_offset", -40)
        
        # Add y-offset
        display_y = normalized_y + y_offset
        return x, display_y
    
    def store(self, control_name, x, y, is_normalized=False):
        """Store a position for a control (normalizing if needed)"""
        if not is_normalized:
            # Normalize if the position includes y-offset
            x, normalized_y = self.normalize(x, y)
        else:
            # Already normalized
            normalized_y = y
        
        # Store the normalized position
        self.positions[control_name] = (x, normalized_y)
        return x, normalized_y
    
    def get_display(self, control_name, default_x=0, default_y=0):
        """Get the display position (with y-offset applied) for a control"""
        # Get normalized position (or use defaults)
        x, normalized_y = self.get_normalized(control_name, default_x, default_y)
        
        # Apply offset for display
        return self.apply_offset(x, normalized_y)
    
    def get_normalized(self, control_name, default_x=0, default_y=0):
        """Get the normalized position (without y-offset) for a control"""
        if control_name in self.positions:
            return self.positions[control_name]
        else:
            # Return defaults if not found
            return default_x, default_y
    
    def update_from_dragging(self, control_name, new_x, new_y):
        """Update a position from dragging (storing normalized values)"""
        x, normalized_y = self.normalize(new_x, new_y)
        self.positions[control_name] = (x, normalized_y)
        return x, normalized_y
    
    def load_from_file(self, game_name):
        """Load positions from file for a specific game"""
        # Reset the positions
        self.positions = {}
        
        try:
            # Use the parent's file loading method to get positions with proper priority
            loaded_positions = self.parent.load_text_positions(game_name)
            
            # Store the loaded positions (they should already be normalized)
            for name, pos in loaded_positions.items():
                if isinstance(pos, list) and len(pos) == 2:
                    x, normalized_y = pos
                    self.positions[name] = (x, normalized_y)
                    
            return len(self.positions) > 0
        except Exception as e:
            print(f"Error loading positions: {e}")
            return False
    
    def save_to_file(self, game_name=None, is_global=False):
        """Save positions to file (globally or for a specific game)"""
        if not self.positions:
            print("No positions to save")
            return False
            
        try:
            # Convert to format expected by file saving function
            positions_to_save = {}
            for name, (x, normalized_y) in self.positions.items():
                positions_to_save[name] = [x, normalized_y]
            
            # Create preview directory if it doesn't exist
            preview_dir = os.path.join(self.parent.mame_dir, "preview")
            os.makedirs(preview_dir, exist_ok=True)
            
            # Determine the file path
            if is_global:
                filepath = os.path.join(preview_dir, "global_positions.json")
            else:
                filepath = os.path.join(preview_dir, f"{game_name}_positions.json")
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(positions_to_save, f)
                
            print(f"Saved {len(positions_to_save)} positions to: {filepath}")
            return True
                
        except Exception as e:
            print(f"Error saving positions: {e}")
            return False


class MAMEControlConfig(ctk.CTk):
    def __init__(self, preview_only=False):
        debug_print("Starting MAMEControlConfig initialization")

        try:
            super().__init__()
            debug_print("Super initialization complete")

            # Initialize core attributes needed for both modes
            self.visible_control_types = ["BUTTON", "JOYSTICK"]
            self.default_controls = {}
            self.gamedata_json = {}
            self.available_roms = set()
            self.custom_configs = {}
            self.current_game = None
            self.use_xinput = True
            
            # Logo size settings (as percentages)
            self.logo_width_percentage = 15
            self.logo_height_percentage = 15
            
            # NEW CODE: Replace individual directory setup with the centralized method
            self.initialize_directory_structure()
            
            self.clean_cache_directory(max_age_days=None, max_files=None)
            
            # The rest of your initialization code...
            debug_print(f"App directory: {self.app_dir}")
            debug_print(f"MAME directory: {self.mame_dir}")
            debug_print(f"Preview directory: {self.preview_dir}")
            debug_print(f"Settings directory: {self.settings_dir}")
            
            # Initialize the position manager
            self.position_manager = PositionManager(self)

            # Initialize the preview bridge for PyQt functionality
            try:
                from preview_bridge import PreviewBridge
                self.preview_bridge = PreviewBridge()
                debug_print("Preview bridge initialized")
            except ImportError:
                debug_print("Warning: Could not import preview_bridge. Preview functionality will be limited.")
                self.preview_bridge = None

            # Configure the window
            self.title("MAME Control Configuration")
            self.geometry("1280x800")
            self.fullscreen = False  # Track fullscreen state
            
            debug_print("Window configuration complete")
            
            # Bind F11 key for fullscreen toggle
            self.bind("<F11>", self.toggle_fullscreen)
            self.bind("<Escape>", self.exit_fullscreen)
            
            self.selected_line = None
            self.highlight_tag = "highlight"

            # Load color scheme
            self.load_color_scheme()
            
            # Set initial fullscreen state
            self.after(100, self.state, 'zoomed')  # Use zoomed for Windows
            debug_print("Fullscreen state set")
            
            if not self.mame_dir:
                debug_print("ERROR: MAME directory not found!")
                messagebox.showerror("Error", "MAME directory not found!")
                self.quit()
                return

            # Create the interface
            debug_print("Creating layout...")
            self.create_layout()
            debug_print("Layout created")
            
            # Load all data
            debug_print("Loading data...")
            self.load_all_data()
            debug_print("Data loaded")

            # Add this near the end of __init__:
            self.preview_processes = []  # Track any preview processes we launch
            
            # Set the WM_DELETE_WINDOW protocol
            self.protocol("WM_DELETE_WINDOW", self.on_closing)
            
            debug_print("Initialization complete")
        except Exception as e:
            debug_print(f"CRITICAL ERROR in initialization: {e}")
            traceback.print_exc()
            messagebox.showerror("Initialization Error", f"Failed to initialize: {e}")
    
    # Modified on_game_select with extremely thorough debugging
    def on_game_select(self, event):
        """Handle game selection with extreme debugging"""
        try:
            # Get the selected game name
            index = self.game_list.index(f"@{event.x},{event.y}")
            
            # Get the line number (starting from 1)
            line_num = int(index.split('.')[0])
            
            # Get the text from this line
            line = self.game_list.get(f"{line_num}.0", f"{line_num}.0 lineend")
            
            # Skip if line is empty or "No matching ROMs found"
            if not line or line.startswith("No matching ROMs"):
                return
                
            # Highlight the selected line
            self.highlight_selected_game(line_num)
            
            print(f"\n=== GAME SELECTION DEBUG ===")
            print(f"Selected line text: '{line}'")
            
            # Try multiple approaches to extract the ROM name
            
            # Approach 1: Split by dash
            rom_name_1 = line.split(" - ")[0].strip() if " - " in line else line.strip()
            print(f"Approach 1 (split by dash): '{rom_name_1}'")
            
            # Approach 2: Remove icon characters
            rom_name_2 = line.strip()
            for char in "🔧✓✗ \t":
                rom_name_2 = rom_name_2.replace(char, "")
            if " - " in rom_name_2:
                rom_name_2 = rom_name_2.split(" - ")[0]
            print(f"Approach 2 (remove icons): '{rom_name_2}'")
            
            # Approach 3: Strip non-alphanumeric from start
            rom_name_3 = line.strip()
            if " - " in rom_name_3:
                rom_name_3 = rom_name_3.split(" - ")[0].strip()
            while rom_name_3 and not (rom_name_3[0].isalnum() or rom_name_3[0] == '_'):
                rom_name_3 = rom_name_3[1:].strip()
            print(f"Approach 3 (strip non-alphanumeric): '{rom_name_3}'")
            
            # Approach 4: Use regex to extract only alphanumeric
            import re
            match = re.search(r'[a-zA-Z0-9_]+', line)
            rom_name_4 = match.group(0) if match else ""
            print(f"Approach 4 (regex): '{rom_name_4}'")
            
            # Try all approaches in order
            approaches = [
                ("Split by dash", rom_name_1),
                ("Remove icons", rom_name_2),
                ("Strip non-alphanumeric", rom_name_3),
                ("Regex", rom_name_4)
            ]
            
            # Look up each approach in gamedata.json
            found_match = False
            for approach_name, rom_name in approaches:
                print(f"\nTrying lookup with {approach_name}: '{rom_name}'")
                
                # Try direct lookup
                exact_match = rom_name in self.gamedata_json if hasattr(self, 'gamedata_json') else False
                print(f"  Direct match in gamedata.json: {exact_match}")
                
                if exact_match:
                    found_match = True
                    print(f"  USING ROM NAME: '{rom_name}' (from {approach_name})")
                    self.current_game = rom_name
                    break
            
            # If no match found, try direct lookup for diagnostic info
            if not found_match:
                # Try direct lookup on key ROMs for debugging
                for test_name in ["1941", "1943kai", "2020bb"]:
                    if line.lower().find(test_name.lower()) >= 0:
                        print(f"\nFound '{test_name}' in line - trying direct lookup")
                        result = self.direct_rom_lookup(test_name)
                        if result:
                            rom_name = result
                            found_match = True
                            print(f"  USING ROM NAME from direct lookup: '{rom_name}'")
                            self.current_game = rom_name
                            break
                
                # If still no match, take the best guess
                if not found_match:
                    rom_name = rom_name_3  # Use approach 3 as our best guess
                    print(f"\nNo match found - using best guess: '{rom_name}'")
                    self.current_game = rom_name
            
            print("===================================\n")
            
            # Now proceed with getting game data
            game_data = None
            try:
                game_data = self.get_game_data(rom_name)
            except Exception as e:
                print(f"Error getting game data: {e}")
            
            # Clear existing display
            for widget in self.control_frame.winfo_children():
                widget.destroy()
                
            if not game_data:
                # Clear display for ROMs without control data
                self.game_title.configure(text=f"No control data: {rom_name}")
                return
                
            # Update game title
            source_text = f" ({game_data.get('source', 'unknown')})"
            title_text = f"{game_data['gamename']}{source_text}"
            
            # Update title text ensuring left-alignment with proper wrapping
            self.game_title.configure(text=title_text)
            
            # Get custom controls if they exist
            cfg_controls = {}
            if rom_name in self.custom_configs:
                # Only parse the custom configs if we need them
                cfg_controls = self.parse_cfg_controls(self.custom_configs[rom_name])
                
                # Convert mappings if XInput is enabled
                if self.use_xinput:
                    cfg_controls = {
                        control: self.convert_mapping(mapping, True)
                        for control, mapping in cfg_controls.items()
                    }
            
            # Display controls
            if hasattr(self, "display_controls_table"):
                self.display_controls_table(0, game_data, cfg_controls)
            else:
                # Fallback to a simple control display
                self._display_simple_controls(game_data, cfg_controls)
                
        except Exception as e:
            print(f"Error in game selection: {e}")
            import traceback
            traceback.print_exc()

    # This is a very direct method to look up ROM data - add it to your class
    def direct_rom_lookup(self, rom_name):
        """Super direct lookup of ROM data by exact name"""
        print(f"\n=== DIRECT ROM LOOKUP FOR '{rom_name}' ===")
        
        if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
            print("ERROR: gamedata_json not available")
            return None
        
        # Check for exact match
        if rom_name in self.gamedata_json:
            print(f"FOUND direct match for '{rom_name}'")
            return rom_name
        
        # Try case-insensitive search
        for key in self.gamedata_json:
            if key.lower() == rom_name.lower():
                print(f"FOUND case-insensitive match: '{key}'")
                return key
        
        # Try looking for it as part of another key
        partial_matches = []
        for key in self.gamedata_json:
            if rom_name in key:
                partial_matches.append(key)
        
        if partial_matches:
            print(f"Found {len(partial_matches)} partial matches:")
            for match in partial_matches[:5]:
                print(f"  * '{match}'")
            if len(partial_matches) > 5:
                print(f"  * ... and {len(partial_matches) - 5} more")
        else:
            print(f"NO MATCHES found for '{rom_name}'")
        
        print("===================================\n")
        return None

    def debug_gamedata_keys(self):
        """Print all keys in gamedata.json to find problematic ROMs"""
        if hasattr(self, 'gamedata_json') and self.gamedata_json:
            # Sort keys for easier searching
            all_keys = sorted(self.gamedata_json.keys())
            print("\n=== DEBUGGING GAMEDATA.JSON KEYS ===")
            print(f"Total keys: {len(all_keys)}")
            
            # Check specifically for numeric ROMs
            numeric_keys = [k for k in all_keys if k[0].isdigit()]
            print(f"Numeric keys: {len(numeric_keys)}")
            print("Sample numeric ROM names:")
            for key in numeric_keys[:10]:
                print(f"  - '{key}'")
                
            # Look specifically for problematic ROMs
            problem_roms = ['1941', '1943kai', '2020bb', 'actfancr']
            for rom in problem_roms:
                print(f"Looking for '{rom}' in gamedata.json keys:")
                if rom in self.gamedata_json:
                    print(f"  - FOUND EXACT MATCH for '{rom}'")
                    # Get some details about this ROM
                    rom_data = self.gamedata_json[rom]
                    print(f"    Description: {rom_data.get('description', 'Not available')}")
                    print(f"    Has controls: {'controls' in rom_data}")
                    if 'controls' in rom_data:
                        print(f"    Controls count: {len(rom_data['controls'])}")
                else:
                    print(f"  - NOT FOUND as exact match")
                    
                    # Look for partial matches
                    partial_matches = [k for k in all_keys if rom in k]
                    if partial_matches:
                        print(f"  - Found {len(partial_matches)} partial matches:")
                        for match in partial_matches[:5]:
                            print(f"    * '{match}'")
                        if len(partial_matches) > 5:
                            print(f"    * ... and {len(partial_matches) - 5} more")
            print("===================================\n")
    
    def load_color_scheme(self):
        """Load the color scheme for the application"""
        # Define a nice color scheme
        self.colors = {
            "primary": "#1E90FF",         # Dodger Blue
            "primary_hover": "#1A6DAE",   # Darker blue for hover
            "accent": "#3A7CEA",          # Light blue accent
            "bg_dark": "#121212",         # Very dark background
            "bg_medium": "#1E1E1E",       # Medium dark background for panels
            "bg_light": "#252525",        # Lighter background for inputs
            "text": "#FFFFFF",            # White text
            "text_secondary": "#AAAAAA",  # Light gray for secondary text
            "success": "#28a745",         # Green for success indicators
            "warning": "#ffc107",         # Yellow for warnings
            "error": "#dc3545",           # Red for errors
            "highlight": "#3A7CEA"        # Highlight color for selected items
        }
        
        # Configure appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

    
    
    def load_cache_settings(self):
        """Load cache management settings from JSON file"""
        default_settings = {
            "max_age_days": 7,
            "max_files": 100,
            "auto_cleanup_enabled": True
        }
        
        settings_file = os.path.join(self.settings_dir, "cache_settings.json")
        
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    
                # Validate and use settings, falling back to defaults if needed
                self.cache_max_age = int(settings.get("max_age_days", default_settings["max_age_days"]))
                self.cache_max_files = int(settings.get("max_files", default_settings["max_files"]))
                self.cache_auto_cleanup = bool(settings.get("auto_cleanup_enabled", default_settings["auto_cleanup_enabled"]))
            else:
                # Use defaults
                self.cache_max_age = default_settings["max_age_days"]
                self.cache_max_files = default_settings["max_files"]
                self.cache_auto_cleanup = default_settings["auto_cleanup_enabled"]
                
                # Create default settings file
                self.save_cache_settings()
        except Exception as e:
            print(f"Error loading cache settings: {e}")
            # Use defaults on error
            self.cache_max_age = default_settings["max_age_days"]
            self.cache_max_files = default_settings["max_files"]
            self.cache_auto_cleanup = default_settings["auto_cleanup_enabled"]

    def save_cache_settings(self):
        """Save cache management settings to JSON file"""
        settings = {
            "max_age_days": self.cache_max_age,
            "max_files": self.cache_max_files,
            "auto_cleanup_enabled": self.cache_auto_cleanup
        }
        
        settings_file = os.path.join(self.settings_dir, "cache_settings.json")
        
        try:
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
            print(f"Cache settings saved to: {settings_file}")
        except Exception as e:
            print(f"Error saving cache settings: {e}")
    
    # Update the clean_cache_directory method to use the saved settings
    def clean_cache_directory(self, max_age_days=None, max_files=None):
        """Clean old cache files to prevent unlimited growth"""
        # Load settings if not provided
        if max_age_days is None:
            if not hasattr(self, 'cache_max_age'):
                self.load_cache_settings()
            max_age_days = self.cache_max_age
            
        if max_files is None:
            if not hasattr(self, 'cache_max_files'):
                self.load_cache_settings()
            max_files = self.cache_max_files
            
        # Skip cleanup if auto-cleanup is disabled
        if hasattr(self, 'cache_auto_cleanup') and not self.cache_auto_cleanup:
            print("Automatic cache cleanup is disabled")
            return
            
        try:
            cache_dir = os.path.join(self.preview_dir, "cache")
            
            # Skip if directory doesn't exist
            if not os.path.exists(cache_dir):
                print("No cache directory found. Skipping cleanup.")
                return
                
            # Get all cache files with their modification times
            cache_files = []
            for filename in os.listdir(cache_dir):
                if filename.endswith('_cache.json'):
                    filepath = os.path.join(cache_dir, filename)
                    mtime = os.path.getmtime(filepath)
                    cache_files.append((filepath, mtime))
            
            if not cache_files:
                print("No cache files found. Skipping cleanup.")
                return
            
            # If we have more than max_files, remove oldest files
            if len(cache_files) > max_files:
                # Sort by modification time (oldest first)
                cache_files.sort(key=lambda x: x[1])
                # Delete oldest files beyond our limit
                files_to_remove = cache_files[:(len(cache_files) - max_files)]
                for filepath, _ in files_to_remove:
                    try:
                        os.remove(filepath)
                        print(f"Removed old cache file: {os.path.basename(filepath)}")
                    except Exception as e:
                        print(f"Error removing {os.path.basename(filepath)}: {e}")
                        
            # Remove any files older than max_age_days
            cutoff_time = time.time() - (max_age_days * 86400)  # 86400 seconds in a day
            for filepath, mtime in cache_files:
                if mtime < cutoff_time:
                    try:
                        os.remove(filepath)
                        print(f"Removed expired cache file: {os.path.basename(filepath)}")
                    except Exception as e:
                        print(f"Error removing {os.path.basename(filepath)}: {e}")
                        
            print(f"Cache cleanup complete. Directory: {cache_dir}")
        except Exception as e:
            print(f"Error cleaning cache: {e}")
    
    # Replace your clear_cache function with this enhanced version
    def clear_cache(self):
        """Show cache management dialog with options to clear cache and configure settings"""
        try:
            # Ensure settings are loaded
            if not hasattr(self, 'cache_max_age'):
                self.load_cache_settings()
                    
            # Create the dialog window using CTkToplevel instead of tk.Toplevel
            dialog = ctk.CTkToplevel(self)
            dialog.title("Cache Management")
            dialog.geometry("450x400")
            dialog.resizable(False, False)
            dialog.transient(self)  # Make dialog modal
            dialog.grab_set()
            
            # Count existing cache files
            cache_dir = os.path.join(self.preview_dir, "cache")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
                cache_files = []
            else:
                cache_files = [f for f in os.listdir(cache_dir) if f.endswith('_cache.json')]
            
            # Calculate cache size
            total_size = 0
            for filename in cache_files:
                filepath = os.path.join(cache_dir, filename)
                total_size += os.path.getsize(filepath)
            
            # Convert size to readable format
            if total_size < 1024:
                size_str = f"{total_size} bytes"
            elif total_size < 1024 * 1024:
                size_str = f"{total_size / 1024:.1f} KB"
            else:
                size_str = f"{total_size / (1024 * 1024):.1f} MB"
            
            # Dialog layout - use CTkFrame instead of ttk.Frame
            frame = ctk.CTkFrame(dialog, corner_radius=0)
            frame.pack(fill="both", expand=True)
            
            # Cache info section - use CTkLabel instead of ttk.Label
            ctk.CTkLabel(
                frame, 
                text="Cache Information", 
                font=("Arial", 14, "bold")
            ).pack(anchor="w", padx=20, pady=(20, 10))
            
            ctk.CTkLabel(
                frame, 
                text=f"Total cache files: {len(cache_files)}"
            ).pack(anchor="w", padx=20, pady=2)
            
            ctk.CTkLabel(
                frame, 
                text=f"Total cache size: {size_str}"
            ).pack(anchor="w", padx=20, pady=(2, 20))
            
            # Settings section
            ctk.CTkLabel(
                frame, 
                text="Cache Settings", 
                font=("Arial", 14, "bold")
            ).pack(anchor="w", padx=20, pady=(0, 10))
            
            # Auto cleanup enabled - use CTkCheckBox instead of ttk.Checkbutton
            self.auto_cleanup_var = tk.BooleanVar(value=self.cache_auto_cleanup)
            ctk.CTkCheckBox(
                frame, 
                text="Enable automatic cache cleanup", 
                variable=self.auto_cleanup_var
            ).pack(anchor="w", padx=20, pady=(0, 10))
            
            # Settings grid frame
            settings_frame = ctk.CTkFrame(frame, fg_color="transparent")
            settings_frame.pack(fill="x", padx=20, pady=5)
            
            # Max age setting
            ctk.CTkLabel(
                settings_frame, 
                text="Maximum age of cache files (days):"
            ).grid(row=0, column=0, sticky="w", pady=5)
            
            self.max_age_var = tk.StringVar(value=str(self.cache_max_age))
            max_age_entry = ctk.CTkEntry(
                settings_frame, 
                width=70, 
                textvariable=self.max_age_var
            )
            max_age_entry.grid(row=0, column=1, padx=(10, 0), pady=5)
            
            # Max files setting
            ctk.CTkLabel(
                settings_frame, 
                text="Maximum number of cache files:"
            ).grid(row=1, column=0, sticky="w", pady=5)
            
            self.max_files_var = tk.StringVar(value=str(self.cache_max_files))
            max_files_entry = ctk.CTkEntry(
                settings_frame, 
                width=70, 
                textvariable=self.max_files_var
            )
            max_files_entry.grid(row=1, column=1, padx=(10, 0), pady=5)
            
            # Buttons section
            buttons_frame = ctk.CTkFrame(frame, fg_color="transparent")
            buttons_frame.pack(pady=20)
            
            # Clear all button
            ctk.CTkButton(
                buttons_frame, 
                text="Clear All Cache", 
                command=lambda: self.perform_cache_clear(dialog, all_files=True)
            ).pack(side="left", padx=10)
            
            # Save settings button
            ctk.CTkButton(
                buttons_frame, 
                text="Save Settings", 
                command=lambda: self.save_cache_dialog_settings(dialog)
            ).pack(side="left", padx=10)
            
            # Close button
            ctk.CTkButton(
                buttons_frame, 
                text="Close", 
                command=dialog.destroy
            ).pack(side="left", padx=10)
            
            # Center the dialog on the screen
            dialog.update_idletasks()
            width = dialog.winfo_width()
            height = dialog.winfo_height()
            x = (dialog.winfo_screenwidth() // 2) - (width // 2)
            y = (dialog.winfo_screenheight() // 2) - (height // 2)
            dialog.geometry(f'{width}x{height}+{x}+{y}')
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create cache dialog: {str(e)}")
            print(f"Cache dialog error: {e}")

    def perform_cache_clear(self, dialog=None, all_files=True, rom_name=None):
        """Perform the actual cache clearing operation"""
        try:
            cache_dir = os.path.join(self.preview_dir, "cache")
            if not os.path.exists(cache_dir):
                if dialog:
                    messagebox.showinfo("Info", "No cache directory found.", parent=dialog)
                return False
            
            if all_files:
                # Clear all cache files
                deleted_count = 0
                for filename in os.listdir(cache_dir):
                    if filename.endswith('_cache.json'):
                        try:
                            os.remove(os.path.join(cache_dir, filename))
                            deleted_count += 1
                        except Exception as e:
                            print(f"Error deleting {filename}: {e}")
                
                # Also clear memory cache
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache = {}
                    
                if dialog:
                    messagebox.showinfo("Cache Cleared", 
                                    f"Successfully deleted {deleted_count} cache files.", parent=dialog)
                print(f"Cleared all cache files: {deleted_count} files deleted")
                return deleted_count > 0
            elif rom_name:
                # Clear cache for specific ROM
                cache_file = os.path.join(cache_dir, f"{rom_name}_cache.json")
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    print(f"Cleared cache for ROM: {rom_name}")
                    
                    # Also clear from memory cache if it exists
                    if hasattr(self, 'rom_data_cache') and rom_name in self.rom_data_cache:
                        del self.rom_data_cache[rom_name]
                        print(f"Cleared memory cache for ROM: {rom_name}")
                    return True
                else:
                    print(f"No cache file found for ROM: {rom_name}")
                    return False
            
            return False
        except Exception as e:
            print(f"Error clearing cache: {e}")
            if dialog:
                messagebox.showerror("Error", f"Failed to clear cache: {str(e)}", parent=dialog)
            return False
    
    def save_cache_dialog_settings(self, dialog):
        """Save settings from the cache dialog"""
        try:
            # Update instance variables with dialog values
            self.cache_auto_cleanup = self.auto_cleanup_var.get()
            
            try:
                self.cache_max_age = int(self.max_age_var.get())
                if self.cache_max_age < 1:
                    self.cache_max_age = 1
            except ValueError:
                self.cache_max_age = 7  # Default if invalid value
                
            try:
                self.cache_max_files = int(self.max_files_var.get())
                #if self.cache_max_files < 10:
                    #self.cache_max_files = 10
            except ValueError:
                self.cache_max_files = 100  # Default if invalid value
            
            # Save to file
            self.save_cache_settings()
            
            # Run cleanup with new settings if enabled
            if self.cache_auto_cleanup:
                self.clean_cache_directory(max_age_days=self.cache_max_age, max_files=self.cache_max_files)
            
            messagebox.showinfo("Settings Saved", "Cache settings have been saved.", parent=dialog)
        except Exception as e:
            print(f"Error saving cache settings: {e}")
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}", parent=dialog)
    
    def initialize_directory_structure(self):
        """Initialize the standardized directory structure"""
        self.app_dir = get_application_path()
        self.mame_dir = get_mame_parent_dir(self.app_dir)
        
        # Set up directory structure - all data will be stored in these locations
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        self.settings_dir = os.path.join(self.preview_dir, "settings")
        self.info_dir = os.path.join(self.settings_dir, "info")

        # Create these directories if they don't exist
        os.makedirs(self.preview_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        os.makedirs(self.info_dir, exist_ok=True)
        
        # Define standard paths for key files
        self.gamedata_path = os.path.join(self.settings_dir, "gamedata.json")
        self.db_path = os.path.join(self.settings_dir, "gamedata.db")
        self.settings_path = os.path.join(self.settings_dir, "control_config_settings.json")
        
        # Return if the directories were created successfully
        return (os.path.exists(self.preview_dir) and 
                os.path.exists(self.settings_dir) and 
                os.path.exists(self.info_dir))
    
    def check_db_update_needed(self):
        """Check if the SQLite database needs to be updated based on gamedata.json timestamp"""
        # Ensure gamedata.json exists first
        if not os.path.exists(self.gamedata_path):
            return False
                
        # Check if database exists
        if not os.path.exists(self.db_path):
            print(f"Database doesn't exist yet, creating at: {self.db_path}")
            return True
                
        # Get file modification timestamps
        gamedata_mtime = os.path.getmtime(self.gamedata_path)
        db_mtime = os.path.getmtime(self.db_path)
        
        # Compare timestamps - only rebuild if gamedata is newer than database
        return gamedata_mtime > db_mtime

    def on_closing(self):
        """Handle proper cleanup when closing the application"""
        print("Application closing, performing cleanup...")
        
        # Cancel any pending timers
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if attr_name.endswith('_timer') and hasattr(attr, 'cancel'):
                try:
                    attr.cancel()
                    print(f"Canceled timer: {attr_name}")
                except:
                    pass
        
        # Explicitly destroy all child windows
        for widget in self.winfo_children():
            try:
                widget.destroy()
                print(f"Destroyed widget: {widget}")
            except:
                pass
        
        # If you've opened any preview windows, make sure they're closed
        if hasattr(self, 'preview_processes'):
            for process in self.preview_processes:
                try:
                    process.terminate()
                    print(f"Terminated process: {process}")
                except:
                    pass
        
        # Explicitly destroy all custom top-level windows
        for attr_name in dir(self):
            if attr_name.endswith('_dialog') or attr_name.endswith('_window'):
                attr = getattr(self, attr_name)
                if hasattr(attr, 'destroy'):
                    try:
                        attr.destroy()
                        print(f"Destroyed window: {attr_name}")
                    except:
                        pass
        
        # Force garbage collection
        import gc
        gc.collect()
        
        # Destroy the main window
        self.destroy()
        
        # Quit the application
        self.quit()
        
        # Add an explicit exit call
        import sys
        sys.exit(0)
        
    def load_custom_configs(self):
        """Load custom configurations from cfg directory"""
        cfg_dir = os.path.join(self.mame_dir, "cfg")
        if not os.path.exists(cfg_dir):
            print(f"Config directory not found: {cfg_dir}")
            return

        for filename in os.listdir(cfg_dir):
            if filename.endswith(".cfg"):
                game_name = filename[:-4]
                full_path = os.path.join(cfg_dir, filename)
                try:
                    # Read as binary first to handle BOM
                    with open(full_path, "rb") as f:
                        content = f.read()
                    # Decode with UTF-8-SIG to handle BOM
                    self.custom_configs[game_name] = content.decode('utf-8-sig')
                except Exception as e:
                    print(f"Error loading {filename}: {e}")

        print(f"Loaded {len(self.custom_configs)} custom configurations")
    
    def parse_cfg_controls(self, cfg_content):
        """Parse MAME cfg file to extract control mappings with better error handling"""
        controls = {}
        try:
            print(f"Parsing CFG content (length: {len(cfg_content)})")
            import xml.etree.ElementTree as ET
            from io import StringIO
            
            # Parse the XML content
            parser = ET.XMLParser(encoding='utf-8')
            tree = ET.parse(StringIO(cfg_content), parser=parser)
            root = tree.getroot()
            
            # Find all port elements under input
            input_elem = root.find('.//input')
            if input_elem is not None:
                print("Found input element")
                for port in input_elem.findall('port'):
                    control_type = port.get('type')
                    if control_type and control_type.startswith('P') and ('BUTTON' in control_type or 'JOYSTICK' in control_type):
                        # Find the newseq element for the mapping
                        newseq = port.find('.//newseq')
                        if newseq is not None and newseq.text:
                            mapping = newseq.text.strip()
                            controls[control_type] = mapping
                            print(f"Found mapping: {control_type} -> {mapping}")
                
                print(f"Found {len(controls)} control mappings")
                return controls
            else:
                print("No input element found in XML")
                # Fallback: try to parse the text directly using regex
                try:
                    import re
                    mappings = re.findall(r'<port type="([^"]*)".*?<newseq.*?>(.*?)</newseq>', cfg_content, re.DOTALL)
                    if mappings:
                        for control_type, mapping in mappings:
                            if control_type.startswith('P') and ('BUTTON' in control_type or 'JOYSTICK' in control_type):
                                controls[control_type] = mapping.strip()
                                print(f"Found mapping via regex: {control_type} -> {mapping.strip()}")
                    print(f"Found {len(controls)} control mappings via regex")
                    return controls
                except Exception as regex_error:
                    print(f"Regex parsing failed: {regex_error}")
                    return {}
        except ET.ParseError as e:
            print(f"XML parsing failed with error: {str(e)}")
            print("First 100 chars of content:", repr(cfg_content[:100]))
        except Exception as e:
            print(f"Unexpected error parsing cfg: {str(e)}")
            import traceback
            traceback.print_exc()
            
        # If we reach here, something went wrong
        print("Fallback: returning empty controls dictionary")
        return controls
    
    def load_default_config(self):
        """Load the default MAME control configuration"""
        # Look in the cfg directory
        cfg_dir = os.path.join(self.mame_dir, "cfg")
        default_cfg_path = os.path.join(cfg_dir, "default.cfg")
        
        print(f"Looking for default.cfg at: {default_cfg_path}")
        if os.path.exists(default_cfg_path):
            try:
                print(f"Loading default config from: {default_cfg_path}")
                # Read file content
                with open(default_cfg_path, "rb") as f:
                    content = f.read()
                
                # Parse the default mappings
                self.default_controls = self.parse_default_cfg(content.decode('utf-8-sig'))
                
                # Debug output
                print(f"Loaded {len(self.default_controls)} default control mappings")
                for i, (k, v) in enumerate(list(self.default_controls.items())[:5]):
                    print(f"  Sample {i+1}: {k} -> {v}")
                    
                return True
            except Exception as e:
                print(f"Error loading default config: {e}")
                import traceback
                traceback.print_exc()
                self.default_controls = {}
                return False
        else:
            print("No default.cfg found in cfg directory")
            self.default_controls = {}
            return False

    def parse_default_cfg(self, cfg_content):
        """Special parser just for default.cfg - extract ONLY joystick mappings"""
        controls = {}
        try:
            import xml.etree.ElementTree as ET
            from io import StringIO
            import re
            
            # Parse the XML content
            parser = ET.XMLParser(encoding='utf-8')
            tree = ET.parse(StringIO(cfg_content), parser)
            root = tree.getroot()
            
            # Find the input section
            input_elem = root.find('.//input')
            if input_elem is not None:
                print("Found input element in default.cfg")
                joycode_count = 0
                for port in input_elem.findall('port'):
                    control_type = port.get('type')
                    if control_type:
                        # Find the standard sequence
                        newseq = port.find('./newseq[@type="standard"]')
                        if newseq is not None and newseq.text:
                            full_mapping = newseq.text.strip()
                            
                            # Extract only JOYCODE parts using regex
                            joycode_match = re.search(r'(JOYCODE_\d+_[A-Z0-9_]+)', full_mapping)
                            if joycode_match:
                                joycode = joycode_match.group(1)
                                controls[control_type] = joycode
                                joycode_count += 1
            
            print(f"Parsed {len(controls)} joystick controls from default.cfg (found {joycode_count} JOYCODE entries)")
        except Exception as e:
            print(f"Error parsing default.cfg: {e}")
            import traceback
            traceback.print_exc()
        
        return controls

    def toggle_fullscreen(self, event=None):
        """Toggle fullscreen state"""
        self.fullscreen = not self.fullscreen
        self.attributes('-fullscreen', self.fullscreen)
        
    def exit_fullscreen(self, event=None):
        """Exit fullscreen mode"""
        self.fullscreen = False
        self.attributes('-fullscreen', False)

    def find_mame_directory(self) -> Optional[str]:
        """Find the MAME directory containing necessary files"""
        # 1. Check application directory
        app_dir = get_application_path()
        app_gamedata = os.path.join(app_dir, "gamedata.json")
        app_preview_gamedata = os.path.join(app_dir, "preview", "gamedata.json")

        if os.path.exists(app_gamedata):
            print(f"Using bundled gamedata.json: {app_dir}")
            return app_dir
        elif os.path.exists(app_preview_gamedata):
            print(f"Using external preview/gamedata.json: {app_dir}")
            return app_dir

        # 2. Check current script directory
        current_dir = os.path.abspath(os.path.dirname(__file__))
        current_gamedata = os.path.join(current_dir, "gamedata.json")
        current_preview_gamedata = os.path.join(current_dir, "preview", "gamedata.json")

        if os.path.exists(current_gamedata):
            print(f"Found MAME directory: {current_dir}")
            return current_dir
        elif os.path.exists(current_preview_gamedata):
            print(f"Found MAME directory via preview/gamedata.json: {current_dir}")
            return current_dir

        # 3. Check common MAME install paths (and their preview folders)
        common_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), "MAME"),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), "MAME"),
            "C:\\MAME",
            "D:\\MAME"
        ]

        for path in common_paths:
            gamedata_path = os.path.join(path, "gamedata.json")
            preview_gamedata_path = os.path.join(path, "preview", "gamedata.json")

            if os.path.exists(gamedata_path):
                print(f"Found MAME directory: {path}")
                return path
            elif os.path.exists(preview_gamedata_path):
                print(f"Found MAME directory via preview/gamedata.json: {path}")
                return path

        print("Error: gamedata.json not found in known locations")
        return None


    def toggle_xinput(self):
        """Handle toggling between JOYCODE and XInput mappings"""
        self.use_xinput = self.xinput_toggle.get()
        print(f"XInput toggle set to: {self.use_xinput}")
        
        # Refresh the current game display if one is selected
        if self.current_game and self.selected_line is not None:
            # Store the current scroll position
            scroll_pos = self.control_frame._scrollbar.get()
            
            # Create a mock event with coordinates for the selected line
            class MockEvent:
                def __init__(self_mock, line_num):
                    # Calculate position to hit the middle of the line
                    bbox = self.game_list.bbox(f"{line_num}.0")
                    if bbox:
                        self_mock.x = bbox[0] + 5  # A bit to the right of line start
                        self_mock.y = bbox[1] + 5  # A bit below line top
                    else:
                        self_mock.x = 5
                        self_mock.y = line_num * 20  # Approximate line height
            
            # Create the mock event targeting our current line
            mock_event = MockEvent(self.selected_line)
            
            # Force a full refresh of the display
            self.on_game_select(mock_event)
            
            # Restore scroll position
            self.control_frame._scrollbar.set(*scroll_pos)

    def create_layout(self):
        """Create the main application layout with a modern styled approach"""
        debug_print("Creating application layout...")
        
        try:
            # Configure main grid with 3 rows (header, main content, status)
            self.grid_columnconfigure(0, weight=1)     # Single column spans the width
            self.grid_rowconfigure(0, weight=0)        # Top header (fixed height)
            self.grid_rowconfigure(1, weight=1)        # Main content area (expands)
            self.grid_rowconfigure(2, weight=0)        # Status bar (fixed)
            
            debug_print("Main grid configuration set")

            # Create beautiful header with gradient effect and logo
            self.create_header()
            
            # Create main content area with split panels
            self.create_main_content()
            
            # Create status bar
            self.create_status_bar()
            
            debug_print("Layout creation complete")
        except Exception as e:
            debug_print(f"ERROR creating layout: {e}")
            traceback.print_exc()
            messagebox.showerror("Layout Error", f"Failed to create layout: {e}")

    def create_header(self):
        """Create a modern header with logo and gradient effect"""
        # Header frame
        self.header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=self.colors["bg_dark"], height=70)
        self.header_frame.grid(row=0, column=0, sticky="ew")
        
        # Configure the header to have three sections
        self.header_frame.grid_columnconfigure(0, weight=0)  # Logo (fixed width)
        self.header_frame.grid_columnconfigure(1, weight=1)  # Title (expandable)
        self.header_frame.grid_columnconfigure(2, weight=0)  # Actions (fixed width)
        self.header_frame.grid_rowconfigure(0, weight=1)

        # Try to load and display logo (if available)
        try:
            logo_path = os.path.join(self.app_dir, "assets", "mame_logo.png")
            if os.path.exists(logo_path):
                # Use PIL to create a properly sized logo
                logo_image = Image.open(logo_path)
                logo_image = logo_image.resize((40, 40), Image.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
                
                logo_label = ctk.CTkLabel(self.header_frame, image=self.logo_photo, text="")
                logo_label.grid(row=0, column=0, padx=(20, 10), pady=10)
            else:
                # Create a fallback colorful logo using a frame with rounded corners
                logo_frame = ctk.CTkFrame(self.header_frame, width=40, height=40, corner_radius=10, 
                                       fg_color=self.colors["primary"])
                logo_frame.grid(row=0, column=0, padx=(20, 10), pady=10)
                logo_frame.grid_propagate(False)
                
                # Add text "M" to the logo frame
                logo_text = ctk.CTkLabel(logo_frame, text="M", font=("Arial", 20, "bold"))
                logo_text.place(relx=0.5, rely=0.5, anchor="center")
        except Exception as e:
            print(f"Could not load logo: {e}")
            # No logo, just continue
        
        # App title with a modern font
        title_label = ctk.CTkLabel(
            self.header_frame, 
            text="MAME Controls Configuration",
            font=("Arial", 22, "bold"),
            text_color=self.colors["text"]
        )
        title_label.grid(row=0, column=1, padx=20, pady=10, sticky="w")
        
        # Action buttons container on the right
        action_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        action_frame.grid(row=0, column=2, padx=20, pady=5, sticky="e")
        
        # Preview button with icon effect
        self.preview_button = ctk.CTkButton(
            action_frame,
            text="Preview Controls",
            command=self.show_preview,
            width=150,
            height=36,
            corner_radius=8,
            font=("Arial", 13, "bold"),
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"]
        )
        self.preview_button.pack(side="left", padx=10)
        
        # Settings button with gear icon (simulated)
        self.settings_button = ctk.CTkButton(
            action_frame,
            text="⚙️ Settings",
            command=self.show_settings,
            width=120,
            height=36,
            corner_radius=8,
            font=("Arial", 13, "bold")
        )
        self.settings_button.pack(side="left", padx=10)

    def create_main_content(self):
        """Create the main content area with modern styling"""
        # Main content container
        self.main_content = ctk.CTkFrame(self, corner_radius=0, fg_color=self.colors["bg_medium"])
        self.main_content.grid(row=1, column=0, sticky="nsew")
        
        # Configure column widths - 35% for left panel, 65% for right panel
        self.main_content.grid_columnconfigure(0, weight=35)
        self.main_content.grid_columnconfigure(1, weight=65)
        self.main_content.grid_rowconfigure(0, weight=1)
        
        # Create left panel (ROM list with category tabs)
        self.create_left_panel()
        
        # Create right panel (control details)
        self.create_right_panel()

    def create_left_panel(self):
        """Create the left panel with ROM list and filtering options - with reduced gaps"""
        # Left panel container with rounded corners and shadow effect
        self.left_panel = ctk.CTkFrame(
            self.main_content,
            corner_radius=10,
            fg_color=self.colors["bg_light"]
        )
        self.left_panel.grid(row=0, column=0, padx=(20, 10), pady=20, sticky="nsew")
        
        # Configure left panel layout
        self.left_panel.grid_columnconfigure(0, weight=1)
        self.left_panel.grid_rowconfigure(0, weight=0)  # Title (fixed)
        self.left_panel.grid_rowconfigure(1, weight=0)  # Search bar (fixed)
        self.left_panel.grid_rowconfigure(2, weight=0)  # Filter tabs (fixed)
        self.left_panel.grid_rowconfigure(3, weight=1)  # ROM list (expandable)
        self.left_panel.grid_rowconfigure(4, weight=0)  # Stats label (fixed)
        
        # Title for ROM list section - REDUCED TOP PADDING
        rom_title = ctk.CTkLabel(
            self.left_panel,
            text="Available ROMs",
            font=("Arial", 16, "bold"),
            text_color=self.colors["text"]
        )
        rom_title.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")
        
        # Create search bar with icon - REDUCED VERTICAL PADDING
        search_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        search_frame.grid(row=1, column=0, padx=15, pady=(0, 5), sticky="ew")
        
        # Search icon (simulated with text)
        search_icon = ctk.CTkLabel(search_frame, text="🔍", font=("Arial", 14))
        search_icon.pack(side="left", padx=(0, 5))
        
        # Search input
        self.search_var = StringVar()
        self.search_var.trace("w", self.filter_games)
        self.search_entry = ctk.CTkEntry(
            search_frame, 
            placeholder_text="Search games...",
            textvariable=self.search_var,
            height=32,
            corner_radius=8,
            border_width=0
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        
        # Create filter buttons - REDUCED VERTICAL PADDING
        filter_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        filter_frame.grid(row=2, column=0, padx=15, pady=(0, 5), sticky="ew")
        
        # Filter options
        self.filter_var = StringVar(value="all")
        
        filters = [
            ("All", "all"),
            ("With Controls", "with_controls"),
            ("No Controls", "no_controls"),
            ("Custom Config", "custom")
        ]
        
        for i, (text, value) in enumerate(filters):
            filter_button = ctk.CTkButton(
                filter_frame,
                text=text,
                command=lambda v=value: self.set_filter(v),
                width=80,
                height=28,
                corner_radius=4,
                fg_color=self.colors["primary"] if value == "all" else "transparent",
                text_color=self.colors["text"] if value == "all" else self.colors["text_secondary"],
                hover_color=self.colors["accent"]
            )
            filter_button.pack(side="left", padx=(0 if i == 0 else 5, 0), fill="x", expand=True)
            
            # Store reference to buttons for updating active state
            setattr(self, f"filter_btn_{value}", filter_button)
        
        # Game list with modern styling - MORE VERTICAL SPACE
        self.game_list_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.game_list_frame.grid(row=3, column=0, padx=15, pady=(0, 5), sticky="nsew")
        self.game_list_frame.grid_columnconfigure(0, weight=1)
        self.game_list_frame.grid_rowconfigure(0, weight=1)
        
        self.game_list = ctk.CTkTextbox(
            self.game_list_frame, 
            font=("Arial", 13),
            fg_color=self.colors["bg_light"],
            text_color=self.colors["text"],
            corner_radius=5,
            border_width=0
        )
        self.game_list.grid(row=0, column=0, sticky="nsew")
        
        # Configure highlight colors for selected games
        self.game_list._textbox.tag_configure(
            self.highlight_tag, 
            background=self.colors["highlight"], 
            foreground=self.colors["text"]
        )
        
        # Bind click event
        self.game_list.bind("<Button-1>", self.on_game_select)
        
        # Stats counter at the bottom - REDUCED BOTTOM PADDING
        self.stats_label = ctk.CTkLabel(
            self.left_panel,
            text="Loading...",
            font=("Arial", 12),
            text_color=self.colors["text_secondary"]
        )
        self.stats_label.grid(row=4, column=0, padx=15, pady=(0, 10), sticky="w")

    def create_right_panel(self):
        """Create the right panel with attractive control display"""
        # Right panel container with rounded corners and shadow effect
        self.right_panel = ctk.CTkFrame(
            self.main_content,
            corner_radius=10,
            fg_color=self.colors["bg_light"]
        )
        self.right_panel.grid(row=0, column=1, padx=(10, 20), pady=20, sticky="nsew")
        
        # Configure right panel layout
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(0, weight=0)  # Game title (fixed)
        self.right_panel.grid_rowconfigure(1, weight=0)  # Game info (fixed)
        self.right_panel.grid_rowconfigure(2, weight=0)  # Control options (fixed)
        self.right_panel.grid_rowconfigure(3, weight=1)  # Controls display (expandable)
        
        # Game title with larger elegant font
        self.game_title = ctk.CTkLabel(
            self.right_panel,
            text="Select a game",
            font=("Arial", 24, "bold"),
            text_color=self.colors["text"],
            wraplength=600
        )
        self.game_title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        # Options section for controls display
        options_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        options_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        # XInput toggle with modern design
        self.xinput_toggle = ctk.CTkSwitch(
            options_frame,
            text="Use XInput Mappings",
            command=self.toggle_xinput,
            font=("Arial", 13),
            progress_color=self.colors["primary"],
            switch_height=22, 
            switch_width=44
        )
        self.xinput_toggle.select()  # Set it on by default
        self.xinput_toggle.pack(side="left", padx=(0, 20))
        
        # Action buttons for the right panel
        action_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        action_frame.pack(side="right")
        
        # Edit controls button
        self.edit_button = ctk.CTkButton(
            action_frame,
            text="Edit Controls",
            command=self.edit_controls,
            corner_radius=6,
            height=32,
            width=120,
            font=("Arial", 13),
            fg_color=self.colors["accent"]
        )
        self.edit_button.pack(side="left", padx=10)
        
        # Export button
        self.export_button = ctk.CTkButton(
            action_frame,
            text="Export",
            command=self.export_current,
            corner_radius=6,
            height=32,
            width=100,
            font=("Arial", 13)
        )
        self.export_button.pack(side="left", padx=10)
        
        # Controls display frame - the main content of the right panel
        self.control_frame_container = ctk.CTkFrame(
            self.right_panel,
            corner_radius=8,
            fg_color=self.colors["bg_medium"]
        )
        self.control_frame_container.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.control_frame_container.grid_columnconfigure(0, weight=1)
        self.control_frame_container.grid_rowconfigure(0, weight=1)
        
        # Create scrollable frame for controls
        self.control_frame = ctk.CTkScrollableFrame(
            self.control_frame_container,
            fg_color="transparent"
        )
        self.control_frame.grid(row=0, column=0, sticky="nsew")
        
        # Initial display message
        self.control_placeholder = ctk.CTkLabel(
            self.control_frame,
            text="Select a game to view controls",
            font=("Arial", 14),
            text_color=self.colors["text_secondary"]
        )
        self.control_placeholder.pack(padx=20, pady=40)
    
    def create_status_bar(self):
        """Create a status bar at the bottom of the window"""
        # Status bar frame
        self.status_bar = ctk.CTkFrame(self, corner_radius=0, fg_color=self.colors["bg_dark"], height=24)
        self.status_bar.grid(row=2, column=0, sticky="ew")
        
        # Configure status bar layout
        self.status_bar.grid_columnconfigure(0, weight=1)
        self.status_bar.grid_columnconfigure(1, weight=0)
        
        # Status message on the left
        self.status_message = ctk.CTkLabel(
            self.status_bar,
            text="Ready",
            font=("Arial", 11),
            text_color=self.colors["text_secondary"]
        )
        self.status_message.grid(row=0, column=0, padx=15, pady=2, sticky="w")
        
        # Version info on the right
        version_label = ctk.CTkLabel(
            self.status_bar,
            text="v1.0.0",
            font=("Arial", 11),
            text_color=self.colors["text_secondary"]
        )
        version_label.grid(row=0, column=1, padx=15, pady=2, sticky="e")
    
    def show_settings(self):
        """Show a modern settings dialog with tabs for different setting categories"""
        # Create settings dialog
        settings_dialog = ctk.CTkToplevel(self)
        settings_dialog.title("MAME Controls Settings")
        settings_dialog.geometry("650x500")
        settings_dialog.transient(self)
        settings_dialog.grab_set()
        
        # Make dialog modal and center on screen
        settings_dialog.update_idletasks()
        width = settings_dialog.winfo_width()
        height = settings_dialog.winfo_height()
        x = (settings_dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (settings_dialog.winfo_screenheight() // 2) - (height // 2)
        settings_dialog.geometry(f'{width}x{height}+{x}+{y}')
        
        # Add some padding around the content
        main_frame = ctk.CTkFrame(settings_dialog, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title at the top
        title_label = ctk.CTkLabel(
            main_frame, 
            text="Settings",
            font=("Arial", 20, "bold"),
            text_color=self.colors["text"]
        )
        title_label.pack(anchor="w", pady=(0, 15))
        
        # Create tabview for different setting categories
        tabs = ctk.CTkTabview(
            main_frame,
            fg_color=self.colors["bg_light"],
            segmented_button_fg_color=self.colors["bg_medium"],
            segmented_button_selected_color=self.colors["primary"],
            segmented_button_selected_hover_color=self.colors["primary_hover"],
            segmented_button_unselected_color=self.colors["bg_medium"]
        )
        tabs.pack(fill="both", expand=True)
        
        # Add tabs
        general_tab = tabs.add("General")
        appearance_tab = tabs.add("Appearance")
        cache_tab = tabs.add("Cache")
        export_tab = tabs.add("Export")
        
        # ====== GENERAL SETTINGS ======
        general_frame = ctk.CTkFrame(general_tab, fg_color="transparent")
        general_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # MAME Directory setting
        dir_frame = ctk.CTkFrame(general_frame, fg_color="transparent")
        dir_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            dir_frame,
            text="MAME Directory:",
            font=("Arial", 13),
            width=120
        ).pack(side="left", padx=(0, 10))
        
        mame_dir_var = ctk.StringVar(value=self.mame_dir if hasattr(self, "mame_dir") else "")
        mame_dir_entry = ctk.CTkEntry(
            dir_frame,
            textvariable=mame_dir_var,
            width=350,
            height=32,
            border_width=0
        )
        mame_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        def browse_mame_dir():
            directory = tk.filedialog.askdirectory(
                initialdir=mame_dir_var.get(),
                title="Select MAME Directory"
            )
            if directory:
                mame_dir_var.set(directory)
        
        ctk.CTkButton(
            dir_frame,
            text="Browse",
            command=browse_mame_dir,
            width=80,
            height=32,
            corner_radius=6
        ).pack(side="left")
        
        # ROM Directory setting
        rom_dir_frame = ctk.CTkFrame(general_frame, fg_color="transparent")
        rom_dir_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            rom_dir_frame,
            text="ROM Directory:",
            font=("Arial", 13),
            width=120
        ).pack(side="left", padx=(0, 10))
        
        rom_dir_var = ctk.StringVar(value=os.path.join(self.mame_dir, "roms") if hasattr(self, "mame_dir") else "")
        rom_dir_entry = ctk.CTkEntry(
            rom_dir_frame,
            textvariable=rom_dir_var,
            width=350,
            height=32,
            border_width=0
        )
        rom_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        def browse_rom_dir():
            directory = tk.filedialog.askdirectory(
                initialdir=rom_dir_var.get(),
                title="Select ROM Directory"
            )
            if directory:
                rom_dir_var.set(directory)
        
        ctk.CTkButton(
            rom_dir_frame,
            text="Browse",
            command=browse_rom_dir,
            width=80,
            height=32,
            corner_radius=6
        ).pack(side="left")
        
        # Startup options
        startup_frame = ctk.CTkFrame(general_frame, fg_color="transparent")
        startup_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            startup_frame,
            text="Startup Options",
            font=("Arial", 15, "bold")
        ).pack(anchor="w", pady=(10, 5))
        
        # Checkbox options for startup
        auto_scan_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            startup_frame,
            text="Auto-scan ROM directory on startup",
            variable=auto_scan_var,
            font=("Arial", 13),
            checkbox_width=22,
            checkbox_height=22
        ).pack(anchor="w", pady=5)
        
        start_fullscreen_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            startup_frame,
            text="Start in fullscreen mode",
            variable=start_fullscreen_var,
            font=("Arial", 13),
            checkbox_width=22,
            checkbox_height=22
        ).pack(anchor="w", pady=5)
        
        # ====== APPEARANCE SETTINGS ======
        appearance_frame = ctk.CTkFrame(appearance_tab, fg_color="transparent")
        appearance_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Theme selection
        theme_frame = ctk.CTkFrame(appearance_frame, fg_color="transparent")
        theme_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            theme_frame,
            text="Color Theme:",
            font=("Arial", 13),
            width=120
        ).pack(side="left")
        
        # Theme options
        theme_var = ctk.StringVar(value="dark-blue")
        themes = ["dark-blue", "blue", "green", "dark-green", "red"]
        
        theme_combobox = ctk.CTkComboBox(
            theme_frame,
            values=themes,
            variable=theme_var,
            width=200,
            height=32,
            corner_radius=6
        )
        theme_combobox.pack(side="left", padx=10)
        
        # Preview theme colors
        theme_preview = ctk.CTkFrame(
            appearance_frame,
            width=150,
            height=80,
            corner_radius=8
        )
        theme_preview.pack(anchor="w", pady=10)
        theme_preview.grid_propagate(False)
        
        # UI Scale
        scale_frame = ctk.CTkFrame(appearance_frame, fg_color="transparent")
        scale_frame.pack(fill="x", pady=(20, 10))
        
        ctk.CTkLabel(
            scale_frame,
            text="UI Scale:",
            font=("Arial", 13)
        ).pack(anchor="w")
        
        scale_var = ctk.DoubleVar(value=100.0)
        scale_slider = ctk.CTkSlider(
            scale_frame,
            from_=80,
            to=120,
            variable=scale_var,
            width=400,
            progress_color=self.colors["primary"]
        )
        scale_slider.pack(anchor="w", pady=5)
        
        scale_value_label = ctk.CTkLabel(
            scale_frame,
            text="100%",
            font=("Arial", 13)
        )
        scale_value_label.pack(anchor="w")
        
        # Update scale label when slider changes
        def update_scale_label(event=None):
            scale_value_label.configure(text=f"{int(scale_var.get())}%")
        
        scale_slider.bind("<Motion>", update_scale_label)
        scale_slider.bind("<ButtonRelease-1>", update_scale_label)
        
        # Font settings
        font_frame = ctk.CTkFrame(appearance_frame, fg_color="transparent")
        font_frame.pack(fill="x", pady=(20, 10))
        
        ctk.CTkLabel(
            font_frame,
            text="Font Settings:",
            font=("Arial", 15, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        # Font family
        font_family_frame = ctk.CTkFrame(font_frame, fg_color="transparent")
        font_family_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            font_family_frame,
            text="Font Family:",
            width=120,
            font=("Arial", 13)
        ).pack(side="left", padx=(0, 10))
        
        font_var = ctk.StringVar(value="Arial")
        font_options = ["Arial", "Helvetica", "Segoe UI", "Roboto", "Verdana", "Tahoma"]
        
        font_combobox = ctk.CTkComboBox(
            font_family_frame,
            values=font_options,
            variable=font_var,
            width=200,
            height=32,
            corner_radius=6
        )
        font_combobox.pack(side="left")
        
        # Font size
        font_size_frame = ctk.CTkFrame(font_frame, fg_color="transparent")
        font_size_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            font_size_frame,
            text="Font Size:",
            width=120,
            font=("Arial", 13)
        ).pack(side="left", padx=(0, 10))
        
        font_size_var = ctk.IntVar(value=13)
        font_sizes = [str(i) for i in range(10, 21)]
        
        font_size_combobox = ctk.CTkComboBox(
            font_size_frame,
            values=font_sizes,
            variable=font_size_var,
            width=200,
            height=32,
            corner_radius=6
        )
        font_size_combobox.pack(side="left")
        
        # ====== CACHE SETTINGS ======
        cache_frame = ctk.CTkFrame(cache_tab, fg_color="transparent")
        cache_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Cache info
        cache_info_frame = ctk.CTkFrame(
            cache_frame,
            fg_color=self.colors["bg_medium"],
            corner_radius=8
        )
        cache_info_frame.pack(fill="x", pady=10, padx=5)
        
        # Calculate cache size
        cache_dir = os.path.join(self.preview_dir, "cache") if hasattr(self, "preview_dir") else ""
        cache_size = 0
        cache_files = 0
        
        if os.path.exists(cache_dir):
            for filename in os.listdir(cache_dir):
                if filename.endswith('_cache.json'):
                    file_path = os.path.join(cache_dir, filename)
                    cache_size += os.path.getsize(file_path)
                    cache_files += 1
        
        # Format cache size
        if cache_size < 1024:
            size_str = f"{cache_size} bytes"
        elif cache_size < 1024 * 1024:
            size_str = f"{cache_size / 1024:.1f} KB"
        else:
            size_str = f"{cache_size / (1024 * 1024):.1f} MB"
        
        ctk.CTkLabel(
            cache_info_frame,
            text="Cache Information",
            font=("Arial", 15, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(
            cache_info_frame,
            text=f"Cache Files: {cache_files}",
            font=("Arial", 13)
        ).pack(anchor="w", padx=15, pady=2)
        
        ctk.CTkLabel(
            cache_info_frame,
            text=f"Total Size: {size_str}",
            font=("Arial", 13)
        ).pack(anchor="w", padx=15, pady=(2, 15))
        
        # Cache settings
        cache_settings_frame = ctk.CTkFrame(cache_frame, fg_color="transparent")
        cache_settings_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            cache_settings_frame,
            text="Cache Settings",
            font=("Arial", 15, "bold")
        ).pack(anchor="w", pady=(10, 5))
        
        # Enable auto cleanup
        auto_cleanup_var = ctk.BooleanVar(value=hasattr(self, 'cache_auto_cleanup') and self.cache_auto_cleanup)
        ctk.CTkCheckBox(
            cache_settings_frame,
            text="Enable automatic cache cleanup",
            variable=auto_cleanup_var,
            font=("Arial", 13),
            checkbox_width=22,
            checkbox_height=22
        ).pack(anchor="w", pady=5)
        
        # Max age
        max_age_frame = ctk.CTkFrame(cache_settings_frame, fg_color="transparent")
        max_age_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            max_age_frame,
            text="Maximum cache age (days):",
            width=200,
            font=("Arial", 13)
        ).pack(side="left")
        
        max_age_var = ctk.StringVar(value=str(getattr(self, 'cache_max_age', 7)))
        max_age_entry = ctk.CTkEntry(
            max_age_frame,
            textvariable=max_age_var,
            width=80,
            height=32,
            border_width=0
        )
        max_age_entry.pack(side="left", padx=10)
        
        # Max files
        max_files_frame = ctk.CTkFrame(cache_settings_frame, fg_color="transparent")
        max_files_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            max_files_frame,
            text="Maximum number of cache files:",
            width=200,
            font=("Arial", 13)
        ).pack(side="left")
        
        max_files_var = ctk.StringVar(value=str(getattr(self, 'cache_max_files', 100)))
        max_files_entry = ctk.CTkEntry(
            max_files_frame,
            textvariable=max_files_var,
            width=80,
            height=32,
            border_width=0
        )
        max_files_entry.pack(side="left", padx=10)
        
        # Cache actions
        cache_actions_frame = ctk.CTkFrame(cache_frame, fg_color="transparent")
        cache_actions_frame.pack(fill="x", pady=10)
        
        def clear_all_cache():
            if messagebox.askyesno(
                "Confirm Cache Clear",
                "Are you sure you want to clear all cache files?\nThis action cannot be undone.",
                parent=settings_dialog
            ):
                self.perform_cache_clear(dialog=settings_dialog, all_files=True)
        
        ctk.CTkButton(
            cache_actions_frame,
            text="Clear All Cache",
            command=clear_all_cache,
            width=150,
            height=32,
            fg_color=self.colors["error"],
            hover_color="#b30000"
        ).pack(side="left", padx=(0, 10))
        
        # ====== EXPORT SETTINGS ======
        export_frame = ctk.CTkFrame(export_tab, fg_color="transparent")
        export_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Default export directory
        export_dir_frame = ctk.CTkFrame(export_frame, fg_color="transparent")
        export_dir_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            export_dir_frame,
            text="Default Export Directory:",
            font=("Arial", 13),
            width=170
        ).pack(side="left", padx=(0, 10))
        
        # Default to preview/images directory
        images_dir = os.path.join(self.preview_dir, "images") if hasattr(self, "preview_dir") else ""
        export_dir_var = ctk.StringVar(value=images_dir)
        
        export_dir_entry = ctk.CTkEntry(
            export_dir_frame,
            textvariable=export_dir_var,
            width=300,
            height=32,
            border_width=0
        )
        export_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        def browse_export_dir():
            directory = tk.filedialog.askdirectory(
                initialdir=export_dir_var.get(),
                title="Select Export Directory"
            )
            if directory:
                export_dir_var.set(directory)
        
        ctk.CTkButton(
            export_dir_frame,
            text="Browse",
            command=browse_export_dir,
            width=80,
            height=32,
            corner_radius=6
        ).pack(side="left")
        
        # Export quality
        quality_frame = ctk.CTkFrame(export_frame, fg_color="transparent")
        quality_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            quality_frame,
            text="Default Image Quality:",
            font=("Arial", 13),
            width=170
        ).pack(side="left", padx=(0, 10))
        
        quality_var = ctk.IntVar(value=90)
        quality_slider = ctk.CTkSlider(
            quality_frame,
            from_=50,
            to=100,
            variable=quality_var,
            width=300,
            progress_color=self.colors["primary"]
        )
        quality_slider.pack(side="left", padx=(0, 10))
        
        quality_label = ctk.CTkLabel(
            quality_frame,
            text="90%",
            font=("Arial", 13),
            width=50
        )
        quality_label.pack(side="left")
        
        # Update quality label when slider changes
        def update_quality_label(event=None):
            quality_label.configure(text=f"{int(quality_var.get())}%")
        
        quality_slider.bind("<Motion>", update_quality_label)
        quality_slider.bind("<ButtonRelease-1>", update_quality_label)
        
        # Image size options
        size_frame = ctk.CTkFrame(export_frame, fg_color="transparent")
        size_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            size_frame,
            text="Default Image Size:",
            font=("Arial", 13),
            width=170
        ).pack(side="left", padx=(0, 10))
        
        size_var = ctk.StringVar(value="1280x720")
        sizes = ["640x480", "800x600", "1024x768", "1280x720", "1920x1080"]
        
        size_combobox = ctk.CTkComboBox(
            size_frame,
            values=sizes,
            variable=size_var,
            width=150,
            height=32,
            corner_radius=6
        )
        size_combobox.pack(side="left")
        
        # ====== FOOTER BUTTONS ======
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(20, 0))
        
        # Cancel button
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=settings_dialog.destroy,
            width=100,
            height=36,
            corner_radius=8,
            fg_color=self.colors["bg_medium"],
            hover_color=self.colors["bg_light"],
            text_color=self.colors["text"]
        ).pack(side="right", padx=(10, 0))
        
        # Save settings function
        def save_settings():
            try:
                # Update settings from form values
                settings = {
                    "mame_dir": mame_dir_var.get(),
                    "rom_dir": rom_dir_var.get(),
                    "auto_scan": auto_scan_var.get(),
                    "start_fullscreen": start_fullscreen_var.get(),
                    "theme": theme_var.get(),
                    "ui_scale": scale_var.get(),
                    "font_family": font_var.get(),
                    "font_size": font_size_var.get(),
                    "cache_auto_cleanup": auto_cleanup_var.get(),
                    "cache_max_age": int(max_age_var.get()),
                    "cache_max_files": int(max_files_var.get()),
                    "export_dir": export_dir_var.get(),
                    "export_quality": quality_var.get(),
                    "export_size": size_var.get()
                }
                
                # Save to settings file
                with open(self.settings_path, 'w') as f:
                    json.dump(settings, f, indent=4)
                
                # Update current instance settings
                self.cache_auto_cleanup = auto_cleanup_var.get()
                self.cache_max_age = int(max_age_var.get())
                self.cache_max_files = int(max_files_var.get())
                
                # Apply theme changes
                ctk.set_appearance_mode("dark" if "dark" in theme_var.get() else "light")
                ctk.set_default_color_theme(theme_var.get())
                
                # Close dialog
                settings_dialog.destroy()
                
                # Show success message
                messagebox.showinfo("Settings Saved", "Settings have been saved successfully.\nSome changes will take effect after restarting the application.")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings: {str(e)}", parent=settings_dialog)
        
        # Save button
        ctk.CTkButton(
            button_frame,
            text="Save Settings",
            command=save_settings,
            width=150,
            height=36,
            corner_radius=8,
            font=("Arial", 13, "bold"),
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"]
        ).pack(side="right", padx=(10, 0))
        
        # Set initial active tab
        tabs.set("General")
    
    def set_filter(self, filter_value):
        """Set active filter and update the game list"""
        self.filter_var.set(filter_value)
        
        # Update button styling to show active state
        for value in ["all", "with_controls", "no_controls", "custom"]:
            btn = getattr(self, f"filter_btn_{value}", None)
            if btn:
                if value == filter_value:
                    btn.configure(
                        fg_color=self.colors["primary"],
                        text_color=self.colors["text"]
                    )
                else:
                    btn.configure(
                        fg_color="transparent",
                        text_color=self.colors["text_secondary"]
                    )
        
        # Apply the filter
        self.update_game_list()
    
    def edit_controls(self):
        """Edit controls for the current game"""
        if not self.current_game:
            messagebox.showinfo("No Game Selected", "Please select a game first")
            return
        
        # Get game data
        game_data = self.get_game_data(self.current_game)
        if game_data:
            # Show editor dialog
            self.show_control_editor(self.current_game, game_data.get('gamename'))
        else:
            # Show editor for new game
            self.show_control_editor(self.current_game)
    
    def export_current(self):
        """Export the current game preview"""
        if not self.current_game:
            messagebox.showinfo("No Game Selected", "Please select a game first")
            return
        
        # Show export dialog
        self.batch_export_images()
    
    
    def display_controls_table(self, start_row, game_data, cfg_controls):
        """Display controls with modern visual styling"""
        row = start_row

        # Clear existing control placeholder if it exists
        if hasattr(self, 'control_placeholder'):
            if self.control_placeholder.winfo_exists():
                self.control_placeholder.destroy()

        # --- Card-style container for game info ---
        info_card = ctk.CTkFrame(
            self.control_frame,
            corner_radius=8,
            fg_color=self.colors["bg_light"],
            border_width=0
        )
        info_card.grid(row=row, column=0, padx=10, pady=10, sticky="ew")
        info_card.grid_columnconfigure(0, weight=1)
        row += 1

        # Game info with clean layout
        info_text = (
            f"ROM: {game_data['romname']}\n\n"
            f"Players: {game_data['numPlayers']}\n"
            f"Alternating: {game_data['alternating']}\n"
            f"Mirrored: {game_data['mirrored']}"
        )
        if game_data.get('miscDetails'):
            info_text += f"\n\nDetails: {game_data['miscDetails']}"

        info_label = ctk.CTkLabel(
            info_card, 
            text=info_text,
            font=("Arial", 14),
            justify="left",
            anchor="w",
            wraplength=600
        )
        info_label.grid(row=0, column=0, padx=15, pady=15, sticky="ew")

        # --- Controls Header with gradient background ---
        header_card = ctk.CTkFrame(
            self.control_frame, 
            fg_color=self.colors["primary"],
            corner_radius=8,
            height=40
        )
        header_card.grid(row=row, column=0, padx=10, pady=(20, 0), sticky="ew")
        header_card.grid_columnconfigure(0, weight=1)
        header_card.grid_columnconfigure(1, weight=1)
        
        # Make sure the header has a fixed height
        header_card.grid_propagate(False)
        
        # Header labels
        for col, header in enumerate(["Controller Button", "Game Action"]):
            header_label = ctk.CTkLabel(
                header_card,
                text=header,
                font=("Arial", 14, "bold"),
                text_color="white"
            )
            header_label.grid(row=0, column=col, padx=20, pady=10, sticky="w")
        
        row += 1

        # --- Controls Content with alternating row colors ---
        controls_card = ctk.CTkFrame(
            self.control_frame,
            corner_radius=8,
            fg_color=self.colors["bg_light"],
            border_width=1,
            border_color=self.colors["bg_medium"]
        )
        controls_card.grid(row=row, column=0, padx=10, pady=0, sticky="ew")
        
        # Configure columns for equal width
        controls_card.grid_columnconfigure(0, weight=1)
        controls_card.grid_columnconfigure(1, weight=1)

        # Standard controller buttons for a nicer organization
        standard_buttons = [
            "P1 A Button", "P1 B Button", "P1 X Button", "P1 Y Button",
            "P1 LB Button", "P1 RB Button", "P1 LT Button", "P1 RT Button",
            "P1 Left Stick", "P1 Right Stick", "P1 D-Pad", "P1 Start", "P1 Select"
        ]

        # Mapping between XInput codes and button names
        xinput_to_button = {
            "XINPUT_1_A": "P1 A Button", "XINPUT_1_B": "P1 B Button",
            "XINPUT_1_X": "P1 X Button", "XINPUT_1_Y": "P1 Y Button",
            "XINPUT_1_SHOULDER_L": "P1 LB Button", "XINPUT_1_SHOULDER_R": "P1 RB Button",
            "XINPUT_1_TRIGGER_L": "P1 LT Button", "XINPUT_1_TRIGGER_R": "P1 RT Button",
            "XINPUT_1_THUMB_L": "P1 Left Stick Button", "XINPUT_1_THUMB_R": "P1 Right Stick Button",
            "XINPUT_1_DPAD_UP": "P1 D-Pad Up", "XINPUT_1_DPAD_DOWN": "P1 D-Pad Down",
            "XINPUT_1_DPAD_LEFT": "P1 D-Pad Left", "XINPUT_1_DPAD_RIGHT": "P1 D-Pad Right"
        }

        # Default mapping from MAME controls to button names
        default_button_map = {
            "P1_BUTTON1": "P1 A Button", "P1_BUTTON2": "P1 B Button",
            "P1_BUTTON3": "P1 X Button", "P1_BUTTON4": "P1 Y Button",
            "P1_BUTTON5": "P1 LB Button", "P1_BUTTON6": "P1 RB Button",
            "P1_BUTTON7": "P1 LT Button", "P1_BUTTON8": "P1 RT Button",
            "P1_BUTTON9": "P1 Left Stick Button", "P1_BUTTON10": "P1 Right Stick Button",
            "P1_JOYSTICK_UP": "P1 Left Stick Up", "P1_JOYSTICK_DOWN": "P1 Left Stick Down",
            "P1_JOYSTICK_LEFT": "P1 Left Stick Left", "P1_JOYSTICK_RIGHT": "P1 Left Stick Right"
        }

        # Map buttons to actions
        button_to_action = {}

        # Process custom controls
        if cfg_controls:
            for mame_control, mapping in cfg_controls.items():
                if not mame_control.startswith("P1_"):
                    continue

                # Find the corresponding game action
                game_action = next(
                    (label["value"]
                    for player in game_data.get("players", [])
                    for label in player.get("labels", [])
                    if label["name"] == mame_control),
                    None
                )

                if not game_action:
                    continue

                # Get the controller button name
                controller_button = (
                    xinput_to_button.get(mapping)
                    if "XINPUT" in mapping else self.joycode_to_button(mapping)
                )

                if controller_button:
                    button_to_action[controller_button] = game_action

        # Process default controls
        for player in game_data.get("players", []):
            if player["number"] != 1:
                continue
            for label in player.get("labels", []):
                mame_control = label["name"]
                game_action = label["value"]
                controller_button = default_button_map.get(mame_control)
                if controller_button and controller_button not in button_to_action:
                    button_to_action[controller_button] = game_action

        # Display controls with alternating row colors
        control_row = 0
        for button in standard_buttons:
            if button in button_to_action:
                action = button_to_action[button]

                # Alternate row colors
                row_color = self.colors["bg_light"] if control_row % 2 == 0 else self.colors["bg_medium"]
                
                # Create row frame
                row_frame = ctk.CTkFrame(
                    controls_card,
                    fg_color=row_color,
                    corner_radius=0,
                    border_width=0,
                    height=36
                )
                row_frame.grid(row=control_row, column=0, columnspan=2, sticky="ew")
                row_frame.grid_columnconfigure(0, weight=1)
                row_frame.grid_columnconfigure(1, weight=1)
                
                # Force fixed height
                row_frame.grid_propagate(False)
                
                # Button label with icon
                button_icon = "🎮" if "Button" in button else "🕹️"
                button_label = ctk.CTkLabel(
                    row_frame,
                    text=f"{button_icon} {button}",
                    font=("Arial", 13),
                    text_color=self.colors["text"],
                    anchor="w"
                )
                button_label.grid(row=0, column=0, padx=20, pady=8, sticky="w")

                # Action label
                action_label = ctk.CTkLabel(
                    row_frame,
                    text=action,
                    font=("Arial", 13),
                    text_color=self.colors["primary"] if "custom" in action.lower() else self.colors["text"],
                    anchor="w"
                )
                action_label.grid(row=0, column=1, padx=20, pady=8, sticky="w")

                control_row += 1

        row += 1

        # If we have custom config, show it in a collapsible section
        romname = game_data["romname"]
        if romname in self.custom_configs:
            # Collapsible section header
            config_header_frame = ctk.CTkFrame(
                self.control_frame,
                fg_color=self.colors["accent"],
                corner_radius=8,
                height=40
            )
            config_header_frame.grid(row=row, column=0, padx=10, pady=(20, 0), sticky="ew")
            config_header_frame.grid_propagate(False)
            
            # Header with toggle button
            self.config_expanded = tk.BooleanVar(value=False)
            
            def toggle_config():
                expanded = self.config_expanded.get()
                self.config_expanded.set(not expanded)
                
                # Update button text
                toggle_btn.configure(text="▼ Hide Raw Config" if not expanded else "► Show Raw Config")
                
                # Show/hide config content
                if not expanded:
                    config_content.grid(row=row+1, column=0, padx=10, pady=(0, 10), sticky="ew")
                else:
                    config_content.grid_forget()
            
            toggle_btn = ctk.CTkButton(
                config_header_frame,
                text="► Show Raw Config",
                command=toggle_config,
                fg_color="transparent",
                text_color=self.colors["text"],
                hover_color=self.colors["primary"],
                anchor="w",
                width=200,
                height=30,
                corner_radius=0
            )
            toggle_btn.pack(fill="both", expand=True, padx=10)
            
            row += 1
            
            # Config content (initially hidden)
            config_content = ctk.CTkFrame(
                self.control_frame,
                fg_color=self.colors["bg_light"],
                corner_radius=8
            )
            
            # Raw config textbox
            custom_text = ctk.CTkTextbox(
                config_content,
                height=200,
                width=200,
                fg_color=self.colors["bg_dark"],
                text_color=self.colors["text_secondary"],
                font=("Consolas", 12)
            )
            custom_text.pack(fill="both", expand=True, padx=10, pady=10)
            custom_text.insert("1.0", self.custom_configs[romname])
            custom_text.configure(state="disabled")
            
            row += 1

        return row + 1
    
    def direct_get_game_data(self, romname):
        """Direct lookup of game data - used for problematic ROMs"""
        print(f"Performing direct lookup for: {romname}")
        
        if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
            print("gamedata_json not available for direct lookup")
            return None
            
        if romname not in self.gamedata_json:
            print(f"{romname} not found in gamedata_json")
            return None
        
        # Get the raw game data
        game_data = self.gamedata_json[romname]
        print(f"Found raw data for {romname}")
        
        # Process the data similarly to get_game_data but with more direct approach
        # Simple name defaults - these are the fallback button names if none are specified
        default_actions = {
            'P1_JOYSTICK_UP': 'Up',
            'P1_JOYSTICK_DOWN': 'Down',
            'P1_JOYSTICK_LEFT': 'Left',
            'P1_JOYSTICK_RIGHT': 'Right',
            'P2_JOYSTICK_UP': 'Up',
            'P2_JOYSTICK_DOWN': 'Down',
            'P2_JOYSTICK_LEFT': 'Left',
            'P2_JOYSTICK_RIGHT': 'Right',
            'P1_BUTTON1': 'A Button',
            'P1_BUTTON2': 'B Button',
            'P1_BUTTON3': 'X Button',
            'P1_BUTTON4': 'Y Button',
            'P1_BUTTON5': 'LB Button',
            'P1_BUTTON6': 'RB Button',
            'P1_BUTTON7': 'LT Button',
            'P1_BUTTON8': 'RT Button',
            'P1_BUTTON9': 'Left Stick Button',
            'P1_BUTTON10': 'Right Stick Button',
            'P2_BUTTON1': 'A Button',
            'P2_BUTTON2': 'B Button',
            'P2_BUTTON3': 'X Button',
            'P2_BUTTON4': 'Y Button',
            'P2_BUTTON5': 'LB Button',
            'P2_BUTTON6': 'RB Button',
            'P2_BUTTON7': 'LT Button',
            'P2_BUTTON8': 'RT Button',
            'P2_BUTTON9': 'Left Stick Button',
            'P2_BUTTON10': 'Right Stick Button',
        }
        
        # Handle type conversions for numeric fields - CRITICAL FIX
        try:
            # Ensure playercount, buttons and sticks are converted to integers
            # Use direct conversion with error handling
            player_count = 1
            if 'playercount' in game_data:
                try:
                    player_count = int(game_data['playercount'])
                except (ValueError, TypeError):
                    player_count = 1
                    
            buttons_count = 0
            if 'buttons' in game_data:
                try:
                    buttons_count = int(game_data['buttons'])
                except (ValueError, TypeError):
                    buttons_count = 0
                    
            sticks_count = 0
            if 'sticks' in game_data:
                try:
                    sticks_count = int(game_data['sticks'])
                except (ValueError, TypeError):
                    sticks_count = 0
                    
            # Convert alternating to proper boolean
            alternating = False
            if 'alternating' in game_data:
                # Handle different possible values
                alt_value = game_data['alternating']
                if isinstance(alt_value, bool):
                    alternating = alt_value
                elif isinstance(alt_value, str):
                    alternating = alt_value.lower() in ('true', 'yes', '1')
                elif isinstance(alt_value, int):
                    alternating = alt_value != 0
                    
            # Basic structure conversion
            converted_data = {
                'romname': romname,
                'gamename': game_data.get('description', romname),
                'numPlayers': player_count,
                'alternating': alternating,
                'mirrored': False,
                'miscDetails': f"Buttons: {buttons_count}, Sticks: {sticks_count}",
                'players': []
            }
        except Exception as e:
            print(f"Error converting data types for direct lookup of {romname}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # Find controls directly
        controls = game_data.get('controls', None)
        if not controls:
            print(f"No controls in {romname} data")
            return converted_data
        
        print(f"Found controls for {romname}: {len(controls)}")
        
        # Process controls directly - use simpler approach
        p1_controls = []
        p2_controls = []
        
        # Process all controls by type
        for control_name, control_data in controls.items():
            # Extract the friendly name from the control data
            friendly_name = None
            
            # First check for explicit name in the control data
            if isinstance(control_data, dict) and 'name' in control_data:
                friendly_name = control_data['name']
            elif control_name in default_actions:
                friendly_name = default_actions[control_name]
            else:
                # Last resort - use the control name
                parts = control_name.split('_')
                friendly_name = parts[-1] if len(parts) > 1 else control_name
            
            # Add to appropriate player list
            if control_name.startswith('P1_'):
                p1_controls.append({
                    'name': control_name,
                    'value': friendly_name
                })
            elif control_name.startswith('P2_'):
                p2_controls.append({
                    'name': control_name,
                    'value': friendly_name
                })
        
        # Sort controls for consistent display
        p1_controls.sort(key=lambda x: x['name'])
        p2_controls.sort(key=lambda x: x['name'])
        
        # Add controls to the converted data
        if p1_controls:
            converted_data['players'].append({
                'number': 1,
                'numButtons': buttons_count,
                'labels': p1_controls
            })
        
        if p2_controls:
            converted_data['players'].append({
                'number': 2,
                'numButtons': buttons_count,
                'labels': p2_controls
            })
        
        # Set the source
        converted_data['source'] = 'gamedata.json (direct lookup)'
        
        # Cache the result if caching is enabled
        if hasattr(self, 'rom_data_cache'):
            self.rom_data_cache[romname] = converted_data
        
        return converted_data
    
    def convert_raw_data_to_game_data(self, rom_name, raw_data):
        """Convert raw gamedata.json entry to the expected game_data structure"""
        print(f"Converting raw data for {rom_name}")
        
        # Default values for fallback
        default_actions = {
            'P1_JOYSTICK_UP': 'Up',
            'P1_JOYSTICK_DOWN': 'Down',
            'P1_JOYSTICK_LEFT': 'Left',
            'P1_JOYSTICK_RIGHT': 'Right',
            'P2_JOYSTICK_UP': 'Up',
            'P2_JOYSTICK_DOWN': 'Down',
            'P2_JOYSTICK_LEFT': 'Left',
            'P2_JOYSTICK_RIGHT': 'Right',
            'P1_BUTTON1': 'A Button',
            'P1_BUTTON2': 'B Button',
            'P1_BUTTON3': 'X Button',
            'P1_BUTTON4': 'Y Button',
            'P1_BUTTON5': 'LB Button',
            'P1_BUTTON6': 'RB Button',
            'P1_BUTTON7': 'LT Button',
            'P1_BUTTON8': 'RT Button',
            'P1_BUTTON9': 'Left Stick Button',
            'P1_BUTTON10': 'Right Stick Button',
            'P2_BUTTON1': 'A Button',
            'P2_BUTTON2': 'B Button',
            'P2_BUTTON3': 'X Button',
            'P2_BUTTON4': 'Y Button',
            'P2_BUTTON5': 'LB Button',
            'P2_BUTTON6': 'RB Button',
            'P2_BUTTON7': 'LT Button',
            'P2_BUTTON8': 'RT Button',
            'P2_BUTTON9': 'Left Stick Button',
            'P2_BUTTON10': 'Right Stick Button',
        }
        
        try:
            # Safe conversions
            player_count = 1
            buttons_count = 0
            sticks_count = 0
            alternating = False
            
            # Extract values with safe conversions
            if 'playercount' in raw_data:
                try:
                    player_count = int(raw_data['playercount'])
                except (ValueError, TypeError):
                    player_count = 1
                    
            if 'buttons' in raw_data:
                try:
                    buttons_count = int(raw_data['buttons'])
                except (ValueError, TypeError):
                    buttons_count = 0
                    
            if 'sticks' in raw_data:
                try:
                    sticks_count = int(raw_data['sticks'])
                except (ValueError, TypeError):
                    sticks_count = 0
                    
            if 'alternating' in raw_data:
                alt_value = raw_data['alternating']
                if isinstance(alt_value, bool):
                    alternating = alt_value
                elif isinstance(alt_value, str):
                    alternating = alt_value.lower() in ('true', 'yes', '1')
                elif isinstance(alt_value, int):
                    alternating = alt_value != 0
                    
            # Create basic structure
            game_data = {
                'romname': rom_name,
                'gamename': raw_data.get('description', rom_name),
                'numPlayers': player_count,
                'alternating': alternating,
                'mirrored': False,
                'miscDetails': f"Buttons: {buttons_count}, Sticks: {sticks_count}",
                'players': [],
                'source': 'gamedata.json (direct conversion)'
            }
            
            # Extract controls if present
            controls = raw_data.get('controls', {})
            
            if controls:
                print(f"Found {len(controls)} controls for {rom_name}")
                
                # Process controls into player structures
                p1_controls = []
                p2_controls = []
                
                for control_name, control_data in controls.items():
                    # Skip controls we can't process
                    if not isinstance(control_data, dict):
                        continue
                        
                    # Get action name with fallbacks
                    action = None
                    if 'name' in control_data and control_data['name']:
                        action = control_data['name']
                    elif control_name in default_actions:
                        action = default_actions[control_name]
                    else:
                        parts = control_name.split('_')
                        if len(parts) > 1:
                            action = parts[-1]
                        else:
                            action = control_name
                    
                    # Add to appropriate player list
                    if control_name.startswith('P1_'):
                        if 'JOYSTICK' in control_name or 'BUTTON' in control_name:
                            p1_controls.append({
                                'name': control_name,
                                'value': action
                            })
                    elif control_name.startswith('P2_'):
                        if 'JOYSTICK' in control_name or 'BUTTON' in control_name:
                            p2_controls.append({
                                'name': control_name,
                                'value': action
                            })
                
                # Sort controls
                p1_controls.sort(key=lambda x: x['name'])
                p2_controls.sort(key=lambda x: x['name'])
                
                # Add player data
                if p1_controls:
                    game_data['players'].append({
                        'number': 1,
                        'numButtons': buttons_count,
                        'labels': p1_controls
                    })
                    
                if p2_controls:
                    game_data['players'].append({
                        'number': 2,
                        'numButtons': buttons_count,
                        'labels': p2_controls
                    })
            else:
                print(f"No controls found for {rom_name}")
                
            # Cache the result if caching is enabled
            if hasattr(self, 'rom_data_cache'):
                self.rom_data_cache[rom_name] = game_data
                
            return game_data
        except Exception as e:
            print(f"Error converting raw data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _display_controls_basic(self, game_data, cfg_controls):
        """Simple fallback method to display controls"""
        # Clear existing controls
        for widget in self.control_frame.winfo_children():
            widget.destroy()
            
        # Create a simple layout
        info_frame = ctk.CTkFrame(self.control_frame)
        info_frame.pack(fill="x", padx=10, pady=10)
        
        # Game info
        info_text = (
            f"ROM: {game_data['romname']}\n"
            f"Players: {game_data['numPlayers']}\n"
            f"Source: {game_data.get('source', 'Unknown')}"
        )
        
        info_label = ctk.CTkLabel(info_frame, text=info_text, font=("Arial", 14), justify="left")
        info_label.pack(padx=10, pady=10, anchor="w")
        
        # Create a frame for controls
        controls_frame = ctk.CTkFrame(self.control_frame)
        controls_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Add player sections
        for player in game_data.get('players', []):
            player_num = player.get('number', 0)
            
            # Player header
            player_label = ctk.CTkLabel(
                controls_frame,
                text=f"Player {player_num}",
                font=("Arial", 14, "bold")
            )
            player_label.pack(anchor="w", padx=10, pady=(10, 5))
            
            # Control list
            for control in player.get('labels', []):
                control_name = control.get('name', '')
                action = control.get('value', '')
                
                # Format for display
                control_text = f"{control_name}: {action}"
                
                control_label = ctk.CTkLabel(
                    controls_frame,
                    text=control_text,
                    font=("Arial", 12),
                    justify="left"
                )
                control_label.pack(anchor="w", padx=30, pady=2)
                
        # If we have a custom config, show it
        if game_data['romname'] in self.custom_configs:
            config_frame = ctk.CTkFrame(self.control_frame)
            config_frame.pack(fill="x", padx=10, pady=10)
            
            config_label = ctk.CTkLabel(
                config_frame,
                text="Custom Configuration",
                font=("Arial", 14, "bold")
            )
            config_label.pack(anchor="w", padx=10, pady=5)
            
            config_box = ctk.CTkTextbox(config_frame, height=150)
            config_box.pack(fill="x", padx=10, pady=5)
            config_box.insert("1.0", self.custom_configs[game_data['romname']])
            config_box.configure(state="disabled")
    
    def on_game_select(self, event):
        """Handle game selection with a simple, foolproof ROM name extraction"""
        try:
            # Get the selected game name
            index = self.game_list.index(f"@{event.x},{event.y}")
            
            # Get the line number (starting from 1)
            line_num = int(index.split('.')[0])
            
            # Get the text from this line
            line = self.game_list.get(f"{line_num}.0", f"{line_num}.0 lineend")
            
            # Skip if line is empty or "No matching ROMs found"
            if not line or line.startswith("No matching ROMs"):
                return
                
            # Highlight the selected line
            self.highlight_selected_game(line_num)
            
            print(f"Selected line: '{line}'")
            
            # SUPER SIMPLE EXTRACTION - Just grab everything before the dash
            # This is the most reliable way to get the ROM name
            if " - " in line:
                rom_part = line.split(" - ")[0]
            else:
                rom_part = line
                
            # Now strip ALL non-alphanumeric chars from the beginning 
            # until we hit the actual ROM name
            rom_name = rom_part.strip()
            while rom_name and not (rom_name[0].isalnum() or rom_name[0] == '_'):
                rom_name = rom_name[1:].strip()
                
            print(f"Extracted ROM name: '{rom_name}'")
            
            self.current_game = rom_name
            
            # Get game data
            game_data = self.get_game_data(rom_name)
            
            # Clear existing display
            for widget in self.control_frame.winfo_children():
                widget.destroy()
                
            if not game_data:
                # Clear display for ROMs without control data
                self.game_title.configure(text=f"No control data: {rom_name}")
                return
                
            # Update game title
            source_text = f" ({game_data.get('source', 'unknown')})"
            title_text = f"{game_data['gamename']}{source_text}"
            
            # Update title text ensuring left-alignment with proper wrapping
            self.game_title.configure(text=title_text)
            
            # Get custom controls if they exist
            cfg_controls = {}
            if rom_name in self.custom_configs:
                # Only parse the custom configs if we need them
                cfg_controls = self.parse_cfg_controls(self.custom_configs[rom_name])
                
                # Convert mappings if XInput is enabled
                if self.use_xinput:
                    cfg_controls = {
                        control: self.convert_mapping(mapping, True)
                        for control, mapping in cfg_controls.items()
                    }
            
            # Display controls - use the class method that was working before
            if hasattr(self, "display_controls_table"):
                self.display_controls_table(0, game_data, cfg_controls)
            else:
                # Fallback to a very simple control display
                self._display_simple_controls(game_data, cfg_controls)
                
        except Exception as e:
            print(f"Error selecting game: {e}")
            import traceback
            traceback.print_exc()
            
    def _display_simple_controls(self, game_data, cfg_controls):
        """Super simple fallback to display controls"""
        # Basic structure - use simple layout
        info_frame = ctk.CTkFrame(self.control_frame)
        info_frame.pack(fill="x", padx=10, pady=10)
        
        # Game info
        info_text = (
            f"ROM: {game_data['romname']}\n"
            f"Players: {game_data['numPlayers']}\n"
            f"Alternating: {game_data['alternating']}\n"
            f"Mirrored: {game_data['mirrored']}"
        )
        if game_data.get('miscDetails'):
            info_text += f"\n\nDetails: {game_data['miscDetails']}"
        
        info_label = ctk.CTkLabel(info_frame, text=info_text, font=("Arial", 14), justify="left")
        info_label.pack(padx=10, pady=10, anchor="w")
        
        # Controls table - use the original table approach from your code
        controls_frame = ctk.CTkFrame(self.control_frame)
        controls_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Configure columns
        controls_frame.grid_columnconfigure(0, weight=2)  # Control name
        controls_frame.grid_columnconfigure(1, weight=2)  # Default action
        controls_frame.grid_columnconfigure(2, weight=3)  # Current mapping
        
        row = 0
        
        # Headers
        for col, header in enumerate(["Controller Button", "Game Action", "Mapping"]):
            header_label = ctk.CTkLabel(
                controls_frame,
                text=header,
                font=("Arial", 14, "bold")
            )
            header_label.grid(row=row, column=col, padx=5, pady=5, sticky="w")
        row += 1
        
        # Process each player
        for player in game_data.get('players', []):
            player_num = player.get('number', 0)
            
            # Player header
            player_label = ctk.CTkLabel(
                controls_frame,
                text=f"Player {player_num}",
                font=("Arial", 14, "bold"),
                fg_color="#1E90FF",
                text_color="white",
                corner_radius=6
            )
            player_label.grid(row=row, column=0, columnspan=3, padx=5, pady=(10, 5), sticky="w")
            row += 1
            
            # Controls
            for control in player.get('labels', []):
                control_name = control.get('name', '')
                action = control.get('value', '')
                
                # Get custom mapping if available
                mapping = "Default"
                is_custom = False
                
                if control_name in cfg_controls:
                    mapping = cfg_controls[control_name]
                    is_custom = True
                    
                # Format for display
                control_label = ctk.CTkLabel(
                    controls_frame,
                    text=control_name,
                    font=("Arial", 12)
                )
                control_label.grid(row=row, column=0, padx=5, pady=2, sticky="w")
                
                action_label = ctk.CTkLabel(
                    controls_frame,
                    text=action,
                    font=("Arial", 12)
                )
                action_label.grid(row=row, column=1, padx=5, pady=2, sticky="w")
                
                mapping_label = ctk.CTkLabel(
                    controls_frame,
                    text=mapping,
                    font=("Arial", 12),
                    text_color="#3A7CEA" if is_custom else "#AAAAAA"
                )
                mapping_label.grid(row=row, column=2, padx=5, pady=2, sticky="w")
                
                row += 1
        
        # If we have a custom config, show it
        romname = game_data.get('romname', '')
        if romname and hasattr(self, 'custom_configs') and romname in self.custom_configs:
            config_frame = ctk.CTkFrame(self.control_frame)
            config_frame.pack(fill="x", padx=10, pady=10)
            
            config_label = ctk.CTkLabel(
                config_frame,
                text="Custom Configuration",
                font=("Arial", 14, "bold")
            )
            config_label.pack(anchor="w", padx=10, pady=5)
            
            config_box = ctk.CTkTextbox(config_frame, height=150)
            config_box.pack(fill="x", padx=10, pady=5)
            config_box.insert("1.0", self.custom_configs[romname])
            config_box.configure(state="disabled")
    
    # Add a fallback compatibility method for compare_controls if it doesn't exist
    # Simplified version just to ensure controls display correctly
    def compare_controls_fallback(self, game_data, cfg_controls):
        """Simple fallback for compare_controls if the original method isn't available"""
        result = []
        
        for player in game_data.get('players', []):
            for label in player.get('labels', []):
                control_name = label['name']
                action = label['value']
                is_custom = control_name in cfg_controls
                mapping = cfg_controls.get(control_name, "Default")
                result.append((control_name, action, mapping, is_custom))
        
        return result
    
    # The highlight_selected_game method with safer implementation
    def highlight_selected_game(self, line_index):
        """Highlight the selected game in the list safely"""
        if not hasattr(self, 'game_list') or not hasattr(self, 'selected_line'):
            return
            
        try:
            # Clear previous highlight if any
            if self.selected_line is not None:
                self.game_list._textbox.tag_remove(self.highlight_tag, f"{self.selected_line}.0", f"{self.selected_line + 1}.0")
            
            # Apply new highlight
            self.selected_line = line_index
            self.game_list._textbox.tag_add(self.highlight_tag, f"{line_index}.0", f"{line_index + 1}.0")
            
            # Ensure the selected item is visible
            self.game_list.see(f"{line_index}.0")
        except Exception as e:
            print(f"Error highlighting game: {e}")
            # Don't let highlighting errors prevent selection

    # Helper function to dynamically add more buttons to the top bar
    def add_button(self, text, command, width=150):
        """Add a button to the top bar"""
        button = ctk.CTkButton(
            self.top_bar,
            text=text,
            command=command,
            width=width
        )
        button.pack(side="left", padx=5, pady=5)
        return button

    def on_window_resize(self, event=None):
        """Handle window resize to maintain fixed panel proportions"""
        if event and event.widget == self:
            window_width = event.width
            
            # Only handle meaningful resize events (prevent 1px adjustments)
            if window_width > 100:
                # Calculate the appropriate panel widths (40/60 split)
                left_width = int(window_width * 0.4)  # 40% for left panel
                right_width = int(window_width * 0.6)  # 60% for right panel
                
                # Apply fixed width to the panels
                self.main_content.columnconfigure(0, minsize=left_width)
                self.main_content.columnconfigure(1, minsize=right_width)
                
                # Adjust game title wraplength to prevent text overflow
                if hasattr(self, 'game_title'):
                    title_width = right_width - 200  # Leave room for buttons and padding
                    self.game_title.configure(wraplength=title_width if title_width > 300 else 300)

    #######################################################################
    #CONFIF TO CREATE INFO FILES FOR RETROFE
    #- INFO FOLDER ENEDS TO BE IN PREVIEW\SETTINGS\INFO WITH A DEFAULT TEMPLATE
    ##########################################################################
    
    
    def create_info_directory(self):
        """Create info directory in the new folder structure"""
        # Use the predefined info_dir
        if not os.path.exists(self.info_dir):
            os.makedirs(self.info_dir)
        return self.info_dir
    
    def generate_all_configs(self):
        """Generate config files for all available ROMs from gamedata.json"""
        info_dir = self.create_info_directory()
        print(f"Created/Found info directory at: {info_dir}")
        
        # First verify we have the template
        template = self.load_default_template()
        if not template:
            messagebox.showerror("Error", "Could not find default.conf template in info directory!")
            return
        print("Successfully loaded template")
        
        count = 0
        errors = []
        skipped = 0
        
        # Process all ROMs with control data
        roms_to_process = list(self.available_roms)
        
        total_roms = len(roms_to_process)
        print(f"Found {total_roms} ROMs to process")
        
        # Process each ROM
        for rom_name in roms_to_process:
            try:
                # Get game data
                game_data = self.get_game_data(rom_name)
                
                if game_data:
                    config_content = self.generate_game_config(game_data)
                    if config_content:
                        config_path = os.path.join(info_dir, f"{rom_name}.conf")
                        with open(config_path, 'w', encoding='utf-8') as f:
                            f.write(config_content)
                        count += 1
                        if count % 50 == 0:  # Progress update every 50 files
                            print(f"Generated {count}/{total_roms} config files...")
                    else:
                        print(f"Skipping {rom_name}: No config content generated")
                        skipped += 1
                else:
                    print(f"Skipping {rom_name}: No control data found")
                    skipped += 1
            except Exception as e:
                error_msg = f"Error with {rom_name}: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
        
        # Final report
        report = f"Generated {count} config files in {info_dir}\n"
        report += f"Skipped {skipped} ROMs\n"
        if errors:
            report += f"\nEncountered {len(errors)} errors:\n"
            report += "\n".join(errors[:5])  # Show first 5 errors
            if len(errors) > 5:
                report += f"\n...and {len(errors) - 5} more errors"
        
        print(report)
        messagebox.showinfo("Config Generation Report", report)
    
    def load_default_template(self):
        """Load the default.conf template with updated path handling"""
        # Look in the info directory
        template_path = os.path.join(self.info_dir, "default.conf")
        
        print(f"\nLooking for default template at: {template_path}")
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
                print(f"Successfully loaded template ({len(template_content)} characters)")
                return template_content
        except Exception as e:
            print(f"Error loading template: {e}")
            
            # Try legacy paths
            legacy_paths = [
                os.path.join(self.preview_dir, "settings", "info", "default.conf"),
                os.path.join(self.preview_dir, "info", "default.conf"),  # This is now the primary path
                os.path.join(self.app_dir, "info", "default.conf")
            ]
            
            for legacy_path in legacy_paths:
                print(f"Trying legacy path: {legacy_path}")
                try:
                    with open(legacy_path, 'r', encoding='utf-8') as f:
                        template_content = f.read()
                    
                    # Also migrate the template to the new location
                    try:
                        os.makedirs(os.path.dirname(template_path), exist_ok=True)
                        with open(template_path, 'w', encoding='utf-8') as f:
                            f.write(template_content)
                        print(f"Migrated template to: {template_path}")
                    except Exception as migrate_err:
                        print(f"Error migrating template: {migrate_err}")
                    
                    print(f"Successfully loaded template from legacy path ({len(template_content)} characters)")
                    return template_content
                except Exception as alt_e:
                    print(f"Error loading from legacy path: {alt_e}")
            
        # Last resort: create a default template on the fly
        print("Creating default template content")
        default_content = """controller D-pad		= 
controller D-pad t		= 
controller L-stick		= 
controller L-stick t	= 
controller R-stick		= 
controller R-stick t	= 
controller A			= 
controller A t			= 
controller B			= 
controller B t			= 
controller X			= 
controller X t			= 
controller Y			= 
controller Y t			= 
controller LB			= 
controller LB t			= 
controller LT			= 
controller LT t			= 
controller RB			= 
controller RB t			= 
controller RT			= 
controller RT t			= 
controller start		= 
controller start t		=
controller select		= 
controller select t		=
controller xbox			= 
controller xbox t		= """
        # Try to save this for future use
        try:
            os.makedirs(os.path.dirname(template_path), exist_ok=True)
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(default_content)
            print(f"Created new default template at: {template_path}")
        except Exception as save_e:
            print(f"Could not save default template: {save_e}")
            
        return default_content
    
    def generate_game_config(self, game_data: dict) -> str:
        """Generate config file content for a specific game"""
        template = self.load_default_template()
        if not template:
            return None
            
        # Split template into lines while preserving exact spacing
        template_lines = template.splitlines()
        output_lines = []
        
        # Create a dictionary to track which controls are used by this game
        used_controls = {}
        for player in game_data.get('players', []):
            for label in player.get('labels', []):
                control_name = label['name']
                action = label['value']
                
                # Map control to config field
                config_field, _ = self.map_control_to_xinput_config(control_name)
                if config_field:
                    used_controls[config_field.strip()] = action
        
        # Process each line
        for line in template_lines:
            # Keep comments and empty lines as-is
            if line.strip().startswith('#') or not line.strip():
                output_lines.append(line)
                continue
                
            # Process lines with equals sign
            if '=' in line:
                # Split at equals to preserve the exact tab alignment
                parts = line.split('=', 1)
                field_part = parts[0]  # This maintains all whitespace/tabs
                field_name = field_part.strip()
                
                # Special case for default values that should always be set
                if field_name == "controller start t":
                    output_lines.append(f"{field_part}= Start")
                    continue
                elif field_name == "controller select t":
                    output_lines.append(f"{field_part}= Coin")
                    continue
                #elif field_name == "controller xbox t":
                    #output_lines.append(f"{field_part}= Exit")
                    #continue
                
                # If it's a tooltip field (ends with 't')
                if field_name.endswith('t'):
                    # Check if this control is used by the game
                    if field_name in used_controls:
                        # Replace the value part with the game-specific action
                        new_line = f"{field_part}= {used_controls[field_name]}"
                        output_lines.append(new_line)
                    else:
                        # Keep the field but with empty value
                        output_lines.append(f"{field_part}= ")
                else:
                    # For non-tooltip fields, keep the field with empty value
                    output_lines.append(f"{field_part}= ")
            else:
                # For lines without '=', keep them exactly as is
                output_lines.append(line)
        
        return '\n'.join(output_lines)
    
    def map_control_to_xinput_config(self, control_name: str) -> Tuple[str, str]:
        """Map MAME control to Xbox controller config field"""
        mapping_dict = {
            'P1_BUTTON1': ('controller A t', 'A Button'),      # A
            'P1_BUTTON2': ('controller B t', 'B Button'),      # B
            'P1_BUTTON3': ('controller X t', 'X Button'),      # X
            'P1_BUTTON4': ('controller Y t', 'Y Button'),      # Y
            'P1_BUTTON5': ('controller LB t', 'Left Bumper'),  # LB
            'P1_BUTTON6': ('controller RB t', 'Right Bumper'), # RB
            'P1_BUTTON7': ('controller LT t', 'Left Trigger'), # LT
            'P1_BUTTON8': ('controller RT t', 'Right Trigger'),# RT
            'P1_BUTTON9': ('controller LSB t', 'L3'),          # Left Stick Button
            'P1_BUTTON10': ('controller RSB t', 'R3'),         # Right Stick Button
            'P1_BUTTON11': ('controller Start t', 'Start'),          # Left Stick Button
            'P1_BUTTON12': ('controller Select t', 'Select'),         # Right Stick Button
            'P1_JOYSTICK_UP': ('controller L-stick t', 'Left Stick Up'),
            'P1_JOYSTICK_DOWN': ('controller L-stick t', 'Left Stick Down'),
            'P1_JOYSTICK_LEFT': ('controller L-stick t', 'Left Stick Left'),
            'P1_JOYSTICK_RIGHT': ('controller L-stick t', 'Left Stick Right'),
        }
        return mapping_dict.get(control_name, (None, None))
    
    '''#######################################################################
    CONFIF EDIT GAMES IN GAMEDATA.JSON
    - GAMEDATA JSON NEEDS OT BE IN MAME ROOT FODLER
    ##########################################################################
    '''
    
    def analyze_controls(self):
        """Comprehensive analysis of ROM controls with editing capabilities"""
        # Get data from both methods
        generic_games, missing_games = self.identify_generic_controls()
        matched_roms = set()
        for rom in self.available_roms:
            if self.get_game_data(rom):
                matched_roms.add(rom)
        unmatched_roms = self.available_roms - matched_roms
        
        # Identify default controls (games with real control data but not customized)
        default_games = []
        already_categorized = set([g[0] for g in generic_games]) | set(missing_games)
        for rom_name in sorted(matched_roms):
            if rom_name not in already_categorized:
                game_data = self.get_game_data(rom_name)
                if game_data and 'gamename' in game_data:
                    default_games.append((rom_name, game_data.get('gamename', rom_name)))
        
        # Create dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("ROM Control Analysis")
        #dialog.geometry("800x600")
        dialog.transient(self)
        dialog.grab_set()
        
        # Center the dialog on the screen
        dialog_width = 800
        dialog_height = 600

        # Get screen width and height
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()

        # Calculate position x, y
        x = int((screen_width / 2) - (dialog_width / 2))
        y = int((screen_height / 2) - (dialog_height / 2))

        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # Create tabs
        tabview = ctk.CTkTabview(dialog)
        tabview.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Summary tab
        summary_tab = tabview.add("Summary")
        stats_text = (
            f"Total ROMs: {len(self.available_roms)}\n"
            f"ROMs with control data: {len(matched_roms)}\n"
            f"ROMs without control data: {len(unmatched_roms)}\n\n"
            f"Control data breakdown:\n"
            f"- ROMs with generic controls: {len(generic_games)}\n"
            f"- ROMs with custom controls: {len(default_games)}\n"
            f"- ROMs with missing controls: {len(missing_games)}\n\n"
            f"Control data coverage: {(len(matched_roms) / max(len(self.available_roms), 1) * 100):.1f}%"
        )
        stats_label = ctk.CTkLabel(
            summary_tab,
            text=stats_text,
            font=("Arial", 14),
            justify="left"
        )
        stats_label.pack(padx=20, pady=20, anchor="w")
        
        # Create each tab with the better list UI from unmatched_roms
        self.create_game_list_with_edit(tabview.add("Generic Controls"), 
                                    generic_games, "ROMs with Generic Controls")
        self.create_game_list_with_edit(tabview.add("Missing Controls"), 
                                    [(rom, rom) for rom in missing_games], "ROMs with Missing Controls")
        self.create_game_list_with_edit(tabview.add("Custom Controls"), 
                                    default_games, "ROMs with Custom Controls")
        
        # Add export button
        def export_analysis():
            try:
                file_path = os.path.join(self.mame_dir, "controls_analysis.txt")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("MAME Controls Analysis\n")
                    f.write("====================\n\n")
                    f.write(stats_text + "\n\n")
                    
                    f.write("Games with Generic Controls:\n")
                    f.write("==========================\n")
                    for rom, game_name in generic_games:
                        f.write(f"{rom} - {game_name}\n")
                    f.write("\n")
                    
                    f.write("Games with Missing Controls:\n")
                    f.write("==========================\n")
                    for rom in sorted(missing_games):
                        f.write(f"{rom}\n")
                    f.write("\n")
                    
                    f.write("Games with Custom Controls:\n")
                    f.write("==========================\n")
                    for rom, game_name in default_games:
                        f.write(f"{rom} - {game_name}\n")
                        
                messagebox.showinfo("Export Complete", 
                            f"Analysis exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))
        
        # Export button
        export_button = ctk.CTkButton(
            dialog,
            text="Export Analysis",
            command=export_analysis
        )
        export_button.pack(pady=10)
        
        # Close button
        close_button = ctk.CTkButton(
            dialog,
            text="Close",
            command=dialog.destroy
        )
        close_button.pack(pady=10)
        
        # Select Summary tab by default
        tabview.set("Summary")
    
    def show_control_editor(self, rom_name, game_name=None):
        """Show editor for a game's controls with direct gamedata.json editing and standard button layout"""
        game_data = self.get_game_data(rom_name) or {}
        game_name = game_name or game_data.get('gamename', rom_name)
        
        # Check if this is an existing game or a new one
        is_new_game = not bool(game_data)
        
        # Create dialog
        editor = ctk.CTkToplevel(self)
        editor.title(f"{'Add New Game' if is_new_game else 'Edit Controls'} - {game_name}")
        editor.geometry("900x750")  # Made taller to accommodate all controls
        editor.transient(self)
        editor.grab_set()
        
        # Header
        header_frame = ctk.CTkFrame(editor)
        header_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            header_frame,
            text=f"{'Add New Game' if is_new_game else 'Edit Controls for'} {game_name}",
            font=("Arial", 16, "bold")
        ).pack(side=tk.LEFT, padx=10)
        
        # Game properties section (shown prominently for new games)
        properties_frame = ctk.CTkFrame(editor)
        properties_frame.pack(fill="x", padx=10, pady=10)
        
        # Add a label for the properties section
        ctk.CTkLabel(
            properties_frame,
            text="Game Properties",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        # Create grid for properties
        properties_grid = ctk.CTkFrame(properties_frame)
        properties_grid.pack(fill="x", padx=10, pady=5)
        
        # Get current values
        current_description = game_data.get('gamename', game_name) or rom_name
        current_playercount = game_data.get('numPlayers', 2)
        if isinstance(current_playercount, str):
            current_playercount = int(current_playercount)
        
        # For buttons and sticks, try to extract from miscDetails if available
        current_buttons = "6"  # Default
        current_sticks = "1"  # Default
        
        if 'miscDetails' in game_data:
            # Try to parse from miscDetails (format: "Buttons: X, Sticks: Y")
            details = game_data.get('miscDetails', '')
            buttons_match = re.search(r'Buttons: (\d+)', details)
            sticks_match = re.search(r'Sticks: (\d+)', details)
            
            if buttons_match:
                current_buttons = buttons_match.group(1)
            if sticks_match:
                current_sticks = sticks_match.group(1)
        
        # Row 0: Game Description (Name)
        ctk.CTkLabel(properties_grid, text="Game Name:", width=100).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        description_var = ctk.StringVar(value=current_description)
        description_entry = ctk.CTkEntry(properties_grid, width=300, textvariable=description_var)
        description_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Row 1: Player Count
        ctk.CTkLabel(properties_grid, text="Players:", width=100).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        playercount_var = ctk.StringVar(value=str(current_playercount))
        playercount_combo = ctk.CTkComboBox(properties_grid, width=100, values=["1", "2", "3", "4"], variable=playercount_var)
        playercount_combo.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        # Set up players alternating option
        alternating_var = ctk.BooleanVar(value=game_data.get('alternating', False))
        alternating_check = ctk.CTkCheckBox(properties_grid, text="Alternating Play", variable=alternating_var)
        alternating_check.grid(row=1, column=2, padx=5, pady=5, sticky="w")
        
        # Row 2: Buttons and Sticks
        ctk.CTkLabel(properties_grid, text="Buttons:", width=100).grid(row=2, column=0, padx=5, pady=5, sticky="w")
        buttons_var = ctk.StringVar(value=current_buttons)
        buttons_combo = ctk.CTkComboBox(properties_grid, width=100, values=["1", "2", "3", "4", "5", "6", "8"], variable=buttons_var)
        buttons_combo.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        ctk.CTkLabel(properties_grid, text="Sticks:", width=100).grid(row=2, column=2, padx=5, pady=5, sticky="w")
        sticks_var = ctk.StringVar(value=current_sticks)
        sticks_combo = ctk.CTkComboBox(properties_grid, width=100, values=["0", "1", "2"], variable=sticks_var)
        sticks_combo.grid(row=2, column=3, padx=5, pady=5, sticky="w")
        
        # Set column weights
        properties_grid.columnconfigure(1, weight=1)
        properties_grid.columnconfigure(3, weight=1)
        
        # Main content frame with scrolling
        content_frame = ctk.CTkScrollableFrame(editor)
        content_frame.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Define standard controller buttons from the mapping dictionary
        standard_controls = [
            ('P1_BUTTON1', 'A Button'),
            ('P1_BUTTON2', 'B Button'),
            ('P1_BUTTON3', 'X Button'),
            ('P1_BUTTON4', 'Y Button'),
            ('P1_BUTTON5', 'Left Bumper (LB)'),
            ('P1_BUTTON6', 'Right Bumper (RB)'),
            ('P1_BUTTON7', 'Left Trigger (LT)'),
            ('P1_BUTTON8', 'Right Trigger (RT)'),
            ('P1_BUTTON9', 'Left Stick Button (L3)'),
            ('P1_BUTTON10', 'Right Stick Button (R3)'),
            ('P1_JOYSTICK_UP', 'Left Stick Up'),
            ('P1_JOYSTICK_DOWN', 'Left Stick Down'),
            ('P1_JOYSTICK_LEFT', 'Left Stick Left'),
            ('P1_JOYSTICK_RIGHT', 'Left Stick Right')
        ]
        
        # Create a dictionary to store all the entry fields
        control_entries = {}
        
        # Helper function to get existing action for a control
        def get_existing_action(control_name):
            for player in game_data.get('players', []):
                for label in player.get('labels', []):
                    if label.get('name') == control_name:
                        return label.get('value', '')
            return ''
        
        # Header for the controls
        header_frame = ctk.CTkFrame(content_frame)
        header_frame.pack(fill="x", pady=5)
        
        control_label = ctk.CTkLabel(header_frame, text="Control", width=200, font=("Arial", 14, "bold"))
        control_label.pack(side=tk.LEFT, padx=5)
        
        action_label = ctk.CTkLabel(header_frame, text="Action/Function (leave empty to skip)", width=300, font=("Arial", 14, "bold"))
        action_label.pack(side=tk.LEFT, padx=5)
        
        # Create entry fields for each standard control
        for control_name, display_name in standard_controls:
            # Create a frame for each control
            control_frame = ctk.CTkFrame(content_frame)
            control_frame.pack(fill="x", pady=5)
            
            # Button/control name display
            ctk.CTkLabel(control_frame, text=display_name, width=200).pack(side=tk.LEFT, padx=5)
            
            # Get existing action if available
            existing_action = get_existing_action(control_name)
            
            # Create entry for action
            action_entry = ctk.CTkEntry(control_frame, width=400)
            action_entry.insert(0, existing_action)
            action_entry.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
            
            # Store the entry widget in our dictionary
            control_entries[control_name] = action_entry
        
        # Add a section for custom controls
        custom_frame = ctk.CTkFrame(content_frame)
        custom_frame.pack(fill="x", pady=(20, 5))
        
        ctk.CTkLabel(
            custom_frame, 
            text="Add Custom Controls (Optional)", 
            font=("Arial", 14, "bold")
        ).pack(pady=5)
        
        # Frame to hold custom control entries
        custom_controls_frame = ctk.CTkFrame(content_frame)
        custom_controls_frame.pack(fill="x", pady=5)
        
        # List to track custom controls
        custom_control_rows = []
        
        # Function to add a new custom control row
        def add_custom_control_row():
            row_frame = ctk.CTkFrame(custom_controls_frame)
            row_frame.pack(fill="x", pady=2)
            
            # Control name entry
            control_entry = ctk.CTkEntry(row_frame, width=200, placeholder_text="Custom Control (e.g., P1_BUTTON11)")
            control_entry.pack(side=tk.LEFT, padx=5)
            
            # Action entry
            action_entry = ctk.CTkEntry(row_frame, width=400, placeholder_text="Action/Function")
            action_entry.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
            
            # Remove button
            def remove_row():
                row_frame.pack_forget()
                row_frame.destroy()
                if row_data in custom_control_rows:
                    custom_control_rows.remove(row_data)
            
            remove_button = ctk.CTkButton(
                row_frame,
                text="❌",
                width=30,
                command=remove_row
            )
            remove_button.pack(side=tk.LEFT, padx=5)
            
            # Store row data
            row_data = {'frame': row_frame, 'control': control_entry, 'action': action_entry}
            custom_control_rows.append(row_data)
            
            return row_data
        
        # Add first custom row
        add_custom_control_row()
        
        # Add button for additional rows
        add_custom_button = ctk.CTkButton(
            custom_controls_frame,
            text="+ Add Another Custom Control",
            command=add_custom_control_row
        )
        add_custom_button.pack(pady=10)
        
        # Instructions
        instructions_frame = ctk.CTkFrame(editor)
        instructions_frame.pack(fill="x", padx=10, pady=10)
        
        instructions_text = """
        Instructions:
        1. Enter the action/function for each standard control you want to include
        2. Leave fields empty for controls you don't want to add
        3. Use the custom section to add any non-standard controls
        4. Click Save to update the game's controls in the database
        """
        
        ctk.CTkLabel(
            instructions_frame,
            text=instructions_text,
            justify="left"
        ).pack(padx=10, pady=10, anchor="w")
        
        # Buttons frame
        button_frame = ctk.CTkFrame(editor)
        button_frame.pack(fill="x", padx=10, pady=10)
        
        def save_controls():
            """Save controls directly to gamedata.json with support for adding missing games"""
            try:
                # Collect game properties
                game_description = description_var.get().strip() or game_name or rom_name
                game_playercount = playercount_var.get()
                game_buttons = buttons_var.get()
                game_sticks = sticks_var.get()
                game_alternating = alternating_var.get()
                
                # Load the gamedata.json file using centralized path
                gamedata_path = self.get_gamedata_path()
                with open(gamedata_path, 'r', encoding='utf-8') as f:
                    gamedata = json.load(f)
                
                # Find where to save the controls (main entry or clone)
                target_found = False
                
                # Process control entries - only include non-empty fields
                control_updates = {}
                
                # Add standard controls with non-empty values
                for control_name, entry in control_entries.items():
                    action_value = entry.get().strip()
                    
                    # Only add if action is not empty
                    if action_value:
                        control_updates[control_name] = action_value
                
                # Add custom controls with non-empty values
                for row_data in custom_control_rows:
                    control_name = row_data['control'].get().strip()
                    action_value = row_data['action'].get().strip()
                    
                    # Only add if both fields are filled
                    if control_name and action_value:
                        control_updates[control_name] = action_value
                
                print(f"Control updates to save: {len(control_updates)} controls")
                
                # Helper function to update controls in a gamedata structure
                def update_controls_in_data(data):
                    if 'controls' not in data:
                        data['controls'] = {}
                    
                    # First, check if we need to explicitly remove any controls
                    # This is for controls that existed in the original data but aren't in our updates
                    if 'controls' in data:
                        existing_controls = set(data['controls'].keys())
                        updated_controls = set(control_updates.keys())
                        
                        # Find controls that were in the original data but aren't in our updates
                        # These are ones that were explicitly removed or left blank
                        for removed_control in existing_controls - updated_controls:
                            # Remove from the data structure
                            if removed_control in data['controls']:
                                print(f"Removing control: {removed_control}")
                                del data['controls'][removed_control]
                    
                    # Update or add name attributes to controls
                    for control_name, action in control_updates.items():
                        if control_name in data['controls']:
                            # Update existing control
                            data['controls'][control_name]['name'] = action
                        else:
                            # Create new control with placeholder values
                            data['controls'][control_name] = {
                                'name': action,
                                'tag': '',
                                'mask': '0'
                            }
                            
                    return True
                
                # First check if the ROM has its own controls section
                if rom_name in gamedata and 'controls' in gamedata[rom_name]:
                    # Update the game properties too
                    gamedata[rom_name]['description'] = game_description
                    gamedata[rom_name]['playercount'] = game_playercount
                    gamedata[rom_name]['buttons'] = game_buttons
                    gamedata[rom_name]['sticks'] = game_sticks
                    gamedata[rom_name]['alternating'] = game_alternating
                    
                    update_controls_in_data(gamedata[rom_name])
                    target_found = True
                    
                # If not, check clones
                elif rom_name in gamedata and 'clones' in gamedata[rom_name]:
                    # Update the game properties too
                    gamedata[rom_name]['description'] = game_description
                    gamedata[rom_name]['playercount'] = game_playercount
                    gamedata[rom_name]['buttons'] = game_buttons
                    gamedata[rom_name]['sticks'] = game_sticks
                    gamedata[rom_name]['alternating'] = game_alternating
                    
                    # If ROM has no controls but has clones with controls, update the last clone
                    clone_with_controls = None
                    
                    for clone_name in gamedata[rom_name]['clones']:
                        if isinstance(gamedata[rom_name]['clones'], dict) and clone_name in gamedata[rom_name]['clones']:
                            clone_data = gamedata[rom_name]['clones'][clone_name]
                            if 'controls' in clone_data:
                                clone_with_controls = clone_name
                        
                    if clone_with_controls:
                        update_controls_in_data(gamedata[rom_name]['clones'][clone_with_controls])
                        target_found = True
                    else:
                        # No clone has controls either, add controls to the main ROM
                        update_controls_in_data(gamedata[rom_name])
                        target_found = True
                
                # If ROM is a clone, try to find it in its parent's clone list
                else:
                    clone_parent_found = False
                    for parent_name, parent_data in gamedata.items():
                        if 'clones' in parent_data and isinstance(parent_data['clones'], dict) and rom_name in parent_data['clones']:
                            # Update the clone's properties if supported
                            if isinstance(parent_data['clones'][rom_name], dict):
                                parent_data['clones'][rom_name]['description'] = game_description
                                parent_data['clones'][rom_name]['playercount'] = game_playercount
                                parent_data['clones'][rom_name]['buttons'] = game_buttons
                                parent_data['clones'][rom_name]['sticks'] = game_sticks
                                parent_data['clones'][rom_name]['alternating'] = game_alternating
                            
                            update_controls_in_data(parent_data['clones'][rom_name])
                            target_found = True
                            clone_parent_found = True
                            break
                    
                    # If it's not in any parent's clone list, it's a new game
                    if not clone_parent_found:
                        target_found = False
                
                # If no existing control structure was found anywhere, create a new entry
                if not target_found:
                    print(f"Game {rom_name} not found in gamedata.json - creating new entry")
                    # Create a new entry for this ROM
                    gamedata[rom_name] = {
                        "description": game_description,
                        "playercount": game_playercount,
                        "buttons": game_buttons,
                        "sticks": game_sticks,
                        "alternating": game_alternating,
                        "clones": {},
                        "controls": {}
                    }
                    
                    # Add all the controls to the new entry
                    update_controls_in_data(gamedata[rom_name])
                    target_found = True  # Now we have a target
                    
                    messagebox.showinfo(
                        "New Game Added", 
                        f"Added new game entry for {rom_name} to gamedata.json"
                    )
                
                # Save the updated gamedata back to the file
                with open(gamedata_path, 'w', encoding='utf-8') as f:
                    json.dump(gamedata, f, indent=2)
                    
                messagebox.showinfo("Success", f"Controls for {game_description} saved to gamedata.json!")
                
                # Force a reload of gamedata.json
                if hasattr(self, 'gamedata_json'):
                    del self.gamedata_json
                    self.load_gamedata_json()
                
                # Clear the in-memory cache to force reloading data
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache = {}
                    print("Cleared ROM data cache to force refresh")
                
                # Rebuild SQLite database if it's being used
                if hasattr(self, 'db_path') and self.db_path:
                    print("Rebuilding SQLite database to reflect control changes...")
                    self.build_gamedata_db()
                    print("Database rebuild complete")
                
                # Refresh any currently displayed data
                if self.current_game == rom_name and hasattr(self, 'on_game_select'):
                    print(f"Refreshing display for current game: {rom_name}")
                    # Create a mock event to trigger refresh
                    class MockEvent:
                        def __init__(self):
                            self.x = 10
                            self.y = 10
                    self.on_game_select(MockEvent())
                
                # Call cache clear, to remove the games cache if found
                self.perform_cache_clear(rom_name=rom_name, all_files=False)
                
                # Close the editor
                editor.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save controls: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Remove Game button (with confirmation)
        def remove_game():
            """Remove this game entirely from the database"""
            # Confirm with user
            if not messagebox.askyesno(
                "Confirm Removal", 
                f"Are you sure you want to completely remove {rom_name} from the database?\n\nThis action cannot be undone!",
                icon="warning"
            ):
                return
                
            try:
                # Load the gamedata.json file
                gamedata_path = self.get_gamedata_path()
                with open(gamedata_path, 'r', encoding='utf-8') as f:
                    gamedata = json.load(f)
                
                removed = False
                
                # Check if it's a direct entry
                if rom_name in gamedata:
                    # Direct removal
                    del gamedata[rom_name]
                    removed = True
                    print(f"Removed game: {rom_name}")
                else:
                    # Check if it's a clone in any parent's clone list
                    for parent_name, parent_data in gamedata.items():
                        if 'clones' in parent_data and isinstance(parent_data['clones'], dict):
                            if rom_name in parent_data['clones']:
                                # Remove from clone list
                                del parent_data['clones'][rom_name]
                                removed = True
                                print(f"Removed clone game: {rom_name} from parent: {parent_name}")
                                break
                
                if not removed:
                    messagebox.showerror("Error", f"Could not find {rom_name} in the database.")
                    return
                
                # Save the updated gamedata back to the file
                with open(gamedata_path, 'w', encoding='utf-8') as f:
                    json.dump(gamedata, f, indent=2)
                    
                # Force a reload of gamedata.json
                if hasattr(self, 'gamedata_json'):
                    del self.gamedata_json
                    self.load_gamedata_json()
                
                # Clear the in-memory cache to force reloading data
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache = {}
                    print("Cleared ROM data cache to force refresh")
                
                # Rebuild SQLite database if it's being used
                if hasattr(self, 'db_path') and self.db_path:
                    print("Rebuilding SQLite database to reflect game removal...")
                    self.build_gamedata_db()
                    print("Database rebuild complete")
                
                messagebox.showinfo("Success", f"{rom_name} has been removed from the database.")
                
                # Close the editor
                editor.destroy()
                
                # Refresh any currently displayed data
                # Since we removed the current game, we need to select a different game
                if self.current_game == rom_name:
                    self.current_game = None
                    self.game_title.configure(text="Select a game")
                    # Clear the control frame
                    for widget in self.control_frame.winfo_children():
                        widget.destroy()
                    # Update the game list
                    self.update_game_list()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to remove game: {str(e)}")
                import traceback
                traceback.print_exc()

        # Add a distinctive red "Remove Game" button
        remove_button = ctk.CTkButton(
            button_frame,
            text="Remove Game",
            command=remove_game,
            font=("Arial", 14),
            fg_color="#B22222",  # Firebrick red
            hover_color="#8B0000"  # Darker red on hover
        )
        remove_button.pack(side="left", padx=10, pady=5)

        
        # Save button
        save_button = ctk.CTkButton(
            button_frame,
            text="Save Controls",
            command=save_controls,
            font=("Arial", 14)
        )
        save_button.pack(side="left", padx=10, pady=5)
        
        # Close button
        close_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=editor.destroy,
            font=("Arial", 14)
        )
        close_button.pack(side="right", padx=10, pady=5)
    
    def build_gamedata_db(self):
        """Build SQLite database from gamedata.json for faster lookups"""
        print("Building SQLite database...")
        start_time = time.time()
        
        # Load gamedata.json if needed
        if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
            self.load_gamedata_json()
        
        # Verify gamedata is loaded
        if not self.gamedata_json:
            print("ERROR: No gamedata available to build database")
            return False
        
        try:
            # Create database connection
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Drop existing tables if they exist
            cursor.execute("DROP TABLE IF EXISTS games")
            cursor.execute("DROP TABLE IF EXISTS game_controls")
            cursor.execute("DROP TABLE IF EXISTS clone_relationships")
            
            # Create tables
            cursor.execute('''
            CREATE TABLE games (
                rom_name TEXT PRIMARY KEY,
                game_name TEXT,
                player_count INTEGER,
                buttons INTEGER,
                sticks INTEGER,
                alternating BOOLEAN,
                is_clone BOOLEAN,
                parent_rom TEXT
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE game_controls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rom_name TEXT,
                control_name TEXT,
                display_name TEXT,
                FOREIGN KEY (rom_name) REFERENCES games (rom_name)
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE clone_relationships (
                parent_rom TEXT,
                clone_rom TEXT,
                PRIMARY KEY (parent_rom, clone_rom),
                FOREIGN KEY (parent_rom) REFERENCES games (rom_name),
                FOREIGN KEY (clone_rom) REFERENCES games (rom_name)
            )
            ''')
            
            # Create indices for faster lookups
            cursor.execute("CREATE INDEX idx_game_controls_rom ON game_controls (rom_name)")
            cursor.execute("CREATE INDEX idx_clone_parent ON clone_relationships (parent_rom)")
            cursor.execute("CREATE INDEX idx_clone_child ON clone_relationships (clone_rom)")
            
            # Process the data
            games_inserted = 0
            controls_inserted = 0
            clones_inserted = 0
            
            # Process main games first
            for rom_name, game_data in self.gamedata_json.items():
                # Skip entries that are clones (handled separately below)
                if 'parent' in game_data:
                    continue
                    
                # Extract basic game properties
                game_name = game_data.get('description', rom_name)
                player_count = int(game_data.get('playercount', 1))
                buttons = int(game_data.get('buttons', 0))
                sticks = int(game_data.get('sticks', 0))
                alternating = 1 if game_data.get('alternating', False) else 0
                is_clone = 0  # Main entries aren't clones
                parent_rom = None
                
                # Insert game data
                cursor.execute(
                    "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (rom_name, game_name, player_count, buttons, sticks, alternating, is_clone, parent_rom)
                )
                games_inserted += 1
                
                # Extract and insert controls
                if 'controls' in game_data:
                    self._insert_controls(cursor, rom_name, game_data['controls'])
                    controls_inserted += len(game_data['controls'])
                
                # Process clones
                if 'clones' in game_data and isinstance(game_data['clones'], dict):
                    for clone_name, clone_data in game_data['clones'].items():
                        # Extract clone properties
                        clone_game_name = clone_data.get('description', clone_name)
                        clone_player_count = int(clone_data.get('playercount', player_count))  # Inherit from parent if not specified
                        clone_buttons = int(clone_data.get('buttons', buttons))
                        clone_sticks = int(clone_data.get('sticks', sticks))
                        clone_alternating = 1 if clone_data.get('alternating', alternating) else 0
                        
                        # Insert clone as a game
                        cursor.execute(
                            "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (clone_name, clone_game_name, clone_player_count, clone_buttons, clone_sticks, 
                            clone_alternating, 1, rom_name)  # is_clone=1, parent=rom_name
                        )
                        games_inserted += 1
                        
                        # Add clone relationship
                        cursor.execute(
                            "INSERT INTO clone_relationships VALUES (?, ?)",
                            (rom_name, clone_name)
                        )
                        clones_inserted += 1
                        
                        # Extract and insert clone controls
                        if 'controls' in clone_data:
                            self._insert_controls(cursor, clone_name, clone_data['controls'])
                            controls_inserted += len(clone_data['controls'])
            
            # Commit changes and close connection
            conn.commit()
            conn.close()
            
            elapsed_time = time.time() - start_time
            print(f"Database built in {elapsed_time:.2f}s with {games_inserted} games, {controls_inserted} controls")
            return True
            
        except sqlite3.Error as e:
            print(f"SQLite error: {e}")
            if 'conn' in locals():
                conn.close()
            return False
        except Exception as e:
            print(f"ERROR building database: {e}")
            import traceback
            traceback.print_exc()
            if 'conn' in locals():
                conn.close()
            return False

    def _insert_controls(self, cursor, rom_name, controls_dict):
        """Helper method to insert controls into the database"""
        for control_name, control_data in controls_dict.items():
            display_name = control_data.get('name', '')
            if display_name:
                cursor.execute(
                    "INSERT INTO game_controls (rom_name, control_name, display_name) VALUES (?, ?, ?)",
                    (rom_name, control_name, display_name)
                )
    
    def load_all_data(self):
        """Load all necessary data with improved debugging and error handling"""
        print("Starting load_all_data...")
        start_time = time.time()
        
        try:
            # Initialize ROM data cache
            self.rom_data_cache = {}
            
            # 1. Load settings
            print("Loading settings...")
            self.load_settings()
            
            # 2. Scan ROMs directory
            print("Scanning ROMs directory...")
            self.scan_roms_directory()
            print(f"Found {len(self.available_roms)} ROMs")
            
            # 3. Load default controls
            print("Loading default control configurations...")
            if self.load_default_config():
                print(f"Loaded {len(self.default_controls)} default control mappings")
            else:
                print("Failed to load default control config")
                
            # 4. Always load gamedata.json directly - this is critical for controls
            print("Loading gamedata.json...")
            self.load_gamedata_json()
            if hasattr(self, 'gamedata_json'):
                print(f"Loaded gamedata.json with {len(self.gamedata_json)} entries")
            else:
                print("Failed to load gamedata.json or it's empty")
                
            # 5. Load or build the database as a secondary source
            if hasattr(self, 'db_path'):
                db_needs_update = self.check_db_update_needed()
                if db_needs_update:
                    print("Database needs update, rebuilding...")
                    self.build_gamedata_db()
                else:
                    print("Using existing database")
            
            # 6. Load custom configs
            print("Loading custom configs...")
            self.load_custom_configs()
            if hasattr(self, 'custom_configs'):
                print(f"Loaded {len(self.custom_configs)} custom configurations")
            else:
                print("No custom configurations found")
            
            # 7. Update UI
            print("Updating UI elements...")
            self.update_stats_label()
            self.update_game_list()
            
            # 8. Run diagnostic checks
            self.run_data_diagnostic_checks()
            
            # 9. Auto-select first ROM
            self.select_first_rom()
            
            total_time = time.time() - start_time
            print(f"Data loading complete in {total_time:.2f}s")
            
        except Exception as e:
            print(f"Error loading data: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Data Loading Error", f"Failed to load application data: {e}")

    def run_data_diagnostic_checks(self):
        """Run diagnostic checks on the loaded data to help troubleshoot issues"""
        print("\n=== Running Diagnostic Checks ===")
        
        # Check if gamedata.json was loaded properly
        if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
            print("WARNING: gamedata.json is not loaded or empty")
            if hasattr(self, 'gamedata_path'):
                print(f"gamedata.json path: {self.gamedata_path}")
                if os.path.exists(self.gamedata_path):
                    file_size = os.path.getsize(self.gamedata_path)
                    print(f"File exists, size: {file_size} bytes")
                else:
                    print("File does not exist!")
        else:
            # Sample a few entries from gamedata.json
            print(f"gamedata.json contains {len(self.gamedata_json)} entries")
            sample_count = min(3, len(self.gamedata_json))
            if sample_count > 0:
                print(f"Sample entries:")
                for i, (key, value) in enumerate(list(self.gamedata_json.items())[:sample_count]):
                    print(f"  {i+1}. {key}")
                    if 'controls' in value:
                        print(f"     Has controls: {len(value['controls'])} controls defined")
                    else:
                        print("     No controls defined")
        
        # Check if SQLite database was loaded properly
        if hasattr(self, 'db_path'):
            if os.path.exists(self.db_path):
                print(f"SQLite database exists at: {self.db_path}")
                try:
                    # Check database content
                    import sqlite3
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    
                    # Check games table
                    cursor.execute("SELECT COUNT(*) FROM games")
                    games_count = cursor.fetchone()[0]
                    print(f"Database contains {games_count} games")
                    
                    # Check controls table
                    cursor.execute("SELECT COUNT(*) FROM game_controls")
                    controls_count = cursor.fetchone()[0]
                    print(f"Database contains {controls_count} control mappings")
                    
                    # Sample a few entries
                    cursor.execute("SELECT rom_name FROM games LIMIT 3")
                    sample_roms = [row[0] for row in cursor.fetchall()]
                    print(f"Sample ROMs in database: {', '.join(sample_roms)}")
                    
                    conn.close()
                except Exception as e:
                    print(f"Error checking database: {e}")
            else:
                print(f"SQLite database does not exist at: {self.db_path}")
        
        # Test getting game data for a few ROMs
        if hasattr(self, 'available_roms') and self.available_roms:
            print("\nTesting get_game_data for a few ROMs:")
            test_roms = list(self.available_roms)[:3]
            for rom in test_roms:
                print(f"Testing {rom}...")
                game_data = self.get_game_data(rom)
                if game_data:
                    print(f"  Success: Found game data for {rom}")
                    print(f"  Game Name: {game_data.get('gamename', 'Unknown')}")
                    players = game_data.get('players', [])
                    if players:
                        total_controls = sum(len(player.get('labels', [])) for player in players)
                        print(f"  Players: {len(players)}, Total Controls: {total_controls}")
                    else:
                        print("  No player controls defined")
                else:
                    print(f"  Failed: No game data found for {rom}")
        
        print("=== Diagnostic Checks Complete ===\n")
    
    def get_game_data(self, romname):
        """Get game data with improved error handling and type conversion"""
        # 1. Check cache first
        if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
            return self.rom_data_cache[romname]
        
        #print(f"Getting game data for {romname} (not in cache)")
        
        # Track lookup method for diagnostics
        lookup_method = None
        
        # 2. Try in-memory gamedata.json first (should be fastest and most direct)
        if hasattr(self, 'gamedata_json') and self.gamedata_json and romname in self.gamedata_json:
            #print(f"Found {romname} in gamedata.json")
            lookup_method = "gamedata.json"
            
            game_data = self.gamedata_json[romname]
            
            # Process the game data according to the expected output format
            # Simple name defaults - these are the fallback button names if none are specified
            default_actions = {
                'P1_JOYSTICK_UP': 'Up',
                'P1_JOYSTICK_DOWN': 'Down',
                'P1_JOYSTICK_LEFT': 'Left',
                'P1_JOYSTICK_RIGHT': 'Right',
                'P2_JOYSTICK_UP': 'Up',
                'P2_JOYSTICK_DOWN': 'Down',
                'P2_JOYSTICK_LEFT': 'Left',
                'P2_JOYSTICK_RIGHT': 'Right',
                'P1_BUTTON1': 'A Button',
                'P1_BUTTON2': 'B Button',
                'P1_BUTTON3': 'X Button',
                'P1_BUTTON4': 'Y Button',
                'P1_BUTTON5': 'LB Button',
                'P1_BUTTON6': 'RB Button',
                'P1_BUTTON7': 'LT Button',
                'P1_BUTTON8': 'RT Button',
                'P1_BUTTON9': 'Left Stick Button',
                'P1_BUTTON10': 'Right Stick Button',
                # Mirror P1 button names for P2
                'P2_BUTTON1': 'A Button',
                'P2_BUTTON2': 'B Button',
                'P2_BUTTON3': 'X Button',
                'P2_BUTTON4': 'Y Button',
                'P2_BUTTON5': 'LB Button',
                'P2_BUTTON6': 'RB Button',
                'P2_BUTTON7': 'LT Button',
                'P2_BUTTON8': 'RT Button',
                'P2_BUTTON9': 'Left Stick Button',
                'P2_BUTTON10': 'Right Stick Button',
            }
            
            # Handle type conversions for numeric fields - CRITICAL FIX
            try:
                # Ensure playercount, buttons and sticks are converted to integers
                # Use safe conversion with fallbacks
                player_count = 1
                if 'playercount' in game_data:
                    try:
                        # Convert string to int if needed
                        player_count = int(game_data['playercount'])
                    except (ValueError, TypeError):
                        # Fallback to default
                        print(f"Warning: Invalid playercount value '{game_data.get('playercount')}' for {romname}, using default")
                        player_count = 1
                        
                buttons_count = 0
                if 'buttons' in game_data:
                    try:
                        # Convert string to int if needed
                        buttons_count = int(game_data['buttons'])
                    except (ValueError, TypeError):
                        # Fallback to default
                        print(f"Warning: Invalid buttons value '{game_data.get('buttons')}' for {romname}, using default")
                        buttons_count = 0
                        
                sticks_count = 0
                if 'sticks' in game_data:
                    try:
                        # Convert string to int if needed
                        sticks_count = int(game_data['sticks'])
                    except (ValueError, TypeError):
                        # Fallback to default
                        print(f"Warning: Invalid sticks value '{game_data.get('sticks')}' for {romname}, using default")
                        sticks_count = 0
                        
                # Convert alternating to proper boolean
                alternating = False
                if 'alternating' in game_data:
                    # Handle different possible values
                    alt_value = game_data['alternating']
                    if isinstance(alt_value, bool):
                        alternating = alt_value
                    elif isinstance(alt_value, str):
                        alternating = alt_value.lower() in ('true', 'yes', '1')
                    elif isinstance(alt_value, int):
                        alternating = alt_value != 0
                        
                # Basic structure conversion
                converted_data = {
                    'romname': romname,
                    'gamename': game_data.get('description', romname),
                    'numPlayers': player_count,
                    'alternating': alternating,
                    'mirrored': False,
                    'miscDetails': f"Buttons: {buttons_count}, Sticks: {sticks_count}",
                    'players': []
                }
            except Exception as e:
                print(f"Error converting data types for {romname}: {e}")
                import traceback
                traceback.print_exc()
                # Fall back to safe defaults
                converted_data = {
                    'romname': romname,
                    'gamename': game_data.get('description', romname),
                    'numPlayers': 1,
                    'alternating': False,
                    'mirrored': False,
                    'miscDetails': "Error processing game data",
                    'players': []
                }
            
            # Find controls (direct or in a clone)
            controls = None
            if 'controls' in game_data:
                controls = game_data['controls']
                #Found direct controls for {romname}")
                
            # Process the controls
            if controls:
                # First pass - collect P1 button names to mirror to P2
                p1_button_names = {}
                for control_name, control_data in controls.items():
                    if control_name.startswith('P1_BUTTON') and 'name' in control_data:
                        button_num = control_name.replace('P1_BUTTON', '')
                        p1_button_names[f'P2_BUTTON{button_num}'] = control_data['name']
                        
                # Process player controls
                p1_controls = []
                p2_controls = []
                
                for control_name, control_data in controls.items():
                    # Add P1 controls
                    if control_name.startswith('P1_'):
                        # Skip non-joystick/button controls
                        if 'JOYSTICK' in control_name or 'BUTTON' in control_name:
                            # Get the friendly name
                            friendly_name = None
                            
                            # First check for explicit name
                            if 'name' in control_data and control_data['name']:
                                friendly_name = control_data['name']
                            # Then check for default actions
                            elif control_name in default_actions:
                                friendly_name = default_actions[control_name]
                            # Fallback to control name
                            else:
                                parts = control_name.split('_')
                                if len(parts) > 1:
                                    friendly_name = parts[-1]
                                
                            if friendly_name:
                                p1_controls.append({
                                    'name': control_name,
                                    'value': friendly_name
                                })
                    
                    # Add P2 controls - prioritize matching P1 button names
                    elif control_name.startswith('P2_'):
                        if 'JOYSTICK' in control_name or 'BUTTON' in control_name:
                            friendly_name = None
                            
                            # First check for explicit name
                            if 'name' in control_data and control_data['name']:
                                friendly_name = control_data['name']
                            # Then check if we have a matching P1 button name
                            elif control_name in p1_button_names:
                                friendly_name = p1_button_names[control_name]
                            # Then check defaults
                            elif control_name in default_actions:
                                friendly_name = default_actions[control_name]
                            # Fallback to control name
                            else:
                                parts = control_name.split('_')
                                if len(parts) > 1:
                                    friendly_name = parts[-1]
                                
                            if friendly_name:
                                p2_controls.append({
                                    'name': control_name,
                                    'value': friendly_name
                                })
                
                # Sort controls by name to ensure consistent order (Button 1 before Button 2)
                p1_controls.sort(key=lambda x: x['name'])
                p2_controls.sort(key=lambda x: x['name'])
                            
                # Add player 1 if we have controls
                if p1_controls:
                    converted_data['players'].append({
                        'number': 1,
                        'numButtons': buttons_count,
                        'labels': p1_controls
                    })

                # Add player 2 if we have controls
                if p2_controls:
                    converted_data['players'].append({
                        'number': 2,
                        'numButtons': buttons_count,
                        'labels': p2_controls
                    })
                    
            # If we still have no controls, let's generate default ones based on game properties
            elif not converted_data['players'] and (buttons_count > 0 or sticks_count > 0):
                num_buttons = buttons_count
                num_sticks = sticks_count
                p1_controls = []
                
                # Add joystick controls if sticks > 0
                if num_sticks > 0:
                    for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                        control_name = f'P1_JOYSTICK_{direction}'
                        p1_controls.append({
                            'name': control_name,
                            'value': default_actions.get(control_name, direction.capitalize())
                        })
                
                # Add buttons based on the number specified
                for i in range(1, min(num_buttons + 1, 11)):  # Limit to 10 buttons
                    control_name = f'P1_BUTTON{i}'
                    p1_controls.append({
                        'name': control_name,
                        'value': default_actions.get(control_name, f'Button {i}')
                    })
                
                # Sort controls by name
                p1_controls.sort(key=lambda x: x['name'])
                
                # Add player 1
                converted_data['players'].append({
                    'number': 1,
                    'numButtons': num_buttons,
                    'labels': p1_controls
                })
                
                # If two players, mirror controls - USING PROPER TYPE COMPARISON
                player_count = converted_data['numPlayers']
                alternating = converted_data['alternating']
                
                if player_count > 1 and not alternating:
                    p2_controls = []
                    
                    # Mirror P1 controls to P2
                    for p1_control in p1_controls:
                        p1_name = p1_control['name']
                        p2_name = p1_name.replace('P1_', 'P2_')
                        p2_controls.append({
                            'name': p2_name,
                            'value': p1_control['value']
                        })
                    
                    # Add player 2
                    converted_data['players'].append({
                        'number': 2,
                        'numButtons': num_buttons,
                        'labels': p2_controls
                    })
            
            # Mark as gamedata source
            converted_data['source'] = 'gamedata.json'
            
            # Show a diagnostic of what we found
            players = converted_data.get('players', [])
            if players:
                total_controls = sum(len(player.get('labels', [])) for player in players)
                #print(f"Processed game data for {romname}: {len(players)} players, {total_controls} controls")
            else:
                print(f"WARNING: No player controls found for {romname}")
            
            # Cache the result
            if hasattr(self, 'rom_data_cache'):
                self.rom_data_cache[romname] = converted_data
                
            return converted_data
        
        # 3. Try database if available
        if hasattr(self, 'db_path') and os.path.exists(self.db_path):
            db_data = self.get_game_data_from_db(romname)
            if db_data:
                lookup_method = "SQLite database"
                print(f"Found {romname} in SQLite database")
                
                # Cache the result
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache[romname] = db_data
                    
                return db_data
        
        # 4. Try parent lookup before giving up
        if hasattr(self, 'parent_lookup') and romname in self.parent_lookup:
            parent_rom = self.parent_lookup[romname]
            print(f"Looking up parent ROM {parent_rom} for clone {romname}")
            parent_data = self.get_game_data(parent_rom)  # Recursive call
            if parent_data:
                lookup_method = "parent lookup"
                print(f"Found parent data for {romname} via {parent_rom}")
                
                # Update with this ROM's info
                parent_data['romname'] = romname
                if hasattr(self, 'gamedata_json') and romname in self.gamedata_json:
                    parent_data['gamename'] = self.gamedata_json[romname].get('description', f"{romname} (Clone)")
                
                # Cache and return
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache[romname] = parent_data
                    
                return parent_data
        
        # Not found anywhere
        print(f"WARNING: No data found for {romname} via any method")
        return None

    # Also fix the get_game_data_from_db method to handle type conversions
    def get_game_data_from_db(self, romname):
        """Get control data for a ROM from the SQLite database with proper type handling"""
        if not os.path.exists(self.db_path):
            return None
        
        conn = None
        try:
            # Create connection
            conn = sqlite3.connect(self.db_path)
            # Don't use row factory to avoid case sensitivity issues
            cursor = conn.cursor()
            
            # Get basic game info
            cursor.execute("""
                SELECT rom_name, game_name, player_count, buttons, sticks, alternating, is_clone, parent_rom
                FROM games WHERE rom_name = ?
            """, (romname,))
            
            game_row = cursor.fetchone()
            
            if not game_row:
                # Check if this is a clone with a different name in the database
                cursor.execute("""
                    SELECT parent_rom FROM games WHERE rom_name = ? AND is_clone = 1
                """, (romname,))
                parent_result = cursor.fetchone()
                
                if parent_result and parent_result[0]:
                    # This is a clone, get parent data
                    parent_rom = parent_result[0]
                    conn.close()
                    return self.get_game_data_from_db(parent_rom)
                else:
                    # No data found
                    conn.close()
                    return None
            
            # Access columns by index instead of by name
            rom_name = game_row[0]
            game_name = game_row[1] 
            
            # Safely convert numeric values with error handling
            try:
                player_count = int(game_row[2])
            except (ValueError, TypeError):
                player_count = 1
                
            try:
                buttons = int(game_row[3])
            except (ValueError, TypeError):
                buttons = 0
                
            try:
                sticks = int(game_row[4])
            except (ValueError, TypeError):
                sticks = 0
            
            # Convert alternating to bool safely
            alternating = False
            alt_value = game_row[5]
            if isinstance(alt_value, bool):
                alternating = alt_value
            elif isinstance(alt_value, str):
                alternating = alt_value.lower() in ('true', 'yes', '1')
            elif isinstance(alt_value, int):
                alternating = alt_value != 0
                
            is_clone = bool(game_row[6])
            parent_rom = game_row[7]
            
            # Build game data structure
            game_data = {
                'romname': romname,
                'gamename': game_name,
                'numPlayers': player_count,
                'alternating': alternating,
                'mirrored': False,
                'miscDetails': f"Buttons: {buttons}, Sticks: {sticks}",
                'players': [],
                'source': 'gamedata.db'
            }
            
            # Get control data
            cursor.execute("""
                SELECT control_name, display_name FROM game_controls WHERE rom_name = ?
            """, (romname,))
            control_rows = cursor.fetchall()
            
            # If no controls found and this is a clone, try parent controls
            if not control_rows and is_clone and parent_rom:
                cursor.execute("""
                    SELECT control_name, display_name FROM game_controls WHERE rom_name = ?
                """, (parent_rom,))
                control_rows = cursor.fetchall()
                
            # Process controls
            p1_controls = []
            p2_controls = []
            
            # Default action names - used if no name is specified
            default_actions = {
                'P1_JOYSTICK_UP': 'Up',
                'P1_JOYSTICK_DOWN': 'Down',
                'P1_JOYSTICK_LEFT': 'Left',
                'P1_JOYSTICK_RIGHT': 'Right',
                'P2_JOYSTICK_UP': 'Up',
                'P2_JOYSTICK_DOWN': 'Down',
                'P2_JOYSTICK_LEFT': 'Left',
                'P2_JOYSTICK_RIGHT': 'Right',
                'P1_BUTTON1': 'A Button',
                'P1_BUTTON2': 'B Button',
                'P1_BUTTON3': 'X Button',
                'P1_BUTTON4': 'Y Button',
                'P1_BUTTON5': 'LB Button',
                'P1_BUTTON6': 'RB Button',
                'P1_BUTTON7': 'LT Button',
                'P1_BUTTON8': 'RT Button',
                'P1_BUTTON9': 'Left Stick Button',
                'P1_BUTTON10': 'Right Stick Button',
                'P2_BUTTON1': 'A Button',
                'P2_BUTTON2': 'B Button',
                'P2_BUTTON3': 'X Button',
                'P2_BUTTON4': 'Y Button',
                'P2_BUTTON5': 'LB Button',
                'P2_BUTTON6': 'RB Button',
                'P2_BUTTON7': 'LT Button',
                'P2_BUTTON8': 'RT Button',
                'P2_BUTTON9': 'Left Stick Button',
                'P2_BUTTON10': 'Right Stick Button',
            }
            
            for control in control_rows:
                control_name = control[0]  # First column
                display_name = control[1]  # Second column
                
                # If display_name is empty, try to use a default
                if not display_name and control_name in default_actions:
                    display_name = default_actions[control_name]
                
                # If still no display name, try to extract from control name
                if not display_name:
                    parts = control_name.split('_')
                    if len(parts) > 1:
                        display_name = parts[-1].capitalize()
                    else:
                        display_name = control_name  # Last resort
                
                if control_name.startswith('P1_'):
                    p1_controls.append({
                        'name': control_name,
                        'value': display_name
                    })
                elif control_name.startswith('P2_'):
                    p2_controls.append({
                        'name': control_name,
                        'value': display_name
                    })
            
            # If no controls found but we know about buttons/sticks, create default controls
            if not p1_controls and not p2_controls and (buttons > 0 or sticks > 0):
                # Create default P1 controls
                if sticks > 0:
                    # Add joystick controls
                    for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                        control_name = f'P1_JOYSTICK_{direction}'
                        p1_controls.append({
                            'name': control_name,
                            'value': default_actions.get(control_name, direction.capitalize())
                        })
                
                # Add buttons
                for i in range(1, min(buttons + 1, 11)):  # Limit to 10 buttons
                    control_name = f'P1_BUTTON{i}'
                    p1_controls.append({
                        'name': control_name,
                        'value': default_actions.get(control_name, f'Button {i}')
                    })
                
                # Add default P2 controls if it's a 2-player game and not alternating
                if player_count > 1 and not alternating:
                    # Mirror P1 controls
                    for p1_control in p1_controls:
                        p1_name = p1_control['name']
                        p2_name = p1_name.replace('P1_', 'P2_')
                        p2_controls.append({
                            'name': p2_name,
                            'value': p1_control['value']
                        })
            
            # Sort controls by name for consistent order
            p1_controls.sort(key=lambda x: x['name'])
            p2_controls.sort(key=lambda x: x['name'])
            
            # Add player 1 if we have controls
            if p1_controls:
                game_data['players'].append({
                    'number': 1,
                    'numButtons': buttons,
                    'labels': p1_controls
                })
                
            # Add player 2 if we have controls
            if p2_controls:
                game_data['players'].append({
                    'number': 2,
                    'numButtons': buttons,
                    'labels': p2_controls
                })
                
            conn.close()
            return game_data
            
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            if conn:
                conn.close()
            return None
        except Exception as e:
            print(f"Error getting game data from DB: {e}")
            import traceback
            traceback.print_exc()
            if conn:
                conn.close()
            return None
    
    # Modified version of get_game_data to use the database
    def get_game_data_with_db(self, romname):
        """Get control data for a ROM with database prioritization"""
        # First try to get from the database
        db_data = self.get_game_data_from_db(romname)
        if db_data:
            return db_data
        
        # If not found in database, fall back to the original method
        return self.get_game_data(romname)
    
    # Updated get_gamedata_path method to work when exe is in preview folder
    def get_gamedata_path(self):
        """Get the path to the gamedata.json file based on new folder structure"""
        # Always store gamedata.json in settings directory
        settings_path = os.path.join(self.settings_dir, "gamedata.json")
        
        # If the file doesn't exist in settings dir, check if it exists in mame root
        # and copy it to the settings dir
        if not os.path.exists(settings_path):
            legacy_paths = [
                os.path.join(self.mame_dir, "gamedata.json"),
                os.path.join(self.mame_dir, "preview", "gamedata.json")
            ]
            
            for legacy_path in legacy_paths:
                if os.path.exists(legacy_path):
                    print(f"Found gamedata.json at legacy path: {legacy_path}")
                    print(f"Copying to new location: {settings_path}")
                    import shutil
                    shutil.copy2(legacy_path, settings_path)
                    break
        
        # Create directory if it doesn't exist (redundant but safe)
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        
        return settings_path
    
    def create_game_list_with_edit(self, parent_frame, game_list, title_text):
        """Helper function to create a consistent list with edit button for games"""
        # Frame for the list
        list_frame = ctk.CTkFrame(parent_frame)
        list_frame.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Title
        ctk.CTkLabel(
            list_frame,
            text=title_text,
            font=("Arial", 14, "bold")
        ).pack(pady=(5, 10))
        
        # Create frame for list and scrollbar
        list_container = ctk.CTkFrame(list_frame)
        list_container.pack(expand=True, fill="both", padx=5, pady=5)
        
        # Create listbox
        game_listbox = tk.Listbox(list_container, font=("Arial", 12))
        game_listbox.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=game_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        game_listbox.config(yscrollcommand=scrollbar.set)
        
        # Populate listbox
        for rom, game_name in game_list:
            if rom == game_name:
                game_listbox.insert(tk.END, rom)
            else:
                game_listbox.insert(tk.END, f"{rom} - {game_name}")
        
        # Store the rom names for lookup when editing
        rom_map = [rom for rom, _ in game_list]
        
        # Button frame
        button_frame = ctk.CTkFrame(list_frame)
        button_frame.pack(fill="x", padx=10, pady=10)
        
        def edit_selected_game():
            selection = game_listbox.curselection()
            if not selection:
                messagebox.showinfo("Selection Required", "Please select a game to edit")
                return
                
            idx = selection[0]
            if idx < len(rom_map):
                rom = rom_map[idx]
                game_name = game_list[idx][1] if game_list[idx][0] != game_list[idx][1] else None
                self.show_control_editor(rom, game_name)
        
        edit_button = ctk.CTkButton(
            button_frame,
            text="Edit Selected Game",
            command=edit_selected_game
        )
        edit_button.pack(side=tk.LEFT, padx=5)
        
        return list_frame
    
    def identify_generic_controls(self):
        """Identify games that only have generic control names"""
        generic_control_games = []
        missing_control_games = []
        
        # Generic action names that indicate default mappings
        generic_actions = [
            "A Button", "B Button", "X Button", "Y Button", 
            "LB Button", "RB Button", "LT Button", "RT Button",
            "Up", "Down", "Left", "Right"
        ]
        
        for rom_name in sorted(self.available_roms):
            # First check if game data exists at all
            game_data = self.get_game_data(rom_name)
            if not game_data:
                missing_control_games.append(rom_name)
                continue
                
            # Check if controls are just generic
            has_custom_controls = False
            for player in game_data.get('players', []):
                for label in player.get('labels', []):
                    action = label['value']
                    # If we find any non-generic action, mark this game as having custom controls
                    if action not in generic_actions:
                        has_custom_controls = True
                        break
                if has_custom_controls:
                    break
                    
            # If no custom controls found, add to list
            if not has_custom_controls and game_data.get('players'):
                generic_control_games.append((rom_name, game_data.get('gamename', rom_name)))
        
        return generic_control_games, missing_control_games
    
    def show_preview(self):
        """Launch the preview window with caching to ensure default controls are included"""
        if not self.current_game:
            messagebox.showinfo("No Game Selected", "Please select a game first")
            return
                
        # Get complete game data with default values applied
        game_data = self.get_game_data(self.current_game)
        if not game_data:
            messagebox.showinfo("No Control Data", f"No control data found for {self.current_game}")
            return
        
        # IMPORTANT: Get custom control configuration if it exists
        cfg_controls = {}
        if self.current_game in self.custom_configs:
            # Parse the custom config
            cfg_controls = self.parse_cfg_controls(self.custom_configs[self.current_game])
            
            # Convert if XInput is enabled
            if self.use_xinput:
                cfg_controls = {
                    control: self.convert_mapping(mapping, True)
                    for control, mapping in cfg_controls.items()
                }
            
            # Modify game_data to include custom mappings
            # This is the critical part that's missing
            self.update_game_data_with_custom_mappings(game_data, cfg_controls)
        
        # Create cache directory if it doesn't exist yet
        cache_dir = os.path.join(self.preview_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        # Save the processed game data to the cache file
        cache_path = os.path.join(cache_dir, f"{self.current_game}_cache.json")
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(game_data, f, indent=2)
            print(f"Saved processed game data with defaults to cache: {cache_path}")
        except Exception as e:
            print(f"Warning: Could not save cache file: {e}")
        
        # Use the bridge to show the preview if available
        if hasattr(self, 'preview_bridge') and self.preview_bridge:
            success = self.preview_bridge.show_preview(
                self.current_game,
                game_data,
                self.hide_preview_buttons,
                clean_mode=False  # Default to regular mode
            )
            
            if not success:
                # Fall back to the command-line approach if bridge fails
                self._show_preview_legacy()
        else:
            # Use the legacy approach if bridge is not available
            self._show_preview_legacy()

    def _show_preview_legacy(self):
        """Legacy method to launch preview via command line when bridge is not available"""
        if not self.current_game:
            return
                
        # Handle PyInstaller frozen executable
        if getattr(sys, 'frozen', False):
            command = [
                sys.executable,
                "--preview-only",
                "--game", self.current_game
            ]
            if self.hide_preview_buttons:
                command.append("--no-buttons")
                
            # Launch and track the process
            process = subprocess.Popen(command)
            if not hasattr(self, 'preview_processes'):
                self.preview_processes = []
            self.preview_processes.append(process)
            return
        
        # Script-based approach
        try:
            # Find the main script
            script_path = None
            for path in [
                os.path.join(self.app_dir, "mame_controls_main.py"),
                os.path.join(self.mame_dir, "mame_controls_main.py"),
                os.path.join(self.preview_dir, "mame_controls_main.py")
            ]:
                if os.path.exists(path):
                    script_path = path
                    break
                    
            if not script_path:
                messagebox.showerror("Error", "Could not find mame_controls_main.py")
                return
                
            # Launch the script
            command = [
                sys.executable,
                script_path,
                "--preview-only",
                "--game", self.current_game
            ]
            
            if self.hide_preview_buttons:
                command.append("--no-buttons")
                
            # Launch and track the process
            process = subprocess.Popen(command)
            if not hasattr(self, 'preview_processes'):
                self.preview_processes = []
            self.preview_processes.append(process)
        except Exception as e:
            print(f"Error launching preview: {e}")
            messagebox.showerror("Error", f"Failed to launch preview: {str(e)}")

    # Add a new method for batch exporting images using the bridge
    def batch_export_images_with_bridge(self, output_dir, format="png", roms_to_process=None,
                                    hide_buttons=True, clean_mode=True, show_bezel=True, show_logo=True):
        """Use the preview bridge to batch export images without launching external processes"""
        if not hasattr(self, 'preview_bridge') or not self.preview_bridge:
            messagebox.showerror("Error", "Preview bridge not available")
            return False
            
        # If no ROMs provided, use current game
        if not roms_to_process:
            if not self.current_game:
                messagebox.showinfo("No Game Selected", "Please select a game first")
                return False
            roms_to_process = [self.current_game]
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Track results
        results = {
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        
        # Process each ROM
        for rom_name in roms_to_process:
            try:
                # Get game data
                game_data = self.get_game_data(rom_name)
                if not game_data:
                    print(f"Skipping {rom_name}: No game data found")
                    results["skipped"] += 1
                    continue
                    
                # Export the image
                output_path = os.path.join(output_dir, f"{rom_name}.{format}")
                success = self.preview_bridge.export_preview_image(
                    rom_name,
                    output_path,
                    format,
                    show_bezel,
                    show_logo
                )
                
                if success:
                    print(f"Exported {rom_name} to {output_path}")
                    results["success"] += 1
                else:
                    print(f"Failed to export {rom_name}")
                    results["failed"] += 1
                    
            except Exception as e:
                print(f"Error processing {rom_name}: {e}")
                results["failed"] += 1
        
        # Report results
        message = (
            f"Export complete:\n"
            f"- Successfully exported: {results['success']}\n"
            f"- Failed: {results['failed']}\n"
            f"- Skipped: {results['skipped']}"
        )
        
        messagebox.showinfo("Export Results", message)
        return results["success"] > 0

    def update_game_data_with_custom_mappings(self, game_data, cfg_controls):
        """Update game_data to include the custom control mappings from cfg_controls"""
        if not cfg_controls:
            return
            
        print(f"Updating game data with {len(cfg_controls)} custom mappings")
            
        # For each player in the game data
        for player in game_data.get('players', []):
            # For each control in this player
            for label in player.get('labels', []):
                control_name = label['name']
                
                # If this control has a custom mapping in the cfg file, store it
                if control_name in cfg_controls:
                    # Add or update a 'mapping' key to store the current mapping
                    label['mapping'] = cfg_controls[control_name]
                    
                    # You could also add a flag to indicate this is a custom mapping
                    label['is_custom'] = True
                    
                    print(f"Added custom mapping for {control_name}: {cfg_controls[control_name]}")
        
        # Print a sample of the updated data
        if game_data.get('players'):
            sample_player = game_data['players'][0]
            if sample_player.get('labels'):
                sample_control = sample_player['labels'][0]
                print(f"Sample updated control: {sample_control}")
        
        return game_data
    
    def toggle_hide_preview_buttons(self):
        """Toggle whether preview buttons should be hidden"""
        self.hide_preview_buttons = self.hide_buttons_toggle.get()
        
        # Save setting to config file
        self.save_settings()
        
    def save_settings(self):
        """Save current settings to the standard settings file"""
        settings = {
            "preferred_preview_screen": getattr(self, 'preferred_preview_screen', 1),
            "visible_control_types": self.visible_control_types,
            "hide_preview_buttons": getattr(self, 'hide_preview_buttons', False),
            "show_button_names": getattr(self, 'show_button_names', True)
        }
        
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
        """Load settings from JSON file in settings directory"""
        # Set sensible defaults
        self.preferred_preview_screen = 1
        self.visible_control_types = ["BUTTON"]
        self.hide_preview_buttons = False
        self.show_button_names = True
        
        # Load custom settings if available
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r') as f:
                    settings = json.load(f)
                    
                # Load screen preference
                if 'preferred_preview_screen' in settings:
                    self.preferred_preview_screen = settings['preferred_preview_screen']
                    
                # Load visibility settings
                if 'visible_control_types' in settings:
                    if isinstance(settings['visible_control_types'], list):
                        self.visible_control_types = settings['visible_control_types']
                    
                    # Make sure BUTTON is always included
                    if "BUTTON" not in self.visible_control_types:
                        self.visible_control_types.append("BUTTON")

                # Load hide preview buttons setting
                if 'hide_preview_buttons' in settings:
                    if isinstance(settings['hide_preview_buttons'], bool):
                        self.hide_preview_buttons = settings['hide_preview_buttons']
                    elif isinstance(settings['hide_preview_buttons'], int):
                        self.hide_preview_buttons = bool(settings['hide_preview_buttons'])
                    
                    # Update toggle if it exists
                    if hasattr(self, 'hide_buttons_toggle'):
                        if self.hide_preview_buttons:
                            self.hide_buttons_toggle.select()
                        else:
                            self.hide_buttons_toggle.deselect()
                            
                # Load show button names setting
                if 'show_button_names' in settings:
                    if isinstance(settings['show_button_names'], bool):
                        self.show_button_names = settings['show_button_names']
                    elif isinstance(settings['show_button_names'], int):
                        self.show_button_names = bool(settings['show_button_names'])
                        
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            # Create settings file with defaults
            self.save_settings()
                
        return {
            'preferred_preview_screen': self.preferred_preview_screen,
            'visible_control_types': self.visible_control_types,
            'hide_preview_buttons': self.hide_preview_buttons,
            'show_button_names': self.show_button_names
        }

    def convert_mapping(self, mapping: str, to_xinput: bool) -> str:
        """Convert between JOYCODE and XInput mappings"""
        xinput_mappings = {
            'JOYCODE_1_BUTTON1': 'XINPUT_1_A',           # A Button
            'JOYCODE_1_BUTTON2': 'XINPUT_1_B',           # B Button
            'JOYCODE_1_BUTTON3': 'XINPUT_1_X',           # X Button
            'JOYCODE_1_BUTTON4': 'XINPUT_1_Y',           # Y Button
            'JOYCODE_1_BUTTON5': 'XINPUT_1_SHOULDER_L',  # Left Bumper
            'JOYCODE_1_BUTTON6': 'XINPUT_1_SHOULDER_R',  # Right Bumper
            'JOYCODE_1_BUTTON7': 'XINPUT_1_TRIGGER_L',   # Left Trigger
            'JOYCODE_1_BUTTON8': 'XINPUT_1_TRIGGER_R',   # Right Trigger
            'JOYCODE_1_BUTTON9': 'XINPUT_1_THUMB_L',     # Left Stick Button
            'JOYCODE_1_BUTTON10': 'XINPUT_1_THUMB_R',    # Right Stick Button
            'JOYCODE_1_HATUP': 'XINPUT_1_DPAD_UP',       # D-Pad Up
            'JOYCODE_1_HATDOWN': 'XINPUT_1_DPAD_DOWN',   # D-Pad Down
            'JOYCODE_1_HATLEFT': 'XINPUT_1_DPAD_LEFT',   # D-Pad Left
            'JOYCODE_1_HATRIGHT': 'XINPUT_1_DPAD_RIGHT', # D-Pad Right
            'JOYCODE_2_BUTTON1': 'XINPUT_2_A',           # A Button
            'JOYCODE_2_BUTTON2': 'XINPUT_2_B',           # B Button
            'JOYCODE_2_BUTTON3': 'XINPUT_2_X',           # X Button
            'JOYCODE_2_BUTTON4': 'XINPUT_2_Y',           # Y Button
            'JOYCODE_2_BUTTON5': 'XINPUT_2_SHOULDER_L',  # Left Bumper
            'JOYCODE_2_BUTTON6': 'XINPUT_2_SHOULDER_R',  # Right Bumper
            'JOYCODE_2_BUTTON7': 'XINPUT_2_TRIGGER_L',   # Left Trigger
            'JOYCODE_2_BUTTON8': 'XINPUT_2_TRIGGER_R',   # Right Trigger
            'JOYCODE_2_BUTTON9': 'XINPUT_2_THUMB_L',     # Left Stick Button
            'JOYCODE_2_BUTTON10': 'XINPUT_2_THUMB_R',    # Right Stick Button
            'JOYCODE_2_HATUP': 'XINPUT_2_DPAD_UP',       # D-Pad Up
            'JOYCODE_2_HATDOWN': 'XINPUT_2_DPAD_DOWN',   # D-Pad Down
            'JOYCODE_2_HATLEFT': 'XINPUT_2_DPAD_LEFT',   # D-Pad Left
            'JOYCODE_2_HATRIGHT': 'XINPUT_2_DPAD_RIGHT', # D-Pad Right
        }
        joycode_mappings = {v: k for k, v in xinput_mappings.items()}
        
        if to_xinput:
            return xinput_mappings.get(mapping, mapping)
        else:
            return joycode_mappings.get(mapping, mapping)

    def format_control_name(self, control_name: str) -> str:
        """Convert MAME control names to friendly names based on input type"""
        if not self.use_xinput:
            return control_name
            
        # Split control name into parts (e.g., 'P1_BUTTON1' -> ['P1', 'BUTTON1'])
        parts = control_name.split('_')
        if len(parts) < 2:
            return control_name
            
        player_num = parts[0]  # e.g., 'P1'
        control_type = '_'.join(parts[1:])  # Join rest in case of JOYSTICK_UP etc.
        
        # Mapping dictionary for controls based on official XInput mapping
        control_mappings = {
            'BUTTON1': 'A Button',
            'BUTTON2': 'B Button',
            'BUTTON3': 'X Button',
            'BUTTON4': 'Y Button',
            'BUTTON5': 'LB Button',
            'BUTTON6': 'RB Button',
            'BUTTON7': 'LT Button',      # Left Trigger (axis)
            'BUTTON8': 'RT Button',      # Right Trigger (axis)
            'BUTTON9': 'LSB Button',     # Left Stick Button
            'BUTTON10': 'RSB Button',    # Right Stick Button
            'JOYSTICK_UP': 'Left Stick (Up)',
            'JOYSTICK_DOWN': 'Left Stick (Down)',
            'JOYSTICK_LEFT': 'Left Stick (Left)',
            'JOYSTICK_RIGHT': 'Left Stick (Right)',
            'JOYSTICK2_UP': 'Right Stick (Up)',
            'JOYSTICK2_DOWN': 'Right Stick (Down)',
            'JOYSTICK2_LEFT': 'Right Stick (Left)',
            'JOYSTICK2_RIGHT': 'Right Stick (Right)',
        }
        
        # Check if we have a mapping for this control
        if control_type in control_mappings:
            return f"{player_num} {control_mappings[control_type]}"
        
        return control_name
    
    def format_mapping_display(self, mapping: str) -> str:
        """Format the mapping string for display"""
        # Handle XInput mappings
        if "XINPUT" in mapping:
            # Convert XINPUT_1_A to "XInput A"
            parts = mapping.split('_')
            if len(parts) >= 3:
                button_part = ' '.join(parts[2:])
                return f"XInput {button_part}"
                
        # Handle JOYCODE mappings
        elif "JOYCODE" in mapping:
            # Special handling for axis/stick controls
            if "YAXIS_UP" in mapping or "DPADUP" in mapping:
                return "Joy Stick Up"
            elif "YAXIS_DOWN" in mapping or "DPADDOWN" in mapping:
                return "Joy Stick Down"
            elif "XAXIS_LEFT" in mapping or "DPADLEFT" in mapping:
                return "Joy Stick Left"
            elif "XAXIS_RIGHT" in mapping or "DPADRIGHT" in mapping:
                return "Joy Stick Right"
            elif "RYAXIS_NEG" in mapping:  # Right stick Y-axis negative
                return "Joy Right Stick Up"
            elif "RYAXIS_POS" in mapping:  # Right stick Y-axis positive
                return "Joy Right Stick Down"
            elif "RXAXIS_NEG" in mapping:  # Right stick X-axis negative
                return "Joy Right Stick Left"
            elif "RXAXIS_POS" in mapping:  # Right stick X-axis positive
                return "Joy Right Stick Right"
            
            # Standard button format for other joystick controls
            parts = mapping.split('_')
            if len(parts) >= 4:
                joy_num = parts[1]
                control_type = parts[2].capitalize()
                
                # Extract button number for BUTTON types
                if control_type == "Button" and len(parts) >= 4:
                    button_num = parts[3]
                    return f"Joy {joy_num} {control_type} {button_num}"
                else:
                    # Generic format for other controls
                    remainder = '_'.join(parts[3:])
                    return f"Joy {joy_num} {control_type} {remainder}"
                    
        return mapping
        
    def select_first_rom(self):
        """Select and display the first available ROM with improved performance"""
        # Get the first available ROM that has game data (using cache when possible)
        available_games = []
        
        # First check cache to avoid database hits
        if hasattr(self, 'rom_data_cache'):
            available_games = sorted([rom for rom in self.available_roms if rom in self.rom_data_cache])
            
        # If no cached games, do a minimal lookup
        if not available_games:
            if hasattr(self, 'db_path') and os.path.exists(self.db_path):
                # Use database for faster lookup
                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT rom_name FROM games ORDER BY rom_name LIMIT 5")
                    db_roms = [row[0] for row in cursor.fetchall()]
                    conn.close()
                    
                    # Filter to only those that are in available_roms
                    available_games = [rom for rom in db_roms if rom in self.available_roms]
                except:
                    pass
                    
        # If still no games found, do a full scan
        if not available_games:
            available_games = sorted([rom for rom in self.available_roms if self.get_game_data(rom)])
        
        if not available_games:
            print("No ROMs with game data found")
            return
                
        first_rom = available_games[0]
        
        # Check if the game list has content
        list_content = self.game_list.get("1.0", "end-1c")
        if not list_content.strip():
            print("Game list appears to be empty")
            return
        
        # Find the line with our ROM
        lines = list_content.split('\n')
        target_line = None
        
        for i, line in enumerate(lines):
            if first_rom in line:
                target_line = i + 1  # Lines are 1-indexed in Tkinter
                break
                    
        if target_line is None:
            return
        
        # Highlight the selected line
        self.highlight_selected_game(target_line)
        self.current_game = first_rom
        
        # Create a mock event targeting the line
        class MockEvent:
            def __init__(self):
                self.x = 10
                self.y = target_line * 20
        
        # IMPORTANT: Add a delay to allow the UI to fully initialize before selecting a game
        # This ensures the layout calculations are complete before showing game information
        self.after(200, lambda: self.on_game_select(MockEvent()))
            
    def highlight_selected_game(self, line_index):
        """Highlight the selected game in the list"""
        # Clear previous highlight if any
        if self.selected_line is not None:
            self.game_list._textbox.tag_remove(self.highlight_tag, f"{self.selected_line}.0", f"{self.selected_line + 1}.0")
        
        # Apply new highlight
        self.selected_line = line_index
        self.game_list._textbox.tag_add(self.highlight_tag, f"{line_index}.0", f"{line_index + 1}.0")
        
        # Ensure the selected item is visible
        self.game_list.see(f"{line_index}.0")
                   
    def display_controls_table(self, start_row, game_data, cfg_controls):
        """Display controls with reliable basic formatting - simplified but functional approach"""
        row = start_row
        
        print(f"Displaying controls for {game_data['romname']}")
        
        # Clear any existing widgets if present (including error messages or placeholders)
        for widget in self.control_frame.winfo_children():
            widget.destroy()
        
        # Create a frame for game info at the top
        info_frame = ctk.CTkFrame(self.control_frame)
        info_frame.pack(fill="x", padx=10, pady=10, expand=False)
        
        # Game info with clean formatting
        info_text = (
            f"ROM: {game_data['romname']}\n"
            f"Players: {game_data['numPlayers']}\n"
            f"Alternating: {game_data['alternating']}\n"
            f"Mirrored: {game_data['mirrored']}"
        )
        if game_data.get('miscDetails'):
            info_text += f"\n\nDetails: {game_data['miscDetails']}"

        info_label = ctk.CTkLabel(
            info_frame, 
            text=info_text,
            font=("Arial", 14),
            justify="left",
            anchor="w"
        )
        info_label.pack(fill="x", padx=15, pady=15, expand=True)
        
        # Create a frame for the controls table
        controls_frame = ctk.CTkFrame(self.control_frame)
        controls_frame.pack(fill="both", padx=10, pady=10, expand=True)
        
        # Configure the grid for the controls table
        column_weights = [1, 2, 1]  # Adjust column weights for better layout
        for i, weight in enumerate(column_weights):
            controls_frame.grid_columnconfigure(i, weight=weight)
        
        # Create table headers
        headers = ["Controller", "Game Action", "Mapping"]
        for col, header in enumerate(headers):
            header_label = ctk.CTkLabel(
                controls_frame,
                text=header,
                font=("Arial", 13, "bold")
            )
            header_label.grid(row=0, column=col, padx=5, pady=(5, 10), sticky="w")
        
        # Process controls from game_data and cfg_controls
        display_row = 1
        
        # Process P1 controls first, then P2
        for player_num in [1, 2]:
            # Find the player data
            player_data = None
            for player in game_data.get('players', []):
                if player.get('number') == player_num:
                    player_data = player
                    break
            
            if not player_data:
                continue  # Skip if no data for this player
            
            # Add a player header row
            player_header = ctk.CTkLabel(
                controls_frame,
                text=f"Player {player_num}",
                font=("Arial", 12, "bold"),
                fg_color=self.colors["primary"] if hasattr(self, "colors") else "#1E90FF",
                text_color="white",
                corner_radius=6
            )
            player_header.grid(row=display_row, column=0, columnspan=3, padx=5, pady=(10, 5), sticky="w")
            display_row += 1
            
            # Process controls for this player
            for control in player_data.get('labels', []):
                control_name = control.get('name', '')
                action = control.get('value', '')
                
                # Get custom mapping if available
                mapping = "Default"
                is_custom = False
                if control_name in cfg_controls:
                    mapping = cfg_controls[control_name]
                    is_custom = True
                
                # Skip if not visible (using a safe check)
                try:
                    if hasattr(self, 'is_control_visible') and not self.is_control_visible(control_name):
                        continue
                except Exception:
                    # Continue if the visibility check fails
                    pass
                
                # Control name label
                display_name = control_name
                if hasattr(self, 'format_control_name'):
                    try:
                        display_name = self.format_control_name(control_name)
                    except Exception:
                        pass
                        
                control_label = ctk.CTkLabel(
                    controls_frame,
                    text=display_name,
                    font=("Arial", 12)
                )
                control_label.grid(row=display_row, column=0, padx=5, pady=2, sticky="w")
                
                # Action label
                action_label = ctk.CTkLabel(
                    controls_frame,
                    text=action,
                    font=("Arial", 12)
                )
                action_label.grid(row=display_row, column=1, padx=5, pady=2, sticky="w")
                
                # Mapping label with formatting for custom mappings
                mapping_display = mapping
                if hasattr(self, 'format_mapping_display'):
                    try:
                        mapping_display = self.format_mapping_display(mapping)
                    except Exception:
                        pass
                        
                mapping_color = "#3A7CEA" if is_custom else "#AAAAAA"
                if hasattr(self, "colors"):
                    mapping_color = self.colors["primary"] if is_custom else self.colors["text_secondary"]
                
                mapping_label = ctk.CTkLabel(
                    controls_frame,
                    text=mapping_display,
                    font=("Arial", 12),
                    text_color=mapping_color
                )
                mapping_label.grid(row=display_row, column=2, padx=5, pady=2, sticky="w")
                
                display_row += 1
        
        # If no controls were displayed, show a message
        if display_row == 1:
            no_controls_label = ctk.CTkLabel(
                controls_frame,
                text="No controls found for this game",
                font=("Arial", 14),
                text_color="#AAAAAA"
            )
            no_controls_label.grid(row=1, column=0, columnspan=3, padx=5, pady=20)
        
        # If we have a custom config, add a section for it
        romname = game_data.get('romname', '')
        if romname and hasattr(self, 'custom_configs') and romname in self.custom_configs:
            cfg_frame = ctk.CTkFrame(self.control_frame)
            cfg_frame.pack(fill="x", padx=10, pady=10, expand=False)
            
            # Header for the config section
            cfg_header = ctk.CTkLabel(
                cfg_frame,
                text="Custom Configuration",
                font=("Arial", 13, "bold")
            )
            cfg_header.pack(anchor="w", padx=10, pady=(10, 5))
            
            # Display the raw config with a height limit
            config_text = ctk.CTkTextbox(
                cfg_frame,
                height=150,
                font=("Courier", 12)
            )
            config_text.pack(fill="x", padx=10, pady=10, expand=True)
            config_text.insert("1.0", self.custom_configs[romname])
            config_text.configure(state="disabled")
        
        return display_row


    def joycode_to_button(self, joycode):
        """Convert a JOYCODE mapping to a controller button name"""
        if not joycode or "JOYCODE" not in joycode:
            return None
            
        joycode_mapping = {
            "JOYCODE_1_BUTTON1": "P1 A Button",
            "JOYCODE_1_BUTTON2": "P1 B Button",
            "JOYCODE_1_BUTTON3": "P1 X Button",
            "JOYCODE_1_BUTTON4": "P1 Y Button",
            "JOYCODE_1_BUTTON5": "P1 LB Button",
            "JOYCODE_1_BUTTON6": "P1 RB Button",
            "JOYCODE_1_BUTTON7": "P1 LT Button",
            "JOYCODE_1_BUTTON8": "P1 RT Button",
            "JOYCODE_1_BUTTON9": "P1 Left Stick Button",
            "JOYCODE_1_BUTTON10": "P1 Right Stick Button",
            "JOYCODE_1_DPADUP": "P1 D-Pad Up",
            "JOYCODE_1_DPADDOWN": "P1 D-Pad Down",
            "JOYCODE_1_DPADLEFT": "P1 D-Pad Left",
            "JOYCODE_1_DPADRIGHT": "P1 D-Pad Right",
            "JOYCODE_1_YAXIS_UP_SWITCH": "P1 Left Stick Up",
            "JOYCODE_1_YAXIS_DOWN_SWITCH": "P1 Left Stick Down",
            "JOYCODE_1_XAXIS_LEFT_SWITCH": "P1 Left Stick Left",
            "JOYCODE_1_XAXIS_RIGHT_SWITCH": "P1 Left Stick Right"
        }
        
        return joycode_mapping.get(joycode)
    
    def compare_controls(self, game_data: Dict, cfg_controls: Dict) -> List[Tuple[str, str, str, bool]]:
        """Compare controls with game-specific and default mappings"""
        comparisons = []
        
        # Debug output
        has_defaults = hasattr(self, 'default_controls') and self.default_controls
        print(f"Compare controls: ROM={game_data['romname']}, " 
            f"Custom CFG={len(cfg_controls)}, "
            f"Default Controls Available={has_defaults and len(self.default_controls)}, "
            f"XInput={self.use_xinput}")
        
        # Convert default controls to XInput if needed
        default_controls = {}
        if has_defaults:
            for control, mapping in self.default_controls.items():
                if self.use_xinput:
                    default_controls[control] = self.convert_mapping(mapping, True)
                else:
                    default_controls[control] = mapping
        
        # Hardcoded default mappings to use when everything else fails
        standard_mappings = {
            'P1_BUTTON1': 'JOYCODE_1_BUTTON1',
            'P1_BUTTON2': 'JOYCODE_1_BUTTON2',
            'P1_BUTTON3': 'JOYCODE_1_BUTTON3',
            'P1_BUTTON4': 'JOYCODE_1_BUTTON4',
            'P1_BUTTON5': 'JOYCODE_1_BUTTON5',
            'P1_BUTTON6': 'JOYCODE_1_BUTTON6',
            'P1_JOYSTICK_UP': 'JOYCODE_1_DPADUP',
            'P1_JOYSTICK_DOWN': 'JOYCODE_1_DPADDOWN',
            'P1_JOYSTICK_LEFT': 'JOYCODE_1_DPADLEFT',
            'P1_JOYSTICK_RIGHT': 'JOYCODE_1_DPADRIGHT',
            'P2_BUTTON1': 'JOYCODE_2_BUTTON1',
            'P2_BUTTON2': 'JOYCODE_2_BUTTON2',
            'P2_BUTTON3': 'JOYCODE_2_BUTTON3',
            'P2_BUTTON4': 'JOYCODE_2_BUTTON4',
            'P2_BUTTON5': 'JOYCODE_2_BUTTON5',
            'P2_BUTTON6': 'JOYCODE_2_BUTTON6',
            'P2_JOYSTICK_UP': 'JOYCODE_2_DPADUP',
            'P2_JOYSTICK_DOWN': 'JOYCODE_2_DPADDOWN',
            'P2_JOYSTICK_LEFT': 'JOYCODE_2_DPADLEFT',
            'P2_JOYSTICK_RIGHT': 'JOYCODE_2_DPADRIGHT',
        }
        
        # Convert standard mappings to XInput if needed
        if self.use_xinput:
            xinput_mappings = {
                'JOYCODE_1_BUTTON1': 'XINPUT_1_A',
                'JOYCODE_1_BUTTON2': 'XINPUT_1_B',
                'JOYCODE_1_BUTTON3': 'XINPUT_1_X',
                'JOYCODE_1_BUTTON4': 'XINPUT_1_Y',
                'JOYCODE_1_BUTTON5': 'XINPUT_1_SHOULDER_L',
                'JOYCODE_1_BUTTON6': 'XINPUT_1_SHOULDER_R',
                'JOYCODE_1_DPADUP': 'XINPUT_1_DPAD_UP',
                'JOYCODE_1_DPADDOWN': 'XINPUT_1_DPAD_DOWN',
                'JOYCODE_1_DPADLEFT': 'XINPUT_1_DPAD_LEFT',
                'JOYCODE_1_DPADRIGHT': 'XINPUT_1_DPAD_RIGHT',
                'JOYCODE_2_BUTTON1': 'XINPUT_2_A',
                'JOYCODE_2_BUTTON2': 'XINPUT_2_B',
                'JOYCODE_2_BUTTON3': 'XINPUT_2_X',
                'JOYCODE_2_BUTTON4': 'XINPUT_2_Y',
                'JOYCODE_2_BUTTON5': 'XINPUT_2_SHOULDER_L',
                'JOYCODE_2_BUTTON6': 'XINPUT_2_SHOULDER_R',
                'JOYCODE_2_DPADUP': 'XINPUT_2_DPAD_UP',
                'JOYCODE_2_DPADDOWN': 'XINPUT_2_DPAD_DOWN',
                'JOYCODE_2_DPADLEFT': 'XINPUT_2_DPAD_LEFT',
                'JOYCODE_2_DPADRIGHT': 'XINPUT_2_DPAD_RIGHT',
            }
            
            for control, mapping in standard_mappings.items():
                if mapping in xinput_mappings:
                    standard_mappings[control] = xinput_mappings[mapping]
        
        # Get default controls from game data
        for player in game_data.get('players', []):
            player_num = player['number']
            for label in player.get('labels', []):
                control_name = label['name']
                default_label = label['value']
                
                # Game-specific cfg has highest priority
                if control_name in cfg_controls:
                    current_mapping = cfg_controls[control_name]
                    is_different = True  # Custom mapping
                # Default.cfg has second priority - already converted to XInput if needed
                elif control_name in default_controls:
                    current_mapping = default_controls[control_name]
                    is_different = False  # Default mapping from default.cfg
                # Use our hardcoded standard mappings as last resort
                elif control_name in standard_mappings:
                    current_mapping = standard_mappings[control_name]
                    is_different = False  # Standard mapping
                else:
                    current_mapping = "Not mapped"
                    is_different = False
                    
                comparisons.append((control_name, default_label, current_mapping, is_different))
        
        # Debug - print a few samples
        if comparisons:
            print(f"Generated {len(comparisons)} control comparisons. Samples:")
            for i, (name, label, mapping, diff) in enumerate(comparisons[:3]):
                src = "Custom" if diff else ("Default" if mapping != "Not mapped" else "None")
                print(f"  {name}: {label} -> {mapping} ({src})")
        
        return comparisons
        
    # Safe version of update_stats_label
    def update_stats_label(self):
        """Update the statistics label with error handling"""
        try:
            # Safely calculate unmatched ROMs
            try:
                unmatched = len(self.find_unmatched_roms())
            except Exception as e:
                print(f"Error finding unmatched ROMs: {e}")
                unmatched = 0
                
            matched = len(self.available_roms) - unmatched
            
            # Count custom configs
            custom_count = 0
            if hasattr(self, 'custom_configs'):
                custom_count = len(self.custom_configs)
                
            # Update stats text
            stats = (
                f"Available ROMs: {len(self.available_roms)} ({matched} with controls, {unmatched} without)\n"
                f"Custom configs: {custom_count}"
            )
            self.stats_label.configure(text=stats)
        except Exception as e:
            print(f"Error updating stats label: {e}")
            # Set a fallback message
            self.stats_label.configure(text="Stats unavailable")
    
    # Also fix the find_unmatched_roms method to safely handle failing lookups 
    def find_unmatched_roms(self) -> Set[str]:
        """Find ROMs that don't have matching control data with improved error handling"""
        matched_roms = set()
        for rom in self.available_roms:
            try:
                if self.get_game_data(rom):
                    matched_roms.add(rom)
            except Exception as e:
                print(f"Error checking ROM {rom}: {e}")
                # Consider it unmatched if there was an error
        return self.available_roms - matched_roms
    
    def show_unmatched_roms(self):
        """Display ROMs that don't have matching control data"""
        # Categorize ROMs
        matched_roms = []
        unmatched_roms = []

        for rom in sorted(self.available_roms):
            game_data = self.get_game_data(rom)
            if game_data:
                game_name = game_data['gamename']
                matched_roms.append((rom, game_name))
            else:
                unmatched_roms.append(rom)

        # Create new window
        self.unmatched_dialog = ctk.CTkToplevel(self)
        self.unmatched_dialog.title("ROM Control Data Analysis")
        self.unmatched_dialog.geometry("800x600")
        
        # Make it modal
        self.unmatched_dialog.transient(self)
        self.unmatched_dialog.grab_set()
        
        # Create tabs
        tabview = ctk.CTkTabview(self.unmatched_dialog)
        tabview.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Summary tab
        summary_tab = tabview.add("Summary")
        stats_text = (
            f"Total ROMs: {len(self.available_roms)}\n"
            f"Matched ROMs: {len(matched_roms)}\n"
            f"Unmatched ROMs: {len(unmatched_roms)}\n\n"
            f"Control data coverage: {(len(matched_roms) / max(len(self.available_roms), 1) * 100):.1f}%"
        )
        stats_label = ctk.CTkLabel(
            summary_tab,
            text=stats_text,
            font=("Arial", 14),
            justify="left"
        )
        stats_label.pack(padx=20, pady=20, anchor="w")
        
        # Unmatched ROMs tab
        unmatched_tab = tabview.add("Unmatched ROMs")
        if unmatched_roms:
            unmatched_text = ctk.CTkTextbox(unmatched_tab)
            unmatched_text.pack(expand=True, fill="both", padx=10, pady=10)
            
            for rom in sorted(unmatched_roms):
                unmatched_text.insert("end", f"{rom}\n")
                    
            unmatched_text.configure(state="disabled")
        else:
            ctk.CTkLabel(
                unmatched_tab,
                text="No unmatched ROMs found!",
                font=("Arial", 14)
            ).pack(expand=True)
        
        # Matched ROMs tab 
        matched_tab = tabview.add("Matched ROMs")
        if matched_roms:
            matched_text = ctk.CTkTextbox(matched_tab)
            matched_text.pack(expand=True, fill="both", padx=10, pady=10)
            
            for rom, game_name in sorted(matched_roms):
                matched_text.insert("end", f"{rom} - {game_name}\n")
                
            matched_text.configure(state="disabled")
        else:
            ctk.CTkLabel(
                matched_tab,
                text="No matched ROMs found!",
                font=("Arial", 14)
            ).pack(expand=True)
        
        # Select Summary tab by default
        tabview.set("Summary")
        
        # Add export button with embedded export function
        def export_analysis():
            try:
                file_path = os.path.join(self.mame_dir, "control_analysis.txt")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("MAME Control Data Analysis\n")
                    f.write("=========================\n\n")
                    f.write(stats_text + "\n\n")
                    
                    f.write("Matched ROMs:\n")
                    f.write("============\n")
                    for rom, game_name in sorted(matched_roms):
                        f.write(f"{rom} - {game_name}\n")
                    f.write("\n")
                    
                    f.write("Unmatched ROMs:\n")
                    f.write("==============\n")
                    for rom in sorted(unmatched_roms):
                        f.write(f"{rom}\n")
                        
                messagebox.showinfo("Export Complete", 
                                f"Analysis exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))
        
        # Export button using the locally defined function
        export_button = ctk.CTkButton(
            self.unmatched_dialog,
            text="Export Analysis",
            command=export_analysis
        )
        export_button.pack(pady=10)
        
        # Add close button
        close_button = ctk.CTkButton(
            self.unmatched_dialog,
            text="Close",
            command=self.unmatched_dialog.destroy
        )
        close_button.pack(pady=10)
        
    # To fix the specific issue with extracting ROMs with numbers like "1941"
    def update_game_list(self):
        """Update the game list to show all available ROMs with improved display for numbered ROMs"""
        self.game_list.delete("1.0", "end")
        
        # Get the current filter
        current_filter = self.filter_var.get() if hasattr(self, 'filter_var') else "all"
        
        # Sort available ROMs
        available_roms = sorted(self.available_roms)
        filtered_roms = []
        
        # Apply filtering
        for romname in available_roms:
            include = False
            
            if current_filter == "all":
                include = True
            elif current_filter == "with_controls":
                try:
                    include = self.get_game_data(romname) is not None
                except:
                    include = False
            elif current_filter == "no_controls":
                try:
                    include = self.get_game_data(romname) is None
                except:
                    include = True
            elif current_filter == "custom":
                include = hasattr(self, 'custom_configs') and romname in self.custom_configs
            
            if include:
                filtered_roms.append(romname)
        
        # Pre-fetch custom config status for all ROMs (faster than checking one by one)
        has_config = {}
        if hasattr(self, 'custom_configs'):
            has_config = {rom: rom in self.custom_configs for rom in filtered_roms}
        
        # Batch process with fewer database hits
        for romname in filtered_roms:
            # Check first if ROM data is in cache to avoid database lookups
            if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
                game_data = self.rom_data_cache[romname]
                has_data = True
            else:
                # Minimal check for existence - don't load full data yet
                has_data = hasattr(self, 'db_path') and self.rom_exists_in_db(romname) if hasattr(self, 'rom_exists_in_db') else False
                game_data = None
            
            # Create styled prefix icons
            if has_config.get(romname, False):
                config_icon = "🔧 "  # Wrench icon for custom config
            else:
                config_icon = "   "
                
            if has_data:
                data_icon = "✓ "  # Checkmark for ROMs with control data
                # Only fetch the full data if not in cache and needed for display
                if not game_data:
                    try:
                        game_data = self.get_game_data(romname)
                    except:
                        game_data = None
                
                if game_data:
                    display_name = f"{config_icon}{data_icon}{romname} - {game_data['gamename']}"
                else:
                    display_name = f"{config_icon}{data_icon}{romname}"
            else:
                data_icon = "✗ "  # X mark for ROMs without control data
                display_name = f"{config_icon}{data_icon}{romname}"
            
            # Insert the line with proper spacing
            self.game_list.insert("end", f"{display_name}\n")
        
        # If no ROMs found after filtering
        if not filtered_roms:
            self.game_list.insert("end", "No matching ROMs found\n")
        
        # Update stats count
        if hasattr(self, 'stats_label'):
            self.stats_label.configure(text=f"Showing {len(filtered_roms)} of {len(self.available_roms)} ROMs")

    def rom_exists_in_db(self, romname):
        """Quick check if ROM exists in database without loading full data"""
        if not os.path.exists(self.db_path):
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM games WHERE rom_name = ? LIMIT 1", (romname,))
            result = cursor.fetchone() is not None
            conn.close()
            return result
        except:
            return False
    
    def filter_games(self, *args):
        """Filter the game list based on search text with improved performance"""
        search_text = self.search_var.get().lower()
        self.game_list.delete("1.0", "end")
        
        # Reset the selected line when filtering
        self.selected_line = None
        
        # Only perform filtering if search text is provided
        if not search_text:
            self.update_game_list()  # Just show all games
            return
        
        # Use cached game data where possible for faster filtering
        filtered_count = 0
        
        # Track which ROMs match the filter for faster processing
        matching_roms = []
        
        for romname in sorted(self.available_roms):
            # Check if ROM name matches search
            if search_text in romname.lower():
                matching_roms.append(romname)
                continue
                
            # Check cached game data first (fastest)
            if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
                game_data = self.rom_data_cache[romname]
                if 'gamename' in game_data and search_text in game_data['gamename'].lower():
                    matching_roms.append(romname)
                    continue
        
        # Now display all matches efficiently
        for romname in matching_roms:
            # Get game data using cache when possible
            game_data = None
            if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
                game_data = self.rom_data_cache[romname]
            has_config = romname in self.custom_configs
            
            # Build the prefix
            prefix = "* " if has_config else "  "
            if game_data:
                prefix += "+ "
                display_name = f"{romname} - {game_data['gamename']}"
            else:
                prefix += "- "
                display_name = romname
            
            # Insert the line
            self.game_list.insert("end", f"{prefix}{display_name}\n")
            filtered_count += 1
        
        if filtered_count == 0:
            self.game_list.insert("end", "No matching ROMs found.\n")
    
    # Update scan_roms_directory method 
    def scan_roms_directory(self):
        """Scan the roms directory for available games with improved path handling"""
        debug_print("Scanning ROMs directory...")
        
        roms_dir = os.path.join(self.mame_dir, "roms")
        debug_print(f"Looking for ROMs in: {roms_dir}")
        
        if not os.path.exists(roms_dir):
            debug_print(f"ERROR: ROMs directory not found: {roms_dir}")
            messagebox.showwarning("No ROMs Found", f"ROMs directory not found: {roms_dir}")
            self.available_roms = set()
            return

        self.available_roms = set()  # Reset the set
        rom_count = 0

        try:
            for filename in os.listdir(roms_dir):
                # Skip directories and non-ROM files
                full_path = os.path.join(roms_dir, filename)
                if os.path.isdir(full_path):
                    continue
                    
                # Skip files with known non-ROM extensions
                extension = os.path.splitext(filename)[1].lower()
                if extension in ['.txt', '.ini', '.cfg', '.bat', '.exe', '.dll']:
                    continue
                    
                # Strip common ROM extensions
                base_name = os.path.splitext(filename)[0]
                self.available_roms.add(base_name)
                rom_count += 1
                
                if rom_count <= 5:  # Print first 5 ROMs as sample
                    debug_print(f"Found ROM: {base_name}")
            
            debug_print(f"Total ROMs found: {len(self.available_roms)}")
            if len(self.available_roms) > 0:
                debug_print(f"Sample of available ROMs: {list(self.available_roms)[:5]}")
            else:
                debug_print("WARNING: No ROMs were found!")
        except Exception as e:
            debug_print(f"Error scanning ROMs directory: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to scan ROMs directory: {e}")
    
    def load_text_positions(self, rom_name):
        """Load text positions with simplified path handling"""
        positions = {}
        
        # Try ROM-specific positions first
        rom_positions_file = os.path.join(self.settings_dir, f"{rom_name}_positions.json")
        if os.path.exists(rom_positions_file):
            try:
                with open(rom_positions_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Fall back to global positions
        global_positions_file = os.path.join(self.settings_dir, "global_positions.json")
        if os.path.exists(global_positions_file):
            try:
                with open(global_positions_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return positions  # Return empty dict if nothing found
            
    def load_text_appearance_settings(self):
        """Load text appearance settings with simplified path handling"""
        settings = {
            "font_family": "Arial",
            "font_size": 28,
            "title_font_size": 36,
            "bold_strength": 2,
            "y_offset": -40
        }
        
        # Check settings directory
        settings_file = os.path.join(self.settings_dir, "text_appearance_settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
            except Exception as e:
                print(f"Error loading text appearance settings: {e}")
        
        return settings
    
    def load_gamedata_json(self):
        """Load gamedata.json from the settings location with better error handling"""
        if hasattr(self, 'gamedata_json') and self.gamedata_json:
            return self.gamedata_json  # Already loaded
        
        # Get the canonical path to gamedata.json
        gamedata_path = self.get_gamedata_path()
        
        # Ensure the file exists
        if not os.path.exists(gamedata_path):
            print(f"ERROR: gamedata.json not found at {gamedata_path}")
            print("Searching for gamedata.json in alternate locations...")
            
            # Search in common locations
            alt_locations = [
                os.path.join(self.mame_dir, "gamedata.json"),
                os.path.join(self.app_dir, "gamedata.json"),
                os.path.join(self.preview_dir, "gamedata.json")
            ]
            
            for alt_path in alt_locations:
                if os.path.exists(alt_path):
                    print(f"Found gamedata.json at alternate location: {alt_path}")
                    gamedata_path = alt_path
                    break
            else:
                print("gamedata.json not found in any location")
                self.gamedata_json = {}
                self.parent_lookup = {}
                return {}
                    
        try:
            print(f"Loading gamedata.json from: {gamedata_path}")
            with open(gamedata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"Successfully loaded gamedata.json with {len(data)} entries")
            
            # Process the data for main games and clones
            self.gamedata_json = {}
            self.parent_lookup = {}
            
            # Count controls for diagnostics
            games_with_controls = 0
            total_controls = 0
            
            for rom_name, game_data in data.items():
                self.gamedata_json[rom_name] = game_data
                
                # Count controls
                if 'controls' in game_data and game_data['controls']:
                    games_with_controls += 1
                    total_controls += len(game_data['controls'])
                    
                # Build parent-child relationship
                if 'clones' in game_data and isinstance(game_data['clones'], dict):
                    for clone_name, clone_data in game_data['clones'].items():
                        # Store parent reference
                        clone_data['parent'] = rom_name
                        self.parent_lookup[clone_name] = rom_name
                        self.gamedata_json[clone_name] = clone_data
                        
                        # Count clone controls
                        if 'controls' in clone_data and clone_data['controls']:
                            games_with_controls += 1
                            total_controls += len(clone_data['controls'])
            
            print(f"Processed {len(self.gamedata_json)} total games")
            print(f"Found {games_with_controls} games with controls, {total_controls} total controls")
            print(f"Built parent lookup table with {len(self.parent_lookup)} entries")
            
            return self.gamedata_json
                    
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in gamedata.json: {str(e)}")
            # Try to read the file to see what's wrong
            try:
                with open(gamedata_path, 'r', encoding='utf-8') as f:
                    content = f.read(1000)  # Read first 1000 chars
                print(f"First 1000 chars of file: {content}")
            except Exception:
                pass
            self.gamedata_json = {}
            self.parent_lookup = {}
            return {}
        except Exception as e:
            print(f"ERROR loading gamedata.json: {str(e)}")
            import traceback
            traceback.print_exc()
            self.gamedata_json = {}
            self.parent_lookup = {}
            return {}
        
    # Add these remaining methods to the MAMEControlConfig class in mame_controls_tk.py:
    def ensure_preview_folder(self):
        """Create preview directory if it doesn't exist"""
        preview_dir = os.path.join(self.mame_dir, "preview")  # Keep as "preview" here
        if not os.path.exists(preview_dir):
            print(f"Creating preview directory: {preview_dir}")
            os.makedirs(preview_dir)
            
            # Copy any bundled preview images if running as executable
            if getattr(sys, 'frozen', False):
                bundled_preview = os.path.join(get_application_path(), "preview2")  # Use "preview2" here
                if os.path.exists(bundled_preview):
                    import shutil
                    for item in os.listdir(bundled_preview):
                        source = os.path.join(bundled_preview, item)
                        dest = os.path.join(preview_dir, item)
                        if os.path.isfile(source):
                            shutil.copy2(source, dest)
                            print(f"Copied: {item} to preview folder")
        return preview_dir

    def is_control_visible(self, control_name):
        """Check if a control type should be visible based on current settings"""
        if "JOYSTICK" in control_name:
            return "JOYSTICK" in self.visible_control_types
        elif "BUTTON" in control_name:
            return "BUTTON" in self.visible_control_types
        return True

    def apply_font_scaling(self, font_family, font_size):
        """Apply scaling factor for certain fonts that appear small"""
        # Scaling factors for various fonts
        scaling_factors = {
            "Times New Roman": 1.5,
            "Times": 1.5,
            "Georgia": 1.4,
            "Garamond": 1.7,
            "Baskerville": 1.6,
            "Palatino": 1.5,
            "Courier New": 1.3,
            "Courier": 1.3,
            "Consolas": 1.2,
            "Cambria": 1.4
        }
        
        # Apply scaling if font needs it
        scale = scaling_factors.get(font_family, 1.0)
        adjusted_font_size = int(font_size * scale)
        
        print(f"Font size adjustment: {font_family} - original: {font_size}, adjusted: {adjusted_font_size} (scale: {scale})")
        return adjusted_font_size
    
    # 1. First, create a special context manager to suppress messageboxes
    def preview_export_image(self, rom_name, game_data, output_dir, format="png", hide_buttons=True, clean_mode=True, show_bezel=True, show_logo=True):
        """Export a preview image for a ROM using direct PyQt interaction without showing individual messages"""
        try:
            print(f"Direct export of {rom_name} to {output_dir}")
            
            # Make sure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{rom_name}.{format}")
            
            # Create PreviewWindow directly
            from PyQt5.QtWidgets import QApplication, QMessageBox
            import sys
            
            # Initialize PyQt app if needed
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            
            # Import the preview module
            from mame_controls_preview import PreviewWindow
            
            # IMPORTANT: Create a dummy messagebox class to suppress all popups during export
            class DummyMessageBox:
                @staticmethod
                def information(*args, **kwargs):
                    return QMessageBox.Ok
                    
                @staticmethod
                def showinfo(*args, **kwargs):
                    return
                    
                @staticmethod
                def warning(*args, **kwargs):
                    return QMessageBox.Ok
                    
                @staticmethod
                def error(*args, **kwargs):
                    return QMessageBox.Ok
                    
                @staticmethod
                def critical(*args, **kwargs):
                    return QMessageBox.Ok
                    
                @staticmethod
                def question(*args, **kwargs):
                    return QMessageBox.Yes
            
            # Create preview window
            preview = PreviewWindow(
                rom_name,
                game_data,
                self.mame_dir,
                hide_buttons=hide_buttons,
                clean_mode=clean_mode
            )
            
            # Make sure the window is prepared properly
            preview.show()
            
            # Ensure bezel is loaded and visible if requested
            if show_bezel and hasattr(preview, 'integrate_bezel_support'):
                # Force bezel integration if method exists
                preview.integrate_bezel_support()
                
                # Make bezel visible if it exists
                if hasattr(preview, 'has_bezel') and preview.has_bezel:
                    preview.bezel_visible = True
                    if hasattr(preview, 'show_bezel_with_background'):
                        preview.show_bezel_with_background()
            
            # Set logo visibility
            if hasattr(preview, 'logo_visible') and hasattr(preview, 'logo_label'):
                preview.logo_visible = show_logo
                if preview.logo_label:
                    preview.logo_label.setVisible(show_logo)
            
            # PATCH: Replace all messagebox functions in the preview instance
            # Save the original messagebox functions
            original_messagebox = None
            if hasattr(preview, 'messagebox'):
                original_messagebox = preview.messagebox
                preview.messagebox = DummyMessageBox
                
            # Also patch potential direct QMessageBox usage
            original_qmessagebox = QMessageBox
            QMessageBox_showinfo = QMessageBox.information
            QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
            
            # Use the export method
            success = False
            try:
                if hasattr(preview, 'export_image_headless'):
                    print(f"Calling export_image_headless to {output_path}")
                    
                    result = preview.export_image_headless(output_path, format)
                    
                    # Check if file was created without showing a message
                    if result and os.path.exists(output_path):
                        print(f"Successfully exported {rom_name} to {output_path}")
                        success = True
                    else:
                        print(f"Failed to export {rom_name} - file not created")
                        success = False
                else:
                    print(f"ERROR: export_image_headless method not available for {rom_name}")
                    success = False
            finally:
                # IMPORTANT: Restore the original messagebox functions
                if original_messagebox is not None:
                    preview.messagebox = original_messagebox
                    
                # Restore QMessageBox original function
                QMessageBox.information = QMessageBox_showinfo
                
                # Clean up the window
                preview.close()
            
            return success
        except Exception as e:
            print(f"Error during export of {rom_name}: {e}")
            import traceback
            traceback.print_exc()
            return False

    # Modify the batch_export_images method in the MAMEControlConfig class
    def batch_export_images(self):
        """Show dialog to export multiple ROM preview images in batch with improved button accessibility"""
        # Create dialog with better size management
        dialog = ctk.CTkToplevel(self)
        dialog.title("Batch Export Preview Images")
        
        # Make dialog almost full screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight() 
        dialog_width = int(screen_width * 0.9)
        dialog_height = int(screen_height * 0.9)
        x = int((screen_width - dialog_width) / 2)
        y = int((screen_height - dialog_height) / 2)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        # Set minimum size to ensure buttons are visible
        dialog.minsize(width=800, height=700)
        
        dialog.transient(self)
        dialog.grab_set()
        
        # Create two main frames - the action buttons at bottom will stay fixed
        top_frame = ctk.CTkFrame(dialog)
        top_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        # Create title and buttons frame at the very top
        title_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        title_frame.pack(fill="x", padx=0, pady=0)
        
        # Title label - left aligned
        title_label = ctk.CTkLabel(
            title_frame,
            text="Batch Export Preview Images",
            font=("Arial", 18, "bold")
        )
        title_label.pack(side="left", padx=10, pady=10)
        
        # Add the action buttons directly to the title frame - right aligned
        # *** MOVED THE BUTTONS TO THE TOP RIGHT ***
        button_area = ctk.CTkFrame(title_frame, fg_color="transparent")
        button_area.pack(side="right", padx=10, pady=10)
        
        # Description label
        description = """
        This tool will generate preview images for multiple ROMs.
        Choose which ROMs to process and export settings below.
        Images will be saved to the preview/images directory.
        """
        desc_label = ctk.CTkLabel(
            top_frame,
            text=description,
            font=("Arial", 12),
            justify="left"
        )
        desc_label.pack(pady=(0, 10), padx=10, anchor="w")
        
        # Create scrollable content area for all the settings and ROM selection
        content_frame = ctk.CTkScrollableFrame(dialog)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Settings frame
        settings_frame = ctk.CTkFrame(content_frame)
        settings_frame.pack(fill="x", padx=10, pady=10)
        
        # -- Settings section layout --
        settings_section = ctk.CTkFrame(settings_frame)
        settings_section.pack(fill="x", padx=0, pady=0)
        
        # Use a grid layout for better organization of settings
        settings_section.grid_columnconfigure(0, weight=1)  # Display options column
        settings_section.grid_columnconfigure(1, weight=1)  # Output options column
        
        # === DISPLAY OPTIONS - LEFT SIDE ===
        display_options = ctk.CTkFrame(settings_section)
        display_options.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        # Title for display settings
        ctk.CTkLabel(
            display_options,
            text="Display Options",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(5, 10))
        
        # Hide buttons option
        hide_buttons_var = ctk.BooleanVar(value=True)
        hide_buttons_check = ctk.CTkCheckBox(
            display_options,
            text="Hide Control Buttons",
            variable=hide_buttons_var
        )
        hide_buttons_check.pack(anchor="w", padx=20, pady=2)
        
        # Clean mode option (no drag handles, etc)
        clean_mode_var = ctk.BooleanVar(value=True)
        clean_mode_check = ctk.CTkCheckBox(
            display_options,
            text="Clean Mode (No Drag Handles)",
            variable=clean_mode_var
        )
        clean_mode_check.pack(anchor="w", padx=20, pady=2)
        
        # Show bezel option
        show_bezel_var = ctk.BooleanVar(value=True)
        show_bezel_check = ctk.CTkCheckBox(
            display_options,
            text="Show Bezel (If Available)",
            variable=show_bezel_var
        )
        show_bezel_check.pack(anchor="w", padx=20, pady=2)
        
        # Show logo option
        show_logo_var = ctk.BooleanVar(value=True)
        show_logo_check = ctk.CTkCheckBox(
            display_options,
            text="Show Logo (If Available)",
            variable=show_logo_var
        )
        show_logo_check.pack(anchor="w", padx=20, pady=2)
        
        # Add option to suppress final completion message too
        show_completion_var = ctk.BooleanVar(value=False)
        show_completion_check = ctk.CTkCheckBox(
            display_options,
            text="Show Completion Message",
            variable=show_completion_var
        )
        show_completion_check.pack(anchor="w", padx=20, pady=2)
        
        # === OUTPUT OPTIONS - RIGHT SIDE ===
        output_options = ctk.CTkFrame(settings_section)
        output_options.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        # Title and options for output settings
        ctk.CTkLabel(
            output_options,
            text="Output Options",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(5, 10))

        # Image format - only PNG option
        format_frame = ctk.CTkFrame(output_options, fg_color="transparent")
        format_frame.pack(fill="x", padx=20, pady=2)

        ctk.CTkLabel(
            format_frame,
            text="Image Format:",
            width=100
        ).pack(side="left")

        format_var = ctk.StringVar(value="PNG")
        format_combo = ctk.CTkComboBox(
            format_frame,
            values=["PNG"],  # Only PNG option
            variable=format_var,
            width=120
        )
        format_combo.pack(side="left", padx=10)
        
        # Output directory
        output_frame = ctk.CTkFrame(output_options, fg_color="transparent")
        output_frame.pack(fill="x", padx=20, pady=2)
        
        ctk.CTkLabel(
            output_frame,
            text="Output Directory:",
            width=100
        ).pack(side="left")
        
        # Default to preview/images directory
        images_dir = os.path.join(self.preview_dir, "images")
        output_dir_var = ctk.StringVar(value=images_dir)
        
        dir_entry = ctk.CTkEntry(
            output_frame,
            textvariable=output_dir_var,
            width=300
        )
        dir_entry.pack(side="left", padx=10, fill="x", expand=True)
        
        def browse_directory():
            directory = tk.filedialog.askdirectory(
                initialdir=output_dir_var.get(),
                title="Select Output Directory"
            )
            if directory:
                output_dir_var.set(directory)
        
        browse_button = ctk.CTkButton(
            output_frame,
            text="Browse...",
            width=80,
            command=browse_directory
        )
        browse_button.pack(side="left", padx=5)
        
        # ROM selection frame
        rom_selection_frame = ctk.CTkFrame(content_frame)
        rom_selection_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title for ROM selection
        ctk.CTkLabel(
            rom_selection_frame,
            text="ROM Selection",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(5, 10))
        
        # ROM selection options
        selection_options_frame = ctk.CTkFrame(rom_selection_frame, fg_color="transparent")
        selection_options_frame.pack(fill="x", padx=10, pady=5)
        
        # Create a horizontal layout for the radio buttons
        radio_frame = ctk.CTkFrame(selection_options_frame, fg_color="transparent")
        radio_frame.pack(fill="x", padx=0, pady=0)
        
        # Selection mode - horizontal layout
        selection_mode_var = ctk.StringVar(value="all_with_controls")
        
        mode_all = ctk.CTkRadioButton(
            radio_frame,
            text="All ROMs with Controls",
            variable=selection_mode_var,
            value="all_with_controls"
        )
        mode_all.pack(side="left", padx=20, pady=2)
        
        mode_custom = ctk.CTkRadioButton(
            radio_frame,
            text="Custom Selection",
            variable=selection_mode_var,
            value="custom"
        )
        mode_custom.pack(side="left", padx=20, pady=2)
        
        mode_current = ctk.CTkRadioButton(
            radio_frame,
            text="Current ROM Only",
            variable=selection_mode_var,
            value="current"
        )
        mode_current.pack(side="left", padx=20, pady=2)
        
        # List of ROMs with checkboxes
        list_frame = ctk.CTkFrame(rom_selection_frame)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Button frame above the tree - for Select All/Deselect All
        button_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=5, pady=5)
        
        # ROM listbox with checkboxes using ttk
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create Treeview with a single column but configure to show checkboxes
        rom_tree = ttk.Treeview(
            tree_frame,
            columns=("rom_name", "game_name"),
            show="headings",
            selectmode="extended",
            height=15  # Fixed height of 15 rows
        )
        rom_tree.heading("rom_name", text="ROM Name")
        rom_tree.heading("game_name", text="Game Name")
        rom_tree.column("rom_name", width=200)
        rom_tree.column("game_name", width=500)
        
        rom_tree.pack(side="left", fill="both", expand=True)
        
        # Add a scrollbar
        tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=rom_tree.yview)
        tree_scrollbar.pack(side="right", fill="y")
        rom_tree.configure(yscrollcommand=tree_scrollbar.set)
        
        # Populate the tree with ROMs that have controls
        roms_with_data = []
        for rom in sorted(self.available_roms):
            game_data = self.get_game_data(rom)
            if game_data:
                roms_with_data.append((rom, game_data.get('gamename', rom)))
        
        # Insert ROM data into the tree
        for rom, game_name in roms_with_data:
            rom_tree.insert("", "end", values=(rom, game_name))
        
        def select_all_roms():
            for item in rom_tree.get_children():
                rom_tree.selection_add(item)
        
        def deselect_all_roms():
            rom_tree.selection_remove(rom_tree.get_children())
        
        select_all_button = ctk.CTkButton(
            button_frame,
            text="Select All",
            command=select_all_roms,
            width=120
        )
        select_all_button.pack(side="left", padx=5)
        
        deselect_all_button = ctk.CTkButton(
            button_frame,
            text="Deselect All",
            command=deselect_all_roms,
            width=120
        )
        deselect_all_button.pack(side="left", padx=5)
        
        # Create a status bar at the bottom that stays visible
        status_frame = ctk.CTkFrame(dialog)
        status_frame.pack(fill="x", side="bottom", padx=10, pady=10)
        
        # Progress bar
        progress_var = tk.DoubleVar(value=0.0)
        progress_bar = ctk.CTkProgressBar(status_frame)
        progress_bar.pack(fill="x", padx=10, pady=(5, 0))
        progress_bar.set(0)
        
        # Status label
        status_var = tk.StringVar(value="Ready")
        status_label = ctk.CTkLabel(
            status_frame,
            textvariable=status_var,
            font=("Arial", 12)
        )
        status_label.pack(pady=(5, 0))
        
        # Add flag to track cancellation
        cancel_processing = [False]
        
        # IMPORTANT: Main export function - Define this BEFORE creating the buttons
        def start_export():
            # Determine which ROMs to process
            roms_to_process = []
            
            mode = selection_mode_var.get()
            if mode == "all_with_controls":
                roms_to_process = [rom for rom, _ in roms_with_data]
                
                # Show warning for processing all ROMs
                if len(roms_to_process) > 10:  # Only show warning for a significant number of ROMs
                    if not messagebox.askyesno(
                        "Warning - Batch Processing",
                        f"You are about to process {len(roms_to_process)} ROMs, which may take a long time.\n\n"
                        f"This operation can be canceld using the Cancel Export button.\n\n"
                        f"Do you want to continue?",
                        icon="warning"
                    ):
                        return
                
            elif mode == "custom":
                selected_items = rom_tree.selection()
                for item in selected_items:
                    values = rom_tree.item(item, "values")
                    roms_to_process.append(values[0])
                    
                # Show warning if a large number of ROMs selected
                if len(roms_to_process) > 10:  # Only show warning for a significant number of ROMs
                    if not messagebox.askyesno(
                        "Warning - Batch Processing",
                        f"You are about to process {len(roms_to_process)} ROMs, which may take a long time.\n\n"
                        f"Do you want to continue?",
                        icon="warning"
                    ):
                        return
                    
            elif mode == "current" and self.current_game:
                roms_to_process.append(self.current_game)
            
            if not roms_to_process:
                messagebox.showinfo("No ROMs Selected", "Please select at least one ROM to process")
                return
            
            # Get settings
            settings = {
                "hide_buttons": hide_buttons_var.get(),
                "clean_mode": clean_mode_var.get(),
                "show_bezel": show_bezel_var.get(),
                "show_logo": show_logo_var.get(),
                "format": format_var.get().lower(),
                "output_dir": output_dir_var.get(),
                "show_completion": show_completion_var.get()
            }
            
            # Create output directory if it doesn't exist
            os.makedirs(settings["output_dir"], exist_ok=True)
            
            # Set up for processing
            total_roms = len(roms_to_process)
            processed = 0   
            failed = 0
            
            # Reset cancellation flag
            cancel_processing[0] = False
            
            # Update start button to show "Processing..."
            start_button.configure(state="disabled", text="Processing...")
            
            # Update cancel button to show it's active
            cancel_button.configure(text="Cancel Export", fg_color="#dc3545", hover_color="#c82333")
            
            # Update status
            status_var.set(f"Processing 0/{total_roms} ROMs...")
            progress_bar.set(0)
            dialog.update_idletasks()
            
            # Thread-safe update functions
            def update_progress(value):
                progress_var.set(value)
                progress_bar.set(value)
                dialog.update_idletasks()
            
            def update_status(text):
                status_var.set(text)
                dialog.update_idletasks()
            
            # Function to handle cancellation request
            def request_cancel():
                if messagebox.askyesno(
                    "Confirm Cancellation",
                    "Are you sure you want to cancel the export process?\n\n"
                    "Any images already exported will remain.",
                    icon="question"
                ):
                    cancel_processing[0] = True
                    update_status("Cancelling... Please wait for current operation to complete.")
                    cancel_button.configure(state="disabled", text="Cancelling...")
            
            # Update cancel button command
            cancel_button.configure(command=request_cancel)
            
            # Create a separate function for the actual processing
            def process_roms():
                nonlocal processed, failed
                
                for i, rom_name in enumerate(roms_to_process):
                    # Check for cancellation request
                    if cancel_processing[0]:
                        # Update status safely using the main thread
                        dialog.after(0, lambda s=f"Cancelled after processing {processed}/{total_roms} ROMs": update_status(s))
                        break
                    
                    # Update status safely using the main thread
                    dialog.after(0, lambda s=f"Processing {i+1}/{total_roms}: {rom_name}": update_status(s))
                    dialog.after(0, lambda v=(i + 0.5) / total_roms: update_progress(v))
                    
                    # Generate and save the image
                    try:
                        # Get the game data
                        game_data = self.get_game_data(rom_name)
                        if not game_data:
                            raise ValueError(f"No control data found for {rom_name}")
                        
                        # Export the image (using the modified preview_export_image function)
                        file_format = settings["format"].lower()
                        success = self.preview_export_image(
                            rom_name, 
                            game_data,
                            settings["output_dir"],
                            file_format,
                            settings["hide_buttons"],
                            settings["clean_mode"],
                            settings["show_bezel"],
                            settings["show_logo"]
                        )
                        
                        if success:
                            processed += 1
                        else:
                            failed += 1
                    except Exception as e:
                        print(f"Error processing {rom_name}: {e}")
                        import traceback
                        traceback.print_exc()
                        failed += 1
                    
                    # Update progress safely using the main thread
                    dialog.after(0, lambda v=(i + 1) / total_roms: update_progress(v))
                    
                    # Small sleep to allow UI updates
                    time.sleep(0.1)
                
                # All done - update status
                final_status = ""
                if cancel_processing[0]:
                    final_status = f"Cancelled: {processed} exported, {failed} failed"
                elif failed > 0:
                    final_status = f"Completed: {processed} successful, {failed} failed"
                else:
                    final_status = f"Completed: {processed} ROM preview images exported"
                
                # Update UI elements safely on the main thread
                dialog.after(0, lambda s=final_status: update_status(s))
                dialog.after(0, lambda: start_button.configure(state="normal", text="Start Export"))
                dialog.after(0, lambda: cancel_button.configure(
                    state="normal", 
                    text="Close", 
                    fg_color="#2B87D1",  # Reset to default color
                    hover_color="#1A6DAE",
                    command=dialog.destroy
                ))
                
                # Show completion message on the main thread - but only ONE at the end
                # And only if the user wants it
                if settings["show_completion"] and not cancel_processing[0]:
                    dialog.after(0, lambda p=processed, f=failed, d=settings["output_dir"]: 
                                messagebox.showinfo("Export Complete", 
                                                f"Exported {p} ROM preview images to {d}\n" +
                                                (f"Failed: {f}" if f > 0 else "")))
            
            # Start processing in a separate thread
            import threading
            import time
            
            process_thread = threading.Thread(target=process_roms)
            process_thread.daemon = True
            process_thread.start()

        # CRITICAL: Create the buttons AFTER defining the start_export function
        start_button = ctk.CTkButton(
            button_area,
            text="Start Export",
            command=start_export,  # Now this will properly reference the defined function
            width=150,
            height=40,
            font=("Arial", 14, "bold"),
            fg_color="#28a745",  # Green color
            hover_color="#218838"  # Darker green on hover
        )
        start_button.pack(side="left", padx=(0, 10))
        
        cancel_button = ctk.CTkButton(
            button_area,
            text="Cancel",
            command=dialog.destroy,
            width=120,
            height=40
        )
        cancel_button.pack(side="left") 
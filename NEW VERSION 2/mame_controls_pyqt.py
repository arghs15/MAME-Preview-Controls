import subprocess
import sys
import os
import json
import re
import time
from typing import Dict, Optional, Set, List, Tuple
import xml.etree.ElementTree as ET

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

class PositionManager:
    """A simplified position manager for the PyQt implementation"""
    def __init__(self, parent):
        self.parent = parent
        self.positions = {}


class MAMEControlConfig:
    def __init__(self, preview_only=False):
        # Initialize core attributes needed for preview functionality
        self.app_dir = get_application_path()
        self.mame_dir = get_mame_parent_dir(self.app_dir)
        
        # Set up directory structure
        self.initialize_directory_structure()
        
        # Initialize essential attributes
        self.visible_control_types = ["BUTTON", "JOYSTICK"]
        self.default_controls = {}
        self.gamedata_json = {}
        self.available_roms = set()
        self.custom_configs = {}
        self.current_game = None
        self.use_xinput = True
        self.preview_window = None
        self.preview_processes = []
        self.settings_cache = {}
        self.text_positions_cache = {}
        self.appearance_settings_cache = None
        
        # Logo size settings (as percentages)
        self.logo_width_percentage = 15
        self.logo_height_percentage = 15
        
        # Skip main window setup if in preview-only mode
        if not preview_only:
            # Load just enough settings
            self.load_settings()
            self.load_gamedata_json()
            self.hide()
    
    def initialize_directory_structure(self):
        """Initialize the standardized directory structure"""
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        self.settings_dir = os.path.join(self.preview_dir, "settings")
        self.info_dir = os.path.join(self.settings_dir, "info")
        self.cache_dir = os.path.join(self.preview_dir, "cache")

        # Create directories if they don't exist
        os.makedirs(self.preview_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        os.makedirs(self.info_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Define standard paths for key files
        self.gamedata_path = os.path.join(self.settings_dir, "gamedata.json")
        self.db_path = os.path.join(self.settings_dir, "gamedata.db")
        self.settings_path = os.path.join(self.settings_dir, "control_config_settings.json")
        
        return (os.path.exists(self.preview_dir) and 
                os.path.exists(self.settings_dir) and 
                os.path.exists(self.info_dir))

    def load_settings(self):
        """Load settings from JSON file in settings directory"""
        # Set sensible defaults
        self.preferred_preview_screen = 1
        self.visible_control_types = ["BUTTON"]
        self.hide_preview_buttons = False
        self.show_button_names = True
        self.input_mode = 'xinput'  # Add default input mode
        
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
                    
                # Load show button names setting
                if 'show_button_names' in settings:
                    if isinstance(settings['show_button_names'], bool):
                        self.show_button_names = settings['show_button_names']
                    elif isinstance(settings['show_button_names'], int):
                        self.show_button_names = bool(settings['show_button_names'])
                
                # Load input mode (new)
                if 'input_mode' in settings:
                    self.input_mode = settings['input_mode']
                    # Ensure valid value
                    if self.input_mode not in ['joycode', 'xinput', 'dinput']:
                        self.input_mode = 'xinput'
                        
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            # Create settings file with defaults
            self.save_settings()
                
        return {
            'preferred_preview_screen': self.preferred_preview_screen,
            'visible_control_types': self.visible_control_types,
            'hide_preview_buttons': self.hide_preview_buttons,
            'show_button_names': self.show_button_names,
            'input_mode': self.input_mode  # Add to return value
        }
        
    def save_settings(self):
        """Save current settings to the standard settings file"""
        settings = {
            "preferred_preview_screen": getattr(self, 'preferred_preview_screen', 1),
            "visible_control_types": self.visible_control_types,
            "hide_preview_buttons": getattr(self, 'hide_preview_buttons', False),
            "show_button_names": getattr(self, 'show_button_names', True),
            "input_mode": getattr(self, 'input_mode', 'xinput')  # Add input mode
        }
        
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_gamedata_json(self):
        """Load gamedata.json from the canonical settings location"""
        if hasattr(self, 'gamedata_json') and self.gamedata_json:
            return self.gamedata_json  # Already loaded
        
        # Ensure the file exists
        if not os.path.exists(self.gamedata_path):
            print(f"ERROR: gamedata.json not found at {self.gamedata_path}")
            self.gamedata_json = {}
            self.parent_lookup = {}
            return {}
                
        try:
            with open(self.gamedata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Process the data for main games and clones
            self.gamedata_json = {}
            self.parent_lookup = {}
            
            for rom_name, game_data in data.items():
                self.gamedata_json[rom_name] = game_data
                    
                # Build parent-child relationship
                if 'clones' in game_data:
                    for clone_name, clone_data in game_data['clones'].items():
                        # Store parent reference
                        clone_data['parent'] = rom_name
                        self.parent_lookup[clone_name] = rom_name
                        self.gamedata_json[clone_name] = clone_data
                
            return self.gamedata_json
                
        except Exception as e:
            print(f"ERROR loading gamedata.json: {str(e)}")
            self.gamedata_json = {}
            self.parent_lookup = {}
            return {}

    def get_gamedata_path(self):
        """Get the path to the gamedata.json file based on new folder structure"""
        # Always store gamedata.json in settings directory
        settings_path = os.path.join(self.settings_dir, "gamedata.json")
        
        # If file doesn't exist in settings dir, check legacy locations
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

    def load_text_positions(self, rom_name):
        """Load text positions from settings directory"""
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
    
    def load_game_data_from_cache(self, rom_name):
        """Load game data from cache with fallback to defaults for controls without names"""
        cache_path = os.path.join(self.cache_dir, f"{rom_name}_cache.json")
        
        if not os.path.exists(cache_path):
            print(f"No cache file found for {rom_name}")
            return None
            
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                game_data = json.load(f)
                
            # Apply defaults to any unnamed controls
            game_data = self.apply_default_control_names(game_data)
                        
            return game_data
        except Exception as e:
            print(f"Error loading cache for {rom_name}: {e}")
            return None
    
    def apply_default_control_names(self, game_data):
        """Apply default control names for any unnamed controls in the game data"""
        if not game_data or 'players' not in game_data:
            return game_data
        
        # Define default action names
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
        
        # Process each player's controls
        for player in game_data['players']:
            for control in player.get('labels', []):
                control_name = control.get('name', '')
                # If value is missing or empty, apply default
                if not control.get('value') and control_name in default_actions:
                    control['value'] = default_actions[control_name]
                    print(f"Applied default name '{default_actions[control_name]}' to {control_name}")
        
        return game_data

    def get_unified_game_data(self, rom_name):
        """Get game data with consistent defaults for both database and JSON sources"""
        # Try to get from normal method
        game_data = self.get_game_data(rom_name)
        
        # If we got data, apply defaults to any unnamed controls
        if game_data:
            game_data = self.apply_default_control_names(game_data)
            
        return game_data

    def show_preview(self):
        """Launch the preview window with simplified path handling"""
        if not self.current_game:
            print("No game selected. Please select a game first.")
            return
                
        # Get game data
        game_data = self.get_game_data(self.current_game)
        if not game_data:
            print(f"No control data found for {self.current_game}")
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
                
            # Add input mode argument
            if hasattr(self, 'input_mode'):
                command.extend(["--input-mode", self.input_mode])
                
            # Launch and track the process
            process = subprocess.Popen(command)
            self.preview_processes.append(process)
            return
        
        # Use script-based approach
        try:
            # First check the main app directory
            script_path = os.path.join(self.app_dir, "mame_controls_main.py")
            
            # If not found, check the MAME root directory
            if not os.path.exists(script_path):
                script_path = os.path.join(self.mame_dir, "mame_controls_main.py")
            
            # Still not found, check preview directory
            if not os.path.exists(script_path):
                script_path = os.path.join(self.preview_dir, "mame_controls_main.py")
                
            # If none of the above worked, we can't find the main script
            if not os.path.exists(script_path):
                print("Could not find mame_controls_main.py")
                return
                
            # Found the script, build the command
            command = [
                sys.executable,
                script_path,
                "--preview-only",
                "--game", self.current_game
            ]
            
            if self.hide_preview_buttons:
                command.append("--no-buttons")
                
            # Add input mode argument
            if hasattr(self, 'input_mode'):
                command.extend(["--input-mode", self.input_mode])
                
            # Launch and track the process
            process = subprocess.Popen(command)
            self.preview_processes.append(process)
        except Exception as e:
            print(f"Error launching preview: {e}")

    def show_preview_standalone(self, rom_name, auto_close=False, clean_mode=False):
        """Show the preview for a specific ROM without running the main app"""
        print(f"Starting standalone preview for ROM: {rom_name}")
        start_time = time.time()
        
        # Find the MAME directory (already in __init__)
        if not hasattr(self, 'mame_dir') or not self.mame_dir:
            self.mame_dir = self.find_mame_directory()
            if not self.mame_dir:
                print("Error: MAME directory not found!")
                return
        
        print(f"Using MAME directory: {self.mame_dir}")
        
        # Make sure preview and cache directories exist (minimal setup for cache check)
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        os.makedirs(self.preview_dir, exist_ok=True)
        
        # Define and check cache first - before any other operations
        cache_dir = os.path.join(self.preview_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"{rom_name}_cache.json")
        
        # Initialize ROM data cache if needed (minimal memory setup)
        if not hasattr(self, 'rom_data_cache'):
            self.rom_data_cache = {}
        
        # Set the current game
        self.current_game = rom_name
        
        # Check for cached data first - but apply defaults to any unnamed controls
        game_data = None
        if os.path.exists(cache_file):
            try:
                print(f"Found cache file: {cache_file}")
                
                # Load from cache without checking age
                game_data = self.load_game_data_from_cache(rom_name)
                
                if game_data:
                    print(f"Using cached game data for {rom_name}")
                    # Store in memory cache as well
                    self.rom_data_cache[rom_name] = game_data
                    data_load_time = time.time() - start_time
                    print(f"Game data loaded from cache in {data_load_time:.3f} seconds")
                else:
                    print("Warning: Cache file exists but contains no valid data")
            except Exception as e:
                print(f"Error loading cache: {e}")
                game_data = None
        
        # Only if we don't have valid cached data, continue with the full setup
        if not game_data:
            print("No valid cache found, proceeding with full data load...")
            
            # Now complete the settings directory setup only if needed
            self.settings_dir = os.path.join(self.preview_dir, "settings")
            self.info_dir = os.path.join(self.settings_dir, "info")
            os.makedirs(self.settings_dir, exist_ok=True)
            os.makedirs(self.info_dir, exist_ok=True)
            
            # Load settings (for screen preference)
            self.load_settings()
            
            # ADDED: Get command line arguments for screen, button visibility, and input mode
            import sys
            for i, arg in enumerate(sys.argv):
                if arg == '--screen' and i+1 < len(sys.argv):
                    try:
                        self.preferred_preview_screen = int(sys.argv[i+1])
                        print(f"OVERRIDE: Using screen {self.preferred_preview_screen} from command line")
                    except:
                        pass
                elif arg == '--no-buttons':
                    self.hide_preview_buttons = True
                    print(f"OVERRIDE: Hiding buttons due to command line flag")
                elif arg == '--input-mode' and i+1 < len(sys.argv):
                    self.input_mode = sys.argv[i+1]
                    if self.input_mode not in ['xinput', 'dinput', 'joycode']:
                        self.input_mode = 'xinput'  # Default to xinput if invalid
                    print(f"OVERRIDE: Using input mode {self.input_mode} from command line")
            
            # Check if we need to load the database for faster access
            db_path = os.path.join(self.settings_dir, "gamedata.db")
            using_db = os.path.exists(db_path)
            
            if using_db:
                print(f"Found gamedata database at: {db_path}")
                self.db_path = db_path
            
            # Load game data using the unified getter with defaults
            data_load_start = time.time()
            game_data = self.get_unified_game_data(rom_name)
            data_load_time = time.time() - data_load_start
            print(f"Game data loaded in {data_load_time:.3f} seconds")
            
            # Save game data to cache file for future use
            if game_data:
                try:
                    import json
                    with open(cache_file, 'w') as f:
                        json.dump(game_data, f)
                    print(f"Saved game data to cache: {cache_file}")
                except Exception as e:
                    print(f"Error saving cache: {e}")
        else:
            # We have valid cached data, so load just the settings needed for display
            self.load_settings()
            
            # Apply command line overrides for screen/buttons
            import sys
            for i, arg in enumerate(sys.argv):
                if arg == '--screen' and i+1 < len(sys.argv):
                    try:
                        self.preferred_preview_screen = int(sys.argv[i+1])
                        print(f"OVERRIDE: Using screen {self.preferred_preview_screen} from command line")
                    except:
                        pass
                elif arg == '--no-buttons':
                    self.hide_preview_buttons = True
                    print(f"OVERRIDE: Hiding buttons due to command line flag")
        
        # Exit if we still don't have game data
        if not game_data:
            print(f"Error: No control data found for {rom_name}")
            return
        
        # Start MAME process monitoring only if auto_close is enabled
        if auto_close:
            print("Auto-close enabled - preview will close when MAME exits")
            self.monitor_mame_process(check_interval=0.5)
        
        # Show the preview window
        try:
            from mame_controls_preview import PreviewWindow
            
            preview_start = time.time()
            
            # Create the preview window with correct positional parameter order
            self.preview_window = PreviewWindow(
                rom_name,             # 1st positional arg  
                game_data,            # 2nd positional arg
                self.mame_dir,        # 3rd positional arg
                None,                 # 4th positional arg (parent)
                self.hide_preview_buttons,  # 5th positional arg
                clean_mode,           # 6th positional arg
                self.input_mode       # New positional arg
            )
            
            # Mark this as a standalone preview (for proper cleanup)
            self.preview_window.standalone_mode = True
            
            # CRITICAL: Call the method to ensure consistent positioning
            if hasattr(self.preview_window, 'ensure_consistent_text_positioning'):
                self.preview_window.ensure_consistent_text_positioning()
            
            # Apply fullscreen settings
            from PyQt5.QtCore import Qt
            self.preview_window.setWindowFlags(
                Qt.WindowStaysOnTopHint | 
                Qt.FramelessWindowHint | 
                Qt.Tool  # Removes from taskbar
            )
            
            # Remove all window decorations and background
            self.preview_window.setAttribute(Qt.WA_NoSystemBackground, True)
            self.preview_window.setAttribute(Qt.WA_TranslucentBackground, True)
            
            # Apply stylesheets to remove ALL borders
            self.preview_window.setStyleSheet("""
                QMainWindow, QWidget {
                    border: none !important;
                    padding: 0px !important;
                    margin: 0px !important;
                    background-color: black;
                }
            """)
            
            # Get the exact screen geometry
            from PyQt5.QtWidgets import QDesktopWidget
            desktop = QDesktopWidget()
            screen_num = getattr(self, 'preferred_preview_screen', 1)  # Default to screen 1
            screen_geometry = desktop.screenGeometry(screen_num - 1)
            
            # Apply exact geometry before showing
            self.preview_window.setGeometry(screen_geometry)
            print(f"Applied screen geometry: {screen_geometry.width()}x{screen_geometry.height()}")
            
            # Final setup before display
            self.preview_window.showFullScreen()
            self.preview_window.activateWindow()
            self.preview_window.raise_()
            
            # Add a short delay to allow window to settle
            from PyQt5.QtCore import QTimer
            from PyQt5 import sip
            
            def check_window_dimensions():
                if hasattr(self, 'preview_window') and self.preview_window and not sip.isdeleted(self.preview_window):
                    self.ensure_full_dimensions(self.preview_window, screen_geometry)
                else:
                    print("Cannot check dimensions: preview window has been deleted")

            QTimer.singleShot(100, check_window_dimensions)
            
            preview_time = time.time() - preview_start
            total_time = time.time() - start_time
            print(f"Preview window created in {preview_time:.3f} seconds")
            print(f"Total startup time: {total_time:.3f} seconds")
            
        except Exception as e:
            print(f"Error showing preview: {str(e)}")
            import traceback
            traceback.print_exc()
            return

    def ensure_full_dimensions(self, window, screen_geometry):
        """Ensure the window and all children use the full dimensions"""
        # Add safety check to prevent access to deleted objects
        from PyQt5 import sip
        if not window or sip.isdeleted(window):
            print("Window was deleted before dimensions could be checked")
            return
            
        # Log all dimensions
        print(f"Window dimensions: {window.width()}x{window.height()}")
        if hasattr(window, 'central_widget'):
            print(f"Central widget: {window.central_widget.width()}x{window.central_widget.height()}")
        if hasattr(window, 'canvas'):
            print(f"Canvas: {window.canvas.width()}x{window.canvas.height()}")
        
        # Check if dimensions match screen geometry
        if window.width() != screen_geometry.width() or window.height() != screen_geometry.height():
            print("MISMATCH: Window size doesn't match screen size!")
            # Force resize again
            window.setGeometry(screen_geometry)
            
        # Force canvas size if it exists
        if hasattr(window, 'canvas'):
            if window.canvas.width() != screen_geometry.width() or window.canvas.height() != screen_geometry.height():
                print("MISMATCH: Canvas size doesn't match screen size, forcing resize")
                window.canvas.setFixedSize(screen_geometry.width(), screen_geometry.height())
                
        # Make one more attempt to ensure all parent widgets are also sized correctly
        if hasattr(window, 'central_widget'):
            window.central_widget.setFixedSize(screen_geometry.width(), screen_geometry.height())
            
        # Force a repaint
        window.repaint()
    
    def monitor_mame_process(self, check_interval=2.0):
        """Monitor MAME process and close preview when MAME closes"""
        import threading
        import time
        import subprocess
        import sys
        
        print("Starting MAME process monitor")
        
        def check_mame():
            mame_running = True
            check_count = 0
            last_state = True
            
            while mame_running:
                time.sleep(check_interval)
                check_count += 1
                
                # Skip checking if the preview window is gone
                if not hasattr(self, 'preview_window'):
                    print("Preview window closed, stopping monitor")
                    return
                
                # Check if any MAME process is running
                try:
                    if sys.platform == 'win32':
                        output = subprocess.check_output('tasklist /FI "IMAGENAME eq mame*"', shell=True)
                        mame_detected = b'mame' in output.lower()
                    else:
                        output = subprocess.check_output(['ps', 'aux'])
                        mame_detected = b'mame' in output
                    
                    # Only log when state changes
                    if mame_detected != last_state:
                        print(f"MAME running: {mame_detected}")
                        last_state = mame_detected
                    
                    mame_running = mame_detected
                except Exception as e:
                    print(f"Error checking MAME: {e}")
                    continue
            
            # MAME is no longer running - close preview
            print("MAME closed, closing preview")
            if hasattr(self, 'preview_window'):
                # Close the preview window
                if hasattr(self.preview_window, 'close'):
                    self.preview_window.close()
        
        # Start monitoring in a daemon thread
        monitor_thread = threading.Thread(target=check_mame, daemon=True)
        monitor_thread.start()
        print(f"Monitor thread started with check interval {check_interval}s")

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

        # 3. Check common MAME install paths
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

    def get_game_data(self, rom_name):
        """Simplified mock implementation to support preview functionality"""
        # In the slimmed down version, return basic game data structure
        # The tkinter script has its own implementation to get game data
        if rom_name in self.rom_data_cache:
            return self.rom_data_cache[rom_name]
            
        # Return a basic placeholder structure
        basic_data = {
            'romname': rom_name,
            'gamename': rom_name,
            'numPlayers': 2,
            'alternating': False,
            'mirrored': False,
            'miscDetails': "Default game data",
            'players': []
        }
        
        # Add to cache for future
        self.rom_data_cache[rom_name] = basic_data
        return basic_data

    def export_image_headless(self, output_path, format="png"):
        """Export preview image in headless mode"""
        try:
            print(f"Exporting preview image to {output_path}")
            
            # This is a placeholder for the actual implementation in PyQt
            # In a real implementation, this would render the preview window to an image
            
            from PyQt5.QtGui import QImage, QPainter
            from PyQt5.QtCore import Qt
            
            # Create a new image with the same size as the canvas
            if hasattr(self, 'canvas'):
                image = QImage(
                    self.canvas.width(),
                    self.canvas.height(),
                    QImage.Format_ARGB32
                )
                image.fill(Qt.transparent)
                
                # Create painter
                painter = QPainter(image)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.TextAntialiasing)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                
                # Render the canvas
                self.canvas.render(painter)
                
                # End painting
                painter.end()
                
                # Save the image
                result = image.save(output_path, format.upper())
                return result
            else:
                print("ERROR: canvas not available for export")
                return False
        except Exception as e:
            print(f"Error in export_image_headless: {e}")
            import traceback
            traceback.print_exc()
            return False
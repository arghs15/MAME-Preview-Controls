import subprocess
import sys
import os
import json
import time
from typing import Dict, Optional
import xml.etree.ElementTree as ET
from mame_utils import (
    get_application_path, 
    get_mame_parent_dir, 
    find_file_in_standard_locations
)

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
        self.info_dir = os.path.join(self.preview_dir, "info")
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

    # Add this inside class MAMEControlConfig in BOTH files:
    def find_file_in_standard_locations(self, filename, subdirs=None, copy_to_settings=False):
        """Wrapper to use the utility function with instance directories"""
        copy_to = None
        if copy_to_settings and hasattr(self, 'settings_dir'):
            copy_to = os.path.join(self.settings_dir, filename)
        
        return find_file_in_standard_locations(
            filename, 
            subdirs=subdirs,
            app_dir=self.app_dir,
            mame_dir=self.mame_dir,
            copy_to=copy_to
        )

    def find_mame_directory(self) -> Optional[str]:
        """Find the MAME directory containing necessary files"""
        # First, check if we can find gamedata.json
        gamedata_locations = self.find_file_in_standard_locations(
            "gamedata.json", 
            subdirs=[["preview"], ["preview", "settings"]]
        )
        
        if gamedata_locations:
            # Return the parent directory of where we found gamedata.json
            parent_dir = os.path.dirname(gamedata_locations)
            if parent_dir.endswith("preview") or parent_dir.endswith("settings"):
                return os.path.dirname(parent_dir)
            return parent_dir
        
        # Check common MAME install paths as fallback
        common_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), "MAME"),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), "MAME"),
            "C:\\MAME",
            "D:\\MAME"
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                print(f"Found MAME directory: {path}")
                return path
        
        print("Error: MAME directory not found")
        return None
    
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
        
        # Use the new method to find gamedata.json
        gamedata_path = self.find_file_in_standard_locations(
            "gamedata.json",
            subdirs=[["settings"], ["preview", "settings"]],
            copy_to_settings=True
        )
        
        if not gamedata_path:
            print(f"ERROR: gamedata.json not found")
            self.gamedata_json = {}
            self.parent_lookup = {}
            return {}
        
        # Now use the found path
        self.gamedata_path = gamedata_path
        
        try:
            with open(gamedata_path, 'r', encoding='utf-8') as f:
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

    # Complete fix for mame_controls_pyqt.py that handles both old and new cache formats
    def load_game_cache_with_validation(self, cache_path: str, rom_name: str) -> Optional[Dict]:
        """
        Load game cache file with support for both old and new cache formats
        ENHANCED: Handles metadata wrapper format from enhanced cache system
        """
        try:
            if not os.path.exists(cache_path):
                return None
                
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # NEW FORMAT: Cache file has metadata wrapper
            if isinstance(cache_data, dict) and 'game_data' in cache_data:
                print(f"✅ Found NEW format cache for {rom_name}")
                
                # Extract the actual game data from the wrapper
                game_data = cache_data['game_data']
                
                # Optional: Log cache metadata for debugging
                cached_mode = cache_data.get('input_mode', 'unknown')
                cached_friendly = cache_data.get('friendly_names', 'unknown')
                cached_xinput_only = cache_data.get('xinput_only_mode', 'unknown')
                
                print(f"📋 Cache metadata: mode={cached_mode}, friendly={cached_friendly}, xinput_only={cached_xinput_only}")
                
                # Validate that we have proper game data structure
                if not isinstance(game_data, dict):
                    print(f"❌ Invalid game_data structure in cache")
                    return None
                    
                if 'players' not in game_data:
                    print(f"❌ No players data in cached game_data")
                    return None
                    
                return game_data
                
            # OLD FORMAT: Cache file contains direct game data (PRE-ENHANCEMENT)
            elif isinstance(cache_data, dict) and 'players' in cache_data:
                print(f"🔄 Found OLD format cache for {rom_name} - will migrate after fresh load")
                
                # Don't use old cache - it lacks your new fallback mappings
                # Return None to trigger fresh loading with new enhancements
                return None
                
            # INVALID FORMAT: Neither format recognized
            else:
                print(f"❌ Unrecognized cache format for {rom_name}")
                print(f"📋 Cache keys: {list(cache_data.keys()) if isinstance(cache_data, dict) else 'not a dict'}")
                return None
                
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error in cache file: {e}")
            return None
        except Exception as e:
            print(f"❌ Error loading cache file: {e}")
            return None

    def show_preview_standalone(self, rom_name, auto_close=False, clean_mode=False):
        """Show the preview for a specific ROM - OPTIMIZED VERSION"""
        print(f"🚀 Starting optimized preview for ROM: {rom_name}")
        start_time = time.time()
        
        # PERFORMANCE FIX 1: Set directories immediately without validation
        self.app_dir = get_application_path()
        self.mame_dir = get_mame_parent_dir(self.app_dir)
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        self.settings_dir = os.path.join(self.preview_dir, "settings")
        self.cache_dir = os.path.join(self.preview_dir, "cache")
        self.current_game = rom_name
        
        # PERFORMANCE FIX 2: Fast cache loading
        cache_file = os.path.join(self.cache_dir, f"{rom_name}_cache.json")
        game_data = None
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # Handle both cache formats quickly
                if isinstance(cache_data, dict) and 'game_data' in cache_data:
                    game_data = cache_data['game_data']
                    print(f"✅ Loaded from NEW format cache")
                elif isinstance(cache_data, dict) and 'players' in cache_data:
                    game_data = cache_data
                    print(f"✅ Loaded from OLD format cache")
                
                if game_data:
                    cache_load_time = time.time() - start_time
                    print(f"📊 Cache loaded in {cache_load_time:.3f} seconds")
            except Exception as e:
                print(f"⚠️ Cache error: {e}")
        
        # Only do heavy processing if cache failed
        if not game_data:
            print(f"📂 Loading fresh data...")
            # Initialize ROM data cache if needed
            if not hasattr(self, 'rom_data_cache'):
                self.rom_data_cache = {}
            
            # Load minimal settings
            self.input_mode = getattr(self, 'input_mode', 'xinput')
            self.hide_preview_buttons = getattr(self, 'hide_preview_buttons', False)
            
            # Use unified game data getter
            game_data = self.get_unified_game_data(rom_name)
            
            if not game_data:
                print(f"❌ No game data found for {rom_name}")
                return
        
        # PERFORMANCE FIX 3: Skip auto_close setup unless needed
        if auto_close:
            print("🎮 Auto-close enabled")
            self.monitor_mame_process(check_interval=0.5)
        
        # PERFORMANCE FIX 4: Fast preview window creation
        try:
            from mame_controls_preview import PreviewWindow
            
            preview_start = time.time()
            
            # Create preview window with minimal setup
            self.preview_window = PreviewWindow(
                rom_name,
                game_data,
                self.mame_dir,
                None,  # parent
                getattr(self, 'hide_preview_buttons', False),
                clean_mode,
                getattr(self, 'input_mode', 'xinput')
            )
            
            # PERFORMANCE FIX 5: Minimal window setup
            self.preview_window.standalone_mode = True
            
            # Apply fullscreen settings quickly
            from PyQt5.QtCore import Qt
            self.preview_window.setWindowFlags(
                Qt.WindowStaysOnTopHint | 
                Qt.FramelessWindowHint | 
                Qt.Tool
            )
            
            # PERFORMANCE FIX 6: Skip heavy styling in preview mode
            # self.preview_window.setStyleSheet(...)  # SKIP FOR SPEED
            
            # Show fullscreen immediately
            from PyQt5.QtWidgets import QDesktopWidget
            desktop = QDesktopWidget()
            screen_num = getattr(self, 'preferred_preview_screen', 1)
            screen_geometry = desktop.screenGeometry(screen_num - 1)
            
            self.preview_window.setGeometry(screen_geometry)
            self.preview_window.showFullScreen()
            self.preview_window.activateWindow()
            self.preview_window.raise_()
            
            total_time = time.time() - start_time
            print(f"⚡ Total startup time: {total_time:.3f} seconds")
            
        except Exception as e:
            print(f"❌ Error showing preview: {str(e)}")
            import traceback
            traceback.print_exc()
    
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
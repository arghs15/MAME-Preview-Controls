"""
Updates to mame_controls_main.py to support pre-caching game data
which speeds up preview rendering when the user presses pause
"""

import atexit
import gc
import json
import os
import signal
import sys
import argparse
import traceback
# Add this to the very top of mame_controls_main.py:
import builtins
from mame_utils import get_application_path, get_mame_parent_dir

# Performance mode - disable all printing
PERFORMANCE_MODE = False

if PERFORMANCE_MODE:
    def no_print(*args, **kwargs):
        pass
    builtins.print = no_print

# Add this function somewhere in your mame_controls_main.py file
def cleanup_on_exit():
    """Clean up resources when the application exits"""
    print("Performing application cleanup on exit...")
    
    # Force garbage collection
    gc.collect()
    
    # Clean up any temporary directories or files
    temp_dir = getattr(sys, '_MEIPASS', None)
    if temp_dir and os.path.exists(temp_dir):
        try:
            print(f"Note: PyInstaller temp directory will be cleaned up: {temp_dir}")
        except:
            pass
    
    # Make sure all Qt resources are released
    try:
        from PyQt5.QtWidgets import QApplication
        if QApplication.instance():
            print("Forcing QApplication cleanup...")
            # Close any remaining windows
            for window in QApplication.instance().topLevelWidgets():
                window.close()
    except:
        pass
    
    print("Cleanup complete.")

atexit.register(cleanup_on_exit)

def validate_mame_directory(mame_dir):
    """
    Validate that the directory is a valid MAME installation
    Returns True if valid, False if not
    """
    if not os.path.exists(mame_dir):
        print(f"MAME directory not found: {mame_dir}")
        return False
        
    # Check for essential MAME folders/files
    required_items = ["roms", "mame.exe", "mame64.exe", "mame"]
    found_items = []
    
    for item in required_items:
        if os.path.exists(os.path.join(mame_dir, item)):
            found_items.append(item)
    
    # If we found at least one required item, consider it valid
    if found_items:
        print(f"MAME directory validated: {mame_dir}")
        print(f"Found MAME components: {', '.join(found_items)}")
        return True
    
    print(f"Directory exists but doesn't appear to be a MAME installation: {mame_dir}")
    return False

def validate_mame_directory(mame_dir):
    """
    Validate that the directory is a valid MAME installation
    Returns True if valid, False if not
    """
    if not os.path.exists(mame_dir):
        print(f"MAME directory not found: {mame_dir}")
        return False
        
    # Check for essential MAME folders/files
    required_items = ["roms", "mame.exe", "mame64.exe", "mame"]
    found_items = []
    
    for item in required_items:
        if os.path.exists(os.path.join(mame_dir, item)):
            found_items.append(item)
    
    # If we found at least one required item, consider it valid
    if found_items:
        print(f"MAME directory validated: {mame_dir}")
        print(f"Found MAME components: {', '.join(found_items)}")
        return True
    
    print(f"Directory exists but doesn't appear to be a MAME installation: {mame_dir}")
    return False

def show_mame_not_found_error(mame_dir):
    """Display a styled error message when MAME directory is not found"""
    error_message = (
        f"MAME directory not found or invalid!\n\n"
        f"Please make sure the MAME Controls application is placed in a subdirectory of your MAME installation."
        f"\n\nThe correct structure should be:\n"
        f"- MAME Directory (containing mame.exe, roms folder, etc.)\n"
        f"  └── preview (containing this application)"
    )
    
    print("ERROR: " + error_message.replace('\n', ' '))
    
    try:
        # Try using a styled Tkinter dialog
        import tkinter as tk
        from tkinter import font
        
        # Create a custom styled dialog
        def create_styled_error_dialog():
            # Create the root window
            root = tk.Tk()
            root.title("MAME Controls - MAME Not Found")
            root.configure(bg="#1e1e1e")  # Dark background
            
            # Set icon if available
            try:
                icon_paths = ["mame.ico", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mame.ico")]
                for icon_path in icon_paths:
                    if os.path.exists(icon_path):
                        root.iconbitmap(icon_path)
                        break
            except:
                pass
            
            # Calculate window size and position
            window_width = 500
            window_height = 350
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            x_position = (screen_width - window_width) // 2
            y_position = (screen_height - window_height) // 2
            root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
            
            # Create a frame with border
            main_frame = tk.Frame(
                root, 
                bg="#1e1e1e",
                highlightbackground="#1f538d",  # Blue border
                highlightthickness=2
            )
            main_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            # Add error icon
            try:
                from PIL import Image, ImageTk
                # Create a basic error icon if PIL is available
                icon_size = 48
                icon_frame = tk.Frame(main_frame, bg="#1e1e1e", width=icon_size, height=icon_size)
                icon_frame.pack(pady=(20, 5))
                
                # Create a red circle with exclamation mark
                canvas = tk.Canvas(icon_frame, width=icon_size, height=icon_size, 
                                 bg="#1e1e1e", highlightthickness=0)
                canvas.pack()
                
                # Draw a red circle
                canvas.create_oval(4, 4, icon_size-4, icon_size-4, fill="#c41e3a", outline="")
                
                # Draw an exclamation mark
                canvas.create_rectangle(22, 14, 26, 32, fill="white", outline="")
                canvas.create_oval(22, 36, 26, 40, fill="white", outline="")
            except:
                # Skip icon if PIL not available
                pass
            
            # Add title
            title_font = font.Font(family="Segoe UI", size=12, weight="bold")
            title_label = tk.Label(
                main_frame,
                text="MAME Directory Not Found",
                font=title_font,
                fg="white",
                bg="#1e1e1e"
            )
            title_label.pack(pady=(10, 15))
            
            # Add detailed message
            message_frame = tk.Frame(main_frame, bg="#1e1e1e", padx=20)
            message_frame.pack(fill="both", expand=True, padx=10, pady=0)
            
            text_font = font.Font(family="Segoe UI", size=10)
            message_text = tk.Text(
                message_frame,
                wrap=tk.WORD,
                bg="#2d2d2d",
                fg="white",
                font=text_font,
                bd=1,
                padx=10,
                pady=10,
                relief=tk.FLAT,
                highlightbackground="#3d3d3d",
                highlightthickness=1
            )
            message_text.insert(tk.END, error_message)
            message_text.config(state=tk.DISABLED)  # Make readonly
            message_text.pack(fill="both", expand=True)
            
            # Add OK button
            button_frame = tk.Frame(main_frame, bg="#1e1e1e")
            button_frame.pack(fill="x", pady=(15, 20))
            
            def on_ok():
                root.destroy()
                
            ok_button = tk.Button(
                button_frame,
                text="OK",
                command=on_ok,
                bg="#1f538d",  # Blue background
                fg="white",
                font=font.Font(family="Segoe UI", size=10, weight="bold"),
                padx=20,
                pady=5,
                relief=tk.FLAT,
                activebackground="#2a82da",
                activeforeground="white",
                borderwidth=0,
                highlightthickness=0,
                cursor="hand2"
            )
            ok_button.pack()
            
            # Make the OK button the default (Enter key)
            ok_button.focus_set()
            root.bind("<Return>", lambda event: on_ok())
            root.bind("<Escape>", lambda event: on_ok())
            
            # Center the window and bring to front
            root.update_idletasks()
            root.attributes('-topmost', True)
            root.focus_force()
            
            return root
        
        # Create and show the dialog
        dialog = create_styled_error_dialog()
        dialog.mainloop()
        
    except Exception as e:
        # Fallback to PyQt if tkinter fails
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            
            app = QApplication([])
            # Apply dark theme to the app
            set_dark_theme(app)
            
            # Show error message with styled QMessageBox
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("MAME Controls - MAME Not Found")
            msg_box.setText("MAME Directory Not Found")
            msg_box.setInformativeText(error_message)
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # Show the dialog
            msg_box.exec_()
            
        except Exception as e2:
            # If all GUI methods fail, just print to console
            print(f"Failed to show error dialog: {e}, {e2}")
            print("=" * 50)
            print(error_message)
            print("=" * 50)
    
    # Ensure cleanup happens
    cleanup_on_exit()

def main():
    """Main entry point for the application with improved path handling and early cache check"""
    print("Starting MAME Controls application...")
    
    # Set up signal handlers for proper shutdown
    def signal_handler(sig, frame):
        print(f"Received signal {sig}, shutting down...")
        # Force cleanup and exit
        cleanup_on_exit()
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Get application path
    app_dir = get_application_path()
    mame_dir = get_mame_parent_dir(app_dir)
    
    print(f"App directory: {app_dir}")
    print(f"MAME directory: {mame_dir}")
    
    # Add MAME directory validation
    if not validate_mame_directory(mame_dir):
        show_mame_not_found_error(mame_dir)
        return 1
    
    try:
        # Create argument parser
        parser = argparse.ArgumentParser(description='MAME Control Configuration')
        parser.add_argument('--export-image', action='store_true', help='Export image mode')
        parser.add_argument('--preview-only', action='store_true', help='Show only the preview window')
        parser.add_argument('--clean-preview', action='store_true', help='Show preview without buttons and UI elements (like saved image)')
        parser.add_argument('--game', type=str, help='Specify the ROM name to preview')
        parser.add_argument('--screen', type=int, default=1, help='Screen number to display preview on (default: 1)')
        parser.add_argument('--auto-close', action='store_true', help='Automatically close preview when MAME exits')
        parser.add_argument('--no-buttons', action='store_true', help='Hide buttons in preview mode (overrides settings)')
        parser.add_argument('--use-db', action='store_true', help='Force using SQLite database if available')
        parser.add_argument('--precache', action='store_true', help='Precache game data without showing the preview')
        args = parser.parse_args()
        print("Arguments parsed.")
        
        # Make sure the path is properly set for module imports
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.append(script_dir)
        
        # Also ensure parent directory is in path if we're in preview folder
        if os.path.basename(script_dir) == "preview":
            parent_dir = os.path.dirname(script_dir)
            sys.path.append(parent_dir)
        
        print(f"Script directory: {script_dir}")
        
        # Initialize variables that will be used later
        use_cache = False
        use_database = False
        db_path = None
        
        # Check for preview-only mode with a ROM specified - add early cache check
        if args.game and args.preview_only:
            print(f"Mode: Preview-only for ROM: {args.game}")
            
            # Define the cache directory and check if cache exists
            import time  # Import time module here to fix the error
            preview_dir = os.path.join(mame_dir, "preview")
            cache_dir = os.path.join(preview_dir, "cache")
            cache_file = os.path.join(cache_dir, f"{args.game}_cache.json")
            
            # If cache exists and is not too old, we can skip database checks
            cache_exists = os.path.exists(cache_file)
            
            if cache_exists:
                try:
                    # Check cache age
                    cache_age = time.time() - os.path.getmtime(cache_file)
                    print(f"Found cache file: {cache_file}")
                    print(f"Cache age: {cache_age:.1f} seconds")
                    
                    # Consider cache valid if less than 1 hour old
                    if cache_age < 3600:
                        # Verify the cache contains valid data
                        with open(cache_file, 'r') as f:
                            import json
                            cache_data = json.load(f)
                            if cache_data and isinstance(cache_data, dict) and 'romname' in cache_data:
                                print(f"Using cache for {args.game} - skipping database checks")
                                use_cache = True
                except Exception as e:
                    print(f"Error checking cache: {e}")
                    use_cache = False
        
        # Always check database settings, regardless of mode
        settings_dir = os.path.join(app_dir, "settings")
        db_path = os.path.join(settings_dir, "gamedata.db")
        print(f"Looking for database at: {db_path}")
        print(f"Database file exists: {os.path.exists(db_path)}")

        # Ensure settings directory exists
        os.makedirs(settings_dir, exist_ok=True)

        # Database usage logic - respects --use-db flag
        if args.use_db:
            if os.path.exists(db_path):
                print(f"Found database at: {db_path}")
                print("Database support FORCED by --use-db flag")
                use_database = True
            else:
                print("ERROR: --use-db specified but no database found!")
                use_database = False
        elif not use_cache and os.path.exists(db_path):
            # Default behavior: use database if available and not using cache
            print(f"Found database at: {db_path}")
            print("Database support enabled for faster loading")
            use_database = True
        else:
            if use_cache:
                print("Using cache, skipping database")
            else:
                print("No database found, will use traditional JSON lookup")
            use_database = False

        # Check for preview-only mode or precache mode - always use PyQt for both
        if args.game and (args.preview_only or args.precache):
            print(f"Mode: {'Preview-only' if args.preview_only else 'Precache'} for ROM: {args.game}")
            try:
                # Initialize PyQt preview
                from PyQt5.QtWidgets import QApplication
                
                # Import module with proper path handling
                try:
                    # Try direct import first
                    from mame_controls_pyqt import MAMEControlConfig
                except ImportError:
                    # If direct import fails, try using the module from the script directory
                    sys.path.insert(0, script_dir)
                    from mame_controls_pyqt import MAMEControlConfig
                
                # Create QApplication
                app = QApplication(sys.argv)
                app.setApplicationName("MAME Control Preview")

                # Apply dark theme
                set_dark_theme(app)
                
                # Create MAMEControlConfig in preview mode
                config = MAMEControlConfig(preview_only=True)
                
                # CRITICAL FIX: Set the required directory attributes
                config.mame_dir = mame_dir
                config.preview_dir = os.path.join(mame_dir, "preview")
                config.cache_dir = os.path.join(config.preview_dir, "cache")
                
                # Force hide buttons in preview-only mode if requested
                if args.no_buttons:
                    config.hide_preview_buttons = True
                    print("Command line option forcing buttons to be hidden")
                
                # Set database usage flag
                config.use_database = use_database
                if use_database:
                    config.db_path = db_path
                
                    # Define SQLite database access method if needed
                    if not hasattr(config, 'get_game_data_from_db'):
                        import sqlite3
                        import types
                        
                        # Define the database access method
                        def get_game_data_from_db(self, romname):
                            """Get control data for a ROM from the SQLite database"""
                            if not hasattr(self, 'db_path') or not self.db_path or not os.path.exists(self.db_path):
                                print(f"Database not available for {romname}, falling back to JSON lookup")
                                return None
                            
                            try:
                                # Create connection
                                conn = sqlite3.connect(self.db_path)
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
                                player_count = game_row[2]
                                buttons = game_row[3]
                                sticks = game_row[4]
                                alternating = bool(game_row[5])
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
                                
                                for control in control_rows:
                                    control_name = control[0]
                                    display_name = control[1]
                                    
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
                                
                            except Exception as e:
                                print(f"Error getting game data from DB: {e}")
                                import traceback
                                traceback.print_exc()
                                if 'conn' in locals():
                                    conn.close()
                                return None
                                
                        # Add method to config instance
                        config.get_game_data_from_db = types.MethodType(get_game_data_from_db, config)
                
                # Always define and attach the unified game data getter
                import types
                
                def get_unified_game_data(self, romname):
                    """Get game data from database if available, falling back to JSON lookup"""
                    # First check cache
                    if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
                        print(f"Using cached data for {romname}")
                        return self.rom_data_cache[romname]
                    
                    # Check cache directory
                    cache_file = os.path.join(self.cache_dir, f"{romname}_cache.json")
                    if os.path.exists(cache_file):
                        try:
                            import json
                            with open(cache_file, 'r') as f:
                                cache_data = json.load(f)
                            if cache_data:
                                print(f"Loading {romname} from disk cache")
                                if not hasattr(self, 'rom_data_cache'):
                                    self.rom_data_cache = {}
                                self.rom_data_cache[romname] = cache_data
                                return cache_data
                        except Exception as e:
                            print(f"Error loading disk cache: {e}")
                    
                    # Try database if available
                    if hasattr(self, 'get_game_data_from_db') and hasattr(self, 'use_database') and self.use_database:
                        import time
                        start_time = time.time()
                        db_data = self.get_game_data_from_db(romname)
                        load_time = time.time() - start_time
                        
                        if db_data:
                            print(f"Retrieved {romname} from database in {load_time:.3f} seconds")
                            # Cache the result
                            if not hasattr(self, 'rom_data_cache'):
                                self.rom_data_cache = {}
                            self.rom_data_cache[romname] = db_data
                            return db_data
                    
                    # Fall back to original method
                    print(f"Falling back to JSON lookup for {romname}")
                    import time
                    start_time = time.time()
                    json_data = self.get_game_data(romname)
                    load_time = time.time() - start_time
                    print(f"JSON lookup completed in {load_time:.3f} seconds")
                    
                    # Cache the result
                    if json_data:
                        if not hasattr(self, 'rom_data_cache'):
                            self.rom_data_cache = {}
                        self.rom_data_cache[romname] = json_data
                    return json_data
                
                # Make sure the method is attached
                config.get_unified_game_data = types.MethodType(get_unified_game_data, config)
                
                # Initialize the ROM data cache if not already done
                if not hasattr(config, 'rom_data_cache'):
                    config.rom_data_cache = {}
                
                # Patch the config's get_game_data to use unified getter
                original_get_game_data = config.get_game_data
                
                def patched_get_game_data(self, romname):
                    print(f"Patched get_game_data called for: {romname}")
                    return self.get_unified_game_data(romname)
                
                # Only replace if it's not already patched
                if not hasattr(config, '_patched_get_game_data'):
                    config.get_game_data = types.MethodType(patched_get_game_data, config)
                    config._patched_get_game_data = True
                    print("Added unified game data support")
                
                if args.precache:
                    print(f"Precaching game data for: {args.game}")
                    import time
                    import json
                    import sqlite3
                    start_time = time.time()
                    
                    # Set up directories
                    preview_dir = os.path.join(mame_dir, "preview")
                    cache_dir = os.path.join(preview_dir, "cache")
                    os.makedirs(cache_dir, exist_ok=True)
                    cache_file = os.path.join(cache_dir, f"{args.game}_cache.json")
                    
                    # CRITICAL: Import the Tkinter module to access its processing methods
                    try:
                        # Make sure the path is properly set for module imports
                        script_dir = os.path.dirname(os.path.abspath(__file__))
                        sys.path.append(script_dir)
                        
                        # Also ensure parent directory is in path if we're in preview folder
                        if os.path.basename(script_dir) == "preview":
                            parent_dir = os.path.dirname(script_dir)
                            sys.path.append(parent_dir)
                        
                        # Import the Tkinter module to access processing methods
                        from mame_controls_tkinter import MAMEControlConfig
                        
                        # Create a minimal config object to access its methods
                        # We use initially_hidden=True to prevent the GUI from showing
                        temp_config = MAMEControlConfig(initially_hidden=True)
                        temp_config.withdraw()  # Ensure window stays hidden
                        
                        # Set the input mode from settings
                        temp_config.input_mode = temp_config.load_settings().get('input_mode', 'xinput')
                        input_mode = temp_config.input_mode
                        print(f"Using input mode: {input_mode}")
                        
                        # Load custom configs and default controls
                        temp_config.load_custom_configs()
                        temp_config.load_default_config()
                        
                        # Get game data using the same method as the main application
                        game_data = temp_config.get_game_data(args.game)
                        
                        if game_data:
                            print(f"Retrieved {args.game} from {game_data.get('source', 'unknown source')}")
                            
                            # CRITICAL: Apply custom mappings with the correct input mode
                            cfg_controls = {}
                            if args.game in temp_config.custom_configs:
                                # Parse the custom config using the same method
                                cfg_content = temp_config.custom_configs[args.game]
                                parsed_controls = temp_config.parse_cfg_controls(cfg_content)
                                if parsed_controls:
                                    print(f"Found {len(parsed_controls)} control mappings in ROM CFG for {args.game}")
                                    cfg_controls = {
                                        control: temp_config.convert_mapping(mapping, input_mode)
                                        for control, mapping in parsed_controls.items()
                                    }
                                else:
                                    print(f"ROM CFG exists for {args.game} but contains no control mappings")
                            
                            # Apply the same processing as the main application
                            temp_config.update_game_data_with_custom_mappings(game_data, cfg_controls)
                            
                            # Apply XInput-only filtering if enabled
                            if hasattr(temp_config, 'xinput_only_mode') and temp_config.xinput_only_mode:
                                game_data = temp_config.filter_xinput_controls(game_data)
                                print(f"Applied XInput-only filter")
                            
                            # Clean up the temporary config object
                            temp_config.destroy()
                            
                            # Save the processed game data to cache
                            try:
                                with open(cache_file, 'w') as f:
                                    json.dump(game_data, f, indent=2)
                                
                                load_time = time.time() - start_time
                                print(f"Precached {args.game} in {load_time:.3f} seconds using {input_mode} mode")
                                print(f"Saved to: {cache_file}")
                                print(f"Source: {game_data.get('source', 'unknown')}")
                                print(f"Input Mode: {game_data.get('input_mode', 'unknown')}")
                                print(f"Players: {len(game_data.get('players', []))}")
                                
                                if game_data.get('players'):
                                    for player in game_data['players']:
                                        control_count = len(player.get('labels', []))
                                        custom_count = len([l for l in player.get('labels', []) if l.get('is_custom', False)])
                                        mapped_count = len([l for l in player.get('labels', []) if l.get('target_button')])
                                        print(f"  Player {player['number']}: {control_count} controls ({custom_count} custom, {mapped_count} mapped)")
                                        
                                        # Show sample of processed data
                                        if control_count > 0:
                                            sample_label = player['labels'][0]
                                            print(f"    Sample control: {sample_label['name']} -> {sample_label.get('target_button', sample_label.get('display_name', sample_label['value']))}")
                                            
                            except Exception as e:
                                print(f"Error saving cache: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"Error: Failed to get game data for {args.game}")
                            
                    except ImportError as e:
                        print(f"Error importing Tkinter module: {e}")
                        print("Falling back to basic precache without input mode processing...")
                        
                        # Fallback to basic processing without input mode (original behavior)
                        # This is the old code as a backup
                        game_data = None
                        
                        # Try database first if requested and available
                        if use_database and db_path and os.path.exists(db_path):
                            print(f"Attempting to load {args.game} from database")
                            try:
                                import sqlite3
                                conn = sqlite3.connect(db_path)
                                cursor = conn.cursor()
                                
                                # Get basic game info
                                cursor.execute("""
                                    SELECT rom_name, game_name, player_count, buttons, sticks, alternating, is_clone, parent_rom
                                    FROM games WHERE rom_name = ?
                                """, (args.game,))
                                
                                game_row = cursor.fetchone()
                                
                                if game_row:
                                    print(f"Found {args.game} in database")
                                    
                                    # Build game data structure
                                    game_data = {
                                        'romname': args.game,
                                        'gamename': game_row[1],
                                        'numPlayers': game_row[2],
                                        'alternating': bool(game_row[5]),
                                        'mirrored': False,
                                        'miscDetails': f"Buttons: {game_row[3]}, Sticks: {game_row[4]}",
                                        'players': [],
                                        'source': 'gamedata.db'
                                    }
                                    
                                    # Get control data
                                    cursor.execute("""
                                        SELECT control_name, display_name FROM game_controls WHERE rom_name = ?
                                    """, (args.game,))
                                    control_rows = cursor.fetchall()
                                    
                                    # Process controls
                                    p1_controls = []
                                    p2_controls = []
                                    
                                    for control in control_rows:
                                        control_name = control[0]
                                        display_name = control[1]
                                        
                                        if control_name.startswith('P1_'):
                                            p1_controls.append({
                                                'name': control_name,
                                                'value': display_name or control_name
                                            })
                                        elif control_name.startswith('P2_'):
                                            p2_controls.append({
                                                'name': control_name,
                                                'value': display_name or control_name
                                            })
                                    
                                    # Add players
                                    if p1_controls:
                                        game_data['players'].append({
                                            'number': 1,
                                            'numButtons': game_row[3],
                                            'labels': sorted(p1_controls, key=lambda x: x['name'])
                                        })
                                        
                                    if p2_controls:
                                        game_data['players'].append({
                                            'number': 2,
                                            'numButtons': game_row[3],
                                            'labels': sorted(p2_controls, key=lambda x: x['name'])
                                        })
                                
                                conn.close()
                                
                            except Exception as e:
                                print(f"Database lookup failed: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        # Fall back to JSON lookup if database failed or not available
                        if not game_data:
                            print(f"Loading {args.game} from JSON")
                            try:
                                # Load gamedata.json directly
                                gamedata_path = os.path.join(preview_dir, "settings", "gamedata.json")
                                if not os.path.exists(gamedata_path):
                                    # Try alternative locations
                                    alt_paths = [
                                        os.path.join(mame_dir, "gamedata.json"),
                                        os.path.join(app_dir, "gamedata.json"),
                                        os.path.join(app_dir, "settings", "gamedata.json")
                                    ]
                                    for alt_path in alt_paths:
                                        if os.path.exists(alt_path):
                                            gamedata_path = alt_path
                                            break
                                
                                if os.path.exists(gamedata_path):
                                    with open(gamedata_path, 'r', encoding='utf-8') as f:
                                        gamedata_json = json.load(f)
                                    
                                    if args.game in gamedata_json:
                                        raw_data = gamedata_json[args.game]
                                        
                                        # Convert to standard format
                                        game_data = {
                                            'romname': args.game,
                                            'gamename': raw_data.get('description', args.game),
                                            'numPlayers': int(raw_data.get('playercount', 1)),
                                            'alternating': raw_data.get('alternating', False),
                                            'mirrored': False,
                                            'miscDetails': f"Buttons: {raw_data.get('buttons', '?')}, Sticks: {raw_data.get('sticks', '?')}",
                                            'players': [],
                                            'source': 'gamedata.json'
                                        }
                                        
                                        # Process controls
                                        if 'controls' in raw_data:
                                            p1_controls = []
                                            p2_controls = []
                                            
                                            for control_name, control_data in raw_data['controls'].items():
                                                action = control_data.get('name', control_name)
                                                
                                                if control_name.startswith('P1_'):
                                                    p1_controls.append({
                                                        'name': control_name,
                                                        'value': action
                                                    })
                                                elif control_name.startswith('P2_'):
                                                    p2_controls.append({
                                                        'name': control_name,
                                                        'value': action
                                                    })
                                            
                                            # Add players
                                            if p1_controls:
                                                game_data['players'].append({
                                                    'number': 1,
                                                    'numButtons': int(raw_data.get('buttons', 1)),
                                                    'labels': sorted(p1_controls, key=lambda x: x['name'])
                                                })
                                                
                                            if p2_controls:
                                                game_data['players'].append({
                                                    'number': 2,
                                                    'numButtons': int(raw_data.get('buttons', 1)),
                                                    'labels': sorted(p2_controls, key=lambda x: x['name'])
                                                })
                                    else:
                                        print(f"ROM {args.game} not found in gamedata.json")
                                else:
                                    print(f"gamedata.json not found at {gamedata_path}")
                                    
                            except Exception as e:
                                print(f"JSON lookup failed: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        if game_data:
                            # Basic save without advanced processing
                            try:
                                with open(cache_file, 'w') as f:
                                    json.dump(game_data, f, indent=2)
                                
                                load_time = time.time() - start_time
                                print(f"Precached {args.game} in {load_time:.3f} seconds (basic mode)")
                                print(f"Saved to: {cache_file}")
                                print(f"Source: {game_data.get('source', 'unknown')}")
                            except Exception as e:
                                print(f"Error saving cache: {e}")
                        else:
                            print(f"Error: Failed to get game data for {args.game}")
                    
                    except Exception as e:
                        print(f"Unexpected error in precache: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # Exit without showing UI
                    return 0
                else:
                    # Show preview for specified game with clean mode if requested
                    config.show_preview_standalone(args.game, args.auto_close, clean_mode=args.clean_preview)
                    
                    # Run app
                    app.exec_()
                    return 0
            except ImportError:
                print("PyQt5 or necessary modules not found for preview mode.")
                return 1
        
        # Check for export image mode
        if args.game and args.export_image:
            print(f"Mode: Export image for ROM: {args.game}")
            
            if not hasattr(args, 'output') or not args.output:
                print("ERROR: --output parameter is required for export mode")
                return 1
                
            try:
                # Initialize PyQt for the export
                from PyQt5.QtWidgets import QApplication
                
                # Create QApplication
                app = QApplication(sys.argv)
                app.setApplicationName("MAME Control Preview Export")
                
                # Get application paths
                app_dir = get_application_path()
                mame_dir = get_mame_parent_dir(app_dir)
                
                # Get game data (using cached data if available)
                preview_dir = os.path.join(mame_dir, "preview")
                cache_dir = os.path.join(preview_dir, "cache")
                cache_file = os.path.join(cache_dir, f"{args.game}_cache.json")
                
                game_data = None
                if os.path.exists(cache_file):
                    try:
                        import json
                        with open(cache_file, 'r') as f:
                            game_data = json.load(f)
                        print(f"Using cached data for {args.game}")
                    except Exception as e:
                        print(f"Error loading cache: {e}")
                
                if not game_data:
                    # Import module for game data
                    try:
                        # Try direct import first
                        from mame_controls_pyqt import MAMEControlConfig
                    except ImportError:
                        # If direct import fails, try using the module from the script directory
                        sys.path.insert(0, script_dir)
                        from mame_controls_pyqt import MAMEControlConfig
                        
                    # Create config to access game data
                    config = MAMEControlConfig(preview_only=True)
                    game_data = config.get_unified_game_data(args.game)
                    
                    if not game_data:
                        print(f"ERROR: No game data found for {args.game}")
                        return 1
                
                # Import the PreviewWindow class
                try:
                    from mame_controls_preview import PreviewWindow
                except ImportError:
                    print("ERROR: Could not import PreviewWindow class")
                    return 1
                    
                # Create the preview window (not visible)
                preview = PreviewWindow(
                    args.game, 
                    game_data, 
                    mame_dir,
                    hide_buttons=True,  # Always hide buttons in export mode
                    clean_mode=True     # Always use clean mode in export mode
                )
                
                # Configure bezel/logo visibility
                if args.no_bezel and hasattr(preview, 'bezel_visible'):
                    preview.bezel_visible = False
                    
                if args.no_logo and hasattr(preview, 'logo_visible'):
                    preview.logo_visible = False
                    if hasattr(preview, 'logo_label') and preview.logo_label:
                        preview.logo_label.setVisible(False)
                
                # Export the image
                if hasattr(preview, 'export_image_headless'):
                    if preview.export_image_headless(args.output, args.format):
                        print(f"Successfully exported preview for {args.game} to {args.output}")
                        return 0
                    else:
                        print(f"Failed to export preview for {args.game}")
                        return 1
                else:
                    print("ERROR: Export method not available")
                    return 1
                    
            except Exception as e:
                print(f"ERROR in export mode: {e}")
                import traceback
                traceback.print_exc()
                return 1
        
        # Initialize the Tkinter interface (this is now the only GUI mode)
        try:
            # Import the Tkinter version
            import customtkinter as ctk
            
            # Import module with proper path handling
            try:
                # Try direct import first
                from mame_controls_tkinter import MAMEControlConfig
            except ImportError:
                # If direct import fails, try using the module from the script directory
                sys.path.insert(0, script_dir)
                from mame_controls_tkinter import MAMEControlConfig
            
            # Set appearance mode and theme
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("dark-blue")
            
            # Create the Tkinter application with hidden window initially
            app = MAMEControlConfig(initially_hidden=True)

            # Set the window icon (add these lines)
            try:
                icon_path = "P1.ico"
                # Check multiple locations
                if not os.path.exists(icon_path):
                    alternate_path = os.path.join(app_dir, "P1.ico")
                    if os.path.exists(alternate_path):
                        icon_path = alternate_path
                
                if os.path.exists(icon_path):
                    print(f"Setting window icon from: {icon_path}")
                    app.iconbitmap(icon_path)
                else:
                    print("Warning: Could not find icon file for window decoration")
            except Exception as e:
                print(f"Error setting window icon: {e}")

            # Auto maximize
            app.after(100, app.state, 'zoomed')
            
            # Run the application
            app.mainloop()
            return 0
        except ImportError:
            print("CustomTkinter or required modules not found. Please install with:")
            print("pip install customtkinter")
            return 1
        
        return 0  # Return successful exit code
        
    except Exception as e:
        print(f"Unhandled exception in main(): {e}")
        import traceback  # Import traceback here
        traceback.print_exc()
        return 1
        
    finally:
        # Ensure cleanup happens
        cleanup_on_exit()
        
        # Force exit if app is still active
        if 'app' in locals() and hasattr(app, 'quit'):
            try:
                app.quit()
            except:
                pass
            
def load_input_mode_from_settings(preview_dir):
    """Load the current input mode from settings file"""
    settings_dir = os.path.join(preview_dir, "settings")
    settings_path = os.path.join(settings_dir, "control_config_settings.json")
    
    # Default to xinput if no settings found
    default_input_mode = 'xinput'
    
    try:
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            input_mode = settings.get('input_mode', default_input_mode)
            
            # Validate the input mode
            if input_mode not in ['joycode', 'xinput', 'dinput', 'keycode']:
                print(f"Invalid input mode '{input_mode}' in settings, using default: {default_input_mode}")
                input_mode = default_input_mode
                
            print(f"Loaded input mode from settings: {input_mode}")
            return input_mode
        else:
            print(f"No settings file found at {settings_path}, using default: {default_input_mode}")
            return default_input_mode
    except Exception as e:
        print(f"Error loading input mode from settings: {e}, using default: {default_input_mode}")
        return default_input_mode

def apply_input_mode_processing(game_data, input_mode, cfg_controls, mame_dir, rom_name):
    """Apply input mode processing to game data similar to main application"""
    
    # Import the conversion methods (we'll need to add these)
    # For now, let's implement the core logic
    
    # Add current input mode to game_data
    game_data['input_mode'] = input_mode
    
    # Apply custom mappings if available
    if cfg_controls:
        print(f"Applying custom CFG mappings for {rom_name} in {input_mode} mode")
        
        # Process each player's controls
        for player in game_data.get('players', []):
            for label in player.get('labels', []):
                control_name = label['name']
                
                # Check if this control has a mapping
                if control_name in cfg_controls:
                    mapping_value = cfg_controls[control_name]
                    
                    # Add mapping information to the label
                    label['mapping'] = mapping_value
                    label['mapping_source'] = f"ROM CFG ({rom_name}.cfg)"
                    label['is_custom'] = True
                    label['cfg_mapping'] = True
                    label['input_mode'] = input_mode
                    
                    # Process the mapping based on input mode
                    if input_mode == 'keycode':
                        # Extract KEYCODE from mapping
                        keycode_display = extract_keycode_from_mapping(mapping_value)
                        label['target_button'] = keycode_display if keycode_display else "No Key Assigned"
                        label['display_name'] = label['target_button']
                    elif input_mode == 'xinput':
                        if 'XINPUT' in mapping_value:
                            label['target_button'] = get_friendly_xinput_name(mapping_value)
                            label['display_name'] = f"P1 {label['target_button']}"
                        else:
                            # Convert to XInput if possible
                            converted = convert_mapping_to_xinput(mapping_value)
                            if converted.startswith('XINPUT'):
                                label['target_button'] = get_friendly_xinput_name(converted)
                                label['display_name'] = f"P1 {label['target_button']}"
                            else:
                                label['target_button'] = mapping_value
                                label['display_name'] = mapping_value
                    elif input_mode == 'dinput':
                        if 'DINPUT' in mapping_value:
                            label['target_button'] = get_friendly_dinput_name(mapping_value)
                            label['display_name'] = f"P1 {label['target_button']}"
                        else:
                            # Convert to DInput if possible
                            converted = convert_mapping_to_dinput(mapping_value)
                            if converted.startswith('DINPUT'):
                                label['target_button'] = get_friendly_dinput_name(converted)
                                label['display_name'] = f"P1 {label['target_button']}"
                            else:
                                label['target_button'] = mapping_value
                                label['display_name'] = mapping_value
                    elif input_mode == 'joycode':
                        if 'JOYCODE' in mapping_value:
                            label['target_button'] = format_joycode_display(mapping_value)
                            label['display_name'] = label['target_button']
                        else:
                            label['target_button'] = mapping_value
                            label['display_name'] = mapping_value
                else:
                    # No custom mapping, set defaults based on input mode
                    label['is_custom'] = False
                    if input_mode == 'keycode':
                        label['display_name'] = "No Key Assigned"
                    else:
                        label['display_name'] = format_control_name_for_mode(control_name, input_mode)
    
    return game_data

def extract_keycode_from_mapping(mapping):
    """Extract KEYCODE from mapping string"""
    if not mapping:
        return ""
    
    # Handle increment/decrement pairs
    if " ||| " in mapping:
        inc_mapping, dec_mapping = mapping.split(" ||| ")
        inc_keycode = extract_keycode_from_mapping(inc_mapping)
        dec_keycode = extract_keycode_from_mapping(dec_mapping)
        
        if inc_keycode and dec_keycode:
            return f"{inc_keycode} | {dec_keycode}"
        elif inc_keycode:
            return inc_keycode
        elif dec_keycode:
            return dec_keycode
        else:
            return ""
    
    # Handle OR statements - look for KEYCODE part
    if " OR " in mapping:
        parts = mapping.split(" OR ")
        for part in parts:
            part = part.strip()
            if part.startswith('KEYCODE_'):
                return format_keycode_display(part)
        return ""
    
    # Single mapping
    if mapping.startswith('KEYCODE_'):
        return format_keycode_display(mapping)
    
    return ""

def format_keycode_display(mapping):
    """Format KEYCODE mapping string for display"""
    if not mapping or not mapping.startswith("KEYCODE_"):
        return mapping
        
    key_name = mapping.replace("KEYCODE_", "")
    
    # Make common keys more readable
    key_mappings = {
        'LCONTROL': 'Left Ctrl',
        'RCONTROL': 'Right Ctrl',
        'LALT': 'Left Alt',
        'RALT': 'Right Alt', 
        'LSHIFT': 'Left Shift',
        'RSHIFT': 'Right Shift',
        'SPACE': 'Spacebar',
        'ENTER': 'Enter',
        # Add more as needed
    }
    
    friendly_name = key_mappings.get(key_name, key_name)
    return f"Key {friendly_name}"

def get_friendly_xinput_name(mapping):
    """Convert an XINPUT mapping code into a human-friendly button name"""
    parts = mapping.split('_', 2)
    if len(parts) < 3:
        return mapping
    action = parts[2]
    
    friendly_map = {
        "A": "A Button",
        "B": "B Button", 
        "X": "X Button",
        "Y": "Y Button",
        "SHOULDER_L": "LB Button",
        "SHOULDER_R": "RB Button",
        # Add more mappings as needed
    }
    return friendly_map.get(action, action)

def get_friendly_dinput_name(mapping):
    """Convert a DINPUT mapping code into a human-friendly button name"""
    parts = mapping.split('_', 3)
    if len(parts) < 3:
        return mapping
    
    action = parts[2]
    if action.startswith("BUTTON"):
        button_num = action[6:]
        return f"Button {button_num}"
    return action

def format_joycode_display(mapping):
    """Format JOYCODE mapping string for display"""
    if "BUTTON" in mapping:
        parts = mapping.split('_')
        if len(parts) >= 4:
            joy_num = parts[1]
            button_num = parts[3]
            return f"Joy {joy_num} Btn {button_num}"
    return mapping

def format_control_name_for_mode(control_name, input_mode):
    """Format control name based on input mode"""
    if input_mode == 'xinput':
        if control_name == 'P1_BUTTON1':
            return 'P1 A Button'
        elif control_name == 'P1_BUTTON2':
            return 'P1 B Button'
        # Add more xinput mappings
    elif input_mode == 'dinput':
        if control_name.startswith('P1_BUTTON'):
            button_num = int(control_name.replace('P1_BUTTON', '')) - 1
            return f'P1 Button {button_num}'
    elif input_mode == 'joycode':
        if control_name.startswith('P1_BUTTON'):
            button_num = control_name.replace('P1_BUTTON', '')
            return f'Joy 1 Btn {button_num}'
    elif input_mode == 'keycode':
        return "No Key Assigned"
    
    return control_name

def convert_mapping_to_xinput(mapping):
    """Basic conversion to XInput format"""
    # Simplified conversion - add full logic as needed
    if mapping.startswith('JOYCODE_1_BUTTON1'):
        return 'XINPUT_1_A'
    elif mapping.startswith('JOYCODE_1_BUTTON2'):
        return 'XINPUT_1_B'
    # Add more conversions as needed
    return mapping

def convert_mapping_to_dinput(mapping):
    """Basic conversion to DInput format"""
    # Simplified conversion - add full logic as needed  
    if mapping.startswith('JOYCODE_1_BUTTON1'):
        return 'DINPUT_1_BUTTON0'
    elif mapping.startswith('JOYCODE_1_BUTTON2'):
        return 'DINPUT_1_BUTTON1'
    # Add more conversions as needed
    return mapping

def set_dark_theme(app):
    """Apply a dark theme to the PyQt application"""
    from PyQt5.QtGui import QPalette, QColor
    from PyQt5.QtCore import Qt
    
    # Create dark palette with better colors
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(45, 45, 45))
    dark_palette.setColor(QPalette.WindowText, QColor(240, 240, 240))
    dark_palette.setColor(QPalette.Base, QColor(30, 30, 30))
    dark_palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    dark_palette.setColor(QPalette.ToolTipBase, QColor(45, 45, 45))
    dark_palette.setColor(QPalette.ToolTipText, QColor(240, 240, 240))
    dark_palette.setColor(QPalette.Text, QColor(240, 240, 240))
    dark_palette.setColor(QPalette.Button, QColor(55, 55, 55))
    dark_palette.setColor(QPalette.ButtonText, QColor(240, 240, 240))
    dark_palette.setColor(QPalette.BrightText, QColor(255, 50, 50))
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, QColor(240, 240, 240))
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
    
    # Apply palette
    app.setPalette(dark_palette)
    
    # Set stylesheet for controls
    app.setStyleSheet("""
        QMainWindow, QDialog {
            background-color: #2d2d2d;
        }
        QWidget {
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        QToolTip { 
            color: #f0f0f0; 
            background-color: #2a82da; 
            border: 1px solid #f0f0f0;
            border-radius: 4px;
            padding: 4px;
            font-size: 12px;
        }
        QPushButton { 
            background-color: #3d3d3d; 
            border: 1px solid #5a5a5a;
            padding: 6px 12px;
            border-radius: 4px;
            color: #f0f0f0;
            font-weight: bold;
            min-height: 25px;
        }
        QPushButton:hover { 
            background-color: #4a4a4a; 
            border: 1px solid #6a6a6a;
        }
        QPushButton:pressed { 
            background-color: #2a82da; 
            border: 1px solid #2472c4;
        }
        QScrollArea, QTextEdit, QLineEdit {
            background-color: #1e1e1e;
            border: 1px solid #3d3d3d;
            border-radius: 4px;
        }
        QCheckBox { 
            spacing: 8px; 
            color: #f0f0f0;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border-radius: 3px;
        }
        QCheckBox::indicator:unchecked {
            border: 1px solid #5A5A5A;
            background: #3d3d3d;
        }
        QCheckBox::indicator:checked {
            border: 1px solid #2a82da;
            background: #2a82da;
        }
        QLabel {
            color: #f0f0f0;
        }
        QFrame {
            border-radius: 4px;
            border: 1px solid #3d3d3d;
        }
        QScrollBar:vertical {
            border: none;
            background: #2d2d2d;
            width: 10px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #5a5a5a;
            min-height: 20px;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            border: none;
            background: #2d2d2d;
            height: 10px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #5a5a5a;
            min-width: 20px;
            border-radius: 5px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
    """)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Unhandled exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Make sure cleanup happens even after exceptions
        cleanup_on_exit()
        
        # Force exit
        sys.exit(0)
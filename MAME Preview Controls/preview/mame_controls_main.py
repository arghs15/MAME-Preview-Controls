"""
Updates to mame_controls_main.py to support pre-caching game data
which speeds up preview rendering when the user presses pause
"""

import atexit
import gc
import os
import signal
import sys
import argparse
import traceback  # Add this import
import time

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

# Add this line at the end of your import section
atexit.register(cleanup_on_exit)

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
        parser.add_argument('--pyqt', action='store_true', help='Use the PyQt version of the main GUI (default: Tkinter)')
        parser.add_argument('--use-db', action='store_true', help='Force using SQLite database if available')
        # Add new precache argument
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
            use_cache = False
            
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
            
            # Only proceed with database checks if not using cache
            if not use_cache:
                # Check for database in settings directory
                settings_dir = os.path.join(app_dir, "settings")
                db_path = os.path.join(settings_dir, "gamedata.db")
                print(f"Looking for database at: {db_path}")
                print(f"Database file exists: {os.path.exists(db_path)}")

                # Ensure settings directory exists
                os.makedirs(settings_dir, exist_ok=True)

                # Change this to remove the reference to args.use_db
                if os.path.exists(db_path):  # Always use DB if available
                    print(f"Found database at: {db_path}")
                    print("Database support enabled for faster loading")
                    
                    # We'll set this variable to indicate DB support should be enabled
                    use_database = True
                else:
                    print("No database found, will use traditional JSON lookup")
                    use_database = False
            else:
                # Set fallback values when using cache
                use_database = False
                db_path = None
        else:
            # For other modes, proceed with normal database checks
            # Check for database in settings directory
            settings_dir = os.path.join(app_dir, "settings")
            db_path = os.path.join(settings_dir, "gamedata.db")
            print(f"Looking for database at: {db_path}")
            print(f"Database file exists: {os.path.exists(db_path)}")

            # Ensure settings directory exists
            os.makedirs(settings_dir, exist_ok=True)

            # Change this to remove the reference to args.use_db
            if os.path.exists(db_path):  # Always use DB if available
                print(f"Found database at: {db_path}")
                print("Database support enabled for faster loading")
                
                # We'll set this variable to indicate DB support should be enabled
                use_database = True
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
                
                # Force hide buttons in preview-only mode if requested
                if args.no_buttons:
                    config.hide_preview_buttons = True
                    print("Command line option forcing buttons to be hidden")
                
                # Set database usage flag, but only if we're not using cache
                if 'use_cache' in locals() and use_cache:
                    # When using cache, we don't need database
                    config.use_database = False
                    if hasattr(config, 'db_path'):
                        delattr(config, 'db_path')
                else:
                    # Normal database setup
                    config.use_database = use_database
                    if use_database:
                        config.db_path = db_path
                    
                        # Define SQLite database access method if needed
                        if not hasattr(config, 'get_game_data_from_db'):
                            import sqlite3
                            import types
                            
                            # Define the database access method (code unchanged)
                            def get_game_data_from_db(self, romname):
                                # Existing database access code...
                                """Get control data for a ROM from the SQLite database"""
                                if not hasattr(self, 'db_path') or not self.db_path or not os.path.exists(self.db_path):
                                    print(f"Database not available for {romname}, falling back to JSON lookup")
                                    return None
                                
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
                                        control_name = control[0]  # First column
                                        display_name = control[1]  # Second column
                                        
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
                    preview_dir = os.path.join(self.mame_dir, "preview")
                    cache_dir = os.path.join(preview_dir, "cache")
                    cache_file = os.path.join(cache_dir, f"{romname}_cache.json")
                    
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
                
                # Handle the two modes differently
                if args.precache:
                    # Just precache the game data without showing preview
                    print(f"Precaching game data for: {args.game}")
                    import time
                    start_time = time.time()
                    
                    # Make sure we have a cache directory
                    cache_dir = os.path.join(app_dir, "cache")
                    os.makedirs(cache_dir, exist_ok=True)
                    cache_file = os.path.join(cache_dir, f"{args.game}_cache.json")
                    
                    # Load the game data
                    try:
                        game_data = config.get_unified_game_data(args.game)
                        
                        if game_data:
                            # Save to cache file
                            import json
                            with open(cache_file, 'w') as f:
                                json.dump(game_data, f)
                            
                            load_time = time.time() - start_time
                            print(f"Precached {args.game} in {load_time:.3f} seconds, saved to {cache_file}")
                        else:
                            print(f"Error: Failed to get game data for {args.game}")
                    except Exception as e:
                        print(f"Error precaching data: {e}")
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
            
            if not args.output:
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
        
        # For the main application, check which UI to use - now defaulting to Tkinter
        if args.pyqt:  # Changed condition to check for --pyqt flag
            # Initialize PyQt application
            try:
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
                app.setApplicationName("MAME Control Configuration (PyQt)")
                app.setApplicationVersion("1.0")

                # Apply dark theme
                set_dark_theme(app)

                # Create main window
                window = MAMEControlConfig()

                # First make window visible
                window.show()

                # Then maximize it - using multiple methods for redundancy
                from PyQt5.QtCore import QTimer, Qt
                window.setWindowState(Qt.WindowMaximized)
                QTimer.singleShot(100, window.showMaximized)

                # Run application
                return app.exec_()
            except ImportError:
                print("PyQt5 not found, falling back to Tkinter version.")
                args.pyqt = False  # Fall back to Tkinter if PyQt fails
        
        # If not using PyQt (either by default or PyQt failure)
        if not args.pyqt:
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
                
                # Create the Tkinter application
                app = MAMEControlConfig()
                
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
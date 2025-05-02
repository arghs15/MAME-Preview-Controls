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
    """Main entry point for the application with simplified bridge-based approach"""
    # Ensure all necessary imports
    import os
    import sys
    import time
    import json
    import signal
    import traceback
    import argparse
    import importlib.util
    import subprocess
    
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
        parser.add_argument('--precache', action='store_true', help='Precache game data without showing the preview')
        parser.add_argument('--output', type=str, help='Output path for image export')
        parser.add_argument('--format', type=str, default='png', help='Image format for export (default: png)')
        parser.add_argument('--no-bezel', action='store_true', help='Don\'t show bezel in preview/export')
        parser.add_argument('--no-logo', action='store_true', help='Don\'t show game logo in preview/export')
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
        
        # Handle preview-only, precache, or export-image modes using the bridge
        if args.game and (args.preview_only or args.precache or args.export_image):
            operation = "Preview" if args.preview_only else "Precache" if args.precache else "Export"
            print(f"Mode: {operation} for ROM: {args.game}")
            
            try:
                # Import the preview bridge
                from preview_bridge import PreviewBridge
                bridge = PreviewBridge()
                
                # Handle export image mode
                # In the section that handles export-image mode
                if args.export_image:
                    if not args.output:
                        print("ERROR: --output parameter is required for export mode")
                        return 1
                        
                    # Import the preview bridge
                    from preview_bridge import PreviewBridge
                    bridge = PreviewBridge()
                    
                    # Load saved bezel and logo settings
                    bezel_settings = bridge.load_bezel_settings()
                    show_bezel = bezel_settings.get("bezel_visible", True)  # Default to visible
                    show_logo = bezel_settings.get("logo_visible", True)    # Default to visible
                    
                    # Check for ROM-specific settings
                    rom_specific_settings = bridge.load_rom_settings(args.game)
                    if rom_specific_settings:
                        # ROM-specific settings override global settings
                        show_bezel = rom_specific_settings.get("bezel_visible", show_bezel)
                        show_logo = rom_specific_settings.get("logo_visible", show_logo)
                    
                    # Command-line flags only override settings if explicitly provided
                    if args.no_bezel:
                        show_bezel = False
                    
                    if args.no_logo:
                        show_logo = False
                    
                    # Export the image with the determined settings
                    success = bridge.export_preview_image(
                        rom_name=args.game,
                        output_path=args.output,
                        format=args.format or "png",
                        show_bezel=show_bezel,
                        show_logo=show_logo
                    )
                    
                    if success:
                        print(f"Successfully exported preview for {args.game} to {args.output}")
                        return 0
                    else:
                        print(f"Failed to export preview for {args.game}")
                        return 1
                
                # Handle precache mode
                elif args.precache:
                    # Setup cache directories
                    cache_dir = os.path.join(bridge.preview_dir, "cache")
                    os.makedirs(cache_dir, exist_ok=True)
                    cache_file = os.path.join(cache_dir, f"{args.game}_cache.json")
                    
                    # Check if we already have recent cache
                    if os.path.exists(cache_file):
                        cache_age = time.time() - os.path.getmtime(cache_file)
                        if cache_age < 3600:  # Less than an hour old
                            print(f"Cache for {args.game} is recent ({cache_age:.0f}s old), skipping precache")
                            return 0
                    
                    # Get game data - we need to import the tkinter code
                    # Find the tkinter module path
                    tk_module_paths = [
                        os.path.join(script_dir, "mame_controls_tkinter.py"),
                        os.path.join(parent_dir, "mame_controls_tkinter.py") if 'parent_dir' in locals() else None,
                        os.path.join(mame_dir, "preview", "mame_controls_tkinter.py"),
                        os.path.join(mame_dir, "mame_controls_tkinter.py")
                    ]
                    
                    tk_module_path = None
                    for path in tk_module_paths:
                        if path and os.path.exists(path):
                            tk_module_path = path
                            break
                    
                    if not tk_module_path:
                        print("Error: Could not find mame_controls_tkinter.py")
                        return 1
                    
                    # Import the module
                    print(f"Loading module from: {tk_module_path}")
                    spec = importlib.util.spec_from_file_location("mame_controls_tkinter", tk_module_path)
                    tkinter_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(tkinter_module)
                    
                    # Create minimal config instance to access data methods
                    config = tkinter_module.MAMEControlConfig(preview_only=True)
                    game_data = config.get_game_data(args.game)
                    
                    if game_data:
                        # Save to cache
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            json.dump(game_data, f, indent=2)
                        print(f"Successfully precached data for {args.game} to {cache_file}")
                        return 0
                    else:
                        print(f"No game data found for {args.game}")
                        return 1
                
                # Handle preview-only mode
                else:  # args.preview_only
                    # Configure preview settings based on arguments
                    settings = bridge.load_settings()
                    
                    # Override settings with command line arguments if provided
                    if args.no_buttons:
                        settings["hide_preview_buttons"] = True
                    
                    if args.screen:
                        settings["preferred_preview_screen"] = args.screen
                    
                    # Apply settings to bridge (creates attributes dynamically)
                    for key, value in settings.items():
                        setattr(bridge, key, value)
                    
                    # Show the preview
                    result = bridge.show_preview_standalone(
                        rom_name=args.game,
                        auto_close=args.auto_close,
                        clean_mode=args.clean_preview
                    )
                    return result
            
            except ImportError as e:
                print(f"Error: Required module not found: {e}")
                print("Make sure preview_bridge.py and PyQt5 are properly installed")
                return 1
            except Exception as e:
                print(f"Error: {e}")
                traceback.print_exc()
                return 1
        
        # Handle the main application mode
        # For the main application - choose between PyQt and Tkinter
        if args.pyqt:
            # Use PyQt for main GUI
            try:
                from PyQt5.QtWidgets import QApplication
                from PyQt5.QtCore import QTimer, Qt
                
                # Find and import the PyQt module
                pyqt_module_paths = [
                    os.path.join(script_dir, "mame_controls_pyqt.py"),
                    os.path.join(parent_dir, "mame_controls_pyqt.py") if 'parent_dir' in locals() else None,
                    os.path.join(mame_dir, "preview", "mame_controls_pyqt.py"),
                    os.path.join(mame_dir, "mame_controls_pyqt.py")
                ]
                
                pyqt_module_path = None
                for path in pyqt_module_paths:
                    if path and os.path.exists(path):
                        pyqt_module_path = path
                        break
                
                if not pyqt_module_path:
                    print("Error: Could not find mame_controls_pyqt.py")
                    return 1
                
                # Import the module
                spec = importlib.util.spec_from_file_location("mame_controls_pyqt", pyqt_module_path)
                pyqt_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(pyqt_module)
                
                # Create QApplication
                app = QApplication(sys.argv)
                app.setApplicationName("MAME Control Configuration (PyQt)")
                app.setApplicationVersion("1.0")
                
                # Apply dark theme
                set_dark_theme(app)
                
                # Create main window
                window = pyqt_module.MAMEControlConfig()
                
                # First make window visible
                window.show()
                
                # Then maximize it
                window.setWindowState(Qt.WindowMaximized)
                QTimer.singleShot(100, window.showMaximized)
                
                # Run application
                return app.exec_()
                
            except ImportError as e:
                print(f"Error: PyQt5 not found: {e}")
                print("Falling back to Tkinter version")
                args.pyqt = False
        
        # Default to Tkinter for main GUI
        if not args.pyqt:
            try:
                # Find the tkinter module path
                tk_module_paths = [
                    os.path.join(script_dir, "mame_controls_tkinter.py"),
                    os.path.join(parent_dir, "mame_controls_tkinter.py") if 'parent_dir' in locals() else None,
                    os.path.join(mame_dir, "preview", "mame_controls_tkinter.py"),
                    os.path.join(mame_dir, "mame_controls_tkinter.py")
                ]
                
                tk_module_path = None
                for path in tk_module_paths:
                    if path and os.path.exists(path):
                        tk_module_path = path
                        break
                
                if not tk_module_path:
                    print("Error: Could not find mame_controls_tkinter.py")
                    return 1
                
                # Check if customtkinter is available
                try:
                    import customtkinter as ctk
                except ImportError:
                    print("Error: customtkinter module not found")
                    print("Please install with: pip install customtkinter")
                    return 1
                
                # Import the module
                print(f"Loading tkinter module from: {tk_module_path}")
                spec = importlib.util.spec_from_file_location("mame_controls_tkinter", tk_module_path)
                tkinter_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(tkinter_module)
                
                # Set appearance mode and theme
                ctk.set_appearance_mode("dark")
                ctk.set_default_color_theme("dark-blue")
                
                # Create the Tkinter application
                app = tkinter_module.MAMEControlConfig()
                
                # Auto maximize
                app.after(100, app.state, 'zoomed')
                
                # Run the application
                app.mainloop()
                return 0
                
            except ImportError as e:
                print(f"Error: Required module not found: {e}")
                return 1
            except Exception as e:
                print(f"Error launching Tkinter GUI: {e}")
                traceback.print_exc()
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
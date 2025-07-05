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

def create_argument_parser():
    """Create and configure the argument parser with detailed help and examples"""
    
    # Custom formatter that preserves formatting
    class CustomHelpFormatter(argparse.RawDescriptionHelpFormatter):
        def _format_action_invocation(self, action):
            if not action.option_strings:
                default = self._get_default_metavar_for_positional(action)
                metavar, = self._metavar_formatter(action, default)(1)
                return metavar
            else:
                parts = []
                if action.nargs == 0:
                    parts.extend(action.option_strings)
                else:
                    default = self._get_default_metavar_for_optional(action)
                    args_string = self._format_args(action, default)
                    for option_string in action.option_strings:
                        parts.append(f'{option_string} {args_string}')
                return ', '.join(parts)
    
    # Main description
    description = """
MAME Controls Configuration Tool

This application helps you configure and preview MAME control layouts.
It supports multiple input modes (XInput, DInput, JoyCode, KeyCode) and
can generate control overlays for arcade games.

DATABASE vs JSON MODES:
  • Standard mode: Tries database first, falls back to JSON files
  • --use-db mode: Forces database-only operation (no JSON fallback)
  • Database provides faster loading and better organization
  • JSON files are the traditional fallback method

PERFORMANCE MODES:
  • --preview-only: Generates preview from game data (slower, full features)
  • --image-only: Loads pre-saved screenshot (fastest, display only)
"""

    # Examples section
    examples = """
EXAMPLES:

Basic Usage:
  python mame_controls_main.py
    └─ Launch main GUI application

Preview Commands:
  python mame_controls_main.py --preview-only --game pacman
    └─ Show preview window for pacman (uses cache/database/JSON)
  
  python mame_controls_main.py --preview-only --game pacman --use-db
    └─ Show preview for pacman using database only (builds cache first)
  
  python mame_controls_main.py --preview-only --game pacman --clean-preview
    └─ Show clean preview without buttons/UI elements
  
  python mame_controls_main.py --preview-only --game pacman --no-buttons
    └─ Show preview with buttons hidden

Fast Image Display (NEW):
  python mame_controls_main.py --image-only --game sf2
    └─ Load pre-saved sf2.png from preview/screenshots (FASTEST!)
  
  python mame_controls_main.py --image-only --game pacman --auto-close
    └─ Load pacman.png and auto-close when MAME exits

Cache Management:
  python mame_controls_main.py --precache --game pacman
    └─ Pre-build cache for pacman (database → JSON fallback)
  
  python mame_controls_main.py --precache --game pacman --use-db
    └─ Pre-build cache for pacman from database only (no fallback)

Batch Operations:
  for game in pacman galaga frogger; do
    python mame_controls_main.py --precache --game $game
  done
    └─ Pre-cache multiple games for faster preview loading

Export Operations (if supported):
  python mame_controls_main.py --export-image --game pacman --output pacman.png
    └─ Export control layout as image file

Advanced Options:
  python mame_controls_main.py --preview-only --game pacman --screen 2
    └─ Show preview on secondary monitor
  
  python mame_controls_main.py --image-only --game sf2 --screen 2
    └─ Show pre-saved image on secondary monitor

COMMON WORKFLOWS:

1. First-time setup:
   python mame_controls_main.py
   └─ Configure your settings and build database

2. Quick preview:
   python mame_controls_main.py --preview-only --game <romname>
   └─ Fast preview using existing cache/database

3. Lightning-fast display (after saving images):
   python mame_controls_main.py --image-only --game <romname>
   └─ Instant display of pre-saved screenshot (fastest possible)

4. Export all images, then use fast mode:
   # Export images for your favorite games
   python mame_controls_main.py --export-image --game sf2 --output preview/screenshots/sf2.png
   python mame_controls_main.py --export-image --game pacman --output preview/screenshots/pacman.png
   
   # Now use lightning-fast image mode
   python mame_controls_main.py --image-only --game sf2
   python mame_controls_main.py --image-only --game pacman

5. Force fresh data:
   python mame_controls_main.py --precache --game <romname> --use-db
   python mame_controls_main.py --preview-only --game <romname>
   └─ Rebuild cache from database, then show preview

6. Troubleshooting:
   python mame_controls_main.py --preview-only --game <romname> --use-db
   └─ Test if ROM exists in database and can generate preview
"""

    # Create parser with custom formatter
    parser = argparse.ArgumentParser(
        description=description,
        epilog=examples,
        formatter_class=CustomHelpFormatter,
        prog='mame_controls_main.py'
    )
    
    # Mode selection arguments
    mode_group = parser.add_argument_group('MODE SELECTION', 'Choose the operation mode')
    mode_group.add_argument(
        '--preview-only', 
        action='store_true',
        help='Show preview window only (requires --game) - generates from game data'
    )
    mode_group.add_argument(
        '--image-only', 
        action='store_true',
        help='Show pre-saved image only (requires --game) - loads from preview/screenshots/ROMNAME.png (FASTEST!)'
    )
    mode_group.add_argument(
        '--precache', 
        action='store_true',
        help='Pre-build cache for faster preview loading (requires --game)'
    )
    mode_group.add_argument(
        '--export-image', 
        action='store_true',
        help='Export control layout as image (requires --game and --output)'
    )
    
    # Game specification
    game_group = parser.add_argument_group('GAME SPECIFICATION', 'Specify which ROM to work with')
    game_group.add_argument(
        '--game', 
        type=str, 
        metavar='ROMNAME',
        help='ROM name to process (e.g., pacman, galaga, sf2)'
    )
    
    # Data source options
    data_group = parser.add_argument_group('DATA SOURCE OPTIONS', 'Control where game data comes from (only for --preview-only)')
    data_group.add_argument(
        '--use-db', 
        action='store_true',
        help='Force database mode - no JSON fallback (fails if ROM not in database) [ignored in --image-only mode]'
    )
    
    # Preview customization
    preview_group = parser.add_argument_group('PREVIEW CUSTOMIZATION', 'Modify preview appearance and behavior')
    preview_group.add_argument(
        '--clean-preview', 
        action='store_true',
        help='Show preview without buttons and UI elements (clean export-ready view) [ignored in --image-only mode]'
    )
    preview_group.add_argument(
        '--no-buttons', 
        action='store_true',
        help='Hide control buttons in preview (overrides user settings) [ignored in --image-only mode]'
    )
    preview_group.add_argument(
        '--auto-close', 
        action='store_true',
        help='Automatically close preview when MAME process exits [works with both --preview-only and --image-only]'
    )
    preview_group.add_argument(
        '--screen', 
        type=int, 
        default=1, 
        metavar='N',
        help='Display preview on screen number N (default: 1) [works with both --preview-only and --image-only]'
    )
    
    # Export options
    export_group = parser.add_argument_group('EXPORT OPTIONS', 'Image export settings')
    export_group.add_argument(
        '--output', 
        type=str, 
        metavar='FILEPATH',
        help='Output file path for exported image (required with --export-image)'
    )
    export_group.add_argument(
        '--format', 
        type=str, 
        choices=['png', 'jpg', 'jpeg', 'bmp'], 
        default='png',
        help='Image format for export (default: png)'
    )
    export_group.add_argument(
        '--no-bezel', 
        action='store_true',
        help='Exclude bezel/border in exported image'
    )
    export_group.add_argument(
        '--no-logo', 
        action='store_true',
        help='Exclude logo in exported image'
    )
    
    return parser

def validate_arguments(args):
    """Validate argument combinations and provide helpful error messages"""
    errors = []
    
    # Check for required combinations
    if args.preview_only and not args.game:
        errors.append("--preview-only requires --game parameter")
    
    if args.image_only and not args.game:
        errors.append("--image-only requires --game parameter")
    
    if args.precache and not args.game:
        errors.append("--precache requires --game parameter")
    
    if args.export_image and not args.game:
        errors.append("--export-image requires --game parameter")
    
    if args.export_image and not args.output:
        errors.append("--export-image requires --output parameter")
    
    # Check for conflicting modes
    mode_count = sum([args.preview_only, args.image_only, args.precache, args.export_image])
    if mode_count > 1:
        errors.append("Cannot combine --preview-only, --image-only, --precache, and --export-image modes")
    
    # Check for options that only work with certain modes
    if args.clean_preview and not args.preview_only:
        errors.append("--clean-preview only works with --preview-only mode")
    
    if args.auto_close and not (args.preview_only or args.image_only):
        errors.append("--auto-close works with --preview-only or --image-only modes")
    
    if args.no_buttons and not (args.preview_only or args.export_image):
        errors.append("--no-buttons only works with --preview-only or --export-image modes")
    
    # Database options only work with modes that need game data
    if args.use_db and not (args.preview_only or args.precache or args.export_image):
        errors.append("--use-db only works with --preview-only, --precache, or --export-image modes")
    
    # Export-specific validations
    if args.no_bezel and not args.export_image:
        errors.append("--no-bezel only works with --export-image mode")
    
    if args.no_logo and not args.export_image:
        errors.append("--no-logo only works with --export-image mode")
    
    if args.format != 'png' and not args.export_image:
        errors.append("--format only works with --export-image mode")
    
    # File path validation
    if args.output:
        import os
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            errors.append(f"Output directory does not exist: {output_dir}")
    
    return errors

# NEW: Fast image-only preview implementation
def show_image_only_preview(rom_name, mame_dir, auto_close=False, screen=1):
    """Ultra-fast preview mode that just loads a pre-saved screenshot"""
    import os  # Import os at the top of the function
    
    print(f"⚡ LIGHTNING MODE: Loading pre-saved image for {rom_name}")
    
    # Look for screenshot in expected location
    preview_dir = os.path.join(mame_dir, "preview")
    screenshots_dir = os.path.join(preview_dir, "screenshots")
    
    # Try multiple image extensions
    extensions = ['.png', '.jpg', '.jpeg', '.bmp']
    image_path = None
    
    for ext in extensions:
        potential_path = os.path.join(screenshots_dir, f"{rom_name}{ext}")
        if os.path.exists(potential_path):
            image_path = potential_path
            break
    
    if not image_path:
        print(f"❌ ERROR: No screenshot found for '{rom_name}'")
        print(f"📁 Looked in: {screenshots_dir}")
        print(f"🔍 Expected files: {rom_name}.png, {rom_name}.jpg, etc.")
        print(f"💡 Use --export-image first to create the screenshot, or use --preview-only for full generation")
        return 1
    
    print(f"✅ Found screenshot: {os.path.basename(image_path)}")
    print(f"📁 Loading from: {image_path}")
    
    try:
        # Use PyQt5 for fast image display
        from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
        from PyQt5.QtGui import QPixmap, QKeySequence, QFont
        from PyQt5.QtCore import Qt, QTimer
        
        # Create lightweight application
        app = QApplication(sys.argv)
        app.setApplicationName("MAME Controls - Lightning Preview")
        
        # Create main window with MAME-fighting configuration
        window = QWidget()
        window.setWindowTitle(f"MAME Controls - {rom_name.upper()} (Lightning Mode)")
        
        # Try to get the currently active window (might be MAME) and work with it
        try:
            active_window = app.activeWindow()
            if active_window:
                print(f"🎮 Found active window, setting preview as modal")
                window.setWindowModality(Qt.ApplicationModal)
        except:
            pass
        
        # Configure for fullscreen display with MAME-fighting window flags
        window.setWindowFlags(
            Qt.WindowStaysOnTopHint | 
            Qt.FramelessWindowHint | 
            Qt.Tool |  # This is KEY - Qt.Tool flag helps with MAME compatibility
            Qt.X11BypassWindowManagerHint  # Try to bypass window manager completely
        )
        
        window.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                color: white;
            }
        """)
        
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Load and display image
        print(f"📷 Loading image...")
        pixmap = QPixmap(image_path)
        
        if pixmap.isNull():
            print(f"❌ ERROR: Failed to load image from {image_path}")
            return 1
        
        # Create image label with fullscreen scaling
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setScaledContents(False)  # We'll handle scaling manually
        
        # Add to layout
        layout.addWidget(image_label)
        
        window.setLayout(layout)
        
        # Configure for fullscreen display with MAME-fighting window flags
        window.setWindowFlags(
            Qt.WindowStaysOnTopHint | 
            Qt.FramelessWindowHint | 
            Qt.Tool  # This is KEY - Qt.Tool flag helps with MAME compatibility
        )
        
        # Handle screen positioning and fullscreen with exact geometry matching
        from PyQt5.QtWidgets import QDesktopWidget
        desktop = QDesktopWidget()
        
        if screen > 1:
            try:
                if screen <= desktop.screenCount():
                    screen_geometry = desktop.screenGeometry(screen - 1)
                    # Use setGeometry instead of showFullScreen for exact control
                    window.setGeometry(screen_geometry)
                    print(f"📺 Fullscreen on screen {screen} - exact geometry: {screen_geometry.width()}x{screen_geometry.height()}")
                else:
                    print(f"⚠️  Screen {screen} not available, using default")
                    screen_geometry = desktop.screenGeometry(0)
                    window.setGeometry(screen_geometry)
            except Exception as e:
                print(f"⚠️  Screen positioning failed: {e}")
                screen_geometry = desktop.screenGeometry(0)
                window.setGeometry(screen_geometry)
        else:
            # Default to primary screen with exact geometry
            screen_geometry = desktop.screenGeometry(0)
            window.setGeometry(screen_geometry)
            print(f"📺 Fullscreen on primary screen - exact geometry: {screen_geometry.width()}x{screen_geometry.height()}")
        
        # Scale image to fit the exact screen geometry
        scaled_pixmap = pixmap.scaled(
            screen_geometry.size(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        image_label.setPixmap(scaled_pixmap)
        
        # Add keyboard shortcuts for better control
        def close_window():
            print("👋 Closing lightning preview...")
            window.close()
            app.quit()
        
        def toggle_fullscreen():
            if window.isFullScreen():
                window.showNormal()
                print("🪟 Switched to windowed mode")
            else:
                window.showFullScreen()
                print("📺 Switched to fullscreen mode")
        
        # Handle ESC key and F key
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtCore import QTimer
        
        esc_shortcut = QShortcut(QKeySequence("Escape"), window)
        esc_shortcut.activated.connect(close_window)
        
        f_shortcut = QShortcut(QKeySequence("F"), window)
        f_shortcut.activated.connect(toggle_fullscreen)
        
        # Also handle F11 for fullscreen toggle
        f11_shortcut = QShortcut(QKeySequence("F11"), window)
        f11_shortcut.activated.connect(toggle_fullscreen)
        
        # Add gamepad/joystick input handling
        def check_gamepad_input():
            """Check for gamepad button presses to close preview"""
            try:
                import pygame
                
                # Initialize pygame joystick module if not already done
                if not hasattr(check_gamepad_input, 'initialized'):
                    pygame.init()
                    pygame.joystick.init()
                    check_gamepad_input.initialized = True
                    
                    # Initialize all connected joysticks
                    joystick_count = pygame.joystick.get_count()
                    check_gamepad_input.joysticks = []
                    for i in range(joystick_count):
                        joystick = pygame.joystick.Joystick(i)
                        joystick.init()
                        check_gamepad_input.joysticks.append(joystick)
                        print(f"🎮 Gamepad detected: {joystick.get_name()}")
                
                # Process pygame events
                pygame.event.pump()
                
                # Check for joystick button presses
                for joystick in getattr(check_gamepad_input, 'joysticks', []):
                    # Check any button press (buttons 0-15 should cover most gamepads)
                    for button_num in range(min(16, joystick.get_numbuttons())):
                        if joystick.get_button(button_num):
                            print(f"🎮 Gamepad button {button_num} pressed - closing preview")
                            close_window()
                            return
                    
                    # Check D-pad/hat movements
                    for hat_num in range(joystick.get_numhats()):
                        hat_value = joystick.get_hat(hat_num)
                        if hat_value != (0, 0):  # Any D-pad direction
                            print(f"🎮 D-pad pressed - closing preview")
                            close_window()
                            return
                
            except ImportError:
                # pygame not available, skip gamepad input
                pass
            except Exception as e:
                # Ignore gamepad errors to avoid crashes
                pass
        
        # Add additional keyboard input handling for any key press
        def handle_key_press(event):
            """Handle any key press to close preview"""
            key = event.key()
            
            # Allow F and F11 to work for fullscreen toggle
            if key in [Qt.Key_F, Qt.Key_F11]:
                return  # Let the shortcuts handle these
            
            # Allow Escape to work normally
            if key == Qt.Key_Escape:
                return  # Let the shortcut handle this
            
            # Any other key closes the preview
            print(f"⌨️  Key pressed - closing preview")
            close_window()
        
        # Override the key press event for the window
        original_keyPressEvent = window.keyPressEvent
        window.keyPressEvent = handle_key_press
        
        # Start gamepad monitoring timer
        gamepad_timer = QTimer()
        gamepad_timer.timeout.connect(check_gamepad_input)
        gamepad_timer.start(50)  # Check every 50ms for responsive input
        
        # Auto-close functionality if enabled
        if auto_close:
            print("🔄 Auto-close enabled - will monitor for MAME process")
            
            # Simple MAME process monitoring
            def check_mame_process():
                import subprocess
                try:
                    # Check if any MAME process is running
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq mame*.exe'], 
                                          capture_output=True, text=True, timeout=5)
                    if 'mame' not in result.stdout.lower():
                        print("🎮 MAME process not detected, closing preview...")
                        close_window()
                        return
                except:
                    pass  # Continue monitoring
                
                # Check again in 2 seconds
                QTimer.singleShot(2000, check_mame_process)
            
            # Start monitoring after 3 seconds
            QTimer.singleShot(3000, check_mame_process)
        
        # Show window with MAME-compatible display sequence (matching working preview)
        window.show()
        
        # Apply the exact sequence from show_preview_standalone
        window.setGeometry(screen_geometry)
        window.showFullScreen()  # Add this - your working code uses both setGeometry AND showFullScreen
        window.activateWindow()
        window.raise_()
        
        # Force immediate processing
        app.processEvents()
        
        # Additional aggressive window focusing to combat MAME
        def force_window_front():
            """Aggressively bring window to front and keep it there"""
            # Re-apply geometry to ensure fullscreen
            window.setGeometry(screen_geometry)
            window.showFullScreen()  # Force fullscreen again
            window.raise_()
            window.activateWindow()
            window.setFocus()
            # Force window to top again
            app.processEvents()
        
        # Immediate first forcing
        force_window_front()
        
        # Set up a timer to periodically bring window to front (for MAME compatibility)
        focus_timer = QTimer()
        focus_timer.timeout.connect(force_window_front)
        focus_timer.start(100)  # More aggressive - every 100ms initially
        
        # Reduce frequency after 2 seconds, stop after 5 seconds
        def reduce_focus_frequency():
            focus_timer.stop()
            focus_timer.start(500)  # Reduce to every 500ms
            print("🎯 Reduced focus timer frequency")
        
        def stop_focus_timer():
            focus_timer.stop()
            print("🎯 Window focus established")
        
        QTimer.singleShot(2000, reduce_focus_frequency)
        QTimer.singleShot(5000, stop_focus_timer)
        
        # Print performance stats
        file_size = os.path.getsize(image_path)
        print(f"📊 Image loaded: {pixmap.width()}x{pixmap.height()}, {file_size:,} bytes")
        print(f"📺 Displaying fullscreen (scaled: {scaled_pixmap.width()}x{scaled_pixmap.height()})")
        print(f"🎯 Window set to always-on-top for MAME compatibility")
        print(f"⚡ Lightning preview ready! (Any key/gamepad button to close, F/F11 for fullscreen)")
        
        # Run the application
        return app.exec_()
        
    except ImportError:
        print("❌ PyQt5 not available for image display")
        return 1
    except Exception as e:
        print(f"❌ Error in lightning preview: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
def validate_cache_file(cache_file: str, rom_name: str) -> bool:
    """Fast cache validation - only check essential structure"""
    try:
        if not os.path.exists(cache_file):
            return False
            
        # Quick file size check
        if os.path.getsize(cache_file) < 100:  # Too small to be valid
            return False
            
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        
        # Minimal validation - just check if it has game data
        if isinstance(cache_data, dict):
            if 'game_data' in cache_data:  # New format
                return isinstance(cache_data['game_data'], dict)
            elif 'players' in cache_data:  # Old format
                return isinstance(cache_data['players'], list)
        
        return False
        
    except:
        return False

# Replace the argument parsing section in main() with this:
def main():
    """Main entry point for the application with improved path handling and comprehensive argument parsing"""
    print("Starting MAME Controls application...")
    
    # Set up signal handlers for proper shutdown
    def signal_handler(sig, frame):
        print(f"Received signal {sig}, shutting down...")
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
        # Create and parse arguments
        parser = create_argument_parser()
        args = parser.parse_args()
        
        # Validate argument combinations
        validation_errors = validate_arguments(args)
        if validation_errors:
            print("❌ ARGUMENT ERRORS:")
            for error in validation_errors:
                print(f"   • {error}")
            print(f"\nUse '{parser.prog} --help' for usage information and examples.")
            return 1
        
        print("✅ Arguments parsed and validated.")
        
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
        
        # Always check database settings, regardless of mode
        settings_dir = os.path.join(app_dir, "settings")
        db_path = os.path.join(settings_dir, "gamedata.db")
        print(f"Looking for database at: {db_path}")
        print(f"Database file exists: {os.path.exists(db_path)}")

        # Ensure settings directory exists
        os.makedirs(settings_dir, exist_ok=True)

        # Database usage logic - updated to handle --use-db properly
        if args.use_db:
            if os.path.exists(db_path):
                print(f"🗃️  FORCED DATABASE MODE: Using {db_path}")
                print("📝 Cache will be bypassed entirely")
                use_database = True
                use_cache = False  # Force disable cache
            else:
                print(f"❌ ERROR: --use-db specified but database not found at {db_path}")
                print("💡 Run the main application first to build the database")
                return 1
        elif os.path.exists(db_path):
            # Default behavior: use database if available and not using cache
            print(f"🗃️  Database found: {db_path}")
            print("📊 Using database for faster loading")
            use_database = True
        else:
            print("📄 No database found, will use JSON lookup")
            use_database = False

        # Handle precache mode separately (no GUI needed)
        if args.game and args.precache:
            print(f"📦 Precaching game data for: {args.game}")
            
            # Handle --use-db flag for precache
            if args.use_db and not use_database:
                print("❌ Cannot use --use-db: database not available")
                return 1
            
            import time
            import json
            start_time = time.time()
            
            # Set up directories
            preview_dir = os.path.join(mame_dir, "preview")
            cache_dir = os.path.join(preview_dir, "cache")
            settings_dir = os.path.join(preview_dir, "settings")
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(cache_dir, f"{args.game}_cache.json")
            
            # Check if we have an old format cache that needs migration
            needs_migration = False
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        existing_cache = json.load(f)
                    
                    # Check if it's old format (direct game data without wrapper)
                    if isinstance(existing_cache, dict) and 'players' in existing_cache and 'game_data' not in existing_cache:
                        print(f"🔄 Found OLD format cache for {args.game} - will migrate to new format")
                        needs_migration = True
                    elif isinstance(existing_cache, dict) and 'game_data' in existing_cache:
                        print(f"✅ Found NEW format cache for {args.game} - will refresh with latest data")
                    else:
                        print(f"❓ Found unrecognized cache format for {args.game} - will rebuild")
                        needs_migration = True
                        
                except Exception as e:
                    print(f"⚠️  Error reading existing cache: {e} - will rebuild")
                    needs_migration = True
            
            try:
                # Import data utilities directly
                from mame_data_utils import (
                    load_gamedata_json, load_custom_configs, load_default_config,
                    parse_cfg_controls, convert_mapping, update_game_data_with_custom_mappings,
                    filter_xinput_controls, get_game_data, get_game_data_from_db
                )
                
                # Load input mode and settings from settings file
                input_mode, xinput_only_mode, friendly_names = load_input_mode_from_settings(preview_dir)
                
                print(f"🎮 Cache settings: mode={input_mode}, xinput_only={xinput_only_mode}, friendly={friendly_names}")
                
                # Load game data based on --use-db flag
                game_data = None
                
                if use_database and args.use_db:
                    print(f"🗃️  FORCED DATABASE MODE: Loading {args.game} from database only")
                    
                    # Use database directly, bypass all other sources
                    game_data = get_game_data_from_db(args.game, db_path)
                    
                    if game_data:
                        print(f"✅ Retrieved {args.game} from database")
                        game_data['source'] = 'gamedata.db (forced)'
                    else:
                        print(f"❌ ROM {args.game} not found in database")
                        return 1
                else:
                    # Standard loading process (database, then JSON fallback)
                    print(f"📊 Loading {args.game} using standard process...")
                    
                    # Load all data files for fallback
                    gamedata_path = os.path.join(settings_dir, "gamedata.json")
                    if not os.path.exists(gamedata_path):
                        # Try alternative locations
                        alt_paths = [
                            os.path.join(mame_dir, "gamedata.json"),
                            os.path.join(os.path.dirname(mame_dir), "gamedata.json")
                        ]
                        for alt_path in alt_paths:
                            if os.path.exists(alt_path):
                                gamedata_path = alt_path
                                break
                    
                    if not os.path.exists(gamedata_path):
                        print(f"❌ ERROR: gamedata.json not found")
                        return 1
                    
                    # Load gamedata and parent lookup for fallback
                    gamedata_json, parent_lookup, clone_parents = load_gamedata_json(gamedata_path)
                    rom_data_cache = {}
                    
                    # Use the unified get_game_data function
                    game_data = get_game_data(
                        romname=args.game,
                        gamedata_json=gamedata_json,
                        parent_lookup=parent_lookup,
                        db_path=db_path if use_database else None,
                        rom_data_cache=rom_data_cache
                    )
                
                if not game_data:
                    print(f"❌ ERROR: No game data found for {args.game}")
                    return 1
                
                print(f"📋 Data source: {game_data.get('source', 'unknown')}")
                
                # Process custom mappings (same for both database and JSON)
                cfg_controls = {}
                
                # Load custom configs and default controls for processing
                if not args.use_db or not use_database:
                    # Only load these if we're not in pure database mode
                    custom_configs = load_custom_configs(mame_dir)
                    default_controls, original_default_controls = load_default_config(mame_dir)
                else:
                    # In pure database mode, we still need these for custom mapping processing
                    print("🔧 Loading configs for custom mapping processing...")
                    custom_configs = load_custom_configs(mame_dir)
                    default_controls, original_default_controls = load_default_config(mame_dir)
                
                # Process custom mappings if they exist
                if args.game in custom_configs:
                    cfg_content = custom_configs[args.game]
                    parsed_controls = parse_cfg_controls(cfg_content, input_mode)
                    if parsed_controls:
                        print(f"🎛️  Found {len(parsed_controls)} control mappings in ROM CFG")
                        cfg_controls = {
                            control: convert_mapping(mapping, input_mode)
                            for control, mapping in parsed_controls.items()
                        }
                    else:
                        print(f"📄 ROM CFG exists but contains no control mappings")
                
                # Apply custom mappings and input mode processing
                game_data = update_game_data_with_custom_mappings(
                    game_data=game_data,
                    cfg_controls=cfg_controls,
                    default_controls=default_controls,
                    original_default_controls=original_default_controls,
                    input_mode=input_mode
                )
                
                # Apply XInput-only filtering if enabled
                if xinput_only_mode:
                    game_data = filter_xinput_controls(game_data)
                    print(f"🎯 Applied XInput-only filter")
                
                # Save the processed game data to NEW cache format
                try:
                    # Create cache in new format with metadata wrapper
                    new_cache_data = {
                        'rom_name': args.game,
                        'input_mode': input_mode,
                        'friendly_names': friendly_names,
                        'xinput_only_mode': xinput_only_mode,
                        'cached_timestamp': time.time(),
                        'cache_version': '2.0',  # Mark as new format
                        'game_data': game_data  # The actual game data
                    }
                    
                    with open(cache_file, 'w') as f:
                        json.dump(new_cache_data, f, indent=2)
                    
                    load_time = time.time() - start_time
                    
                    # Enhanced status output
                    print("=" * 50)
                    print(f"✅ PRECACHE COMPLETE")
                    print(f"🎮 ROM: {args.game}")
                    print(f"⏱️  Time: {load_time:.3f} seconds")
                    print(f"📊 Source: {game_data.get('source', 'unknown')}")
                    print(f"🎛️  Input Mode: {input_mode}")
                    print(f"🎯 XInput-only: {xinput_only_mode}")
                    print(f"🎨 Friendly Names: {friendly_names}")
                    print(f"📁 Cache File: {os.path.basename(cache_file)}")
                    print(f"📋 Cache Version: 2.0 (NEW FORMAT)")
                    
                    if needs_migration:
                        print(f"🔄 Successfully migrated from old cache format")
                    
                    if use_database and args.use_db:
                        print(f"🗃️  Database Mode: FORCED (bypassed cache)")
                    elif use_database:
                        print(f"🗃️  Database Mode: AUTO")
                    else:
                        print(f"📄 JSON Mode: Fallback")
                    
                    print(f"👥 Players: {len(game_data.get('players', []))}")
                    
                    if game_data.get('players'):
                        for player in game_data['players']:
                            control_count = len(player.get('labels', []))
                            custom_count = len([l for l in player.get('labels', []) if l.get('is_custom', False)])
                            mapped_count = len([l for l in player.get('labels', []) if l.get('target_button')])
                            print(f"  P{player['number']}: {control_count} controls ({custom_count} custom, {mapped_count} mapped)")
                            
                            # Show sample control
                            if control_count > 0:
                                sample_label = player['labels'][0]
                                display_value = (sample_label.get('target_button') or 
                                            sample_label.get('display_name') or 
                                            sample_label['value'])
                                print(f"    Sample: {sample_label['name']} → {display_value}")
                    
                    print("=" * 50)
                                
                except Exception as e:
                    print(f"❌ Error saving cache: {e}")
                    import traceback
                    traceback.print_exc()
                    return 1
                
            except ImportError as e:
                print(f"❌ Error importing data utilities: {e}")
                print("💡 Make sure mame_data_utils.py is in the correct location")
                return 1
            except Exception as e:
                print(f"❌ Unexpected error in precache: {e}")
                import traceback
                traceback.print_exc()
                return 1
            
            # Exit without showing any UI
            return 0

        # Handle IMAGE-ONLY mode (NEW - FASTEST MODE)
        if args.game and args.image_only:
            print(f"⚡ LIGHTNING MODE: Fast image display for ROM: {args.game}")
            
            # This mode completely bypasses all game data loading and just shows a pre-saved image
            # It's the fastest possible way to display a control layout
            # Perfect for when you've already exported images and want instant display
            
            print(f"🚀 Launching lightning preview...")
            return show_image_only_preview(
                rom_name=args.game,
                mame_dir=mame_dir,
                auto_close=args.auto_close,
                screen=args.screen
            )
        
        # Check for preview-only mode - OPTIMIZED VERSION
        if args.game and args.preview_only:
            print(f"🎯 Fast preview mode for ROM: {args.game}")
            
            # PERFORMANCE FIX 1: Quick cache check only
            preview_dir = os.path.join(mame_dir, "preview")
            cache_dir = os.path.join(preview_dir, "cache")
            cache_file = os.path.join(cache_dir, f"{args.game}_cache.json")
            
            # For standard preview mode, just check cache exists (skip heavy validation)
            if not args.use_db and not os.path.exists(cache_file):
                print(f"❌ No cache for '{args.game}' - run precache first")
                return 1
            
            try:
                # PERFORMANCE FIX 2: Minimal imports
                from PyQt5.QtWidgets import QApplication
                from mame_controls_pyqt import MAMEControlConfig
                
                # PERFORMANCE FIX 3: Lightweight app creation
                app = QApplication(sys.argv)
                app.setApplicationName("MAME Control Preview")

                # SKIP: set_dark_theme(app)  # MAJOR PERFORMANCE HIT - SKIP IN PREVIEW MODE
                
                # PERFORMANCE FIX 4: Minimal config creation
                config = MAMEControlConfig(preview_only=True)
                
                # Set only essential attributes
                config.mame_dir = mame_dir
                config.preview_dir = preview_dir
                config.cache_dir = cache_dir
                
                # PERFORMANCE FIX 5: Apply command line options quickly
                if args.no_buttons:
                    config.hide_preview_buttons = True
                
                # PERFORMANCE FIX 6: Handle database mode efficiently (if needed)
                if args.use_db:
                    # For --use-db mode, build minimal cache then show preview
                    db_path = os.path.join(preview_dir, "settings", "gamedata.db")
                    if os.path.exists(db_path):
                        config.use_database = True
                        config.db_path = db_path
                
                # PERFORMANCE FIX 7: Fast preview launch
                print(f"🚀 Launching preview...")
                config.show_preview_standalone(args.game, args.auto_close, args.clean_preview)
                
                # Run app
                return app.exec_()
                
            except ImportError:
                print("❌ PyQt5 not found for preview mode")
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
    """Load the current input mode from settings file with enhanced error handling"""
    settings_dir = os.path.join(preview_dir, "settings")
    settings_path = os.path.join(settings_dir, "control_config_settings.json")
    
    # Default to xinput if no settings found
    default_input_mode = 'xinput'
    default_xinput_only_mode = True
    default_friendly_names = True
    
    try:
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            
            # Load input mode
            input_mode = settings.get('input_mode', default_input_mode)
            if input_mode not in ['joycode', 'xinput', 'dinput', 'keycode']:
                print(f"Invalid input mode '{input_mode}' in settings, using default: {default_input_mode}")
                input_mode = default_input_mode
            
            # Load other settings that affect cache
            xinput_only_mode = settings.get('xinput_only_mode', default_xinput_only_mode)
            friendly_names = settings.get('friendly_names', default_friendly_names)
                
            print(f"Loaded settings: mode={input_mode}, xinput_only={xinput_only_mode}, friendly={friendly_names}")
            return input_mode, xinput_only_mode, friendly_names
        else:
            print(f"No settings file found at {settings_path}, using defaults")
            return default_input_mode, default_xinput_only_mode, default_friendly_names
    except Exception as e:
        print(f"Error loading settings: {e}, using defaults")
        return default_input_mode, default_xinput_only_mode, default_friendly_names

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
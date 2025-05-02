import builtins
import os
import random
import sys
import json
import traceback
from PyQt5 import sip
from PyQt5.QtWidgets import (QAction, QGridLayout, QLayout, QLineEdit, QMainWindow, QMenu, QMessageBox, QSizePolicy, QSpinBox, QVBoxLayout, QHBoxLayout, QWidget, 
                            QLabel, QPushButton, QFrame, QApplication, QDesktopWidget,
                            QDialog, QGroupBox, QCheckBox, QSlider, QComboBox)
from PyQt5.QtGui import QBrush, QFontInfo, QImage, QLinearGradient, QPalette, QPixmap, QFont, QColor, QPainter, QPen, QFontMetrics
from PyQt5.QtCore import Qt, QPoint, QTimer, QRect, QEvent, QSize

# Helper function that should be at the top of the file
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
    if os.path.basename(app_path) == "preview":
        return os.path.dirname(app_path)
    else:
        # We're already in the MAME directory
        return app_path
    
class PreviewWindow(QMainWindow):
    """Window for displaying game controls preview"""
    def __init__(self, rom_name, game_data, mame_dir, parent=None, hide_buttons=False, clean_mode=False, font_registry=None):
        """Enhanced initialization with better parameter handling"""
        # Make sure we call super().__init__ with the correct parent parameter
        # The parent must be a QWidget or None, not a string
        super().__init__(parent)  # Ensure parent is passed correctly

        # Path handling
        self.setVisible(False)  # Start invisible
        self.rom_name = rom_name
        self.game_data = game_data
        
        # Set up path handling
        if hasattr(self, 'setup_directory_structure'):
            # Use the new directory structure setup method if available
            self.setup_directory_structure()
        else:
            # Legacy path handling
            self.app_dir = get_application_path()
            
            # If mame_dir is in preview folder, adjust to parent
            if isinstance(mame_dir, str) and os.path.basename(mame_dir).lower() == "preview":
                self.mame_dir = os.path.dirname(mame_dir)
            else:
                self.mame_dir = mame_dir
                
            # Define key directories
            self.preview_dir = os.path.join(self.mame_dir, "preview")
            self.settings_dir = os.path.join(self.preview_dir, "settings")
            self.fonts_dir = os.path.join(self.preview_dir, "fonts")
            
            # Create directories if they don't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            os.makedirs(self.fonts_dir, exist_ok=True)
        
        print(f"ROM: {rom_name}")
        print(f"App directory: {self.app_dir if hasattr(self, 'app_dir') else 'Not set'}")
        print(f"MAME directory: {self.mame_dir}")
        print(f"Preview directory: {self.preview_dir if hasattr(self, 'preview_dir') else 'Not set'}")
        
        self.control_labels = {}
        self.bg_label = None
        
        # Add clean preview mode parameters
        self.hide_buttons = hide_buttons
        self.clean_mode = clean_mode
        
        # Print debugging info
        print(f"Initializing PreviewWindow for ROM: {rom_name}")
        print(f"Clean mode: {clean_mode}, Hide buttons: {hide_buttons}")

        # Force window to be displayed in the correct place
        self.parent = parent
        
        try:
            # Load settings
            self.text_settings = self.load_text_settings()
            self.logo_settings = self.load_logo_settings()

            # Check if button prefix setting is initialized
            if "show_button_prefix" not in self.text_settings:
                self.text_settings["show_button_prefix"] = True
                print("Initialized button prefix setting to default (True)")
            else:
                print(f"Loaded button prefix setting: {self.text_settings['show_button_prefix']}")

            # CRITICAL: Force font loading BEFORE creating labels
            self.load_and_register_fonts()
            
            # Initialize logo_visible from settings
            self.logo_visible = self.logo_settings.get("logo_visible", True)

            # Configure window
            self.setWindowTitle(f"Control Preview: {rom_name}")
            self.resize(1280, 720)
            
            # Set attributes for proper window handling
            self.setAttribute(Qt.WA_DeleteOnClose, True)
            
            # Create central widget with black background
            self.central_widget = QWidget()
            self.central_widget.setStyleSheet("background-color: black;")
            self.setCentralWidget(self.central_widget)

            # Main layout
            self.main_layout = QVBoxLayout(self.central_widget)
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_layout.setSpacing(0)

            # Canvas area for background + controls
            self.canvas = QWidget()
            self.canvas.setStyleSheet("background-color: black;")
            self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            self.main_layout.addWidget(self.canvas, 1)

            # Load background
            self.load_background_image_fullscreen()

            # Create control labels - WITH clean mode parameter
            self.create_control_labels(clean_mode=self.clean_mode)

            # Make sure the font is properly applied
            self.apply_text_settings()
            
            # Initialize alignment grid system
            self.alignment_grid_visible = False
            self.grid_x_start = 200       # Default first column X-position
            self.grid_x_step = 300        # Default X-spacing between columns
            self.grid_y_start = 100       # Default first row Y-position
            self.grid_y_step = 60         # Default Y-spacing between rows
            self.grid_columns = 3         # Number of columns in grid
            self.grid_rows = 8            # Number of rows in grid
            self.grid_lines = []          # Empty list to store grid line objects

            # Then, if you have a load_grid_settings method, call it after initializing defaults:
            try:
                if hasattr(self, 'load_grid_settings'):
                    self.load_grid_settings()
            except Exception as e:
                print(f"Error loading grid settings: {e}")
                # Keep using defaults
            
            # Add logo if enabled
            if self.logo_visible:
                self.add_logo()
                
                # NEW: Add a small delay then force logo resize to ensure it applies correctly
                QTimer.singleShot(100, self.force_logo_resize)
            
            # Create button frame as a FLOATING OVERLAY
            if not self.hide_buttons and not self.clean_mode:
                self.create_floating_button_frame()
            
            # Track whether texts are visible
            self.texts_visible = True
            
            # Joystick controls visibility
            self.joystick_visible = True
            
            # Track current screen
            self.current_screen = self.load_screen_setting_from_config()

            # Now move to that screen
            self.initializing_screen = True
            self.current_screen = self.load_screen_setting_from_config()
            self.move_to_screen(self.current_screen)
            self.initializing_screen = False
            
            # Bind ESC key to close
            self.keyPressEvent = self.handle_key_press
            
            # Apply proper layering
            self.layering_for_bezel()
            self.integrate_bezel_support()
            self.canvas.resizeEvent = self.on_canvas_resize_with_background
        
            # Add this line to initialize bezel state after a short delay
            QTimer.singleShot(500, self.ensure_bezel_state)
            
            print("PreviewWindow initialization complete")
            
            QTimer.singleShot(600, self.apply_joystick_visibility)
            QTimer.singleShot(300, self.force_resize_all_labels)
            QTimer.singleShot(1000, self.detect_screen_after_startup)
            # Add this line at the end of __init__, just before self.setVisible(True)
            self.enhance_preview_window_init()
            
            # Make sure we have a transparent background
            transparent_bg_path = self.initialize_transparent_background()
            if transparent_bg_path:
                # Ensure the background is loaded
                self.load_background_image_fullscreen(force_default=transparent_bg_path)
            
            self.initialize_controller_close()
            
            self.setVisible(True)  # Now show the window

            print(f"Window size: {self.width()}x{self.height()}")
            print(f"Canvas size: {self.canvas.width()}x{self.canvas.height()}")
            
        except Exception as e:
            print(f"Error in PreviewWindow initialization: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error initializing preview: {e}")
            self.close()
            
            # Create button frame as a FLOATING OVERLAY
            if not self.hide_buttons and not self.clean_mode:
                self.create_floating_button_frame()
            
            # Track whether texts are visible
            self.texts_visible = True
            
            # Joystick controls visibility
            self.joystick_visible = True
            
            # Track current screen
            self.current_screen = self.load_screen_setting_from_config()

            # Now move to that screen
            self.initializing_screen = True
            self.current_screen = self.load_screen_setting_from_config()
            self.move_to_screen(self.current_screen)
            self.initializing_screen = False
            
            # Bind ESC key to close
            self.keyPressEvent = self.handle_key_press
            
            # Move to primary screen first
            #self.move_to_screen(1)  # Start with primary screen
            self.layering_for_bezel()
            self.integrate_bezel_support()
            self.canvas.resizeEvent = self.on_canvas_resize_with_background
        
            # Add this line to initialize bezel state after a short delay
            QTimer.singleShot(500, self.ensure_bezel_state)
            
            print("PreviewWindow initialization complete")
            
            QTimer.singleShot(600, self.apply_joystick_visibility)
            #QTimer.singleShot(200, self.load_and_register_fonts)
            QTimer.singleShot(300, self.force_resize_all_labels)
            QTimer.singleShot(1000, self.detect_screen_after_startup)
            # Add this line at the end of __init__, just before self.setVisible(True)
            self.enhance_preview_window_init()
            
            self.setVisible(True)  # Now show the fully prepared window

            print(f"Window size: {self.width()}x{self.height()}")
            print(f"Canvas size: {self.canvas.width()}x{self.canvas.height()}")

            
        except Exception as e:
            print(f"Error in PreviewWindow initialization: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error initializing preview: {e}")
            self.close()

    # Add this method to the PreviewWindow class to map button prefixes to control names
    def get_control_name_from_prefix(self, prefix):
        """Map a button prefix back to a standard control name for position lookup"""
        prefix_to_control = {
            "A": "P1_BUTTON1",
            "B": "P1_BUTTON2",
            "X": "P1_BUTTON3",
            "Y": "P1_BUTTON4",
            "LB": "P1_BUTTON5",
            "RB": "P1_BUTTON6",
            "LT": "P1_BUTTON7",
            "RT": "P1_BUTTON8",
            "LS": "P1_BUTTON9",
            "RS": "P1_BUTTON10",
            "LS↑": "P1_JOYSTICK_UP",
            "LS↓": "P1_JOYSTICK_DOWN",
            "LS←": "P1_JOYSTICK_LEFT",
            "LS→": "P1_JOYSTICK_RIGHT",
            "RS↑": "P1_JOYSTICK2_UP",
            "RS↓": "P1_JOYSTICK2_DOWN",
            "RS←": "P1_JOYSTICK2_LEFT",
            "RS→": "P1_JOYSTICK2_RIGHT",
            "START": "P1_START",
            "BACK": "P1_SELECT"
        }
        
        return prefix_to_control.get(prefix, "")
    
    # Add this method to the PreviewWindow class
    def resizeEvent(self, event):
        """Handle main window resize events"""
        # Call the parent class's resizeEvent first
        super().resizeEvent(event)
        
        # Reposition the button frame
        if hasattr(self, 'position_button_frame'):
            self.position_button_frame()
        
        # Also handle bezel resizing if needed
        if hasattr(self, 'on_resize_with_bezel'):
            self.on_resize_with_bezel(event)
    
    def setup_directory_structure(self):
        """Set up and validate the directory structure for the application"""
        # Determine base path
        self.app_dir = get_application_path()
        
        # If we're in the preview folder, mame_dir is the parent
        if os.path.basename(self.app_dir) == "preview":
            self.mame_dir = os.path.dirname(self.app_dir)
            self.preview_dir = self.app_dir
        else:
            # We're running from the MAME directory
            self.mame_dir = self.app_dir
            self.preview_dir = os.path.join(self.mame_dir, "preview")
        
        # Define all required directories
        self.settings_dir = os.path.join(self.preview_dir, "settings")
        self.fonts_dir = os.path.join(self.preview_dir, "fonts")
        self.images_dir = os.path.join(self.preview_dir, "images")
        self.bezels_dir = os.path.join(self.preview_dir, "bezels")
        self.logos_dir = os.path.join(self.preview_dir, "logos")
        self.info_dir = os.path.join(self.preview_dir, "info")
        
        # Create all required directories
        os.makedirs(self.preview_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        os.makedirs(self.fonts_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.bezels_dir, exist_ok=True)
        os.makedirs(self.logos_dir, exist_ok=True)
        os.makedirs(self.info_dir, exist_ok=True)
        
        # Validate critical directories
        if not os.path.exists(self.mame_dir):
            print(f"WARNING: MAME directory not found: {self.mame_dir}")
        
        # Print path information
        print("\n--- Directory Structure ---")
        print(f"App directory: {self.app_dir}")
        print(f"MAME directory: {self.mame_dir}")
        print(f"Preview directory: {self.preview_dir}")
        print(f"Settings directory: {self.settings_dir}")
        print(f"Fonts directory: {self.fonts_dir}")
        print(f"Images directory: {self.images_dir}")
        print(f"Bezels directory: {self.bezels_dir}")
        print(f"Logos directory: {self.logos_dir}")
        print(f"Info directory: {self.info_dir}")
        print("---------------------------\n")
        
        return True
    
    def detect_screen_after_startup(self):
        """After window is shown, detect which screen it's on and set current_screen"""
        try:
            from PyQt5.QtWidgets import QDesktopWidget
            window_center = self.frameGeometry().center()
            desktop = QDesktopWidget()
            for i in range(desktop.screenCount()):
                if desktop.screenGeometry(i).contains(window_center):
                    self.current_screen = i + 1
                    print(f"[POST-DETECT] Actually on screen {self.current_screen}")
                    break
        except Exception as e:
            print(f"Failed to detect screen: {e}")

    def load_screen_setting_from_config(self):
        """Load initial screen setting from control_config_settings.json using new paths"""
        try:
            config_path = os.path.join(self.settings_dir, "control_config_settings.json")
            
            # Try legacy path if not found
            if not os.path.exists(config_path):
                legacy_path = os.path.join(self.preview_dir, "control_config_settings.json")
                if os.path.exists(legacy_path):
                    # Migrate to new location
                    try:
                        with open(legacy_path, 'r') as f:
                            settings = json.load(f)
                        
                        # Ensure settings dir exists
                        os.makedirs(self.settings_dir, exist_ok=True)
                        
                        # Save to new location
                        with open(config_path, 'w') as f:
                            json.dump(settings, f)
                        
                        print(f"Migrated control config settings from {legacy_path} to {config_path}")
                        
                        # Get screen setting
                        screen = settings.get("screen", 1)
                        return screen if screen in [1, 2] else 1
                    except Exception as e:
                        print(f"Error migrating control config settings: {e}")
            
            # Normal path loading
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    screen = data.get("screen", 1)
                    return screen if screen in [1, 2] else 1
        except Exception as e:
            print(f"Error loading screen setting: {e}")
        
        return 1

    def show_measurement_guides(self, x, y, width, height):
        """Show dynamic measurement guides with pixel distances"""
        from PyQt5.QtWidgets import QLabel, QFrame
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor, QPalette
        
        # Remove any existing measurement guides
        self.hide_measurement_guides()
        
        # Store current element position
        if not hasattr(self, 'measurement_guides'):
            self.measurement_guides = []
        
        # Get canvas dimensions
        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        
        # 1. Create vertical guide at element's X position
        v_line = QFrame(self.canvas)
        v_line.setFrameShape(QFrame.VLine)
        v_line.setFixedWidth(1)
        v_line.setGeometry(x, 0, 1, canvas_height)
        v_line.setStyleSheet("background-color: rgba(255, 100, 100, 180);")  # Red-ish
        v_line.raise_()
        v_line.show()
        self.measurement_guides.append(v_line)
        
        # 2. Create horizontal guide at element's Y position
        h_line = QFrame(self.canvas)
        h_line.setFrameShape(QFrame.HLine)
        h_line.setFixedHeight(1)
        h_line.setGeometry(0, y, canvas_width, 1)
        h_line.setStyleSheet("background-color: rgba(255, 100, 100, 180);")  # Red-ish
        h_line.raise_()
        h_line.show()
        self.measurement_guides.append(h_line)
        
        # 3. Create distance indicator for X position (from left edge)
        x_indicator = QLabel(f"{x}px", self.canvas)
        x_indicator.setStyleSheet("""
            background-color: rgba(255, 100, 100, 200);
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Arial';
            font-size: 10px;
        """)
        x_indicator.adjustSize()

        # Position horizontally centered, just BELOW the element (e.g., 10px below)
        x_indicator.move(x - x_indicator.width() // 2, y + height + 8)
        x_indicator.raise_()
        x_indicator.show()
        self.measurement_guides.append(x_indicator)

        # 4. Create distance indicator for Y position (from top edge)
        y_indicator = QLabel(f"{y}px", self.canvas)
        y_indicator.setStyleSheet("""
            background-color: rgba(255, 100, 100, 200);
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Arial';
            font-size: 10px;
        """)
        y_indicator.adjustSize()

        # Position vertically centered, just to the RIGHT of the element (e.g., 10px to the right)
        y_indicator.move(x + width + 8, y - y_indicator.height() // 2)
        y_indicator.raise_()
        y_indicator.show()
        self.measurement_guides.append(y_indicator)

        # 5. Create distance indicators from grid origin (if available)
        if hasattr(self, 'grid_x_start') and hasattr(self, 'grid_y_start'):
            x_offset = x - self.grid_x_start
            y_offset = y - self.grid_y_start
            
            if x_offset != 0:  # Only show if there's an actual offset
                offset_x_indicator = QLabel(f"Offset: {x_offset}px", self.canvas)
                offset_x_indicator.setStyleSheet("""
                    background-color: rgba(100, 100, 255, 200);
                    color: white;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-family: 'Arial';
                    font-size: 10px;
                """)
                offset_x_indicator.adjustSize()
                offset_x_indicator.move(self.grid_x_start + x_offset//2 - offset_x_indicator.width()//2, 30)
                offset_x_indicator.raise_()
                offset_x_indicator.show()
                self.measurement_guides.append(offset_x_indicator)
            
            if y_offset != 0:  # Only show if there's an actual offset
                offset_y_indicator = QLabel(f"Offset: {y_offset}px", self.canvas)
                offset_y_indicator.setStyleSheet("""
                    background-color: rgba(100, 100, 255, 200);
                    color: white;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-family: 'Arial';
                    font-size: 10px;
                """)
                offset_y_indicator.adjustSize()
                offset_y_indicator.move(30, self.grid_y_start + y_offset//2 - offset_y_indicator.height()//2)
                offset_y_indicator.raise_()
                offset_y_indicator.show()
                self.measurement_guides.append(offset_y_indicator)

    def hide_measurement_guides(self):
        """Hide all measurement guides"""
        if hasattr(self, 'measurement_guides'):
            for guide in self.measurement_guides:
                try:
                    if guide and not sip.isdeleted(guide):
                        guide.deleteLater()
                except Exception as e:
                    print(f"Warning: Failed to delete guide: {e}")
            self.measurement_guides = []

    def enhance_preview_window_init(self):
        """Call this in PreviewWindow.__init__ after setting up controls"""
        try:
            # Load any saved settings
            if hasattr(self, 'load_grid_settings'):
                self.load_grid_settings()
            if hasattr(self, 'load_snapping_settings'):
                self.load_snapping_settings()
            
            # ONLY add the shortcut text if NOT in clean mode
            if not hasattr(self, 'clean_mode') or not self.clean_mode:
                from PyQt5.QtWidgets import QLabel
                
                try:
                    self.shortcuts_label = QLabel("Hold Shift to temporarily disable snapping", self)
                    self.shortcuts_label.setStyleSheet("""
                        background-color: rgba(0, 0, 0, 180);
                        color: white;
                        padding: 5px;
                        border-radius: 3px;
                    """)
                    self.shortcuts_label.adjustSize()
                    self.shortcuts_label.move(10, self.height() - self.shortcuts_label.height() - 10)
                    self.shortcuts_label.show()
                    
                    # Hide after a delay
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(5000, lambda: self.shortcuts_label.hide())
                except Exception as e:
                    print(f"Error creating shortcuts label: {e}")
        except Exception as e:
            print(f"Error in enhance_preview_window_init: {e}")
    
    # 1. Add these properties to PreviewWindow's initialization or setup_alignment_features method
    def setup_snapping_controls(self):
        """Initialize snapping control settings with robust error handling"""
        try:
            # Default snapping settings
            print(f"Has bottom_row: {hasattr(self, 'bottom_row')}")
            print("Setting up snapping controls")
            
            self.snapping_enabled = True
            self.snap_distance = 15
            self.snap_to_grid = True
            self.snap_to_screen_center = True
            self.snap_to_controls = True
            self.snap_to_logo = True
            
            # Load any saved snapping settings
            if hasattr(self, 'load_snapping_settings'):
                try:
                    self.load_snapping_settings()
                except Exception as e:
                    print(f"Error loading snapping settings: {e}")
            
            # Only add the button if bottom_row exists and snap_button doesn't
            if hasattr(self, 'bottom_row') and not hasattr(self, 'snap_button'):
                try:
                    from PyQt5.QtWidgets import QPushButton
                    
                    button_style = """
                        QPushButton {
                            background-color: #404050;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            padding: 6px 10px;
                            font-weight: bold;
                            font-family: 'Segoe UI', Arial, sans-serif;
                            font-size: 12px;
                            min-width: 80px;
                        }
                        QPushButton:hover {
                            background-color: #555565;
                        }
                        QPushButton:pressed {
                            background-color: #303040;
                        }
                    """
                    
                    self.snap_button = QPushButton("Disable Snap" if self.snapping_enabled else "Enable Snap")
                    self.snap_button.clicked.connect(self.toggle_snapping)
                    self.snap_button.setStyleSheet(button_style)
                    self.bottom_row.addWidget(self.snap_button)
                    
                    print(f"Snap button created and added to layout: {self.snap_button.text()}")
                    
                    # Add a button for snapping settings
                    self.snap_settings_button = QPushButton("Snap Settings")
                    self.snap_settings_button.clicked.connect(self.show_snapping_settings)
                    self.snap_settings_button.setStyleSheet(button_style)
                    self.bottom_row.addWidget(self.snap_settings_button)
                except Exception as e:
                    print(f"Error creating snap buttons: {e}")
            else:
                print(f"Not creating snap buttons - bottom_row exists: {hasattr(self, 'bottom_row')}, snap_button exists: {hasattr(self, 'snap_button')}")
        except Exception as e:
            print(f"Error in setup_snapping_controls: {e}")
            import traceback
            traceback.print_exc()

    def toggle_snapping(self):
        """Toggle snapping with direct action button text"""
        # Check if snapping_enabled exists, if not initialize it
        if not hasattr(self, 'snapping_enabled'):
            self.snapping_enabled = True  # Default to enabled
        
        # Toggle the state
        self.snapping_enabled = not self.snapping_enabled
        
        # Update button text to show NEXT action (not current state)
        if hasattr(self, 'snap_button'):
            self.snap_button.setText("Enable Snap" if not self.snapping_enabled else "Disable Snap")
        
        # Save the setting
        self.save_snapping_settings()
        
        print(f"Snapping {'enabled' if self.snapping_enabled else 'disabled'}")

    def save_snapping_settings(self):
        """Save snapping settings to file"""
        try:
            import os
            import json
            
            # Create preview directory if it doesn't exist
            preview_dir = os.path.join(self.mame_dir, "preview")
            os.makedirs(preview_dir, exist_ok=True)
            
            # Create settings object with default values for missing attributes
            settings = {
                "snapping_enabled": getattr(self, 'snapping_enabled', True),
                "snap_distance": getattr(self, 'snap_distance', 15),  # Default to 15 if not set
                "snap_to_grid": getattr(self, 'snap_to_grid', True),
                "snap_to_screen_center": getattr(self, 'snap_to_screen_center', True), 
                "snap_to_controls": getattr(self, 'snap_to_controls', True),
                "snap_to_logo": getattr(self, 'snap_to_logo', True)
            }
            
            # Also initialize these attributes on the object so they're available next time
            for attr, value in settings.items():
                setattr(self, attr, value)
            
            # Save to global settings file
            settings_file = os.path.join(preview_dir, "snapping_settings.json")
            with open(settings_file, 'w') as f:
                json.dump(settings, f)
            
            print(f"Saved snapping settings: {settings}")
            return True
        except Exception as e:
            print(f"Error saving snapping settings: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_snapping_settings(self):
        """Load snapping settings from file"""
        try:
            import os
            import json
            
            # Path to settings file
            preview_dir = os.path.join(self.mame_dir, "preview")
            settings_file = os.path.join(preview_dir, "snapping_settings.json")
            
            # Check if file exists
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                
                # Apply settings
                self.snapping_enabled = settings.get("snapping_enabled", True)
                self.snap_distance = settings.get("snap_distance", 15)
                self.snap_to_grid = settings.get("snap_to_grid", True)
                self.snap_to_screen_center = settings.get("snap_to_screen_center", True)
                self.snap_to_controls = settings.get("snap_to_controls", True)
                self.snap_to_logo = settings.get("snap_to_logo", True)
                
                print(f"Loaded snapping settings from {settings_file}")
                return True
        except Exception as e:
            print(f"Error loading snapping settings: {e}")
            import traceback
            traceback.print_exc()
        
        return False

    # 3. Add a Snapping Settings dialog
    def show_snapping_settings(self):
        """Show dialog for snapping settings"""
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                    QPushButton, QSpinBox, QCheckBox, QGroupBox)
        
        class SnappingSettingsDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Snapping Settings")
                self.resize(350, 300)
                
                # Store reference to preview window
                self.preview = parent
                
                layout = QVBoxLayout(self)
                
                # Main toggle
                self.enable_snap = QCheckBox("Enable Snapping")
                self.enable_snap.setChecked(parent.snapping_enabled)
                layout.addWidget(self.enable_snap)
                
                # Snap distance
                distance_layout = QHBoxLayout()
                distance_label = QLabel("Snap Distance (pixels):")
                self.distance_spin = QSpinBox()
                self.distance_spin.setRange(1, 30)
                self.distance_spin.setValue(parent.snap_distance)
                self.distance_spin.setToolTip("Distance in pixels where snapping activates")
                distance_layout.addWidget(distance_label)
                distance_layout.addWidget(self.distance_spin)
                layout.addLayout(distance_layout)
                
                # Snap types group
                snap_types_group = QGroupBox("Snap Types")
                snap_types_layout = QVBoxLayout(snap_types_group)
                
                self.snap_to_grid = QCheckBox("Snap to Grid")
                self.snap_to_grid.setChecked(parent.snap_to_grid)
                snap_types_layout.addWidget(self.snap_to_grid)
                
                self.snap_to_screen_center = QCheckBox("Snap to Screen Center")
                self.snap_to_screen_center.setChecked(parent.snap_to_screen_center)
                snap_types_layout.addWidget(self.snap_to_screen_center)
                
                self.snap_to_controls = QCheckBox("Snap to Other Controls")
                self.snap_to_controls.setChecked(parent.snap_to_controls)
                snap_types_layout.addWidget(self.snap_to_controls)
                
                self.snap_to_logo = QCheckBox("Snap to Logo")
                self.snap_to_logo.setChecked(parent.snap_to_logo)
                snap_types_layout.addWidget(self.snap_to_logo)
                
                layout.addWidget(snap_types_group)
                
                # Buttons
                button_layout = QHBoxLayout()
                
                apply_button = QPushButton("Apply")
                apply_button.clicked.connect(self.apply_settings)
                
                ok_button = QPushButton("OK")
                ok_button.clicked.connect(self.accept_settings)
                
                cancel_button = QPushButton("Cancel")
                cancel_button.clicked.connect(self.reject)
                
                button_layout.addWidget(apply_button)
                button_layout.addStretch()
                button_layout.addWidget(ok_button)
                button_layout.addWidget(cancel_button)
                
                layout.addLayout(button_layout)
            
            def apply_settings(self):
                """Apply settings to preview window"""
                self.preview.snapping_enabled = self.enable_snap.isChecked()
                self.preview.snap_distance = self.distance_spin.value()
                self.preview.snap_to_grid = self.snap_to_grid.isChecked()
                self.preview.snap_to_screen_center = self.snap_to_screen_center.isChecked()
                self.preview.snap_to_controls = self.snap_to_controls.isChecked()
                self.preview.snap_to_logo = self.snap_to_logo.isChecked()
                
                # Update snap button text
                if hasattr(self.preview, 'snap_button'):
                    self.preview.snap_button.setText(
                        "Disable Snap" if self.preview.snapping_enabled else "Enable Snap"
                    )
                
                # Save settings
                self.preview.save_snapping_settings()
            
            def accept_settings(self):
                """Apply settings and close dialog"""
                self.apply_settings()
                self.accept()
        
        # Create and show the dialog
        dialog = SnappingSettingsDialog(self)
        dialog.exec_()
    
    def load_grid_settings(self):
        """Load grid settings from file"""
        try:
            import os
            import json
            
            # Path to settings file
            preview_dir = os.path.join(self.mame_dir, "preview")
            settings_file = os.path.join(preview_dir, "grid_settings.json")
            
            # Check if file exists
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                
                # Apply settings
                self.grid_x_start = settings.get("grid_x_start", 200)
                self.grid_y_start = settings.get("grid_y_start", 100)
                self.grid_x_step = settings.get("grid_x_step", 300)
                self.grid_y_step = settings.get("grid_y_step", 60)
                self.grid_columns = settings.get("grid_columns", 3)
                self.grid_rows = settings.get("grid_rows", 8)
                
                print(f"Loaded grid settings from {settings_file}")
                return True
        except Exception as e:
            print(f"Error loading grid settings: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    # Add this method to PreviewWindow class
    def setup_alignment_features(self):
        """Set up alignment features in the PreviewWindow"""
        # Initialize the alignment grid system
        self.initialize_alignment_grid()
        
        # Add the grid toggle button to the floating control panel
        if hasattr(self, 'bottom_row') and not hasattr(self, 'grid_button'):
            from PyQt5.QtWidgets import QPushButton
            from PyQt5.QtCore import Qt
            
            button_style = """
                QPushButton {
                    background-color: #404050;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 10px;
                    font-weight: bold;
                    font-size: 12px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #555565;
                }
                QPushButton:pressed {
                    background-color: #303040;
                }
            """
            
            self.grid_button = QPushButton("Show Grid")
            self.grid_button.clicked.connect(self.toggle_alignment_grid)
            self.grid_button.setStyleSheet(button_style)
            self.bottom_row.addWidget(self.grid_button)

    def initialize_alignment_grid(self):
        """Initialize the alignment grid system"""
        self.alignment_grid_visible = False
        self.grid_x_start = 200  # Default first column X-position
        self.grid_x_step = 300   # Default X-spacing between columns
        self.grid_y_start = 100  # Default first row Y-position
        self.grid_y_step = 60    # Default Y-spacing between rows
        self.grid_columns = 3    # Number of columns in grid
        self.grid_rows = 8       # Number of rows in grid
        
        # Create a toggle button for the grid if we have a button frame
        if hasattr(self, 'bottom_row'):
            from PyQt5.QtWidgets import QPushButton
            
            button_style = """
                QPushButton {
                    background-color: #404050;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 10px;
                    font-weight: bold;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 12px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #555565;
                }
                QPushButton:pressed {
                    background-color: #303040;
                }
            """
            
            if not hasattr(self, 'grid_button'):
                self.grid_button = QPushButton("Show Grid")
                self.grid_button.clicked.connect(self.toggle_alignment_grid)
                self.grid_button.setStyleSheet(button_style)
                self.bottom_row.addWidget(self.grid_button)

    def toggle_alignment_grid(self):
        """Toggle the alignment grid visibility"""
        self.alignment_grid_visible = not self.alignment_grid_visible
        
        if self.alignment_grid_visible:
            self.show_alignment_grid()
            # Only try to update the button text if the button exists
            if hasattr(self, 'grid_button'):
                self.grid_button.setText("Hide Grid")
        else:
            self.hide_alignment_grid()
            # Only try to update the button text if the button exists
            if hasattr(self, 'grid_button'):
                self.grid_button.setText("Show Grid")

    def show_alignment_grid(self):
        """Show the alignment grid"""
        if not hasattr(self, 'grid_lines'):
            self.grid_lines = []
        
        # Hide any existing grid
        self.hide_alignment_grid()
        
        from PyQt5.QtWidgets import QFrame, QLabel
        from PyQt5.QtGui import QPalette, QColor
        
        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        
        # Create vertical grid lines (columns)
        # Vertical grid lines (columns)
        num_columns = (canvas_width - self.grid_x_start) // self.grid_x_step + 1
        for col in range(num_columns):
            x = self.grid_x_start + col * self.grid_x_step
            line = QFrame(self.canvas)
            line.setFrameShape(QFrame.VLine)
            line.setFixedWidth(1)
            line.setGeometry(x, 0, 1, canvas_height)
            
            # Style for grid lines - more subtle than alignment guides
            line.setStyleSheet("background-color: rgba(0, 180, 180, 120);")
            
            line.show()
            self.grid_lines.append(line)
            
            # Add column number label
            col_label = QLabel(f"{x}px", self.canvas)
            col_label.setStyleSheet("color: rgba(0, 180, 180, 180); background: transparent;")
            col_label.move(x + 5, 10)
            col_label.show()
            self.grid_lines.append(col_label)
        
        # Create horizontal grid lines (rows)
        num_rows = (canvas_height - self.grid_y_start) // self.grid_y_step + 1
        for row in range(num_rows):
            y = self.grid_y_start + row * self.grid_y_step
            line = QFrame(self.canvas)
            line.setFrameShape(QFrame.HLine)
            line.setFixedHeight(1)
            line.setGeometry(0, y, canvas_width, 1)
            
            # Style for grid lines
            line.setStyleSheet("background-color: rgba(0, 180, 180, 120);")
            
            line.show()
            self.grid_lines.append(line)
            
            # Add row number label
            row_label = QLabel(f"{y}px", self.canvas)
            row_label.setStyleSheet("color: rgba(0, 180, 180, 180); background: transparent;")
            row_label.move(10, y + 5)
            row_label.show()
            self.grid_lines.append(row_label)

    def hide_alignment_grid(self):
        """Hide the alignment grid"""
        if hasattr(self, 'grid_lines'):
            for line in self.grid_lines:
                line.deleteLater()
            self.grid_lines = []
    
    # 3. Update show_alignment_guides method to not reference shadow elements

    def show_alignment_guides(self, guide_lines):
        """Show alignment guide lines with enhanced visibility, no shadow references"""
        # Remove any existing guide lines
        self.hide_alignment_guides()
        
        # Create guide lines
        from PyQt5.QtWidgets import QFrame
        from PyQt5.QtGui import QPalette, QColor
        
        self.guide_labels = []
        
        for x1, y1, x2, y2 in guide_lines:
            guide = QFrame(self.canvas)
            
            # Ensure all values are integers
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            
            # Set line style
            if x1 == x2:  # Vertical line
                guide.setFrameShape(QFrame.VLine)
                guide.setFixedWidth(2)  # Make line thicker
            else:  # Horizontal line
                guide.setFrameShape(QFrame.HLine)
                guide.setFixedHeight(2)  # Make line thicker
            
            guide.setFrameShadow(QFrame.Plain)
            guide.setLineWidth(2)
            
            # Set bright color for visibility
            palette = QPalette()
            palette.setColor(QPalette.WindowText, QColor(0, 255, 255))  # Cyan color
            guide.setPalette(palette)
            
            # Add a more visible style
            guide.setStyleSheet("background-color: rgba(0, 255, 255, 180);")  # Semi-transparent cyan
            
            # Position and size the guide
            if x1 == x2:  # Vertical line
                guide.setGeometry(x1-1, y1, 2, y2-y1)  # Center line on position
            else:  # Horizontal line
                guide.setGeometry(x1, y1-1, x2-x1, 2)  # Center line on position
            
            # Make sure guide is on top
            guide.raise_()
            guide.show()
            self.guide_labels.append(guide)
        
        # Set timer to auto-hide guides after a short period
        from PyQt5.QtCore import QTimer
        if hasattr(self, 'guide_timer'):
            self.guide_timer.stop()
        self.guide_timer = QTimer(self)
        self.guide_timer.setSingleShot(True)
        self.guide_timer.timeout.connect(self.hide_alignment_guides)
        self.guide_timer.start(1500)  # Hide after 1.5 seconds (increased from 1s)

    def hide_alignment_guides(self):
        """Hide alignment guide lines"""
        if hasattr(self, 'guide_labels'):
            for guide in self.guide_labels:
                try:
                    guide.deleteLater()
                except:
                    pass  # Ignore errors if the guide is already deleted
            self.guide_labels = []
    
    def toggle_button_prefixes(self):
        """Toggle the visibility of button prefixes for all controls"""
        # Toggle the setting
        show_prefixes = not self.text_settings.get("show_button_prefix", True)
        self.text_settings["show_button_prefix"] = show_prefixes
        
        # Update all control labels
        for control_name, control_data in self.control_labels.items():
            if 'label' in control_data and control_data['label']:
                label = control_data['label']
                action_text = control_data['action']
                prefix = control_data.get('prefix', '')
                
                # Apply uppercase if enabled
                if self.text_settings.get("use_uppercase", False):
                    action_text = action_text.upper()
                
                # Set label text based on prefix setting
                if show_prefixes and prefix:
                    label.setText(f"{prefix}: {action_text}")
                else:
                    label.setText(action_text)
        
        # Update button text
        if hasattr(self, 'prefix_button'):
            self.prefix_button.setText("Hide Prefixes" if show_prefixes else "Show Prefixes")
        
        # Save the updated setting to file
        try:
            preview_dir = os.path.join(self.mame_dir, "preview")
            os.makedirs(preview_dir, exist_ok=True)
            
            # Try to load existing settings first
            settings_file = os.path.join(preview_dir, "global_text_settings.json")
            current_settings = {}
            
            if os.path.exists(settings_file):
                try:
                    with open(settings_file, 'r') as f:
                        current_settings = json.load(f)
                except:
                    pass  # Use empty settings if file can't be read
            
            # Update with our new setting
            current_settings["show_button_prefix"] = show_prefixes
            
            # Save back to file
            with open(settings_file, 'w') as f:
                json.dump(current_settings, f)
            
            print(f"Saved button prefix setting: {show_prefixes}")
        except Exception as e:
            print(f"Error saving button prefix setting: {e}")
            import traceback
            traceback.print_exc()
        
        # Force a canvas update
        self.canvas.update()
        
        return show_prefixes
    
    # Fix 3: Enhanced load_and_register_fonts with better debugging
    def load_and_register_fonts(self):
        """Load and register fonts from settings at startup with improved error detection"""
        from PyQt5.QtGui import QFontDatabase, QFont, QFontInfo
        
        print("\n=== LOADING FONTS ===")
        # Get requested font from settings
        font_family = self.text_settings.get("font_family", "Arial")
        font_size = self.text_settings.get("font_size", 28)
        bold_strength = self.text_settings.get("bold_strength", 2)
        
        print(f"Target font from settings: {font_family}")
        
        # 1. First try to load from custom fonts directory in preview/fonts
        font_found = False
        exact_family_name = None
        
        if hasattr(self, 'fonts_dir') and os.path.exists(self.fonts_dir):
            print(f"Scanning fonts directory: {self.fonts_dir}")
            for filename in os.listdir(self.fonts_dir):
                if filename.lower().endswith(('.ttf', '.otf')):
                    # Check if filename matches our target font
                    base_name = os.path.splitext(filename)[0].lower()
                    name_match = (
                        base_name == font_family.lower() or 
                        font_family.lower() in base_name or 
                        base_name in font_family.lower()
                    )
                    
                    if name_match:
                        font_path = os.path.join(self.fonts_dir, filename)
                        print(f"MATCH FOUND! Loading font: {font_path}")
                        
                        # Register the font
                        font_id = QFontDatabase.addApplicationFont(font_path)
                        if font_id >= 0:
                            families = QFontDatabase.applicationFontFamilies(font_id)
                            if families and len(families) > 0:
                                exact_family_name = families[0]
                                print(f"*** FONT LOADED SUCCESSFULLY: {exact_family_name} ***")
                                font_found = True
                                break
        
        # 2. If no custom font found, try system fonts
        if not font_found:
            # For system fonts, just use the family name directly
            exact_family_name = font_family
            print(f"Using system font: {exact_family_name}")
        
        # 3. Store the font information
        self.font_name = exact_family_name or font_family
        
        # 4. Create the actual font object
        self.current_font = QFont(self.font_name, font_size)
        self.current_font.setBold(bold_strength > 0)
        
        # 5. Force exact matching - this is critical
        self.current_font.setStyleStrategy(QFont.PreferMatch)
        
        # Print font diagnostic info
        info = QFontInfo(self.current_font)
        print(f"Created font object: {self.font_name}")
        print(f"Weight: {self.current_font.weight()}, Size: {self.current_font.pointSize()}")
        print(f"Actual family being used: {info.family()}")
        
        # Debug whether there's a font substitution
        if info.family() != self.font_name:
            print(f"WARNING: FONT SUBSTITUTION DETECTED! Requested: {self.font_name}, Using: {info.family()}")
        else:
            print(f"PERFECT MATCH: {self.font_name} is being used exactly as requested")
        
        print("=== FONT LOADING COMPLETE ===\n")
        
        # Apply the font to existing controls if any
        self.apply_current_font_to_controls()
        
        return self.current_font  # Return the created font for reference

    def apply_current_font_to_controls(self):
        """Apply the current font to all control labels and properly resize them"""
        if not hasattr(self, 'current_font'):
            print("No current font to apply")
            return
                
        if not hasattr(self, 'control_labels'):
            print("No controls to apply font to")
            return
                
        print(f"Applying font {self.current_font.family()} to {len(self.control_labels)} controls")
        for control_name, control_data in self.control_labels.items():
            if 'label' in control_data and control_data['label']:
                label = control_data['label']
                    
                # Apply the font
                label.setFont(self.current_font)
                    
                # CRITICAL: Adjust size to match new font
                label.adjustSize()
                    
                # Make sure we don't have any size restrictions
                label.setMinimumSize(0, 0)
                label.setMaximumSize(16777215, 16777215)  # Qt's QWIDGETSIZE_MAX
                    
                # Also reset size policy to ensure it can grow
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        print("Font applied and labels resized")
    
    def init_fonts(self):
        """Initialize and preload fonts at startup to ensure they're available throughout the session"""
        from PyQt5.QtGui import QFontDatabase, QFont
        
        print("\n--- INITIALIZING FONTS ---")
        # Get requested font from settings
        font_family = self.text_settings.get("font_family", "Arial")
        font_size = self.text_settings.get("font_size", 28)
        
        # 1. First try to load the exact font file if it's a known system font
        system_font_map = {
            "Times New Roman": "times.ttf",
            "Impact": "impact.ttf",
            "Courier New": "cour.ttf",
            "Comic Sans MS": "comic.ttf",
            "Georgia": "georgia.ttf",
            "Arial": "arial.ttf",
            "Verdana": "verdana.ttf",
            "Tahoma": "tahoma.ttf",
            "Calibri": "calibri.ttf"
        }
        
        # Store the actual font family name loaded
        self.initialized_font_family = None
        
        if font_family in system_font_map:
            font_file = system_font_map[font_family]
            font_path = os.path.join("C:\\Windows\\Fonts", font_file)
            
            if os.path.exists(font_path):
                print(f"Preloading system font: {font_path}")
                font_id = QFontDatabase.addApplicationFont(font_path)
                
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        self.initialized_font_family = families[0]
                        print(f"System font loaded and registered as: {self.initialized_font_family}")
        
        # 2. Check for custom fonts if we couldn't load a system font
        if not self.initialized_font_family:
            fonts_dir = os.path.join(self.mame_dir, "preview", "fonts")
            if os.path.exists(fonts_dir):
                # Try to find a matching font file
                for filename in os.listdir(fonts_dir):
                    if filename.lower().endswith(('.ttf', '.otf')):
                        base_name = os.path.splitext(filename)[0]
                        
                        # Check if this might be the font we're looking for
                        if (base_name.lower() == font_family.lower() or
                            font_family.lower() in base_name.lower()):
                            
                            font_path = os.path.join(fonts_dir, filename)
                            print(f"Trying to load custom font: {font_path}")
                            
                            font_id = QFontDatabase.addApplicationFont(font_path)
                            if font_id >= 0:
                                families = QFontDatabase.applicationFontFamilies(font_id)
                                if families:
                                    self.initialized_font_family = families[0]
                                    print(f"Custom font loaded and registered as: {self.initialized_font_family}")
                                    break
        
        # Create a proper QFont with the exact family name
        if self.initialized_font_family:
            # Store the font for future use
            self.initialized_font = QFont(self.initialized_font_family, font_size)
            self.initialized_font.setBold(self.text_settings.get("bold_strength", 2) > 0)
            self.initialized_font.setStyleStrategy(QFont.PreferMatch)
            
            print(f"Initialized font: {self.initialized_font_family} at size {font_size}")
        else:
            print(f"Could not initialize font: {font_family}. Will fallback to system handling.")
        
        print("--- FONT INITIALIZATION COMPLETE ---\n")

    # 10. Remove the shadow toggle button from UI
    def create_floating_button_frame(self):
        """Create clean, simple floating button frame without shadow toggle"""
        from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from PyQt5.QtCore import Qt, QPoint, QTimer
        
        # Create a floating button frame
        self.button_frame = QFrame(self)
        
        # Simple, clean styling with no border
        self.button_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 45, 200);
                border-radius: 8px;
                border: none;
            }
        """)
        
        # Use a vertical layout to contain all elements
        main_layout = QVBoxLayout(self.button_frame)
        main_layout.setContentsMargins(10, 5, 10, 10)
        main_layout.setSpacing(5)
        
        # Add a visible drag handle at the top - THIS IS THE DESIGNATED DRAG AREA
        handle_layout = QHBoxLayout()
        handle_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create a drag handle label with grip dots
        self.drag_handle = QLabel("• • •")
        self.drag_handle.setStyleSheet("""
            color: #888888;
            font-size: 14px;
            font-weight: bold;
            padding: 0px;
            background-color: rgba(60, 60, 65, 100);
            border-radius: 4px;
        """)
        self.drag_handle.setAlignment(Qt.AlignCenter)
        self.drag_handle.setCursor(Qt.OpenHandCursor)
        self.drag_handle.setFixedHeight(20)
        handle_layout.addWidget(self.drag_handle)
        
        # Add the handle to the main layout
        main_layout.addLayout(handle_layout)
        
        # Create two horizontal rows for buttons
        self.top_row = QHBoxLayout()
        self.bottom_row = QHBoxLayout()
        
        # Add rows to main layout
        main_layout.addLayout(self.top_row)
        main_layout.addLayout(self.bottom_row)
        
        # Clean, Tkinter-like button style
        button_style = """
            QPushButton {
                background-color: #404050;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
                font-weight: bold;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #555565;
            }
            QPushButton:pressed {
                background-color: #303040;
            }
        """
        
        # First row buttons
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.close_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.close_button)
        
        self.global_save_button = QPushButton("Global Save")
        self.global_save_button.clicked.connect(lambda: self.save_positions(is_global=True))
        self.global_save_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.global_save_button)
        
        self.rom_save_button = QPushButton("ROM Save")
        self.rom_save_button.clicked.connect(lambda: self.save_positions(is_global=False))
        self.rom_save_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.rom_save_button)
        
        self.text_settings_button = QPushButton("Text Settings")
        self.text_settings_button.clicked.connect(self.show_text_settings)
        self.text_settings_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.text_settings_button)
        
        self.xinput_controls_button = QPushButton("Show All XInput")
        self.xinput_controls_button.clicked.connect(self.toggle_xinput_controls)
        self.xinput_controls_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.xinput_controls_button)

        # Second row buttons
        self.toggle_texts_button = QPushButton("Hide Texts")
        self.toggle_texts_button.clicked.connect(self.toggle_texts)
        self.toggle_texts_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.toggle_texts_button)
        
        self.joystick_button = QPushButton("Joystick")
        self.joystick_button.clicked.connect(self.toggle_joystick_controls)
        self.joystick_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.joystick_button)
        
        # Add button prefix toggle button
        prefix_text = "Hide Prefixes" if self.text_settings.get("show_button_prefix", True) else "Show Prefixes"
        self.prefix_button = QPushButton(prefix_text)
        self.prefix_button.clicked.connect(self.toggle_button_prefixes)
        self.prefix_button.setStyleSheet(button_style)
        self.prefix_button.setToolTip("Toggle button prefixes (e.g., A: Jump)")
        self.bottom_row.addWidget(self.prefix_button)
        
        # Logo toggle
        logo_text = "Hide Logo" if self.logo_visible else "Show Logo"
        self.logo_button = QPushButton(logo_text)
        self.logo_button.clicked.connect(self.toggle_logo)
        self.logo_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.logo_button)
        
        self.center_logo_button = QPushButton("Center Logo")
        self.center_logo_button.clicked.connect(self.center_logo)
        self.center_logo_button.setStyleSheet(button_style)
        self.center_logo_button.setToolTip("Center logo in the canvas") 
        self.bottom_row.addWidget(self.center_logo_button)
        
        # Screen toggle with number indicator
        self.screen_button = QPushButton(f"Screen {getattr(self, 'current_screen', 1)}")
        self.screen_button.clicked.connect(self.toggle_screen)
        self.screen_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.screen_button)
        
        # Add save image button
        self.save_image_button = QPushButton("Save Image")
        self.save_image_button.clicked.connect(self.save_image)
        self.save_image_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.save_image_button)
        
        # IMPROVED: Add dragging functionality to the drag handle only
        self.drag_handle.mousePressEvent = self.handle_drag_press
        self.drag_handle.mouseMoveEvent = self.handle_drag_move
        self.drag_handle.mouseReleaseEvent = self.handle_drag_release
        
        # Store a flag to track frame dragging state
        self.button_dragging = False
        self.button_drag_pos = None
        
        # Initialize snapping settings from saved values
        self.snapping_enabled = True  # Default value if no settings found
        self.snap_distance = 15
        self.snap_to_grid = True
        self.snap_to_screen_center = True
        self.snap_to_controls = True
        self.snap_to_logo = True

        # Load any saved snapping settings
        try:
            self.load_snapping_settings()
            print(f"Loaded snapping settings, enabled = {self.snapping_enabled}")
        except Exception as e:
            print(f"Error loading snapping settings: {e}")
            # Keep using defaults

        # Now create the snap button with text based on loaded settings
        self.snap_button = QPushButton("Disable Snap" if self.snapping_enabled else "Enable Snap", self)
        self.snap_button.clicked.connect(self.toggle_snapping)
        self.snap_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.snap_button)

        # Add Grid Toggle Button
        self.grid_button = QPushButton("Show Grid")
        self.grid_button.clicked.connect(self.toggle_alignment_grid)
        self.grid_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.grid_button)

        # Determine button frame position
        self.position_button_frame()
        
        # Update logo button text after a short delay to ensure settings are loaded
        QTimer.singleShot(100, self.update_center_logo_button_text)
        
        # Show button frame
        self.button_frame.show()

    # 2. Now, update the drag handle event handlers
    # Fix the drag handling to prevent jittering
    def handle_drag_press(self, event):
        """Handle mouse press on the drag handle with smooth drag initiation"""
        from PyQt5.QtCore import Qt
        
        if event.button() == Qt.LeftButton:
            self.button_dragging = True
            # IMPORTANT: Store the global position of the mouse when dragging starts
            self.drag_start_global_pos = event.globalPos()
            # Store the initial position of the button frame
            self.button_frame_start_pos = self.button_frame.pos()
            self.drag_handle.setCursor(Qt.ClosedHandCursor)
            event.accept()

    def handle_drag_move(self, event):
        """Handle mouse move on the drag handle with consistent delta calculation"""
        from PyQt5.QtCore import Qt
        
        if self.button_dragging and hasattr(self, 'drag_start_global_pos'):
            # Calculate movement delta from the initial global position
            # This ensures consistent movement without jittering
            delta = event.globalPos() - self.drag_start_global_pos
            
            # Apply delta to the original frame position
            new_pos = self.button_frame_start_pos + delta
            
            # Keep within window bounds
            new_pos.setX(max(0, min(self.width() - self.button_frame.width(), new_pos.x())))
            new_pos.setY(max(0, min(self.height() - self.button_frame.height(), new_pos.y())))
            
            # Move the frame
            self.button_frame.move(new_pos)
            event.accept()

    def handle_drag_release(self, event):
        """Handle mouse release on the drag handle"""
        from PyQt5.QtCore import Qt
        
        if event.button() == Qt.LeftButton:
            self.button_dragging = False
            self.drag_handle.setCursor(Qt.OpenHandCursor)
            # Clear the global position reference
            if hasattr(self, 'drag_start_global_pos'):
                delattr(self, 'drag_start_global_pos')
            event.accept()
    
    '''def button_frame_mouse_press(self, event):
        """Handle mouse press on button frame for dragging with improved button handling"""
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication
        
        # Check if we're clicking on a button (or other interactive widget)
        child_widget = self.button_frame.childAt(event.pos())
        
        # If we're clicking on a button, let the button handle the event
        if child_widget and child_widget.__class__.__name__ in ['QPushButton', 'QCheckBox', 'QRadioButton', 'QSlider', 'QSpinBox']:
            # Ignore the event in the frame to let it propagate to the button
            event.ignore()
            return
        
        # Only start dragging if left button is pressed on the frame itself
        if event.button() == Qt.LeftButton:
            # Store the click position and start dragging
            self.button_dragging = True
            self.button_drag_pos = event.pos()
            self.button_frame.setCursor(Qt.ClosedHandCursor)
            
            # Accept the event to prevent further propagation
            event.accept()

    def button_frame_mouse_move(self, event):
        """Handle mouse move for button frame dragging with improved handling"""
        from PyQt5.QtCore import Qt, QPoint
        
        # Only process if we're in dragging mode
        if not hasattr(self, 'button_dragging') or not self.button_dragging or not hasattr(self, 'button_drag_pos'):
            return
        
        # Calculate the new position
        delta = event.pos() - self.button_drag_pos
        new_pos = self.button_frame.pos() + delta
        
        # Keep within window bounds
        new_pos.setX(max(0, min(self.width() - self.button_frame.width(), new_pos.x())))
        new_pos.setY(max(0, min(self.height() - self.button_frame.height(), new_pos.y())))
        
        # Move the frame
        self.button_frame.move(new_pos)
        
        # Accept the event
        event.accept()

    def button_frame_mouse_release(self, event):
        """Handle mouse release to end button frame dragging with improved click handling"""
        from PyQt5.QtCore import Qt
        
        # Only process if we're in dragging mode and left button was released
        if hasattr(self, 'button_dragging') and self.button_dragging and event.button() == Qt.LeftButton:
            # End dragging mode
            self.button_dragging = False
            self.button_frame.setCursor(Qt.OpenHandCursor)
            
            # Only accept if we actually dragged
            if hasattr(self, 'button_drag_start_pos') and hasattr(self, 'button_drag_pos'):
                # Check if we actually dragged or just clicked
                start_pos = getattr(self, 'button_drag_start_pos', event.pos())
                drag_distance = (event.pos() - start_pos).manhattanLength() if hasattr(start_pos, 'manhattanLength') else 0
                
                # If minimal movement, treat as click and let it propagate to children
                if drag_distance < 5:  # Small threshold for movement
                    event.ignore()
                else:
                    event.accept()
            else:
                # Accept the event if no start position info
                event.accept()'''

    def position_button_frame(self, initial_position=None):
        """Position the button frame with option for custom initial position"""
        if hasattr(self, 'button_frame'):
            # Calculate target width - 90% of window width, max 1000px
            target_width = int(min(1000, self.width() * 0.9))
            
            # Make sure the layout respects our width constraints
            if hasattr(self, 'main_layout'):
                self.main_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
                
            # Adjust size first to get natural height based on contents
            self.button_frame.adjustSize()
            
            # Get the natural dimensions
            natural_width = self.button_frame.width()
            button_height = self.button_frame.height()
            
            # Use the larger of calculated or natural width
            frame_width = max(natural_width, target_width)
            
            # Set fixed width AFTER getting natural size
            self.button_frame.setFixedWidth(frame_width)
            
            # If initial position is specified, use it
            if initial_position:
                x_pos, y_pos = initial_position
            else:
                # Position at bottom center, 20px from bottom
                x_pos = (self.width() - frame_width) // 2  # Center horizontally
                y_pos = self.height() - button_height - 20  # 20px from bottom
                
            # Make sure position is valid
            x_pos = max(0, min(self.width() - frame_width, x_pos))
            y_pos = max(0, min(self.height() - button_height, y_pos))
            
            # Move to position and force update
            self.button_frame.move(x_pos, y_pos)
            self.button_frame.updateGeometry()
            
            # Debug output
            print(f"Button frame positioned: {frame_width}x{button_height} at ({x_pos}, {y_pos})")
            print(f"Window size: {self.width()}x{self.height()}")

    def on_resize_with_buttons(self, event):
        """Handle resize events and reposition the button frame"""
        # Let the normal resize event happen first
        super().resizeEvent(event)
        
        # Reposition the button frame with a short delay to ensure geometry is updated
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, self.position_button_frame)
        
        # Also handle bezel resizing if needed
        if hasattr(self, 'on_resize_with_bezel'):
            self.on_resize_with_bezel(event)
    
    # Add this to the PreviewWindow class
    def ensure_bezel_state(self):
        """Ensure bezel visibility state matches settings"""
        if not hasattr(self, 'has_bezel') or not self.has_bezel:
            return
            
        # Make sure bezel is shown if it should be based on settings
        if self.bezel_visible and (not hasattr(self, 'bezel_label') or not self.bezel_label or not self.bezel_label.isVisible()):
            self.show_bezel_with_background()
            print("Ensuring bezel is visible based on settings")
            
        # Update button text
        if hasattr(self, 'bezel_button'):
            self.bezel_button.setText("Hide Bezel" if self.bezel_visible else "Show Bezel")
    
    # 12. Modify the force_resize_all_labels method to not update shadows
    def force_resize_all_labels(self):
        """Force all control labels to resize according to their content"""
        if not hasattr(self, 'control_labels'):
            return
                
        print("Force resizing all control labels")
        for control_name, control_data in self.control_labels.items():
            if 'label' in control_data and control_data['label']:
                label = control_data['label']
                    
                # Make sure we don't have size restrictions
                label.setMinimumSize(0, 0)
                label.setMaximumSize(16777215, 16777215)
                    
                # Reset size policy
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    
                # Adjust size to content
                label.adjustSize()
        
        # Force a repaint
        if hasattr(self, 'canvas'):
            self.canvas.update()
                
        print("All labels resized")

    # Replace toggle_bezel_improved to always save global settings
    def toggle_bezel_improved(self):
        """Toggle bezel visibility and save the setting globally"""
        if not self.has_bezel:
            print("No bezel available to toggle")
            return
        
        # Toggle visibility flag
        self.bezel_visible = not self.bezel_visible
        
        # Update button text
        self.bezel_button.setText("Hide Bezel" if self.bezel_visible else "Show Bezel")
        
        # Show or hide bezel
        if self.bezel_visible:
            self.show_bezel_with_background()
            print(f"Bezel visibility is now: {self.bezel_visible}")
        else:
            if hasattr(self, 'bezel_label') and self.bezel_label:
                self.bezel_label.hide()
                print("Bezel hidden")
        
        # Always raise controls to top
        self.raise_controls_above_bezel()
        
        # ALWAYS save as global settings
        self.save_bezel_settings(is_global=True)
        print(f"Saved bezel visibility ({self.bezel_visible}) to GLOBAL settings")
    
    # Add method to find bezel path
    def find_bezel_path(self, rom_name):
        """Find bezel image path for a ROM name with updated paths"""
        # Define possible locations for bezels
        possible_paths = [
            # Priority 1: First look in preview/bezels directory
            os.path.join(self.preview_dir, "bezels", f"{rom_name}.png"),
            os.path.join(self.preview_dir, "bezels", f"{rom_name}_bezel.png"),
            
            # Priority 2: Check in preview/artwork directory 
            os.path.join(self.preview_dir, "artwork", rom_name, "Bezel.png"),
            os.path.join(self.preview_dir, "artwork", rom_name, "bezel.png"),
            os.path.join(self.preview_dir, "artwork", rom_name, f"{rom_name}_bezel.png"),
            
            # Priority 3: Traditional artwork locations in MAME directory
            os.path.join(self.mame_dir, "artwork", rom_name, "Bezel.png"),
            os.path.join(self.mame_dir, "artwork", rom_name, "bezel.png"),
            os.path.join(self.mame_dir, "artwork", rom_name, f"{rom_name}_bezel.png"),
            os.path.join(self.mame_dir, "bezels", f"{rom_name}.png"),
            os.path.join(self.mame_dir, "bezels", f"{rom_name}_bezel.png"),
        ]
        
        # Check each possible path
        for path in possible_paths:
            if os.path.exists(path):
                print(f"Found bezel at: {path}")
                return path
        
        print(f"No bezel found for {rom_name}")
        return None

    # Replace the show_bezel_with_background method for better bezel display
    def show_bezel_with_background(self):
        """Display bezel while preserving background with proper layering"""
        # Find bezel path
        bezel_path = self.find_bezel_path(self.rom_name)
        if not bezel_path:
            print("Cannot show bezel: no bezel image found")
            return
        
        try:
            print("\n--- Showing bezel with proper layering ---")
            
            # Create or recreate bezel label
            if hasattr(self, 'bezel_label') and self.bezel_label:
                self.bezel_label.deleteLater()
            
            # Create a fresh bezel label on the canvas
            self.bezel_label = QLabel(self.canvas)
            
            # Load bezel image
            self.original_bezel_pixmap = QPixmap(bezel_path)
            if self.original_bezel_pixmap.isNull():
                print(f"Error loading bezel image from {bezel_path}")
                self.bezel_visible = False
                return
            
            # Resize bezel to match window while preserving aspect ratio
            window_width = self.canvas.width()
            window_height = self.canvas.height()
            
            # Scale with high quality
            bezel_pixmap = self.original_bezel_pixmap.scaled(
                window_width,
                window_height,
                Qt.KeepAspectRatio,  # Keep aspect ratio
                Qt.SmoothTransformation  # High quality scaling
            )
            
            # Store this for saving to image later
            self.bezel_pixmap = bezel_pixmap
            
            # Set up the bezel label
            self.bezel_label.setPixmap(bezel_pixmap)
            
            # Position bezel in center
            x = (window_width - bezel_pixmap.width()) // 2
            y = (window_height - bezel_pixmap.height()) // 2
            self.bezel_label.setGeometry(x, y, bezel_pixmap.width(), bezel_pixmap.height())
            
            # CRITICAL: Make bezel transparent
            self.bezel_label.setStyleSheet("background-color: transparent;")
            
            # CRITICAL LAYERING FIX: First lower the bezel behind everything
            self.bezel_label.lower()
            
            # Then, if we have a background, make sure bezel is ABOVE background but BELOW other controls
            if hasattr(self, 'bg_label') and self.bg_label:
                # Print current widget stacking info
                print(f"Background exists: {self.bg_label.isVisible()}")
                
                # First lower background to bottom
                self.bg_label.lower()
                
                # Then raise bezel above background
                self.bezel_label.stackUnder(self.bg_label)
                self.bezel_label.raise_()
                
                print("Fixed layering: Background -> Bezel -> Other elements")
            
            # Make sure the bezel is visible
            self.bezel_label.show()
            self.bezel_visible = True
            
            # Now raise all controls above bezel
            self.raise_controls_above_bezel()
            
            print(f"Bezel displayed: {bezel_pixmap.width()}x{bezel_pixmap.height()} at ({x},{y})")
            print(f"Bezel visibility is set to: {self.bezel_visible}")
            
        except Exception as e:
            print(f"Error showing bezel: {e}")
            import traceback
            traceback.print_exc()
            self.bezel_visible = False
            
    # Improved method to raise controls above bezel
    def raise_controls_above_bezel(self):
        """Ensure all controls are above the bezel with proper debug info"""
        print("\n--- Applying proper stacking order ---")
        
        if not hasattr(self, 'bezel_label') or not self.bezel_label:
            print("No bezel label exists to stack controls above")
            return
        
        # First make sure background is at the bottom
        if hasattr(self, 'bg_label') and self.bg_label:
            self.bg_label.lower()
            print("Lowered background to bottom layer")
        
        # Then place bezel above background
        self.bezel_label.lower()  # First lower it all the way down
        if hasattr(self, 'bg_label') and self.bg_label:
            self.bezel_label.stackUnder(self.bg_label)  # Then stack under background
            self.bezel_label.raise_()  # Then raise above background
            print("Positioned bezel above background")
        
        # Raise all control labels to the top
        if hasattr(self, 'control_labels'):
            for control_data in self.control_labels.values():
                if 'label' in control_data and control_data['label'] and control_data['label'].isVisible():
                    control_data['label'].raise_()
            print(f"Raised {len(self.control_labels)} control labels to top")
        
        # Raise logo if it exists (should be on top of bezel but below controls)
        if hasattr(self, 'logo_label') and self.logo_label and self.logo_label.isVisible():
            self.logo_label.raise_()
            print("Raised logo above bezel")
        
        print("Final stack order: Background -> Bezel -> Shadows/Logo -> Controls")
    
    # Make sure the bezel is properly layered in window setup
    def layering_for_bezel(self):
        """Setup proper layering for bezel display"""
        # If we have a bezel, ensure proper layering at startup
        if hasattr(self, 'has_bezel') and self.has_bezel:
            # Make sure background label exists and is on top of bezel
            if hasattr(self, 'bg_label') and self.bg_label:
                self.bg_label.raise_()
            
            # Make sure logo is on top if it exists
            if hasattr(self, 'logo_label') and self.logo_label:
                self.logo_label.raise_()
            
            # Make sure all control labels are on top
            if hasattr(self, 'control_labels'):
                for control_data in self.control_labels.values():
                    if 'label' in control_data and control_data['label']:
                        control_data['label'].raise_()
            
            print("Layering setup for bezel display")
    
    # Replace integrate_bezel_support to load from settings
    # Update integrate_bezel_support to initialize joystick visibility
    def integrate_bezel_support(self):
        """Add bezel support with joystick visibility settings"""
        # Initialize with defaults
        self.bezel_label = None
        self.has_bezel = False
        
        # Load bezel and joystick settings
        bezel_settings = self.load_bezel_settings()
        self.bezel_visible = bezel_settings.get("bezel_visible", False)
        self.joystick_visible = bezel_settings.get("joystick_visible", True)  # Default to visible
        print(f"Loaded bezel visibility: {self.bezel_visible}, joystick visibility: {self.joystick_visible}")
        
        # Clean, Tkinter-like button style
        button_style = """
            QPushButton {
                background-color: #404050;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
                font-weight: bold;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #555565;
            }
            QPushButton:pressed {
                background-color: #303040;
            }
        """
        
        # Create bezel toggle button
        self.bezel_button = QPushButton("Show Bezel")
        self.bezel_button.clicked.connect(self.toggle_bezel_improved)
        self.bezel_button.setStyleSheet(button_style)
        
        # Add to the bottom row
        if hasattr(self, 'bottom_row'):
            self.top_row.addWidget(self.bezel_button)
        elif hasattr(self, 'button_layout'):
            self.button_layout.addWidget(self.bezel_button)
        
        # Check if a bezel exists for this ROM
        bezel_path = self.find_bezel_path(self.rom_name)
        self.has_bezel = bezel_path is not None
        
        # Update button state
        self.bezel_button.setEnabled(self.has_bezel)
        
        if not self.has_bezel:
            self.bezel_button.setText("No Bezel")
            self.bezel_button.setToolTip(f"No bezel found for {self.rom_name}")
        else:
            # Set initial button text based on visibility setting
            self.bezel_button.setText("Hide Bezel" if self.bezel_visible else "Show Bezel")
            self.bezel_button.setToolTip(f"Toggle bezel visibility: {bezel_path}")
            print(f"Bezel available at: {bezel_path}")
            
            # If bezel should be visible based on settings, show it
            if self.bezel_visible:
                # Use a small delay to ensure the canvas is fully initialized
                QTimer.singleShot(100, self.show_bezel_with_background)
                print("Bezel initialized as visible based on settings")
    
    # 3. Modify the on_label_move method to remove shadow handling
    def on_label_move(self, event, label, orig_func=None):
        """Handle label movement without shadow updates"""
        # If we should use the original function, do that
        if orig_func is not None:
            # Call the original mouseMoveEvent method for the label
            orig_func(event)
            return
            
        # Direct handling (if orig_func is None)
        if hasattr(label, 'dragging') and label.dragging:
            # Get the current mouse position
            delta = event.pos() - label.drag_start_pos
            
            # FIXED: Use original position + delta to preserve offset
            if hasattr(label, 'original_label_pos'):
                new_pos = label.original_label_pos + delta
            else:
                # Fallback to mapToParent
                new_pos = label.mapToParent(event.pos() - label.drag_start_pos)
            
            # Move the label
            label.move(new_pos)
        
        # Let event propagate
        event.accept()

    def create_presized_label(self, text, font, control_name=""):
        """Create a properly sized label before positioning it"""
        from PyQt5.QtWidgets import QSizePolicy
        from PyQt5.QtCore import Qt
        
        # Create the label
        label = DraggableLabel(text, self.canvas, settings=self.text_settings.copy())
        
        # Apply font directly
        label.setFont(font)
        
        # Important text display fixes
        label.setWordWrap(False)  # Prevent wrapping
        label.setTextFormat(Qt.PlainText)  # Simple text format
        
        # Remove any constraints
        label.setMinimumSize(0, 0)
        label.setMaximumSize(16777215, 16777215)  # Qt's maximum
        
        # Set expanding size policy
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Force size calculation
        label.adjustSize()
        
        # Track the actual size used
        width = label.width()
        height = label.height()
        
        if control_name:
            print(f"Presized {control_name}: {width}x{height}")
        
        return label, width, height

    # 11. Modify the show_all_xinput_controls method to remove shadow creation
    def show_all_xinput_controls(self):
        """Show all possible P1 XInput controls for global positioning without shadows"""
        # Standard XInput controls for positioning - P1 ONLY
        xinput_controls = {
            "P1_JOYSTICK_UP": "LS Up",
            "P1_JOYSTICK_DOWN": "LS Down",
            "P1_JOYSTICK_LEFT": "LS Left",
            "P1_JOYSTICK_RIGHT": "LS Right",
            "P1_JOYSTICK2_UP": "RS Up",
            "P1_JOYSTICK2_DOWN": "RS Down",
            "P1_JOYSTICK2_LEFT": "RS Left",
            "P1_JOYSTICK2_RIGHT": "RS Right",
            "P1_BUTTON1": "A Button",
            "P1_BUTTON2": "B Button",
            "P1_BUTTON3": "X Button",
            "P1_BUTTON4": "Y Button",
            "P1_BUTTON5": "Left Bumper",
            "P1_BUTTON6": "Right Bumper",
            "P1_BUTTON7": "Left Trigger",
            "P1_BUTTON8": "Right Trigger",
            "P1_BUTTON9": "LS Button",
            "P1_BUTTON10": "RS Button",
            "P1_START": "Start Button",
            "P1_SELECT": "Back Button",
        }
        
        try:
            from PyQt5.QtGui import QFont, QFontInfo, QColor, QFontDatabase, QFontMetrics
            from PyQt5.QtCore import QPoint, Qt, QTimer
            from PyQt5.QtWidgets import QLabel, QSizePolicy
            import os
            
            print("\n--- Showing all P1 XInput controls without shadows ---")
            
            # CRITICAL FIX: First ensure fonts are properly loaded/registered
            if not hasattr(self, 'current_font') or self.current_font is None:
                print("Font not initialized - forcing font loading before showing XInput controls")
                self.load_and_register_fonts()
            
            # Save existing control positions
            if not hasattr(self, 'original_controls_backup'):
                self.original_controls_backup = {}
                for control_name, control_data in self.control_labels.items():
                    self.original_controls_backup[control_name] = {
                        'action': control_data['action'],
                        'position': control_data['label'].pos(),
                        'original_pos': control_data.get('original_pos', QPoint(0, 0))
                    }
                print(f"Backed up {len(self.original_controls_backup)} original controls")
            
            # Clear ALL existing controls first
            for control_name in list(self.control_labels.keys()):
                # Remove the control from the canvas
                if control_name in self.control_labels:
                    if 'label' in self.control_labels[control_name]:
                        self.control_labels[control_name]['label'].deleteLater()
                    del self.control_labels[control_name]

            # Clear collections
            self.control_labels = {}
            print("Cleared all existing controls")
            
            # Load saved positions
            saved_positions = self.load_saved_positions()
            
            # Extract text settings and style information
            font_family = self.text_settings.get("font_family", "Arial")
            font_size = self.text_settings.get("font_size", 28)
            bold_strength = self.text_settings.get("bold_strength", 2) > 0
            use_uppercase = self.text_settings.get("use_uppercase", False)
            show_button_prefix = self.text_settings.get("show_button_prefix", True)
            y_offset = self.text_settings.get("y_offset", -40)
            
            # Get color and gradient settings
            use_prefix_gradient = self.text_settings.get("use_prefix_gradient", False)
            use_action_gradient = self.text_settings.get("use_action_gradient", False)
            prefix_color = self.text_settings.get("prefix_color", "#FFC107")
            action_color = self.text_settings.get("action_color", "#FFFFFF")
            prefix_gradient_start = self.text_settings.get("prefix_gradient_start", "#FFC107")
            prefix_gradient_end = self.text_settings.get("prefix_gradient_end", "#FF5722")
            action_gradient_start = self.text_settings.get("action_gradient_start", "#2196F3")
            action_gradient_end = self.text_settings.get("action_gradient_end", "#4CAF50")
            
            # CRITICAL FIX: Use font objects that already exist rather than creating new ones
            if hasattr(self, 'current_font') and self.current_font:
                font = QFont(self.current_font)  # Create a copy to avoid modifying the original
                print(f"Using existing current_font for XInput controls: {font.family()}")
            elif hasattr(self, 'initialized_font') and self.initialized_font:
                font = QFont(self.initialized_font)
                print(f"Using initialized_font for XInput controls: {font.family()}")
            else:
                # Create a standard font as a last resort
                font = QFont(font_family, font_size)
                font.setBold(bold_strength)
                font.setStyleStrategy(QFont.PreferMatch)  # Force exact matching
                print(f"Created new font for XInput controls: {font.family()} (fallback)")
            
            # Print actual font info for debugging
            font_info = QFontInfo(font)
            print(f"Actual font being used: {font_info.family()}, size: {font_info.pointSize()}")
            
            # Calculate the maximum text width needed 
            font_metrics = QFontMetrics(font)
            max_text_width = 0
            
            # First determine the longest text to ensure consistent sizing
            for control_name, action_text in xinput_controls.items():
                button_prefix = self.get_button_prefix(control_name)
                if use_uppercase:
                    action_text = action_text.upper()
                
                display_text = action_text
                if show_button_prefix and button_prefix:
                    display_text = f"{button_prefix}: {action_text}"
                
                # Calculate width needed for this text
                text_width = font_metrics.horizontalAdvance(display_text)
                
                # Add some padding to ensure no cut-off
                text_width += 20  # 10px padding on each side
                
                max_text_width = max(max_text_width, text_width)
            
            print(f"Calculated maximum text width: {max_text_width}px")
            
            # Default grid layout
            grid_x, grid_y = 0, 0
            
            # Create all P1 XInput controls
            for control_name, action_text in xinput_controls.items():
                # Apply uppercase if needed
                if use_uppercase:
                    action_text = action_text.upper()
                
                # Get button prefix
                button_prefix = self.get_button_prefix(control_name)
                
                # Add prefix if enabled
                display_text = action_text
                if show_button_prefix and button_prefix:
                    display_text = f"{button_prefix}: {action_text}"
                
                # Choose the correct label class based on gradient settings
                if use_prefix_gradient or use_action_gradient:
                    # Use gradient-enabled label
                    label = GradientDraggableLabel(display_text, self.canvas, settings=self.text_settings.copy())
                    
                    # Set gradient properties
                    label.use_prefix_gradient = use_prefix_gradient
                    label.use_action_gradient = use_action_gradient
                    label.prefix_gradient_start = QColor(prefix_gradient_start)
                    label.prefix_gradient_end = QColor(prefix_gradient_end)
                    label.action_gradient_start = QColor(action_gradient_start)
                    label.action_gradient_end = QColor(action_gradient_end)
                else:
                    # Use color-enabled label
                    label = ColoredDraggableLabel(display_text, self.canvas, settings=self.text_settings.copy())
                
                # CRITICAL FIX: Apply font directly using existing font object
                label.setFont(font)
                
                # Additional precautions to ensure proper font application
                label.setStyleSheet(f"background-color: transparent; border: none; font-family: '{font.family()}';")
                
                label.prefix = button_prefix
                label.action = action_text
                
                # IMPORTANT: Remove size constraints and set expanding policy for proper sizing
                label.setMinimumSize(0, 0)
                label.setMaximumSize(16777215, 16777215)  # Qt's QWIDGETSIZE_MAX
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                
                # Make sure we have proper settings in the label
                label.settings = self.text_settings.copy()
                
                # CRITICAL FIX FOR TEXT TRUNCATION:
                # First, let the label auto-size based on content
                label.adjustSize()
                # Then, ensure it's at least as wide as our calculated max width
                # This creates consistency and prevents long text from being cut off
                label_width = max(label.width(), max_text_width)
                label_height = label.height()
                label.resize(label_width, label_height)
                
                # Determine position - now completely separated from creation
                x, y = 0, 0
                
                # Check for saved position in the following order:
                # a) Global positions from saved_positions
                # b) Backup positions from original_controls_backup
                # c) Default grid-based position
                if saved_positions and control_name in saved_positions:
                    # Use the EXACT coordinates from global positions
                    pos_x, pos_y = saved_positions[control_name]
                    x, y = pos_x, pos_y + y_offset
                    original_pos = QPoint(pos_x, pos_y)
                    print(f"Using global position for {control_name}: ({pos_x}, {pos_y})")
                
                elif control_name in self.original_controls_backup:
                    # Use backup position exactly as stored
                    backup_pos = self.original_controls_backup[control_name]['position']
                    x, y = backup_pos.x(), backup_pos.y()
                    original_pos = self.original_controls_backup[control_name]['original_pos']
                    print(f"Using backup position for {control_name}: ({x}, {y})")
                
                else:
                    # Use grid position with fixed spacing
                    x = 100 + (grid_x * 220)  # Wider spacing for longer labels
                    y = 100 + (grid_y * 60) + y_offset
                    original_pos = QPoint(x, y - y_offset)
                    
                    # Update grid
                    grid_x = (grid_x + 1) % 4
                    if grid_x == 0:
                        grid_y += 1
                    print(f"Using grid position for {control_name}: ({x}, {y})")
                
                # Apply position
                label.move(x, y)
                
                # Store in control_labels with original position
                self.control_labels[control_name] = {
                    'label': label,
                    'action': action_text,
                    'prefix': button_prefix,
                    'original_pos': original_pos
                }
                
                # Apply visibility based on joystick settings
                is_visible = True
                if "JOYSTICK" in control_name and hasattr(self, 'joystick_visible'):
                    is_visible = self.joystick_visible
                
                label.setVisible(is_visible)
            
            # Update button text
            if hasattr(self, 'xinput_controls_button'):
                self.xinput_controls_button.setText("Normal Controls")
            
            # Set XInput mode flag
            self.showing_all_xinput_controls = True
            
            # CRITICAL FIX: Force updates with staggered timers for reliable application
            QTimer.singleShot(50, lambda: self.force_resize_all_labels())
            QTimer.singleShot(150, lambda: self.apply_text_settings())
            QTimer.singleShot(250, lambda: self.force_resize_all_labels())  # Second pass
            
            # Force a canvas update
            self.canvas.update()
            
            print(f"Created and displayed {len(xinput_controls)} P1 XInput controls without shadows")
            return True
            
        except Exception as e:
            print(f"Error showing XInput controls: {e}")
            import traceback
            traceback.print_exc()
            return False

    # Fix 1: Modify the toggle_xinput_controls method to explicitly force font reloading
    def toggle_xinput_controls(self):
        """Toggle between normal game controls and all XInput controls with improved font handling"""
        # Check if already showing all XInput controls
        if hasattr(self, 'showing_all_xinput_controls') and self.showing_all_xinput_controls:
            # Switch back to normal game controls
            self.showing_all_xinput_controls = False
            
            # CRITICAL FIX: Store current font information before clearing controls
            if hasattr(self, 'current_font'):
                stored_font = self.current_font
                print(f"Stored current font before control reset: {stored_font.family()}")
            else:
                stored_font = None
                print("No current_font to store")
            
            # CRITICAL FIX: Before clearing, ensure the fonts are loaded/registered
            self.load_and_register_fonts()
            
            # Clear all current controls
            for control_name in list(self.control_labels.keys()):
                # Remove the control from the canvas
                if control_name in self.control_labels:
                    self.control_labels[control_name]['label'].deleteLater()
                    del self.control_labels[control_name]

            # Clear collections
            self.control_labels = {}
            
            # Update button text
            if hasattr(self, 'xinput_controls_button'):
                self.xinput_controls_button.setText("Show All XInput")
            
            # Reload the current game controls from scratch
            self.create_control_labels()
            
            # CRITICAL FIX: Force apply the font after recreating controls
            QTimer.singleShot(100, self.apply_text_settings)
            QTimer.singleShot(200, self.force_resize_all_labels)
            
            print("Switched back to normal game controls with font restoration")
        else:
            # Switch to showing all XInput controls
            self.show_all_xinput_controls()

    # 15. Modify apply_joystick_visibility to not update shadows
    def apply_joystick_visibility(self):
        """Force apply joystick visibility settings to all controls"""
        controls_updated = 0
        
        for control_name, control_data in self.control_labels.items():
            if "JOYSTICK" in control_name:
                is_visible = self.texts_visible and self.joystick_visible
                
                # Only update if needed
                if control_data['label'].isVisible() != is_visible:
                    control_data['label'].setVisible(is_visible)
                    controls_updated += 1
        
        print(f"Applied joystick visibility ({self.joystick_visible}) to {controls_updated} controls")
        return controls_updated

    # Call this at the end of PreviewWindow.__init__
    def init_joystick_delayed(self):
        """Set up a delayed joystick visibility initialization"""
        # After UI is fully initialized, apply joystick visibility
        QTimer.singleShot(600, self.apply_joystick_visibility)
        print("Scheduled delayed joystick visibility application")
    
    # Add method to initialize joystick visibility during startup
    def initialize_joystick_visibility(self):
        """Apply joystick visibility setting to controls"""
        # Make sure joystick_visible is initialized
        if not hasattr(self, 'joystick_visible'):
            # Try to load from settings
            bezel_settings = self.load_bezel_settings()
            self.joystick_visible = bezel_settings.get("joystick_visible", True)
        
        # Update joystick button text if it exists
        if hasattr(self, 'joystick_button'):
            self.joystick_button.setText("Show Joystick" if not self.joystick_visible else "Hide Joystick")
        
        # Apply visibility to joystick controls
        for control_name, control_data in self.control_labels.items():
            if "JOYSTICK" in control_name:
                is_visible = self.texts_visible and self.joystick_visible
                control_data['label'].setVisible(is_visible)
        
        print(f"Initialized joystick visibility to: {self.joystick_visible}")

    # Add this to the button_frame creation in __init__
    def add_xinput_controls_button(self):
        """Add a button to show all XInput controls"""
        button_style = """
            QPushButton {
                background-color: #3d3d3d;
                color: white;
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                min-width: 90px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """
        
        # Create button for XInput controls toggle
        '''self.xinput_controls_button = QPushButton("Show All XInput")
        self.xinput_controls_button.clicked.connect(self.toggle_xinput_controls)
        self.xinput_controls_button.setStyleSheet(button_style)
        self.button_layout.setToolTip("Show all XInput controls for positioning")'''
        
        # Add to bottom row if it exists
        if hasattr(self, 'bottom_row'):
            self.bottom_row.addWidget(self.xinput_controls_button)
    
    # Add method to hide bezel
    def hide_bezel(self):
        """Hide the bezel image"""
        if self.bezel_label:
            self.bezel_label.hide()
            print("Bezel hidden")

    # Update resizeEvent to handle bezel resizing
    def on_resize_with_bezel(self, event):
        """Handle resize events with bezel support"""
        # Call the original resize handler first
        if hasattr(self, 'on_canvas_resize'):
            self.canvas.resizeEvent = self.on_canvas_resize_with_background
        # Update bezel size if it exists and is visible
        if hasattr(self, 'bezel_visible') and self.bezel_visible and hasattr(self, 'bezel_label') and self.bezel_label:
            window_width = self.width()
            window_height = self.height()
            
            # Resize bezel to match window
            if hasattr(self.bezel_label, 'pixmap') and self.bezel_label.pixmap() and not self.bezel_label.pixmap().isNull():
                # Get the original pixmap
                original_pixmap = self.bezel_label.pixmap()
                
                # When scaling background or bezel images
                scaled_pixmap = original_pixmap.scaled(
                    self.canvas.width(),
                    self.canvas.height(),
                    Qt.IgnoreAspectRatio,  # This forces it to fill the entire space
                    Qt.SmoothTransformation
                )
                self.bezel_label.setPixmap(scaled_pixmap)
                self.bezel_label.setGeometry(0, 0, window_width, window_height)
                
                print(f"Bezel resized to {window_width}x{window_height}")
    
    # Add helper method to explicitly save global text settings
    def save_global_text_settings(self):
        """Save current text settings as global defaults in settings directory"""
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Save to global settings file
            settings_file = os.path.join(self.settings_dir, "text_appearance_settings.json")
            
            with open(settings_file, 'w') as f:
                json.dump(self.text_settings, f)
            print(f"Saved GLOBAL text settings to {settings_file}: {self.text_settings}")
            
            # Optional - show a confirmation message
            QMessageBox.information(self, "Settings Saved", 
                                "Text settings have been saved as global defaults.")
        except Exception as e:
            print(f"Error saving global text settings: {e}")
            import traceback
            traceback.print_exc()
    
    def load_bezel_settings(self):
        """Load bezel and joystick visibility settings from file in settings directory"""
        settings = {
            "bezel_visible": False,  # Default to hidden
            "joystick_visible": True  # Default to visible
        }
        
        try:
            # Check new location first
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            
            # If not found, check legacy locations
            if not os.path.exists(settings_file):
                legacy_paths = [
                    os.path.join(self.preview_dir, "global_bezel.json"),
                    os.path.join(self.preview_dir, f"{self.rom_name}_bezel.json")
                ]
                
                for legacy_path in legacy_paths:
                    if os.path.exists(legacy_path):
                        # Load from legacy location
                        with open(legacy_path, 'r') as f:
                            loaded_settings = json.load(f)
                        
                        # Migrate to new location
                        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
                        with open(settings_file, 'w') as f:
                            json.dump(loaded_settings, f)
                        
                        print(f"Migrated bezel settings from {legacy_path} to {settings_file}")
                        settings.update(loaded_settings)
                        return settings
            
            # Regular loading from new location
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
                    print(f"Loaded bezel/joystick settings from {settings_file}: {settings}")
        except Exception as e:
            print(f"Error loading bezel/joystick settings: {e}")
        
        return settings

    # Add method to save bezel settings
    def save_bezel_settings(self, is_global=True):
        """Save bezel and joystick visibility settings to file in settings directory"""
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Settings file path - always global in new structure
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            
            # Create settings object
            settings = {
                "bezel_visible": self.bezel_visible,
                "joystick_visible": getattr(self, 'joystick_visible', True)  # Default to True if not set
            }
            
            # Save settings
            with open(settings_file, 'w') as f:
                json.dump(settings, f)
                
            print(f"Saved bezel/joystick settings to {settings_file}: {settings}")
            
            # Show message if global
            if is_global:
                print(f"GLOBAL bezel/joystick settings saved")
                QMessageBox.information(
                    self,
                    "Global Settings Saved",
                    f"Visibility settings saved as global default."
                )
                
            return True
        except Exception as e:
            print(f"Error saving bezel/joystick settings: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def center_logo(self):
        """Center the logo horizontally in the canvas while preserving Y position"""
        if not hasattr(self, 'logo_label') or not self.logo_label:
            print("No logo to center")
            return False

        # Get canvas and logo dimensions
        canvas_width = self.canvas.width()
        logo_width = self.logo_label.width()
        
        # Get current Y position
        current_pos = self.logo_label.pos()
        current_y = current_pos.y()

        # Calculate center X position
        x = (canvas_width - logo_width) // 2

        # Move logo to new X position, keeping current Y
        self.logo_label.move(x, current_y)

        # Update settings to enable horizontal centering
        self.logo_settings["keep_horizontally_centered"] = True
        self.logo_settings["custom_position"] = True
        self.logo_settings["x_position"] = x
        self.logo_settings["y_position"] = current_y

        # Save to file immediately to persist across ROM changes
        if hasattr(self, 'save_logo_settings'):
            self.save_logo_settings(is_global=True)

        print(f"Logo horizontally centered at X={x}, Y remains {current_y}")
        return True
    
    def load_logo_settings(self):
        """Load logo settings from file with new path handling and button text update"""
        settings = {
            "logo_visible": True,
            "custom_position": True,
            "x_position": 20,
            "y_position": 20,
            "width_percentage": 15,
            "height_percentage": 15,
            "maintain_aspect": True,
            "keep_horizontally_centered": False
        }
        
        try:
            # First try the settings directory
            settings_file = os.path.join(self.settings_dir, "logo_settings.json")
            
            # If not found, check legacy locations
            if not os.path.exists(settings_file):
                legacy_paths = [
                    os.path.join(self.preview_dir, f"{self.rom_name}_logo.json"),
                    os.path.join(self.preview_dir, "global_logo.json"),
                    os.path.join(self.mame_dir, "logo_settings.json")
                ]
                
                for legacy_path in legacy_paths:
                    if os.path.exists(legacy_path):
                        # Load settings from legacy location
                        with open(legacy_path, 'r') as f:
                            loaded_settings = json.load(f)
                        
                        # Migrate to new location
                        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
                        with open(settings_file, 'w') as f:
                            json.dump(loaded_settings, f)
                        
                        print(f"Migrated logo settings from {legacy_path} to {settings_file}")
                        settings.update(loaded_settings)
                        break
            
            # Regular loading from new location
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
                    print(f"Loaded logo settings: {settings}")
            
            # NEW: Update center logo button text after loading settings
            self.update_center_logo_button_text()
            
        except Exception as e:
            print(f"Error loading logo settings: {e}")
            import traceback
            traceback.print_exc()
        
        return settings
    
    # Make sure the toggle_logo method properly handles visibility
    def toggle_logo(self):
        """Toggle logo visibility"""
        self.logo_visible = not self.logo_visible
        
        # Update button text
        self.logo_button.setText("Hide Logo" if self.logo_visible else "Show Logo")
        
        # Toggle logo visibility
        if hasattr(self, 'logo_label'):
            self.logo_label.setVisible(self.logo_visible)
        elif self.logo_visible:
            # Create logo if it doesn't exist yet
            self.add_logo()
        
        # Update settings
        self.logo_settings["logo_visible"] = self.logo_visible
        
        # Save setting immediately 
        self.save_positions(is_global=False)  # Save for current ROM by default
    
    def show_logo_position(self):
        """Show dialog to configure logo position"""
        self.show_logo_settings()
    
    def save_logo_settings(self, is_global=False):
        """Save logo settings to file in settings directory"""
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Determine file path - always save in settings dir now
            settings_file = os.path.join(self.settings_dir, "logo_settings.json")
            
            # Only save the settings we need
            settings_to_save = {
                "logo_visible": self.logo_settings.get("logo_visible", True),
                "custom_position": True,  # Always use custom position
                "x_position": self.logo_settings.get("x_position", 20),
                "y_position": self.logo_settings.get("y_position", 20),
                "width_percentage": self.logo_settings.get("width_percentage", 15),
                "height_percentage": self.logo_settings.get("height_percentage", 15),
                "maintain_aspect": self.logo_settings.get("maintain_aspect", True),
                "keep_horizontally_centered": self.logo_settings.get("keep_horizontally_centered", False)
            }
            
            # Save to file
            with open(settings_file, 'w') as f:
                json.dump(settings_to_save, f)
                
            print(f"Saved logo settings to {settings_file}: {settings_to_save}")
            return True
        except Exception as e:
            print(f"Error saving logo settings: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Add a method to add_logo to store original pixmap
    # Improved add_logo method to handle sizes better
    def add_logo(self):
        """Add logo overlay to preview with horizontal centering support"""
        # Find logo path
        logo_path = self.find_logo_path(self.rom_name)
        if not logo_path:
            print(f"No logo found for {self.rom_name}")
            return
                
        # Create logo label
        self.logo_label = QLabel(self.canvas)
        
        # Load and store original pixmap
        original_pixmap = QPixmap(logo_path)
        self.original_logo_pixmap = original_pixmap  # Store unmodified original
        
        if original_pixmap.isNull():
            print(f"Error loading logo image from {logo_path}")
            return
        
        # Set initial pixmap
        self.logo_label.setPixmap(original_pixmap)

        # Always remove border, especially important in clean mode
        self.logo_label.setStyleSheet("background-color: transparent; border: none;")

        # Only enable drag and resize in non-clean mode
        if not hasattr(self, 'clean_mode') or not self.clean_mode:
            # Set cursor for dragging
            self.logo_label.setCursor(Qt.OpenHandCursor)
            
            # Enable mouse tracking for logo
            self.logo_label.setMouseTracking(True)
            
            # Add drag and resize support
            self.logo_label.mousePressEvent = lambda event: self.logo_mouse_press(event)
            self.logo_label.mouseMoveEvent = lambda event: self.logo_mouse_move(event)
            self.logo_label.mouseReleaseEvent = lambda event: self.logo_mouse_release(event)
            
            # Add custom paint event for resize handle
            self.logo_label.paintEvent = lambda event: self.logo_paint_event(event)
        
        # Now update the logo display to apply settings
        # This will resize according to saved settings
        self.update_logo_display()
        
        # Show the logo
        self.logo_label.show()
        
        # Check for horizontal centering flag in settings
        is_horizontally_centered = self.logo_settings.get("keep_horizontally_centered", False)
        
        if is_horizontally_centered:
            print("Logo initialized with horizontal centering enabled")
            
            # Force a resize to apply the correct centered position
            QTimer.singleShot(100, self.force_logo_resize)
        
        print(f"Logo added and sized: {self.logo_label.width()}x{self.logo_label.height()}")
    
    def update_center_logo_button_text(self):
        """Make sure the center logo button always says 'Center Logo'"""
        if hasattr(self, 'center_logo_button'):
            self.center_logo_button.setText("Center Logo")
    
    # Improve logo_mouse_press to store the original pixmap for proper resizing
    def logo_mouse_press(self, event):
        """Handle mouse press on logo for dragging and resizing with pixmap preservation"""
        if event.button() == Qt.LeftButton:
            # Check if we're in the resize corner
            if self.is_in_logo_resize_corner(event.pos()):
                # Start resizing
                self.logo_is_resizing = True
                self.logo_original_size = self.logo_label.size()
                self.logo_resize_start_pos = event.pos()
                
                # Make sure we have the original pixmap stored
                if not hasattr(self, 'original_logo_pixmap') or not self.original_logo_pixmap:
                    self.original_logo_pixmap = self.logo_label.pixmap()
                    
                self.logo_label.setCursor(Qt.SizeFDiagCursor)
                print("Logo resize started")
            else:
                # Start dragging
                self.logo_drag_start_pos = event.pos()
                self.logo_is_dragging = True
                
                # Change cursor to indicate dragging
                self.logo_label.setCursor(Qt.ClosedHandCursor)
                
                # Enable custom position mode
                self.logo_settings["custom_position"] = True

    # Add a method to check if we're in the logo resize corner
    def is_in_logo_resize_corner(self, pos):
        """Check if the position is in the logo resize corner"""
        if not hasattr(self, 'logo_label') or not self.logo_label:
            return False
            
        # Define resize handle size
        resize_handle_size = 15
        
        # Check if position is in bottom-right corner
        return (pos.x() > self.logo_label.width() - resize_handle_size and 
                pos.y() > self.logo_label.height() - resize_handle_size)
    
    # Modified logo_mouse_move method for more consistent pixmap handling
    def logo_mouse_move(self, event):
        """Handle mouse move on logo for dragging and resizing with reliable pixmap scaling"""
        # Handle resizing with direct pixmap manipulation
        if hasattr(self, 'logo_is_resizing') and self.logo_is_resizing:
            # Calculate size change
            delta_width = event.x() - self.logo_resize_start_pos.x()
            delta_height = event.y() - self.logo_resize_start_pos.y()
            
            # Calculate new size with minimum
            new_width = max(50, self.logo_original_size.width() + delta_width)
            new_height = max(30, self.logo_original_size.height() + delta_height)
            
            # Get the original pixmap
            if hasattr(self, 'original_logo_pixmap') and not self.original_logo_pixmap.isNull():
                original_pixmap = self.original_logo_pixmap
            else:
                # Fallback to the current pixmap if original not available
                original_pixmap = self.logo_label.pixmap()
                self.original_logo_pixmap = QPixmap(original_pixmap)  # Make a copy
            
            # Resize the pixmap with proper aspect ratio handling
            if self.logo_settings.get("maintain_aspect", True):
                scaled_pixmap = original_pixmap.scaled(
                    new_width, 
                    new_height, 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
            else:
                scaled_pixmap = original_pixmap.scaled(
                    new_width, 
                    new_height, 
                    Qt.IgnoreAspectRatio, 
                    Qt.SmoothTransformation
                )
            
            # Apply the scaled pixmap
            self.logo_label.setPixmap(scaled_pixmap)
            
            # Actually resize the label to match the pixmap
            self.logo_label.resize(scaled_pixmap.width(), scaled_pixmap.height())
            
            # Update size percentages for settings
            canvas_width = self.canvas.width()
            canvas_height = self.canvas.height()
            
            width_percentage = (scaled_pixmap.width() / canvas_width) * 100
            height_percentage = (scaled_pixmap.height() / canvas_height) * 100
            
            # Update settings in memory
            self.logo_settings["width_percentage"] = width_percentage
            self.logo_settings["height_percentage"] = height_percentage
            
            # Debug output (occasionally)
            if random.random() < 0.05:
                print(f"Logo resized: {scaled_pixmap.width()}x{scaled_pixmap.height()} " +
                    f"({width_percentage:.1f}%, {height_percentage:.1f}%)")
        
        # Rest of the method for handling dragging and cursor updates...
        elif hasattr(self, 'logo_is_dragging') and self.logo_is_dragging:
            # Calculate new position
            delta = event.pos() - self.logo_drag_start_pos
            new_pos = self.logo_label.pos() + delta
            
            # Apply boundaries
            canvas_width = self.canvas.width()
            canvas_height = self.canvas.height()
            logo_width = self.logo_label.width()
            logo_height = self.logo_label.height()
            
            margin = 10
            new_pos.setX(max(margin, min(canvas_width - logo_width - margin, new_pos.x())))
            new_pos.setY(max(margin, min(canvas_height - logo_height - margin, new_pos.y())))
            
            # Move the logo
            self.logo_label.move(new_pos)
            
            # Update position in memory
            self.logo_settings["x_position"] = new_pos.x()
            self.logo_settings["y_position"] = new_pos.y()
            
            # NEW: Disable horizontal centering when manually moved
            if self.logo_settings.get("keep_horizontally_centered", False):
                self.logo_settings["keep_horizontally_centered"] = False
                print("Horizontal centering disabled due to manual positioning")
        
        # Update cursor
        elif hasattr(self, 'logo_label') and self.logo_label:
            if self.is_in_logo_resize_corner(event.pos()):
                self.logo_label.setCursor(Qt.SizeFDiagCursor)
            else:
                self.logo_label.setCursor(Qt.OpenHandCursor)
                
    # Add a method that forces the logo to resize according to settings
    def force_logo_resize(self):
        """Force logo to resize according to current settings with improved center handling"""
        if not hasattr(self, 'logo_label') or not self.logo_label:
            print("No logo label to resize")
            return False
            
        if not hasattr(self, 'original_logo_pixmap') or self.original_logo_pixmap.isNull():
            # Try to load the logo image again
            logo_path = self.find_logo_path(self.rom_name)
            if not logo_path:
                print("Cannot force resize - no logo image found")
                return False
                
            self.original_logo_pixmap = QPixmap(logo_path)
            if self.original_logo_pixmap.isNull():
                print("Cannot force resize - failed to load logo image")
                return False
        
        # Get canvas and logo dimensions
        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        
        # Calculate target size
        width_percent = float(self.logo_settings.get("width_percentage", 15))
        height_percent = float(self.logo_settings.get("height_percentage", 15))
        
        target_width = int((width_percent / 100) * canvas_width)
        target_height = int((height_percent / 100) * canvas_height)
        
        print(f"Force-resizing logo to {target_width}x{target_height} pixels " +
            f"({width_percent:.1f}%, {height_percent:.1f}%)")
        
        # Scale the pixmap to the target size
        if self.logo_settings.get("maintain_aspect", True):
            scaled_pixmap = self.original_logo_pixmap.scaled(
                target_width, 
                target_height, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
        else:
            scaled_pixmap = self.original_logo_pixmap.scaled(
                target_width, 
                target_height, 
                Qt.IgnoreAspectRatio, 
                Qt.SmoothTransformation
            )
        
        # Apply the scaled pixmap
        self.logo_label.setPixmap(scaled_pixmap)
        
        # Ensure label size matches pixmap size
        self.logo_label.resize(scaled_pixmap.width(), scaled_pixmap.height())
        
        # Check for center position override
        is_centered = self.logo_settings.get("logo_position", "") == "center"
        
        # Position the logo
        if is_centered:
            # Center the logo regardless of custom position flag
            x = (canvas_width - scaled_pixmap.width()) // 2
            y = (canvas_height - scaled_pixmap.height()) // 2
            self.logo_label.move(x, y)
            
            # Update stored position
            self.logo_settings["x_position"] = x
            self.logo_settings["y_position"] = y
            print(f"Logo centered at ({x}, {y}) after resize")
        elif self.logo_settings.get("custom_position", False):
            # Use custom position if not centered
            x = self.logo_settings.get("x_position", 20)
            y = self.logo_settings.get("y_position", 20)
            self.logo_label.move(x, y)
            print(f"Logo positioned at custom ({x}, {y}) after resize")
        else:
            # Use preset position
            position = self.logo_settings.get("logo_position", "top-left")
            self.position_logo(position)
            print(f"Logo positioned at {position} after resize")
        
        print(f"Logo resized to {scaled_pixmap.width()}x{scaled_pixmap.height()} pixels")
        return True
    
    def handle_logo_during_resize(self):
        """Update logo position during resize, maintaining horizontal centering"""
        if not hasattr(self, 'logo_label') or not self.logo_label or not self.logo_label.isVisible():
            return
        
        # Check if horizontal centering is enabled
        is_horizontally_centered = self.logo_settings.get("keep_horizontally_centered", False)
        
        if is_horizontally_centered:
            # Simply use force_logo_resize which will handle horizontal centering
            self.force_logo_resize()
        elif hasattr(self, 'update_logo_display'):
            # Otherwise use standard update
            self.update_logo_display()
    
    def logo_mouse_release(self, event):
        """Handle mouse release on logo to end dragging or resizing with settings save"""
        if event.button() == Qt.LeftButton:
            was_resizing = hasattr(self, 'logo_is_resizing') and self.logo_is_resizing
            was_dragging = hasattr(self, 'logo_is_dragging') and self.logo_is_dragging
            
            # End resizing/dragging states
            if hasattr(self, 'logo_is_resizing'):
                self.logo_is_resizing = False
            if hasattr(self, 'logo_is_dragging'):
                self.logo_is_dragging = False
            
            # Reset cursor
            if self.is_in_logo_resize_corner(event.pos()):
                self.logo_label.setCursor(Qt.SizeFDiagCursor)
            else:
                self.logo_label.setCursor(Qt.OpenHandCursor)
            
            # Save settings if the logo was moved or resized
            if was_resizing or was_dragging:
                # Update position and size in settings
                if was_resizing:
                    pixmap = self.logo_label.pixmap()
                    canvas_width = self.canvas.width()
                    canvas_height = self.canvas.height()
                    
                    # Update size percentages
                    self.logo_settings["width_percentage"] = (pixmap.width() / canvas_width) * 100
                    self.logo_settings["height_percentage"] = (pixmap.height() / canvas_height) * 100
                
                if was_dragging:
                    pos = self.logo_label.pos()
                    self.logo_settings["x_position"] = pos.x()
                    self.logo_settings["y_position"] = pos.y()
                    self.logo_settings["custom_position"] = True
                    
                    # Disable horizontal centering if manually moved
                    if self.logo_settings.get("keep_horizontally_centered", False):
                        self.logo_settings["keep_horizontally_centered"] = False
                        print("Horizontal centering disabled due to manual drag")
                
                # Save settings after movement or resizing
                if hasattr(self, 'save_logo_settings'):
                    self.save_logo_settings()
                    action = "resized" if was_resizing else "moved"
                    print(f"Logo {action} - settings saved")
    
    def toggle_horizontal_centering(self, enabled):
        """Toggle horizontal centering controls"""
        # Disable X position spinner when horizontal centering is enabled
        self.x_spin.setEnabled(not enabled)

    
    # Add logo resize handle display in paintEvent
    def logo_paint_event(self, event):
        """Paint event handler for logo label to draw resize handle"""
        # Call the original paint event first (we'll need to hook this up properly)
        QLabel.paintEvent(self.logo_label, event)
        
        # Draw a resize handle in the corner
        if hasattr(self, 'logo_label') and self.logo_label:
            painter = QPainter(self.logo_label)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            
            # Draw in bottom-right corner
            handle_size = 12
            width = self.logo_label.width()
            height = self.logo_label.height()
            
            # Draw diagonal lines for resize handle
            for i in range(1, 3):
                offset = i * 4
                painter.drawLine(
                    width - offset, height, 
                    width, height - offset
                )
            
            painter.end()
    
    def find_logo_path(self, rom_name):
        """Find logo path for a ROM name with updated paths"""
        # Define possible locations for logos
        possible_paths = [
            # Priority 1: First look in preview/logos directory
            os.path.join(self.preview_dir, "logos", f"{rom_name}.png"),
            os.path.join(self.preview_dir, "logos", f"{rom_name}.jpg"),
            
            # Priority 2: Check in collections path
            os.path.join(self.mame_dir, "..", "..", "collections", "Arcades", "medium_artwork", "logo", f"{rom_name}.png"),
            os.path.join(self.mame_dir, "..", "..", "collections", "Arcades", "medium_artwork", "logo", f"{rom_name}.jpg"),
            
            # Priority 3: Check in artwork/logos directory
            os.path.join(self.mame_dir, "artwork", "logos", f"{rom_name}.png"),
            os.path.join(self.mame_dir, "artwork", "logos", f"{rom_name}.jpg"),
        ]
        
        # Check each possible path
        for path in possible_paths:
            if os.path.exists(path):
                print(f"Found logo at: {path}")
                return path
        
        # If not found by exact name, try case-insensitive search in priority directories
        logo_dirs = [
            os.path.join(self.preview_dir, "logos"),
            os.path.join(self.mame_dir, "..", "..", "collections", "Arcades", "medium_artwork", "logo"),
            os.path.join(self.mame_dir, "artwork", "logos")
        ]
        
        for logo_dir in logo_dirs:
            if os.path.exists(logo_dir):
                for filename in os.listdir(logo_dir):
                    file_base, file_ext = os.path.splitext(filename.lower())
                    if file_base == rom_name.lower() and file_ext.lower() in ['.png', '.jpg', '.jpeg']:
                        logo_path = os.path.join(logo_dir, filename)
                        print(f"Found logo with case-insensitive match: {logo_path}")
                        return logo_path
        
        print(f"No logo found for {rom_name}")
        return None
    
    def update_logo_display(self):
        """Update the logo display based on current settings with persistent horizontal centering"""
        if not hasattr(self, 'logo_label') or not self.logo_label:
            print("No logo label to update")
            return
            
        # Make sure we have the original pixmap
        if not hasattr(self, 'original_logo_pixmap') or not self.original_logo_pixmap or self.original_logo_pixmap.isNull():
            # If we don't have original, use current pixmap as original
            self.original_logo_pixmap = self.logo_label.pixmap()
            if not self.original_logo_pixmap or self.original_logo_pixmap.isNull():
                print("No logo pixmap available to resize")
                return
        
        # Get current canvas dimensions 
        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        
        # Get size percentages from settings
        width_percent = self.logo_settings.get("width_percentage", 15) / 100
        height_percent = self.logo_settings.get("height_percentage", 15) / 100
        
        # Calculate pixel dimensions based on percentages
        target_width = int(canvas_width * width_percent)
        target_height = int(canvas_height * height_percent)
        
        print(f"Logo target size: {target_width}x{target_height} pixels ({width_percent*100:.1f}%, {height_percent*100:.1f}%)")
        
        # Get original size for reference
        orig_width = self.original_logo_pixmap.width()
        orig_height = self.original_logo_pixmap.height()
        
        # Handle aspect ratio if needed
        if self.logo_settings.get("maintain_aspect", True):
            orig_ratio = orig_width / orig_height if orig_height > 0 else 1
            
            # Calculate dimensions preserving aspect ratio
            if (target_width / target_height) > orig_ratio:
                # Height is limiting factor
                final_height = target_height
                final_width = int(final_height * orig_ratio)
            else:
                # Width is limiting factor
                final_width = target_width
                final_height = int(final_width / orig_ratio)
        else:
            # Use target dimensions directly
            final_width = target_width
            final_height = target_height
        
        # Apply minimum size constraints
        final_width = max(30, final_width)
        final_height = max(20, final_height)
        
        # Scale the original pixmap to the calculated size
        scaled_pixmap = self.original_logo_pixmap.scaled(
            final_width, 
            final_height, 
            Qt.KeepAspectRatio if self.logo_settings.get("maintain_aspect", True) else Qt.IgnoreAspectRatio, 
            Qt.SmoothTransformation
        )
        
        # Set the pixmap on the label
        self.logo_label.setPixmap(scaled_pixmap)
        
        # Resize the label to match pixmap
        self.logo_label.resize(scaled_pixmap.width(), scaled_pixmap.height())
        
        # Check if horizontal centering is enabled
        is_horizontally_centered = self.logo_settings.get("keep_horizontally_centered", False)
        
        # Get current position
        current_y = self.logo_settings.get("y_position", 20)
        
        if is_horizontally_centered:
            # Calculate horizontal center position
            x = (canvas_width - scaled_pixmap.width()) // 2
            y = current_y  # Keep current Y position
            
            # Update X position in settings
            self.logo_settings["x_position"] = x
            
            print(f"Logo horizontally centered at X={x}, Y={y}")
        elif self.logo_settings.get("custom_position", False):
            # Use custom position
            x = self.logo_settings.get("x_position", 20)
            y = self.logo_settings.get("y_position", 20)
            print(f"Using custom logo position: ({x}, {y})")
        else:
            # Default position if no special handling
            x = 20
            y = 20
            print(f"Using default logo position: (20, 20)")
        
        # Move to position
        self.logo_label.move(x, y)
        
        print(f"Logo display updated: {scaled_pixmap.width()}x{scaled_pixmap.height()} pixels")
        
    # 7. Modify the duplicate_control_label method in PreviewWindow
    def duplicate_control_label(self, label):
        """Duplicate a control label without shadow"""
        # Find which control this label belongs to
        for control_name, control_data in self.control_labels.items():
            if control_data['label'] == label:
                # Create a new unique control name
                new_control_name = f"{control_name}_copy"
                counter = 1
                
                # Make sure the name is unique
                while new_control_name in self.control_labels:
                    new_control_name = f"{control_name}_copy{counter}"
                    counter += 1
                
                # Create a new label with the same text
                action_text = control_data['action']
                
                # Create a new draggable label
                new_label = DraggableLabel(action_text, self.canvas, settings=self.text_settings)
                
                # Copy font and other properties
                new_label.setFont(label.font())
                new_label.setStyleSheet(label.styleSheet())
                
                # Position slightly offset from original
                new_pos = QPoint(label.pos().x() + 20, label.pos().y() + 20)
                new_label.move(new_pos)
                
                # Store the new label
                self.control_labels[new_control_name] = {
                    'label': new_label,
                    'action': action_text,
                    'original_pos': new_pos
                }
                
                # Show the new label
                new_label.show()
                
                break
    
    def create_button_rows(self):
        """Create the button rows for the preview window"""
        # Create two rows for buttons
        self.top_row = QHBoxLayout()
        self.bottom_row = QHBoxLayout()
        
        # Button style
        button_style = """
            QPushButton {
                background-color: #3d3d3d;
                color: white;
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                min-width: 90px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """
        
        # Top row buttons
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.close_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.close_button)
        
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_positions)
        self.reset_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.reset_button)
        
        self.global_button = QPushButton("Global")
        self.global_button.clicked.connect(lambda: self.save_positions(is_global=True))
        self.global_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.global_button)
        
        self.rom_button = QPushButton("ROM")
        self.rom_button.clicked.connect(lambda: self.save_positions(is_global=False))
        self.rom_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.rom_button)
        
        self.text_settings_button = QPushButton("Text Settings")
        self.text_settings_button.clicked.connect(self.show_text_settings)
        self.text_settings_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.text_settings_button)
        
        self.save_image_button = QPushButton("Save Image")
        self.save_image_button.clicked.connect(self.save_image)
        self.save_image_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.save_image_button)
        
        # Bottom row buttons
        self.joystick_button = QPushButton("Joystick")
        self.joystick_button.clicked.connect(self.toggle_joystick_controls)
        self.joystick_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.joystick_button)
        
        self.toggle_texts_button = QPushButton("Hide Texts")
        self.toggle_texts_button.clicked.connect(self.toggle_texts)
        self.toggle_texts_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.toggle_texts_button)
        
        # Add logo controls
        self.logo_visible = self.logo_settings.get("logo_visible", True)
        logo_text = "Hide Logo" if self.logo_visible else "Show Logo"
        self.logo_button = QPushButton(logo_text)
        self.logo_button.clicked.connect(self.toggle_logo)
        self.logo_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.logo_button)
        
        self.logo_pos_button = QPushButton("Logo Pos")
        self.logo_pos_button.clicked.connect(self.show_logo_position)
        self.logo_pos_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.logo_pos_button)
        
        # Add screen toggle button
        self.screen_button = QPushButton("Screen 2")
        self.screen_button.clicked.connect(self.toggle_screen)
        self.screen_button.setStyleSheet(button_style)
        self.bottom_row.addWidget(self.screen_button)
        
        # Add rows to button layout
        self.button_layout.addLayout(self.top_row)
        self.button_layout.addLayout(self.bottom_row)
    
    def save_image(self):
        """Enhanced save_image method that preserves transparency"""
        try:
            # Create the images directory if it doesn't exist
            images_dir = os.path.join(self.preview_dir, "images")
            os.makedirs(images_dir, exist_ok=True)
            
            # Define the output path
            output_path = os.path.join(images_dir, f"{self.rom_name}.png")
            
            # Check if file already exists
            if os.path.exists(output_path):
                # Ask for confirmation
                if QMessageBox.question(
                    self, 
                    "Confirm Overwrite", 
                    f"Image already exists for {self.rom_name}. Overwrite?",
                    QMessageBox.Yes | QMessageBox.No
                ) != QMessageBox.Yes:
                    return False
            
            # Create a new image with the same size as the canvas
            # Use QImage with Format_ARGB32 to support transparency
            from PyQt5.QtGui import QImage
            image = QImage(
                self.canvas.width(),
                self.canvas.height(),
                QImage.Format_ARGB32
            )
            # Fill with transparent background instead of black
            image.fill(Qt.transparent)
            
            # Create painter for the image
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # Draw the background image if it's not the default transparent one
            if hasattr(self, 'background_pixmap') and self.background_pixmap and not self.background_pixmap.isNull():
                # Check if this is the default transparent background
                if hasattr(self, 'original_background_pixmap') and self.original_background_pixmap:
                    bg_path = self.original_background_pixmap.cacheKey()
                    default_path = os.path.join(self.preview_dir, "images", "default.png")
                    
                    # If it's not the default transparent background, draw it
                    bg_pixmap = self.background_pixmap
                    
                    # Calculate position to center the pixmap
                    x = (self.canvas.width() - bg_pixmap.width()) // 2
                    y = (self.canvas.height() - bg_pixmap.height()) // 2
                    
                    # Draw the pixmap
                    painter.drawPixmap(x, y, bg_pixmap)
            
            # Draw the bezel if it's visible
            if hasattr(self, 'bezel_visible') and self.bezel_visible and hasattr(self, 'bezel_pixmap') and not self.bezel_pixmap.isNull():
                bezel_pixmap = self.bezel_pixmap
                # Position bezel in center
                x = (self.canvas.width() - bezel_pixmap.width()) // 2
                y = (self.canvas.height() - bezel_pixmap.height()) // 2
                painter.drawPixmap(x, y, bezel_pixmap)
            
            # Draw the logo if visible
            if hasattr(self, 'logo_label') and self.logo_label and self.logo_label.isVisible():
                logo_pixmap = self.logo_label.pixmap()
                if logo_pixmap and not logo_pixmap.isNull():
                    painter.drawPixmap(self.logo_label.pos(), logo_pixmap)
            
            # Draw control labels with color preservation
            if hasattr(self, 'control_labels'):
                for control_name, control_data in self.control_labels.items():
                    label = control_data['label']
                    
                    # Skip if not visible
                    if not label.isVisible():
                        continue
                    
                    # Get font and position information
                    font = label.font()
                    painter.setFont(font)
                    metrics = QFontMetrics(font)
                    
                    # Get label position
                    pos = label.pos()
                    label_width = label.width()
                    
                    # Get settings and properties from the label
                    settings = getattr(label, 'settings', {})
                    prefix = getattr(label, 'prefix', '')
                    action = getattr(label, 'action', label.text())
                    
                    # Calculate vertical position - centered in the label
                    y = int(pos.y() + (label.height() + metrics.ascent() - metrics.descent()) / 2)
                    
                    # Handle colored/gradient text
                    if prefix and ": " in label.text():
                        prefix_text = f"{prefix}: "
                        
                        # Calculate widths for centering - Using width() for Qt compatibility
                        prefix_width = metrics.width(prefix_text)
                        action_width = metrics.width(action)
                        total_width = prefix_width + action_width
                        
                        # Center the text within the label
                        x = int(pos.x() + (label_width - total_width) / 2)
                        
                        # Draw prefix with its color or gradient
                        if hasattr(label, 'use_prefix_gradient') and getattr(label, 'use_prefix_gradient', False):
                            # Handle gradient prefix
                            start_color = getattr(label, 'prefix_gradient_start', 
                                                QColor(settings.get("prefix_gradient_start", "#FFC107")))
                            end_color = getattr(label, 'prefix_gradient_end', 
                                            QColor(settings.get("prefix_gradient_end", "#FF5722")))
                            
                            # Create gradient
                            prefix_rect = metrics.boundingRect(prefix_text)
                            prefix_rect.moveLeft(int(x))
                            prefix_rect.moveTop(int(y - metrics.ascent()))
                            
                            # Create vertical gradient (top to bottom)
                            gradient = QLinearGradient(
                                prefix_rect.left(), prefix_rect.top(),
                                prefix_rect.left(), prefix_rect.bottom()
                            )
                            # Set colors in top-to-bottom order
                            gradient.setColorAt(0, start_color)
                            gradient.setColorAt(1, end_color)
                            
                            # Apply gradient
                            painter.setPen(QPen(QBrush(gradient), 1))
                        else:
                            # Solid color
                            prefix_color = QColor(settings.get("prefix_color", "#FFC107"))
                            painter.setPen(prefix_color)
                        
                        # Draw prefix
                        painter.drawText(int(x), int(y), prefix_text)
                        
                        # Draw action text with its color or gradient
                        if hasattr(label, 'use_action_gradient') and getattr(label, 'use_action_gradient', False):
                            # Handle gradient action
                            start_color = getattr(label, 'action_gradient_start', 
                                                QColor(settings.get("action_gradient_start", "#2196F3")))
                            end_color = getattr(label, 'action_gradient_end', 
                                            QColor(settings.get("action_gradient_end", "#4CAF50")))
                            
                            # Create gradient
                            action_rect = metrics.boundingRect(action)
                            action_rect.moveLeft(int(x + prefix_width))
                            action_rect.moveTop(int(y - metrics.ascent()))
                            
                            # Create vertical gradient (top to bottom)
                            gradient = QLinearGradient(
                                action_rect.left(), action_rect.top(),
                                action_rect.left(), action_rect.bottom()
                            )
                            # Set colors in top-to-bottom order
                            gradient.setColorAt(0, start_color)
                            gradient.setColorAt(1, end_color)
                            
                            # Apply gradient
                            painter.setPen(QPen(QBrush(gradient), 1))
                        else:
                            # Solid color
                            action_color = QColor(settings.get("action_color", "#FFFFFF"))
                            painter.setPen(action_color)
                        
                        # Draw action
                        painter.drawText(int(x + prefix_width), int(y), action)
                    else:
                        # Single text - center it
                        text_width = metrics.width(label.text())
                        x = int(pos.x() + (label_width - text_width) / 2)
                        
                        # Use action color/gradient for the whole text
                        if hasattr(label, 'use_action_gradient') and getattr(label, 'use_action_gradient', False):
                            # Handle gradient
                            start_color = getattr(label, 'action_gradient_start', 
                                                QColor(settings.get("action_gradient_start", "#2196F3")))
                            end_color = getattr(label, 'action_gradient_end', 
                                            QColor(settings.get("action_gradient_end", "#4CAF50")))
                            
                            # Create gradient
                            text_rect = metrics.boundingRect(label.text())
                            text_rect.moveLeft(int(x))
                            text_rect.moveTop(int(y - metrics.ascent()))
                            
                            # Create vertical gradient (top to bottom)
                            gradient = QLinearGradient(
                                text_rect.left(), text_rect.top(),
                                text_rect.left(), text_rect.bottom()
                            )
                            # Set colors in top-to-bottom order
                            gradient.setColorAt(0, start_color)
                            gradient.setColorAt(1, end_color)
                            
                            # Apply gradient
                            painter.setPen(QPen(QBrush(gradient), 1))
                        else:
                            # Solid color
                            action_color = QColor(settings.get("action_color", "#FFFFFF"))
                            painter.setPen(action_color)
                        
                        # Draw text
                        painter.drawText(int(x), int(y), label.text())
            
            # End painting
            painter.end()
            
            # Save the image as PNG to preserve transparency
            if image.save(output_path, "PNG"):
                print(f"Image saved successfully to {output_path}")
                QMessageBox.information(
                    self,
                    "Success",
                    f"Image saved to:\n{output_path}"
                )
                return True
            else:
                print(f"Failed to save image to {output_path}")
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Failed to save image. Could not write to file."
                )
                return False
                
        except Exception as e:
            print(f"Error saving image: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save image: {str(e)}"
            )
            return False

    def handle_key_press(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key_Escape:
            # Close the window
            self.close()
            
            # If this is a standalone preview, also exit the application
            if getattr(self, 'standalone_mode', False):
                # Give a short delay before quitting to allow cleanup
                QTimer.singleShot(100, QApplication.quit)
    
    # Make sure the window is full screen without borders
    def set_fullscreen(self):
        """Make the window truly fullscreen without borders"""
        # Get screen geometry
        screen_rect = QApplication.desktop().screenGeometry(self.current_screen - 1)  # -1 for 0-based index
        
        # Set window to exactly screen size
        self.setGeometry(screen_rect)
        
        # Remove window frame
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        
        # Update window
        self.show()
        
        print(f"Set window to full screen: {screen_rect.width()}x{screen_rect.height()}")
    
    # Modify move_to_screen to ensure full screen
    def move_to_screen(self, screen_index):
        """Move window to specified screen with true fullscreen"""
        try:
            desktop = QDesktopWidget()
            if desktop.screenCount() < screen_index:
                print(f"Screen {screen_index} not available, using screen 1")
                screen_index = 1

            screen_geometry = desktop.screenGeometry(screen_index - 1)  # Convert to 0-based index

            # Only update current_screen if not in initial load mode
            if not getattr(self, 'initializing_screen', False):
                self.current_screen = screen_index
            else:
                print(f"[INIT MOVE] Moving to screen {screen_index} without overwriting current_screen ({self.current_screen})")

            # To reduce flashing, only update flags once
            if not (self.windowFlags() & Qt.FramelessWindowHint):
                self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
                self.show()

            self.setGeometry(screen_geometry)
            QTimer.singleShot(100, self.check_dimensions)

            print(f"Window moved to screen {screen_index} in fullscreen mode")
        except Exception as e:
            print(f"Error moving to screen: {e}")
            import traceback
            traceback.print_exc()

            
    def check_dimensions(self):
        """Debug method to check actual dimensions after fullscreen is applied"""
        print(f"After fullscreen - Window: {self.width()}x{self.height()}, Canvas: {self.canvas.width()}x{self.canvas.height()}")
        print(f"Central widget: {self.central_widget.width()}x{self.central_widget.height()}")
        
        # If canvas isn't filling window, force its size
        if self.canvas.width() < self.width() or self.canvas.height() < self.height():
            print("Canvas smaller than window, forcing size match")
            self.canvas.setGeometry(0, 0, self.width(), self.height())
    
    def toggle_screen(self):
        """Toggle between screens with improved reliability"""
        desktop = QDesktopWidget()
        num_screens = desktop.screenCount()
        
        if num_screens < 2:
            print("Only one screen available")
            return
            
        # Get target screen (toggling between 1 and 2)
        target_screen = 1 if self.current_screen == 2 else 2
        
        # Update button text
        self.screen_button.setText(f"Screen {target_screen}")
        
        # Important: Pre-update the current_screen value BEFORE calling move_to_screen
        old_screen = self.current_screen
        self.current_screen = target_screen
        
        print(f"Toggle screen: Changing from {old_screen} to {target_screen}")
        
        # Now call move_to_screen with the new value
        self.move_to_screen(target_screen)
    
    # Add a method to force controls above the bezel
    def force_controls_above_bezel(self):
        """Force all control elements to be above the bezel"""
        if not hasattr(self, 'bezel_label') or not self.bezel_label:
            return
        
        # Raise all control labels
        if hasattr(self, 'control_labels'):
            for control_data in self.control_labels.values():
                if 'label' in control_data and control_data['label']:
                    control_data['label'].raise_()
        
        # Raise logo if it exists
        if hasattr(self, 'logo_label') and self.logo_label:
            self.logo_label.raise_()
        
        print("All controls raised above bezel")

    def initialize_transparent_background(self):
        """Create and ensure a blank transparent background exists before displaying preview"""
        try:
            # Use absolute paths to ensure correct location
            images_dir = os.path.abspath(os.path.join(self.preview_dir, "images"))
            os.makedirs(images_dir, exist_ok=True)
            
            default_path = os.path.join(images_dir, "default.png")
            print(f"Checking for default background at: {default_path}")
            
            # Create the transparent image if it doesn't exist
            if not os.path.exists(default_path):
                print("Creating new transparent background image...")
                
                # Create a transparent image at 1920x1080 resolution
                from PyQt5.QtGui import QImage
                default_image = QImage(1920, 1080, QImage.Format_ARGB32)
                default_image.fill(Qt.transparent)  # Completely transparent
                
                # Save the image
                try:
                    success = default_image.save(default_path, "PNG")
                    if success:
                        print(f"Successfully created transparent background at: {default_path}")
                    else:
                        print(f"Failed to save transparent background to {default_path}")
                except Exception as e:
                    print(f"Exception while saving transparent background: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"Transparent background already exists at: {default_path}")
            
            return default_path
        except Exception as e:
            print(f"Error creating transparent background: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # You'll also need to modify the load_background_image_fullscreen method to accept a forced default:
    def load_background_image_fullscreen(self, force_default=None):
        """Load the background image for the game with improved path handling"""
        try:
            image_path = None
            
            # If force_default is provided, use it directly
            if force_default and os.path.exists(force_default):
                image_path = force_default
                print(f"Using forced default background: {image_path}")
            else:
                # First check for game-specific image in preview directory
                possible_paths = [
                    # First look in preview/images directory
                    os.path.join(self.preview_dir, "images", f"{self.rom_name}.png"),
                    os.path.join(self.preview_dir, "images", f"{self.rom_name}.jpg"),
                    
                    # Then check in preview root
                    os.path.join(self.preview_dir, f"{self.rom_name}.png"),
                    os.path.join(self.preview_dir, f"{self.rom_name}.jpg"),
                    
                    # Default images
                    os.path.join(self.preview_dir, "images", "default.png"),
                    os.path.join(self.preview_dir, "images", "default.jpg"),
                    os.path.join(self.preview_dir, "default.png"),
                    os.path.join(self.preview_dir, "default.jpg"),
                ]
                
                # Find the first existing image path
                for path in possible_paths:
                    if os.path.exists(path):
                        image_path = path
                        print(f"Found background image: {image_path}")
                        break
                
                # If no image found, use initialize_transparent_background to create one
                if not image_path:
                    image_path = self.initialize_transparent_background()
                    
            # Set background image if found or created
            if image_path:
                # Create background label with image
                self.bg_label = QLabel(self.canvas)
                
                # Load the original pixmap without scaling yet
                original_pixmap = QPixmap(image_path)
                
                if original_pixmap.isNull():
                    print(f"Error: Could not load image from {image_path}")
                    self.bg_label.setText("Error loading background image")
                    self.bg_label.setStyleSheet("color: red; font-size: 18px;")
                    self.bg_label.setAlignment(Qt.AlignCenter)
                    return
                
                # Store the original pixmap for high-quality saving later
                self.original_background_pixmap = original_pixmap
                
                # Create a high-quality scaled version to display
                # Calculate aspect ratio preserving fit
                canvas_w = self.canvas.width()
                canvas_h = self.canvas.height()
                
                # Calculate the scaled size that fills the canvas while preserving aspect ratio
                scaled_pixmap = original_pixmap.scaled(
                    canvas_w, 
                    canvas_h, 
                    Qt.KeepAspectRatio,  # Preserve aspect ratio
                    Qt.SmoothTransformation  # High quality scaling
                )
                
                # Store the properly scaled pixmap
                self.background_pixmap = scaled_pixmap
                
                # Set it on the label
                self.bg_label.setPixmap(scaled_pixmap)
                
                # Position the background image in the center
                x = (canvas_w - scaled_pixmap.width()) // 2
                y = (canvas_h - scaled_pixmap.height()) // 2
                self.bg_label.setGeometry(x, y, scaled_pixmap.width(), scaled_pixmap.height())
                
                # Store the background position for control positioning
                self.bg_pos = (x, y)
                self.bg_size = (scaled_pixmap.width(), scaled_pixmap.height())
                
                # Make sure the background is below everything
                self.bg_label.lower()
                
                print(f"Background loaded: {scaled_pixmap.width()}x{scaled_pixmap.height()}, positioned at ({x},{y})")
                
                # Update when window resizes
                self.canvas.resizeEvent = self.on_canvas_resize_with_background
            else:
                # Fallback to a transparent background
                print("Could not create or find a background image, using transparent background")
                self.bg_label = QLabel(self.canvas)
                self.bg_label.setStyleSheet("background-color: transparent;")
                self.bg_label.setGeometry(0, 0, self.canvas.width(), self.canvas.height())
        except Exception as e:
            print(f"Error loading background image: {e}")
            import traceback
            traceback.print_exc()
            # Handle error by showing message on canvas
            if hasattr(self, 'bg_label') and self.bg_label:
                self.bg_label.setText(f"Error loading image: {str(e)}")
                self.bg_label.setStyleSheet("color: red; font-size: 18px;")
                self.bg_label.setAlignment(Qt.AlignCenter)
            else:
                self.bg_label = QLabel(f"Error: {str(e)}", self.canvas)
                self.bg_label.setStyleSheet("color: red; font-size: 18px;")
                self.bg_label.setAlignment(Qt.AlignCenter)
                self.bg_label.setGeometry(0, 0, self.canvas.width(), self.canvas.height())

    def update_logo_display(self):
        """Update the logo display based on current settings with improved centering"""
        if not hasattr(self, 'logo_label') or not self.logo_label:
            print("No logo label to update")
            return
        
        # Make sure we have the original pixmap
        if not hasattr(self, 'original_logo_pixmap') or not self.original_logo_pixmap or self.original_logo_pixmap.isNull():
            # If we don't have original, use current pixmap as original
            self.original_logo_pixmap = self.logo_label.pixmap()
            if not self.original_logo_pixmap or self.original_logo_pixmap.isNull():
                print("No logo pixmap available to resize")
                return
        
        # Get current canvas dimensions 
        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        
        # Get size percentages from settings
        width_percent = self.logo_settings.get("width_percentage", 15) / 100
        height_percent = self.logo_settings.get("height_percentage", 15) / 100
        
        # Calculate pixel dimensions based on percentages
        target_width = int(canvas_width * width_percent)
        target_height = int(canvas_height * height_percent)
        
        print(f"Logo target size: {target_width}x{target_height} pixels ({width_percent*100:.1f}%, {height_percent*100:.1f}%)")
        
        # Get original size for reference
        orig_width = self.original_logo_pixmap.width()
        orig_height = self.original_logo_pixmap.height()
        
        # Handle aspect ratio if needed
        if self.logo_settings.get("maintain_aspect", True):
            orig_ratio = orig_width / orig_height if orig_height > 0 else 1
            
            # Calculate dimensions preserving aspect ratio
            if (target_width / target_height) > orig_ratio:
                # Height is limiting factor
                final_height = target_height
                final_width = int(final_height * orig_ratio)
            else:
                # Width is limiting factor
                final_width = target_width
                final_height = int(final_width / orig_ratio)
        else:
            # Use target dimensions directly
            final_width = target_width
            final_height = target_height
        
        # Apply minimum size constraints
        final_width = max(30, final_width)
        final_height = max(20, final_height)
        
        # Scale the original pixmap to the calculated size
        scaled_pixmap = self.original_logo_pixmap.scaled(
            final_width, 
            final_height, 
            Qt.KeepAspectRatio if self.logo_settings.get("maintain_aspect", True) else Qt.IgnoreAspectRatio, 
            Qt.SmoothTransformation
        )
        
        # Set the pixmap on the label
        self.logo_label.setPixmap(scaled_pixmap)
        
        # Resize the label to match pixmap
        self.logo_label.resize(scaled_pixmap.width(), scaled_pixmap.height())
        
        # Position the logo based on settings
        logo_position = self.logo_settings.get("logo_position", "")
        is_centered = logo_position == "center"
        
        # NEW: Center overrides custom position - always center if center position is selected
        if is_centered:
            # Calculate center position
            x = (canvas_width - scaled_pixmap.width()) // 2
            y = (canvas_height - scaled_pixmap.height()) // 2
            
            # Update the position in settings too (important for saving later)
            self.logo_settings["x_position"] = x
            self.logo_settings["y_position"] = y
            
            print(f"Logo centered at ({x}, {y})")
        elif self.logo_settings.get("custom_position", False) and "x_position" in self.logo_settings and "y_position" in self.logo_settings:
            # Use custom position
            x = self.logo_settings.get("x_position", 20)
            y = self.logo_settings.get("y_position", 20)
            print(f"Using custom logo position: ({x}, {y})")
        else:
            # Use position based on selected preset
            self.position_logo(logo_position)
            return  # position_logo handles the actual move
        
        # Move to position
        self.logo_label.move(x, y)
        
        print(f"Logo display updated: {scaled_pixmap.width()}x{scaled_pixmap.height()} pixels")


    def center_logo(self):
        """Center the logo horizontally in the canvas while preserving Y position"""
        if not hasattr(self, 'logo_label') or not self.logo_label:
            print("No logo to center")
            return False

        # Get canvas and logo dimensions
        canvas_width = self.canvas.width()
        logo_width = self.logo_label.width()
        
        # Get current Y position
        current_pos = self.logo_label.pos()
        current_y = current_pos.y()

        # Calculate center X position
        x = (canvas_width - logo_width) // 2

        # Move logo to new X position, keeping current Y
        self.logo_label.move(x, current_y)

        # Update settings to enable horizontal centering
        self.logo_settings["keep_horizontally_centered"] = True
        self.logo_settings["custom_position"] = True
        self.logo_settings["x_position"] = x
        self.logo_settings["y_position"] = current_y

        # Save to file immediately to persist across ROM changes
        if hasattr(self, 'save_logo_settings'):
            self.save_logo_settings(is_global=True)

        print(f"Logo horizontally centered at X={x}, Y remains {current_y}")
        return True

    def force_logo_resize(self):
        """Force logo to resize according to current settings with persistent horizontal centering"""
        if not hasattr(self, 'logo_label') or not self.logo_label:
            print("No logo label to resize")
            return False
            
        if not hasattr(self, 'original_logo_pixmap') or self.original_logo_pixmap.isNull():
            # Try to load the logo image again
            logo_path = self.find_logo_path(self.rom_name)
            if not logo_path:
                print("Cannot force resize - no logo image found")
                return False
                
            self.original_logo_pixmap = QPixmap(logo_path)
            if self.original_logo_pixmap.isNull():
                print("Cannot force resize - failed to load logo image")
                return False
        
        # Get canvas and logo dimensions
        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        
        # Calculate target size
        width_percent = float(self.logo_settings.get("width_percentage", 15))
        height_percent = float(self.logo_settings.get("height_percentage", 15))
        
        target_width = int((width_percent / 100) * canvas_width)
        target_height = int((height_percent / 100) * canvas_height)
        
        print(f"Force-resizing logo to {target_width}x{target_height} pixels " +
            f"({width_percent:.1f}%, {height_percent:.1f}%)")
        
        # Scale the pixmap to the target size
        if self.logo_settings.get("maintain_aspect", True):
            scaled_pixmap = self.original_logo_pixmap.scaled(
                target_width, 
                target_height, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
        else:
            scaled_pixmap = self.original_logo_pixmap.scaled(
                target_width, 
                target_height, 
                Qt.IgnoreAspectRatio, 
                Qt.SmoothTransformation
            )
        
        # Apply the scaled pixmap
        self.logo_label.setPixmap(scaled_pixmap)
        
        # Ensure label size matches pixmap size
        self.logo_label.resize(scaled_pixmap.width(), scaled_pixmap.height())
        
        # Check if horizontal centering is enabled
        is_horizontally_centered = self.logo_settings.get("keep_horizontally_centered", False)
        
        # Position the logo
        if is_horizontally_centered:
            # Recalculate horizontal center with new dimensions
            x = (canvas_width - scaled_pixmap.width()) // 2
            y = self.logo_settings.get("y_position", 20)  # Use stored Y position
            
            # Move logo to new position
            self.logo_label.move(x, y)
            
            # Update X position in settings
            self.logo_settings["x_position"] = x
            
            print(f"Logo horizontally centered at X={x}, Y={y} after resize")
        else:
            # Use custom position
            x = self.logo_settings.get("x_position", 20)
            y = self.logo_settings.get("y_position", 20)
            self.logo_label.move(x, y)
            print(f"Logo positioned at custom ({x}, {y}) after resize")
        
        print(f"Logo resized to {scaled_pixmap.width()}x{scaled_pixmap.height()} pixels")
        return True

    # 5. Update the on_canvas_resize_with_background method to maintain centering
    def on_canvas_resize_with_background(self, event):
        """Handle canvas resize while maintaining proper layer stacking and logo centering"""
        try:
            print("\n--- Canvas resize with bezel and logo handling ---")
            
            # Recalculate the background image position and scaling
            if hasattr(self, 'original_background_pixmap') and not self.original_background_pixmap.isNull():
                # Get the original unscaled pixmap
                original_pixmap = self.original_background_pixmap
                
                # Create a high-quality scaled version to fill the canvas
                canvas_w = self.canvas.width()
                canvas_h = self.canvas.height()
                
                # Scale with high quality while preserving aspect ratio
                scaled_pixmap = original_pixmap.scaled(
                    canvas_w, 
                    canvas_h, 
                    Qt.KeepAspectRatio,  # Preserve aspect ratio
                    Qt.SmoothTransformation  # High quality scaling
                )
                
                # Update the stored pixmap
                self.background_pixmap = scaled_pixmap
                
                # Update the bg_label with the newly scaled pixmap
                if hasattr(self, 'bg_label') and self.bg_label:
                    self.bg_label.setPixmap(scaled_pixmap)
                    
                    # Center the background
                    x = (canvas_w - scaled_pixmap.width()) // 2
                    y = (canvas_h - scaled_pixmap.height()) // 2
                    self.bg_label.setGeometry(x, y, scaled_pixmap.width(), scaled_pixmap.height())
                    
                    # Store the background position for control positioning
                    self.bg_pos = (x, y)
                    self.bg_size = (scaled_pixmap.width(), scaled_pixmap.height())
                    
                    # Make sure the background is below everything
                    self.bg_label.lower()
                    
                    print(f"Background resized: {scaled_pixmap.width()}x{scaled_pixmap.height()}, positioned at ({x},{y})")
            
            # Also update bezel if it's visible
            if hasattr(self, 'bezel_visible') and self.bezel_visible and hasattr(self, 'bezel_label') and self.bezel_label:
                # Resize the bezel to match the new canvas size
                if hasattr(self, 'original_bezel_pixmap') and not self.original_bezel_pixmap.isNull():
                    canvas_w = self.canvas.width()
                    canvas_h = self.canvas.height()
                    
                    bezel_pixmap = self.original_bezel_pixmap.scaled(
                        canvas_w,
                        canvas_h,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    
                    self.bezel_pixmap = bezel_pixmap
                    self.bezel_label.setPixmap(bezel_pixmap)
                    
                    # Position bezel in center
                    x = (canvas_w - bezel_pixmap.width()) // 2
                    y = (canvas_h - bezel_pixmap.height()) // 2
                    self.bezel_label.setGeometry(x, y, bezel_pixmap.width(), bezel_pixmap.height())
                    
                    print(f"Bezel resized: {bezel_pixmap.width()}x{bezel_pixmap.height()}, positioned at ({x},{y})")
            
            # Update logo positioning
            self.handle_logo_during_resize()

            # Redraw grid if it's currently visible
            if hasattr(self, 'alignment_grid_visible') and self.alignment_grid_visible:
                self.show_alignment_grid()
                    
            # Fix layering again after resize
            QTimer.singleShot(100, self.raise_controls_above_bezel)
            
            # Add at the end - force resize all labels
            QTimer.singleShot(100, self.force_resize_all_labels)
                
        except Exception as e:
            print(f"Error in canvas resize: {e}")
            import traceback
            traceback.print_exc()

    def save_logo_settings_global(self):
        """Save logo settings globally to ensure they persist across ROM changes"""
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Save to global settings file
            settings_file = os.path.join(self.settings_dir, "logo_settings.json")
            
            with open(settings_file, 'w') as f:
                json.dump(self.logo_settings, f)
                
            print(f"Saved global logo settings to: {settings_file}")
            print(f"Settings: {self.logo_settings}")
            return True
        except Exception as e:
            print(f"Error saving global logo settings: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def check_layer_visibility(self):
        """Print diagnostic information about layer visibility"""
        print("\n----- LAYER VISIBILITY CHECK -----")
        
        # Check background
        if hasattr(self, 'bg_label') and self.bg_label:
            print(f"Background: {'VISIBLE' if self.bg_label.isVisible() else 'HIDDEN'}")
            if self.bg_label.pixmap():
                print(f"  Size: {self.bg_label.pixmap().width()}x{self.bg_label.pixmap().height()}")
            else:
                print("  No pixmap loaded")
        else:
            print("Background: NOT CREATED")
        
        # Check bezel
        if hasattr(self, 'bezel_label') and self.bezel_label:
            print(f"Bezel: {'VISIBLE' if self.bezel_label.isVisible() else 'HIDDEN'}")
            if self.bezel_label.pixmap():
                print(f"  Size: {self.bezel_label.pixmap().width()}x{self.bezel_label.pixmap().height()}")
            else:
                print("  No pixmap loaded")
        else:
            print("Bezel: NOT CREATED")
        
        # Check logo
        if hasattr(self, 'logo_label') and self.logo_label:
            print(f"Logo: {'VISIBLE' if self.logo_label.isVisible() else 'HIDDEN'}")
            if self.logo_label.pixmap():
                print(f"  Size: {self.logo_label.pixmap().width()}x{self.logo_label.pixmap().height()}")
            else:
                print("  No pixmap loaded")
        else:
            print("Logo: NOT CREATED")
        
        # Check controls (sample)
        if hasattr(self, 'control_labels') and self.control_labels:
            visible_controls = sum(1 for c in self.control_labels.values() 
                                if 'label' in c and c['label'] and c['label'].isVisible())
            print(f"Controls: {visible_controls} visible out of {len(self.control_labels)} total")
        else:
            print("Controls: NOT CREATED")
        
        print("--------------------------------")

        self.check_layer_visibility()
    
    def on_canvas_resize(self, event):
        """Handle canvas resize to update background image"""
        try:
            # Resize and center the background image
            if hasattr(self, 'bg_label'):
                # Get the original pixmap
                pixmap = self.bg_label.pixmap()
                if pixmap and not pixmap.isNull():
                    # Resize to fill the canvas, stretching it
                    new_pixmap = pixmap.scaled(
                        self.canvas.width(), 
                        self.canvas.height(), 
                        Qt.IgnoreAspectRatio,  # Stretch to fill the canvas without keeping aspect ratio
                        Qt.SmoothTransformation
                    )
                    self.bg_label.setPixmap(new_pixmap)
                    
                    # Center the background
                    self.center_background()
            
            # Also update control positions
            self.update_control_positions()
                    
            # Call the original QWidget resize event directly instead of using super()
            QWidget.resizeEvent(self.canvas, event)
            
        except Exception as e:
            print(f"Error in on_canvas_resize: {e}")
            import traceback
            traceback.print_exc()

    
    def center_background(self):
        """Center the background image in the canvas"""
        if hasattr(self, 'bg_label') and self.bg_label.pixmap():
            pixmap = self.bg_label.pixmap()
            # Calculate position to center the pixmap
            x = (self.canvas.width() - pixmap.width()) // 2
            y = (self.canvas.height() - pixmap.height()) // 2
            self.bg_label.setGeometry(x, y, pixmap.width(), pixmap.height())
            
            # Store the background position for control positioning
            self.bg_pos = (x, y)
            self.bg_size = (pixmap.width(), pixmap.height())
    
    def load_text_settings(self):
        """Load text appearance settings from new settings directory"""
        settings = {
            "font_family": "Arial",
            "font_size": 28,
            "bold_strength": 2,
            "use_uppercase": False,
            "y_offset": -40,
            "show_button_prefix": True,
            "prefix_color": "#FFC107",  # Default prefix color (amber)
            "action_color": "#FFFFFF",  # Default action text color (white)
            # Add default gradient settings
            "use_prefix_gradient": False,
            "use_action_gradient": False,
            "prefix_gradient_start": "#FFC107",
            "prefix_gradient_end": "#FF5722",
            "action_gradient_start": "#2196F3",
            "action_gradient_end": "#4CAF50"
        }
        
        try:
            # First try the new settings directory
            settings_file = os.path.join(self.settings_dir, "text_appearance_settings.json")
            
            # Regular loading from new location
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
                    
                # Debug gradient settings
                prefix_gradient = settings.get("use_prefix_gradient", False)
                action_gradient = settings.get("use_action_gradient", False)
                print(f"Loaded gradient settings: prefix={prefix_gradient}, action={action_gradient}")
        except Exception as e:
            print(f"Error loading text appearance settings: {e}")
            import traceback
            traceback.print_exc()
        
        return settings
    
    # Update the save_text_settings method in PreviewWindow
    def save_text_settings(self, settings):
        """Save text appearance settings to file in settings directory"""
        try:
            # Update local settings
            self.text_settings.update(settings)
            
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Save to settings file in settings directory
            settings_file = os.path.join(self.settings_dir, "text_appearance_settings.json")
            
            with open(settings_file, 'w') as f:
                json.dump(self.text_settings, f)
            print(f"Saved text settings to {settings_file}: {self.text_settings}")
        except Exception as e:
            print(f"Error saving text settings: {e}")
            import traceback
            traceback.print_exc()
          
    def on_label_press(self, event, label):
        """Handle mouse press on label"""
        from PyQt5.QtCore import Qt
        
        if event.button() == Qt.LeftButton:
            # Make sure draggable flag is set
            label.dragging = True
            label.drag_start_pos = event.pos()
            label.setCursor(Qt.ClosedHandCursor)
            event.accept()

    # 4. Update on_label_move method to remove shadow parameter and handling
    def on_label_move(self, event, label, orig_func=None):
        """Handle label movement without shadow updates"""
        # If we should use the original function, do that
        if orig_func is not None:
            # Call the original mouseMoveEvent method for the label
            orig_func(event)
            return
            
        # Direct handling (if orig_func is None)
        if hasattr(label, 'dragging') and label.dragging:
            # Get the current mouse position
            delta = event.pos() - label.drag_start_pos
            
            # FIXED: Use original position + delta to preserve offset
            if hasattr(label, 'original_label_pos'):
                new_pos = label.original_label_pos + delta
            else:
                # Fallback to mapToParent
                new_pos = label.mapToParent(event.pos() - label.drag_start_pos)
            
            # Initialize guide lines list and snapping variables
            guide_lines = []
            snapped = False
            canvas_width = self.canvas.width()
            canvas_height = self.canvas.height()
            
            # Check if snapping is enabled and not overridden
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtCore import Qt
            modifiers = QApplication.keyboardModifiers()
            disable_snap = bool(modifiers & Qt.ShiftModifier)  # Shift key disables snapping temporarily
            
            apply_snapping = (
                not disable_snap and
                hasattr(self, 'snapping_enabled') and
                self.snapping_enabled
            )
            
            # Get snap distance if available
            snap_distance = getattr(self, 'snap_distance', 15)
            
            if apply_snapping:
                # Get label center coordinates
                label_center_x = new_pos.x() + label.width() // 2
                label_center_y = new_pos.y() + label.height() // 2
                
                # 1. Absolute grid position snapping (if enabled)
                if (hasattr(self, 'snap_to_grid') and self.snap_to_grid and
                    hasattr(self, 'grid_x_start') and hasattr(self, 'grid_y_start')):
                    
                    grid_x_start = self.grid_x_start
                    grid_x_step = self.grid_x_step
                    
                    # Snap to column X positions
                    for col in range(self.grid_columns):
                        grid_x = grid_x_start + (col * grid_x_step)
                        if abs(new_pos.x() - grid_x) < snap_distance:
                            new_pos.setX(grid_x)
                            guide_lines.append((grid_x, 0, grid_x, canvas_height))
                            snapped = True
                            break
                    
                    # Snap to row Y positions
                    grid_y_start = self.grid_y_start
                    grid_y_step = self.grid_y_step
                    
                    for row in range(self.grid_rows):
                        grid_y = grid_y_start + (row * grid_y_step)
                        if abs(new_pos.y() - grid_y) < snap_distance:
                            new_pos.setY(grid_y)
                            guide_lines.append((0, grid_y, canvas_width, grid_y))
                            snapped = True
                            break
                
                # 2. Screen center alignment (if enabled)
                if hasattr(self, 'snap_to_screen_center') and self.snap_to_screen_center:
                    # Horizontal center
                    screen_center_x = canvas_width // 2
                    if abs(label_center_x - screen_center_x) < snap_distance:
                        new_pos.setX(int(screen_center_x - label.width() / 2))
                        guide_lines.append((screen_center_x, 0, screen_center_x, canvas_height))
                        snapped = True
                    
                    # Vertical center
                    screen_center_y = canvas_height // 2
                    if abs(label_center_y - screen_center_y) < snap_distance:
                        new_pos.setY(int(screen_center_y - label.height() / 2))
                        guide_lines.append((0, screen_center_y, canvas_width, screen_center_y))
                        snapped = True
                
                # 3. Check alignment with other controls (if enabled)
                if (hasattr(self, 'snap_to_controls') and self.snap_to_controls and
                    hasattr(self, 'control_labels')):
                    
                    for control_name, control_data in self.control_labels.items():
                        other_label = control_data.get('label')
                        if other_label is label or not other_label or not other_label.isVisible():
                            continue
                        
                        # X-position alignment - snap to left edge of other labels
                        other_x = other_label.pos().x()
                        if abs(new_pos.x() - other_x) < snap_distance:
                            new_pos.setX(other_x)
                            guide_lines.append((other_x, 0, other_x, canvas_height))
                            snapped = True
                        
                        # Y-position alignment - snap to top edge of other labels
                        other_y = other_label.pos().y()
                        if abs(new_pos.y() - other_y) < snap_distance:
                            new_pos.setY(other_y)
                            guide_lines.append((0, other_y, canvas_width, other_y))
                            snapped = True
                
                # 4. Check alignment with logo (if enabled)
                if (hasattr(self, 'snap_to_logo') and self.snap_to_logo and
                    hasattr(self, 'logo_label') and self.logo_label and
                    self.logo_label.isVisible()):
                    
                    logo = self.logo_label
                    
                    # Left edge alignment (absolute X position)
                    logo_left = logo.pos().x()
                    if abs(new_pos.x() - logo_left) < snap_distance:
                        new_pos.setX(logo_left)
                        guide_lines.append((logo_left, 0, logo_left, canvas_height))
                        snapped = True
                    
                    # Top edge alignment
                    logo_top = logo.pos().y()
                    if abs(new_pos.y() - logo_top) < snap_distance:
                        new_pos.setY(logo_top)
                        guide_lines.append((0, logo_top, canvas_width, logo_top))
                        snapped = True
            
            # 5. Show dynamic measurement guides
            if hasattr(self, 'show_measurement_guides'):
                try:
                    self.show_measurement_guides(
                        new_pos.x(), new_pos.y(), 
                        label.width(), label.height()
                    )
                except Exception as e:
                    print(f"Error showing measurement guides: {e}")

            # Add snapping status info if needed
            if disable_snap and hasattr(self, 'show_position_indicator'):
                try:
                    self.show_position_indicator(
                        new_pos.x(), new_pos.y(), 
                        "Snapping temporarily disabled (Shift)"
                    )
                except Exception as e:
                    print(f"Error showing position indicator with status: {e}")
            
            # Show alignment guides if snapped
            if snapped and guide_lines and hasattr(self, 'show_alignment_guides'):
                try:
                    self.show_alignment_guides(guide_lines)
                except Exception as e:
                    print(f"Error showing alignment guides: {e}")
            elif hasattr(self, 'hide_alignment_guides'):
                try:
                    self.hide_alignment_guides()
                except Exception as e:
                    print(f"Error hiding alignment guides: {e}")
            
            # Move the label
            label.move(new_pos)
            
            # Show position indicator regardless of snapping
            if hasattr(self, 'show_position_indicator'):
                try:
                    self.show_position_indicator(new_pos.x(), new_pos.y())
                except Exception as e:
                    print(f"Error showing position indicator: {e}")
        
        # Let event propagate
        event.accept()

    def on_label_release(self, event, label):
        """Handle mouse release to end dragging"""
        from PyQt5.QtCore import Qt
        
        if event.button() == Qt.LeftButton:
            label.dragging = False
            label.setCursor(Qt.OpenHandCursor)
            
            # Hide guidance elements
            if hasattr(self, 'hide_alignment_guides'):
                self.hide_alignment_guides()
            if hasattr(self, 'hide_measurement_guides'):
                self.hide_measurement_guides()
            if hasattr(self, 'hide_position_indicator'):
                self.hide_position_indicator()
                
            event.accept()
    
    def get_button_prefix(self, control_name):
        """Generate button prefix based on control name"""
        prefixes = {
            'P1_BUTTON1': 'A',
            'P1_BUTTON2': 'B',
            'P1_BUTTON3': 'X',
            'P1_BUTTON4': 'Y',
            'P1_BUTTON5': 'LB',
            'P1_BUTTON6': 'RB', 
            'P1_BUTTON7': 'LT',
            'P1_BUTTON8': 'RT',
            'P1_BUTTON9': 'LS',
            'P1_BUTTON10': 'RS',
            'P1_START': 'START',
            'P1_SELECT': 'BACK',
            'P1_JOYSTICK_UP': 'LS↑',
            'P1_JOYSTICK_DOWN': 'LS↓',
            'P1_JOYSTICK_LEFT': 'LS←',
            'P1_JOYSTICK_RIGHT': 'LS→',
            'P1_JOYSTICK2_UP': 'RS↑',
            'P1_JOYSTICK2_DOWN': 'RS↓',
            'P1_JOYSTICK2_LEFT': 'RS←',
            'P1_JOYSTICK2_RIGHT': 'RS→',
        }
        
        return prefixes.get(control_name, "")
    
    def ensure_clean_layout(self):
        """Ensure all controls are properly laid out in clean mode"""
        # Force a redraw of the canvas
        self.canvas.update()
                
        # If logo exists, make sure it has no border
        if hasattr(self, 'logo_label') and self.logo_label:
            self.logo_label.setStyleSheet("background-color: transparent; border: none;")
            
        print("Clean layout applied - shadows positioned correctly")
    
    # Add or update a method to load saved positions
    def load_saved_positions(self):
        """Load saved positions from ROM-specific or global config with improved error handling"""
        positions = {}
        rom_positions = {}
        global_positions = {}
        
        try:
            print("\n=== Loading saved positions ===")
            # Check for both ROM-specific and global positions (in settings directory)
            rom_positions_file = os.path.join(self.settings_dir, f"{self.rom_name}_positions.json")
            global_positions_file = os.path.join(self.settings_dir, "global_positions.json")
            
            # Log what we're looking for
            print(f"Looking for ROM-specific positions at: {rom_positions_file}")
            print(f"Looking for global positions at: {global_positions_file}")
            
            # First load global positions (as a base)
            if os.path.exists(global_positions_file):
                with open(global_positions_file, 'r') as f:
                    global_positions = json.load(f)
                    print(f"Loaded global positions from {global_positions_file}")
                    print(f"Found {len(global_positions)} global positions")
            else:
                print("No global position file found")
                
                # Check legacy global paths
                legacy_global_paths = [
                    os.path.join(self.preview_dir, "global_positions.json"),
                    os.path.join(self.mame_dir, "global_positions.json")
                ]
                
                for legacy_path in legacy_global_paths:
                    if os.path.exists(legacy_path):
                        print(f"Found legacy global positions at {legacy_path}")
                        with open(legacy_path, 'r') as f:
                            global_positions = json.load(f)
                        
                        # Migrate to new location
                        os.makedirs(self.settings_dir, exist_ok=True)
                        with open(global_positions_file, 'w') as f:
                            json.dump(global_positions, f)
                        
                        print(f"Migrated global positions from {legacy_path} to {global_positions_file}")
                        break
            
            # Then check for ROM-specific positions (which would override globals)
            if os.path.exists(rom_positions_file):
                with open(rom_positions_file, 'r') as f:
                    rom_positions = json.load(f)
                    print(f"Loaded ROM-specific positions for {self.rom_name} from {rom_positions_file}")
                    print(f"Found {len(rom_positions)} ROM-specific positions")
            else:
                print("No ROM-specific position file found")
                
                # Check legacy ROM-specific path
                legacy_rom_path = os.path.join(self.preview_dir, f"{self.rom_name}_positions.json")
                if os.path.exists(legacy_rom_path):
                    print(f"Found legacy ROM-specific positions at {legacy_rom_path}")
                    with open(legacy_rom_path, 'r') as f:
                        rom_positions = json.load(f)
                    
                    # Migrate to new location
                    os.makedirs(self.settings_dir, exist_ok=True)
                    with open(rom_positions_file, 'w') as f:
                        json.dump(rom_positions, f)
                    
                    print(f"Migrated ROM-specific positions from {legacy_rom_path} to {rom_positions_file}")
            
            # Start with global positions, then override with ROM-specific ones
            positions = global_positions.copy()
            positions.update(rom_positions)  # ROM positions take precedence
            
            print(f"Combined positions: {len(positions)} total ({len(global_positions)} global, {len(rom_positions)} ROM-specific)")
            
        except Exception as e:
            print(f"Error loading saved positions: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"Returning {len(positions)} positions")
        return positions
    
    def update_control_positions(self):
        """Update control positions when canvas resizes"""
        # This would be used to maintain relative positions on resize
        # Placeholder for now - requires position management system
        pass
    
    # 13. Modify the toggle_texts method to not update shadows
    def toggle_texts(self):
        """Toggle visibility of control labels except joystick controls"""
        self.texts_visible = not self.texts_visible
        
        # Update button text
        self.toggle_texts_button.setText("Show Texts" if not self.texts_visible else "Hide Texts")
        
        # Toggle visibility for each control, but skip joystick controls
        for control_name, control_data in self.control_labels.items():
            # Skip joystick controls - these are controlled by the joystick button only
            if "JOYSTICK" in control_name:
                continue
                
            # Toggle visibility for non-joystick controls
            control_data['label'].setVisible(self.texts_visible)
        
        # Force update to ensure proper rendering
        if hasattr(self, 'canvas'):
            self.canvas.update()
    
    # 14. Modify toggle_joystick_controls to not update shadows
    def toggle_joystick_controls(self):
        """Toggle visibility of joystick controls and save setting"""
        self.joystick_visible = not self.joystick_visible
        
        # Update button text
        self.joystick_button.setText("Show Joystick" if not self.joystick_visible else "Hide Joystick")
        
        # Toggle visibility for joystick controls
        for control_name, control_data in self.control_labels.items():
            if "JOYSTICK" in control_name:
                is_visible = self.texts_visible and self.joystick_visible
                control_data['label'].setVisible(is_visible)
        
        # Save the joystick visibility setting (globally)
        self.save_bezel_settings(is_global=True)
        print(f"Joystick visibility set to {self.joystick_visible} and saved to settings")
    
    # Update the reset_positions method to better handle saved positions
    def reset_positions(self):
        """Reset control labels to their original positions"""
        try:
            # Apply y-offset from text settings
            y_offset = self.text_settings.get("y_offset", -40)
            
            for control_name, control_data in self.control_labels.items():
                # Get the original position
                original_pos = control_data.get('original_pos', QPoint(100, 100))
                
                # Apply the current y-offset 
                new_pos = QPoint(original_pos.x(), original_pos.y() + y_offset)
                
                # Move the labels
                control_data['label'].move(new_pos)
            
            print(f"Reset {len(self.control_labels)} control positions to original values")
            
            # Also reload saved positions to update self.control_labels with fresh saved positions 
            saved_positions = self.load_saved_positions()
            if saved_positions:
                # Update original positions in control_labels
                for control_name, position in saved_positions.items():
                    if control_name in self.control_labels:
                        pos_x, pos_y = position
                        self.control_labels[control_name]['original_pos'] = QPoint(pos_x, pos_y)
                
                print(f"Updated {len(saved_positions)} original positions from saved positions")
                
        except Exception as e:
            print(f"Error resetting positions: {e}")
            import traceback
            traceback.print_exc()
        
    # Now let's add a new method to handle saving both control positions and logo position
    # Update the save_positions method to include saving both text and logo settings
    # Enhanced save_positions method to properly save logo size
    def save_positions(self, is_global=False):
        """Save current control positions, text settings and logo settings to settings directory"""
        # Create positions dictionary
        positions = {}
        
        # Save control positions
        y_offset = self.text_settings.get("y_offset", -40)
        
        for control_name, control_data in self.control_labels.items():
            label_pos = control_data['label'].pos()
            
            # Store normalized position (without y-offset)
            positions[control_name] = [label_pos.x(), label_pos.y() - y_offset]
        
        # Save to file
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Determine the file paths - always save in settings directory
            positions_filepath = os.path.join(self.settings_dir, 
                                            "global_positions.json" if is_global else f"{self.rom_name}_positions.json")
            
            # Save positions to file
            with open(positions_filepath, 'w') as f:
                json.dump(positions, f)
            print(f"Saved {len(positions)} positions to: {positions_filepath}")
            
            # Also save text settings
            self.save_text_settings(self.text_settings)
            
            # Save logo settings
            if hasattr(self, 'logo_label') and self.logo_label:
                # Update logo settings before saving
                if self.logo_label.isVisible():
                    # Update current logo position and size
                    self.logo_settings["logo_visible"] = True
                    self.logo_settings["custom_position"] = True
                    self.logo_settings["x_position"] = self.logo_label.pos().x()
                    self.logo_settings["y_position"] = self.logo_label.pos().y()
                    
                    # Update size percentages based on current pixmap
                    logo_pixmap = self.logo_label.pixmap()
                    if logo_pixmap and not logo_pixmap.isNull():
                        canvas_width = self.canvas.width()
                        canvas_height = self.canvas.height()
                        
                        width_percentage = (logo_pixmap.width() / canvas_width) * 100
                        height_percentage = (logo_pixmap.height() / canvas_height) * 100
                        
                        self.logo_settings["width_percentage"] = width_percentage
                        self.logo_settings["height_percentage"] = height_percentage
                
                # Save logo settings
                self.save_logo_settings()
            
            # Print confirmation
            save_type = "global" if is_global else f"ROM-specific ({self.rom_name})"
            print(f"All settings saved as {save_type}")
            
            # Show confirmation message
            QMessageBox.information(
                self,
                "Settings Saved",
                f"Settings saved as {save_type}."
            )
            return True
            
        except Exception as e:
            print(f"Error saving settings: {e}")
            import traceback
            traceback.print_exc()
            
            # Show error message
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings: {str(e)}"
            )
            return False
    
    # Update the show_text_settings method to include a global save option
    def show_text_settings(self):
        """Show dialog to configure text appearance with global saving"""
        dialog = TextSettingsDialog(self, self.text_settings)
        dialog.setWindowTitle("Text Appearance Settings")
        
        if dialog.exec_() == QDialog.Accepted:
            # Use the save_global_text_settings method instead
            self.save_global_text_settings()
            print("Text settings updated and saved globally")
    
    def update_text_settings(self, settings):
        """Update text settings and properly apply to all controls with global saving"""
        # First, capture the current uppercase state before updating
        old_uppercase = self.text_settings.get("use_uppercase", False)
        new_uppercase = settings.get("use_uppercase", old_uppercase)
        uppercase_changed = old_uppercase != new_uppercase
        
        if uppercase_changed:
            print(f"Uppercase setting changing from {old_uppercase} to {new_uppercase}")
            
            # Special handling for first run - ensure we have original case data
            if not hasattr(self, '_original_case_data'):
                self._original_case_data = {}
                # Store original lowercase versions of all control text
                for control_name, control_data in self.control_labels.items():
                    if 'action' in control_data:
                        # Store the lowercase version
                        self._original_case_data[control_name] = control_data['action'].lower()
                        print(f"Stored original case for {control_name}: {self._original_case_data[control_name]}")
        
        # Update local settings with merge
        self.text_settings.update(settings)
        
        # Update font information
        font_family = settings.get("font_family", "Arial")
        font_size = settings.get("font_size", 28)
        bold_strength = settings.get("bold_strength", 2)
        
        # Reload and register the font
        self.load_and_register_fonts()
        
        # Force immediate recreation of control labels to handle case change correctly
        if uppercase_changed:
            # This approach ensures case changes apply immediately, even on first run
            self.recreate_control_labels_with_case()
        else:
            # Normal update for other changes
            self.apply_text_settings(uppercase_changed=uppercase_changed)
        
        # Save to file
        try:
            settings_dir = os.path.join(self.settings_dir)
            os.makedirs(settings_dir, exist_ok=True)
            
            # Save to global settings to ensure persistence
            settings_file = os.path.join(settings_dir, "text_appearance_settings.json")
            
            # Update the font_family with actual family name if available
            if hasattr(self, 'font_name') and self.font_name:
                self.text_settings["font_family"] = self.font_name
            
            with open(settings_file, 'w') as f:
                json.dump(self.text_settings, f)
            print(f"Saved text settings to {settings_file}: {self.text_settings}")
        except Exception as e:
            print(f"Error saving text settings: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"Text settings updated and applied: {self.text_settings}")

    def create_control_labels(self, clean_mode=False):
        """Create control labels without shadows and respect clean_mode"""
        if not self.game_data or 'players' not in self.game_data:
            return
            
        # CRITICAL FIX: Make sure we have properly loaded fonts
        if not hasattr(self, 'current_font') or self.current_font is None:
            print("Font not initialized before creating labels - forcing font loading")
            self.load_and_register_fonts()
        
        # Load saved positions
        saved_positions = {}
        if hasattr(self, 'load_saved_positions'):
            try:
                saved_positions = self.load_saved_positions()
            except Exception as e:
                print(f"Error loading saved positions: {e}")
        
        # Make sure joystick_visible is set before we start creating controls
        if not hasattr(self, 'joystick_visible'):
            # Load from settings if possible
            bezel_settings = {}
            if hasattr(self, 'load_bezel_settings'):
                try:
                    bezel_settings = self.load_bezel_settings()
                except Exception as e:
                    print(f"Error loading bezel settings: {e}")
            self.joystick_visible = bezel_settings.get("joystick_visible", True)
            print(f"Pre-initialized joystick visibility to: {self.joystick_visible}")
        
        # Process controls
        for player in self.game_data.get('players', []):
            if player['number'] != 1:  # Only show Player 1 controls
                continue
                    
            # Create a label for each control
            grid_x, grid_y = 0, 0
            for control in player.get('labels', []):
                control_name = control['name']
                action_text = control['value']
                
                # Get button prefix based on mapping if available, or control name otherwise
                button_prefix = ""
                if 'mapping' in control and control.get('is_custom', False):
                    # Use the mapping to determine the button prefix
                    button_prefix = self.get_button_prefix_from_mapping(control['mapping'])
                elif hasattr(self, 'get_button_prefix'):
                    # Default: use control name to determine prefix
                    button_prefix = self.get_button_prefix(control_name)
                
                # Determine visibility
                is_visible = True
                if "JOYSTICK" in control_name:
                    is_visible = getattr(self, 'joystick_visible', True)
                
                # Apply text settings
                if self.text_settings.get("use_uppercase", False):
                    action_text = action_text.upper()
                
                # Add prefix if enabled in settings
                show_button_prefix = self.text_settings.get("show_button_prefix", True)
                display_text = f"{button_prefix}: {action_text}" if show_button_prefix and button_prefix else action_text
                
                # Get position
                if control_name in saved_positions:
                    # Get saved position
                    pos_x, pos_y = saved_positions[control_name]
                    
                    # Apply y-offset from text settings
                    y_offset = self.text_settings.get("y_offset", -40)
                    
                    # Use saved position
                    x, y = pos_x, pos_y + y_offset
                    original_pos = QPoint(pos_x, pos_y)  # Store without offset
                else:
                    # Default position based on a grid layout
                    x = 100 + (grid_x * 150)
                    y = 100 + (grid_y * 40)
                    
                    # Apply y-offset from text settings
                    y_offset = self.text_settings.get("y_offset", -40)
                    y += y_offset
                    
                    # Store original position without offset
                    original_pos = QPoint(x, y - y_offset)
                    
                    # Update grid position
                    grid_x = (grid_x + 1) % 5
                    if grid_x == 0:
                        grid_y += 1
                
                # Determine if we should use gradient
                use_prefix_gradient = self.text_settings.get("use_prefix_gradient", False)
                use_action_gradient = self.text_settings.get("use_action_gradient", False)
                use_gradient = use_prefix_gradient or use_action_gradient
                
                try:
                    # Create the appropriate label type
                    if use_gradient:
                        # Use the gradient-enabled label
                        label = GradientDraggableLabel(display_text, self.canvas, settings=self.text_settings)
                    else:
                        # Use the color-enabled label
                        label = ColoredDraggableLabel(display_text, self.canvas, settings=self.text_settings)
                    
                    # CRITICAL FIX: Apply font with priority order and debug info
                    font_applied = False
                    
                    # 1. First try current_font (most specific)
                    if hasattr(self, 'current_font') and self.current_font:
                        label.setFont(self.current_font)
                        print(f"Applied current_font to {control_name}: {self.current_font.family()}")
                        font_applied = True
                    
                    # 2. Next try initialized_font
                    elif hasattr(self, 'initialized_font') and self.initialized_font:
                        label.setFont(self.initialized_font)
                        print(f"Applied initialized_font to {control_name}: {self.initialized_font.family()}")
                        font_applied = True
                    
                    # 3. If neither is available, create a new font with identical specs
                    # to what would have been created by load_and_register_fonts
                    if not font_applied:
                        from PyQt5.QtGui import QFont
                        font_family = self.text_settings.get("font_family", "Arial")
                        font_size = self.text_settings.get("font_size", 28)
                        font = QFont(font_family, font_size)
                        font.setBold(self.text_settings.get("bold_strength", 2) > 0)
                        font.setStyleStrategy(QFont.PreferMatch)  # CRITICAL: Ensure exact matching
                        label.setFont(font)
                        print(f"Created new font for {control_name}: {font.family()} (fallback)")
                    
                    # Position the label
                    label.move(x, y)
                    
                    # CRITICAL FIX: Make sure to set draggable flag correctly based on clean_mode
                    label.draggable = not clean_mode
                    
                    # CRITICAL FIX: Disable cursor change in clean mode
                    if clean_mode:
                        label.setCursor(Qt.ArrowCursor)
                    
                    # For gradient labels, explicitly set gradient properties
                    if use_gradient and hasattr(label, 'use_prefix_gradient'):
                        label.use_prefix_gradient = use_prefix_gradient
                        label.use_action_gradient = use_action_gradient
                        
                        # Set gradient colors
                        label.prefix_gradient_start = QColor(self.text_settings.get("prefix_gradient_start", "#FFC107"))
                        label.prefix_gradient_end = QColor(self.text_settings.get("prefix_gradient_end", "#FF5722"))
                        label.action_gradient_start = QColor(self.text_settings.get("action_gradient_start", "#2196F3"))
                        label.action_gradient_end = QColor(self.text_settings.get("action_gradient_end", "#4CAF50"))
                    
                    # CRITICAL FIX: Apply text color via stylesheet as a reinforcement
                    text_color = self.text_settings.get("action_color", "#FFFFFF")
                    label.setStyleSheet(f"color: {text_color}; background-color: transparent; font-family: '{label.font().family()}';")
                    
                    # Apply visibility
                    label.setVisible(is_visible)
                    
                    # CRITICAL FIX: Only assign drag events if not in clean mode
                    if not clean_mode:
                        label.mousePressEvent = lambda event, lbl=label: self.on_label_press(event, lbl)
                        label.mouseMoveEvent = lambda event, lbl=label: self.on_label_move(event, lbl)
                        label.mouseReleaseEvent = lambda event, lbl=label: self.on_label_release(event, lbl)
                    else:
                        # In clean mode, make sure we don't respond to mouse events
                        label.mousePressEvent = lambda event: None
                        label.mouseMoveEvent = lambda event: None
                        label.mouseReleaseEvent = lambda event: None
                    
                    # Store the label
                    self.control_labels[control_name] = {
                        'label': label,
                        'action': action_text,
                        'prefix': button_prefix,
                        'original_pos': original_pos
                    }
                except Exception as e:
                    print(f"Error creating label for {control_name}: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Force a canvas update
        self.canvas.update()
        print(f"Created {len(self.control_labels)} control labels with {'non-draggable' if clean_mode else 'draggable'} behavior")

    def get_button_prefix_from_mapping(self, mapping):
        """Get the button prefix based on XINPUT mapping"""
        xinput_to_prefix = {
            "XINPUT_1_A": "A",
            "XINPUT_1_B": "B",
            "XINPUT_1_X": "X",
            "XINPUT_1_Y": "Y",
            "XINPUT_1_SHOULDER_L": "LB",
            "XINPUT_1_SHOULDER_R": "RB",
            "XINPUT_1_TRIGGER_L": "LT",
            "XINPUT_1_TRIGGER_R": "RT",
            "XINPUT_1_THUMB_L": "LS",
            "XINPUT_1_THUMB_R": "RS",
            "XINPUT_1_DPAD_UP": "D↑",
            "XINPUT_1_DPAD_DOWN": "D↓",
            "XINPUT_1_DPAD_LEFT": "D←",
            "XINPUT_1_DPAD_RIGHT": "D→"
        }
        
        return xinput_to_prefix.get(mapping, "")

    def apply_text_settings(self, uppercase_changed=False):
        """Apply current text settings to all controls with both font and gradient support"""
        # Import QTimer at the beginning of the method
        from PyQt5.QtCore import QTimer
        
        # Extract settings
        font_family = self.text_settings.get("font_family", "Arial")
        font_size = self.text_settings.get("font_size", 28)
        bold_strength = self.text_settings.get("bold_strength", 2) > 0
        use_uppercase = self.text_settings.get("use_uppercase", False)
        show_button_prefix = self.text_settings.get("show_button_prefix", True)
        prefix_color = self.text_settings.get("prefix_color", "#FFC107")
        action_color = self.text_settings.get("action_color", "#FFFFFF")
        y_offset = self.text_settings.get("y_offset", -40)
        
        # Extract gradient-specific settings
        use_prefix_gradient = self.text_settings.get("use_prefix_gradient", False)
        use_action_gradient = self.text_settings.get("use_action_gradient", False)
        prefix_gradient_start = self.text_settings.get("prefix_gradient_start", "#FFC107")
        prefix_gradient_end = self.text_settings.get("prefix_gradient_end", "#FF5722")
        action_gradient_start = self.text_settings.get("action_gradient_start", "#2196F3")
        action_gradient_end = self.text_settings.get("action_gradient_end", "#4CAF50")
        
        # Log debug info about gradient settings
        print(f"Applying gradient settings: prefix={use_prefix_gradient}, action={use_action_gradient}")
        print(f"Prefix gradient: {prefix_gradient_start} -> {prefix_gradient_end}")
        print(f"Action gradient: {action_gradient_start} -> {action_gradient_end}")
        
        # DIRECT FONT LOADING - Create a completely new approach
        from PyQt5.QtGui import QFontDatabase, QFont, QFontInfo
        
        # Step 1: Create a font object with the requested family
        font = QFont(font_family, font_size)
        font.setBold(bold_strength > 0)
        
        # Step 2: Check if Qt is substituting the font
        font_info = QFontInfo(font)
        if font_info.family() != font_family:
            print(f"FONT SUBSTITUTION DETECTED: {font_family} → {font_info.family()}")
            
            # CRITICAL FIX: Ensure the font is available by loading the specific font file
            system_font_map = {
                "Times New Roman": "times.ttf",
                "Impact": "impact.ttf",
                "Courier New": "cour.ttf",
                "Comic Sans MS": "comic.ttf",
                "Georgia": "georgia.ttf"
            }
            
            font_loaded = False
            
            # Try loading system font if it's in our map
            if font_family in system_font_map and os.path.exists("C:\\Windows\\Fonts"):
                font_file = system_font_map[font_family]
                font_path = os.path.join("C:\\Windows\\Fonts", font_file)
                
                if os.path.exists(font_path):
                    print(f"Loading font directly from: {font_path}")
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    
                    if font_id >= 0:
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        if families:
                            # IMPORTANT: Get the EXACT font family name from Qt
                            exact_family = families[0]
                            print(f"Font registered as: {exact_family}")
                            
                            # Replace the font object completely
                            font = QFont(exact_family, font_size)
                            font.setBold(bold_strength > 0)
                            
                            # Force exact match
                            font.setStyleStrategy(QFont.PreferMatch)
                            
                            # Double check it worked
                            new_info = QFontInfo(font)
                            print(f"New font family: {new_info.family()}")
                            font_loaded = True
            
            # If system font loading failed, try custom fonts
            if not font_loaded:
                fonts_dir = os.path.join(self.mame_dir, "preview", "fonts")
                if os.path.exists(fonts_dir):
                    # Try exact match
                    potential_files = [
                        f"{font_family}.ttf",
                        f"{font_family}.otf",
                        font_family.lower() + ".ttf",
                        font_family.lower() + ".otf"
                    ]
                    
                    for file_name in potential_files:
                        font_path = os.path.join(fonts_dir, file_name)
                        if os.path.exists(font_path):
                            print(f"Loading custom font: {font_path}")
                            font_id = QFontDatabase.addApplicationFont(font_path)
                            
                            if font_id >= 0:
                                families = QFontDatabase.applicationFontFamilies(font_id)
                                if families:
                                    exact_family = families[0]
                                    print(f"Custom font registered as: {exact_family}")
                                    
                                    font = QFont(exact_family, font_size)
                                    font.setBold(bold_strength > 0)
                                    font.setStyleStrategy(QFont.PreferMatch)
                                    
                                    font_loaded = True
                                    break
                    
                    # If no exact match, try all font files
                    if not font_loaded:
                        for filename in os.listdir(fonts_dir):
                            if filename.lower().endswith(('.ttf', '.otf')):
                                font_path = os.path.join(fonts_dir, filename)
                                print(f"Trying font: {font_path}")
                                
                                font_id = QFontDatabase.addApplicationFont(font_path)
                                if font_id >= 0:
                                    families = QFontDatabase.applicationFontFamilies(font_id)
                                    for family in families:
                                        # Check if this font family contains our requested name
                                        if (font_family.lower() in family.lower() or 
                                            family.lower() in font_family.lower()):
                                            print(f"Found matching font: {family}")
                                            
                                            font = QFont(family, font_size)
                                            font.setBold(bold_strength > 0)
                                            font.setStyleStrategy(QFont.PreferMatch)
                                            
                                            font_loaded = True
                                            break
                                
                                if font_loaded:
                                    break
        
        # Now apply the font and settings to ALL controls
        from PyQt5.QtCore import QTimer
        from PyQt5.QtGui import QColor
        from PyQt5.QtCore import QPoint
        
        for control_name, control_data in self.control_labels.items():
            if 'label' in control_data:
                label = control_data['label']
                
                # Get original action text (store in lowercase)
                action_text = control_data['action']
                if uppercase_changed and use_uppercase == False:
                    # Convert stored action text back to lowercase if needed
                    # Only do this when toggling from uppercase to lowercase
                    action_text = action_text.lower()
                    control_data['action'] = action_text
                    print(f"Converted '{control_name}' action text to lowercase: {action_text}")
                
                prefix = control_data.get('prefix', '')
                
                # Apply uppercase if enabled
                display_text = action_text
                if use_uppercase:
                    display_text = action_text.upper()
                
                # Create the display text with or without prefix
                if show_button_prefix and prefix:
                    display_text = f"{prefix}: {display_text}"
                
                # Update the text
                label.setText(display_text)
                
                # Update label settings
                if hasattr(label, 'settings'):
                    label.settings.update(self.text_settings)
                
                # If it's a ColoredPrefixLabel or GradientPrefixLabel, update prefix and action
                if hasattr(label, 'parse_text'):
                    try:
                        label.parse_text(display_text)
                    except Exception as e:
                        print(f"Error parsing text for {control_name}: {e}")
                
                # Apply the font - TWO ways for redundancy
                label.setFont(font)
                
                # Special gradient updates for GradientPrefixLabel - do this safely
                if hasattr(label, 'use_prefix_gradient') and hasattr(label, 'use_action_gradient'):
                    try:
                        # Update gradient flags
                        label.use_prefix_gradient = use_prefix_gradient
                        label.use_action_gradient = use_action_gradient
                        
                        # Update gradient colors if these attributes exist
                        if hasattr(label, 'prefix_gradient_start'):
                            label.prefix_gradient_start = QColor(prefix_gradient_start)
                        if hasattr(label, 'prefix_gradient_end'):
                            label.prefix_gradient_end = QColor(prefix_gradient_end)
                        if hasattr(label, 'action_gradient_start'):
                            label.action_gradient_start = QColor(action_gradient_start)
                        if hasattr(label, 'action_gradient_end'):
                            label.action_gradient_end = QColor(action_gradient_end)
                    except Exception as e:
                        print(f"Error updating gradient settings: {e}")
                
                # FORCE SPECIFIC FONT NAME as fallback with stylesheet (as a second approach)
                label.setStyleSheet(f"background-color: transparent; border: none; font-family: '{font.family()}';")
                
                # Update positions
                original_pos = control_data.get('original_pos', QPoint(100, 100))
                label_x, label_y = original_pos.x(), original_pos.y() + y_offset
                
                # Move the label
                label.move(label_x, label_y)
                
                # Force repaint
                label.update()
        
        # If we have a prefix button, update its text
        if hasattr(self, 'prefix_button'):
            self.prefix_button.setText("Hide Prefixes" if show_button_prefix else "Show Prefixes")
        
        # Force a repaint
        if hasattr(self, 'canvas'):
            self.canvas.update()
        
        # Verify font application - do this more safely
        if hasattr(self, 'verify_font_application'):
            try:
                # Use a short delay to allow Qt to properly apply fonts
                QTimer.singleShot(100, self.verify_font_application)
            except Exception as e:
                print(f"Error scheduling font verification: {e}")
        
        print("Text settings applied to all controls with better font handling")

    def verify_font_application(self, control_name=None):
        """Verify that fonts are being correctly applied to labels"""
        try:
            print("\n--- FONT APPLICATION VERIFICATION ---")
            
            # Get the requested font family from settings
            requested_font = self.text_settings.get("font_family", "Arial")
            print(f"Requested font from settings: {requested_font}")
            
            # Check a specific control or all controls
            if control_name and control_name in self.control_labels:
                label = self.control_labels[control_name]['label']
                actual_font = label.font().family()
                actual_size = label.font().pointSize()
                print(f"Control '{control_name}': font={actual_font}, size={actual_size}")
            else:
                # Check a sample of controls
                sample_count = min(3, len(self.control_labels))
                count = 0
                for name, data in self.control_labels.items():
                    if count >= sample_count:
                        break
                    if 'label' in data:
                        label = data['label']
                        actual_font = label.font().family()
                        actual_size = label.font().pointSize()
                        print(f"Control '{name}': font={actual_font}, size={actual_size}")
                        count += 1
            
            print("----------------------------------")
        except Exception as e:
            print(f"Error in verify_font_application: {e}")
 
    def initialize_controller_close(self):
        """Initialize controller input detection using the inputs package"""
        try:
            # Try to import inputs module
            from inputs import devices, get_gamepad
            
            # Check if gamepads are available
            gamepads = [device for device in devices.gamepads]
            if not gamepads:
                print("No gamepads detected, controller close feature disabled")
                return
                
            print(f"Found gamepad: {gamepads[0].name}, enabling controller close feature")
            
            # Flag to prevent multiple polling loops
            self.xinput_polling_active = True
            
            # Track last detected button press time to prevent multiple triggers
            self.last_button_press_time = 0
            
            # Create a dedicated thread for controller polling
            import threading
            import time
            import queue
            
            # Create a queue for button events
            self.controller_event_queue = queue.Queue()
            
            # Thread function for continuous controller polling
            def controller_polling_thread():
                try:
                    while getattr(self, 'xinput_polling_active', False):
                        try:
                            # Get events from controller
                            events = get_gamepad()
                            
                            # Look for button presses
                            for event in events:
                                if event.ev_type == "Key" and event.state == 1:
                                    # Put button press event in queue
                                    self.controller_event_queue.put(event.code)
                                    
                        except Exception as e:
                            # Ignore expected errors
                            if "No more events to read" not in str(e):
                                print(f"Controller polling error: {e}")
                            
                        # Short sleep to avoid consuming too much CPU
                        time.sleep(0.01)
                except Exception as e:
                    print(f"Controller thread error: {e}")
                
                print("Controller polling thread ended")
            
            # Start the polling thread
            self.controller_thread = threading.Thread(target=controller_polling_thread)
            self.controller_thread.daemon = True
            self.controller_thread.start()
            
            # Function to check the event queue from the main thread
            def check_controller_queue():
                # Process up to 5 events at a time
                for _ in range(5):
                    if self.controller_event_queue.empty():
                        break
                    
                    try:
                        # Get button code from queue
                        button_code = self.controller_event_queue.get_nowait()
                        
                        # Check debounce time (300ms)
                        current_time = time.time()
                        if current_time - self.last_button_press_time > 0.3:
                            print(f"Controller button pressed: {button_code}")
                            self.last_button_press_time = current_time
                            
                            # Close the preview
                            self.close()
                            return
                    except queue.Empty:
                        break
                    except Exception as e:
                        print(f"Error processing controller event: {e}")
                
                # Schedule next check if still active
                if getattr(self, 'xinput_polling_active', False):
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(33, check_controller_queue)  # ~30Hz checking
            
            # Start the event queue checker using QTimer
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, check_controller_queue)
            print("Controller close feature enabled")
            
        except ImportError:
            print("Inputs package not available, install with: pip install inputs")
        except Exception as e:
            print(f"Error setting up controller input: {e}")

    def closeEvent(self, event):
        """Override close event to ensure proper cleanup"""
        print("PreviewWindow closeEvent triggered, performing cleanup...")
        
        # Stop controller polling
        self.xinput_polling_active = False
        
        # Cancel any pending timers
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if isinstance(attr, QTimer):
                try:
                    attr.stop()
                    print(f"Stopped timer: {attr_name}")
                except:
                    pass
        
        # Free resources
        self.cleanup_resources()
        
        # Accept the close event to allow the window to close
        event.accept()
        
        # If we're in standalone mode, quit the application
        if getattr(self, 'standalone_mode', False):
            QApplication.quit()

    # 9. Modify the cleanup_resources method to remove shadow references
    def cleanup_resources(self):
        """Clean up all resources to ensure proper application shutdown"""
        print("Cleaning up PreviewWindow resources...")
        
        # Clear any stored pixmaps
        pixmap_attributes = [
            'background_pixmap', 'original_background_pixmap', 
            'bezel_pixmap', 'original_bezel_pixmap',
            'logo_pixmap', 'original_logo_pixmap'
        ]
        
        for attr_name in pixmap_attributes:
            if hasattr(self, attr_name):
                try:
                    setattr(self, attr_name, None)
                    print(f"Cleared {attr_name}")
                except:
                    pass
        
        # Remove all control labels
        if hasattr(self, 'control_labels'):
            for control_name in list(self.control_labels.keys()):
                control_data = self.control_labels[control_name]
                if 'label' in control_data and control_data['label']:
                    try:
                        control_data['label'].setParent(None)
                        control_data['label'].deleteLater()
                    except:
                        pass
            self.control_labels.clear()
            print("Cleared control labels")
        
        # Clear other UI elements
        ui_elements = [
            'bg_label', 'bezel_label', 'logo_label', 'button_frame',
            'position_indicator', 'guide_labels', 'grid_lines'
        ]
        
        for elem_name in ui_elements:
            if hasattr(self, elem_name):
                elem = getattr(self, elem_name)
                if elem:
                    if isinstance(elem, list):
                        for item in elem:
                            try:
                                if not sip.isdeleted(item):
                                    item.setParent(None)
                                    item.deleteLater()
                            except:
                                pass
                        setattr(self, elem_name, [])
                    else:
                        try:
                            if not sip.isdeleted(elem):
                                elem.setParent(None)
                                elem.deleteLater()
                            setattr(self, elem_name, None)
                        except:
                            pass
                print(f"Cleared {elem_name}")
        
        # Force update
        if hasattr(self, 'canvas') and self.canvas:
            try:
                self.canvas.update()
            except:
                pass
        
        # Force immediate garbage collection
        import gc
        gc.collect()
        print("Garbage collection completed")
    
    # Add this function to mame_controls_preview.py
    def export_image_headless(self, output_path, format="png"):
        """Export preview image in headless mode using existing save_image functionality"""
        try:
            print(f"Exporting preview image to {output_path}")
            
            # If the original save_image function exists, use it
            if hasattr(self, 'save_image'):
                # Get the current output path to restore it later
                original_output_path = getattr(self, '_output_path', None)
                
                # Set the output path temporarily
                self._output_path = output_path
                
                # Call the existing save_image function
                result = self.save_image()
                
                # Restore original path
                if original_output_path:
                    self._output_path = original_output_path
                
                return result
            else:
                print("ERROR: save_image method not available")
                return False
        except Exception as e:
            print(f"Error in export_image_headless: {e}")
            import traceback
            traceback.print_exc()
            return False

    # Add this to mame_controls_preview.py to handle command line parameters
    def add_cli_export_support():
        """Add CLI support for batch export mode to the preview module"""
        import argparse
        
        parser = argparse.ArgumentParser(description='MAME Control Preview')
        parser.add_argument('--export-image', action='store_true', help='Export image mode')
        parser.add_argument('--game', type=str, help='ROM name')
        parser.add_argument('--output', type=str, help='Output image path')
        parser.add_argument('--format', type=str, default='png', choices=['png', 'jpg'], help='Image format')
        parser.add_argument('--no-buttons', action='store_true', help='Hide control buttons')
        parser.add_argument('--clean-mode', action='store_true', help='Clean mode with no drag handles')
        parser.add_argument('--no-bezel', action='store_true', help='Hide bezel')
        parser.add_argument('--no-logo', action='store_true', help='Hide logo')
        
        args = parser.parse_args()
        
        # If export mode is enabled, handle it
        if args.export_image:
            if not args.game or not args.output:
                print("ERROR: --game and --output parameters are required for export mode")
                sys.exit(1)
            
            # Get application paths
            app_dir = get_application_path()
            mame_dir = get_mame_parent_dir(app_dir)
            
            # Find and load game data
            from PyQt5.QtWidgets import QApplication
            app = QApplication(sys.argv)
            
            # Create a headless app for image export
            try:
                # Load game data from cache 
                preview_dir = os.path.join(mame_dir, "preview")
                cache_dir = os.path.join(preview_dir, "cache")
                cache_path = os.path.join(cache_dir, f"{args.game}_cache.json")
                
                if os.path.exists(cache_path):
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        game_data = json.load(f)
                else:
                    print(f"ERROR: Cache file not found: {cache_path}")
                    sys.exit(1)
                    
                # Create preview window with command line options
                hide_buttons = args.no_buttons
                clean_mode = args.clean_mode
                
                # Create the preview window (starts invisible)
                preview = PreviewWindow(
                    args.game, 
                    game_data, 
                    mame_dir,
                    hide_buttons=hide_buttons,
                    clean_mode=clean_mode
                )
                
                # Set bezel/logo visibility if specified
                if args.no_bezel and hasattr(preview, 'bezel_visible'):
                    preview.bezel_visible = False
                    
                if args.no_logo and hasattr(preview, 'logo_visible'):
                    preview.logo_visible = False
                    if hasattr(preview, 'logo_label') and preview.logo_label:
                        preview.logo_label.setVisible(False)
                
                # Export the image
                if preview.export_image_headless(args.output, args.format):
                    print(f"Successfully exported preview for {args.game} to {args.output}")
                    sys.exit(0)
                else:
                    print(f"Failed to export preview for {args.game}")
                    sys.exit(1)
                    
            except Exception as e:
                print(f"ERROR in export mode: {e}")
                import traceback
                traceback.print_exc()
                sys.exit(1)
                
        return args

# 1. First, modify the EnhancedLabel class to remove shadow functionality
class EnhancedLabel(QLabel):
    """A label with improved rendering without shadows"""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        
        # Set transparent background
        self.setStyleSheet("background-color: transparent;")
        
    def paintEvent(self, event):
        """Override paint event to draw text with better positioning"""
        if not self.text():
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        # Get current font metrics
        metrics = QFontMetrics(self.font())
        text_rect = metrics.boundingRect(self.text())
        
        # Calculate text position (centered in the label)
        x = int((self.width() - text_rect.width()) / 2)
        y = int((self.height() + metrics.ascent() - metrics.descent()) / 2)
        
        # Draw main text
        painter.setPen(self.palette().color(QPalette.WindowText))
        painter.drawText(int(x), int(y), self.text())
        
# 2. Also update the DraggableLabel class to strictly respect the draggable property
class DraggableLabel(QLabel):
    """A draggable label without shadow functionality that respects draggable flag"""
    def __init__(self, text, parent=None, settings=None):
        super().__init__(text, parent)
        self.settings = settings or {}
        
        # Apply font settings
        self.update_appearance()
        
        # Enable mouse tracking
        self.setMouseTracking(True)
        self.dragging = False
        self.offset = QPoint()
        
        # Original position for reset
        self.original_pos = self.pos()
        
        # Original font size
        self.original_font_size = self.settings.get("font_size", 28)
        
        # Create context menu - not used in clean mode
        self.setup_context_menu()
        
        # Enable auto-resizing based on content
        self.setWordWrap(True)
        self.adjustSize()
        
        # Allow draggability to be controlled
        self.draggable = True
        
    # Add to DraggableLabel class
    def setFont(self, font):
        """Override setFont to automatically resize the label"""
        super().setFont(font)
        
        # Adjust size to fit new font
        self.adjustSize()
        
        # Make sure we don't have size restrictions
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)  # Qt's QWIDGETSIZE_MAX
        
        # Also reset size policy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def setup_context_menu(self):
        """Setup right-click context menu"""
        self.menu = QMenu(self)
        
        # Font size options
        font_menu = QMenu("Font Size", self.menu)
        
        # Add size options
        for size in [16, 20, 24, 28, 32, 36, 40]:
            action = QAction(f"{size}px", self)
            action.triggered.connect(lambda checked, s=size: self.change_font_size(s))
            font_menu.addAction(action)
        
        self.menu.addMenu(font_menu)
        
        # Color options
        color_menu = QMenu("Text Color", self.menu)
        
        # Add color options
        colors = {
            "White": Qt.white,
            "Yellow": Qt.yellow,
            "Red": Qt.red,
            "Green": QColor(50, 255, 50),
            "Blue": QColor(80, 160, 255),
            "Pink": QColor(255, 100, 255)
        }
        
        for name, color in colors.items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, c=color: self.change_text_color(c))
            color_menu.addAction(action)
        
        self.menu.addMenu(color_menu)
        
        # Add reset option
        reset_action = QAction("Reset Size", self)
        reset_action.triggered.connect(self.reset_font_size)
        self.menu.addAction(reset_action)
        
        # Add duplicate option
        duplicate_action = QAction("Duplicate", self)
        duplicate_action.triggered.connect(self.duplicate_label)
        self.menu.addAction(duplicate_action)
        
    def update_appearance(self):
        """Update appearance based on settings"""
        # If we have an initialized font, use it directly
        from PyQt5.QtCore import Qt
        if hasattr(self, 'initialized_font') and self.initialized_font:
            self.setFont(self.initialized_font)
            print(f"DraggableLabel using initialized font: {self.initialized_font.family()}")
        else:
            # Standard font creation as fallback
            font_family = self.settings.get("font_family", "Arial")
            font_size = self.settings.get("font_size", 28)
            use_bold = self.settings.get("bold_strength", 2) > 0
            
            font = QFont(font_family, font_size)
            font.setBold(use_bold)
            self.setFont(font)
        
        # Only use stylesheet for color and background 
        self.setStyleSheet("color: white; background-color: transparent; border: none;")
        self.setCursor(Qt.OpenHandCursor)
        
    def update_text(self, text):
        """Update the displayed text, applying uppercase and prefix if needed"""
        if self.settings.get("use_uppercase", False):
            text = text.upper()
        
        # If there's a prefix in the label, preserve it
        if ': ' in text:
            prefix, content = text.split(': ', 1)
            if self.settings.get("show_button_prefix", True):
                self.setText(f"{prefix}: {content}")
            else:
                self.setText(content)
        else:
            self.setText(text)
            
    def mousePressEvent(self, event):
        """Handle mouse press events for dragging with respect for draggable flag"""
        from PyQt5.QtCore import Qt
        
        # CRITICAL FIX: Only handle dragging if explicitly allowed
        if not getattr(self, 'draggable', True):
            event.ignore()  # Pass event to parent
            return
            
        if event.button() == Qt.LeftButton:
            # Make sure dragging flag is set
            self.dragging = True
            
            # CRITICAL FIX: Store both the mouse position and the label's current position
            self.drag_start_pos = event.pos()
            self.original_label_pos = self.pos()
            
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move with proper offset preservation and respect for draggable flag"""
        # CRITICAL FIX: Only handle dragging if explicitly allowed
        if not getattr(self, 'draggable', True):
            event.ignore()  # Pass event to parent
            return
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication
        
        if hasattr(self, 'dragging') and self.dragging and hasattr(self, 'drag_start_pos'):
            # Calculate the delta from the initial click position
            delta = event.pos() - self.drag_start_pos
            
            # FIXED: Apply the delta to the original label position to preserve offset
            # This ensures that wherever you click on the label, it maintains that relative position
            if hasattr(self, 'original_label_pos'):
                new_pos = self.original_label_pos + delta
            else:
                # Fallback for compatibility (shouldn't happen with the fixed mousePressEvent)
                new_pos = self.mapToParent(event.pos() - self.drag_start_pos)
                
            # Rest of the snapping and guidance code remains the same
            original_pos = new_pos  # Store original position before any snapping
            
            # Initialize guide lines list and snapping variables
            guide_lines = []
            snapped = False
            parent = self.parent()
            
            if parent:
                # Get canvas dimensions
                canvas_width = parent.width()
                canvas_height = parent.height()
                
                # Find reference to preview window
                preview_window = self.find_preview_window_parent()
                
                if preview_window:
                    # Check if snapping is enabled and not overridden
                    modifiers = QApplication.keyboardModifiers()
                    disable_snap = bool(modifiers & Qt.ShiftModifier)  # Shift key disables snapping temporarily
                    
                    apply_snapping = (
                        not disable_snap and
                        hasattr(preview_window, 'snapping_enabled') and
                        preview_window.snapping_enabled
                    )
                    
                    # Get snap distance if available
                    snap_distance = getattr(preview_window, 'snap_distance', 15)
                    
                    if apply_snapping:
                        # Get label center coordinates
                        label_center_x = new_pos.x() + self.width() // 2
                        label_center_y = new_pos.y() + self.height() // 2
                        
                        # 1. Absolute grid position snapping (if enabled)
                        if (hasattr(preview_window, 'snap_to_grid') and preview_window.snap_to_grid and
                            hasattr(preview_window, 'grid_x_start') and hasattr(preview_window, 'grid_y_start')):
                            
                            grid_x_start = preview_window.grid_x_start
                            grid_x_step = preview_window.grid_x_step
                            
                            # Snap to column X positions
                            for col in range(preview_window.grid_columns):
                                grid_x = grid_x_start + (col * grid_x_step)
                                if abs(new_pos.x() - grid_x) < snap_distance:
                                    new_pos.setX(grid_x)
                                    guide_lines.append((grid_x, 0, grid_x, canvas_height))
                                    snapped = True
                                    break
                            
                            # Snap to row Y positions
                            grid_y_start = preview_window.grid_y_start
                            grid_y_step = preview_window.grid_y_step
                            
                            for row in range(preview_window.grid_rows):
                                grid_y = grid_y_start + (row * grid_y_step)
                                if abs(new_pos.y() - grid_y) < snap_distance:
                                    new_pos.setY(grid_y)
                                    guide_lines.append((0, grid_y, canvas_width, grid_y))
                                    snapped = True
                                    break
                        
                        # Apply the move
                        self.move(new_pos)
                        
                        # Rest of snapping logic...
                        # 2. Screen center alignment (if enabled)
                        if hasattr(preview_window, 'snap_to_screen_center') and preview_window.snap_to_screen_center:
                            # Horizontal center
                            screen_center_x = canvas_width // 2
                            if abs(label_center_x - screen_center_x) < snap_distance:
                                new_pos.setX(int(screen_center_x - self.width() / 2))
                                guide_lines.append((screen_center_x, 0, screen_center_x, canvas_height))
                                snapped = True
                            
                            # Vertical center
                            screen_center_y = canvas_height // 2
                            if abs(label_center_y - screen_center_y) < snap_distance:
                                new_pos.setY(int(screen_center_y - self.height() / 2))
                                guide_lines.append((0, screen_center_y, canvas_width, screen_center_y))
                                snapped = True
                        
                        # 3. Check alignment with other controls (if enabled)
                        if (hasattr(preview_window, 'snap_to_controls') and preview_window.snap_to_controls and
                            hasattr(preview_window, 'control_labels')):
                            
                            for control_name, control_data in preview_window.control_labels.items():
                                other_label = control_data.get('label')
                                if other_label is self or not other_label or not other_label.isVisible():
                                    continue
                                
                                # X-position alignment - snap to left edge of other labels
                                other_x = other_label.pos().x()
                                if abs(new_pos.x() - other_x) < snap_distance:
                                    new_pos.setX(other_x)
                                    guide_lines.append((other_x, 0, other_x, canvas_height))
                                    snapped = True
                                
                                # Y-position alignment - snap to top edge of other labels
                                other_y = other_label.pos().y()
                                if abs(new_pos.y() - other_y) < snap_distance:
                                    new_pos.setY(other_y)
                                    guide_lines.append((0, other_y, canvas_width, other_y))
                                    snapped = True
                        
                        # 4. Check alignment with logo (if enabled)
                        if (hasattr(preview_window, 'snap_to_logo') and preview_window.snap_to_logo and
                            hasattr(preview_window, 'logo_label') and preview_window.logo_label and
                            preview_window.logo_label.isVisible()):
                            
                            logo = preview_window.logo_label
                            
                            # Left edge alignment (absolute X position)
                            logo_left = logo.pos().x()
                            if abs(new_pos.x() - logo_left) < snap_distance:
                                new_pos.setX(logo_left)
                                guide_lines.append((logo_left, 0, logo_left, canvas_height))
                                snapped = True
                            
                            # Top edge alignment
                            logo_top = logo.pos().y()
                            if abs(new_pos.y() - logo_top) < snap_distance:
                                new_pos.setY(logo_top)
                                guide_lines.append((0, logo_top, canvas_width, logo_top))
                                snapped = True
                    
                    # 5. Calculate distance indicators for display
                    # Show dynamic measurement guides
                    if hasattr(preview_window, 'show_measurement_guides'):
                        try:
                            preview_window.show_measurement_guides(
                                new_pos.x(), new_pos.y(), 
                                self.width(), self.height()
                            )
                        except Exception as e:
                            print(f"Error showing measurement guides: {e}")

                    # Add snapping status info if needed
                    if disable_snap and hasattr(preview_window, 'show_position_indicator'):
                        try:
                            preview_window.show_position_indicator(
                                new_pos.x(), new_pos.y(), 
                                "Snapping temporarily disabled (Shift)"
                            )
                        except Exception as e:
                            print(f"Error showing position indicator with status: {e}")
                    
                    # Show alignment guides if snapped
                    if snapped and guide_lines and hasattr(preview_window, 'show_alignment_guides'):
                        try:
                            preview_window.show_alignment_guides(guide_lines)
                        except Exception as e:
                            print(f"Error showing alignment guides: {e}")
                    elif hasattr(preview_window, 'hide_alignment_guides'):
                        try:
                            preview_window.hide_alignment_guides()
                        except Exception as e:
                            print(f"Error hiding alignment guides: {e}")
                
                # Apply the final position (if not already applied in snapping code)
                self.move(new_pos)
            
            # Apply the move
            self.move(new_pos)
                
            event.accept()
        
    def mouseReleaseEvent(self, event):
        """Handle mouse release with respect for draggable flag"""
        from PyQt5.QtCore import Qt
        
        # CRITICAL FIX: Only handle dragging if explicitly allowed
        if not getattr(self, 'draggable', True):
            event.ignore()  # Pass event to parent
            return
        
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.OpenHandCursor)
            
            # Hide guidance elements
            if hasattr(self, 'parent'):
                parent = self.parent()
                if parent and hasattr(parent, 'hide_alignment_guides'):
                    parent.hide_alignment_guides()
                if parent and hasattr(parent, 'hide_measurement_guides'):
                    parent.hide_measurement_guides()
                if parent and hasattr(parent, 'hide_position_indicator'):
                    parent.hide_position_indicator()
                
            event.accept()
    
    def find_preview_window_parent(self):
        """Find the PreviewWindow parent to access alignment guide methods"""
        current = self.parent()
        while current:
            # Look for a parent that has both show_alignment_guides and hide_alignment_guides methods
            if (hasattr(current, 'show_alignment_guides') and 
                hasattr(current, 'hide_alignment_guides')):
                return current
            current = current.parent()
        return None
            
    def contextMenuEvent(self, event):
        """Show context menu on right-click if draggable is enabled"""
        # CRITICAL FIX: Only show context menu if explicitly allowed
        if not getattr(self, 'draggable', True):
            event.ignore()  # Pass event to parent
            return
            
        self.menu.exec_(event.globalPos())
    
    def paintEvent(self, event):
        """Override paint event to draw text properly centered"""
        # Use default QLabel painting
        super().paintEvent(event)
    
    def change_font_size(self, size):
        """Change font size through context menu"""
        current_font = self.font()
        current_font.setPointSize(size)
        self.setFont(current_font)
        
        # Update settings
        if self.settings:
            self.settings["font_size"] = size
    
    def reset_font_size(self):
        """Reset font size to original"""
        self.change_font_size(self.original_font_size)
    
    def change_text_color(self, color):
        """Change text color"""
        self.setStyleSheet(f"color: {color.name()}; background-color: transparent; border: none;")
    
    def duplicate_label(self):
        """Duplicate this label"""
        if hasattr(self.parent(), "duplicate_control_label"):
            self.parent().duplicate_control_label(self)

class TextSettingsDialog(QDialog):
    """Dialog for configuring text appearance in preview with improved live preview"""
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Text Appearance Settings")
        self.resize(400, 550)  # Increased height to accommodate new controls
        
        # Store parent reference for settings access
        self.parent = parent
        
        # Store font file to family name mapping
        self.font_file_to_family = {}
        
        # Use provided settings or load defaults
        self.settings = settings or {
            "font_family": "Arial",
            "font_size": 28,
            "bold_strength": 2,
            "use_uppercase": False,
            "show_button_prefix": True,  # New default setting
            "prefix_color": "#FFC107",   # Default prefix color
            "action_color": "#FFFFFF",     # Default text color
            "y_offset": -40,
            "use_prefix_gradient": False,
            "use_action_gradient": False,
            "prefix_gradient_start": "#FFC107",
            "prefix_gradient_end": "#FF5722",
            "action_gradient_start": "#2196F3",
            "action_gradient_end": "#4CAF50"
        }
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Font section
        font_group = QGroupBox("Font Settings")
        font_layout = QVBoxLayout(font_group)
        
        # Font family selection
        font_row = QHBoxLayout()
        font_label = QLabel("Font Family:")
        
        self.font_combo = QComboBox()
        # Add common fonts
        fonts = ["Arial", "Verdana", "Tahoma", "Times New Roman", "Courier New", "Segoe UI", 
                "Calibri", "Georgia", "Impact", "System"]
        
        # Load custom fonts from preview/fonts directory
        if parent and hasattr(parent, 'mame_dir'):
            fonts_dir = os.path.join(parent.mame_dir, "preview", "fonts")
            if os.path.exists(fonts_dir):
                from PyQt5.QtGui import QFontDatabase
                
                print(f"Scanning for fonts in: {fonts_dir}")
                for filename in os.listdir(fonts_dir):
                    if filename.lower().endswith(('.ttf', '.otf')):
                        font_path = os.path.join(fonts_dir, filename)
                        
                        # Load font into QFontDatabase to get proper family name
                        font_id = QFontDatabase.addApplicationFont(font_path)
                        if font_id >= 0:
                            # Get the actual font family names
                            font_families = QFontDatabase.applicationFontFamilies(font_id)
                            if font_families:
                                actual_family = font_families[0]
                                print(f"Loaded font {filename}: family name = {actual_family}")
                                
                                # Add to our fonts list
                                fonts.append(actual_family)
                                
                                # Store mapping from filename to family name
                                base_name = os.path.splitext(filename)[0]
                                self.font_file_to_family[base_name] = actual_family
                            else:
                                print(f"Could not get family name for {filename}")
                        else:
                            print(f"Failed to load font: {filename}")

        self.font_combo.addItems(sorted(fonts))
        
        # Set current font - handle mapping from filename to family if needed
        current_font = self.settings.get("font_family", "Arial")
        if current_font in self.font_file_to_family:
            current_font = self.font_file_to_family[current_font]
            # Update the settings with the proper family name
            self.settings["font_family"] = current_font
        
        index = self.font_combo.findText(current_font)
        if index >= 0:
            self.font_combo.setCurrentIndex(index)
            
        font_row.addWidget(font_label)
        font_row.addWidget(self.font_combo)
        font_layout.addLayout(font_row)
        
        # Font size slider
        size_row = QHBoxLayout()
        size_label = QLabel("Font Size:")
        
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(12)
        self.size_slider.setMaximum(48)
        self.size_slider.setValue(self.settings.get("font_size", 28))
        
        self.size_value = QLabel(str(self.size_slider.value()))
        self.size_slider.valueChanged.connect(lambda v: self.size_value.setText(str(v)))
        
        size_row.addWidget(size_label)
        size_row.addWidget(self.size_slider)
        size_row.addWidget(self.size_value)
        font_layout.addLayout(size_row)
        
        # Bold strength
        bold_row = QHBoxLayout()
        bold_label = QLabel("Bold Strength:")
        
        self.bold_slider = QSlider(Qt.Horizontal)
        self.bold_slider.setMinimum(0)
        self.bold_slider.setMaximum(5)
        self.bold_slider.setValue(self.settings.get("bold_strength", 2))
        
        self.bold_labels = ["None", "Light", "Medium", "Strong", "Very Strong", "Maximum"]
        self.bold_value = QLabel(self.bold_labels[self.bold_slider.value()])
        
        self.bold_slider.valueChanged.connect(
            lambda v: self.bold_value.setText(self.bold_labels[v])
        )
        
        bold_row.addWidget(bold_label)
        bold_row.addWidget(self.bold_slider)
        bold_row.addWidget(self.bold_value)
        font_layout.addLayout(bold_row)
        
        layout.addWidget(font_group)
        
        # Text options
        options_group = QGroupBox("Text Options")
        options_layout = QVBoxLayout(options_group)
        
        # Uppercase option
        self.uppercase_check = QCheckBox("Use UPPERCASE for all text")
        self.uppercase_check.setChecked(self.settings.get("use_uppercase", False))
        options_layout.addWidget(self.uppercase_check)
        
        # Button prefix option (NEW)
        self.prefix_check = QCheckBox("Show button prefixes (e.g., A: Jump)")
        self.prefix_check.setChecked(self.settings.get("show_button_prefix", True))
        options_layout.addWidget(self.prefix_check)
        
        # Y-offset slider for vertical positioning
        offset_row = QHBoxLayout()
        offset_label = QLabel("Y-Offset:")
        
        self.offset_slider = QSlider(Qt.Horizontal)
        self.offset_slider.setMinimum(-80)
        self.offset_slider.setMaximum(0)
        self.offset_slider.setValue(self.settings.get("y_offset", -40))
        
        self.offset_value = QLabel(str(self.offset_slider.value()))
        self.offset_slider.valueChanged.connect(lambda v: self.offset_value.setText(str(v)))
        
        offset_row.addWidget(offset_label)
        offset_row.addWidget(self.offset_slider)
        offset_row.addWidget(self.offset_value)
        options_layout.addLayout(offset_row)
        
        layout.addWidget(options_group)
        
        # Color options
        color_group = QGroupBox("Color Options")
        color_layout = QVBoxLayout(color_group)

        # Prefix color
        prefix_color_row = QHBoxLayout()
        prefix_color_label = QLabel("Prefix Color:")
        self.prefix_color_edit = QLineEdit(self.settings.get("prefix_color", "#FFC107"))
        self.prefix_color_edit.setMaximumWidth(100)
        self.prefix_color_edit.setPlaceholderText("#RRGGBB")
        self.prefix_color_edit.textChanged.connect(self.update_preview)

        prefix_color_row.addWidget(prefix_color_label)
        prefix_color_row.addWidget(self.prefix_color_edit)
        prefix_color_row.addStretch()
        color_layout.addLayout(prefix_color_row)

        # Action color
        action_color_row = QHBoxLayout()
        action_color_label = QLabel("Action Color:")
        self.action_color_edit = QLineEdit(self.settings.get("action_color", "#FFFFFF"))
        self.action_color_edit.setMaximumWidth(100)
        self.action_color_edit.setPlaceholderText("#RRGGBB")
        self.action_color_edit.textChanged.connect(self.update_preview)

        action_color_row.addWidget(action_color_label)
        action_color_row.addWidget(self.action_color_edit)
        action_color_row.addStretch()
        color_layout.addLayout(action_color_row)

        layout.addWidget(color_group)
        
        # Gradient options
        gradient_group = QGroupBox("Gradient Options")
        gradient_layout = QVBoxLayout(gradient_group)

        # Prefix gradient toggle
        prefix_gradient_row = QHBoxLayout()
        self.prefix_gradient_check = QCheckBox("Use Gradient for Prefix")
        self.prefix_gradient_check.setChecked(self.settings.get("use_prefix_gradient", False))
        self.prefix_gradient_check.stateChanged.connect(self.update_preview)
        prefix_gradient_row.addWidget(self.prefix_gradient_check)
        gradient_layout.addLayout(prefix_gradient_row)

        # Prefix gradient colors
        prefix_gradient_colors = QHBoxLayout()
        prefix_gradient_start_label = QLabel("Start:")
        self.prefix_gradient_start = QLineEdit(self.settings.get("prefix_gradient_start", "#FFC107"))
        self.prefix_gradient_start.setMaximumWidth(80)
        prefix_gradient_end_label = QLabel("End:")
        self.prefix_gradient_end = QLineEdit(self.settings.get("prefix_gradient_end", "#FF5722"))
        self.prefix_gradient_end.setMaximumWidth(80)

        self.prefix_gradient_start.textChanged.connect(self.update_preview)
        self.prefix_gradient_end.textChanged.connect(self.update_preview)

        prefix_gradient_colors.addWidget(prefix_gradient_start_label)
        prefix_gradient_colors.addWidget(self.prefix_gradient_start)
        prefix_gradient_colors.addWidget(prefix_gradient_end_label)
        prefix_gradient_colors.addWidget(self.prefix_gradient_end)
        prefix_gradient_colors.addStretch()
        gradient_layout.addLayout(prefix_gradient_colors)

        # Action gradient toggle
        action_gradient_row = QHBoxLayout()
        self.action_gradient_check = QCheckBox("Use Gradient for Action Text")
        self.action_gradient_check.setChecked(self.settings.get("use_action_gradient", False))
        self.action_gradient_check.stateChanged.connect(self.update_preview)
        action_gradient_row.addWidget(self.action_gradient_check)
        gradient_layout.addLayout(action_gradient_row)

        # Action gradient colors
        action_gradient_colors = QHBoxLayout()
        action_gradient_start_label = QLabel("Start:")
        self.action_gradient_start = QLineEdit(self.settings.get("action_gradient_start", "#2196F3"))
        self.action_gradient_start.setMaximumWidth(80)
        action_gradient_end_label = QLabel("End:")
        self.action_gradient_end = QLineEdit(self.settings.get("action_gradient_end", "#4CAF50"))
        self.action_gradient_end.setMaximumWidth(80)

        self.action_gradient_start.textChanged.connect(self.update_preview)
        self.action_gradient_end.textChanged.connect(self.update_preview)

        action_gradient_colors.addWidget(action_gradient_start_label)
        action_gradient_colors.addWidget(self.action_gradient_start)
        action_gradient_colors.addWidget(action_gradient_end_label)
        action_gradient_colors.addWidget(self.action_gradient_end)
        action_gradient_colors.addStretch()
        gradient_layout.addLayout(action_gradient_colors)

        # Add preset gradient buttons
        preset_row = QHBoxLayout()
        preset_label = QLabel("Presets:")
        preset_fire = QPushButton("Fire")
        preset_fire.clicked.connect(lambda: self.apply_preset("fire"))
        preset_ice = QPushButton("Ice")
        preset_ice.clicked.connect(lambda: self.apply_preset("ice"))
        preset_rainbow = QPushButton("Rainbow")
        preset_rainbow.clicked.connect(lambda: self.apply_preset("rainbow"))

        preset_row.addWidget(preset_label)
        preset_row.addWidget(preset_fire)
        preset_row.addWidget(preset_ice)
        preset_row.addWidget(preset_rainbow)
        preset_row.addStretch()
        gradient_layout.addLayout(preset_row)

        layout.addWidget(gradient_group)
        
        # Preview section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_label = QLabel("A: Preview Text")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(100)
        self.preview_label.setStyleSheet("background-color: black; color: white;")
        
        preview_layout.addWidget(self.preview_label)
        layout.addWidget(preview_group)
        
        # Update preview when settings change
        self.font_combo.currentTextChanged.connect(self.update_preview)
        self.size_slider.valueChanged.connect(self.update_preview)
        self.bold_slider.valueChanged.connect(self.update_preview)
        self.uppercase_check.stateChanged.connect(self.update_preview)
        self.prefix_check.stateChanged.connect(self.update_preview)
        
        # Initial preview update
        self.update_preview()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_settings)
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept_settings)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.apply_button)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)

    def apply_preset(self, preset_name):
        """Apply a preset gradient configuration"""
        presets = {
            "fire": {
                "prefix": ("#FFEB3B", "#FF5722"),  # Yellow to Orange-Red
                "action": ("#FF9800", "#F44336")   # Orange to Red
            },
            "ice": {
                "prefix": ("#E1F5FE", "#0277BD"),  # Light Blue to Deep Blue
                "action": ("#B3E5FC", "#01579B")   # Pale Blue to Navy
            },
            "rainbow": {
                "prefix": ("#FF5722", "#2196F3"),  # Red-Orange to Blue
                "action": ("#4CAF50", "#9C27B0")   # Green to Purple
            }
        }
        
        if preset_name in presets:
            preset = presets[preset_name]
            
            # Set prefix gradient
            self.prefix_gradient_start.setText(preset["prefix"][0])
            self.prefix_gradient_end.setText(preset["prefix"][1])
            
            # Set action gradient
            self.action_gradient_start.setText(preset["action"][0])
            self.action_gradient_end.setText(preset["action"][1])
            
            # Enable gradient checkboxes
            self.prefix_gradient_check.setChecked(True)
            self.action_gradient_check.setChecked(True)
            
            # Update preview
            self.update_preview()
    
    def update_preview(self):
        """Update the preview label with better appearance"""
        try:
            # Get current settings
            font_family = self.font_combo.currentText()
            font_size = self.size_slider.value()
            bold_strength = self.bold_slider.value()
            use_uppercase = self.uppercase_check.isChecked()
            show_prefix = self.prefix_check.isChecked()
            
            # Color and gradient settings
            prefix_color = self.prefix_color_edit.text()
            action_color = self.action_color_edit.text()
            use_prefix_gradient = self.prefix_gradient_check.isChecked()
            prefix_gradient_start = self.prefix_gradient_start.text()
            prefix_gradient_end = self.prefix_gradient_end.text()
            use_action_gradient = self.action_gradient_check.isChecked()
            action_gradient_start = self.action_gradient_start.text()
            action_gradient_end = self.action_gradient_end.text()
            
            # Create font
            font = QFont(font_family, font_size)
            font.setBold(bold_strength > 0)
            font.setWeight(QFont.Bold if bold_strength > 0 else QFont.Normal)
            
            # Apply font to preview
            self.preview_label.setFont(font)
            
            # Apply uppercase if enabled
            preview_text = "Preview Text"
            if use_uppercase:
                preview_text = preview_text.upper()
            
            # Get preview label dimensions for scaling
            preview_width = self.preview_label.width()
            preview_height = self.preview_label.height()
            
            # Determine a good font size for the preview - between 18 and 32 depending on the chosen size
            preview_font_size = min(max(int(font_size * 0.9), 18), 32)
            
            # Create enhanced preview with proper colors and gradients
            if show_prefix:
                # Define a fixed left position 
                left_margin = 20  # Fixed left margin
                top_margin = preview_height // 2  # Vertical center
                
                svg_width = preview_width
                svg_height = preview_height
                
                # Start SVG
                svg_content = f"""
                <svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="black"/>
                """
                
                # Approach 1: Create a containing group with a left-aligned position
                svg_content += f"""
                <g>
                """
                
                # Current X position starts at left margin
                current_x = left_margin
                
                # Add prefix text with color or gradient
                prefix_text = "A:"
                
                if use_prefix_gradient:
                    # Use linearGradient for prefix
                    gradient_id = "prefixGradient"
                    svg_content += f"""
                    <defs>
                        <linearGradient id="{gradient_id}" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="{prefix_gradient_start}"/>
                            <stop offset="100%" stop-color="{prefix_gradient_end}"/>
                        </linearGradient>
                    </defs>
                    <text x="{current_x}" y="{top_margin}" 
                        font-family="{font_family}" font-size="{preview_font_size}" 
                        fill="url(#{gradient_id})" 
                        dominant-baseline="central"
                        font-weight="{bold_strength * 100 if bold_strength > 0 else 'normal'}">
                        {prefix_text}
                    </text>
                    """
                else:
                    # Use solid color for prefix
                    svg_content += f"""
                    <text x="{current_x}" y="{top_margin}" 
                        font-family="{font_family}" font-size="{preview_font_size}" 
                        fill="{prefix_color}" 
                        dominant-baseline="central"
                        font-weight="{bold_strength * 100 if bold_strength > 0 else 'normal'}">
                        {prefix_text}
                    </text>
                    """
                
                # Estimate width of prefix text with extra spacing for custom fonts
                # Use a more generous estimate for custom fonts
                is_custom_font = font_family not in ["Arial", "Verdana", "Tahoma", "Times New Roman", 
                                                    "Courier New", "Segoe UI", "Calibri", "Georgia", 
                                                    "Impact", "System"]
                
                if is_custom_font:
                    # More generous spacing for custom fonts that might have unusual metrics
                    prefix_width = len(prefix_text) * (preview_font_size * 0.8) + 15
                else:
                    # Standard spacing for system fonts
                    prefix_width = len(prefix_text) * (preview_font_size * 0.6) + 5
                
                # Add spacing after prefix
                current_x += prefix_width
                
                # Add action text with color or gradient
                if use_action_gradient:
                    # Use linearGradient for action text
                    gradient_id = "actionGradient"
                    svg_content += f"""
                    <defs>
                        <linearGradient id="{gradient_id}" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="{action_gradient_start}"/>
                            <stop offset="100%" stop-color="{action_gradient_end}"/>
                        </linearGradient>
                    </defs>
                    <text x="{current_x}" y="{top_margin}" 
                        font-family="{font_family}" font-size="{preview_font_size}" 
                        fill="url(#{gradient_id})" 
                        dominant-baseline="central"
                        font-weight="{bold_strength * 100 if bold_strength > 0 else 'normal'}">
                        {preview_text}
                    </text>
                    """
                else:
                    # Use solid color for action text
                    svg_content += f"""
                    <text x="{current_x}" y="{top_margin}" 
                        font-family="{font_family}" font-size="{preview_font_size}" 
                        fill="{action_color}" 
                        dominant-baseline="central"
                        font-weight="{bold_strength * 100 if bold_strength > 0 else 'normal'}">
                        {preview_text}
                    </text>
                    """
                
                # Close the group
                svg_content += "</g>"
                
                # Close SVG
                svg_content += "</svg>"
                
                # Apply to preview label
                self.preview_label.setText("")  # Clear text content
                self.preview_label.setPixmap(self.svg_to_pixmap(svg_content))
                
            else:
                # Single text element (no prefix) - use left alignment
                svg_width = preview_width
                svg_height = preview_height
                
                # Start SVG
                svg_content = f"""
                <svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="black"/>
                """
                
                # Define a fixed left position
                left_margin = 20  # Fixed left margin
                top_margin = preview_height // 2  # Vertical center
                
                if use_action_gradient:
                    # Use linearGradient for text
                    gradient_id = "textGradient"
                    svg_content += f"""
                    <defs>
                        <linearGradient id="{gradient_id}" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="{action_gradient_start}"/>
                            <stop offset="100%" stop-color="{action_gradient_end}"/>
                        </linearGradient>
                    </defs>
                    <text x="{left_margin}" y="{top_margin}" 
                        font-family="{font_family}" font-size="{preview_font_size}" 
                        fill="url(#{gradient_id})" 
                        dominant-baseline="central"
                        font-weight="{bold_strength * 100 if bold_strength > 0 else 'normal'}">
                        {preview_text}
                    </text>
                    """
                else:
                    # Use solid color for text
                    svg_content += f"""
                    <text x="{left_margin}" y="{top_margin}" 
                        font-family="{font_family}" font-size="{preview_font_size}" 
                        fill="{action_color}" 
                        dominant-baseline="central"
                        font-weight="{bold_strength * 100 if bold_strength > 0 else 'normal'}">
                        {preview_text}
                    </text>
                    """
                
                # Close SVG
                svg_content += "</svg>"
                
                # Apply to preview label
                self.preview_label.setText("")  # Clear text content
                self.preview_label.setPixmap(self.svg_to_pixmap(svg_content))
                
        except Exception as e:
            print(f"Error updating preview: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback to simple text preview if rendering fails
            self.preview_label.setText(f"A: {preview_text}" if show_prefix else preview_text)
            self.preview_label.setStyleSheet("background-color: black; color: white;")

    def svg_to_pixmap(self, svg_content):
        """Convert SVG content to a QPixmap that fits in the preview label"""
        try:
            from PyQt5.QtSvg import QSvgRenderer
            from PyQt5.QtCore import QByteArray, QSize, QRectF
            
            # Create a QSvgRenderer with the SVG content
            renderer = QSvgRenderer(QByteArray(svg_content.encode()))
            
            # Create a pixmap to render to - use the ACTUAL size of the preview label
            preview_size = self.preview_label.size()
            pixmap = QPixmap(preview_size)
            pixmap.fill(Qt.black)  # Fill with black background to match the preview styling
            
            # Create painter for the pixmap
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)  # Add text antialiasing
            painter.setRenderHint(QPainter.SmoothPixmapTransform)  # Add smooth transform
            
            # Render SVG to the pixmap
            renderer.render(painter)
            painter.end()
            
            return pixmap
        except Exception as e:
            print(f"Error converting SVG to pixmap: {e}")
            import traceback
            traceback.print_exc()
            
            # Return empty pixmap on error
            empty_pixmap = QPixmap(self.preview_label.size())
            empty_pixmap.fill(Qt.black)
            return empty_pixmap

    def get_current_settings(self):
        """Get the current settings from dialog controls"""
        return {
            "font_family": self.font_combo.currentText(),
            "font_size": self.size_slider.value(),
            "bold_strength": self.bold_slider.value(),
            "use_uppercase": self.uppercase_check.isChecked(),
            "show_button_prefix": self.prefix_check.isChecked(),
            "y_offset": self.offset_slider.value(),
            "prefix_color": self.prefix_color_edit.text(),
            "action_color": self.action_color_edit.text(),
            "use_prefix_gradient": self.prefix_gradient_check.isChecked(),
            "prefix_gradient_start": self.prefix_gradient_start.text(),
            "prefix_gradient_end": self.prefix_gradient_end.text(),
            "use_action_gradient": self.action_gradient_check.isChecked(),
            "action_gradient_start": self.action_gradient_start.text(),
            "action_gradient_end": self.action_gradient_end.text()
        }
    
    def apply_settings(self):
        """Apply the current settings without closing dialog"""
        settings = self.get_current_settings()
        
        # Update settings locally
        self.settings = settings
        
        # If parent provided and has the method, update parent settings
        if self.parent and hasattr(self.parent, 'update_text_settings'):
            self.parent.update_text_settings(settings)
    
    def accept_settings(self):
        """Save settings and close dialog"""
        self.apply_settings()
        self.accept()

class GridSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alignment Grid Settings")
        self.resize(350, 300)
        
        # Store reference to preview window
        self.preview = parent
        
        layout = QVBoxLayout(self)
        
        # Grid Origin group
        origin_group = QGroupBox("Grid Origin")
        origin_layout = QVBoxLayout(origin_group)
        
        # X Start position
        x_start_layout = QHBoxLayout()
        x_start_label = QLabel("X Start Position:")
        self.x_start_spin = QSpinBox()
        self.x_start_spin.setRange(0, 1000)
        self.x_start_spin.setValue(parent.grid_x_start)
        x_start_layout.addWidget(x_start_label)
        x_start_layout.addWidget(self.x_start_spin)
        origin_layout.addLayout(x_start_layout)
        
        # Y Start position
        y_start_layout = QHBoxLayout()
        y_start_label = QLabel("Y Start Position:")
        self.y_start_spin = QSpinBox()
        self.y_start_spin.setRange(0, 1000)
        self.y_start_spin.setValue(parent.grid_y_start)
        y_start_layout.addWidget(y_start_label)
        y_start_layout.addWidget(self.y_start_spin)
        origin_layout.addLayout(y_start_layout)
        
        layout.addWidget(origin_group)
        
        # Grid Spacing group
        spacing_group = QGroupBox("Grid Spacing")
        spacing_layout = QVBoxLayout(spacing_group)
        
        # X Step
        x_step_layout = QHBoxLayout()
        x_step_label = QLabel("X Step Size:")
        self.x_step_spin = QSpinBox()
        self.x_step_spin.setRange(20, 500)
        self.x_step_spin.setValue(parent.grid_x_step)
        x_step_layout.addWidget(x_step_label)
        x_step_layout.addWidget(self.x_step_spin)
        spacing_layout.addLayout(x_step_layout)
        
        # Y Step
        y_step_layout = QHBoxLayout()
        y_step_label = QLabel("Y Step Size:")
        self.y_step_spin = QSpinBox()
        self.y_step_spin.setRange(20, 500)
        self.y_step_spin.setValue(parent.grid_y_step)
        y_step_layout.addWidget(y_step_label)
        y_step_layout.addWidget(self.y_step_spin)
        spacing_layout.addLayout(y_step_layout)
        
        layout.addWidget(spacing_group)
        
        # Grid Size group
        size_group = QGroupBox("Grid Size")
        size_layout = QVBoxLayout(size_group)
        
        # Columns
        columns_layout = QHBoxLayout()
        columns_label = QLabel("Number of Columns:")
        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 10)
        self.columns_spin.setValue(parent.grid_columns)
        columns_layout.addWidget(columns_label)
        columns_layout.addWidget(self.columns_spin)
        size_layout.addLayout(columns_layout)
        
        # Rows
        rows_layout = QHBoxLayout()
        rows_label = QLabel("Number of Rows:")
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 20)
        self.rows_spin.setValue(parent.grid_rows)
        rows_layout.addWidget(rows_label)
        rows_layout.addWidget(self.rows_spin)
        size_layout.addLayout(rows_layout)
        
        layout.addWidget(size_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.apply_settings)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept_settings)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(apply_button)
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
    
    def apply_settings(self):
        """Apply grid settings to preview window"""
        self.preview.grid_x_start = self.x_start_spin.value()
        self.preview.grid_y_start = self.y_start_spin.value()
        self.preview.grid_x_step = self.x_step_spin.value()
        self.preview.grid_y_step = self.y_step_spin.value()
        self.preview.grid_columns = self.columns_spin.value()
        self.preview.grid_rows = self.rows_spin.value()
        
        # Update the grid if it's visible
        if self.preview.alignment_grid_visible:
            self.preview.show_alignment_grid()
        
        # Save settings to a file
        self.preview.save_grid_settings()
    
    def accept_settings(self):
        """Apply settings and close dialog"""
        self.apply_settings()
        self.accept()

        # Store the dialog class for later use
        self.GridSettingsDialog = GridSettingsDialog

        # Add a button to open grid settings
        if hasattr(self, 'bottom_row') and not hasattr(self, 'grid_settings_button'):
            from PyQt5.QtWidgets import QPushButton
            
            button_style = """
                QPushButton {
                    background-color: #404050;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 10px;
                    font-weight: bold;
                    font-size: 12px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #555565;
                }
                QPushButton:pressed {
                    background-color: #303040;
                }
            """
            
            self.grid_settings_button = QPushButton("Grid Settings")
            self.grid_settings_button.clicked.connect(self.show_grid_settings)
            self.grid_settings_button.setStyleSheet(button_style)
            self.bottom_row.addWidget(self.grid_settings_button)

    def show_grid_settings(self):
        """Show the grid settings dialog"""
        if hasattr(self, 'GridSettingsDialog'):
            dialog = self.GridSettingsDialog(self)
            dialog.exec_()

    def save_grid_settings(self):
        """Save grid settings to file in new settings directory"""
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Create settings object
            settings = {
                "grid_x_start": self.grid_x_start,
                "grid_y_start": self.grid_y_start,
                "grid_x_step": self.grid_x_step,
                "grid_y_step": self.grid_y_step,
                "grid_columns": self.grid_columns,
                "grid_rows": self.grid_rows
            }
            
            # Save to settings file
            settings_file = os.path.join(self.settings_dir, "grid_settings.json")
            with open(settings_file, 'w') as f:
                json.dump(settings, f)
            
            print(f"Saved grid settings to {settings_file}: {settings}")
            return True
        except Exception as e:
            print(f"Error saving grid settings: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_grid_settings(self):
        """Load grid settings from file in new settings directory"""
        try:
            # Try new location first
            settings_file = os.path.join(self.settings_dir, "grid_settings.json")
            
            # If not found, check legacy location
            if not os.path.exists(settings_file):
                legacy_path = os.path.join(self.preview_dir, "grid_settings.json")
                if os.path.exists(legacy_path):
                    # Migrate from legacy location
                    with open(legacy_path, 'r') as f:
                        settings = json.load(f)
                    
                    # Save to new location
                    os.makedirs(os.path.dirname(settings_file), exist_ok=True)
                    with open(settings_file, 'w') as f:
                        json.dump(settings, f)
                    
                    print(f"Migrated grid settings from {legacy_path} to {settings_file}")
                    
                    # Apply settings
                    self.grid_x_start = settings.get("grid_x_start", 200)
                    self.grid_y_start = settings.get("grid_y_start", 100)
                    self.grid_x_step = settings.get("grid_x_step", 300)
                    self.grid_y_step = settings.get("grid_y_step", 60)
                    self.grid_columns = settings.get("grid_columns", 3)
                    self.grid_rows = settings.get("grid_rows", 8)
                    
                    print(f"Loaded grid settings from migrated file")
                    return True
            
            # Normal path loading
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                
                # Apply settings
                self.grid_x_start = settings.get("grid_x_start", 200)
                self.grid_y_start = settings.get("grid_y_start", 100)
                self.grid_x_step = settings.get("grid_x_step", 300)
                self.grid_y_step = settings.get("grid_y_step", 60)
                self.grid_columns = settings.get("grid_columns", 3)
                self.grid_rows = settings.get("grid_rows", 8)
                
                print(f"Loaded grid settings from {settings_file}")
                return True
        except Exception as e:
            print(f"Error loading grid settings: {e}")
            import traceback
            traceback.print_exc()

        return False

# Also add the position indicator class
class PositionIndicator(QLabel):
    """Label that displays position information during dragging"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet("""
            background-color: rgba(0, 0, 0, 180);
            color: #00FFFF;
            border: 1px solid #00FFFF;
            border-radius: 4px;
            padding: 4px 8px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
        """)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(200, 45)  # Enough space for multiple lines of text
        self.hide()

    # And the position indicator methods
    def show_position_indicator(self, x, y, extra_info=None):
        """Show a position indicator with coordinates"""
        from PyQt5.QtWidgets import QLabel
        from PyQt5.QtCore import Qt, QTimer
        
        # Create position indicator if it doesn't exist yet
        if not hasattr(self, 'position_indicator'):
            self.position_indicator = QLabel(self.canvas)
            self.position_indicator.setStyleSheet("""
                background-color: rgba(0, 0, 0, 180);
                color: #00FFFF;
                border: 1px solid #00FFFF;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            """)
            self.position_indicator.setAlignment(Qt.AlignCenter)
            self.position_indicator.setFixedSize(200, 45)  # Space for multiple lines
            self.position_indicator.hide()
        
        # Format the text with X and Y coordinates
        text = f"X: {x}px, Y: {y}px"
        
        # Add extra info like distance if provided
        if extra_info:
            text += f"\n{extra_info}"
        
        self.position_indicator.setText(text)
        
        # Position the indicator near the mouse but ensure it's visible
        indicator_x = min(x + 20, self.canvas.width() - self.position_indicator.width() - 10)
        indicator_y = max(y - 50, 10)  # Above the cursor, but not off-screen
        
        self.position_indicator.move(indicator_x, indicator_y)
        self.position_indicator.show()
        self.position_indicator.raise_()
        
        # Auto-hide after a delay
        if hasattr(self, 'indicator_timer'):
            self.indicator_timer.stop()
        else:
            self.indicator_timer = QTimer(self)
            self.indicator_timer.setSingleShot(True)
            self.indicator_timer.timeout.connect(lambda: self.position_indicator.hide())
        
        self.indicator_timer.start(2000)  # Hide after 2 seconds

    def hide_position_indicator(self):
        """Hide the position indicator"""
        if hasattr(self, 'position_indicator'):
            self.position_indicator.hide()

    def create_absolute_alignment_lines(self, x=None, y=None):
        """Create absolute alignment lines at specified X or Y positions"""
        guide_lines = []
        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        
        if x is not None:
            # Create vertical guide line at fixed X
            guide_lines.append((x, 0, x, canvas_height))
        
        if y is not None:
            # Create horizontal guide line at fixed Y
            guide_lines.append((0, y, canvas_width, y))
        
        self.show_alignment_guides(guide_lines)

# 1. Update GradientPrefixLabel to remove shadow handling
class GradientPrefixLabel(DraggableLabel):
    """A label that supports gradient text for prefix and action text without shadows"""
    def __init__(self, text, parent=None, settings=None):
        # Call the parent constructor safely
        try:
            super().__init__(text, parent, settings)
        except Exception as e:
            print(f"Error in GradientPrefixLabel initialization calling super(): {e}")
            # Fallback to QLabel if DraggableLabel fails
            QLabel.__init__(self, text, parent)
            # Set draggable attributes manually
            self.draggable = False
            self.dragging = False
            
        self.settings = settings or {}
        self.prefix = ""
        self.action = ""
        self.parse_text(text)
        
        # Initialize gradient settings
        self.use_prefix_gradient = self.settings.get("use_prefix_gradient", False)
        self.use_action_gradient = self.settings.get("use_action_gradient", False)
        self.prefix_gradient_start = QColor(self.settings.get("prefix_gradient_start", "#FFC107"))
        self.prefix_gradient_end = QColor(self.settings.get("prefix_gradient_end", "#FF5722"))
        self.action_gradient_start = QColor(self.settings.get("action_gradient_start", "#2196F3"))
        self.action_gradient_end = QColor(self.settings.get("action_gradient_end", "#4CAF50"))
    
    def parse_text(self, text):
        """Parse text into prefix and action components"""
        if ": " in text:
            parts = text.split(": ", 1)
            self.prefix = parts[0]
            self.action = parts[1]
        else:
            self.prefix = ""
            self.action = text
    
    def paintEvent(self, event):
        """Paint event with correct top-to-bottom gradient color order and no shadows"""
        if not self.text():
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        # Get current font metrics
        metrics = QFontMetrics(self.font())
        
        # Vertical centering
        y = int((self.height() + metrics.ascent() - metrics.descent()) / 2)
        
        # Try to call parent paintEvent for resize handle, but safely handle if it fails
        try:
            # This might fail if parent isn't DraggableLabel
            super().paintEvent(event)
        except Exception as e:
            # If it fails, we'll just skip the resize handle drawing
            pass
        
        if self.prefix and ": " in self.text():
            prefix_text = f"{self.prefix}: "
            
            # Accurate widths for centering
            prefix_width = metrics.horizontalAdvance(prefix_text)
            action_width = metrics.horizontalAdvance(self.action)
            total_width = prefix_width + action_width
            
            # Horizontally center the combined text block
            x = int((self.width() - total_width) / 2)
            
            # Calculate prefix rectangle for gradient
            prefix_rect = metrics.boundingRect(prefix_text)
            prefix_rect.moveLeft(int(x))
            prefix_rect.moveTop(int(y - metrics.ascent()))
            
            if self.use_prefix_gradient and self.settings.get("use_prefix_gradient", False):
                # Create vertical gradient (top to bottom) for prefix
                gradient = QLinearGradient(
                    prefix_rect.left(), prefix_rect.top(),
                    prefix_rect.left(), prefix_rect.bottom()
                )
                # Set start color at top (0.0) and end color at bottom (1.0)
                gradient.setColorAt(0, self.prefix_gradient_start)
                gradient.setColorAt(1, self.prefix_gradient_end)
                
                # Apply gradient using QPen with QBrush
                gradient_brush = QBrush(gradient)
                painter.setPen(QPen(gradient_brush, 1))
            else:
                # Solid color
                prefix_color = QColor(self.settings.get("prefix_color", "#FFC107"))
                painter.setPen(prefix_color)
                
            # Draw prefix text
            painter.drawText(int(x), int(y), prefix_text)
            
            # Calculate action rectangle for gradient
            action_rect = metrics.boundingRect(self.action)
            action_rect.moveLeft(int(x + prefix_width))
            action_rect.moveTop(int(y - metrics.ascent()))
            
            if self.use_action_gradient and self.settings.get("use_action_gradient", False):
                # Create vertical gradient (top to bottom) for action
                gradient = QLinearGradient(
                    action_rect.left(), action_rect.top(),
                    action_rect.left(), action_rect.bottom()
                )
                # Set colors in top-to-bottom order
                gradient.setColorAt(0, self.action_gradient_start)
                gradient.setColorAt(1, self.action_gradient_end)
                
                # Apply gradient using QPen with QBrush
                gradient_brush = QBrush(gradient)
                painter.setPen(QPen(gradient_brush, 1))
            else:
                # Solid color
                action_color = QColor(self.settings.get("action_color", "#FFFFFF"))
                painter.setPen(action_color)
                
            # Draw action text precisely positioned after prefix
            painter.drawText(int(x + prefix_width), int(y), self.action)
        else:
            # Center single text
            text = self.text()
            text_width = metrics.horizontalAdvance(text)
            x = int((self.width() - text_width) / 2)
            
            # Create text rectangle for gradient
            text_rect = metrics.boundingRect(text)
            text_rect.moveLeft(int(x))
            text_rect.moveTop(int(y - metrics.ascent()))
            
            if self.use_action_gradient and self.settings.get("use_action_gradient", False):
                # Create vertical gradient (top to bottom)
                gradient = QLinearGradient(
                    text_rect.left(), text_rect.top(),
                    text_rect.left(), text_rect.bottom()
                )
                # Set colors in top-to-bottom order
                gradient.setColorAt(0, self.action_gradient_start)
                gradient.setColorAt(1, self.action_gradient_end)
                
                # Apply gradient
                gradient_brush = QBrush(gradient)
                painter.setPen(QPen(gradient_brush, 1))
            else:
                # Solid color
                action_color = QColor(self.settings.get("action_color", "#FFFFFF"))
                painter.setPen(action_color)
                
            # Draw text
            painter.drawText(int(x), int(y), text)

# 2. Update ColoredPrefixLabel to remove shadow handling

class ColoredPrefixLabel(DraggableLabel):
    """A label that supports different colors for prefix and action text without shadows"""
    def __init__(self, text, parent=None, settings=None):
        # Call the parent constructor safely
        try:
            super().__init__(text, parent, settings)
        except Exception as e:
            print(f"Error in ColoredPrefixLabel initialization calling super(): {e}")
            # Fallback to QLabel if DraggableLabel fails
            QLabel.__init__(self, text, parent)
            # Set draggable attributes manually
            self.draggable = False
            self.dragging = False
        
        self.settings = settings or {}
        self.prefix = ""
        self.action = ""
        self.parse_text(text)
    
    def parse_text(self, text):
        """Parse text into prefix and action components"""
        if ": " in text:
            parts = text.split(": ", 1)
            self.prefix = parts[0]
            self.action = parts[1]
        else:
            self.prefix = ""
            self.action = text
    
    def paintEvent(self, event):
        """Override paint event to draw text with different colors without shadows"""
        if not self.text():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Get current font metrics
        metrics = QFontMetrics(self.font())

        # Vertical centering
        y = int((self.height() + metrics.ascent() - metrics.descent()) / 2)

        # Get colors from settings
        prefix_color = QColor(self.settings.get("prefix_color", "#FFC107"))
        action_color = QColor(self.settings.get("action_color", "#FFFFFF"))

        # Try to call parent paintEvent for resize handle, but safely handle if it fails
        try:
            # This might fail if parent isn't DraggableLabel
            super().paintEvent(event)
        except Exception as e:
            # If it fails, we'll just skip the resize handle drawing
            pass

        if self.prefix and ": " in self.text():
            prefix_text = f"{self.prefix}: "

            # Accurate widths
            prefix_width = metrics.horizontalAdvance(prefix_text)
            action_width = metrics.horizontalAdvance(self.action)
            total_width = prefix_width + action_width

            # Horizontally center the combined text block
            x = int((self.width() - total_width) / 2)

            # Draw prefix
            painter.setPen(prefix_color)
            painter.drawText(x, y, prefix_text)

            # Draw action text right after prefix
            painter.setPen(action_color)
            painter.drawText(x + prefix_width, y, self.action)

        else:
            # Center full single-part text
            text = self.text()

            text_width = metrics.horizontalAdvance(text)
            x = int((self.width() - text_width) / 2)

            painter.setPen(action_color)
            painter.drawText(x, y, text)


# 6. Modify the ColoredDraggableLabel class to remove shadow functionality
class ColoredDraggableLabel(DraggableLabel):
    """A draggable label that supports different colors for prefix and action text"""
    def __init__(self, text, parent=None, settings=None):
        super().__init__(text, parent, settings)
        self.settings = settings or {}
        self.prefix = ""
        self.action = ""
        self.parse_text(text)
    
    def mousePressEvent(self, event):
        """Override to ensure proper offset tracking"""
        # IMPORTANT: Call DraggableLabel's method to ensure proper offset tracking
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Override to ensure proper offset preservation"""
        # IMPORTANT: Call DraggableLabel's method to ensure proper movement
        super().mouseMoveEvent(event)
    
    def parse_text(self, text):
        """Parse text into prefix and action components"""
        if ": " in text:
            parts = text.split(": ", 1)
            self.prefix = parts[0]
            self.action = parts[1]
        else:
            self.prefix = ""
            self.action = text
    
    def paintEvent(self, event):
        """Override paint event to draw text with different colors without shadows"""
        if not self.text():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Get current font metrics
        metrics = QFontMetrics(self.font())

        # Vertical centering
        y = int((self.height() + metrics.ascent() - metrics.descent()) / 2)

        # Get colors from settings
        prefix_color = QColor(self.settings.get("prefix_color", "#FFC107"))
        action_color = QColor(self.settings.get("action_color", "#FFFFFF"))

        if self.prefix and ": " in self.text():
            prefix_text = f"{self.prefix}: "

            # Accurate widths
            prefix_width = metrics.horizontalAdvance(prefix_text)
            action_width = metrics.horizontalAdvance(self.action)
            total_width = prefix_width + action_width

            # Horizontally center the combined text block
            x = int((self.width() - total_width) / 2)

            # Draw prefix
            painter.setPen(prefix_color)
            painter.drawText(x, y, prefix_text)

            # Draw action text right after prefix
            painter.setPen(action_color)
            painter.drawText(x + prefix_width, y, self.action)

        else:
            # Center full single-part text
            text = self.text()

            text_width = metrics.horizontalAdvance(text)
            x = int((self.width() - text_width) / 2)

            painter.setPen(action_color)
            painter.drawText(x, y, text)

# 5. Modify the GradientDraggableLabel class to remove shadow functionality
class GradientDraggableLabel(DraggableLabel):
    """A draggable label that supports gradient text for prefix and action text"""
    def __init__(self, text, parent=None, settings=None):
        super().__init__(text, parent, settings)
        self.settings = settings or {}
        self.prefix = ""
        self.action = ""
        self.parse_text(text)
        
        # Initialize gradient settings
        self.use_prefix_gradient = self.settings.get("use_prefix_gradient", False)
        self.use_action_gradient = self.settings.get("use_action_gradient", False)
        self.prefix_gradient_start = QColor(self.settings.get("prefix_gradient_start", "#FFC107"))
        self.prefix_gradient_end = QColor(self.settings.get("prefix_gradient_end", "#FF5722"))
        self.action_gradient_start = QColor(self.settings.get("action_gradient_start", "#2196F3"))
        self.action_gradient_end = QColor(self.settings.get("action_gradient_end", "#4CAF50"))
    
    def mousePressEvent(self, event):
        """Override to ensure proper offset tracking"""
        # IMPORTANT: Call DraggableLabel's method to ensure proper offset tracking
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Override to ensure proper offset preservation"""
        # IMPORTANT: Call DraggableLabel's method to ensure proper movement
        super().mouseMoveEvent(event)
    
    def parse_text(self, text):
        """Parse text into prefix and action components"""
        if ": " in text:
            parts = text.split(": ", 1)
            self.prefix = parts[0]
            self.action = parts[1]
        else:
            self.prefix = ""
            self.action = text
    
    def paintEvent(self, event):
        """Paint event with gradient rendering without shadows"""
        if not self.text():
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        # Get current font metrics
        metrics = QFontMetrics(self.font())
        
        # Vertical centering
        y = int((self.height() + metrics.ascent() - metrics.descent()) / 2)
        
        if self.prefix and ": " in self.text():
            prefix_text = f"{self.prefix}: "
            
            # Accurate widths for centering
            prefix_width = metrics.horizontalAdvance(prefix_text)
            action_width = metrics.horizontalAdvance(self.action)
            total_width = prefix_width + action_width
            
            # Horizontally center the combined text block
            x = int((self.width() - total_width) / 2)
            
            # Calculate prefix rectangle for gradient
            prefix_rect = metrics.boundingRect(prefix_text)
            prefix_rect.moveLeft(int(x))
            prefix_rect.moveTop(int(y - metrics.ascent()))
            
            if self.use_prefix_gradient and self.settings.get("use_prefix_gradient", False):
                # Create vertical gradient (top to bottom) for prefix
                gradient = QLinearGradient(
                    prefix_rect.left(), prefix_rect.top(),
                    prefix_rect.left(), prefix_rect.bottom()
                )
                # Set start color at top (0.0) and end color at bottom (1.0)
                gradient.setColorAt(0, self.prefix_gradient_start)
                gradient.setColorAt(1, self.prefix_gradient_end)
                
                # Apply gradient using QPen with QBrush
                gradient_brush = QBrush(gradient)
                painter.setPen(QPen(gradient_brush, 1))
            else:
                # Solid color
                prefix_color = QColor(self.settings.get("prefix_color", "#FFC107"))
                painter.setPen(prefix_color)
                
            # Draw prefix text
            painter.drawText(int(x), int(y), prefix_text)
            
            # Calculate action rectangle for gradient
            action_rect = metrics.boundingRect(self.action)
            action_rect.moveLeft(int(x + prefix_width))
            action_rect.moveTop(int(y - metrics.ascent()))
            
            if self.use_action_gradient and self.settings.get("use_action_gradient", False):
                # Create vertical gradient (top to bottom) for action
                gradient = QLinearGradient(
                    action_rect.left(), action_rect.top(),
                    action_rect.left(), action_rect.bottom()
                )
                # Set colors in top-to-bottom order
                gradient.setColorAt(0, self.action_gradient_start)
                gradient.setColorAt(1, self.action_gradient_end)
                
                # Apply gradient using QPen with QBrush
                gradient_brush = QBrush(gradient)
                painter.setPen(QPen(gradient_brush, 1))
            else:
                # Solid color
                action_color = QColor(self.settings.get("action_color", "#FFFFFF"))
                painter.setPen(action_color)
                
            # Draw action text precisely positioned after prefix
            painter.drawText(int(x + prefix_width), int(y), self.action)
        else:
            # Center single text
            text = self.text()
            text_width = metrics.horizontalAdvance(text)
            x = int((self.width() - text_width) / 2)
            
            # Create text rectangle for gradient
            text_rect = metrics.boundingRect(text)
            text_rect.moveLeft(int(x))
            text_rect.moveTop(int(y - metrics.ascent()))
            
            if self.use_action_gradient and self.settings.get("use_action_gradient", False):
                # Create vertical gradient (top to bottom)
                gradient = QLinearGradient(
                    text_rect.left(), text_rect.top(),
                    text_rect.left(), text_rect.bottom()
                )
                # Set colors in top-to-bottom order
                gradient.setColorAt(0, self.action_gradient_start)
                gradient.setColorAt(1, self.action_gradient_end)
                
                # Apply gradient
                gradient_brush = QBrush(gradient)
                painter.setPen(QPen(gradient_brush, 1))
            else:
                # Solid color
                action_color = QColor(self.settings.get("action_color", "#FFFFFF"))
                painter.setPen(action_color)
                
            # Draw text
            painter.drawText(int(x), int(y), text)
    
class LogoSettingsDialog(QDialog):
    """Dialog for configuring logo appearance and position with improved center handling"""
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Logo Settings")
        self.resize(400, 350)
        
        # Store parent reference for settings access
        self.parent = parent
        
        # Use provided settings or load defaults
        self.settings = settings or {
            "logo_visible": True,
            "logo_position": "top-left",
            "width_percentage": 15,
            "height_percentage": 15,
            "custom_position": False,
            "x_position": 20,
            "y_position": 20,
            "maintain_aspect": True
        }
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Position selection group
        position_group = QGroupBox("Logo Position")
        position_layout = QVBoxLayout(position_group)
        
        # Position buttons grid
        pos_grid = QGridLayout()
        
        # Create position buttons
        self.position_buttons = {}
        positions = [
            ("top-left", 0, 0, "Top Left"),
            ("top-center", 0, 1, "Top Center"),
            ("top-right", 0, 2, "Top Right"),
            ("center-left", 1, 0, "Center Left"),
            ("center", 1, 1, "Center"),
            ("center-right", 1, 2, "Center Right"),
            ("bottom-left", 2, 0, "Bottom Left"),
            ("bottom-center", 2, 1, "Bottom Center"),
            ("bottom-right", 2, 2, "Bottom Right")
        ]
        
        for pos_id, row, col, label in positions:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda checked, p=pos_id: self.set_position(p))
            
            # Check if this is the current position
            if pos_id == self.settings.get("logo_position", "top-left"):
                btn.setChecked(True)
            
            pos_grid.addWidget(btn, row, col)
            self.position_buttons[pos_id] = btn
        
        position_layout.addLayout(pos_grid)
        
        # Custom position checkbox
        self.custom_position_check = QCheckBox("Use Custom Position (X, Y)")
        self.custom_position_check.setChecked(self.settings.get("custom_position", False))
        self.custom_position_check.toggled.connect(self.toggle_custom_position)
        position_layout.addWidget(self.custom_position_check)
        
        # Custom position controls
        custom_pos_layout = QHBoxLayout()
        
        self.x_spin = QSpinBox()
        self.x_spin.setMinimum(0)
        self.x_spin.setMaximum(1920)  # Increased for higher resolution displays
        self.x_spin.setValue(self.settings.get("x_position", 20))
        
        self.y_spin = QSpinBox()
        self.y_spin.setMinimum(0)
        self.y_spin.setMaximum(1080)  # Increased for higher resolution displays
        self.y_spin.setValue(self.settings.get("y_position", 20))
        
        custom_pos_layout.addWidget(QLabel("X:"))
        custom_pos_layout.addWidget(self.x_spin)
        custom_pos_layout.addWidget(QLabel("Y:"))
        custom_pos_layout.addWidget(self.y_spin)
        
        position_layout.addLayout(custom_pos_layout)
        
        # Note about center position
        center_note = QLabel("Note: Center position ignores custom X/Y values")
        center_note.setStyleSheet("color: #666; font-style: italic;")
        position_layout.addWidget(center_note)
        
        layout.addWidget(position_group)
        
        # Size settings group
        size_group = QGroupBox("Logo Size")
        size_layout = QVBoxLayout(size_group)
        
        # Width percentage slider
        width_row = QHBoxLayout()
        width_label = QLabel("Width %:")
        
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setMinimum(5)
        self.width_slider.setMaximum(50)
        self.width_slider.setValue(int(self.settings.get("width_percentage", 15)))
        
        self.width_value = QLabel(f"{self.width_slider.value()}%")
        self.width_slider.valueChanged.connect(
            lambda v: self.width_value.setText(f"{v}%")
        )
        
        width_row.addWidget(width_label)
        width_row.addWidget(self.width_slider)
        width_row.addWidget(self.width_value)
        size_layout.addLayout(width_row)
        
        # Height percentage slider
        height_row = QHBoxLayout()
        height_label = QLabel("Height %:")
        
        self.height_slider = QSlider(Qt.Horizontal)
        self.height_slider.setMinimum(5)
        self.height_slider.setMaximum(50)
        self.height_slider.setValue(int(self.settings.get("height_percentage", 15)))
        
        self.height_value = QLabel(f"{self.height_slider.value()}%")
        self.height_slider.valueChanged.connect(
            lambda v: self.height_value.setText(f"{v}%")
        )
        
        height_row.addWidget(height_label)
        height_row.addWidget(self.height_slider)
        height_row.addWidget(self.height_value)
        size_layout.addLayout(height_row)
        
        # Add maintain aspect ratio checkbox
        self.aspect_check = QCheckBox("Maintain Aspect Ratio")
        self.aspect_check.setChecked(self.settings.get("maintain_aspect", True))
        size_layout.addWidget(self.aspect_check)
        
        layout.addWidget(size_group)
        
        # Preview section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_label = QLabel("Logo Preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(100)
        self.preview_label.setStyleSheet("background-color: black; color: white;")
        
        preview_layout.addWidget(self.preview_label)
        layout.addWidget(preview_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_settings)
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept_settings)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.apply_button)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # Initialize UI based on settings
        self.toggle_custom_position(self.settings.get("custom_position", False))
        
        # If center position is selected, disable custom position
        if self.settings.get("logo_position") == "center":
            self.update_for_center_position()
    
    def set_position(self, position):
        """Set the logo position with special handling for center"""
        for pos_id, button in self.position_buttons.items():
            button.setChecked(pos_id == position)
        
        # Special handling for center position
        if position == "center":
            self.update_for_center_position()
        else:
            # Re-enable custom position option for non-center positions
            self.custom_position_check.setEnabled(True)
            
    def update_for_center_position(self):
        """Apply special settings when center position is selected"""
        # Disable and uncheck custom position when center is selected
        self.custom_position_check.setChecked(False)
        self.custom_position_check.setEnabled(False)
        self.x_spin.setEnabled(False)
        self.y_spin.setEnabled(False)
    
    def toggle_custom_position(self, enabled):
        """Toggle custom position controls"""
        # Skip if center is selected
        if self.is_center_selected():
            return
            
        self.x_spin.setEnabled(enabled)
        self.y_spin.setEnabled(enabled)
        
        # Update button states - disable position buttons if custom is enabled
        for pos_id, button in self.position_buttons.items():
            if pos_id != "center":  # Center is special case
                button.setEnabled(not enabled)
    
    def is_center_selected(self):
        """Check if center position is currently selected"""
        return self.position_buttons["center"].isChecked()
    
    def get_current_settings(self):
        """Get the current settings from dialog controls"""
        settings = {
            "custom_position": True,  # Always use custom position
            "width_percentage": self.width_slider.value(),
            "height_percentage": self.height_slider.value(),
            "maintain_aspect": self.aspect_check.isChecked(),
            "logo_visible": self.settings.get("logo_visible", True),  # Preserve visibility
            "keep_horizontally_centered": self.center_horizontally_check.isChecked(),
            "x_position": self.x_spin.value(),
            "y_position": self.y_spin.value()
        }
        
        return settings
    
    def apply_settings(self):
        """Apply the current settings without closing dialog"""
        settings = self.get_current_settings()
        
        # Update settings locally
        self.settings = settings
        
        # If parent provided and has the method, update parent settings
        if self.parent and hasattr(self.parent, 'update_logo_settings'):
            self.parent.update_logo_settings(settings)
    
    def accept_settings(self):
        """Save settings and close dialog"""
        self.apply_settings()
        self.accept()

    def show_logo_settings(self):
        """Show dialog to configure logo settings"""
        dialog = LogoSettingsDialog(self, self.logo_settings)
        if dialog.exec_() == QDialog.Accepted:
            print("Logo settings updated and saved")
        
        def update_logo_settings(self, settings):
            """Update logo settings and apply to the logo"""
            # Update local settings
            self.logo_settings = settings
            
            # Update logo visibility
            if hasattr(self, 'logo_label'):
                self.logo_visible = settings.get("logo_visible", True)
                self.logo_label.setVisible(self.logo_visible)
                
                # Update logo position and size
                self.update_logo_display()
            
            # Save settings to file
            self.save_logo_settings()

def show_preview(rom_name, game_data, mame_dir):
    """Show the preview window for a specific ROM"""
    # Create and show preview window
    preview = PreviewWindow(rom_name, game_data, mame_dir)
    preview.showFullScreen()  # For a fullscreen experience
    return preview
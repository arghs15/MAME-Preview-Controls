import os
import random
import sys
import json
from PyQt5 import sip
from PyQt5.QtWidgets import (QGridLayout, QLayout, QLineEdit, QMainWindow, QMessageBox, QSizePolicy, QSpinBox, QVBoxLayout, QHBoxLayout, QWidget, 
                            QLabel, QPushButton, QApplication, QDesktopWidget,
                            QDialog, QGroupBox, QCheckBox, QSlider, QComboBox)
from PyQt5.QtGui import QBrush, QLinearGradient, QPalette, QPixmap, QFont, QColor, QPainter, QPen, QFontMetrics
from PyQt5.QtCore import Qt, QPoint, QTimer

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
        """Enhanced initialization with correct parameter handling and order"""
        
        # Start timing
        import time
        self._init_start_time = time.time()
        
        def checkpoint(name):
            """Record a timing checkpoint"""
            current_time = time.time()
            elapsed = current_time - self._init_start_time
            print(f"⏱️  Checkpoint '{name}': {elapsed:.3f}s")
        
        # Make sure we call super().__init__ with the correct parent parameter
        super().__init__(parent)
        checkpoint("super_init")

        # Path handling - Start invisible
        self.setVisible(False)
        self.rom_name = rom_name
        self.game_data = game_data
        checkpoint("basic_setup")
        
        # Initialize conversion maps
        self.initialize_conversion_maps()
        
        # Initialize flags and settings
        self._fonts_loaded = False
        self._initializing = True
        self.debug_mode = False
        
        # Initialize input mode
        self.use_xinput = game_data.get('input_mode') == 'xinput' if game_data else True
        print(f"Input mode for {rom_name}: {'XInput' if self.use_xinput else 'DirectInput'}")
        checkpoint("conversion_maps")

        # Set up directory structure
        if hasattr(self, 'setup_directory_structure'):
            self.setup_directory_structure()
        else:
            # Legacy path handling
            self.app_dir = get_application_path()
            
            if isinstance(mame_dir, str) and os.path.basename(mame_dir).lower() == "preview":
                self.mame_dir = os.path.dirname(mame_dir)
            else:
                self.mame_dir = mame_dir
                
            self.preview_dir = os.path.join(self.mame_dir, "preview")
            self.settings_dir = os.path.join(self.preview_dir, "settings")
            self.fonts_dir = os.path.join(self.preview_dir, "fonts")
            
            os.makedirs(self.settings_dir, exist_ok=True)
            os.makedirs(self.fonts_dir, exist_ok=True)
        
        print(f"ROM: {rom_name}")
        print(f"App directory: {self.app_dir if hasattr(self, 'app_dir') else 'Not set'}")
        print(f"MAME directory: {self.mame_dir}")
        print(f"Preview directory: {self.preview_dir if hasattr(self, 'preview_dir') else 'Not set'}")
        checkpoint("directory_setup")
        
        # Initialize control storage
        self.control_labels = {}
        self.bg_label = None
        
        # Add clean preview mode parameters
        self.hide_buttons = hide_buttons
        self.clean_mode = clean_mode
        
        print(f"Initializing PreviewWindow for ROM: {rom_name}")
        print(f"Clean mode: {clean_mode}, Hide buttons: {hide_buttons}")

        # Force window to be displayed in the correct place
        self.parent = parent
        
        try:
            # 🔥 CRITICAL: Load settings in correct order
            
            # 1. Load text settings FIRST (required for font loading)
            try:
                self.text_settings = self.load_text_settings()
                print("✅ Text settings loaded successfully")
            except Exception as e:
                print(f"⚠️  Error loading text settings: {e}")
                # Provide fallback defaults
                self.text_settings = {
                    "font_family": "Arial",
                    "font_size": 28,
                    "bold_strength": 2,
                    "use_uppercase": False,
                    "y_offset": -40,
                    "show_button_prefix": True,
                    "prefix_color": "#FFC107",
                    "action_color": "#FFFFFF",
                    "use_prefix_gradient": False,
                    "use_action_gradient": False,
                    "prefix_gradient_start": "#FFC107",
                    "prefix_gradient_end": "#FF5722",
                    "action_gradient_start": "#2196F3",
                    "action_gradient_end": "#4CAF50"
                }
            checkpoint("text_settings")
            
            # 2. Load logo settings
            try:
                self.logo_settings = self.load_logo_settings()
            except Exception as e:
                print(f"⚠️  Error loading logo settings: {e}")
                self.logo_settings = {
                    "logo_visible": True,
                    "custom_position": True,
                    "x_position": 20,
                    "y_position": 20,
                    "width_percentage": 15,
                    "height_percentage": 15,
                    "maintain_aspect": True,
                    "keep_horizontally_centered": False
                }
            checkpoint("logo_settings")
            
            # 3. Load bezel and directional settings
            try:
                bezel_settings = self.load_bezel_settings_with_directional()
                self.bezel_visible = bezel_settings.get("bezel_visible", False)
            except Exception as e:
                print(f"⚠️  Error loading bezel settings: {e}")
                self.bezel_visible = False
                # Set defaults
                self.directional_mode = "show_all"
                self.joystick_visible = True
                self.hide_specialized_with_directional = False
                self.auto_show_directionals_for_directional_only = True
            checkpoint("bezel_settings")

            # 4. Pre-analyze the game for directional-only status
            directional_count = 0
            button_count = 0
            
            # Analyze game controls to determine if it's standard-directional-only
            self.analyze_game_controls_improved()

            print(f"Early game control analysis: {directional_count} directional, {button_count} buttons")
            print(f"Is directional-only game: {self.is_directional_only_game}")
            
            # Get the auto-show setting
            self.auto_show_directionals_for_directional_only = bezel_settings.get("auto_show_directionals_for_directional_only", True)
            
            # Set joystick visibility - critical to do this before any UI elements are created
            self.joystick_visible = bezel_settings.get("joystick_visible", True)
            
            # IMPORTANT: Pre-determine whether directional controls should be visible
            self.should_show_directional = self.joystick_visible
            if self.is_directional_only_game and self.auto_show_directionals_for_directional_only:
                self.should_show_directional = True
                print("Auto-showing directional controls for directional-only game")
            else:
                print(f"Using standard joystick visibility: {self.joystick_visible}")
            
            # Initialize texts_visible BEFORE creating controls
            self.texts_visible = True

            # Check if button prefix setting is initialized
            if "show_button_prefix" not in self.text_settings:
                self.text_settings["show_button_prefix"] = True
                print("Initialized button prefix setting to default (True)")
            else:
                print(f"Loaded button prefix setting: {self.text_settings['show_button_prefix']}")
            checkpoint("game_analysis")

            # 5. CRITICAL: Force font loading BEFORE creating labels (now text_settings exists)
            try:
                self.load_and_register_fonts()
                print("✅ Fonts loaded successfully")
            except Exception as e:
                print(f"⚠️  Error loading fonts: {e}")
                # Create a basic fallback font
                from PyQt5.QtGui import QFont
                self.current_font = QFont("Arial", 28)
            checkpoint("font_loading")
            
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
            checkpoint("ui_setup")

            # Load background
            self.load_background_image_fullscreen()

            # Create control labels - WITH clean mode parameter
            self.create_control_labels(clean_mode=self.clean_mode)
            checkpoint("control_labels")

            # Make sure the font is properly applied
            self.apply_text_settings()
            
            # Initialize alignment grid system
            self.alignment_grid_visible = False
            self.grid_x_start = 200
            self.grid_x_step = 300
            self.grid_y_start = 100
            self.grid_y_step = 60
            self.grid_columns = 3
            self.grid_rows = 8
            self.grid_lines = []

            # Load grid settings if available
            try:
                if hasattr(self, 'load_grid_settings'):
                    self.load_grid_settings()
            except Exception as e:
                print(f"Error loading grid settings: {e}")
            checkpoint("grid_setup")
            
            # Add logo if enabled
            if self.logo_visible:
                self.add_logo()
                QTimer.singleShot(100, self.force_logo_resize)
            
            # Create button frame as a FLOATING OVERLAY
            if not self.hide_buttons and not self.clean_mode:
                self.create_floating_button_frame()
            
            # Track whether texts are visible
            self.texts_visible = True
            
            # Track current screen
            self.current_screen = self.load_screen_setting_from_config()

            # Now move to that screen
            self.initializing_screen = True
            self.current_screen = self.load_screen_setting_from_config()
            self.move_to_screen(self.current_screen)
            self.initializing_screen = False
            checkpoint("screen_setup")
            
            # Bind ESC key to close
            self.keyPressEvent = self.handle_key_press
            
            # Apply proper layering
            self.layering_for_bezel()
            self.integrate_bezel_support()
            self.canvas.resizeEvent = self.on_canvas_resize_with_background
        
            # Add bezel state initialization after a short delay
            QTimer.singleShot(500, self.ensure_bezel_state)
            
            print("PreviewWindow initialization complete")
            checkpoint("bezel_integration")
            
            # Initialize directional mode from saved settings AFTER creating button frame
            if not hasattr(self, '_directional_mode_initialized'):
                self.init_directional_mode_on_startup()
            
            # Make sure we have a transparent background
            transparent_bg_path = self.initialize_transparent_background()
            if transparent_bg_path:
                self.load_background_image_fullscreen(force_default=transparent_bg_path)
            
            self.initialize_controller_close()
            checkpoint("controller_setup")
            
            # CRITICAL: Enforce layer order AFTER everything is created but BEFORE showing
            self.enforce_layer_order()
            
            # Initialize no buttons notification support
            self.no_buttons_label = None
            self.no_buttons_visible = False

            # Create No Buttons notification AFTER control analysis and canvas creation
            self.create_no_buttons_notification()

            # Debug check
            if hasattr(self, 'no_buttons_label') and self.no_buttons_label:
                print(f"DEBUG: No buttons label created successfully for {self.rom_name}")
                print(f"DEBUG: has_any_buttons = {self.has_any_buttons}")
            else:
                print(f"DEBUG: No buttons label NOT created for {self.rom_name}")
                print(f"DEBUG: has_any_buttons = {getattr(self, 'has_any_buttons', 'NOT SET')}")

            # Update No Buttons visibility after a delay
            QTimer.singleShot(400, self.update_no_buttons_visibility)
            checkpoint("no_buttons_setup")

            # Set visibility and finalize
            self.setVisible(True)

            print(f"Window size: {self.width()}x{self.height()}")
            print(f"Canvas size: {self.canvas.width()}x{self.canvas.height()}")
            
            # Finalize initialization
            self._initializing = False
            QTimer.singleShot(500, self._finalize_initialization)
            checkpoint("final_setup")

            # Calculate total time
            total_time = time.time() - self._init_start_time
            print(f"\n🚀 PreviewWindow initialized in {total_time:.3f} seconds")

        except Exception as e:
            print(f"Error in PreviewWindow initialization: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error initializing preview: {e}")
            self.close()

    def _finalize_initialization(self):
        """Consolidate all final initialization tasks with guards"""
        
        # Guard against multiple finalization
        if hasattr(self, '_finalization_complete'):
            print("Finalization already complete, skipping...")
            return
        
        print("=== STARTING FINAL INITIALIZATION ===")
        
        # Track what we actually do
        tasks_performed = []
        
        # Only run each task if needed
        if not hasattr(self, '_bezel_state_ensured'):
            self.ensure_bezel_state()
            self._bezel_state_ensured = True
            tasks_performed.append("bezel_state")
        
        if not hasattr(self, '_labels_force_resized'):
            self.force_resize_all_labels()
            self._labels_force_resized = True
            tasks_performed.append("force_resize")
        
        if not hasattr(self, '_text_settings_applied'):
            self.apply_text_settings()
            self._text_settings_applied = True
            tasks_performed.append("text_settings")
        
        # Layer order can be enforced multiple times safely, but limit it
        if not hasattr(self, '_layer_order_enforced'):
            self.enforce_layer_order()
            self._layer_order_enforced = True
            tasks_performed.append("layer_order")
        
        if not hasattr(self, '_no_buttons_updated'):
            self.update_no_buttons_visibility()
            self._no_buttons_updated = True
            tasks_performed.append("no_buttons")
        
        if not hasattr(self, '_screen_detected'):
            self.detect_screen_after_startup()
            self._screen_detected = True
            tasks_performed.append("screen_detect")
        
        # Set completion flag
        self._finalization_complete = True
        
        print(f"=== FINALIZATION COMPLETE ===")
        print(f"Tasks performed: {', '.join(tasks_performed) if tasks_performed else 'none (already done)'}")
    
    def create_no_buttons_notification(self):
        """Create the 'No Buttons Used' notification label"""
        
        print("Creating No Buttons notification for button-less game")
        
        notification_text = "NB: No Buttons Used"
        if self.text_settings.get("use_uppercase", False):
            notification_text = notification_text.upper()
        
        # Get gradient settings
        use_prefix_gradient = self.text_settings.get("use_prefix_gradient", False)
        use_action_gradient = self.text_settings.get("use_action_gradient", False)
        use_gradient = use_prefix_gradient or use_action_gradient
        
        try:
            # Create the appropriate label type based on gradient settings
            if use_gradient:
                # Use the gradient-enabled label
                self.no_buttons_label = GradientDraggableLabel(notification_text, self.canvas, settings=self.text_settings)
                
                # Set gradient properties explicitly
                self.no_buttons_label.use_prefix_gradient = use_prefix_gradient
                self.no_buttons_label.use_action_gradient = use_action_gradient
                self.no_buttons_label.prefix_gradient_start = QColor(self.text_settings.get("prefix_gradient_start", "#FFC107"))
                self.no_buttons_label.prefix_gradient_end = QColor(self.text_settings.get("prefix_gradient_end", "#FF5722"))
                self.no_buttons_label.action_gradient_start = QColor(self.text_settings.get("action_gradient_start", "#2196F3"))
                self.no_buttons_label.action_gradient_end = QColor(self.text_settings.get("action_gradient_end", "#4CAF50"))
            else:
                # Use the color-enabled label
                self.no_buttons_label = ColoredDraggableLabel(notification_text, self.canvas, settings=self.text_settings)
            
            # Apply font
            if hasattr(self, 'current_font') and self.current_font:
                self.no_buttons_label.setFont(self.current_font)
            
            # Style the label with proper font family
            action_color = self.text_settings.get("action_color", "#FFFFFF")
            font_family = self.current_font.family() if hasattr(self, 'current_font') else "Arial"
            self.no_buttons_label.setStyleSheet(f"color: {action_color}; background-color: transparent; border: none; font-family: '{font_family}';")
            
            # Configure label sizing
            self.no_buttons_label.setMinimumSize(0, 0)
            self.no_buttons_label.setMaximumSize(16777215, 16777215)
            self.no_buttons_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
            # Make sure settings are properly stored
            self.no_buttons_label.settings = self.text_settings.copy()
            self.no_buttons_label.adjustSize()

            # Calculate proper width with padding
            font_metrics = QFontMetrics(self.no_buttons_label.font())
            text_width = font_metrics.horizontalAdvance(notification_text)
            
            # Add generous padding for the notification text
            padding = 60
            label_width = text_width + padding
            label_height = self.no_buttons_label.height()
            self.no_buttons_label.resize(label_width, label_height)
            
            # Position the notification
            saved_positions = self.load_saved_positions()
            if "NO_BUTTONS_NOTIFICATION" in saved_positions:
                pos_x, pos_y = saved_positions["NO_BUTTONS_NOTIFICATION"]
                y_offset = self.text_settings.get("y_offset", -40)
                x, y = pos_x, pos_y + y_offset
            else:
                x = (self.canvas.width() - label_width) // 2
                y = (self.canvas.height() - label_height) // 2
            
            self.no_buttons_label.move(x, y)
            
            # Set up dragging if not in clean mode
            if not self.clean_mode:
                self.no_buttons_label.mousePressEvent = lambda event: self.on_label_press(event, self.no_buttons_label)
                self.no_buttons_label.mouseMoveEvent = lambda event: self.on_label_move(event, self.no_buttons_label)
                self.no_buttons_label.mouseReleaseEvent = lambda event: self.on_label_release(event, self.no_buttons_label)
            
            # Initially hide the notification
            self.no_buttons_label.setVisible(False)
            self.no_buttons_visible = False
            
            # Add to control_labels immediately so it gets processed by apply_text_settings
            self.control_labels["NO_BUTTONS_NOTIFICATION"] = {
                'label': self.no_buttons_label,
                'action': "No Buttons Used",
                'prefix': "",
                'original_pos': QPoint(x, y - self.text_settings.get("y_offset", -40))
            }
            
            print(f"DEBUG: No buttons label positioned at ({x}, {y})")
            print(f"DEBUG: Label type: {type(self.no_buttons_label).__name__}")
            print(f"DEBUG: Use gradient: {use_gradient}, prefix: {use_prefix_gradient}, action: {use_action_gradient}")
            print(f"DEBUG: Added to control_labels for text settings processing")
            
        except Exception as e:
            print(f"Error creating No Buttons notification: {e}")
            import traceback
            traceback.print_exc()

        # Force apply current text settings immediately
        QTimer.singleShot(50, self.apply_text_settings)

    def update_no_buttons_visibility(self):
        """Update the visibility of the No Buttons notification - STRICT logic"""
        if not hasattr(self, 'no_buttons_label') or not self.no_buttons_label:
            return
        
        # Get current view state
        current_view = getattr(self, 'current_view_state', 'normal')
        
        print(f"DEBUG: update_no_buttons_visibility called - view: {current_view}, has_any_buttons: {getattr(self, 'has_any_buttons', 'UNKNOWN')}")
        
        # RULE 1: NEVER show in specialized views (except Show All Controls)
        if current_view in ['all_buttons', 'specialized_1', 'specialized_2']:
            if self.no_buttons_visible:
                self.no_buttons_label.setVisible(False)
                self.no_buttons_visible = False
                print("DEBUG: Force hiding - specialized view")
            return
        
        # RULE 2: Only show in Show All Controls if we want to demonstrate it exists
        if current_view == 'all_controls':
            # Show it in Show All Controls only
            if not self.no_buttons_visible:
                self.no_buttons_label.setVisible(True)
                self.no_buttons_label.raise_()
                self.no_buttons_visible = True
                print("DEBUG: Showing in Show All Controls view")
            return
        
        # RULE 3: Normal view - ONLY for games with no buttons AND all directionals hidden
        if current_view == 'normal':
            # First check: Does this game actually have NO buttons?
            has_buttons = getattr(self, 'has_any_buttons', True)
            
            if has_buttons:
                # Game has buttons - NEVER show notification
                if self.no_buttons_visible:
                    self.no_buttons_label.setVisible(False)
                    self.no_buttons_visible = False
                    print("DEBUG: Game has buttons - hiding notification")
                return
            
            # Game has no buttons - check if all directionals are hidden
            all_directional_hidden = True
            directional_count = 0
            
            for control_name, control_data in self.control_labels.items():
                if control_name == "NO_BUTTONS_NOTIFICATION":
                    continue
                if 'label' not in control_data or not control_data['label']:
                    continue
                
                # Check if this is any type of directional control
                is_directional = (
                    any(control_type in control_name for control_type in 
                        ["JOYSTICK", "JOYSTICKLEFT", "JOYSTICKRIGHT", "DPAD"]) or
                    any(control_type in control_name for control_type in 
                        ["DIAL", "PADDLE", "TRACKBALL", "MOUSE", "LIGHTGUN", "AD_STICK", "PEDAL", "POSITIONAL"])
                )
                
                if is_directional:
                    directional_count += 1
                    if control_data['label'].isVisible():
                        all_directional_hidden = False
                        print(f"DEBUG: Found visible directional: {control_name}")
                        break
            
            print(f"DEBUG: Directional analysis - count: {directional_count}, all_hidden: {all_directional_hidden}")
            
            # Show notification ONLY if: no buttons + all directionals hidden + texts visible
            should_show = all_directional_hidden and self.texts_visible and directional_count > 0
            
            if should_show != self.no_buttons_visible:
                self.no_buttons_label.setVisible(should_show)
                self.no_buttons_visible = should_show
                if should_show:
                    self.no_buttons_label.raise_()
                print(f"DEBUG: Normal view final decision - {'SHOW' if should_show else 'HIDE'}")
        
        # RULE 4: Any other case - hide it
        else:
            if self.no_buttons_visible:
                self.no_buttons_label.setVisible(False)
                self.no_buttons_visible = False
                print("DEBUG: Unknown view state - hiding notification")

    def save_no_buttons_position(self):
        """Save the position of the No Buttons notification"""
        if not hasattr(self, 'no_buttons_label') or not self.no_buttons_label:
            return
        
        pos = self.no_buttons_label.pos()
        y_offset = self.text_settings.get("y_offset", -40)
        normalized_pos = [pos.x(), pos.y() - y_offset]
        
        # UPDATE the existing entry instead of creating new one
        if "NO_BUTTONS_NOTIFICATION" in self.control_labels:
            self.control_labels["NO_BUTTONS_NOTIFICATION"]['original_pos'] = QPoint(normalized_pos[0], normalized_pos[1])
        
        print(f"No Buttons notification position updated: {normalized_pos}")
    
    def init_directional_mode_on_startup(self):
        """Initialize directional mode from saved settings on startup (with guard)"""
        
        # Guard against multiple initialization
        if hasattr(self, '_directional_mode_initialized'):
            print("Directional mode already initialized, skipping...")
            return
        
        print("Initializing directional mode (first time)")
        
        # First load the directional mode settings
        self.load_directional_mode_settings()
        
        # Apply the loaded mode to all controls
        self.apply_directional_mode()
        
        # Update the button text to match the current mode
        self.update_directional_mode_button_text()
        
        # Set the guard flag
        self._directional_mode_initialized = True
        
        print(f"STARTUP: Initialized with directional mode '{self.directional_mode}'")

    def load_directional_mode_settings(self):
        """Load directional mode settings from bezel_settings.json (updated for 4 modes)"""
        try:
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                
                # Load the saved directional mode
                self.directional_mode = settings.get('directional_mode', 'show_all')
                self.joystick_visible = settings.get('joystick_visible', True)
                self.hide_specialized_with_directional = settings.get('hide_specialized_with_directional', False)
                
                print(f"LOAD: Loaded directional mode '{self.directional_mode}'")
                print(f"LOAD: joystick_visible={self.joystick_visible}, hide_specialized={self.hide_specialized_with_directional}")
                
                return True
            else:
                # Set defaults if no settings file
                self.directional_mode = 'show_all'
                self.joystick_visible = True
                self.hide_specialized_with_directional = False
                print("LOAD: No settings file found, using defaults")
                return False
                
        except Exception as e:
            print(f"Error loading directional mode settings: {e}")
            # Set defaults on error
            self.directional_mode = 'show_all'
            self.joystick_visible = True
            self.hide_specialized_with_directional = False
            return False

    def distribute_controls_vertically(self):
        """Distribute visible controls evenly in columns with improved boundary detection"""
        # Get all visible control labels
        visible_controls = []
        for control_name, control_data in self.control_labels.items():
            if 'label' in control_data and control_data['label'].isVisible():
                label = control_data['label']
                visible_controls.append((control_name, label))
        
        if len(visible_controls) < 2:
            self.show_toast_notification("Need at least 2 visible controls to distribute")
            return False
        
        print(f"\n=== DISTRIBUTE DEBUG (Enhanced) ===")
        print(f"Processing {len(visible_controls)} visible controls")
        
        # Group controls by column (similar X positions)
        columns = {}
        column_tolerance = 50  # Controls within 50px horizontally are considered same column
        
        for control_name, label in visible_controls:
            x_pos = label.x()
            
            # Find which column this control belongs to
            assigned_column = None
            for col_x in columns.keys():
                if abs(x_pos - col_x) <= column_tolerance:
                    assigned_column = col_x
                    break
            
            # If no existing column found, create new one
            if assigned_column is None:
                assigned_column = x_pos
                columns[assigned_column] = []
            
            columns[assigned_column].append((control_name, label))
        
        print(f"Found {len(columns)} columns with controls:")
        for col_x, controls in columns.items():
            print(f"  Column at X={col_x}: {len(controls)} controls")
        
        total_changes = 0
        columns_processed = 0
        
        # Process each column separately
        for col_x, column_controls in columns.items():
            # Need at least 2 controls in a column to distribute
            if len(column_controls) < 2:
                print(f"  Skipping column at X={col_x} - only {len(column_controls)} control(s)")
                continue
            
            print(f"\n--- Processing Column at X={col_x} ---")
            
            # Sort controls in this column by Y position
            column_controls.sort(key=lambda item: item[1].y())
            
            # Print BEFORE positions with label heights
            print("BEFORE Distribution:")
            for i, (control_name, label) in enumerate(column_controls):
                label_height = label.height()
                print(f"  {i}: {control_name} at Y={label.y()}, height={label_height}px")
            
            # Find the actual visual boundaries (topmost and bottommost controls)
            topmost_control = column_controls[0]  # First in sorted list
            bottommost_control = column_controls[-1]  # Last in sorted list
            
            topmost_name, topmost_label = topmost_control
            bottommost_name, bottommost_label = bottommost_control
            
            topmost_y = topmost_label.y()
            bottommost_y = bottommost_label.y()
            
            # Calculate available space between the boundaries
            total_height = bottommost_y - topmost_y
            
            print(f"Visual boundaries:")
            print(f"  Topmost: {topmost_name} at Y={topmost_y}")
            print(f"  Bottommost: {bottommost_name} at Y={bottommost_y}")
            print(f"  Available height: {total_height}px")
            
            # Calculate more reasonable minimum spacing
            avg_label_height = sum(label.height() for _, label in column_controls) / len(column_controls)
            min_spacing = avg_label_height + 5
            
            print(f"Average label height: {avg_label_height:.1f}px, Min spacing: {min_spacing:.1f}px")
            
            # Only skip if total height is extremely small
            required_minimum = min_spacing * (len(column_controls) - 1)
            if total_height < required_minimum * 0.5:  # Very relaxed requirement
                print(f"  Skipping column - insufficient space for distribution")
                print(f"  Need at least: {required_minimum * 0.5:.1f}px, Have: {total_height}px")
                continue
            
            # Calculate even spacing for this column
            steps = len(column_controls) - 1
            if steps > 0:
                step_size = total_height / steps
            else:
                step_size = 0
            
            print(f"Steps: {steps}, Step size: {step_size:.1f}px")
            
            column_changes = 0
            
            # Calculate target positions based on actual topmost/bottommost
            print("\nTarget positions:")
            for i, (control_name, label) in enumerate(column_controls):
                if i == 0:
                    # Keep topmost exactly where it is
                    target_y = topmost_y
                elif i == len(column_controls) - 1:
                    # Keep bottommost exactly where it is
                    target_y = bottommost_y
                else:
                    # Distribute evenly between top and bottom
                    target_y = int(topmost_y + (i * step_size))
                
                current_y = label.y()
                will_move = abs(current_y - target_y) > 2
                print(f"  {i}: {control_name} → Y={target_y} (current: {current_y}) {'MOVE' if will_move else 'STAY'}")
                
                # Apply the move
                if will_move:
                    label.move(label.x(), target_y)
                    column_changes += 1
                    print(f"  MOVED: {control_name} from Y={current_y} to Y={target_y}")
            
            # Print AFTER positions
            print("\nAFTER Distribution:")
            # Re-sort to show current positions
            column_controls.sort(key=lambda item: item[1].y())
            for i, (control_name, label) in enumerate(column_controls):
                spacing = ""
                if i > 0:
                    prev_y = column_controls[i-1][1].y()
                    gap = label.y() - prev_y
                    spacing = f" (gap: {gap}px)"
                print(f"  {i}: {control_name} at Y={label.y()}{spacing}")
            
            # Calculate actual spacing between adjacent controls
            print("\nActual gaps between controls:")
            for i in range(1, len(column_controls)):
                prev_label = column_controls[i-1][1]
                curr_label = column_controls[i][1]
                prev_y = prev_label.y()
                curr_y = curr_label.y()
                gap = curr_y - prev_y
                prev_height = prev_label.height()
                overlap_check = gap < prev_height
                status = " (OVERLAP!)" if overlap_check else " (OK)"
                print(f"  Gap {i-1}→{i}: {gap}px{status}")
            
            if column_changes > 0:
                print(f"\nDistributed {column_changes} controls in column at X={col_x}")
                total_changes += column_changes
                columns_processed += 1
        
        print(f"\n=== DISTRIBUTE COMPLETE ===\n")
        
        # Force a repaint to ensure changes are visible
        if hasattr(self, 'canvas'):
            self.canvas.update()
        
        # Show results
        if total_changes > 0:
            self.show_toast_notification(f"Distributed {total_changes} controls across {columns_processed} columns")
        else:
            self.show_toast_notification("Controls already evenly distributed")
        
        return total_changes > 0

    def show_toast_notification(self, message, duration=2000):
        """Show a brief notification that automatically disappears after specified duration (ms)"""
        from PyQt5.QtWidgets import QLabel
        from PyQt5.QtCore import Qt, QTimer
        
        # Create a floating label for the notification with improved visibility
        toast = QLabel(message, self)
        toast.setStyleSheet("""
            background-color: rgba(40, 40, 45, 220);
            color: white;
            font-size: 16px;
            font-weight: bold;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 60);
        """)
        toast.setAlignment(Qt.AlignCenter)
        toast.setWordWrap(True)
        toast.setFixedSize(300, 80)
        
        # Calculate position (center of the window)
        x = (self.width() - toast.width()) // 2
        y = (self.height() - toast.height()) // 2
        toast.move(x, y)
        
        # Make sure it's visible and on top
        toast.raise_()
        toast.show()
        
        # Schedule automatic hiding
        QTimer.singleShot(duration, toast.deleteLater)
        
        return toast
        
    def calculate_max_text_width(self, controls_dict, font, show_button_prefix=True, use_uppercase=False, extra_padding=40):
        """Calculate the maximum text width needed for all controls with improved padding for long text"""
        from PyQt5.QtGui import QFontMetrics
        
        font_metrics = QFontMetrics(font)
        max_width = 0
        
        # Check each control's text width
        for control_name, action_text in controls_dict.items():
            # Apply uppercase if needed
            if use_uppercase:
                action_text = action_text.upper()
            
            # Get button prefix
            button_prefix = self.get_button_prefix(control_name)
            
            # Add prefix if enabled
            display_text = action_text
            if show_button_prefix and button_prefix:
                display_text = f"{button_prefix}: {action_text}"
            
            # ADD THIS LINE to truncate long text
            display_text = self.truncate_display_text(display_text)
            
            # Calculate width with more precision using horizontalAdvance
            text_width = font_metrics.horizontalAdvance(display_text)
            
            # Keep track of max width
            max_width = max(max_width, text_width)
            
            # Special handling for known problematic controls and longer texts
            if (control_name == "P1_SELECT" or 
                "Select" in action_text or 
                len(display_text) > 15 or
                len(action_text) > 12):  # Added check for longer action text
                # Log the width for debugging
                print(f"Width for '{display_text}': {text_width}px")
                # Add extra padding for these special cases
                text_width += 20  # Additional padding for problematic controls
        
        # Add variable extra padding based on text length
        if max_width > 200:
            extra_padding = 60  # Use more padding for very long text
        elif max_width > 150:
            extra_padding = 50  # More padding for longer text
        
        result_width = max_width + extra_padding
        
        print(f"Max text width calculated: {max_width}px + {extra_padding}px padding = {result_width}px")
        return result_width

    def recreate_control_labels_with_case(self):
        """Recreate control labels to properly handle case changes and gradient settings"""
        print("Recreating control labels to apply case and gradient changes...")
        
        # Store current positions and visibility
        label_info = {}
        for control_name, control_data in self.control_labels.items():
            if 'label' in control_data and control_data['label']:
                label = control_data['label']
                label_info[control_name] = {
                    'position': label.pos(),
                    'visible': label.isVisible(),
                    'action': control_data['action'],
                    'prefix': control_data.get('prefix', '')
                }
        
        # Clear all current controls
        for control_name in list(self.control_labels.keys()):
            if control_name in self.control_labels:
                if 'label' in self.control_labels[control_name]:
                    self.control_labels[control_name]['label'].deleteLater()
                del self.control_labels[control_name]
        
        # Recreate controls with proper case and gradient settings
        self.create_control_labels()
        
        # Restore positions and visibility
        for control_name, info in label_info.items():
            if control_name in self.control_labels and 'label' in self.control_labels[control_name]:
                control_data = self.control_labels[control_name]
                
                # Restore position and visibility
                control_data['label'].move(info['position'])
                control_data['label'].setVisible(info['visible'])
                
                # Make sure action and prefix are preserved
                control_data['action'] = info['action']
                control_data['prefix'] = info['prefix']
        
        # Force apply font and update WITH uppercase_changed=True
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, lambda: self.apply_text_settings(uppercase_changed=True))
        QTimer.singleShot(200, self.force_resize_all_labels)
        
        print("Control labels recreated with case and gradient changes applied")
    
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
            # Add specialized controls button
            if hasattr(self, 'add_specialized_controls_button'):
                self.add_specialized_controls_button()
                
            # Other initialization code...
            # Load any saved settings
            if hasattr(self, 'load_grid_settings'):
                self.load_grid_settings()
            if hasattr(self, 'load_snapping_settings'):
                self.load_snapping_settings()
            
        except Exception as e:
            print(f"Error in enhance_preview_window_init: {e}")
    
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
        
        # Show toast notification
        status = "enabled" if self.snapping_enabled else "disabled"
        self.show_toast_notification(f"Snapping {status}")
        
        print(f"Snapping {'enabled' if self.snapping_enabled else 'disabled'}")

    def save_snapping_settings(self):
        """Save snapping settings to file in settings directory"""
        try:
            import os
            import json
            
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
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
            
            # Save to settings file in settings directory (not preview dir)
            settings_file = os.path.join(self.settings_dir, "snapping_settings.json")
            with open(settings_file, 'w') as f:
                json.dump(settings, f)
            
            print(f"Saved snapping settings to {settings_file}: {settings}")
            return True
        except Exception as e:
            print(f"Error saving snapping settings: {e}")
            import traceback
            traceback.print_exc()
            return False

    # 2. Fix load_snapping_settings method to check settings_dir first, with migration from preview_dir
    def load_snapping_settings(self):
        """Load snapping settings from file with migration support"""
        try:
            import os
            import json
            
            # Path to settings file in settings directory
            settings_file = os.path.join(self.settings_dir, "snapping_settings.json")
            
            # Check if file exists in settings directory
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
            else:
                # Check for legacy file in preview directory
                legacy_file = os.path.join(self.preview_dir, "snapping_settings.json")
                if os.path.exists(legacy_file):
                    # Load from legacy location
                    with open(legacy_file, 'r') as f:
                        settings = json.load(f)
                    
                    # Apply settings
                    self.snapping_enabled = settings.get("snapping_enabled", True)
                    self.snap_distance = settings.get("snap_distance", 15)
                    self.snap_to_grid = settings.get("snap_to_grid", True)
                    self.snap_to_screen_center = settings.get("snap_to_screen_center", True)
                    self.snap_to_controls = settings.get("snap_to_controls", True)
                    self.snap_to_logo = settings.get("snap_to_logo", True)
                    
                    # Migrate settings to new location
                    self.save_snapping_settings()
                    
                    print(f"Migrated snapping settings from {legacy_file} to {settings_file}")
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

                self.apply_button = QPushButton("Apply")
                self.apply_button.clicked.connect(self.apply_settings)

                # Change "OK" to "Done"
                self.ok_button = QPushButton("Done")  # Changed from "OK" to "Done"
                self.ok_button.clicked.connect(self.accept_settings)

                self.cancel_button = QPushButton("Cancel")
                self.cancel_button.clicked.connect(self.reject)

                button_layout.addWidget(self.apply_button)
                button_layout.addStretch()
                button_layout.addWidget(self.ok_button)
                button_layout.addWidget(self.cancel_button)
                
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
    
    # 3. Fix toggle_button_prefixes method to save to settings directory
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
                
                # IMPORTANT: Make sure the label keeps its complete styling information
                if hasattr(label, 'parse_text'):
                    try:
                        label.parse_text(label.text())
                    except Exception as e:
                        print(f"Error parsing text for {control_name}: {e}")
                        
                # Force the correct colors/gradients to be reapplied
                if hasattr(label, 'update'):
                    label.update()
        
        # Update button text
        if hasattr(self, 'prefix_button'):
            self.prefix_button.setText("Hide Prefixes" if show_prefixes else "Show Prefixes")
        
        # Save the updated setting to file in settings directory
        try:
            import os
            import json
            
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Try to load existing settings first
            settings_file = os.path.join(self.settings_dir, "text_appearance_settings.json")
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
            
            print(f"Saved button prefix setting to {settings_file}: {show_prefixes}")
        except Exception as e:
            print(f"Error saving button prefix setting: {e}")
            import traceback
            traceback.print_exc()
        
        # Force a complete refresh of all label styling
        QTimer.singleShot(100, self.apply_text_settings)
        QTimer.singleShot(200, self.force_resize_all_labels)
        
        # Force a canvas update
        self.canvas.update()
        
        return show_prefixes
    
    # 1. FONT LOADING (happening multiple times)
    # Fix: Add a font loading guard
    def load_and_register_fonts(self):
        """Load and register fonts from settings at startup with improved error detection"""
        from PyQt5.QtGui import QFontDatabase, QFont, QFontInfo
        
        if hasattr(self, '_fonts_loaded') and self._fonts_loaded:
            print("Fonts already loaded, skipping...")
            return self.current_font
    
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
        
        # Set the guard flag
        self._fonts_loaded = True
        print("=== FONT LOADING COMPLETE ===\n")
        return self.current_font

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

    # 10. Remove the shadow toggle button from UI
    def create_floating_button_frame(self):
        """Create clean, simple floating button frame without shadow toggle"""
        from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from PyQt5.QtCore import Qt, QPoint, QTimer
        
        # The rest of your current create_floating_button_frame implementation...
        
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
        self.close_button.setToolTip("Close the preview window (ESC key)")
        self.top_row.addWidget(self.close_button)
        
        self.global_save_button = QPushButton("Global Save")
        self.global_save_button.clicked.connect(lambda: self.save_positions(is_global=True))
        self.global_save_button.setStyleSheet(button_style)
        self.global_save_button.setToolTip("Save current layout for all games\nUse this for standard layouts")
        self.top_row.addWidget(self.global_save_button)
        
        self.rom_save_button = QPushButton("ROM Save")
        self.rom_save_button.clicked.connect(lambda: self.save_positions(is_global=False))
        self.rom_save_button.setStyleSheet(button_style)
        self.rom_save_button.setToolTip(f"Save layout specifically for {self.rom_name}\nOverrides global layout for this game only")
        self.top_row.addWidget(self.rom_save_button)

        # Mapping Save button (only if ROM has mapping)
        if self.has_mapping():
            mapping = self.get_current_mapping()
            self.mapping_save_button = QPushButton(f"Save {mapping}")
            self.mapping_save_button.clicked.connect(self.save_mapping_positions)
            self.mapping_save_button.setStyleSheet(button_style)
            self.mapping_save_button.setToolTip(f"Save layout for all games with mapping: {mapping}")
            self.top_row.addWidget(self.mapping_save_button)
        
        # In your create_floating_button_frame method, add another button:
        self.reset_rom_button = QPushButton("Reset ROM")
        self.reset_rom_button.clicked.connect(self.delete_rom_specific_settings)
        self.reset_rom_button.setStyleSheet(button_style)
        self.reset_rom_button.setToolTip("Delete ROM-specific settings and revert to global")
        self.top_row.addWidget(self.reset_rom_button)
        
        self.text_settings_button = QPushButton("Text Settings")
        self.text_settings_button.clicked.connect(self.show_text_settings)
        self.text_settings_button.setStyleSheet(button_style)
        self.text_settings_button.setToolTip("Configure text appearance\nFont, size, color, gradients, and more")
        self.top_row.addWidget(self.text_settings_button)
        
        '''self.xinput_controls_button = QPushButton("Show All XInput")
        self.xinput_controls_button.clicked.connect(self.toggle_xinput_controls)
        self.xinput_controls_button.setStyleSheet(button_style)
        self.top_row.addWidget(self.xinput_controls_button)'''

        # Create specialized controls button with clearer labeling
        self.controls_mode_button = QPushButton("Show All Controls")
        self.controls_mode_button.clicked.connect(self.toggle_controls_view)
        self.controls_mode_button.setStyleSheet(button_style)
        self.controls_mode_button.setToolTip("Toggle between control views:\nNormal → All Buttons → Directionals → Normal")
        self.top_row.addWidget(self.controls_mode_button)

        # Second row buttons
        '''self.toggle_texts_button = QPushButton("Hide Texts")
        self.toggle_texts_button.clicked.connect(self.toggle_texts)
        self.toggle_texts_button.setStyleSheet(button_style)
        self.toggle_texts_button.setToolTip("Show/hide control text labels\nHides all text except directional controls")
        self.bottom_row.addWidget(self.toggle_texts_button)'''

        # Create the joystick button with better initial text
        self.directional_mode_button = QPushButton("Hide Directional")
        self.directional_mode_button.clicked.connect(self.cycle_directional_mode)
        self.directional_mode_button.setStyleSheet(button_style)
        self.directional_mode_button.setToolTip("Cycle through directional control visibility modes")
        self.bottom_row.addWidget(self.directional_mode_button)
        
        # Initialize directional mode and update button text
        # Initialize directional mode from saved settings

        self.update_directional_mode_button_text()
        
        # Add a settings button if it doesn't exist
        if not hasattr(self, 'settings_button'):
            self.settings_button = QPushButton("Settings")
            self.settings_button.clicked.connect(self.show_settings_dialog)
            self.settings_button.setStyleSheet(button_style)
            self.bottom_row.addWidget(self.settings_button)
            self.settings_button.setVisible(False)  # ADD THIS LINE TO HIDE IT

        # Add button prefix toggle button
        prefix_text = "Hide Prefixes" if self.text_settings.get("show_button_prefix", True) else "Show Prefixes"
        self.prefix_button = QPushButton(prefix_text)
        self.prefix_button.clicked.connect(self.toggle_button_prefixes)
        self.prefix_button.setStyleSheet(button_style)
        self.prefix_button.setToolTip("Toggle button prefixes\nE.g., 'A: Jump' vs 'Jump'")
        self.bottom_row.addWidget(self.prefix_button)
        
        # Logo toggle
        logo_text = "Hide Logo" if self.logo_visible else "Show Logo"
        self.logo_button = QPushButton(logo_text)
        self.logo_button.clicked.connect(self.toggle_logo)
        self.logo_button.setStyleSheet(button_style)
        self.logo_button.setToolTip(
            f"Show/hide the game logo\n"
            f"Files in preview\\logos\\{self.rom_name}.png override standard locations\n"
            f"Priority: preview\\logos > collections\\medium_artwork\\logo\\{self.rom_name}.png"
        )
        self.top_row.addWidget(self.logo_button)
        
        self.center_logo_button = QPushButton("Center Logo")
        self.center_logo_button.clicked.connect(self.center_logo)
        self.center_logo_button.setStyleSheet(button_style)
        self.center_logo_button.setToolTip("Center logo horizontally\nMaintains vertical position")
        self.bottom_row.addWidget(self.center_logo_button)
        
        # Add Distribute Vertically button with enhanced tooltip
        self.distribute_button = QPushButton("Distribute Vertically")
        self.distribute_button.clicked.connect(self.distribute_controls_vertically)
        self.distribute_button.setStyleSheet(button_style)
        self.distribute_button.setToolTip(
            "Evenly distribute visible controls vertically\n"
            "Keeps topmost and bottommost controls in place\n"
            "and repositions controls in between with equal spacing"
        )
        self.bottom_row.addWidget(self.distribute_button)
        
        # Screen toggle with number indicator
        self.screen_button = QPushButton(f"Screen {getattr(self, 'current_screen', 1)}")
        self.screen_button.clicked.connect(self.toggle_screen)
        self.screen_button.setStyleSheet(button_style)
        self.screen_button.setToolTip("Toggle between screens\nMoves preview to next monitor")
        self.bottom_row.addWidget(self.screen_button)
        
        # Add save image button
        self.save_image_button = QPushButton("Save Image")
        self.save_image_button.clicked.connect(self.save_image)
        self.save_image_button.setStyleSheet(button_style)
        self.save_image_button.setToolTip("Save current view as PNG image\nStored in preview/screenshots folder")
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
        self.snap_button.setToolTip("Toggle snapping when dragging controls\nHold Shift to temporarily disable snapping")
        self.bottom_row.addWidget(self.snap_button)

        # Add Grid Toggle Button
        self.grid_button = QPushButton("Show Grid")
        self.grid_button.clicked.connect(self.toggle_alignment_grid)
        self.grid_button.setStyleSheet(button_style)
        self.grid_button.setToolTip("Show/hide alignment grid\nUse for precise positioning")
        self.bottom_row.addWidget(self.grid_button)

        # Determine button frame position
        self.position_button_frame()
        
        # Update logo button text after a short delay to ensure settings are loaded
        QTimer.singleShot(100, self.update_center_logo_button_text)
        self.init_directional_mode_on_startup()
        # Show button frame
        self.button_frame.show()

        # After creating the button frame and all standard buttons, call the enhance method
        self.enhance_preview_window_init()

    def show_settings_dialog(self):
        """Show a dialog for various settings"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QPushButton, QLabel, QGroupBox, QHBoxLayout
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Preview Settings")
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # Directional controls settings group
        directional_group = QGroupBox("Directional Controls")
        directional_layout = QVBoxLayout(directional_group)
        
        # Get the current setting (default to True if not set)
        auto_show_directionals = getattr(self, 'auto_show_directionals_for_directional_only', True)
        print(f"Current auto-show setting: {auto_show_directionals}")
        
        # Create the checkbox with EXPLICIT initial state
        checkbox = QCheckBox("Auto-show directional controls for directional-only games")
        checkbox.setChecked(auto_show_directionals)  # Set the initial state
        checkbox.setToolTip("When enabled, games with only directional controls will always show those controls")
        directional_layout.addWidget(checkbox)
        
        # Add explanation text
        explanation = QLabel("This setting keeps directional controls visible for games that only have directional inputs, even when 'Hide Directional' is active.")
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color: #666; font-style: italic;")
        directional_layout.addWidget(explanation)
        
        # Add to main layout
        layout.addWidget(directional_group)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(ok_button)
        buttons_layout.addWidget(cancel_button)
        
        layout.addLayout(buttons_layout)
        
        # Define the save function inside this method for better closure
        def save_settings():
            # Get the checkbox state directly
            new_value = checkbox.isChecked()
            print(f"New auto-show setting from checkbox: {new_value}")
            
            # Explicitly update the instance variable
            self.auto_show_directionals_for_directional_only = new_value
            
            # Save to bezel settings file
            try:
                # Load existing settings first
                settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
                settings = {}
                
                if os.path.exists(settings_file):
                    with open(settings_file, 'r') as f:
                        settings = json.load(f)
                
                # Update with the new setting
                settings['auto_show_directionals_for_directional_only'] = new_value
                
                # Write back to file
                with open(settings_file, 'w') as f:
                    json.dump(settings, f)
                
                print(f"Saved auto_show_directionals setting: {new_value}")
                
                # Immediately reapply visibility to see the change
                self.apply_joystick_visibility()
                
            except Exception as e:
                print(f"Error saving settings: {e}")
                import traceback
                traceback.print_exc()
            
            # Close the dialog
            dialog.accept()
        
        # Connect buttons
        ok_button.clicked.connect(save_settings)
        cancel_button.clicked.connect(dialog.reject)
        
        # Show the dialog
        dialog.exec_()
    
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
    
    # 3. FORCE RESIZE ALL LABELS (happening 5+ times)
    # Fix: Add debouncing
    def force_resize_all_labels(self):
        """Force resize with debouncing"""
        if hasattr(self, '_resize_timer'):
            self._resize_timer.stop()
        
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._do_force_resize_all_labels)
        self._resize_timer.start(100)  # 100ms debounce
    
    def _do_force_resize_all_labels(self):
        """Force all control labels to resize according to their content with extra padding for different fonts"""
        if not hasattr(self, 'control_labels'):
            return
                    
        print("Force resizing all control labels (debounced)")
        for control_name, control_data in self.control_labels.items():
            if 'label' in control_data and control_data['label']:
                label = control_data['label']
                
                # Get the displayed text
                display_text = label.text()
                action_text = control_data['action']
                        
                # Make sure we don't have size restrictions
                label.setMinimumSize(0, 0)
                label.setMaximumSize(16777215, 16777215)
                        
                # Reset size policy
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                        
                # First get the natural size through adjustSize
                label.adjustSize()
                
                # Now calculate a better width based on text metrics
                font_metrics = QFontMetrics(label.font())
                text_width = font_metrics.horizontalAdvance(display_text)
                
                # Get font family to check if it's a custom font
                font_family = label.font().family()
                is_custom_font = font_family not in ["Arial", "Verdana", "Tahoma", "Times New Roman", 
                                                "Courier New", "Segoe UI", "Calibri", "Georgia", 
                                                "Impact", "System"]
                
                # Use a moderate padding - less extreme than before since we're not centering
                padding = 20  # Basic padding 
                
                if is_custom_font:
                    # Add extra padding for custom fonts
                    padding += 10
                
                # Add extra padding for problematic controls and longer texts
                if "SELECT" in control_name or "Select" in action_text or len(display_text) > 15:
                    padding += 15
                
                # For very long text, add a bit more
                if len(display_text) > 20:
                    padding += 15
                
                # Calculate final width and ensure it's not too narrow
                final_width = text_width + padding
                
                # Ensure label is wide enough for the text plus padding
                label.resize(final_width, label.height())
                
                if "SELECT" in control_name or len(display_text) > 15:
                    print(f"Resized {control_name}: text_width={text_width}, final_width={final_width}, text='{display_text}'")
        
        # Force a repaint
        if hasattr(self, 'canvas'):
            self.canvas.update()
                    
        print("All labels resized with improved width calculation")

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
                # First lower background to bottom
                self.bg_label.lower()
                
                # Then raise bezel above background
                self.bezel_label.stackUnder(self.bg_label)
                self.bezel_label.raise_()
                
                print("Fixed layering: Background -> Bezel -> Other elements")
            
            # Make sure the bezel is visible
            self.bezel_label.show()
            self.bezel_visible = True
            
            # CRITICAL FIX: Ensure logo stays interactive by raising it above bezel
            if hasattr(self, 'logo_label') and self.logo_label and self.logo_label.isVisible():
                self.logo_label.raise_()
                print("Logo raised above bezel to maintain interactivity")
            
            # Now raise all controls above bezel (but logo should be on top)
            self.raise_controls_above_bezel()
            
            print(f"Bezel displayed: {bezel_pixmap.width()}x{bezel_pixmap.height()} at ({x},{y})")
            print(f"Bezel visibility is set to: {self.bezel_visible}")
            
        except Exception as e:
            print(f"Error showing bezel: {e}")
            import traceback
            traceback.print_exc()
            self.bezel_visible = False

    # 2. LAYER ORDER ENFORCEMENT (happening 6+ times)
    # Fix: Add debouncing and reduce redundant calls
    def enforce_layer_order(self):
        """Enforce layer order with debouncing"""
        # Debounce rapid calls
        if hasattr(self, '_enforce_timer'):
            self._enforce_timer.stop()
        
        self._enforce_timer = QTimer()
        self._enforce_timer.setSingleShot(True)
        self._enforce_timer.timeout.connect(self._do_enforce_layer_order)
        self._enforce_timer.start(50)  # 50ms debounce
    
    def _do_enforce_layer_order(self):
        """
        Enforce the correct stacking order for all elements with logo on top:
        1. Background (bottom)
        2. Bezel (above background)
        3. Controls (above bezel)
        4. Logo (top - must be interactive)
        """
        print("\n--- Enforcing layer order (debounced) ---")
        
        # Step 1: Send background to the absolute bottom
        if hasattr(self, 'bg_label') and self.bg_label:
            self.bg_label.lower()
            print("Background placed at bottom layer")
        
        # Step 2: Place bezel above background
        if hasattr(self, 'bezel_label') and self.bezel_label and self.bezel_label.isVisible():
            # First lower it to bottom, then raise it above background
            self.bezel_label.lower()
            if hasattr(self, 'bg_label') and self.bg_label:
                self.bezel_label.stackUnder(self.bg_label)
                self.bezel_label.raise_()
            print("Bezel placed above background")
        
        # Step 3: Raise all control labels above bezel
        if hasattr(self, 'control_labels'):
            controls_raised = 0
            for control_name, control_data in self.control_labels.items():
                if 'label' in control_data and control_data['label'] and control_data['label'].isVisible():
                    control_data['label'].raise_()
                    controls_raised += 1
            print(f"Raised {controls_raised} visible controls above bezel")
        
        # Step 4: CRITICAL - Logo must be on absolute top to remain interactive
        if hasattr(self, 'logo_label') and self.logo_label and self.logo_label.isVisible():
            self.logo_label.raise_()
            # Double-raise to ensure it's really on top
            self.logo_label.raise_()
            print("Logo placed on absolute top layer (interactive)")
        
        # Step 4: Place No Buttons notification above regular controls
        if hasattr(self, 'no_buttons_label') and self.no_buttons_label and self.no_buttons_label.isVisible():
            self.no_buttons_label.raise_()
            print("No Buttons notification placed above controls")
        
        # Step 5: Force immediate repaint to apply changes
        if hasattr(self, 'canvas'):
            self.canvas.update()
            self.canvas.repaint()
        
        print("Layer order enforcement complete: Background -> Bezel -> Controls -> Logo (top)")

    def toggle_bezel_improved(self):
        """Toggle bezel visibility and save ONLY bezel setting"""
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
        
        # CRITICAL: Enforce correct layer order with logo on top
        self.enforce_layer_order()
        
        # FIXED: Save ONLY bezel visibility, don't touch directional settings
        self.save_bezel_visibility_only()
        self.show_toast_notification("Bezel visibility saved")
        print(f"Saved bezel visibility ({self.bezel_visible}) to GLOBAL settings")

    # NEW METHOD: Save only bezel visibility without affecting directional settings
    def save_bezel_visibility_only(self):
        """Save ONLY bezel visibility without affecting other settings"""
        try:
            # Load existing settings first to preserve them
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            existing_settings = {}
            
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    existing_settings = json.load(f)
            
            # Update ONLY the bezel visibility
            existing_settings["bezel_visible"] = self.bezel_visible
            
            # Write back to file, preserving all other settings
            os.makedirs(self.settings_dir, exist_ok=True)
            with open(settings_file, 'w') as f:
                json.dump(existing_settings, f)
            
            print(f"Saved ONLY bezel visibility: {self.bezel_visible}")
            return True
            
        except Exception as e:
            print(f"Error saving bezel visibility: {e}")
            return False
    
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
            self.bezel_button.setToolTip(
                f"Show/hide bezel overlay\n"
                f"Files in preview\\bezels\\{self.rom_name}.png override standard locations\n"
                f"Priority: preview\\bezels > mame\\artwork\\{self.rom_name}"
            )
            
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

    def convert_mapping(self, mapping, to_xinput=True):
        """Convert JOYCODE mappings to XINPUT format for button prefix extraction."""
        if not mapping:
            return mapping
                    
        # Handle multiple mappings with ||| separator
        if " ||| " in mapping:
            parts = [part.strip() for part in mapping.split(" ||| ")]
            converted_parts = []
            
            for part in parts:
                # Convert each part
                if part in self.joycode_to_xinput_map:
                    converted_parts.append(self.joycode_to_xinput_map[part])
                else:
                    converted_parts.append(part)
            
            return " ||| ".join(converted_parts)
        
        # For regular mappings, do direct lookup
        if mapping in self.joycode_to_xinput_map:
            return self.joycode_to_xinput_map[mapping]
        
        # If no conversion available, return original
        return mapping

    def initialize_conversion_maps(self):
        """Initialize mapping conversion dictionaries."""
        print("Initializing conversion maps...")
        # JOYCODE to XINPUT conversion map
        self.joycode_to_xinput_map = {
            # Button mappings
            "JOYCODE_1_BUTTON1": "XINPUT_1_A",
            "JOYCODE_1_BUTTON2": "XINPUT_1_B",
            "JOYCODE_1_BUTTON3": "XINPUT_1_X",
            "JOYCODE_1_BUTTON4": "XINPUT_1_Y",
            "JOYCODE_1_BUTTON5": "XINPUT_1_SHOULDER_L",
            "JOYCODE_1_BUTTON6": "XINPUT_1_SHOULDER_R",
            "JOYCODE_1_BUTTON7": "XINPUT_1_START",
            "JOYCODE_1_BUTTON8": "XINPUT_1_SELECT",
            "JOYCODE_1_BUTTON9": "XINPUT_1_THUMB_L",
            "JOYCODE_1_BUTTON10": "XINPUT_1_THUMB_R",
            
            # D-pad mappings
            "JOYCODE_1_DPADUP": "XINPUT_1_DPAD_UP",
            "JOYCODE_1_DPADDOWN": "XINPUT_1_DPAD_DOWN",
            "JOYCODE_1_DPADLEFT": "XINPUT_1_DPAD_LEFT",
            "JOYCODE_1_DPADRIGHT": "XINPUT_1_DPAD_RIGHT",
            
            # Full axis mappings - CRITICAL for our issue
            "JOYCODE_1_ZAXIS": "XINPUT_1_TRIGGER_L",        # Left Trigger
            "JOYCODE_1_RZAXIS": "XINPUT_1_TRIGGER_R",       # Right Trigger
            
            # Axis switch mappings
            "JOYCODE_1_ZAXIS_NEG_SWITCH": "XINPUT_1_TRIGGER_L",  # Left Trigger pulled
            "JOYCODE_1_RZAXIS_NEG_SWITCH": "XINPUT_1_TRIGGER_R", # Right Trigger pulled
            
            # Analog stick mappings
            "JOYCODE_1_XAXIS_LEFT_SWITCH": "XINPUT_1_LSTICK_LEFT",
            "JOYCODE_1_XAXIS_RIGHT_SWITCH": "XINPUT_1_LSTICK_RIGHT",
            "JOYCODE_1_YAXIS_UP_SWITCH": "XINPUT_1_LSTICK_UP",
            "JOYCODE_1_YAXIS_DOWN_SWITCH": "XINPUT_1_LSTICK_DOWN",
            "JOYCODE_1_RXAXIS_LEFT_SWITCH": "XINPUT_1_RSTICK_LEFT",
            "JOYCODE_1_RXAXIS_RIGHT_SWITCH": "XINPUT_1_RSTICK_RIGHT",
            "JOYCODE_1_RYAXIS_UP_SWITCH": "XINPUT_1_RSTICK_UP",
            "JOYCODE_1_RYAXIS_DOWN_SWITCH": "XINPUT_1_RSTICK_DOWN"
        }
        
        print(f"JOYCODE_1_ZAXIS mapped to: {self.joycode_to_xinput_map.get('JOYCODE_1_ZAXIS', 'NOT FOUND')}")
    
    # 5. Updated format_control_name method to produce more readable control names
    def format_control_name(self, control_name):
        """Format control names for better display with specialized control handling"""
        # Check for specialized control formats first
        specialized_formats = {
            'P1_DIAL': 'Rotary Dial',
            'P1_DIAL_V': 'Vertical Dial',
            'P1_PADDLE': 'Paddle Control',
            'P1_TRACKBALL_X': 'Trackball X',
            'P1_TRACKBALL_Y': 'Trackball Y',
            'P1_MOUSE_X': 'Mouse X',
            'P1_MOUSE_Y': 'Mouse Y',
            'P1_LIGHTGUN_X': 'Light Gun X',
            'P1_LIGHTGUN_Y': 'Light Gun Y',
            'P1_AD_STICK_X': 'Analog X',
            'P1_AD_STICK_Y': 'Analog Y',
            'P1_AD_STICK_Z': 'Analog Z',
            'P1_PEDAL': 'Pedal 1',
            'P1_PEDAL2': 'Pedal 2',
            'P1_POSITIONAL': 'Positional',
            'P1_GAMBLE_HIGH': 'Gamble High',
            'P1_GAMBLE_LOW': 'Gamble Low',
        }
        
        if control_name in specialized_formats:
            return specialized_formats[control_name]
        
        # Handle standard button names
        if 'BUTTON' in control_name:
            # Extract player number and button number
            parts = control_name.split('_')
            if len(parts) >= 3:
                player = parts[0].replace('P', 'Player ')
                button = 'Button ' + parts[2].replace('BUTTON', '')
                return f"{player} {button}"
        
        # Joystick directions
        if '_JOYSTICK_' in control_name:
            direction = control_name.split('_')[-1]
            return f"Left Stick {direction.title()}"
        
        if '_JOYSTICKRIGHT_' in control_name:
            direction = control_name.split('_')[-1]
            return f"Right Stick {direction.title()}"
        
        # D-pad directions
        if '_DPAD_' in control_name:
            direction = control_name.split('_')[-1]
            return f"D-Pad {direction.title()}"
        
        # Common system buttons
        if '_START' in control_name:
            player = control_name.split('_')[0].replace('P', 'Player ')
            return f"{player} Start"
        
        if '_SELECT' in control_name:
            player = control_name.split('_')[0].replace('P', 'Player ')
            return f"{player} Select"
        
        # If no special formatting applies, make it more readable
        # Remove P1_ prefix, replace underscores with spaces, and title case
        readable = control_name.replace('P1_', '').replace('_', ' ').title()
        return readable
    
    # Add these new methods to your PreviewWindow class

    def show_specialized_controls_group_1(self):
        """Show Group 1: Movement/Tracking Controls (9 controls)"""
        
        # Group 1: Movement and Tracking Controls
        specialized_controls_group_1 = {
            "P1_DIAL": "Rotary",
            "P1_DIAL_V": "Vertical", 
            "P1_PADDLE": "Paddle",
            "P1_TRACKBALL_X": "Trackball X",
            "P1_TRACKBALL_Y": "Trackball Y",
            "P1_MOUSE_X": "Mouse X",
            "P1_MOUSE_Y": "Mouse Y",
            "P1_AD_STICK_X": "Analog X",
            "P1_AD_STICK_Y": "Analog Y",
            "P1_AD_STICK_Z": "Analog Z",
        }
        
        return self._show_specialized_group(specialized_controls_group_1, "Group 1 (Movement/Tracking)")

    def show_specialized_controls_group_2(self):
        """Show Group 2: Action/Input Controls (7 controls)"""
        
        # Group 2: Action and Input Controls  
        specialized_controls_group_2 = {
            "P1_LIGHTGUN_X": "Light Gun X",
            "P1_LIGHTGUN_Y": "Light Gun Y", 
            "P1_PEDAL": "Pedal1",
            "P1_PEDAL2": "Pedal2",
            "P1_POSITIONAL": "Positional",
            "P1_GAMBLE_HIGH": "Gamble High",
            "P1_GAMBLE_LOW": "Gamble Low",
        }
        
        return self._show_specialized_group(specialized_controls_group_2, "Group 2 (Action/Input)")

    # Fix 3: Update _show_specialized_group to not delete No Buttons notification
    def _show_specialized_group(self, controls_dict, group_name, hide_no_buttons=True):
        """Common method to show a group of specialized controls"""
        try:
            print(f"\n--- Showing {group_name} ---")
            
            # Save existing control positions as backup
            if not hasattr(self, 'original_controls_backup'):
                self.original_controls_backup = {}
                for control_name, control_data in self.control_labels.items():
                    self.original_controls_backup[control_name] = {
                        'action': control_data['action'],
                        'position': control_data['label'].pos(),
                        'original_pos': control_data.get('original_pos', QPoint(0, 0))
                    }
            
            # PRESERVE No Buttons notification during specialized views
            no_buttons_data = None
            if "NO_BUTTONS_NOTIFICATION" in self.control_labels:
                no_buttons_data = self.control_labels["NO_BUTTONS_NOTIFICATION"].copy()
                if hide_no_buttons:
                    # Hide it but don't delete it
                    no_buttons_data['label'].setVisible(False)
                    self.no_buttons_visible = False
                    print("DEBUG: Hiding No Buttons notification in specialized view")

            # Clear other controls but preserve No Buttons notification
            for control_name in list(self.control_labels.keys()):
                if control_name == "NO_BUTTONS_NOTIFICATION":
                    continue  # Don't delete the No Buttons notification
                    
                # Remove other controls from the canvas
                if control_name in self.control_labels:
                    if 'label' in self.control_labels[control_name]:
                        self.control_labels[control_name]['label'].deleteLater()
                    del self.control_labels[control_name]

            # Clear collections but restore No Buttons notification
            self.control_labels = {}
            if no_buttons_data:
                self.control_labels["NO_BUTTONS_NOTIFICATION"] = no_buttons_data
                self.no_buttons_label = no_buttons_data['label']
            
            print("Cleared all existing controls except No Buttons notification")
            
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
            
            # Use existing font if available
            if hasattr(self, 'current_font') and self.current_font:
                font = QFont(self.current_font)
            elif hasattr(self, 'initialized_font') and self.initialized_font:
                font = QFont(self.initialized_font)
            else:
                font = QFont(font_family, font_size)
                font.setBold(bold_strength)
                font.setStyleStrategy(QFont.PreferMatch)
            
            # Calculate maximum text width
            max_text_width = self.calculate_max_text_width(
                controls_dict,
                font,
                show_button_prefix=show_button_prefix,
                use_uppercase=use_uppercase,
                extra_padding=40
            )
            
            # Default grid layout - spread them out more with fewer controls
            grid_x, grid_y = 0, 0
            controls_per_row = 3  # 3 controls per row for better spacing
            
            # Create all controls in the group
            for control_name, action_text in controls_dict.items():
                # Apply uppercase if needed
                if use_uppercase:
                    action_text = action_text.upper()
                
                # Get button prefix
                button_prefix = self.get_button_prefix(control_name)
                
                # Add prefix if enabled
                display_text = action_text
                if show_button_prefix and button_prefix:
                    display_text = f"{button_prefix}: {action_text}"
                
                # Truncate long text
                display_text = self.truncate_display_text(display_text)
                
                # Choose the correct label class based on gradient settings
                if use_prefix_gradient or use_action_gradient:
                    label = GradientDraggableLabel(display_text, self.canvas, settings=self.text_settings.copy())
                    label.use_prefix_gradient = use_prefix_gradient
                    label.use_action_gradient = use_action_gradient
                    label.prefix_gradient_start = QColor(prefix_gradient_start)
                    label.prefix_gradient_end = QColor(prefix_gradient_end)
                    label.action_gradient_start = QColor(action_gradient_start)
                    label.action_gradient_end = QColor(action_gradient_end)
                else:
                    label = ColoredDraggableLabel(display_text, self.canvas, settings=self.text_settings.copy())
                
                # Apply font and styling
                label.setFont(font)
                label.setStyleSheet(f"background-color: transparent; border: none; font-family: '{font.family()}';")
                label.prefix = button_prefix
                label.action = action_text
                
                # Configure label sizing
                label.setMinimumSize(0, 0)
                label.setMaximumSize(16777215, 16777215)
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                label.settings = self.text_settings.copy()
                label.adjustSize()

                # Calculate proper width
                font_metrics = QFontMetrics(label.font())
                text_width = font_metrics.horizontalAdvance(display_text)
                font_family = label.font().family()
                is_custom_font = font_family not in ["Arial", "Verdana", "Tahoma", "Times New Roman", 
                                                "Courier New", "Segoe UI", "Calibri", "Georgia", 
                                                "Impact", "System"]
                base_padding = 50 if is_custom_font else 30
                if len(display_text) > 15:
                    base_padding += 20
                if "SELECT" in control_name or "Select" in action_text:
                    base_padding += 25
                    
                label_width = text_width + base_padding
                label_height = label.height()
                label.resize(label_width, label_height)
                
                # Determine position
                if saved_positions and control_name in saved_positions:
                    pos_x, pos_y = saved_positions[control_name]
                    x, y = pos_x, pos_y + y_offset
                    original_pos = QPoint(pos_x, pos_y)
                elif control_name in self.original_controls_backup:
                    backup_pos = self.original_controls_backup[control_name]['position']
                    x, y = backup_pos.x(), backup_pos.y()
                    original_pos = self.original_controls_backup[control_name]['original_pos']
                else:
                    # Better grid layout with more spacing for fewer controls
                    row = grid_y
                    col = grid_x
                    
                    x = 150 + (col * 400)  # More space between columns
                    y = 100 + (row * 80) + y_offset  # More space between rows
                    
                    original_pos = QPoint(x, y - y_offset)
                    
                    # Update grid position
                    grid_x = (grid_x + 1) % controls_per_row
                    if grid_x == 0:
                        grid_y += 1
                
                # Apply position
                label.move(x, y)
                
                # Store in control_labels
                self.control_labels[control_name] = {
                    'label': label,
                    'action': action_text,
                    'prefix': button_prefix,
                    'original_pos': original_pos
                }
                
                # All controls should be visible
                label.setVisible(True)
            
            # Force updates
            QTimer.singleShot(50, lambda: self.force_resize_all_labels())
            QTimer.singleShot(150, lambda: self.apply_text_settings())
            
            # Force a canvas update
            self.canvas.update()
            
            print(f"Created and displayed {len(controls_dict)} controls in {group_name}")
        
            # Only hide No Buttons notification if requested
            if hide_no_buttons and hasattr(self, 'no_buttons_label') and self.no_buttons_label:
                self.no_buttons_label.setVisible(False)
                self.no_buttons_visible = False
                print(f"DEBUG: Hiding No Buttons notification in {group_name}")
            
            return True
            
        except Exception as e:
            print(f"Error showing {group_name}: {e}")
            return False

    def toggle_controls_view(self):
        """Toggle between control views with proper No Buttons notification handling"""

        if not hasattr(self, 'current_view_state'):
            self.current_view_state = 'normal'

        if self.current_view_state == 'normal':
            self.current_view_state = 'all_controls'
            self.show_all_controls_combined()
            next_state_text = "XInput Controls"

        elif self.current_view_state == 'all_controls':
            self.current_view_state = 'all_buttons'
            self.show_all_xinput_controls()
            next_state_text = "Specialized Group 1"

        elif self.current_view_state == 'all_buttons':
            self.current_view_state = 'specialized_1'
            self.show_specialized_controls_group_1()
            next_state_text = "Specialized Group 2"

        elif self.current_view_state == 'specialized_1':
            self.current_view_state = 'specialized_2'
            self.show_specialized_controls_group_2()
            rom_name = getattr(self, 'rom_name', 'Normal')
            next_state_text = f"{rom_name} Controls"

        elif self.current_view_state == 'specialized_2':
            self.current_view_state = 'normal'

            # PRESERVE No Buttons notification during the transition
            no_buttons_data = None
            if "NO_BUTTONS_NOTIFICATION" in self.control_labels:
                no_buttons_data = self.control_labels["NO_BUTTONS_NOTIFICATION"].copy()
                # Don't delete the actual label widget yet
                no_buttons_label = no_buttons_data['label']

            # Clear existing controls EXCEPT No Buttons notification
            for control_name in list(self.control_labels.keys()):
                if control_name == "NO_BUTTONS_NOTIFICATION":
                    continue  # Skip deleting this one
                
                if 'label' in self.control_labels[control_name]:
                    self.control_labels[control_name]['label'].deleteLater()
                del self.control_labels[control_name]

            # Recreate default ROM-specific layout
            self.create_control_labels(clean_mode=False)

            # RESTORE No Buttons notification if it existed
            if no_buttons_data:
                self.control_labels["NO_BUTTONS_NOTIFICATION"] = no_buttons_data
                print("DEBUG: Preserved No Buttons notification during view transition")

            # Restore appearance and layout
            QTimer.singleShot(100, self.apply_text_settings)
            QTimer.singleShot(200, self.force_resize_all_labels)

            # CRITICAL: Reapply directional visibility setting
            self.apply_directional_mode()

            next_state_text = "All Controls"

        else:
            self.current_view_state = 'normal'
            next_state_text = "All Controls"
        
        # Update button label for next toggle
        self.controls_mode_button.setText(f"Show {next_state_text}")
        
        # IMPORTANT: Update No Buttons visibility based on new view state
        QTimer.singleShot(150, self.update_no_buttons_visibility)

    # Fix 2: Update show_all_controls_combined to ensure notification is created and shown
    def show_all_controls_combined(self):
        """Show all possible control types in one view"""

        print("\n--- Showing all combined controls ---")
        
        # Combine all groups manually
        combined_controls = {
            # Add standard directional controls
            "P1_JOYSTICK_UP": "LS Up",
            "P1_JOYSTICK_DOWN": "LS Down",
            "P1_JOYSTICK_LEFT": "LS Left",
            "P1_JOYSTICK_RIGHT": "LS Right",
            "P1_JOYSTICKRIGHT_UP": "RS Up",
            "P1_JOYSTICKRIGHT_DOWN": "RS Down",
            "P1_JOYSTICKRIGHT_LEFT": "RS Left",
            "P1_JOYSTICKRIGHT_RIGHT": "RS Right",
            # Add XInput buttons
            **{f"P1_BUTTON{i}": f"Button {i}" for i in range(1, 11)},
            "P1_START": "Start",
            "P1_SELECT": "Select",
            # Add specialized controls
            "P1_DIAL": "Rotary Dial",
            "P1_DIAL_V": "Vertical Dial",
            "P1_PADDLE": "Paddle",
            "P1_TRACKBALL_X": "Trackball X",
            "P1_TRACKBALL_Y": "Trackball Y",
            "P1_MOUSE_X": "Mouse X",
            "P1_MOUSE_Y": "Mouse Y",
            "P1_AD_STICK_X": "Analog X",
            "P1_AD_STICK_Y": "Analog Y",
            "P1_AD_STICK_Z": "Analog Z",
            "P1_LIGHTGUN_X": "Light Gun X",
            "P1_LIGHTGUN_Y": "Light Gun Y",
            "P1_PEDAL": "Pedal 1",
            "P1_PEDAL2": "Pedal 2",
            "P1_POSITIONAL": "Positional",
            "P1_GAMBLE_HIGH": "Gamble High",
            "P1_GAMBLE_LOW": "Gamble Low",
        }

        # PRESERVE No Buttons notification if it exists
        no_buttons_data = None
        if "NO_BUTTONS_NOTIFICATION" in self.control_labels:
            no_buttons_data = self.control_labels["NO_BUTTONS_NOTIFICATION"].copy()
            print("DEBUG: Preserving existing No Buttons notification")

        # Clear existing controls EXCEPT No Buttons notification
        for control_name in list(self.control_labels.keys()):
            if control_name == "NO_BUTTONS_NOTIFICATION":
                continue  # Don't delete the No Buttons notification
            if 'label' in self.control_labels[control_name]:
                self.control_labels[control_name]['label'].deleteLater()
            del self.control_labels[control_name]

        # Create the combined label layout (don't hide No Buttons notification)
        self._show_specialized_group(combined_controls, group_name="All Combined Controls", hide_no_buttons=False)

        # RESTORE or CREATE No Buttons notification
        if no_buttons_data:
            # Restore the preserved notification
            self.control_labels["NO_BUTTONS_NOTIFICATION"] = no_buttons_data
            self.no_buttons_label = no_buttons_data['label']
            print("DEBUG: Restored preserved No Buttons notification")
        elif not hasattr(self, 'no_buttons_label') or not self.no_buttons_label:
            # Create it if it doesn't exist
            print("DEBUG: Creating new No Buttons notification for Show All Controls")
            self.create_no_buttons_notification()

        # FORCE it to show in Show All Controls view
        if hasattr(self, 'no_buttons_label') and self.no_buttons_label:
            self.no_buttons_label.setVisible(True)
            self.no_buttons_label.raise_()
            self.no_buttons_visible = True
            print("DEBUG: Forcing No Buttons notification visible in Show All Controls view")
        # Truncate display text with minimal space loss
    def truncate_display_text(self, text, max_length=15):
        """Truncate display text with minimal space loss"""
        if len(text) <= max_length:
            return text
        return text[:max_length-1] + "›"  # Single character indicator
    
    def show_all_directional_controls(self):
        """Show all directional controls for global positioning"""
        
        # Directional controls for positioning - P1 ONLY
        directional_controls = {
            # Left stick
            "P1_JOYSTICK_UP": "LS Up",
            "P1_JOYSTICK_DOWN": "LS Down",
            "P1_JOYSTICK_LEFT": "LS Left",
            "P1_JOYSTICK_RIGHT": "LS Right",
            
            # Right stick 
            "P1_JOYSTICKRIGHT_UP": "RS Up",
            "P1_JOYSTICKRIGHT_DOWN": "RS Down",
            "P1_JOYSTICKRIGHT_LEFT": "RS Left",
            "P1_JOYSTICKRIGHT_RIGHT": "RS Right",
        }
        
        try:
            from PyQt5.QtGui import QFont, QFontInfo, QColor, QFontDatabase, QFontMetrics
            from PyQt5.QtCore import QPoint, Qt, QTimer
            from PyQt5.QtWidgets import QLabel, QSizePolicy
            import os
            
            print("\n--- Showing directional controls ---")
            
            # Save existing control positions as backup
            if not hasattr(self, 'original_controls_backup'):
                self.original_controls_backup = {}
                for control_name, control_data in self.control_labels.items():
                    self.original_controls_backup[control_name] = {
                        'action': control_data['action'],
                        'position': control_data['label'].pos(),
                        'original_pos': control_data.get('original_pos', QPoint(0, 0))
                    }
            
            # Clear ALL existing controls first
            for control_name in list(self.control_labels.keys()):
                if control_name in self.control_labels:
                    if 'label' in self.control_labels[control_name]:
                        self.control_labels[control_name]['label'].deleteLater()
                    del self.control_labels[control_name]

            # Clear collections
            self.control_labels = {}
            
            # Load saved positions
            saved_positions = self.load_saved_positions()
            
            # Extract text settings
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
            
            # Use existing font if available
            if hasattr(self, 'current_font') and self.current_font:
                font = QFont(self.current_font)
            elif hasattr(self, 'initialized_font') and self.initialized_font:
                font = QFont(self.initialized_font)
            else:
                # Create a standard font as a last resort
                font = QFont(font_family, font_size)
                font.setBold(bold_strength)
                font.setStyleStrategy(QFont.PreferMatch)
            
            # Calculate maximum text width
            max_text_width = self.calculate_max_text_width(
                directional_controls,
                font,
                show_button_prefix=show_button_prefix,
                use_uppercase=use_uppercase,
                extra_padding=40
            )
            
            # Create all directional controls with organized layout
            for control_name, action_text in directional_controls.items():
                # Apply uppercase if needed
                if use_uppercase:
                    action_text = action_text.upper()
                
                # Get button prefix
                button_prefix = self.get_button_prefix(control_name)
                
                # Add prefix if enabled
                display_text = action_text
                if show_button_prefix and button_prefix:
                    display_text = f"{button_prefix}: {action_text}"
                
                # ADD THIS LINE to truncate long text
                display_text = self.truncate_display_text(display_text)
                
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
                
                # Apply font
                label.setFont(font)
                label.setStyleSheet(f"background-color: transparent; border: none; font-family: '{font.family()}';")
                
                label.prefix = button_prefix
                label.action = action_text
                
                # Configure label sizing
                label.setMinimumSize(0, 0)
                label.setMaximumSize(16777215, 16777215)
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                
                # Make sure we have proper settings in the label
                label.settings = self.text_settings.copy()
                
                # Let the label auto-size based on content
                label.adjustSize()

                # Resize with better sizing logic
                font_metrics = QFontMetrics(label.font())
                text_width = font_metrics.horizontalAdvance(display_text)
                
                # Get font family to check if it's a custom font
                font_family = label.font().family()
                is_custom_font = font_family not in ["Arial", "Verdana", "Tahoma", "Times New Roman", 
                                                    "Courier New", "Segoe UI", "Calibri", "Georgia", 
                                                    "Impact", "System"]

                # Determine padding based on font type
                base_padding = 50 if is_custom_font else 30
                if len(display_text) > 15:
                    base_padding += 20
                if len(display_text) > 20:
                    base_padding += 30
                    
                label_width = text_width + base_padding
                label_height = label.height()
                label.resize(label_width, label_height)
                
                # Determine position from saved positions or organize in a grid
                x, y = 0, 0
                
                if saved_positions and control_name in saved_positions:
                    # Use the coordinates from global positions
                    pos_x, pos_y = saved_positions[control_name]
                    x, y = pos_x, pos_y + y_offset
                    original_pos = QPoint(pos_x, pos_y)
                
                elif control_name in self.original_controls_backup:
                    # Use backup position
                    backup_pos = self.original_controls_backup[control_name]['position']
                    x, y = backup_pos.x(), backup_pos.y()
                    original_pos = self.original_controls_backup[control_name]['original_pos']
                
                else:
                    # Organize in a logical layout by control type
                    if 'JOYSTICK_' in control_name:  # Left stick
                        if 'UP' in control_name:
                            x, y = 300, 100 + y_offset
                        elif 'DOWN' in control_name:
                            x, y = 300, 220 + y_offset
                        elif 'LEFT' in control_name:
                            x, y = 200, 160 + y_offset
                        elif 'RIGHT' in control_name:
                            x, y = 400, 160 + y_offset
                            
                    elif 'JOYSTICKRIGHT_' in control_name:  # Right stick
                        if 'UP' in control_name:
                            x, y = 700, 100 + y_offset
                        elif 'DOWN' in control_name:
                            x, y = 700, 220 + y_offset
                        elif 'LEFT' in control_name:
                            x, y = 600, 160 + y_offset
                        elif 'RIGHT' in control_name:
                            x, y = 800, 160 + y_offset
                    
                    original_pos = QPoint(x, y - y_offset)
                
                # Apply position
                label.move(x, y)
                
                # Store in control_labels
                self.control_labels[control_name] = {
                    'label': label,
                    'action': action_text,
                    'prefix': button_prefix,
                    'original_pos': original_pos
                }
                
                # All controls should be visible
                label.setVisible(True)
            
            # Set directional mode flag
            self.showing_all_directionals = True
            self.showing_all_xinput_controls = False
            self.showing_specialized_controls = False
            
            # Force updates
            QTimer.singleShot(50, lambda: self.force_resize_all_labels())
            QTimer.singleShot(150, lambda: self.apply_text_settings())
            
            # Force a canvas update
            self.canvas.update()
            
            print(f"Created and displayed {len(directional_controls)} directional controls")
            return True
            
        except Exception as e:
            print(f"Error showing directional controls: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def show_all_xinput_controls(self):
        """Show all standard controls for global positioning with fixed prefixes"""
        
        # Standard controls for positioning - P1 ONLY
        standard_controls = {
            # Analog sticks
            "P1_JOYSTICK_UP": "LS Up",
            "P1_JOYSTICK_DOWN": "LS Down",
            "P1_JOYSTICK_LEFT": "LS Left",
            "P1_JOYSTICK_RIGHT": "LS Right",
            "P1_JOYSTICKRIGHT_UP": "RS Up",
            "P1_JOYSTICKRIGHT_DOWN": "RS Down",
            "P1_JOYSTICKRIGHT_LEFT": "RS Left",
            "P1_JOYSTICKRIGHT_RIGHT": "RS Right",
            
            # Face buttons with DirectInput equivalents
            "P1_BUTTON1": "Button 1",
            "P1_BUTTON2": "Button 2",
            "P1_BUTTON3": "Button 3",
            "P1_BUTTON4": "Button 4",
            
            # Shoulder/trigger buttons
            "P1_BUTTON5": "Button 5",
            "P1_BUTTON6": "Button 6",
            "P1_BUTTON7": "Button 7",
            "P1_BUTTON8": "Button 8",
            
            # Thumbstick buttons
            "P1_BUTTON9": "Button 9",
            "P1_BUTTON10": "Button 10",
            
            # System buttons
            "P1_START": "Start",
            "P1_SELECT": "Select",
        }
        
        try:
            from PyQt5.QtGui import QFont, QFontInfo, QColor, QFontDatabase, QFontMetrics
            from PyQt5.QtCore import QPoint, Qt, QTimer
            from PyQt5.QtWidgets import QLabel, QSizePolicy
            import os
            
            print("\n--- Showing standard controls with fixed prefixes ---")
            
            # CRITICAL FIX: First ensure fonts are properly loaded/registered
            if not hasattr(self, 'current_font') or self.current_font is None:
                print("Font not initialized - forcing font loading before showing controls")
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
            
            # Clear ALL existing controls first AND hide No Buttons notification
            for control_name in list(self.control_labels.keys()):
                if control_name == "NO_BUTTONS_NOTIFICATION":
                    # ALWAYS hide No Buttons notification during specialized views
                    if 'label' in self.control_labels[control_name] and self.control_labels[control_name]['label']:
                        self.control_labels[control_name]['label'].setVisible(False)
                        self.no_buttons_visible = False
                        print("DEBUG: Hiding No Buttons notification in specialized view")
                    continue  # Don't delete it, just hide it
                
                # Remove other controls from the canvas
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
                print(f"Using existing current_font for controls: {font.family()}")
            elif hasattr(self, 'initialized_font') and self.initialized_font:
                font = QFont(self.initialized_font)
                print(f"Using initialized_font for controls: {font.family()}")
            else:
                # Create a standard font as a last resort
                font = QFont(font_family, font_size)
                font.setBold(bold_strength)
                font.setStyleStrategy(QFont.PreferMatch)  # Force exact matching
                print(f"Created new font for controls: {font.family()} (fallback)")
            
            # NOW call calculate_max_text_width AFTER defining standard_controls and font
            max_text_width = self.calculate_max_text_width(
                standard_controls,
                font,
                show_button_prefix=show_button_prefix,
                use_uppercase=use_uppercase,
                extra_padding=40  # Increased padding for safety
            )
            
            # Print actual font info for debugging
            font_info = QFontInfo(font)
            print(f"Actual font being used: {font_info.family()}, size: {font_info.pointSize()}")
            
            # Calculate the maximum text width needed 
            font_metrics = QFontMetrics(font)
            max_text_width = 0
            
            # Default grid layout
            grid_x, grid_y = 0, 0
            
            # Create all controls
            for control_name, action_text in standard_controls.items():
                # Apply uppercase if needed
                if use_uppercase:
                    action_text = action_text.upper()
                
                # SIMPLE SOLUTION: Just use a fixed prefix for all controls
                # This way we don't need to detect the mode or handle all the different mapping types
                button_prefix = "P1"  # Simple fixed prefix
                
                # Add prefix if enabled
                display_text = action_text
                if show_button_prefix and button_prefix:
                    display_text = f"{button_prefix}: {action_text}"
                
                # ADD THIS LINE to truncate long text
                display_text = self.truncate_display_text(display_text)
                
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
                
                # First, let the label auto-size based on content
                label.adjustSize()

                # More aggressive approach to prevent text truncation
                font_metrics = QFontMetrics(label.font())
                text_width = font_metrics.horizontalAdvance(display_text)

                # Get font family to check if it's a custom font
                font_family = label.font().family()
                is_custom_font = font_family not in ["Arial", "Verdana", "Tahoma", "Times New Roman", 
                                                "Courier New", "Segoe UI", "Calibri", "Georgia", 
                                                "Impact", "System"]

                # Determine base padding based on font type
                base_padding = 50 if is_custom_font else 30

                # Add additional padding for longer text
                if len(display_text) > 15:
                    base_padding += 20
                if len(display_text) > 20:
                    base_padding += 30
                    
                # Special case for Select button or text containing Select
                if "SELECT" in control_name or "Select" in action_text:
                    base_padding += 25
                    
                # Calculate final width with generous padding
                label_width = text_width + base_padding
                label_height = label.height()

                # Debug output for problematic labels
                if "SELECT" in control_name or len(display_text) > 15:
                    print(f"Setting width for {control_name}: text={text_width}px, padding={base_padding}px, final={label_width}px")

                # Resize with the calculated width
                label.resize(label_width, label_height)
                
                # Determine position
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
                    # Use a more organized grid layout for standard controls
                    # Group similar controls together
                    if 'BUTTON' in control_name:
                        if int(control_name.replace('P1_BUTTON', '')) <= 4:
                            # Face buttons (1-4) in a 2x2 grid
                            button_num = int(control_name.replace('P1_BUTTON', ''))
                            col = (button_num - 1) % 2
                            row = (button_num - 1) // 2
                            x = 100 + (col * 200)
                            y = 100 + (row * 60) + y_offset
                        else:
                            # Shoulder/trigger buttons (5-10) in rows
                            button_num = int(control_name.replace('P1_BUTTON', ''))
                            row = 2 + (button_num - 5) // 2
                            col = (button_num - 5) % 2
                            x = 100 + (col * 200)
                            y = 100 + (row * 60) + y_offset
                    elif 'JOYSTICK' in control_name:
                        # Left stick controls
                        if 'UP' in control_name:
                            x, y = 450, 100 + y_offset
                        elif 'DOWN' in control_name:
                            x, y = 450, 160 + y_offset
                        elif 'LEFT' in control_name:
                            x, y = 350, 130 + y_offset
                        elif 'RIGHT' in control_name:
                            x, y = 550, 130 + y_offset
                    elif 'JOYSTICKRIGHT' in control_name:
                        # Right stick controls
                        if 'UP' in control_name:
                            x, y = 450, 220 + y_offset
                        elif 'DOWN' in control_name:
                            x, y = 450, 280 + y_offset
                        elif 'LEFT' in control_name:
                            x, y = 350, 250 + y_offset
                        elif 'RIGHT' in control_name:
                            x, y = 550, 250 + y_offset
                    elif 'START' in control_name:
                        x, y = 700, 220 + y_offset
                    elif 'SELECT' in control_name:
                        x, y = 700, 280 + y_offset
                    else:
                        # Default fallback grid
                        x = 100 + (grid_x * 220)
                        y = 350 + (grid_y * 60) + y_offset
                        grid_x = (grid_x + 1) % 4
                        if grid_x == 0:
                            grid_y += 1
                    
                    original_pos = QPoint(x, y - y_offset)
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
                if any(control_type in control_name for control_type in ["JOYSTICK", "JOYSTICKRIGHT", "DPAD"]):
                    is_visible = self.texts_visible and self.joystick_visible
                
                label.setVisible(is_visible)
            
            # Update button text to include current ROM name
            if hasattr(self, 'xinput_controls_button'):
                self.xinput_controls_button.setText("Specialized Group 1")
            
            # Set XInput mode flag
            self.showing_all_xinput_controls = True
            self.showing_specialized_controls = False
            
            # CRITICAL FIX: Force updates with staggered timers for reliable application
            QTimer.singleShot(50, lambda: self.force_resize_all_labels())
            QTimer.singleShot(150, lambda: self.apply_text_settings())
            QTimer.singleShot(250, lambda: self.force_resize_all_labels())  # Second pass
            
            # Force a canvas update
            self.canvas.update()
            
            print(f"Created and displayed {len(standard_controls)} standard controls with fixed P1 prefixes")
    
            # Hide No Buttons notification in specialized views (except Show All Controls)
            if hasattr(self, 'no_buttons_label') and self.no_buttons_label:
                self.no_buttons_label.setVisible(False)
                self.no_buttons_visible = False
                print("DEBUG: Hiding No Buttons notification in specialized view")
            
            return True
            
        except Exception as e:
            print(f"Error showing controls: {e}")
            import traceback
            traceback.print_exc()
            return False

    # 5. Update the toggle_xinput_controls method to handle the interaction with specialized controls
    def toggle_xinput_controls(self):
        """Toggle between normal game controls and standard XInput controls"""
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
                self.xinput_controls_button.setText("Standard XInput")
            
            # Reload the current game controls from scratch
            self.create_control_labels()
            
            # CRITICAL FIX: Force apply the font after recreating controls
            QTimer.singleShot(100, self.apply_text_settings)
            QTimer.singleShot(200, self.force_resize_all_labels)
            
            print("Switched back to normal game controls with font restoration")
        else:
            # Make sure we're not showing specialized controls
            self.showing_specialized_controls = False
            
            # Switch to showing all XInput controls
            self.show_all_xinput_controls()
            
            # Update specialized controls button if it exists
            if hasattr(self, 'specialized_controls_button'):
                self.specialized_controls_button.setText("Specialized Controls")

    def get_standard_directional_controls(self, control_name):
        """Check if control is standard directional"""
        return any(control_type in control_name for control_type in [
            "JOYSTICK", "JOYSTICKLEFT", "JOYSTICKRIGHT", "DPAD"
        ])

    def get_specialized_directional_controls(self, control_name):
        """Check if control is specialized directional"""
        return any(control_type in control_name for control_type in [
            "DIAL", "PADDLE", "TRACKBALL", "MOUSE", "LIGHTGUN", 
            "AD_STICK", "PEDAL", "POSITIONAL"
        ])

    def apply_joystick_visibility(self):
        """Apply joystick visibility ONLY to standard directional controls, leave specialized controls alone"""
        controls_updated = 0
        
        # Get the auto-show directionals setting
        auto_show_directionals = getattr(self, 'auto_show_directionals_for_directional_only', True)
        
        # Check if this is a directional-only game
        is_directional_only = getattr(self, 'is_directional_only_game', False)
        
        for control_name, control_data in self.control_labels.items():
            # Skip if label doesn't exist
            if 'label' not in control_data or not control_data['label']:
                continue
                
            # ONLY affect STANDARD directional controls (joystick, d-pad)
            # Do NOT affect specialized controls (trackball, dial, etc.)
            standard_directional_types = [
                "JOYSTICK", "JOYSTICKLEFT", "JOYSTICKRIGHT", "DPAD"
            ]
            
            if any(control_type in control_name for control_type in standard_directional_types):
                # This is a standard directional control - apply joystick_visible logic
                
                if is_directional_only and auto_show_directionals and not self.joystick_visible:
                    # Override to visible for directional-only games (if auto-show enabled)
                    is_visible = self.texts_visible
                    print(f"Auto-showing standard directional {control_name} for directional-only game")
                else:
                    # Use manual joystick_visible setting
                    is_visible = self.texts_visible and self.joystick_visible
                
                # Only update if needed
                if control_data['label'].isVisible() != is_visible:
                    control_data['label'].setVisible(is_visible)
                    controls_updated += 1
                    print(f"Updated {control_name} visibility to {is_visible}")
            
            # SPECIALIZED controls are left alone - they keep their current visibility
            # This includes: DIAL, PADDLE, TRACKBALL, MOUSE, LIGHTGUN, AD_STICK, PEDAL, POSITIONAL
        
        # Force immediate canvas update to remove delay
        if hasattr(self, 'canvas'):
            self.canvas.update()
            self.canvas.repaint()
        
        print(f"Applied standard directional visibility to {controls_updated} controls (joystick_visible: {self.joystick_visible})")
        print(f"Specialized directional controls (trackball, dial, etc.) are unaffected")
        return controls_updated

    def is_standard_directional_control(self, control_name):
        """Check if control is a standard directional control (joystick, d-pad)"""
        standard_directional_types = [
            "JOYSTICK", "JOYSTICKLEFT", "JOYSTICKRIGHT", "DPAD"
        ]
        return any(control_type in control_name for control_type in standard_directional_types)

    def is_specialized_directional_control(self, control_name):
        """Check if control is a specialized directional control (dial, trackball, etc.)"""
        specialized_directional_types = [
            "DIAL", "PADDLE", "TRACKBALL", "MOUSE", "LIGHTGUN", 
            "AD_STICK", "PEDAL", "POSITIONAL"
        ]
        return any(control_type in control_name for control_type in specialized_directional_types)

    # Update the game analysis method to use the helper:
    def analyze_game_controls_improved(self):
        """Analyze game controls to determine if it's directional-only (standard directional only)"""
        directional_count = 0
        button_count = 0
        
        # Scan game data to identify control types
        for player in self.game_data.get('players', []):
            if player['number'] != 1:  # Only analyze Player 1 controls
                continue
            
            for control in player.get('labels', []):
                control_name = control['name']
                
                # Count STANDARD directional controls only
                if self.is_standard_directional_control(control_name):
                    directional_count += 1
                # Count button controls (excluding directional inputs)
                elif any(control_type in control_name for control_type in ["BUTTON", "START", "SELECT", "GAMBLE"]):
                    button_count += 1
        
        # Determine if this is a directional-only game (based on STANDARD directional only)
        self.is_directional_only_game = directional_count > 0 and button_count == 0
        self.has_any_buttons = button_count > 0
        print(f"Game control analysis: {directional_count} standard directional, {button_count} buttons")
        print(f"Is standard-directional-only game: {self.is_directional_only_game}")
        
        return self.is_directional_only_game

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
            
            # Use simplified PyQt5 toast notification
            self.show_toast_notification("Text settings saved")
            
        except Exception as e:
            print(f"Error saving global text settings: {e}")
            import traceback
            traceback.print_exc()
    
    def load_bezel_settings_with_directional(self):
        """Load bezel and directional mode settings from file in settings directory"""
        settings = {
            "bezel_visible": False,
            "joystick_visible": True,  # Default to visible 
            "auto_show_directionals_for_directional_only": True,
            "directional_mode": "show_all",  # Add this
            "hide_specialized_with_directional": False  # Add this
        }
        
        try:
            # Check new location first
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
                    print(f"Loaded bezel/directional settings from {settings_file}: {settings}")
        except Exception as e:
            print(f"Error loading bezel/directional settings: {e}")
        
        # Set the directional mode variables
        self.directional_mode = settings.get("directional_mode", "show_all")
        self.joystick_visible = settings.get("joystick_visible", True)
        self.hide_specialized_with_directional = settings.get("hide_specialized_with_directional", False)
        self.auto_show_directionals_for_directional_only = settings.get("auto_show_directionals_for_directional_only", True)

        return settings
    
    def load_bezel_settings(self):
        """Load bezel settings with caching"""
        # Return cached result if available
        if hasattr(self, '_cached_bezel_settings'):
            print("Using cached bezel settings")
            return self._cached_bezel_settings
        
        print("Loading bezel settings (first time)")
        """Load bezel and joystick visibility settings from file in settings directory"""
        settings = {
            "bezel_visible": False,
            "joystick_visible": False,
            "auto_show_directionals_for_directional_only": True
        }
        
        try:
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
                    print(f"Loaded bezel/joystick settings from {settings_file}")
            
            # Cache the result
            self._cached_bezel_settings = settings
            print(f"Cached bezel settings for future use")
            
        except Exception as e:
            print(f"Error loading bezel/joystick settings: {e}")
            # Cache the defaults even on error
            self._cached_bezel_settings = settings
        
        return settings

    # ALSO FIX: Your save_bezel_settings method is overwriting directional settings
    def save_bezel_settings(self, is_global=True):
        """Save bezel and directional settings - FIXED VERSION"""
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Settings file path - always global in new structure
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            
            # Load existing settings first to avoid overwriting
            existing_settings = {}
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    existing_settings = json.load(f)
            
            # Create settings object with current values
            new_settings = {
                "bezel_visible": getattr(self, 'bezel_visible', False),
                "joystick_visible": getattr(self, 'joystick_visible', True),
                "auto_show_directionals_for_directional_only": getattr(self, 'auto_show_directionals_for_directional_only', True),
                "directional_mode": getattr(self, 'directional_mode', 'show_all'),
                "hide_specialized_with_directional": getattr(self, 'hide_specialized_with_directional', False)
            }
            
            # Merge with existing settings (existing takes precedence for unset values)
            for key, value in existing_settings.items():
                if key not in new_settings:
                    new_settings[key] = value
            
            # Save settings
            with open(settings_file, 'w') as f:
                json.dump(new_settings, f)
                
            print(f"Saved bezel/directional settings to {settings_file}: {new_settings}")
            return True
            
        except Exception as e:
            print(f"Error saving bezel/directional settings: {e}")
            import traceback
            traceback.print_exc()
            return False
    
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
    
    def toggle_logo(self):
        """Toggle logo visibility with global saving"""
        self.logo_visible = not self.logo_visible
        
        # Update button text
        self.logo_button.setText("Hide Logo" if self.logo_visible else "Show Logo")
        
        # Toggle logo visibility
        if hasattr(self, 'logo_label'):
            self.logo_label.setVisible(self.logo_visible)
        elif self.logo_visible:
            # Create logo if it doesn't exist yet
            self.add_logo()
        
        # CRITICAL: Enforce correct layer order
        self.enforce_layer_order()
        
        # Update settings
        self.logo_settings["logo_visible"] = self.logo_visible
        
        # Save the logo settings *globally* (not per ROM)
        if hasattr(self, 'save_logo_settings'):
            self.save_logo_settings(is_global=True)
            self.show_toast_notification("Logo visibility saved globally")
        else:
            # Fallback to save_positions if save_logo_settings is not available
            # But make sure to use is_global=True for global saving
            self.save_positions(is_global=True)
            self.show_toast_notification("Logo visibility saved globally")
    
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
            self.show_toast_notification("Logo settings saved")
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
        
    def delete_rom_specific_settings(self):
        """Delete ROM-specific settings files and refresh preview with global settings"""
        try:
            # List of possible ROM-specific settings files
            rom_files = [
                os.path.join(self.settings_dir, f"{self.rom_name}_positions.json"),
                os.path.join(self.settings_dir, f"{self.rom_name}_logo.json"),
                os.path.join(self.settings_dir, f"{self.rom_name}_bezel.json"),
                # Add any other ROM-specific settings files here
            ]
            
            # Check if any files exist
            existing_files = [f for f in rom_files if os.path.exists(f)]
            
            if not existing_files:
                # No files to delete
                self.show_toast_notification(f"No ROM-specific settings found for {self.rom_name}")
                return False
            
            # Ask for confirmation
            from PyQt5.QtWidgets import QMessageBox
            confirm = QMessageBox.question(
                self,
                "Confirm Reset",
                f"Delete all ROM-specific settings for {self.rom_name}?\n\nThis will revert to global settings.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if confirm != QMessageBox.Yes:
                return False
                
            # Delete the files
            deleted_count = 0
            for file_path in existing_files:
                try:
                    os.remove(file_path)
                    print(f"Deleted ROM-specific settings: {file_path}")
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")
            
            # Show success message
            self.show_toast_notification(f"Reset {deleted_count} ROM-specific settings")
            
            # REFRESH PREVIEW WITH GLOBAL SETTINGS:
            
            # 1. Reload global positions
            from PyQt5.QtCore import QTimer
            global_positions = self.load_saved_positions()  # This now loads global positions since ROM files are gone
            
            # 2. Reset control positions
            self.reset_positions()
            
            # 3. Reload bezel settings from global
            bezel_settings = self.load_bezel_settings()
            self.bezel_visible = bezel_settings.get("bezel_visible", False)
            
            # 4. Apply bezel visibility
            if hasattr(self, 'bezel_label') and self.bezel_label:
                self.bezel_label.setVisible(self.bezel_visible)
                if hasattr(self, 'bezel_button'):
                    self.bezel_button.setText("Hide Bezel" if self.bezel_visible else "Show Bezel")
            
            # 5. Reload logo settings from global
            self.logo_settings = self.load_logo_settings()
            self.logo_visible = self.logo_settings.get("logo_visible", True)
            
            # 6. Apply logo settings
            if hasattr(self, 'logo_label') and self.logo_label:
                self.logo_label.setVisible(self.logo_visible)
                self.update_logo_display()  # Apply position, size, etc.
                if hasattr(self, 'logo_button'):
                    self.logo_button.setText("Hide Logo" if self.logo_visible else "Show Logo")
            
            # 7. Reload and apply text settings
            self.text_settings = self.load_text_settings()
            self.apply_text_settings()
            
            # 8. Enforce the proper layer order
            self.enforce_layer_order()
            
            # 9. Force a complete refresh with slight delays
            QTimer.singleShot(100, self.force_resize_all_labels)
            QTimer.singleShot(300, self.enforce_layer_order)
            
            print(f"Preview refreshed with global settings")
            return True
            
        except Exception as e:
            print(f"Error resetting ROM settings: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def save_image(self):
        """Enhanced save_image method that uses toast notifications"""
        try:
            # Create the images directory if it doesn't exist
            images_dir = os.path.join(self.preview_dir, "screenshots")
            os.makedirs(images_dir, exist_ok=True)
            
            # Define the output path
            output_path = os.path.join(images_dir, f"{self.rom_name}.png")
            
            # Check if file already exists - keep confirmation for overwriting
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
            # Fill with transparent background
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
                    
                    # Get settings and properties from the label
                    settings = getattr(label, 'settings', {})
                    prefix = getattr(label, 'prefix', '')
                    action = getattr(label, 'action', label.text())
                    
                    # Calculate vertical position - centered in the label
                    y = int(pos.y() + (label.height() + metrics.ascent() - metrics.descent()) / 2)
                    
                    # Check for the label's text alignment mode - default to left alignment
                    text_alignment = getattr(label, 'text_alignment', Qt.AlignLeft | Qt.AlignVCenter)
                    
                    # FIXED: Use fixed left margin to match label classes
                    # This ensures consistent text positioning between preview and saved image
                    left_margin = 10  # Same as in ColoredDraggableLabel and GradientDraggableLabel
                    x = int(pos.x() + left_margin)  # Fixed left margin
                    
                    # Handle colored/gradient text
                    if prefix and ": " in label.text():
                        prefix_text = f"{prefix}: "
                        
                        # Calculate widths
                        prefix_width = metrics.horizontalAdvance(prefix_text)
                        
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
                        # Single text - use same left alignment as label classes
                        
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
                
                # Use toast notification instead of message box
                self.show_toast_notification(f"Image saved to screenshots folder")
                
                return True
            else:
                print(f"Failed to save image to {output_path}")
                
                # Keep error as a dialog
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
            
            # Keep error as a dialog
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save image: {str(e)}"
            )
            return False

    def handle_key_press(self, event):
        """Handle key press events"""
        from PyQt5.QtCore import Qt
        
        # Close on Escape
        if event.key() == Qt.Key_Escape:
            # Close the window
            self.close()
            
            # If this is a standalone preview, also exit the application
            if getattr(self, 'standalone_mode', False):
                # Give a short delay before quitting to allow cleanup
                QTimer.singleShot(100, QApplication.quit)
        
        # Distribute vertically with Ctrl+D
        elif event.key() == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            self.distribute_controls_vertically()
            event.accept()
    
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

    def load_background_image_fullscreen(self, force_default=None):
        """Load background image with detailed debugging"""
        try:
            image_path = None
            
            # If force_default is provided, use it directly
            if force_default and os.path.exists(force_default):
                image_path = force_default
                print(f"Using forced default background: {image_path}")
            else:
                # Build priority list for background images
                possible_paths = []
                
                # Priority 1: ROM-specific images in preview/images directory
                possible_paths.extend([
                    os.path.join(self.preview_dir, "images", f"{self.rom_name}.png"),
                    os.path.join(self.preview_dir, "images", f"{self.rom_name}.jpg"),
                ])
                
                # Priority 2: Default images
                possible_paths.extend([
                    os.path.join(self.preview_dir, "images", "default.png"),
                    os.path.join(self.preview_dir, "images", "default.jpg"),
                ])
                
                # Find the first existing image path
                for path in possible_paths:
                    if os.path.exists(path):
                        image_path = path
                        print(f"Found background image: {image_path}")
                        break
                
                # If no image found, create transparent default
                if not image_path:
                    image_path = self.initialize_transparent_background()
                    print(f"Created transparent background: {image_path}")
                    
            # DEBUG: Print what we're about to load
            print(f"DEBUG: About to load background from: {image_path}")
            print(f"DEBUG: File exists: {os.path.exists(image_path) if image_path else False}")
            
            # Set background image if found or created
            if image_path and os.path.exists(image_path):
                # Clean up existing background
                if hasattr(self, 'bg_label') and self.bg_label:
                    print("DEBUG: Cleaning up existing background")
                    self.bg_label.deleteLater()
                    
                # Create new background label
                print("DEBUG: Creating new background label")
                self.bg_label = QLabel(self.canvas)
                
                # Load the original pixmap
                print(f"DEBUG: Loading pixmap from {image_path}")
                original_pixmap = QPixmap(image_path)
                
                if original_pixmap.isNull():
                    print(f"ERROR: Could not load pixmap from {image_path}")
                    self.bg_label.setText("Error loading background image")
                    self.bg_label.setStyleSheet("color: red; font-size: 18px;")
                    self.bg_label.setAlignment(Qt.AlignCenter)
                    self.bg_label.setGeometry(0, 0, self.canvas.width(), self.canvas.height())
                    return
                
                print(f"DEBUG: Original pixmap size: {original_pixmap.width()}x{original_pixmap.height()}")
                
                # Store the original pixmap
                self.original_background_pixmap = original_pixmap
                
                # Get current canvas dimensions
                canvas_w = self.canvas.width()
                canvas_h = self.canvas.height()
                print(f"DEBUG: Canvas size: {canvas_w}x{canvas_h}")
                
                # SIMPLIFIED LOGIC: Always scale to fill canvas for now
                scaled_pixmap = original_pixmap.scaled(
                    canvas_w, 
                    canvas_h, 
                    Qt.IgnoreAspectRatio,  # Fill entire canvas
                    Qt.SmoothTransformation
                )
                
                print(f"DEBUG: Scaled pixmap size: {scaled_pixmap.width()}x{scaled_pixmap.height()}")
                
                # Always position at origin for now
                x, y = 0, 0
                
                # Store the scaled pixmap
                self.background_pixmap = scaled_pixmap
                
                # Set pixmap on label
                print("DEBUG: Setting pixmap on label")
                self.bg_label.setPixmap(scaled_pixmap)
                
                # Position the background
                print(f"DEBUG: Positioning background at ({x},{y}) with size {scaled_pixmap.width()}x{scaled_pixmap.height()}")
                self.bg_label.setGeometry(x, y, scaled_pixmap.width(), scaled_pixmap.height())
                
                # Store position info
                self.bg_pos = (x, y)
                self.bg_size = (scaled_pixmap.width(), scaled_pixmap.height())
                
                # Make sure background is below everything
                print("DEBUG: Lowering background to bottom layer")
                self.bg_label.lower()
                
                # Make sure it's visible
                print("DEBUG: Making background visible")
                self.bg_label.setVisible(True)
                self.bg_label.show()
                
                print(f"SUCCESS: Background loaded: {scaled_pixmap.width()}x{scaled_pixmap.height()}, positioned at ({x},{y})")
                
                # Update resize handler
                self.canvas.resizeEvent = self.on_canvas_resize_with_background
                
            else:
                print("ERROR: No background image path found or file doesn't exist")
                # Create a fallback colored background for debugging
                self.bg_label = QLabel(self.canvas)
                self.bg_label.setStyleSheet("background-color: #1a1a1a;")  # Dark gray for debugging
                self.bg_label.setGeometry(0, 0, self.canvas.width(), self.canvas.height())
                self.bg_label.show()
                print("DEBUG: Created fallback colored background")
                
        except Exception as e:
            print(f"EXCEPTION in load_background_image_fullscreen: {e}")
            import traceback
            traceback.print_exc()
            
            # Emergency fallback
            try:
                self.bg_label = QLabel("Background Load Error", self.canvas)
                self.bg_label.setStyleSheet("color: red; font-size: 18px; background-color: black;")
                self.bg_label.setAlignment(Qt.AlignCenter)
                self.bg_label.setGeometry(0, 0, self.canvas.width(), self.canvas.height())
                self.bg_label.show()
            except:
                print("Failed to create emergency fallback background")

    def on_canvas_resize_with_background(self, event):
        """Debounced canvas resize handler"""
        # Cancel any pending resize operation
        if hasattr(self, '_canvas_resize_timer'):
            self._canvas_resize_timer.stop()
        
        # Store the event for the actual resize
        self._pending_resize_event = event
        
        # Create new timer for debounced resize
        self._canvas_resize_timer = QTimer()
        self._canvas_resize_timer.setSingleShot(True)
        self._canvas_resize_timer.timeout.connect(self._do_canvas_resize)
        self._canvas_resize_timer.start(50)  # 50ms debounce

    def _do_canvas_resize(self):
        """Actually perform the canvas resize"""
        try:
            event = getattr(self, '_pending_resize_event', None)
            if not event:
                return
                
            print(f"--- Canvas resize event: {self.canvas.width()}x{self.canvas.height()} (debounced) ---")
            
            # Your existing resize logic here
            if hasattr(self, 'original_background_pixmap') and not self.original_background_pixmap.isNull():
                print("DEBUG: Resizing background...")
                
                canvas_w = self.canvas.width()
                canvas_h = self.canvas.height()
                
                scaled_pixmap = self.original_background_pixmap.scaled(
                    canvas_w, canvas_h, 
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation
                )
                
                if hasattr(self, 'bg_label') and self.bg_label:
                    self.bg_label.setPixmap(scaled_pixmap)
                    self.bg_label.setGeometry(0, 0, canvas_w, canvas_h)
                    print(f"DEBUG: Background resized to {canvas_w}x{canvas_h} (debounced)")
            
        except Exception as e:
            print(f"ERROR in debounced resize handler: {e}")

    def get_game_mappings(self):
        """Extract mappings from game data, supporting both gamedata.json and cache formats"""
        mappings = []
        
        try:
            print(f"\n=== MAPPING EXTRACTION DEBUG for {self.rom_name} ===")
            print(f"game_data type: {type(self.game_data)}")
            
            if hasattr(self, 'game_data') and self.game_data:
                # Print the keys available in game_data
                if isinstance(self.game_data, dict):
                    print(f"Available keys in game_data: {list(self.game_data.keys())}")
                
                # Method 1: Check for mappings directly at root level (cache format)
                if 'mappings' in self.game_data:
                    mappings = self.game_data['mappings']
                    print(f"Found mappings at root level: {mappings}")
                
                # Method 2: Check if game_data is nested with ROM name key (gamedata.json format)
                elif self.rom_name in self.game_data:
                    rom_data = self.game_data[self.rom_name]
                    print(f"Found ROM data for {self.rom_name}: {type(rom_data)}")
                    if isinstance(rom_data, dict) and 'mappings' in rom_data:
                        mappings = rom_data['mappings']
                        print(f"Found mappings in ROM data: {mappings}")
                
                # Method 3: Search through all values for mappings key
                else:
                    print("Searching through all game_data values for mappings...")
                    for key, value in self.game_data.items():
                        if isinstance(value, dict) and 'mappings' in value:
                            mappings = value['mappings']
                            print(f"Found mappings in {key}: {mappings}")
                            break
            
            # Ensure mappings is a list
            if isinstance(mappings, str):
                mappings = [mappings]
            elif not isinstance(mappings, list):
                if mappings:  # If mappings exists but isn't a list, try to convert
                    mappings = [str(mappings)]
                else:
                    mappings = []
            
            print(f"Final mappings result: {mappings}")
            print("=== END MAPPING EXTRACTION DEBUG ===\n")
                
        except Exception as e:
            print(f"Error extracting mappings: {e}")
            import traceback
            traceback.print_exc()
            mappings = []
        
        return mappings
    
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

    # 4. LOGO FORCE RESIZE (happening 3 times)
    # Fix: Add similar debouncing
    def force_logo_resize(self):
        """Force logo resize with debouncing"""
        if hasattr(self, '_logo_resize_timer'):
            self._logo_resize_timer.stop()
        
        self._logo_resize_timer = QTimer()
        self._logo_resize_timer.setSingleShot(True)
        self._logo_resize_timer.timeout.connect(self._do_force_logo_resize)
        self._logo_resize_timer.start(100)
    
    def _do_force_logo_resize(self):
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
        
        print(f"Logo resized to {scaled_pixmap.width()}x{scaled_pixmap.height()} pixels (debounced)")
        return True
    
    # 4. Fix load_text_settings to check settings_dir first, then migrate from preview_dir
    def load_text_settings(self):
        """Load text appearance settings from settings directory with migration support"""
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
            import os
            import json
            
            # First try the settings directory
            settings_file = os.path.join(self.settings_dir, "text_appearance_settings.json")
            
            # Check if file exists in settings directory
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
                    
                # Debug gradient settings
                prefix_gradient = settings.get("use_prefix_gradient", False)
                action_gradient = settings.get("use_action_gradient", False)
                print(f"Loaded text settings from {settings_file}")
                print(f"Loaded gradient settings: prefix={prefix_gradient}, action={action_gradient}")
            else:
                # Check for legacy global_text_settings.json in preview directory
                legacy_file = os.path.join(self.preview_dir, "global_text_settings.json")
                if os.path.exists(legacy_file):
                    # Load from legacy location
                    with open(legacy_file, 'r') as f:
                        loaded_settings = json.load(f)
                        settings.update(loaded_settings)
                    
                    # Migrate settings to new location
                    os.makedirs(self.settings_dir, exist_ok=True)
                    with open(settings_file, 'w') as f:
                        json.dump(settings, f)
                    
                    print(f"Migrated text settings from {legacy_file} to {settings_file}")
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

    # Fix 4: Update the mouse event handlers for No Buttons notification
    def on_label_release(self, event, label):
        """Handle mouse release to end dragging"""
        from PyQt5.QtCore import Qt
        
        if event.button() == Qt.LeftButton:
            label.dragging = False
            label.setCursor(Qt.OpenHandCursor)
            
            # SAVE POSITION if this is the No Buttons notification
            if hasattr(self, 'no_buttons_label') and label is self.no_buttons_label:
                self.save_no_buttons_position_to_file()
            
            # Hide guidance elements
            if hasattr(self, 'hide_alignment_guides'):
                self.hide_alignment_guides()
            if hasattr(self, 'hide_measurement_guides'):
                self.hide_measurement_guides()
            if hasattr(self, 'hide_position_indicator'):
                self.hide_position_indicator()
                
            event.accept()
    
    # Fix 6: Ensure the notification is created properly in __init__
    def enhance_no_buttons_initialization(self):
        """Call this in PreviewWindow.__init__ after control analysis"""
        # Make sure we have analyzed the game controls first
        if not hasattr(self, 'has_any_buttons'):
            self.analyze_game_controls_improved()
        
        # Always create the No Buttons notification (even for games with buttons)
        # so it's available for the "Show All Controls" view
        self.create_no_buttons_notification()
        
        # Set initial visibility based on game type
        if hasattr(self, 'no_buttons_label') and self.no_buttons_label:
            # Initially hide it - it will be shown when appropriate
            self.no_buttons_label.setVisible(False)
            self.no_buttons_visible = False
            print("DEBUG: No Buttons notification created and initially hidden")
        
        # Update visibility after a delay to ensure everything is initialized
        QTimer.singleShot(500, self.update_no_buttons_visibility)

    # Fix 5: Add proper position saving to file
    def save_no_buttons_position_to_file(self):
        """Save the No Buttons notification position to the actual position files"""
        if not hasattr(self, 'no_buttons_label') or not self.no_buttons_label:
            return
        
        try:
            # Update the in-memory position first
            self.save_no_buttons_position()
            
            # Get the current position
            pos = self.no_buttons_label.pos()
            y_offset = self.text_settings.get("y_offset", -40)
            normalized_pos = [pos.x(), pos.y() - y_offset]
            
            # Load existing global positions
            import os, json
            os.makedirs(self.settings_dir, exist_ok=True)
            positions_file = os.path.join(self.settings_dir, "global_positions.json")
            
            positions = {}
            if os.path.exists(positions_file):
                with open(positions_file, 'r') as f:
                    positions = json.load(f)
            
            # Update with No Buttons position
            positions["NO_BUTTONS_NOTIFICATION"] = normalized_pos
            
            # Save back to file
            with open(positions_file, 'w') as f:
                json.dump(positions, f)
            
            print(f"Saved No Buttons notification position to file: {normalized_pos}")
            
        except Exception as e:
            print(f"Error saving No Buttons position to file: {e}")
            import traceback
            traceback.print_exc()

    # 1. Enhanced get_button_prefix method for PreviewWindow class
    def get_button_prefix(self, control_name):
        """Generate button prefix based on control name with support for specialized controls"""
        # Standard XInput control prefixes
        standard_prefixes = {
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
            # Left joystick - both naming conventions
            'P1_JOYSTICK_UP': 'LS↑',
            'P1_JOYSTICK_DOWN': 'LS↓',
            'P1_JOYSTICK_LEFT': 'LS←',
            'P1_JOYSTICK_RIGHT': 'LS→',
            'P1_JOYSTICKLEFT_UP': 'LS↑',     # Add this
            'P1_JOYSTICKLEFT_DOWN': 'LS↓',   # Add this 
            'P1_JOYSTICKLEFT_LEFT': 'LS←',   # Add this
            'P1_JOYSTICKLEFT_RIGHT': 'LS→',  # Add this
            
            # Right joystick mappings
            'P1_JOYSTICKRIGHT_UP': 'RS↑',
            'P1_JOYSTICKRIGHT_DOWN': 'RS↓',
            'P1_JOYSTICKRIGHT_LEFT': 'RS←',
            'P1_JOYSTICKRIGHT_RIGHT': 'RS→',
        }
        
        # Add specialized MAME control prefixes
        specialized_prefixes = {
            # Rotary controls
            'P1_DIAL': 'DIAL',
            'P1_DIAL_V': 'DIAL↑↓',
            'P1_PADDLE': 'PDL',
            
            # Trackball controls
            'P1_TRACKBALL_X': 'TRK←→',
            'P1_TRACKBALL_Y': 'TRK↑↓',
            
            # Mouse controls
            'P1_MOUSE_X': 'MSE←→',
            'P1_MOUSE_Y': 'MSE↑↓',
            
            # Light gun controls
            'P1_LIGHTGUN_X': 'GUN←→',
            'P1_LIGHTGUN_Y': 'GUN↑↓',
            
            # Analog stick controls
            'P1_AD_STICK_X': 'ASX',
            'P1_AD_STICK_Y': 'ASY',
            'P1_AD_STICK_Z': 'ASZ',
            
            # Pedal inputs
            'P1_PEDAL': 'PED1',
            'P1_PEDAL2': 'PED2',
            
            # Positional control
            'P1_POSITIONAL': 'POS',
            
            # Gambling controls
            'P1_GAMBLE_HIGH': 'HIGH',
            'P1_GAMBLE_LOW': 'LOW',
        }
        
        # Combine standard and specialized prefixes
        all_prefixes = {**standard_prefixes, **specialized_prefixes}
        
        # Return the prefix if found, otherwise empty string
        return all_prefixes.get(control_name, "")
    
    def get_current_mapping(self):
        """Get the mapping value for the current ROM"""
        try:
            # Check if game_data has mapping information
            if hasattr(self, 'game_data') and self.game_data:
                # Method 1: Check for mappings directly at root level (cache format)
                if 'mappings' in self.game_data:
                    mappings = self.game_data['mappings']
                    if mappings:
                        # Return first mapping if it's a list, or the mapping itself if it's a string
                        if isinstance(mappings, list) and len(mappings) > 0:
                            return mappings[0]
                        elif isinstance(mappings, str):
                            return mappings
                
                # Method 2: Check if game_data is nested with ROM name key (gamedata.json format)
                elif self.rom_name in self.game_data:
                    rom_data = self.game_data[self.rom_name]
                    if isinstance(rom_data, dict) and 'mappings' in rom_data:
                        mappings = rom_data['mappings']
                        if mappings:
                            if isinstance(mappings, list) and len(mappings) > 0:
                                return mappings[0]
                            elif isinstance(mappings, str):
                                return mappings
                
                # Method 3: Search through all values for mappings key
                else:
                    for key, value in self.game_data.items():
                        if isinstance(value, dict) and 'mappings' in value:
                            mappings = value['mappings']
                            if mappings:
                                if isinstance(mappings, list) and len(mappings) > 0:
                                    return mappings[0]
                                elif isinstance(mappings, str):
                                    return mappings
            
            print(f"No mapping found for {self.rom_name}")
            return None
                    
        except Exception as e:
            print(f"Error getting mapping for {self.rom_name}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def has_mapping(self):
        """Check if the current ROM has a mapping value"""
        mapping = self.get_current_mapping()
        return mapping is not None and mapping.strip() != ""

    def save_mapping_positions(self):
        """Save current control positions for the current mapping"""
        try:
            # Get the mapping for this ROM
            mapping = self.get_current_mapping()
            if not mapping:
                self.show_toast_notification("No mapping available for this ROM")
                return False
            
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Define the mapping positions file
            mapping_positions_file = os.path.join(self.settings_dir, f"{mapping}_positions.json")
            
            # Load existing mapping positions to preserve them
            existing_positions = {}
            if os.path.exists(mapping_positions_file):
                try:
                    with open(mapping_positions_file, 'r') as f:
                        existing_positions = json.load(f)
                    print(f"Loaded {len(existing_positions)} existing mapping positions to preserve")
                except Exception as e:
                    print(f"Error loading existing mapping positions: {e}")
            
            # Get positions for current controls
            y_offset = self.text_settings.get("y_offset", -40)
            new_positions = {}
            
            for control_name, control_data in self.control_labels.items():
                label_pos = control_data['label'].pos()
                
                # Store normalized position (without y-offset)
                new_positions[control_name] = [label_pos.x(), label_pos.y() - y_offset]
            
            # Merge existing and new positions (new ones override existing ones)
            merged_positions = {**existing_positions, **new_positions}
            
            # Save merged positions to file
            with open(mapping_positions_file, 'w') as f:
                json.dump(merged_positions, f)
            
            print(f"Saved {len(new_positions)} new positions and preserved {len(existing_positions) - len(set(existing_positions.keys()) & set(new_positions.keys()))} existing positions for mapping '{mapping}' to: {mapping_positions_file}")
            
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
            
            # Show success notification
            self.show_toast_notification(f"Positions saved for mapping: {mapping}")
            
            print(f"All settings saved for mapping '{mapping}'")
            return True
                
        except Exception as e:
            print(f"Error saving mapping positions: {e}")
            import traceback
            traceback.print_exc()
            
            # Show error message
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save mapping positions: {str(e)}"
            )
            return False

    def load_saved_positions_with_mapping_support(self):
        """Enhanced load_saved_positions that includes mapping-based positions with proper priority"""
        positions = {}
        rom_positions = {}
        mapping_positions = {}
        global_positions = {}
        
        try:
            print("\n=== Loading saved positions with mapping support ===")
            
            # Define file paths
            rom_positions_file = os.path.join(self.settings_dir, f"{self.rom_name}_positions.json")
            global_positions_file = os.path.join(self.settings_dir, "global_positions.json")
            
            # Get mapping-specific file if mapping exists
            mapping = self.get_current_mapping()
            mapping_positions_file = None
            if mapping:
                mapping_positions_file = os.path.join(self.settings_dir, f"{mapping}_positions.json")
                print(f"Looking for mapping positions at: {mapping_positions_file}")
            
            # 1. Load global positions (lowest priority)
            if os.path.exists(global_positions_file):
                with open(global_positions_file, 'r') as f:
                    global_positions = json.load(f)
                    print(f"Loaded {len(global_positions)} global positions")
            else:
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
                        
                        print(f"Migrated global positions from {legacy_path}")
                        break
            
            # 2. Load mapping positions (medium priority)
            if mapping_positions_file and os.path.exists(mapping_positions_file):
                with open(mapping_positions_file, 'r') as f:
                    mapping_positions = json.load(f)
                    print(f"Loaded {len(mapping_positions)} mapping positions for '{mapping}'")
            
            # 3. Load ROM-specific positions (highest priority)
            if os.path.exists(rom_positions_file):
                with open(rom_positions_file, 'r') as f:
                    rom_positions = json.load(f)
                    print(f"Loaded {len(rom_positions)} ROM-specific positions")
            else:
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
                    
                    print(f"Migrated ROM-specific positions from {legacy_rom_path}")
            
            # Apply positions in priority order: global → mapping → ROM-specific
            positions = global_positions.copy()
            positions.update(mapping_positions)  # Mapping positions override global
            positions.update(rom_positions)      # ROM positions override both
            
            print(f"Final position priority: {len(global_positions)} global, {len(mapping_positions)} mapping, {len(rom_positions)} ROM-specific")
            print(f"Total combined positions: {len(positions)}")
            
            # Debug which positions came from where
            if mapping and mapping_positions:
                print(f"Using mapping '{mapping}' positions for shared layout")
            
        except Exception as e:
            print(f"Error loading saved positions with mapping support: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"Returning {len(positions)} total positions")
        return positions
    
    # 5. LOAD SAVED POSITIONS (happening 3 times)
    # Fix: Cache the results
    def load_saved_positions(self):
        """Load saved positions with caching"""
        # Return cached result if available
        if hasattr(self, '_cached_positions'):
            print("Using cached positions")
            return self._cached_positions
        
        print("\n=== Loading saved positions (first time) ===")
        """Enhanced load_saved_positions that includes mapping-based positions with proper priority"""
        positions = {}
        rom_positions = {}
        mapping_positions = {}
        global_positions = {}
        
        try:
            print("\n=== Loading saved positions with mapping support ===")
            
            # Define file paths
            rom_positions_file = os.path.join(self.settings_dir, f"{self.rom_name}_positions.json")
            global_positions_file = os.path.join(self.settings_dir, "global_positions.json")
            
            # Get mapping-specific file if mapping exists
            mapping = self.get_current_mapping()
            mapping_positions_file = None
            if mapping:
                mapping_positions_file = os.path.join(self.settings_dir, f"{mapping}_positions.json")
                print(f"Looking for mapping positions at: {mapping_positions_file}")
            
            # 1. Load global positions (lowest priority)
            if os.path.exists(global_positions_file):
                with open(global_positions_file, 'r') as f:
                    global_positions = json.load(f)
                    print(f"Loaded {len(global_positions)} global positions")
            else:
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
                        
                        print(f"Migrated global positions from {legacy_path}")
                        break
            
            # 2. Load mapping positions (medium priority)
            if mapping_positions_file and os.path.exists(mapping_positions_file):
                with open(mapping_positions_file, 'r') as f:
                    mapping_positions = json.load(f)
                    print(f"Loaded {len(mapping_positions)} mapping positions for '{mapping}'")
            
            # 3. Load ROM-specific positions (highest priority)
            if os.path.exists(rom_positions_file):
                with open(rom_positions_file, 'r') as f:
                    rom_positions = json.load(f)
                    print(f"Loaded {len(rom_positions)} ROM-specific positions")
            else:
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
                    
                    print(f"Migrated ROM-specific positions from {legacy_rom_path}")
            
            # Apply positions in priority order: global → mapping → ROM-specific
            positions = global_positions.copy()
            positions.update(mapping_positions)  # Mapping positions override global
            positions.update(rom_positions)      # ROM positions override both
            
            print(f"Final position priority: {len(global_positions)} global, {len(mapping_positions)} mapping, {len(rom_positions)} ROM-specific")
            print(f"Total combined positions: {len(positions)}")
            
            # Debug which positions came from where
            if mapping and mapping_positions:
                print(f"Using mapping '{mapping}' positions for shared layout")
            
        except Exception as e:
            print(f"Error loading saved positions with mapping support: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"Returning {len(positions)} total positions")
        self._cached_positions = positions
        return positions
    
    # Replace your existing toggle_texts method with this one
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
        
        # CRITICAL: Enforce correct layer order 
        self.enforce_layer_order()
        
        # Force update to ensure proper rendering
        if hasattr(self, 'canvas'):
            self.canvas.update()
    
    def toggle_joystick_controls(self):
        """Toggle visibility of all directional controls with immediate response and proper saving"""
        self.joystick_visible = not self.joystick_visible
        
        # Update button text
        if hasattr(self, 'joystick_button'):
            self.joystick_button.setText("Show Directional" if not self.joystick_visible else "Hide Directional")
        
        # Apply the joystick visibility immediately
        self.apply_joystick_visibility()
        
        # CRITICAL: Enforce correct layer order
        self.enforce_layer_order()
        
        # Save the setting - make sure this actually saves joystick_visible
        saved = self.save_bezel_settings(is_global=True)
        if saved:
            print(f"Joystick visibility saved: {self.joystick_visible}")
        else:
            print("ERROR: Failed to save joystick visibility setting")
        
        # Show toast notification
        status = "hidden" if not self.joystick_visible else "visible"
        self.show_toast_notification(f"Directional controls {status}")
        
        print(f"Directional controls visibility set to {self.joystick_visible}")
    
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
        
    def save_positions(self, is_global=False):
        """Save current control positions to file while preserving existing positions"""
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.settings_dir, exist_ok=True)
            
            # Determine the file paths - always save in settings directory
            positions_filepath = os.path.join(self.settings_dir, 
                                            "global_positions.json" if is_global else f"{self.rom_name}_positions.json")
            
            # Load existing positions to preserve them
            existing_positions = {}
            if os.path.exists(positions_filepath):
                try:
                    with open(positions_filepath, 'r') as f:
                        existing_positions = json.load(f)
                    print(f"Loaded {len(existing_positions)} existing positions to preserve")
                except Exception as e:
                    print(f"Error loading existing positions: {e}")
            
            if hasattr(self, 'no_buttons_label') and self.no_buttons_label:
                self.save_no_buttons_position()
            # Get positions for current controls
            y_offset = self.text_settings.get("y_offset", -40)
            new_positions = {}
            
            for control_name, control_data in self.control_labels.items():
                label_pos = control_data['label'].pos()
                
                # Store normalized position (without y-offset)
                new_positions[control_name] = [label_pos.x(), label_pos.y() - y_offset]
            
            # Merge existing and new positions (new ones override existing ones)
            merged_positions = {**existing_positions, **new_positions}
            
            # Save merged positions to file
            with open(positions_filepath, 'w') as f:
                json.dump(merged_positions, f)
            
            print(f"Saved {len(new_positions)} new positions and preserved {len(existing_positions) - len(set(existing_positions.keys()) & set(new_positions.keys()))} existing positions to: {positions_filepath}")
            
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
            
            # Show toast notification with appropriate message
            if is_global:
                self.show_toast_notification("Positions saved for all games")
            else:
                self.show_toast_notification(f"Positions saved for {self.rom_name}")
                
            return True
                
        except Exception as e:
            print(f"Error saving settings: {e}")
            import traceback
            traceback.print_exc()
            
            # Keep error message as a dialog
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
        
        # NEW: Also check if gradient settings changed
        old_prefix_gradient = self.text_settings.get("use_prefix_gradient", False)
        new_prefix_gradient = settings.get("use_prefix_gradient", False)
        old_action_gradient = self.text_settings.get("use_action_gradient", False)
        new_action_gradient = settings.get("use_action_gradient", False)
        gradient_changed = (old_prefix_gradient != new_prefix_gradient or 
                            old_action_gradient != new_action_gradient)
        
        # Debug output for gradient changes
        print(f"Gradient settings check - Old prefix: {old_prefix_gradient}, New prefix: {new_prefix_gradient}")
        print(f"Gradient settings check - Old action: {old_action_gradient}, New action: {new_action_gradient}")
        print(f"Gradient changed: {gradient_changed}")
        
        if uppercase_changed and new_uppercase == False:
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
        
        # Force immediate recreation of control labels when uppercase or gradient settings change
        if uppercase_changed or gradient_changed:
            print(f"Need to recreate labels - Uppercase changed: {uppercase_changed}, Gradient changed: {gradient_changed}")
            # This approach ensures both case and gradient changes apply immediately
            self.recreate_control_labels_with_case()
        else:
            # Normal update for other changes
            self.apply_text_settings()
        
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

    def init_directional_mode(self):
        """Initialize the directional mode from saved settings"""
        # Load current settings
        joystick_visible = getattr(self, 'joystick_visible', True)
        hide_specialized = getattr(self, 'hide_specialized_with_directional', False)
        
        # Determine current mode based on settings
        if joystick_visible:
            self.directional_mode = "show_all"  # Everything visible
        elif hide_specialized:
            self.directional_mode = "hide_all"  # Both standard and specialized hidden
        else:
            self.directional_mode = "hide_standard"  # Only standard hidden
        
        print(f"INIT: Directional mode = {self.directional_mode}")

    def cycle_directional_mode(self):
        """Cycle through FOUR directional visibility modes with immediate response"""
        # Define the 4-mode cycle: show_all -> hide_standard -> hide_specialized -> hide_all -> show_all
        mode_cycle = {
            "show_all": "hide_standard",           # Show All -> Hide Standard Directional
            "hide_standard": "hide_specialized",   # Hide Standard -> Hide Specialized Only  
            "hide_specialized": "hide_all",        # Hide Specialized -> Hide All Directional
            "hide_all": "show_all"                 # Hide All -> Show All
        }
        
        # Get current mode or default
        current_mode = getattr(self, 'directional_mode', 'show_all')
        
        # Cycle to next mode
        self.directional_mode = mode_cycle.get(current_mode, 'show_all')
        
        print(f"CYCLE: {current_mode} -> {self.directional_mode}")
        
        # Apply the new mode immediately
        self.apply_directional_mode()
        
        # Update button text
        self.update_directional_mode_button_text()
        
        # Save settings
        self.save_directional_mode_settings()
        
        # Show notification
        mode_names = {
            "show_all": "All directional controls visible",
            "hide_standard": "Standard directional controls hidden",
            "hide_specialized": "Specialized directional controls hidden", 
            "hide_all": "All directional controls hidden"
        }
        self.show_toast_notification(mode_names[self.directional_mode])

    def apply_directional_mode(self):
        """Apply the current directional mode to all controls (no notification update)"""
        # Set internal flags based on mode
        if self.directional_mode == "show_all":
            self.joystick_visible = True
            self.hide_specialized_with_directional = False
        elif self.directional_mode == "hide_standard":
            self.joystick_visible = False
            self.hide_specialized_with_directional = False
        elif self.directional_mode == "hide_specialized":
            self.joystick_visible = True  # Keep standard visible
            self.hide_specialized_with_directional = True  # Hide specialized
        elif self.directional_mode == "hide_all":
            self.joystick_visible = False
            self.hide_specialized_with_directional = True
        
        print(f"APPLY MODE: joystick_visible={self.joystick_visible}, hide_specialized={self.hide_specialized_with_directional}")
        
        # Apply visibility to all controls
        controls_updated = 0
        
        # Get the auto-show directionals setting
        auto_show_directionals = getattr(self, 'auto_show_directionals_for_directional_only', True)
        is_directional_only = getattr(self, 'is_directional_only_game', False)
        
        for control_name, control_data in self.control_labels.items():
            # SKIP the No Buttons notification entirely during directional mode changes
            if control_name == "NO_BUTTONS_NOTIFICATION":
                continue
                
            if 'label' not in control_data or not control_data['label']:
                continue
            
            # Define control types
            standard_directional_types = [
                "JOYSTICK", "JOYSTICKLEFT", "JOYSTICKRIGHT", "DPAD"
            ]
            
            specialized_directional_types = [
                "DIAL", "PADDLE", "TRACKBALL", "MOUSE", "LIGHTGUN", 
                "AD_STICK", "PEDAL", "POSITIONAL"
            ]
            
            is_standard_directional = any(control_type in control_name for control_type in standard_directional_types)
            is_specialized_directional = any(control_type in control_name for control_type in specialized_directional_types)
            
            # Determine visibility based on mode and control type
            is_visible = self.texts_visible  # Default for non-directional controls
            
            if is_standard_directional:
                # Standard directional: affected by hide_standard and hide_all modes
                if self.directional_mode in ["hide_standard", "hide_all"]:
                    if is_directional_only and auto_show_directionals:
                        is_visible = self.texts_visible  # Auto-show override
                    else:
                        is_visible = False
                else:  # show_all or hide_specialized
                    is_visible = self.texts_visible
            
            elif is_specialized_directional:
                # Specialized directional: affected by hide_specialized and hide_all modes
                if self.directional_mode in ["hide_specialized", "hide_all"]:
                    if is_directional_only and auto_show_directionals:
                        is_visible = self.texts_visible  # Auto-show override
                    else:
                        is_visible = False
                else:  # show_all or hide_standard
                    is_visible = self.texts_visible
            
            # Apply visibility change
            if control_data['label'].isVisible() != is_visible:
                control_data['label'].setVisible(is_visible)
                # If we're making a control visible, ensure it's on top
                if is_visible:
                    control_data['label'].raise_()
                controls_updated += 1
                control_type = "specialized" if is_specialized_directional else "standard"
                print(f"Updated {control_type} {control_name} visibility to {is_visible}")
        
        # Force immediate canvas update and layer enforcement
        if hasattr(self, 'canvas'):
            self.canvas.update()
            self.canvas.repaint()
        
        # CRITICAL: Enforce layer order after visibility changes
        self.enforce_layer_order()
        
        # REMOVED: No longer calling update_no_buttons_visibility here
        # The notification will be handled separately based on view state changes
        
        print(f"Applied mode '{self.directional_mode}' to {controls_updated} controls")

    def update_directional_mode_button_text(self):
        """Update button text to show what will happen NEXT (now with 4 modes)"""
        if not hasattr(self, 'directional_mode_button'):
            return
        
        # Button shows what will happen when clicked (next state)
        mode = getattr(self, 'directional_mode', 'show_all')
        
        if mode == "show_all":
            self.directional_mode_button.setText("Hide Standard")
            self.directional_mode_button.setToolTip(
                "Currently: All directional controls visible\n"
                "Click to hide standard directional controls (joystick, d-pad)"
            )
        elif mode == "hide_standard":
            self.directional_mode_button.setText("Hide Specialized")
            self.directional_mode_button.setToolTip(
                "Currently: Standard directional controls hidden\n"
                "Click to hide specialized controls (trackball, dial, etc.)"
            )
        elif mode == "hide_specialized":
            self.directional_mode_button.setText("Hide All Directional")
            self.directional_mode_button.setToolTip(
                "Currently: Specialized directional controls hidden\n"
                "Click to hide ALL directional controls"
            )
        elif mode == "hide_all":
            self.directional_mode_button.setText("Show All")
            self.directional_mode_button.setToolTip(
                "Currently: All directional controls hidden\n"
                "Click to show all directional controls"
            )
        
        print(f"BUTTON: Updated button text for mode '{mode}' -> '{self.directional_mode_button.text()}'")

    # FIX: Update save_directional_mode_settings to preserve bezel_visible
    def save_directional_mode_settings(self):
        """Save directional mode settings without affecting bezel visibility"""
        try:
            # Load existing settings first
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            existing_settings = {}
            
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    existing_settings = json.load(f)
            
            # Update ONLY directional mode settings, preserve bezel_visible
            existing_settings['joystick_visible'] = getattr(self, 'joystick_visible', True)
            existing_settings['hide_specialized_with_directional'] = getattr(self, 'hide_specialized_with_directional', False)
            existing_settings['directional_mode'] = getattr(self, 'directional_mode', 'show_all')
            existing_settings['auto_show_directionals_for_directional_only'] = getattr(self, 'auto_show_directionals_for_directional_only', True)
            
            # DO NOT touch bezel_visible here - let it keep its existing value
            
            # Save back to file
            os.makedirs(self.settings_dir, exist_ok=True)
            with open(settings_file, 'w') as f:
                json.dump(existing_settings, f)
            
            print(f"SAVE: Saved directional mode '{self.directional_mode}' settings")
            print(f"SAVE: joystick_visible={self.joystick_visible}, hide_specialized={getattr(self, 'hide_specialized_with_directional', False)}")
            print(f"SAVE: Preserved existing bezel_visible setting")
            
        except Exception as e:
            print(f"Error saving directional mode settings: {e}")
    
    def create_control_labels(self, clean_mode=False):
        """Create control labels with directional mode support and batch optimization"""
        if not self.game_data or 'players' not in self.game_data:
            return
                
        print("=== BATCH CREATING CONTROL LABELS ===")
        
        # Pre-calculate EVERYTHING once at the top
        if not hasattr(self, 'current_font') or self.current_font is None:
            print("Font not initialized before creating labels - forcing font loading")
            self.load_and_register_fonts()
        
        # Cache all the expensive lookups
        saved_positions = self.load_saved_positions() if hasattr(self, 'load_saved_positions') else {}
        current_font = self.current_font
        directional_mode = getattr(self, 'directional_mode', 'show_all')
        y_offset = self.text_settings.get("y_offset", -40)
        show_button_prefix = self.text_settings.get("show_button_prefix", True)
        use_uppercase = self.text_settings.get("use_uppercase", False)
        use_prefix_gradient = self.text_settings.get("use_prefix_gradient", False)
        use_action_gradient = self.text_settings.get("use_action_gradient", False)
        
        # Count controls first for better progress tracking
        total_controls = 0
        for player in self.game_data.get('players', []):
            if player['number'] == 1:
                total_controls += len(player.get('labels', []))
        
        print(f"Batch processing {total_controls} controls with pre-calculated settings")
        
        # Process controls with batch optimization
        control_count = 0
        for player in self.game_data.get('players', []):
            if player['number'] != 1:  # Only show Player 1 controls
                continue
                                
            print(f"\n*** Batch processing controls for {self.rom_name} ***")
            
            # Create all controls for this player in one batch
            for control in player.get('labels', []):
                control_count += 1
                control_name = control['name']
                action_text = control['value']
                
                # Only print debug for custom controls to reduce log spam
                if control.get('is_custom', False) or control_name == "P1_BUTTON3":
                    # Only print debug for problematic controls
                    if control_count <= 2 or control.get('is_custom', False):
                        print(f"Control: {control_name}, Value: {action_text}, Mapping: {control.get('mapping', 'NONE')}")
                
                # Special debug for P1_BUTTON3 (or any custom controls)
                if control_name == "P1_BUTTON3" or control.get('is_custom', False):
                    print(f"*** DEBUGGING CUSTOM CONTROL: {control_name} ***")
                    print(f"Action: {action_text}")
                    print(f"Mapping: {control.get('mapping', 'NONE')}")
                    print(f"Is Custom: {control.get('is_custom', False)}")
                    print(f"Mapping source: {control.get('mapping_source', 'UNKNOWN')}")
                    print(f"CFG Mapping: {control.get('cfg_mapping', False)}")
                    print(f"Input Mode: {control.get('input_mode', 'UNKNOWN')}")
                    print(f"Target Button: {control.get('target_button', 'UNKNOWN')}")
                    
            # Create a label for each control
            grid_x, grid_y = 0, 0
            for control in player.get('labels', []):
                control_name = control['name']
                action_text = control['value']
                
                # Get button prefix based on control type with enhanced debugging
                button_prefix = ""
                if 'mapping' in control and control['mapping'] and control['mapping'] != "NONE":
                    # Try to get prefix from ANY mapping (custom OR default)
                    button_prefix = self.get_button_prefix_from_mapping(control['mapping'])
                    
                    # Enhanced debugging for custom controls
                    if control_name == "P1_BUTTON3" or control.get('is_custom', False):
                        print(f"Generated prefix from mapping '{control['mapping']}': '{button_prefix}'")
                    
                    # If no prefix found and we have a DirectInput mapping, try to extract it
                    if not button_prefix and 'DINPUT_' in control['mapping']:
                        button_num = control['mapping'].replace('DINPUT_1_BUTTON', '')
                        if button_num.isdigit():
                            button_prefix = f"B{button_num}"
                            if control_name == "P1_BUTTON3":
                                print(f"Fallback DINPUT prefix: '{button_prefix}'")
                else:
                    # Use fallback if no mapping exists OR mapping is "NONE"
                    if hasattr(self, 'get_button_prefix'):
                        button_prefix = self.get_button_prefix(control_name)
                        if control_name == "P1_BUTTON3":
                            print(f"Fallback prefix from control name: '{button_prefix}'")
                
                # Final debug output for custom controls
                if control_name == "P1_BUTTON3" or control.get('is_custom', False):
                    print(f"FINAL PREFIX for {control_name}: '{button_prefix}'")
                    print("=== END CUSTOM CONTROL DEBUG ===\n")
                
                # Determine visibility based on directional mode and control type
                is_visible = True
                
                # Define control types
                standard_directional_types = [
                    "JOYSTICK", "JOYSTICKLEFT", "JOYSTICKRIGHT", "DPAD"
                ]
                
                specialized_directional_types = [
                    "DIAL", "PADDLE", "TRACKBALL", "MOUSE", "LIGHTGUN", 
                    "AD_STICK", "PEDAL", "POSITIONAL"
                ]
                
                is_standard_directional = any(control_type in control_name for control_type in standard_directional_types)
                is_specialized_directional = any(control_type in control_name for control_type in specialized_directional_types)
                
                # Apply visibility based on current directional mode
                directional_mode = getattr(self, 'directional_mode', 'show_all')
                
                if is_standard_directional:
                    # Standard directional: affected by hide_standard and hide_all modes
                    if directional_mode in ["hide_standard", "hide_all"]:
                        is_visible = self.texts_visible and self.should_show_directional
                        print(f"CREATE: Standard directional {control_name}, mode={directional_mode}, visible={is_visible}")
                    else:  # show_all
                        is_visible = self.texts_visible
                        print(f"CREATE: Standard directional {control_name}, mode={directional_mode}, visible={is_visible}")
                elif is_specialized_directional:
                    # Specialized directional: only affected in hide_all mode
                    if directional_mode == "hide_all":
                        is_visible = self.texts_visible and self.should_show_directional
                        print(f"CREATE: Specialized {control_name}, mode={directional_mode}, visible={is_visible}")
                    else:  # show_all or hide_standard
                        is_visible = self.texts_visible
                        print(f"CREATE: Specialized {control_name}, mode={directional_mode}, visible={is_visible}")
                # else: regular buttons stay visible (is_visible remains True)
                
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
                    # OPTIMIZED: Use pre-calculated font (much faster)
                    label.setFont(current_font)
                    if control_count <= 3:  # Only log first few controls
                        print(f"Applied current_font to {control_name}: {current_font.family()}")
                    
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
                    
                    # Apply visibility setting based on directional mode
                    label.setVisible(is_visible)
                    
                    # First, let the label auto-size based on content
                    label.adjustSize()

                    # More aggressive approach to prevent text truncation
                    font_metrics = QFontMetrics(label.font())
                    text_width = font_metrics.horizontalAdvance(display_text)

                    # Get font family to check if it's a custom font
                    font_family = label.font().family()
                    is_custom_font = font_family not in ["Arial", "Verdana", "Tahoma", "Times New Roman", 
                                                    "Courier New", "Segoe UI", "Calibri", "Georgia", 
                                                    "Impact", "System"]

                    # Determine base padding based on font type
                    base_padding = 50 if is_custom_font else 30

                    # Add additional padding for longer text
                    if len(display_text) > 15:
                        base_padding += 20
                    if len(display_text) > 20:
                        base_padding += 30
                        
                    # Special case for Select button or text containing select
                    if "SELECT" in control_name or "Select" in action_text:
                        base_padding += 25
                        
                    # Calculate final width with generous padding
                    label_width = text_width + base_padding
                    label_height = label.height()

                    # Debug output for problematic labels
                    if "SELECT" in control_name or len(display_text) > 15:
                        print(f"Setting width for {control_name}: text={text_width}px, padding={base_padding}px, final={label_width}px")

                    # Resize with the calculated width
                    label.resize(label_width, label_height)
                    
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
        print(f"=== BATCH CREATION COMPLETE ===")
        print(f"Created {len(self.control_labels)} control labels in optimized batch mode")
        print(f"Directional mode: {directional_mode}, Font: {current_font.family()}")

    def get_button_prefix_from_mapping(self, mapping):
        """Get the button prefix based on mapping string, including multiple button assignments and new MAME codes"""
        # Standard XINPUT mappings
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
            "XINPUT_1_DPAD_RIGHT": "D→",
            "XINPUT_1_START": "START",
            "XINPUT_1_SELECT": "BACK",

            # ADD THESE FOR DUAL-STICK GAMES LIKE SMASH T.V.:
            "XINPUT_1_LEFTY_POS": "LS↓",      # Left stick down
            "XINPUT_1_LEFTY_NEG": "LS↑",      # Left stick up  
            "XINPUT_1_LEFTX_POS": "LS→",      # Left stick right
            "XINPUT_1_LEFTX_NEG": "LS←",      # Left stick left
            "XINPUT_1_RIGHTY_POS": "RS↓",     # Right stick down
            "XINPUT_1_RIGHTY_NEG": "RS↑",     # Right stick up
            "XINPUT_1_RIGHTX_POS": "RS→",     # Right stick right
            "XINPUT_1_RIGHTX_NEG": "RS←",     # Right stick left
        }
        
        # Add DirectInput mappings
        dinput_to_prefix = {
            "DINPUT_1_BUTTON0": "B0",
            "DINPUT_1_BUTTON1": "B1",
            "DINPUT_1_BUTTON2": "B2",
            "DINPUT_1_BUTTON3": "B3",
            "DINPUT_1_BUTTON4": "B4",
            "DINPUT_1_BUTTON5": "B5",
            "DINPUT_1_BUTTON6": "B6",
            "DINPUT_1_BUTTON7": "B7",
            "DINPUT_1_BUTTON8": "B8",
            "DINPUT_1_BUTTON9": "B9",
            "DINPUT_1_POV_UP": "POV↑",
            "DINPUT_1_POV_DOWN": "POV↓",
            "DINPUT_1_POV_LEFT": "POV←",
            "DINPUT_1_POV_RIGHT": "POV→",
            "DINPUT_1_XAXIS_NEG": "X←",
            "DINPUT_1_XAXIS_POS": "X→",
            "DINPUT_1_YAXIS_NEG": "Y↑",
            "DINPUT_1_YAXIS_POS": "Y↓",
            "DINPUT_1_ZAXIS": "Z-AXIS",      # DirectInput Z-axis
            "DINPUT_1_RZAXIS": "RZ-AXIS",    # DirectInput RZ-axis
        }
        
        # MAME specialized control mappings
        mame_to_prefix = {
            # Analog mappings
            "JOYCODE_1_XAXIS": "ASX",
            "JOYCODE_1_YAXIS": "ASY",
            "JOYCODE_1_ZAXIS": "ASZ",
            
            # Mouse mappings
            "MOUSECODE_1_XAXIS": "MSE←→",
            "MOUSECODE_1_YAXIS": "MSE↑↓",
            
            # Trackball mappings
            "TRACKCODE_1_XAXIS": "TRK←→",
            "TRACKCODE_1_YAXIS": "TRK↑↓",
            
            # Lightgun mappings  
            "GUNCODE_1_XAXIS": "GUN←→",
            "GUNCODE_1_YAXIS": "GUN↑↓",
            
            # Dial/Paddle mappings
            "DIALCODE_1_XAXIS": "DIAL",
            "DIALCODE_1_YAXIS": "DIAL↕",
            "PADDLE_1_X": "PDL",
            
            # Pedal mappings
            "PEDALCODE_1": "PED1",
            "PEDALCODE_2": "PED2",
            
            # Positional
            "POSITIONAL_1": "POS",
            
            # Additional dial-type control codes
            "MOUSECODE_1_XAXIS_POS_FAST": "MSE→+",
            "MOUSECODE_1_XAXIS_NEG_FAST": "MSE←+",
            "MOUSECODE_1_YAXIS_POS_FAST": "MSE↓+",
            "MOUSECODE_1_YAXIS_NEG_FAST": "MSE↑+",
            "TRACKCODE_1_XAXIS_POS_FAST": "TRK→+",
            "TRACKCODE_1_XAXIS_NEG_FAST": "TRK←+",
            "TRACKCODE_1_YAXIS_POS_FAST": "TRK↓+",
            "TRACKCODE_1_YAXIS_NEG_FAST": "TRK↑+"
        }
        
        # Add directional joystick mappings (including both old and new formats)
        directional_to_prefix = {
            # Left stick mappings - STANDARD FORMAT
            "JOYCODE_1_XAXIS_RIGHT_SWITCH": "→",
            "JOYCODE_1_XAXIS_LEFT_SWITCH": "←",
            "JOYCODE_1_YAXIS_UP_SWITCH": "↑",
            "JOYCODE_1_YAXIS_DOWN_SWITCH": "↓",
            
            # Left stick mappings - NEW SLIDER2 FORMAT
            "JOYCODE_1_SLIDER2_LEFT_SWITCH": "←",
            "JOYCODE_1_SLIDER2_RIGHT_SWITCH": "→",
            "JOYCODE_1_SLIDER2_UP_SWITCH": "↑",
            "JOYCODE_1_SLIDER2_DOWN_SWITCH": "↓",
            
            # RIGHT STICK MAPPINGS
            "JOYCODE_1_RXAXIS_POS_SWITCH": "RS→",   # Right stick right
            "JOYCODE_1_RXAXIS_NEG_SWITCH": "RS←",   # Right stick left  
            "JOYCODE_1_RYAXIS_NEG_SWITCH": "RS↑",   # Right stick up
            "JOYCODE_1_RYAXIS_POS_SWITCH": "RS↓",   # Right stick down
            
            # D-pad mappings - OLD FORMAT (for backward compatibility)
            "JOYCODE_1_DPADUP": "D↑",
            "JOYCODE_1_DPADDOWN": "D↓",
            "JOYCODE_1_DPADLEFT": "D←",
            "JOYCODE_1_DPADRIGHT": "D→",
            
            # D-pad mappings - NEW FORMAT (HAT controls)
            "JOYCODE_1_HAT1UP": "D↑",
            "JOYCODE_1_HAT1DOWN": "D↓",
            "JOYCODE_1_HAT1LEFT": "D←",
            "JOYCODE_1_HAT1RIGHT": "D→",
        }

        # Add trigger/analog axis mappings (including both old and new formats)
        trigger_to_prefix = {
            # OLD FORMAT - for backward compatibility
            "JOYCODE_1_ZAXIS_NEG_SWITCH": "LT",
            "JOYCODE_1_ZAXIS_POS_SWITCH": "LT+",
            "JOYCODE_1_RZAXIS_NEG_SWITCH": "RT",
            "JOYCODE_1_RZAXIS_POS_SWITCH": "RT+",
            "JOYCODE_1_ZAXIS": "LT",         # Left Trigger full axis
            "JOYCODE_1_RZAXIS": "RT",        # Right Trigger full axis
            
            # NEW FORMAT - SLIDER controls
            "JOYCODE_1_SLIDER2_NEG_SWITCH": "LT",
            "JOYCODE_1_SLIDER2_POS_SWITCH": "LT+",
            
            # Other axis mappings
            "JOYCODE_1_XAXIS": "LS←→",       # Left Stick X
            "JOYCODE_1_YAXIS": "LS↑↓",       # Left Stick Y
            "JOYCODE_1_RXAXIS": "RS←→",      # Right Stick X
            "JOYCODE_1_RYAXIS": "RS↑↓" 
        }

        # Keyboard-specific mappings
        keyboard_to_prefix = {
            # Arrow keys
            "KEYCODE_UP": "↑",
            "KEYCODE_DOWN": "↓", 
            "KEYCODE_LEFT": "←",
            "KEYCODE_RIGHT": "→",
            
            # Common action keys
            "KEYCODE_Z": "Z",
            "KEYCODE_X": "X",
            "KEYCODE_C": "C",
            "KEYCODE_A": "A",
            "KEYCODE_S": "S",
            "KEYCODE_D": "D",
            "KEYCODE_Q": "Q",
            "KEYCODE_W": "W",
            "KEYCODE_E": "E",
            "KEYCODE_R": "R",
            
            # Numeric keys
            "KEYCODE_1": "1",
            "KEYCODE_2": "2",
            "KEYCODE_3": "3",
            "KEYCODE_4": "4",
            "KEYCODE_5": "5",
            
            # Function/special keys
            "KEYCODE_SPACE": "SPC",
            "KEYCODE_ENTER": "↵",
            "KEYCODE_LSHIFT": "⇧",
            "KEYCODE_RSHIFT": "⇧",
            "KEYCODE_LCONTROL": "Ctrl",
            "KEYCODE_RCONTROL": "Ctrl",
            "KEYCODE_LALT": "Alt",
            "KEYCODE_RALT": "Alt",
            "KEYCODE_TAB": "⇥",
            "KEYCODE_ESC": "Esc",
            
            # Player 2 common keys
            "KEYCODE_I": "I",
            "KEYCODE_J": "J", 
            "KEYCODE_K": "K",
            "KEYCODE_L": "L"
        }
        
        # JOYCODE mappings - including both old and new button mappings
        joycode_to_prefix = {
            # Buttons - use getattr with fallback to avoid AttributeError
            "JOYCODE_1_BUTTON1": "A" if getattr(self, 'use_xinput', True) else "B1",
            "JOYCODE_1_BUTTON2": "B" if getattr(self, 'use_xinput', True) else "B2",
            "JOYCODE_1_BUTTON3": "X" if getattr(self, 'use_xinput', True) else "B3",
            "JOYCODE_1_BUTTON4": "Y" if getattr(self, 'use_xinput', True) else "B4",
            "JOYCODE_1_BUTTON5": "LB" if getattr(self, 'use_xinput', True) else "B5",
            "JOYCODE_1_BUTTON6": "RB" if getattr(self, 'use_xinput', True) else "B6",
            "JOYCODE_1_BUTTON7": "LT" if getattr(self, 'use_xinput', True) else "B7",
            
            # OLD FORMAT - Button 8 and 9 (for backward compatibility)
            "JOYCODE_1_BUTTON8": "BACK" if getattr(self, 'use_xinput', True) else "B8",
            "JOYCODE_1_BUTTON9": "START" if getattr(self, 'use_xinput', True) else "B9",
            
            # NEW FORMAT - Named buttons
            "JOYCODE_1_SELECT": "BACK",
            "JOYCODE_1_START": "START",
            
            # Axes - CRITICAL: These should work regardless of input mode
            "JOYCODE_1_ZAXIS": "LT" if getattr(self, 'use_xinput', True) else "Z-AXIS",
            "JOYCODE_1_RZAXIS": "RT" if getattr(self, 'use_xinput', True) else "RZ-AXIS",
            "JOYCODE_1_ZAXIS_NEG_SWITCH": "LT",
            "JOYCODE_1_RZAXIS_NEG_SWITCH": "RT",
            
            # NEW SLIDER FORMAT
            "JOYCODE_1_SLIDER2_NEG_SWITCH": "LT",
            "JOYCODE_1_SLIDER2_POS_SWITCH": "LT+",
        }
        
        # Combine all mappings
        all_mappings = {**xinput_to_prefix, **dinput_to_prefix, **joycode_to_prefix, 
                        **keyboard_to_prefix, **directional_to_prefix, **trigger_to_prefix}
        
        # Handle multiple button assignments with BOTH ||| and space separators
        if "|||" in mapping or " " in mapping:
            # Determine which separator to use
            if "|||" in mapping:
                parts = [part.strip() for part in mapping.split("|||")]
            else:
                # Handle space-separated mappings (like JOYCODE_1_BUTTON1 JOYCODE_1_BUTTON2)
                parts = [part.strip() for part in mapping.split(" ") if part.strip()]
            
            prefixes = []
            
            for part in parts:
                # Look up the prefix for this part
                if part in all_mappings:
                    prefixes.append(all_mappings[part])
                # Handle other special cases
                elif "DINPUT_1_BUTTON" in part:
                    try:
                        button_num = int(part.replace("DINPUT_1_BUTTON", ""))
                        prefixes.append(f"B{button_num}")
                    except:
                        pass
                elif "JOYCODE_1_BUTTON" in part:
                    try:
                        button_num = int(part.replace("JOYCODE_1_BUTTON", ""))
                        if button_num <= 10:
                            standard_buttons = ["", "A", "B", "X", "Y", "LB", "RB", "LT", "RT", "LS", "RS"]
                            if button_num < len(standard_buttons):
                                prefixes.append(standard_buttons[button_num])
                            else:
                                prefixes.append(f"B{button_num}")
                    except:
                        pass
            
            # Enhanced handling for common combinations
            if len(prefixes) >= 2:
                # Sort prefixes for consistent display
                prefixes.sort()
                
                # Special cases for common button combinations
                if set(prefixes) == {"A", "B"}:
                    return "A+B"  # Your specific case!
                elif set(prefixes) == {"X", "Y"}:
                    return "X+Y"
                elif set(prefixes) == {"LB", "RB"}:
                    return "LB+RB"
                elif set(prefixes) == {"LT", "RT"}:
                    return "LT+RT"
                # Handle directional pairs (keep your existing logic)
                elif "←" in prefixes and "→" in prefixes:
                    return "←/→"
                elif "↑" in prefixes and "↓" in prefixes:
                    return "↑/↓"
                elif "D←" in prefixes and "D→" in prefixes:
                    return "D←/→"
                elif "D↑" in prefixes and "D↓" in prefixes:
                    return "D↑/↓"
                else:
                    # For other combinations, use + for simultaneous presses
                    return "+".join(prefixes)
            elif len(prefixes) == 1:
                return prefixes[0]
            else:
                return ""  # No valid prefixes found
        
        # Check for direct match in standard mappings
        if mapping in all_mappings:
            return all_mappings[mapping]
        
        # Special handling for DirectInput buttons not explicitly listed
        if "DINPUT_1_BUTTON" in mapping:
            try:
                # Extract button number
                button_num = int(mapping.replace("DINPUT_1_BUTTON", ""))
                return f"B{button_num}"
            except:
                pass
        
        # Special handling for keyboard keys not explicitly listed
        if mapping.startswith("KEYCODE_"):
            # Extract the key name
            key_name = mapping.replace("KEYCODE_", "")
            # For most keys, just return the key name
            if len(key_name) == 1:  # Single character keys
                return key_name
            else:
                return key_name[:3]  # First 3 chars for longer key names
        
        # If no direct match, try partial matching for JOYCODE buttons
        if "JOYCODE_1_BUTTON" in mapping:
            try:
                # Extract button number
                button_num = int(mapping.replace("JOYCODE_1_BUTTON", ""))
                if button_num <= 10:
                    # Use standard button mapping (1=A, 2=B, etc.)
                    standard_buttons = ["", "A", "B", "X", "Y", "LB", "RB", "LT", "RT", "LS", "RS"]
                    if button_num < len(standard_buttons):
                        return standard_buttons[button_num]
                    else:
                        return f"B{button_num}"
            except:
                pass
                
        # Return empty string for unknown mappings
        return ""

    def apply_text_settings(self, uppercase_changed=False):
        """Apply current text settings to all controls with both font and gradient support"""
        # Import QTimer at the beginning of the method
        from PyQt5.QtCore import QTimer
        
        # ADD THIS: Create a hash of current settings to detect actual changes
        import hashlib
        settings_hash = hashlib.md5(str(self.text_settings).encode()).hexdigest()
        
        # ADD THIS: Check if settings actually changed
        if (hasattr(self, '_last_settings_hash') and 
            self._last_settings_hash == settings_hash and 
            not uppercase_changed):
            print("Text settings unchanged, skipping apply")
            return
        
        print("Applying text settings (changes detected)")
        
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

                # Special handling for No Buttons notification
                if control_name == "NO_BUTTONS_NOTIFICATION":
                    notification_text = "NB: No Buttons Used"
                    if use_uppercase:
                        notification_text = notification_text.upper()
                    
                    print(f"DEBUG: Applying text settings to No Buttons notification")
                    print(f"DEBUG: Font family: {font_family}, size: {font_size}")
                    print(f"DEBUG: Use action gradient: {use_action_gradient}")
                    print(f"DEBUG: Action color: {action_color}")
                    
                    # Update text and font
                    label.setText(notification_text)
                    label.setFont(font)
                    
                    # Update label settings completely
                    if hasattr(label, 'settings'):
                        label.settings.update(self.text_settings)
                    
                    # Handle gradient settings properly
                    if hasattr(label, 'use_prefix_gradient') and hasattr(label, 'use_action_gradient'):
                        label.use_prefix_gradient = use_prefix_gradient
                        label.use_action_gradient = use_action_gradient
                        
                        # Update all gradient colors
                        if hasattr(label, 'prefix_gradient_start'):
                            label.prefix_gradient_start = QColor(prefix_gradient_start)
                        if hasattr(label, 'prefix_gradient_end'):
                            label.prefix_gradient_end = QColor(prefix_gradient_end)
                        if hasattr(label, 'action_gradient_start'):
                            label.action_gradient_start = QColor(action_gradient_start)
                        if hasattr(label, 'action_gradient_end'):
                            label.action_gradient_end = QColor(action_gradient_end)
                    
                    # Apply complete styling
                    label.setStyleSheet(f"color: {action_color}; background-color: transparent; border: none; font-family: '{font.family()}';")
                    
                    # Debug what we actually applied
                    actual_font = label.font()
                    print(f"DEBUG: Applied font to notification: {actual_font.family()}, size: {actual_font.pointSize()}")
                    
                    # Force repaint and resize
                    label.adjustSize()
                    label.update()
                    continue
                
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
                
                # ADD THIS LINE to truncate long text
                display_text = self.truncate_display_text(display_text)
                
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
        
        # Force resize all labels to handle new font dimensions
        self.force_resize_all_labels()

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
        
        # ADD THIS: Store the hash ONLY after successful completion
        self._last_settings_hash = settings_hash

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
        
class DraggableLabel(QLabel):
    """A draggable label without right-click menu functionality"""
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
            
    # 1. Update the mousePressEvent method to store position more reliably
    def mousePressEvent(self, event):
        """Handle mouse press events for dragging with improved position tracking"""
        from PyQt5.QtCore import Qt
        
        # CRITICAL FIX: Only handle dragging if explicitly allowed
        if not getattr(self, 'draggable', True):
            event.ignore()  # Pass event to parent
            return
            
        if event.button() == Qt.LeftButton:
            # Make sure dragging flag is set
            self.dragging = True
            
            # Store BOTH the mouse position relative to the label AND the absolute label position
            self.drag_start_pos = event.pos()
            self.original_label_pos = self.pos()
            
            # Store absolute cursor position for more stable dragging
            self.global_start_pos = event.globalPos()
            
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()

    # 2. Completely rewritten mouseMoveEvent for smoother dragging
    def mouseMoveEvent(self, event):
        """Handle mouse move with improved position calculation"""
        from PyQt5.QtCore import Qt, QPoint
        from PyQt5.QtWidgets import QApplication
        
        # Only handle dragging if explicitly allowed
        if not getattr(self, 'draggable', True):
            event.ignore()  # Pass event to parent
            return
        
        # Only process if we're in dragging mode
        if not hasattr(self, 'dragging') or not self.dragging or not hasattr(self, 'global_start_pos'):
            return
        
        # Calculate the global movement delta - this is more reliable
        delta = event.globalPos() - self.global_start_pos
        
        # Apply delta to original position
        new_pos = self.original_label_pos + delta
        
        # Variables for snapping and guides
        parent = self.parent()
        snapped = False
        guide_lines = []
        
        # Only apply snapping if parent exists and we have a preview window
        if parent:
            # Find reference to preview window
            preview_window = self.find_preview_window_parent()
            
            if preview_window:
                # Check if snapping is enabled and not overridden by Shift key
                modifiers = QApplication.keyboardModifiers()
                disable_snap = bool(modifiers & Qt.ShiftModifier)  # Shift key disables snapping temporarily
                
                apply_snapping = (
                    not disable_snap and
                    hasattr(preview_window, 'snapping_enabled') and
                    preview_window.snapping_enabled
                )
                
                if apply_snapping:
                    # Apply snapping logic
                    canvas_width = parent.width()
                    canvas_height = parent.height()
                    snap_distance = getattr(preview_window, 'snap_distance', 15)
                    
                    # Get label center coordinates
                    label_center_x = new_pos.x() + self.width() // 2
                    label_center_y = new_pos.y() + self.height() // 2
                    
                    # Apply grid snapping if enabled
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
                    
                    # Show measurement guides if enabled
                    if hasattr(preview_window, 'show_measurement_guides'):
                        try:
                            preview_window.show_measurement_guides(
                                new_pos.x(), new_pos.y(), 
                                self.width(), self.height()
                            )
                        except Exception as e:
                            print(f"Error showing measurement guides: {e}")
                    
                    # Show snapping guides if snapped
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
        
        # Move the label to the final position
        self.move(new_pos)
        
        # Accept the event
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
    
    def paintEvent(self, event):
        """Override paint event to draw text properly centered"""
        # Use default QLabel painting
        super().paintEvent(event)

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

# Simplified version of ColoredDraggableLabel (without right-click menu)
class ColoredDraggableLabel(DraggableLabel):
    """A draggable label that supports different colors for prefix and action text"""
    def __init__(self, text, parent=None, settings=None):
        super().__init__(text, parent, settings)
        self.settings = settings or {}
        self.prefix = ""
        self.action = ""
        self.parse_text(text)

        # Add text alignment control
        from PyQt5.QtCore import Qt
        self.text_alignment = Qt.AlignLeft | Qt.AlignVCenter  # Default to left alignment
    
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
        """Override paint event to draw text with left alignment"""
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

            # Use left alignment with small margin
            x = 10  # Fixed left margin

            # Draw prefix
            painter.setPen(prefix_color)
            painter.drawText(x, y, prefix_text)

            # Get prefix width
            prefix_width = metrics.horizontalAdvance(prefix_text)

            # Draw action text right after prefix
            painter.setPen(action_color)
            painter.drawText(x + prefix_width, y, self.action)
        else:
            # Draw single-part text with left alignment
            text = self.text()
            painter.setPen(action_color)
            painter.drawText(10, y, text)  # 10px from left edge

# Simplified version of GradientDraggableLabel (without right-click menu)
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

        # Add text alignment control
        from PyQt5.QtCore import Qt
        self.text_alignment = Qt.AlignLeft | Qt.AlignVCenter  # Default to left alignment
    
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
        """Paint event with gradient rendering and left alignment"""
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
            
            # Use fixed left margin instead of centering
            x = 10
            
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
            prefix_width = metrics.horizontalAdvance(prefix_text)
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
            # Left-align single text
            text = self.text()
            x = 10  # Fixed left margin
            
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
# preview_bridge.py - A lightweight bridge between tkinter and PyQt previews

import os
import sys
import json
import time
import gc
import subprocess
from typing import Dict, Optional, List, Tuple, Any

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

class PreviewBridge:
    """
    A minimal bridge to launch PyQt previews without the full PyQt GUI.
    This provides a clean interface for tkinter to use PyQt preview functionality.
    """
    
    def __init__(self):
        """Initialize the bridge with paths and minimal setup"""
        self.app_dir = get_application_path()
        self.mame_dir = get_mame_parent_dir(self.app_dir)
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        self.settings_dir = os.path.join(self.preview_dir, "settings")
        
        # Create required directories
        os.makedirs(self.preview_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        
        # Initialize PyQt app if needed
        self._initialize_qt()
        self.preview_window = None
        
        # Patch the PreviewWindow class to make it safer
        self.ensure_safe_preview_window()
        
    def _initialize_qt(self):
        """Initialize PyQt application instance (only when needed)"""
        try:
            from PyQt5.QtWidgets import QApplication
            self.app = QApplication.instance() or QApplication(sys.argv)
            self.app.setApplicationName("MAME Controls Preview")
            self._apply_dark_theme()
            return True
        except ImportError:
            print("PyQt5 not available. Preview functionality will be limited.")
            self.app = None
            return False
            
    def load_rom_settings(self, rom_name):
        """Load ROM-specific settings if they exist"""
        settings = None
        
        # Check for ROM-specific settings
        rom_settings_file = os.path.join(self.settings_dir, f"{rom_name}_settings.json")
        if os.path.exists(rom_settings_file):
            try:
                with open(rom_settings_file, 'r') as f:
                    settings = json.load(f)
                    print(f"Loaded ROM-specific settings for {rom_name}")
            except Exception as e:
                print(f"Error loading ROM-specific settings: {e}")
        
        return settings
    
    def load_bezel_settings(self):
        """Load bezel and joystick visibility settings from file in settings directory"""
        settings = {
            "bezel_visible": False,  # Default to hidden
            "joystick_visible": True,  # Default to visible
            "logo_visible": True  # Default to visible
        }
        
        try:
            # Check settings directory first
            settings_file = os.path.join(self.settings_dir, "bezel_settings.json")
            
            # If not found, check legacy locations
            if not os.path.exists(settings_file):
                legacy_paths = [
                    os.path.join(self.preview_dir, "global_bezel.json"),
                    os.path.join(self.preview_dir, "bezel_settings.json")
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
                    print(f"Loaded bezel/joystick/logo settings from {settings_file}: {settings}")
        except Exception as e:
            print(f"Error loading bezel/joystick/logo settings: {e}")
        
        return settings
    
    def ensure_safe_preview_window(self):
        """Patch the PreviewWindow class to add safe timers and cleanup"""
        try:
            from PyQt5.QtCore import QTimer, Qt
            from PyQt5 import sip
            
            # Import the preview module - we need to patch it
            import sys
            from importlib import import_module
            
            # Keep track of the original class
            preview_module = import_module('mame_controls_preview')
            original_init = preview_module.PreviewWindow.__init__
            original_closeEvent = getattr(preview_module.PreviewWindow, 'closeEvent', None)
            
            # Define safer timer function
            def safe_timer(self, ms, callback):
                """Create a safe timer that checks if objects still exist before callback"""
                timer = QTimer(self)
                timer.setSingleShot(True)
                
                def safe_callback():
                    try:
                        # Only call callback if widget is still valid
                        if not sip.isdeleted(self):
                            callback()
                    except:
                        pass
                
                timer.timeout.connect(safe_callback)
                timer.start(ms)
                return timer
            
            # Add method to PreviewWindow class
            preview_module.PreviewWindow.safe_timer = safe_timer
            
            # Define enhanced closeEvent handler
            def enhanced_closeEvent(self, event):
                """Enhanced closeEvent that ensures proper cleanup"""
                # Cancel all pending timers
                for attr_name in dir(self):
                    if attr_name.endswith('_timer') and hasattr(self, attr_name):
                        timer = getattr(self, attr_name)
                        if hasattr(timer, 'stop'):
                            try:
                                timer.stop()
                            except:
                                pass
                
                # Clear any references to widgets
                for attr_name in dir(self):
                    if hasattr(self, attr_name):
                        attr = getattr(self, attr_name)
                        if hasattr(attr, 'deleteLater'):
                            try:
                                attr.setParent(None)  # Disconnect from parent
                            except:
                                pass
                
                # IMPORTANT: Check if this is a standalone window
                is_standalone = getattr(self, 'standalone_mode', False)
                is_quit_on_close = self.testAttribute(Qt.WA_QuitOnClose)
                
                # Call original closeEvent if it exists
                if original_closeEvent:
                    try:
                        original_closeEvent(self, event)
                    except:
                        event.accept()
                else:
                    event.accept()
                    
                # If not in standalone mode, and not set to quit on close,
                # make sure application doesn't exit
                if not is_standalone and not is_quit_on_close:
                    # Use a timer to schedule deletion after event processing
                    QTimer.singleShot(100, self.deleteLater)
                    
                    # If this is the last window, but we don't want to quit,
                    # create a hidden window to keep the application running
                    from PyQt5.QtWidgets import QApplication
                    if len(QApplication.topLevelWidgets()) <= 1:
                        from PyQt5.QtWidgets import QWidget
                        dummy = QWidget()
                        dummy.setAttribute(Qt.WA_QuitOnClose, False) 
                        dummy.setAttribute(Qt.WA_DeleteOnClose, True)
                        dummy.hide()
            
            # Replace the closeEvent method
            preview_module.PreviewWindow.closeEvent = enhanced_closeEvent
            
            # Patch the __init__ method to use safe timers
            def patched_init(self, *args, **kwargs):
                # Call original initialization
                original_init(self, *args, **kwargs)
                
                # Add a flag to track if this is a standalone window
                self.standalone_mode = False
                
                # Replace any QTimer.singleShot calls in labels or widgets
                # This is specifically targeting the shortcuts_label timer
                if hasattr(self, 'shortcuts_label'):
                    # Cancel any existing timer
                    if hasattr(self, 'shortcuts_timer'):
                        try:
                            self.shortcuts_timer.stop()
                        except:
                            pass
                    
                    # Create a safer timer
                    def hide_shortcuts():
                        if hasattr(self, 'shortcuts_label') and not sip.isdeleted(self.shortcuts_label):
                            self.shortcuts_label.hide()
                    
                    self.shortcuts_timer = self.safe_timer(5000, hide_shortcuts)
            
            # Apply the patched init
            preview_module.PreviewWindow.__init__ = patched_init
            
            print("Enhanced PreviewWindow with safer timer handling")
            return True
            
        except Exception as e:
            print(f"Could not patch PreviewWindow: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _apply_dark_theme(self):
        """Apply dark theme to the PyQt application"""
        try:
            from PyQt5.QtGui import QPalette, QColor
            from PyQt5.QtCore import Qt
            
            # Create dark palette
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
            dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.HighlightedText, QColor(240, 240, 240))
            
            # Apply palette
            self.app.setPalette(dark_palette)
            
            # Apply stylesheet
            self.app.setStyleSheet("""
                QWidget { background-color: #2d2d2d; color: #f0f0f0; }
                QPushButton { 
                    background-color: #3d3d3d; 
                    border: 1px solid #5a5a5a;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #4a4a4a; }
                QPushButton:pressed { background-color: #2a82da; }
            """)
        except Exception as e:
            print(f"Warning: Could not apply dark theme: {e}")
    
    def load_settings(self):
        """Load settings from settings file"""
        settings = {
            "preferred_preview_screen": 1,
            "hide_preview_buttons": False,
            "show_button_names": True
        }
        
        settings_path = os.path.join(self.settings_dir, "control_config_settings.json")
        
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
            except Exception as e:
                print(f"Error loading settings: {e}")
                
        return settings
    
    def cache_game_data(self, rom_name: str, game_data: Dict[str, Any]) -> bool:
        """Save game data to cache for faster access"""
        cache_dir = os.path.join(self.preview_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        cache_path = os.path.join(cache_dir, f"{rom_name}_cache.json")
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(game_data, f, indent=2)
            print(f"Saved game data to cache: {cache_path}")
            return True
        except Exception as e:
            print(f"Error saving to cache: {e}")
            return False
    
    def load_game_data_from_cache(self, rom_name: str) -> Optional[Dict[str, Any]]:
        """Load game data from cache file"""
        cache_dir = os.path.join(self.preview_dir, "cache")
        cache_path = os.path.join(cache_dir, f"{rom_name}_cache.json")
        
        if not os.path.exists(cache_path):
            print(f"No cache found for ROM: {rom_name}")
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                game_data = json.load(f)
            
            # Validate minimal expected structure
            if not isinstance(game_data, dict) or 'romname' not in game_data:
                print(f"Invalid cache data for ROM: {rom_name}")
                return None
                
            return game_data
        except Exception as e:
            print(f"Error loading cache: {e}")
            return None
    
    # Add this to preview_bridge.py
    def show_preview(self, rom_name: str, game_data: Dict[str, Any], 
                    hide_buttons: bool = False, clean_mode: bool = False) -> bool:
        """Show preview window for a ROM using patched PyQt window for maximum performance"""
        # First, ensure any previous preview window is properly closed
        if self.preview_window is not None:
            try:
                self.preview_window.close()
            except:
                pass
            self.preview_window = None
        
        # Force garbage collection
        import gc
        gc.collect()
        
        if not self.app:
            if not self._initialize_qt():
                print("Error: PyQt is required for preview functionality")
                return False
        
        # Explicitly tell app not to quit on window close
        self.app.setQuitOnLastWindowClosed(False)
        
        # Ensure critical paths exist
        os.makedirs(self.preview_dir, exist_ok=True)
        
        # Cache the game data for faster access later
        self.cache_game_data(rom_name, game_data)
        
        try:
            # Get our patched preview window class
            PatchedPreviewWindow = self._create_patched_preview_window()
            if not PatchedPreviewWindow:
                print("Could not create patched preview window, using separate process")
                # Fall back to separate process approach
                return self._show_preview_separate_process(rom_name, hide_buttons, clean_mode)
            
            from PyQt5.QtCore import Qt
            
            # Create the preview window with our patched class
            self.preview_window = PatchedPreviewWindow(
                rom_name,
                game_data,
                self.mame_dir,
                None,  # No parent widget
                hide_buttons,
                clean_mode
            )
            
            # Extra safety - ensure window doesn't close app
            self.preview_window.setAttribute(Qt.WA_QuitOnClose, False)
            
            # Show the window
            self.preview_window.show()
            self.preview_window.activateWindow()
            self.preview_window.raise_()
            
            return True
        except Exception as e:
            print(f"Error showing preview: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to separate process approach
            return self._show_preview_separate_process(rom_name, hide_buttons, clean_mode)

    def _create_patched_preview_window(self):
        """Create a patched version of PreviewWindow that won't close the application"""
        try:
            # Import the original class
            from mame_controls_preview import PreviewWindow as OriginalPreviewWindow
            from PyQt5.QtCore import Qt, QTimer
            from PyQt5.QtWidgets import QApplication
            from PyQt5 import sip
            
            # Create a subclass that overrides problematic behaviors
            class PatchedPreviewWindow(OriginalPreviewWindow):
                def __init__(self, *args, **kwargs):
                    # Initialize a flag to track cleanup state
                    self._is_being_closed = False
                    
                    # Save original singleShot method to restore later
                    self._original_singleShot = QTimer.singleShot
                    
                    # Patch QTimer.singleShot with our safe version for initialization
                    QTimer.singleShot = self._safe_singleShot
                    
                    try:
                        # Call original init with patched timer
                        super().__init__(*args, **kwargs)
                    finally:
                        # Restore original singleShot
                        QTimer.singleShot = self._original_singleShot
                    
                    # Ensure window doesn't close app
                    self.setAttribute(Qt.WA_QuitOnClose, False)
                    self.setAttribute(Qt.WA_DeleteOnClose, True)
                    
                    # Override any existing closeEvent connection
                    if hasattr(self, 'close_button') and self.close_button:
                        try:
                            self.close_button.clicked.disconnect()
                            self.close_button.clicked.connect(self.close)
                        except:
                            pass
                        
                    # Create a list to store our timers so they don't get garbage collected
                    self._safe_timers = []
                    
                    # Replace the specific shortcuts_label timer if it exists
                    if hasattr(self, 'shortcuts_label') and self.shortcuts_label:
                        # Create a safe timer for the shortcuts label
                        safe_timer = QTimer(self)
                        safe_timer.setSingleShot(True)
                        safe_timer.timeout.connect(self._hide_shortcuts_safely)
                        safe_timer.start(5000)
                        self._safe_timers.append(safe_timer)
                    
                    # IMPORTANT: Ensure bezel is displayed
                    # Schedule a call to ensure bezel is loaded and visible
                    bezel_timer = QTimer(self)
                    bezel_timer.setSingleShot(True)
                    bezel_timer.timeout.connect(self._ensure_bezel_visible)
                    bezel_timer.start(100)  # Short delay to let window fully initialize
                    self._safe_timers.append(bezel_timer)
                
                def _ensure_bezel_visible(self):
                    """Ensure the bezel is properly loaded and displayed"""
                    try:
                        # Check if we have bezel integration methods
                        if hasattr(self, 'integrate_bezel_support'):
                            # Force bezel integration
                            self.integrate_bezel_support()
                            
                        # Make bezel visible if it exists
                        if hasattr(self, 'has_bezel') and self.has_bezel:
                            self.bezel_visible = True
                            if hasattr(self, 'show_bezel_with_background'):
                                self.show_bezel_with_background()
                            elif hasattr(self, 'bezel_label') and self.bezel_label:
                                self.bezel_label.show()
                    except Exception as e:
                        print(f"Error ensuring bezel is visible: {e}")
                
                def _hide_shortcuts_safely(self):
                    """Safely hide the shortcuts label if it still exists"""
                    try:
                        if hasattr(self, 'shortcuts_label') and self.shortcuts_label and not sip.isdeleted(self.shortcuts_label):
                            self.shortcuts_label.hide()
                    except:
                        pass
                
                def _safe_singleShot(self, msec, callback):
                    """Safe replacement for QTimer.singleShot during initialization"""
                    # Create a real QTimer and keep a reference to it
                    timer = QTimer()
                    timer.setSingleShot(True)
                    
                    # Store the original object and callback
                    original_self = self
                    original_callback = callback
                    
                    def safe_wrapper():
                        try:
                            # Check if the relevant objects still exist
                            if not sip.isdeleted(original_self):
                                # If it's a lambda that accesses shortcuts_label, handle specially
                                if callable(original_callback) and "shortcuts_label" in str(original_callback):
                                    if hasattr(original_self, 'shortcuts_label') and not sip.isdeleted(original_self.shortcuts_label):
                                        original_self.shortcuts_label.hide()
                                else:
                                    # Otherwise, call the original callback
                                    original_callback()
                        except Exception as e:
                            print(f"Error in safe timer callback: {e}")
                    
                    # Connect our safe wrapper
                    timer.timeout.connect(safe_wrapper)
                    timer.start(msec)
                    
                    # Keep a reference to prevent garbage collection
                    if not hasattr(self, '_safe_timers'):
                        self._safe_timers = []
                    self._safe_timers.append(timer)
                    
                    return timer
                    
                def closeEvent(self, event):
                    # Prevent multiple closeEvents from causing issues
                    if self._is_being_closed:
                        event.accept()
                        return
                        
                    self._is_being_closed = True
                    print("PatchedPreviewWindow closing...")
                    
                    # Cancel all timers first
                    if hasattr(self, '_safe_timers'):
                        for timer in self._safe_timers:
                            try:
                                timer.stop()
                            except:
                                pass
                        self._safe_timers = []
                    
                    # Clean up resources safely
                    self._cleanup_resources()
                    
                    # Accept the event
                    event.accept()
                    
                    # Ensure the application stays running
                    if QApplication.instance() and len(QApplication.topLevelWidgets()) <= 1:
                        # Create a tiny invisible widget to keep app running
                        from PyQt5.QtWidgets import QWidget
                        keeper = QWidget()
                        keeper.setAttribute(Qt.WA_QuitOnClose, False)
                        keeper.resize(1, 1)
                        keeper.hide()
                        
                    # Schedule deletion after event processing
                    QTimer.singleShot(100, self.deleteLater)
                
                def _cleanup_resources(self):
                    """Safely clean up resources to prevent memory leaks"""
                    print("Cleaning up resources...")
                    
                    # Explicitly handle shortcuts_label
                    if hasattr(self, 'shortcuts_label') and self.shortcuts_label:
                        try:
                            self.shortcuts_label.hide()
                            self.shortcuts_label.setParent(None)
                            self.shortcuts_label.deleteLater()
                            self.shortcuts_label = None
                        except:
                            pass
                    
                    # Clear timers
                    for attr_name in dir(self):
                        if attr_name.endswith('_timer') and hasattr(self, attr_name):
                            timer = getattr(self, attr_name)
                            if hasattr(timer, 'stop'):
                                try:
                                    timer.stop()
                                    print(f"Stopped timer: {attr_name}")
                                except:
                                    pass
                    
                    # Safely remove widgets
                    widget_attrs = [
                        'bg_label', 'bezel_label', 'logo_label', 
                        'button_frame', 'central_widget'
                    ]
                    
                    for attr_name in widget_attrs:
                        if hasattr(self, attr_name):
                            widget = getattr(self, attr_name)
                            if widget:
                                try:
                                    widget.setParent(None)
                                    widget.deleteLater()
                                except:
                                    pass
                                setattr(self, attr_name, None)
                    
                    # Clear pixmaps to free memory
                    pixmap_attrs = [
                        'background_pixmap', 'original_background_pixmap',
                        'bezel_pixmap', 'original_bezel_pixmap',
                        'original_logo_pixmap'
                    ]
                    
                    for attr_name in pixmap_attrs:
                        if hasattr(self, attr_name):
                            setattr(self, attr_name, None)
                    
                    # Force garbage collection
                    import gc
                    gc.collect()
                    
                # Override any method that might hide or remove the bezel
                def toggle_bezel(self, state=None):
                    """Override to ensure bezel stays visible"""
                    if state is None:
                        state = not getattr(self, 'bezel_visible', False)
                    
                    # Set visibility state
                    self.bezel_visible = state
                    
                    # Show or hide based on state
                    if hasattr(self, 'bezel_label') and self.bezel_label:
                        if state:
                            self.bezel_label.show()
                        else:
                            self.bezel_label.hide()
            
            # Return the patched class
            return PatchedPreviewWindow
        except Exception as e:
            print(f"Error creating patched preview window: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _show_preview_separate_process(self, rom_name, hide_buttons=False, clean_mode=False):
        """Fallback method to show preview in a separate process if patched window fails"""
        try:
            # Get path to main script
            main_script = None
            main_script_paths = [
                os.path.join(self.app_dir, "mame_controls_main.py"),
                os.path.join(self.mame_dir, "mame_controls_main.py"),
                os.path.join(self.mame_dir, "preview", "mame_controls_main.py")
            ]
            
            for path in main_script_paths:
                if os.path.exists(path):
                    main_script = path
                    break
                    
            if not main_script:
                print("Error: Could not find mame_controls_main.py")
                return False
                
            # Launch the preview in a separate process
            cmd = [
                sys.executable, 
                main_script,
                "--preview-only",
                "--game", rom_name
            ]
            
            if hide_buttons:
                cmd.append("--no-buttons")
                
            if clean_mode:
                cmd.append("--clean-preview")
                
            # Launch the process
            import subprocess
            process = subprocess.Popen(cmd)
            
            # Store the process
            if not hasattr(self, 'preview_processes'):
                self.preview_processes = []
                
            # Clean up any completed processes
            self.preview_processes = [p for p in self.preview_processes if p.poll() is None]
            
            # Add the new process
            self.preview_processes.append(process)
            
            return True
        except Exception as e:
            print(f"Error launching preview: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def show_preview_standalone(self, rom_name: str, auto_close: bool = False, 
                            clean_mode: bool = False) -> int:
        """Launch a standalone preview for a ROM with optimized startup"""
        # First, ensure any previous preview window is properly closed
        if self.preview_window is not None:
            try:
                self.preview_window.close()
            except:
                pass
            self.preview_window = None
            
        # Force garbage collection
        import gc
        gc.collect()
        
        if not self.app:
            if not self._initialize_qt():
                print("Error: PyQt is required for preview functionality")
                return 1
                
        # In standalone mode, we DO want to quit on last window closed
        self.app.setQuitOnLastWindowClosed(True)
        
        # Load settings for screen selection
        settings = self.load_settings()
        screen_num = settings.get("preferred_preview_screen", 1)
        hide_buttons = settings.get("hide_preview_buttons", False)
        
        # Check for cached game data
        game_data = self.load_game_data_from_cache(rom_name)
        
        if not game_data:
            print(f"No cached data for {rom_name}, trying to load game data directly")
            
            # Try to load data using dynamic import approach (faster than subprocess)
            try:
                # First look for tkinter module to get game data
                import importlib.util
                import sys
                
                # Try common module locations
                tk_module_paths = [
                    os.path.join(self.app_dir, "mame_controls_tkinter.py"),
                    os.path.join(self.mame_dir, "preview", "mame_controls_tkinter.py"),
                    os.path.join(self.mame_dir, "mame_controls_tkinter.py")
                ]
                
                tk_module_path = None
                for path in tk_module_paths:
                    if os.path.exists(path):
                        tk_module_path = path
                        break
                        
                if tk_module_path:
                    print(f"Loading tkinter module from: {tk_module_path}")
                    spec = importlib.util.spec_from_file_location("mame_controls_tkinter", tk_module_path)
                    tkinter_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(tkinter_module)
                    
                    # Create minimal instance to get game data
                    config = tkinter_module.MAMEControlConfig(preview_only=True)
                    game_data = config.get_game_data(rom_name)
                    
                    if game_data:
                        # Cache the data for future use
                        self.cache_game_data(rom_name, game_data)
                        print(f"Successfully loaded and cached game data for {rom_name}")
                    else:
                        # Fall back to subprocess approach
                        print("Could not get game data directly, falling back to subprocess")
                        return self._standalone_preview_subprocess(rom_name, hide_buttons, clean_mode, auto_close)
                else:
                    # Fall back to subprocess approach
                    return self._standalone_preview_subprocess(rom_name, hide_buttons, clean_mode, auto_close)
            except Exception as e:
                print(f"Error loading game data: {e}")
                import traceback
                traceback.print_exc()
                return self._standalone_preview_subprocess(rom_name, hide_buttons, clean_mode, auto_close)
        
        try:
            # Get our patched preview window class (same one used for regular preview)
            PatchedPreviewWindow = self._create_patched_preview_window()
            if not PatchedPreviewWindow:
                print("Could not create patched preview window, using subprocess")
                return self._standalone_preview_subprocess(rom_name, hide_buttons, clean_mode, auto_close)
            
            # Import necessary Qt classes
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QDesktopWidget
            
            # Get screen geometry
            desktop = QDesktopWidget()
            screen_geometry = desktop.screenGeometry(screen_num - 1)
            
            # Create the preview window with our patched class
            self.preview_window = PatchedPreviewWindow(
                rom_name,
                game_data,
                self.mame_dir,
                None,  # No parent
                hide_buttons,
                clean_mode
            )
            
            # Mark this as a standalone window
            self.preview_window.standalone_mode = True
            
            # In standalone mode, we DO want the window to close the app
            self.preview_window.setAttribute(Qt.WA_QuitOnClose, True)
            
            # Apply fullscreen settings
            self.preview_window.setWindowFlags(
                Qt.WindowStaysOnTopHint | 
                Qt.FramelessWindowHint | 
                Qt.Tool  # Removes from taskbar
            )
            
            # Set background properties
            self.preview_window.setAttribute(Qt.WA_NoSystemBackground, True)
            self.preview_window.setAttribute(Qt.WA_TranslucentBackground, True)
            
            # Apply exact geometry
            self.preview_window.setGeometry(screen_geometry)
            
            # Set up monitor for MAME process if auto_close
            if auto_close:
                self._start_mame_monitor()
            
            # Show fullscreen
            self.preview_window.showFullScreen()
            self.preview_window.activateWindow()
            self.preview_window.raise_()
            
            # Execute the application event loop (blocks until window is closed)
            return self.app.exec_()
        except Exception as e:
            print(f"Error in standalone preview: {e}")
            import traceback
            traceback.print_exc()
            return self._standalone_preview_subprocess(rom_name, hide_buttons, clean_mode, auto_close)

    def _standalone_preview_subprocess(self, rom_name, hide_buttons=False, clean_mode=False, auto_close=False):
        """Fallback method to launch standalone preview as a separate process"""
        # Get path to main script
        main_script = None
        main_script_paths = [
            os.path.join(self.app_dir, "mame_controls_main.py"),
            os.path.join(self.mame_dir, "mame_controls_main.py"),
            os.path.join(self.mame_dir, "preview", "mame_controls_main.py")
        ]
        
        for path in main_script_paths:
            if os.path.exists(path):
                main_script = path
                break
                
        if not main_script:
            print("Error: Could not find mame_controls_main.py")
            return 1
            
        # Launch the preview in a separate process
        cmd = [
            sys.executable, 
            main_script,
            "--preview-only",
            "--game", rom_name
        ]
        
        if hide_buttons:
            cmd.append("--no-buttons")
            
        if clean_mode:
            cmd.append("--clean-preview")
            
        if auto_close:
            cmd.append("--auto-close")
        
        # Execute the command and wait for it to complete
        import subprocess
        process = subprocess.Popen(cmd)
        return process.wait()  # Return the process exit code

    def _start_mame_monitor(self, check_interval: float = 1.0):
        """Start a thread to monitor MAME process and close preview when MAME exits"""
        import threading
        
        def check_mame():
            mame_running = True
            while mame_running and hasattr(self, 'preview_window') and self.preview_window:
                time.sleep(check_interval)
                
                # Check if any MAME process is running
                try:
                    if sys.platform == 'win32':
                        output = subprocess.check_output('tasklist /FI "IMAGENAME eq mame*"', shell=True)
                        mame_detected = b'mame' in output.lower()
                    else:
                        output = subprocess.check_output(['ps', 'aux'])
                        mame_detected = b'mame' in output
                        
                    mame_running = mame_detected
                except Exception:
                    continue
                    
            # MAME is no longer running - close preview
            if hasattr(self, 'preview_window') and self.preview_window:
                print("MAME closed, closing preview")
                self.preview_window.close()
        
        # Start monitoring in a daemon thread
        monitor_thread = threading.Thread(target=check_mame, daemon=True)
        monitor_thread.start()
    
    def export_preview_image(self, rom_name, output_path, format="png", show_bezel=True, show_logo=True):
        """Export a preview image for a ROM to the specified path"""
        try:
            print(f"Exporting preview for {rom_name} to {output_path}")
            print(f"Settings: show_bezel={show_bezel}, show_logo={show_logo}")
            
            # Get game data from cache (or load it if needed)
            game_data = self.load_game_data_from_cache(rom_name)
            if not game_data:
                print(f"No cached game data found for {rom_name}")
                return False
            
            # Import required modules
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtCore import QTimer, Qt
            import sys
            
            # Ensure we have a QApplication
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            
            # Import the preview module
            from mame_controls_preview import PreviewWindow
            
            # Create preview window
            preview = PreviewWindow(
                rom_name,
                game_data,
                self.mame_dir,
                hide_buttons=True,
                clean_mode=True
            )
            
            # Force window to be ready
            preview.show()
            app.processEvents()
            
            # IMPORTANT: Override the bezel visibility with our parameter
            # This needs to be done AFTER the window is created/shown
            if hasattr(preview, 'has_bezel') and preview.has_bezel:
                preview.bezel_visible = show_bezel
                
                # Make sure the bezel is properly shown or hidden
                if show_bezel:
                    print("Forcing bezel to be visible for export")
                    preview.show_bezel_with_background()
                    # Make sure the bezel label is also visible
                    if hasattr(preview, 'bezel_label') and preview.bezel_label:
                        preview.bezel_label.setVisible(True)
                else:
                    print("Forcing bezel to be hidden for export")
                    if hasattr(preview, 'bezel_label') and preview.bezel_label:
                        preview.bezel_label.hide()
            
            # Set logo visibility
            if hasattr(preview, 'logo_visible') and hasattr(preview, 'logo_label'):
                preview.logo_visible = show_logo
                if preview.logo_label:
                    preview.logo_label.setVisible(show_logo)
                    
            # Force processing to ensure UI updates
            app.processEvents()
            
            # Sleep briefly to ensure rendering completes
            import time
            time.sleep(0.5)
            app.processEvents()
            
            # Export the image
            success = False
            try:
                # Try headless export first
                if hasattr(preview, 'export_image_headless'):
                    success = preview.export_image_headless(output_path, format)
                else:
                    # Fall back to regular export
                    success = preview.save_image()
                    
                # Verify the file was created
                if not os.path.exists(output_path):
                    print(f"Export failed: File not created at {output_path}")
                    success = False
            except Exception as export_err:
                print(f"Error during export: {export_err}")
                success = False
                
            # Close preview
            preview.close()
            return success
        except Exception as e:
            print(f"Error in export_preview_image: {e}")
            import traceback
            traceback.print_exc()
            return False
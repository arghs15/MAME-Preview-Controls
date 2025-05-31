import queue
import sqlite3
import sys
import os
import json
import re
import subprocess
import threading
import time
import traceback
from typing import Dict, Set, Tuple
import xml.etree.ElementTree as ET
import customtkinter as ctk
from tkinter import messagebox, StringVar
from functools import lru_cache
import tkinter as tk
from tkinter import ttk, messagebox
from screeninfo import get_monitors
from mame_data_utils import cleanup_database_connections
cleanup_database_connections()
from mame_utils import (
    get_application_path, 
    get_mame_parent_dir, 
    find_file_in_standard_locations
)
# Add this import after your existing imports
from mame_data_utils import (
    # Data loading functions
    load_gamedata_json, get_game_data,
    build_gamedata_db, check_db_update_needed, rom_exists_in_db,
    
    # Config parsing functions
    load_custom_configs, load_default_config, parse_cfg_controls,
    
    # Mapping conversion functions
    convert_mapping,
    
    # Data processing functions
    update_game_data_with_custom_mappings, filter_xinput_controls,
    scan_roms_directory,
    
    # Cache management functions
    clean_cache_directory
)

# Theme settings for the application
THEME_COLORS = {
    "dark": {
        "primary": "#1f538d",         # Primary accent color
        "secondary": "#2B87D1",       # Secondary accent color
        "background": "#1e1e1e",      # Main background
        "card_bg": "#2d2d2d",         # Card/frame background
        "sidebar_bg": "#252525",      # Sidebar background
        "text": "#ffffff",            # Main text color
        "text_dimmed": "#a0a0a0",     # Secondary text color
        "text_grey": "#d6d6d6",
        "highlight": "#3a7ebf",       # Highlight color
        "success": "#28a745",         # Success color
        "warning": "#ffc107",         # Warning color  
        "danger": "#dc3545",          # Danger/error color
        "button_hover": "#1A6DAE",    # Button hover color
    }
}

class AsyncLoader:
    """Handles asynchronous loading of data to improve UI responsiveness"""
    def __init__(self, callback=None):
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.worker_thread = None
        self.callback = callback
        self.running = False
    
    def start_worker(self):
        """Start the worker thread"""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
    
    def stop_worker(self):
        """Stop the worker thread"""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.task_queue.put(None)  # Signal to exit
            self.worker_thread.join(timeout=1.0)
    
    def _worker_loop(self):
        """Worker thread main loop"""
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.5)
                if task is None:  # Exit signal
                    break
                    
                func, args, kwargs = task
                try:
                    result = func(*args, **kwargs)
                    self.result_queue.put((True, result))
                except Exception as e:
                    print(f"Error in worker task: {e}")
                    traceback.print_exc()
                    self.result_queue.put((False, str(e)))
                
                self.task_queue.task_done()
                
            except queue.Empty:
                pass  # No tasks, continue waiting
    
    def add_task(self, func, *args, **kwargs):
        """Add a task to the queue"""
        self.task_queue.put((func, args, kwargs))
        self.start_worker()  # Ensure worker is running
    
    def process_results(self):
        """Process any available results"""
        try:
            while not self.result_queue.empty():
                success, result = self.result_queue.get_nowait()
                if self.callback:
                    self.callback(success, result)
                self.result_queue.task_done()
            return True
        except Exception as e:
            print(f"Error processing results: {e}")
            return False

class CustomSidebarTab(ctk.CTkFrame):
    """Custom sidebar tab button with icon support and active state - no changes needed"""
    def __init__(self, master, text, icon_path=None, command=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        
        self.master = master
        self.text = text
        self.command = command
        self.is_active = False
        
        # Container frame for consistent layout
        self.container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=6)
        self.container.pack(fill="x", padx=5, pady=2)
        
        # Icon (if provided)
        self.icon = None
        self.icon_label = None
        if icon_path and os.path.exists(icon_path):
            try:
                self.icon = ctk.CTkImage(light_image=tk.PhotoImage(file=icon_path),
                                         dark_image=tk.PhotoImage(file=icon_path),
                                         size=(20, 20))
                self.icon_label = ctk.CTkLabel(self.container, image=self.icon, text="")
                self.icon_label.pack(side="left", padx=(10, 5))
            except Exception as e:
                print(f"Error loading icon {icon_path}: {e}")
        
        # Text label
        self.label = ctk.CTkLabel(self.container, text=text, anchor="w")
        self.label.pack(side="left", fill="x", expand=True, padx=(10 if not self.icon else 5, 10))
        
        # Bind click event
        self.bind("<Button-1>", self._on_click)
        self.container.bind("<Button-1>", self._on_click)
        self.label.bind("<Button-1>", self._on_click)
        if self.icon_label:
            self.icon_label.bind("<Button-1>", self._on_click)
        
        # Set inactive state initially
        self.set_active(False)
    
    def _on_click(self, event):
        """Handle click event"""
        if self.command:
            self.command()
    
    def set_active(self, active):
        """Set active state with visual feedback"""
        self.is_active = active
        
        if active:
            self.container.configure(fg_color=THEME_COLORS["dark"]["primary"])
            self.label.configure(text_color="white")
            if self.icon_label:
                self.icon_label.configure(text_color="white")
        else:
            self.container.configure(fg_color="transparent")
            self.label.configure(text_color=THEME_COLORS["dark"]["text"])
            if self.icon_label:
                self.icon_label.configure(text_color=THEME_COLORS["dark"]["text"])

class MAMEControlConfig(ctk.CTk):
    def __init__(self, preview_only=False, initially_hidden=False):
        # FEATURE TOGGLES - Set to False to disable features
        self.ALLOW_CUSTOM_CONTROLS = False  # Set to True to enable custom controls dropdown
        self.ALLOW_ADD_NEW_GAME = True     # Set to True to enable "Add New Game" tab
        self.ALLOW_REMOVE_GAME = False     # Set to True to enable "Remove Game" button
        self.SHOW_HIDE_BUTTONS_TOGGLE = False  # NEW: Set to False to hide the toggle
        
        # Add ROM source mode tracking
        self.rom_source_mode = "physical"  # "physical" or "database"
        self.database_roms = set()  # Will hold all parent ROMs from gamedata
        
        # Add panel proportion configuration here
        self.LEFT_PANEL_RATIO = 0.35  # Left panel takes 35% of window width
        self.MIN_LEFT_PANEL_WIDTH = 400  # Minimum width in pixels
        self.original_default_controls = {}  # Store original mappings for KEYCODE mode

        # Add ROM data cache to improve performance
        self.rom_data_cache = {}
        self.processed_cache = {}  # ADD THIS LINE for processed data cache

        try:
            # Initialize with super().__init__ but don't show the window yet
            super().__init__()

            # Always withdraw the main window until loading is complete
            self.withdraw()
            
            # Create a separate splash window
            self.splash_window = self.create_splash_window()
            
            # Set theme colors and appearance
            self.theme_colors = THEME_COLORS["dark"]
            self.configure(fg_color=self.theme_colors["background"])
            
            # Initialize core attributes needed for both modes
            self.visible_control_types = ["BUTTON", "JOYSTICK", "DIAL", "PEDAL", "AD_STICK", "TRACKBALL", "LIGHTGUN", "MOUSE"]
            self.default_controls = {}
            self.gamedata_json = {}
            self.available_roms = set()
            self.custom_configs = {}
            self.current_game = None
            self.use_xinput = True
            
            # Initialize the async loader for better responsiveness
            self.async_loader = AsyncLoader(callback=self.on_async_task_complete)
            
            # Current view mode
            self.current_view = "all"  # Default view
            
            # Logo size settings (as percentages)
            self.logo_width_percentage = 15
            self.logo_height_percentage = 15

            # Initialize directory structure
            self.initialize_directory_structure()
            
            # Add ROM data cache to improve performance
            self.rom_data_cache = {}
            
            # Configure the window
            self.title("MAME Control Configuration")
            self.geometry("1280x800")
            self.fullscreen = False  # Track fullscreen state
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("dark-blue")
            
            # Bind F11 key for fullscreen toggle
            self.bind("<F11>", self.toggle_fullscreen)
            self.bind("<Escape>", self.exit_fullscreen)
            
            self.selected_line = None
            self.highlight_tag = "highlight"
            
            if not self.mame_dir:
                if hasattr(self, 'splash_window') and self.splash_window:
                    self.splash_window.destroy()
                messagebox.showerror("Error", "MAME directory not found!")
                self.quit()
                return

            self.create_layout()
            
            # Start loading process with slight delay to ensure splash is shown
            self.after(100, self._start_loading_process)
            
            # Set the WM_DELETE_WINDOW protocol
            self.protocol("WM_DELETE_WINDOW", self.on_closing)

        except Exception as e:
            traceback.print_exc()
            if hasattr(self, 'splash_window') and self.splash_window:
                self.splash_window.destroy()
            messagebox.showerror("Initialization Error", f"Failed to initialize: {e}")

    def _start_loading_process(self):
        """Begin the sequential loading process with separate splash window"""
        
        # Update splash message
        self.update_splash_message("Loading settings...")
        
        # Load settings first (synchronous)
        self.load_settings()
        
        # Schedule the next step
        self.after(100, self._load_essential_data)

    def _load_essential_data(self):
        """Load essential data synchronously - FIXED"""
        try:
            # Update message
            self.update_splash_message("Scanning ROMs directory...")
            
            # Scan ROMs directory
            self.available_roms = scan_roms_directory(self.mame_dir)
            
            # Update message
            self.update_splash_message("Updating game list...")
            
            # Update the game list (this will auto-select first ROM)
            if hasattr(self, 'game_listbox'):
                self.update_game_list_by_category()  # ← This already calls select_first_rom!
            
            # Update stats
            self.update_stats_label()
            
            # REMOVE THIS LINE - it's causing the double call:
            # self.select_first_rom()  # ← DELETE THIS LINE
            
            # Schedule secondary data loading
            self.after(100, self._load_secondary_data)
            
        except Exception as e:
            traceback.print_exc()
            self.update_splash_message(f"Error: {str(e)}")
            
            # Still try to continue
            self.after(1000, self._load_secondary_data)

    def debug_database_contents(self):
        """Debug what's actually in the database vs JSON"""
        import sqlite3
        
        print(f"\n=== DATABASE DEBUG ===")
        print(f"Database path: {self.db_path}")
        print(f"Database exists: {os.path.exists(self.db_path)}")
        
        if not os.path.exists(self.db_path):
            print("❌ Database file doesn't exist!")
            return
        
        file_size = os.path.getsize(self.db_path)
        print(f"Database size: {file_size:,} bytes")
        
        if file_size < 1000:
            print("⚠️ Database file is very small - likely empty!")
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"Tables in database: {tables}")
            
            if 'games' not in tables:
                print("❌ 'games' table missing!")
                conn.close()
                return
            
            # Count total games in database
            cursor.execute("SELECT COUNT(*) FROM games")
            db_game_count = cursor.fetchone()[0]
            print(f"Games in database: {db_game_count}")
            
            # Count games in JSON
            json_game_count = len(self.gamedata_json) if hasattr(self, 'gamedata_json') else 0
            print(f"Games in JSON: {json_game_count}")
            
            if db_game_count == 0:
                print("❌ Database has no games - building failed!")
                conn.close()
                return
            
            if json_game_count > 0 and db_game_count < json_game_count / 2:
                print("⚠️ Database has significantly fewer games than JSON!")
            
            conn.close()
            
        except Exception as e:
            print(f"❌ Error checking database: {e}")
            import traceback
            traceback.print_exc()
    
    # Replace your _load_secondary_data method with this corrected version:

    def _load_secondary_data(self):
        """Load secondary data with proper database checking - NO FORCED REBUILD"""
        try:
            self.update_splash_message("Loading default controls...")
            
            # Load default config
            self.default_controls, self.original_default_controls = load_default_config(self.mame_dir)
            print(f"Loaded {len(self.default_controls)} default controls")
            
            self.update_splash_message("Loading custom configurations...")
            
            # Load custom configs  
            self.custom_configs = load_custom_configs(self.mame_dir)
            print(f"Loaded {len(self.custom_configs)} custom configs")
            
            self.update_splash_message("Checking database...")
            
            # Ensure gamedata.json is loaded
            if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
                print("Loading gamedata.json for database operations...")
                self.load_gamedata_json()
            
            # PROPER CHECK: Only rebuild if actually needed
            needs_rebuild = False
            
            # Check if database file exists
            if not os.path.exists(self.db_path):
                print("Database file doesn't exist, will create new one")
                needs_rebuild = True
            else:
                # Check if database has valid schema
                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM games")
                    game_count = cursor.fetchone()[0]
                    conn.close()
                    
                    if game_count == 0:
                        print("Database exists but is empty, rebuilding...")
                        needs_rebuild = True
                    else:
                        print(f"Database found with {game_count} games")
                        # Check timestamps
                        if check_db_update_needed(self.gamedata_path, self.db_path):
                            print("gamedata.json is newer than database, rebuilding...")
                            needs_rebuild = True
                        else:
                            print("Database is up to date, no rebuild needed")
                            
                except sqlite3.Error as e:
                    print(f"Database appears corrupted ({e}), rebuilding...")
                    needs_rebuild = True
            
            # Only rebuild if actually needed
            if needs_rebuild:
                self.update_splash_message("Building database...")
                print(f"Building database with {len(self.gamedata_json)} game entries...")
                
                if self.gamedata_json:
                    from mame_data_utils import build_gamedata_db
                    success = build_gamedata_db(self.gamedata_json, self.db_path)
                    if success:
                        print("✅ Database build completed successfully")
                    else:
                        print("❌ Database build failed")
                else:
                    print("❌ ERROR: No gamedata available for database building!")
            
            # Move to finish loading
            self.after(100, self._finish_loading)
            
        except Exception as e:
            print(f"Error in secondary data loading: {e}")
            import traceback
            traceback.print_exc()
            self.after(500, self._finish_loading)


    def _load_default_config_wrapper(self):
        """Wrapper for loading default config"""
        self.default_controls, self.original_default_controls = load_default_config(self.mame_dir)
        return bool(self.default_controls)

    def _load_custom_configs_wrapper(self):
        """Wrapper for loading custom configs"""
        self.custom_configs = load_custom_configs(self.mame_dir)
        return len(self.custom_configs)

    def _check_loading_progress(self):
        """Check if async loading is complete"""
        # Process any completed tasks
        self.async_loader.process_results()
        
        # Check if all tasks are complete
        if self.async_loader.task_queue.empty() and self.async_loader.result_queue.empty():
            self.after(500, self._finish_loading)
        else:
            # Not done yet, check again soon
            self.after(100, self._check_loading_progress)

    def _finish_loading(self):
        """Finish loading and show the main application"""
        
        # Update message for the final step
        self.update_splash_message("Starting application...")
        
        # Apply any final configurations
        self._apply_initial_panel_sizes()
        if hasattr(self, 'after_init_setup'):
            self.after_init_setup()
        
        # Schedule showing the main window
        self.after(500, self.show_application)

    def show_application(self):
        """Show the application window on the same monitor as the splash"""
        try:
            
            # Close splash window
            if hasattr(self, 'splash_window') and self.splash_window:
                try:
                    self.splash_window.destroy()
                except:
                    pass
                self.splash_window = None
            
            # Force full UI update
            self.update_idletasks()
            
            # Get the monitor to use - use the one we determined at launch time
            if hasattr(self, 'launch_monitor'):
                monitor = self.launch_monitor
            else:
                # Fallback to primary monitor if launch_monitor wasn't set
                monitors = get_monitors()
                monitor = monitors[0]  # Default to first
                for m in monitors:
                    if getattr(m, 'is_primary', False):
                        monitor = m
                        break
            
            # Set window size and position
            win_width = 1280
            win_height = 800
            x = monitor.x + (monitor.width - win_width) // 2
            y = monitor.y + (monitor.height - win_height) // 2
            
            # Position window on the appropriate monitor
            self.geometry(f"{win_width}x{win_height}+{x}+{y}")
            
            # Show the main window
            self.deiconify()
            
            # Auto maximize after showing
            self.state('zoomed')
            
            # Force another update to ensure complete rendering
            self.update_idletasks()
            
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            # Show window anyway in case of error to avoid being stuck
            try:
                self.deiconify()
            except:
                pass
    
    def create_splash_window(self):
        """Create a separate splash window that shows on the appropriate monitor"""
        try:
            # Create a toplevel window for splash
            splash = tk.Toplevel()
            splash.title("Loading")
            splash.withdraw()  # Hide initially
            
            # Check if running as executable
            is_frozen = getattr(sys, 'frozen', False)
            
            # Different positioning strategy based on running mode
            if is_frozen:
                # When running as executable, try to determine launch monitor
                try:
                    # Get executable path
                    if hasattr(sys, '_MEIPASS'):
                        # PyInstaller specific
                        exe_dir = os.path.dirname(sys.executable)
                    else:
                        exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
                    
                    # Get mouse pointer location to determine which monitor the user is using
                    mouse_x = splash.winfo_pointerx()
                    mouse_y = splash.winfo_pointery()
                    
                    # Find monitor containing mouse pointer
                    monitors = get_monitors()
                    launch_monitor = monitors[0]  # Default to first
                    
                    for monitor in monitors:
                        if (monitor.x <= mouse_x < monitor.x + monitor.width and
                            monitor.y <= mouse_y < monitor.y + monitor.height):
                            launch_monitor = monitor
                            break
                    
                    # Store for main window
                    self.launch_monitor = launch_monitor
                    
                    # Center splash on launch monitor
                    splash_width = 400
                    splash_height = 200
                    x = launch_monitor.x + (launch_monitor.width - splash_width) // 2
                    y = launch_monitor.y + (launch_monitor.height - splash_height) // 2
                    
                except Exception as e:
                    # Fallback to primary monitor
                    monitors = get_monitors()
                    primary_monitor = monitors[0]
                    for m in monitors:
                        if getattr(m, 'is_primary', False):
                            primary_monitor = m
                            break
                    
                    self.launch_monitor = primary_monitor
                    
                    splash_width = 400
                    splash_height = 200
                    x = primary_monitor.x + (primary_monitor.width - splash_width) // 2
                    y = primary_monitor.y + (primary_monitor.height - splash_height) // 2
                    
            else:
                # When running as script, always use primary monitor
                monitors = get_monitors()
                primary_monitor = monitors[0]  # Default to first
                for monitor in monitors:
                    if getattr(monitor, 'is_primary', False):
                        primary_monitor = monitor
                        break
                
                self.launch_monitor = primary_monitor
                
                splash_width = 400
                splash_height = 200
                x = primary_monitor.x + (primary_monitor.width - splash_width) // 2
                y = primary_monitor.y + (primary_monitor.height - splash_height) // 2

            # Set window position
            splash.geometry(f"{splash_width}x{splash_height}+{x}+{y}")
            
            # Configure appearance
            splash.configure(bg="#1e1e1e")  # Dark background
            
            # Frame with border
            frame = tk.Frame(
                splash, 
                bg="#1e1e1e",
                highlightbackground="#1f538d",  # Blue border
                highlightthickness=2
            )
            frame.pack(fill="both", expand=True, padx=2, pady=2)
            
            # Add a title
            title_label = tk.Label(
                frame,
                text="MAME Controls Configuration",
                font=("Arial", 16, "bold"),
                fg="white",
                bg="#1e1e1e"
            )
            title_label.pack(pady=(20, 10))
            
            # Add loading message
            self.splash_message = tk.StringVar(value="Starting...")
            message_label = tk.Label(
                frame,
                textvariable=self.splash_message,
                font=("Arial", 12),
                fg="white",
                bg="#1e1e1e"
            )
            message_label.pack(pady=(10, 20))
            
            # Add progress bar
            style = ttk.Style()
            style.theme_use('default')
            style.configure(
                "Blue.Horizontal.TProgressbar",
                troughcolor="#2d2d2d",
                background="#1f538d",  # Blue color
                borderwidth=0
            )
            
            self.splash_progress = ttk.Progressbar(
                frame,
                orient="horizontal",
                length=300,
                mode="indeterminate",
                style="Blue.Horizontal.TProgressbar"
            )
            self.splash_progress.pack(pady=10)
            self.splash_progress.start(15)  # Start animation
            
            # Now show the window
            splash.deiconify()
            
            # Ensure it stays on top
            splash.attributes('-topmost', True)
            splash.focus_force()
            
            # Disable closing with X button
            splash.protocol("WM_DELETE_WINDOW", lambda: None)
            
            # Update to ensure it's rendered
            splash.update()
            
            return splash
                
        except Exception as e:
            return None
    
    def update_splash_message(self, message):
        """Update the splash window message"""
        if hasattr(self, 'splash_message'):
            self.splash_message.set(message)
            if hasattr(self, 'splash_window') and self.splash_window:
                self.splash_window.update_idletasks()
    
    def check_and_build_db_if_needed(self):
        """Check and build the database only if needed"""
        if check_db_update_needed(self.gamedata_path, self.db_path):
            print("Database needs updating, rebuilding...")
            self.load_gamedata_json()  # ← Already updated above
            return build_gamedata_db(self.gamedata_json, self.db_path)
        else:
            print("Database is up to date, skipping rebuild")
            return False
    
    def process_async_results(self):
        """Process any results from async tasks"""
        self.async_loader.process_results()
        # Schedule the next check
        self.after(100, self.process_async_results)
    
    def on_async_task_complete(self, success, result):
        """Handle completion of async tasks"""
        if not success:
            print(f"Async task failed: {result}")
        else:
            # Handle successful task completion if needed
            pass

    def toggle_game_list(self):
        """Simple toggle that truly collapses the game list panel"""
        try:
            # Check if sidebar is currently visible
            sidebar_visible = self.sidebar.winfo_ismapped()
            
            if sidebar_visible:
                # Hide the panels
                self.sidebar.grid_remove()
                
                # Adjust column configuration to give all space to right panel
                self.grid_columnconfigure(0, minsize=0, weight=0)  # Sidebar column - collapse to nothing
                
                # Update button text to show expand icon
                self.collapse_button.configure(text="▶")
            else:
                # Show the panels
                self.sidebar.grid()  # Restore sidebar to grid
                
                # Restore column configuration
                self.grid_columnconfigure(0, minsize=220, weight=0)  # Restore sidebar width
                
                # Update button text to show collapse icon
                self.collapse_button.configure(text="◀")
            
            # Force layout update
            self.update_idletasks()
            
        except Exception as e:
            print(f"Error toggling game list: {e}")

    def load_cache_settings(self):
        """Load cache management settings from JSON file"""
        default_settings = {
            "max_age_days": 9999,
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
    
    def clean_cache_directory(self, max_age_days=None, max_files=None):
        """Clean cache using utility function"""
        if max_age_days is None:
            max_age_days = getattr(self, 'cache_max_age', 7)
        if max_files is None:
            max_files = getattr(self, 'cache_max_files', 100)
        
        return clean_cache_directory(self.cache_dir, max_age_days, max_files)

    def clear_cache(self):
        """Show cache management dialog with options to clear cache and configure settings - FIXED"""
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
                if os.path.exists(filepath):
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
            
            # FIXED: Correct cache clearing functions
            def clear_all_cache():
                """Clear all cache files"""
                try:
                    from mame_data_utils import perform_cache_clear
                    success = perform_cache_clear(cache_dir, all_files=True)
                    
                    if success:
                        # Update dialog display
                        dialog.destroy()
                        # Show success message
                        messagebox.showinfo("Cache Cleared", "All cache files have been cleared successfully.")
                        
                        # Clear in-memory caches too
                        if hasattr(self, 'rom_data_cache'):
                            self.rom_data_cache.clear()
                        if hasattr(self, 'processed_cache'):
                            self.processed_cache.clear()
                        
                        print("All cache cleared successfully")
                    else:
                        messagebox.showwarning("Cache Clear", "No cache files were found to clear.")
                except Exception as e:
                    print(f"Error clearing cache: {e}")
                    messagebox.showerror("Error", f"Failed to clear cache: {str(e)}")
            
            def clear_old_cache():
                """Clear old cache files based on settings"""
                try:
                    max_age = int(self.max_age_var.get()) if self.max_age_var.get().isdigit() else 7
                    max_files = int(self.max_files_var.get()) if self.max_files_var.get().isdigit() else 100
                    
                    from mame_data_utils import clean_cache_directory
                    success = clean_cache_directory(cache_dir, max_age, max_files)
                    
                    if success:
                        dialog.destroy()
                        messagebox.showinfo("Cache Cleaned", f"Old cache files have been cleaned based on your settings.")
                        print("Cache cleaned successfully")
                    else:
                        messagebox.showwarning("Cache Clean", "No old cache files were found to clean.")
                except Exception as e:
                    print(f"Error cleaning cache: {e}")
                    messagebox.showerror("Error", f"Failed to clean cache: {str(e)}")
            
            # Buttons section
            buttons_frame = ctk.CTkFrame(frame, fg_color="transparent")
            buttons_frame.pack(pady=20)
            
            # Clear all button - FIXED
            ctk.CTkButton(
                buttons_frame, 
                text="Clear All Cache", 
                command=clear_all_cache,
                fg_color=self.theme_colors["danger"],
                hover_color="#c82333"
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
                clean_cache_directory(self.cache_dir, self.cache_max_age, self.cache_max_files)
            
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
        self.cache_dir = os.path.join(self.preview_dir, "cache")

        # Create these directories if they don't exist
        os.makedirs(self.preview_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        os.makedirs(self.info_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Define standard paths for key files
        self.gamedata_path = os.path.join(self.settings_dir, "gamedata.json")
        self.db_path = os.path.join(self.settings_dir, "gamedata.db")
        self.settings_path = os.path.join(self.settings_dir, "control_config_settings.json")
        
        # Return if the directories were created successfully
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

    # Add this to the on_closing method in the MAMEControlConfig class
    def on_closing(self):
        """Handle proper cleanup when closing the application"""
        print("Application closing, performing cleanup...")
        
        # Stop async loader
        if hasattr(self, 'async_loader'):
            self.async_loader.stop_worker()
        
        # Clear caches to free memory
        if hasattr(self, 'rom_data_cache'):
            self.rom_data_cache.clear()
        if hasattr(self, 'processed_cache'):
            self.processed_cache.clear()
        
        # Cancel any pending timers
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if attr_name.endswith('_timer') and hasattr(attr, 'cancel'):
                try:
                    attr.cancel()
                    print(f"Canceled timer: {attr_name}")
                except:
                    pass
        
        # Stop all worker threads - particularly important for Qt applications
        import threading
        running_threads = threading.enumerate()
        main_thread = threading.main_thread()
        
        for thread in running_threads:
            # Don't try to stop the main thread
            if thread is not main_thread and thread.is_alive():
                try:
                    thread.daemon = True  # Make sure thread won't prevent exit
                    print(f"Setting thread as daemon: {thread.name}")
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

    def toggle_fullscreen(self, event=None):
        """Toggle fullscreen state"""
        self.fullscreen = not self.fullscreen
        self.attributes('-fullscreen', self.fullscreen)
        
    def exit_fullscreen(self, event=None):
        """Exit fullscreen mode"""
        self.fullscreen = False
        self.attributes('-fullscreen', False)

    def create_layout(self):
        """Create the modern application layout with sidebar and content panels"""
        
        try:
            # Configure main grid with 2 columns (sidebar, main content) and 2 rows (content, toolbar)
            self.grid_columnconfigure(0, weight=0)     # Sidebar (fixed width)
            self.grid_columnconfigure(1, weight=1)     # Main content (expands)
            self.grid_rowconfigure(0, weight=1)        # Main content area (expands)
            self.grid_rowconfigure(1, weight=0)        # Bottom toolbar (fixed height)

            # Create main content frame first
            self.main_content = ctk.CTkFrame(self, fg_color=self.theme_colors["background"], corner_radius=0)
            self.main_content.grid(row=0, column=1, sticky="nsew")
            
            # Configure main content layout
            self.main_content.grid_columnconfigure(0, weight=1)
            self.main_content.grid_rowconfigure(0, weight=0)  # Top bar
            self.main_content.grid_rowconfigure(1, weight=1)  # Content area
            
            # Create top bar
            self.create_top_bar()
            
            # Create the split view for games list and control display
            self.create_split_view()
            
            # Now create sidebar - IMPORTANT: Create sidebar after game_list exists
            self.create_sidebar()
            
            # Create bottom toolbar spanning both columns
            self.create_bottom_toolbar()
            
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Layout Error", f"Failed to create layout: {e}")

    def create_bottom_toolbar(self):
        """Create bottom toolbar with app controls and file access buttons"""
        try:
            # Create toolbar frame spanning both sidebar and main content
            self.bottom_toolbar = ctk.CTkFrame(
                self, 
                height=50, 
                fg_color=self.theme_colors["card_bg"], 
                corner_radius=0
            )
            self.bottom_toolbar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
            self.bottom_toolbar.pack_propagate(False)  # Keep fixed height
            
            # Create left section for file operations
            left_section = ctk.CTkFrame(self.bottom_toolbar, fg_color="transparent")
            left_section.pack(side="left", fill="y", padx=15, pady=8)
            
            # ROM CFG button
            self.open_rom_cfg_button = ctk.CTkButton(
                left_section,
                text="Open ROM CFG",
                command=self.open_selected_rom_cfg,
                width=120,
                height=34,
                font=("Arial", 12),
                fg_color=self.theme_colors["primary"],
                hover_color="#218838",  # Darker green for hover
                corner_radius=4
            )
            self.open_rom_cfg_button.pack(side="left", padx=(0, 10))
            
            # Default CFG button  
            self.open_default_cfg_button = ctk.CTkButton(
                left_section,
                text="Open Default CFG",
                command=self.open_default_cfg,
                width=130,
                height=34,
                font=("Arial", 12),
                fg_color=self.theme_colors["secondary"],
                hover_color=self.theme_colors["primary"],
                corner_radius=4
            )
            self.open_default_cfg_button.pack(side="left", padx=(0, 10))
            
            # Add separator
            separator = ctk.CTkFrame(
                left_section, 
                width=2, 
                height=30, 
                fg_color=self.theme_colors["text_dimmed"]
            )
            separator.pack(side="left", padx=10)
            
            # Center section for status or additional controls (optional)
            center_section = ctk.CTkFrame(self.bottom_toolbar, fg_color="transparent")
            center_section.pack(side="left", fill="both", expand=True, padx=10, pady=8)
            
            # Status indicator (shows current ROM if selected)
            self.toolbar_status = ctk.CTkLabel(
                center_section,
                text="No ROM selected",
                font=("Arial", 11),
                text_color=self.theme_colors["text_dimmed"],
                anchor="w"
            )
            self.toolbar_status.pack(side="left", fill="x", expand=True, padx=10)
            
            # Create right section for app controls
            right_section = ctk.CTkFrame(self.bottom_toolbar, fg_color="transparent")
            right_section.pack(side="right", fill="y", padx=15, pady=8)
            
            # Restart app button
            self.restart_button = ctk.CTkButton(
                right_section,
                text="Refresh Data",  # Changed from "Restart App"
                command=self.restart_application,  # Keep the same command
                width=100,
                height=34,
                font=("Arial", 12),
                fg_color=self.theme_colors["secondary"],
                hover_color=self.theme_colors["primary"],
                corner_radius=4
            )
            self.restart_button.pack(side="right", padx=(10, 0))
            
            # Close app button
            self.close_button = ctk.CTkButton(
                right_section,
                text="Close App",
                command=self.close_application,
                width=90,
                height=34,
                font=("Arial", 12),
                fg_color=self.theme_colors["danger"],
                hover_color="#c82333",  # Darker red
                corner_radius=4
            )
            self.close_button.pack(side="right", padx=(10, 0))
            
            # Update ROM CFG button state based on current selection
            self.update_toolbar_status()
            
        except Exception as e:
            traceback.print_exc()

    def update_toolbar_status(self):
        """Update the toolbar status and button states based on current ROM selection"""
        try:
            if hasattr(self, 'current_game') and self.current_game:
                # Update status text
                self.toolbar_status.configure(text=f"Selected: {self.current_game}")
                
                # Check if ROM has a CFG file
                cfg_path = os.path.join(self.mame_dir, "cfg", f"{self.current_game}.cfg")
                if os.path.exists(cfg_path):
                    self.open_rom_cfg_button.configure(
                        text="Open ROM CFG",
                        state="normal",
                        fg_color=self.theme_colors["success"]  # Green for available
                    )
                else:
                    self.open_rom_cfg_button.configure(
                        text="No ROM CFG",
                        state="normal",
                        fg_color=self.theme_colors["text_dimmed"]  # Gray for not available
                    )
            else:
                # No ROM selected
                self.toolbar_status.configure(text="No ROM selected")
                self.open_rom_cfg_button.configure(
                    text="Open ROM CFG",
                    state="disabled",
                    fg_color=self.theme_colors["text_dimmed"]
                )
            
            # Check default CFG availability
            default_cfg_path = os.path.join(self.mame_dir, "cfg", "default.cfg")
            if os.path.exists(default_cfg_path):
                self.open_default_cfg_button.configure(
                    state="normal",
                    fg_color=self.theme_colors["secondary"]
                )
            else:
                self.open_default_cfg_button.configure(
                    state="disabled",
                    fg_color=self.theme_colors["text_dimmed"]
                )
                
        except Exception as e:
            print(f"Error updating toolbar status: {e}")

    def open_selected_rom_cfg(self):
        """Open the CFG file for the currently selected ROM in the default editor"""
        try:
            if not hasattr(self, 'current_game') or not self.current_game:
                messagebox.showinfo("No ROM Selected", "Please select a ROM first.")
                return
            
            cfg_path = os.path.join(self.mame_dir, "cfg", f"{self.current_game}.cfg")
            
            if not os.path.exists(cfg_path):
                messagebox.showinfo(
                    "CFG File Not Found", 
                    f"No CFG file found for {self.current_game}.\n\n"
                    f"Expected location: {cfg_path}\n\n"
                    f"CFG files are created by MAME when you customize controls in-game."
                )
                return
                # Ask if user wants to create the file
                '''if messagebox.askyesno(
                    "CFG File Not Found", 
                    f"No CFG file found for {self.current_game}.\n\n"
                    f"Would you like to create a new CFG file?\n\n"
                    f"This will create: {os.path.basename(cfg_path)}",
                    icon="question"
                ):
                    self.create_new_rom_cfg(cfg_path)
                return'''
            
            # Open the file in the default editor
            self.open_file_in_editor(cfg_path)
            
            # Update status
            self.update_status_message(f"Opened CFG file for {self.current_game}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open ROM CFG file:\n{str(e)}")

    def create_new_rom_cfg(self, cfg_path):
        """Create a new CFG file for the ROM with basic structure"""
        try:
            # Create a basic CFG structure
            cfg_content = '''<?xml version="1.0"?>
    <mameconfig version="10">
        <system name="{rom_name}">
            <input>
                <remap origcode="KEYCODE_5" newcode="KEYCODE_1" />
                <remap origcode="KEYCODE_6" newcode="KEYCODE_2" />
            </input>
        </system>
    </mameconfig>'''.format(rom_name=self.current_game)
            
            # Ensure cfg directory exists
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            
            # Write the file
            with open(cfg_path, 'w', encoding='utf-8') as f:
                f.write(cfg_content)
            
            # Open the newly created file
            self.open_file_in_editor(cfg_path)
            
            # Update toolbar
            self.update_toolbar_status()
            
            messagebox.showinfo(
                "CFG File Created", 
                f"Created new CFG file for {self.current_game}.\n\n"
                f"The file has been opened in your default editor."
            )
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create CFG file:\n{str(e)}")

    def open_default_cfg(self):
        """Open the default.cfg file in the default editor"""
        try:
            default_cfg_path = os.path.join(self.mame_dir, "cfg", "default.cfg")
            
            if not os.path.exists(default_cfg_path):
                messagebox.showwarning(
                    "Default CFG Not Found", 
                    f"Default CFG file not found at:\n{default_cfg_path}\n\n"
                    f"This file is typically created by MAME when you first run it."
                )
                return
            
            # Open the file in the default editor
            self.open_file_in_editor(default_cfg_path)
            
            # Update status
            self.update_status_message("Opened default.cfg file")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open default CFG file:\n{str(e)}")

    def open_file_in_editor(self, file_path):
        """Open a file in the system's default editor"""
        try:
            import subprocess
            import platform
            
            system = platform.system()
            
            if system == "Windows":
                # Windows - use start command
                subprocess.run(['start', '', file_path], shell=True, check=True)
            elif system == "Darwin":  # macOS
                # macOS - use open command
                subprocess.run(['open', file_path], check=True)
            elif system == "Linux":
                # Linux - use xdg-open
                subprocess.run(['xdg-open', file_path], check=True)
            else:
                # Fallback for other systems
                subprocess.run(['notepad', file_path] if system == "Windows" else ['nano', file_path], check=True)
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to open file with system editor: {e}")
        except FileNotFoundError:
            raise Exception("No suitable editor found on the system")
        except Exception as e:
            raise Exception(f"Unexpected error opening file: {e}")
    
    def restart_application(self):
        """Refresh the application data without restarting"""
        try:
            # Create splash window using existing method
            self.splash_window = self.create_splash_window()
            self.update_splash_message("Refreshing application data...")
            
            # Clear all caches
            if hasattr(self, 'rom_data_cache'):
                self.rom_data_cache.clear()
            if hasattr(self, 'processed_cache'):
                self.processed_cache.clear()
            
            # Update splash message
            self.update_splash_message("Reloading configurations...")
            
            # Reload default controls
            self.default_controls, self.original_default_controls = load_default_config(self.mame_dir)
            print(f"Reloaded {len(self.default_controls)} default controls")
            
            # Reload custom configs
            self.custom_configs = load_custom_configs(self.mame_dir)
            print(f"Reloaded {len(self.custom_configs)} custom configs")
            
            # Update splash message
            self.update_splash_message("Reloading game database...")
            
            # Reload gamedata.json
            self.gamedata_json, self.parent_lookup, self.clone_parents = load_gamedata_json(self.gamedata_path)
            print(f"Reloaded gamedata.json with {len(self.gamedata_json)} entries")
            
            # Update splash message
            self.update_splash_message("Rebuilding database...")
            
            # Check if database needs rebuilding
            if check_db_update_needed(self.gamedata_path, self.db_path):
                print("Rebuilding database...")
                build_gamedata_db(self.gamedata_json, self.db_path)
            
            # Update splash message
            self.update_splash_message("Scanning ROMs...")
            
            # Rescan available ROMs
            self.available_roms = scan_roms_directory(self.mame_dir)
            print(f"Found {len(self.available_roms)} ROMs")
            
            # Update splash message
            self.update_splash_message("Updating display...")
            
            # Store current selection
            current_selection = self.current_game if hasattr(self, 'current_game') else None
            current_view = self.current_view if hasattr(self, 'current_view') else 'all'
            
            # Update the game list
            self.update_game_list_by_category(auto_select_first=False)
            
            # Try to restore previous selection
            if current_selection and current_selection in self.available_roms:
                # Find and select the ROM in the list
                for i, (rom_name, _) in enumerate(self.game_list_data):
                    if rom_name == current_selection:
                        self.game_listbox.selection_clear(0, tk.END)
                        self.game_listbox.selection_set(i)
                        self.game_listbox.activate(i)
                        self.game_listbox.see(i)
                        self.current_game = rom_name
                        self.selected_line = i + 1
                        # Refresh the display
                        self.after(50, lambda: self.display_game_info(rom_name))
                        break
            
            # Update stats
            self.update_stats_label()
            
            # Close splash window
            if hasattr(self, 'splash_window') and self.splash_window:
                self.splash_window.destroy()
                self.splash_window = None
            
            # Show success message
            self.update_status_message("Application data refreshed successfully")
            
            # Show a brief notification
            messagebox.showinfo(
                "Refresh Complete",
                "All configuration files and game data have been reloaded.",
                parent=self
            )
            
        except Exception as e:
            # Make sure splash is closed on error
            if hasattr(self, 'splash_window') and self.splash_window:
                try:
                    self.splash_window.destroy()
                except:
                    pass
                self.splash_window = None
                
            messagebox.showerror("Refresh Error", f"Failed to refresh application:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def close_application(self):
        """Close the application"""
        try:
            self.on_closing()
                
        except Exception as e:
            # Force close even if there's an error
            try:
                self.destroy()
            except:
                pass

    def cleanup_before_exit(self):
        """Perform cleanup operations before exiting"""
        try:
            
            # Save current settings
            if hasattr(self, 'save_settings'):
                self.save_settings()
            
            # Stop async loader
            if hasattr(self, 'async_loader'):
                self.async_loader.stop_worker()
            
            # Cancel any pending timers
            for attr_name in dir(self):
                attr = getattr(self, attr_name)
                if attr_name.endswith('_timer') and hasattr(attr, 'cancel'):
                    try:
                        attr.cancel()
                    except:
                        pass
            
            # Terminate any preview processes
            if hasattr(self, 'preview_processes'):
                for process in self.preview_processes:
                    try:
                        process.terminate()
                    except:
                        pass
            
            
        except Exception as e:
            print(f"Error during cleanup: {e}")

    # ==============================================================================
    # NEW: DATABASE CONTROLS PANEL
    # ==============================================================================

    def create_database_controls_panel(self, parent_frame):
        """Create a panel for managing ALL gamedata.json entries (thousands of ROMs)"""
        
        # Main container frame with scrolling
        container = ctk.CTkScrollableFrame(
            parent_frame,
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        container.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Title and description
        header_frame = ctk.CTkFrame(container, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        header_frame.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            header_frame,
            text="Database Controls Manager",
            font=("Arial", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        description_text = (
            "Browse and manage ALL games in the gamedata.json database. "
            "This includes games you own and thousands of other arcade games. "
            "Use this to add control mappings for games you don't have yet."
        )
        
        ctk.CTkLabel(
            header_frame,
            text=description_text,
            font=("Arial", 13),
            justify="left",
            wraplength=750
        ).pack(anchor="w", padx=15, pady=(0, 15))
        
        # Statistics frame
        stats_frame = ctk.CTkFrame(container, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        stats_frame.pack(fill="x", padx=0, pady=(0, 15))
        
        # Calculate database statistics
        total_games_in_db = len(self.gamedata_json)
        total_clones_in_db = 0
        games_with_controls = 0
        games_without_controls = 0
        
        for rom_name, rom_data in self.gamedata_json.items():
            # Count clones
            if 'clones' in rom_data and isinstance(rom_data['clones'], dict):
                total_clones_in_db += len(rom_data['clones'])
            
            # Count games with/without controls
            if 'controls' in rom_data and rom_data['controls']:
                games_with_controls += 1
            else:
                games_without_controls += 1
        
        total_entries = total_games_in_db + total_clones_in_db
        
        stats_text = (
            f"Database Statistics:\n"
            f"• Total parent games: {total_games_in_db:,}\n"
            f"• Total clone games: {total_clones_in_db:,}\n"
            f"• Total database entries: {total_entries:,}\n"
            f"• Games with controls: {games_with_controls:,}\n"
            f"• Games without controls: {games_without_controls:,}\n"
            f"• Coverage: {(games_with_controls/max(total_games_in_db, 1)*100):.1f}%"
        )
        
        ctk.CTkLabel(
            stats_frame,
            text="Database Overview",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        ctk.CTkLabel(
            stats_frame,
            text=stats_text,
            font=("Arial", 13),
            justify="left"
        ).pack(anchor="w", padx=15, pady=(0, 15))
        
        # Action buttons frame
        actions_frame = ctk.CTkFrame(container, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        actions_frame.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            actions_frame,
            text="Database Actions",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Button grid
        button_grid = ctk.CTkFrame(actions_frame, fg_color="transparent")
        button_grid.pack(fill="x", padx=15, pady=(0, 15))
        
        # Row 1: Browse categories
        ctk.CTkButton(
            button_grid,
            text="Browse Games with Controls",
            command=lambda: self.show_database_category("with_controls"),
            width=200,
            height=40,
            fg_color=self.theme_colors["success"],
            hover_color="#218838"
        ).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        ctk.CTkButton(
            button_grid,
            text="Browse Games without Controls", 
            command=lambda: self.show_database_category("without_controls"),
            width=200,
            height=40,
            fg_color=self.theme_colors["warning"],
            hover_color="#e0a800"
        ).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Row 2: Search and advanced
        ctk.CTkButton(
            button_grid,
            text="Search All Games",
            command=self.show_database_search,
            width=200,
            height=40,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        
        ctk.CTkButton(
            button_grid,
            text="Browse Clone Games",
            command=lambda: self.show_database_category("clones"),
            width=200,
            height=40,
            fg_color=self.theme_colors["secondary"],
            hover_color=self.theme_colors["primary"]
        ).grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # Make grid columns expand evenly
        button_grid.columnconfigure(0, weight=1)
        button_grid.columnconfigure(1, weight=1)

    # ==============================================================================
    # DATABASE CATEGORY BROWSER
    # ==============================================================================

    def show_database_category(self, category):
        """Show a category of games from the database"""
        
        # Create new dialog for browsing
        browser = ctk.CTkToplevel(self)
        browser.title(f"Database Browser - {category.replace('_', ' ').title()}")
        browser.geometry("900x700")
        browser.transient(self)
        browser.grab_set()
        
        # Header
        header_frame = ctk.CTkFrame(browser, fg_color=self.theme_colors["primary"], height=60)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        ctk.CTkLabel(
            header_frame,
            text=f"Database Browser - {category.replace('_', ' ').title()}",
            font=("Arial", 18, "bold"),
            text_color="white"
        ).pack(side="left", padx=20, pady=15)
        
        # Search box in header
        search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(
            header_frame,
            width=200,
            placeholder_text="Search...",
            textvariable=search_var
        )
        search_entry.pack(side="right", padx=20, pady=15)
        
        # Main content area
        content_frame = ctk.CTkFrame(browser, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Results area with stats
        stats_label = ctk.CTkLabel(content_frame, text="Loading...", font=("Arial", 12))
        stats_label.pack(anchor="w", pady=(0, 10))
        
        # Game list with virtual scrolling
        list_frame = ctk.CTkFrame(content_frame)
        list_frame.pack(fill="both", expand=True)
        
        # Create the virtualized list
        game_listbox = tk.Listbox(
            list_frame,
            font=("Arial", 12),
            height=25,
            background=self.theme_colors["card_bg"],
            foreground=self.theme_colors["text"],
            selectbackground=self.theme_colors["primary"]
        )
        game_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        # Scrollbar
        scrollbar = ctk.CTkScrollbar(list_frame, orientation="vertical", command=game_listbox.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        game_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Populate the list based on category
        games_data = []
        
        if category == "with_controls":
            for rom_name, rom_data in self.gamedata_json.items():
                if 'controls' in rom_data and rom_data['controls']:
                    games_data.append({
                        'rom_name': rom_name,
                        'game_name': rom_data.get('description', rom_name),
                        'owned': rom_name in self.available_roms,
                        'has_controls': True
                    })
        
        elif category == "without_controls":
            for rom_name, rom_data in self.gamedata_json.items():
                if 'controls' not in rom_data or not rom_data['controls']:
                    games_data.append({
                        'rom_name': rom_name,
                        'game_name': rom_data.get('description', rom_name),
                        'owned': rom_name in self.available_roms,
                        'has_controls': False
                    })
        
        elif category == "clones":
            for parent_rom, parent_data in self.gamedata_json.items():
                if 'clones' in parent_data and isinstance(parent_data['clones'], dict):
                    for clone_rom, clone_data in parent_data['clones'].items():
                        games_data.append({
                            'rom_name': clone_rom,
                            'game_name': clone_data.get('description', clone_rom),
                            'owned': clone_rom in self.available_roms,
                            'parent': parent_rom,
                            'is_clone': True
                        })
        
        # Sort games alphabetically
        games_data.sort(key=lambda x: x['rom_name'])
        
        # Populate listbox (limit to first 1000 for performance)
        display_limit = 1000
        displayed_games = games_data[:display_limit]
        
        for game in displayed_games:
            status = "★" if game['owned'] else "○"
            rom_name = game['rom_name']
            game_name = game['game_name']
            
            if game.get('is_clone'):
                display_text = f"{status} {rom_name} - {game_name} [Clone of {game.get('parent', '')}]"
            else:
                display_text = f"{status} {rom_name} - {game_name}"
            
            game_listbox.insert(tk.END, display_text)
        
        # Update stats
        total_count = len(games_data)
        displayed_count = len(displayed_games)
        owned_count = sum(1 for game in games_data if game['owned'])
        
        stats_text = f"Total: {total_count:,} games | Displayed: {displayed_count:,} | You own: {owned_count:,}"
        if total_count > display_limit:
            stats_text += f" | Use search to find specific games"
        
        stats_label.configure(text=stats_text)
        
        # Bind double-click to edit
        def on_double_click(event):
            selection = game_listbox.curselection()
            if selection and selection[0] < len(displayed_games):
                game = displayed_games[selection[0]]
                rom_name = game['rom_name']
                browser.destroy()  # Close browser
                self.show_control_editor(rom_name)  # Open editor
        
        game_listbox.bind("<Double-Button-1>", on_double_click)
        
        # Search functionality
        def perform_search(*args):
            search_text = search_var.get().lower().strip()
            if not search_text:
                return
            
            # Filter games based on search
            filtered_games = [
                game for game in games_data 
                if search_text in game['rom_name'].lower() or search_text in game['game_name'].lower()
            ]
            
            # Update listbox
            game_listbox.delete(0, tk.END)
            
            display_filtered = filtered_games[:500]  # Limit search results
            for game in display_filtered:
                status = "★" if game['owned'] else "○"
                rom_name = game['rom_name']
                game_name = game['game_name']
                
                if game.get('is_clone'):
                    display_text = f"{status} {rom_name} - {game_name} [Clone of {game.get('parent', '')}]"
                else:
                    display_text = f"{status} {rom_name} - {game_name}"
                
                game_listbox.insert(tk.END, display_text)
            
            # Update displayed_games for double-click
            nonlocal displayed_games
            displayed_games = display_filtered
            
            # Update stats
            stats_label.configure(text=f"Search results: {len(filtered_games):,} games | Displayed: {len(display_filtered):,}")
        
        search_var.trace("w", perform_search)
        
        # Buttons
        button_frame = ctk.CTkFrame(browser, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        ctk.CTkButton(
            button_frame,
            text="Close",
            command=browser.destroy,
            width=100
        ).pack(side="right")
        
        # Instructions
        ctk.CTkLabel(
            button_frame,
            text="★ = Games you own | ○ = Available in database | Double-click to edit",
            font=("Arial", 11),
            text_color=self.theme_colors["text_dimmed"]
        ).pack(side="left")

    def show_database_search(self):
        """Show advanced search interface for all database games"""
        # This could be implemented as a more advanced search dialog
        # with multiple filters, etc. For now, just show the "without_controls" category
        # as that's probably what users want to search through most
        self.show_database_category("without_controls")
    
    def create_sidebar(self):
        """Create sidebar with enhanced category filters including specialized control types"""
        # Create sidebar frame
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=self.theme_colors["sidebar_bg"], corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)  # Prevent sidebar from resizing
        
        # App title/logo section
        title_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=60)
        title_frame.pack(fill="x", padx=0, pady=(10, 20))
        
        # App title with icon
        app_title = ctk.CTkLabel(
            title_frame, 
            text="MAME Controls",
            font=("Arial", 18, "bold"),
            text_color=self.theme_colors["text"]
        )
        app_title.pack(side="left", padx=(15, 0))
        
        # Sidebar tabs section
        tabs_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        tabs_frame.pack(fill="x", padx=0, pady=0)
        
        # Category divider
        category_label = ctk.CTkLabel(
            tabs_frame,
            text="CATEGORIES",
            font=("Arial", 11),
            text_color=self.theme_colors["text_dimmed"]
        )
        category_label.pack(anchor="w", padx=15, pady=(0, 5))
        
        # Define the sidebar tabs
        self.sidebar_tabs = {}
        
        # Helper function to set active tab
        def set_tab_active(tab_name):
            # Deactivate all tabs
            for name, tab in self.sidebar_tabs.items():
                tab.set_active(False)
            
            # Activate selected tab
            if tab_name in self.sidebar_tabs:
                self.sidebar_tabs[tab_name].set_active(True)
                
            # Update view based on tab
            self.current_view = tab_name
            if hasattr(self, 'game_listbox'):  # Only update if game_list exists
                self.update_game_list_by_category()
        
        # Add "All ROMs" tab
        self.sidebar_tabs["all"] = CustomSidebarTab(
            tabs_frame, 
            text="All Your ROMs",
            command=lambda: set_tab_active("all")
        )
        self.sidebar_tabs["all"].pack(fill="x", padx=5, pady=2)
        
        # Add "With Controls" tab
        self.sidebar_tabs["with_controls"] = CustomSidebarTab(
            tabs_frame, 
            text="Exist in Database",
            command=lambda: set_tab_active("with_controls")
        )
        self.sidebar_tabs["with_controls"].pack(fill="x", padx=5, pady=2)
        
        
        # ADD this NEW tab for Custom Actions:
        self.sidebar_tabs["custom_actions"] = CustomSidebarTab(
            tabs_frame, 
            text="Have Game Actions",               # NEW TAB
            command=lambda: set_tab_active("custom_actions")
        )
        self.sidebar_tabs["custom_actions"].pack(fill="x", padx=5, pady=2)
        
        # Add "Generic Controls" tab
        self.sidebar_tabs["generic"] = CustomSidebarTab(
            tabs_frame, 
            text="No Game Actions",
            command=lambda: set_tab_active("generic")
        )
        self.sidebar_tabs["generic"].pack(fill="x", padx=5, pady=2)
        
        # Add "Missing Controls" tab
        self.sidebar_tabs["missing"] = CustomSidebarTab(
            tabs_frame, 
            text="Missing from Database",
            command=lambda: set_tab_active("missing")
        )
        self.sidebar_tabs["missing"].pack(fill="x", padx=5, pady=2)
        
        # Add "Clone ROMs" tab
        self.sidebar_tabs["clones"] = CustomSidebarTab(
            tabs_frame, 
            text="Clones",
            command=lambda: set_tab_active("clones")
        )
        self.sidebar_tabs["clones"].pack(fill="x", padx=5, pady=2)
        
        # NEW CATEGORY: Special Controls section divider
        special_label = ctk.CTkLabel(
            tabs_frame,
            text="SPECIAL CONTROLS",
            font=("Arial", 11),
            text_color=self.theme_colors["text_dimmed"]
        )
        special_label.pack(anchor="w", padx=15, pady=(20, 5))
        
        # Add "No Buttons" tab
        self.sidebar_tabs["no_buttons"] = CustomSidebarTab(
            tabs_frame, 
            text="No Buttons",
            command=lambda: set_tab_active("no_buttons")
        )
        self.sidebar_tabs["no_buttons"].pack(fill="x", padx=5, pady=2)
        
        # Add "Specialized Input" tab
        self.sidebar_tabs["specialized"] = CustomSidebarTab(
            tabs_frame, 
            text="Specialized Input",
            command=lambda: set_tab_active("specialized")
        )
        self.sidebar_tabs["specialized"].pack(fill="x", padx=5, pady=2)
        
        # Add "Analog Controls" tab
        self.sidebar_tabs["analog"] = CustomSidebarTab(
            tabs_frame, 
            text="Analog Controls",
            command=lambda: set_tab_active("analog")
        )
        self.sidebar_tabs["analog"].pack(fill="x", padx=5, pady=2)
        
        # Add "Multi-Player" tab
        self.sidebar_tabs["multiplayer"] = CustomSidebarTab(
            tabs_frame, 
            text="Multi-Player",
            command=lambda: set_tab_active("multiplayer")
        )
        self.sidebar_tabs["multiplayer"].pack(fill="x", padx=5, pady=2)
        
        # Add "Single-Player" tab
        self.sidebar_tabs["singleplayer"] = CustomSidebarTab(
            tabs_frame, 
            text="Single-Player Only",
            command=lambda: set_tab_active("singleplayer")
        )
        self.sidebar_tabs["singleplayer"].pack(fill="x", padx=5, pady=2)
        
        # Tools section divider
        tools_label = ctk.CTkLabel(
            tabs_frame,
            text="TOOLS",
            font=("Arial", 11),
            text_color=self.theme_colors["text_dimmed"]
        )
        tools_label.pack(anchor="w", padx=15, pady=(20, 5))
        
        # Add this list to store references to tool buttons
        tools_buttons = []
        
        # Create function to handle tool button activation
        def activate_tool_button(button_index):
            # Deactivate all tool buttons
            for btn in tools_buttons:
                btn.set_active(False)
            
            # Activate the clicked button
            tools_buttons[button_index].set_active(True)
            
            # Reset after a delay (since tools just perform actions and don't change views)
            self.after(500, lambda: tools_buttons[button_index].set_active(False))
        
        # Add Tools buttons with activation
        tool_commands = [
            {"text": "Generate Config Files", "command": self.generate_all_configs},
            {"text": "Batch Export Images", "command": self.batch_export_images},
            {"text": "Analyze Controls", "command": self.analyze_controls},
            {"text": "Clear Cache", "command": self.clear_cache},
        ]
        
        for i, btn_config in enumerate(tool_commands):
            # Create a combined command that handles highlighting and the original command
            original_command = btn_config["command"]
            combined_command = lambda idx=i, cmd=original_command: (activate_tool_button(idx), cmd())
            
            # Create the button with the combined command
            btn = CustomSidebarTab(
                tabs_frame, 
                text=btn_config["text"],
                command=combined_command
            )
            btn.pack(fill="x", padx=5, pady=2)
            tools_buttons.append(btn)
        
        # Status section at bottom of sidebar
        self.status_frame = ctk.CTkFrame(self.sidebar, fg_color=self.theme_colors["card_bg"], corner_radius=6, height=80)
        self.status_frame.pack(fill="x", padx=15, pady=(20, 20), side="bottom")
        
        # CHANGE TO - add fixed width:
        self.stats_label = ctk.CTkLabel(
            self.status_frame, 
            text="Loading...",
            font=("Arial", 12), 
            text_color=self.theme_colors["text"],
            justify="left",
            anchor="w",
            width=200  # Fixed width prevents text length from affecting layout
        )
        self.stats_label.pack(padx=10, pady=10, fill="y")  # Remove fill="both", expand=True
        
        # Set initial active tab - but don't call update_game_list_by_category yet
        # (this will happen during load_all_data)
        self.sidebar_tabs["all"].set_active(True)
        self.current_view = "all"

    def create_top_bar(self):
        """Create top bar with control buttons - UPDATED with ROM source toggle"""
        self.top_bar = ctk.CTkFrame(self.main_content, height=60, fg_color=self.theme_colors["card_bg"], corner_radius=0)
        self.top_bar.grid(row=0, column=0, sticky="ew")
        
        # Prevent the top bar from resizing
        self.top_bar.pack_propagate(False)
        
        # Add collapse button
        collapse_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        collapse_frame.pack(side="left", padx=(10, 0), pady=10)
        
        self.collapse_button = ctk.CTkButton(
            collapse_frame,
            text="◀",  # Left arrow
            width=30,
            height=30,
            command=self.toggle_game_list,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"],
            corner_radius=15  # Make it round
        )
        self.collapse_button.pack(side="left")
        
        # Add search bar
        search_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        search_frame.pack(side="left", padx=20, pady=10)
        
        # Search icon label (using Unicode magnifying glass)
        search_icon = ctk.CTkLabel(search_frame, text="🔍", font=("Arial", 14))
        search_icon.pack(side="left", padx=(0, 5))
        
        # Search entry
        self.search_var = StringVar()
        self.search_var.trace("w", self.filter_games)
        
        self.search_entry = ctk.CTkEntry(
            search_frame,
            width=250,
            placeholder_text="Search ROMs...",
            textvariable=self.search_var,
            border_width=0
        )
        self.search_entry.pack(side="left", padx=0)
        
        # Add buttons on the right side
        toggle_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        toggle_frame.pack(side="right", padx=20, pady=10)
        
        # Preview button 
        self.preview_button = ctk.CTkButton(
            toggle_frame,
            text="Preview Controls",
            command=self.show_preview,
            fg_color=self.theme_colors["success"],
            hover_color="#218838",
            height=32
        )
        self.preview_button.pack(side="right", padx=10)
        
        # NEW: ROM Source Toggle (rightmost)
        self.rom_source_toggle = ctk.CTkSwitch(
            toggle_frame,
            text="Show All Games",
            command=self.toggle_rom_source,
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"]
        )
        # Set initial state based on settings
        if hasattr(self, 'rom_source_mode') and self.rom_source_mode == "database":
            self.rom_source_toggle.select()
        else:
            self.rom_source_toggle.deselect()
        
        self.rom_source_toggle.pack(side="right", padx=10)
        
        # Only show hide buttons toggle if feature is enabled
        if getattr(self, 'SHOW_HIDE_BUTTONS_TOGGLE', True):  # Default to True for backwards compatibility
            # Hide buttons toggle
            self.hide_buttons_toggle = ctk.CTkSwitch(
                toggle_frame,
                text="Hide Preview Buttons",
                command=self.toggle_hide_preview_buttons,
                button_color=self.theme_colors["primary"],
                button_hover_color=self.theme_colors["secondary"]
            )
            # Set initial state based on settings
            if hasattr(self, 'hide_preview_buttons') and self.hide_preview_buttons:
                self.hide_buttons_toggle.select()
            else:
                self.hide_buttons_toggle.deselect()
            
            self.hide_buttons_toggle.pack(side="right", padx=10)
    
    def toggle_rom_source(self):
        """Toggle between physical ROMs and database ROMs - FIXED VERSION"""
        try:
            # Cancel any pending display updates
            if hasattr(self, '_display_timer') and self._display_timer:
                self.after_cancel(self._display_timer)
                self._display_timer = None
            
            old_mode = self.rom_source_mode
            if self.rom_source_toggle.get():
                self.rom_source_mode = "database"
            else:
                self.rom_source_mode = "physical"
            
            if old_mode == self.rom_source_mode:
                return
            
            # NEW: Clear current selection to prevent selection events
            self.current_game = None
            
            # NEW: Temporarily disable selection events
            if hasattr(self, 'game_listbox'):
                # Clear listbox selection to prevent events
                self.game_listbox.selection_clear(0, tk.END)
                
                # Temporarily unbind selection events
                self.game_listbox.unbind("<ButtonRelease-1>")
                self.game_listbox.unbind("<Button-3>")
                self.game_listbox.unbind("<Double-Button-1>")
            
            # Load ROM set
            self.load_rom_set_for_current_mode()
            
            # Update game list WITHOUT auto-selecting first ROM
            self.update_game_list_by_category(auto_select_first=False)
            
            # Re-bind selection events
            if hasattr(self, 'game_listbox'):
                self.game_listbox.bind("<ButtonRelease-1>", self.on_rom_click_release)
                self.game_listbox.bind("<Button-3>", self.show_game_context_menu_listbox)
                self.game_listbox.bind("<Double-Button-1>", self.on_game_double_click)
            
            # Schedule single display update
            if hasattr(self, 'available_roms') and self.available_roms:
                self._display_timer = self.after(150, self._delayed_first_rom_select)
            else:
                self.current_game = None
                self.game_title.configure(text="No ROMs available")
                for widget in self.control_frame.winfo_children():
                    widget.destroy()
            
            self.update_stats_label()
            self.save_settings()
            
            mode_text = "all games in database" if self.rom_source_mode == "database" else "physical ROMs"
            self.update_status_message(f"Now showing {mode_text}")
            
        except Exception as e:
            print(f"Error toggling ROM source: {e}")
    
    def _delayed_first_rom_select(self):
        """Select first ROM with single display update - NO FLASH VERSION"""
        try:
            if hasattr(self, 'game_list_data') and self.game_list_data:
                first_rom, _ = self.game_list_data[0]
                
                # Check if this is the same ROM already selected
                if hasattr(self, 'current_game') and self.current_game == first_rom:
                    print(f"ROM {first_rom} already selected, skipping display update")
                    return
                
                self.current_game = first_rom
                
                # Update listbox selection
                self.game_listbox.selection_clear(0, tk.END)
                self.game_listbox.selection_set(0)
                self.game_listbox.activate(0)
                self.game_listbox.see(0)
                
                # GENTLE: Only update if we actually need to
                self.display_game_info(first_rom)
                print(f"SINGLE display_game_info call for {first_rom}")
        except Exception as e:
            print(f"Error in delayed ROM select: {e}")
    
    def load_rom_set_for_current_mode(self):
        """Load the appropriate ROM set based on current mode"""
        try:
            if self.rom_source_mode == "database":
                # Load all parent ROMs from gamedata.json
                self.load_database_roms()
                # Use database ROMs as available ROMs
                self.available_roms = self.database_roms.copy()
                print(f"Loaded {len(self.available_roms)} database ROMs")
            else:
                # Load physical ROMs from mame\roms directory
                self.available_roms = scan_roms_directory(self.mame_dir)
                print(f"Loaded {len(self.available_roms)} physical ROMs")
                
        except Exception as e:
            print(f"Error loading ROM set: {e}")
            import traceback
            traceback.print_exc()
    
    def load_database_roms(self):
        """Load all parent ROMs from gamedata.json (exclude clones)"""
        try:
            # Ensure gamedata is loaded
            if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
                self.load_gamedata_json()
            
            self.database_roms = set()
            
            # Add all parent ROMs (those that aren't clones themselves)
            for rom_name, game_data in self.gamedata_json.items():
                # Skip if this ROM is a clone (has 'parent' key)
                if 'parent' not in game_data:
                    self.database_roms.add(rom_name)
            
            print(f"Loaded {len(self.database_roms)} parent ROMs from database")
            
            # Sample output for debugging
            if len(self.database_roms) > 0:
                sample_roms = list(self.database_roms)[:5]
                print(f"Sample database ROMs: {sample_roms}")
                
        except Exception as e:
            print(f"Error loading database ROMs: {e}")
            import traceback
            traceback.print_exc()
            self.database_roms = set()
    
    # 2. Replace the create_split_view method with this version:
    def create_split_view(self):
        """Create split view with game list and control display panels with fixed proportions"""
        # Container frame for split view
        self.split_container = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.split_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        
        # Get initial window width - if window isn't sized yet, use a default
        window_width = self.winfo_width()
        if window_width < 100:
            window_width = 1280  # Default initial width
            
        # Calculate left panel width based on ratio with minimum constraint
        left_width = max(int(window_width * self.LEFT_PANEL_RATIO), self.MIN_LEFT_PANEL_WIDTH)
        
        # Configure grid with fixed proportions
        self.split_container.columnconfigure(0, minsize=left_width, weight=0)  # Fixed width for left panel
        self.split_container.columnconfigure(1, weight=1)  # Right panel takes remaining space
        self.split_container.rowconfigure(0, weight=1)  # Full height
        
        # Create the left and right panels
        self.create_game_list_panel(width=left_width)
        self.create_control_display_panel()
        
        # Prevent panels from resizing based on content
        if hasattr(self, 'left_panel'):
            self.left_panel.grid_propagate(False)
        if hasattr(self, 'right_panel'):
            self.right_panel.grid_propagate(False)
        
        # Register resize event handler
        self.bind("<Configure>", self.on_window_resize)

    # 4. Update on_window_resize method:
    def on_window_resize(self, event=None):
        """Handle window resize to maintain fixed panel proportions"""
        # Only process if this is the main window being resized
        if event and event.widget == self:
            window_width = event.width
            
            # Only handle significant resize events
            if window_width > 100:
                # Calculate the left panel width based on ratio
                left_width = int(window_width * self.LEFT_PANEL_RATIO)
                
                # Enforce minimum width
                if left_width < self.MIN_LEFT_PANEL_WIDTH:
                    left_width = self.MIN_LEFT_PANEL_WIDTH
                
                # Update container column configuration
                if hasattr(self, 'split_container'):
                    self.split_container.columnconfigure(0, minsize=left_width, weight=0)
                    
                    # Force immediate update of the layout
                    self.split_container.update_idletasks()
                    
                    # Directly configure panel widths
                    if hasattr(self, 'left_panel'):
                        self.left_panel.configure(width=left_width)
                    
                    # Ensure width is applied by forcing propagation off
                    if hasattr(self, 'left_panel'):
                        self.left_panel.grid_propagate(False)
                    if hasattr(self, 'right_panel'):
                        self.right_panel.grid_propagate(False)
                        
                    # Adjust game title wraplength
                    if hasattr(self, 'game_title'):
                        title_width = max(window_width - left_width - 200, 300)
                        self.game_title.configure(wraplength=title_width)

    # 5. Handle initial window size in a post-initialization method
    def after_init_setup(self):
        """Perform setup tasks after window initialization"""
        # Ensure settings are properly loaded
        self.load_settings()
        
        # Update toggle states based on loaded settings
        if hasattr(self, 'xinput_only_toggle'):
            if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
                self.xinput_only_toggle.select()
            else:
                self.xinput_only_toggle.deselect()
        # Use after() to ensure window is fully created
        self.after(100, self._apply_initial_panel_sizes)

    def _apply_initial_panel_sizes(self):
        """Apply initial panel sizes after window is fully initialized"""
        window_width = self.winfo_width()
        
        # Calculate initial left panel width
        left_width = max(int(window_width * self.LEFT_PANEL_RATIO), self.MIN_LEFT_PANEL_WIDTH)
        
        # Apply to column config
        if hasattr(self, 'split_container'):
            self.split_container.columnconfigure(0, minsize=left_width, weight=0)
            
        # Apply to panel directly
        if hasattr(self, 'left_panel'):
            self.left_panel.configure(width=left_width)
            self.left_panel.grid_propagate(False)
        
        # Force layout update
        self.update_idletasks()

    def create_game_list_panel(self, width=None):
        """Create the game list panel with a virtual list for better performance with improved styling"""
        # Set default width if not provided
        if width is None:
            width = self.MIN_LEFT_PANEL_WIDTH
                
        # Game list container with fixed width
        self.left_panel = ctk.CTkFrame(
            self.split_container, 
            corner_radius=0,
            fg_color=self.theme_colors["card_bg"],
            border_width=0,
            width=width  # Set explicit width
        )
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 10), pady=20)
        
        # Force fixed size
        self.left_panel.grid_propagate(False)
        
        # Configure layout
        self.left_panel.columnconfigure(0, weight=1)
        self.left_panel.rowconfigure(0, weight=0)  # Header
        self.left_panel.rowconfigure(1, weight=1)  # Game list
        
        # Panel header with title
        list_header = ctk.CTkFrame(self.left_panel, fg_color="transparent", height=40)
        list_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        
        # List title
        self.list_title_label = ctk.CTkLabel(
            list_header, 
            text="Available ROMs",
            font=("Arial", 14, "bold"),
            text_color=self.theme_colors["text"],  # Match the text color
            anchor="w"
        )
        self.list_title_label.pack(side="left", padx=5)
        
        # Create the game list frame
        self.game_list_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.game_list_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Use a tkinter Listbox with enhanced custom styling inside a Frame
        # Create a frame with the card_bg color
        list_container = tk.Frame(
            self.game_list_frame, 
            background=self.theme_colors["card_bg"]  # Match the card background color
        )
        list_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create a Listbox with improved styling
        self.game_listbox = tk.Listbox(
            list_container,
            background=self.theme_colors["card_bg"],     # Grey background
            #foreground=self.theme_colors["text_grey"],                        # Softer grey text instead of bright white
            foreground="white",                        # White text
            font=("Arial", 12),                          # Smaller font (13 instead of 14, no bold)
            activestyle="none",                     
            selectbackground=self.theme_colors["primary"],  
            selectforeground="white",               
            relief="flat",                          
            highlightthickness=0,                   
            borderwidth=0,                          
            exportselection=False                   
        )
        # Add left padding to prevent text from being cut off
        self.game_listbox.pack(side="left", fill="both", expand=True, padx=(10, 0))
        
        # Create a custom CTkScrollbar that matches the theme
        scrollbar_frame = ctk.CTkFrame(list_container, fg_color="transparent", width=22)
        scrollbar_frame.pack(side="right", fill="y", padx=(2, 4))
        
        # Custom CTk scrollbar with improved styling
        game_scrollbar = ctk.CTkScrollbar(
            scrollbar_frame,
            orientation="vertical",
            button_color=self.theme_colors["primary"],         # Primary color for scrollbar thumb
            button_hover_color=self.theme_colors["secondary"], # Secondary color for hover
            fg_color=self.theme_colors["card_bg"],            # Background color matching panel
            corner_radius=10,                                 # Enhanced rounded corners
            width=14                                          # Make it slightly narrower
        )
        game_scrollbar.pack(fill="y", expand=True)
        
        # Connect scrollbar to listbox (need a custom function to bridge CTkScrollbar to Listbox)
        def on_listbox_scroll(*args):
            game_scrollbar.set(*args)
            
        def on_scrollbar_move(value):
            self.game_listbox.yview_moveto(value)
        
        self.game_listbox.configure(yscrollcommand=on_listbox_scroll)
        game_scrollbar.configure(command=self.game_listbox.yview)
        
        # Bind events with debouncing to prevent selection issues
        # Replace direct event binding with debounced version
        def on_selection_change(event):
            if hasattr(self, '_selection_timer') and self._selection_timer:
                self.after_cancel(self._selection_timer)
            self._selection_timer = self.after(50, lambda: self.on_game_select_from_listbox(event))

        self.game_listbox.bind("<ButtonRelease-1>", self.on_rom_click_release)
        self.game_listbox.bind("<Button-3>", self.show_game_context_menu_listbox)  # Right-click menu
        self.game_listbox.bind("<Double-Button-1>", self.on_game_double_click)     # Double-click to preview
        
        # Store references to helper properties
        self.highlight_tag = "highlight"  # Keep for compatibility
        self.selected_line = None  # Keep for compatibility
        
        # Store the list data
        self.game_list_data = []  # Will hold (rom_name, display_text) tuples

    def on_rom_click_release(self, event):
        widget = event.widget
        try:
            index = widget.nearest(event.y)
            if index >= 0:
                widget.selection_clear(0, tk.END)
                widget.selection_set(index)
                widget.activate(index)

                rom_name = widget.get(index)
                self.on_game_select_from_listbox(event)
        except Exception as e:
            print(f"Error handling ROM click: {e}")

    
    def on_game_select_from_listbox(self, event):
        """Handle game selection from listbox with improved stability and NO duplicate calls"""
        try:
            # Check if selection is active
            if not self.game_listbox.winfo_exists():
                return
                    
            # Get selected index - carefully handle empty selection
            selected_indices = self.game_listbox.curselection()
            if not selected_indices:
                return
                        
            index = selected_indices[0]
            
            # Ensure index is valid for our data list
            if index < len(self.game_list_data):
                rom_name, display_text = self.game_list_data[index]
                
                # Check if this is actually a change in selection
                if self.current_game == rom_name:
                    return  # Skip processing if no change
                        
                # Store the selected ROM
                self.current_game = rom_name
                
                # Update toolbar status immediately
                if hasattr(self, 'update_toolbar_status'):
                    self.update_toolbar_status()

                # Store selected line (for compatibility)
                self.selected_line = index + 1
                
                # CRITICAL FIX: Check processed cache first to avoid duplicate work
                cache_key = f"{rom_name}_{self.input_mode}"
                
                if hasattr(self, 'processed_cache') and cache_key in self.processed_cache:
                    # Use cached processed data - no duplicate calls!
                    print(f"Using processed cache for {rom_name}")
                    processed_data = self.processed_cache[cache_key]
                    self.after(10, lambda: self.display_game_info(rom_name, processed_data))
                else:
                    # Load and process data once, then cache it
                    self.after(10, lambda: self.display_game_info(rom_name))
                
                # Explicitly maintain selection (prevents flickering)
                self.after(20, lambda idx=index: self.game_listbox.selection_set(idx))
                
                # Ensure listbox still has focus
                self.after(30, lambda: self.game_listbox.focus_set())
            
        except Exception as e:
            print(f"Error selecting game from listbox: {e}")
            import traceback
            traceback.print_exc()

    def on_game_double_click(self, event):
        """Handle double-click on game list item to preview controls"""
        # Get the current selection
        selected_indices = self.game_listbox.curselection()
        if not selected_indices:
            return
            
        index = selected_indices[0]
        if index < len(self.game_list_data):
            rom_name, _ = self.game_list_data[index]
            self.current_game = rom_name
            self.show_preview()

    def create_control_display_panel(self):
        """Create the control display panel with fixed proportions and consistent alignment"""
        # Control display container with fixed proportions
        self.right_panel = ctk.CTkFrame(
            self.split_container, 
            corner_radius=0,
            fg_color=self.theme_colors["card_bg"],
            border_width=0
        )
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
        
        # Prevent resizing based on content
        self.right_panel.grid_propagate(False)
        
        # Configure the control display panel
        self.right_panel.columnconfigure(0, weight=1)
        self.right_panel.rowconfigure(0, weight=0)  # Header
        self.right_panel.rowconfigure(1, weight=1)  # Control content
        
        # Create header with game title - FIXED PADDING TO MATCH CONTENT BELOW
        title_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent", height=40)
        title_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 0))
        
        # Game title label - FIXED ALIGNMENT AND PADDING 
        self.game_title = ctk.CTkLabel(
            title_frame, 
            text="Select a game",
            font=("Arial", 18, "bold"),
            anchor="w",
            justify="left"
        )
        self.game_title.pack(side="left", fill="x", expand=True, padx=0)  # Explicit padx=0 to ensure no extra padding
        
        # Create scrollable frame for controls with enhanced styling
        self.control_frame_container = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.control_frame_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # Control frame
        self.control_frame = ctk.CTkScrollableFrame(
            self.control_frame_container,
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        self.control_frame.pack(fill="both", expand=True, padx=5, pady=5)

    def edit_current_game_controls(self):
        """Edit controls for the currently selected game"""
        if self.current_game:
            self.show_control_editor(self.current_game)
        else:
            messagebox.showinfo("No Game Selected", "Please select a game first.")
    
    def preview_rom_controls(self, rom_name):
        """Preview controls for a specific ROM with proper handling of prefixes"""
        # Clean the ROM name in case it has prefixes
        if rom_name:
                
            # Strip any leading/trailing whitespace
            rom_name = rom_name.strip()
            
            print(f"Previewing ROM with cleaned name: '{rom_name}'")
        
        # Save current game
        previous_game = self.current_game
        
        # Temporarily set the current game to the selected one
        self.current_game = rom_name
        
        # Call the preview function
        self.show_preview()
        
        # Restore previous game selection
        self.current_game = previous_game

    def show_custom_config(self, rom_name):
        """Display custom configuration for a ROM"""
        if rom_name not in self.custom_configs:
            messagebox.showinfo("No Custom Config", 
                            f"No custom configuration found for {rom_name}")
            return
        
        # Create a dialog window
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Custom Configuration: {rom_name}")
        dialog.geometry("800x600")
        dialog.transient(self)
        dialog.grab_set()
        
        # Create a frame for the content
        frame = ctk.CTkFrame(dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Add a title
        ctk.CTkLabel(
            frame,
            text=f"Custom Configuration for {rom_name}",
            font=("Arial", 16, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        # Add a scrollable text area for the config
        config_text = ctk.CTkTextbox(frame, font=("Consolas", 12))
        config_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Insert the configuration text
        config_text.insert("1.0", self.custom_configs[rom_name])
        config_text.configure(state="disabled")  # Make read-only
        
        # Add a close button
        ctk.CTkButton(
            frame,
            text="Close",
            command=dialog.destroy,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).pack(pady=(10, 0))

    def update_game_list_by_category(self, auto_select_first=True):
        previously_selected_rom = None
        if not auto_select_first and hasattr(self, 'current_game'):
            previously_selected_rom = self.current_game
        
        # Get all ROMs
        available_roms = sorted(self.available_roms)
        
        # Prepare lists for different categories
        with_controls = []
        missing_controls = []
        with_custom_config = []
        generic_controls = []
        custom_actions_roms = []
        clone_roms = []
        
        # NEW CATEGORIES
        no_buttons_roms = []
        specialized_roms = []
        analog_roms = []
        multiplayer_roms = []
        singleplayer_roms = []
        
        # Build parent->clone lookup if needed
        if not hasattr(self, 'parent_lookup') or not self.parent_lookup:
            self.parent_lookup = {}
            
            # Load gamedata.json if needed
            if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
                self.load_gamedata_json()
                
            # Build parent->clones mapping
            for parent_rom, parent_data in self.gamedata_json.items():
                if 'clones' in parent_data and isinstance(parent_data['clones'], dict):
                    for clone_rom in parent_data['clones'].keys():
                        self.parent_lookup[clone_rom] = parent_rom
                        clone_roms.append(clone_rom)
        
        # Process and categorize ROMs using the FIXED categorization
        for rom in available_roms:
            # Check if ROM is a clone
            if rom not in clone_roms and rom in self.parent_lookup:
                clone_roms.append(rom)
                
            # Check if ROM has custom config
            has_custom = rom in self.custom_configs
            if has_custom:
                with_custom_config.append(rom)
            
            # Use the FIXED categorization method
            categories = self.categorize_controls_properly(rom)
            
            if categories['has_controls']:
                with_controls.append(rom)
                
                # FIXED: Now properly distinguishes between generic and custom
                if categories['has_generic_controls']:
                    generic_controls.append(rom)
                elif categories['has_custom_controls']:
                    custom_actions_roms.append(rom)
                
                # Get game data for additional categorization
                from mame_data_utils import get_game_data
                game_data = get_game_data(rom, self.gamedata_json, self.parent_lookup, 
                                        self.db_path, getattr(self, 'rom_data_cache', {}))
                if game_data:
                    # Player count categorization
                    player_count = int(game_data.get('numPlayers', 1))
                    if player_count == 1:
                        singleplayer_roms.append(rom)
                    elif player_count > 1:
                        multiplayer_roms.append(rom)
                    
                    # Control type analysis
                    has_specialized = False
                    has_analog = False
                    has_buttons = False
                    
                    specialized_types = [
                        "TRACKBALL", "LIGHTGUN", "MOUSE", "DIAL", "PADDLE", 
                        "POSITIONAL", "GAMBLE", "AD_STICK"
                    ]
                    
                    analog_types = [
                        "AD_STICK", "DIAL", "PADDLE", "PEDAL", "POSITIONAL"
                    ]
                    
                    # Check each player's controls
                    for player in game_data.get('players', []):
                        for label in player.get('labels', []):
                            control_name = label['name']
                            
                            if "BUTTON" in control_name:
                                has_buttons = True
                            
                            for specialized_type in specialized_types:
                                if specialized_type in control_name:
                                    has_specialized = True
                                    break
                                    
                            for analog_type in analog_types:
                                if analog_type in control_name:
                                    has_analog = True
                                    break
                    
                    if has_specialized:
                        specialized_roms.append(rom)
                    if has_analog:
                        analog_roms.append(rom)
                    if not has_buttons:
                        no_buttons_roms.append(rom)
            else:
                missing_controls.append(rom)
        
        # Filter list based on current view
        display_roms = []
        if self.current_view == "all":
            display_roms = available_roms
        elif self.current_view == "with_controls":
            display_roms = with_controls
        elif self.current_view == "missing":
            display_roms = missing_controls
        elif self.current_view == "custom_config":
            display_roms = with_custom_config
        elif self.current_view == "generic":
            display_roms = generic_controls
        elif self.current_view == "clones":
            display_roms = sorted(clone_roms)
        elif self.current_view == "custom_actions":
            display_roms = custom_actions_roms
        elif self.current_view == "no_buttons":
            display_roms = no_buttons_roms
        elif self.current_view == "specialized":
            display_roms = specialized_roms
        elif self.current_view == "analog":
            display_roms = analog_roms
        elif self.current_view == "multiplayer":
            display_roms = multiplayer_roms
        elif self.current_view == "singleplayer":
            display_roms = singleplayer_roms
        
        # Apply search filter if needed
        search_text = ""
        if hasattr(self, 'search_var'):
            search_text = self.search_var.get().lower().strip()
        
        if search_text:
            filtered_roms = self._filter_rom_list(display_roms, search_text)
            display_roms = filtered_roms
        
        # Build the list data
        self.game_list_data = []
        list_display_items = []
        
        # Check if we have any ROMs to display
        if not display_roms:
            # Clear the listbox and set a message
            self.game_listbox.delete(0, tk.END)
            self.game_listbox.insert(tk.END, "No matching ROMs found.")
            return
        
        # Build display items for each ROM
        for rom in display_roms:
            # Determine display format
            has_config = rom in self.custom_configs
            has_data = self.get_game_data(rom) is not None
            is_clone = rom in self.parent_lookup if hasattr(self, 'parent_lookup') else False
            
            # Create display text with consistent clone formatting
            if is_clone and (self.current_view == "clones" or self.current_view == "all"):
                parent_rom = self.parent_lookup.get(rom, "")
                
                # Get the CLONE's description, not the parent's
                if has_data:
                    from mame_data_utils import get_game_data
                    game_data = get_game_data(rom, self.gamedata_json, self.parent_lookup, 
                                            self.db_path, getattr(self, 'rom_data_cache', {}))
                    
                    # Use clone's own description if available, otherwise fall back to ROM name
                    clone_description = game_data.get('gamename', rom)
                    
                    # Check if this is the clone's own description or inherited from parent
                    if rom in self.gamedata_json:
                        clone_description = self.gamedata_json[rom].get('description', rom)
                    elif parent_rom in self.gamedata_json and 'clones' in self.gamedata_json[parent_rom]:
                        clone_data = self.gamedata_json[parent_rom]['clones'].get(rom, {})
                        clone_description = clone_data.get('description', rom)
                    
                    display_text = f"{rom} - {clone_description} [Clone of {parent_rom}]"
                else:
                    display_text = f"{rom} [Clone of {parent_rom}]"
            else:
                # Regular display for non-clones
                if has_data:
                    if hasattr(self, 'name_cache') and rom in self.name_cache:
                        game_name = self.name_cache[rom].capitalize()
                        display_text = f"{rom} - {game_name}"
                    else:
                        from mame_data_utils import get_game_data
                        game_data = get_game_data(rom, self.gamedata_json, self.parent_lookup, 
                                                self.db_path, getattr(self, 'rom_data_cache', {}))
                        
                        # For clones not in clone view, use their own description
                        if is_clone and rom in self.gamedata_json:
                            clone_desc = self.gamedata_json[rom].get('description', game_data['gamename'])
                            display_text = f"{rom} - {clone_desc}"
                        else:
                            display_text = f"{rom} - {game_data['gamename']}"
                else:
                    display_text = f"{rom}"
            
            # Store both the ROM name and display text
            self.game_list_data.append((rom, display_text))
            list_display_items.append(display_text)
        
        # Update the listbox
        self.game_listbox.delete(0, tk.END)
        for item in list_display_items:
            self.game_listbox.insert(tk.END, item)
        
        # Handle ROM selection
        if auto_select_first and display_roms:
            # Auto-select first ROM when switching categories
            first_rom, _ = self.game_list_data[0]
            self.current_game = first_rom
            self.selected_line = 1
            
            # Select in listbox
            self.game_listbox.selection_clear(0, tk.END)
            self.game_listbox.selection_set(0)
            self.game_listbox.see(0)
            
            # Display ROM info after a brief delay to ensure UI is ready
            self.after(50, lambda: self.display_game_info(first_rom))
            
        elif previously_selected_rom:
            # Try to select the previously selected ROM if it's still in the list
            for i, (rom_name, _) in enumerate(self.game_list_data):
                if rom_name == previously_selected_rom:
                    # We found the previously selected ROM, select it again
                    self.game_listbox.selection_clear(0, tk.END)
                    self.game_listbox.selection_set(i)
                    self.game_listbox.see(i)
                    self.current_game = rom_name
                    self.selected_line = i + 1
                    
                    # Force a refresh of the display after a short delay
                    self.after(50, lambda: self.display_game_info(rom_name))
                    break
        
        # Update the title based on current view
        view_titles = {
            "all": "All ROMs",
            "with_controls": "ROMs with Controls",
            "missing": "ROMs Missing Controls",
            "custom_config": "ROMs with Custom Config",
            "generic": "ROMs with Generic Controls",
            "custom_actions": "ROMs with Custom Actions",
            "clones": "Clone ROMs",
            "no_buttons": "ROMs with No Buttons",
            "specialized": "Specialized Input",
            "analog": "Analog Controls",
            "multiplayer": "Multi-Player ROMs",
            "singleplayer": "Single-Player ROMs"
        }
        
        # Update the list panel title if method exists
        if hasattr(self, 'update_list_title'):
            self.update_list_title(f"{view_titles.get(self.current_view, 'ROMs')} ({len(display_roms)})")

    def update_list_title(self, title_text):
        """Update the title of the game list panel"""
        if hasattr(self, 'list_title_label'):
            self.list_title_label.configure(text=title_text)
        else:
            # Fallback for backward compatibility
            for widget in self.left_panel.winfo_children():
                if isinstance(widget, ctk.CTkFrame) and widget.winfo_y() < 50:  # Header is at the top
                    for child in widget.winfo_children():
                        if isinstance(child, ctk.CTkLabel):
                            child.configure(text=title_text)
                            return
    
    def display_no_control_data(self, rom_name):
        """Display no control data message efficiently"""
        self.game_title.configure(text=f"No control data: {rom_name}")
        
        # Clear existing controls
        for widget in self.control_frame.winfo_children():
            widget.destroy()
        
        # Create a card to show the missing data
        missing_card = ctk.CTkFrame(
            self.control_frame, 
            fg_color=self.theme_colors["card_bg"], 
            corner_radius=6
        )
        missing_card.pack(fill="x", padx=10, pady=10)
        
        # Title
        ctk.CTkLabel(
            missing_card,
            text="No Control Data Available",
            font=("Arial", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Message
        ctk.CTkLabel(
            missing_card,
            text=f"The ROM '{rom_name}' doesn't have any control configuration data.",
            font=("Arial", 13)
        ).pack(anchor="w", padx=15, pady=(0, 5))
        
        # Debug info
        has_rom_cfg = rom_name in self.custom_configs 
        has_default_cfg = hasattr(self, 'default_controls') and bool(self.default_controls)
        
        debug_info = f"ROM-specific CFG: {'Yes' if has_rom_cfg else 'No'}\n"
        debug_info += f"Default CFG: {'Yes' if has_default_cfg else 'No'}\n" 
        debug_info += f"Gamedata.json: {'Yes' if rom_name in self.gamedata_json else 'No'}"
        
        ctk.CTkLabel(
            missing_card,
            text=debug_info,
            font=("Arial", 11),
            text_color=self.theme_colors["text_dimmed"]
        ).pack(anchor="w", padx=15, pady=(5, 5))
        
        # Add button to create controls - only if adding new games is allowed
        if self.ALLOW_ADD_NEW_GAME:  # or if False: to disable
            add_button = ctk.CTkButton(
                missing_card,
                text="Add Control Configuration",
                command=lambda r=rom_name: self.show_control_editor(r),
                fg_color=self.theme_colors["primary"],
                hover_color=self.theme_colors["button_hover"],
                height=35
            )
            add_button.pack(anchor="w", padx=15, pady=(5, 15))
    
    def save_processed_cache_to_disk(self, rom_name, game_data):
        """Save processed data to disk cache without blocking UI"""
        try:
            if not hasattr(self, 'cache_dir') or not self.cache_dir:
                return
                
            cache_path = os.path.join(self.cache_dir, f"{rom_name}_cache.json")
            
            # Create cache directory if needed
            os.makedirs(self.cache_dir, exist_ok=True)
            
            # Save to disk
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(game_data, f, indent=2)
                
            print(f"Saved processed cache for {rom_name}")
            
        except Exception as e:
            print(f"Warning: Could not save cache for {rom_name}: {e}")
    
    def display_game_info(self, rom_name, processed_data=None):
        """Display game information and controls - WITH STARTUP GUARD"""
        try:     
            print(f"DEBUG display_game_info: Starting for {rom_name}, input_mode={self.input_mode}")
            
            # Update toolbar status when a new ROM is selected
            if hasattr(self, 'update_toolbar_status'):
                self.update_toolbar_status()
            
            # Initialize processed cache if it doesn't exist
            if not hasattr(self, 'processed_cache'):
                self.processed_cache = {}
            
            cache_key = f"{rom_name}_{self.input_mode}"
            
            # Initialize cfg_controls for all code paths
            cfg_controls = {}
            
            # Use provided processed data or get from cache or process fresh
            if processed_data:
                game_data = processed_data
                self.processed_cache[cache_key] = processed_data
            elif cache_key in self.processed_cache:
                print(f"Using cached processed data for {rom_name}")
                game_data = self.processed_cache[cache_key]
            else:
                print(f"Processing fresh data for {rom_name}")
                # Get raw game data ONCE
                game_data = self.get_game_data(rom_name)
                
                if not game_data:
                    self.display_no_control_data(rom_name)
                    return

                # IMPORTANT: Apply custom mappings ONCE here
                if rom_name in self.custom_configs:
                    cfg_controls = parse_cfg_controls(self.custom_configs[rom_name], self.input_mode)
                    cfg_controls = {
                        control: convert_mapping(mapping, self.input_mode)
                        for control, mapping in cfg_controls.items()
                    }

                # Apply all processing ONCE
                game_data = update_game_data_with_custom_mappings(
                    game_data, 
                    cfg_controls, 
                    getattr(self, 'default_controls', {}),
                    getattr(self, 'original_default_controls', {}),
                    self.input_mode
                )

                # Apply XInput filtering if enabled
                if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
                    game_data = filter_xinput_controls(game_data)
                
                # Cache the processed result
                self.processed_cache[cache_key] = game_data
                
                # Save to disk cache asynchronously
                self.after_idle(lambda: self.save_processed_cache_to_disk(rom_name, game_data))

            # For cached data, we need to regenerate cfg_controls if it exists
            if not cfg_controls and rom_name in self.custom_configs:
                cfg_controls = parse_cfg_controls(self.custom_configs[rom_name], self.input_mode)
                cfg_controls = {
                    control: convert_mapping(mapping, self.input_mode)
                    for control, mapping in cfg_controls.items()
                }

            # Now display using the processed data
            current_mode = getattr(self, 'input_mode', 'xinput' if self.use_xinput else 'joycode')
            print(f"Display game info using input mode: {current_mode}")

            # Update game title
            source_text = f" ({game_data.get('source', 'unknown')})"
            title_text = f"{game_data['gamename']}{source_text}"
            self.game_title.configure(text=title_text)
            
            # Clear existing display
            for widget in self.control_frame.winfo_children():
                widget.destroy()
            
            # Display controls with processed data (no more duplicate processing)
            row = 0
            self.display_controls_table(row, game_data, cfg_controls)
            
        except Exception as e:
            print(f"Error displaying game info: {e}")
            import traceback
            traceback.print_exc()

    def show_game_context_menu_listbox(self, event):
        """Show context menu on right-click for ROM entries in listbox"""
        try:
            # Get the clicked item index
            clicked_index = self.game_listbox.nearest(event.y)
            
            # Clear selection and select the clicked item
            self.game_listbox.selection_clear(0, tk.END)
            self.game_listbox.selection_set(clicked_index)
            self.game_listbox.activate(clicked_index)
            
            # Get ROM name from our data list
            if clicked_index < len(self.game_list_data):
                rom_name, display_text = self.game_list_data[clicked_index]
                #rom_name, display_text = self.game_list_data[index]
                
                # DEBUGGING: Print raw line content
                print(f"Context menu for ROM: '{rom_name}'")
                
                # Check if this is a clone ROM
                is_clone = rom_name in self.parent_lookup if hasattr(self, 'parent_lookup') else False
                parent_rom = self.parent_lookup.get(rom_name) if is_clone else None
                
                # Create context menu
                context_menu = tk.Menu(self, tearoff=0)
                
               # Add menu items - only show Edit Controls if adding new games is allowed
                if self.ALLOW_ADD_NEW_GAME:
                    if is_clone and parent_rom:
                        # For clones, show different edit option that redirects to parent
                        context_menu.add_command(label=f"Edit Controls (Parent: {parent_rom})", 
                                            command=lambda: self.show_control_editor(rom_name))
                    else:
                        # Regular edit option for non-clones
                        context_menu.add_command(label="Edit Controls", 
                                            command=lambda: self.show_control_editor(rom_name))
                
                # Preview controls is always available
                context_menu.add_command(label="Preview Controls", 
                                    command=lambda: self.preview_rom_controls(rom_name))
                
                context_menu.add_separator()
                
                # Check if ROM has custom config
                has_custom_config = rom_name in self.custom_configs
                
                if has_custom_config:
                    context_menu.add_command(label="View Custom Config", 
                                        command=lambda: self.show_custom_config(rom_name))
                
                context_menu.add_command(label="Clear Cache for this ROM", 
                                    command=lambda: self.perform_cache_clear(None, all_files=False, rom_name=rom_name))
                
                # Display the context menu
                context_menu.tk_popup(event.x_root, event.y_root)
        
        except Exception as e:
            print(f"Error showing context menu: {e}")
            import traceback
            traceback.print_exc()
    
    def _get_category_roms(self):
        """Get the ROM list for the current category without any search filtering"""
        # Get all ROMs
        available_roms = sorted(self.available_roms)
            
        # Prepare lists for different categories
        with_controls = []
        missing_controls = []
        with_custom_config = []
        generic_controls = []
        clone_roms = []
        
        # We'll only load the necessary category data based on current view
        if self.current_view == "all":
            return available_roms
        elif self.current_view == "clones":
            # Just return list from parent_lookup
            if hasattr(self, 'parent_lookup'):
                return sorted(self.parent_lookup.keys())
            return []
        elif self.current_view == "custom_config":
            # These we can get directly
            return sorted(self.custom_configs.keys())
        
       # For these categories we need to check each ROM's data
        for rom in available_roms:
            # Quick check for category - only load data if absolutely necessary
            if self.current_view == "with_controls":
                # Check if ROM has cached data or exists in database
                if rom in self.rom_data_cache or rom_exists_in_db(rom, self.db_path):
                    with_controls.append(rom)
                
            elif self.current_view == "missing":
                # Opposite of with_controls
                if rom not in self.rom_data_cache and not rom_exists_in_db(rom, self.db_path):
                    missing_controls.append(rom)
                    
            elif self.current_view == "generic":
                # This requires actual data inspection, more expensive
                game_data = get_game_data(rom, self.gamedata_json, self.parent_lookup, 
                                        self.db_path, getattr(self, 'rom_data_cache', {}))
                if not game_data:
                    continue
                    
                # Check if controls are generic
                has_custom_controls = False
                for player in game_data.get('players', []):
                    for label in player.get('labels', []):
                        action = label['value']
                        # Standard generic actions
                        generic_actions = [
                            "A Button", "B Button", "X Button", "Y Button", 
                            "LB Button", "RB Button", "LT Button", "RT Button",
                            "Up", "Down", "Left", "Right"
                        ]
                        # If we find any non-generic action, mark as having custom controls
                        if action not in generic_actions:
                            has_custom_controls = True
                            break
                    if has_custom_controls:
                        break
                        
                if not has_custom_controls and game_data.get('players'):
                    generic_controls.append(rom)
        
        # Return the appropriate list based on current view
        if self.current_view == "with_controls":
            return with_controls
        elif self.current_view == "missing":
            return missing_controls
        elif self.current_view == "generic":
            return generic_controls
        
        # Fallback to all ROMs
        return available_roms
    
    def _filter_rom_list(self, rom_list, search_text):
        """Filter a list of ROMs based on search text"""
        # If no search text, return original list
        if not search_text:
            return rom_list
            
        filtered_roms = []
        
        # For multi-word searches
        if ' ' in search_text:
            search_terms = search_text.split()
            
            for rom in rom_list:
                rom_lower = rom.lower()
                
                # First check if all terms match the ROM name (fast check)
                all_terms_in_rom = True
                for term in search_terms:
                    if term not in rom_lower:
                        all_terms_in_rom = False
                        break
                
                if all_terms_in_rom:
                    filtered_roms.append(rom)
                    continue
                    
                # Check game name using name cache (if available)
                if hasattr(self, 'name_cache') and rom in self.name_cache:
                    game_name = self.name_cache[rom]
                    
                    # Check if all terms are in the game name
                    all_terms_in_game = True
                    for term in search_terms:
                        if term not in game_name:
                            all_terms_in_game = False
                            break
                    
                    if all_terms_in_game:
                        filtered_roms.append(rom)
                # Fallback to loading game data if name cache not available
                elif rom in self.rom_data_cache:
                    game_data = self.rom_data_cache[rom]
                    game_name = game_data.get('gamename', '').lower()
                    
                    # Check if all terms are in the game name
                    all_terms_in_game = True
                    for term in search_terms:
                        if term not in game_name:
                            all_terms_in_game = False
                            break
                    
                    if all_terms_in_game:
                        filtered_roms.append(rom)
        else:
            # Single-word search (simpler)
            # Try to use text lookup cache if available
            if hasattr(self, 'text_lookup') and search_text in self.text_lookup:
                # Get all ROMs that contain this word
                matching_roms = self.text_lookup[search_text]
                # But only include ROMs from our current list
                filtered_roms = [rom for rom in rom_list if rom in matching_roms]
            else:
                # Fallback to standard filtering
                for rom in rom_list:
                    if search_text in rom.lower():
                        filtered_roms.append(rom)
                        continue
                        
                    # Check game name using name cache (if available)
                    if hasattr(self, 'name_cache') and rom in self.name_cache:
                        game_name = self.name_cache[rom]
                        if search_text in game_name:
                            filtered_roms.append(rom)
                    # Fallback to ROM data cache
                    elif rom in self.rom_data_cache:
                        game_data = self.rom_data_cache[rom]
                        if 'gamename' in game_data and search_text in game_data['gamename'].lower():
                            filtered_roms.append(rom)
        
        return filtered_roms
    
    def on_game_select(self, event):
        """Compatibility method for handling game selection from the text widget"""
        if hasattr(self, 'game_listbox'):
            # For listbox, use the selected item if any
            selected_indices = self.game_listbox.curselection()
            if selected_indices:
                index = selected_indices[0]
                if index < len(self.game_list_data):
                    rom_name, _ = self.game_list_data[index]
                    self.current_game = rom_name
                    self.selected_line = index + 1  # 1-indexed for compatibility
                    self.display_game_info(rom_name)
        else:
            # Original implementation for text widget
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
                
                # Extract ROM name
                import re
                pattern = r'^[\*\+\- ]*([^ ].*?)(?:\s+- |\s+\[Clone)'
                match = re.search(pattern, line)
                
                if match:
                    romname = match.group(1).strip()
                else:
                    # Alternative approach if the regex fails
                    cleaned_line = line.strip()
                    if cleaned_line.startswith("* "):
                        cleaned_line = cleaned_line[2:]
                    if cleaned_line.startswith("+ ") or cleaned_line.startswith("- "):
                        cleaned_line = cleaned_line[2:]
                        
                    # If there's a " - " separator, take everything before it
                    if " - " in cleaned_line:
                        romname = cleaned_line.split(" - ")[0].strip()
                    # If there's a clone indicator, take everything before it
                    elif " [Clone" in cleaned_line:
                        romname = cleaned_line.split(" [Clone")[0].strip()
                    # Otherwise, use the whole line
                    else:
                        romname = cleaned_line
                
                self.current_game = romname
                
                # Display ROM info
                self.display_game_info(romname)
                    
            except Exception as e:
                print(f"Error displaying game: {str(e)}")
                import traceback
                traceback.print_exc()
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
        # Look in the info directory first
        template_path = os.path.join(self.info_dir, "default.conf")
        
        if os.path.exists(template_path):
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"Error loading template: {e}")
        
        # Try to find in other locations
        found_path = self.find_file_in_standard_locations(
            "default.conf",
            subdirs=[["settings", "info"], ["preview", "settings", "info"], ["info"]],
            copy_to_settings=False  # We'll copy to info_dir instead
        )
        
        if found_path:
            try:
                with open(found_path, 'r', encoding='utf-8') as f:
                    template_content = f.read()
                
                # Copy to info directory for future use
                try:
                    os.makedirs(self.info_dir, exist_ok=True)
                    with open(template_path, 'w', encoding='utf-8') as f:
                        f.write(template_content)
                    print(f"Migrated template to: {template_path}")
                except Exception as e:
                    print(f"Error migrating template: {e}")
                
                return template_content
            except Exception as e:
                print(f"Error reading template: {e}")
        
        # Last resort: create default template
        print("Creating default template content")
        default_content = self._get_default_template_content()
        
        # Try to save for future use
        try:
            os.makedirs(self.info_dir, exist_ok=True)
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(default_content)
            print(f"Created new default template at: {template_path}")
        except Exception as e:
            print(f"Could not save default template: {e}")
        
        return default_content

    def _get_default_template_content(self):
        """Get default template content"""
        return """controller D-pad		= 
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
    
    def analyze_controls(self):
        """Comprehensive analysis of ROM controls with improved visual styling and clone count"""
        try:
            # Get data from both methods
            generic_games, missing_games = self.identify_generic_controls()
            matched_roms = set()
            for rom in self.available_roms:
                if self.get_game_data(rom):
                    matched_roms.add(rom)
            unmatched_roms = self.available_roms - matched_roms
            
            # Identify clone ROMs - only count those that are in available_roms
            clone_roms = []
            if hasattr(self, 'parent_lookup') and self.parent_lookup:
                for clone_rom in self.parent_lookup.keys():
                    if clone_rom in self.available_roms:
                        clone_roms.append(clone_rom)
            
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
                f"- ROMs with missing controls: {len(missing_games)}\n"
                f"- Clone ROMs: {len(clone_roms)}\n\n"  # Added clone count
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
            
            # Add a new tab for clones if we have any
            if clone_roms:
                # Build a list of tuples with (rom_name, game_name) for each clone
                clone_game_list = []
                for clone_rom in sorted(clone_roms):
                    parent_rom = self.parent_lookup.get(clone_rom, "")
                    # Verify parent is in available ROMs
                    if parent_rom not in self.available_roms:
                        parent_rom = f"{parent_rom} (not available)"
                    
                    game_data = self.get_game_data(clone_rom)
                    if game_data and 'gamename' in game_data:
                        clone_game_list.append((clone_rom, f"{game_data['gamename']} (Clone of {parent_rom})"))
                    else:
                        clone_game_list.append((clone_rom, f"Clone of {parent_rom}"))
                
                self.create_game_list_with_edit(tabview.add("Clone ROMs"), 
                                        clone_game_list, "Clone ROMs")
            
            # Add a new tab for adding games
            if self.ALLOW_ADD_NEW_GAME:  # Toggle add new game feature
                add_game_tab = tabview.add("Add New Game")
                self.create_add_game_panel(add_game_tab)
            
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
                        f.write("\n")
                        
                        # Add clone section to export
                        f.write("Clone ROMs:\n")
                        f.write("==========\n")
                        for clone_rom in sorted(clone_roms):
                            parent_rom = self.parent_lookup.get(clone_rom, "")
                            if parent_rom not in self.available_roms:
                                parent_rom = f"{parent_rom} (not available)"
                            f.write(f"{clone_rom} - Clone of {parent_rom}\n")
                            
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
            
        except Exception as e:
            print(f"Error in analyze_controls: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
            
    def create_add_game_panel(self, parent_frame):
        """Create a panel for adding new games to gamedata.json using the unified editor"""
        # Main container frame with scrolling
        container = ctk.CTkScrollableFrame(
            parent_frame,
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        container.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Title and description
        header_frame = ctk.CTkFrame(container, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        header_frame.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            header_frame,
            text="Add New Game to gamedata.json",
            font=("Arial", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        description_text = (
            "This tool allows you to add a new game to the gamedata.json database. "
            "Fill in the required information below to create a new entry in the proper format."
        )
        
        ctk.CTkLabel(
            header_frame,
            text=description_text,
            font=("Arial", 13),
            justify="left",
            wraplength=750
        ).pack(anchor="w", padx=15, pady=(0, 15))
        
        # Add "Launch Editor" button
        def launch_editor():
            # Use the unified editor with no initial ROM name (new game)
            self.show_unified_game_editor(None, True, parent_frame.winfo_toplevel())
        
        launch_button = ctk.CTkButton(
            container,
            text="Launch Game Editor",
            command=launch_editor,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"],
            font=("Arial", 16, "bold"),
            height=60
        )
        launch_button.pack(pady=20)
        
        # Add help text
        help_frame = ctk.CTkFrame(container, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        help_frame.pack(fill="x", padx=0, pady=(15, 0))
        
        help_text = (
            "Click the button above to open the full-featured game editor where you can:\n\n"
            "• Enter all game properties (name, button count, etc.)\n"
            "• Define all standard and specialized controls\n"
            "• Add clone ROMs\n"
            "• Add custom controls\n"
            "• Preview the JSON that will be added to gamedata.json\n\n"
            "The editor provides a streamlined interface for creating new game entries "
            "with all the necessary configuration options."
        )
        
        ctk.CTkLabel(
            help_frame,
            text=help_text,
            font=("Arial", 13),
            justify="left",
            wraplength=750
        ).pack(anchor="w", padx=15, pady=15)

    def show_unified_game_editor(self, rom_name=None, is_new_game=True, parent=None):
        """
        Unified editor for adding/editing games with complete functionality
        
        Parameters:
        - rom_name: Name of the ROM to edit, or None for a new game
        - is_new_game: Whether this is a new game or editing an existing one
        - parent: Parent window for this dialog (used for modal behavior)
        """
        # If editing existing game, load its data
        game_data = {}
        if rom_name and not is_new_game:
            game_data = self.get_game_data(rom_name) or {}
        
        # Set display name
        display_name = game_data.get('gamename', rom_name) if rom_name else "New Game"
        
        # Create dialog with improved styling
        if parent is None:
            parent = self
        
        editor = ctk.CTkToplevel(parent)
        editor.title(f"{'Add New Game' if is_new_game else 'Edit Controls'} - {display_name}")
        editor.geometry("900x750")
        editor.configure(fg_color=self.theme_colors["background"])
        editor.transient(parent)
        editor.grab_set()
        
        # Header section
        header_frame = ctk.CTkFrame(editor, fg_color=self.theme_colors["primary"], corner_radius=0, height=60)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)  # Maintain fixed height
        
        ctk.CTkLabel(
            header_frame,
            text=f"{'Add New Game' if is_new_game else 'Edit Controls for'} {display_name}",
            font=("Arial", 18, "bold"),
            text_color="#ffffff"
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Main content area with scrolling
        content_frame = ctk.CTkScrollableFrame(
            editor, 
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Game properties card
        props_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        props_card.pack(fill="x", padx=0, pady=(0, 15))
        
        # Card title
        ctk.CTkLabel(
            props_card,
            text="Game Properties",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Properties grid
        properties_grid = ctk.CTkFrame(props_card, fg_color="transparent")
        properties_grid.pack(fill="x", padx=15, pady=(0, 15))
        
        # Get current values
        if is_new_game:
            # Default values for new game
            current_description = display_name if display_name != "New Game" else ""
            current_playercount = 2
            current_buttons = "6"
            current_sticks = "1"
            current_alternating = False
        else:
            # Values from existing game data
            current_description = game_data.get('gamename', display_name) or rom_name
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
                    
            current_alternating = game_data.get('alternating', False)
        
        # Configure the grid
        properties_grid.columnconfigure(0, weight=0)  # Label
        properties_grid.columnconfigure(1, weight=1)  # Entry
        properties_grid.columnconfigure(2, weight=0)  # Label
        properties_grid.columnconfigure(3, weight=1)  # Entry
        
        # ROM Name field (disabled if editing existing game)
        ctk.CTkLabel(
            properties_grid, 
            text="ROM Name:", 
            font=("Arial", 13),
            width=100
        ).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        rom_name_var = tk.StringVar(value=rom_name or "")
        rom_name_entry = ctk.CTkEntry(
            properties_grid, 
            width=300, 
            textvariable=rom_name_var,
            fg_color=self.theme_colors["background"],
            state="normal" if is_new_game else "disabled"
        )
        rom_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Row 1: Game Description (Name)
        ctk.CTkLabel(
            properties_grid, 
            text="Game Name:", 
            font=("Arial", 13),
            width=100
        ).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        description_var = tk.StringVar(value=current_description)
        description_entry = ctk.CTkEntry(
            properties_grid, 
            width=300, 
            textvariable=description_var,
            fg_color=self.theme_colors["background"]
        )
        description_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # Row 2: Player Count
        ctk.CTkLabel(
            properties_grid, 
            text="Players:", 
            font=("Arial", 13),
            width=100
        ).grid(row=2, column=0, padx=5, pady=5, sticky="w")
        
        playercount_var = tk.StringVar(value=str(current_playercount))
        playercount_combo = ctk.CTkComboBox(
            properties_grid, 
            width=100, 
            values=["1", "2", "3", "4"], 
            variable=playercount_var,
            fg_color=self.theme_colors["background"],
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"],
            dropdown_fg_color=self.theme_colors["card_bg"]
        )
        playercount_combo.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        # Set up players alternating option
        alternating_var = tk.BooleanVar(value=current_alternating)
        alternating_check = ctk.CTkCheckBox(
            properties_grid, 
            text="Alternating Play", 
            variable=alternating_var,
            checkbox_width=20,
            checkbox_height=20,
            corner_radius=3,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        alternating_check.grid(row=2, column=2, padx=5, pady=5, sticky="w")
        
        # Row 3: Buttons and Sticks
        ctk.CTkLabel(
            properties_grid, 
            text="Buttons:", 
            font=("Arial", 13),
            width=100
        ).grid(row=3, column=0, padx=5, pady=5, sticky="w")
        
        buttons_var = tk.StringVar(value=current_buttons)
        buttons_combo = ctk.CTkComboBox(
            properties_grid, 
            width=100, 
            values=["1", "2", "3", "4", "5", "6", "8"], 
            variable=buttons_var,
            fg_color=self.theme_colors["background"],
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"],
            dropdown_fg_color=self.theme_colors["card_bg"]
        )
        buttons_combo.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        
        ctk.CTkLabel(
            properties_grid, 
            text="Sticks:", 
            font=("Arial", 13),
            width=100
        ).grid(row=3, column=2, padx=5, pady=5, sticky="w")
        
        sticks_var = tk.StringVar(value=current_sticks)
        sticks_combo = ctk.CTkComboBox(
            properties_grid, 
            width=100, 
            values=["0", "1", "2"], 
            variable=sticks_var,
            fg_color=self.theme_colors["background"],
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"],
            dropdown_fg_color=self.theme_colors["card_bg"]
        )
        sticks_combo.grid(row=3, column=3, padx=5, pady=5, sticky="w")
        
        # Initialize clone_entries for use throughout the method
        clone_entries = []
        preview_text = None  # Define here to avoid NameError
        
        controls_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        controls_card.pack(fill="x", padx=0, pady=(0, 15))

        # Card title
        ctk.CTkLabel(
            controls_card,
            text="Control Mappings",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))

        # Get existing controls from game data to ensure we show ALL controls
        existing_controls = []
        existing_control_names = set()  # Track which control names exist in the game data
                
        if game_data and 'players' in game_data:
            for player in game_data.get('players', []):
                for label in player.get('labels', []):
                    # Add all controls to our list including specialized ones like P1_DIAL
                    existing_controls.append((label['name'], label['value']))
                    existing_control_names.add(label['name'])

        # FIXED: Only show controls that actually exist, don't auto-generate
        standard_controls = []

        if not is_new_game:
            # For existing games, ONLY show controls that are actually defined
            # Don't auto-generate based on button count
            
            print(f"Existing game: found {len(existing_control_names)} actual controls")
            print(f"Controls found: {sorted(existing_control_names)}")
            
            # Only add controls that actually exist in the game data
            for control_name in sorted(existing_control_names):
                # Only include standard button/joystick controls in the standard_controls list
                # Specialized controls will be handled separately
                if (control_name.startswith('P1_BUTTON') or 
                    control_name.startswith('P1_JOYSTICK') or
                    control_name.startswith('P1_START') or 
                    control_name.startswith('P1_SELECT')):
                    
                    # Create display name
                    if control_name.startswith('P1_BUTTON'):
                        button_num = control_name.replace('P1_BUTTON', '')
                        display_name = f'P1 Button {button_num}'
                    elif control_name == 'P1_START':
                        display_name = 'P1 Start Button'
                    elif control_name == 'P1_SELECT':
                        display_name = 'P1 Select/Coin Button'
                    elif control_name == 'P1_JOYSTICK_UP':
                        display_name = 'P1 Joystick Up'
                    elif control_name == 'P1_JOYSTICK_DOWN':
                        display_name = 'P1 Joystick Down'
                    elif control_name == 'P1_JOYSTICK_LEFT':
                        display_name = 'P1 Joystick Left'
                    elif control_name == 'P1_JOYSTICK_RIGHT':
                        display_name = 'P1 Joystick Right'
                    else:
                        display_name = control_name
                        
                    standard_controls.append((control_name, display_name))

        # For new games, don't pre-generate any controls - let user add what they need
        if is_new_game:
            print("New game: not pre-generating any controls")
            standard_controls = []

        # Only add directional controls if they actually exist in the game data
        directional_controls = []
        if not is_new_game and any(name.startswith('P1_JOYSTICK_') for name in existing_control_names):
            # Only add the specific directional controls that exist
            for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                control_name = f'P1_JOYSTICK_{direction}'
                if control_name in existing_control_names:
                    directional_controls.append((control_name, f'P1 Joystick {direction.capitalize()}'))

        # Only add right stick controls if they actually exist
        right_stick_controls = []
        if any(name.startswith('P1_JOYSTICKRIGHT_') for name in existing_control_names):
            for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                control_name = f'P1_JOYSTICKRIGHT_{direction}'
                if control_name in existing_control_names:
                    right_stick_controls.append((control_name, f'P1 Right Stick {direction.capitalize()}'))

        # Only add D-pad controls if they actually exist
        dpad_controls = []
        if any(name.startswith('P1_DPAD_') for name in existing_control_names):
            for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                control_name = f'P1_DPAD_{direction}'
                if control_name in existing_control_names:
                    dpad_controls.append((control_name, f'P1 D-Pad {direction.capitalize()}'))

        # System buttons - only if they exist
        system_controls = []
        for control_name in ['P1_START', 'P1_SELECT']:
            if control_name in existing_control_names:
                if control_name == 'P1_START':
                    system_controls.append((control_name, 'P1 Start Button'))
                elif control_name == 'P1_SELECT':
                    system_controls.append((control_name, 'P1 Select/Coin Button'))

        # Define all specialized controls but only add the ones that exist in the game data
        all_specialized_controls = [
            ('P1_DIAL', 'Rotary Dial'),
            ('P1_DIAL_V', 'Vertical Dial'),
            ('P1_PADDLE', 'Paddle Controller'),
            ('P1_TRACKBALL_X', 'Trackball X-Axis'),
            ('P1_TRACKBALL_Y', 'Trackball Y-Axis'),
            ('P1_MOUSE_X', 'Mouse X-Axis'),
            ('P1_MOUSE_Y', 'Mouse Y-Axis'),
            ('P1_LIGHTGUN_X', 'Light Gun X-Axis'),
            ('P1_LIGHTGUN_Y', 'Light Gun Y-Axis'),
            ('P1_AD_STICK_X', 'Analog Stick X-Axis'),
            ('P1_AD_STICK_Y', 'Analog Stick Y-Axis'),
            ('P1_AD_STICK_Z', 'Analog Stick Z-Axis'),
            ('P1_PEDAL', 'Pedal Input'),
            ('P1_PEDAL2', 'Second Pedal Input'),
            ('P1_POSITIONAL', 'Positional Control'),
            ('P1_GAMBLE_HIGH', 'Gamble High'),
            ('P1_GAMBLE_LOW', 'Gamble Low'),
        ]

        # Only include specialized controls if they exist in the game data
        specialized_controls = [
            control for control in all_specialized_controls 
            if control[0] in existing_control_names
        ]

        # Create the final control list, merging all relevant controls
        all_controls = standard_controls + directional_controls + right_stick_controls + dpad_controls + system_controls + specialized_controls

        # Add any custom controls that aren't in our lists but are in the game data
        for control_name, action in existing_controls:
            if not any(control[0] == control_name for control in all_controls):
                all_controls.append((control_name, action))

        print(f"Final controls to display: {len(all_controls)}")
        for control_name, display_name in all_controls:
            print(f"  {control_name}: {display_name}")

        # Create a dictionary to store all the entry fields
        control_entries = {}

        # Helper function to get existing action for a control
        def get_existing_action(control_name):
            for player in game_data.get('players', []):
                for label in player.get('labels', []):
                    if label.get('name') == control_name:
                        return label.get('value', '')
            return ''

        # Headers for controls
        headers_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        headers_frame.pack(fill="x", padx=15, pady=(0, 5))

        # Two-column grid for headers
        headers_frame.columnconfigure(0, weight=1)  # Control
        headers_frame.columnconfigure(1, weight=1)  # Action

        # Header labels
        control_header = ctk.CTkFrame(headers_frame, fg_color=self.theme_colors["primary"], corner_radius=4)
        control_header.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkLabel(
            control_header,
            text="Control",
            font=("Arial", 13, "bold"),
            text_color="#ffffff"
        ).pack(padx=10, pady=5)

        action_header = ctk.CTkFrame(headers_frame, fg_color=self.theme_colors["primary"], corner_radius=4)
        action_header.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        ctk.CTkLabel(
            action_header,
            text="Action/Function (leave empty to skip)",
            font=("Arial", 13, "bold"),
            text_color="#ffffff"
        ).pack(padx=10, pady=5)

        # Create container for the controls
        controls_container = ctk.CTkFrame(controls_card, fg_color="transparent")
        controls_container.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Calculate dynamic height based on number of controls
        num_controls = len(all_controls)
        if num_controls == 0:
            # Minimum height for empty state
            dynamic_height = 60
        elif num_controls <= 3:
            # Small height for few controls
            dynamic_height = min(num_controls * 45 + 20, 150)
        elif num_controls <= 8:
            # Medium height for moderate number of controls
            dynamic_height = min(num_controls * 42 + 20, 300)
        else:
            # Cap height for many controls and enable scrolling
            dynamic_height = 350

        print(f"Setting controls frame height to {dynamic_height}px for {num_controls} controls")

        # Create a scrollable container for controls with dynamic height
        controls_scroll = ctk.CTkScrollableFrame(
            controls_container,
            height=dynamic_height,  # Dynamic height based on content
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        controls_scroll.pack(fill="x", expand=False)  # Don't expand, use calculated height

        # Function to update height when controls are added/removed
        def update_controls_height():
            """Update the height of the controls frame based on current content"""
            current_children = len([child for child in controls_scroll.winfo_children() 
                                if isinstance(child, ctk.CTkFrame)])
            
            if current_children == 0:
                new_height = 60
            elif current_children <= 3:
                new_height = min(current_children * 45 + 20, 150)
            elif current_children <= 8:
                new_height = min(current_children * 42 + 20, 300)
            else:
                new_height = 350
            
            # Only update if height changed significantly
            current_height = controls_scroll.cget("height")
            if abs(current_height - new_height) > 10:
                controls_scroll.configure(height=new_height)
                print(f"Updated controls frame height: {current_height} -> {new_height} ({current_children} controls)")

        def update_empty_state():
            """Update empty state message and frame height"""
            control_widgets = [child for child in controls_scroll.winfo_children() 
                            if isinstance(child, ctk.CTkFrame)]
            
            # Check if we have the empty state frame
            empty_frames = [child for child in controls_scroll.winfo_children() 
                        if isinstance(child, ctk.CTkFrame) and 
                        any(isinstance(grandchild, ctk.CTkLabel) and 
                            "No controls defined yet" in grandchild.cget("text") 
                            for grandchild in child.winfo_children())]
            
            if len(control_widgets) == 0 or (len(control_widgets) == 1 and empty_frames):
                # Show empty state if no real controls
                if not empty_frames:
                    empty_frame = ctk.CTkFrame(controls_scroll, fg_color=self.theme_colors["background"], corner_radius=4)
                    empty_frame.pack(fill="x", pady=10)
                    
                    ctk.CTkLabel(
                        empty_frame,
                        text="No controls defined yet. Use 'Add Custom Controls' below to add controls.",
                        font=("Arial", 13),
                        text_color=self.theme_colors["text_dimmed"]
                    ).pack(pady=20)
                
                # Set minimum height for empty state
                controls_scroll.configure(height=80)
            else:
                # Remove empty state frames if we have real controls
                for empty_frame in empty_frames:
                    empty_frame.destroy()
                
                # Update height based on actual controls
                if hasattr(controls_scroll, 'update_height'):
                    controls_scroll.update_height()

        # Row alternating colors
        alt_colors = [self.theme_colors["card_bg"], self.theme_colors["background"]]

        # Create entry fields for each control
        for i, (control_name, display_name) in enumerate(all_controls):
            # Create a frame for each control with alternating background
            control_frame = ctk.CTkFrame(
                controls_scroll, 
                fg_color=alt_colors[i % 2],
                corner_radius=4,
                height=40  # Fixed row height
            )
            control_frame.pack(fill="x", pady=2)
            control_frame.pack_propagate(False)  # Maintain fixed row height
            
            # Configure columns
            control_frame.columnconfigure(0, weight=1)  # Control name
            control_frame.columnconfigure(1, weight=1)  # Action entry
            
            # Control name label
            ctk.CTkLabel(
                control_frame, 
                text=display_name, 
                font=("Arial", 13),
                anchor="w",
                width=200
            ).grid(row=0, column=0, padx=10, pady=8, sticky="w")
            
            # Get existing action if available
            existing_action = get_existing_action(control_name)
            
            # Create entry for action
            action_entry = ctk.CTkEntry(
                control_frame, 
                width=400,
                fg_color=self.theme_colors["background"]
            )
            action_entry.insert(0, existing_action)
            action_entry.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
            
            # Store the entry widget in our dictionary
            control_entries[control_name] = action_entry

        # Store the update function for use in custom controls section
        controls_scroll.update_height = update_controls_height

        # Call update_empty_state to handle initial state
        update_empty_state()

        # Add a section for custom controls with simple styling
        if self.ALLOW_CUSTOM_CONTROLS or (is_new_game and self.ALLOW_ADD_NEW_GAME):
            custom_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
            custom_card.pack(fill="x", padx=0, pady=(0, 15))
            
            # Simple header
            ctk.CTkLabel(
                custom_card,
                text="Add Custom Controls",
                font=("Arial", 16, "bold"),
                anchor="w"
            ).pack(anchor="w", padx=15, pady=(15, 10))
            
            # Simple description
            ctk.CTkLabel(
                custom_card,
                text="Add additional controls that will appear in the Controller Mappings section above.",
                font=("Arial", 12),
                text_color=self.theme_colors["text_dimmed"],
                wraplength=750,
                justify="left"
            ).pack(anchor="w", padx=15, pady=(0, 15))
            
            # Frame to hold the add control form
            add_form_frame = ctk.CTkFrame(custom_card, fg_color=self.theme_colors["background"], corner_radius=6)
            add_form_frame.pack(fill="x", padx=15, pady=(0, 15))
            
            # Form grid
            add_form_frame.columnconfigure(0, weight=1)
            add_form_frame.columnconfigure(1, weight=2)
            add_form_frame.columnconfigure(2, weight=0)
            
            # Control name dropdown
            all_control_options = [
                # Standard buttons from 1-12
                "P1_BUTTON1", "P1_BUTTON2", "P1_BUTTON3", "P1_BUTTON4", 
                "P1_BUTTON5", "P1_BUTTON6", "P1_BUTTON7", "P1_BUTTON8",
                "P1_BUTTON9", "P1_BUTTON10", "P1_BUTTON11", "P1_BUTTON12",
                # System buttons
                "P1_START", "P1_SELECT", "P1_COIN",
                # Joysticks
                "P1_JOYSTICK_UP", "P1_JOYSTICK_DOWN", "P1_JOYSTICK_LEFT", "P1_JOYSTICK_RIGHT",
                "P1_JOYSTICKRIGHT_UP", "P1_JOYSTICKRIGHT_DOWN", "P1_JOYSTICKRIGHT_LEFT", "P1_JOYSTICKRIGHT_RIGHT",
                # D-Pad
                "P1_DPAD_UP", "P1_DPAD_DOWN", "P1_DPAD_LEFT", "P1_DPAD_RIGHT",
                # Specialized controls
                "P1_DIAL", "P1_DIAL_V", "P1_PADDLE", "P1_TRACKBALL_X", "P1_TRACKBALL_Y",
                "P1_MOUSE_X", "P1_MOUSE_Y", "P1_LIGHTGUN_X", "P1_LIGHTGUN_Y",
                "P1_AD_STICK_X", "P1_AD_STICK_Y", "P1_AD_STICK_Z",
                "P1_PEDAL", "P1_PEDAL2", "P1_POSITIONAL",
                "P1_GAMBLE_HIGH", "P1_GAMBLE_LOW",
                # Player 2 controls
                "P2_BUTTON1", "P2_BUTTON2", "P2_BUTTON3", "P2_BUTTON4",
                "P2_JOYSTICK_UP", "P2_JOYSTICK_DOWN", "P2_JOYSTICK_LEFT", "P2_JOYSTICK_RIGHT",
                "P2_START", "P2_SELECT",
            ]
            
            def get_available_controls():
                """Get controls not already used in standard or custom controls"""
                used_controls = set()
                
                # From standard controls
                for control_name, entry in control_entries.items():
                    if isinstance(entry, ctk.CTkEntry) and entry.get().strip():
                        used_controls.add(control_name)
                
                return [c for c in all_control_options if c not in used_controls]
            
            # Control selection
            ctk.CTkLabel(add_form_frame, text="Control:", font=("Arial", 13)).grid(
                row=0, column=0, padx=10, pady=10, sticky="w"
            )
            
            control_var = tk.StringVar()
            control_dropdown = ctk.CTkComboBox(
                add_form_frame,
                variable=control_var,
                values=get_available_controls() + ["OTHER (Type custom name)"],
                width=250,
                fg_color=self.theme_colors["card_bg"],
                button_color=self.theme_colors["primary"],
                button_hover_color=self.theme_colors["secondary"],
                dropdown_fg_color=self.theme_colors["card_bg"]
            )
            control_dropdown.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
            
            # Custom control entry (initially hidden)
            custom_control_entry = ctk.CTkEntry(
                add_form_frame,
                placeholder_text="Enter custom control name",
                width=250,
                fg_color=self.theme_colors["card_bg"]
            )
            custom_control_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
            custom_control_entry.grid_remove()
            
            # Action entry
            ctk.CTkLabel(add_form_frame, text="Action:", font=("Arial", 13)).grid(
                row=0, column=1, padx=10, pady=10, sticky="w"
            )
            
            action_entry = ctk.CTkEntry(
                add_form_frame,
                placeholder_text="Enter action name (e.g., 'Fire Weapon', 'Jump')",
                width=400,
                fg_color=self.theme_colors["card_bg"]
            )
            action_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
            
            # Function to handle dropdown changes
            def on_control_dropdown_change(*args):
                if control_var.get() == "OTHER (Type custom name)":
                    control_dropdown.grid_remove()
                    custom_control_entry.grid()
                    custom_control_entry.focus_set()
                else:
                    custom_control_entry.grid_remove()
                    control_dropdown.grid()
            
            control_var.trace_add("write", on_control_dropdown_change)
            
            def add_custom_control():
                """Add the custom control to the main controls section"""
                # Get control name
                if control_dropdown.winfo_viewable():
                    control_name = control_var.get()
                    if control_name == "OTHER (Type custom name)":
                        messagebox.showerror("Error", "Please select a control or enter a custom name", parent=editor)
                        return
                else:
                    control_name = custom_control_entry.get().strip()
                    if not control_name:
                        messagebox.showerror("Error", "Please enter a custom control name", parent=editor)
                        return
                
                # Get action
                action = action_entry.get().strip()
                if not action:
                    messagebox.showerror("Error", "Please enter an action name", parent=editor)
                    return
                
                # Check if control already exists
                if control_name in control_entries:
                    messagebox.showerror("Error", f"Control '{control_name}' already exists", parent=editor)
                    return
                
                # Add to the main controls section
                # Find the controls container (controls_scroll)
                if 'controls_scroll' in locals() and controls_scroll.winfo_exists():
                    # Count existing controls for alternating colors
                    existing_count = len([child for child in controls_scroll.winfo_children() 
                                        if isinstance(child, ctk.CTkFrame)])
                    
                    # Create control frame with alternating background
                    alt_colors = [self.theme_colors["card_bg"], self.theme_colors["background"]]
                    control_frame = ctk.CTkFrame(
                        controls_scroll, 
                        fg_color=alt_colors[existing_count % 2],
                        corner_radius=4,
                        height=40  # Fixed row height
                    )
                    control_frame.pack(fill="x", pady=2)
                    control_frame.pack_propagate(False)  # Maintain fixed row height
                    
                    # Configure columns
                    control_frame.columnconfigure(0, weight=1)
                    control_frame.columnconfigure(1, weight=1)
                    
                    # Control name label with special styling for custom controls
                    ctk.CTkLabel(
                        control_frame, 
                        text=f"{control_name} (Custom)", 
                        font=("Arial", 13),
                        text_color=self.theme_colors["success"],  # Green to indicate custom
                        anchor="w",
                        width=200
                    ).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                    
                    # Create entry for action (pre-filled)
                    new_action_entry = ctk.CTkEntry(
                        control_frame, 
                        width=400,
                        fg_color=self.theme_colors["background"]
                    )
                    new_action_entry.insert(0, action)
                    new_action_entry.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
                    
                    # Store the entry widget in our dictionary
                    control_entries[control_name] = new_action_entry
                    
                    # IMPORTANT: Update the controls frame height dynamically
                    if hasattr(controls_scroll, 'update_height'):
                        controls_scroll.after(100, controls_scroll.update_height)
                    
                    # Also update empty state
                    controls_scroll.after(100, update_empty_state)
                    
                    # Clear the form
                    action_entry.delete(0, tk.END)
                    if custom_control_entry.winfo_viewable():
                        custom_control_entry.delete(0, tk.END)
                        # Switch back to dropdown
                        custom_control_entry.grid_remove()
                        control_dropdown.grid()
                    
                    # Update dropdown to remove the used control
                    control_dropdown.configure(values=get_available_controls() + ["OTHER (Type custom name)"])
                    if get_available_controls():
                        control_var.set(get_available_controls()[0])
                    else:
                        control_var.set("OTHER (Type custom name)")
                    
                    # Show success message
                    messagebox.showinfo(
                        "Custom Control Added", 
                        f"'{control_name}' has been added to the Controller Mappings section above.",
                        parent=editor
                    )
                    
                    # Scroll the controls section to show the new control
                    controls_scroll.update_idletasks()
                    # Scroll to bottom to show the newly added control
                    controls_scroll._parent_canvas.yview_moveto(1.0)
            
            # Add button
            add_button = ctk.CTkButton(
                add_form_frame,
                text="Add Control",
                command=add_custom_control,
                width=120,
                height=35,
                fg_color=self.theme_colors["success"],
                hover_color="#218838",
                font=("Arial", 13, "bold")
            )
            add_button.grid(row=1, column=2, padx=10, pady=5)
            
            # Helper text
            ctk.CTkLabel(
                custom_card,
                text="💡 Added controls will appear in the Controller Mappings section above with '(Custom)' label.",
                font=("Arial", 11),
                text_color=self.theme_colors["text_dimmed"],
                justify="left"
            ).pack(anchor="w", padx=15, pady=(0, 15))

        else:
            # Create empty list to prevent errors in save function
            custom_control_rows = []
        
        # MOVED: Clone games section BELOW control mappings
        # Clone games card
        clone_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        clone_card.pack(fill="x", padx=0, pady=(0, 15))
        
        # Adjust title based on whether creating new game or editing existing
        title_text = "Clone Games (Optional)" if is_new_game else "Manage Clone Games"
        
        ctk.CTkLabel(
            clone_card,
            text=title_text,
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Adjust description based on whether creating new game or editing existing
        clones_description = "You can add clone ROMs for this game. These will inherit the parent game's settings."
        if not is_new_game:
            clones_description = "Add, edit, or remove clone ROMs for this game. Clones inherit the parent game's settings unless overridden."
        
        ctk.CTkLabel(
            clone_card,
            text=clones_description,
            font=("Arial", 12),
            text_color=self.theme_colors["text_dimmed"],
            wraplength=750
        ).pack(anchor="w", padx=15, pady=(0, 10))
        
        # Container for clone entries
        clones_container = ctk.CTkFrame(clone_card, fg_color="transparent")
        clones_container.pack(fill="x", padx=15, pady=(0, 15))
        
        def add_clone_row(clone_rom="", clone_desc=""):
            row_frame = ctk.CTkFrame(
                clones_container, 
                fg_color=self.theme_colors["background"],
                corner_radius=4
            )
            row_frame.pack(fill="x", pady=2)
            
            # Clone ROM name
            clone_rom_var = tk.StringVar(value=clone_rom)
            clone_rom_entry = ctk.CTkEntry(
                row_frame,
                width=150,
                textvariable=clone_rom_var,
                fg_color=self.theme_colors["card_bg"],
                placeholder_text="Clone ROM Name"
            )
            clone_rom_entry.pack(side="left", padx=10, pady=8)
            
            # Clone description
            clone_desc_var = tk.StringVar(value=clone_desc)
            clone_desc_entry = ctk.CTkEntry(
                row_frame,
                width=400,
                textvariable=clone_desc_var,
                fg_color=self.theme_colors["card_bg"],
                placeholder_text="Clone Description"
            )
            clone_desc_entry.pack(side="left", padx=10, pady=8)
            
            # Remove button
            def remove_row():
                row_frame.destroy()
                clone_entries.remove(clone_data)
            
            remove_button = ctk.CTkButton(
                row_frame,
                text="×",
                width=30,
                height=30,
                command=remove_row,
                fg_color=self.theme_colors["danger"],
                hover_color="#c82333",
                font=("Arial", 14, "bold"),
                corner_radius=15
            )
            remove_button.pack(side="right", padx=10, pady=8)
            
            # Store data for this row
            clone_data = {
                "frame": row_frame,
                "rom_var": clone_rom_var,
                "desc_var": clone_desc_var
            }
            
            clone_entries.append(clone_data)
            
            return clone_data
        
        # If editing existing game, load any existing clones
        existing_clones_added = False
        if not is_new_game and rom_name in self.gamedata_json:
            parent_data = self.gamedata_json[rom_name]
            if 'clones' in parent_data and isinstance(parent_data['clones'], dict):
                # Add rows for existing clones
                for clone_rom, clone_data in parent_data['clones'].items():
                    clone_desc = clone_data.get('description', f"{clone_rom} (Clone of {rom_name})")
                    add_clone_row(clone_rom, clone_desc)
                    existing_clones_added = True
        
        # Add initial clone row if no existing clones
        if not existing_clones_added:
            add_clone_row()
        
        # Add another clone button
        add_clone_button = ctk.CTkButton(
            clones_container,
            text="+ Add Another Clone",
            command=add_clone_row,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"],
            height=35
        )
        add_clone_button.pack(pady=10)
        
        # If creating a new game, show the preview section
        if is_new_game:
            # Preview section - show JSON output
            preview_frame = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
            preview_frame.pack(fill="x", padx=0, pady=(0, 15))
            
            ctk.CTkLabel(
                preview_frame,
                text="JSON Preview",
                font=("Arial", 14, "bold")
            ).pack(anchor="w", padx=15, pady=(15, 10))
            
            # Preview text box
            preview_text = ctk.CTkTextbox(
                preview_frame,
                height=150,
                font=("Consolas", 12),
                fg_color=self.theme_colors["background"]
            )
            preview_text.pack(fill="x", padx=15, pady=(0, 15))
        
        # Preview JSON function - only used if is_new_game is True
        def update_preview():
            """Update the JSON preview based on current form values"""
            if not is_new_game or not preview_text:
                return
                
            try:
                # Get values from form
                current_rom_name = rom_name_var.get().strip()
                if not current_rom_name:
                    preview_text.delete("1.0", "end")
                    preview_text.insert("1.0", "Please enter a ROM name to generate preview")
                    return
                    
                # Build the JSON structure
                game_entry = {
                    current_rom_name: {
                        "description": description_var.get().strip() or current_rom_name,
                        "playercount": playercount_var.get(),
                        "buttons": buttons_var.get(),
                        "sticks": sticks_var.get(),
                        "alternating": bool(alternating_var.get()),
                        "clones": {},
                        "controls": {}
                    }
                }
                
                # Add clones
                for clone_data in clone_entries:
                    clone_rom = clone_data["rom_var"].get().strip()
                    clone_desc = clone_data["desc_var"].get().strip()
                    
                    if clone_rom:
                        game_entry[current_rom_name]["clones"][clone_rom] = {
                            "description": clone_desc or f"{clone_rom} (Clone of {current_rom_name})"
                        }
                
                # Add ALL controls from control_entries (both standard and custom)
                for control_name, entry in control_entries.items():
                    if isinstance(entry, ctk.CTkEntry):  # Check if it's an entry widget
                        control_label = entry.get().strip()
                        if control_label:
                            game_entry[current_rom_name]["controls"][control_name] = {
                                "name": control_label,
                                "tag": "",
                                "mask": "0"
                            }
                
                # Format and display the JSON
                import json
                formatted_json = json.dumps(game_entry, indent=2)
                preview_text.delete("1.0", "end")
                preview_text.insert("1.0", formatted_json)
            except Exception as e:
                preview_text.delete("1.0", "end")
                preview_text.insert("1.0", f"Error generating preview: {str(e)}")
                print(f"Preview error: {e}")
                import traceback
                traceback.print_exc()
        
        # Add button to manually update preview if we're adding a new game
        if is_new_game and preview_text:
            update_preview_button = ctk.CTkButton(
                preview_frame,
                text="Update Preview",
                command=update_preview,
                fg_color=self.theme_colors["primary"],
                hover_color=self.theme_colors["button_hover"],
                height=30,
                width=120
            )
            update_preview_button.pack(anchor="e", padx=15, pady=(0, 15))
            
            # Initial preview update
            editor.after(100, update_preview)
        
        # Set up update events for key fields
        def setup_update_events():
            """Set up events to update the preview when key fields change"""
            if is_new_game and preview_text:
                rom_name_var.trace_add("write", lambda *args: editor.after(500, update_preview))
                description_var.trace_add("write", lambda *args: editor.after(500, update_preview))
                playercount_var.trace_add("write", lambda *args: editor.after(500, update_preview))
                buttons_var.trace_add("write", lambda *args: editor.after(500, update_preview))
                sticks_var.trace_add("write", lambda *args: editor.after(500, update_preview))
                alternating_var.trace_add("write", lambda *args: editor.after(500, update_preview))
        
        # Set up update events after a short delay
        editor.after(200, setup_update_events)
        
        # Bottom buttons area (fixed at bottom)
        button_area = ctk.CTkFrame(editor, height=70, fg_color=self.theme_colors["card_bg"], corner_radius=0)
        button_area.pack(fill="x", side="bottom", padx=0, pady=0)
        button_area.pack_propagate(False)  # Keep fixed height
        
        # Button container
        button_container = ctk.CTkFrame(button_area, fg_color="transparent")
        button_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Remove Game button (with confirmation) - only show if not a new game and feature is enabled
        if not is_new_game and self.ALLOW_REMOVE_GAME:
            remove_button = ctk.CTkButton(
                button_container,
                text="Remove Game",
                command=lambda: self.remove_game(rom_name, editor),
                fg_color=self.theme_colors["danger"],
                hover_color="#c82333",
                font=("Arial", 14),
                height=40,
                width=150
            )
            remove_button.pack(side="left", padx=5)
        
        # Fix 2: Modified save_game function to preserve existing data and only update what changed
        # Replace your entire save_game function with this complete version:

        def save_game():
            """Save game data while preserving existing properties - COMPLETE FIXED VERSION"""
            try:
                # Validate ROM name
                current_rom_name = rom_name_var.get().strip()
                if not current_rom_name:
                    messagebox.showerror("Error", "ROM Name is required", parent=editor)
                    return
                    
                # Get existing gamedata.json
                gamedata_path = self.gamedata_path
                try:
                    with open(gamedata_path, 'r', encoding='utf-8') as f:
                        gamedata = json.load(f)
                except FileNotFoundError:
                    gamedata = {}
                except json.JSONDecodeError:
                    messagebox.showerror("Error", "The gamedata.json file is corrupted", parent=editor)
                    return
                    
                # Check if game already exists
                if is_new_game and current_rom_name in gamedata:
                    if not messagebox.askyesno("Warning", 
                                        f"'{current_rom_name}' already exists. Overwrite?", 
                                        parent=editor):
                        return
                
                # Preserve existing data or create new entry
                if current_rom_name in gamedata:
                    game_entry = gamedata[current_rom_name].copy()
                else:
                    game_entry = {}
                
                # Update basic properties
                game_entry["description"] = description_var.get().strip() or current_rom_name
                game_entry["playercount"] = playercount_var.get()
                game_entry["buttons"] = buttons_var.get()
                game_entry["sticks"] = sticks_var.get()
                game_entry["alternating"] = bool(alternating_var.get())
                
                # Handle clones
                if not clone_entries:
                    if "clones" not in game_entry:
                        game_entry["clones"] = {}
                else:
                    new_clones = {}
                    for clone_data in clone_entries:
                        clone_rom = clone_data["rom_var"].get().strip()
                        clone_desc = clone_data["desc_var"].get().strip()
                        
                        if clone_rom:
                            new_clones[clone_rom] = {
                                "description": clone_desc or f"{clone_rom} (Clone of {current_rom_name})"
                            }
                    
                    game_entry["clones"] = new_clones
                
                # Handle controls
                if not control_entries:
                    if "controls" not in game_entry:
                        game_entry["controls"] = {}
                else:
                    if "controls" not in game_entry:
                        game_entry["controls"] = {}
                    
                    existing_controls = game_entry["controls"].copy()
                    displayed_controls = set()
                    controls_added = 0
                    
                    # Update displayed controls
                    for control_name, entry in control_entries.items():
                        if isinstance(entry, ctk.CTkEntry):
                            control_label = entry.get().strip()
                            displayed_controls.add(control_name)
                            
                            if control_label:
                                if control_name not in existing_controls:
                                    existing_controls[control_name] = {
                                        "name": control_label,
                                        "tag": "",
                                        "mask": "0"
                                    }
                                    controls_added += 1
                                else:
                                    existing_controls[control_name]["name"] = control_label
                                    if "tag" not in existing_controls[control_name]:
                                        existing_controls[control_name]["tag"] = ""
                                    if "mask" not in existing_controls[control_name]:
                                        existing_controls[control_name]["mask"] = "0"
                            else:
                                if control_name in existing_controls:
                                    del existing_controls[control_name]
                    
                    # Preserve non-displayed controls
                    for control_name, control_data in game_entry.get("controls", {}).items():
                        if control_name not in displayed_controls:
                            existing_controls[control_name] = control_data
                    
                    game_entry["controls"] = existing_controls
                
                # Update button count if needed
                defined_buttons = set()
                for control_name in game_entry.get("controls", {}):
                    if control_name.startswith("P1_BUTTON"):
                        try:
                            button_num = int(control_name.replace("P1_BUTTON", ""))
                            defined_buttons.add(button_num)
                        except ValueError:
                            pass
                
                current_buttons = int(buttons_var.get())
                
                if defined_buttons:
                    max_defined_button = max(defined_buttons)
                    
                    if max_defined_button > current_buttons:
                        if messagebox.askyesno("Update Button Count", 
                                    f"You've defined buttons up to P1_BUTTON{max_defined_button}, but the game is set to use {current_buttons} buttons.\n\nWould you like to update the button count to {max_defined_button}?", 
                                    parent=editor):
                            buttons_var.set(str(max_defined_button))
                            game_entry["buttons"] = str(max_defined_button)
                    
                    elif max_defined_button < current_buttons:
                        if messagebox.askyesno("Reduce Button Count", 
                                    f"The highest button you've defined is P1_BUTTON{max_defined_button}, but the game is set to use {current_buttons} buttons.\n\nWould you like to reduce the button count to {max_defined_button}?", 
                                    parent=editor):
                            buttons_var.set(str(max_defined_button))
                            game_entry["buttons"] = str(max_defined_button)
                
                # Save to JSON
                gamedata[current_rom_name] = game_entry
                
                with open(gamedata_path, 'w', encoding='utf-8') as f:
                    json.dump(gamedata, f, indent=2)
                
                # Success message
                action_text = 'added to' if is_new_game else 'updated in'
                messagebox.showinfo("Success", 
                            f"Game '{current_rom_name}' {action_text} gamedata.json with {controls_added} control mappings", 
                            parent=editor)
                
                # Refresh data using startup logic
                if hasattr(self, 'gamedata_json'):
                    del self.gamedata_json
                self.load_gamedata_json()
                
                # FIXED: Rebuild database if needed OR if editing a clone
                if hasattr(self, 'db_path') and self.db_path:
                    # Check if we're editing a clone
                    is_editing_clone = (not is_new_game and 
                                    hasattr(self, 'parent_lookup') and 
                                    current_rom_name in self.parent_lookup)
                    
                    if check_db_update_needed(self.gamedata_path, self.db_path) or is_editing_clone:
                        from mame_data_utils import build_gamedata_db
                        build_gamedata_db(self.gamedata_json, self.db_path)
                
                # FIXED: Clear cache for edited ROM and related ROMs
                roms_to_clear = [current_rom_name]
                
                # If editing a clone, also clear parent cache
                if hasattr(self, 'parent_lookup') and current_rom_name in self.parent_lookup:
                    parent_rom = self.parent_lookup[current_rom_name]
                    roms_to_clear.append(parent_rom)
                
                # If editing a parent, clear all its clones' cache
                if hasattr(self, 'clone_parents') and current_rom_name in self.clone_parents:
                    clone_list = self.clone_parents[current_rom_name]
                    roms_to_clear.extend(clone_list)
                
                # Clear ROM data cache
                if hasattr(self, 'rom_data_cache'):
                    for rom_name in roms_to_clear:
                        if rom_name in self.rom_data_cache:
                            del self.rom_data_cache[rom_name]
                
                # Clear processed cache
                if hasattr(self, 'processed_cache'):
                    keys_to_remove = []
                    for rom_name in roms_to_clear:
                        keys_to_remove.extend([key for key in self.processed_cache.keys() if key.startswith(f"{rom_name}_")])
                    for key in keys_to_remove:
                        del self.processed_cache[key]
                
                # Update UI
                if hasattr(self, 'update_game_list_by_category'):
                    self.update_game_list_by_category(auto_select_first=False)
                
                if hasattr(self, 'current_game') and self.current_game == current_rom_name:
                    self.after(100, lambda: self.display_game_info(current_rom_name))
                
                # Reselect edited ROM
                edited_rom = current_rom_name
                self.after(150, lambda: self.reselect_rom_after_edit(edited_rom))
                
                # Close editor
                editor.destroy()
                        
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save game data: {str(e)}", parent=editor)
                import traceback
                traceback.print_exc()
        # Save button
        save_button = ctk.CTkButton(
            button_container,
            text="Save Controls",
            command=save_game,
            fg_color=self.theme_colors["success"],
            hover_color="#218838",
            font=("Arial", 14, "bold"),
            height=40,
            width=150
        )
        save_button.pack(side="right", padx=5)
        
        # Cancel button
        cancel_button = ctk.CTkButton(
            button_container,
            text="Cancel",
            command=editor.destroy,
            fg_color=self.theme_colors["danger"],
            hover_color="#c82333",
            font=("Arial", 14, "bold"),
            height=40,
            width=120
        )
        cancel_button.pack(side="right", padx=5)

        # Center the dialog on the screen
        editor.update_idletasks()
        width = editor.winfo_width()
        height = editor.winfo_height()
        x = (editor.winfo_screenwidth() // 2) - (width // 2)
        y = (editor.winfo_screenheight() // 2) - (height // 2)
        editor.geometry(f'{width}x{height}+{x}+{y}')

    def verify_data_consistency_after_save(self, rom_name):
        """Verify that ROM data is consistent between JSON and database after save"""
        try:
            print(f"\n=== VERIFYING DATA CONSISTENCY FOR {rom_name} ===")
            
            # Check JSON data
            json_controls = 0
            if rom_name in self.gamedata_json:
                json_controls = len(self.gamedata_json[rom_name].get('controls', {}))
                print(f"JSON: {json_controls} controls")
                
                # Show first few controls from JSON
                for i, (control_name, control_data) in enumerate(self.gamedata_json[rom_name].get('controls', {}).items()):
                    if i < 3:  # Show first 3
                        name_value = control_data.get('name', '') if isinstance(control_data, dict) else str(control_data)
                        print(f"  JSON: {control_name} -> '{name_value}'")
            else:
                print(f"JSON: ROM {rom_name} not found!")
            
            # Check database data
            db_controls = 0
            if hasattr(self, 'db_path') and os.path.exists(self.db_path):
                try:
                    import sqlite3
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM game_controls WHERE rom_name = ?", (rom_name,))
                    db_controls = cursor.fetchone()[0]
                    print(f"Database: {db_controls} controls")
                    
                    # Show first few controls from database
                    cursor.execute("SELECT control_name, display_name FROM game_controls WHERE rom_name = ? LIMIT 3", (rom_name,))
                    db_sample = cursor.fetchall()
                    for control_name, display_name in db_sample:
                        print(f"  DB: {control_name} -> '{display_name}'")
                    
                    conn.close()
                except Exception as e:
                    print(f"Database check failed: {e}")
            
            # Check what get_game_data returns
            game_data = self.get_game_data(rom_name)
            if game_data:
                ui_controls = sum(len(p.get('labels', [])) for p in game_data.get('players', []))
                print(f"get_game_data(): {ui_controls} controls, source: {game_data.get('source', 'unknown')}")
                
                # Show first few controls from game_data
                for player in game_data.get('players', []):
                    for i, label in enumerate(player.get('labels', [])):
                        if i < 3:  # Show first 3
                            print(f"  UI: {label['name']} -> '{label['value']}'")
                    break  # Just first player
            else:
                print(f"get_game_data(): No data returned!")
            
            # Summary
            if json_controls > 0 and db_controls > 0 and game_data:
                if json_controls == db_controls:
                    print(f"✅ CONSISTENT: All sources have matching control counts")
                else:
                    print(f"❌ INCONSISTENT: JSON({json_controls}) != DB({db_controls})")
            else:
                print(f"❌ MISSING DATA: JSON({json_controls}), DB({db_controls}), UI({bool(game_data)})")
                
        except Exception as e:
            print(f"Error in consistency check: {e}")
            import traceback
            traceback.print_exc()
    
    def reselect_rom_after_edit(self, rom_name):
        """Reselect the specified ROM after editing to maintain selection"""
        try:
            if not hasattr(self, 'game_list_data') or not self.game_list_data:
                return
            
            # Find the ROM in the current game list
            for i, (current_rom, display_text) in enumerate(self.game_list_data):
                if current_rom == rom_name:
                    # Found it! Select this item in the listbox
                    self.game_listbox.selection_clear(0, tk.END)
                    self.game_listbox.selection_set(i)
                    self.game_listbox.activate(i)
                    self.game_listbox.see(i)  # Scroll to make it visible
                    
                    # Update current_game
                    self.current_game = rom_name
                    self.selected_line = i + 1
                    
                    print(f"Reselected edited ROM: {rom_name} at index {i}")
                    return
            
            # If ROM not found in current list, it might be in a different category
            print(f"ROM {rom_name} not found in current list - may be in different category")
            
        except Exception as e:
            print(f"Error reselecting ROM after edit: {e}")
            # Fallback - just ensure the ROM is still the current game
            if hasattr(self, 'current_game'):
                self.current_game = rom_name
    
    def show_control_editor(self, rom_name, game_name=None):
        """Show enhanced editor for a game's controls by using the unified editor"""
        # Strip any prefixes (*, +, -) that might have been included in the ROM name
        if rom_name:
            # Remove common prefixes that might be part of the display format but not the actual ROM name
            if rom_name.startswith("* "):
                rom_name = rom_name[2:]
            if rom_name.startswith("+ ") or rom_name.startswith("- "):
                rom_name = rom_name[2:]
                
            # Strip any leading/trailing whitespace
            rom_name = rom_name.strip()
            
            print(f"Editing ROM with cleaned name: '{rom_name}'")
        
        # Check if this is a clone - if so, redirect to parent ROM
        if hasattr(self, 'parent_lookup') and rom_name in self.parent_lookup:
            parent_rom = self.parent_lookup[rom_name]
            # Show a brief message about the redirection
            messagebox.showinfo("Clone ROM", 
                            f"{rom_name} is a clone of {parent_rom}.\n\nEditing the parent ROM's controls instead.")
            # Redirect to edit the parent ROM
            rom_name = parent_rom
            # If we have game data for the clone, use it to provide context in the title
            clone_data = self.get_game_data(rom_name)
            if clone_data:
                game_name = clone_data.get('gamename', rom_name)
        
        # Get game data
        game_data = self.get_game_data(rom_name)
        
        # Check if this is an existing game or a new one
        is_new_game = not bool(game_data)
        
        # Use the unified editor instead of duplicating code
        self.show_unified_game_editor(rom_name, is_new_game, self)

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

    def remove_game(self, rom_name, dialog):
        """Remove a game entirely from the database"""
        # Confirm with user
        if not messagebox.askyesno(
            "Confirm Removal", 
            f"Are you sure you want to completely remove {rom_name} from the database?\n\nThis action cannot be undone!",
            icon="warning",
            parent=dialog
        ):
            return False
                
        try:
            # Load the gamedata.json file
            gamedata_path = self.gamedata_path
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
                messagebox.showerror(
                    "Error", 
                    f"Could not find {rom_name} in the database.",
                    parent=dialog
                )
                return False
            
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
            
            messagebox.showinfo(
                "Success", 
                f"{rom_name} has been removed from the database.",
                parent=dialog
            )
            
            # Close the editor
            dialog.destroy()
            
            # Refresh any currently displayed data
            # Since we removed the current game, we need to select a different game
            if self.current_game == rom_name:
                self.current_game = None
                self.game_title.configure(text="Select a game")
                # Clear the control frame
                for widget in self.control_frame.winfo_children():
                    widget.destroy()
            
            # Update sidebar categories
            if hasattr(self, 'update_game_list_by_category'):
                self.update_game_list_by_category()
            
            # Update stats label
            self.update_stats_label()
            
            return True
            
        except Exception as e:
            messagebox.showerror(
                "Error", 
                f"Failed to remove game: {str(e)}",
                parent=dialog
            )
            import traceback
            traceback.print_exc()
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

    # Update your get_game_data method in tkinter:
    @lru_cache(maxsize=128)  # Keep the cache decorator in tkinter
    def get_game_data(self, romname):
        """Get game data using utility function with manual caching"""
        # Check manual cache first
        if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
            return self.rom_data_cache[romname]
        
        # Call utils function
        from mame_data_utils import get_game_data
        result = get_game_data(
            romname=romname,
            gamedata_json=self.gamedata_json,
            parent_lookup=self.parent_lookup,
            db_path=self.db_path,
            rom_data_cache=getattr(self, 'rom_data_cache', {})
        )
        
        # Cache the result
        if not hasattr(self, 'rom_data_cache'):
            self.rom_data_cache = {}
        if result:
            self.rom_data_cache[romname] = result
        
        return result

    # Update the get_game_data_from_db method to handle controls without names
    def get_game_data_from_db(self, romname):
        """Get control data for a ROM from the SQLite database with better handling of unnamed controls"""
        
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
                SELECT control_name, display_name FROM game_controls WHERE rom_name = ?
            """, (romname,))
            control_rows = cursor.fetchall()
            
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
                # ADD SPECIALIZED CONTROLS:
                'P1_PEDAL': 'Accelerator Pedal',
                'P1_PEDAL2': 'Brake Pedal',
                'P1_AD_STICK_X': 'Analog Stick Left/Right',
                'P1_AD_STICK_Y': 'Analog Stick Up/Down',
                'P1_AD_STICK_Z': 'Analog Stick Z-Axis',
                'P1_DIAL': 'Dial Control',
                'P1_DIAL_V': 'Vertical Dial',
                'P1_PADDLE': 'Paddle Control',
                'P1_TRACKBALL_X': 'Trackball X-Axis',
                'P1_TRACKBALL_Y': 'Trackball Y-Axis',
                'P1_MOUSE_X': 'Mouse X-Axis',
                'P1_MOUSE_Y': 'Mouse Y-Axis',
                'P1_LIGHTGUN_X': 'Light Gun X-Axis',
                'P1_LIGHTGUN_Y': 'Light Gun Y-Axis',
                'P1_POSITIONAL': 'Positional Control',
                'P1_GAMBLE_HIGH': 'Gamble High',
                'P1_GAMBLE_LOW': 'Gamble Low',
                'P2_PEDAL': 'Accelerator Pedal',
                'P2_PEDAL2': 'Brake Pedal',
                'P2_AD_STICK_X': 'Analog Stick Left/Right',
                'P2_AD_STICK_Y': 'Analog Stick Up/Down',
                'P2_AD_STICK_Z': 'Analog Stick Z-Axis',
            }
            
            # System control mappings for non-P1_/P2_ prefixed controls
            system_control_mappings = {
                'SERVICE1': ('P1_SERVICE', 'Service Button'),
                'TEST1': ('P1_TEST', 'Test Button')
            }

            for control in control_rows:
                control_name = control[0]  # First column
                display_name = control[1]  # Second column
                
                # Handle system control mapping first
                if control_name in system_control_mappings:
                    mapped_name, default_action = system_control_mappings[control_name]
                    control_name = mapped_name  # Use the mapped name
                    if not display_name:
                        display_name = default_action
                
                # If display_name is empty, try to use a default
                if not display_name and control_name in default_actions:
                    display_name = default_actions[control_name]
                
                # If still no display name, try to extract from control name
                if not display_name:
                    parts = control_name.split('_')
                    if len(parts) > 1:
                        display_name = parts[-1].replace('_', ' ').title()
                    else:
                        display_name = control_name  # Last resort
                
                # Add to appropriate player list (NO FILTERING BY CONTROL TYPE)
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
            if conn:
                conn.close()
            return None
    
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
            # Check if this is a clone
            is_clone = hasattr(self, 'parent_lookup') and rom in self.parent_lookup
            
            if is_clone and hasattr(self, 'parent_lookup'):
                parent_rom = self.parent_lookup.get(rom, "")
                # Add special display for clones
                if rom == game_name:
                    game_listbox.insert(tk.END, f"{rom} [Clone of {parent_rom}]")
                else:
                    game_listbox.insert(tk.END, f"{rom} - {game_name} [Clone of {parent_rom}]")
            else:
                # Regular display for non-clones
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
                # This will use our updated show_control_editor which handles redirecting clones
                self.show_control_editor(rom, game_name)
        
        # Only show edit button if adding new games is allowed
        if self.ALLOW_ADD_NEW_GAME:  # or if False: to disable
            edit_button = ctk.CTkButton(
                button_frame,
                text="Edit Selected Game",
                command=edit_selected_game
            )
            edit_button.pack(side=tk.LEFT, padx=5)
        
        return list_frame
    
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
            cfg_controls = parse_cfg_controls(self.custom_configs[self.current_game], self.input_mode)
            
            # Convert based on current input mode
            current_mode = getattr(self, 'input_mode', 'xinput' if self.use_xinput else 'joycode')
            cfg_controls = {
                control: convert_mapping(mapping, current_mode)
                for control, mapping in cfg_controls.items()
            }
            
            # Modify game_data to include custom mappings
            game_data = update_game_data_with_custom_mappings(
                game_data, 
                cfg_controls, 
                getattr(self, 'default_controls', {}),
                getattr(self, 'original_default_controls', {}),
                self.input_mode
            )

        # NEW CODE: Filter out non-XInput controls if in XInput Only mode
        if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
            game_data = filter_xinput_controls(game_data)
        
        # Create cache directory if it doesn't exist yet
        cache_dir = os.path.join(self.preview_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        # Save the processed game data to the cache file
        cache_path = os.path.join(cache_dir, f"{self.current_game}_cache.json")
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(game_data, f, indent=2)
            print(f"Saved processed game data to cache: {cache_path}")
        except Exception as e:
            print(f"Warning: Could not save cache file: {e}")
        
        # The rest of the method remains unchanged
        
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
                messagebox.showerror("Error", "Could not find mame_controls_main.py")
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
                
            # Launch and track the process
            process = subprocess.Popen(command)
            if not hasattr(self, 'preview_processes'):
                self.preview_processes = []
            self.preview_processes.append(process)
        except Exception as e:
            print(f"Error launching preview: {e}")
            messagebox.showerror("Error", f"Failed to launch preview: {str(e)}")

    def toggle_hide_preview_buttons(self):
        """Toggle whether preview buttons should be hidden"""
        if hasattr(self, 'hide_buttons_toggle'):
            self.hide_preview_buttons = self.hide_buttons_toggle.get()
            print(f"Hide preview buttons set to: {self.hide_preview_buttons}")
            
            # Save setting to config file
            self.save_settings()
        
    def save_settings(self):
        """Save current settings to the standard settings file - UPDATED with ROM source mode"""
        settings = {
            "preferred_preview_screen": getattr(self, 'preferred_preview_screen', 1),
            "visible_control_types": getattr(self, 'visible_control_types', ["BUTTON", "JOYSTICK"]),
            "hide_preview_buttons": getattr(self, 'hide_preview_buttons', False),
            "show_button_names": getattr(self, 'show_button_names', True),
            "input_mode": getattr(self, 'input_mode', 'xinput'),
            "xinput_only_mode": getattr(self, 'xinput_only_mode', True),
            "rom_source_mode": getattr(self, 'rom_source_mode', 'physical')  # NEW SETTING
        }
        
        print(f"Debug - saving settings: {settings}")
        
        try:
            if hasattr(self, 'settings_path'):
                # Ensure settings directory exists
                os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
                
                # Save settings
                with open(self.settings_path, 'w') as f:
                    json.dump(settings, f, indent=2)
                print(f"Settings saved to: {self.settings_path}")
                return True
            else:
                print("Error: settings_path not available")
                return False
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def load_settings(self):
        """Load settings from JSON file in settings directory"""
        # Set sensible defaults
        self.preferred_preview_screen = 1
        self.visible_control_types = ["BUTTON"]
        self.hide_preview_buttons = False
        self.show_button_names = True
        self.input_mode = 'xinput'  # Change default to 'xinput' instead of boolean
        self.xinput_only_mode = True
        
        # Load custom settings if available
        if hasattr(self, 'settings_path') and os.path.exists(self.settings_path):
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
                    self.hide_preview_buttons = bool(settings.get('hide_preview_buttons', False))
                    
                    # Update toggle if it exists
                    if hasattr(self, 'hide_buttons_toggle'):
                        if self.hide_preview_buttons:
                            self.hide_buttons_toggle.select()
                        else:
                            self.hide_buttons_toggle.deselect()
                    
                # Load show button names setting
                if 'show_button_names' in settings:
                    self.show_button_names = bool(settings.get('show_button_names', True))
                    
                # Load input mode setting (Now supports 'joycode', 'xinput', 'dinput', or 'keycode')
                if 'input_mode' in settings:
                    self.input_mode = settings.get('input_mode', 'xinput')
                    # Ensure valid value
                    if self.input_mode not in ['joycode', 'xinput', 'dinput', 'keycode']:
                        self.input_mode = 'xinput'
                    
                # Load XInput Only Mode setting
                if 'xinput_only_mode' in settings:
                    self.xinput_only_mode = bool(settings.get('xinput_only_mode', True))
                    
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
            'input_mode': self.input_mode
        }

    def load_settings(self):
        """Load settings from JSON file in settings directory - UPDATED with ROM source mode"""
        # Set sensible defaults
        self.preferred_preview_screen = 1
        self.visible_control_types = ["BUTTON"]
        self.hide_preview_buttons = False
        self.show_button_names = True
        self.input_mode = 'xinput'
        self.xinput_only_mode = True
        self.rom_source_mode = 'physical'  # NEW DEFAULT
        
        # Load custom settings if available
        if hasattr(self, 'settings_path') and os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r') as f:
                    settings = json.load(f)
                    
                # Load existing settings...
                if 'preferred_preview_screen' in settings:
                    self.preferred_preview_screen = settings['preferred_preview_screen']
                    
                if 'visible_control_types' in settings:
                    if isinstance(settings['visible_control_types'], list):
                        self.visible_control_types = settings['visible_control_types']
                    
                    if "BUTTON" not in self.visible_control_types:
                        self.visible_control_types.append("BUTTON")

                if 'hide_preview_buttons' in settings:
                    self.hide_preview_buttons = bool(settings.get('hide_preview_buttons', False))
                    
                if 'show_button_names' in settings:
                    self.show_button_names = bool(settings.get('show_button_names', True))
                    
                if 'input_mode' in settings:
                    self.input_mode = settings.get('input_mode', 'xinput')
                    if self.input_mode not in ['joycode', 'xinput', 'dinput', 'keycode']:
                        self.input_mode = 'xinput'
                    
                if 'xinput_only_mode' in settings:
                    self.xinput_only_mode = bool(settings.get('xinput_only_mode', True))
                
                # NEW: Load ROM source mode setting
                if 'rom_source_mode' in settings:
                    self.rom_source_mode = settings.get('rom_source_mode', 'physical')
                    if self.rom_source_mode not in ['physical', 'database']:
                        self.rom_source_mode = 'physical'
                    
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
            'input_mode': self.input_mode,
            'rom_source_mode': self.rom_source_mode  # NEW
        }
    
    def save_settings(self):
        """Save current settings to the standard settings file"""
        settings = {
            "preferred_preview_screen": getattr(self, 'preferred_preview_screen', 1),
            "visible_control_types": getattr(self, 'visible_control_types', ["BUTTON", "JOYSTICK"]),
            "hide_preview_buttons": getattr(self, 'hide_preview_buttons', False),
            "show_button_names": getattr(self, 'show_button_names', True),
            "input_mode": getattr(self, 'input_mode', 'xinput'),  # Save as string
            "xinput_only_mode": getattr(self, 'xinput_only_mode', True)
        }
        
        print(f"Debug - saving settings: {settings}")
        
        try:
            if hasattr(self, 'settings_path'):
                # Ensure settings directory exists
                os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
                
                # Save settings
                with open(self.settings_path, 'w') as f:
                    json.dump(settings, f, indent=2)
                print(f"Settings saved to: {self.settings_path}")
                return True
            else:
                print("Error: settings_path not available")
                return False
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False
    
    def format_control_name(self, control_name: str) -> str:
        """Convert MAME control names to friendly names based on input type"""
        # Split control name into parts (e.g., 'P1_BUTTON1' -> ['P1', 'BUTTON1'])
        parts = control_name.split('_')
        if len(parts) < 2:
            return control_name
            
        player_num = parts[0]  # e.g., 'P1'
        control_type = '_'.join(parts[1:])  # Join rest in case of JOYSTICK_UP etc.
        
        if self.input_mode == 'joycode':
            # Simple JOYCODE-style formatting
            if control_type.startswith('BUTTON'):
                button_num = control_type[6:]  # Extract number from 'BUTTON1'
                return f"{player_num} Button {button_num}"
            elif control_type == 'JOYSTICK_UP':
                return f"{player_num} Joystick Up"
            elif control_type == 'JOYSTICK_DOWN':
                return f"{player_num} Joystick Down"
            elif control_type == 'JOYSTICK_LEFT':
                return f"{player_num} Joystick Left"
            elif control_type == 'JOYSTICK_RIGHT':
                return f"{player_num} Joystick Right"
            else:
                return f"{player_num}_{control_type}"
        
        elif self.input_mode == 'dinput':
            # DInput-style formatting
            if control_type.startswith('BUTTON'):
                button_index = int(control_type[6:]) - 1  # Convert from 1-based to 0-based
                if button_index < 0:
                    button_index = 0
                return f"{player_num} Button {button_index}"
            elif control_type == 'JOYSTICK_UP':
                return f"{player_num} Stick POV Up"
            elif control_type == 'JOYSTICK_DOWN':
                return f"{player_num} Stick POV Down"
            elif control_type == 'JOYSTICK_LEFT':
                return f"{player_num} Stick POV Left"
            elif control_type == 'JOYSTICK_RIGHT':
                return f"{player_num} Stick POV Right"
            else:
                return f"{player_num}_{control_type}"
        
        else:  # Default to XInput
            # XInput-style formatting
            control_mappings = {
                'BUTTON1': 'A Button',
                'BUTTON2': 'B Button',
                'BUTTON3': 'X Button',
                'BUTTON4': 'Y Button',
                'BUTTON5': 'LB Button',
                'BUTTON6': 'RB Button',
                'BUTTON7': 'Start Button',
                'BUTTON8': 'Back Button',
                'BUTTON9': 'L3 Button',
                'BUTTON10': 'R3 Button',
                'JOYSTICK_UP': 'Left Stick Up',
                'JOYSTICK_DOWN': 'Left Stick Down',
                'JOYSTICK_LEFT': 'Left Stick Left',
                'JOYSTICK_RIGHT': 'Left Stick Right',
                'JOYSTICKRIGHT_UP': 'Right Stick Up',
                'JOYSTICKRIGHT_DOWN': 'Right Stick Down',
                'JOYSTICKRIGHT_LEFT': 'Right Stick Left',
                'JOYSTICKRIGHT_RIGHT': 'Right Stick Right',
            }
            
            # Check if we have a mapping for this control
            if control_type in control_mappings:
                return f"{player_num} {control_mappings[control_type]}"
            
            return f"{player_num}_{control_type}"

    def select_first_rom(self):
        """Select the first available ROM in the listbox"""
        # Check if we have any ROMs
        if not self.available_roms:
            print("No available ROMs, exiting select_first_rom")
            return
        
        # Make sure the game_list_data is populated
        if not hasattr(self, 'game_list_data') or not self.game_list_data:
            # If we don't have any items in the data list yet, trigger an update
            if hasattr(self, 'update_game_list_by_category'):
                self.update_game_list_by_category()
        
        # Check if we have any items in the listbox
        if not hasattr(self, 'game_listbox') or self.game_listbox.size() == 0:
            print("No ROMs found in listbox")
            return
            
        # Select the first item in the listbox
        self.game_listbox.selection_clear(0, tk.END)  # Clear any existing selection
        self.game_listbox.selection_set(0)  # Select the first item
        self.game_listbox.activate(0)  # Make it the active item
        self.game_listbox.see(0)  # Ensure it's visible
        
        # Get the ROM name for the first item
        if hasattr(self, 'game_list_data') and len(self.game_list_data) > 0:
            first_rom, _ = self.game_list_data[0]
            self.current_game = first_rom
            
            # Update selected_line for compatibility with other methods
            self.selected_line = 1
            
            # Display the ROM info
            self.after(200, lambda: self.display_game_info(first_rom))
        else:
            print("No game data available for selection")
            
        print(f"Selected first ROM: {getattr(self, 'current_game', 'None')}")

            
    def highlight_selected_game(self, line_index):
        """Highlight the selected game in the list with enhanced visual styling"""
        if hasattr(self, 'game_listbox'):
            # Clear any previous selection
            self.game_listbox.selection_clear(0, tk.END)
            
            # Convert from 1-indexed to 0-indexed if needed
            listbox_index = line_index - 1 if line_index > 0 else 0
            
            # Set the new selection
            if listbox_index < self.game_listbox.size():
                self.game_listbox.selection_set(listbox_index)
                self.game_listbox.activate(listbox_index)
                self.game_listbox.see(listbox_index)
            
            # Store the selected line (1-indexed for backward compatibility)
            self.selected_line = line_index
        else:
            # Fallback for original text widget if it exists
            if hasattr(self, 'game_list') and hasattr(self.game_list, '_textbox'):
                # Clear previous highlight if any
                if self.selected_line is not None:
                    self.game_list._textbox.tag_remove(self.highlight_tag, f"{self.selected_line}.0", f"{self.selected_line + 1}.0")
                
                # Apply new highlight
                self.selected_line = line_index
                self.game_list._textbox.tag_add(self.highlight_tag, f"{line_index}.0", f"{line_index + 1}.0")
                
                # Ensure the selected item is visible
                self.game_list.see(f"{line_index}.0")

    def create_hover_label(self, parent, text, font, color, bg_color, x_pos, width, tooltip_text=None):
        """Create a label with hover functionality and tooltip for long text"""
        
        # Check if text is longer than available width
        import tkinter.font as tkFont
        font_obj = tkFont.Font(font=font)
        text_width = font_obj.measure(text)
        
        is_truncated = text_width > width - 10  # 10px padding
        
        # Use different colors based on whether text is truncated
        if is_truncated:
            # Use a lighter blue for truncated text to indicate it's hoverable
            display_color = self.theme_colors["highlight"]  # Lighter blue for truncated
            hover_color = self.theme_colors["secondary"]    # Brighter blue on hover
        else:
            # Use original color for normal text
            display_color = color
            hover_color = color  # No color change for non-truncated text
        
        label = tk.Label(
            parent,
            text=text,
            font=font,
            anchor="w",
            justify="left",
            background=bg_color,
            foreground=display_color
        )
        label.place(x=x_pos, y=10, width=width)
        
        # If text is too long, add hover functionality
        if is_truncated:
            
            # Store colors
            original_color = display_color
            
            # Tooltip window reference
            tooltip = None
            
            def on_enter(event):
                nonlocal tooltip
                # Change to brighter blue
                label.configure(foreground=hover_color)
                
                # Create tooltip
                tooltip = tk.Toplevel()
                tooltip.wm_overrideredirect(True)
                tooltip.configure(bg="#2d2d2d", relief="solid", borderwidth=1)
                
                tooltip_label = tk.Label(
                    tooltip,
                    text=tooltip_text or text,
                    background="#2d2d2d",
                    foreground="white",
                    font=font,
                    padx=8,
                    pady=4
                )
                tooltip_label.pack()
                
                # Position tooltip near mouse
                x = event.x_root + 10
                y = event.y_root + 10
                tooltip.geometry(f"+{x}+{y}")
            
            def on_leave(event):
                nonlocal tooltip
                # Restore lighter blue color (not original color)
                label.configure(foreground=original_color)
                
                # Destroy tooltip
                if tooltip:
                    tooltip.destroy()
                    tooltip = None
            
            # Bind hover events
            label.bind("<Enter>", on_enter)
            label.bind("<Leave>", on_leave)
            
            # Add cursor change to indicate it's interactive
            label.configure(cursor="hand2")
        
        return label
    
    
    # Complete updated display_controls_table method with proper mappings support and fixed alignment
    def display_controls_table(self, start_row, game_data, cfg_controls):
        """
        Display game information and controls with mappings support and proper alignment
        """
        try:
            row = start_row
            
            # Get romname from game_data
            romname = game_data.get('romname', '')
            
            # Clear existing controls
            children_to_destroy = list(self.control_frame.winfo_children())
            for widget in children_to_destroy:
                widget.destroy()
            
            # Force immediate cleanup
            self.control_frame.update_idletasks()
            
            # Collect metadata once - INCLUDING MAPPINGS
            metadata = {
                'romname': romname,
                'gamename': game_data['gamename'],
                'numPlayers': game_data['numPlayers'],
                'alternating': game_data['alternating'],
                'mirrored': game_data.get('mirrored', False),
                'miscDetails': game_data.get('miscDetails', ''),
                'mappings': game_data.get('mappings', []),  # ENSURE MAPPINGS ARE INCLUDED
                'source': game_data.get('source', 'unknown'),
                'input_mode': self.input_mode
            }
            
            # Pre-process control data
            processed_controls = []
            has_rom_cfg_used = False
            has_default_cfg = hasattr(self, 'default_controls') and bool(self.default_controls)
            
            for player in game_data.get('players', []):
                if player.get('number') == 1:  # Only Player 1 for now
                    for label in player.get('labels', []):
                        control_name = label['name']
                        action = label['value']
                        
                        # Pre-extract all display data
                        display_name = label.get('display_name', label.get('target_button', action))
                        mapping_source = label.get('mapping_source', 'Game Data')
                        is_custom = label.get('is_custom', False)
                        mapping = label.get('mapping', '')
                        
                        if is_custom:
                            has_rom_cfg_used = True
                        
                        # Determine source color once
                        if 'ROM CFG' in mapping_source:
                            source_color = self.theme_colors["success"]
                        elif 'Default CFG' in mapping_source:
                            source_color = self.theme_colors["primary"]
                        else:
                            source_color = "#888888"
                        
                        # Pre-format display source
                        display_source = "ROM CFG" if "ROM CFG" in mapping_source else \
                                    "Default CFG" if "Default CFG" in mapping_source else "Game Data"
                        
                        processed_controls.append({
                            'control_name': control_name,
                            'action': action,
                            'display_name': display_name,
                            'mapping_source': mapping_source,
                            'source_color': source_color,
                            'display_source': display_source,
                            'is_custom': is_custom,
                            'mapping': mapping
                        })
            
            # === GAME INFO CARD ===
            info_card = ctk.CTkFrame(self.control_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
            info_card.pack(fill="x", padx=10, pady=10, expand=True)
            info_card.columnconfigure(0, weight=1)
            
            # Metadata section - SINGLE COLUMN LAYOUT
            metadata_frame = ctk.CTkFrame(info_card, fg_color="transparent")
            metadata_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
            metadata_frame.columnconfigure(0, weight=1)
            
            # Single info section with everything together
            info_section = ctk.CTkFrame(metadata_frame, fg_color="transparent")
            info_section.grid(row=0, column=0, sticky="ew")
            info_section.columnconfigure(0, weight=1)
            
            ctk.CTkLabel(
                info_section,
                text="ROM Information",
                font=("Arial", 14, "bold"),
                anchor="w"
            ).pack(anchor="w", pady=(0, 10), fill="x")
            
            # Build complete info text including additional details
            info_text = f"ROM Name: {metadata['romname']}\n"
            info_text += f"Players: {metadata['numPlayers']}\n"
            info_text += f"Alternating Play: {'Yes' if metadata['alternating'] else 'No'}\n"
            info_text += f"Mirrored Controls: {'Yes' if metadata['mirrored'] else 'No'}"
            
            # Add miscDetails if available
            if metadata['miscDetails']:
                info_text += f"\n{metadata['miscDetails']}"
            
            # Add mappings if available
            if metadata['mappings']:
                if len(metadata['mappings']) == 1:
                    info_text += f"\nMapping: {metadata['mappings'][0]}"
                else:
                    mappings_str = ", ".join(metadata['mappings'])
                    info_text += f"\nMappings: {mappings_str}"
            
            ctk.CTkLabel(
                info_section,
                text=info_text,
                font=("Arial", 13),
                justify="left",
                anchor="w"
            ).pack(anchor="w", fill="x")
            
            # === STATUS INDICATORS ===
            indicator_frame = ctk.CTkFrame(info_card, fg_color="transparent")
            indicator_frame.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="ew")
            
            # Create status grid efficiently
            status_grid = ctk.CTkFrame(indicator_frame, fg_color="transparent")
            status_grid.pack(fill="x")
            
            # Pre-calculate all status info
            has_rom_cfg_file = romname in self.custom_configs
            has_gamedata_entry = romname in self.gamedata_json or (hasattr(self, 'parent_lookup') and romname in self.parent_lookup)
            has_control_mappings = bool(processed_controls)
            
            # Status rows data
            status_rows = [
                {
                    'label': 'ROM CFG File:',
                    'text': f"EXISTS & USED ({romname}.cfg)" if has_rom_cfg_used else 
                        f"EXISTS BUT EMPTY ({romname}.cfg)" if has_rom_cfg_file else "NOT FOUND",
                    'color': self.theme_colors["success"] if has_rom_cfg_used else 
                            self.theme_colors["warning"] if has_rom_cfg_file else self.theme_colors["text_dimmed"]
                },
                {
                    'label': 'GameData Entry:',
                    'text': "EXISTS WITH CONTROLS" if has_control_mappings else 
                        "EXISTS BUT NO CONTROLS" if has_gamedata_entry else "NOT FOUND",
                    'color': self.theme_colors["success"] if has_control_mappings else 
                            self.theme_colors["warning"] if has_gamedata_entry else self.theme_colors["text_dimmed"]
                },
                {
                    'label': 'Active Source:',
                    'text': "ROM CFG" if has_rom_cfg_used else "DEFAULT CFG" if has_default_cfg else 
                        "GAMEDATA" if has_control_mappings else "NONE",
                    'color': self.theme_colors["success"] if has_rom_cfg_used else 
                            self.theme_colors["primary"] if has_default_cfg else 
                            self.theme_colors["secondary"] if has_control_mappings else self.theme_colors["danger"]
                },
                {
                    'label': 'Input Mode:',
                    'text': metadata['input_mode'].upper(),
                    'color': self.theme_colors["primary"]
                }
            ]
            
            # Create status rows efficiently
            for status in status_rows:
                status_frame = ctk.CTkFrame(status_grid, fg_color="transparent")
                status_frame.pack(fill="x", pady=2)
                
                ctk.CTkLabel(
                    status_frame,
                    text=status['label'],
                    font=("Arial", 12),
                    anchor="w",
                    width=120
                ).pack(side="left")
                
                ctk.CTkLabel(
                    status_frame,
                    text=status['text'],
                    font=("Arial", 12, "bold"),
                    text_color=status['color'],
                    anchor="w"
                ).pack(side="left", padx=(10, 0))
            
            # === CONTROLS CARD ===
            controls_card = ctk.CTkFrame(self.control_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
            controls_card.pack(fill="x", padx=10, pady=10, expand=True)
            controls_card.columnconfigure(0, weight=1)
            
            # Title and edit button frame
            title_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
            title_frame.pack(fill="x", padx=15, pady=(15, 10))
            
            # Input mode toggle
            input_mode_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
            input_mode_frame.pack(fill="x", padx=15, pady=(5, 10))
            
            ctk.CTkLabel(
                input_mode_frame,
                text="Input Mode:",
                font=("Arial", 13),
                anchor="w"
            ).pack(side="left", padx=(0, 10))
            
            # Create radio buttons efficiently
            if not hasattr(self, 'input_mode_var'):
                self.input_mode_var = tk.StringVar(value=self.input_mode)
            
            mode_buttons = [
                ("XInput", "xinput"), 
                ("DInput", "dinput"),
                ("KEYCODE", "keycode")
            ]
            
            for text, value in mode_buttons:
                mode_button = ctk.CTkRadioButton(
                    input_mode_frame,
                    text=text,
                    variable=self.input_mode_var,
                    value=value,
                    command=self.toggle_input_mode,
                    fg_color=self.theme_colors["primary"],
                    hover_color=self.theme_colors["secondary"]
                )
                mode_button.pack(side="left", padx=(0, 15))
            
            # Title and edit button
            ctk.CTkLabel(
                title_frame,
                text="Player 1 Controller Mappings",
                font=("Arial", 16, "bold"),
                anchor="w"
            ).pack(side="left", anchor="w")
            
            edit_button = ctk.CTkButton(
                title_frame,
                text="Edit Controls",
                command=self.edit_current_game_controls,
                width=120,
                height=30,
                fg_color=self.theme_colors["primary"],
                hover_color=self.theme_colors["button_hover"]
            )
            edit_button.pack(side="right", padx=5)
            
            # === CONTROLS DISPLAY ===
            if not processed_controls:
                # No controls message
                empty_frame = ctk.CTkFrame(controls_card, fg_color=self.theme_colors["background"], corner_radius=4)
                empty_frame.pack(fill="x", padx=15, pady=15)
                
                ctk.CTkLabel(
                    empty_frame,
                    text="No controller mappings found for Player 1",
                    font=("Arial", 13),
                    text_color=self.theme_colors["text_dimmed"]
                ).pack(pady=20)
                
                return row + 1
            
            # Controls display with canvas
            canvas_container = ctk.CTkFrame(controls_card, fg_color="transparent")
            canvas_container.pack(fill="both", expand=True, padx=15, pady=5)
            
            # Header frame
            header_frame = ctk.CTkFrame(canvas_container, fg_color=self.theme_colors["primary"], height=36)
            header_frame.pack(fill="x", pady=(0, 5))
            header_frame.pack_propagate(False)
            
            # Header setup
            header_titles = ["MAME Control", "Controller Input", "Game Action", "Mapping Source"]
            col_widths = [180, 200, 180, 160]
            x_positions = [15]
            for i in range(1, len(header_titles)):
                x_positions.append(x_positions[i-1] + col_widths[i-1] + 15)
            
            for i, title in enumerate(header_titles):
                header_label = ctk.CTkLabel(
                    header_frame,
                    text=title,
                    font=("Arial", 13, "bold"),
                    text_color="#ffffff",
                    anchor="w",
                    justify="left"
                )
                header_label.place(x=x_positions[i], y=5)
            
            # Canvas for controls
            num_controls = len(processed_controls)
            canvas_height = min(400, num_controls * 40 + 10)
            
            canvas = tk.Canvas(
                canvas_container,
                height=canvas_height,
                background=self.theme_colors["card_bg"],
                highlightthickness=0,
                bd=0
            )
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Scrollbar
            scrollbar = ctk.CTkScrollbar(
                canvas_container, 
                orientation="vertical",
                command=canvas.yview,
                button_color=self.theme_colors["primary"],
                button_hover_color=self.theme_colors["secondary"],
                fg_color=self.theme_colors["card_bg"],
                corner_radius=10,
                width=14
            )
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            canvas.configure(yscrollcommand=scrollbar.set)
            
            # Controls frame
            controls_frame = tk.Frame(canvas, background=self.theme_colors["card_bg"])
            canvas_window = canvas.create_window((0, 0), window=controls_frame, anchor=tk.NW)
            
            # Create control rows
            alt_colors = [self.theme_colors["card_bg"], self.theme_colors["card_bg"]]
            
            for i, control in enumerate(processed_controls):
                row_frame = tk.Frame(
                    controls_frame,
                    background=alt_colors[i % 2],
                    height=40
                )
                row_frame.pack(fill=tk.X, pady=1, expand=True)
                row_frame.pack_propagate(False)
                
                # Create labels with pre-processed data
                labels_data = [
                    (control['control_name'], ("Consolas", 12), "#888888"),
                    (control['display_name'], ("Arial", 13), self.theme_colors["primary"]),
                    (control['action'], ("Arial", 13, "bold"), self.theme_colors["text"]),
                    (control['display_source'], ("Arial", 12), control['source_color'])
                ]
                
                # With this:
                for j, (text, font, color) in enumerate(labels_data):
                    # Create tooltip text for long entries
                    tooltip_text = None
                    if j == 2 and len(text) > 20:  # Game Action column with long text
                        tooltip_text = f"Full Action: {text}"
                    elif j == 1 and len(text) > 25:  # Controller Input column with long text
                        tooltip_text = f"Full Input: {text}"
                    
                    label = self.create_hover_label(
                        row_frame,
                        text=text,
                        font=font,
                        color=color,
                        bg_color=alt_colors[i % 2],
                        x_pos=x_positions[j],
                        width=col_widths[j],
                        tooltip_text=tooltip_text
                    )
            
            # Canvas update functions
            def update_canvas_width(event=None):
                canvas_width = canvas.winfo_width()
                canvas.itemconfig(canvas_window, width=canvas_width)
                for child in controls_frame.winfo_children():
                    if isinstance(child, tk.Frame):
                        child.configure(width=canvas_width)
            
            canvas.bind("<Configure>", update_canvas_width)
            controls_frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.update_idletasks()
            update_canvas_width()
            
            return row + 1

        except Exception as e:
            print(f"Error in controls display: {e}")
            import traceback
            traceback.print_exc()
            return start_row + 1
    
    def toggle_input_mode(self):
        """Handle toggling between input modes with cache clearing"""
        if hasattr(self, 'input_mode_var'):
            old_mode = self.input_mode
            self.input_mode = self.input_mode_var.get()
            print(f"Input mode changed from {old_mode} to {self.input_mode}")
            
            # Clear BOTH caches when mode changes
            if hasattr(self, 'rom_data_cache'):
                self.rom_data_cache.clear()
            if hasattr(self, 'processed_cache'):
                self.processed_cache.clear()
                print("Cleared processed cache due to input mode change")
            
            # Save the setting
            self.save_settings()
            
            # Refresh current game display if one is selected
            if self.current_game:
                # This will trigger fresh processing with new input mode
                self.display_game_info(self.current_game)
                
                # Update status message
                self.update_status_message(f"Input mode changed to {self.input_mode.upper()}")
        
    def categorize_controls_properly(self, rom_name):
        """
        Properly categorize a ROM's controls - CORRECTED VERSION
        Returns: dict with boolean flags for each category
        """
        result = {
            'has_controls': False,
            'has_generic_controls': False,  # Has controls but no "name" fields
            'has_custom_controls': False,   # Has controls with "name" fields
            'has_cfg_file': False          # Has .cfg file override
        }
        
        # Check if ROM has a .cfg file
        result['has_cfg_file'] = rom_name in self.custom_configs
        
        # Function to check if controls have "name" fields
        def check_controls_for_names(controls_dict):
            has_names = False
            for control_name, control_data in controls_dict.items():
                if isinstance(control_data, dict) and 'name' in control_data:
                    name_value = control_data['name']
                    if name_value and name_value.strip():  # Non-empty name
                        has_names = True
                        break
            return has_names
        
        # Check ROM directly
        if rom_name in self.gamedata_json:
            rom_data = self.gamedata_json[rom_name]
            if 'controls' in rom_data and rom_data['controls']:
                result['has_controls'] = True
                # Check if any controls have "name" fields
                if check_controls_for_names(rom_data['controls']):
                    result['has_custom_controls'] = True
                else:
                    result['has_generic_controls'] = True
        
        # Check parent ROM if this is a clone
        elif hasattr(self, 'parent_lookup') and rom_name in self.parent_lookup:
            parent_rom = self.parent_lookup[rom_name]
            if parent_rom in self.gamedata_json:
                parent_data = self.gamedata_json[parent_rom]
                if 'controls' in parent_data and parent_data['controls']:
                    result['has_controls'] = True
                    # Check if any controls have "name" fields
                    if check_controls_for_names(parent_data['controls']):
                        result['has_custom_controls'] = True
                    else:
                        result['has_generic_controls'] = True
        
        # If no gamedata.json entry, check if it has control data from other sources
        if not result['has_controls']:
            from mame_data_utils import get_game_data
            game_data = get_game_data(rom_name, self.gamedata_json, self.parent_lookup, 
                                    self.db_path, getattr(self, 'rom_data_cache', {}))
            if game_data and game_data.get('players'):
                result['has_controls'] = True
                result['has_generic_controls'] = True  # Has controls but no gamedata.json names
        
        return result

    def update_stats_label(self):
        """Update the statistics label with corrected categorization - UPDATED for ROM source mode"""
        try:
            total_roms = len(self.available_roms)
            
            # Add mode indicator to stats
            mode_text = "Database" if self.rom_source_mode == "database" else "Physical"
            
            # Categorize all ROMs properly
            with_controls = 0
            missing_controls = 0
            generic_controls = 0
            custom_controls = 0
            with_cfg_files = 0
            clone_roms = 0
            
            for rom in self.available_roms:
                # Check if it's a clone
                if hasattr(self, 'parent_lookup') and rom in self.parent_lookup:
                    clone_roms += 1
                
                # Categorize controls
                categories = self.categorize_controls_properly(rom)
                
                if categories['has_controls']:
                    with_controls += 1
                    
                    if categories['has_generic_controls']:
                        generic_controls += 1
                    elif categories['has_custom_controls']:
                        custom_controls += 1
                else:
                    missing_controls += 1
                
                if categories['has_cfg_file']:
                    with_cfg_files += 1
            
            # Format the stats with mode indicator
            stats = (
                f"Mode: {mode_text}\n"
                f"ROMs: {total_roms}\n"
                f"With Controls: {with_controls} ({with_controls/max(total_roms, 1)*100:.1f}%)\n"
                f"Missing Controls: {missing_controls}\n"
                f"Custom Actions: {custom_controls}\n"
                f"Generic Controls: {generic_controls}\n"
            )
            
            # Only show clone count in physical mode (database mode shows parents only)
            if self.rom_source_mode == "physical":
                stats += f"Clone ROMs: {clone_roms}\n"
            
            self.stats_label.configure(text=stats)
            
            # Debug output
            print(f"Stats ({mode_text}): Total={total_roms}, WithControls={with_controls}, "
                f"Missing={missing_controls}, Custom={custom_controls}, "
                f"Generic={generic_controls}, CFG={with_cfg_files}, Clones={clone_roms}")
            
        except Exception as e:
            print(f"Error updating stats: {e}")
            import traceback
            traceback.print_exc()
            self.stats_label.configure(text="Statistics: Error")
   
    def update_game_list(self):
        """Update the game list to show all available ROMs with improved performance"""
        # For compatibility, now just calls the category-based update
        self.update_game_list_by_category()

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
        """Filter the game list based on search text with debouncing and direct filtering for Listbox"""
        # If we had a scheduled update, cancel it
        if hasattr(self, '_filter_timer') and self._filter_timer:
            self.after_cancel(self._filter_timer)
            self._filter_timer = None

        # Schedule a new update after short delay (300ms)
        self._filter_timer = self.after(200, self._perform_filtering)
    
    def _perform_filtering(self):
        """Actually perform the filtering after debounce delay for Listbox"""
        try:
            # Get search text
            search_text = self.search_var.get().lower().strip()
            
            # Skip rebuild if search text is empty
            if not search_text:
                # Just do a normal category update
                self.update_game_list_by_category()
                return
            
            # Get the current category list without filtering
            category_roms = self._get_category_roms()
            
            # Apply filter directly to this list
            filtered_roms = self._filter_rom_list(category_roms, search_text)
            
            # Update the listbox with filtered roms (reusing code from update_game_list_by_category)
            self.game_list_data = []
            list_display_items = []
            
            # Check if we have any ROMs to display
            if not filtered_roms:
                self.game_listbox.delete(0, tk.END)
                self.game_listbox.insert(tk.END, "No matching ROMs found.")
                
                # Update the title
                title = f"{self.current_view.capitalize()} (filtered: 0)"
                self.update_list_title(title)
                return
            
            # Build display items for each ROM
            for rom in filtered_roms:
                # Determine display format
                has_config = rom in self.custom_configs
                has_data = self.get_game_data(rom) is not None
                is_clone = rom in self.parent_lookup if hasattr(self, 'parent_lookup') else False
                
                # Create display text without prefixes
                if is_clone and (self.current_view == "clones" or self.current_view == "all"):
                    parent_rom = self.parent_lookup.get(rom, "")
                    
                    # Get game name if available
                    if has_data:
                        game_data = get_game_data(rom, self.gamedata_json, self.parent_lookup, 
                                                self.db_path, getattr(self, 'rom_data_cache', {}))
                        display_text = f"{rom} - {game_data['gamename']} [Clone of {parent_rom}]"
                    else:
                        display_text = f"{rom} [Clone of {parent_rom}]"
                else:
                    # Regular display for non-clones or when not in clone view
                    if has_data:
                        if hasattr(self, 'name_cache') and rom in self.name_cache:
                            game_name = self.name_cache[rom].capitalize()
                            display_text = f"{rom} - {game_name}"
                        else:
                            game_data = get_game_data(rom, self.gamedata_json, self.parent_lookup, 
                                                    self.db_path, getattr(self, 'rom_data_cache', {}))
                            display_text = f"{rom} - {game_data['gamename']}"
                    else:
                        display_text = f"{rom}"
                
                # Store both the ROM name and display text
                self.game_list_data.append((rom, display_text))
                list_display_items.append(display_text)
            
            # Remember current selection if any
            current_selection = None
            if hasattr(self, 'current_game') and self.current_game:
                current_selection = self.current_game
            
            # Update the listbox
            self.game_listbox.delete(0, tk.END)
            for item in list_display_items:
                self.game_listbox.insert(tk.END, item)
            
            # Update the title
            view_titles = {
                "all": "All ROMs",
                "with_controls": "ROMs with Controls",
                "missing": "ROMs Missing Controls",
                "custom_config": "ROMs with Custom Config",
                "generic": "ROMs with Generic Controls",
                "clones": "Clone ROMs"
            }
            title = f"{view_titles.get(self.current_view, 'ROMs')} (filtered: {len(filtered_roms)})"
            self.update_list_title(title)
            
            # Try to re-select previously selected ROM if it's in the filtered results
            if current_selection:
                found_index = None
                for i, (rom_name, _) in enumerate(self.game_list_data):
                    if rom_name == current_selection:
                        found_index = i
                        break
                
                if found_index is not None:
                    # Clear any existing selection
                    self.game_listbox.selection_clear(0, tk.END)
                    
                    # Select the item
                    self.game_listbox.selection_set(found_index)
                    self.game_listbox.see(found_index)
                    self.game_listbox.activate(found_index)
                    
                    # Force refresh with current input mode
                    rom_name = self.game_list_data[found_index][0]
                    
                    # Clear cache to force refresh with current input mode
                    if hasattr(self, 'rom_data_cache') and rom_name in self.rom_data_cache:
                        print(f"Clearing cache for {rom_name} to ensure refresh with current input mode")
                        del self.rom_data_cache[rom_name]
                    
                    # Update the display with current input mode
                    self.after(50, lambda: self.display_game_info(rom_name))
                
        except Exception as e:
            print(f"Error in search filtering: {e}")
            import traceback
            traceback.print_exc()

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
        """Load gamedata.json using the utility function"""
        try:
            self.gamedata_json, self.parent_lookup, self.clone_parents = load_gamedata_json(self.gamedata_path)
            return self.gamedata_json
        except Exception as e:
            # Handle GUI-specific error display
            if hasattr(self, 'splash_window') and self.splash_window:
                self.splash_window.destroy()
            messagebox.showerror("Error Loading gamedata.json", str(e))
            self.after(1, self.force_close_with_json_error)
            return {}

    def force_close_with_json_error(self):
        """Force close the application after a JSON error"""
        try:
            print("Forcing application close due to JSON error...")
            
            # Clean up any resources
            if hasattr(self, 'async_loader'):
                try:
                    self.async_loader.stop_worker()
                except:
                    pass
            
            # Destroy any remaining windows
            if hasattr(self, 'splash_window') and self.splash_window:
                try:
                    self.splash_window.destroy()
                except:
                    pass
            
            # Cancel any pending after() calls
            try:
                # Cancel all pending after() calls
                for i in range(1000):  # Clear a reasonable number of pending calls
                    try:
                        self.after_cancel(f"after#{i}")
                    except:
                        pass
            except:
                pass
            
            # Withdraw the main window immediately
            try:
                self.withdraw()
            except:
                pass
            
            # Exit the application immediately
            self.quit()
            
            # Force exit if needed
            import sys
            print("Exiting application...")
            sys.exit(1)
            
        except Exception as e:
            print(f"Error during forced close: {e}")
            # Force exit even if cleanup fails
            import sys
            sys.exit(1)

    def has_json_error(self):
        """Check if there was a JSON loading error"""
        return hasattr(self, '_json_error_shown') and self._json_error_shown

    def export_image_headless(self, output_path, format="png"):
        """Export preview image in headless mode using existing save_image functionality with bezel settings"""
        try:
            print(f"Exporting preview image to {output_path} with bezel_visible={getattr(self, 'bezel_visible', 'Not set')}")
            
            # Force bezel visibility based on the settings again, just to be sure
            if hasattr(self, 'bezel_visible') and self.bezel_visible and hasattr(self, 'has_bezel') and self.has_bezel:
                # Ensure bezel is visible for export
                if hasattr(self, 'show_bezel_with_background'):
                    print("Forcing bezel visibility for export...")
                    self.show_bezel_with_background()
                    
                    # Force bezel to top of z-order
                    if hasattr(self, 'bezel_label') and self.bezel_label:
                        self.bezel_label.raise_()
                        
                    # Add a brief delay to ensure bezel is rendered
                    from PyQt5.QtCore import QTimer
                    from PyQt5.QtWidgets import QApplication
                    QTimer.singleShot(200, lambda: None)
                    QApplication.processEvents()  # Process events to update UI
            
            # Ensure controls are above bezel
            if hasattr(self, 'raise_controls_above_bezel'):
                self.raise_controls_above_bezel()
                
            # If the original save_image function exists, use it
            if hasattr(self, 'save_image'):
                # Get the current output path to restore it later
                original_output_path = getattr(self, '_output_path', None)
                
                # Set the output path temporarily
                self._output_path = output_path
                
                # Instead of just calling save_image, we'll duplicate its functionality here
                # to ensure we have complete control over the process
                
                # Create a new image with the same size as the canvas
                from PyQt5.QtGui import QImage, QPainter, QPixmap, QColor
                from PyQt5.QtCore import Qt
                
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
                    bg_pixmap = self.background_pixmap
                    
                    # Calculate position to center the pixmap
                    x = (self.canvas.width() - bg_pixmap.width()) // 2
                    y = (self.canvas.height() - bg_pixmap.height()) // 2
                    
                    # Draw the pixmap
                    painter.drawPixmap(x, y, bg_pixmap)
                
                # Draw the bezel if it's visible
                if hasattr(self, 'bezel_visible') and self.bezel_visible and hasattr(self, 'bezel_pixmap'):
                    bezel_pixmap = getattr(self, 'bezel_pixmap', None)
                    if bezel_pixmap and not bezel_pixmap.isNull():
                        # Position bezel in center
                        x = (self.canvas.width() - bezel_pixmap.width()) // 2
                        y = (self.canvas.height() - bezel_pixmap.height()) // 2
                        painter.drawPixmap(x, y, bezel_pixmap)
                        print(f"Drew bezel at {x},{y} with size {bezel_pixmap.width()}x{bezel_pixmap.height()}")
                
                # Draw the logo if visible
                if hasattr(self, 'logo_label') and self.logo_label and self.logo_label.isVisible():
                    logo_pixmap = self.logo_label.pixmap()
                    if logo_pixmap and not logo_pixmap.isNull():
                        painter.drawPixmap(self.logo_label.pos(), logo_pixmap)
                
                # Draw control labels
                if hasattr(self, 'control_labels'):
                    for control_name, control_data in self.control_labels.items():
                        label = control_data['label']
                        
                        # Skip if not visible
                        if not label.isVisible():
                            continue
                        
                        # Get label position
                        pos = label.pos()
                        
                        # Get settings and properties from the label
                        settings = getattr(label, 'settings', {})
                        prefix = getattr(label, 'prefix', '')
                        action = getattr(label, 'action', label.text())
                        
                        # Draw the text - simplified for export
                        if hasattr(label, 'paintEvent'):
                            # Force the label to paint itself to an image
                            label_image = QPixmap(label.size())
                            label_image.fill(Qt.transparent)
                            label_painter = QPainter(label_image)
                            label.render(label_painter)
                            label_painter.end()
                            
                            # Draw the label image to our canvas
                            painter.drawPixmap(pos, label_image)
                        else:
                            # Fallback - just draw the text
                            painter.setPen(QColor(settings.get("action_color", "#FFFFFF")))
                            painter.setFont(label.font())
                            painter.drawText(pos.x(), pos.y() + label.height()//2, label.text())
                
                # End painting
                painter.end()
                
                # Save the image
                result = image.save(output_path, format.upper())
                
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
    
    def preview_export_image(self, rom_name, game_data, output_dir, format="png"):
        """Export a preview image for a ROM with proper handling of bezel and text layering"""
        try:
            print(f"Exporting {rom_name} to {output_dir}")
            
            # Make sure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{rom_name}.{format}")
            
            # IMPORTANT: Add this section to apply custom mappings from ROM CFG
            # Check if ROM has a custom CFG file and apply those mappings
            cfg_controls = {}
            if rom_name in self.custom_configs:
                # Parse the custom config
                cfg_controls = parse_cfg_controls(self.custom_configs[rom_name], self.input_mode)
                
                # Convert if XInput is enabled
                if self.use_xinput:
                    cfg_controls = {
                        control: convert_mapping(mapping, 'xinput')
                        for control, mapping in cfg_controls.items()
                    }
                
                # Update game_data with custom mappings
                game_data = update_game_data_with_custom_mappings(
                    game_data, cfg_controls, 
                    getattr(self, 'default_controls', {}),
                    getattr(self, 'original_default_controls', {}),
                    self.input_mode
                )
                print(f"Applied custom mapping from ROM CFG for {rom_name}")
            
            # NEW CODE: Filter out non-XInput controls if in XInput Only mode
            if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
                game_data = filter_xinput_controls(game_data)
                print(f"Applied XInput filter for preview")
            
            # Create PreviewWindow directly
            from PyQt5.QtWidgets import QApplication, QMessageBox
            from PyQt5.QtCore import Qt
            import sys
            
            # Initialize PyQt app if needed
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            
            # Import the preview module
            from mame_controls_preview import PreviewWindow
            
            # Create dummy messagebox class to suppress all popups
            class DummyMessageBox:
                @staticmethod
                def information(*args, **kwargs): return QMessageBox.Ok
                @staticmethod
                def showinfo(*args, **kwargs): return
                @staticmethod
                def warning(*args, **kwargs): return QMessageBox.Ok
                @staticmethod
                def error(*args, **kwargs): return QMessageBox.Ok
                @staticmethod
                def critical(*args, **kwargs): return QMessageBox.Ok
                @staticmethod
                def question(*args, **kwargs): return QMessageBox.Yes
            
            # Create preview window but NEVER make it visible
            preview = PreviewWindow(
                rom_name,
                game_data,
                self.mame_dir,
                hide_buttons=True,
                clean_mode=True
            )
            
            # IMPORTANT: Set window to never be visible
            preview.setAttribute(Qt.WA_ShowWithoutActivating, True)
            preview.setAttribute(Qt.WA_DontShowOnScreen, True)
            preview.show()  # Must still call show() for proper rendering
            
            # Block all window activation and focus events
            preview.setAttribute(Qt.WA_ShowWithoutActivating, True)
            preview.setAttribute(Qt.WA_DontShowOnScreen, True)
            
            # Patch messagebox functions
            preview.messagebox = DummyMessageBox
            original_qmessagebox = QMessageBox.information
            QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
            
            # Process events to ensure UI is initialized
            app.processEvents()
            
            # Load bezel settings from file
            try:
                # Get bezel settings path
                settings_dir = os.path.join(self.preview_dir, "settings")
                bezel_settings_path = os.path.join(settings_dir, "bezel_settings.json")
                
                # First check if we have ROM-specific settings
                rom_bezel_settings_path = os.path.join(settings_dir, f"{rom_name}_bezel_settings.json")
                
                # Choose which settings file to use
                settings_path = rom_bezel_settings_path if os.path.exists(rom_bezel_settings_path) else bezel_settings_path
                
                if os.path.exists(settings_path):
                    with open(settings_path, 'r') as f:
                        bezel_settings = json.load(f)
                        
                    # Explicitly set settings values
                    preview.bezel_visible = bezel_settings.get("bezel_visible", True)
                    preview.logo_visible = bezel_settings.get("logo_visible", True)
                    
                    # Update UI based on settings
                    # Force bezel visibility based on settings
                    if preview.bezel_visible and hasattr(preview, 'has_bezel') and preview.has_bezel:
                        # First show the bezel
                        if hasattr(preview, 'show_bezel_with_background'):
                            preview.show_bezel_with_background()
                            
                        # Force bezel to top of z-order
                        if hasattr(preview, 'bezel_label') and preview.bezel_label:
                            preview.bezel_label.raise_()
                    else:
                        # Explicitly hide bezel
                        if hasattr(preview, 'hide_bezel'):
                            preview.hide_bezel()
                        elif hasattr(preview, 'bezel_label') and preview.bezel_label:
                            preview.bezel_label.setVisible(False)
                    
                    # Handle logo visibility
                    if hasattr(preview, 'logo_label') and preview.logo_label:
                        preview.logo_label.setVisible(preview.logo_visible)
                else:
                    print(f"No bezel settings found, using defaults")
            except Exception as e:
                print(f"Error loading bezel settings: {e}")
            
            # CRITICAL: Ensure controls are above bezel
            if hasattr(preview, 'raise_controls_above_bezel'):
                preview.raise_controls_above_bezel()
            else:
                # Manual raising of controls if method doesn't exist
                if hasattr(preview, 'control_labels'):
                    for control_name, control_data in preview.control_labels.items():
                        if 'label' in control_data and control_data['label']:
                            control_data['label'].raise_()
            
            # Process events to ensure UI updates
            app.processEvents()
            
            # Use direct image generation instead of showing window first
            success = False
            try:
                # Create a direct rendering of the canvas to an image
                from PyQt5.QtGui import QImage, QPainter, QPixmap, QColor
                
                # Process pending events to ensure components are ready
                app.processEvents()
                
                if hasattr(preview, 'export_image_headless'):
                    result = preview.export_image_headless(output_path, format)
                    success = result and os.path.exists(output_path)
                else:
                    # Fallback to standard rendering method
                    # Create the image
                    image = QImage(
                        preview.canvas.width(),
                        preview.canvas.height(),
                        QImage.Format_ARGB32
                    )
                    image.fill(Qt.transparent)
                    
                    # Create painter for the image
                    painter = QPainter(image)
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.setRenderHint(QPainter.TextAntialiasing)
                    painter.setRenderHint(QPainter.SmoothPixmapTransform)
                    
                    # Render the canvas and all its children directly to the image
                    preview.canvas.render(painter)
                    
                    # End painting
                    painter.end()
                    
                    # Save the image
                    success = image.save(output_path, format.upper())
                    
                print(f"Exported {rom_name} with result: {success}")
            finally:
                # Restore QMessageBox
                QMessageBox.information = original_qmessagebox
                
                # Close and destroy the window immediately
                preview.close()
                preview.deleteLater()
                
            return success
        except Exception as e:
            print(f"Error during export of {rom_name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def batch_export_images(self):
        """Enhanced batch export dialog for ROM preview images with fixed directory selection"""
        # Create dialog with improved styling 
        dialog = ctk.CTkToplevel(self)
        dialog.title("Batch Export Preview Images")

        # Get screen dimensions
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()

        # Set dialog size as percentage of screen (70% width, 80% height)
        dialog_width = int(screen_width * 0.7)
        dialog_height = int(screen_height * 0.8)

        # Position dialog in center of screen
        x_position = (screen_width - dialog_width) // 2
        y_position = (screen_height - dialog_height) // 2

        # Set geometry with calculated dimensions and position
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x_position}+{y_position}")

        dialog.configure(fg_color=self.theme_colors["background"])
        dialog.transient(self)
        dialog.grab_set()
        
        # Create header
        header_frame = ctk.CTkFrame(
            dialog, 
            fg_color=self.theme_colors["primary"], 
            corner_radius=0, 
            height=60
        )
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)  # Maintain fixed height
        
        ctk.CTkLabel(
            header_frame,
            text="Batch Export Preview Images",
            font=("Arial", 18, "bold"),
            text_color="#ffffff"
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Main content with scrolling
        content_frame = ctk.CTkScrollableFrame(
            dialog, 
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        content_frame.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        
        # Description card
        desc_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        desc_card.pack(fill="x", padx=0, pady=(0, 15))
        
        # Description text
        description = (
            "This tool will generate preview images for multiple ROMs using current global settings "
            "(or ROM-specific settings where available).\n\n"
            "Choose which ROMs to process and export settings below."
        )
        
        ctk.CTkLabel(
            desc_card,
            text=description,
            font=("Arial", 13),
            justify="left",
            wraplength=800
        ).pack(padx=15, pady=15, anchor="w")
        
        # Output settings card
        settings_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        settings_card.pack(fill="x", padx=0, pady=(0, 15))
        
        # Card title
        ctk.CTkLabel(
            settings_card,
            text="Output Settings",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Settings container
        settings_container = ctk.CTkFrame(settings_card, fg_color="transparent")
        settings_container.pack(fill="x", padx=15, pady=(0, 15))
        
        # Format selection
        format_frame = ctk.CTkFrame(settings_container, fg_color="transparent")
        format_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            format_frame,
            text="Image Format:",
            font=("Arial", 13),
            width=120,
            anchor="w"
        ).pack(side="left", padx=(0, 10))
        
        format_var = ctk.StringVar(value="PNG")
        format_combo = ctk.CTkComboBox(
            format_frame,
            values=["PNG"],  # Only PNG option
            variable=format_var,
            width=120,
            fg_color=self.theme_colors["background"],
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"],
            dropdown_fg_color=self.theme_colors["card_bg"]
        )
        format_combo.pack(side="left", padx=0)
        
        # Output directory
        output_frame = ctk.CTkFrame(settings_container, fg_color="transparent")
        output_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            output_frame,
            text="Output Directory:",
            font=("Arial", 13),
            width=120,
            anchor="w"
        ).pack(side="left", padx=(0, 10))
        
        # Default to preview/screenshots directory
        images_dir = os.path.join(self.preview_dir, "screenshots")
        if not os.path.exists(images_dir):
            os.makedirs(images_dir, exist_ok=True)
        
        # Display the fixed output directory
        output_dir_var = ctk.StringVar(value=images_dir)
        dir_entry = ctk.CTkEntry(
            output_frame,
            textvariable=output_dir_var,
            width=400,
            fg_color=self.theme_colors["background"],
            state="readonly"  # Make it read-only
        )
        dir_entry.pack(side="left", padx=0, fill="x", expand=True)
        
        # Add a label to inform about the fixed directory
        dir_info_label = ctk.CTkLabel(
            output_frame,
            text="Images will be saved to screenshots folder",
            font=("Arial", 11),
            text_color=self.theme_colors["text_dimmed"]
        )
        dir_info_label.pack(side="right", padx=(10, 0))
        
        # ROM selection card
        selection_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        selection_card.pack(fill="x", padx=0, pady=(0, 15))
        
        # Card title
        ctk.CTkLabel(
            selection_card,
            text="ROM Selection",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Selection options container
        selection_container = ctk.CTkFrame(selection_card, fg_color="transparent")
        selection_container.pack(fill="x", padx=15, pady=(0, 15))
        
        # ROM selection mode
        mode_frame = ctk.CTkFrame(selection_container, fg_color="transparent")
        mode_frame.pack(fill="x", pady=5)
        
        # CHANGED: Default selection is now "current" instead of "all_with_controls"
        selection_mode_var = ctk.StringVar(value="current")
        
        # Changed order to put Current ROM first
        mode_current = ctk.CTkRadioButton(
            mode_frame,
            text="Current ROM Only",
            variable=selection_mode_var,
            value="current",
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        mode_current.pack(side="left", padx=(0, 20))
        
        mode_custom = ctk.CTkRadioButton(
            mode_frame,
            text="Custom Selection",
            variable=selection_mode_var,
            value="custom",
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        mode_custom.pack(side="left", padx=(0, 20))
        
        mode_all = ctk.CTkRadioButton(
            mode_frame,
            text="All ROMs with Controls",
            variable=selection_mode_var,
            value="all_with_controls",
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        mode_all.pack(side="left")
        
        # Custom selection list frame
        list_frame = ctk.CTkFrame(selection_container, fg_color=self.theme_colors["background"], corner_radius=6)
        list_frame.pack(fill="x", pady=10)
        
        # Button frame for Select All/Deselect All
        list_button_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        list_button_frame.pack(fill="x", padx=10, pady=10)
        
        def select_all_roms():
            for item in rom_tree.get_children():
                rom_tree.selection_add(item)
        
        def deselect_all_roms():
            rom_tree.selection_remove(rom_tree.get_children())
        
        select_all_button = ctk.CTkButton(
            list_button_frame,
            text="Select All",
            command=select_all_roms,
            width=120,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        )
        select_all_button.pack(side="left", padx=5)

        deselect_all_button = ctk.CTkButton(
            list_button_frame,
            text="Deselect All",
            command=deselect_all_roms,
            width=120,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        )
        deselect_all_button.pack(side="left", padx=5)
        
        # Tree frame for ROM selection
        tree_frame = tk.Frame(list_frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Create treeview with modern styling using ttk
        style = ttk.Style()
        style.configure(
            "Treeview", 
            background=self.theme_colors["background"],
            foreground=self.theme_colors["text"],
            fieldbackground=self.theme_colors["background"],
            borderwidth=0
        )
        style.configure(
            "Treeview.Heading", 
            background=self.theme_colors["primary"],
            foreground="white",
            relief="flat"
        )
        style.map(
            "Treeview",
            background=[("selected", self.theme_colors["primary"])],
            foreground=[("selected", "white")]
        )
        
        # Create Treeview with columns for ROM name and game name
        rom_tree = ttk.Treeview(
            tree_frame,
            columns=("rom_name", "game_name"),
            show="headings",
            selectmode="extended",
            height=15
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
            game_data = get_game_data(rom, self.gamedata_json, self.parent_lookup, 
                                    self.db_path, getattr(self, 'rom_data_cache', {}))
            if game_data:
                roms_with_data.append((rom, game_data.get('gamename', rom)))
        
        # Insert ROM data into the tree
        for rom, game_name in roms_with_data:
            rom_tree.insert("", "end", values=(rom, game_name))
        
        # Status frame at the bottom (fixed)
        status_frame = ctk.CTkFrame(dialog, height=100, fg_color=self.theme_colors["card_bg"], corner_radius=0)
        status_frame.pack(fill="x", side="bottom", padx=0, pady=0)
        status_frame.pack_propagate(False)  # Keep fixed height
        
        # Progress section
        progress_container = ctk.CTkFrame(status_frame, fg_color="transparent")
        progress_container.pack(fill="x", padx=20, pady=(15, 5))
        
        # Progress bar
        progress_var = tk.DoubleVar(value=0.0)
        progress_bar = ctk.CTkProgressBar(
            progress_container,
            fg_color=self.theme_colors["background"],
            progress_color=self.theme_colors["primary"],
            height=15,
            corner_radius=2
        )
        progress_bar.pack(fill="x", padx=0, pady=(0, 5))
        progress_bar.set(0)
        
        # Status label
        status_var = tk.StringVar(value="Ready")
        status_label = ctk.CTkLabel(
            progress_container,
            textvariable=status_var,
            font=("Arial", 13)
        )
        status_label.pack(pady=0)
        
        # Button container
        button_container = ctk.CTkFrame(status_frame, fg_color="transparent")
        button_container.pack(fill="x", padx=20, pady=5)
        
        # Add flag to track cancellation
        cancel_processing = [False]
        
        # IMPORTANT: Main export function 
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
                        f"This operation can be canceled using the Cancel Export button.\n\n"
                        f"Do you want to continue?",
                        icon="warning",
                        parent=dialog
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
                        icon="warning",
                        parent=dialog
                    ):
                        return
                    
            elif mode == "current" and self.current_game:
                roms_to_process.append(self.current_game)
            
            if not roms_to_process:
                messagebox.showinfo(
                    "No ROMs Selected", 
                    "Please select at least one ROM to process",
                    parent=dialog
                )
                return
            
            # Get settings
            settings = {
                "format": format_var.get().lower(),
                "output_dir": output_dir_var.get()
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
            cancel_button.configure(
                text="Cancel Export", 
                fg_color=self.theme_colors["danger"], 
                hover_color="#c82333"
            )
            
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
                    icon="question",
                    parent=dialog
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
                        
                        # IMPORTANT: Add the custom mapping code that was missing
                        # Check if ROM has a custom CFG file and apply those mappings
                        cfg_controls = {}
                        if rom_name in self.custom_configs:
                            # Parse the custom config
                            cfg_controls = parse_cfg_controls(self.custom_configs[rom_name], self.input_mode)
                            
                            # Convert if XInput is enabled
                            if self.use_xinput:
                                cfg_controls = {
                                    control: convert_mapping(mapping, True)
                                    for control, mapping in cfg_controls.items()
                                }
                            
                            # Update game_data with custom mappings
                            game_data = update_game_data_with_custom_mappings(
                                game_data, 
                                cfg_controls, 
                                getattr(self, 'default_controls', {}),
                                getattr(self, 'original_default_controls', {}),
                                self.input_mode
                            )
                            print(f"Applied custom mapping from ROM CFG for {rom_name}")
                        
                        # Export the image using preview_export_image which respects settings
                        file_format = settings["format"].lower()
                        
                        # Set output path
                        output_path = os.path.join(settings["output_dir"], f"{rom_name}.{file_format}")
                        
                        # Use preview_export_image which will use existing settings
                        success = self.preview_export_image(
                            rom_name, 
                            game_data,
                            settings["output_dir"],
                            file_format
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
                    fg_color=self.theme_colors["card_bg"],
                    hover_color=self.theme_colors["background"],
                    border_width=1,
                    border_color=self.theme_colors["text_dimmed"],
                    text_color=self.theme_colors["text"],
                    command=dialog.destroy
                ))
                
                # Show completion message on the main thread
                if not cancel_processing[0]:
                    dialog.after(0, lambda p=processed, f=failed, d=settings["output_dir"]: 
                                messagebox.showinfo(
                                    "Export Complete", 
                                    f"Exported {p} ROM preview images to {d}\n" +
                                    (f"Failed: {f}" if f > 0 else ""),
                                    parent=dialog
                                ))
            
            # Start processing in a separate thread
            import threading
            import time
            
            # Create the thread with a name for better identification
            process_thread = threading.Thread(
                target=process_roms,
                name="BatchExportThread",
                daemon=True  # Make thread a daemon so it won't prevent application exit
            )
            process_thread.start()
            
            # Add cleanup for when dialog is closed
            def on_dialog_close():
                # Signal thread to stop if it's still running
                cancel_processing[0] = True
                # Wait briefly for thread to respond to cancel
                dialog.after(100, dialog.destroy)
            
            # Use this instead of direct destroy
            cancel_button.configure(command=on_dialog_close)
            
            # Proper protocol handler for dialog close
            dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)
        
        # IMPROVED: Better styled buttons - Start Export button
        start_button = ctk.CTkButton(
            button_container,
            text="Start Export",
            command=start_export,
            width=150,
            height=40,
            corner_radius=6,  # Rounded corners
            font=("Arial", 14, "bold"),
            fg_color=self.theme_colors["success"],  # Green color
            hover_color="#218838"  # Darker green on hover
        )
        start_button.pack(side="left", padx=5)
        
        # IMPROVED: Better styled cancel button - Red theme
        cancel_button = ctk.CTkButton(
            button_container,
            text="Cancel",
            command=dialog.destroy,
            width=120,
            height=40,
            corner_radius=6,  # Rounded corners
            font=("Arial", 14),
            fg_color=self.theme_colors["danger"],  # Red color
            hover_color="#c82333",  # Darker red on hover
            text_color="white"  # White text
        )
        cancel_button.pack(side="right", padx=5)
        
        # Center the dialog on the screen
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')

    def create_status_bar(self):
        """Create a status bar at the bottom of the main window"""
        try:
            # Status bar container
            self.status_bar = ctk.CTkFrame(self, height=25, fg_color=self.theme_colors["card_bg"], corner_radius=0)
            self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
            self.status_bar.pack_propagate(False)  # Keep fixed height
            
            # Status message
            self.status_message = ctk.CTkLabel(
                self.status_bar,
                text="Ready",
                font=("Arial", 11),
                text_color=self.theme_colors["text_dimmed"],
                anchor="w"
            )
            self.status_message.pack(side="left", padx=10, fill="y")
            
            # Version info
            self.version_label = ctk.CTkLabel(
                self.status_bar,
                text="MAME Controls Config v2.0",
                font=("Arial", 11),
                text_color=self.theme_colors["text_dimmed"]
            )
            self.version_label.pack(side="right", padx=10, fill="y")
            
            # Update grid configuration to accommodate status bar
            self.grid_rowconfigure(2, weight=0)  # Status bar (fixed height)
            
            return True
        except Exception as e:
            print(f"Error creating status bar: {e}")
            return False
    
    def update_status_message(self, message, timeout=5000):
        """Update the status bar message with optional timeout - FIXED"""
        try:
            # Check if status_message widget exists
            if not hasattr(self, 'status_message'):
                print(f"Status message widget not found, message was: {message}")
                return False
                
            # Check if the widget still exists (not destroyed)
            if not hasattr(self.status_message, 'configure'):
                print(f"Status message widget destroyed, message was: {message}")
                return False
            
            # Update message text
            self.status_message.configure(text=message)
            
            # Clear after timeout (if specified)
            if timeout > 0:
                self.after(timeout, lambda: self._clear_status_message_safe())
            
            return True
        except Exception as e:
            print(f"Error updating status message: {e}")
            print(f"Message was: {message}")
            return False
    
    def _clear_status_message_safe(self):
        """Safely clear status message"""
        try:
            if hasattr(self, 'status_message') and hasattr(self.status_message, 'configure'):
                self.status_message.configure(text="Ready")
        except:
            pass  # Ignore errors when clearing

if __name__ == "__main__":
    try:
        app = MAMEControlConfig()
        app.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
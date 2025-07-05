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
        self.custom_layouts = {}  # Will be loaded when fightstick tool is opened
        self.ALLOW_CUSTOM_CONTROLS = True  # Set to True to enable custom controls dropdown
        self.ALLOW_ADD_NEW_GAME = True     # Set to True to enable "Add New Game" tab
        self.ALLOW_REMOVE_GAME = False     # Set to True to enable "Remove Game" button
        self.SHOW_HIDE_BUTTONS_TOGGLE = False  # NEW: Set to False to hide the toggle
        self.CONTROLS_ONLY_EDIT = True     # NEW: Set to True to disable game property editing
        self.show_friendly_names = True  # Default to friendly names
        # Add ROM source mode tracking
        self.rom_source_mode = "physical"  # ALWAYS DEFAULT TO PHYSICAL
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

    def load_gamedata_json(self):
        """Load gamedata.json using the utility function"""
        try:
            from mame_data_utils import load_gamedata_json  # Add this import
            self.gamedata_json, self.parent_lookup, self.clone_parents = load_gamedata_json(self.gamedata_path)
            return self.gamedata_json
        except Exception as e:
            # Handle GUI-specific error display
            if hasattr(self, 'splash_window') and self.splash_window:
                self.splash_window.destroy()
            messagebox.showerror("Error Loading gamedata.json", str(e))
            self.after(1, self.force_close_with_json_error)
            return {}
    
    def _start_loading_process(self):
        """Begin the sequential loading process - FIXED with proper game selection"""
        
        # Update splash message
        self.update_splash_message("Loading settings...")
        
        # Load settings first (synchronous)
        self.load_settings()
        
        # Schedule the next step
        self.after(100, self._load_essential_data)

    def _load_essential_data(self):
        """Load essential data synchronously - FIXED to NOT auto-select"""
        try:
            # Update message
            self.update_splash_message("Scanning ROMs directory...")
            
            # Scan ROMs directory
            self.available_roms = scan_roms_directory(self.mame_dir)
            
            # Update message
            self.update_splash_message("Updating game list...")
            
            # Update the game list WITHOUT auto-selecting
            if hasattr(self, 'game_listbox'):
                self.update_game_list_by_category(auto_select_first=False)  # CRITICAL: False here
            
            # Update stats
            self.update_stats_label()
            
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
        """Finish loading and show the main application - SIMPLIFIED"""
        
        # Update message for the final step
        self.update_splash_message("Starting application...")
        
        # Apply any final configurations
        self._apply_initial_panel_sizes()
        if hasattr(self, 'after_init_setup'):
            self.after_init_setup()
        
        # REMOVED: self.debug_rom_source_state()
        
        # Schedule showing the main window FIRST
        self.after(500, self.show_application)
        
        # THEN schedule first game selection AFTER window is shown and stable
        self.after(1500, self._safe_first_game_selection)

    def _safe_first_game_selection(self):
        """Safely select first game with splash updates"""
        try:
            print("=== SAFE FIRST GAME SELECTION START ===")
            
            # Update splash to show we're loading the first ROM
            self.update_splash_message("Loading first ROM...")
            
            # Multiple safety checks
            if not hasattr(self, 'available_roms') or not self.available_roms:
                print("ERROR: No available ROMs")
                self._close_splash_safely()
                return
                
            if not hasattr(self, 'game_listbox') or not self.game_listbox.winfo_exists():
                print("ERROR: Game listbox doesn't exist")
                self._close_splash_safely()
                return
                
            if self.game_listbox.size() == 0:
                print("ERROR: Game listbox is empty")
                self._close_splash_safely()
                return
                
            if not hasattr(self, 'game_list_data') or not self.game_list_data:
                print("ERROR: Game list data is empty")
                self._close_splash_safely()
                return
            
            # Check if already selected
            if hasattr(self, 'current_game') and self.current_game:
                print(f"Game already selected: {self.current_game}")
                self._close_splash_safely()
                return
            
            # Get first ROM
            first_rom, _ = self.game_list_data[0]
            print(f"Selecting first ROM: {first_rom}")
            
            # Update splash with specific ROM name
            self.update_splash_message(f"Loading {first_rom}...")
            
            # Set current game FIRST
            self.current_game = first_rom
            self.selected_line = 1
            
            # Update listbox selection
            self.game_listbox.selection_clear(0, tk.END)
            self.game_listbox.selection_set(0)
            self.game_listbox.activate(0)
            self.game_listbox.see(0)
            
            # Update toolbar if available
            if hasattr(self, 'update_toolbar_status'):
                self.update_toolbar_status()
            
            # Display the game info - THIS is what takes time
            # We'll close splash after this completes
            self.display_game_info_with_splash_close(first_rom)
            
            print(f"=== INITIATED LOADING OF: {first_rom} ===")
            
        except Exception as e:
            print(f"ERROR in safe first game selection: {e}")
            import traceback
            traceback.print_exc()
            # Close splash on error
            self._close_splash_safely()
    
    def _close_splash_safely(self):
        """Safely close the splash window"""
        try:
            if hasattr(self, 'splash_window') and self.splash_window:
                print("=== CLOSING SPLASH WINDOW ===")
                self.splash_window.destroy()
                self.splash_window = None
                
                # Bring main window to front
                self.lift()
                self.focus_force()
                
        except Exception as e:
            print(f"Error closing splash: {e}")

    def display_game_info_with_splash_close(self, rom_name):
        """Display game info and close splash when done"""
        try:
            print(f"=== LOADING GAME INFO FOR: {rom_name} ===")
            
            # Update splash one more time
            self.update_splash_message(f"Processing {rom_name} controls...")
            
            # Call the regular display_game_info method
            self.display_game_info(rom_name)
            
            # Close splash after a short delay to ensure display is complete
            self.after(500, self._close_splash_with_completion_message)
            
        except Exception as e:
            print(f"Error in display_game_info_with_splash_close: {e}")
            # Close splash even on error
            self._close_splash_safely()

    def _close_splash_with_completion_message(self):
        """Close splash with a completion message"""
        try:
            # Show completion message briefly
            self.update_splash_message("Ready!")
            
            # Close splash after showing ready message
            self.after(300, self._close_splash_safely)
            
        except Exception as e:
            print(f"Error in completion message: {e}")
            self._close_splash_safely()
    
    def _delayed_first_game_selection(self):
        """Select first game after UI is fully loaded - FIXED"""
        try:
            print("DEBUG: Starting delayed first game selection")
            
            # Ensure we have available ROMs
            if not hasattr(self, 'available_roms') or not self.available_roms:
                print("DEBUG: No available ROMs found")
                return
                
            # Ensure game list is populated
            if not hasattr(self, 'game_list_data') or not self.game_list_data:
                print("DEBUG: Game list not populated, updating...")
                self.update_game_list_by_category(auto_select_first=False)
                
            # Wait a bit more for the update to complete
            self.after(200, self._actually_select_first_game)
            
        except Exception as e:
            print(f"DEBUG: Error in delayed first game selection: {e}")
            import traceback
            traceback.print_exc()

    def _actually_select_first_game(self):
        """Actually select the first game - FIXED"""
        try:
            print("DEBUG: Actually selecting first game")
            
            # Check if we have data
            if not hasattr(self, 'game_list_data') or not self.game_list_data:
                print("DEBUG: Still no game list data")
                return
                
            # Check if listbox exists and has items
            if not hasattr(self, 'game_listbox') or self.game_listbox.size() == 0:
                print("DEBUG: Listbox not ready")
                return
                
            # Get first ROM
            first_rom, _ = self.game_list_data[0]
            print(f"DEBUG: Selecting first ROM: {first_rom}")
            
            # Clear any existing selection
            self.game_listbox.selection_clear(0, tk.END)
            
            # Select first item
            self.game_listbox.selection_set(0)
            self.game_listbox.activate(0)
            self.game_listbox.see(0)
            
            # Set current game
            self.current_game = first_rom
            self.selected_line = 1
            
            # Mark as selected to prevent future auto-selection
            self._first_rom_selected = True
            
            # Update toolbar
            if hasattr(self, 'update_toolbar_status'):
                self.update_toolbar_status()
            
            # Display the game info
            self.display_game_info(first_rom)
            
            print(f"DEBUG: Successfully selected first ROM: {first_rom}")
            
        except Exception as e:
            print(f"DEBUG: Error in actually selecting first game: {e}")
            import traceback
            traceback.print_exc()
    
    def show_application(self):
        """Show the application window - KEEP SPLASH until first ROM loads"""
        try:
            print("=== SHOWING APPLICATION WINDOW (keeping splash) ===")
            
            # DON'T close splash window yet! Keep it visible during first ROM loading
            # We'll close it in _safe_first_game_selection after ROM loads
            
            # Force full UI update
            self.update_idletasks()
            
            # Get the monitor to use
            if hasattr(self, 'launch_monitor'):
                monitor = self.launch_monitor
            else:
                monitors = get_monitors()
                monitor = monitors[0]
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
            
            # Show the main window (but splash stays on top)
            self.deiconify()
            
            # Auto maximize after showing
            self.state('zoomed')
            
            # Force another update to ensure complete rendering
            self.update_idletasks()
            
            print("=== APPLICATION WINDOW SHOWN (splash still visible) ===")
                    
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
            
            # Show the splash window
            splash.deiconify()
            
            # ENHANCED: Ensure it stays on top even after main window shows
            splash.attributes('-topmost', True)
            splash.focus_force()
            
            # ENHANCED: Keep it on top during the entire loading process
            def keep_splash_on_top():
                try:
                    if splash.winfo_exists():
                        splash.attributes('-topmost', True)  
                        splash.lift()
                        # Schedule next check
                        splash.after(500, keep_splash_on_top)
                except:
                    pass  # Window was destroyed
            
            # Start the keep-on-top loop
            splash.after(500, keep_splash_on_top)
            
            # Disable closing with X button
            splash.protocol("WM_DELETE_WINDOW", lambda: None)
            
            # Update to ensure it's rendered
            splash.update()
            
            return splash
                    
        except Exception as e:
            return None
    
    def update_splash_message(self, message):
        """Update the splash window message - FIXED to handle destroyed window"""
        try:
            if hasattr(self, 'splash_window') and self.splash_window:
                # Check if the window still exists
                if self.splash_window.winfo_exists():
                    if hasattr(self, 'splash_message'):
                        self.splash_message.set(message)
                        self.splash_window.update_idletasks()
                        print(f"SPLASH: {message}")
                else:
                    print(f"Splash window destroyed, message was: {message}")
            else:
                print(f"No splash window, message was: {message}")
        except Exception as e:
            print(f"Error updating splash message: {e}")
    
    def check_and_build_db_if_needed(self):
        """Check and build the database only if needed"""
        if check_db_update_needed(self.gamedata_path, self.db_path):
            print("Database needs updating, rebuilding...")
            from mame_data_utils import build_gamedata_db
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
        
        # Set up directory structure
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        self.settings_dir = os.path.join(self.preview_dir, "settings")
        self.info_dir = os.path.join(self.preview_dir, "info")  # FIXED: Direct in preview folder
        self.cache_dir = os.path.join(self.preview_dir, "cache")

        # Create directories if they don't exist
        os.makedirs(self.preview_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        os.makedirs(self.info_dir, exist_ok=True)  # FIXED: Create info dir in preview
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
            from mame_data_utils import load_gamedata_json
            self.gamedata_json, self.parent_lookup, self.clone_parents = load_gamedata_json(self.gamedata_path)
            
            # Update splash message
            self.update_splash_message("Rebuilding database...")
            
            # Check if database needs rebuilding
            if check_db_update_needed(self.gamedata_path, self.db_path):
                print("Rebuilding database...")
                from mame_data_utils import build_gamedata_db
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
        
        # Add "Mixed Controls" tab (add this after the "analog" tab)
        self.sidebar_tabs["mixed_controls"] = CustomSidebarTab(
            tabs_frame, 
            text="Mixed Controls",
            command=lambda: set_tab_active("mixed_controls")
        )
        self.sidebar_tabs["mixed_controls"].pack(fill="x", padx=5, pady=2)
        
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
            {"text": "Fightstick Mapper", "command": self.create_fightstick_mapping_tool},  # NEW
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

    def toggle_friendly_names(self):
        """Toggle between friendly names and raw mapping display - ENHANCED CACHE CLEARING"""
        # Get the toggle state directly instead of inverting it
        self.show_friendly_names = self.friendly_names_toggle.get()
        
        print(f"DEBUG: Toggled friendly names to: {self.show_friendly_names}")
        
        # CRITICAL: Clear processed cache to force reprocessing with new setting
        if hasattr(self, 'processed_cache'):
            cleared_count = len(self.processed_cache)
            self.processed_cache.clear()
            print(f"DEBUG: Cleared processed cache ({cleared_count} entries) for friendly names toggle")
        
        # CRITICAL: Also clear ROM data cache to force fresh processing
        if hasattr(self, 'rom_data_cache'):
            cleared_count = len(self.rom_data_cache)
            self.rom_data_cache.clear()
            print(f"DEBUG: Cleared rom_data_cache ({cleared_count} entries) for friendly names toggle")
        
        # Clear LRU cache if it exists
        if hasattr(self.get_game_data, 'cache_clear'):
            self.get_game_data.cache_clear()
            print("DEBUG: Cleared LRU cache for friendly names toggle")
        
        # Save the setting
        self.save_settings()
        
        # Refresh current game display if one is selected
        if self.current_game:
            print(f"DEBUG: Refreshing display for {self.current_game} with friendly_names={self.show_friendly_names}")
            # Force fresh processing by NOT passing processed_data
            self.display_game_info(self.current_game)
            
        # Update status message (with better error handling)
        mode_text = "friendly names" if self.show_friendly_names else "raw mappings"
        try:
            if hasattr(self, 'update_status_message'):
                self.update_status_message(f"Display mode changed to {mode_text}")
            else:
                print(f"Display mode changed to {mode_text}")
        except Exception as e:
            print(f"Could not update status: {e}, message was: Display mode changed to {mode_text}")
    
    def create_top_bar(self):
        """Create top bar with control buttons - INCLUDE FRIENDLY NAMES TOGGLE"""
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
        
        # NEW: Friendly names toggle
        self.friendly_names_toggle = ctk.CTkSwitch(
            toggle_frame,
            text="Friendly Names",
            command=self.toggle_friendly_names,
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"]
        )
        
        # Set initial state based on settings
        if hasattr(self, 'show_friendly_names') and self.show_friendly_names:
            self.friendly_names_toggle.select()
        else:
            self.friendly_names_toggle.deselect()
        
        self.friendly_names_toggle.pack(side="right", padx=10)
        
        # ROM Source Toggle
        self.rom_source_toggle = ctk.CTkSwitch(
            toggle_frame,
            text="Show All Games",
            command=self.toggle_rom_source,
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"]
        )
        
        # ALWAYS start with toggle OFF (physical ROMs)
        self.rom_source_toggle.deselect()
        print("Toggle set to OFF - starting with physical ROMs")
        
        self.rom_source_toggle.pack(side="right", padx=10)

        # Only show hide buttons toggle if feature is enabled
        if getattr(self, 'SHOW_HIDE_BUTTONS_TOGGLE', True):
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
    
    def _set_initial_toggle_state(self):
        """Set the initial toggle state based on loaded settings"""
        try:
            if hasattr(self, 'rom_source_mode'):
                if self.rom_source_mode == "database":
                    self.rom_source_toggle.select()
                    print("Set toggle to SELECTED (database mode)")
                else:
                    self.rom_source_toggle.deselect()
                    print("Set toggle to DESELECTED (physical mode)")
            else:
                # Default to physical mode
                self.rom_source_toggle.deselect()
                print("No rom_source_mode found, defaulting to physical mode")
        except Exception as e:
            print(f"Error setting initial toggle state: {e}")

    def toggle_rom_source(self):
        """Toggle between physical ROMs and database ROMs - DON'T SAVE STATE"""
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
            
            print(f"ROM source mode changed from {old_mode} to {self.rom_source_mode}")
            
            # Clear current selection to prevent selection events
            self.current_game = None
            
            # Temporarily disable selection events
            if hasattr(self, 'game_listbox'):
                self.game_listbox.selection_clear(0, tk.END)
                self.game_listbox.unbind("<ButtonRelease-1>")
                self.game_listbox.unbind("<Button-3>")
                self.game_listbox.unbind("<Double-Button-1>")
            
            # Load ROM set for current mode
            self.load_rom_set_for_current_mode()
            
            # Ensure we have ROMs before updating the list
            if not hasattr(self, 'available_roms') or not self.available_roms:
                print(f"ERROR: No ROMs loaded for {self.rom_source_mode} mode")
                if hasattr(self, 'game_title'):
                    self.game_title.configure(text=f"No ROMs available in {self.rom_source_mode} mode")
                if hasattr(self, 'control_frame'):
                    for widget in self.control_frame.winfo_children():
                        widget.destroy()
            else:
                print(f"Available ROMs after mode change: {len(self.available_roms)}")
                
                # Update game list WITHOUT auto-selecting first ROM
                if hasattr(self, 'game_listbox'):
                    self.update_game_list_by_category(auto_select_first=False)
            
            # Re-bind selection events
            if hasattr(self, 'game_listbox'):
                self.game_listbox.bind("<ButtonRelease-1>", self.on_rom_click_release)
                self.game_listbox.bind("<Button-3>", self.show_game_context_menu_listbox)
                self.game_listbox.bind("<Double-Button-1>", self.on_game_double_click)
            
            # Schedule single display update only if we have ROMs
            if hasattr(self, 'available_roms') and self.available_roms:
                self._display_timer = self.after(150, self._delayed_first_rom_select)
            else:
                # Clear display if no ROMs
                self.current_game = None
                if hasattr(self, 'game_title'):
                    self.game_title.configure(text="No ROMs available in this mode")
                if hasattr(self, 'control_frame'):
                    for widget in self.control_frame.winfo_children():
                        widget.destroy()
            
            # Update stats
            self.update_stats_label()
            
            # DON'T SAVE SETTINGS - this is the key change!
            # self.save_settings()  # REMOVED - don't save toggle state
            
            mode_text = "all games in database" if self.rom_source_mode == "database" else "physical ROMs"
            self.update_status_message(f"Now showing {mode_text}")
            
        except Exception as e:
            print(f"Error toggling ROM source: {e}")
            import traceback
            traceback.print_exc()

    def load_database_roms(self):
        """Load all parent ROMs from gamedata.json (exclude clones)"""
        try:
            # Ensure gamedata is loaded first
            if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
                print("Loading gamedata.json for database ROMs...")
                from mame_data_utils import load_gamedata_json
                self.gamedata_json, self.parent_lookup, self.clone_parents = load_gamedata_json(self.gamedata_path)
            
            if not self.gamedata_json:
                print("ERROR: Could not load gamedata.json")
                self.database_roms = set()
                return
            
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
            else:
                print("WARNING: No database ROMs were loaded!")
                    
        except Exception as e:
            print(f"Error loading database ROMs: {e}")
            import traceback
            traceback.print_exc()
            self.database_roms = set()
    
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
                if not hasattr(self, 'database_roms') or not self.database_roms:
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
        """Handle game selection from listbox with FIXED duplicate call prevention"""
        try:
            # Add debouncing to prevent rapid-fire calls
            current_time = time.time()
            if hasattr(self, '_last_selection_time') and (current_time - self._last_selection_time) < 0.1:
                return  # Skip if called too recently
            self._last_selection_time = current_time
            
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
                
                # Process display with slight delay to prevent rapid calls
                self.after(50, lambda: self.display_game_info(rom_name))
                
                # Explicitly maintain selection (prevents flickering)
                self.after(70, lambda idx=index: self.game_listbox.selection_set(idx))
                
                # Ensure listbox still has focus
                self.after(90, lambda: self.game_listbox.focus_set())
            
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
        """Update game list by category with FIXED first ROM selection logic"""
        
        # Store previously selected ROM if we're not auto-selecting
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
        mixed_controls_roms = []
        
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
                
                # ADD THIS NEW SECTION HERE - RIGHT AFTER THE ABOVE if/elif BLOCK:
                # Check for mixed controls (some with names, some without)
                if self.has_mixed_controls(rom):
                    mixed_controls_roms.append(rom)
                
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
        elif self.current_view == "mixed_controls":
            display_roms = mixed_controls_roms
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
        
        # Handle ROM selection - FIXED to not interfere with startup
        if auto_select_first and display_roms:
            # Check if this is during startup (no current game set yet)
            if not hasattr(self, 'current_game') or not self.current_game:
                # During startup - DON'T auto-select, let the safe selection handle it
                print("DEBUG: Skipping auto-select during startup")
                pass
            else:
                # After startup - normal category switching behavior
                first_rom, _ = self.game_list_data[0]
                self.current_game = first_rom
                self.selected_line = 1
                
                # Select in listbox
                self.game_listbox.selection_clear(0, tk.END)
                self.game_listbox.selection_set(0)
                self.game_listbox.see(0)
                
                # Display ROM info
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
            "mixed_controls": "Mixed Controls",  # NEW
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
    
    def load_processed_cache_from_disk(self, rom_name):
        """Load processed data from disk cache if it matches current settings"""
        try:
            if not hasattr(self, 'cache_dir') or not self.cache_dir:
                return None
                
            cache_filename = f"{rom_name}_cache.json"
            cache_path = os.path.join(self.cache_dir, cache_filename)
            
            if not os.path.exists(cache_path):
                return None
            
            # Load the cache file
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Validate cache matches current settings
            current_settings = {
                'input_mode': self.input_mode,
                'friendly_names': getattr(self, 'show_friendly_names', True),
                'xinput_only_mode': getattr(self, 'xinput_only_mode', True)
            }
            
            cached_settings = {
                'input_mode': cache_data.get('input_mode'),
                'friendly_names': cache_data.get('friendly_names', True),
                'xinput_only_mode': cache_data.get('xinput_only_mode', True)
            }
            
            # Check if settings match
            if cached_settings == current_settings:
                print(f"Loaded valid disk cache for {rom_name}")
                return cache_data.get('game_data')
            else:
                print(f"Disk cache for {rom_name} is outdated (settings changed)")
                # Optionally remove outdated cache
                try:
                    os.remove(cache_path)
                    print(f"Removed outdated cache file for {rom_name}")
                except:
                    pass
                return None
            
        except Exception as e:
            print(f"Error loading disk cache for {rom_name}: {e}")
            return None
    
    def save_processed_cache_to_disk(self, rom_name, game_data):
        """Save processed data to disk cache with clean ROM-based filename"""
        try:
            if not hasattr(self, 'cache_dir') or not self.cache_dir:
                return
                
            # CLEAN filename - just ROM name
            cache_filename = f"{rom_name}_cache.json"
            cache_path = os.path.join(self.cache_dir, cache_filename)
            
            # Create cache directory if needed
            os.makedirs(self.cache_dir, exist_ok=True)
            
            # ENHANCED: Store cache metadata in the JSON to track what settings were used
            cache_data = {
                'rom_name': rom_name,
                'input_mode': self.input_mode,
                'friendly_names': getattr(self, 'show_friendly_names', True),
                'xinput_only_mode': getattr(self, 'xinput_only_mode', True),
                'cached_timestamp': time.time(),
                'game_data': game_data
            }
            
            # Save to disk
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
                
            print(f"Saved processed cache for {rom_name} (mode: {self.input_mode}, friendly: {getattr(self, 'show_friendly_names', True)})")
            
        except Exception as e:
            print(f"Warning: Could not save cache for {rom_name}: {e}")
    
    def debug_cache_state(self):
        """Debug method to check current cache state"""
        print(f"\n=== CACHE DEBUG ===")
        print(f"Current input mode: {getattr(self, 'input_mode', 'not set')}")
        print(f"Current friendly_names: {getattr(self, 'show_friendly_names', 'not set')}")
        print(f"Current game: {getattr(self, 'current_game', 'not set')}")
        
        if hasattr(self, 'processed_cache'):
            print(f"Processed cache entries: {len(self.processed_cache)}")
            for key in list(self.processed_cache.keys())[:5]:  # Show first 5
                print(f"  Cache key: {key}")
        else:
            print("No processed cache")
            
        if hasattr(self, 'rom_data_cache'):
            print(f"ROM data cache entries: {len(self.rom_data_cache)}")
        else:
            print("No ROM data cache")
        print("===================\n")
    
    def display_game_info(self, rom_name, processed_data=None):
        """Display game information and controls - WITH PROPER CACHE VALIDATION"""
        try:     
            print(f"DEBUG display_game_info: Starting for {rom_name}, input_mode={self.input_mode}, friendly_names={getattr(self, 'show_friendly_names', True)}")
            
            # Update splash if it's still visible (for first ROM)
            if hasattr(self, 'splash_window') and getattr(self, 'splash_window', None):
                self.update_splash_message(f"Loading {rom_name} controls...")
            
            # Update toolbar status when a new ROM is selected
            if hasattr(self, 'update_toolbar_status'):
                self.update_toolbar_status()
            
            # Initialize processed cache if it doesn't exist
            if not hasattr(self, 'processed_cache'):
                self.processed_cache = {}
            
            # FIXED: Include input_mode AND friendly_names in cache key
            cache_key = f"{rom_name}_{self.input_mode}_{getattr(self, 'show_friendly_names', True)}"
            print(f"Using cache key: {cache_key}")
            
            # Initialize cfg_controls for all code paths
            cfg_controls = {}
            
            # Use provided processed data or get from cache or process fresh
            if processed_data:
                game_data = processed_data
                self.processed_cache[cache_key] = processed_data
            elif cache_key in self.processed_cache:
                print(f"Using in-memory cached data for {rom_name}")
                game_data = self.processed_cache[cache_key]
            else:
                # Try loading from disk cache first
                disk_cached_data = self.load_processed_cache_from_disk(rom_name)
                if disk_cached_data:
                    print(f"Using valid disk cached data for {rom_name}")
                    game_data = disk_cached_data
                    # Store in memory cache too
                    self.processed_cache[cache_key] = disk_cached_data
                else:
                    print(f"Processing fresh data for {rom_name} with mode={self.input_mode}, friendly_names={getattr(self, 'show_friendly_names', True)}")
                    
                    # Update splash during processing
                    if hasattr(self, 'splash_window') and getattr(self, 'splash_window', None):
                        self.update_splash_message(f"Processing {rom_name} data...")
                    
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

                    # Apply all processing ONCE - PASS friendly_names parameter
                    game_data = update_game_data_with_custom_mappings(
                        game_data, 
                        cfg_controls, 
                        getattr(self, 'default_controls', {}),
                        getattr(self, 'original_default_controls', {}),
                        self.input_mode,
                        getattr(self, 'show_friendly_names', True)  # CRITICAL: Pass the toggle setting
                    )

                    # Apply XInput filtering if enabled
                    if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
                        game_data = filter_xinput_controls(game_data)
                    
                    # Cache the processed result with the CORRECT cache key
                    self.processed_cache[cache_key] = game_data
                    print(f"Cached processed data with key: {cache_key}")
                    
                    # Save to disk cache asynchronously (with clean filename)
                    self.after_idle(lambda: self.save_processed_cache_to_disk(rom_name, game_data))

            # For cached data, we need to regenerate cfg_controls if it exists
            if not cfg_controls and rom_name in self.custom_configs:
                cfg_controls = parse_cfg_controls(self.custom_configs[rom_name], self.input_mode)
                cfg_controls = {
                    control: convert_mapping(mapping, self.input_mode)
                    for control, mapping in cfg_controls.items()
                }

            # Update splash before display
            if hasattr(self, 'splash_window') and getattr(self, 'splash_window', None):
                self.update_splash_message(f"Displaying {rom_name}...")

            # Now display using the processed data
            current_mode = getattr(self, 'input_mode', 'xinput' if self.use_xinput else 'joycode')
            print(f"Display game info using input mode: {current_mode}, friendly_names: {getattr(self, 'show_friendly_names', True)}")

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
            
            print(f"=== COMPLETED DISPLAY FOR: {rom_name} ===")
            
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
        skipped_roms = []  # NEW: Track which ROMs were skipped
        
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
                        skipped_roms.append(f"{rom_name} (no mappable controls)")  # NEW: Add reason
                else:
                    print(f"Skipping {rom_name}: No control data found")
                    skipped += 1
                    skipped_roms.append(f"{rom_name} (no control data)")  # NEW: Add reason
            except Exception as e:
                error_msg = f"Error with {rom_name}: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
        
        # Enhanced final report with ROM names
        report = f"Generated {count} config files in {info_dir}\n"
        
        # NEW: Include skipped ROM details
        if skipped > 0:
            report += f"\nSkipped {skipped} ROMs:\n"
            # Show up to 10 skipped ROMs, then summarize the rest
            if len(skipped_roms) <= 10:
                for rom in skipped_roms:
                    report += f"  • {rom}\n"
            else:
                # Show first 8, then summary
                for rom in skipped_roms[:8]:
                    report += f"  • {rom}\n"
                report += f"  • ... and {len(skipped_roms) - 8} more ROMs\n"
        
        # Error section (existing)
        if errors:
            report += f"\nEncountered {len(errors)} errors:\n"
            if len(errors) <= 5:
                for error in errors:
                    report += f"  • {error}\n"
            else:
                for error in errors[:3]:
                    report += f"  • {error}\n"
                report += f"  • ... and {len(errors) - 3} more errors\n"
        
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
            subdirs=[["info"], ["preview", "info"], ["settings", "info"]],  # Check preview/info first
            copy_to_settings=False
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
        # Create each line separately to avoid any indentation issues
        lines = [
            "controller D-pad = ",
            "controller D-pad t = ",
            "controller L-stick = ",
            "controller L-stick t = ",
            "controller R-stick = ",
            "controller R-stick t = ",
            "controller A = ",
            "controller A t = ",
            "controller B = ",
            "controller B t = ",
            "controller X = ",
            "controller X t = ",
            "controller Y = ",
            "controller Y t = ",
            "controller LB = ",
            "controller LB t = ",
            "controller LT = ",
            "controller LT t = ",
            "controller RB = ",
            "controller RB t = ",
            "controller RT = ",
            "controller RT t = ",
            "controller start = ",
            "controller start t = ",
            "controller select = ",
            "controller select t = ",
            "controller xbox = ",
            "controller xbox t = "
        ]
        return "\n".join(lines)

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
            # FIXED: Import and call the utility function correctly
            from mame_data_utils import identify_generic_controls, find_unmatched_roms
            
            # Get data using the utility functions with proper parameters
            generic_games, missing_games = identify_generic_controls(
                self.available_roms, 
                self.gamedata_json, 
                self.parent_lookup, 
                self.db_path, 
                getattr(self, 'rom_data_cache', {})
            )
            
            # Get matched ROMs
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
        # ROM Name field - ADD state parameter based on toggle
        rom_name_entry = ctk.CTkEntry(
            properties_grid, 
            width=300, 
            textvariable=rom_name_var,
            fg_color=self.theme_colors["background"],
            state="disabled" if (self.CONTROLS_ONLY_EDIT or not is_new_game) else "normal"  # MODIFIED
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
            fg_color=self.theme_colors["background"],
            state="disabled" if (self.CONTROLS_ONLY_EDIT and not is_new_game) else "normal"  # ADDED
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
            dropdown_fg_color=self.theme_colors["card_bg"],
            state="disabled" if (self.CONTROLS_ONLY_EDIT and not is_new_game) else "normal"  # ADDED
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
            hover_color=self.theme_colors["secondary"],
            state="disabled" if (self.CONTROLS_ONLY_EDIT and not is_new_game) else "normal"  # ADDED
        )
        alternating_check.grid(row=2, column=2, padx=5, pady=5, sticky="w")

        # Console game checkbox
        console_var = tk.BooleanVar(value=game_data.get('console', False) if not is_new_game else False)
        console_check = ctk.CTkCheckBox(
            properties_grid, 
            text="Console Game", 
            variable=console_var,
            checkbox_width=20,
            checkbox_height=20,
            corner_radius=3,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"],
            state="disabled" if (self.CONTROLS_ONLY_EDIT and not is_new_game) else "normal"
        )
        console_check.grid(row=2, column=3, padx=5, pady=5, sticky="w")
        
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
            dropdown_fg_color=self.theme_colors["card_bg"],
            state="disabled" if (self.CONTROLS_ONLY_EDIT and not is_new_game) else "normal"  # ADDED
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
            dropdown_fg_color=self.theme_colors["card_bg"],
            state="disabled" if (self.CONTROLS_ONLY_EDIT and not is_new_game) else "normal"  # ADDED
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

        # Get existing controls from game data - ONLY PLAYER 1 CONTROLS
        existing_controls = []
        existing_control_names = set()
                
        if game_data and 'players' in game_data:
            for player in game_data.get('players', []):
                # ONLY process Player 1 controls
                if player.get('number') == 1:
                    for label in player.get('labels', []):
                        # Only add P1 controls
                        if label['name'].startswith('P1_'):
                            existing_controls.append((label['name'], label['value']))
                            existing_control_names.add(label['name'])

        print(f"Found {len(existing_control_names)} P1 controls: {sorted(existing_control_names)}")

        # Initialize all control lists
        standard_controls = []
        directional_controls = []
        right_stick_controls = []
        dpad_controls = []
        system_controls = []
        specialized_controls = []

        if not is_new_game:
            # Track which controls we've already added to prevent duplicates
            added_controls = set()
            
            # 1. Add standard buttons first
            for control_name in sorted(existing_control_names):
                if control_name.startswith('P1_BUTTON'):
                    button_num = control_name.replace('P1_BUTTON', '')
                    display_name = f'P1 Button {button_num}'
                    standard_controls.append((control_name, display_name))
                    added_controls.add(control_name)
                    
            # 2. Add directional controls (handle duplicates)
            for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                # Check all possible joystick variants for this direction
                variants = [
                    f'P1_JOYSTICK_{direction}',
                    f'P1_JOYSTICKLEFT_{direction}'
                ]
                
                # Only add the first variant that exists and hasn't been added yet
                for variant in variants:
                    if variant in existing_control_names and variant not in added_controls:
                        if 'LEFT' in variant:
                            display_name = f'P1 Left Stick {direction.capitalize()}'
                        else:
                            display_name = f'P1 Joystick {direction.capitalize()}'
                        directional_controls.append((variant, display_name))
                        added_controls.add(variant)
                        break  # Only add one variant per direction
                        
            # 3. Add right stick controls if they exist
            for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                control_name = f'P1_JOYSTICKRIGHT_{direction}'
                if control_name in existing_control_names and control_name not in added_controls:
                    display_name = f'P1 Right Stick {direction.capitalize()}'
                    right_stick_controls.append((control_name, display_name))
                    added_controls.add(control_name)
                    
            # 4. Add D-pad controls if they exist
            for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                control_name = f'P1_DPAD_{direction}'
                if control_name in existing_control_names and control_name not in added_controls:
                    display_name = f'P1 D-Pad {direction.capitalize()}'
                    dpad_controls.append((control_name, display_name))
                    added_controls.add(control_name)
                    
            # 5. Add system controls
            for control_name in ['P1_START', 'P1_SELECT']:
                if control_name in existing_control_names and control_name not in added_controls:
                    if control_name == 'P1_START':
                        display_name = 'P1 Start Button'
                    else:
                        display_name = 'P1 Select/Coin Button'
                    system_controls.append((control_name, display_name))
                    added_controls.add(control_name)
                    
            # 6. Add specialized controls
            specialized_types = [
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
            
            for control_name, display_name in specialized_types:
                if control_name in existing_control_names and control_name not in added_controls:
                    specialized_controls.append((control_name, display_name))
                    added_controls.add(control_name)

        # For new games, start with empty lists
        if is_new_game:
            print("New game: not pre-generating any controls")

        # Create the final control list - P1 controls only, no duplicates
        all_controls = (standard_controls + directional_controls + 
                       right_stick_controls + dpad_controls + 
                       system_controls + specialized_controls)

        print(f"Final P1 controls to display: {len(all_controls)}")
        for control_name, display_name in all_controls:
            print(f"  {control_name}: {display_name}")

        # Verify no duplicates
        control_names_check = [c[0] for c in all_controls]
        if len(control_names_check) != len(set(control_names_check)):
            print("WARNING: Duplicate controls detected!")
            duplicates = [name for name in control_names_check if control_names_check.count(name) > 1]
            print(f"Duplicates: {duplicates}")
        else:
            print("✓ No duplicate controls found")

        # Create the final control list, merging all relevant controls
        all_controls = standard_controls + directional_controls + right_stick_controls + dpad_controls + system_controls + specialized_controls

        # Create the final control list - P1 controls only
        all_controls = (standard_controls + directional_controls + 
                       right_stick_controls + dpad_controls + 
                       system_controls + specialized_controls)

        print(f"Final P1 controls to display: {len(all_controls)}")
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
        
        # Mappings card - ADD THIS NEW SECTION
        mappings_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        mappings_card.pack(fill="x", padx=0, pady=(0, 15))

        ctk.CTkLabel(
            mappings_card,
            text="Game Mappings (Categories)",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))

        mappings_description = (
            "Mappings help categorize games for tools like the Fightstick Mapper. "
            "Common mappings include: sf, ki, mk, tekken, darkstalkers, marvel, capcom, snk, etc."
        )

        ctk.CTkLabel(
            mappings_card,
            text=mappings_description,
            font=("Arial", 12),
            text_color=self.theme_colors["text_dimmed"],
            wraplength=750
        ).pack(anchor="w", padx=15, pady=(0, 10))

        # Container for mapping entries
        mappings_container = ctk.CTkFrame(mappings_card, fg_color="transparent")
        mappings_container.pack(fill="x", padx=15, pady=(0, 15))

        # Get existing mappings
        existing_mappings = []
        if not is_new_game and rom_name in self.gamedata_json:
            existing_mappings = self.gamedata_json[rom_name].get('mappings', [])

        # Store mapping entries for saving
        mapping_entries = []

        def add_mapping_row(mapping_value=""):
            """Add a new mapping entry row"""
            row_frame = ctk.CTkFrame(
                mappings_container, 
                fg_color=self.theme_colors["background"],
                corner_radius=4
            )
            row_frame.pack(fill="x", pady=2)
            
            # Mapping value entry
            mapping_var = tk.StringVar(value=mapping_value)
            mapping_entry = ctk.CTkEntry(
                row_frame,
                width=200,
                textvariable=mapping_var,
                fg_color=self.theme_colors["card_bg"],
                placeholder_text="Enter mapping (e.g., sf, ki, mk)"
            )
            mapping_entry.pack(side="left", padx=10, pady=8)
            
            # Common mappings dropdown for quick selection
            common_mappings = [
                "sf", "ki", "mk", "tekken", "neogeo"
            ]
            
            def on_common_select(selection):
                if selection and selection != "Select common...":
                    mapping_var.set(selection)
            
            common_dropdown = ctk.CTkComboBox(
                row_frame,
                values=["Select common..."] + common_mappings,
                command=on_common_select,
                width=150,
                fg_color=self.theme_colors["card_bg"],
                button_color=self.theme_colors["primary"],
                button_hover_color=self.theme_colors["secondary"],
                dropdown_fg_color=self.theme_colors["card_bg"]
            )
            common_dropdown.pack(side="left", padx=10, pady=8)
            
            # Remove button
            def remove_row():
                row_frame.destroy()
                mapping_entries.remove(mapping_data)
            
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
            mapping_data = {
                "frame": row_frame,
                "var": mapping_var
            }
            
            mapping_entries.append(mapping_data)
            
            return mapping_data

        # Add existing mappings
        if existing_mappings:
            for mapping in existing_mappings:
                add_mapping_row(mapping)
        else:
            # Add one empty row by default
            add_mapping_row()

        # Add another mapping button
        add_mapping_button = ctk.CTkButton(
            mappings_container,
            text="+ Add Another Mapping",
            command=add_mapping_row,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"],
            height=35
        )
        add_mapping_button.pack(pady=10)

        # Predefined mapping templates
        templates_frame = ctk.CTkFrame(mappings_card, fg_color=self.theme_colors["background"], corner_radius=4)
        templates_frame.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkLabel(
            templates_frame,
            text="Quick Templates:",
            font=("Arial", 13, "bold")
        ).pack(side="left", padx=10, pady=8)

        def apply_template(template_mappings):
            """Apply a predefined template"""
            # Clear existing entries
            for mapping_data in mapping_entries[:]:
                mapping_data["frame"].destroy()
            mapping_entries.clear()
            
            # Add template mappings
            for mapping in template_mappings:
                add_mapping_row(mapping)

        # Template buttons
        templates = [
            ("Street Fighter", ["sf"]),
            ("Killer Instinct", ["ki"]),
            ("Mortal Kombat", ["mk"]),
            ("Tekken", ["tekken"]),
            ("SNK/Neo Geo", ["neogeo"])
        ]

        for template_name, template_mappings in templates:
            template_button = ctk.CTkButton(
                templates_frame,
                text=template_name,
                command=lambda t=template_mappings: apply_template(t),
                width=100,
                height=30,
                fg_color=self.theme_colors["secondary"],
                hover_color=self.theme_colors["primary"],
                font=("Arial", 11)
            )
            template_button.pack(side="left", padx=5, pady=8)
        
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
                        "controls": {},
                        "console": bool(console_var.get()),
                    }
                }
                
                # ADD THE MAPPINGS PREVIEW CODE HERE - RIGHT AFTER THE alternating LINE:
                # Add mappings to preview
                if mapping_entries:
                    preview_mappings = []
                    for mapping_data in mapping_entries:
                        mapping_value = mapping_data["var"].get().strip()
                        if mapping_value:
                            preview_mappings.append(mapping_value)
                    
                    if preview_mappings:
                        game_entry[current_rom_name]["mappings"] = preview_mappings
                
                # Add clones (this section already exists)
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
                console_var.trace_add("write", lambda *args: editor.after(500, update_preview))  # NEW LINE
        
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
        
        def save_game():
            """Save game data while preserving existing properties - FIXED VERSION FOR CLONES"""
            try:
                # Validate ROM name
                current_rom_name = rom_name_var.get().strip()
                if not current_rom_name:
                    messagebox.showerror("Error", "ROM Name is required", parent=editor)
                    return
                    
                # IMPORTANT: Track if we're editing a clone BEFORE any changes
                original_rom_being_edited = getattr(self, 'current_game', None)
                is_editing_clone = (original_rom_being_edited and 
                                hasattr(self, 'parent_lookup') and 
                                original_rom_being_edited in self.parent_lookup and
                                self.parent_lookup[original_rom_being_edited] == current_rom_name)
                
                print(f"Save operation: current_rom_name={current_rom_name}, original_rom={original_rom_being_edited}, is_editing_clone={is_editing_clone}")
                
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
                # Use this:
                from collections import OrderedDict

                if current_rom_name in gamedata:
                    game_entry = OrderedDict(gamedata[current_rom_name])
                else:
                    game_entry = OrderedDict()
                
                # Update basic properties
                game_entry["description"] = description_var.get().strip() or current_rom_name
                game_entry["playercount"] = playercount_var.get()
                game_entry["buttons"] = buttons_var.get()
                game_entry["sticks"] = sticks_var.get()
                game_entry["alternating"] = bool(alternating_var.get())
                game_entry["console"] = bool(console_var.get())
                
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
                
                # ADD THE MAPPINGS CODE HERE - RIGHT AFTER THE CLONES SECTION:
                # Handle mappings - ADD THIS SECTION IN save_game()
                new_mappings = []
                for mapping_data in mapping_entries:
                    mapping_value = mapping_data["var"].get().strip()
                    if mapping_value:
                        new_mappings.append(mapping_value)
                
                # Remove duplicates while preserving order
                seen = set()
                unique_mappings = []
                for mapping in new_mappings:
                    if mapping.lower() not in seen:
                        seen.add(mapping.lower())
                        unique_mappings.append(mapping)
                
                game_entry["mappings"] = unique_mappings
                
                # Handle controls (this is the next section that already exists)
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
                
                # Update button count if needed - FIXED VERSION
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
                    # Use the COUNT of defined buttons, not the highest number
                    actual_button_count = len(defined_buttons)
                    max_defined_button = max(defined_buttons)
                    
                    # Only suggest changes if there's a significant discrepancy
                    if actual_button_count != current_buttons:
                        # Show detailed information about the buttons
                        button_list = sorted(defined_buttons)
                        button_list_str = ", ".join([f"P1_BUTTON{b}" for b in button_list])
                        
                        if messagebox.askyesno("Update Button Count", 
                                    f"You've defined {actual_button_count} buttons: {button_list_str}\n\n"
                                    f"The game is currently set to use {current_buttons} buttons.\n\n"
                                    f"Would you like to update the button count to {actual_button_count}?", 
                                    parent=editor):
                            buttons_var.set(str(actual_button_count))
                            game_entry["buttons"] = str(actual_button_count)
                    
                    # Separately warn about gaps in button numbering if they exist
                    if len(defined_buttons) > 0:
                        min_button = min(defined_buttons)
                        max_button = max(defined_buttons)
                        expected_buttons = set(range(min_button, max_button + 1))
                        missing_buttons = expected_buttons - defined_buttons
                        
                        if missing_buttons and len(missing_buttons) > 0:
                            missing_list = sorted(missing_buttons)
                            missing_str = ", ".join([f"P1_BUTTON{b}" for b in missing_list])
                            messagebox.showwarning("Button Numbering Gap", 
                                        f"Warning: You have gaps in your button numbering.\n\n"
                                        f"Defined buttons: {button_list_str}\n"
                                        f"Missing buttons: {missing_str}\n\n"
                                        f"This is unusual but not necessarily wrong. Most games use consecutive button numbers starting from 1.",
                                        parent=editor)
                
                # Save to JSON
                gamedata[current_rom_name] = game_entry
                
                with open(gamedata_path, 'w', encoding='utf-8') as f:
                    json.dump(gamedata, f, indent=2)
                
                # Success message
                action_text = 'added to' if is_new_game else 'updated in'
                messagebox.showinfo("Success", 
                            f"Game '{current_rom_name}' {action_text} gamedata.json with {controls_added} control mappings", 
                            parent=editor)
                
                # SIMPLE FIX: Clear the LRU cache on get_game_data
                if hasattr(self.get_game_data, 'cache_clear'):
                    self.get_game_data.cache_clear()
                    print("Cleared LRU cache on get_game_data method")

                # Also clear the manual caches
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache.clear()
                    print("Cleared rom_data_cache")

                if hasattr(self, 'processed_cache'):
                    self.processed_cache.clear() 
                    print("Cleared processed_cache")

                # Refresh data using startup logic
                if hasattr(self, 'gamedata_json'):
                    del self.gamedata_json
                from mame_data_utils import load_gamedata_json
                self.gamedata_json, self.parent_lookup, self.clone_parents = load_gamedata_json(self.gamedata_path)

                # Database rebuild (same as before)
                needs_rebuild = False
                if is_editing_clone:
                    print(f"Rebuilding database because we edited parent {current_rom_name} through clone {original_rom_being_edited}")
                    needs_rebuild = True
                elif hasattr(self, 'clone_parents') and current_rom_name in self.clone_parents:
                    print(f"Rebuilding database because {current_rom_name} has clone ROMs")
                    needs_rebuild = True
                elif hasattr(self, 'db_path') and self.db_path:
                    from mame_data_utils import check_db_update_needed
                    if check_db_update_needed(self.gamedata_path, self.db_path):
                        needs_rebuild = True

                if needs_rebuild and hasattr(self, 'db_path') and self.db_path:
                    from mame_data_utils import build_gamedata_db
                    build_gamedata_db(self.gamedata_json, self.db_path)

                # Update UI
                if hasattr(self, 'update_game_list_by_category'):
                    self.update_game_list_by_category(auto_select_first=False)

                # Reselect the original ROM 
                rom_to_reselect = original_rom_being_edited if is_editing_clone else current_rom_name
                if hasattr(self, 'current_game'):
                    self.current_game = rom_to_reselect

                # Simple refresh after database is rebuilt
                if rom_to_reselect:
                    # Just reselect - this will trigger display_game_info automatically
                    self.after(150, lambda: self.reselect_rom_after_edit(rom_to_reselect))
                
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
        
        # PERFORMANCE OPTIMIZATION 1: Quick validation without full data loading
        cache_file = os.path.join(self.cache_dir, f"{self.current_game}_cache.json")
        
        # Check if we have a valid cache first (fastest path)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_peek = json.load(f)
                
                # Quick validation - if it has basic structure, we're good
                if isinstance(cache_peek, dict) and ('players' in cache_peek or 'game_data' in cache_peek):
                    print(f"✅ Valid cache found for {self.current_game} - launching preview directly")
                    self._launch_preview_process()
                    return
                else:
                    print(f"🔄 Invalid cache structure detected - will rebuild")
            except Exception as e:
                print(f"⚠️ Cache read error: {e} - will rebuild")
        
        # PERFORMANCE OPTIMIZATION 2: Only get minimal data for validation
        print(f"📦 Building cache for {self.current_game}...")
        
        # Get game data efficiently (this method should already be optimized)
        game_data = self.get_game_data(self.current_game)
        if not game_data:
            messagebox.showinfo("No Control Data", f"No control data found for {self.current_game}")
            return
        
        # PERFORMANCE OPTIMIZATION 3: Process custom configs only if they exist
        cfg_controls = {}
        if self.current_game in self.custom_configs:
            print(f"🎛️ Processing custom config for {self.current_game}")
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
        else:
            print(f"📄 No custom config found for {self.current_game}")

        # PERFORMANCE OPTIMIZATION 4: Apply XInput filtering only if needed
        if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
            game_data = filter_xinput_controls(game_data)
            print(f"🎯 Applied XInput-only filter")
        
        # PERFORMANCE OPTIMIZATION 5: Streamlined cache creation
        try:
            # Create cache in new format with metadata wrapper
            cache_data = {
                'rom_name': self.current_game,
                'input_mode': getattr(self, 'input_mode', 'xinput'),
                'friendly_names': getattr(self, 'friendly_names', True),
                'xinput_only_mode': getattr(self, 'xinput_only_mode', True),
                'cached_timestamp': time.time(),
                'cache_version': '2.0',
                'game_data': game_data
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            print(f"💾 Cache created for {self.current_game}")
            
        except Exception as e:
            print(f"⚠️ Error saving cache: {e} - preview will still launch")
        
        # Launch the preview
        self._launch_preview_process()

    def _launch_preview_process(self):
        """Optimized preview launch process"""
        
        # PERFORMANCE OPTIMIZATION 6: Handle PyInstaller frozen executable (fastest path)
        if getattr(sys, 'frozen', False):
            command = [
                sys.executable,
                "--preview-only",
                "--game", self.current_game
            ]
            if self.hide_preview_buttons:
                command.append("--no-buttons")
                
            # Launch and track the process
            process = subprocess.Popen(command, 
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            if not hasattr(self, 'preview_processes'):
                self.preview_processes = []
            self.preview_processes.append(process)
            print(f"🚀 Preview launched (PyInstaller mode)")
            return
        
        # PERFORMANCE OPTIMIZATION 7: Optimized script path discovery
        script_candidates = [
            os.path.join(self.app_dir, "mame_controls_main.py"),
            os.path.join(self.mame_dir, "mame_controls_main.py"), 
            os.path.join(self.preview_dir, "mame_controls_main.py")
        ]
        
        script_path = None
        for candidate in script_candidates:
            if os.path.exists(candidate):
                script_path = candidate
                break
        
        if not script_path:
            messagebox.showerror("Error", "Could not find mame_controls_main.py")
            return
        
        # Build and launch command
        try:
            command = [
                sys.executable,
                script_path,
                "--preview-only",
                "--game", self.current_game
            ]
            
            if self.hide_preview_buttons:
                command.append("--no-buttons")
                
            # Launch with optimized process creation
            process = subprocess.Popen(command,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            if not hasattr(self, 'preview_processes'):
                self.preview_processes = []
            self.preview_processes.append(process)
            print(f"🚀 Preview launched (script mode): {os.path.basename(script_path)}")
            
        except Exception as e:
            print(f"❌ Error launching preview: {e}")
            messagebox.showerror("Error", f"Failed to launch preview: {str(e)}")

    def toggle_hide_preview_buttons(self):
        """Toggle whether preview buttons should be hidden"""
        if hasattr(self, 'hide_buttons_toggle'):
            self.hide_preview_buttons = self.hide_buttons_toggle.get()
            print(f"Hide preview buttons set to: {self.hide_preview_buttons}")
            
            # Save setting to config file
            self.save_settings()
        
    def save_settings(self):
        """Save current settings - INCLUDE friendly names setting"""
        settings = {
            "preferred_preview_screen": getattr(self, 'preferred_preview_screen', 1),
            "visible_control_types": getattr(self, 'visible_control_types', ["BUTTON", "JOYSTICK"]),
            "hide_preview_buttons": getattr(self, 'hide_preview_buttons', False),
            "show_button_names": getattr(self, 'show_button_names', True),
            "input_mode": getattr(self, 'input_mode', 'xinput'),
            "xinput_only_mode": getattr(self, 'xinput_only_mode', True),
            "show_directional_alternatives": getattr(self, 'show_directional_alternatives', True),
            "show_friendly_names": getattr(self, 'show_friendly_names', True)  # NEW
        }
        
        print(f"Debug - saving settings (toggle state not saved): {settings}")
        
        try:
            if hasattr(self, 'settings_path'):
                os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
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

    # 3. FORCE physical mode in load_settings - IGNORE any saved rom_source_mode:
    def load_settings(self):
        """Load settings - ALWAYS force physical ROM mode on startup"""
        # Set sensible defaults
        self.preferred_preview_screen = 1
        self.visible_control_types = ["BUTTON"]
        self.hide_preview_buttons = False
        self.show_button_names = True
        self.input_mode = 'xinput'
        self.xinput_only_mode = True
        self.rom_source_mode = 'physical'  # ALWAYS FORCE PHYSICAL ON STARTUP
        
        # Load custom settings if available
        if hasattr(self, 'settings_path') and os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r') as f:
                    settings = json.load(f)
                    
                # Load all settings EXCEPT rom_source_mode
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
                
                # Load friendly names setting
                if 'show_friendly_names' in settings:
                    self.show_friendly_names = bool(settings.get('show_friendly_names', True))
                
                # IGNORE any saved rom_source_mode - always force physical
                self.rom_source_mode = 'physical'
                print("Forced ROM source mode to 'physical' on startup (toggle state not saved)")
                
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
            'rom_source_mode': self.rom_source_mode  # Will always be 'physical'
        }

    # 4. ALWAYS start physical in _load_secondary_data but load database ROMs too:
    def _load_secondary_data(self):
        """Load secondary data - ALWAYS start physical but prep database ROMs for toggle"""
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
                from mame_data_utils import load_gamedata_json
                self.gamedata_json, self.parent_lookup, self.clone_parents = load_gamedata_json(self.gamedata_path)
            
            # Database check and rebuild logic (unchanged)
            needs_rebuild = False
            
            if not os.path.exists(self.db_path):
                print("Database file doesn't exist, will create new one")
                needs_rebuild = True
            else:
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
                        if check_db_update_needed(self.gamedata_path, self.db_path):
                            print("gamedata.json is newer than database, rebuilding...")
                            needs_rebuild = True
                        else:
                            print("Database is up to date, no rebuild needed")
                            
                except sqlite3.Error as e:
                    print(f"Database appears corrupted ({e}), rebuilding...")
                    needs_rebuild = True
            
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
            
            # STARTUP STRATEGY: Always start with physical ROMs
            self.update_splash_message("Loading ROM sources...")
            
            # Load physical ROMs (for startup)
            print("Loading physical ROMs for startup...")
            self.available_roms = scan_roms_directory(self.mame_dir)
            
            # Also load database ROMs in background (for toggle)
            print("Loading database ROMs in background for toggle...")
            if self.gamedata_json:
                self.load_database_roms()
            
            # Force physical mode on startup
            self.rom_source_mode = 'physical'
            print(f"✅ STARTUP: Always using physical mode - {len(self.available_roms)} ROMs")
            print(f"✅ READY FOR TOGGLE: Database has {len(getattr(self, 'database_roms', []))} ROMs available")
            
            # Move to finish loading
            self.after(100, self._finish_loading)
            
        except Exception as e:
            print(f"Error in secondary data loading: {e}")
            import traceback
            traceback.print_exc()
            self.after(500, self._finish_loading)

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
        """Select the first available ROM in the listbox - FIXED to prevent duplicate calls"""
        
        # Add guard to prevent multiple calls during startup
        if hasattr(self, '_first_rom_selected') and self._first_rom_selected:
            print("First ROM already selected, skipping duplicate call")
            return
        
        # Check if we have any ROMs
        if not self.available_roms:
            print("No available ROMs, exiting select_first_rom")
            return
        
        # Make sure the game_list_data is populated
        if not hasattr(self, 'game_list_data') or not self.game_list_data:
            # If we don't have any items in the data list yet, trigger an update
            if hasattr(self, 'update_game_list_by_category'):
                self.update_game_list_by_category(auto_select_first=False)  # Don't auto-select during update
        
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
            
            # Mark as selected to prevent duplicate calls
            self._first_rom_selected = True
            
            # Display the ROM info with a slight delay to ensure UI is ready
            self.after(200, lambda: self.display_game_info(first_rom))
            print(f"Selected first ROM: {first_rom}")
        else:
            print("No game data available for selection")

            
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

    def create_hover_label(self, parent, text, font, color, bg_color, x_pos, width, tooltip_text=None, anchor="w"):
        """Create a label with hover functionality and tooltip for long text - UPDATED with anchor support"""
        
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
            anchor=anchor,  # NEW: Use the provided anchor parameter
            justify="left" if anchor == "w" else "right",  # NEW: Adjust justify based on anchor
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
                'console': game_data.get('console', False),  
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
            info_text += f"Console Game: {'Yes' if metadata.get('console', False) else 'No'}"  # NEW LINE
            #info_text += f"Alternating Play: {'Yes' if metadata['alternating'] else 'No'}\n"
            #info_text += f"Mirrored Controls: {'Yes' if metadata['mirrored'] else 'No'}"
            
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
            
            # Header setup - UPDATED column widths for better spacing
            header_titles = ["MAME Control", "Controller Input", "Game Action", "Mapping Source"]
            
            # NEW: Adjust column widths - first 3 columns equal, last column smaller and right-aligned
            total_width = 760  # Approximate total available width
            source_col_width = 120  # Fixed smaller width for mapping source
            remaining_width = total_width - source_col_width
            equal_col_width = remaining_width // 3  # Divide remaining space equally among first 3 columns
            
            col_widths = [equal_col_width, equal_col_width, equal_col_width, source_col_width]
            
            x_positions = [15]
            for i in range(1, len(header_titles)):
                x_positions.append(x_positions[i-1] + col_widths[i-1] + 15)

            for i, title in enumerate(header_titles):
                header_label = ctk.CTkLabel(
                    header_frame,
                    text=title,
                    font=("Arial", 13, "bold"),
                    text_color="#ffffff",
                    anchor="w" if i < 3 else "e",  # NEW: Right-align the last column header
                    justify="left" if i < 3 else "right"  # NEW: Right-align the last column header
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
            
            # In the control processing loop, around line where you create control entries:
            for i, control in enumerate(processed_controls):
                row_frame = tk.Frame(
                    controls_frame,
                    background=alt_colors[i % 2],
                    height=40
                )
                row_frame.pack(fill=tk.X, pady=1, expand=True)
                row_frame.pack_propagate(False)
                
                # FIXED: Enhanced handling for directional controls with proper color coding
                display_name = control['display_name']
                
                # FIX: Only show enhanced color for XInput alternatives, not default mappings
                if (hasattr(self, 'input_mode') and self.input_mode == 'xinput' and 
                    '|' in display_name and 
                    any(direction in control['control_name'] for direction in 
                    ['JOYSTICK_UP', 'JOYSTICK_DOWN', 'JOYSTICK_LEFT', 'JOYSTICK_RIGHT']) and
                    control.get('is_custom', False)):  # FIX: Only for custom mappings, not defaults
                    
                    # Enhanced tooltip for directional controls
                    tooltip_text = f"XInput Options: {display_name}"
                    
                    # Color coding ONLY for custom enhanced controls
                    display_color = self.theme_colors["success"]  # Green for enhanced controls
                else:
                    tooltip_text = None
                    # FIX: Use source color, not enhanced color for default mappings
                    display_color = control.get('source_color', self.theme_colors["text"])
                
                # Create labels with corrected data and alignment
                labels_data = [
                    # FIXED: Use source_color for MAME control when it's from ROM CFG, otherwise use MAME control color
                    (control['control_name'], ("Consolas", 12), 
                    control['source_color'] if control.get('is_custom', False) else self.get_mame_control_color(control['control_name']), 
                    "w"),  # Left-aligned
                    (display_name, ("Arial", 13), display_color, "w"),               # Left-aligned
                    (control['action'], ("Arial", 13, "bold"), self.theme_colors["text"], "w"),  # Left-aligned
                    (control['display_source'], ("Arial", 12), control['source_color'], "e")     # Right-aligned
                ]
                
                # Create labels with enhanced tooltip support and proper alignment
                for j, (text, font, color, anchor) in enumerate(labels_data):
                    # Enhanced tooltip text for controller input column (j==1)
                    if j == 1 and tooltip_text:
                        label_tooltip = tooltip_text
                    elif j == 2 and len(text) > 20:
                        label_tooltip = f"Full Action: {text}"
                    elif j == 1 and len(text) > 25:
                        label_tooltip = f"Full Input: {text}"
                    else:
                        label_tooltip = None
                    
                    # NEW: Pass the anchor parameter to create_hover_label
                    label = self.create_hover_label(
                        row_frame,
                        text=text,
                        font=font,
                        color=color,
                        bg_color=alt_colors[i % 2],
                        x_pos=x_positions[j],
                        width=col_widths[j],
                        tooltip_text=label_tooltip,
                        anchor=anchor  # NEW: Pass anchor parameter
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
    
    
    # Alternative: Dynamic color based on control type for even better visual organization
    def get_mame_control_color(self, control_name):
        """Get color for MAME control based on control type"""
        
        if "BUTTON" in control_name:
            #return "#4A90E2"  # Blue for buttons
            return "#4A90E2"  # Blue for buttons
        elif "JOYSTICK" in control_name or "STICK" in control_name:
            #return "#16A085"  # Teal for joysticks/movement
            return "#4A90E2"  # Teal for joysticks/movement
        elif any(special in control_name for special in ["DIAL", "PADDLE", "TRACKBALL", "MOUSE", "LIGHTGUN"]):
            #return "#E67E22"  # Orange for specialized controls
            return "#4A90E2"  # Orange for specialized controls
        elif any(special in control_name for special in ["PEDAL", "AD_STICK"]):
            #return "#8E44AD"  # Purple for analog controls
            return "#4A90E2"  # Purple for analog controls
        else:
            return self.theme_colors["primary"]  # Default blue
    
    def toggle_input_mode(self):
        """Handle toggling between input modes with CLEAN cache clearing"""
        if hasattr(self, 'input_mode_var'):
            old_mode = self.input_mode
            self.input_mode = self.input_mode_var.get()
            print(f"Input mode changed from {old_mode} to {self.input_mode}")
            
            # CRITICAL: Clear in-memory caches when mode changes
            if hasattr(self, 'rom_data_cache'):
                cleared_count = len(self.rom_data_cache)
                self.rom_data_cache.clear()
                print(f"Cleared rom_data_cache ({cleared_count} entries)")
                
            if hasattr(self, 'processed_cache'):
                cleared_count = len(self.processed_cache)
                self.processed_cache.clear()
                print(f"Cleared processed_cache ({cleared_count} entries)")
            
            # ALSO clear the @lru_cache on get_game_data if it exists
            if hasattr(self.get_game_data, 'cache_clear'):
                self.get_game_data.cache_clear()
                print("Cleared LRU cache on get_game_data method")
            
            # ALSO clear any disk cache files for ALL games to force regeneration
            if hasattr(self, 'cache_dir') and self.cache_dir:
                try:
                    import os
                    cache_files_removed = 0
                    for filename in os.listdir(self.cache_dir):
                        if filename.endswith('_cache.json'):
                            try:
                                os.remove(os.path.join(self.cache_dir, filename))
                                cache_files_removed += 1
                            except Exception as e:
                                print(f"Error removing cache file {filename}: {e}")
                    print(f"Removed {cache_files_removed} disk cache files")
                except Exception as e:
                    print(f"Error clearing disk cache: {e}")
            
            # Save the setting
            self.save_settings()
            
            # Refresh current game display if one is selected
            if self.current_game:
                print(f"Refreshing display for {self.current_game} with new input mode {self.input_mode}")
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
        """Update the statistics label - SIMPLIFIED without ROM source mode"""
        try:
            total_roms = len(self.available_roms)
            
            # REMOVED: mode_text = "Database" if self.rom_source_mode == "database" else "Physical"
            
            # Categorize all ROMs properly
            with_controls = 0
            missing_controls = 0
            generic_controls = 0
            custom_controls = 0
            mixed_controls = 0
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
                    
                    # Check for mixed controls
                    if self.has_mixed_controls(rom):
                        mixed_controls += 1
                else:
                    missing_controls += 1
                
                if categories['has_cfg_file']:
                    with_cfg_files += 1
            
            # SIMPLIFIED stats format (no mode indicator)
            stats = (
                f"ROMs: {total_roms}\n"
                f"With Controls: {with_controls} ({with_controls/max(total_roms, 1)*100:.1f}%)\n"
                f"Missing Controls: {missing_controls}\n"
                f"Custom Actions: {custom_controls}\n"
                f"Generic Controls: {generic_controls}\n"
                f"Mixed Controls: {mixed_controls}\n"
                f"Clone ROMs: {clone_roms}\n"
            )
            
            self.stats_label.configure(text=stats)
            
            # Debug output (simplified)
            print(f"Stats: Total={total_roms}, WithControls={with_controls}, "
                f"Missing={missing_controls}, Custom={custom_controls}, "
                f"Generic={generic_controls}, Mixed={mixed_controls}, CFG={with_cfg_files}, Clones={clone_roms}")
            
        except Exception as e:
            print(f"Error updating stats: {e}")
            import traceback
            traceback.print_exc()
            self.stats_label.configure(text="Statistics: Error")
   
    def has_mixed_controls(self, rom_name):
        """
        Check if a ROM has mixed P1 button controls 
        Returns True only if:
        1. ROM has some P1_BUTTON1-8 with custom 'name' values (like "Jab Punch")
        2. ROM has some P1_BUTTON1-8 without 'name' values
        3. Only looks at P1 buttons, ignores P2, joysticks, and other controls
        """
        try:
            # Get the raw gamedata for this ROM (before any processing/fallbacks)
            rom_data = None
            
            # Check ROM directly
            if rom_name in self.gamedata_json:
                rom_data = self.gamedata_json[rom_name]
            # Check parent if this is a clone
            elif hasattr(self, 'parent_lookup') and rom_name in self.parent_lookup:
                parent_rom = self.parent_lookup[rom_name]
                if parent_rom in self.gamedata_json:
                    rom_data = self.gamedata_json[parent_rom]
            
            if not rom_data or 'controls' not in rom_data:
                return False
            
            controls = rom_data['controls']
            if not controls:
                return False
            
            # Only look at P1_BUTTON1 through P1_BUTTON8
            p1_buttons = []
            for i in range(1, 9):  # BUTTON1 through BUTTON8
                button_name = f"P1_BUTTON{i}"
                if button_name in controls:
                    control_data = controls[button_name]
                    # Only include if the control has actual data
                    if control_data and isinstance(control_data, dict):
                        # Must have tag/mask or other meaningful data
                        if 'tag' in control_data or 'mask' in control_data:
                            p1_buttons.append((button_name, control_data))
            
            # Need at least 2 P1 buttons to have a meaningful mix
            if len(p1_buttons) < 2:
                return False
            
            # Count P1 buttons with and without custom names
            buttons_with_names = 0
            buttons_without_names = 0
            
            for button_name, control_data in p1_buttons:
                # Check if it has a meaningful 'name' field
                if 'name' in control_data:
                    name_value = control_data.get('name', '').strip()
                    if name_value:  # Has real custom name like "Jab Punch"
                        buttons_with_names += 1
                    else:  # Has 'name' key but it's empty
                        buttons_without_names += 1
                else:
                    # No 'name' key at all - just has tag/mask
                    buttons_without_names += 1
            
            # Return True only if we have BOTH named and unnamed P1 buttons
            result = buttons_with_names > 0 and buttons_without_names > 0
            
            if result:
                #print(f"Mixed P1 buttons found for {rom_name}: {buttons_with_names} with names, {buttons_without_names} without names")
                # Debug: show which buttons have names
                for button_name, control_data in p1_buttons:
                    name_value = control_data.get('name', '').strip()
                    #print(f"  {button_name}: {'HAS NAME' if name_value else 'NO NAME'} - {name_value}")
            
            return result
            
        except Exception as e:
            print(f"Error checking mixed controls for {rom_name}: {e}")
            return False
    
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
                
                # Update game_data with custom mappings - PASS friendly_names (always True for export)
                game_data = update_game_data_with_custom_mappings(
                    game_data, cfg_controls, 
                    getattr(self, 'default_controls', {}),
                    getattr(self, 'original_default_controls', {}),
                    self.input_mode,
                    True  # Always use friendly names for export
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
            
            # CRITICAL FIX: Process events multiple times to ensure full initialization
            import time  # Import time at the top to avoid conflicts
            for i in range(5):  # Process events multiple times
                app.processEvents()
                time.sleep(0.02)  # Small delay between processing
            
            print(f"Preview window initialized for {rom_name}")
            
            # CRITICAL FIX: Wait for window to be fully ready
            time.sleep(0.1)  # Give window time to fully initialize
            
            # Force another round of event processing
            app.processEvents()
            
            # FIXED: Load all settings properly even when no cache exists
            try:
                # Get settings directory
                settings_dir = os.path.join(self.preview_dir, "settings")
                
                # 1. Load bezel settings
                bezel_settings_path = os.path.join(settings_dir, "bezel_settings.json")
                rom_bezel_settings_path = os.path.join(settings_dir, f"{rom_name}_bezel_settings.json")
                
                # Choose which settings file to use
                settings_path = rom_bezel_settings_path if os.path.exists(rom_bezel_settings_path) else bezel_settings_path
                
                if os.path.exists(settings_path):
                    with open(settings_path, 'r') as f:
                        bezel_settings = json.load(f)
                        
                    # Apply bezel settings
                    preview.bezel_visible = bezel_settings.get("bezel_visible", True)
                    preview.logo_visible = bezel_settings.get("logo_visible", True)
                    
                    # CRITICAL FIX: Apply logo size settings
                    if 'logo_width_percentage' in bezel_settings:
                        preview.logo_width_percentage = bezel_settings['logo_width_percentage']
                    if 'logo_height_percentage' in bezel_settings:
                        preview.logo_height_percentage = bezel_settings['logo_height_percentage']
                    
                    print(f"Loaded bezel settings: logo size {preview.logo_width_percentage}% x {preview.logo_height_percentage}%")
                else:
                    # CRITICAL FIX: Load global logo settings even when no bezel settings exist
                    global_settings_path = os.path.join(settings_dir, "global_settings.json")
                    if os.path.exists(global_settings_path):
                        with open(global_settings_path, 'r') as f:
                            global_settings = json.load(f)
                        
                        # Apply logo size from global settings
                        if 'logo_width_percentage' in global_settings:
                            preview.logo_width_percentage = global_settings['logo_width_percentage']
                        if 'logo_height_percentage' in global_settings:
                            preview.logo_height_percentage = global_settings['logo_height_percentage']
                        
                        print(f"Loaded global logo settings: {preview.logo_width_percentage}% x {preview.logo_height_percentage}%")
                    else:
                        # CRITICAL FIX: Use proper default logo sizes (not tiny defaults)
                        preview.logo_width_percentage = getattr(self, 'logo_width_percentage', 15)
                        preview.logo_height_percentage = getattr(self, 'logo_height_percentage', 15)
                        print(f"Using fallback logo settings: {preview.logo_width_percentage}% x {preview.logo_height_percentage}%")
                
                # 3. Load text appearance settings to ensure proper text rendering
                text_settings_path = os.path.join(settings_dir, "text_appearance_settings.json")
                rom_text_settings_path = os.path.join(settings_dir, f"{rom_name}_text_appearance_settings.json")
                
                text_settings_file = rom_text_settings_path if os.path.exists(rom_text_settings_path) else text_settings_path
                
                if os.path.exists(text_settings_file):
                    with open(text_settings_file, 'r') as f:
                        text_settings = json.load(f)
                    
                    # Apply text settings to preview
                    if hasattr(preview, 'text_settings'):
                        preview.text_settings.update(text_settings)
                    else:
                        preview.text_settings = text_settings
                    
                    print(f"Loaded text appearance settings for proper text rendering")
                
                # CRITICAL FIX: Ensure logo is resized properly if it exists
                if hasattr(preview, 'logo_label') and preview.logo_label and hasattr(preview, 'resize_logo'):
                    preview.resize_logo()
                    print(f"Resized logo to {preview.logo_width_percentage}% x {preview.logo_height_percentage}%")
                
                # Update UI based on settings
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
                    
            except Exception as e:
                print(f"Error loading settings for {rom_name}: {e}")
                # CRITICAL FIX: Even on error, ensure proper logo sizes
                if hasattr(preview, 'logo_width_percentage'):
                    if not hasattr(preview, 'logo_width_percentage') or preview.logo_width_percentage < 5:
                        preview.logo_width_percentage = getattr(self, 'logo_width_percentage', 15)
                    if not hasattr(preview, 'logo_height_percentage') or preview.logo_height_percentage < 5:
                        preview.logo_height_percentage = getattr(self, 'logo_height_percentage', 15)
            
            # CRITICAL: Ensure controls are above bezel
            if hasattr(preview, 'raise_controls_above_bezel'):
                preview.raise_controls_above_bezel()
            else:
                # Manual raising of controls if method doesn't exist
                if hasattr(preview, 'control_labels'):
                    for control_name, control_data in preview.control_labels.items():
                        if 'label' in control_data and control_data['label']:
                            control_data['label'].raise_()
            
            # CRITICAL FIX: Final processing to ensure everything is rendered properly
            for i in range(5):
                app.processEvents()
                time.sleep(0.03)
            
            print(f"Final UI processing completed for {rom_name}")
            
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
                            
                            # Update game_data with custom mappings - PASS friendly_names (always True for batch export)
                            game_data = update_game_data_with_custom_mappings(
                                game_data, 
                                cfg_controls, 
                                getattr(self, 'default_controls', {}),
                                getattr(self, 'original_default_controls', {}),
                                self.input_mode,
                                True  # Always use friendly names for batch export
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
    
    def initialize_fightstick_directory(self):
        """Initialize the fightstick layouts directory"""
        self.fightstick_dir = os.path.join(self.preview_dir, "fightstick")
        os.makedirs(self.fightstick_dir, exist_ok=True)
        
        # Create layouts subdirectory
        self.layouts_dir = os.path.join(self.fightstick_dir, "layouts")
        os.makedirs(self.layouts_dir, exist_ok=True)
        
        return self.fightstick_dir

    def save_custom_layout(self, layout_name, mappings, base_preset, description=""):
        """Save a custom fightstick layout to file"""
        try:
            # Ensure directory exists
            if not hasattr(self, 'layouts_dir'):
                self.initialize_fightstick_directory()
            
            # Clean filename
            safe_filename = "".join(c for c in layout_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_filename = safe_filename.replace(' ', '_')
            
            layout_data = {
                "name": layout_name,
                "description": description,
                "base_preset": base_preset,
                "created_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mappings": mappings,
                "version": "1.0"
            }
            
            filepath = os.path.join(self.layouts_dir, f"{safe_filename}.json")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(layout_data, f, indent=2)
            
            print(f"Saved custom layout: {filepath}")
            return filepath
            
        except Exception as e:
            print(f"Error saving layout: {e}")
            return None

    def load_custom_layouts(self):
        """Load all custom fightstick layouts from files"""
        custom_layouts = {}
        
        if not hasattr(self, 'layouts_dir'):
            self.initialize_fightstick_directory()
        
        if not os.path.exists(self.layouts_dir):
            return custom_layouts
        
        try:
            for filename in os.listdir(self.layouts_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.layouts_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            layout_data = json.load(f)
                        
                        # Validate required fields
                        if all(key in layout_data for key in ['name', 'mappings', 'base_preset']):
                            layout_id = filename[:-5]  # Remove .json extension
                            custom_layouts[layout_id] = layout_data
                            print(f"Loaded custom layout: {layout_data['name']}")
                        else:
                            print(f"Invalid layout file: {filename}")
                            
                    except Exception as e:
                        print(f"Error loading layout {filename}: {e}")
        
        except Exception as e:
            print(f"Error reading layouts directory: {e}")
        
        return custom_layouts

    def delete_custom_layout(self, layout_id):
        """Delete a custom layout file"""
        try:
            filepath = os.path.join(self.layouts_dir, f"{layout_id}.json")
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"Deleted custom layout: {layout_id}")
                return True
            return False
        except Exception as e:
            print(f"Error deleting layout: {e}")
            return False

    def create_button_remapping_dialog(self, parent_dialog, current_mappings, preset_name):
        """Create a dialog for customizing button mappings before applying to games"""
        
        # Create the remapping dialog
        remap_dialog = ctk.CTkToplevel(parent_dialog)
        remap_dialog.title(f"Customize {preset_name} Button Layout")
        remap_dialog.geometry("900x600")
        remap_dialog.configure(fg_color=self.theme_colors["background"])
        remap_dialog.transient(parent_dialog)
        remap_dialog.grab_set()
        
        # Header
        header_frame = ctk.CTkFrame(remap_dialog, fg_color=self.theme_colors["primary"], corner_radius=0, height=60)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        ctk.CTkLabel(
            header_frame,
            text=f"Customize {preset_name} Layout",
            font=("Arial", 18, "bold"),
            text_color="#ffffff"
        ).pack(side="left", padx=20, pady=15)
        
        # Main content
        content_frame = ctk.CTkScrollableFrame(
            remap_dialog, 
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Description
        desc_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        desc_card.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            desc_card,
            text="Customize which physical buttons map to each game action. This is useful if your fightstick has a different button layout.",
            font=("Arial", 13),
            wraplength=800,
            justify="left"
        ).pack(padx=15, pady=15, anchor="w")
        
        # Available button options
        available_buttons = [
            ("JOYCODE_1_BUTTON1", "Button 1 (A)"),
            ("JOYCODE_1_BUTTON2", "Button 2 (B)"),
            ("JOYCODE_1_BUTTON3", "Button 3 (X)"),
            ("JOYCODE_1_BUTTON4", "Button 4 (Y)"),
            ("JOYCODE_1_BUTTON5", "Button 5 (LB)"),
            ("JOYCODE_1_BUTTON6", "Button 6 (RB)"),
            ("JOYCODE_1_BUTTON7", "Button 7 (LT)"),
            ("JOYCODE_1_BUTTON8", "Button 8 (RT)"),
            ("JOYCODE_1_SLIDER2_NEG_SWITCH", "Slider/Trigger (RT Analog)"),
            ("JOYCODE_1_SLIDER2_POS_SWITCH", "Slider/Trigger (LT Analog)"),
        ]
        
        # Mapping configuration card
        mapping_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        mapping_card.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            mapping_card,
            text="Button Mappings",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Create mapping grid
        mapping_frame = ctk.CTkFrame(mapping_card, fg_color="transparent")
        mapping_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # Headers
        header_frame = ctk.CTkFrame(mapping_frame, fg_color=self.theme_colors["primary"], corner_radius=4)
        header_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(header_frame, text="Game Action", font=("Arial", 13, "bold"), text_color="white").pack(side="left", padx=20, pady=8)
        ctk.CTkLabel(header_frame, text="Physical Button", font=("Arial", 13, "bold"), text_color="white").pack(side="right", padx=20, pady=8)
        
        # Store the dropdown variables
        dropdown_vars = {}
        
        # Game action names for better display
        action_names = {
            "P1_BUTTON1": "Light Punch",
            "P1_BUTTON2": "Medium Punch", 
            "P1_BUTTON3": "Heavy Punch",
            "P1_BUTTON4": "Light Kick",
            "P1_BUTTON5": "Medium Kick",
            "P1_BUTTON6": "Heavy Kick",
            "P2_BUTTON1": "P2 Light Punch",
            "P2_BUTTON2": "P2 Medium Punch",
            "P2_BUTTON3": "P2 Heavy Punch", 
            "P2_BUTTON4": "P2 Light Kick",
            "P2_BUTTON5": "P2 Medium Kick",
            "P2_BUTTON6": "P2 Heavy Kick"
        }
        
        # For Mortal Kombat
        if "mortal" in preset_name.lower() or "mk" in preset_name.lower():
            action_names.update({
                "P1_BUTTON1": "High Punch",
                "P1_BUTTON2": "Block",
                "P1_BUTTON3": "High Kick", 
                "P1_BUTTON4": "Low Punch",
                "P1_BUTTON5": "Low Kick",
                "P1_BUTTON6": "Run"
            })
        
        # For Tekken
        if "tekken" in preset_name.lower():
            action_names.update({
                "P1_BUTTON1": "Left Punch",
                "P1_BUTTON2": "Right Punch",
                "P1_BUTTON3": "Left Kick",
                "P1_BUTTON4": "Right Kick",
                "P1_BUTTON5": "Tag" if "tag" in preset_name.lower() else "Special"
            })
        
        # Create dropdowns for each mapping
        for mame_control, current_joycode in current_mappings.items():
            if mame_control.startswith('P1_'):  # Only show P1 controls in the UI
                row_frame = ctk.CTkFrame(mapping_frame, fg_color=self.theme_colors["background"], corner_radius=4)
                row_frame.pack(fill="x", pady=2)
                
                # Action name
                action_name = action_names.get(mame_control, mame_control)
                ctk.CTkLabel(
                    row_frame,
                    text=action_name,
                    font=("Arial", 13),
                    anchor="w"
                ).pack(side="left", padx=20, pady=8)
                
                # Find current selection
                current_selection = None
                for button_code, button_name in available_buttons:
                    if button_code == current_joycode:
                        current_selection = button_name
                        break
                
                if current_selection is None:
                    current_selection = current_joycode  # Fallback to raw code
                
                # Dropdown for button selection
                button_var = tk.StringVar(value=current_selection)
                dropdown_vars[mame_control] = button_var
                
                button_values = [name for _, name in available_buttons]
                button_dropdown = ctk.CTkComboBox(
                    row_frame,
                    values=button_values,
                    variable=button_var,
                    width=200,
                    fg_color=self.theme_colors["card_bg"],
                    button_color=self.theme_colors["primary"],
                    button_hover_color=self.theme_colors["secondary"],
                    dropdown_fg_color=self.theme_colors["card_bg"]
                )
                button_dropdown.pack(side="right", padx=20, pady=8)
        
        # Quick preset buttons
        presets_frame = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        presets_frame.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            presets_frame,
            text="Quick Layouts",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        quick_frame = ctk.CTkFrame(presets_frame, fg_color="transparent")
        quick_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        def apply_standard_layout():
            """Apply standard 6-button fightstick layout"""
            standard_layout = {
                "P1_BUTTON1": "Button 3 (X)",    # Light Punch -> X
                "P1_BUTTON2": "Button 4 (Y)",    # Medium Punch -> Y  
                "P1_BUTTON3": "Button 6 (RB)",   # Heavy Punch -> RB
                "P1_BUTTON4": "Button 1 (A)",    # Light Kick -> A
                "P1_BUTTON5": "Button 2 (B)",    # Medium Kick -> B
                "P1_BUTTON6": "Slider/Trigger (RT Analog)"  # Heavy Kick -> RT
            }
            for control, button_name in standard_layout.items():
                if control in dropdown_vars:
                    dropdown_vars[control].set(button_name)
        
        def apply_alternative_layout():
            """Apply alternative layout (swapped triggers)"""
            alt_layout = {
                "P1_BUTTON1": "Button 3 (X)",
                "P1_BUTTON2": "Button 4 (Y)",
                "P1_BUTTON3": "Button 5 (LB)",   # Heavy Punch -> LB instead of RB
                "P1_BUTTON4": "Button 1 (A)",
                "P1_BUTTON5": "Button 2 (B)",
                "P1_BUTTON6": "Button 6 (RB)"    # Heavy Kick -> RB instead of RT
            }
            for control, button_name in alt_layout.items():
                if control in dropdown_vars:
                    dropdown_vars[control].set(button_name)
        
        ctk.CTkButton(
            quick_frame,
            text="Standard Layout",
            command=apply_standard_layout,
            width=140,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            quick_frame,
            text="Alternative Layout",
            command=apply_alternative_layout,
            width=140,
            fg_color=self.theme_colors["secondary"],
            hover_color=self.theme_colors["primary"]
        ).pack(side="left", padx=5)
        
        # Bottom buttons
        buttons_frame = ctk.CTkFrame(remap_dialog, height=70, fg_color=self.theme_colors["card_bg"], corner_radius=0)
        buttons_frame.pack(fill="x", side="bottom", padx=0, pady=0)
        buttons_frame.pack_propagate(False)
        
        button_container = ctk.CTkFrame(buttons_frame, fg_color="transparent")
        button_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Store result
        result = {"mappings": None, "cancelled": True}
        
        def apply_custom_mappings():
            """Apply the customized mappings"""
            # Convert dropdown selections back to joycodes
            new_mappings = {}
            button_name_to_code = {name: code for code, name in available_buttons}
            
            for mame_control, var in dropdown_vars.items():
                selected_name = var.get()
                joycode = button_name_to_code.get(selected_name, selected_name)
                new_mappings[mame_control] = joycode
                
                # Also update P2 controls if they exist in original mappings
                p2_control = mame_control.replace("P1_", "P2_")
                if p2_control in current_mappings:
                    p2_joycode = joycode.replace("JOYCODE_1_", "JOYCODE_2_")
                    new_mappings[p2_control] = p2_joycode
            
            result["mappings"] = new_mappings
            result["cancelled"] = False
            remap_dialog.destroy()
        
        def cancel_remapping():
            """Cancel the remapping"""
            result["cancelled"] = True
            remap_dialog.destroy()
        
        # Apply button
        ctk.CTkButton(
            button_container,
            text="Apply Custom Layout",
            command=apply_custom_mappings,
            width=180,
            height=40,
            fg_color=self.theme_colors["success"],
            hover_color="#218838",
            font=("Arial", 14, "bold")
        ).pack(side="right", padx=5)
        
        # Cancel button
        ctk.CTkButton(
            button_container,
            text="Cancel",
            command=cancel_remapping,
            width=120,
            height=40,
            fg_color=self.theme_colors["danger"],
            hover_color="#c82333",
            font=("Arial", 14)
        ).pack(side="right", padx=5)
        
        # Center dialog
        remap_dialog.update_idletasks()
        width = remap_dialog.winfo_width()
        height = remap_dialog.winfo_height()
        x = (remap_dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (remap_dialog.winfo_screenheight() // 2) - (height // 2)
        remap_dialog.geometry(f'{width}x{height}+{x}+{y}')
        
        # Wait for dialog to close
        remap_dialog.wait_window()
        
        return result

    def create_layout_save_dialog(self, parent, base_name):
        """Dialog to get name and description for saving custom layout"""
        save_dialog = ctk.CTkToplevel(parent)
        save_dialog.title("Save Custom Layout")
        save_dialog.geometry("400x300")
        save_dialog.configure(fg_color=self.theme_colors["background"])
        save_dialog.transient(parent)
        save_dialog.grab_set()
        
        # Content
        ctk.CTkLabel(
            save_dialog,
            text="Save Custom Layout",
            font=("Arial", 16, "bold")
        ).pack(pady=20)
        
        # Name field
        name_frame = ctk.CTkFrame(save_dialog, fg_color="transparent")
        name_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(name_frame, text="Layout Name:", font=("Arial", 13)).pack(anchor="w")
        name_var = tk.StringVar(value=f"My {base_name} Layout")
        name_entry = ctk.CTkEntry(name_frame, textvariable=name_var, width=300)
        name_entry.pack(fill="x", pady=5)
        
        # Description field
        desc_frame = ctk.CTkFrame(save_dialog, fg_color="transparent")
        desc_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(desc_frame, text="Description (optional):", font=("Arial", 13)).pack(anchor="w")
        desc_var = tk.StringVar(value=f"Custom layout based on {base_name}")
        desc_entry = ctk.CTkEntry(desc_frame, textvariable=desc_var, width=300)
        desc_entry.pack(fill="x", pady=5)
        
        # Result storage
        result = {"name": "", "description": "", "cancelled": True}
        
        # Buttons
        button_frame = ctk.CTkFrame(save_dialog, fg_color="transparent")
        button_frame.pack(pady=20)
        
        def save_layout():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Invalid Name", "Please enter a layout name.", parent=save_dialog)
                return
            
            result["name"] = name
            result["description"] = desc_var.get().strip()
            result["cancelled"] = False
            save_dialog.destroy()
        
        ctk.CTkButton(
            button_frame,
            text="Save Layout",
            command=save_layout,
            fg_color=self.theme_colors["success"]
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=save_dialog.destroy,
            fg_color=self.theme_colors["danger"]
        ).pack(side="left", padx=10)
        
        # Center and wait
        save_dialog.update_idletasks()
        width = save_dialog.winfo_width()
        height = save_dialog.winfo_height()
        x = (save_dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (save_dialog.winfo_screenheight() // 2) - (height // 2)
        save_dialog.geometry(f'{width}x{height}+{x}+{y}')
        
        save_dialog.wait_window()
        return result

    def show_layout_manager_dialog(self, parent):
        """Dialog to manage existing custom layouts"""
        manager_dialog = ctk.CTkToplevel(parent)
        manager_dialog.title("Manage Custom Layouts")
        manager_dialog.geometry("600x400")
        manager_dialog.configure(fg_color=self.theme_colors["background"])
        manager_dialog.transient(parent)
        manager_dialog.grab_set()
        
        # Header
        ctk.CTkLabel(
            manager_dialog,
            text="Manage Custom Layouts",
            font=("Arial", 16, "bold")
        ).pack(pady=20)
        
        # Layout list
        list_frame = ctk.CTkFrame(manager_dialog)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Create listbox for layouts
        layout_listbox = tk.Listbox(
            list_frame,
            font=("Arial", 12),
            height=10,
            background=self.theme_colors["card_bg"],
            foreground=self.theme_colors["text"],
            selectbackground=self.theme_colors["primary"]
        )
        layout_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        # Populate with custom layouts
        layout_ids = []
        for layout_id, layout_data in self.custom_layouts.items():
            created_date = layout_data.get('created_date', 'Unknown date')
            display_text = f"{layout_data['name']} - {created_date}"
            layout_listbox.insert(tk.END, display_text)
            layout_ids.append(layout_id)
        
        # Scrollbar
        scrollbar = ctk.CTkScrollbar(list_frame, orientation="vertical", command=layout_listbox.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        layout_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Buttons
        button_frame = ctk.CTkFrame(manager_dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=20)
        
        def delete_selected():
            selection = layout_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a layout to delete.", parent=manager_dialog)
                return
            
            idx = selection[0]
            layout_id = layout_ids[idx]
            layout_name = self.custom_layouts[layout_id]['name']
            
            if messagebox.askyesno("Confirm Delete", f"Delete custom layout '{layout_name}'?", parent=manager_dialog):
                if self.delete_custom_layout(layout_id):
                    # Refresh the layouts
                    self.custom_layouts = self.load_custom_layouts()
                    manager_dialog.destroy()
                    messagebox.showinfo("Deleted", f"Custom layout '{layout_name}' deleted.", parent=parent)
                else:
                    messagebox.showerror("Error", "Failed to delete layout.", parent=manager_dialog)
        
        ctk.CTkButton(
            button_frame,
            text="Delete Selected",
            command=delete_selected,
            fg_color=self.theme_colors["danger"],
            hover_color="#c82333"
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            button_frame,
            text="Close",
            command=manager_dialog.destroy,
            fg_color=self.theme_colors["primary"]
        ).pack(side="right", padx=10)
        
        # Center dialog
        manager_dialog.update_idletasks()
        width = manager_dialog.winfo_width()
        height = manager_dialog.winfo_height()
        x = (manager_dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (manager_dialog.winfo_screenheight() // 2) - (height // 2)
        manager_dialog.geometry(f'{width}x{height}+{x}+{y}')

    # ====================================================================
    # REPLACE YOUR EXISTING create_fightstick_mapping_tool METHOD WITH THIS
    # ====================================================================

    def configure_game_fightstick_mapping(self, rom_name, button_mappings, backup_cfg=True, create_missing=True, update_existing=True, mame_version="new"):
        """Configure a single game's CFG file with fightstick button mappings"""
        try:
            import xml.etree.ElementTree as ET
            import shutil
            from datetime import datetime
            
            # Construct CFG file path
            cfg_dir = os.path.join(self.mame_dir, "cfg")
            cfg_path = os.path.join(cfg_dir, f"{rom_name}.cfg")
            
            # Create cfg directory if it doesn't exist
            os.makedirs(cfg_dir, exist_ok=True)
            
            # Backup existing CFG if it exists and backup is enabled
            if backup_cfg and os.path.exists(cfg_path):
                # Create backup in fightstick directory
                if not hasattr(self, 'fightstick_dir'):
                    self.initialize_fightstick_directory()
                
                backup_dir = os.path.join(self.fightstick_dir, "backups")
                os.makedirs(backup_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_filename = f"{rom_name}.{timestamp}.cfg"
                backup_path = os.path.join(backup_dir, backup_filename)
                
                shutil.copy2(cfg_path, backup_path)
                print(f"Backed up existing CFG to: {backup_path}")
            
            # Load or create CFG structure
            if os.path.exists(cfg_path):
                try:
                    tree = ET.parse(cfg_path)
                    root = tree.getroot()
                except ET.ParseError as e:
                    print(f"Warning: Corrupted CFG file {cfg_path}, creating new one: {e}")
                    root = self.create_new_cfg_structure(rom_name)
                    tree = ET.ElementTree(root)
            else:
                root = self.create_new_cfg_structure(rom_name)
                tree = ET.ElementTree(root)
            
            # Find or create system element
            system_elem = root.find(f".//system[@name='{rom_name}']")
            if system_elem is None:
                system_elem = ET.SubElement(root, "system", name=rom_name)
            
            # Find or create input element
            input_elem = system_elem.find("input")
            if input_elem is None:
                input_elem = ET.SubElement(system_elem, "input")
            
            # Track which buttons were modified
            modified_buttons = []
            created_buttons = []
            
            # Process each button mapping
            for mame_control, joycode in button_mappings.items():
                # Skip if no joycode specified
                if not joycode:
                    continue
                
                # Convert MAME control to port data
                port_data = self.mame_control_to_port_data(mame_control, joycode, mame_version, rom_name)
                if not port_data:
                    print(f"Warning: Could not convert {mame_control} to port data")
                    continue
                
                # Check if port already exists - match by tag and type (not mask)
                existing_port = input_elem.find(f".//port[@tag='{port_data['tag']}'][@type='{port_data['type']}'][@mask='{port_data['mask']}']")
                
                if existing_port is not None:
                    if update_existing:
                        # Update existing port
                        newseq = existing_port.find("newseq[@type='standard']")
                        if newseq is not None:
                            old_value = newseq.text
                            newseq.text = port_data['newseq']
                            modified_buttons.append(f"{mame_control}: {old_value} -> {port_data['newseq']}")
                        else:
                            # Add newseq to existing port
                            newseq = ET.SubElement(existing_port, "newseq")
                            newseq.set("type", "standard")
                            newseq.text = port_data['newseq']
                            created_buttons.append(f"{mame_control}: Added newseq {port_data['newseq']}")
                        
                        # Update defvalue if it exists
                        existing_port.set("defvalue", port_data['defvalue'])
                    else:
                        print(f"Skipping existing button {mame_control} (update_existing=False)")
                else:
                    if create_missing:
                        # Create new port
                        self.add_formatted_port_to_input(input_elem, port_data)
                        created_buttons.append(f"{mame_control}: Created with {port_data['newseq']}")
                    else:
                        print(f"Skipping missing button {mame_control} (create_missing=False)")
            
            # Save the modified CFG file
            self.save_formatted_cfg(tree, cfg_path)
            
            # Prepare result message
            changes = []
            if created_buttons:
                changes.append(f"Created {len(created_buttons)} buttons")
            if modified_buttons:
                changes.append(f"Modified {len(modified_buttons)} buttons")
            
            if changes:
                message = f"CFG updated: {', '.join(changes)}"
            else:
                message = "No changes made (all buttons already configured)"
            
            return {
                'success': True,
                'message': message,
                'created_count': len(created_buttons),
                'modified_count': len(modified_buttons),
                'cfg_path': cfg_path
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f"Error configuring {rom_name}: {str(e)}",
                'created_count': 0,
                'modified_count': 0
            }

    def mame_control_to_port_data(self, mame_control, joycode, mame_version="new", rom_name=None):
        """Convert MAME control name and joycode to port data for CFG file using gamedata"""
        try:
            # Get the port info from gamedata for this specific ROM first
            port_info = None
            
            if rom_name and rom_name in self.gamedata_json:
                rom_data = self.gamedata_json[rom_name]
                if 'controls' in rom_data and rom_data['controls']:
                    if mame_control in rom_data['controls']:
                        control_data = rom_data['controls'][mame_control]
                        if isinstance(control_data, dict) and 'tag' in control_data and 'mask' in control_data:
                            port_info = {
                                'tag': control_data['tag'],
                                'type': mame_control,
                                'mask': control_data['mask']
                            }
            
            # If not found in specific ROM, look through gamedata to find any game with this control
            if not port_info:
                for rom_name_search, rom_data in self.gamedata_json.items():
                    if 'controls' in rom_data and rom_data['controls']:
                        if mame_control in rom_data['controls']:
                            control_data = rom_data['controls'][mame_control]
                            if isinstance(control_data, dict) and 'tag' in control_data and 'mask' in control_data:
                                port_info = {
                                    'tag': control_data['tag'],
                                    'type': mame_control,
                                    'mask': control_data['mask']
                                }
                                break
            
            # If we still couldn't find it in gamedata, fall back to basic structure
            if not port_info:
                print(f"Warning: Could not find port info for {mame_control} in gamedata, using fallback")
                
                # Simple fallback based on player and button number
                if mame_control.startswith('P1_'):
                    if 'BUTTON1' in mame_control or 'BUTTON2' in mame_control or 'BUTTON3' in mame_control:
                        tag = ":IN0"
                    else:
                        tag = ":IN1"
                elif mame_control.startswith('P2_'):
                    if 'BUTTON1' in mame_control or 'BUTTON2' in mame_control or 'BUTTON3' in mame_control:
                        tag = ":IN0"
                    elif 'BUTTON6' in mame_control:
                        tag = ":IN2"
                    else:
                        tag = ":IN1"
                else:
                    tag = ":IN0"
                
                port_info = {
                    'tag': tag,
                    'type': mame_control,
                    'mask': "1"  # Default mask
                }
            
            # Handle MAME version differences for analog controls
            if "SLIDER2" in joycode and mame_version == "old":
                joycode = joycode.replace("SLIDER2", "ZAXIS")
            elif "ZAXIS" in joycode and mame_version == "new":
                joycode = joycode.replace("ZAXIS", "SLIDER2")
            
            # Handle defvalue logic - normally matches mask, but some tags are exceptions
            defvalue = "0"  # Default to 0
            
            # For most standard input tags, defvalue should match the mask
            if port_info['tag'] in [":IN0", ":IN1", ":IN2", ":IN3", ":IN4", ":IN5"]:
                defvalue = port_info['mask']  # Copy mask to defvalue
            # For JVS and other special tags, keep defvalue as 0
            elif port_info['tag'].startswith(":JVS_"):
                defvalue = "0"  # Keep as 0 for JVS tags
            # Add other exception tags as needed
            
            return {
                'tag': port_info['tag'],
                'type': port_info['type'],
                'mask': port_info['mask'],
                'defvalue': defvalue,  # Now uses proper logic
                'newseq': joycode
            }
            
        except Exception as e:
            print(f"Error converting {mame_control} to port data: {e}")
            return None
    
    def create_fightstick_mapping_tool(self):
        """Create a tool for configuring fightstick button mappings for fighting games with custom layout support"""
        
        # Store reference to main app for use in nested functions
        main_app = self  # ADD THIS LINE
        
        # Initialize the fightstick directory and load custom layouts
        self.initialize_fightstick_directory()
        self.custom_layouts = self.load_custom_layouts()
        
        # Create dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Fightstick Button Mapper")
        dialog.geometry("800x700")
        dialog.configure(fg_color=self.theme_colors["background"])
        dialog.transient(self)
        dialog.grab_set()
        
        # Store dialog reference for custom layout dialogs
        self.fightstick_dialog = dialog
        
        # Header
        header_frame = ctk.CTkFrame(dialog, fg_color=self.theme_colors["primary"], corner_radius=0, height=60)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        ctk.CTkLabel(
            header_frame,
            text="Fightstick Button Mapper",
            font=("Arial", 18, "bold"),
            text_color="#ffffff"
        ).pack(side="left", padx=20, pady=15)
        
        # Main content with scrolling
        content_frame = ctk.CTkScrollableFrame(
            dialog, 
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Description card
        desc_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        desc_card.pack(fill="x", padx=0, pady=(0, 15))
        
        description_text = (
            "This tool configures fighting games to work properly with arcade fightsticks by:\n\n"
            "• Remapping buttons to match standard fightstick layout\n"
            "• Adding missing button configurations to CFG files\n"
            "• Setting correct mask and defvalue for each button\n"
            "• Creating and using custom button layouts\n\n"
            "Select a mapping preset, customize if needed, and choose which games to configure."
        )
        
        ctk.CTkLabel(
            desc_card,
            text=description_text,
            font=("Arial", 13),
            justify="left",
            wraplength=750
        ).pack(padx=15, pady=15, anchor="w")
        
        # Mapping presets card
        presets_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        presets_card.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            presets_card,
            text="Button Mapping Presets",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Define mapping presets (your existing ones)
        mapping_presets = {
            "6button": {
                "name": "6-Button Fighting Games (SF/KI/etc)",
                "description": "Standard 6-button layout for Street Fighter, Killer Instinct, and similar games",
                "mappings": {
                    "P1_BUTTON1": "JOYCODE_1_BUTTON3",  # Light Punch -> Button 3
                    "P1_BUTTON2": "JOYCODE_1_BUTTON4",  # Medium Punch -> Button 4  
                    "P1_BUTTON3": "JOYCODE_1_BUTTON6",  # Heavy Punch -> Button 6
                    "P1_BUTTON4": "JOYCODE_1_BUTTON1",  # Light Kick -> Button 1
                    "P1_BUTTON5": "JOYCODE_1_BUTTON2",  # Medium Kick -> Button 2
                    "P1_BUTTON6": "JOYCODE_1_SLIDER2_NEG_SWITCH",  # Heavy Kick -> Slider
                    "P2_BUTTON1": "JOYCODE_2_BUTTON3",
                    "P2_BUTTON2": "JOYCODE_2_BUTTON4",
                    "P2_BUTTON3": "JOYCODE_2_BUTTON6", 
                    "P2_BUTTON4": "JOYCODE_2_BUTTON1",
                    "P2_BUTTON5": "JOYCODE_2_BUTTON2",
                    "P2_BUTTON6": "JOYCODE_2_SLIDER2_NEG_SWITCH"
                }
            },
            "mk": {
                "name": "Mortal Kombat Layout",
                "description": "6-button Mortal Kombat layout (HP, LP, BL, RN, HK, LK)",
                "mappings": {
                    "P1_BUTTON1": "JOYCODE_1_BUTTON6",  # High Punch -> Button 6 (RB)
                    "P1_BUTTON2": "JOYCODE_1_BUTTON4",  # Block -> Button 4 (Y)
                    "P1_BUTTON3": "JOYCODE_1_SLIDER2_NEG_SWITCH",  # High Kick -> Slider (RT)
                    "P1_BUTTON4": "JOYCODE_1_BUTTON3",  # Low Punch -> Button 3 (X)
                    "P1_BUTTON5": "JOYCODE_1_BUTTON1",  # Low Kick -> Button 1 (A)
                    "P1_BUTTON6": "JOYCODE_1_BUTTON2",  # Run -> Button 2 (B)
                    "P2_BUTTON1": "JOYCODE_2_BUTTON6",
                    "P2_BUTTON2": "JOYCODE_2_BUTTON4",
                    "P2_BUTTON3": "JOYCODE_2_SLIDER2_NEG_SWITCH",
                    "P2_BUTTON4": "JOYCODE_2_BUTTON3",
                    "P2_BUTTON5": "JOYCODE_2_BUTTON1",
                    "P2_BUTTON6": "JOYCODE_2_BUTTON2",
                }
            },
            "tekken": {
                "name": "Tekken Layout",
                "description": "4-button Tekken layout (LP, RP, LK, RK)",
                "mappings": {
                    "P1_BUTTON1": "JOYCODE_1_BUTTON3",  # Left Punch -> Button 3 (X)
                    "P1_BUTTON2": "JOYCODE_1_BUTTON4",  # Right Punch -> Button 4 (Y)
                    "P1_BUTTON3": "JOYCODE_1_BUTTON1",  # Left Kick -> Button 1 (A)
                    "P1_BUTTON4": "JOYCODE_1_BUTTON2",  # Right Kick -> Button 2 (B)
                    "P2_BUTTON1": "JOYCODE_2_BUTTON3",
                    "P2_BUTTON2": "JOYCODE_2_BUTTON4",
                    "P2_BUTTON3": "JOYCODE_2_BUTTON1",
                    "P2_BUTTON4": "JOYCODE_2_BUTTON2",
                }
            },
            "tekkent": {
                "name": "Tekken Tag Layout",
                "description": "5-button Tekken layout (LP, RP, LK, RK, Tag)",
                "mappings": {
                    "P1_BUTTON1": "JOYCODE_1_BUTTON3",  # Left Punch -> Button 3 (X)
                    "P1_BUTTON2": "JOYCODE_1_BUTTON4",  # Right Punch -> Button 4 (Y)
                    "P1_BUTTON3": "JOYCODE_1_BUTTON6",  # Left Kick -> Button 6 (RB)
                    "P1_BUTTON4": "JOYCODE_1_BUTTON1",  # Right Kick -> Button 1 (A)
                    "P1_BUTTON5": "JOYCODE_1_BUTTON2",  # Tag -> Button 2 (B)
                    "P2_BUTTON1": "JOYCODE_2_BUTTON3",
                    "P2_BUTTON2": "JOYCODE_2_BUTTON4",
                    "P2_BUTTON3": "JOYCODE_2_BUTTON6",
                    "P2_BUTTON4": "JOYCODE_2_BUTTON1",
                    "P2_BUTTON5": "JOYCODE_2_BUTTON2",
                }
            }
        }
        
        # Store mapping presets for access by other methods
        self.mapping_presets = mapping_presets
        
        # Enhanced preset selection with custom layouts
        preset_frame = ctk.CTkFrame(presets_card, fg_color=self.theme_colors["background"], corner_radius=4)
        preset_frame.pack(fill="x", padx=15, pady=10)
        
        # Label for the dropdown
        ctk.CTkLabel(
            preset_frame,
            text="Select Fighting Game Layout:",
            font=("Arial", 13, "bold")
        ).pack(side="left", padx=10, pady=10)
        
        # Function to get all preset options including custom layouts
        def get_all_preset_options():
            """Get all available presets including custom layouts"""
            options = ["All Compatible Games"]
            
            # Add built-in presets
            for preset_id, preset_data in mapping_presets.items():
                options.append(preset_data["name"])
            
            # Add separator and custom layouts if they exist
            if main_app.custom_layouts:  # CHANGED: Use main_app
                options.append("--- Custom Layouts ---")
                for layout_id, layout_data in main_app.custom_layouts.items():  # CHANGED: Use main_app
                    options.append(f"Custom: {layout_data['name']}")
            
            return options
        
        # Create dropdown with all preset options
        preset_options = get_all_preset_options()
        preset_descriptions = {
            "All Compatible Games": "Automatically apply the best mapping to ALL compatible fighting games based on their type"
        }
        
        # Add descriptions for built-in presets
        for preset_id, preset_data in mapping_presets.items():
            preset_descriptions[preset_data["name"]] = preset_data["description"]
        
        # Add descriptions for custom layouts
        for layout_id, layout_data in self.custom_layouts.items():
            display_name = f"Custom: {layout_data['name']}"
            preset_descriptions[display_name] = layout_data.get('description', 'Custom layout')
        
        preset_var = tk.StringVar(value=preset_options[0])
        
        preset_dropdown = ctk.CTkComboBox(
            preset_frame,
            values=preset_options,
            variable=preset_var,
            command=lambda choice: update_preset_selection(choice),
            width=350,
            fg_color=self.theme_colors["card_bg"],
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"],
            dropdown_fg_color=self.theme_colors["card_bg"]
        )
        preset_dropdown.pack(side="left", padx=10, pady=10)
        
        # Store references for later use
        self.preset_var = preset_var
        self.preset_dropdown = preset_dropdown
        
        # Custom layout management buttons
        layout_buttons_frame = ctk.CTkFrame(preset_frame, fg_color="transparent")
        layout_buttons_frame.pack(side="left", padx=10, pady=10)
        
        def customize_current_layout():
            """Customize the currently selected layout"""
            selected = preset_var.get()
            
            # Skip separator items
            if selected.startswith("---"):
                messagebox.showinfo("Invalid Selection", "Please select a valid preset to customize.", parent=dialog)
                return
            
            if selected.startswith("Custom: "):
                # Editing existing custom layout
                custom_name = selected[8:]  # Remove "Custom: " prefix
                base_mappings = None
                base_preset = None
                
                for layout_id, layout_data in main_app.custom_layouts.items():  # CHANGED: Use main_app
                    if layout_data['name'] == custom_name:
                        base_mappings = layout_data['mappings']
                        base_preset = layout_data['base_preset']
                        break
                        
                if not base_mappings:
                    messagebox.showerror("Error", "Custom layout not found.", parent=dialog)
                    return
                    
            elif selected == "All Compatible Games":
                # For "All Compatible Games", let user pick a base layout
                messagebox.showinfo("Select Base Layout", "Please select a specific preset first, then customize it.", parent=dialog)
                return
            else:
                # Creating new custom layout from built-in preset
                base_preset = None
                for preset_id, preset_data in mapping_presets.items():
                    if preset_data["name"] == selected:
                        base_mappings = preset_data['mappings'].copy()
                        base_preset = preset_id
                        break
                
                if not base_preset:
                    messagebox.showwarning("Invalid Selection", "Please select a valid preset to customize.", parent=dialog)
                    return
            
            # Show customization dialog
            result = main_app.create_button_remapping_dialog(dialog, base_mappings, selected)  # CHANGED: Use main_app
            
            if not result["cancelled"]:
                # Get save details
                save_dialog = main_app.create_layout_save_dialog(dialog, selected.replace("Custom: ", ""))  # CHANGED: Use main_app
                if not save_dialog["cancelled"]:
                    # Save the custom layout
                    saved_path = main_app.save_custom_layout(  # CHANGED: Use main_app
                        save_dialog["name"],
                        result["mappings"],
                        base_preset,
                        save_dialog["description"]
                    )
                    
                    if saved_path:
                        # Refresh custom layouts
                        main_app.custom_layouts = main_app.load_custom_layouts()  # CHANGED: Use main_app
                        
                        # Update dropdown options
                        new_options = get_all_preset_options()
                        preset_dropdown.configure(values=new_options)
                        preset_var.set(f"Custom: {save_dialog['name']}")
                        
                        # Update descriptions
                        preset_descriptions[f"Custom: {save_dialog['name']}"] = save_dialog['description']
                        
                        messagebox.showinfo("Layout Saved", f"Custom layout '{save_dialog['name']}' saved successfully!", parent=dialog)
                        
                        # Refresh the UI
                        update_preset_selection(f"Custom: {save_dialog['name']}")
        
        def manage_custom_layouts():
            """Show dialog to manage (delete/rename) custom layouts"""
            if not main_app.custom_layouts:  # CHANGED: Use main_app
                messagebox.showinfo("No Custom Layouts", "No custom layouts found.", parent=dialog)
                return
            
            main_app.show_layout_manager_dialog(dialog)  # CHANGED: Use main_app
            
            # Refresh after managing
            main_app.custom_layouts = main_app.load_custom_layouts()  # CHANGED: Use main_app
            new_options = get_all_preset_options()
            preset_dropdown.configure(values=new_options)
            
            # Reset to first option if current selection was deleted
            current_selection = preset_var.get()
            if current_selection not in new_options:
                preset_var.set(new_options[0])
                update_preset_selection(new_options[0])
        
        # Add the management buttons
        ctk.CTkButton(
            layout_buttons_frame,
            text="Customize",
            command=customize_current_layout,
            width=100,
            height=35,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            layout_buttons_frame,
            text="Manage",
            command=manage_custom_layouts,
            width=90,
            height=35,
            fg_color=self.theme_colors["secondary"],
            hover_color=self.theme_colors["primary"]
        ).pack(side="left", padx=5)
        
        # Description label that updates based on selection
        description_label = ctk.CTkLabel(
            presets_card,
            text=preset_descriptions[preset_options[0]],
            font=("Arial", 12),
            text_color=self.theme_colors["text_dimmed"],
            wraplength=700,
            justify="left"
        )
        description_label.pack(padx=15, pady=(0, 15))
        
        # Game selection card
        games_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        games_card.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            games_card,
            text="Game Selection",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Function to get ALL games from ALL mappings for "All Compatible Games" option
        def get_all_compatible_games():
            """Get all fighting games with their appropriate mappings"""
            all_games = []
            game_mapping_assignments = {}
            
            # Process each mapping type
            for preset_id, preset_data in mapping_presets.items():
                if preset_id == "6button":
                    target_mappings = ["sf", "ki", "darkstalkers", "marvel", "capcom"]
                else:
                    target_mappings = [preset_id]
                
                # Find games for this mapping type
                for rom_name, rom_data in self.gamedata_json.items():
                    if rom_name in self.available_roms and 'mappings' in rom_data:
                        if any(mapping in rom_data['mappings'] for mapping in target_mappings):
                            if rom_name not in game_mapping_assignments:
                                game_name = rom_data.get('description', rom_name)
                                all_games.append((rom_name, game_name, False, preset_id))
                                game_mapping_assignments[rom_name] = preset_id
                                
                                # Add clones
                                if 'clones' in rom_data:
                                    for clone_rom, clone_data in rom_data['clones'].items():
                                        if clone_rom in self.available_roms and clone_rom not in game_mapping_assignments:
                                            clone_name = clone_data.get('description', f"{clone_rom} (Clone)")
                                            all_games.append((clone_rom, clone_name, True, preset_id))
                                            game_mapping_assignments[clone_rom] = preset_id
            
            return sorted(all_games, key=lambda x: x[1]), game_mapping_assignments
        
        # Find games with the selected mapping
        def get_games_for_mapping(mapping_type):
            """Get all games (including clones) that have the specified mapping AND exist in user's ROM folder"""
            games = []
            
            if mapping_type == "6button":
                target_mappings = ["sf", "ki", "darkstalkers", "marvel", "capcom"]
            else:
                target_mappings = [mapping_type]
            
            for rom_name, rom_data in self.gamedata_json.items():
                if rom_name in self.available_roms and 'mappings' in rom_data:
                    if any(mapping in rom_data['mappings'] for mapping in target_mappings):
                        game_name = rom_data.get('description', rom_name)
                        games.append((rom_name, game_name, False))
                        
                        # Add clones that the user also owns
                        if 'clones' in rom_data:
                            for clone_rom, clone_data in rom_data['clones'].items():
                                if clone_rom in self.available_roms:
                                    clone_name = clone_data.get('description', f"{clone_rom} (Clone)")
                                    games.append((clone_rom, clone_name, True))
            
            return sorted(games, key=lambda x: x[1])
        
        # Game list frame
        games_list_frame = ctk.CTkFrame(games_card, fg_color=self.theme_colors["background"], corner_radius=4)
        games_list_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # Create scrollable list for games
        games_listbox = tk.Listbox(
            games_list_frame,
            height=10,
            selectmode="extended",
            background=self.theme_colors["card_bg"],
            foreground=self.theme_colors["text"],
            font=("Arial", 11),
            activestyle="none",
            selectbackground=self.theme_colors["primary"],
            selectforeground="white"
        )
        games_listbox.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        # Scrollbar for games list
        games_scrollbar = ctk.CTkScrollbar(games_list_frame, orientation="vertical", command=games_listbox.yview)
        games_scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)
        games_listbox.configure(yscrollcommand=games_scrollbar.set)
        
        # Store games data for processing
        current_games = []
        game_mapping_assignments = {}
        
        # Function to update preset selection
        def update_preset_selection(choice):
            """Handle preset selection including custom layouts"""
            nonlocal current_games, game_mapping_assignments
            
            # Skip separator items
            if choice.startswith("---"):
                return
            
            # Update description label
            description_label.configure(text=preset_descriptions.get(choice, ""))
            
            # Clear the current list
            games_listbox.delete(0, tk.END)
            
            if choice == "All Compatible Games":
                # Show all compatible games from all presets
                games, game_assignments = get_all_compatible_games()
                
                # Group games by mapping type for display
                games_by_type = {}
                for rom_name, game_name, is_clone, preset_id in games:
                    preset_name = mapping_presets[preset_id]["name"]
                    if preset_name not in games_by_type:
                        games_by_type[preset_name] = []
                    games_by_type[preset_name].append((rom_name, game_name, is_clone, preset_id))
                
                # Add games grouped by type
                for preset_name, preset_games in games_by_type.items():
                    # Add header for this mapping type
                    games_listbox.insert(tk.END, f"--- {preset_name} ({len(preset_games)} games) ---")
                    games_listbox.itemconfig(tk.END, {'bg': self.theme_colors["primary"], 'fg': 'white'})
                    
                    # Add games for this type
                    for rom_name, game_name, is_clone, preset_id in preset_games:
                        display_text = f"  {rom_name} - {game_name}"
                        if is_clone:
                            display_text += " [Clone]"
                        games_listbox.insert(tk.END, display_text)
                
                # Select all game entries (not headers)
                for i in range(games_listbox.size()):
                    item_text = games_listbox.get(i)
                    if not item_text.startswith("---"):
                        games_listbox.selection_set(i)
                
                current_games = games
                game_mapping_assignments = game_assignments
                
            elif choice.startswith("Custom: "):
                # Handle custom layout selection
                custom_name = choice[8:]
                custom_layout = None
                
                for layout_id, layout_data in self.custom_layouts.items():
                    if layout_data['name'] == custom_name:
                        custom_layout = layout_data
                        break
                
                if custom_layout:
                    # Get the base preset to determine which games to show
                    base_preset = custom_layout['base_preset']
                    if base_preset in mapping_presets:
                        games = get_games_for_mapping(base_preset)
                        
                        for rom_name, game_name, is_clone in games:
                            display_text = f"{rom_name} - {game_name}"
                            if is_clone:
                                display_text += " [Clone]"
                            games_listbox.insert(tk.END, display_text)
                        
                        # Select all by default
                        games_listbox.select_set(0, tk.END)
                        
                        # Store games data with custom preset info
                        current_games = [(rom, name, clone, f"custom_{custom_name}") for rom, name, clone in games]
                        game_mapping_assignments = {rom: f"custom_{custom_name}" for rom, _, _ in games}
            else:
                # Single built-in preset mode
                selected_preset = None
                for preset_id, preset_data in mapping_presets.items():
                    if preset_data["name"] == choice:
                        selected_preset = preset_id
                        break
                
                if selected_preset:
                    games = get_games_for_mapping(selected_preset)
                    
                    for rom_name, game_name, is_clone in games:
                        display_text = f"{rom_name} - {game_name}"
                        if is_clone:
                            display_text += " [Clone]"
                        games_listbox.insert(tk.END, display_text)
                    
                    # Select all by default
                    games_listbox.select_set(0, tk.END)
                    
                    current_games = [(rom, name, clone, selected_preset) for rom, name, clone in games]
                    game_mapping_assignments = {rom: selected_preset for rom, _, _ in games}
        
        # Initial setup
        update_preset_selection(preset_options[0])
        
        # Selection buttons
        selection_frame = ctk.CTkFrame(games_card, fg_color="transparent")
        selection_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        def select_all_games():
            if preset_var.get() == "All Compatible Games":
                # Select all non-header items
                for i in range(games_listbox.size()):
                    item_text = games_listbox.get(i)
                    if not item_text.startswith("---"):
                        games_listbox.selection_set(i)
            else:
                games_listbox.select_set(0, tk.END)
        
        def deselect_all_games():
            games_listbox.select_clear(0, tk.END)
        
        ctk.CTkButton(
            selection_frame,
            text="Select All",
            command=select_all_games,
            width=100,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            selection_frame,
            text="Deselect All", 
            command=deselect_all_games,
            width=100,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).pack(side="left", padx=5)
        
        # Rest of your existing code (Options card, Status area, etc.)
        # Options card
        options_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        options_card.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            options_card,
            text="Configuration Options",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # MAME Version toggle
        mame_version_frame = ctk.CTkFrame(options_card, fg_color="transparent")
        mame_version_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        mame_version_var = tk.StringVar(value="new")
        
        ctk.CTkLabel(
            mame_version_frame,
            text="MAME Version Compatibility:",
            font=("Arial", 13, "bold")
        ).pack(side="left", padx=0, pady=5)
        
        mame_new_radio = ctk.CTkRadioButton(
            mame_version_frame,
            text="New MAME (0.250+)",
            variable=mame_version_var,
            value="new",
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        mame_new_radio.pack(side="left", padx=15, pady=5)
        
        mame_old_radio = ctk.CTkRadioButton(
            mame_version_frame,
            text="Old MAME (0.249-)",
            variable=mame_version_var,
            value="old",
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        mame_old_radio.pack(side="left", padx=15, pady=5)
        
        # Version info label
        version_info_label = ctk.CTkLabel(
            options_card,
            text="New MAME uses SLIDER2, Old MAME uses ZAXIS for analog controls",
            font=("Arial", 11),
            text_color=self.theme_colors["text_dimmed"]
        )
        version_info_label.pack(padx=15, pady=(0, 10))
        
        # Other options checkboxes
        options_frame = ctk.CTkFrame(options_card, fg_color="transparent")
        options_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        backup_cfg_var = tk.BooleanVar(value=True)
        create_missing_var = tk.BooleanVar(value=True)
        update_existing_var = tk.BooleanVar(value=True)
        
        ctk.CTkCheckBox(
            options_frame,
            text="Backup existing CFG files before modifying",
            variable=backup_cfg_var,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        ).pack(anchor="w", pady=2)
        
        ctk.CTkCheckBox(
            options_frame,
            text="Create missing button entries in CFG files",
            variable=create_missing_var,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        ).pack(anchor="w", pady=2)
        
        ctk.CTkCheckBox(
            options_frame,
            text="Update existing button mappings",
            variable=update_existing_var,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        ).pack(anchor="w", pady=2)
        
        # Status area
        status_frame = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        status_frame.pack(fill="x", padx=0, pady=(0, 15))
        
        status_text = ctk.CTkTextbox(
            status_frame,
            height=100,
            font=("Consolas", 11),
            fg_color=self.theme_colors["background"]
        )
        status_text.pack(fill="x", padx=15, pady=15)
        status_text.insert("1.0", "Ready to configure fightstick mappings...")
        
        # Enhanced apply function that handles custom layouts
        def apply_fightstick_mappings():
            """Apply the selected fightstick mappings to selected games"""
            try:
                selected_display_name = preset_var.get()
                selected_indices = games_listbox.curselection()
                
                if not selected_indices:
                    messagebox.showwarning("No Games Selected", "Please select at least one game to configure.", parent=dialog)
                    return
                
                # Build list of games to process
                games_to_process = []
                
                if selected_display_name == "All Compatible Games":
                    # Process with individual mappings per game
                    listbox_index = 0
                    for rom_name, game_name, is_clone, preset_id in current_games:
                        # Skip headers in the listbox
                        while listbox_index < games_listbox.size():
                            if not games_listbox.get(listbox_index).startswith("---"):
                                break
                            listbox_index += 1
                        
                        # Check if this game is selected
                        if listbox_index in selected_indices:
                            if preset_id.startswith("custom_"):
                                preset_name = f"Custom: {preset_id[7:]}"  # Remove "custom_" prefix
                            else:
                                preset_name = mapping_presets[preset_id]["name"]
                            
                            games_to_process.append({
                                'rom_name': rom_name,
                                'preset_id': preset_id,
                                'preset_name': preset_name
                            })
                        
                        listbox_index += 1
                        
                elif selected_display_name.startswith("Custom: "):
                    # Custom layout mode
                    custom_name = selected_display_name[8:]
                    custom_layout = None
                    
                    for layout_id, layout_data in main_app.custom_layouts.items():  # CHANGED: Use main_app
                        if layout_data['name'] == custom_name:
                            custom_layout = layout_data
                            break
                    
                    if not custom_layout:
                        messagebox.showerror("Error", "Custom layout not found.", parent=dialog)
                        return
                    
                    # Get selected games
                    for index in selected_indices:
                        if index < len(current_games):
                            rom_name = current_games[index][0]
                            games_to_process.append({
                                'rom_name': rom_name,
                                'preset_id': f"custom_{custom_name}",
                                'preset_name': f"Custom: {custom_name}"
                            })
                else:
                    # Single built-in preset mode
                    selected_preset = None
                    for preset_id, preset_data in mapping_presets.items():
                        if preset_data["name"] == selected_display_name:
                            selected_preset = preset_id
                            break
                    
                    if not selected_preset:
                        messagebox.showerror("Error", "No valid preset selected.", parent=dialog)
                        return
                    
                    # Get selected games
                    for index in selected_indices:
                        if index < len(current_games):
                            rom_name = current_games[index][0]
                            games_to_process.append({
                                'rom_name': rom_name,
                                'preset_id': selected_preset,
                                'preset_name': mapping_presets[selected_preset]["name"]
                            })
                
                if not games_to_process:
                    messagebox.showwarning("No Games Selected", "Please select at least one game to configure.", parent=dialog)
                    return
                
                # Show confirmation
                if len(set(game['preset_name'] for game in games_to_process)) > 1:
                    # Multiple preset types
                    preset_counts = {}
                    for game in games_to_process:
                        preset_name = game['preset_name']
                        preset_counts[preset_name] = preset_counts.get(preset_name, 0) + 1
                    
                    preset_summary = []
                    for preset_name, count in preset_counts.items():
                        preset_summary.append(f"• {preset_name}: {count} games")
                    
                    confirmation_msg = (
                        f"Apply fightstick mappings to {len(games_to_process)} games?\n\n"
                        f"Mappings to be applied:\n" + "\n".join(preset_summary) + "\n\n"
                        f"This will modify CFG files in your MAME cfg directory."
                    )
                else:
                    # Single preset type
                    preset_name = games_to_process[0]['preset_name']
                    confirmation_msg = (
                        f"Apply {preset_name} to {len(games_to_process)} games?\n\n"
                        f"This will modify CFG files in your MAME cfg directory."
                    )
                
                if not messagebox.askyesno("Confirm Configuration", confirmation_msg, parent=dialog):
                    return
                
                # Clear status
                status_text.delete("1.0", tk.END)
                status_text.insert("1.0", f"Configuring {len(games_to_process)} games...\n\n")
                dialog.update_idletasks()
                
                processed_count = 0
                error_count = 0
                
                # Process each selected game with its appropriate mapping
                for game_info in games_to_process:
                    try:
                        rom_name = game_info['rom_name']
                        preset_id = game_info['preset_id']
                        preset_name = game_info['preset_name']
                        
                        # Get the mappings for this specific preset
                        if preset_id.startswith("custom_"):
                            # Use custom layout mappings
                            custom_name = preset_id[7:]  # Remove "custom_" prefix
                            custom_layout = None
                            
                            for layout_id, layout_data in main_app.custom_layouts.items():  # CHANGED: Use main_app
                                if layout_data['name'] == custom_name:
                                    custom_layout = layout_data
                                    break
                            
                            if custom_layout:
                                button_mappings = custom_layout['mappings']
                            else:
                                raise Exception(f"Custom layout '{custom_name}' not found")
                        else:
                            # Use built-in preset mappings
                            button_mappings = mapping_presets[preset_id]['mappings']
                        
                        # CRITICAL FIX: Use main_app instead of self
                        result = main_app.configure_game_fightstick_mapping(
                            rom_name, 
                            button_mappings,
                            backup_cfg_var.get(),
                            create_missing_var.get(),
                            update_existing_var.get(),
                            mame_version_var.get()
                        )
                        
                        if result['success']:
                            status_text.insert(tk.END, f"✓ {rom_name} ({preset_name}): {result['message']}\n")
                            processed_count += 1
                        else:
                            status_text.insert(tk.END, f"✗ {rom_name}: {result['message']}\n")
                            error_count += 1
                            
                    except Exception as e:
                        status_text.insert(tk.END, f"✗ {rom_name}: Error - {str(e)}\n")
                        error_count += 1
                    
                    status_text.see(tk.END)
                    dialog.update_idletasks()
                
                # Summary
                status_text.insert(tk.END, f"\nCompleted: {processed_count} successful, {error_count} errors")
                status_text.see(tk.END)
                
                # Show completion message
                completion_msg = (
                    f"Processed {processed_count} games successfully.\n"
                    f"Errors: {error_count}"
                )
                
                messagebox.showinfo("Configuration Complete", completion_msg, parent=dialog)
                
            except Exception as e:
                status_text.insert(tk.END, f"\nFATAL ERROR: {str(e)}")
                messagebox.showerror("Error", f"Failed to apply mappings: {str(e)}", parent=dialog)
        
        # Bottom buttons
        buttons_frame = ctk.CTkFrame(dialog, height=70, fg_color=self.theme_colors["card_bg"], corner_radius=0)
        buttons_frame.pack(fill="x", side="bottom", padx=0, pady=0)
        buttons_frame.pack_propagate(False)
        
        button_container = ctk.CTkFrame(buttons_frame, fg_color="transparent")
        button_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Apply button
        apply_button = ctk.CTkButton(
            button_container,
            text="Apply Mappings",
            command=apply_fightstick_mappings,
            width=150,
            height=40,
            fg_color=self.theme_colors["success"],
            hover_color="#218838",
            font=("Arial", 14, "bold")
        )
        apply_button.pack(side="right", padx=5)
        
        # Close button
        ctk.CTkButton(
            button_container,
            text="Close",
            command=dialog.destroy,
            width=120,
            height=40,
            fg_color=self.theme_colors["danger"],
            hover_color="#c82333",
            font=("Arial", 14)
        ).pack(side="right", padx=5)
        
        # Center dialog
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height() 
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')

    # ====================================================================
    # ADDITIONAL HELPER METHODS (keep your existing ones and add these)
    # ====================================================================

    def add_formatted_port_to_input(self, input_elem, port_data):
        """Add a properly formatted port element to input"""
        import xml.etree.ElementTree as ET
        
        # Create the port element
        port = ET.SubElement(input_elem, "port")
        port.set("tag", port_data['tag'])
        port.set("type", port_data['type']) 
        port.set("mask", port_data['mask'])
        port.set("defvalue", port_data['defvalue'])
        
        # Create newseq element
        newseq = ET.SubElement(port, "newseq")
        newseq.set("type", "standard")
        newseq.text = port_data['newseq']
        
        return port

    def save_formatted_cfg(self, tree, cfg_path):
        """Save CFG file with exact MAME formatting - multiline newseq style"""
        import xml.etree.ElementTree as ET
        
        # Build the formatted XML string manually
        root = tree.getroot()
        
        lines = [
            '<?xml version="1.0"?>',
            '<!-- This file is autogenerated; comments and unknown tags will be stripped -->'
        ]
        
        def format_element(elem, indent_level=0):
            """Recursively format elements with proper MAME-style indentation"""
            indent = "    " * indent_level
            result_lines = []
            
            # Opening tag with attributes
            tag_line = f"{indent}<{elem.tag}"
            for key, value in elem.attrib.items():
                tag_line += f' {key}="{value}"'
            tag_line += ">"
            result_lines.append(tag_line)
            
            # Handle special formatting for newseq elements
            if elem.tag == "newseq" and elem.text and elem.text.strip():
                # Multi-line format for newseq
                result_lines.append(f"{indent}    {elem.text.strip()}")
                result_lines.append(f"{indent}</{elem.tag}>")
            elif len(elem) > 0:
                # Has child elements
                for child in elem:
                    child_lines = format_element(child, indent_level + 1)
                    result_lines.extend(child_lines)
                result_lines.append(f"{indent}</{elem.tag}>")
            elif elem.text and elem.text.strip():
                # Has text content but no children
                result_lines[-1] = result_lines[-1][:-1] + f">{elem.text.strip()}</{elem.tag}>"
            else:
                # Self-closing or empty element
                if elem.tag in ["coins"]:
                    result_lines[-1] = result_lines[-1][:-1] + " />"
                else:
                    result_lines.append(f"{indent}</{elem.tag}>")
            
            return result_lines
        
        # Format the entire tree
        formatted_lines = format_element(root)
        lines.extend(formatted_lines)
        
        # Write to file
        with open(cfg_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            f.write('\n')

    def create_new_cfg_structure(self, rom_name):
        """Create a new CFG XML structure"""
        import xml.etree.ElementTree as ET
        root = ET.Element("mameconfig", version="10")
        ET.SubElement(root, "system", name=rom_name)
        return root

if __name__ == "__main__":
    try:
        app = MAMEControlConfig()
        app.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
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
from mame_utils import (
    get_application_path, 
    get_mame_parent_dir, 
    find_file_in_standard_locations
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

        # Add panel proportion configuration here
        self.LEFT_PANEL_RATIO = 0.35  # Left panel takes 35% of window width
        self.MIN_LEFT_PANEL_WIDTH = 400  # Minimum width in pixels
        
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
        """Load essential data synchronously"""
        try:
            # Update message
            self.update_splash_message("Scanning ROMs directory...")
            
            # Scan ROMs directory
            self.scan_roms_directory()
            
            # Update message
            self.update_splash_message("Updating game list...")
            
            # Update the game list
            if hasattr(self, 'game_listbox'):
                self.update_game_list_by_category()
            
            # Update stats
            self.update_stats_label()
            
            # Select first ROM
            self.select_first_rom()
            
            # Schedule secondary data loading
            self.after(100, self._load_secondary_data)
        except Exception as e:
            traceback.print_exc()
            self.update_splash_message(f"Error: {str(e)}")
            
            # Still try to continue
            self.after(1000, self._load_secondary_data)

    def _load_secondary_data(self):
        """Start asynchronous loading of secondary data"""
        self.update_splash_message("Loading additional data...")
        
        # Add tasks to async loader
        self.async_loader.add_task(self.load_default_config)
        self.async_loader.add_task(self.load_custom_configs)
        
        # Check if database needs to be built/updated
        self.async_loader.add_task(self.check_and_build_db_if_needed)
        
        # Process results and check if loading is complete
        self.after(100, self._check_loading_progress)

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
        if self.check_db_update_needed():
            print("Database needs updating, rebuilding...")
            self.load_gamedata_json()
            return self.build_gamedata_db()
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
        """Clean old cache files to prevent unlimited growth"""
        # Load settings if not provided
        if max_age_days is None:
            if not hasattr(self, 'cache_max_age'):
                self.load_cache_settings()
            max_age_days = self.cache_max_age
            
        if max_files is None:
            if not hasattr(self, 'cache_max_files'):
                self.load_cache_settings()
            max_files = self.cache_max_files
            
        # Skip cleanup if auto-cleanup is disabled
        if hasattr(self, 'cache_auto_cleanup') and not self.cache_auto_cleanup:
            print("Automatic cache cleanup is disabled")
            return
            
        try:
            # Skip if directory doesn't exist
            if not os.path.exists(self.cache_dir):
                print("No cache directory found. Skipping cleanup.")
                return
                
            # Get all cache files with their modification times
            cache_files = []
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('_cache.json'):
                    filepath = os.path.join(self.cache_dir, filename)
                    mtime = os.path.getmtime(filepath)
                    cache_files.append((filepath, mtime))
            
            if not cache_files:
                print("No cache files found. Skipping cleanup.")
                return
            
            # If we have more than max_files, remove oldest files
            if len(cache_files) > max_files:
                # Sort by modification time (oldest first)
                cache_files.sort(key=lambda x: x[1])
                # Delete oldest files beyond our limit
                files_to_remove = cache_files[:(len(cache_files) - max_files)]
                for filepath, _ in files_to_remove:
                    try:
                        os.remove(filepath)
                        print(f"Removed old cache file: {os.path.basename(filepath)}")
                    except Exception as e:
                        print(f"Error removing {os.path.basename(filepath)}: {e}")
                        
            # Remove any files older than max_age_days
            cutoff_time = time.time() - (max_age_days * 86400)  # 86400 seconds in a day
            for filepath, mtime in cache_files:
                if mtime < cutoff_time:
                    try:
                        os.remove(filepath)
                        print(f"Removed expired cache file: {os.path.basename(filepath)}")
                    except Exception as e:
                        print(f"Error removing {os.path.basename(filepath)}: {e}")
                        
            print(f"Cache cleanup complete. Directory: {self.cache_dir}")
        except Exception as e:
            print(f"Error cleaning cache: {e}")
    
    # Replace your clear_cache function with this enhanced version
    def clear_cache(self):
        """Show cache management dialog with options to clear cache and configure settings"""
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
            
            # Buttons section
            buttons_frame = ctk.CTkFrame(frame, fg_color="transparent")
            buttons_frame.pack(pady=20)
            
            # Clear all button
            ctk.CTkButton(
                buttons_frame, 
                text="Clear All Cache", 
                command=lambda: self.perform_cache_clear(dialog, all_files=True)
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

    def perform_cache_clear(self, dialog=None, all_files=True, rom_name=None):
        """Perform the actual cache clearing operation"""
        try:
            cache_dir = os.path.join(self.preview_dir, "cache")
            if not os.path.exists(cache_dir):
                if dialog:
                    messagebox.showinfo("Info", "No cache directory found.", parent=dialog)
                return False
            
            if all_files:
                # Clear all cache files
                deleted_count = 0
                for filename in os.listdir(cache_dir):
                    if filename.endswith('_cache.json'):
                        try:
                            os.remove(os.path.join(cache_dir, filename))
                            deleted_count += 1
                        except Exception as e:
                            print(f"Error deleting {filename}: {e}")
                
                # Also clear memory cache
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache = {}
                    
                if dialog:
                    messagebox.showinfo("Cache Cleared", 
                                    f"Successfully deleted {deleted_count} cache files.", parent=dialog)
                print(f"Cleared all cache files: {deleted_count} files deleted")
                return deleted_count > 0
            elif rom_name:
                # Clear cache for specific ROM
                cache_file = os.path.join(cache_dir, f"{rom_name}_cache.json")
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    print(f"Cleared cache for ROM: {rom_name}")
                    
                    # Also clear from memory cache if it exists
                    if hasattr(self, 'rom_data_cache') and rom_name in self.rom_data_cache:
                        del self.rom_data_cache[rom_name]
                        print(f"Cleared memory cache for ROM: {rom_name}")
                    return True
                else:
                    print(f"No cache file found for ROM: {rom_name}")
                    return False
            
            return False
        except Exception as e:
            print(f"Error clearing cache: {e}")
            if dialog:
                messagebox.showerror("Error", f"Failed to clear cache: {str(e)}", parent=dialog)
            return False
    
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
                self.clean_cache_directory(max_age_days=self.cache_max_age, max_files=self.cache_max_files)
            
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
        
    def load_custom_configs(self):
        """Load custom configurations from cfg directory"""
        cfg_dir = os.path.join(self.mame_dir, "cfg")
        if not os.path.exists(cfg_dir):
            print(f"Config directory not found: {cfg_dir}")
            return

        for filename in os.listdir(cfg_dir):
            if filename.endswith(".cfg"):
                game_name = filename[:-4]
                full_path = os.path.join(cfg_dir, filename)
                try:
                    # Read as binary first to handle BOM
                    with open(full_path, "rb") as f:
                        content = f.read()
                    # Decode with UTF-8-SIG to handle BOM
                    self.custom_configs[game_name] = content.decode('utf-8-sig')
                except Exception as e:
                    print(f"Error loading {filename}: {e}")

        print(f"Loaded {len(self.custom_configs)} custom configurations")
    
    def parse_cfg_controls(self, cfg_content: str) -> Dict[str, str]:
        """Parse MAME cfg file to extract control mappings with support for increment/decrement pairs"""
        controls = {}
        try:
            import xml.etree.ElementTree as ET
            from io import StringIO

            print(f"Parsing CFG content of length: {len(cfg_content)}")

            # Always use xinput mode for parsing
            mapping_mode = 'xinput'
            print(f"Using mapping mode: {mapping_mode} for parsing CFG")

            # Mapping extractor - revised to prioritize XInput
            def get_preferred_mapping(mapping_str: str) -> str:
                if not mapping_str:
                    return "NONE"
                    
                # For multiple options (separated by OR)
                if "OR" in mapping_str:
                    parts = [p.strip() for p in mapping_str.strip().split("OR")]
                    
                    # Always prioritize XINPUT first, then JOYCODE
                    for part in parts:
                        if "XINPUT" in part:
                            return part
                    for part in parts:
                        if "JOYCODE" in part:
                            # Convert JOYCODE to XINPUT if possible
                            xinput_mapping = self.convert_mapping(part, 'xinput')
                            if xinput_mapping.startswith("XINPUT"):
                                return xinput_mapping
                            return part
                            
                    # If no matching part, return the first one
                    return parts[0]
                else:
                    # Single mapping, return as is or convert if needed
                    if "XINPUT" in mapping_str:
                        return mapping_str.strip()
                    elif "JOYCODE" in mapping_str:
                        # Try to convert to XInput
                        xinput_mapping = self.convert_mapping(mapping_str.strip(), 'xinput')
                        if xinput_mapping.startswith("XINPUT"):
                            return xinput_mapping
                    return mapping_str.strip()

            # Parse the XML content
            parser = ET.XMLParser(encoding='utf-8')
            tree = ET.parse(StringIO(cfg_content), parser=parser)
            root = tree.getroot()

            # Find all port elements under input
            input_elem = root.find('.//input')
            if input_elem is not None:
                # Debug - count total ports
                all_ports = input_elem.findall('port')
                print(f"Found {len(all_ports)} total ports in config")

                # DEBUG: Print ALL port types found
                print("=== ALL PORT TYPES FOUND ===")
                for port in all_ports:
                    control_type = port.get('type')
                    if control_type:
                        print(f"Port type: {control_type}")
                print("=== END PORT TYPES ===")

                # Process all port elements regardless of type
                for port in all_ports:
                    control_type = port.get('type')
                    if control_type:  # Any control type
                        
                        # DEBUG: Print detailed info for paddle-related controls
                        if "PADDLE" in control_type.upper() or "STEER" in control_type.upper():
                            print(f"=== PADDLE/STEERING CONTROL FOUND ===")
                            print(f"Control type: {control_type}")
                            
                            # Print all sequences for this control
                            all_sequences = port.findall('./newseq')
                            for seq in all_sequences:
                                seq_type = seq.get('type', 'unknown')
                                seq_text = seq.text if seq.text else "None"
                                print(f"  Sequence type: {seq_type}, text: {seq_text}")
                            print("=== END PADDLE/STEERING INFO ===")
                        
                        # Special handling for directional controls that might use increment/decrement
                        special_control = any(substr in control_type for substr in 
                                            ["PADDLE", "DIAL", "TRACKBALL", "MOUSE", "LIGHTGUN", 
                                            "AD_STICK", "PEDAL", "POSITIONAL", "GAMBLE", "STEER"])

                        if special_control:
                            # Look for increment and decrement sequences
                            inc_newseq = port.find('./newseq[@type="increment"]')
                            dec_newseq = port.find('./newseq[@type="decrement"]')
                            std_newseq = port.find('./newseq[@type="standard"]')

                            mapping_found = False

                            # FIXED: Handle case where only increment exists
                            if inc_newseq is not None and inc_newseq.text and inc_newseq.text.strip() != "NONE":
                                if (dec_newseq is None or not dec_newseq.text or dec_newseq.text.strip() == "NONE"):
                                    inc_mapping = get_preferred_mapping(inc_newseq.text.strip())
                                    controls[control_type] = inc_mapping
                                    print(f"Found increment-only mapping: {control_type} -> {inc_mapping}")
                                    mapping_found = True
                                elif dec_newseq is not None and dec_newseq.text and dec_newseq.text.strip() != "NONE":
                                    inc_mapping = get_preferred_mapping(inc_newseq.text.strip())
                                    dec_mapping = get_preferred_mapping(dec_newseq.text.strip())
                                    combined_mapping = f"{inc_mapping} ||| {dec_mapping}"
                                    controls[control_type] = combined_mapping
                                    print(f"Found directional mapping: {control_type} -> {combined_mapping}")
                                    mapping_found = True
                            elif dec_newseq is not None and dec_newseq.text and dec_newseq.text.strip() != "NONE":
                                dec_mapping = get_preferred_mapping(dec_newseq.text.strip())
                                controls[control_type] = dec_mapping
                                print(f"Found decrement-only mapping: {control_type} -> {dec_mapping}")
                                mapping_found = True
                            elif std_newseq is not None and std_newseq.text and std_newseq.text.strip() != "NONE":
                                mapping = get_preferred_mapping(std_newseq.text.strip())
                                controls[control_type] = mapping
                                print(f"Found standard mapping for special control: {control_type} -> {mapping}")
                                mapping_found = True

                            # If no standard mapping types found, look for any other sequence
                            if not mapping_found:
                                all_sequences = port.findall('./newseq')
                                for seq in all_sequences:
                                    seq_type = seq.get('type', 'unknown')
                                    if seq.text and seq.text.strip() != "NONE":
                                        mapping = get_preferred_mapping(seq.text.strip())
                                        controls[control_type] = mapping
                                        print(f"Found {seq_type} sequence mapping for {control_type} -> {mapping}")
                                        mapping_found = True
                                        break  # Use the first valid mapping found
                                
                                if not mapping_found:
                                    print(f"WARNING: No mapping found for special control: {control_type}")
                        else:
                            # Regular handling for standard sequence (non-special controls)
                            newseq = port.find('./newseq[@type="standard"]')
                            if newseq is not None and newseq.text and newseq.text.strip() != "NONE":
                                mapping = get_preferred_mapping(newseq.text.strip())
                                controls[control_type] = mapping
                                print(f"Found standard mapping: {control_type} -> {mapping}")
            else:
                print("No input element found in XML")

            # DEBUG: Create potential mappings for common paddle control names
            paddle_aliases = {
                "P1_PADDLE": None,
                "PADDLE": None,
                "PADDLE_1": None,
                "P1_STEER": None,
                "STEERING": None,
                "STEERING_1": None
            }
            
            print("=== CHECKING FOR PADDLE ALIASES ===")
            for control_name in controls.keys():
                for alias in paddle_aliases.keys():
                    if alias.lower() in control_name.lower() or control_name.lower() in alias.lower():
                        print(f"Potential paddle alias found: {control_name} might be {alias}")
                        # If we found a paddle-like control but P1_PADDLE doesn't exist, create the mapping
                        if "P1_PADDLE" not in controls and ("PADDLE" in control_name.upper() or "STEER" in control_name.upper()):
                            controls["P1_PADDLE"] = controls[control_name]
                            print(f"Created P1_PADDLE mapping from {control_name}: {controls[control_name]}")

        except ET.ParseError as e:
            print(f"XML parsing failed with error: {str(e)}")
            print("First 100 chars of content:", repr(cfg_content[:100]))
        except Exception as e:
            print(f"Unexpected error parsing cfg: {str(e)}")

        print(f"Found {len(controls)} control mappings")
        if controls:
            print("All mappings found:")
            for k, v in controls.items():
                print(f"  {k}: {v}")

        return controls

    def load_default_config(self):
        """Load the default MAME control configuration"""
        # Look in the cfg directory
        cfg_dir = os.path.join(self.mame_dir, "cfg")
        default_cfg_path = os.path.join(cfg_dir, "default.cfg")
        
        print(f"Looking for default.cfg at: {default_cfg_path}")
        if os.path.exists(default_cfg_path):
            try:
                print(f"Loading default config from: {default_cfg_path}")
                # Read file content
                with open(default_cfg_path, "rb") as f:
                    content = f.read()
                
                # Parse the default mappings using the enhanced parser
                self.default_controls = self.parse_default_cfg(content.decode('utf-8-sig'))
                
                # DEBUG: Print sample mappings
                print(f"Loaded {len(self.default_controls)} default control mappings")
                for i, (k, v) in enumerate(list(self.default_controls.items())[:5]):
                    print(f"  Sample {i+1}: {k} -> {v}")
                    
                return True
            except Exception as e:
                print(f"Error loading default config: {e}")
                import traceback
                traceback.print_exc()
                self.default_controls = {}
                return False
        else:
            print("No default.cfg found in cfg directory")
            self.default_controls = {}
            return False

    def parse_default_cfg(self, cfg_content):
        """Parse default.cfg to extract all control mappings focusing on XInput format"""
        controls = {}
        try:
            import xml.etree.ElementTree as ET
            from io import StringIO

            def get_preferred_mapping(mapping_str: str) -> str:
                if not mapping_str:
                    return "NONE"
                parts = [p.strip() for p in mapping_str.strip().split("OR")]
                for part in parts:
                    if "XINPUT" in part:
                        return part
                for part in parts:
                    if "JOYCODE" in part:
                        xinput = self.convert_mapping(part, "xinput")
                        return xinput if xinput.startswith("XINPUT") else part
                return parts[0] if parts else mapping_str.strip()

            tree = ET.parse(StringIO(cfg_content), ET.XMLParser(encoding='utf-8'))
            root = tree.getroot()
            input_elem = root.find('.//input')

            if input_elem is not None:
                for port in input_elem.findall('port'):
                    ctype = port.get('type')
                    if not ctype:
                        continue

                    std = port.find('./newseq[@type="standard"]')
                    inc = port.find('./newseq[@type="increment"]')
                    dec = port.find('./newseq[@type="decrement"]')

                    if inc is not None and dec is not None and inc.text and dec.text:
                        inc_map = get_preferred_mapping(inc.text.strip())
                        dec_map = get_preferred_mapping(dec.text.strip())
                        controls[ctype] = f"{inc_map} ||| {dec_map}"
                    elif inc is not None and inc.text:
                        controls[ctype] = get_preferred_mapping(inc.text.strip())
                    elif dec is not None and dec.text:
                        controls[ctype] = get_preferred_mapping(dec.text.strip())
                    elif std is not None and std.text:
                        controls[ctype] = get_preferred_mapping(std.text.strip())
        except Exception as e:
            print(f"Error parsing default.cfg: {e}")
        return controls


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
                hover_color=self.theme_colors["button_hover"],
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
                text="Restart App",
                command=self.restart_application,
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
        """Restart the application"""
        try:
            
            # Save current settings before restart
            self.save_settings()
            
            # Clean shutdown
            self.cleanup_before_exit()
            
            # Restart the application
            import subprocess
            import sys
            
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                subprocess.Popen([sys.executable] + sys.argv[1:])
            else:
                # Running as script
                subprocess.Popen([sys.executable] + sys.argv)
            
            # Exit current instance
            self.destroy()
            sys.exit(0)
                
        except Exception as e:
            messagebox.showerror("Restart Error", f"Failed to restart application:\n{str(e)}")

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
            text="All ROMs",
            command=lambda: set_tab_active("all")
        )
        self.sidebar_tabs["all"].pack(fill="x", padx=5, pady=2)
        
        # Add "With Controls" tab
        self.sidebar_tabs["with_controls"] = CustomSidebarTab(
            tabs_frame, 
            text="With Controls",
            command=lambda: set_tab_active("with_controls")
        )
        self.sidebar_tabs["with_controls"].pack(fill="x", padx=5, pady=2)
        
        # Add "Generic Controls" tab
        self.sidebar_tabs["generic"] = CustomSidebarTab(
            tabs_frame, 
            text="Generic Controls",
            command=lambda: set_tab_active("generic")
        )
        self.sidebar_tabs["generic"].pack(fill="x", padx=5, pady=2)
        
        # Add "Missing Controls" tab
        self.sidebar_tabs["missing"] = CustomSidebarTab(
            tabs_frame, 
            text="Missing Controls",
            command=lambda: set_tab_active("missing")
        )
        self.sidebar_tabs["missing"].pack(fill="x", padx=5, pady=2)
        
        # Add "Custom Config" tab
        self.sidebar_tabs["custom_config"] = CustomSidebarTab(
            tabs_frame, 
            text="With Custom Config",
            command=lambda: set_tab_active("custom_config")
        )
        self.sidebar_tabs["custom_config"].pack(fill="x", padx=5, pady=2)
        
        # Add "Clone ROMs" tab
        self.sidebar_tabs["clones"] = CustomSidebarTab(
            tabs_frame, 
            text="Clone ROMs",
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
        
        # Stats label in the status frame
        self.stats_label = ctk.CTkLabel(
            self.status_frame, 
            text="Loading...",
            font=("Arial", 12), 
            text_color=self.theme_colors["text"],
            justify="left",
            anchor="w"
        )
        self.stats_label.pack(padx=10, pady=10, fill="both", expand=True)
        
        # Set initial active tab - but don't call update_game_list_by_category yet
        # (this will happen during load_all_data)
        self.sidebar_tabs["all"].set_active(True)
        self.current_view = "all"

    def create_top_bar(self):
        """Create top bar with control buttons"""
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
        
        # CHANGED ORDER: The packing order is reversed to get correct right-to-left appearance
        
        self.preview_button = ctk.CTkButton(
            toggle_frame,
            text="Preview Controls",
            command=self.show_preview,
            fg_color=self.theme_colors["success"],  # Changed from primary to success (green)
            hover_color="#218838",  # Darker green for hover
            height=32
        )
        self.preview_button.pack(side="right", padx=10)
        
        # 3. Hide buttons toggle (will appear to the left of XInput only toggle)
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
        """Handle game selection from listbox with improved stability"""
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
                
                # After setting self.current_game, update toolbar
                if hasattr(self, 'update_toolbar_status'):
                    self.update_toolbar_status()

                # Store selected line (for compatibility)
                self.selected_line = index + 1  # 1-indexed for backward compatibility
                
                # Clear cache entry to force refresh with current input mode
                if hasattr(self, 'rom_data_cache') and rom_name in self.rom_data_cache:
                    del self.rom_data_cache[rom_name]
                
                # Update the display with a slight delay to prevent UI conflicts
                # Use the current input mode
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
            # Remove common prefixes that might be part of the display format but not the actual ROM name
            if rom_name.startswith("* "):
                rom_name = rom_name[2:]
            if rom_name.startswith("+ ") or rom_name.startswith("- "):
                rom_name = rom_name[2:]
                
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

    def update_game_list_by_category(self):
        """Update game list based on current sidebar category selection with enhanced filtering options"""
        # Remember currently selected ROM if any
        previously_selected_rom = self.current_game if hasattr(self, 'current_game') else None
        
        # Get all ROMs
        available_roms = sorted(self.available_roms)
        
        # Prepare lists for different categories
        with_controls = []
        missing_controls = []
        with_custom_config = []
        generic_controls = []
        clone_roms = []  # List for clone ROMs
        
        # NEW CATEGORIES
        no_buttons_roms = []    # ROMs with controls but no buttons
        specialized_roms = []   # ROMs with specialized inputs (trackball, lightgun, etc.)
        analog_roms = []        # ROMs with analog controls
        multiplayer_roms = []   # ROMs with more than 1 player
        singleplayer_roms = []  # ROMs with exactly 1 player
        
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
                        clone_roms.append(clone_rom)  # Add to our clones list
        
        # Process and categorize ROMs
        for rom in available_roms:
            # Check if ROM is a clone (if not already identified)
            if rom not in clone_roms and rom in self.parent_lookup:
                clone_roms.append(rom)
                
            # Check if ROM has custom config
            has_custom = rom in self.custom_configs
            if has_custom:
                with_custom_config.append(rom)
            
            # Check if ROM has control data
            game_data = self.get_game_data(rom)
            if game_data:
                with_controls.append(rom)
                
                # Check player count for single/multiplayer categories
                player_count = int(game_data.get('numPlayers', 1))
                if player_count == 1:
                    singleplayer_roms.append(rom)
                elif player_count > 1:
                    multiplayer_roms.append(rom)
                
                # NEW: Check for specialized controls
                has_specialized = False
                has_analog = False
                has_buttons = False
                
                # Specialized input detection
                specialized_types = [
                    "TRACKBALL", "LIGHTGUN", "MOUSE", "DIAL", "PADDLE", 
                    "POSITIONAL", "GAMBLE", "AD_STICK"
                ]
                
                # Analog input detection
                analog_types = [
                    "AD_STICK", "DIAL", "PADDLE", "PEDAL", "POSITIONAL"
                ]
                
                # Check each player's controls
                for player in game_data.get('players', []):
                    for label in player.get('labels', []):
                        control_name = label['name']
                        
                        # Check for buttons
                        if "BUTTON" in control_name:
                            has_buttons = True
                        
                        # Check for specialized controls
                        for specialized_type in specialized_types:
                            if specialized_type in control_name:
                                has_specialized = True
                                break
                                
                        # Check for analog controls
                        for analog_type in analog_types:
                            if analog_type in control_name:
                                has_analog = True
                                break
                
                # Add to specialized category if it has specialized controls
                if has_specialized:
                    specialized_roms.append(rom)
                    
                # Add to analog category if it has analog controls
                if has_analog:
                    analog_roms.append(rom)
                    
                # Add to no_buttons category if it has controls but no buttons
                if not has_buttons:
                    no_buttons_roms.append(rom)
                    
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
                
                if not has_custom_controls:
                    generic_controls.append(rom)
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
        # NEW CATEGORIES
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
            
            # Build the prefix
            prefix = "* " if has_config else "  "
            prefix += "+ " if has_data else "- "
            
            # Create display text
            if is_clone and (self.current_view == "clones" or self.current_view == "all"):
                parent_rom = self.parent_lookup.get(rom, "")
                
                # Get game name if available
                if has_data:
                    game_data = self.get_game_data(rom)
                    display_text = f"{prefix}{rom} - {game_data['gamename']} [Clone of {parent_rom}]"
                else:
                    display_text = f"{prefix}{rom} [Clone of {parent_rom}]"
            else:
                # Regular display for non-clones or when not in clone view
                if has_data:
                    game_data = self.get_game_data(rom)
                    display_text = f"{prefix}{rom} - {game_data['gamename']}"
                else:
                    display_text = f"{prefix}{rom}"
            
            # Store both the ROM name and display text
            self.game_list_data.append((rom, display_text))
            list_display_items.append(display_text)
        
        # Update the listbox
        self.game_listbox.delete(0, tk.END)
        for item in list_display_items:
            self.game_listbox.insert(tk.END, item)
        
        # Try to select the previously selected ROM if it's still in the list
        if previously_selected_rom:
            for i, (rom_name, _) in enumerate(self.game_list_data):
                if rom_name == previously_selected_rom:
                    # We found the previously selected ROM, select it again
                    self.game_listbox.selection_clear(0, tk.END)
                    self.game_listbox.selection_set(i)
                    self.game_listbox.see(i)  # Ensure it's visible
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
            "clones": "Clone ROMs",
            # NEW CATEGORIES
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
    
    def display_game_info(self, rom_name):
        """Display game information and controls"""
        try:
            # Update toolbar status when a new ROM is selected
            if hasattr(self, 'update_toolbar_status'):
                self.update_toolbar_status()
                
            # Get game data
            game_data = self.get_game_data(rom_name)
            
            # Update UI with game data
            if not game_data:
                # Clear display for ROMs without control data
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
                
                # Add button to create controls
                add_button = ctk.CTkButton(
                    missing_card,
                    text="Add Control Configuration",
                    command=lambda r=rom_name: self.show_control_editor(r),
                    fg_color=self.theme_colors["primary"],
                    hover_color=self.theme_colors["button_hover"],
                    height=35
                )
                add_button.pack(anchor="w", padx=15, pady=(5, 15))
                
                return

            current_mode = getattr(self, 'input_mode', 'xinput' if self.use_xinput else 'joycode')
            print(f"Display game info using input mode: {current_mode}")

            # IMPORTANT: Get custom control configuration if it exists
            cfg_controls = {}
            if rom_name in self.custom_configs:
                # Parse the custom config
                cfg_content = self.custom_configs[rom_name]
                # Add debug output to check if there are any mappings in the file
                parsed_controls = self.parse_cfg_controls(cfg_content)
                if parsed_controls:
                    print(f"Found {len(parsed_controls)} control mappings in ROM CFG for {rom_name}")
                    # Convert using current mode
                    cfg_controls = {
                        control: self.convert_mapping(mapping, current_mode)
                        for control, mapping in parsed_controls.items()
                    }
                else:
                    print(f"ROM CFG exists for {rom_name} but contains no control mappings")

            # Update game title
            source_text = f" ({game_data.get('source', 'unknown')})"
            title_text = f"{game_data['gamename']}{source_text}"
            self.game_title.configure(text=title_text)
            
            # Clear existing display
            for widget in self.control_frame.winfo_children():
                widget.destroy()
                
            # Display controls with enhanced styling
            row = 0
            self.display_controls_table(row, game_data, cfg_controls)
            
        except Exception as e:
            print(f"Error displaying game info: {e}")
            import traceback
            traceback.print_exc()
    
    def show_game_context_menu_listbox(self, event):
        """Show context menu on right-click for ROM entries in listbox"""
        try:
            # Get the index at the event position (CTkListbox may have a different method for this)
            # You might need to adjust this based on CTkListbox's API
            index = self.game_listbox.curselection()
            
            # Select the clicked item
            self.game_listbox.activate(index)
            
            # Get ROM name from our data list
            if index < len(self.game_list_data):
                rom_name, display_text = self.game_list_data[index]
                
                # DEBUGGING: Print raw line content
                print(f"Context menu for ROM: '{rom_name}'")
                
                # Check if this is a clone ROM
                is_clone = rom_name in self.parent_lookup if hasattr(self, 'parent_lookup') else False
                parent_rom = self.parent_lookup.get(rom_name) if is_clone else None
                
                # Create context menu
                context_menu = tk.Menu(self, tearoff=0)
                
                # Add menu items
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
                if rom in self.rom_data_cache or self.rom_exists_in_db(rom):
                    with_controls.append(rom)
                
            elif self.current_view == "missing":
                # Opposite of with_controls
                if rom not in self.rom_data_cache and not self.rom_exists_in_db(rom):
                    missing_controls.append(rom)
                    
            elif self.current_view == "generic":
                # This requires actual data inspection, more expensive
                game_data = self.get_game_data(rom)
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
        
        # REORDERED: Control mappings card MOVED UP before clone management
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
        # Get existing controls from game data to ensure we show ALL controls
        existing_controls = []
        existing_control_names = set()  # Track which control names exist in the game data
                
        if game_data and 'players' in game_data:
            for player in game_data.get('players', []):
                for label in player.get('labels', []):
                    # Add all controls to our list including specialized ones like P1_DIAL
                    existing_controls.append((label['name'], label['value']))
                    existing_control_names.add(label['name'])

        # Dynamically generate buttons based on game data
        standard_controls = []

        # First determine how many buttons to show
        if is_new_game:
            # For new games, use the buttons value from the UI
            buttons_to_show = int(buttons_var.get())
            print(f"New game: showing {buttons_to_show} buttons from UI input")
        else:
            # For existing games, only show buttons that are actually defined in the controls
            num_buttons = int(game_data.get('buttons', 2))  # Default to 2 if not specified
            print(f"Existing game: game defines {num_buttons} buttons")
            
            # Only show buttons that are actually defined in the controls
            defined_buttons = []
            for i in range(1, 11):  # Check up to button 10
                button_name = f"P1_BUTTON{i}"
                if button_name in existing_control_names or (
                    'controls' in game_data and button_name in game_data['controls']):
                    defined_buttons.append(button_name)
            
            print(f"Found {len(defined_buttons)} defined buttons: {defined_buttons}")
            buttons_to_show = max(num_buttons, len(defined_buttons))
            print(f"Will show {buttons_to_show} buttons")

        # Generate button controls - ONLY for buttons that exist in the game
        for i in range(1, buttons_to_show + 1):
            control_name = f'P1_BUTTON{i}'
            display_name = f'P1 Button {i}'
            standard_controls.append((control_name, display_name))

        # Only add directional controls if they're used in this game
        directional_controls = []
        if any(name.startswith('P1_JOYSTICK_') for name in existing_control_names):
            directional_controls.extend([
                ('P1_JOYSTICK_UP', 'P1 Joystick Up'),
                ('P1_JOYSTICK_DOWN', 'P1 Joystick Down'),
                ('P1_JOYSTICK_LEFT', 'P1 Joystick Left'),
                ('P1_JOYSTICK_RIGHT', 'P1 Joystick Right'),
            ])

        # Only add right stick controls if they're used
        right_stick_controls = []
        if any(name.startswith('P1_JOYSTICKRIGHT_') for name in existing_control_names):
            right_stick_controls.extend([
                ('P1_JOYSTICKRIGHT_UP', 'P1 Right Stick Up'),
                ('P1_JOYSTICKRIGHT_DOWN', 'P1 Right Stick Down'),
                ('P1_JOYSTICKRIGHT_LEFT', 'P1 Right Stick Left'),
                ('P1_JOYSTICKRIGHT_RIGHT', 'P1 Right Stick Right'),
            ])

        # Only add D-pad controls if they're used
        dpad_controls = []
        if any(name.startswith('P1_DPAD_') for name in existing_control_names):
            dpad_controls.extend([
                ('P1_DPAD_UP', 'P1 D-Pad Up'),
                ('P1_DPAD_DOWN', 'P1 D-Pad Down'),
                ('P1_DPAD_LEFT', 'P1 D-Pad Left'),
                ('P1_DPAD_RIGHT', 'P1 D-Pad Right'),
            ])

        # System buttons are common so we'll include them
        system_controls = [
            ('P1_START', 'P1 Start Button'),
            ('P1_SELECT', 'P1 Select/Coin Button'),
        ]

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
        
        # Create container for control entries
        controls_container = ctk.CTkFrame(controls_card, fg_color="transparent")
        controls_container.pack(fill="x", padx=15, pady=(0, 15))
        
        # Create a scrollable container for controls
        controls_scroll = ctk.CTkScrollableFrame(
            controls_container,
            fg_color="transparent",
            height=300,  # Limit height to make sure we don't get a huge dialog
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        controls_scroll.pack(fill="x", expand=True)
        
        # Row alternating colors
        alt_colors = [self.theme_colors["card_bg"], self.theme_colors["background"]]
        
        # Create entry fields for each standard control
        for i, (control_name, display_name) in enumerate(standard_controls):
            # Create a frame for each control with alternating background
            control_frame = ctk.CTkFrame(
                controls_scroll, 
                fg_color=alt_colors[i % 2],
                corner_radius=4
            )
            control_frame.pack(fill="x", pady=2)
            
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
        
        # Create entry fields for specialized controls
        for i, (control_name, display_name) in enumerate(specialized_controls):
            # Create a frame for each control with alternating background
            control_frame = ctk.CTkFrame(
                controls_scroll, 
                fg_color=alt_colors[i % 2],
                corner_radius=4
            )
            control_frame.pack(fill="x", pady=2)
            
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
        
        # Add any additional controls found in game data but not in our predefined lists
        additional_controls = []
        for control_name, action in existing_controls:
            if not any(control[0] == control_name for control in standard_controls + specialized_controls):
                additional_controls.append((control_name, action))
        
        if additional_controls:
            
            # Create entry fields for additional controls
            for i, (control_name, action) in enumerate(additional_controls):
                control_frame = ctk.CTkFrame(
                    controls_scroll, 
                    fg_color=alt_colors[i % 2],
                    corner_radius=4
                )
                control_frame.pack(fill="x", pady=2)
                
                # Configure columns
                control_frame.columnconfigure(0, weight=1)  # Control name
                control_frame.columnconfigure(1, weight=1)  # Action entry
                
                # Control name label
                ctk.CTkLabel(
                    control_frame, 
                    text=control_name, 
                    font=("Arial", 13),
                    anchor="w",
                    width=200
                ).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                
                # Create entry for action
                action_entry = ctk.CTkEntry(
                    control_frame, 
                    width=400,
                    fg_color=self.theme_colors["background"]
                )
                action_entry.insert(0, action)
                action_entry.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
                
                # Store the entry widget in our dictionary
                control_entries[control_name] = action_entry
        
        # Add a section for custom controls with enhanced styling
        custom_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        custom_card.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            custom_card, 
            text="Custom Controls (Optional)", 
            font=("Arial", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Frame to hold custom control entries
        custom_controls_frame = ctk.CTkFrame(custom_card, fg_color="transparent")
        custom_controls_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # List to track custom controls
        custom_control_rows = []
        
        def update_all_dropdowns(changed_control, add=False):
            """
            Update all dropdown menus when a control is added or removed
            
            Parameters:
            - changed_control: The control name that was added or removed
            - add: True if the control should be added to dropdowns, False if it should be removed
            """
            # Only process if it's a valid control name
            if not changed_control or changed_control == "OTHER (Type custom name)":
                return
                
            for row_data in custom_control_rows:
                if 'dropdown' not in row_data or not row_data['dropdown'].winfo_exists():
                    continue
                    
                dropdown = row_data['dropdown']
                current_options = dropdown.cget("values")
                current_value = row_data['control_var'].get()
                
                # Skip updating this dropdown if it's the one that changed
                if current_value == changed_control and not add:
                    continue
                    
                if add:
                    # Add the control back to the options if it's not already there
                    if changed_control not in current_options:
                        # Insert the control in alphabetical order (keeping "OTHER" at the end)
                        new_options = list(current_options)
                        if "OTHER (Type custom name)" in new_options:
                            new_options.remove("OTHER (Type custom name)")
                            
                        new_options.append(changed_control)
                        new_options.sort()  # Sort alphabetically
                        new_options.append("OTHER (Type custom name)")  # Keep OTHER at the end
                        
                        # Update the dropdown
                        dropdown.configure(values=new_options)
                else:
                    # Remove the control from the options
                    if changed_control in current_options:
                        new_options = [opt for opt in current_options if opt != changed_control]
                        dropdown.configure(values=new_options)
        
        def add_custom_control_row():
            row_frame = ctk.CTkFrame(custom_controls_frame, fg_color=self.theme_colors["background"], corner_radius=4)
            row_frame.pack(fill="x", pady=2)
            
            # Configure columns
            row_frame.columnconfigure(0, weight=1)  # Control name
            row_frame.columnconfigure(1, weight=1)  # Action entry
            row_frame.columnconfigure(2, weight=0)  # Remove button
            
            # Define comprehensive list of all possible MAME controls
            all_control_options = [
                # Standard buttons from 1-12
                "P1_BUTTON1", "P1_BUTTON2", "P1_BUTTON3", "P1_BUTTON4", 
                "P1_BUTTON5", "P1_BUTTON6", "P1_BUTTON7", "P1_BUTTON8",
                "P1_BUTTON9", "P1_BUTTON10", "P1_BUTTON11", "P1_BUTTON12",
                # System buttons
                "P1_START", "P1_SELECT", "P1_COIN",
                # Joysticks
                "P1_JOYSTICK_UP", "P1_JOYSTICK_DOWN", "P1_JOYSTICK_LEFT", "P1_JOYSTICK_RIGHT",
                # Right joystick
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
            
            # Get list of already assigned controls
            already_assigned = []
            
            # From standard controls
            for control_name, entry in control_entries.items():
                if isinstance(entry, ctk.CTkEntry) and entry.get().strip():
                    already_assigned.append(control_name)
            
            # From custom controls
            for row_data in custom_control_rows:
                if 'dropdown' in row_data and row_data['dropdown'].winfo_viewable():
                    control = row_data['control_var'].get()
                    if control and control != "OTHER (Type custom name)":
                        already_assigned.append(control)
                elif 'custom_entry' in row_data and row_data['custom_entry'].winfo_exists():
                    control = row_data['custom_entry'].get().strip()
                    if control:
                        already_assigned.append(control)
            
            # Filter out already assigned controls
            available_controls = [c for c in all_control_options if c not in already_assigned]
            
            # Always add the custom option at the end
            control_options = available_controls + ["OTHER (Type custom name)"]
            
            # Control name dropdown
            control_var = tk.StringVar()
            if control_options:
                control_var.set(control_options[0])  # Set the first available option as default
            
            control_dropdown = ctk.CTkComboBox(
                row_frame,
                width=250,
                values=control_options,
                variable=control_var,
                fg_color=self.theme_colors["card_bg"],
                button_color=self.theme_colors["primary"],
                button_hover_color=self.theme_colors["secondary"],
                dropdown_fg_color=self.theme_colors["card_bg"]
            )
            control_dropdown.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
            
            # Custom control entry (initially hidden)
            custom_control_entry = ctk.CTkEntry(
                row_frame,
                width=250,
                placeholder_text="Enter custom control name",
                fg_color=self.theme_colors["card_bg"]
            )
            custom_control_entry.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
            custom_control_entry.grid_remove()  # Initially hidden
            
            # Function to handle dropdown changes
            def on_dropdown_change(*args):
                old_value = getattr(control_var, "_last_value", None)
                new_value = control_var.get()
                
                # Store the current value for next time
                control_var._last_value = new_value
                
                if new_value == "OTHER (Type custom name)":
                    # Hide dropdown, show custom entry
                    control_dropdown.grid_remove()
                    custom_control_entry.grid()
                    custom_control_entry.focus_set()
                elif old_value != new_value:
                    # Control selection changed, update other dropdowns
                    update_all_dropdowns(new_value, add=False)  # Remove from other dropdowns
                    if old_value and old_value != "OTHER (Type custom name)":
                        update_all_dropdowns(old_value, add=True)  # Add old value back to other dropdowns

            # Bind the change event
            control_var.trace_add("write", on_dropdown_change)
            
            # Action entry
            action_entry = ctk.CTkEntry(
                row_frame, 
                width=400, 
                placeholder_text="Action/Function",
                fg_color=self.theme_colors["card_bg"]
            )
            action_entry.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

            def remove_row():
                row_frame.pack_forget()
                row_frame.destroy()
                if row_data in custom_control_rows:
                    custom_control_rows.remove(row_data)
                    
                    # Update other dropdowns to make this control available again
                    if 'dropdown' in row_data and row_data['dropdown'].winfo_viewable():
                        removed_control = row_data['control_var'].get()
                        if removed_control != "OTHER (Type custom name)":
                            update_all_dropdowns(removed_control, add=True)
                    elif 'custom_entry' in row_data:
                        removed_control = row_data['custom_entry'].get().strip()
                        if removed_control:
                            update_all_dropdowns(removed_control, add=True)
            
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
            remove_button.grid(row=0, column=2, padx=(5, 10), pady=8)
            
            # Store row data
            row_data = {
                'frame': row_frame, 
                'dropdown': control_dropdown,
                'custom_entry': custom_control_entry,
                'control_var': control_var,
                'action': action_entry
            }
            custom_control_rows.append(row_data)
            
            return row_data
        
        # Add first custom row
        add_custom_control_row()
        
        # Add button for additional rows
        add_custom_button = ctk.CTkButton(
            custom_controls_frame,
            text="+ Add Another Custom Control",
            command=add_custom_control_row,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"],
            height=35
        )
        add_custom_button.pack(pady=10)
        
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
                
                # Add controls
                for control_name, entry in control_entries.items():
                    if isinstance(entry, ctk.CTkEntry):  # Check if it's an entry widget
                        control_label = entry.get().strip()
                        if control_label:
                            game_entry[current_rom_name]["controls"][control_name] = {
                                "name": control_label,
                                "tag": "",
                                "mask": "0"
                            }
                
                # Add custom controls
                for row_data in custom_control_rows:
                    # Get control name based on whether dropdown or custom entry is used
                    if row_data['dropdown'].winfo_viewable():  # If dropdown is visible
                        control_name = row_data['control_var'].get()
                        # Skip the "OTHER" option
                        if control_name == "OTHER (Type custom name)":
                            continue
                    else:  # Custom entry is being used
                        control_name = row_data['custom_entry'].get().strip()
                    
                    control_label = row_data['action'].get().strip()
                    
                    # Only add if both fields have values and it's not the placeholder option
                    if control_name and control_label and control_name != "OTHER (Type custom name)":
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
        
        # Remove Game button (with confirmation) - only show if not a new game
        if not is_new_game:
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
        
        # Save function to handle both new and existing games
        def save_game():
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
                    # Create new file if it doesn't exist
                    gamedata = {}
                except json.JSONDecodeError:
                    # Handle corrupted JSON
                    messagebox.showerror("Error", "The gamedata.json file is corrupted", parent=editor)
                    return
                    
                # Check if game already exists
                if is_new_game and current_rom_name in gamedata:
                    if not messagebox.askyesno("Warning", 
                                        f"'{current_rom_name}' already exists. Overwrite?", 
                                        parent=editor):
                        return
                
                # Build the game entry
                game_entry = {
                    "description": description_var.get().strip() or current_rom_name,
                    "playercount": playercount_var.get(),
                    "buttons": buttons_var.get(),
                    "sticks": sticks_var.get(),
                    "alternating": bool(alternating_var.get()),
                    "clones": {},
                    "controls": {}
                }
                
                # Add clones
                for clone_data in clone_entries:
                    clone_rom = clone_data["rom_var"].get().strip()
                    clone_desc = clone_data["desc_var"].get().strip()
                    
                    if clone_rom:
                        game_entry["clones"][clone_rom] = {
                            "description": clone_desc or f"{clone_rom} (Clone of {current_rom_name})"
                        }
                
                # Track defined button numbers from standard controls
                defined_buttons = set()
                
                # Add standard controls
                for control_name, entry in control_entries.items():
                    if isinstance(entry, ctk.CTkEntry):  # Check if it's an entry widget
                        control_label = entry.get().strip()
                        if control_label:
                            game_entry["controls"][control_name] = {
                                "name": control_label,
                                "tag": "",
                                "mask": "0"
                            }
                            
                            # Track button numbers
                            if control_name.startswith("P1_BUTTON"):
                                try:
                                    button_num = int(control_name.replace("P1_BUTTON", ""))
                                    defined_buttons.add(button_num)
                                except ValueError:
                                    pass
                
                # Add custom controls
                for row_data in custom_control_rows:
                    # Get control name based on whether dropdown or custom entry is used
                    if row_data['dropdown'].winfo_viewable():  # If dropdown is visible
                        control_name = row_data['control_var'].get()
                        # Skip the "OTHER" option
                        if control_name == "OTHER (Type custom name)":
                            continue
                    else:  # Custom entry is being used
                        control_name = row_data['custom_entry'].get().strip()
                    
                    control_label = row_data['action'].get().strip()
                    
                    # Only add if both fields have values and it's not the placeholder option
                    if control_name and control_label and control_name != "OTHER (Type custom name)":
                        game_entry["controls"][control_name] = {
                            "name": control_label,
                            "tag": "",
                            "mask": "0"
                        }
                        
                        # Track button numbers
                        if control_name.startswith("P1_BUTTON"):
                            try:
                                button_num = int(control_name.replace("P1_BUTTON", ""))
                                defined_buttons.add(button_num)
                            except ValueError:
                                pass
                
                # Get the current button setting
                current_buttons = int(buttons_var.get())
                
                # If we have defined buttons, check if we need to update the count
                if defined_buttons:
                    max_defined_button = max(defined_buttons) if defined_buttons else 0
                    
                    # Case 1: More buttons defined than current setting
                    if max_defined_button > current_buttons:
                        if messagebox.askyesno("Update Button Count", 
                                    f"You've defined buttons up to P1_BUTTON{max_defined_button}, but the game is set to use {current_buttons} buttons.\n\nWould you like to update the button count to {max_defined_button}?", 
                                    parent=editor):
                            # Update the button count
                            buttons_var.set(str(max_defined_button))
                            game_entry["buttons"] = str(max_defined_button)
                            print(f"Updated button count to {max_defined_button}")
                    
                    # Case 2: Fewer buttons defined than current setting
                    elif max_defined_button < current_buttons:
                        if messagebox.askyesno("Reduce Button Count", 
                                    f"The highest button you've defined is P1_BUTTON{max_defined_button}, but the game is set to use {current_buttons} buttons.\n\nWould you like to reduce the button count to {max_defined_button}?", 
                                    parent=editor):
                            # Update the button count
                            buttons_var.set(str(max_defined_button))
                            game_entry["buttons"] = str(max_defined_button)
                            print(f"Reduced button count to {max_defined_button}")
                
                # Update or add entry to gamedata
                gamedata[current_rom_name] = game_entry
                
                # Save the updated gamedata.json
                with open(gamedata_path, 'w', encoding='utf-8') as f:
                    json.dump(gamedata, f, indent=2)
                
                # Show success message
                messagebox.showinfo("Success", 
                            f"Game '{current_rom_name}' {'added to' if is_new_game else 'updated in'} gamedata.json", 
                            parent=editor)
                
                # Force reload of gamedata.json
                if hasattr(self, 'gamedata_json'):
                    del self.gamedata_json
                    self.load_gamedata_json()
                
                # Clear the in-memory cache to force reloading data
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache = {}
                    print("Cleared ROM data cache to force refresh")
                
                # Rebuild SQLite database if it's being used
                if hasattr(self, 'db_path') and self.db_path:
                    print("Rebuilding SQLite database to reflect changes...")
                    self.build_gamedata_db()
                    print("Database rebuild complete")
                    
                # Update sidebar categories
                if hasattr(self, 'update_game_list_by_category'):
                    self.update_game_list_by_category()
                
                # Close the editor
                editor.destroy()
                
                # Force refresh of the current display if needed
                if hasattr(self, 'on_game_select') and hasattr(self, 'game_list') and hasattr(self, 'selected_line'):
                    # Create a mock event to trigger refresh if needed
                    class MockEvent:
                        def __init__(self):
                            self.x = 10
                            self.y = 10
                    self.after(100, lambda: self.on_game_select(MockEvent()))
                    
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save game data: {str(e)}", parent=editor)
                print(f"Error saving game data: {e}")
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
            fg_color=self.theme_colors["card_bg"],
            hover_color=self.theme_colors["background"],
            border_width=1,
            border_color=self.theme_colors["text_dimmed"],
            text_color=self.theme_colors["text"],
            font=("Arial", 14),
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

    @lru_cache(maxsize=128)
    def get_game_data(self, romname):
        """Get game data with integrated database prioritization and improved handling of unnamed controls"""
        
        # 1. Check cache first (this is redundant with lru_cache but kept for backward compatibility)
        if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
            cached_data = self.rom_data_cache[romname]
            
        # 2. Try database first if available
        if os.path.exists(self.db_path):
            db_data = self.get_game_data_from_db(romname)
            if db_data:
                # Cache the result
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache[romname] = db_data
                return db_data
        
        # 3. Fall back to JSON lookup if needed
        # Load gamedata.json first if needed
        if not hasattr(self, 'gamedata_json') or not self.gamedata_json:
            self.load_gamedata_json()
                
        # Continue with the existing lookup logic...
        if romname in self.gamedata_json:
            game_data = self.gamedata_json[romname]
            
            # Simple name defaults - these are the fallback button names if none are specified
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
                # Mirror P1 button names for P2
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
            
            # Basic structure conversion
            converted_data = {
                'romname': romname,
                'gamename': game_data.get('description', romname),
                'numPlayers': int(game_data.get('playercount', 1)),
                'alternating': game_data.get('alternating', False),
                'mirrored': False,
                'miscDetails': f"Buttons: {game_data.get('buttons', '?')}, Sticks: {game_data.get('sticks', '?')}",
                'players': []
            }
            
            # Check if this is a clone and needs to inherit controls from parent
            needs_parent_controls = False
            
            # Find controls (direct or in a clone)
            controls = None
            if 'controls' in game_data:
                controls = game_data['controls']
            else:
                needs_parent_controls = True
                
            # If no controls and this is a clone, try to use parent controls
            if needs_parent_controls:
                parent_rom = None
                
                # Check explicit parent field (should be there from load_gamedata_json)
                if 'parent' in game_data:
                    parent_rom = game_data['parent']
                
                # Also check parent lookup table for redundancy
                elif hasattr(self, 'parent_lookup') and romname in self.parent_lookup:
                    parent_rom = self.parent_lookup[romname]
                
                # If we found a parent, try to get its controls
                if parent_rom and parent_rom in self.gamedata_json:
                    parent_data = self.gamedata_json[parent_rom]
                    if 'controls' in parent_data:
                        controls = parent_data['controls']
            
            # Now process the controls (either direct or inherited from parent)
            if controls:
                # First pass - collect P1 button names to mirror to P2
                p1_button_names = {}
                for control_name, control_data in controls.items():
                    if control_name.startswith('P1_BUTTON') and 'name' in control_data:
                        button_num = control_name.replace('P1_BUTTON', '')
                        p1_button_names[f'P2_BUTTON{button_num}'] = control_data['name']
                        
                # Process player controls
                p1_controls = []
                p2_controls = []
                
                for control_name, control_data in controls.items():
                    # Add P1 controls
                    if control_name.startswith('P1_'):
                        
                        # Include standard controls AND specialized analog/positional controls
                        specialized_control_types = ['JOYSTICK', 'BUTTON', 'PEDAL', 'AD_STICK', 'DIAL', 'PADDLE', 
                                                   'TRACKBALL', 'LIGHTGUN', 'MOUSE', 'POSITIONAL', 'GAMBLE']
                        
                        if any(control_type in control_name for control_type in specialized_control_types):
                            
                            # Get the friendly name - IMPORTANT: Always provide a fallback
                            friendly_name = None
                            
                            # First check for explicit name
                            if 'name' in control_data and control_data['name']:
                                friendly_name = control_data['name']
                            # Then check for default actions
                            elif control_name in default_actions:
                                friendly_name = default_actions[control_name]
                            # ALWAYS provide a fallback - never leave friendly_name as None
                            else:
                                parts = control_name.split('_')
                                if len(parts) > 1:
                                    friendly_name = parts[-1].replace('_', ' ').title()
                                else:
                                    friendly_name = control_name
                            
                            # ALWAYS add the control - don't check if friendly_name exists
                            control_entry = {
                                'name': control_name,
                                'value': friendly_name
                            }
                            p1_controls.append(control_entry)
           
                # Handle system controls that don't have P1_ prefix
                # If shown the directional and analog only games will not displayt correctly.
                system_control_mappings = {
                    #'START1': ('P1_START', 'Start Button'),
                    #'START2': ('P2_START', 'Start Button'), 
                    #'COIN1': ('P1_SELECT', 'Insert Coin'),
                    #'COIN2': ('P2_SELECT', 'Insert Coin'),
                    'SERVICE1': ('P1_SERVICE', 'Service Button'),
                    'TEST1': ('P1_TEST', 'Test Button')
                }

                for original_control, control_data in controls.items():
                    if original_control in system_control_mappings:
                        mapped_name, default_action = system_control_mappings[original_control]
                        
                        # Determine which player list this belongs to
                        if mapped_name.startswith('P1_'):
                            target_list = p1_controls
                        elif mapped_name.startswith('P2_'):
                            target_list = p2_controls
                        else:
                            continue
                            
                        # Get friendly name
                        friendly_name = None
                        if 'name' in control_data and control_data['name']:
                            friendly_name = control_data['name']
                        else:
                            friendly_name = default_action
                            
                        # Add to appropriate player list
                        target_list.append({
                            'name': mapped_name,  # Use the standardized name
                            'value': friendly_name
                        })
                
                # Also check for special direction mappings (P1_UP, etc.)
                for control_name, control_data in controls.items():
                    if control_name == 'P1_UP' and 'name' in control_data:
                        # Update the joystick control if it exists
                        for control in p1_controls:
                            if control['name'] == 'P1_JOYSTICK_UP':
                                control['value'] = control_data['name']
                    elif control_name == 'P1_DOWN' and 'name' in control_data:
                        for control in p1_controls:
                            if control['name'] == 'P1_JOYSTICK_DOWN':
                                control['value'] = control_data['name']
                    elif control_name == 'P1_LEFT' and 'name' in control_data:
                        for control in p1_controls:
                            if control['name'] == 'P1_JOYSTICK_LEFT':
                                control['value'] = control_data['name']
                    elif control_name == 'P1_RIGHT' and 'name' in control_data:
                        for control in p1_controls:
                            if control['name'] == 'P1_JOYSTICK_RIGHT':
                                control['value'] = control_data['name']
                    # Also handle P2 directional controls the same way
                    elif control_name == 'P2_UP' and 'name' in control_data:
                        for control in p2_controls:
                            if control['name'] == 'P2_JOYSTICK_UP':
                                control['value'] = control_data['name']
                    elif control_name == 'P2_DOWN' and 'name' in control_data:
                        for control in p2_controls:
                            if control['name'] == 'P2_JOYSTICK_DOWN':
                                control['value'] = control_data['name']
                    elif control_name == 'P2_LEFT' and 'name' in control_data:
                        for control in p2_controls:
                            if control['name'] == 'P2_JOYSTICK_LEFT':
                                control['value'] = control_data['name']
                    elif control_name == 'P2_RIGHT' and 'name' in control_data:
                        for control in p2_controls:
                            if control['name'] == 'P2_JOYSTICK_RIGHT':
                                control['value'] = control_data['name']
                
                # Sort controls by name to ensure consistent order (Button 1 before Button 2)
                p1_controls.sort(key=lambda x: x['name'])
                p2_controls.sort(key=lambda x: x['name'])
                            
                # Add player 1 if we have controls
                if p1_controls:
                    converted_data['players'].append({
                        'number': 1,
                        'numButtons': int(game_data.get('buttons', 1)),
                        'labels': p1_controls
                    })

                # Add player 2 if we have controls
                if p2_controls:
                    converted_data['players'].append({
                        'number': 2,
                        'numButtons': int(game_data.get('buttons', 1)),
                        'labels': p2_controls
                    })
                    
            # If we still have no controls, let's generate default ones based on game properties
            elif not converted_data['players'] and (game_data.get('buttons') or game_data.get('sticks')):
                num_buttons = int(game_data.get('buttons', 6))
                num_sticks = int(game_data.get('sticks', 1))
                p1_controls = []
                
                # Add joystick controls if sticks > 0
                if num_sticks > 0:
                    for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                        control_name = f'P1_JOYSTICK_{direction}'
                        p1_controls.append({
                            'name': control_name,
                            'value': default_actions.get(control_name, direction.capitalize())
                        })
                
                # Add buttons based on the number specified
                for i in range(1, min(num_buttons + 1, 11)):  # Limit to 10 buttons
                    control_name = f'P1_BUTTON{i}'
                    p1_controls.append({
                        'name': control_name,
                        'value': default_actions.get(control_name, f'Button {i}')
                    })
                
                # Sort controls by name
                p1_controls.sort(key=lambda x: x['name'])
                
                # Add player 1
                converted_data['players'].append({
                    'number': 1,
                    'numButtons': num_buttons,
                    'labels': p1_controls
                })
                
                # If two players, mirror controls
                if game_data.get('playercount', 1) > 1 and not game_data.get('alternating', False):
                    p2_controls = []
                    
                    # Mirror P1 controls to P2
                    for p1_control in p1_controls:
                        p1_name = p1_control['name']
                        p2_name = p1_name.replace('P1_', 'P2_')
                        p2_controls.append({
                            'name': p2_name,
                            'value': p1_control['value']
                        })
                    
                    # Add player 2
                    converted_data['players'].append({
                        'number': 2,
                        'numButtons': num_buttons,
                        'labels': p2_controls
                    })
                
            # Mark as gamedata source
            converted_data['source'] = 'gamedata.json'
            
            # Cache the result if caching is enabled
            if hasattr(self, 'rom_data_cache'):
                self.rom_data_cache[romname] = converted_data
                
            return converted_data
        
        # Try parent lookup before giving up
        if hasattr(self, 'parent_lookup') and romname in self.parent_lookup:
            parent_rom = self.parent_lookup[romname]
            parent_data = self.get_game_data(parent_rom)  # Recursive call
            if parent_data:
                # Update with this ROM's info and cache
                parent_data['romname'] = romname
                if romname in self.gamedata_json:
                    parent_data['gamename'] = self.gamedata_json[romname].get('description', f"{romname} (Clone)")
                
                # Cache and return
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache[romname] = parent_data
                return parent_data
        
        # Not found anywhere
        return None

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
        
        edit_button = ctk.CTkButton(
            button_frame,
            text="Edit Selected Game",
            command=edit_selected_game
        )
        edit_button.pack(side=tk.LEFT, padx=5)
        
        return list_frame
    
    def identify_generic_controls(self):
        """Identify games that only have generic control names"""
        generic_control_games = []
        missing_control_games = []
        
        # Generic action names that indicate default mappings
        generic_actions = [
            "A Button", "B Button", "X Button", "Y Button", 
            "LB Button", "RB Button", "LT Button", "RT Button",
            "Up", "Down", "Left", "Right"
        ]
        
        for rom_name in sorted(self.available_roms):
            # First check if game data exists at all
            game_data = self.get_game_data(rom_name)
            if not game_data:
                missing_control_games.append(rom_name)
                continue
                
            # Check if controls are just generic
            has_custom_controls = False
            for player in game_data.get('players', []):
                for label in player.get('labels', []):
                    action = label['value']
                    # If we find any non-generic action, mark this game as having custom controls
                    if action not in generic_actions:
                        has_custom_controls = True
                        break
                if has_custom_controls:
                    break
                    
            # If no custom controls found, add to list
            if not has_custom_controls and game_data.get('players'):
                generic_control_games.append((rom_name, game_data.get('gamename', rom_name)))
        
        return generic_control_games, missing_control_games
    
    def filter_xinput_controls(self, game_data):
        """Filter game_data to only include XInput-compatible controls"""
        if not game_data:
            return game_data
                
        # Make a copy to avoid modifying the original
        import copy
        filtered_data = copy.deepcopy(game_data)
            
        # Define strictly which controls are valid in XInput mode
        xinput_controls = {
            'P1_BUTTON1', 'P1_BUTTON2', 'P1_BUTTON3', 'P1_BUTTON4',
            'P1_BUTTON5', 'P1_BUTTON6', 'P1_BUTTON7', 'P1_BUTTON8',
            'P1_BUTTON9', 'P1_BUTTON10', 
            'P1_JOYSTICK_UP', 'P1_JOYSTICK_DOWN', 'P1_JOYSTICK_LEFT', 'P1_JOYSTICK_RIGHT',
            'P1_JOYSTICKRIGHT_UP', 'P1_JOYSTICKRIGHT_DOWN', 'P1_JOYSTICKRIGHT_LEFT', 'P1_JOYSTICKRIGHT_RIGHT',
            # Add these left joystick controls
            'P1_JOYSTICKLEFT_UP', 'P1_JOYSTICKLEFT_DOWN', 'P1_JOYSTICKLEFT_LEFT', 'P1_JOYSTICKLEFT_RIGHT',
            'P1_DPAD_UP', 'P1_DPAD_DOWN', 'P1_DPAD_LEFT', 'P1_DPAD_RIGHT',
            'P1_START', 'P1_SELECT',
            # Add these analog controls that were missing
            'P1_AD_STICK_X', 'P1_AD_STICK_Y', 'P1_AD_STICK_Z',
            'P1_DIAL', 'P1_DIAL_V', 'P1_PADDLE', 'P1_PEDAL', 'P1_PEDAL2',
            'P1_TRACKBALL_X', 'P1_TRACKBALL_Y', 'P1_MOUSE_X', 'P1_MOUSE_Y',
            'P1_LIGHTGUN_X', 'P1_LIGHTGUN_Y', 'P1_POSITIONAL'
        }
        
        # For each player, filter labels to only XInput controls
        for player in filtered_data.get('players', []):
            original_count = len(player.get('labels', []))
            filtered_labels = [label for label in player.get('labels', []) 
                            if label['name'] in xinput_controls]
            player['labels'] = filtered_labels
            print(f"Filtered player {player['number']} controls from {original_count} to {len(filtered_labels)}")
        
        # Mark data as XInput only
        filtered_data['xinput_only_mode'] = True
        
        return filtered_data
    
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
            cfg_controls = self.parse_cfg_controls(self.custom_configs[self.current_game])
            
            # Convert based on current input mode
            current_mode = getattr(self, 'input_mode', 'xinput' if self.use_xinput else 'joycode')
            cfg_controls = {
                control: self.convert_mapping(mapping, current_mode)
                for control, mapping in cfg_controls.items()
            }
            
            # Modify game_data to include custom mappings
            self.update_game_data_with_custom_mappings(game_data, cfg_controls)

        # NEW CODE: Filter out non-XInput controls if in XInput Only mode
        if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
            game_data = self.filter_xinput_controls(game_data)
        
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


    def get_friendly_xinput_name(self, mapping: str) -> str:
        """Convert an XINPUT mapping code into a human-friendly button/stick name."""
        parts = mapping.split('_', 2)  # e.g., ["XINPUT", "1", "A"] or ["XINPUT", "1", "LEFTX_NEG"]
        if len(parts) < 3:
            return mapping
        action = parts[2]
        # Updated friendly labels for known XInput controls
        friendly_map = {
            "A":           "A Button",
            "B":           "B Button",
            "X":           "X Button",
            "Y":           "Y Button",
            "SHOULDER_L":  "LB Button",
            "SHOULDER_R":  "RB Button",
            "TRIGGER_L":   "Left Trigger",  # Changed from "LT Button" for better clarity with analog
            "TRIGGER_R":   "Right Trigger", # Changed from "RT Button"
            "THUMB_L":     "Left Stick Button",
            "THUMB_R":     "Right Stick Button",
            "DPAD_UP":     "D-Pad Up",
            "DPAD_DOWN":   "D-Pad Down",
            "DPAD_LEFT":   "D-Pad Left",
            "DPAD_RIGHT":  "D-Pad Right",
            "LEFTX_NEG":   "Left Stick (Left)",
            "LEFTX_POS":   "Left Stick (Right)",
            "LEFTY_NEG":   "Left Stick (Up)",
            "LEFTY_POS":   "Left Stick (Down)",
            "RIGHTX_NEG":  "Right Stick (Left)",
            "RIGHTX_POS":  "Right Stick (Right)",
            "RIGHTY_NEG":  "Right Stick (Up)",
            "RIGHTY_POS":  "Right Stick (Down)"
        }
        return friendly_map.get(action, action)  # Return friendly name or fallback to raw action

    def update_game_data_with_custom_mappings(self, game_data, cfg_controls):
        """Update game_data to include the custom control mappings with support for multiple input modes"""
        if not cfg_controls and not hasattr(self, 'default_controls'):
            return
                            
        # Debug output: Print all available cfg_controls
        print(f"Available custom mappings: {len(cfg_controls)}")
        for control, mapping in cfg_controls.items():
            print(f"  Custom mapping: {control} -> {mapping}")
        
        # Debug output: Print all default controls too
        if hasattr(self, 'default_controls'):
            print(f"Available default mappings: {len(self.default_controls)}")
            for control, mapping in list(self.default_controls.items())[:5]:  # Just show first 5
                print(f"  Default mapping: {control} -> {mapping}")
        
        # Add a flag to the game_data to indicate it uses ROM CFG
        if game_data['romname'] in self.custom_configs:
            game_data['has_rom_cfg'] = True
            game_data['rom_cfg_file'] = f"{game_data['romname']}.cfg"
        
        # Also add flag for default cfg if available
        if hasattr(self, 'default_controls') and self.default_controls:
            game_data['has_default_cfg'] = True
        
        # Combine ROM-specific and default mappings
        all_mappings = {}
        
        # First, add default mappings (always converted to current input mode)
        if hasattr(self, 'default_controls') and self.default_controls:
            for control, mapping in self.default_controls.items():
                # Convert to current input mode
                converted_mapping = self.convert_mapping(mapping, self.input_mode)
                all_mappings[control] = {'mapping': converted_mapping, 'source': 'Default CFG'}
        
        # Then override with ROM-specific mappings
        for control, mapping in cfg_controls.items():
            # Make sure mapping is converted to current input mode
            converted_mapping = self.convert_mapping(mapping, self.input_mode)
            all_mappings[control] = {'mapping': converted_mapping, 'source': f"ROM CFG ({game_data['romname']}.cfg)"}
        
        # IMPORTANT: Now check each control in the game data and ensure it gets a mapping
        for player in game_data.get('players', []):
            for label in player.get('labels', []):
                control_name = label['name']
                
                # Debug output for paddle specifically
                if control_name == 'P1_PADDLE':
                    print(f"*** Processing P1_PADDLE ***")
                    print(f"  In cfg_controls: {control_name in cfg_controls}")
                    print(f"  In default_controls: {control_name in getattr(self, 'default_controls', {})}")
                    print(f"  In all_mappings: {control_name in all_mappings}")
                    if control_name in all_mappings:
                        print(f"  Mapping: {all_mappings[control_name]['mapping']}")
                        print(f"  Source: {all_mappings[control_name]['source']}")
        
        # Add current input mode to game_data
        game_data['input_mode'] = self.input_mode
        
        # Define the functional categories for organizing controls
        functional_categories = {
            'move_horizontal': ['P1_JOYSTICK_LEFT', 'P1_JOYSTICK_RIGHT', 'P1_AD_STICK_X', 'P1_DIAL'],
            'move_vertical': ['P1_JOYSTICK_UP', 'P1_JOYSTICK_DOWN', 'P1_AD_STICK_Y', 'P1_DIAL_V'],
            'action_primary': ['P1_BUTTON1', 'P1_BUTTON2'],
            'action_secondary': ['P1_BUTTON3', 'P1_BUTTON4'],
            'action_special': ['P1_BUTTON5', 'P1_BUTTON6', 'P1_BUTTON7', 'P1_BUTTON8'],
            'system_control': ['P1_START', 'P1_SELECT', 'P1_COIN'],
            'analog_input': ['P1_PEDAL', 'P1_PEDAL2', 'P1_PADDLE', 'P1_AD_STICK_Z'],
            'precision_aim': ['P1_TRACKBALL_X', 'P1_TRACKBALL_Y', 'P1_LIGHTGUN_X', 'P1_LIGHTGUN_Y', 'P1_MOUSE_X', 'P1_MOUSE_Y'],
            'special_function': ['P1_GAMBLE_HIGH', 'P1_GAMBLE_LOW']
        }
        
        # Process each control in the game data
        for player in game_data.get('players', []):
            for label in player.get('labels', []):
                control_name = label['name']
                
                # Get the functional category for this control
                func_category = 'other'  # Default to 'other'
                for category, controls in functional_categories.items():
                    if control_name in controls:
                        func_category = category
                        break
                        
                # Additional catch-all logic for controls not explicitly listed
                if func_category == 'other' and control_name.startswith('P1_'):
                    # Generic category assignment based on control name patterns
                    if 'BUTTON' in control_name:
                        # Try to determine which button category based on the button number
                        try:
                            button_num = int(control_name.replace('P1_BUTTON', ''))
                            if button_num <= 2:
                                func_category = 'action_primary'
                            elif button_num <= 4:
                                func_category = 'action_secondary'
                            else:
                                func_category = 'action_special'
                        except ValueError:
                            # If we can't parse a button number, keep as 'other'
                            pass
                    elif 'JOYSTICK' in control_name:
                        if 'LEFT' in control_name or 'RIGHT' in control_name:
                            func_category = 'move_horizontal'
                        elif 'UP' in control_name or 'DOWN' in control_name:
                            func_category = 'move_vertical'
                    elif 'AD_STICK_X' in control_name:
                        func_category = 'move_horizontal'
                    elif 'AD_STICK_Y' in control_name:
                        func_category = 'move_vertical'
                    elif 'AD_STICK_Z' in control_name:
                        func_category = 'analog_input'
                    elif 'DIAL' in control_name:
                        if 'V' in control_name or 'Y' in control_name:
                            func_category = 'move_vertical'
                        else:
                            func_category = 'move_horizontal'
                    elif 'TRACKBALL' in control_name or 'LIGHTGUN' in control_name or 'MOUSE' in control_name:
                        func_category = 'precision_aim'
                    elif 'START' in control_name or 'SELECT' in control_name or 'COIN' in control_name:
                        func_category = 'system_control'
                    elif 'PEDAL' in control_name:
                        func_category = 'analog_input'
                    elif 'PADDLE' in control_name:
                        func_category = 'analog_input'
                
                # Store the functional category
                label['func_category'] = func_category
                
                # Check if this control has a mapping in all_mappings
                if control_name in all_mappings:
                    mapping_info = all_mappings[control_name]
                    
                    # Add mapping information to the label
                    label['mapping'] = mapping_info['mapping']
                    label['mapping_source'] = mapping_info['source']
                    label['is_custom'] = 'ROM CFG' in mapping_info['source']
                    label['cfg_mapping'] = True
                    
                    # Also store the input mode
                    label['input_mode'] = self.input_mode
                    
                    # Special handling for increment/decrement pairs
                    if " ||| " in mapping_info['mapping']:
                        inc_mapping, dec_mapping = mapping_info['mapping'].split(" ||| ")
                        
                        # Process based on current input mode
                        if self.input_mode == 'xinput':
                            # Handle XInput format for both directions
                            if 'XINPUT' in inc_mapping and 'XINPUT' in dec_mapping:
                                # If either part is NONE, just show the other part
                                if inc_mapping == "NONE" and dec_mapping != "NONE":
                                    dec_friendly = self.get_friendly_xinput_name(dec_mapping)
                                    label['target_button'] = dec_friendly
                                elif dec_mapping == "NONE" and inc_mapping != "NONE":
                                    inc_friendly = self.get_friendly_xinput_name(inc_mapping)
                                    label['target_button'] = inc_friendly
                                else:
                                    # Both have values
                                    inc_friendly = self.get_friendly_xinput_name(inc_mapping)
                                    dec_friendly = self.get_friendly_xinput_name(dec_mapping)
                                    label['target_button'] = f"{inc_friendly} | {dec_friendly}"
                        elif self.input_mode == 'dinput':
                            # Handle DInput format for both directions
                            inc_converted = self.convert_mapping(inc_mapping, 'dinput')
                            dec_converted = self.convert_mapping(dec_mapping, 'dinput')
                            
                            if inc_mapping == "NONE" or inc_converted == "NONE":
                                dec_friendly = self.get_friendly_dinput_name(dec_converted) if 'DINPUT' in dec_converted else dec_converted
                                if dec_mapping != "NONE" and dec_friendly != "NONE":
                                    label['target_button'] = dec_friendly
                            elif dec_mapping == "NONE" or dec_converted == "NONE":
                                inc_friendly = self.get_friendly_dinput_name(inc_converted) if 'DINPUT' in inc_converted else inc_converted
                                if inc_mapping != "NONE" and inc_friendly != "NONE":
                                    label['target_button'] = inc_friendly
                            else:
                                # Both have values
                                inc_friendly = self.get_friendly_dinput_name(inc_converted) if 'DINPUT' in inc_converted else inc_converted
                                dec_friendly = self.get_friendly_dinput_name(dec_converted) if 'DINPUT' in dec_converted else dec_converted
                                label['target_button'] = f"{inc_friendly} | {dec_friendly}"
                        else:  # joycode mode
                            # Use direct JOYCODE formatting
                            if inc_mapping == "NONE":
                                label['target_button'] = self.format_joycode_display(dec_mapping)
                            elif dec_mapping == "NONE":
                                label['target_button'] = self.format_joycode_display(inc_mapping)
                            else:
                                inc_display = self.format_joycode_display(inc_mapping)
                                dec_display = self.format_joycode_display(dec_mapping)
                                label['target_button'] = f"{inc_display} | {dec_display}"
                    else:
                        # Regular mapping handling for standard controls
                        if self.input_mode == 'xinput' and 'XINPUT' in mapping_info['mapping']:
                            # Extract the button part for XInput
                            label['target_button'] = self.get_friendly_xinput_name(mapping_info['mapping'])
                        elif self.input_mode == 'dinput' and 'DINPUT' in mapping_info['mapping']:
                            # Extract the button part for DInput
                            label['target_button'] = self.get_friendly_dinput_name(mapping_info['mapping'])
                        elif self.input_mode == 'joycode' and 'JOYCODE' in mapping_info['mapping']:
                            # Format JOYCODE display
                            label['target_button'] = self.format_joycode_display(mapping_info['mapping'])
                        else:
                            # Try conversion if not in the right format
                            converted = self.convert_mapping(mapping_info['mapping'], self.input_mode)
                            if self.input_mode == 'xinput' and 'XINPUT' in converted:
                                label['target_button'] = self.get_friendly_xinput_name(converted)
                            elif self.input_mode == 'dinput' and 'DINPUT' in converted:
                                label['target_button'] = self.get_friendly_dinput_name(converted)
                            elif self.input_mode == 'joycode' and 'JOYCODE' in converted:
                                label['target_button'] = self.format_joycode_display(converted)
                            else:
                                # Fallback to original format
                                label['target_button'] = self.format_mapping_display(mapping_info['mapping'])
                    
                    # Add debug output
                    print(f"Applied mapping for {control_name}: {label['mapping']} from {label['mapping_source']} (Mode: {self.input_mode})")
                else:
                    label['is_custom'] = False
                    
                # Set appropriate display style based on function
                if func_category == 'move_horizontal':
                    label['display_style'] = 'horizontal'
                elif func_category == 'move_vertical':
                    label['display_style'] = 'vertical'
                elif func_category == 'action_primary':
                    label['display_style'] = 'primary_button'
                elif func_category == 'action_secondary':
                    label['display_style'] = 'secondary_button'
                elif func_category == 'system_control':
                    label['display_style'] = 'system_button'
                elif func_category == 'analog_input':
                    label['display_style'] = 'analog_control'
                elif func_category == 'precision_aim':
                    label['display_style'] = 'precision_control'
                elif func_category == 'special_function':
                    label['display_style'] = 'special_button'
                else:
                    label['display_style'] = 'standard'  # Default style for 'other' controls
                        
                # Set display name based on input mode conventions
                if 'target_button' in label:
                    # Always use target_button if available from mapping
                    if self.input_mode == 'dinput':
                        label['display_name'] = f'P1 {label["target_button"]}'
                    elif self.input_mode == 'joycode':
                        # Keep JOYCODE format
                        label['display_name'] = label["target_button"]
                    else:
                        # XInput format
                        label['display_name'] = f'P1 {label["target_button"]}'
                else:
                    # No mapping, use default display names based on input mode
                    if self.input_mode == 'dinput':
                        # DInput uses 0-based button numbers
                        if control_name.startswith('P1_BUTTON'):
                            button_num = int(control_name.replace('P1_BUTTON', '')) - 1
                            if button_num < 0:
                                button_num = 0
                            label['display_name'] = f'P1 Button {button_num}'
                        elif control_name == 'P1_JOYSTICK_UP':
                            label['display_name'] = 'P1 POV Up'
                        elif control_name == 'P1_JOYSTICK_DOWN':
                            label['display_name'] = 'P1 POV Down'
                        elif control_name == 'P1_JOYSTICK_LEFT':
                            label['display_name'] = 'P1 POV Left'
                        elif control_name == 'P1_JOYSTICK_RIGHT':
                            label['display_name'] = 'P1 POV Right'
                        else:
                            label['display_name'] = self.format_control_name(control_name)
                    elif self.input_mode == 'joycode':
                        # JOYCODE uses direct button numbers
                        if control_name.startswith('P1_BUTTON'):
                            button_num = control_name.replace('P1_BUTTON', '')
                            label['display_name'] = f'Joy 1 Button {button_num}'
                        elif control_name == 'P1_JOYSTICK_UP':
                            label['display_name'] = 'Joy Up'
                        elif control_name == 'P1_JOYSTICK_DOWN':
                            label['display_name'] = 'Joy Down'
                        elif control_name == 'P1_JOYSTICK_LEFT':
                            label['display_name'] = 'Joy Left'
                        elif control_name == 'P1_JOYSTICK_RIGHT':
                            label['display_name'] = 'Joy Right'
                        else:
                            label['display_name'] = control_name
                    else:
                        # XInput uses named buttons
                        if control_name == 'P1_BUTTON1':
                            label['display_name'] = 'P1 A Button'
                        elif control_name == 'P1_BUTTON2':
                            label['display_name'] = 'P1 B Button'
                        elif control_name == 'P1_BUTTON3':
                            label['display_name'] = 'P1 X Button'
                        elif control_name == 'P1_BUTTON4':
                            label['display_name'] = 'P1 Y Button'
                        elif control_name == 'P1_BUTTON5':
                            label['display_name'] = 'P1 LB Button'
                        elif control_name == 'P1_BUTTON6':
                            label['display_name'] = 'P1 RB Button'
                        elif control_name == 'P1_BUTTON7':
                            label['display_name'] = 'P1 LT Button'
                        elif control_name == 'P1_BUTTON8':
                            label['display_name'] = 'P1 RT Button'
                        elif control_name == 'P1_JOYSTICK_UP':
                            label['display_name'] = 'P1 LS Up'
                        elif control_name == 'P1_JOYSTICK_DOWN':
                            label['display_name'] = 'P1 LS Down'
                        elif control_name == 'P1_JOYSTICK_LEFT':
                            label['display_name'] = 'P1 LS Left'
                        elif control_name == 'P1_JOYSTICK_RIGHT':
                            label['display_name'] = 'P1 LS Right'
                        else:
                            label['display_name'] = self.format_control_name(control_name)

    def toggle_hide_preview_buttons(self):
        """Toggle whether preview buttons should be hidden"""
        if hasattr(self, 'hide_buttons_toggle'):
            self.hide_preview_buttons = self.hide_buttons_toggle.get()
            print(f"Hide preview buttons set to: {self.hide_preview_buttons}")
            
            # Save setting to config file
            self.save_settings()
        
    def save_settings(self):
        """Save current settings to the standard settings file"""
        settings = {
            "preferred_preview_screen": getattr(self, 'preferred_preview_screen', 1),
            "visible_control_types": getattr(self, 'visible_control_types', ["BUTTON", "JOYSTICK"]),
            "hide_preview_buttons": getattr(self, 'hide_preview_buttons', False),
            "show_button_names": getattr(self, 'show_button_names', True),
            "use_xinput": getattr(self, 'use_xinput', True),
            "xinput_only_mode": getattr(self, 'xinput_only_mode', True)  # Change to True
        }
        
        print(f"Debug - saving settings: {settings}")  # Add this debug line
        
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
                    
                # Load input mode setting (Now supports 'joycode', 'xinput', or 'dinput')
                if 'input_mode' in settings:
                    self.input_mode = settings.get('input_mode', 'xinput')
                    # Ensure valid value
                    if self.input_mode not in ['joycode', 'xinput', 'dinput']:
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
    
    def get_friendly_dinput_name(self, mapping: str) -> str:
        """Convert a DINPUT mapping code into a human-friendly button/stick name."""
        parts = mapping.split('_', 3)  # e.g., ["DINPUT", "1", "BUTTON0"]
        if len(parts) < 3:
            return mapping
        
        player_num = parts[1]
        action = parts[2]
        
        # Friendly labels for DInput controls
        if action.startswith("BUTTON"):
            button_num = action[6:]  # Extract number from 'BUTTON0'
            return f"Button {button_num}"
        elif action == "POV_UP":
            return f"POV Up"
        elif action == "POV_DOWN":
            return f"POV Down"
        elif action == "POV_LEFT":
            return f"POV Left"
        elif action == "POV_RIGHT":
            return f"POV Right"
        elif action == "XAXIS_NEG":
            return f"X-Axis Left"
        elif action == "XAXIS_POS":
            return f"X-Axis Right"
        elif action == "YAXIS_NEG":
            return f"Y-Axis Up"
        elif action == "YAXIS_POS":
            return f"Y-Axis Down"
        
        return f"DInput {player_num} {action}"  # Return a formatted string for unknown controls
    
    def convert_mapping(self, mapping: str, to_mode: str = None) -> str:
        """Convert between JOYCODE, XInput, and DInput mappings with support for increment/decrement pairs"""
        if not mapping:
            return mapping
            
        # Determine target mode if not explicitly specified
        if to_mode is None:
            to_mode = self.input_mode
        
        # Handle special format for increment/decrement pairs
        if " ||| " in mapping:
            # Split into increment and decrement parts
            inc_mapping, dec_mapping = mapping.split(" ||| ")
            
            # Convert each part separately
            inc_converted = self.convert_single_mapping(inc_mapping, to_mode)
            dec_converted = self.convert_single_mapping(dec_mapping, to_mode)
            
            # Return combined converted mapping
            return f"{inc_converted} ||| {dec_converted}"
        
        # For regular mappings, use the original logic
        return self.convert_single_mapping(mapping, to_mode)

    def convert_single_mapping(self, mapping: str, to_mode: str) -> str:
        """Convert a mapping string between JOYCODE, XInput, and DInput formats"""
        # If mapping contains multiple options (separated by OR)
        if " OR " in mapping:
            parts = mapping.split(" OR ")
            
            # Process based on target mode
            if to_mode == 'xinput':
                # First look for parts that are already in XInput format
                for part in parts:
                    part = part.strip()
                    if part.startswith('XINPUT'):
                        print(f"  Found XINPUT part in OR statement: {part}")
                        return part
                
                # No direct XInput mapping found, try to convert JOYCODE parts
                for part in parts:
                    if part.startswith('JOYCODE'):
                        converted = self.joycode_to_xinput(part.strip())
                        if converted.startswith('XINPUT'):
                            print(f"  Converting JOYCODE->XINPUT: {part} -> {converted}")
                            return converted
                        
            elif to_mode == 'dinput':
                # First look for parts that are already in DInput format
                for part in parts:
                    part = part.strip()
                    if part.startswith('DINPUT'):
                        return part
                
                # No direct DInput mapping found, try to convert JOYCODE parts
                for part in parts:
                    if part.startswith('JOYCODE'):
                        converted = self.joycode_to_dinput(part.strip())
                        if converted.startswith('DINPUT'):
                            print(f"  Converting JOYCODE->DINPUT: {part} -> {converted}")
                            return converted
                            
            elif to_mode == 'joycode':
                # First look for parts that are already in JOYCODE format
                for part in parts:
                    part = part.strip()
                    if part.startswith('JOYCODE'):
                        return part
                
                # Try to convert XInput to JOYCODE
                for part in parts:
                    if part.startswith('XINPUT'):
                        converted = self.xinput_to_joycode(part.strip())
                        if converted.startswith('JOYCODE'):
                            print(f"  Converting XINPUT->JOYCODE: {part} -> {converted}")
                            return converted
                            
                # Try to convert DInput to JOYCODE
                for part in parts:
                    if part.startswith('DINPUT'):
                        converted = self.dinput_to_joycode(part.strip())
                        if converted.startswith('JOYCODE'):
                            print(f"  Converting DINPUT->JOYCODE: {part} -> {converted}")
                            return converted
                        
            # If no conversion found, return the first part
            print(f"  No suitable conversion found, using first part: {parts[0]}")
            return parts[0].strip()
        
        # Simple direct conversion for individual mappings
        if mapping.startswith('JOYCODE'):
            if to_mode == 'xinput':
                return self.joycode_to_xinput(mapping)
            elif to_mode == 'dinput':
                return self.joycode_to_dinput(mapping)
        elif mapping.startswith('XINPUT'):
            if to_mode == 'joycode':
                return self.xinput_to_joycode(mapping)
            elif to_mode == 'dinput':
                return self.xinput_to_dinput(mapping)
        elif mapping.startswith('DINPUT'):
            if to_mode == 'joycode':
                return self.dinput_to_joycode(mapping)
            elif to_mode == 'xinput':
                return self.dinput_to_xinput(mapping)
        
        # If already in the right format or if no conversion found, return as is
        return mapping

    def joycode_to_xinput(self, mapping: str) -> str:
        """Convert JOYCODE to XInput format"""
        # Define XInput mapping dictionary
        xinput_mappings = {
            # Standard buttons
            'JOYCODE_1_BUTTON1': 'XINPUT_1_A',           # A Button
            'JOYCODE_1_BUTTON2': 'XINPUT_1_B',           # B Button
            'JOYCODE_1_BUTTON3': 'XINPUT_1_X',           # X Button
            'JOYCODE_1_BUTTON4': 'XINPUT_1_Y',           # Y Button
            'JOYCODE_1_BUTTON5': 'XINPUT_1_SHOULDER_L',  # Left Bumper
            'JOYCODE_1_BUTTON6': 'XINPUT_1_SHOULDER_R',  # Right Bumper
            'JOYCODE_1_BUTTON7': 'XINPUT_1_START',       # Start
            'JOYCODE_1_BUTTON8': 'XINPUT_1_BACK',        # Back/Select
            'JOYCODE_1_BUTTON9': 'XINPUT_1_THUMB_L',     # Left Stick Button
            'JOYCODE_1_BUTTON10': 'XINPUT_1_THUMB_R',    # Right Stick Button
            
            # D-pad
            'JOYCODE_1_HATUP': 'XINPUT_1_DPAD_UP',       # D-Pad Up
            'JOYCODE_1_HATDOWN': 'XINPUT_1_DPAD_DOWN',   # D-Pad Down
            'JOYCODE_1_HATLEFT': 'XINPUT_1_DPAD_LEFT',   # D-Pad Left
            'JOYCODE_1_HATRIGHT': 'XINPUT_1_DPAD_RIGHT', # D-Pad Right
            
            # Same mappings for player 2
            'JOYCODE_2_BUTTON1': 'XINPUT_2_A',
            'JOYCODE_2_BUTTON2': 'XINPUT_2_B',
            'JOYCODE_2_BUTTON3': 'XINPUT_2_X',
            'JOYCODE_2_BUTTON4': 'XINPUT_2_Y',
            'JOYCODE_2_BUTTON5': 'XINPUT_2_SHOULDER_L',
            'JOYCODE_2_BUTTON6': 'XINPUT_2_SHOULDER_R',
            'JOYCODE_2_BUTTON7': 'XINPUT_2_START',
            'JOYCODE_2_BUTTON8': 'XINPUT_2_BACK',
            'JOYCODE_2_BUTTON9': 'XINPUT_2_THUMB_L',
            'JOYCODE_2_BUTTON10': 'XINPUT_2_THUMB_R',
            # ... add more mappings as needed
        }
        
        if mapping in xinput_mappings:
            return xinput_mappings[mapping]
        return mapping

    def joycode_to_dinput(self, mapping: str) -> str:
        """Convert JOYCODE to DInput format"""
        # Define DInput mapping dictionary
        dinput_mappings = {
            # Standard buttons
            'JOYCODE_1_BUTTON1': 'DINPUT_1_BUTTON0',  # Button 0
            'JOYCODE_1_BUTTON2': 'DINPUT_1_BUTTON1',  # Button 1
            'JOYCODE_1_BUTTON3': 'DINPUT_1_BUTTON2',  # Button 2
            'JOYCODE_1_BUTTON4': 'DINPUT_1_BUTTON3',  # Button 3
            'JOYCODE_1_BUTTON5': 'DINPUT_1_BUTTON4',  # Button 4
            'JOYCODE_1_BUTTON6': 'DINPUT_1_BUTTON5',  # Button 5
            'JOYCODE_1_BUTTON7': 'DINPUT_1_BUTTON6',  # Button 6
            'JOYCODE_1_BUTTON8': 'DINPUT_1_BUTTON7',  # Button 7
            'JOYCODE_1_BUTTON9': 'DINPUT_1_BUTTON8',  # Button 8
            'JOYCODE_1_BUTTON10': 'DINPUT_1_BUTTON9', # Button 9
            
            # Same mappings for player 2
            'JOYCODE_2_BUTTON1': 'DINPUT_2_BUTTON0',
            'JOYCODE_2_BUTTON2': 'DINPUT_2_BUTTON1',
            'JOYCODE_2_BUTTON3': 'DINPUT_2_BUTTON2',
            'JOYCODE_2_BUTTON4': 'DINPUT_2_BUTTON3',
            'JOYCODE_2_BUTTON5': 'DINPUT_2_BUTTON4',
            'JOYCODE_2_BUTTON6': 'DINPUT_2_BUTTON5',
            'JOYCODE_2_BUTTON7': 'DINPUT_2_BUTTON6',
            'JOYCODE_2_BUTTON8': 'DINPUT_2_BUTTON7',
            'JOYCODE_2_BUTTON9': 'DINPUT_2_BUTTON8',
            'JOYCODE_2_BUTTON10': 'DINPUT_2_BUTTON9',
            # ... add more mappings as needed
        }
        
        if mapping in dinput_mappings:
            return dinput_mappings[mapping]
        return mapping

    def xinput_to_joycode(self, mapping: str) -> str:
        """Convert XInput to JOYCODE format"""
        # Define reverse mapping dictionary
        reverse_mappings = {
            'XINPUT_1_A': 'JOYCODE_1_BUTTON1',
            'XINPUT_1_B': 'JOYCODE_1_BUTTON2',
            'XINPUT_1_X': 'JOYCODE_1_BUTTON3',
            'XINPUT_1_Y': 'JOYCODE_1_BUTTON4',
            'XINPUT_1_SHOULDER_L': 'JOYCODE_1_BUTTON5',
            'XINPUT_1_SHOULDER_R': 'JOYCODE_1_BUTTON6',
            'XINPUT_1_START': 'JOYCODE_1_BUTTON7',
            'XINPUT_1_BACK': 'JOYCODE_1_BUTTON8',
            'XINPUT_1_THUMB_L': 'JOYCODE_1_BUTTON9',
            'XINPUT_1_THUMB_R': 'JOYCODE_1_BUTTON10',
            # ... add more mappings as needed
        }
        
        if mapping in reverse_mappings:
            return reverse_mappings[mapping]
        return mapping

    def xinput_to_dinput(self, mapping: str) -> str:
        """Convert XInput to DInput format"""
        # Define direct mapping dictionary
        mapping_dict = {
            'XINPUT_1_A': 'DINPUT_1_BUTTON0',
            'XINPUT_1_B': 'DINPUT_1_BUTTON1',
            'XINPUT_1_X': 'DINPUT_1_BUTTON2',
            'XINPUT_1_Y': 'DINPUT_1_BUTTON3',
            'XINPUT_1_SHOULDER_L': 'DINPUT_1_BUTTON4',
            'XINPUT_1_SHOULDER_R': 'DINPUT_1_BUTTON5',
            'XINPUT_1_START': 'DINPUT_1_BUTTON6',
            'XINPUT_1_BACK': 'DINPUT_1_BUTTON7',
            'XINPUT_1_THUMB_L': 'DINPUT_1_BUTTON8',
            'XINPUT_1_THUMB_R': 'DINPUT_1_BUTTON9',
            # ... add more mappings as needed
        }
        
        if mapping in mapping_dict:
            return mapping_dict[mapping]
        return mapping

    def dinput_to_joycode(self, mapping: str) -> str:
        """Convert DInput to JOYCODE format"""
        # Define reverse mapping dictionary
        reverse_mappings = {
            'DINPUT_1_BUTTON0': 'JOYCODE_1_BUTTON1',
            'DINPUT_1_BUTTON1': 'JOYCODE_1_BUTTON2',
            'DINPUT_1_BUTTON2': 'JOYCODE_1_BUTTON3',
            'DINPUT_1_BUTTON3': 'JOYCODE_1_BUTTON4',
            'DINPUT_1_BUTTON4': 'JOYCODE_1_BUTTON5',
            'DINPUT_1_BUTTON5': 'JOYCODE_1_BUTTON6',
            'DINPUT_1_BUTTON6': 'JOYCODE_1_BUTTON7',
            'DINPUT_1_BUTTON7': 'JOYCODE_1_BUTTON8',
            'DINPUT_1_BUTTON8': 'JOYCODE_1_BUTTON9',
            'DINPUT_1_BUTTON9': 'JOYCODE_1_BUTTON10',
            # ... add more mappings as needed
        }
        
        if mapping in reverse_mappings:
            return reverse_mappings[mapping]
        return mapping

    def dinput_to_xinput(self, mapping: str) -> str:
        """Convert DInput to XInput format"""
        # Define mapping dictionary
        mapping_dict = {
            'DINPUT_1_BUTTON0': 'XINPUT_1_A',
            'DINPUT_1_BUTTON1': 'XINPUT_1_B',
            'DINPUT_1_BUTTON2': 'XINPUT_1_X',
            'DINPUT_1_BUTTON3': 'XINPUT_1_Y',
            'DINPUT_1_BUTTON4': 'XINPUT_1_SHOULDER_L',
            'DINPUT_1_BUTTON5': 'XINPUT_1_SHOULDER_R',
            'DINPUT_1_BUTTON6': 'XINPUT_1_START',
            'DINPUT_1_BUTTON7': 'XINPUT_1_BACK',
            'DINPUT_1_BUTTON8': 'XINPUT_1_THUMB_L',
            'DINPUT_1_BUTTON9': 'XINPUT_1_THUMB_R',
            # ... add more mappings as needed
        }
        
        if mapping in mapping_dict:
            return mapping_dict[mapping]
        return mapping

    def format_joycode_display(self, mapping: str) -> str:
        """Format JOYCODE mapping string for display."""
        if not mapping or not "JOYCODE" in mapping:
            return mapping
            
        # Basic display for JOYCODE
        if "YAXIS_UP" in mapping or "DPADUP" in mapping:
            return "Joy Up"
        elif "YAXIS_DOWN" in mapping or "DPADDOWN" in mapping:
            return "Joy Down"
        elif "XAXIS_LEFT" in mapping or "DPADLEFT" in mapping:
            return "Joy Left"
        elif "XAXIS_RIGHT" in mapping or "DPADRIGHT" in mapping:
            return "Joy Right"
        elif "RYAXIS_NEG" in mapping:
            return "Joy R-Up"
        elif "RYAXIS_POS" in mapping:
            return "Joy R-Down"
        elif "RXAXIS_NEG" in mapping:
            return "Joy R-Left"
        elif "RXAXIS_POS" in mapping:
            return "Joy R-Right"
        
        # Standard joystick button formatting
        parts = mapping.split('_')
        if len(parts) >= 4:
            joy_num = parts[1]
            control_type = parts[2].capitalize()
            
            if control_type == "Button":
                button_num = parts[3]
                return f"Joy {joy_num} Btn {button_num}"
            else:
                remainder = '_'.join(parts[3:])
                return f"Joy {joy_num} {control_type} {remainder}"
                
        return mapping
    
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
    
    def format_mapping_display(self, mapping: str) -> str:
        """Format the mapping string for display using friendly names for the current input mode."""
        
        # Handle OR statements by finding matching parts
        if " OR " in mapping:
            parts = mapping.split(" OR ")
            
            # Find part matching the current input mode
            for part in parts:
                part = part.strip()
                if self.input_mode == 'xinput' and "XINPUT" in part:
                    mapping = part
                    break
                elif self.input_mode == 'dinput' and "DINPUT" in part:
                    mapping = part
                    break
                elif self.input_mode == 'joycode' and "JOYCODE" in part:
                    mapping = part
                    break
            
            # If no matching part found, convert first part to current mode
            if " OR " in mapping:
                mapping = parts[0].strip()
                converted = self.convert_mapping(mapping, self.input_mode)
                if converted != mapping:
                    mapping = converted
        
        # Format based on the current input mode
        if self.input_mode == 'xinput':
            if mapping.startswith("XINPUT"):
                return self.get_friendly_xinput_name(mapping)
            else:
                # Try to convert to XInput
                converted = self.convert_mapping(mapping, 'xinput')
                if converted.startswith("XINPUT"):
                    return self.get_friendly_xinput_name(converted)
        
        elif self.input_mode == 'dinput':
            if mapping.startswith("DINPUT"):
                return self.get_friendly_dinput_name(mapping)
            else:
                # Try to convert to DInput
                converted = self.convert_mapping(mapping, 'dinput')
                if converted.startswith("DINPUT"):
                    return self.get_friendly_dinput_name(converted)
        
        elif self.input_mode == 'joycode':
            if "JOYCODE" in mapping:
                # Format JOYCODE mappings nicely
                if "YAXIS_UP" in mapping or "DPADUP" in mapping:
                    return "Joy Up"
                elif "YAXIS_DOWN" in mapping or "DPADDOWN" in mapping:
                    return "Joy Down"
                elif "XAXIS_LEFT" in mapping or "DPADLEFT" in mapping:
                    return "Joy Left"
                elif "XAXIS_RIGHT" in mapping or "DPADRIGHT" in mapping:
                    return "Joy Right"
                elif "RYAXIS_NEG" in mapping:
                    return "Joy R-Up"
                elif "RYAXIS_POS" in mapping:
                    return "Joy R-Down"
                elif "RXAXIS_NEG" in mapping:
                    return "Joy R-Left"
                elif "RXAXIS_POS" in mapping:
                    return "Joy R-Right"
                
                # Standard joystick button formatting
                parts = mapping.split('_')
                if len(parts) >= 4:
                    joy_num = parts[1]
                    control_type = parts[2].capitalize()
                    
                    if control_type == "Button":
                        button_num = parts[3]
                        return f"Joy {joy_num} Btn {button_num}"
                    else:
                        remainder = '_'.join(parts[3:])
                        return f"Joy {joy_num} {control_type} {remainder}"
            else:
                # Try to convert to JOYCODE
                converted = self.convert_mapping(mapping, 'joycode')
                if "JOYCODE" in converted:
                    # Recursive call to format the converted mapping
                    return self.format_mapping_display(converted)
        
        # For keyboard mappings, convert to "Key X" format
        if mapping.startswith("KEYCODE"):
            key_name = mapping.replace("KEYCODE_", "")
            return f"Key {key_name}"

        # Fallback to original mapping if no conversion was possible
        return mapping

    def select_first_rom(self):
        """Select the first available ROM in the listbox"""
        # Check if we have any ROMs
        if not self.available_roms:
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

    def display_controls_table(self, start_row, game_data, cfg_controls):
        """Display controls using a canvas-based approach for significantly better performance"""
        row = start_row
        
        # Get romname from game_data
        romname = game_data.get('romname', '')
        
        # Clear existing controls first
        for widget in self.control_frame.winfo_children():
            widget.destroy()
        
        # Game info card - for the header section
        info_card = ctk.CTkFrame(self.control_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        info_card.pack(fill="x", padx=10, pady=10, expand=True)
        
        # Configure the info_card for proper expansion
        info_card.columnconfigure(0, weight=1)
        
        # Game metadata section
        metadata_frame = ctk.CTkFrame(info_card, fg_color="transparent")
        metadata_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        
        # Two-column layout for metadata with proper expansion
        metadata_frame.columnconfigure(0, weight=1)
        metadata_frame.columnconfigure(1, weight=1)
        
        # Left column - Basic info
        basic_info = ctk.CTkFrame(metadata_frame, fg_color="transparent")
        basic_info.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        basic_info.columnconfigure(0, weight=1)
        
        # ROM info
        ctk.CTkLabel(
            basic_info,
            text="ROM Information",
            font=("Arial", 14, "bold"),
            anchor="w"
        ).pack(anchor="w", pady=(0, 10), fill="x")
        
        info_text = f"ROM Name: {game_data['romname']}\n"
        info_text += f"Players: {game_data['numPlayers']}\n"
        info_text += f"Alternating Play: {'Yes' if game_data['alternating'] else 'No'}\n"
        info_text += f"Mirrored Controls: {'Yes' if game_data.get('mirrored', False) else 'No'}"
        
        ctk.CTkLabel(
            basic_info,
            text=info_text,
            font=("Arial", 13),
            justify="left",
            anchor="w"
        ).pack(anchor="w", fill="x")
        
        # Right column - Additional info
        if game_data.get('miscDetails'):
            additional_info = ctk.CTkFrame(metadata_frame, fg_color="transparent")
            additional_info.grid(row=0, column=1, sticky="ew", padx=(10, 0))
            additional_info.columnconfigure(0, weight=1)
            
            ctk.CTkLabel(
                additional_info,
                text="Additional Details",
                font=("Arial", 14, "bold"),
                anchor="w"
            ).pack(anchor="w", pady=(0, 10), fill="x")
            
            ctk.CTkLabel(
                additional_info,
                text=game_data['miscDetails'],
                font=("Arial", 13),
                justify="left",
                anchor="w",
                wraplength=300
            ).pack(anchor="w", fill="x")
        
        # Add indicators for config sources and input mode
        indicator_frame = ctk.CTkFrame(info_card, fg_color="transparent")
        indicator_frame.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="ew")

        # First check if ROM CFG actually contains control mappings
        has_rom_cfg = False
        has_default_cfg = hasattr(self, 'default_controls') and bool(self.default_controls)
        has_gamedata = bool(game_data.get('players', []))

        # See if this ROM has a custom config with actual control mappings
        if romname in self.custom_configs:
            # Parse the custom config to check if it has any control mappings
            parsed_controls = self.parse_cfg_controls(self.custom_configs[romname])
            if parsed_controls:
                has_rom_cfg = True
                print(f"ROM {romname} has {len(parsed_controls)} control mappings in its cfg file")

        # Determine the primary source based on controls actually used
        if has_rom_cfg and cfg_controls:
            primary_source = "ROM CFG"
            primary_color = self.theme_colors["success"]
        elif has_default_cfg:
            primary_source = "Default CFG"
            primary_color = self.theme_colors["primary"]
        else:
            primary_source = "Game Data"
            primary_color = "#888888"
        
        # Display source indicator
        ctk.CTkLabel(
            indicator_frame,
            text="Control Source: ",
            font=("Arial", 13),
            anchor="w"
        ).pack(side="left", padx=(0, 5))
        
        # Color code based on source
        primary_color = self.theme_colors["success"] if primary_source == "ROM CFG" else \
                    self.theme_colors["primary"] if primary_source == "Default CFG" else \
                    "#888888"  # Game Data
        
        ctk.CTkLabel(
            indicator_frame,
            text=primary_source,
            font=("Arial", 13, "bold"),
            text_color=primary_color,
            anchor="w"
        ).pack(side="left")
        
        # Show 'XInput Mode' indicator (always showing XInput now)
        ctk.CTkLabel(
            indicator_frame,
            text="  |  Input Mode: ",
            font=("Arial", 13),
            anchor="w"
        ).pack(side="left", padx=(10, 5))
        
        ctk.CTkLabel(
            indicator_frame,
            text="XInput Mode",
            font=("Arial", 13, "bold"),
            text_color=self.theme_colors["primary"],
            anchor="w"
        ).pack(side="left")
        
        # Show ROM CFG filename if applicable
        if has_rom_cfg:
            ctk.CTkLabel(
                indicator_frame,
                text=f"  |  ROM CFG: ",
                font=("Arial", 13),
                anchor="w"
            ).pack(side="left", padx=(10, 0))
            
            ctk.CTkLabel(
                indicator_frame,
                text=f"{romname}.cfg",
                font=("Arial", 13, "bold"),
                text_color=self.theme_colors["success"],
                anchor="w"
            ).pack(side="left")
        
        row += 1
        
        # Controls card - container for the canvas approach
        controls_card = ctk.CTkFrame(self.control_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        controls_card.pack(fill="x", padx=10, pady=10, expand=True)
        
        # Configure grid for full width expansion
        controls_card.columnconfigure(0, weight=1)
        
        # Create a frame for title and edit button
        title_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(15, 10))
        
        # Add input mode toggle
        input_mode_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        input_mode_frame.pack(fill="x", padx=15, pady=(5, 10))

        # Label
        ctk.CTkLabel(
            input_mode_frame,
            text="Input Mode:",
            font=("Arial", 13),
            anchor="w"
        ).pack(side="left", padx=(0, 10))

        # Create radio buttons for each input mode
        self.input_mode_var = tk.StringVar(value=self.input_mode)

        mode_joycode = ctk.CTkRadioButton(
            input_mode_frame,
            text="JOYCODE",
            variable=self.input_mode_var,
            value="joycode",
            command=self.toggle_input_mode,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        mode_joycode.pack(side="left", padx=(0, 15))

        mode_xinput = ctk.CTkRadioButton(
            input_mode_frame,
            text="XInput",
            variable=self.input_mode_var,
            value="xinput",
            command=self.toggle_input_mode,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        mode_xinput.pack(side="left", padx=(0, 15))

        mode_dinput = ctk.CTkRadioButton(
            input_mode_frame,
            text="DInput",
            variable=self.input_mode_var,
            value="dinput",
            command=self.toggle_input_mode,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        )
        mode_dinput.pack(side="left")
        
        # Title on the left
        ctk.CTkLabel(
            title_frame,
            text="Player 1 Controller Mappings",  # Updated to specify Player 1
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(side="left", anchor="w")
        
        # Edit button on the right
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
        
        # Container for the canvas and scrollbar
        canvas_container = ctk.CTkFrame(controls_card, fg_color="transparent")
        canvas_container.pack(fill="both", expand=True, padx=15, pady=5)
        
        # Create the header
        header_frame = ctk.CTkFrame(canvas_container, fg_color=self.theme_colors["primary"], height=36)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.pack_propagate(False)  # Fix the height
        
        # Header column widths (in pixels) - UPDATED for 4 columns
        col_widths = [180, 200, 180, 160]  # Adjusted width for 4 columns

        # Create header labels - UPDATED for 4 columns with improved alignment
        header_titles = ["MAME Control", "Controller Input", "Game Action", "Mapping Source"]

        # Calculate consistent x positions for both headers and content
        x_positions = [15]  # Start with padding for first column
        for i in range(1, len(header_titles)):
            x_positions.append(x_positions[i-1] + col_widths[i-1] + 15)  # Previous position + width + padding

        # Place header labels using consistent positions
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
        
        # When collecting controls, add this debug print
        all_controls = []
        #print(f"DEBUG: Starting to collect Player 1 controls")
        
        for player in game_data.get('players', []):
            player_num = player.get('number')
            #print(f"DEBUG: Player {player_num} has {len(player.get('labels', []))} labels")
            
            if player.get('number') == 1:  # Only include Player 1
                for label in player.get('labels', []):
                    # Add debug information
                    control_name = label['name']
                    action = label['value']
                    #print(f"DEBUG: Processing control {control_name}: {action}")
                    
                    # For AD_STICK controls, ensure they're processed
                    if "AD_STICK" in control_name:
                        #print(f"DEBUG: Found AD_STICK control: {control_name}")
                        # Force flag to true for these controls
                        label['is_custom'] = control_name in cfg_controls
                        # Set display mode to ensure it shows up
                        if "AD_STICK_X" in control_name:
                            label['display_style'] = 'move_horizontal'
                        elif "AD_STICK_Y" in control_name:
                            label['display_style'] = 'move_vertical'
                        elif "AD_STICK_Z" in control_name:
                            label['display_style'] = 'analog_input'
                    
                    # Determine mapping information
                    is_custom = control_name in cfg_controls
                    is_default = not is_custom and hasattr(self, 'default_controls') and control_name in self.default_controls
                    
                    if is_custom:
                        mapping_source = f"ROM CFG ({romname}.cfg)"
                        mapping_value = cfg_controls[control_name]
                    elif is_default:
                        mapping_source = "Default CFG"
                        default_mapping = self.default_controls[control_name]
                        # Always convert to XInput
                        mapping_value = self.convert_mapping(default_mapping, 'xinput')
                    else:
                        mapping_source = "Game Data"
                        mapping_value = ""
                    
                    # Add to the list
                    control_data = {
                        'name': control_name,
                        'action': action,
                        'mapping': mapping_value,
                        'is_custom': is_custom,
                        'is_default': is_default,
                        'source': mapping_source
                    }
                    
                    # Extract display name from the label for display
                    if 'target_button' in label:
                        control_data['display_name'] = f"P1 {label['target_button']}"
                    elif 'display_name' in label:
                        control_data['display_name'] = label['display_name']
                    else:
                        control_data['display_name'] = self.format_control_name(control_name)
                    
                    all_controls.append(control_data)
        
        # Sort controls to keep a consistent order (BUTTON1, BUTTON2, etc.)
        all_controls.sort(key=lambda c: c['name'])
        
        print(f"Displaying {len(all_controls)} Player 1 controls for {romname}")
        
        # Create a canvas for the controls list with NATIVE Tkinter canvas (not CTk)
        # This is MUCH faster than using CTk widgets for the list items
        canvas_height = min(400, len(all_controls) * 40 + 10)  # Limit initial height, with 40px per row
        
        # We're using a tk.Canvas (not CTk) for maximum performance
        # This avoids the double-rendering overhead of CTk
        canvas = tk.Canvas(
            canvas_container,
            height=canvas_height,
            background=self.theme_colors["card_bg"],  # Use card_bg for light gray like left frame
            highlightthickness=0,
            bd=0
        )
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Create scrollbar for the canvas - use CTkScrollbar for consistent styling
        scrollbar = ctk.CTkScrollbar(
            canvas_container, 
            orientation="vertical",
            command=canvas.yview,
            button_color=self.theme_colors["primary"],         # Primary color for scrollbar thumb
            button_hover_color=self.theme_colors["secondary"], # Secondary color for hover
            fg_color=self.theme_colors["card_bg"],             # Match the frame background color
            corner_radius=10,                                  # Rounded corners
            width=14                                           # Make it slightly narrower for more pronounced curves
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Configure the canvas scrolling
        def on_canvas_yscroll(*args):
            canvas.yview_moveto(args[0])
            
        scrollbar.configure(command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create a frame inside the canvas to hold the controls
        controls_frame = tk.Frame(canvas, background=self.theme_colors["card_bg"])  # Match the canvas background
        canvas_window = canvas.create_window((0, 0), window=controls_frame, anchor=tk.NW)
        
        # Helper function to check if text fits in allocated width
        def text_fits_width(text, font, width):
            """Check if text fits within the given width"""
            try:
                # Create a temporary label to measure text
                temp_label = tk.Label(controls_frame, text=text, font=font)
                temp_label.update_idletasks()
                text_width = temp_label.winfo_reqwidth()
                temp_label.destroy()
                return text_width <= width
            except:
                return True  # If measurement fails, assume it fits
        
        def truncate_text_with_ellipsis(text, font, max_width):
            """Truncate text to fit within max_width and add ellipsis if needed"""
            if text_fits_width(text, font, max_width):
                return text, False  # Text fits, no truncation needed
            
            # Binary search to find the longest text that fits
            ellipsis = "..."
            left, right = 0, len(text)
            best_fit = ""
            
            while left <= right:
                mid = (left + right) // 2
                test_text = text[:mid] + ellipsis
                
                if text_fits_width(test_text, font, max_width):
                    best_fit = test_text
                    left = mid + 1
                else:
                    right = mid - 1
            
            return best_fit if best_fit else ellipsis, True  # Return truncated text and truncation flag
        
        def create_tooltip(parent_widget, full_text):
            """Create a tooltip that shows the full text on hover"""
            tooltip_window = None
            
            def show_tooltip(event):
                nonlocal tooltip_window
                if tooltip_window:
                    return  # Tooltip already showing
                    
                x = event.x_root + 10
                y = event.y_root + 10
                
                # Create tooltip window
                tooltip_window = tk.Toplevel(parent_widget)
                tooltip_window.wm_overrideredirect(True)
                tooltip_window.wm_geometry(f"+{x}+{y}")
                tooltip_window.configure(background="#333333", bd=1, relief="solid")
                
                # Create content frame with padding
                content_frame = tk.Frame(tooltip_window, background="#333333", bd=0)
                content_frame.pack(padx=5, pady=5)
                
                # Add the full text
                tip_label = tk.Label(
                    content_frame,
                    text=full_text,
                    background="#333333",
                    foreground="white",
                    font=("Arial", 11),
                    justify="left",
                    wraplength=400  # Allow wrapping for very long text
                )
                tip_label.pack()
                
                # Auto-destroy after 5 seconds
                tooltip_window.after(5000, hide_tooltip)
            
            def hide_tooltip(event=None):
                nonlocal tooltip_window
                if tooltip_window:
                    try:
                        tooltip_window.destroy()
                    except:
                        pass
                    tooltip_window = None
            
            # Bind hover events
            parent_widget.bind("<Enter>", show_tooltip)
            parent_widget.bind("<Leave>", hide_tooltip)
            parent_widget.bind("<Button-1>", hide_tooltip)  # Hide on click
        
        # If there are no controls to display
        if not all_controls:
            empty_frame = tk.Frame(controls_frame, background=self.theme_colors["card_bg"], height=60)
            empty_frame.pack(fill=tk.X, pady=10)
            
            # No matching controls message with consistent font
            tk.Label(
                empty_frame,
                text="No controller mappings found for Player 1",
                font=("Arial", 13),  # Match CTk font style
                foreground=self.theme_colors["text_dimmed"],
                background=self.theme_colors["card_bg"]  # Match the frame background
            ).pack(fill=tk.BOTH, expand=True, pady=20)
        else:
            # CRITICAL OPTIMIZATION: Create rows directly with tk widgets, not CTk
            # This eliminates the double-rendering overhead of CTk
            max_rows = 100  # Show up to 100 controls without a "Load more" button
            visible_rows = min(max_rows, len(all_controls))
            
            # Use a single consistent background color matching card_bg
            bg_color = self.theme_colors["card_bg"]

            # When creating each row:
            for i in range(visible_rows):
                control = all_controls[i]
                control_name = control['name']
                action = control['action']
                
                # Special case for analog controls which may not have mappings
                is_analog_control = ("AD_STICK" in control_name or 
                                    "DIAL" in control_name or 
                                    "PEDAL" in control_name or 
                                    "PADDLE" in control_name or 
                                    "TRACKBALL" in control_name or
                                    "LIGHTGUN" in control_name or
                                    "MOUSE" in control_name)
                
                # Process mapping with OR statements or increment/decrement pairs
                mapping_value = control.get('mapping', '')
                primary_mapping = ""
                all_mappings = []
                display_text = ""

                # Special handling for increment/decrement pairs
                if " ||| " in mapping_value:
                    # Split into increment and decrement parts
                    inc_mapping, dec_mapping = mapping_value.split(" ||| ")
                    
                    # Format each part
                    inc_display = self.format_mapping_display(inc_mapping)
                    dec_display = self.format_mapping_display(dec_mapping)
                    
                    # Combine with a vertical bar
                    display_text = f"{inc_display} | {dec_display}"
                    all_mappings = [inc_display, dec_display]
                    primary_mapping = display_text
                # Handle OR statements
                elif " OR " in mapping_value:
                    # This is the existing code for OR statements
                    mapping_parts = mapping_value.split(" OR ")
                    
                    # Look for parts matching the current input mode
                    joycode_part = None
                    for part in mapping_parts:
                        part = part.strip()
                        if self.input_mode == 'xinput' and "JOYCODE" in part:
                            joycode_part = part
                            # Convert the JOYCODE part to the current input mode
                            converted = self.convert_mapping(joycode_part, self.input_mode)
                            if "XINPUT" in converted:
                                primary_mapping = self.get_friendly_xinput_name(converted)
                                break
                        elif self.input_mode == 'dinput' and "JOYCODE" in part:
                            joycode_part = part
                            converted = self.convert_mapping(joycode_part, self.input_mode)
                            if "DINPUT" in converted:
                                primary_mapping = self.get_friendly_dinput_name(converted)
                                break
                        elif self.input_mode == 'joycode' and "JOYCODE" in part:
                            joycode_part = part
                            primary_mapping = self.format_joycode_display(joycode_part)
                            break
                    
                    # Only proceed with normal processing if no JOYCODE part was found or converted
                    if not primary_mapping:
                        # Get all formatted mappings for tooltip
                        for part in mapping_parts:
                            if "XINPUT" in part:
                                primary_mapping = self.get_friendly_xinput_name(part)
                            elif "JOYCODE" in part:
                                # Try to convert JOYCODE to XINPUT
                                converted = self.convert_mapping(part, 'xinput')
                                if "XINPUT" in converted:
                                    primary_mapping = self.get_friendly_xinput_name(converted)
                    
                    # If no XINPUT mapping found, use first mapping as primary
                    if not primary_mapping and all_mappings:
                        primary_mapping = all_mappings[0]
                        
                    # Create display text with counter
                    if len(all_mappings) > 1:
                        display_text = f"{primary_mapping} (+{len(all_mappings)-1})"
                    else:
                        display_text = primary_mapping
                elif mapping_value:
                    # Use the appropriate display format based on current input mode
                    if self.input_mode == 'xinput':
                        if "XINPUT" in mapping_value:
                            display_text = self.get_friendly_xinput_name(mapping_value)
                        else:
                            # Try to convert to XInput
                            converted = self.convert_mapping(mapping_value, 'xinput')
                            if "XINPUT" in converted:
                                display_text = self.get_friendly_xinput_name(converted)
                            else:
                                display_text = self.format_mapping_display(mapping_value)
                    elif self.input_mode == 'dinput':
                        if "DINPUT" in mapping_value:
                            display_text = self.get_friendly_dinput_name(mapping_value)
                        else:
                            # Try to convert to DInput
                            converted = self.convert_mapping(mapping_value, 'dinput')
                            if "DINPUT" in converted:
                                display_text = self.get_friendly_dinput_name(converted)
                            else:
                                display_text = self.format_mapping_display(mapping_value)
                    else:  # joycode mode
                        if "JOYCODE" in mapping_value:
                            display_text = self.format_joycode_display(mapping_value)
                        else:
                            # Try to convert to Joycode
                            converted = self.convert_mapping(mapping_value, 'joycode')
                            if "JOYCODE" in converted:
                                display_text = self.format_joycode_display(converted)
                            else:
                                display_text = self.format_mapping_display(mapping_value)
                    all_mappings = [display_text]
                else:
                    # No mapping - for analog controls show a description
                    if is_analog_control:
                        if "AD_STICK_X" in control_name:
                            display_text = "Left/Right Controls"
                        elif "AD_STICK_Y" in control_name:
                            display_text = "Up/Down Controls"
                        elif "AD_STICK_Z" in control_name:
                            display_text = "Throttle Controls"
                        elif "DIAL" in control_name:
                            display_text = "Dial Controls"
                        elif "PADDLE" in control_name:
                            display_text = "Paddle Controls"
                        elif "PEDAL" in control_name:
                            display_text = "Pedal Controls"
                        elif "TRACKBALL" in control_name or "MOUSE" in control_name or "LIGHTGUN" in control_name:
                            display_text = "Positional Controls"
                        else:
                            display_text = "Analog Controls"
                        all_mappings = [display_text]
                
                # Determine actual mapping source by checking if mapping exists
                if control_name in cfg_controls and cfg_controls[control_name].strip() not in ["", "NONE"]:
                    source = f"ROM CFG ({romname}.cfg)"
                    source_color = self.theme_colors["success"]  # Green for ROM CFG
                elif hasattr(self, 'default_controls') and control_name in self.default_controls:
                    source = "Default CFG"
                    source_color = self.theme_colors["primary"]  # Primary color for Default CFG
                else:
                    source = "Game Data"  
                    source_color = "#888888"  # Gray for Game Data
                
                # Create row container with consistent background
                row_height = 40
                row_frame = tk.Frame(
                    controls_frame,
                    background=bg_color,
                    height=row_height
                )
                row_frame.pack(fill=tk.X, pady=1, expand=True)
                row_frame.pack_propagate(False)  # Keep fixed height
                
                # Column 1: Raw MAME Control Name (new column!)
                control_name = control['name']
                
                # Column 2: Display Name (Controller Input) - THE ENHANCED COLUMN
                display_name = control.get('display_name', self.format_control_name(control['name']))
                
                # Check if the controller input text needs truncation
                controller_input_font = ("Arial", 13)
                original_display_text = display_text if display_text else ("Analog Control" if is_analog_control else "")
                truncated_text, was_truncated = truncate_text_with_ellipsis(
                    original_display_text, 
                    controller_input_font, 
                    col_widths[1] - 10  # Account for padding
                )
                
                # Column 3: Game Action
                action = control['action']
                
                # Column 4: Source (optional - could keep or remove this)
                source = control.get('source', '')
                if not source and is_analog_control:
                    source = "Game Data"  # Default source for analog controls
                
                # Column 1: Raw MAME Control Name
                label1 = tk.Label(
                    row_frame,
                    text=control_name,
                    font=("Consolas", 12),
                    anchor="w",
                    justify="left",
                    background=bg_color,
                    foreground="#888888"
                )
                label1.place(x=x_positions[0], y=10, width=col_widths[0])
                
                # Column 2: Controller Input with hover tooltip - ENHANCED VERSION
                label2 = tk.Label(
                    row_frame,
                    text=truncated_text,
                    font=controller_input_font,
                    anchor="w",
                    justify="left",
                    background=bg_color,
                    foreground=self.theme_colors["primary"]
                )
                label2.place(x=x_positions[1], y=10, width=col_widths[1])
                
                # Add tooltip if text was truncated
                if was_truncated and original_display_text:
                    create_tooltip(label2, original_display_text)
                    # Visual indicator that there's more content (subtle color change)
                    label2.configure(foreground=self.theme_colors["secondary"])
                
                # Column 3: Game Action
                label3 = tk.Label(
                    row_frame,
                    text=action,
                    font=("Arial", 13, "bold"),
                    anchor="w",
                    justify="left",
                    background=bg_color,
                    foreground=self.theme_colors["text"]
                )
                label3.place(x=x_positions[2], y=10, width=col_widths[2])
                
                # Column 4: Mapping Source - with appropriate styling based on source
                # Determine source color based on type
                # Column 4: Mapping Source - with more compact display
                display_source = source
                if "ROM CFG" in source:
                    display_source = "ROM CFG"
                elif "Default CFG" in source:
                    display_source = "Default CFG"
                else:
                    display_source = "Game Data"

                label4 = tk.Label(
                    row_frame,
                    text=display_source,
                    font=("Arial", 12),
                    anchor="w",
                    justify="left",
                    background=bg_color,
                    foreground=source_color
                )
                label4.place(x=x_positions[3], y=10, width=col_widths[3])

                # Add tooltip to show full source on hover (only for ROM CFG)
                if "ROM CFG" in source:
                    def show_tooltip(event, full_text=source):
                        tooltip = tk.Toplevel(row_frame)
                        tooltip.wm_overrideredirect(True)
                        tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
                        tooltip.configure(background="#333333", bd=1, relief="solid")
                        
                        padding_frame = tk.Frame(tooltip, background="#333333", bd=2)
                        padding_frame.pack()
                        
                        tip_label = tk.Label(
                            padding_frame, 
                            text=full_text, 
                            background="#333333", 
                            foreground="white",
                            font=("Arial", 11),
                            justify="left"
                        )
                        tip_label.pack()
                        
                        # Store reference and schedule cleanup
                        label4.tooltip = tooltip
                        row_frame.after(3000, tooltip.destroy)

                    def hide_tooltip(event):
                        if hasattr(label4, "tooltip") and label4.tooltip:
                            label4.tooltip.destroy()
                            label4.tooltip = None

                    # Bind hover events
                    label4.bind("<Enter>", lambda e: show_tooltip(e))
                    label4.bind("<Leave>", hide_tooltip)
        
        # Update the canvas scroll region
        def update_canvas_width(event=None):
            # Set the proper width for controls_frame to match canvas width
            canvas_width = canvas.winfo_width()
            canvas.itemconfig(canvas_window, width=canvas_width)
            
            # Make sure all row frames fill the width
            for child in controls_frame.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(width=canvas_width)
        
        # Bind resize event
        canvas.bind("<Configure>", update_canvas_width)
            
        controls_frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        
        # Initial call to set correct widths
        canvas.update_idletasks()
        update_canvas_width()
        
        # Display raw custom config if it exists
        if romname in self.custom_configs:
            config_card = ctk.CTkFrame(self.control_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
            config_card.pack(fill="x", padx=10, pady=10, expand=True)
            
            # Configure grid for proper expansion
            config_card.columnconfigure(0, weight=1)
            
            # Card title with indicator
            cfg_title_frame = ctk.CTkFrame(config_card, fg_color="transparent")
            cfg_title_frame.pack(fill="x", padx=15, pady=(15, 10))
            
            ctk.CTkLabel(
                cfg_title_frame,
                text="Custom Configuration File",
                font=("Arial", 16, "bold"),
                anchor="w"
            ).pack(side="left")
            
            # Add an indicator for the file
            ctk.CTkLabel(
                cfg_title_frame,
                text=f"({romname}.cfg)",
                font=("Arial", 12),
                text_color=self.theme_colors["text_dimmed"],
                anchor="w"
            ).pack(side="left", padx=(10, 0))
            
            # Add a button to view the full config
            view_button = ctk.CTkButton(
                config_card,
                text="View Full Config",
                command=lambda r=romname: self.show_custom_config(r),
                fg_color=self.theme_colors["primary"],
                hover_color=self.theme_colors["button_hover"],
                width=120,
                height=28
            )
            view_button.pack(anchor="e", padx=15, pady=(0, 10))
            
            # Config preview (first few lines)
            config_preview = ctk.CTkTextbox(
                config_card, 
                font=("Consolas", 12),
                height=100,
                fg_color=self.theme_colors["background"]
            )
            config_preview.pack(fill="x", padx=15, pady=(0, 15), expand=True)
            
            # Get first few lines of the config
            config_lines = self.custom_configs[romname].split('\n')
            preview_text = '\n'.join(config_lines[:10])
            if len(config_lines) > 10:
                preview_text += '\n...'
            
            config_preview.insert("1.0", preview_text)
            config_preview.configure(state="disabled")  # Make read-only
            
            row += 1
        
        # Update and save cache
        try:
            if hasattr(self, 'cache_dir') and self.cache_dir:
                # Create cache directory if it doesn't exist
                os.makedirs(self.cache_dir, exist_ok=True)
                
                # IMPORTANT: If in XInput Only mode, filter game_data before caching
                if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
                    # Filter the game data to only include XInput controls
                    cache_game_data = self.filter_xinput_controls(game_data)
                    cache_path = os.path.join(self.cache_dir, f"{romname}_cache.json")
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(cache_game_data, f, indent=2)
                    # Also update in-memory cache
                    if hasattr(self, 'rom_data_cache'):
                        self.rom_data_cache[romname] = cache_game_data
                else:
                    # Standard caching
                    cache_path = os.path.join(self.cache_dir, f"{romname}_cache.json")
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(game_data, f, indent=2)
                    # Also update in-memory cache
                    if hasattr(self, 'rom_data_cache'):
                        self.rom_data_cache[romname] = game_data
        except Exception as e:
            print(f"Warning: Could not update cache: {e}")
        
        return row

    def toggle_input_mode(self):
        """Handle toggling between input modes (JOYCODE, XInput, DInput)"""
        if hasattr(self, 'input_mode_var'):
            # Get the current toggle state
            old_mode = self.input_mode
            self.input_mode = self.input_mode_var.get()
            print(f"Input mode changed from {old_mode} to {self.input_mode}")
            
            # Save the setting
            self.save_settings()
            
            # Clear cache for current game
            if self.current_game and hasattr(self, 'rom_data_cache') and self.current_game in self.rom_data_cache:
                print(f"Clearing ROM data cache for {self.current_game} due to input mode change")
                del self.rom_data_cache[self.current_game]
                
                # Also clear cache file if it exists
                cache_file = os.path.join(self.cache_dir, f"{self.current_game}_cache.json")
                if os.path.exists(cache_file):
                    try:
                        os.remove(cache_file)
                        print(f"Removed cache file for {self.current_game}")
                    except Exception as e:
                        print(f"Error removing cache file: {e}")
            
            # Refresh the current game display if one is selected
            if self.current_game:
                # Force full refresh of display with current input mode
                self.display_game_info(self.current_game)
                
                # Update status message
                self.update_status_message(f"Input mode changed to {self.input_mode.upper()}")
        
    def update_stats_label(self):
        """Update the statistics label with enhanced formatting including clone stats"""
        try:
            unmatched = len(self.find_unmatched_roms())
            matched = len(self.available_roms) - unmatched
            
            # Count ROMs with custom configs
            custom_count = len(self.custom_configs)
            
            # Count clone ROMs
            clone_count = len(self.parent_lookup) if hasattr(self, 'parent_lookup') else 0
            
            # Count ROMs with generic controls
            generic_count = 0
            for rom in self.available_roms:
                game_data = self.get_game_data(rom)
                if not game_data or not game_data.get('players'):
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
                
                if not has_custom_controls:
                    generic_count += 1
            
            # Format the stats
            stats = (
                f"ROMs: {len(self.available_roms)}\n"
                f"With Controls: {matched} ({matched/max(len(self.available_roms), 1)*100:.1f}%)\n"
                f"Missing Controls: {unmatched}\n"
                f"Clone ROMs: {clone_count}\n"  # Add clone count
                f"With Custom Config: {custom_count}"
            )
            
            # Update the label
            self.stats_label.configure(text=stats)
            
        except Exception as e:
            print(f"Error updating stats: {e}")
            self.stats_label.configure(text="Statistics: Error")
    
    def find_unmatched_roms(self) -> Set[str]:
        """Find ROMs that don't have matching control data"""
        matched_roms = set()
        for rom in self.available_roms:
            if self.get_game_data(rom):
                matched_roms.add(rom)
        return self.available_roms - matched_roms
   
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
                
                # Build the prefix
                prefix = "* " if has_config else "  "
                prefix += "+ " if has_data else "- "
                
                # Create display text
                if is_clone and (self.current_view == "clones" or self.current_view == "all"):
                    parent_rom = self.parent_lookup.get(rom, "")
                    
                    # Get game name if available (use name cache if available)
                    if has_data:
                        if hasattr(self, 'name_cache') and rom in self.name_cache:
                            game_name = self.name_cache[rom].capitalize()
                            display_text = f"{prefix}{rom} - {game_name} [Clone of {parent_rom}]"
                        else:
                            game_data = self.get_game_data(rom)
                            display_text = f"{prefix}{rom} - {game_data['gamename']} [Clone of {parent_rom}]"
                    else:
                        display_text = f"{prefix}{rom} [Clone of {parent_rom}]"
                else:
                    # Regular display for non-clones or when not in clone view
                    if has_data:
                        if hasattr(self, 'name_cache') and rom in self.name_cache:
                            game_name = self.name_cache[rom].capitalize()
                            display_text = f"{prefix}{rom} - {game_name}"
                        else:
                            game_data = self.get_game_data(rom)
                            display_text = f"{prefix}{rom} - {game_data['gamename']}"
                    else:
                        display_text = f"{prefix}{rom}"
                
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

    # Update scan_roms_directory method 
    def scan_roms_directory(self):
        """Scan the roms directory for available games with improved path handling"""
        
        roms_dir = os.path.join(self.mame_dir, "roms")
        
        if not os.path.exists(roms_dir):
            messagebox.showwarning("No ROMs Found", f"ROMs directory not found: {roms_dir}")
            self.available_roms = set()
            return

        self.available_roms = set()  # Reset the set
        rom_count = 0

        try:
            for filename in os.listdir(roms_dir):
                # Skip directories and non-ROM files
                full_path = os.path.join(roms_dir, filename)
                if os.path.isdir(full_path):
                    continue
                    
                # Skip files with known non-ROM extensions
                extension = os.path.splitext(filename)[1].lower()
                if extension in ['.txt', '.ini', '.cfg', '.bat', '.exe', '.dll']:
                    continue
                    
                # Strip common ROM extensions
                base_name = os.path.splitext(filename)[0]
                self.available_roms.add(base_name)
                rom_count += 1
                
                if rom_count <= 5:  # Print first 5 ROMs as sample
                    print(f"Found ROM: {base_name}")
            
            print(f"Total ROMs found: {len(self.available_roms)}")
            if len(self.available_roms) > 0:
                print(f"Sample of available ROMs: {list(self.available_roms)[:5]}")
            else:
                print("WARNING: No ROMs were found!")
        except Exception as e:
            print(f"Error scanning ROMs directory: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to scan ROMs directory: {e}")
    
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
    
    # Update load_gamedata_json method
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
            self.clone_parents = {}  # New dictionary to track which parents have which clones
            
            for rom_name, game_data in data.items():
                self.gamedata_json[rom_name] = game_data
                    
                # Build parent-child relationship
                if 'clones' in game_data and isinstance(game_data['clones'], dict):
                    # Track all this parent's clones
                    self.clone_parents[rom_name] = list(game_data['clones'].keys())
                    
                    for clone_name, clone_data in game_data['clones'].items():
                        # Store parent reference
                        clone_data['parent'] = rom_name
                        self.parent_lookup[clone_name] = rom_name
                        
                        # Don't add clones as top-level entries in gamedata_json
                        # This avoids duplicating entries and preserves the hierarchy
                
            return self.gamedata_json
                
        except Exception as e:
            print(f"ERROR loading gamedata.json: {str(e)}")
            self.gamedata_json = {}
            self.parent_lookup = {}
            return {}

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
                cfg_controls = self.parse_cfg_controls(self.custom_configs[rom_name])
                
                # Convert if XInput is enabled
                if self.use_xinput:
                    cfg_controls = {
                        control: self.convert_mapping(mapping, True)
                        for control, mapping in cfg_controls.items()
                    }
                
                # Update game_data with custom mappings
                self.update_game_data_with_custom_mappings(game_data, cfg_controls)
                print(f"Applied custom mapping from ROM CFG for {rom_name}")
            
            # NEW CODE: Filter out non-XInput controls if in XInput Only mode
            if hasattr(self, 'xinput_only_mode') and self.xinput_only_mode:
                game_data = self.filter_xinput_controls(game_data)
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
            game_data = self.get_game_data(rom)
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
                            cfg_controls = self.parse_cfg_controls(self.custom_configs[rom_name])
                            
                            # Convert if XInput is enabled
                            if self.use_xinput:
                                cfg_controls = {
                                    control: self.convert_mapping(mapping, True)
                                    for control, mapping in cfg_controls.items()
                                }
                            
                            # Update game_data with custom mappings
                            self.update_game_data_with_custom_mappings(game_data, cfg_controls)
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
        """Update the status bar message with optional timeout"""
        try:
            # Update message text
            self.status_message.configure(text=message)
            
            # Clear after timeout (if specified)
            if timeout > 0:
                self.after(timeout, lambda: self.status_message.configure(text="Ready"))
            
            return True
        except Exception as e:
            print(f"Error updating status message: {e}")
            return False

if __name__ == "__main__":
    try:
        app = MAMEControlConfig()
        app.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
import os
import sys
import json
import time
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from datetime import datetime
import xml.etree.ElementTree as ET
import shutil

# Add this function to handle bundled resources
def get_bundled_file_path(filename):
    """Get the path to a bundled file, works for both development and PyInstaller"""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        return os.path.join(bundle_dir, 'data', filename)
    else:
        # Running as script
        # Look for the file in various development locations
        script_dir = os.path.dirname(os.path.abspath(__file__))
        search_paths = [
            os.path.join(script_dir, filename),
            os.path.join(script_dir, 'settings', filename),
            os.path.join(script_dir, '..', filename),
            os.path.join(script_dir, '..', 'settings', filename),
            os.path.join(script_dir, 'preview', 'settings', filename)
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        return None


class FightstickMapper(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Theme settings
        self.theme_colors = {
            "primary": "#1f538d",
            "secondary": "#2B87D1", 
            "background": "#1e1e1e",
            "card_bg": "#2d2d2d",
            "sidebar_bg": "#252525",
            "text": "#ffffff",
            "text_dimmed": "#a0a0a0",
            "text_grey": "#d6d6d6",
            "highlight": "#3a7ebf",
            "success": "#28a745",
            "warning": "#ffc107",
            "danger": "#dc3545",
            "button_hover": "#1A6DAE",
        }
        
        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        
        # Configure window
        self.title("MAME Fightstick Button Mapper")
        self.geometry("900x800")
        self.configure(fg_color=self.theme_colors["background"])
        
        # Initialize variables
        self.mame_dir = None
        self.fightstick_dir = None
        self.layouts_dir = None
        self.custom_layouts = {}
        self.gamedata_json = {}
        self.available_roms = set()
        
        # Load settings
        self.load_settings()
        
        # Create UI
        self.create_ui()
        
        # Load initial data if MAME directory is set
        if self.mame_dir and os.path.exists(self.mame_dir):
            self.load_game_data()

    def get_app_directory(self):
        """Get the directory where the app is located (works for both .exe and .py)"""
        if getattr(sys, 'frozen', False):
            # Running as PyInstaller bundle
            return os.path.dirname(sys.executable)
        else:
            # Running as script
            return os.path.dirname(os.path.abspath(__file__))

    def get_settings_file_path(self):
        """Get the path to the settings file"""
        app_dir = self.get_app_directory()
        return os.path.join(app_dir, "fightstick_settings.json")

    def load_settings(self):
        """Load application settings from app directory"""
        try:
            settings_file = self.get_settings_file_path()
            
            if os.path.exists(settings_file):
                try:
                    with open(settings_file, 'r') as f:
                        settings = json.load(f)
                        self.mame_dir = settings.get('mame_dir')
                        if self.mame_dir and os.path.exists(self.mame_dir):
                            self.initialize_fightstick_directory()
                            print(f"Loaded settings from: {settings_file}")
                            print(f"MAME directory: {self.mame_dir}")
                            return
                        else:
                            print(f"MAME directory in settings no longer exists: {self.mame_dir}")
                            self.mame_dir = None
                except Exception as e:
                    print(f"Error loading settings from {settings_file}: {e}")
            
            # If no valid settings found, try to find existing MAME installations
            print("No valid settings found, searching for existing MAME installations...")
            self.search_for_existing_mame()
            
        except Exception as e:
            print(f"Error in load_settings: {e}")

    def search_for_existing_mame(self):
        """Search common locations for existing MAME installations"""
        possible_mame_dirs = [
            "C:/MAME",
            "C:/MAME64", 
            "D:/MAME",
            os.path.expanduser("~/MAME"),
            os.path.join(os.path.expanduser("~"), "Documents", "MAME"),
            # Add more common locations
            "C:/Games/MAME",
            "D:/Games/MAME",
            "C:/Program Files/MAME",
            "C:/Program Files (x86)/MAME"
        ]
        
        for mame_dir in possible_mame_dirs:
            if os.path.exists(mame_dir) and self.validate_mame_directory(mame_dir):
                print(f"Found existing MAME installation at: {mame_dir}")
                # Don't auto-set it, just report it was found
                # User still needs to manually select it
                break

    def save_settings(self):
        """Save application settings to app directory"""
        try:
            settings_file = self.get_settings_file_path()
            
            settings = {
                'mame_dir': self.mame_dir,
                'last_updated': datetime.now().isoformat(),
                'app_version': '1.0'
            }
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            
            print(f"Settings saved to: {settings_file}")
            
        except Exception as e:
            print(f"Error saving settings: {e}")

    def create_ui(self):
        """Create the main user interface"""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color=self.theme_colors["primary"], corner_radius=0, height=60)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        ctk.CTkLabel(
            header_frame,
            text="MAME Fightstick Button Mapper",
            font=("Arial", 18, "bold"),
            text_color="#ffffff"
        ).pack(side="left", padx=20, pady=15)
        
        # MAME Directory button
        self.dir_button = ctk.CTkButton(
            header_frame,
            text="Set MAME Directory",
            command=self.select_mame_directory,
            width=150,
            height=35,
            fg_color=self.theme_colors["secondary"],
            hover_color=self.theme_colors["primary"]
        )
        self.dir_button.pack(side="right", padx=20, pady=12)
        
        # Main content with scrolling
        self.content_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=self.theme_colors["primary"],
            scrollbar_button_hover_color=self.theme_colors["secondary"]
        )
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Create all UI components first
        self.create_description_card()
        self.create_presets_card()
        self.create_game_selection_card()
        self.create_options_card()
        self.create_status_area()
        self.create_bottom_buttons()
        
        # MAME Directory status card (create after buttons exist)
        self.create_directory_status_card()

    def create_description_card(self):
        """Create description card"""
        desc_card = ctk.CTkFrame(self.content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
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
            wraplength=850
        ).pack(padx=15, pady=15, anchor="w")

    def create_presets_card(self):
        """Create mapping presets card"""
        self.presets_card = ctk.CTkFrame(self.content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        self.presets_card.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            self.presets_card,
            text="Button Mapping Presets",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Define mapping presets
        self.mapping_presets = {
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
        
        # Preset selection
        preset_frame = ctk.CTkFrame(self.presets_card, fg_color=self.theme_colors["background"], corner_radius=4)
        preset_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            preset_frame,
            text="Select Fighting Game Layout:",
            font=("Arial", 13, "bold")
        ).pack(side="left", padx=10, pady=10)
        
        preset_options = ["All Compatible Games"] + [preset["name"] for preset in self.mapping_presets.values()]
        self.preset_var = tk.StringVar(value=preset_options[0])
        
        self.preset_dropdown = ctk.CTkComboBox(
            preset_frame,
            values=preset_options,
            variable=self.preset_var,
            command=self.update_preset_selection,
            width=350,
            fg_color=self.theme_colors["card_bg"],
            button_color=self.theme_colors["primary"],
            button_hover_color=self.theme_colors["secondary"],
            dropdown_fg_color=self.theme_colors["card_bg"]
        )
        self.preset_dropdown.pack(side="left", padx=10, pady=10)
        
        # Description label
        self.description_label = ctk.CTkLabel(
            self.presets_card,
            text="Automatically apply the best mapping to ALL compatible fighting games based on their type",
            font=("Arial", 12),
            text_color=self.theme_colors["text_dimmed"],
            wraplength=800,
            justify="left"
        )
        self.description_label.pack(padx=15, pady=(0, 15))

    def create_game_selection_card(self):
        """Create game selection card"""
        self.games_card = ctk.CTkFrame(self.content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        self.games_card.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            self.games_card,
            text="Game Selection",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Game list frame
        games_list_frame = ctk.CTkFrame(self.games_card, fg_color=self.theme_colors["background"], corner_radius=4)
        games_list_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # Create listbox for games
        self.games_listbox = tk.Listbox(
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
        self.games_listbox.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        # Scrollbar
        games_scrollbar = ctk.CTkScrollbar(games_list_frame, orientation="vertical", command=self.games_listbox.yview)
        games_scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)
        self.games_listbox.configure(yscrollcommand=games_scrollbar.set)
        
        # Selection buttons
        selection_frame = ctk.CTkFrame(self.games_card, fg_color="transparent")
        selection_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkButton(
            selection_frame,
            text="Select All",
            command=self.select_all_games,
            width=100,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            selection_frame,
            text="Deselect All", 
            command=self.deselect_all_games,
            width=100,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).pack(side="left", padx=5)
        
        # Store games data
        self.current_games = []
        self.game_mapping_assignments = {}

    def create_options_card(self):
        """Create configuration options card"""
        options_card = ctk.CTkFrame(self.content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
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
        
        self.mame_version_var = tk.StringVar(value="new")
        
        ctk.CTkLabel(
            mame_version_frame,
            text="MAME Version Compatibility:",
            font=("Arial", 13, "bold")
        ).pack(side="left", padx=0, pady=5)
        
        ctk.CTkRadioButton(
            mame_version_frame,
            text="New MAME (0.250+)",
            variable=self.mame_version_var,
            value="new",
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        ).pack(side="left", padx=15, pady=5)
        
        ctk.CTkRadioButton(
            mame_version_frame,
            text="Old MAME (0.249-)",
            variable=self.mame_version_var,
            value="old",
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        ).pack(side="left", padx=15, pady=5)
        
        # Version info
        ctk.CTkLabel(
            options_card,
            text="New MAME uses SLIDER2, Old MAME uses ZAXIS for analog controls",
            font=("Arial", 11),
            text_color=self.theme_colors["text_dimmed"]
        ).pack(padx=15, pady=(0, 10))
        
        # Other options
        options_frame = ctk.CTkFrame(options_card, fg_color="transparent")
        options_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        self.backup_cfg_var = tk.BooleanVar(value=True)
        self.create_missing_var = tk.BooleanVar(value=True)
        self.update_existing_var = tk.BooleanVar(value=True)
        
        ctk.CTkCheckBox(
            options_frame,
            text="Backup existing CFG files before modifying",
            variable=self.backup_cfg_var,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        ).pack(anchor="w", pady=2)
        
        ctk.CTkCheckBox(
            options_frame,
            text="Create missing button entries in CFG files",
            variable=self.create_missing_var,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        ).pack(anchor="w", pady=2)
        
        ctk.CTkCheckBox(
            options_frame,
            text="Update existing button mappings",
            variable=self.update_existing_var,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["secondary"]
        ).pack(anchor="w", pady=2)

    def create_status_area(self):
        """Create status display area"""
        status_frame = ctk.CTkFrame(self.content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        status_frame.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(
            status_frame,
            text="Status",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        self.status_text = ctk.CTkTextbox(
            status_frame,
            height=120,
            font=("Consolas", 11),
            fg_color=self.theme_colors["background"]
        )
        self.status_text.pack(fill="x", padx=15, pady=(0, 15))
        self.status_text.insert("1.0", "Ready to configure fightstick mappings...\n\nPlease set your MAME directory first.")

    def create_bottom_buttons(self):
        """Create bottom action buttons"""
        buttons_frame = ctk.CTkFrame(self, height=70, fg_color=self.theme_colors["card_bg"], corner_radius=0)
        buttons_frame.pack(fill="x", side="bottom", padx=0, pady=0)
        buttons_frame.pack_propagate(False)
        
        button_container = ctk.CTkFrame(buttons_frame, fg_color="transparent")
        button_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Apply button
        self.apply_button = ctk.CTkButton(
            button_container,
            text="Apply Mappings",
            command=self.apply_fightstick_mappings,
            width=150,
            height=40,
            fg_color=self.theme_colors["success"],
            hover_color="#218838",
            font=("Arial", 14, "bold"),
            state="disabled"
        )
        self.apply_button.pack(side="right", padx=5)
        
        # Close button
        ctk.CTkButton(
            button_container,
            text="Exit",
            command=self.quit,
            width=120,
            height=40,
            fg_color=self.theme_colors["danger"],
            hover_color="#c82333",
            font=("Arial", 14)
        ).pack(side="right", padx=5)

    def select_mame_directory(self):
        """Select MAME directory"""
        directory = filedialog.askdirectory(
            title="Select MAME Directory",
            initialdir=self.mame_dir if self.mame_dir else os.path.expanduser("~")
        )
        
        if directory:
            # Validate that this looks like a MAME directory
            if not self.validate_mame_directory(directory):
                if not messagebox.askyesno(
                    "Directory Validation",
                    "This directory doesn't appear to contain MAME files (no mame.exe or mame64.exe found).\n\nDo you want to use it anyway?",
                    icon="warning"
                ):
                    return
            
            self.mame_dir = directory
            self.initialize_fightstick_directory()
            
            # Save settings to the new fightstick folder
            self.save_settings()
            
            self.update_directory_status()
            self.load_game_data()
            
            # Update status
            self.status_text.delete("1.0", tk.END)
            self.status_text.insert("1.0", f"📁 MAME directory set to: {directory}\n")
            self.status_text.insert(tk.END, f"⚙️  Settings will be saved to: {self.fightstick_dir}/fightstick_settings.json\n")
            self.status_text.insert(tk.END, "\n🔄 Loading game data...")

    def validate_mame_directory(self, directory):
        """Validate that the directory contains MAME"""
        mame_executables = ["mame.exe", "mame64.exe", "mame"]
        for exe in mame_executables:
            if os.path.exists(os.path.join(directory, exe)):
                return True
        return False

    # Update initialize_fightstick_directory to create the template
    def initialize_fightstick_directory(self):
        """Initialize fightstick directory structure"""
        if not self.mame_dir:
            return
            
        self.fightstick_dir = os.path.join(self.mame_dir, "fightstick")
        os.makedirs(self.fightstick_dir, exist_ok=True)
        
        # Create subdirectories
        self.layouts_dir = os.path.join(self.fightstick_dir, "layouts")
        self.backups_dir = os.path.join(self.fightstick_dir, "backups")
        os.makedirs(self.layouts_dir, exist_ok=True)
        os.makedirs(self.backups_dir, exist_ok=True)
        
        # Load custom layouts
        self.load_custom_layouts()
        
        # Create user mappings template
        self.create_user_mappings_template()
        
        print(f"Initialized fightstick directory: {self.fightstick_dir}")
        print(f"  - Layouts: {self.layouts_dir}")
        print(f"  - Backups: {self.backups_dir}")
        print(f"  - User mappings: {self.get_user_mappings_file()}")

    def load_custom_layouts(self):
        """Load custom fightstick layouts"""
        self.custom_layouts = {}
        
        if not self.layouts_dir or not os.path.exists(self.layouts_dir):
            return
            
        try:
            for filename in os.listdir(self.layouts_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.layouts_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            layout_data = json.load(f)
                        
                        if all(key in layout_data for key in ['name', 'mappings', 'base_preset']):
                            layout_id = filename[:-5]
                            self.custom_layouts[layout_id] = layout_data
                    except Exception as e:
                        print(f"Error loading layout {filename}: {e}")
        except Exception as e:
            print(f"Error reading layouts directory: {e}")

    def create_directory_status_card(self):
        """Create card showing MAME directory status"""
        # Create the card first
        self.dir_status_card = ctk.CTkFrame(self.content_frame, fg_color=self.theme_colors["card_bg"], corner_radius=6)
        
        ctk.CTkLabel(
            self.dir_status_card,
            text="MAME Directory Status",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Status display
        status_frame = ctk.CTkFrame(self.dir_status_card, fg_color="transparent")
        status_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        self.dir_status_label = ctk.CTkLabel(
            status_frame,
            text="No MAME directory set",
            font=("Arial", 13),
            anchor="w",
            justify="left"  # Add this
        )
        self.dir_status_label.pack(anchor="w", pady=5, padx=0)  # Remove any padding
        
        # Pack at the top by finding all children and repacking them
        children = list(self.content_frame.winfo_children())
        for child in children:
            child.pack_forget()
        
        # Pack directory status first
        self.dir_status_card.pack(fill="x", padx=0, pady=(0, 15))
        
        # Repack other children in order
        for child in children:
            if child != self.dir_status_card:
                child.pack(fill="x", padx=0, pady=(0, 15))
        
        self.update_directory_status()

    def update_directory_status(self):
        """Update directory status display with proper alignment"""
        if self.mame_dir and os.path.exists(self.mame_dir):
            # Use consistent formatting - no extra spaces, let the UI handle alignment
            status_text = f"✓ MAME Directory: {self.mame_dir}"
            if self.fightstick_dir:
                status_text += f"\n✓ Fightstick Config: {self.fightstick_dir}"
            color = self.theme_colors["success"]
            # Only try to configure apply button if it exists
            if hasattr(self, 'apply_button'):
                self.apply_button.configure(state="normal")
        else:
            status_text = "❌ No MAME directory set - Please select your MAME installation folder"
            color = self.theme_colors["danger"]
            # Only try to configure apply button if it exists
            if hasattr(self, 'apply_button'):
                self.apply_button.configure(state="disabled")
        
        self.dir_status_label.configure(text=status_text, text_color=color)

    def get_user_mappings_file(self):
        """Get path to user mappings file"""
        if self.fightstick_dir:
            return os.path.join(self.fightstick_dir, "user_rom_mappings.txt")
        return None

    def load_user_rom_mappings(self):
        """Load user-defined ROM mappings from text file"""
        mappings_file = self.get_user_mappings_file()
        if not mappings_file or not os.path.exists(mappings_file):
            return
        
        try:
            added_count = 0
            with open(mappings_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse line: rom_name = mapping_type
                    if '=' in line:
                        rom_name, mapping_type = [part.strip() for part in line.split('=', 1)]
                        
                        # Validate mapping type
                        if mapping_type in ['sf', 'mk', 'tekken', 'tekkent']:
                            # Add to gamedata if not already there
                            if rom_name not in self.gamedata_json:
                                self.add_rom_with_mapping(rom_name, mapping_type)
                                added_count += 1
                                print(f"Added user mapping: {rom_name} -> {mapping_type}")
                            else:
                                # Update existing mapping
                                if 'mappings' not in self.gamedata_json[rom_name]:
                                    self.gamedata_json[rom_name]['mappings'] = []
                                if mapping_type not in self.gamedata_json[rom_name]['mappings']:
                                    self.gamedata_json[rom_name]['mappings'].append(mapping_type)
                                    print(f"Updated mapping for {rom_name}: added {mapping_type}")
                        else:
                            print(f"Warning: Invalid mapping type '{mapping_type}' on line {line_num}")
                    else:
                        print(f"Warning: Invalid format on line {line_num}: {line}")
            
            if added_count > 0:
                print(f"Loaded {added_count} custom ROM mappings from user file")
                
        except Exception as e:
            print(f"Error loading user ROM mappings: {e}")

    def add_rom_with_mapping(self, rom_name, mapping_type):
        """Add a ROM with specified mapping using template from existing games"""
        
        # Find a template game with the same mapping type
        template_rom = None
        for existing_rom, rom_data in self.gamedata_json.items():
            if 'mappings' in rom_data and mapping_type in rom_data['mappings']:
                if 'controls' in rom_data and rom_data['controls']:
                    template_rom = existing_rom
                    break
        
        if not template_rom:
            print(f"Warning: No template found for mapping type '{mapping_type}'")
            return
        
        # Copy control structure from template
        template_data = self.gamedata_json[template_rom]
        
        new_rom_data = {
            "description": f"{rom_name} (User Added - {mapping_type.upper()} Layout)",
            "mappings": [mapping_type],
            "controls": template_data['controls'].copy()  # Copy the control definitions
        }
        
        # Add optional fields if they exist in template
        for field in ['playercount', 'buttons', 'sticks']:
            if field in template_data:
                new_rom_data[field] = template_data[field]
        
        self.gamedata_json[rom_name] = new_rom_data

    def create_user_mappings_template(self):
        """Create a template user mappings file"""
        mappings_file = self.get_user_mappings_file()
        if not mappings_file:
            return
            
        try:
            # Only create if it doesn't exist
            if not os.path.exists(mappings_file):
                template_content = """# User ROM Mappings
    # Add your custom ROM mappings here
    # Format: rom_name = mapping_type
    # 
    # Available mapping types:
    #   sf      = 6-button Street Fighter layout (LP, MP, HP, LK, MK, HK)
    #   mk      = Mortal Kombat layout (HP, LP, BL, RN, HK, LK)
    #   tekken  = 4-button Tekken layout (LP, RP, LK, RK)
    #   tekkent = 5-button Tekken Tag layout (LP, RP, LK, RK, Tag)
    #
    # Examples:
    # mygame = sf
    # anothergame = mk
    # tekken8 = tekken
    #
    # Lines starting with # are comments and will be ignored
    # Empty lines are also ignored

    """
                
                with open(mappings_file, 'w', encoding='utf-8') as f:
                    f.write(template_content)
                
                print(f"Created user mappings template: {mappings_file}")
        
        except Exception as e:
            print(f"Error creating user mappings template: {e}")

    def load_game_data(self):
        """Load game data from MAME directory and bundled gamedata.json"""
        if not self.mame_dir:
            return
            
        try:
            # Scan for ROM files
            roms_dir = os.path.join(self.mame_dir, "roms")
            if os.path.exists(roms_dir):
                self.available_roms = set()
                for file in os.listdir(roms_dir):
                    if file.endswith('.zip'):
                        rom_name = file[:-4]  # Remove .zip extension
                        self.available_roms.add(rom_name)
            
            # Load gamedata.json - First try bundled version, then external
            gamedata_loaded = False
            
            # 1. Try bundled gamedata.json (from PyInstaller)
            bundled_gamedata_path = get_bundled_file_path('gamedata.json')
            if bundled_gamedata_path and os.path.exists(bundled_gamedata_path):
                try:
                    with open(bundled_gamedata_path, 'r', encoding='utf-8') as f:
                        self.gamedata_json = json.load(f)
                    gamedata_loaded = True
                    self.status_text.insert(tk.END, f"✅ Loaded bundled gamedata.json with {len(self.gamedata_json)} games\n")
                except Exception as e:
                    self.status_text.insert(tk.END, f"Error loading bundled gamedata.json: {e}\n")
            
            # 2. Load user ROM mappings AFTER gamedata is loaded
            if gamedata_loaded:
                self.load_user_rom_mappings()
            
            # 3. Final status update
            self.status_text.delete("1.0", tk.END)
            self.status_text.insert("1.0", f"📁 Loaded {len(self.available_roms)} ROMs from {roms_dir}\n")
            
            if gamedata_loaded:
                self.status_text.insert(tk.END, f"🎮 Game data loaded: {len(self.gamedata_json)} games available\n")
                
                # Check if user mappings file exists
                user_mappings_file = self.get_user_mappings_file()
                if user_mappings_file and os.path.exists(user_mappings_file):
                    self.status_text.insert(tk.END, f"📝 User ROM mappings loaded from: {os.path.basename(user_mappings_file)}\n")
                
                # Count fighting games
                fighting_games = 0
                for rom_name, rom_data in self.gamedata_json.items():
                    if 'mappings' in rom_data and rom_data['mappings']:
                        for mapping in rom_data['mappings']:
                            if mapping in ['sf', 'ki', 'mk', 'tekken', 'tekkent', 'darkstalkers', 'marvel', 'capcom']:
                                fighting_games += 1
                                break
                
                self.status_text.insert(tk.END, f"⚔️  Fighting games detected: ~{fighting_games}\n")
                self.status_text.insert(tk.END, "\n✅ Ready to configure fightstick mappings!")
            else:
                self.status_text.insert(tk.END, "\n⚠️  WARNING: No gamedata.json found!")
            
            # Update preset selection to populate games
            self.update_preset_selection(self.preset_var.get())
            
        except Exception as e:
            error_msg = f"Error loading game data: {e}"
            self.status_text.delete("1.0", tk.END)
            self.status_text.insert("1.0", error_msg)

    def update_preset_selection(self, choice):
        """Update game list based on preset selection"""
        self.games_listbox.delete(0, tk.END)
        self.current_games = []
        
        if not self.mame_dir or not self.available_roms:
            self.games_listbox.insert(tk.END, "No MAME directory set or no ROMs found")
            return
        
        # Find games based on mapping type
        games_found = []
        
        if choice == "All Compatible Games":
            # Show all compatible games from all presets
            for preset_id, preset_data in self.mapping_presets.items():
                preset_games = self.get_games_for_mapping(preset_id)
                for rom_name, game_name, is_clone in preset_games:
                    games_found.append((rom_name, game_name, is_clone, preset_id))
        else:
            # Single preset mode
            selected_preset = None
            for preset_id, preset_data in self.mapping_presets.items():
                if preset_data["name"] == choice:
                    selected_preset = preset_id
                    break
            
            if selected_preset:
                preset_games = self.get_games_for_mapping(selected_preset)
                for rom_name, game_name, is_clone in preset_games:
                    games_found.append((rom_name, game_name, is_clone, selected_preset))
        
        # Populate listbox
        if not games_found:
            self.games_listbox.insert(tk.END, "No compatible games found")
        else:
            if choice == "All Compatible Games":
                # Group by preset type
                games_by_type = {}
                for rom_name, game_name, is_clone, preset_id in games_found:
                    preset_name = self.mapping_presets[preset_id]["name"]
                    if preset_name not in games_by_type:
                        games_by_type[preset_name] = []
                    games_by_type[preset_name].append((rom_name, game_name, is_clone, preset_id))
                
                for preset_name, preset_games in games_by_type.items():
                    self.games_listbox.insert(tk.END, f"--- {preset_name} ({len(preset_games)} games) ---")
                    for rom_name, game_name, is_clone, preset_id in preset_games:
                        display_text = f"  {rom_name} - {game_name or rom_name}"
                        if is_clone:
                            display_text += " [Clone]"
                        self.games_listbox.insert(tk.END, display_text)
                
                # Select all non-header items
                for i in range(self.games_listbox.size()):
                    item_text = self.games_listbox.get(i)
                    if not item_text.startswith("---"):
                        self.games_listbox.selection_set(i)
            else:
                # Single preset display
                for rom_name, game_name, is_clone, preset_id in games_found:
                    display_text = f"{rom_name} - {game_name or rom_name}"
                    if is_clone:
                        display_text += " [Clone]"
                    self.games_listbox.insert(tk.END, display_text)
                
                self.games_listbox.select_set(0, tk.END)
        
        self.current_games = games_found

    def get_games_for_mapping(self, mapping_type):
        """Get games that match a specific mapping type"""
        games = []
        
        # Define which mappings each game type should have
        mapping_indicators = {
            "6button": ["sf", "ki", "darkstalkers", "marvel", "capcom"],
            "mk": ["mk"],
            "tekken": ["tekken"],
            "tekkent": ["tekkent"]
        }
        
        target_mappings = mapping_indicators.get(mapping_type, [mapping_type])
        
        # Check available ROMs
        for rom_name in self.available_roms:
            # Check if ROM has matching mapping in gamedata
            has_mapping = False
            game_name = rom_name
            is_clone = False
            
            if rom_name in self.gamedata_json:
                rom_data = self.gamedata_json[rom_name]
                game_name = rom_data.get('description', rom_name)
                
                # Check for mappings
                rom_mappings = rom_data.get('mappings', [])
                if any(mapping in rom_mappings for mapping in target_mappings):
                    has_mapping = True
            
            # Add some common fighting games by name if not found in mappings
            if not has_mapping:
                rom_lower = rom_name.lower()
                if mapping_type == "6button" and any(term in rom_lower for term in ["sf", "street", "fighter", "xmen", "marvel", "darkstalkers", "vampire"]):
                    has_mapping = True
                elif mapping_type == "mk" and any(term in rom_lower for term in ["mk", "mortal", "kombat"]):
                    has_mapping = True
                elif mapping_type == "tekken" and "tekken" in rom_lower and "tag" not in rom_lower:
                    has_mapping = True
                elif mapping_type == "tekkent" and "tekken" in rom_lower and "tag" in rom_lower:
                    has_mapping = True
            
            if has_mapping:
                games.append((rom_name, game_name, is_clone))
        
        return sorted(games, key=lambda x: x[1])

    def select_all_games(self):
        """Select all games in the list"""
        if self.preset_var.get() == "All Compatible Games":
            # Select all non-header items
            for i in range(self.games_listbox.size()):
                item_text = self.games_listbox.get(i)
                if not item_text.startswith("---"):
                    self.games_listbox.selection_set(i)
        else:
            self.games_listbox.select_set(0, tk.END)

    def deselect_all_games(self):
        """Deselect all games"""
        self.games_listbox.select_clear(0, tk.END)

    def apply_fightstick_mappings(self):
        """Apply fightstick mappings to selected games"""
        if not self.mame_dir:
            messagebox.showerror("Error", "Please set MAME directory first")
            return
        
        selected_indices = self.games_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Games Selected", "Please select at least one game to configure.")
            return
        
        # Build list of games to process
        games_to_process = []
        selected_display_name = self.preset_var.get()
        
        if selected_display_name == "All Compatible Games":
            # Process with individual mappings per game
            listbox_index = 0
            for rom_name, game_name, is_clone, preset_id in self.current_games:
                # Skip headers in the listbox
                while listbox_index < self.games_listbox.size():
                    if not self.games_listbox.get(listbox_index).startswith("---"):
                        break
                    listbox_index += 1
                
                if listbox_index in selected_indices:
                    games_to_process.append({
                        'rom_name': rom_name,
                        'preset_id': preset_id,
                        'preset_name': self.mapping_presets[preset_id]["name"]
                    })
                
                listbox_index += 1
        else:
            # Single preset mode
            selected_preset = None
            for preset_id, preset_data in self.mapping_presets.items():
                if preset_data["name"] == selected_display_name:
                    selected_preset = preset_id
                    break
            
            if not selected_preset:
                messagebox.showerror("Error", "No valid preset selected.")
                return
            
            for index in selected_indices:
                if index < len(self.current_games):
                    rom_name = self.current_games[index][0]
                    games_to_process.append({
                        'rom_name': rom_name,
                        'preset_id': selected_preset,
                        'preset_name': self.mapping_presets[selected_preset]["name"]
                    })
        
        if not games_to_process:
            messagebox.showwarning("No Games Selected", "Please select at least one game to configure.")
            return
        
        # Show confirmation
        confirmation_msg = f"Apply fightstick mappings to {len(games_to_process)} games?\n\nThis will modify CFG files in your MAME cfg directory."
        if not messagebox.askyesno("Confirm Configuration", confirmation_msg):
            return
        
        # Clear status and start processing
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert("1.0", f"Configuring {len(games_to_process)} games...\n\n")
        self.update_idletasks()
        
        processed_count = 0
        error_count = 0
        
        for game_info in games_to_process:
            try:
                rom_name = game_info['rom_name']
                preset_id = game_info['preset_id']
                preset_name = game_info['preset_name']
                
                button_mappings = self.mapping_presets[preset_id]['mappings']
                
                result = self.configure_game_fightstick_mapping(
                    rom_name,
                    button_mappings,
                    self.backup_cfg_var.get(),
                    self.create_missing_var.get(),
                    self.update_existing_var.get(),
                    self.mame_version_var.get()
                )
                
                if result['success']:
                    self.status_text.insert(tk.END, f"✓ {rom_name} ({preset_name}): {result['message']}\n")
                    processed_count += 1
                else:
                    self.status_text.insert(tk.END, f"✗ {rom_name}: {result['message']}\n")
                    error_count += 1
                    
            except Exception as e:
                self.status_text.insert(tk.END, f"✗ {rom_name}: Error - {str(e)}\n")
                error_count += 1
            
            self.status_text.see(tk.END)
            self.update_idletasks()
        
        # Summary
        self.status_text.insert(tk.END, f"\nCompleted: {processed_count} successful, {error_count} errors")
        self.status_text.see(tk.END)
        
        # Show completion message
        completion_msg = f"Processed {processed_count} games successfully.\nErrors: {error_count}"
        messagebox.showinfo("Configuration Complete", completion_msg)

    def configure_game_fightstick_mapping(self, rom_name, button_mappings, backup_cfg, create_missing, update_existing, mame_version):
        """Configure a single game's CFG file with fightstick button mappings"""
        try:
            # Construct CFG file path
            cfg_dir = os.path.join(self.mame_dir, "cfg")
            cfg_path = os.path.join(cfg_dir, f"{rom_name}.cfg")
            
            os.makedirs(cfg_dir, exist_ok=True)
            
            # Backup existing CFG if requested
            if backup_cfg and os.path.exists(cfg_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_filename = f"{rom_name}.{timestamp}.cfg"
                backup_path = os.path.join(self.backups_dir, backup_filename)
                shutil.copy2(cfg_path, backup_path)
            
            # Load or create CFG structure
            if os.path.exists(cfg_path):
                try:
                    tree = ET.parse(cfg_path)
                    root = tree.getroot()
                except ET.ParseError:
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
            
            # Track changes
            modified_buttons = []
            created_buttons = []
            
            # Process each button mapping
            for mame_control, joycode in button_mappings.items():
                if not joycode:
                    continue
                
                # Convert MAME control to port data using gamedata
                port_data = self.mame_control_to_port_data(mame_control, joycode, mame_version, rom_name)
                if not port_data:
                    # If we can't get proper port data, skip this control
                    continue
                
                # Check if port already exists
                existing_port = input_elem.find(f".//port[@tag='{port_data['tag']}'][@type='{port_data['type']}'][@mask='{port_data['mask']}']")
                
                if existing_port is not None:
                    if update_existing:
                        newseq = existing_port.find("newseq[@type='standard']")
                        if newseq is not None:
                            old_value = newseq.text
                            newseq.text = port_data['newseq']
                            modified_buttons.append(f"{mame_control}: {old_value} -> {port_data['newseq']}")
                        else:
                            newseq = ET.SubElement(existing_port, "newseq")
                            newseq.set("type", "standard")
                            newseq.text = port_data['newseq']
                            created_buttons.append(f"{mame_control}: Added newseq {port_data['newseq']}")
                        
                        existing_port.set("defvalue", port_data['defvalue'])
                else:
                    if create_missing:
                        self.add_formatted_port_to_input(input_elem, port_data)
                        created_buttons.append(f"{mame_control}: Created with {port_data['newseq']}")
            
            # Save the CFG file
            self.save_formatted_cfg(tree, cfg_path)
            
            # Prepare result message
            changes = []
            if created_buttons:
                changes.append(f"Created {len(created_buttons)} buttons")
            if modified_buttons:
                changes.append(f"Modified {len(modified_buttons)} buttons")
            
            message = f"CFG updated: {', '.join(changes)}" if changes else "No changes made"
            
            return {
                'success': True,
                'message': message,
                'created_count': len(created_buttons),
                'modified_count': len(modified_buttons),
                'cfg_path': cfg_path
            }
            
        except Exception as e:
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
                        tag = ":INPUTS"
                    else:
                        tag = ":EXTRA"
                elif mame_control.startswith('P2_'):
                    if 'BUTTON1' in mame_control or 'BUTTON2' in mame_control or 'BUTTON3' in mame_control:
                        tag = ":INPUTS"
                    elif 'BUTTON6' in mame_control:
                        tag = ":INPUTS"  # P2_BUTTON6 is usually in :INPUTS
                    else:
                        tag = ":EXTRA"
                else:
                    tag = ":INPUTS"
                
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
            
            # CRITICAL FIX: Correct defvalue logic
            # For most input controls, defvalue should match the mask value
            defvalue = port_info['mask']  # Default: defvalue = mask
            
            # Special cases where defvalue should be 0:
            special_zero_defvalue_tags = [
                ":JVS_",     # JVS system tags
                ":MAHJONG",  # Mahjong inputs
                ":HANAFUDA", # Hanafuda inputs
                ":KEYPAD",   # Keypad inputs
            ]
            
            # Check if this tag should have defvalue=0
            for special_tag in special_zero_defvalue_tags:
                if port_info['tag'].startswith(special_tag):
                    defvalue = "0"
                    break
            
            # Additional logic: if mask is "0", defvalue should also be "0"
            if port_info['mask'] == "0":
                defvalue = "0"
            
            return {
                'tag': port_info['tag'],
                'type': port_info['type'],
                'mask': port_info['mask'],
                'defvalue': defvalue,
                'newseq': joycode
            }
            
        except Exception as e:
            print(f"Error converting {mame_control} to port data: {e}")
            return None

    def add_formatted_port_to_input(self, input_elem, port_data):
        """Add a properly formatted port element to input"""
        port = ET.SubElement(input_elem, "port")
        port.set("tag", port_data['tag'])
        port.set("type", port_data['type'])
        port.set("mask", port_data['mask'])
        port.set("defvalue", port_data['defvalue'])
        
        newseq = ET.SubElement(port, "newseq")
        newseq.set("type", "standard")
        newseq.text = port_data['newseq']
        
        return port

    def save_formatted_cfg(self, tree, cfg_path):
        """Save CFG file with proper XML formatting matching MAME's style"""
        try:
            root = tree.getroot()
            
            # First, apply standard indentation
            ET.indent(tree, space="    ", level=0)
            
            # Now manually format newseq elements to put content on separate lines
            for newseq in root.iter('newseq'):
                if newseq.text and newseq.text.strip():
                    # Calculate proper indentation based on nesting level
                    # newseq is inside port which is inside input which is inside system which is inside root
                    # So it needs 5 levels of indentation (20 spaces)
                    indent = "                    "  # 20 spaces for the content
                    closing_indent = "                "      # 16 spaces for closing tag alignment
                    
                    newseq.text = f"\n{indent}{newseq.text.strip()}\n{closing_indent}"
            
            # Get the XML string without declaration
            xml_content = ET.tostring(root, encoding='unicode')
            
            # Build final XML with MAME-style header
            final_xml = '<?xml version="1.0"?>\n'
            final_xml += '<!-- This file is autogenerated; comments and unknown tags will be stripped -->\n'
            final_xml += xml_content
            
            # Write to file
            with open(cfg_path, 'w', encoding='utf-8') as f:
                f.write(final_xml)
                
            print(f"CFG file saved with MAME formatting: {cfg_path}")
                
        except Exception as e:
            print(f"Error formatting CFG file: {e}")
            # Fallback to basic save
            try:
                tree.write(cfg_path, encoding='utf-8', xml_declaration=True)
            except Exception as fallback_error:
                print(f"Fallback save also failed: {fallback_error}")

    def create_new_cfg_structure(self, rom_name):
        """Create a new CFG XML structure"""
        root = ET.Element("mameconfig", version="10")
        ET.SubElement(root, "system", name=rom_name)
        return root


def main():
    """Main entry point"""
    try:
        app = FightstickMapper()
        app.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
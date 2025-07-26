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
        """Create mapping presets card with enhanced custom layout support"""
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
                "description": "Standard 6-button layout: LP(X), MP(Y), HP(RB), LK(A), MK(B), HK(RT)",
                "mappings": {
                    "P1_BUTTON1": "JOYCODE_1_BUTTON3",           # Light Punch -> X
                    "P1_BUTTON2": "JOYCODE_1_BUTTON4",           # Medium Punch -> Y
                    "P1_BUTTON3": "JOYCODE_1_BUTTON6",           # Heavy Punch -> RB
                    "P1_BUTTON4": "JOYCODE_1_BUTTON1",           # Light Kick -> A
                    "P1_BUTTON5": "JOYCODE_1_BUTTON2",           # Medium Kick -> B
                    "P1_BUTTON6": "JOYCODE_1_SLIDER2_NEG_SWITCH", # Heavy Kick -> RT (your working trigger)
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
                "description": "6-button MK layout: HP(RB), LP(X), BL(Y), RN(B), HK(RT), LK(A)",
                "mappings": {
                    "P1_BUTTON1": "JOYCODE_1_BUTTON6",           # High Punch -> RB
                    "P1_BUTTON2": "JOYCODE_1_BUTTON4",           # Block -> Y
                    "P1_BUTTON3": "JOYCODE_1_SLIDER2_NEG_SWITCH", # High Kick -> RT
                    "P1_BUTTON4": "JOYCODE_1_BUTTON3",           # Low Punch -> X
                    "P1_BUTTON5": "JOYCODE_1_BUTTON1",           # Low Kick -> A
                    "P1_BUTTON6": "JOYCODE_1_BUTTON2",           # Run -> B
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
                "description": "4-button Tekken layout: LP(X), RP(Y), LK(A), RK(B)",
                "mappings": {
                    "P1_BUTTON1": "JOYCODE_1_BUTTON3",           # Left Punch -> X
                    "P1_BUTTON2": "JOYCODE_1_BUTTON4",           # Right Punch -> Y
                    "P1_BUTTON3": "JOYCODE_1_BUTTON1",           # Left Kick -> A
                    "P1_BUTTON4": "JOYCODE_1_BUTTON2",           # Right Kick -> B
                    "P2_BUTTON1": "JOYCODE_2_BUTTON3",
                    "P2_BUTTON2": "JOYCODE_2_BUTTON4",
                    "P2_BUTTON3": "JOYCODE_2_BUTTON1",
                    "P2_BUTTON4": "JOYCODE_2_BUTTON2",
                }
            },
            "tekkent": {
                "name": "Tekken Tag Layout",
                "description": "5-button Tekken Tag layout: LP(X), RP(Y), LK(RB), RK(A), Tag(B)",
                "mappings": {
                    "P1_BUTTON1": "JOYCODE_1_BUTTON3",           # Left Punch -> X
                    "P1_BUTTON2": "JOYCODE_1_BUTTON4",           # Right Punch -> Y
                    "P1_BUTTON3": "JOYCODE_1_BUTTON6",           # Left Kick -> RB
                    "P1_BUTTON4": "JOYCODE_1_BUTTON1",           # Right Kick -> A
                    "P1_BUTTON5": "JOYCODE_1_BUTTON2",           # Tag -> B
                    "P2_BUTTON1": "JOYCODE_2_BUTTON3",
                    "P2_BUTTON2": "JOYCODE_2_BUTTON4",
                    "P2_BUTTON3": "JOYCODE_2_BUTTON6",
                    "P2_BUTTON4": "JOYCODE_2_BUTTON1",
                    "P2_BUTTON5": "JOYCODE_2_BUTTON2",
                }
            }
        }
        
        # Enhanced preset selection with custom layouts
        preset_frame = ctk.CTkFrame(self.presets_card, fg_color=self.theme_colors["background"], corner_radius=4)
        preset_frame.pack(fill="x", padx=15, pady=10)
        
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
            for preset_id, preset_data in self.mapping_presets.items():
                options.append(preset_data["name"])
            
            # Add separator and custom layouts if they exist
            if self.custom_layouts:
                options.append("--- Custom Layouts ---")
                for layout_id, layout_data in self.custom_layouts.items():
                    options.append(f"Custom: {layout_data['name']}")
            
            return options
        
        # Create dropdown with all preset options
        preset_options = get_all_preset_options()
        preset_descriptions = {
            "All Compatible Games": "Automatically apply the best mapping to ALL compatible fighting games based on their type"
        }
        
        # Add descriptions for built-in presets
        for preset_id, preset_data in self.mapping_presets.items():
            preset_descriptions[preset_data["name"]] = preset_data["description"]
        
        # Add descriptions for custom layouts
        for layout_id, layout_data in self.custom_layouts.items():
            display_name = f"Custom: {layout_data['name']}"
            preset_descriptions[display_name] = layout_data.get('description', 'Custom layout')
        
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
        
        # Custom layout management buttons
        layout_buttons_frame = ctk.CTkFrame(preset_frame, fg_color="transparent")
        layout_buttons_frame.pack(side="left", padx=10, pady=10)
        
        ctk.CTkButton(
            layout_buttons_frame,
            text="Customize",
            command=self.customize_current_layout,
            width=100,
            height=35,
            fg_color=self.theme_colors["primary"],
            hover_color=self.theme_colors["button_hover"]
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            layout_buttons_frame,
            text="Manage",
            command=self.manage_custom_layouts,
            width=90,
            height=35,
            fg_color=self.theme_colors["secondary"],
            hover_color=self.theme_colors["primary"]
        ).pack(side="left", padx=5)
        
        # Description label that updates based on selection
        self.description_label = ctk.CTkLabel(
            self.presets_card,
            text=preset_descriptions[preset_options[0]],
            font=("Arial", 12),
            text_color=self.theme_colors["text_dimmed"],
            wraplength=800,
            justify="left"
        )
        self.description_label.pack(padx=15, pady=(0, 15))
        
        # Store preset descriptions for easy access
        self.preset_descriptions = preset_descriptions

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

    # ====================================================================
    # CUSTOM LAYOUT MANAGEMENT METHODS (Added from main app)
    # ====================================================================

    def customize_current_layout(self):
        """Customize the currently selected layout"""
        selected = self.preset_var.get()
        
        # Skip separator items
        if selected.startswith("---"):
            messagebox.showinfo("Invalid Selection", "Please select a valid preset to customize.")
            return
        
        if selected.startswith("Custom: "):
            # Editing existing custom layout
            custom_name = selected[8:]  # Remove "Custom: " prefix
            base_mappings = None
            base_preset = None
            
            for layout_id, layout_data in self.custom_layouts.items():
                if layout_data['name'] == custom_name:
                    base_mappings = layout_data['mappings']
                    base_preset = layout_data['base_preset']
                    break
                    
            if not base_mappings:
                messagebox.showerror("Error", "Custom layout not found.")
                return
                
        elif selected == "All Compatible Games":
            # For "All Compatible Games", let user pick a base layout
            messagebox.showinfo("Select Base Layout", "Please select a specific preset first, then customize it.")
            return
        else:
            # Creating new custom layout from built-in preset
            base_preset = None
            for preset_id, preset_data in self.mapping_presets.items():
                if preset_data["name"] == selected:
                    base_mappings = preset_data['mappings'].copy()
                    base_preset = preset_id
                    break
            
            if not base_preset:
                messagebox.showwarning("Invalid Selection", "Please select a valid preset to customize.")
                return
        
        # Show customization dialog
        result = self.create_button_remapping_dialog(base_mappings, selected)
        
        if not result["cancelled"]:
            # Get save details
            save_dialog = self.create_layout_save_dialog(selected.replace("Custom: ", ""))
            if not save_dialog["cancelled"]:
                # Save the custom layout
                saved_path = self.save_custom_layout(
                    save_dialog["name"],
                    result["mappings"],
                    base_preset,
                    save_dialog["description"]
                )
                
                if saved_path:
                    # Refresh custom layouts
                    self.load_custom_layouts()
                    
                    # Update dropdown options
                    self.refresh_preset_dropdown()
                    self.preset_var.set(f"Custom: {save_dialog['name']}")
                    
                    messagebox.showinfo("Layout Saved", f"Custom layout '{save_dialog['name']}' saved successfully!")
                    
                    # Refresh the UI
                    self.update_preset_selection(f"Custom: {save_dialog['name']}")

    def manage_custom_layouts(self):
        """Show dialog to manage (delete/rename) custom layouts"""
        if not self.custom_layouts:
            messagebox.showinfo("No Custom Layouts", "No custom layouts found.")
            return
        
        self.show_layout_manager_dialog()
        
        # Refresh after managing
        self.load_custom_layouts()
        self.refresh_preset_dropdown()
        
        # Reset to first option if current selection was deleted
        current_selection = self.preset_var.get()
        current_options = self.preset_dropdown.cget("values")
        if current_selection not in current_options:
            self.preset_var.set(current_options[0])
            self.update_preset_selection(current_options[0])

    def refresh_preset_dropdown(self):
        """Refresh the preset dropdown with current options including custom layouts"""
        # Get all preset options including custom layouts
        options = ["All Compatible Games"]
        
        # Add built-in presets
        for preset_id, preset_data in self.mapping_presets.items():
            options.append(preset_data["name"])
        
        # Add separator and custom layouts if they exist
        if self.custom_layouts:
            options.append("--- Custom Layouts ---")
            for layout_id, layout_data in self.custom_layouts.items():
                options.append(f"Custom: {layout_data['name']}")
        
        # Update dropdown
        self.preset_dropdown.configure(values=options)
        
        # Update descriptions
        self.preset_descriptions = {
            "All Compatible Games": "Automatically apply the best mapping to ALL compatible fighting games based on their type"
        }
        
        # Add descriptions for built-in presets
        for preset_id, preset_data in self.mapping_presets.items():
            self.preset_descriptions[preset_data["name"]] = preset_data["description"]
        
        # Add descriptions for custom layouts
        for layout_id, layout_data in self.custom_layouts.items():
            display_name = f"Custom: {layout_data['name']}"
            self.preset_descriptions[display_name] = layout_data.get('description', 'Custom layout')

    def create_button_remapping_dialog(self, current_mappings, preset_name):
        """Create a dialog for customizing button mappings before applying to games"""
        
        # Create the remapping dialog
        remap_dialog = ctk.CTkToplevel(self)
        remap_dialog.title(f"Customize {preset_name} Button Layout")
        remap_dialog.geometry("900x600")
        remap_dialog.configure(fg_color=self.theme_colors["background"])
        remap_dialog.transient(self)
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
        
        available_buttons = [
            # Standard XInput buttons - these mappings are consistent in MAME
            ("JOYCODE_1_BUTTON1", "Button 1 (A)"),           # XInput A button
            ("JOYCODE_1_BUTTON2", "Button 2 (B)"),           # XInput B button  
            ("JOYCODE_1_BUTTON3", "Button 3 (X)"),           # XInput X button
            ("JOYCODE_1_BUTTON4", "Button 4 (Y)"),           # XInput Y button
            ("JOYCODE_1_BUTTON5", "Button 5 (LB)"),          # XInput Left Bumper
            ("JOYCODE_1_BUTTON6", "Button 6 (RB)"),          # XInput Right Bumper
            
            # Analog triggers - both options
            ("JOYCODE_1_SLIDER1_NEG_SWITCH", "Trigger 1 (LT)"),     # XInput Left Trigger
            ("JOYCODE_1_SLIDER2_NEG_SWITCH", "Trigger 2 (RT)"),     # XInput Right Trigger (your working one)
            
            # Additional buttons if available on controller
            ("JOYCODE_1_BUTTON7", "Button 7 (Back)"),        # XInput Back/Select button
            ("JOYCODE_1_BUTTON8", "Button 8 (Start)"),       # XInput Start button
            ("JOYCODE_1_BUTTON9", "Button 9 (LS)"),          # XInput Left Stick Click
            ("JOYCODE_1_BUTTON10", "Button 10 (RS)"),        # XInput Right Stick Click
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
            """Apply standard 6-button fightstick layout - shows current working mapping"""
            standard_layout = {
                "P1_BUTTON1": "Button 3 (X)",           # Light Punch -> X
                "P1_BUTTON2": "Button 4 (Y)",           # Medium Punch -> Y  
                "P1_BUTTON3": "Button 6 (RB)",          # Heavy Punch -> Right Bumper
                "P1_BUTTON4": "Button 1 (A)",           # Light Kick -> A
                "P1_BUTTON5": "Button 2 (B)",           # Medium Kick -> B
                "P1_BUTTON6": "Trigger 2 (RT)"          # Heavy Kick -> Right Trigger (this is your working one)
            }
            for control, button_name in standard_layout.items():
                if control in dropdown_vars:
                    dropdown_vars[control].set(button_name)

        def apply_alternative_layout():
            """Apply alternative layout using different buttons"""
            alt_layout = {
                "P1_BUTTON1": "Button 3 (X)",
                "P1_BUTTON2": "Button 4 (Y)",
                "P1_BUTTON3": "Button 5 (LB)",          # Heavy Punch -> Left Bumper instead of RB
                "P1_BUTTON4": "Button 1 (A)",
                "P1_BUTTON5": "Button 2 (B)",
                "P1_BUTTON6": "Button 6 (RB)"           # Heavy Kick -> Right Bumper instead of RT
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

    def create_layout_save_dialog(self, base_name):
        """Dialog to get name and description for saving custom layout"""
        save_dialog = ctk.CTkToplevel(self)
        save_dialog.title("Save Custom Layout")
        save_dialog.geometry("400x300")
        save_dialog.configure(fg_color=self.theme_colors["background"])
        save_dialog.transient(self)
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

    def show_layout_manager_dialog(self):
        """Dialog to manage existing custom layouts"""
        manager_dialog = ctk.CTkToplevel(self)
        manager_dialog.title("Manage Custom Layouts")
        manager_dialog.geometry("600x400")
        manager_dialog.configure(fg_color=self.theme_colors["background"])
        manager_dialog.transient(self)
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
                    self.load_custom_layouts()
                    manager_dialog.destroy()
                    messagebox.showinfo("Deleted", f"Custom layout '{layout_name}' deleted.")
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

    def save_custom_layout(self, layout_name, mappings, base_preset, description=""):
        """Save a custom fightstick layout to file"""
        try:
            # Ensure directory exists
            if not self.layouts_dir:
                return None
                
            os.makedirs(self.layouts_dir, exist_ok=True)
            
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

    # ====================================================================
    # EXISTING METHODS (Keep all the original methods)
    # ====================================================================

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

    def get_display_name_for_rom(self, rom_name):
        """Get enhanced display name showing clone relationships"""
        
        # Get base description
        if rom_name in self.gamedata_json:
            base_description = self.gamedata_json[rom_name].get('description', rom_name)
        else:
            base_description = rom_name
        
        # Check if this ROM is a clone
        parent_rom = self.find_parent_rom(rom_name)
        if parent_rom:
            # Get parent description for nicer display
            if parent_rom in self.gamedata_json:
                parent_description = self.gamedata_json[parent_rom].get('description', parent_rom)
                # Extract just the game name (before first parenthesis)
                parent_game_name = parent_description.split('(')[0].strip()
            else:
                parent_game_name = parent_rom.upper()
            
            return f"{base_description} [Clone of {parent_game_name}]"
        
        return base_description

    def is_rom_clone(self, rom_name):
        """Check if a ROM is a clone"""
        return self.find_parent_rom(rom_name) is not None

    def get_games_for_mapping_enhanced(self, mapping_type):
        """Enhanced version that includes clone information and better sorting"""
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
            is_clone = self.is_rom_clone(rom_name)
            
            if rom_name in self.gamedata_json:
                rom_data = self.gamedata_json[rom_name]
                
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
                # Get enhanced display name
                display_name = self.get_display_name_for_rom(rom_name)
                games.append((rom_name, display_name, is_clone))
        
        # Enhanced sorting: Parents first, then clones, alphabetically within each group
        def sort_key(game_tuple):
            rom_name, display_name, is_clone = game_tuple
            
            # Primary sort: parents before clones
            clone_priority = 1 if is_clone else 0
            
            # Secondary sort: alphabetical by display name
            alpha_sort = display_name.lower()
            
            return (clone_priority, alpha_sort)
        
        return sorted(games, key=sort_key)

    # Update your update_preset_selection method to use enhanced display:

    def update_preset_selection(self, choice):
        """Update game list based on preset selection with enhanced clone display"""
        self.games_listbox.delete(0, tk.END)
        self.current_games = []
        
        if not self.mame_dir or not self.available_roms:
            self.games_listbox.insert(tk.END, "No MAME directory set or no ROMs found")
            return
        
        # Update description label
        self.description_label.configure(text=self.preset_descriptions.get(choice, ""))
        
        # Skip separator items
        if choice.startswith("---"):
            return
        
        # Find games based on mapping type
        games_found = []
        
        if choice == "All Compatible Games":
            # Show all compatible games from all presets with grouping
            preset_groups = {}
            
            for preset_id, preset_data in self.mapping_presets.items():
                preset_games = self.get_games_for_mapping_enhanced(preset_id)
                preset_groups[preset_data["name"]] = preset_games
                
                for rom_name, display_name, is_clone in preset_games:
                    games_found.append((rom_name, display_name, is_clone, preset_id))
        
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
                if base_preset in self.mapping_presets:
                    preset_games = self.get_games_for_mapping_enhanced(base_preset)
                    for rom_name, display_name, is_clone in preset_games:
                        games_found.append((rom_name, display_name, is_clone, f"custom_{custom_name}"))
        else:
            # Single preset mode
            selected_preset = None
            for preset_id, preset_data in self.mapping_presets.items():
                if preset_data["name"] == choice:
                    selected_preset = preset_id
                    break
            
            if selected_preset:
                preset_games = self.get_games_for_mapping_enhanced(selected_preset)
                for rom_name, display_name, is_clone in preset_games:
                    games_found.append((rom_name, display_name, is_clone, selected_preset))
        
        # Populate listbox with enhanced display
        if not games_found:
            self.games_listbox.insert(tk.END, "No compatible games found")
        else:
            if choice == "All Compatible Games":
                # Group by preset type with enhanced display
                games_by_type = {}
                for rom_name, display_name, is_clone, preset_id in games_found:
                    if preset_id.startswith("custom_"):
                        preset_name = f"Custom: {preset_id[7:]}"
                    else:
                        preset_name = self.mapping_presets[preset_id]["name"]
                    
                    if preset_name not in games_by_type:
                        games_by_type[preset_name] = []
                    games_by_type[preset_name].append((rom_name, display_name, is_clone, preset_id))
                
                for preset_name, preset_games in games_by_type.items():
                    # Count parents and clones
                    parent_count = sum(1 for _, _, is_clone, _ in preset_games if not is_clone)
                    clone_count = sum(1 for _, _, is_clone, _ in preset_games if is_clone)
                    
                    if clone_count > 0:
                        header_text = f"--- {preset_name} ({parent_count} games, {clone_count} clones) ---"
                    else:
                        header_text = f"--- {preset_name} ({parent_count} games) ---"
                    
                    self.games_listbox.insert(tk.END, header_text)
                    
                    for rom_name, display_name, is_clone, preset_id in preset_games:
                        # Indent clones slightly
                        if is_clone:
                            display_text = f"    {rom_name} - {display_name}"
                        else:
                            display_text = f"  {rom_name} - {display_name}"
                        
                        self.games_listbox.insert(tk.END, display_text)
                
                # Select all non-header items
                for i in range(self.games_listbox.size()):
                    item_text = self.games_listbox.get(i)
                    if not item_text.startswith("---"):
                        self.games_listbox.selection_set(i)
            else:
                # Single preset display - simple and clean
                for rom_name, display_name, is_clone, preset_id in games_found:
                    display_text = f"{rom_name} - {display_name}"
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
        """Apply fightstick mappings to selected games with enhanced custom layout support"""
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
                    if preset_id.startswith("custom_"):
                        preset_name = f"Custom: {preset_id[7:]}"
                    else:
                        preset_name = self.mapping_presets[preset_id]["name"]
                    
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
            
            for layout_id, layout_data in self.custom_layouts.items():
                if layout_data['name'] == custom_name:
                    custom_layout = layout_data
                    break
            
            if not custom_layout:
                messagebox.showerror("Error", "Custom layout not found.")
                return
            
            # Get selected games
            for index in selected_indices:
                if index < len(self.current_games):
                    rom_name = self.current_games[index][0]
                    games_to_process.append({
                        'rom_name': rom_name,
                        'preset_id': f"custom_{custom_name}",
                        'preset_name': f"Custom: {custom_name}"
                    })
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
                
                # Get the mappings for this specific preset
                if preset_id.startswith("custom_"):
                    # Use custom layout mappings
                    custom_name = preset_id[7:]  # Remove "custom_" prefix
                    custom_layout = None
                    
                    for layout_id, layout_data in self.custom_layouts.items():
                        if layout_data['name'] == custom_name:
                            custom_layout = layout_data
                            break
                    
                    if custom_layout:
                        button_mappings = custom_layout['mappings']
                    else:
                        raise Exception(f"Custom layout '{custom_name}' not found")
                else:
                    # Use built-in preset mappings
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

    def find_parent_rom(self, clone_rom_name):
        """Find the parent ROM for a clone by checking gamedata.json structure"""
        
        # Method 1: Check if clone has explicit parent/cloneof field
        if clone_rom_name in self.gamedata_json:
            rom_data = self.gamedata_json[clone_rom_name]
            if 'parent' in rom_data:
                return rom_data['parent']
            if 'cloneof' in rom_data:
                return rom_data['cloneof']
        
        # Method 2: Search through all ROMs to find where this clone is listed
        for potential_parent, parent_data in self.gamedata_json.items():
            if 'clones' in parent_data and isinstance(parent_data['clones'], dict):
                if clone_rom_name in parent_data['clones']:
                    print(f"  Found {clone_rom_name} as clone of {potential_parent}")
                    return potential_parent
        
        # Method 3: Fallback to common patterns if not found in structure
        common_parents = {
            'sf2rb': 'sf2ce',      # Rainbow Edition -> Champion Edition
            'sf2rb2': 'sf2ce',     
            'sf2rb3': 'sf2ce',     
            'sf2red': 'sf2ce',     
            'sf2reda': 'sf2ce',    
            'sf2ce': 'sf2',        # Champion Edition -> Original
            'sf2hf': 'sf2',        # Hyper Fighting -> Original
            'sf2t': 'sf2',         # Turbo -> Original
        }
        
        parent = common_parents.get(clone_rom_name, None)
        if parent:
            print(f"  Using fallback parent mapping: {clone_rom_name} -> {parent}")
        
        return parent

    def get_control_data_with_parent_fallback(self, rom_name, mame_control):
        """Get control data for a ROM, falling back to parent if it's a clone"""
        
        print(f"  Looking for {mame_control} control data for {rom_name}")
        
        # First try the ROM itself
        if rom_name in self.gamedata_json:
            rom_data = self.gamedata_json[rom_name]
            if 'controls' in rom_data and rom_data['controls']:
                if mame_control in rom_data['controls']:
                    control_data = rom_data['controls'][mame_control]
                    if isinstance(control_data, dict) and 'tag' in control_data and 'mask' in control_data:
                        print(f"  ✓ Found control data in {rom_name}: {control_data}")
                        return control_data, rom_name
            else:
                print(f"  {rom_name} has no controls section")
        else:
            print(f"  {rom_name} not found in gamedata")
        
        # If not found, try the parent ROM
        parent_rom = self.find_parent_rom(rom_name)
        if parent_rom:
            print(f"  {rom_name} is clone of {parent_rom}, checking parent...")
            if parent_rom in self.gamedata_json:
                parent_data = self.gamedata_json[parent_rom]
                if 'controls' in parent_data and parent_data['controls']:
                    if mame_control in parent_data['controls']:
                        control_data = parent_data['controls'][mame_control]
                        if isinstance(control_data, dict) and 'tag' in control_data and 'mask' in control_data:
                            print(f"  ✓ Found control data in parent {parent_rom}: {control_data}")
                            return control_data, parent_rom
                    else:
                        print(f"  {mame_control} not found in parent {parent_rom}")
                else:
                    print(f"  Parent {parent_rom} has no controls section")
            
            # If parent doesn't have it, try parent's parent (recursively)
            grandparent_data, source_rom = self.get_control_data_with_parent_fallback(parent_rom, mame_control)
            if grandparent_data:
                print(f"  ✓ Found control data in grandparent chain: {source_rom}")
                return grandparent_data, source_rom
        else:
            print(f"  No parent found for {rom_name}")
        
        print(f"  ✗ No control data found for {mame_control} in {rom_name} or its parents")
        return None, None

    # Enhanced debug method to check specific ROM relationships:
    def debug_specific_roms(self, roms_to_check=None):
        """Debug specific ROMs to understand their control inheritance"""
        if roms_to_check is None:
            roms_to_check = ['sf2', 'sf2ce', 'sf2rb', 'sf2hf']
        
        print(f"\n=== DEBUGGING SPECIFIC ROMS: {roms_to_check} ===")
        
        for rom in roms_to_check:
            print(f"\n--- {rom} ---")
            
            # Check if ROM exists in gamedata
            if rom in self.gamedata_json:
                rom_data = self.gamedata_json[rom]
                print(f"✓ Found in gamedata")
                
                # Check for parent info
                parent = rom_data.get('parent', rom_data.get('cloneof', None))
                if parent:
                    print(f"  Explicit parent: {parent}")
                
                # Check if it has controls
                if 'controls' in rom_data and rom_data['controls']:
                    control_count = len(rom_data['controls'])
                    print(f"  Has controls: {control_count} entries")
                    
                    # Check for P1_BUTTON6 specifically
                    if 'P1_BUTTON6' in rom_data['controls']:
                        p1b6 = rom_data['controls']['P1_BUTTON6']
                        print(f"  P1_BUTTON6: tag={p1b6.get('tag')}, mask={p1b6.get('mask')}")
                    else:
                        print(f"  P1_BUTTON6: NOT FOUND")
                else:
                    print(f"  No controls section")
                
                # Check if it has clones
                if 'clones' in rom_data:
                    clone_count = len(rom_data['clones'])
                    clone_names = list(rom_data['clones'].keys())[:5]  # First 5 clones
                    print(f"  Has clones: {clone_count} ({clone_names}...)")
            else:
                print(f"✗ NOT found in gamedata")
            
            # Test parent lookup
            parent = self.find_parent_rom(rom)
            print(f"  Parent lookup result: {parent}")
            
            # Test control inheritance for P1_BUTTON6
            control_data, source = self.get_control_data_with_parent_fallback(rom, 'P1_BUTTON6')
            if control_data:
                print(f"  P1_BUTTON6 inheritance: {control_data} (from {source})")
            else:
                print(f"  P1_BUTTON6 inheritance: FAILED")
        
        print("="*60)
    
    def configure_game_fightstick_mapping(self, rom_name, button_mappings, backup_cfg, create_missing, update_existing, mame_version):
        """Configure a single game's CFG file with fightstick button mappings"""
        if rom_name == "sf2rb":
            print(f"\n=== DEBUGGING SF2RB PARENT LOOKUP ===")
            parent = self.find_parent_rom("sf2rb")
            print(f"Parent found: {parent}")
            
            if parent == "sf2ce":
                control_data, source = self.get_control_data_with_parent_fallback("sf2rb", "P1_BUTTON1")
                print(f"P1_BUTTON1 data: {control_data} from {source}")
                
                control_data, source = self.get_control_data_with_parent_fallback("sf2rb", "P1_BUTTON6")  
                print(f"P1_BUTTON6 data: {control_data} from {source}")
            else:
                print(f"ERROR: Parent lookup failed!")
        
        try:
            # Add debugging for specific ROMs
            if rom_name in ['sf2', 'sf2ce', 'sf2rb']:
                print(f"\n=== DEBUGGING {rom_name} CONFIGURATION ===")
                self.debug_specific_roms([rom_name])
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

    # Fix the mame_control_to_port_data method - remove the broken defvalue logic:
    def mame_control_to_port_data(self, mame_control, joycode, mame_version="new", rom_name=None):
        """Convert MAME control name and joycode to port data for CFG file using gamedata with clone support"""
        try:
            print(f"Converting {mame_control} -> {joycode} (MAME {mame_version}) for ROM: {rom_name}")
            
            # Get the port info using parent fallback for clones
            port_info = None
            source_rom = None
            
            if rom_name:
                control_data, source_rom = self.get_control_data_with_parent_fallback(rom_name, mame_control)
                if control_data:
                    port_info = {
                        'tag': control_data['tag'],
                        'type': mame_control,
                        'mask': control_data['mask']
                    }
                    print(f"  ✓ Using clone inheritance from {source_rom}: {port_info}")
            
            # ONLY search through all gamedata if clone inheritance completely failed
            if not port_info:
                print(f"  Clone inheritance failed, searching all gamedata...")
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
                                print(f"  Found fallback control data in {rom_name_search}: {port_info}")
                                break
            
            # Enhanced fallback for missing controls (only if everything else failed)
            if not port_info:
                print(f"  Using enhanced fallback for {mame_control}")
                
                # Determine tag based on control type and button number
                if mame_control.startswith('P1_'):
                    if 'BUTTON1' in mame_control or 'BUTTON2' in mame_control or 'BUTTON3' in mame_control:
                        tag = ":IN1"
                    elif 'BUTTON4' in mame_control or 'BUTTON5' in mame_control or 'BUTTON6' in mame_control:
                        tag = ":IN2"
                    else:
                        tag = ":EXTRA"
                elif mame_control.startswith('P2_'):
                    if 'BUTTON1' in mame_control or 'BUTTON2' in mame_control or 'BUTTON3' in mame_control:
                        tag = ":IN1"
                    elif 'BUTTON4' in mame_control or 'BUTTON5' in mame_control or 'BUTTON6' in mame_control:
                        tag = ":IN2"
                    else:
                        tag = ":EXTRA"
                else:
                    tag = ":INPUTS"
                
                # Generate reasonable mask values based on SF2 structure
                button_masks = {
                    'P1_BUTTON1': '16',    
                    'P1_BUTTON2': '32',
                    'P1_BUTTON3': '64',
                    'P1_BUTTON4': '1',
                    'P1_BUTTON5': '2',
                    'P1_BUTTON6': '4',     
                    'P2_BUTTON1': '4096',  
                    'P2_BUTTON2': '8192',
                    'P2_BUTTON3': '16384',
                    'P2_BUTTON4': '16',
                    'P2_BUTTON5': '32',
                    'P2_BUTTON6': '64',    
                }
                
                mask = button_masks.get(mame_control, "1")
                
                port_info = {
                    'tag': tag,
                    'type': mame_control,
                    'mask': mask
                }
                print(f"  Generated enhanced fallback: {port_info}")
            
            # Handle MAME version differences for analog controls
            original_joycode = joycode
            if mame_version == "old":
                joycode = joycode.replace("SLIDER2", "ZAXIS")
                joycode = joycode.replace("SLIDER1", "ZAXIS_UP")
            elif mame_version == "new":
                joycode = joycode.replace("ZAXIS", "SLIDER2")
                joycode = joycode.replace("ZAXIS_UP", "SLIDER1")
            
            if joycode != original_joycode:
                print(f"  Converted joycode: {original_joycode} -> {joycode}")
            
            # Simple defvalue logic - use the mask value
            defvalue = port_info['mask']
            
            # Only set defvalue=0 for very specific cases
            special_zero_defvalue_tags = [
                ":JVS_", ":MAHJONG", ":HANAFUDA", ":KEYPAD",
            ]
            
            for special_tag in special_zero_defvalue_tags:
                if port_info['tag'].startswith(special_tag):
                    defvalue = "0"
                    print(f"  Special tag {special_tag} detected, setting defvalue=0")
                    break
            
            if port_info['mask'] == "0":
                defvalue = "0"
            
            result = {
                'tag': port_info['tag'],
                'type': port_info['type'],
                'mask': port_info['mask'],
                'defvalue': defvalue,
                'newseq': joycode
            }
            
            print(f"  Final result: {result}")
            print(f"  Source: {source_rom or 'fallback'}")
            return result
            
        except Exception as e:
            print(f"  ERROR converting {mame_control} to port data: {e}")
            import traceback
            traceback.print_exc()
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
from doctest import debug_script
import subprocess
import sys
import os
import json
import re
import time
from typing import Dict, Optional, Set, List, Tuple
import xml.etree.ElementTree as ET
from PyQt5.QtWidgets import (QApplication, QComboBox, QDesktopWidget, QDialog, QListWidget, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, 
                            QSplitter, QLabel, QLineEdit, QTextEdit, QFrame, QPushButton, 
                            QCheckBox, QScrollArea, QGridLayout, QMessageBox, QFileDialog)
from PyQt5.QtCore import QTimer, Qt, QSize, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QColor, QPalette
import sqlite3
import time

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
    
class GameListWidget(QTextEdit):
    """Custom widget for the game list with highlighting support"""
    gameSelected = pyqtSignal(str, int)  # Signal for game selection (game_name, line_number)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Arial", 12))
        self.setCursor(Qt.PointingHandCursor)
        self.selected_line = None
        
        # Setup document for text formatting
        self.document().setDefaultStyleSheet("a { text-decoration: none; color: white; }")
        
    def mousePressEvent(self, event):
        """Handle mouse click event to select a game"""
        cursor = self.cursorForPosition(event.pos())
        block_number = cursor.blockNumber() + 1  # Lines start at 1
        
        # Get text content of the line
        cursor.select(QTextCursor.LineUnderCursor)
        line = cursor.selectedText()
        
        # Remove prefix indicators
        if line.startswith("* "):
            line = line[2:]
        if line.startswith("+ ") or line.startswith("- "):
            line = line[2:]
        
        # Extract ROM name
        rom_name = line.split(" - ")[0] if " - " in line else line
        
        # Highlight the selected line
        self.highlight_line(block_number)
        
        # Emit signal with ROM name and line number
        self.gameSelected.emit(rom_name, block_number)
    
    def highlight_line(self, line_number):
        """Highlight the selected line and remove highlight from previously selected line"""
        # Create background color for highlighting
        highlight_color = QColor(26, 95, 180)  # Similar to #1a5fb4
        
        # Create a cursor for the document
        cursor = QTextCursor(self.document())
        
        # Clear previous highlighting if any
        if self.selected_line is not None:
            cursor.setPosition(0)
            for _ in range(self.selected_line - 1):
                cursor.movePosition(QTextCursor.NextBlock)
            
            # Select the previously highlighted line
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            
            # Remove formatting
            fmt = cursor.charFormat()
            fmt.setBackground(Qt.transparent)
            cursor.setCharFormat(fmt)
        
        # Apply new highlighting
        cursor.setPosition(0)
        for _ in range(line_number - 1):
            cursor.movePosition(QTextCursor.NextBlock)
        
        # Select the line to highlight
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        
        # Apply highlighting
        fmt = cursor.charFormat()
        fmt.setBackground(highlight_color)
        fmt.setForeground(Qt.white)
        cursor.setCharFormat(fmt)
        
        # Store the selected line
        self.selected_line = line_number
        
        # REMOVE THIS LINE:
        # self.ensureCursorVisible()


class PositionManager:
    """A simplified position manager for the PyQt implementation"""
    def __init__(self, parent):
        self.parent = parent
        self.positions = {}


class MAMEControlConfig(QMainWindow):
    def __init__(self, preview_only=False):
        super().__init__()
        
        # Initialize core attributes needed for both modes
        self.visible_control_types = ["BUTTON", "JOYSTICK"]
        self.default_controls = {}
        self.gamedata_json = {}
        self.available_roms = set()
        self.custom_configs = {}
        self.current_game = None
        self.use_xinput = True
        self.preview_window = None  # Track preview window

        self.rom_data_cache = {}
        self.preview_processes = []  # Track any preview processes we launch

        self.settings_cache = {}  # Cache for loaded settings
        self.text_positions_cache = {}  # Cache for loaded text positions
        self.appearance_settings_cache = None  # Cache for text appearance settings

        # Logo size settings (as percentages)
        self.logo_width_percentage = 15
        self.logo_height_percentage = 15
        
        # NEW CODE: Use the centralized directory structure method
        self.initialize_directory_structure()
        
        # Check for critical directory
        if not self.mame_dir:
            QMessageBox.critical(self, "Error", "Please place this script in the MAME directory!")
            sys.exit(1)
        
        print(f"Application directory: {self.app_dir}")
        print(f"MAME directory: {self.mame_dir}")
        print(f"Preview directory: {self.preview_dir}")
        print(f"Settings directory: {self.settings_dir}")
        print(f"Info directory: {self.info_dir}")
        
        # Skip main window setup if in preview-only mode
        if not preview_only:
            # Configure the window
            self.setWindowTitle("MAME Control Configuration Checker")
                
            # Create the interface
            self.create_layout()
            
            # Load all data
            self.load_all_data()
        else:
            # For preview-only mode, just initialize minimal attributes
            self.load_settings()  # Still need settings for preview
            self.load_gamedata_json()  # Need game data for preview
            self.hide()  # Hide the main window

        # Ensure the window is maximizable
        from PyQt5.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(800, 600)  # Set a reasonable minimum size
    
    def initialize_directory_structure(self):
        """Initialize the standardized directory structure"""
        self.app_dir = get_application_path()
        self.mame_dir = get_mame_parent_dir(self.app_dir)
        
        # Set up directory structure - all data will be stored in these locations
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        self.settings_dir = os.path.join(self.preview_dir, "settings")
        self.info_dir = os.path.join(self.settings_dir, "info")

        # Create these directories if they don't exist
        os.makedirs(self.preview_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        os.makedirs(self.info_dir, exist_ok=True)
        
        # Define standard paths for key files
        self.gamedata_path = os.path.join(self.settings_dir, "gamedata.json")
        self.db_path = os.path.join(self.settings_dir, "gamedata.db")
        self.settings_path = os.path.join(self.settings_dir, "control_config_settings.json")
        
        # Return if the directories were created successfully
        return (os.path.exists(self.preview_dir) and 
                os.path.exists(self.settings_dir) and 
                os.path.exists(self.info_dir))
    
    def get_application_path(self):
        """Get the base path for the application (handles PyInstaller bundling)"""
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            return os.path.dirname(sys.executable)
        else:
            # Running as script
            return os.path.dirname(os.path.abspath(__file__))
            
    def find_mame_directory(self) -> Optional[str]:
        """Find the MAME directory containing necessary files"""
        # First check in the application directory
        app_dir = self.get_application_path()
        print(f"Application directory: {app_dir}")
        
        # If we're in the preview folder, try the parent directory first
        if os.path.basename(app_dir).lower() == "preview":
            parent_dir = os.path.dirname(app_dir)
            parent_roms = os.path.join(parent_dir, "roms")
            
            if os.path.exists(parent_roms):
                print(f"Found MAME directory (parent of preview): {parent_dir}")
                return parent_dir
        
        # Check for gamedata.json
        app_gamedata = os.path.join(app_dir, "gamedata.json")
        if os.path.exists(app_gamedata):
            print(f"Using bundled gamedata.json: {app_dir}")
            return app_dir
        
        # Check current directory
        current_dir = os.path.abspath(os.path.dirname(__file__))
        current_gamedata = os.path.join(current_dir, "gamedata.json")
        
        if os.path.exists(current_gamedata):
            print(f"Found MAME directory: {current_dir}")
            return current_dir
        
        # Check for roms directory
        app_roms = os.path.join(app_dir, "roms")
        if os.path.exists(app_roms):
            print(f"Found MAME directory with roms folder: {app_dir}")
            return app_dir
                
        # Then check common MAME paths
        common_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), "MAME"),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), "MAME"),
            "C:\\MAME",
            "D:\\MAME"
        ]
        
        for path in common_paths:
            gamedata_path = os.path.join(path, "gamedata.json")
            if os.path.exists(gamedata_path):
                print(f"Found MAME directory: {path}")
                return path
        
        print("Error: gamedata.json not found in known locations")
        print(f"Current app directory: {app_dir}")
        print(f"Current working directory: {os.getcwd()}")
        
        # As a last resort, walk up from current directory to find roms
        check_dir = os.getcwd()
        for _ in range(3):  # Check up to 3 levels up
            roms_dir = os.path.join(check_dir, "roms")
            if os.path.exists(roms_dir):
                print(f"Found MAME directory by locating roms folder: {check_dir}")
                return check_dir
            check_dir = os.path.dirname(check_dir)
                
        return None
        
    def select_first_rom(self):
        """Select and display the first available ROM with improved performance"""
        print("\n=== Auto-selecting first ROM ===")
        
        try:
            # Get the first available ROM that has game data (using cache when possible)
            available_games = []
            
            # First check cache to avoid database hits
            if hasattr(self, 'rom_data_cache'):
                available_games = sorted([rom for rom in self.available_roms if rom in self.rom_data_cache])
                
            # If no cached games, do a minimal lookup
            if not available_games:
                if hasattr(self, 'db_path') and os.path.exists(self.db_path):
                    # Use database for faster lookup
                    try:
                        conn = sqlite3.connect(self.db_path)
                        cursor = conn.cursor()
                        cursor.execute("SELECT rom_name FROM games ORDER BY rom_name LIMIT 5")
                        db_roms = [row[0] for row in cursor.fetchall()]
                        conn.close()
                        
                        # Filter to only those that are in available_roms
                        available_games = [rom for rom in db_roms if rom in self.available_roms]
                    except:
                        pass
            
            # If still no games found, do a full scan
            if not available_games:
                available_games = sorted([rom for rom in self.available_roms if self.get_game_data(rom)])
            
            if not available_games:
                print("No ROMs with game data found")
                return
                    
            first_rom = available_games[0]
            print(f"Selected first ROM: {first_rom}")
            
            # Find the corresponding line in the game list
            line_number = None
            for i in range(self.game_list.document().blockCount()):
                line = self.game_list.document().findBlockByNumber(i).text()
                if first_rom in line:
                    line_number = i + 1  # Lines are 1-indexed
                    break
            
            if line_number is None:
                print(f"Could not find '{first_rom}' in game list")
                return
            
            # Highlight the selected line
            self.game_list.highlight_line(line_number)
            
            # Update game data display
            self.on_game_selected(first_rom, line_number)
                    
        except Exception as e:
            print(f"Error in auto-selection: {e}")
            import traceback
            traceback.print_exc()
            
    def compare_controls(self, game_data: Dict, cfg_controls: Dict) -> List[Tuple[str, str, str, bool]]:
        """Compare controls with game-specific and default mappings"""
        comparisons = []
        
        # Debug output
        has_defaults = hasattr(self, 'default_controls') and self.default_controls
        print(f"Compare controls: ROM={game_data['romname']}, " 
            f"Custom CFG={len(cfg_controls)}, "
            f"Default Controls Available={has_defaults and len(self.default_controls)}, "
            f"XInput={self.use_xinput}")
        
        # Convert default controls to XInput if needed
        default_controls = {}
        if has_defaults:
            for control, mapping in self.default_controls.items():
                if self.use_xinput:
                    default_controls[control] = self.convert_mapping(mapping, True)
                else:
                    default_controls[control] = mapping
        
        # Get default controls from game data
        for player in game_data.get('players', []):
            player_num = player['number']
            for label in player.get('labels', []):
                control_name = label['name']
                default_label = label['value']
                
                # Game-specific cfg has highest priority
                if control_name in cfg_controls:
                    current_mapping = cfg_controls[control_name]
                    is_different = True  # Custom mapping
                # Default.cfg has second priority - already converted to XInput if needed
                elif control_name in default_controls:
                    current_mapping = default_controls[control_name]
                    is_different = False  # Default mapping from default.cfg
                else:
                    current_mapping = "Not mapped"
                    is_different = False
                    
                comparisons.append((control_name, default_label, current_mapping, is_different))
        
        # Debug - print a few samples
        if comparisons:
            print(f"Generated {len(comparisons)} control comparisons. Samples:")
            for i, (name, label, mapping, diff) in enumerate(comparisons[:3]):
                src = "Custom" if diff else ("Default" if mapping != "Not mapped" else "None")
                print(f"  {name}: {label} -> {mapping} ({src})")
        
        return comparisons
    
    def format_control_name(self, control_name: str) -> str:
        """Convert MAME control names to friendly names based on input type"""
        if not self.use_xinput:
            return control_name
            
        # Split control name into parts (e.g., 'P1_BUTTON1' -> ['P1', 'BUTTON1'])
        parts = control_name.split('_')
        if len(parts) < 2:
            return control_name
            
        player_num = parts[0]  # e.g., 'P1'
        control_type = '_'.join(parts[1:])  # Join rest in case of JOYSTICK_UP etc.
        
        # Mapping dictionary for controls based on official XInput mapping
        control_mappings = {
            'BUTTON1': 'A Button',
            'BUTTON2': 'B Button',
            'BUTTON3': 'X Button',
            'BUTTON4': 'Y Button',
            'BUTTON5': 'LB Button',
            'BUTTON6': 'RB Button',
            'BUTTON7': 'LT Button',      # Left Trigger (axis)
            'BUTTON8': 'RT Button',      # Right Trigger (axis)
            'BUTTON9': 'LSB Button',     # Left Stick Button
            'BUTTON10': 'RSB Button',    # Right Stick Button
            'JOYSTICK_UP': 'Left Stick (Up)',
            'JOYSTICK_DOWN': 'Left Stick (Down)',
            'JOYSTICK_LEFT': 'Left Stick (Left)',
            'JOYSTICK_RIGHT': 'Left Stick (Right)',
            'JOYSTICK2_UP': 'Right Stick (Up)',
            'JOYSTICK2_DOWN': 'Right Stick (Down)',
            'JOYSTICK2_LEFT': 'Right Stick (Left)',
            'JOYSTICK2_RIGHT': 'Right Stick (Right)',
        }
        
        # Check if we have a mapping for this control
        if control_type in control_mappings:
            return f"{player_num} {control_mappings[control_type]}"
        
        return control_name
    
    def convert_mapping(self, mapping: str, to_xinput: bool) -> str:
        """Convert between JOYCODE and XInput mappings"""
        xinput_mappings = {
            'JOYCODE_1_BUTTON1': 'XINPUT_1_A',           # A Button
            'JOYCODE_1_BUTTON2': 'XINPUT_1_B',           # B Button
            'JOYCODE_1_BUTTON3': 'XINPUT_1_X',           # X Button
            'JOYCODE_1_BUTTON4': 'XINPUT_1_Y',           # Y Button
            'JOYCODE_1_BUTTON5': 'XINPUT_1_SHOULDER_L',  # Left Bumper
            'JOYCODE_1_BUTTON6': 'XINPUT_1_SHOULDER_R',  # Right Bumper
            'JOYCODE_1_BUTTON7': 'XINPUT_1_TRIGGER_L',   # Left Trigger
            'JOYCODE_1_BUTTON8': 'XINPUT_1_TRIGGER_R',   # Right Trigger
            'JOYCODE_1_BUTTON9': 'XINPUT_1_THUMB_L',     # Left Stick Button
            'JOYCODE_1_BUTTON10': 'XINPUT_1_THUMB_R',    # Right Stick Button
            'JOYCODE_1_HATUP': 'XINPUT_1_DPAD_UP',       # D-Pad Up
            'JOYCODE_1_HATDOWN': 'XINPUT_1_DPAD_DOWN',   # D-Pad Down
            'JOYCODE_1_HATLEFT': 'XINPUT_1_DPAD_LEFT',   # D-Pad Left
            'JOYCODE_1_HATRIGHT': 'XINPUT_1_DPAD_RIGHT', # D-Pad Right
            'JOYCODE_2_BUTTON1': 'XINPUT_2_A',           # A Button
            'JOYCODE_2_BUTTON2': 'XINPUT_2_B',           # B Button
            'JOYCODE_2_BUTTON3': 'XINPUT_2_X',           # X Button
            'JOYCODE_2_BUTTON4': 'XINPUT_2_Y',           # Y Button
            'JOYCODE_2_BUTTON5': 'XINPUT_2_SHOULDER_L',  # Left Bumper
            'JOYCODE_2_BUTTON6': 'XINPUT_2_SHOULDER_R',  # Right Bumper
            'JOYCODE_2_BUTTON7': 'XINPUT_2_TRIGGER_L',   # Left Trigger
            'JOYCODE_2_BUTTON8': 'XINPUT_2_TRIGGER_R',   # Right Trigger
            'JOYCODE_2_BUTTON9': 'XINPUT_2_THUMB_L',     # Left Stick Button
            'JOYCODE_2_BUTTON10': 'XINPUT_2_THUMB_R',    # Right Stick Button
            'JOYCODE_2_HATUP': 'XINPUT_2_DPAD_UP',       # D-Pad Up
            'JOYCODE_2_HATDOWN': 'XINPUT_2_DPAD_DOWN',   # D-Pad Down
            'JOYCODE_2_HATLEFT': 'XINPUT_2_DPAD_LEFT',   # D-Pad Left
            'JOYCODE_2_HATRIGHT': 'XINPUT_2_DPAD_RIGHT', # D-Pad Right
        }
        joycode_mappings = {v: k for k, v in xinput_mappings.items()}
        
        if to_xinput:
            return xinput_mappings.get(mapping, mapping)
        else:
            return joycode_mappings.get(mapping, mapping)
            
    def format_mapping_display(self, mapping: str) -> str:
        """Format the mapping string for display"""
        # Handle XInput mappings
        if "XINPUT" in mapping:
            # Convert XINPUT_1_A to "XInput A"
            parts = mapping.split('_')
            if len(parts) >= 3:
                button_part = ' '.join(parts[2:])
                return f"XInput {button_part}"
                
        # Handle JOYCODE mappings
        elif "JOYCODE" in mapping:
            # Special handling for axis/stick controls
            if "YAXIS_UP" in mapping or "DPADUP" in mapping:
                return "Joy Stick Up"
            elif "YAXIS_DOWN" in mapping or "DPADDOWN" in mapping:
                return "Joy Stick Down"
            elif "XAXIS_LEFT" in mapping or "DPADLEFT" in mapping:
                return "Joy Stick Left"
            elif "XAXIS_RIGHT" in mapping or "DPADRIGHT" in mapping:
                return "Joy Stick Right"
            elif "RYAXIS_NEG" in mapping:  # Right stick Y-axis negative
                return "Joy Right Stick Up"
            elif "RYAXIS_POS" in mapping:  # Right stick Y-axis positive
                return "Joy Right Stick Down"
            elif "RXAXIS_NEG" in mapping:  # Right stick X-axis negative
                return "Joy Right Stick Left"
            elif "RXAXIS_POS" in mapping:  # Right stick X-axis positive
                return "Joy Right Stick Right"
            
            # Standard button format for other joystick controls
            parts = mapping.split('_')
            if len(parts) >= 3:
                joy_num = parts[1]
                control_type = parts[2].capitalize()
                
                # Extract button number for BUTTON types
                if control_type == "Button" and len(parts) >= 4:
                    button_num = parts[3]
                    return f"Joy {joy_num} {control_type} {button_num}"
                else:
                    # Generic format for other controls
                    remainder = '_'.join(parts[3:])
                    return f"Joy {joy_num} {control_type} {remainder}"
        
        return mapping
    
    def parse_cfg_controls(self, cfg_content: str) -> Dict[str, str]:
        """Parse MAME cfg file to extract control mappings"""
        controls = {}
        try:
            # Parse the XML content
            try:
                root = ET.fromstring(cfg_content)
                
                # Find all port elements under input
                input_elem = root.find('.//input')
                if input_elem is not None:
                    print("Found input element")
                    for port in input_elem.findall('port'):
                        control_type = port.get('type')
                        if control_type and control_type.startswith('P') and ('BUTTON' in control_type or 'JOYSTICK' in control_type):
                            # Find the newseq element for the mapping
                            newseq = port.find('.//newseq')
                            if newseq is not None and newseq.text:
                                mapping = newseq.text.strip()
                                controls[control_type] = mapping
                                print(f"Found mapping: {control_type} -> {mapping}")
                else:
                    print("No input element found in XML")
                    
            except ET.ParseError as e:
                print(f"XML parsing failed with error: {str(e)}")
                print("First 100 chars of content:", repr(cfg_content[:100]))
                
        except Exception as e:
            print(f"Unexpected error parsing cfg: {str(e)}")
            
        print(f"Found {len(controls)} control mappings")
        if controls:
            print("Sample mappings:")
            for k, v in list(controls.items())[:3]:
                print(f"  {k}: {v}")
                
        return controls
    
    def toggle_xinput(self):
        """Handle toggling between JOYCODE and XInput mappings"""
        self.use_xinput = self.xinput_toggle.isChecked()
        print(f"XInput toggle set to: {self.use_xinput}")
        
        # Refresh the current game display if one is selected
        if self.current_game:
            # Reload the current game data
            game_data = self.get_game_data(self.current_game)
            if game_data:
                # Create a mock line number
                line_number = 1
                if hasattr(self.game_list, 'selected_line') and self.game_list.selected_line is not None:
                    line_number = self.game_list.selected_line
                    
                # Redisplay the game
                self.on_game_selected(self.current_game, line_number)
    
    def toggle_hide_preview_buttons(self):
        """Toggle whether preview buttons should be hidden"""
        self.hide_preview_buttons = self.hide_buttons_toggle.isChecked()
        print(f"Hide preview buttons set to: {self.hide_preview_buttons}")

    def show_preview(self):
        """Launch the preview window with simplified path handling"""
        if not self.current_game:
            #messagebox.showinfo("No Game Selected", "Please select a game first")
            return
                
        # Get game data
        game_data = self.get_game_data(self.current_game)
        if not game_data:
            #messagebox.showinfo("No Control Data", f"No control data found for {self.current_game}")
            return
        
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
                #messagebox.showerror("Error", "Could not find mame_controls_main.py")
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
            #messagebox.showerror("Error", f"Failed to launch preview: {str(e)}")


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

    def get_gamedata_path(self):
        """Get the path to the gamedata.json file based on new folder structure"""
        # Always store gamedata.json in settings directory
        settings_path = os.path.join(self.settings_dir, "gamedata.json")
        
        # If the file doesn't exist in settings dir, check if it exists in mame root
        # and copy it to the settings dir
        if not os.path.exists(settings_path):
            legacy_paths = [
                os.path.join(self.mame_dir, "gamedata.json"),
                os.path.join(self.mame_dir, "preview", "gamedata.json")
            ]
            
            for legacy_path in legacy_paths:
                if os.path.exists(legacy_path):
                    print(f"Found gamedata.json at legacy path: {legacy_path}")
                    print(f"Copying to new location: {settings_path}")
                    import shutil
                    shutil.copy2(legacy_path, settings_path)
                    break
        
        # Create directory if it doesn't exist (redundant but safe)
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        
        return settings_path
    
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
    
    def _insert_controls(self, cursor, rom_name, controls_dict):
        """Helper method to insert controls into the database"""
        for control_name, control_data in controls_dict.items():
            display_name = control_data.get('name', '')
            if display_name:
                cursor.execute(
                    "INSERT INTO game_controls (rom_name, control_name, display_name) VALUES (?, ?, ?)",
                    (rom_name, control_name, display_name)
                )
    
    # Replace the show_preview method with this:
    def show_preview(self):
        """Show a preview of the control layout with enhanced path handling"""
        if not self.current_game:
            QMessageBox.information(self, "No Game Selected", "Please select a game first")
            return
            
        # Get game data
        game_data = self.get_game_data(self.current_game)
        if not game_data:
            QMessageBox.information(self, "No Control Data", f"No control data found for {self.current_game}")
            return
        
        try:
            # Import the preview window module
            print(f"Attempting to import preview module from: {self.mame_dir}")
            
            # Try multiple possible locations for the preview module
            preview_module_paths = [
                os.path.join(self.app_dir, "mame_controls_preview.py"),
                os.path.join(self.mame_dir, "mame_controls_preview.py"),
                os.path.join(self.mame_dir, "preview", "mame_controls_preview.py")
            ]
            
            # Add directories to sys.path if they're not already there
            for path in [self.app_dir, self.mame_dir, os.path.join(self.mame_dir, "preview")]:
                if path not in sys.path:
                    sys.path.append(path)
                    print(f"Added {path} to sys.path")
            
            # Try to import the module
            found_module = False
            for path in preview_module_paths:
                if os.path.exists(path):
                    print(f"Found preview module at: {path}")
                    found_module = True
                    # Add directory to path if not already there
                    dir_path = os.path.dirname(path)
                    if dir_path not in sys.path:
                        sys.path.append(dir_path)
                        print(f"Added {dir_path} to sys.path")
                    break
                    
            if not found_module:
                QMessageBox.critical(self, "Error", "Could not find mame_controls_preview.py module")
                return
            
            # Import from current directory
            from mame_controls_preview import PreviewWindow
            print("Successfully imported PreviewWindow")
            
            # Create preview window as a modal dialog to ensure it appears on top
            print(f"Creating preview window for {self.current_game}")
            self.preview_window = PreviewWindow(self.current_game, game_data, self.mame_dir, self, 
                                            self.hide_preview_buttons)
            
            # Make preview window modal
            print("Setting preview window as modal")
            self.preview_window.setWindowModality(Qt.ApplicationModal)
            
            # Show the window as a modal dialog
            print("Showing preview window")
            self.preview_window.show()
            self.preview_window.activateWindow()  # Force window to front
            self.preview_window.raise_()  # Raise window to the top
            print("Preview window displayed")
            
        except ImportError as e:
            QMessageBox.critical(self, "Error", f"Could not import preview module: {str(e)}")
            print(f"Import error: {e}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error showing preview: {str(e)}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    
    def get_game_data(self, romname):
        """Get game data with integrated database prioritization"""
        # 1. Check cache first
        if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
            return self.rom_data_cache[romname]
        
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
            
            # Simple name defaults
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
                # Mirror P1 button names for P2
                'P2_BUTTON1': 'A Button',
                'P2_BUTTON2': 'B Button',
                'P2_BUTTON3': 'X Button',
                'P2_BUTTON4': 'Y Button',
                'P2_BUTTON5': 'LB Button',
                'P2_BUTTON6': 'RB Button',
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
                #print(f"Found direct controls for {romname}")
            else:
                needs_parent_controls = True
                #print(f"No direct controls for {romname}, needs parent controls")
                
            # If no controls and this is a clone, try to use parent controls
            if needs_parent_controls:
                parent_rom = None
                
                # Check explicit parent field (should be there from load_gamedata_json)
                if 'parent' in game_data:
                    parent_rom = game_data['parent']
                    #print(f"Found parent {parent_rom} via direct reference")
                
                # Also check parent lookup table for redundancy
                elif hasattr(self, 'parent_lookup') and romname in self.parent_lookup:
                    parent_rom = self.parent_lookup[romname]
                    #print(f"Found parent {parent_rom} via lookup table")
                
                # If we found a parent, try to get its controls
                if parent_rom and parent_rom in self.gamedata_json:
                    parent_data = self.gamedata_json[parent_rom]
                    if 'controls' in parent_data:
                        controls = parent_data['controls']
                        #print(f"Using controls from parent {parent_rom} for clone {romname}")
            
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
                        # Skip non-joystick/button controls
                        if 'JOYSTICK' in control_name or 'BUTTON' in control_name:
                            # Get the friendly name
                            friendly_name = None
                            
                            # First check for explicit name
                            if 'name' in control_data:
                                friendly_name = control_data['name']
                            # Then check for default actions
                            elif control_name in default_actions:
                                friendly_name = default_actions[control_name]
                            # Fallback to control name
                            else:
                                parts = control_name.split('_')
                                if len(parts) > 1:
                                    friendly_name = parts[-1]
                                
                            if friendly_name:
                                p1_controls.append({
                                    'name': control_name,
                                    'value': friendly_name
                                })
                    
                    # Add P2 controls - prioritize matching P1 button names
                    elif control_name.startswith('P2_'):
                        if 'JOYSTICK' in control_name or 'BUTTON' in control_name:
                            friendly_name = None
                            
                            # First check for explicit name
                            if 'name' in control_data:
                                friendly_name = control_data['name']
                            # Then check if we have a matching P1 button name
                            elif control_name in p1_button_names:
                                friendly_name = p1_button_names[control_name]
                            # Then check defaults
                            elif control_name in default_actions:
                                friendly_name = default_actions[control_name]
                            # Fallback to control name
                            else:
                                parts = control_name.split('_')
                                if len(parts) > 1:
                                    friendly_name = parts[-1]
                                
                            if friendly_name:
                                p2_controls.append({
                                    'name': control_name,
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

    def get_game_data_from_db(self, romname):
        """Get control data for a ROM from the SQLite database with streamlined error handling"""
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
                SELECT rom_name, game_name, player_count, buttons, sticks, alternating, is_clone, parent_rom
                FROM games WHERE rom_name = ?
            """, (romname,))
            
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
            
            for control in control_rows:
                control_name = control[0]  # First column
                display_name = control[1]  # Second column
                
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
    
    def show_preview_standalone(self, rom_name, auto_close=False, clean_mode=False):
        """Show the preview for a specific ROM without running the main app, with optimized cache prioritization"""
        print(f"Starting standalone preview for ROM: {rom_name}")
        start_time = time.time()
        
        # Find the MAME directory (already in __init__)
        if not hasattr(self, 'mame_dir') or not self.mame_dir:
            self.mame_dir = self.find_mame_directory()
            if not self.mame_dir:
                print("Error: MAME directory not found!")
                return
        
        print(f"Using MAME directory: {self.mame_dir}")
        
        # Make sure preview and cache directories exist (minimal setup for cache check)
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        os.makedirs(self.preview_dir, exist_ok=True)
        
        # Define and check cache first - before any other operations
        cache_dir = os.path.join(self.preview_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"{rom_name}_cache.json")
        
        # Initialize ROM data cache if needed (minimal memory setup)
        if not hasattr(self, 'rom_data_cache'):
            self.rom_data_cache = {}
        
        # Set the current game
        self.current_game = rom_name
        
        # Check for cached data first
        game_data = None
        if os.path.exists(cache_file):
            try:
                print(f"Found cache file: {cache_file}")
                cache_age = time.time() - os.path.getmtime(cache_file)
                print(f"Cache age: {cache_age:.1f} seconds")
                
                # Only use cache if it's recent (less than 1 hour old)
                if cache_age < 3600:
                    import json
                    with open(cache_file, 'r') as f:
                        game_data = json.load(f)
                    
                    if game_data:
                        print(f"Using cached game data for {rom_name}")
                        # Store in memory cache as well
                        self.rom_data_cache[rom_name] = game_data
                        data_load_time = time.time() - start_time
                        print(f"Game data loaded from cache in {data_load_time:.3f} seconds")
                    else:
                        print("Warning: Cache file exists but contains no valid data")
            except Exception as e:
                print(f"Error loading cache: {e}")
                game_data = None
        
        # Only if we don't have valid cached data, continue with the full setup
        if not game_data:
            print("No valid cache found, proceeding with full data load...")
            
            # Now complete the settings directory setup only if needed
            self.settings_dir = os.path.join(self.preview_dir, "settings")
            self.info_dir = os.path.join(self.settings_dir, "info")
            os.makedirs(self.settings_dir, exist_ok=True)
            os.makedirs(self.info_dir, exist_ok=True)
            
            # Load settings (for screen preference)
            self.load_settings()
            
            # ADDED: Get command line arguments for screen and button visibility
            import sys
            for i, arg in enumerate(sys.argv):
                if arg == '--screen' and i+1 < len(sys.argv):
                    try:
                        self.preferred_preview_screen = int(sys.argv[i+1])
                        print(f"OVERRIDE: Using screen {self.preferred_preview_screen} from command line")
                    except:
                        pass
                elif arg == '--no-buttons':
                    self.hide_preview_buttons = True
                    print(f"OVERRIDE: Hiding buttons due to command line flag")
            
            # Check if we need to load the database for faster access
            db_path = os.path.join(self.settings_dir, "gamedata.db")
            using_db = os.path.exists(db_path)
            
            if using_db:
                print(f"Found gamedata database at: {db_path}")
                self.db_path = db_path
                # Add the get_game_data_from_db method if not already present
                if not hasattr(self, 'get_game_data_from_db'):
                    # The original database method implementation remains unchanged
                    pass
            
            # Load game data using the unified getter
            data_load_start = time.time()
            game_data = self.get_unified_game_data(rom_name)
            data_load_time = time.time() - data_load_start
            print(f"Game data loaded in {data_load_time:.3f} seconds")
            
            # Save game data to cache file for future use
            if game_data:
                try:
                    import json
                    with open(cache_file, 'w') as f:
                        json.dump(game_data, f)
                    print(f"Saved game data to cache: {cache_file}")
                except Exception as e:
                    print(f"Error saving cache: {e}")
        else:
            # We have valid cached data, so load just the settings needed for display
            self.load_settings()
            
            # Apply command line overrides for screen/buttons
            import sys
            for i, arg in enumerate(sys.argv):
                if arg == '--screen' and i+1 < len(sys.argv):
                    try:
                        self.preferred_preview_screen = int(sys.argv[i+1])
                        print(f"OVERRIDE: Using screen {self.preferred_preview_screen} from command line")
                    except:
                        pass
                elif arg == '--no-buttons':
                    self.hide_preview_buttons = True
                    print(f"OVERRIDE: Hiding buttons due to command line flag")
        
        # Exit if we still don't have game data
        if not game_data:
            print(f"Error: No control data found for {rom_name}")
            # Only show message box if we have Qt loaded
            if hasattr(sys, 'modules') and 'PyQt5.QtWidgets' in sys.modules:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Error", f"No control data found for {rom_name}")
            return
        
        # Start MAME process monitoring only if auto_close is enabled
        if auto_close:
            print("Auto-close enabled - preview will close when MAME exits")
            self.monitor_mame_process(check_interval=0.5)
        
        # Show the preview window
        try:
            from mame_controls_preview import PreviewWindow
            
            preview_start = time.time()
            
            # Create the preview window with correct positional parameter order
            self.preview_window = PreviewWindow(
                rom_name,             # 1st positional arg  
                game_data,            # 2nd positional arg
                self.mame_dir,        # 3rd positional arg
                None,                 # 4th positional arg (parent)
                self.hide_preview_buttons,  # 5th positional arg
                clean_mode            # 6th positional arg
            )
            
            # Mark this as a standalone preview (for proper cleanup)
            self.preview_window.standalone_mode = True
            
            # CRITICAL ADDITION: Call the method to ensure consistent positioning
            if hasattr(self.preview_window, 'ensure_consistent_text_positioning'):
                self.preview_window.ensure_consistent_text_positioning()
            
            # Apply fullscreen settings
            from PyQt5.QtCore import Qt
            self.preview_window.setWindowFlags(
                Qt.WindowStaysOnTopHint | 
                Qt.FramelessWindowHint | 
                Qt.Tool  # Removes from taskbar
            )
            
            # Remove all window decorations and background
            self.preview_window.setAttribute(Qt.WA_NoSystemBackground, True)
            self.preview_window.setAttribute(Qt.WA_TranslucentBackground, True)
            
            # Apply stylesheets to remove ALL borders
            self.preview_window.setStyleSheet("""
                QMainWindow, QWidget {
                    border: none !important;
                    padding: 0px !important;
                    margin: 0px !important;
                    background-color: black;
                }
            """)
            
            # Get the exact screen geometry
            from PyQt5.QtWidgets import QDesktopWidget
            desktop = QDesktopWidget()
            screen_num = getattr(self, 'preferred_preview_screen', 1)  # Default to screen 1
            screen_geometry = desktop.screenGeometry(screen_num - 1)
            
            # Apply exact geometry before showing
            self.preview_window.setGeometry(screen_geometry)
            print(f"Applied screen geometry: {screen_geometry.width()}x{screen_geometry.height()}")
            
            # Final setup before display
            self.preview_window.showFullScreen()
            self.preview_window.activateWindow()
            self.preview_window.raise_()
            
            # Add a short delay to allow window to settle
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, lambda: self.ensure_full_dimensions(self.preview_window, screen_geometry))
            
            preview_time = time.time() - preview_start
            total_time = time.time() - start_time
            print(f"Preview window created in {preview_time:.3f} seconds")
            print(f"Total startup time: {total_time:.3f} seconds")
            
        except Exception as e:
            print(f"Error showing preview: {str(e)}")
            import traceback
            traceback.print_exc()
            return

    def ensure_full_dimensions(self, window, screen_geometry):
        """Ensure the window and all children use the full dimensions"""
        if not window:
            return
            
        # Log all dimensions
        print(f"Window dimensions: {window.width()}x{window.height()}")
        if hasattr(window, 'central_widget'):
            print(f"Central widget: {window.central_widget.width()}x{window.central_widget.height()}")
        if hasattr(window, 'canvas'):
            print(f"Canvas: {window.canvas.width()}x{window.canvas.height()}")
        
        # Check if dimensions match screen geometry
        if window.width() != screen_geometry.width() or window.height() != screen_geometry.height():
            print("MISMATCH: Window size doesn't match screen size!")
            # Force resize again
            window.setGeometry(screen_geometry)
            
        # Force canvas size if it exists
        if hasattr(window, 'canvas'):
            if window.canvas.width() != screen_geometry.width() or window.canvas.height() != screen_geometry.height():
                print("MISMATCH: Canvas size doesn't match screen size, forcing resize")
                window.canvas.setFixedSize(screen_geometry.width(), screen_geometry.height())
                
        # Make one more attempt to ensure all parent widgets are also sized correctly
        if hasattr(window, 'central_widget'):
            window.central_widget.setFixedSize(screen_geometry.width(), screen_geometry.height())
            
        # Force a repaint
        window.repaint()
        
    def monitor_mame_process(self, check_interval=2.0):
        """Monitor MAME process and close preview when MAME closes"""
        import threading
        import time
        import subprocess
        import sys
        
        print("Starting MAME process monitor")
        
        def check_mame():
            mame_running = True
            check_count = 0
            last_state = True
            
            while mame_running:
                time.sleep(check_interval)
                check_count += 1
                
                # Skip checking if the preview window is gone
                if not hasattr(self, 'preview_window'):
                    print("Preview window closed, stopping monitor")
                    return
                
                # Check if any MAME process is running
                try:
                    if sys.platform == 'win32':
                        output = subprocess.check_output('tasklist /FI "IMAGENAME eq mame*"', shell=True)
                        mame_detected = b'mame' in output.lower()
                    else:
                        output = subprocess.check_output(['ps', 'aux'])
                        mame_detected = b'mame' in output
                    
                    # Only log when state changes
                    if mame_detected != last_state:
                        print(f"MAME running: {mame_detected}")
                        last_state = mame_detected
                    
                    mame_running = mame_detected
                except Exception as e:
                    print(f"Error checking MAME: {e}")
                    continue
            
            # MAME is no longer running - close preview
            print("MAME closed, closing preview")
            if hasattr(self, 'preview_window'):
                # Close the preview window
                if hasattr(self.preview_window, 'close'):
                    self.preview_window.close()
        
        # Start monitoring in a daemon thread
        monitor_thread = threading.Thread(target=check_mame, daemon=True)
        monitor_thread.start()
        print(f"Monitor thread started with check interval {check_interval}s")
    
    def show_unmatched_roms(self):
        """Display ROMs that don't have matching control data"""
        # Find unmatched ROMs
        unmatched_roms = sorted(self.find_unmatched_roms())
        matched_roms = sorted(self.available_roms - set(unmatched_roms))
        
        # Create a simple dialog showing unmatched ROMs
        message = f"Unmatched ROMs: {len(unmatched_roms)} of {len(self.available_roms)}"
        if unmatched_roms:
            message += "\n\nSample of unmatched ROMs (first 10):\n"
            message += "\n".join(unmatched_roms[:10])
            if len(unmatched_roms) > 10:
                message += f"\n...and {len(unmatched_roms) - 10} more"
        else:
            message += "\n\nAll ROMs have matching control data!"
        
        QMessageBox.information(self, "Unmatched ROMs", message)
    
    def generate_all_configs(self):
        """Generate config files for all available ROMs"""
        # Simplified implementation for now
        QMessageBox.information(self, "Coming Soon", "This feature will be implemented in a future version.")
    
    def on_game_selected(self, rom_name, line_number):
        """Handle game selection and display controls - optimized PyQt version"""
        try:
            # Store current game
            self.current_game = rom_name
            
            # Get game data using cache when possible
            if hasattr(self, 'rom_data_cache') and rom_name in self.rom_data_cache:
                game_data = self.rom_data_cache[rom_name]
            else:
                game_data = self.get_game_data(rom_name)
            
            if not game_data:
                # Clear display for ROMs without control data
                self.game_title.setText(f"No control data: {rom_name}")
                # Clear the controls display
                for i in reversed(range(self.control_layout.count())):
                    item = self.control_layout.itemAt(i)
                    if item.widget():
                        item.widget().deleteLater()
                    elif item.layout():
                        while item.layout().count():
                            child = item.layout().takeAt(0)
                            if child.widget():
                                child.widget().deleteLater()
                return
                
            # Update game title with data source
            source_text = f" (Source: {game_data.get('source', 'unknown')})" 
            self.game_title.setText(f"{game_data['gamename']}{source_text}")
            
            # Get custom controls if they exist
            cfg_controls = {}
            if rom_name in self.custom_configs:
                cfg_controls = self.parse_cfg_controls(self.custom_configs[rom_name])
                
                # Convert mappings if XInput is enabled
                if self.use_xinput:
                    cfg_controls = {
                        control: self.convert_mapping(mapping, True)
                        for control, mapping in cfg_controls.items()
                    }
            
            # Display game info and controls
            self.display_controls_table(game_data, cfg_controls)
                
        except Exception as e:
            print(f"Error displaying game: {str(e)}")
            import traceback
            traceback.print_exc()

    def display_controls_table(self, game_data, cfg_controls):
        """Display the controls table - optimized PyQt version with fixed vertical alignment"""
        from PyQt5.QtGui import QFont
        from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit, QSpacerItem, QSizePolicy
        
        # First clear any existing layout content
        for i in reversed(range(self.control_layout.count())):
            item = self.control_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
            elif item.spacerItem():
                self.control_layout.removeItem(item)
        
        row = 0
        
        # Create basic game info section - always at the top
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.StyledPanel)
        info_layout = QVBoxLayout(info_frame)
        
        # Game info with larger font and better spacing
        info_text = (
            f"ROM: {game_data['romname']}\n\n"
            f"Players: {game_data['numPlayers']}\n"
            f"Alternating: {game_data['alternating']}\n"
            f"Mirrored: {game_data['mirrored']}"
        )
        if game_data.get('miscDetails'):
            info_text += f"\n\nDetails: {game_data['miscDetails']}"
            
        info_label = QLabel(info_text)
        info_label.setFont(QFont("Arial", 14))
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        
        self.control_layout.addWidget(info_frame)
        
        # Create column headers
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.StyledPanel)
        header_layout = QHBoxLayout(header_frame)
        
        headers = ["Control", "Default Action", "Current Mapping"]
        header_weights = [2, 2, 3]
        
        for header, weight in zip(headers, header_weights):
            header_label = QLabel(header)
            header_label.setFont(QFont("Arial", 14, QFont.Bold))
            header_layout.addWidget(header_label, weight)
            
        self.control_layout.addWidget(header_frame)
        
        # Create controls list frame
        controls_frame = QFrame()
        controls_frame.setFrameShape(QFrame.StyledPanel)
        controls_layout = QGridLayout(controls_frame)
        
        # Display control comparisons
        comparisons = self.compare_controls(game_data, cfg_controls)
        for row, (control_name, default_label, current_mapping, is_different) in enumerate(comparisons):
            # Control name
            display_control = self.format_control_name(control_name)
            name_label = QLabel(display_control)
            name_label.setFont(QFont("Arial", 12))
            controls_layout.addWidget(name_label, row, 0)
            
            # Default action
            default_action_label = QLabel(default_label)
            default_action_label.setFont(QFont("Arial", 12))
            controls_layout.addWidget(default_action_label, row, 1)
            
            # Current mapping
            display_mapping = self.format_mapping_display(current_mapping)
            mapping_label = QLabel(display_mapping)
            mapping_label.setFont(QFont("Arial", 12))
            if is_different:
                from PyQt5.QtGui import QColor
                mapping_label.setStyleSheet("color: yellow;")
            controls_layout.addWidget(mapping_label, row, 2)
        
        self.control_layout.addWidget(controls_frame)
        
        # Display raw custom config if it exists
        romname = game_data['romname']
        if romname in self.custom_configs:
            custom_header = QLabel("RAW CONFIGURATION FILE")
            custom_header.setFont(QFont("Arial", 16, QFont.Bold))
            self.control_layout.addWidget(custom_header)
            
            custom_text = QTextEdit()
            custom_text.setReadOnly(True)
            custom_text.setFont(QFont("Courier New", 10))
            custom_text.setMinimumHeight(200)
            custom_text.setText(self.custom_configs[romname])
            self.control_layout.addWidget(custom_text)
        
        # Add a spacer at the bottom to push content up
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.control_layout.addSpacerItem(spacer)

    def create_layout(self):
        """Create the main application layout"""
        # Main central widget
        from PyQt5.QtWidgets import QSizePolicy
        central_widget = QWidget()
        central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCentralWidget(central_widget)
        
        # Main horizontal layout with splitter
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(main_splitter)
        
        # Left panel (game list)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        
        # Stats frame
        stats_frame = QFrame()
        stats_frame.setFrameShape(QFrame.StyledPanel)
        stats_layout = QHBoxLayout(stats_frame)
        
        # Stats label
        self.stats_label = QLabel("Loading...")
        self.stats_label.setFont(QFont("Arial", 12))
        stats_layout.addWidget(self.stats_label)
        
        # Unmatched ROMs button
        self.unmatched_button = QPushButton("Show Unmatched ROMs")
        self.unmatched_button.setFixedWidth(150)
        self.unmatched_button.clicked.connect(self.show_unmatched_roms)
        stats_layout.addWidget(self.unmatched_button)
        
        # Generate configs button
        self.generate_configs_button = QPushButton("Generate Info Files")
        self.generate_configs_button.setFixedWidth(150)
        self.generate_configs_button.clicked.connect(self.generate_all_configs)
        stats_layout.addWidget(self.generate_configs_button)
        
        # The correct way to add the analyze button:
        self.analyze_button = QPushButton("Analyze Controls")
        self.analyze_button.setFixedWidth(150)
        self.analyze_button.clicked.connect(self.analyze_controls)
        stats_layout.addWidget(self.analyze_button)  # Use stats_layout, not self.stats_frame

        left_layout.addWidget(stats_frame)
        
        # Search box
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search games...")
        self.search_entry.textChanged.connect(self.filter_games)
        left_layout.addWidget(self.search_entry)
        
        # Game list widget
        self.game_list = GameListWidget()
        self.game_list.gameSelected.connect(self.on_game_selected)
        left_layout.addWidget(self.game_list)
        
        # Right panel (control display)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        
        # Game title and preview button row
        title_row = QHBoxLayout()
        
        # Game title
        self.game_title = QLabel("Select a game")
        self.game_title.setFont(QFont("Arial", 20, QFont.Bold)) 
        title_row.addWidget(self.game_title)
        
        # Preview button
        self.preview_button = QPushButton("Preview Controls")
        self.preview_button.setFixedWidth(150)
        self.preview_button.clicked.connect(self.show_preview)
        title_row.addWidget(self.preview_button)
        
        # Hide preview buttons toggle
        self.hide_buttons_toggle = QCheckBox("Hide Preview Buttons")
        self.hide_buttons_toggle.toggled.connect(self.toggle_hide_preview_buttons)
        title_row.addWidget(self.hide_buttons_toggle)
        
        right_layout.addLayout(title_row)
        
        # Toggle switches row
        toggle_row = QHBoxLayout()
        
        # XInput toggle
        self.xinput_toggle = QCheckBox("Use XInput Mappings")
        self.xinput_toggle.setChecked(True)
        self.xinput_toggle.toggled.connect(self.toggle_xinput)
        toggle_row.addWidget(self.xinput_toggle)
        
        toggle_row.addStretch()
        right_layout.addLayout(toggle_row)
        
        # Controls display (scrollable)
        self.control_scroll = QScrollArea()
        self.control_scroll.setWidgetResizable(True)
        self.control_frame = QWidget()
        self.control_layout = QVBoxLayout(self.control_frame)
        self.control_scroll.setWidget(self.control_frame)
        right_layout.addWidget(self.control_scroll)
        
        # Add panels to splitter
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        
        # Set initial splitter sizes
        main_splitter.setSizes([300, 700])

    def analyze_controls(self):
        """Comprehensive analysis of ROM controls with editing capabilities"""
        # Get data from both methods
        generic_games, missing_games = self.identify_generic_controls()
        matched_roms = set()
        for rom in self.available_roms:
            if self.get_game_data(rom):
                matched_roms.add(rom)
        unmatched_roms = self.available_roms - matched_roms
        
        # Identify default controls (games with real control data but not customized)
        default_games = []
        already_categorized = set([g[0] for g in generic_games]) | set(missing_games)
        for rom_name in sorted(matched_roms):
            if rom_name not in already_categorized:
                game_data = self.get_game_data(rom_name)
                if game_data and 'gamename' in game_data:
                    default_games.append((rom_name, game_data.get('gamename', rom_name)))
        
        # Create dialog using PyQt with dark theme
        dialog = QDialog(self)
        dialog.setWindowTitle("ROM Control Analysis")
        dialog.setMinimumSize(800, 600)
        dialog.setModal(True)
        
        # Apply dark theme to dialog
        dialog.setStyleSheet("""
            QDialog {
                background-color: #333333;
                color: white;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #1a5fb4;
                color: white;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #3584e4;
            }
            QTabWidget::pane {
                border: 1px solid #76797c;
                background-color: #232629;
            }
            QTabWidget::tab-bar {
                left: 5px;
            }
            QTabBar::tab {
                background-color: #31363b;
                color: white;
                padding: 5px;
            }
            QTabBar::tab:selected {
                background-color: #1a5fb4;
            }
        """)
        
        # Create main dialog layout
        main_layout = QVBoxLayout(dialog)
        
        # Create tab widget
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)
        
        # Summary tab
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        stats_text = (
            f"Total ROMs: {len(self.available_roms)}\n"
            f"ROMs with control data: {len(matched_roms)}\n"
            f"ROMs without control data: {len(unmatched_roms)}\n\n"
            f"Control data breakdown:\n"
            f"- ROMs with generic controls: {len(generic_games)}\n"
            f"- ROMs with custom controls: {len(default_games)}\n"
            f"- ROMs with missing controls: {len(missing_games)}\n\n"
            f"Control data coverage: {(len(matched_roms) / max(len(self.available_roms), 1) * 100):.1f}%"
        )
        stats_label = QLabel(stats_text)
        stats_label.setFont(QFont("Arial", 14))
        stats_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        summary_layout.addWidget(stats_label)
        tab_widget.addTab(summary_tab, "Summary")
        
        # Create each tab with the list UI
        self.create_game_list_with_edit(tab_widget, generic_games, "Generic Controls")
        self.create_game_list_with_edit(tab_widget, [(rom, rom) for rom in missing_games], "Missing Controls")
        self.create_game_list_with_edit(tab_widget, default_games, "Custom Controls")
        
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
                        
                QMessageBox.information(self, "Export Complete", 
                            f"Analysis exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
        
        # Add buttons at the bottom
        button_layout = QHBoxLayout()
        export_button = QPushButton("Export Analysis")
        export_button.clicked.connect(export_analysis)
        button_layout.addWidget(export_button)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)
        
        main_layout.addLayout(button_layout)
        
        # Show the dialog
        dialog.exec_()
    
    def create_game_list_with_edit(self, tab_widget, game_list, title_text):
        """Helper function to create a consistent list with edit button for games"""
        # Create tab with black background
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        
        # Set tab background color to match the dark theme
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))  # Dark gray background
        palette.setColor(QPalette.WindowText, Qt.white)  # White text
        tab.setPalette(palette)
        tab.setAutoFillBackground(True)
        
        # Title with white text
        title_label = QLabel(title_text)
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setStyleSheet("color: white;")
        tab_layout.addWidget(title_label)
        
        # Create list widget with dark theme
        list_widget = QListWidget()
        list_widget.setFont(QFont("Arial", 12))
        list_widget.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d;
                color: white;
            }
            QListWidget::item:selected {
                background-color: #1a5fb4;
            }
        """)
        
        # Populate list
        for rom, game_name in game_list:
            if rom == game_name:
                list_widget.addItem(rom)
            else:
                list_widget.addItem(f"{rom} - {game_name}")
        
        tab_layout.addWidget(list_widget)
        
        # Store the rom names for lookup when editing
        list_widget.rom_map = [rom for rom, _ in game_list]
        
        # Button for editing with styling
        edit_button = QPushButton("Edit Selected Game")
        edit_button.setStyleSheet("""
            QPushButton {
                background-color: #1a5fb4;
                color: white;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #3584e4;
            }
        """)
        edit_button.clicked.connect(lambda: self.edit_selected_game(list_widget))
        tab_layout.addWidget(edit_button)
        
        # Add tab
        tab_widget.addTab(tab, title_text)
        
        return tab

    def edit_selected_game(self, list_widget):
        """Handle editing the selected game"""
        selected_items = list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Selection Required", "Please select a game to edit")
            return
        
        selected_index = list_widget.row(selected_items[0])
        if selected_index < len(list_widget.rom_map):
            rom = list_widget.rom_map[selected_index]
            selected_text = selected_items[0].text()
            
            # Extract game name if present
            game_name = None
            if " - " in selected_text:
                parts = selected_text.split(" - ", 1)
                if len(parts) == 2 and parts[0] == rom:
                    game_name = parts[1]
            
            self.show_control_editor(rom, game_name)
    
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
    
    def show_control_editor(self, rom_name, game_name=None):
        """Show editor for a game's controls with direct gamedata.json editing and standard button layout"""
        game_data = self.get_game_data(rom_name) or {}
        game_name = game_name or game_data.get('gamename', rom_name)
        
        # Check if this is an existing game or a new one
        is_new_game = not bool(game_data)
        
        # Create dialog
        editor = QDialog(self)
        editor.setWindowTitle(f"{'Add New Game' if is_new_game else 'Edit Controls'} - {game_name}")
        editor.setMinimumSize(900, 750)
        editor.setModal(True)
        
        # Main layout
        main_layout = QVBoxLayout(editor)
        
        # Header
        header_label = QLabel(f"{'Add New Game' if is_new_game else 'Edit Controls for'} {game_name}")
        header_label.setFont(QFont("Arial", 16, QFont.Bold))
        main_layout.addWidget(header_label)
        
        # Game properties section
        properties_frame = QFrame()
        properties_frame.setFrameShape(QFrame.StyledPanel)
        properties_layout = QVBoxLayout(properties_frame)
        
        properties_label = QLabel("Game Properties")
        properties_label.setFont(QFont("Arial", 14, QFont.Bold))
        properties_layout.addWidget(properties_label)
        
        # Properties grid
        properties_grid = QGridLayout()
        
        # Get current values
        current_description = game_data.get('gamename', game_name) or rom_name
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
        
        # Add game name field
        properties_grid.addWidget(QLabel("Game Name:"), 0, 0)
        description_edit = QLineEdit()
        description_edit.setText(current_description)
        properties_grid.addWidget(description_edit, 0, 1, 1, 3)
        
        # Add player count field
        properties_grid.addWidget(QLabel("Players:"), 1, 0)
        playercount_combo = QComboBox()
        playercount_combo.addItems(["1", "2", "3", "4"])
        playercount_combo.setCurrentText(str(current_playercount))
        properties_grid.addWidget(playercount_combo, 1, 1)
        
        # Add alternating option
        alternating_check = QCheckBox("Alternating Play")
        alternating_check.setChecked(game_data.get('alternating', False))
        properties_grid.addWidget(alternating_check, 1, 2)
        
        # Add buttons and sticks fields
        properties_grid.addWidget(QLabel("Buttons:"), 2, 0)
        buttons_combo = QComboBox()
        buttons_combo.addItems(["1", "2", "3", "4", "5", "6", "8"])
        buttons_combo.setCurrentText(current_buttons)
        properties_grid.addWidget(buttons_combo, 2, 1)
        
        properties_grid.addWidget(QLabel("Sticks:"), 2, 2)
        sticks_combo = QComboBox()
        sticks_combo.addItems(["0", "1", "2"])
        sticks_combo.setCurrentText(current_sticks)
        properties_grid.addWidget(sticks_combo, 2, 3)
        
        properties_layout.addLayout(properties_grid)
        main_layout.addWidget(properties_frame)
        
        # Scroll area for controls
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_scroll.setWidget(controls_widget)
        
        # Define standard controller buttons
        standard_controls = [
            ('P1_BUTTON1', 'A Button'),
            ('P1_BUTTON2', 'B Button'),
            ('P1_BUTTON3', 'X Button'),
            ('P1_BUTTON4', 'Y Button'),
            ('P1_BUTTON5', 'Left Bumper (LB)'),
            ('P1_BUTTON6', 'Right Bumper (RB)'),
            ('P1_BUTTON7', 'Left Trigger (LT)'),
            ('P1_BUTTON8', 'Right Trigger (RT)'),
            ('P1_BUTTON9', 'Left Stick Button (L3)'),
            ('P1_BUTTON10', 'Right Stick Button (R3)'),
            ('P1_JOYSTICK_UP', 'Left Stick Up'),
            ('P1_JOYSTICK_DOWN', 'Left Stick Down'),
            ('P1_JOYSTICK_LEFT', 'Left Stick Left'),
            ('P1_JOYSTICK_RIGHT', 'Left Stick Right')
        ]
        
        # Dictionary to store control entries
        control_entries = {}
        
        # Helper function to get existing action for a control
        def get_existing_action(control_name):
            for player in game_data.get('players', []):
                for label in player.get('labels', []):
                    if label.get('name') == control_name:
                        return label.get('value', '')
            return ''
        
        # Header for controls
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.addWidget(QLabel("Control"))
        header_layout.addWidget(QLabel("Action/Function (leave empty to skip)"))
        controls_layout.addWidget(header_frame)
        
        # Create entry fields for each standard control
        for control_name, display_name in standard_controls:
            control_frame = QFrame()
            control_layout = QHBoxLayout(control_frame)
            
            # Control name label
            control_layout.addWidget(QLabel(display_name))
            
            # Get existing action
            existing_action = get_existing_action(control_name)
            
            # Action entry field
            action_entry = QLineEdit()
            action_entry.setText(existing_action)
            control_layout.addWidget(action_entry)
            
            # Store the entry widget
            control_entries[control_name] = action_entry
            
            # Add to controls layout
            controls_layout.addWidget(control_frame)
        
        # Add custom controls section
        custom_frame = QFrame()
        custom_layout = QVBoxLayout(custom_frame)
        
        custom_label = QLabel("Add Custom Controls (Optional)")
        custom_label.setFont(QFont("Arial", 14, QFont.Bold))
        custom_layout.addWidget(custom_label)
        
        # Container for custom controls
        custom_controls_container = QWidget()
        custom_controls_layout = QVBoxLayout(custom_controls_container)
        custom_controls_container.setLayout(custom_controls_layout)
        custom_layout.addWidget(custom_controls_container)
        
        # List to track custom controls
        custom_control_rows = []
        
        # Function to add a new custom control row
        def add_custom_row():
            row_frame = QFrame()
            row_layout = QHBoxLayout(row_frame)
            
            # Control name entry
            control_entry = QLineEdit()
            control_entry.setPlaceholderText("Custom Control (e.g., P1_BUTTON11)")
            row_layout.addWidget(control_entry)
            
            # Action entry
            action_entry = QLineEdit()
            action_entry.setPlaceholderText("Action/Function")
            row_layout.addWidget(action_entry)
            
            # Remove button
            remove_button = QPushButton("❌")
            remove_button.setFixedWidth(30)
            
            def remove_row():
                row_frame.setParent(None)
                row_frame.deleteLater()
                if row_data in custom_control_rows:
                    custom_control_rows.remove(row_data)
                    
            remove_button.clicked.connect(remove_row)
            row_layout.addWidget(remove_button)
            
            # Store row data
            row_data = {'frame': row_frame, 'control': control_entry, 'action': action_entry}
            custom_control_rows.append(row_data)
            
            # Add to layout
            custom_controls_layout.addWidget(row_frame)
            
            return row_data
        
        # Add first custom row
        add_custom_row()
        
        # Add button for more rows
        add_custom_button = QPushButton("+ Add Another Custom Control")
        add_custom_button.clicked.connect(add_custom_row)
        custom_layout.addWidget(add_custom_button)
        
        # Add custom controls section to main layout
        controls_layout.addWidget(custom_frame)
        
        # Add scroll area to main layout
        main_layout.addWidget(controls_scroll)
        
        # Add instructions
        instructions_label = QLabel("""
        Instructions:
        1. Enter the action/function for each standard control you want to include
        2. Leave fields empty for controls you don't want to add
        3. Use the custom section to add any non-standard controls
        4. Click Save to update the game's controls in the database
        """)
        instructions_label.setWordWrap(True)
        main_layout.addWidget(instructions_label)
        
        # Add button layout
        button_layout = QHBoxLayout()
        
        # Save function
        def save_controls():
            """Save controls directly to gamedata.json"""
            try:
                # Collect game properties
                game_description = description_edit.text().strip() or game_name or rom_name
                game_playercount = playercount_combo.currentText()
                game_buttons = buttons_combo.currentText()
                game_sticks = sticks_combo.currentText()
                game_alternating = alternating_check.isChecked()
                
                # Load the gamedata.json file using centralized path
                gamedata_path = self.get_gamedata_path()
                with open(gamedata_path, 'r', encoding='utf-8') as f:
                    gamedata = json.load(f)
                
                # Process control entries - only include non-empty fields
                control_updates = {}
                
                # Add standard controls with non-empty values
                for control_name, entry in control_entries.items():
                    action_value = entry.text().strip()
                    
                    # Only add if action is not empty
                    if action_value:
                        control_updates[control_name] = action_value
                
                # Add custom controls with non-empty values
                for row_data in custom_control_rows:
                    control_name = row_data['control'].text().strip()
                    action_value = row_data['action'].text().strip()
                    
                    # Only add if both fields are filled
                    if control_name and action_value:
                        control_updates[control_name] = action_value
                
                # Helper function to update controls in a gamedata structure
                def update_controls_in_data(data):
                    if 'controls' not in data:
                        data['controls'] = {}
                    
                    # First, check if we need to explicitly remove any controls
                    if 'controls' in data:
                        existing_controls = set(data['controls'].keys())
                        updated_controls = set(control_updates.keys())
                        
                        # Find controls that were in the original data but aren't in our updates
                        for removed_control in existing_controls - updated_controls:
                            # Remove from the data structure
                            if removed_control in data['controls']:
                                del data['controls'][removed_control]
                    
                    # Update or add name attributes to controls
                    for control_name, action in control_updates.items():
                        if control_name in data['controls']:
                            # Update existing control
                            data['controls'][control_name]['name'] = action
                        else:
                            # Create new control with placeholder values
                            data['controls'][control_name] = {
                                'name': action,
                                'tag': '',
                                'mask': '0'
                            }
                            
                    return True
                
                # Determine where to save the controls based on ROM structure
                target_found = False
                
                # First check if the ROM has its own controls section
                if rom_name in gamedata and 'controls' in gamedata[rom_name]:
                    # Update the game properties too
                    gamedata[rom_name]['description'] = game_description
                    gamedata[rom_name]['playercount'] = game_playercount
                    gamedata[rom_name]['buttons'] = game_buttons
                    gamedata[rom_name]['sticks'] = game_sticks
                    gamedata[rom_name]['alternating'] = game_alternating
                    
                    update_controls_in_data(gamedata[rom_name])
                    target_found = True
                    
                # If not, check clones
                elif rom_name in gamedata and 'clones' in gamedata[rom_name]:
                    # Update the game properties too
                    gamedata[rom_name]['description'] = game_description
                    gamedata[rom_name]['playercount'] = game_playercount
                    gamedata[rom_name]['buttons'] = game_buttons
                    gamedata[rom_name]['sticks'] = game_sticks
                    gamedata[rom_name]['alternating'] = game_alternating
                    
                    # If ROM has no controls but has clones with controls, update the last clone
                    clone_with_controls = None
                    
                    for clone_name in gamedata[rom_name]['clones']:
                        if isinstance(gamedata[rom_name]['clones'], dict) and clone_name in gamedata[rom_name]['clones']:
                            clone_data = gamedata[rom_name]['clones'][clone_name]
                            if 'controls' in clone_data:
                                clone_with_controls = clone_name
                        
                    if clone_with_controls:
                        update_controls_in_data(gamedata[rom_name]['clones'][clone_with_controls])
                        target_found = True
                    else:
                        # No clone has controls either, add controls to the main ROM
                        update_controls_in_data(gamedata[rom_name])
                        target_found = True
                
                # If ROM is a clone, try to find it in its parent's clone list
                else:
                    clone_parent_found = False
                    for parent_name, parent_data in gamedata.items():
                        if 'clones' in parent_data and isinstance(parent_data['clones'], dict) and rom_name in parent_data['clones']:
                            # Update the clone's properties if supported
                            if isinstance(parent_data['clones'][rom_name], dict):
                                parent_data['clones'][rom_name]['description'] = game_description
                                parent_data['clones'][rom_name]['playercount'] = game_playercount
                                parent_data['clones'][rom_name]['buttons'] = game_buttons
                                parent_data['clones'][rom_name]['sticks'] = game_sticks
                                parent_data['clones'][rom_name]['alternating'] = game_alternating
                            
                            update_controls_in_data(parent_data['clones'][rom_name])
                            target_found = True
                            clone_parent_found = True
                            break
                    
                    # If it's not in any parent's clone list, it's a new game
                    if not clone_parent_found:
                        target_found = False
                
                # If no existing control structure was found anywhere, create a new entry
                if not target_found:
                    # Create a new entry for this ROM
                    gamedata[rom_name] = {
                        "description": game_description,
                        "playercount": game_playercount,
                        "buttons": game_buttons,
                        "sticks": game_sticks,
                        "alternating": game_alternating,
                        "clones": {},
                        "controls": {}
                    }
                    
                    # Add all the controls to the new entry
                    update_controls_in_data(gamedata[rom_name])
                    
                    QMessageBox.information(self, "New Game Added", f"Added new game entry for {rom_name} to gamedata.json")
                
                # Save the updated gamedata back to the file
                with open(gamedata_path, 'w', encoding='utf-8') as f:
                    json.dump(gamedata, f, indent=2)
                    
                QMessageBox.information(self, "Success", f"Controls for {game_description} saved to gamedata.json!")
                
                # Force a reload of gamedata.json
                if hasattr(self, 'gamedata_json'):
                    del self.gamedata_json
                    self.load_gamedata_json()
                
                # Clear the in-memory cache to force reloading data
                if hasattr(self, 'rom_data_cache'):
                    self.rom_data_cache = {}
                
                # Rebuild SQLite database if it's being used
                if hasattr(self, 'db_path') and self.db_path:
                    self.build_gamedata_db()
                
                # Replace the refresh code in save_controls with this:
                # Refresh any currently displayed data
                if self.current_game == rom_name:
                    self.refresh_display()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save controls: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Remove game function
        def remove_game():
            """Remove this game entirely from the database"""
            # Confirm with user
            msgBox = QMessageBox()
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.setText(f"Are you sure you want to completely remove {rom_name} from the database?")
            msgBox.setInformativeText("This action cannot be undone!")
            msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msgBox.setDefaultButton(QMessageBox.No)
            
            if msgBox.exec_() == QMessageBox.No:
                return
                
            try:
                # Load the gamedata.json file
                gamedata_path = self.get_gamedata_path()
                with open(gamedata_path, 'r', encoding='utf-8') as f:
                    gamedata = json.load(f)
                
                removed = False
                
                # Check if it's a direct entry
                if rom_name in gamedata:
                    # Direct removal
                    del gamedata[rom_name]
                    removed = True
                else:
                    # Check if it's a clone in any parent's clone list
                    for parent_name, parent_data in gamedata.items():
                        if 'clones' in parent_data and isinstance(parent_data['clones'], dict):
                            if rom_name in parent_data['clones']:
                                # Remove from clone list
                                del parent_data['clones'][rom_name]
                                removed = True
                                break
                
                if not removed:
                    QMessageBox.critical(self, "Error", f"Could not find {rom_name} in the database.")
                    return
                
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
                
                # Rebuild SQLite database if it's being used
                if hasattr(self, 'db_path') and self.db_path:
                    self.build_gamedata_db()
                
                QMessageBox.information(self, "Success", f"{rom_name} has been removed from the database.")
                
                # Close the editor
                editor.accept()
                
                # Refresh any currently displayed data
                if self.current_game == rom_name:
                    self.current_game = None
                    self.game_title.setText("Select a game")
                    # Clear the control frame
                    for widget in self.control_frame.winfo_children():
                        widget.setParent(None)
                    # Update the game list
                    self.update_game_list()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove game: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Add Remove Game button
        remove_button = QPushButton("Remove Game")
        remove_button.setStyleSheet("background-color: #B22222; color: white;")
        remove_button.clicked.connect(remove_game)
        button_layout.addWidget(remove_button)
        
        # Add Save button
        save_button = QPushButton("Save Controls")
        save_button.clicked.connect(save_controls)
        button_layout.addWidget(save_button)
        
        # Add Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(editor.reject)
        button_layout.addWidget(cancel_button)
        
        # Add button layout to main layout
        main_layout.addLayout(button_layout)
        
        # Execute the dialog
        editor.exec_()
    
    def refresh_display(self):
        """Refresh the current game display after changes"""
        if self.current_game:
            # Clear the ROM data cache to force reloading data
            if hasattr(self, 'rom_data_cache') and self.current_game in self.rom_data_cache:
                del self.rom_data_cache[self.current_game]
                
            # Get fresh game data
            game_data = self.get_game_data(self.current_game)
            if game_data:
                # Update game title
                self.game_title.setText(game_data['gamename'])
                
                # Clear existing display
                for i in reversed(range(self.control_layout.count())):
                    item = self.control_layout.itemAt(i)
                    if item.widget():
                        item.widget().deleteLater()
                    elif item.layout():
                        # For QHBoxLayout or QVBoxLayout items
                        while item.layout().count():
                            child = item.layout().takeAt(0)
                            if child.widget():
                                child.widget().deleteLater()
                
                # Call on_game_selected with current game data
                if hasattr(self, 'selected_line') and self.selected_line is not None:
                    self.on_game_selected(self.current_game, self.selected_line)
                else:
                    # Fallback if no selected line
                    self.on_game_selected(self.current_game, 1)
        
        # Also refresh the game list
        self.update_game_list()
    
    def load_all_data(self):
        """Load all necessary data with streamlined logic"""
        start_time = time.time()
        
        try:
            # Initialize ROM data cache
            self.rom_data_cache = {}
            
            # 1. Load settings
            self.load_settings()
            
            # 2. Scan ROMs directory
            self.scan_roms_directory()
            
            # 3. Load default controls
            self.load_default_config()
            
            # 4. Check if database needs update
            db_needs_update = self.check_db_update_needed()
            
            if db_needs_update:
                # If database update is needed, load gamedata.json and build db
                self.load_gamedata_json()
                self.build_gamedata_db()
            else:
                # Using existing SQLite database - no need to load full gamedata.json
                self.gamedata_json = {}  # Empty placeholder
                self.parent_lookup = {}  # Empty placeholder
            
            # 5. Load custom configs
            self.load_custom_configs()
            
            # 6. Update UI
            self.update_stats_label()
            self.update_game_list()
            
            # 7. Auto-select first ROM
            self.select_first_rom()
            
            total_time = time.time() - start_time
            print(f"Data loading complete in {total_time:.2f}s")
            
        except Exception as e:
            print(f"Error loading data: {e}")
            import traceback
            traceback.print_exc()
            #messagebox.showerror("Data Loading Error", f"Failed to load application data: {e}")
    
    def scan_roms_directory(self):
        """Scan the roms directory for available games with corrected path"""
        # Use the correct path: mame_dir/roms (not preview/roms)
        roms_dir = os.path.join(self.mame_dir, "roms")
        print(f"\nScanning ROMs directory: {roms_dir}")
        
        if not os.path.exists(roms_dir):
            print(f"ERROR: ROMs directory not found: {roms_dir}")
            QMessageBox.warning(self, "No ROMs Found", f"ROMs directory not found: {roms_dir}")
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
                print("Sample of available ROMs:", list(self.available_roms)[:5])
            else:
                print("WARNING: No ROMs were found!")
        except Exception as e:
            print(f"Error scanning ROMs directory: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.error(self, "Error", f"Failed to scan ROMs directory: {e}")
    
    def load_gamedata_json(self):
        """Load gamedata.json from the canonical settings location"""
        if hasattr(self, 'gamedata_json') and self.gamedata_json:
            return self.gamedata_json  # Already loaded
        
        # Ensure the file exists
        if not os.path.exists(self.gamedata_path):
            print(f"ERROR: gamedata.json not found at {self.gamedata_path}")
            self.gamedata_json = {}
            self.parent_lookup = {}
            return {}
                
        try:
            with open(self.gamedata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Process the data for main games and clones
            self.gamedata_json = {}
            self.parent_lookup = {}
            
            for rom_name, game_data in data.items():
                self.gamedata_json[rom_name] = game_data
                    
                # Build parent-child relationship
                if 'clones' in game_data:
                    for clone_name, clone_data in game_data['clones'].items():
                        # Store parent reference
                        clone_data['parent'] = rom_name
                        self.parent_lookup[clone_name] = rom_name
                        self.gamedata_json[clone_name] = clone_data
                
            return self.gamedata_json
                
        except Exception as e:
            print(f"ERROR loading gamedata.json: {str(e)}")
            self.gamedata_json = {}
            self.parent_lookup = {}
            return {}
    
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
                
                # Parse the default mappings
                self.default_controls = self.parse_default_cfg(content.decode('utf-8-sig'))
                
                # Debug output
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
        """Special parser just for default.cfg - extract ONLY joystick mappings"""
        controls = {}
        try:
            import re
            
            # Parse the XML content
            try:
                root = ET.fromstring(cfg_content)
                
                # Find the input section
                input_elem = root.find('.//input')
                if input_elem is not None:
                    print("Found input element in default.cfg")
                    joycode_count = 0
                    for port in input_elem.findall('port'):
                        control_type = port.get('type')
                        if control_type:
                            # Find the standard sequence
                            newseq = port.find('./newseq[@type="standard"]')
                            if newseq is not None and newseq.text:
                                full_mapping = newseq.text.strip()
                                
                                # Extract only JOYCODE parts using regex
                                joycode_match = re.search(r'(JOYCODE_\d+_[A-Z0-9_]+)', full_mapping)
                                if joycode_match:
                                    joycode = joycode_match.group(1)
                                    controls[control_type] = joycode
                                    joycode_count += 1
                
                print(f"Parsed {len(controls)} joystick controls from default.cfg (found {joycode_count} JOYCODE entries)")
            except ET.ParseError as e:
                print(f"XML parsing error: {e}")
                
        except Exception as e:
            print(f"Error parsing default.cfg: {e}")
            import traceback
            traceback.print_exc()
        
        return controls
    
    def load_settings(self):
        """Load settings from JSON file in settings directory"""
        # Set sensible defaults
        self.preferred_preview_screen = 1
        self.visible_control_types = ["BUTTON"]
        self.hide_preview_buttons = False
        self.show_button_names = True
        
        # Load custom settings if available
        if os.path.exists(self.settings_path):
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
                    if isinstance(settings['hide_preview_buttons'], bool):
                        self.hide_preview_buttons = settings['hide_preview_buttons']
                    elif isinstance(settings['hide_preview_buttons'], int):
                        self.hide_preview_buttons = bool(settings['hide_preview_buttons'])
                    
                    # Update toggle if it exists
                    if hasattr(self, 'hide_buttons_toggle'):
                        if self.hide_preview_buttons:
                            self.hide_buttons_toggle.select()
                        else:
                            self.hide_buttons_toggle.deselect()
                            
                # Load show button names setting
                if 'show_button_names' in settings:
                    if isinstance(settings['show_button_names'], bool):
                        self.show_button_names = settings['show_button_names']
                    elif isinstance(settings['show_button_names'], int):
                        self.show_button_names = bool(settings['show_button_names'])
                        
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            # Create settings file with defaults
            self.save_settings()
                
        return {
            'preferred_preview_screen': self.preferred_preview_screen,
            'visible_control_types': self.visible_control_types,
            'hide_preview_buttons': self.hide_preview_buttons,
            'show_button_names': self.show_button_names
        }
    
    def save_settings(self):
        """Save current settings to the standard settings file"""
        settings = {
            "preferred_preview_screen": getattr(self, 'preferred_preview_screen', 1),
            "visible_control_types": self.visible_control_types,
            "hide_preview_buttons": getattr(self, 'hide_preview_buttons', False),
            "show_button_names": getattr(self, 'show_button_names', True)
        }
        
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def update_stats_label(self):
        """Update the statistics label"""
        unmatched = len(self.find_unmatched_roms())
        matched = len(self.available_roms) - unmatched
        
        # Check if we're using the database
        using_db = hasattr(self, 'db_path') and os.path.exists(self.db_path)
        db_status = f"Database: Active" if using_db else "Database: Not used"
        
        stats = (
            f"Available ROMs: {len(self.available_roms)} ({matched} with controls, {unmatched} without)\n"
            f"Custom configs: {len(self.custom_configs)}\n"
            f"{db_status}"
        )
        # PyQt version uses setText instead of configure
        self.stats_label.setText(stats)
    
    def find_unmatched_roms(self) -> Set[str]:
        """Find ROMs that don't have matching control data"""
        matched_roms = set()
        for rom in self.available_roms:
            if self.get_game_data(rom):
                matched_roms.add(rom)
        return self.available_roms - matched_roms
    
    def update_game_list(self):
        """Update the game list to show all available ROMs with improved performance"""
        # Clear existing content
        self.game_list.clear()
        
        # Sort available ROMs
        available_roms = sorted(self.available_roms)
        
        # Pre-fetch custom config status for all ROMs (faster than checking one by one)
        has_config = {rom: rom in self.custom_configs for rom in available_roms}
        
        # Batch process with fewer database hits
        for romname in available_roms:
            # Check first if ROM data is in cache to avoid database lookups
            if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
                game_data = self.rom_data_cache[romname]
                has_data = True
            else:
                # Minimal check for existence - don't load full data yet
                has_data = self.rom_exists_in_db(romname) if hasattr(self, 'db_path') else False
                game_data = None
            
            # Build the prefix
            prefix = "* " if has_config.get(romname, False) else "  "
            
            if has_data:
                prefix += "+ "
                # Only fetch the full data if not in cache and needed for display
                if not game_data:
                    game_data = self.get_game_data(romname)
                
                if game_data:
                    display_name = f"{romname} - {game_data['gamename']}"
                else:
                    display_name = romname
            else:
                prefix += "- "
                display_name = romname
            
            # Insert the line - PyQt specific version
            self.game_list.append(f"{prefix}{display_name}")
    
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
    
    def filter_games(self, search_text):
        """Filter the game list based on search text with improved performance"""
        search_text = search_text.lower()
        
        # Clear the list for a fresh start
        self.game_list.clear()
        
        # Sort ROMs once
        available_roms = sorted(self.available_roms)
        
        # Reset selection
        self.game_list.selected_line = None
        
        # Track which ROMs match the filter for batch addition
        matching_roms = []
        
        # First pass: find matches using cache where possible
        for romname in available_roms:
            # Check if ROM name matches search
            if search_text in romname.lower():
                matching_roms.append(romname)
                continue
                
            # Check cached game data
            if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
                game_data = self.rom_data_cache[romname]
                if 'gamename' in game_data and search_text in game_data['gamename'].lower():
                    matching_roms.append(romname)
                    continue
            
            # If not in cache, only do a full lookup if searching
            if search_text:  # Only do expensive lookup if we're searching
                game_data = self.get_game_data(romname)
                if game_data and 'gamename' in game_data and search_text in game_data['gamename'].lower():
                    matching_roms.append(romname)
        
        # Second pass: add all matching ROMs to the list
        for romname in matching_roms:
            # Get game data
            game_data = self.get_game_data(romname)
            has_config = romname in self.custom_configs
            
            # Build the prefix
            prefix = "* " if has_config else "  "
            if game_data:
                prefix += "+ "
                display_name = f"{romname} - {game_data['gamename']}"
            else:
                prefix += "- "
                display_name = romname
            
            # Add to the list
            self.game_list.append(f"{prefix}{display_name}")
    
    def get_game_data(self, romname):
        """Get control data for a ROM with database prioritization"""
        # Check if we have a ROM data cache
        if hasattr(self, 'rom_data_cache') and romname in self.rom_data_cache:
            return self.rom_data_cache[romname]
        
        # First try to get from the database
        db_data = self.get_game_data_from_db(romname)
        if db_data:
            # Cache the result
            if hasattr(self, 'rom_data_cache'):
                self.rom_data_cache[romname] = db_data
            return db_data

        # For the PyQt version, we'll just use the JSON-based implementation without the database
        if not hasattr(self, 'gamedata_json'):
            self.load_gamedata_json()
                
        # Debug output
        #print(f"\nLooking up game data for: {romname}")
        
        if romname in self.gamedata_json:
            game_data = self.gamedata_json[romname]
            
            # Simple name defaults
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
                # Mirror P1 button names for P2
                'P2_BUTTON1': 'A Button',
                'P2_BUTTON2': 'B Button',
                'P2_BUTTON3': 'X Button',
                'P2_BUTTON4': 'Y Button',
                'P2_BUTTON5': 'LB Button',
                'P2_BUTTON6': 'RB Button',
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
                #print(f"Found direct controls for {romname}")
            else:
                needs_parent_controls = True
                #print(f"No direct controls for {romname}, needs parent controls")
                
            # If no controls and this is a clone, try to use parent controls
            if needs_parent_controls:
                parent_rom = None
                
                # Check explicit parent field (should be there from load_gamedata_json)
                if 'parent' in game_data:
                    parent_rom = game_data['parent']
                    #print(f"Found parent {parent_rom} via direct reference")
                
                # Also check parent lookup table for redundancy
                elif hasattr(self, 'parent_lookup') and romname in self.parent_lookup:
                    parent_rom = self.parent_lookup[romname]
                    #print(f"Found parent {parent_rom} via lookup table")
                
                # If we found a parent, try to get its controls
                if parent_rom and parent_rom in self.gamedata_json:
                    parent_data = self.gamedata_json[parent_rom]
                    if 'controls' in parent_data:
                        controls = parent_data['controls']
                        #print(f"Using controls from parent {parent_rom} for clone {romname}")
            
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
                        # Skip non-joystick/button controls
                        if 'JOYSTICK' in control_name or 'BUTTON' in control_name:
                            # Get the friendly name
                            friendly_name = None
                            
                            # First check for explicit name
                            if 'name' in control_data:
                                friendly_name = control_data['name']
                            # Then check for default actions
                            elif control_name in default_actions:
                                friendly_name = default_actions[control_name]
                            # Fallback to control name
                            else:
                                parts = control_name.split('_')
                                if len(parts) > 1:
                                    friendly_name = parts[-1]
                                
                            if friendly_name:
                                p1_controls.append({
                                    'name': control_name,
                                    'value': friendly_name
                                })
                    
                    # Add P2 controls - prioritize matching P1 button names
                    elif control_name.startswith('P2_'):
                        if 'JOYSTICK' in control_name or 'BUTTON' in control_name:
                            friendly_name = None
                            
                            # First check for explicit name
                            if 'name' in control_data:
                                friendly_name = control_data['name']
                            # Then check if we have a matching P1 button name
                            elif control_name in p1_button_names:
                                friendly_name = p1_button_names[control_name]
                            # Then check defaults
                            elif control_name in default_actions:
                                friendly_name = default_actions[control_name]
                            # Fallback to control name
                            else:
                                parts = control_name.split('_')
                                if len(parts) > 1:
                                    friendly_name = parts[-1]
                                
                            if friendly_name:
                                p2_controls.append({
                                    'name': control_name,
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
                
            # Mark as gamedata source
            converted_data['source'] = 'gamedata.json'
            return converted_data
            
        # Try parent lookup if direct lookup failed
        if romname in self.gamedata_json and 'parent' in self.gamedata_json[romname]:
            parent_rom = self.gamedata_json[romname]['parent']
            if parent_rom:
                # Recursive call to get parent data
                parent_data = self.get_game_data(parent_rom)
                if parent_data:
                    # Update with this ROM's info
                    parent_data['romname'] = romname
                    parent_data['gamename'] = self.gamedata_json[romname].get('description', f"{romname} (Clone)")
                    return parent_data
        
        # Not found
        return None
    
    # Add a cleanup method to be called when the application closes
    def on_closing(self):
        """Handle proper cleanup when closing the application"""
        print("Application closing, performing cleanup...")
        
        # Terminate any running preview processes
        if hasattr(self, 'preview_processes'):
            for process in self.preview_processes:
                try:
                    process.terminate()
                    print(f"Terminated process: {process}")
                except:
                    pass
        
        # Close the main window and exit
        self.close()
    
    # Entry point for testing
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer
    
    app = QApplication(sys.argv)
    window = MAMEControlConfig()
    
    # Show window first
    window.show()
    
    # Then maximize it with multiple approaches for reliability
    window.setWindowState(Qt.WindowMaximized)
    QTimer.singleShot(100, window.showMaximized)
    
    sys.exit(app.exec_())
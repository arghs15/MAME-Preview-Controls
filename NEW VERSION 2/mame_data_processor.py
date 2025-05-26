"""
MAME Data Processor - Lightweight data processing without GUI
Handles precaching and data processing operations for MAME Controls
"""

import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from io import StringIO
from mame_utils import get_application_path, get_mame_parent_dir, find_file_in_standard_locations


class MAMEDataProcessor:
    def __init__(self):
        """Initialize the data processor with essential components only"""
        print("Initializing MAME Data Processor...")
        
        # Initialize directory structure
        self.app_dir = get_application_path()
        self.mame_dir = get_mame_parent_dir(self.app_dir)
        self.preview_dir = os.path.join(self.mame_dir, "preview")
        self.settings_dir = os.path.join(self.preview_dir, "settings")
        self.cache_dir = os.path.join(self.preview_dir, "cache")
        
        # Create directories if they don't exist
        os.makedirs(self.preview_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Define standard paths
        self.gamedata_path = os.path.join(self.settings_dir, "gamedata.json")
        self.db_path = os.path.join(self.settings_dir, "gamedata.db")
        self.settings_path = os.path.join(self.settings_dir, "control_config_settings.json")
        
        # Initialize data structures
        self.gamedata_json = {}
        self.parent_lookup = {}
        self.custom_configs = {}
        self.default_controls = {}
        self.original_default_controls = {}
        
        # Load essential data
        self.load_settings()
        self.load_gamedata_json()
        self.load_custom_configs()
        self.load_default_config()
        
        print(f"Data processor initialized with input mode: {self.input_mode}")

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

    def load_settings(self):
        """Load settings to determine input mode"""
        # Set defaults
        self.input_mode = 'xinput'
        
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    settings = json.load(f)
                
                self.input_mode = settings.get('input_mode', 'xinput')
                
                # Ensure valid value
                if self.input_mode not in ['joycode', 'xinput', 'dinput', 'keycode']:
                    self.input_mode = 'xinput'
                    
                print(f"Loaded input mode from settings: {self.input_mode}")
            else:
                print(f"No settings file found, using default: {self.input_mode}")
                
        except Exception as e:
            print(f"Error loading settings: {e}")
            self.input_mode = 'xinput'

    def load_gamedata_json(self):
        """Load gamedata.json from the canonical settings location"""
        # Use the utility function to find gamedata.json
        gamedata_path = self.find_file_in_standard_locations(
            "gamedata.json",
            subdirs=[["settings"], ["preview", "settings"]],
            copy_to_settings=True
        )
        
        if not gamedata_path:
            print(f"ERROR: gamedata.json not found")
            return {}
        
        self.gamedata_path = gamedata_path
        
        try:
            with open(gamedata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Process the data for main games and clones
            for rom_name, game_data in data.items():
                self.gamedata_json[rom_name] = game_data
                    
                # Build parent-child relationship
                if 'clones' in game_data:
                    for clone_name, clone_data in game_data['clones'].items():
                        clone_data['parent'] = rom_name
                        self.parent_lookup[clone_name] = rom_name
                        self.gamedata_json[clone_name] = clone_data
            
            print(f"Loaded {len(self.gamedata_json)} games from gamedata.json")
            return self.gamedata_json
                
        except Exception as e:
            print(f"ERROR loading gamedata.json: {str(e)}")
            return {}

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
                    with open(full_path, "rb") as f:
                        content = f.read()
                    self.custom_configs[game_name] = content.decode('utf-8-sig')
                except Exception as e:
                    print(f"Error loading {filename}: {e}")

        print(f"Loaded {len(self.custom_configs)} custom configurations")

    def load_default_config(self):
        """Load the default MAME control configuration"""
        cfg_dir = os.path.join(self.mame_dir, "cfg")
        default_cfg_path = os.path.join(cfg_dir, "default.cfg")
        
        if os.path.exists(default_cfg_path):
            try:
                with open(default_cfg_path, "rb") as f:
                    content = f.read()
                
                self.default_controls = self.parse_default_cfg(content.decode('utf-8-sig'))
                print(f"Loaded {len(self.default_controls)} default control mappings")
                return True
            except Exception as e:
                print(f"Error loading default config: {e}")
                self.default_controls = {}
                return False
        else:
            print("No default.cfg found")
            self.default_controls = {}
            return False

    def parse_default_cfg(self, cfg_content):
        """Parse default.cfg to extract all control mappings"""
        controls = {}
        original_controls = {}
        
        try:
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

                    original_mapping = None

                    if inc is not None and dec is not None and inc.text and dec.text:
                        original_mapping = f"{inc.text.strip()} ||| {dec.text.strip()}"
                        inc_map = get_preferred_mapping(inc.text.strip())
                        dec_map = get_preferred_mapping(dec.text.strip())
                        controls[ctype] = f"{inc_map} ||| {dec_map}"
                    elif inc is not None and inc.text:
                        original_mapping = inc.text.strip()
                        controls[ctype] = get_preferred_mapping(inc.text.strip())
                    elif dec is not None and dec.text:
                        original_mapping = dec.text.strip()
                        controls[ctype] = get_preferred_mapping(dec.text.strip())
                    elif std is not None and std.text:
                        original_mapping = std.text.strip()
                        controls[ctype] = get_preferred_mapping(std.text.strip())

                    if original_mapping:
                        original_controls[ctype] = original_mapping

        except Exception as e:
            print(f"Error parsing default.cfg: {e}")
        
        self.original_default_controls = original_controls
        return controls

    def parse_cfg_controls(self, cfg_content: str):
        """Parse MAME cfg file to extract control mappings"""
        controls = {}
        try:
            def get_preferred_mapping(mapping_str: str) -> str:
                if not mapping_str:
                    return "NONE"
                    
                if "OR" in mapping_str:
                    parts = [p.strip() for p in mapping_str.strip().split("OR")]
                    
                    for part in parts:
                        if "XINPUT" in part:
                            return part
                    for part in parts:
                        if "JOYCODE" in part:
                            xinput_mapping = self.convert_mapping(part, 'xinput')
                            if xinput_mapping.startswith("XINPUT"):
                                return xinput_mapping
                            return part
                            
                    return parts[0]
                else:
                    if "XINPUT" in mapping_str:
                        return mapping_str.strip()
                    elif "JOYCODE" in mapping_str:
                        xinput_mapping = self.convert_mapping(mapping_str.strip(), 'xinput')
                        if xinput_mapping.startswith("XINPUT"):
                            return xinput_mapping
                    return mapping_str.strip()

            parser = ET.XMLParser(encoding='utf-8')
            tree = ET.parse(StringIO(cfg_content), parser=parser)
            root = tree.getroot()

            input_elem = root.find('.//input')
            if input_elem is not None:
                all_ports = input_elem.findall('port')
                
                for port in all_ports:
                    control_type = port.get('type')
                    if control_type:
                        special_control = any(substr in control_type for substr in 
                                            ["PADDLE", "DIAL", "TRACKBALL", "MOUSE", "LIGHTGUN", 
                                            "AD_STICK", "PEDAL", "POSITIONAL", "GAMBLE", "STEER"])

                        if special_control:
                            inc_newseq = port.find('./newseq[@type="increment"]')
                            dec_newseq = port.find('./newseq[@type="decrement"]')
                            std_newseq = port.find('./newseq[@type="standard"]')

                            mapping_found = False

                            if inc_newseq is not None and inc_newseq.text and inc_newseq.text.strip() != "NONE":
                                if (dec_newseq is None or not dec_newseq.text or dec_newseq.text.strip() == "NONE"):
                                    inc_mapping = get_preferred_mapping(inc_newseq.text.strip())
                                    controls[control_type] = inc_mapping
                                    mapping_found = True
                                elif dec_newseq is not None and dec_newseq.text and dec_newseq.text.strip() != "NONE":
                                    inc_mapping = get_preferred_mapping(inc_newseq.text.strip())
                                    dec_mapping = get_preferred_mapping(dec_newseq.text.strip())
                                    combined_mapping = f"{inc_mapping} ||| {dec_mapping}"
                                    controls[control_type] = combined_mapping
                                    mapping_found = True
                            elif dec_newseq is not None and dec_newseq.text and dec_newseq.text.strip() != "NONE":
                                dec_mapping = get_preferred_mapping(dec_newseq.text.strip())
                                controls[control_type] = dec_mapping
                                mapping_found = True
                            elif std_newseq is not None and std_newseq.text and std_newseq.text.strip() != "NONE":
                                mapping = get_preferred_mapping(std_newseq.text.strip())
                                controls[control_type] = mapping
                                mapping_found = True

                            if not mapping_found:
                                all_sequences = port.findall('./newseq')
                                for seq in all_sequences:
                                    seq_type = seq.get('type', 'unknown')
                                    if seq.text and seq.text.strip() != "NONE":
                                        mapping = get_preferred_mapping(seq.text.strip())
                                        controls[control_type] = mapping
                                        mapping_found = True
                                        break
                        else:
                            newseq = port.find('./newseq[@type="standard"]')
                            if newseq is not None and newseq.text and newseq.text.strip() != "NONE":
                                mapping = get_preferred_mapping(newseq.text.strip())
                                controls[control_type] = mapping

        except Exception as e:
            print(f"Error parsing cfg: {str(e)}")

        return controls

    def get_game_data(self, romname):
        """Get game data for a ROM"""
        if romname in self.gamedata_json:
            game_data = self.gamedata_json[romname]
            
            # Default actions for unnamed controls
            default_actions = {
                'P1_JOYSTICK_UP': 'Up',
                'P1_JOYSTICK_DOWN': 'Down',
                'P1_JOYSTICK_LEFT': 'Left',
                'P1_JOYSTICK_RIGHT': 'Right',
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
                'P1_PEDAL': 'Accelerator Pedal',
                'P1_PEDAL2': 'Brake Pedal',
                'P1_AD_STICK_X': 'Steering Left/Right',
                'P1_AD_STICK_Y': 'Lean Forward/Back',
                'P1_AD_STICK_Z': 'Throttle Control',
                'P1_DIAL': 'Dial Control',
                'P1_PADDLE': 'Paddle Control',
                'P1_TRACKBALL_X': 'Trackball X-Axis',
                'P1_TRACKBALL_Y': 'Trackball Y-Axis',
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
            
            # Process controls
            controls = None
            if 'controls' in game_data:
                controls = game_data['controls']
            elif 'parent' in game_data:
                parent_rom = game_data['parent']
                if parent_rom in self.gamedata_json:
                    parent_data = self.gamedata_json[parent_rom]
                    if 'controls' in parent_data:
                        controls = parent_data['controls']
            
            if controls:
                p1_controls = []
                
                for control_name, control_data in controls.items():
                    if control_name.startswith('P1_'):
                        specialized_control_types = ['JOYSTICK', 'BUTTON', 'PEDAL', 'AD_STICK', 'DIAL', 'PADDLE', 
                                                   'TRACKBALL', 'LIGHTGUN', 'MOUSE', 'POSITIONAL', 'GAMBLE']
                        
                        if any(control_type in control_name for control_type in specialized_control_types):
                            friendly_name = None
                            
                            if 'name' in control_data and control_data['name']:
                                friendly_name = control_data['name']
                            elif control_name in default_actions:
                                friendly_name = default_actions[control_name]
                            else:
                                parts = control_name.split('_')
                                if len(parts) > 1:
                                    friendly_name = parts[-1].replace('_', ' ').title()
                                else:
                                    friendly_name = control_name
                            
                            control_entry = {
                                'name': control_name,
                                'value': friendly_name
                            }
                            p1_controls.append(control_entry)
                
                # Sort controls by name
                p1_controls.sort(key=lambda x: x['name'])
                
                if p1_controls:
                    converted_data['players'].append({
                        'number': 1,
                        'numButtons': int(game_data.get('buttons', 1)),
                        'labels': p1_controls
                    })
            
            converted_data['source'] = 'gamedata.json'
            return converted_data
        
        return None

    def update_game_data_with_custom_mappings(self, game_data, cfg_controls):
        """Update game_data to include custom control mappings"""
        if not cfg_controls and not hasattr(self, 'default_controls'):
            return
                            
        romname = game_data.get('romname', '')
        
        # Add flags to game_data
        if romname in self.custom_configs:
            game_data['has_rom_cfg'] = True
            game_data['rom_cfg_file'] = f"{romname}.cfg"
        
        if hasattr(self, 'default_controls') and self.default_controls:
            game_data['has_default_cfg'] = True
        
        # Combine ROM-specific and default mappings
        all_mappings = {}

        # Add default mappings first
        if hasattr(self, 'default_controls') and self.default_controls:
            for control, mapping in self.default_controls.items():
                if self.input_mode == 'keycode':
                    if hasattr(self, 'original_default_controls') and control in self.original_default_controls:
                        original_mapping = self.original_default_controls[control]
                    else:
                        original_mapping = mapping
                else:
                    original_mapping = self.convert_mapping(mapping, self.input_mode)
                all_mappings[control] = {'mapping': original_mapping, 'source': 'Default CFG'}

        # Add ROM-specific mappings
        for control, mapping in cfg_controls.items():
            if self.input_mode == 'keycode':
                rom_keycode = self.extract_keycode_from_mapping(mapping)
                
                if rom_keycode:
                    all_mappings[control] = {'mapping': mapping, 'source': f"ROM CFG ({romname}.cfg)"}
                else:
                    if (hasattr(self, 'original_default_controls') and 
                        control in self.original_default_controls):
                        
                        default_original = self.original_default_controls[control]
                        default_keycode = self.extract_keycode_from_mapping(default_original)
                        
                        if default_keycode:
                            all_mappings[control] = {
                                'mapping': default_original, 
                                'source': 'Default CFG (fallback)'
                            }
                        else:
                            all_mappings[control] = {'mapping': mapping, 'source': f"ROM CFG ({romname}.cfg)"}
                    else:
                        all_mappings[control] = {'mapping': mapping, 'source': f"ROM CFG ({romname}.cfg)"}
            else:
                all_mappings[control] = {'mapping': mapping, 'source': f"ROM CFG ({romname}.cfg)"}
        
        # Define functional categories
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
                
                # Get functional category
                func_category = 'other'
                for category, controls in functional_categories.items():
                    if control_name in controls:
                        func_category = category
                        break
                        
                # Generic category assignment if not found
                if func_category == 'other' and control_name.startswith('P1_'):
                    if 'BUTTON' in control_name:
                        try:
                            button_num = int(control_name.replace('P1_BUTTON', ''))
                            if button_num <= 2:
                                func_category = 'action_primary'
                            elif button_num <= 4:
                                func_category = 'action_secondary'
                            else:
                                func_category = 'action_special'
                        except ValueError:
                            pass
                    elif 'JOYSTICK' in control_name:
                        if 'LEFT' in control_name or 'RIGHT' in control_name:
                            func_category = 'move_horizontal'
                        elif 'UP' in control_name or 'DOWN' in control_name:
                            func_category = 'move_vertical'
                
                label['func_category'] = func_category
                
                # Apply mappings if available
                if control_name in all_mappings:
                    mapping_info = all_mappings[control_name]
                    
                    label['mapping'] = mapping_info['mapping']
                    label['mapping_source'] = mapping_info['source']
                    label['is_custom'] = 'ROM CFG' in mapping_info['source']
                    label['cfg_mapping'] = True
                    label['input_mode'] = self.input_mode
                    
                    # Process target_button based on input mode
                    if " ||| " in mapping_info['mapping']:
                        inc_mapping, dec_mapping = mapping_info['mapping'].split(" ||| ")
                        
                        if self.input_mode == 'xinput':
                            if 'XINPUT' in inc_mapping and 'XINPUT' in dec_mapping:
                                if inc_mapping == "NONE" and dec_mapping != "NONE":
                                    dec_friendly = self.get_friendly_xinput_name(dec_mapping)
                                    label['target_button'] = dec_friendly
                                elif dec_mapping == "NONE" and inc_mapping != "NONE":
                                    inc_friendly = self.get_friendly_xinput_name(inc_mapping)
                                    label['target_button'] = inc_friendly
                                else:
                                    inc_friendly = self.get_friendly_xinput_name(inc_mapping)
                                    dec_friendly = self.get_friendly_xinput_name(dec_mapping)
                                    label['target_button'] = f"{inc_friendly} | {dec_friendly}"
                        elif self.input_mode == 'keycode':
                            inc_keycode = self.extract_keycode_from_mapping(inc_mapping)
                            dec_keycode = self.extract_keycode_from_mapping(dec_mapping)
                            
                            if inc_keycode and dec_keycode:
                                label['target_button'] = f"{inc_keycode} | {dec_keycode}"
                            elif inc_keycode:
                                label['target_button'] = inc_keycode
                            elif dec_keycode:
                                label['target_button'] = dec_keycode
                            else:
                                label['target_button'] = "No Key Assigned"
                        # Add other input modes as needed
                    else:
                        # Regular mapping
                        if self.input_mode == 'xinput' and 'XINPUT' in mapping_info['mapping']:
                            label['target_button'] = self.get_friendly_xinput_name(mapping_info['mapping'])
                        elif self.input_mode == 'keycode':
                            keycode_display = self.extract_keycode_from_mapping(mapping_info['mapping'])
                            label['target_button'] = keycode_display if keycode_display else "No Key Assigned"
                        # Add other input modes as needed
                else:
                    label['is_custom'] = False
                
                # Set display style
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
                    label['display_style'] = 'standard'
                        
                # Set display name
                if 'target_button' in label:
                    if self.input_mode == 'keycode':
                        label['display_name'] = label["target_button"]
                    else:
                        label['display_name'] = f'P1 {label["target_button"]}'
                else:
                    if self.input_mode == 'keycode':
                        label['display_name'] = "No Key Assigned"
                    else:
                        # Set default display names for other modes
                        if control_name == 'P1_BUTTON1':
                            label['display_name'] = 'P1 A Button'
                        elif control_name == 'P1_BUTTON2':
                            label['display_name'] = 'P1 B Button'
                        # Add more default mappings as needed
                        else:
                            label['display_name'] = self.format_control_name(control_name)
        
        # Add current input mode to game_data
        game_data['input_mode'] = self.input_mode

    def precache_game(self, rom_name):
        """Fast precaching without GUI - main function called from command line"""
        start_time = time.time()
        
        print(f"Precaching game data for: {rom_name}")
        
        # Set up cache path
        cache_file = os.path.join(self.cache_dir, f"{rom_name}_cache.json")
        
        # Get game data
        game_data = self.get_game_data(rom_name)
        if not game_data:
            print(f"Error: No control data found for {rom_name}")
            return False
        
        print(f"Retrieved {rom_name} from {game_data.get('source', 'unknown source')}")
        
        # Apply custom mappings if they exist
        cfg_controls = {}
        if rom_name in self.custom_configs:
            cfg_content = self.custom_configs[rom_name]
            parsed_controls = self.parse_cfg_controls(cfg_content)
            if parsed_controls:
                print(f"Found {len(parsed_controls)} control mappings in ROM CFG for {rom_name}")
                cfg_controls = {
                    control: self.convert_mapping(mapping, self.input_mode)
                    for control, mapping in parsed_controls.items()
                }
            else:
                print(f"ROM CFG exists for {rom_name} but contains no control mappings")
        
        # Apply custom mappings
        self.update_game_data_with_custom_mappings(game_data, cfg_controls)
        
        # Save to cache
        try:
            with open(cache_file, 'w') as f:
                json.dump(game_data, f, indent=2)
            
            load_time = time.time() - start_time
            print(f"Precached {rom_name} in {load_time:.3f} seconds using {self.input_mode} mode")
            print(f"Saved to: {cache_file}")
            print(f"Source: {game_data.get('source', 'unknown')}")
            print(f"Input Mode: {game_data.get('input_mode', 'unknown')}")
            print(f"Players: {len(game_data.get('players', []))}")
            
            if game_data.get('players'):
                for player in game_data['players']:
                    control_count = len(player.get('labels', []))
                    custom_count = len([l for l in player.get('labels', []) if l.get('is_custom', False)])
                    mapped_count = len([l for l in player.get('labels', []) if l.get('target_button')])
                    print(f"  Player {player['number']}: {control_count} controls ({custom_count} custom, {mapped_count} mapped)")
                    
                    if control_count > 0:
                        sample_label = player['labels'][0]
                        print(f"    Sample control: {sample_label['name']} -> {sample_label.get('target_button', sample_label.get('display_name', sample_label['value']))}")
                        
            return True
            
        except Exception as e:
            print(f"Error saving cache: {e}")
            return False

    # Helper methods for input mode processing
    def convert_mapping(self, mapping: str, to_mode: str = None) -> str:
        """Convert between mapping formats"""
        if not mapping:
            return mapping
            
        if to_mode is None:
            to_mode = self.input_mode
        
        if " ||| " in mapping:
            inc_mapping, dec_mapping = mapping.split(" ||| ")
            inc_converted = self.convert_single_mapping(inc_mapping, to_mode)
            dec_converted = self.convert_single_mapping(dec_mapping, to_mode)
            return f"{inc_converted} ||| {dec_converted}"
        
        return self.convert_single_mapping(mapping, to_mode)

    def convert_single_mapping(self, mapping: str, to_mode: str) -> str:
        """Convert a single mapping between formats"""
        if " OR " in mapping:
            parts = mapping.split(" OR ")
            
            if to_mode == 'xinput':
                for part in parts:
                    part = part.strip()
                    if part.startswith('XINPUT'):
                        return part
                
                for part in parts:
                    if part.startswith('JOYCODE'):
                        converted = self.joycode_to_xinput(part.strip())
                        if converted.startswith('XINPUT'):
                            return converted
                        
            return parts[0].strip()
        
        # Direct conversion
        if mapping.startswith('JOYCODE') and to_mode == 'xinput':
            return self.joycode_to_xinput(mapping)
        
        return mapping

    def joycode_to_xinput(self, mapping: str) -> str:
        """Convert JOYCODE to XInput format"""
        xinput_mappings = {
            'JOYCODE_1_BUTTON1': 'XINPUT_1_A',
            'JOYCODE_1_BUTTON2': 'XINPUT_1_B',
            'JOYCODE_1_BUTTON3': 'XINPUT_1_X',
            'JOYCODE_1_BUTTON4': 'XINPUT_1_Y',
            'JOYCODE_1_BUTTON5': 'XINPUT_1_SHOULDER_L',
            'JOYCODE_1_BUTTON6': 'XINPUT_1_SHOULDER_R',
        }
        
        return xinput_mappings.get(mapping, mapping)

    def get_friendly_xinput_name(self, mapping: str) -> str:
        """Convert XINPUT mapping to friendly name"""
        parts = mapping.split('_', 2)
        if len(parts) < 3:
            return mapping
        action = parts[2]
        
        friendly_map = {
            "A": "A Button",
            "B": "B Button", 
            "X": "X Button",
            "Y": "Y Button",
            "SHOULDER_L": "LB Button",
            "SHOULDER_R": "RB Button",
        }
        return friendly_map.get(action, action)

    def extract_keycode_from_mapping(self, mapping: str) -> str:
        """Extract KEYCODE from mapping string"""
        if not mapping:
            return ""
        
        if " ||| " in mapping:
            inc_mapping, dec_mapping = mapping.split(" ||| ")
            inc_keycode = self.extract_keycode_from_mapping(inc_mapping)
            dec_keycode = self.extract_keycode_from_mapping(dec_mapping)
            
            if inc_keycode and dec_keycode:
                return f"{inc_keycode} | {dec_keycode}"
            elif inc_keycode:
                return inc_keycode
            elif dec_keycode:
                return dec_keycode
            else:
                return ""
        
        if " OR " in mapping:
            parts = mapping.split(" OR ")
            for part in parts:
                part = part.strip()
                if part.startswith('KEYCODE_'):
                    return self.format_keycode_display(part)
            return ""
        
        if mapping.startswith('KEYCODE_'):
            return self.format_keycode_display(mapping)
        
        return ""

    def format_keycode_display(self, mapping: str) -> str:
        """Format KEYCODE mapping for display"""
        if not mapping or not mapping.startswith("KEYCODE_"):
            return mapping
            
        key_name = mapping.replace("KEYCODE_", "")
        
        key_mappings = {
            'LCONTROL': 'Left Ctrl',
            'RCONTROL': 'Right Ctrl',
            'LALT': 'Left Alt',
            'RALT': 'Right Alt', 
            'LSHIFT': 'Left Shift',
            'RSHIFT': 'Right Shift',
            'SPACE': 'Spacebar',
            'ENTER': 'Enter',
        }
        
        friendly_name = key_mappings.get(key_name, key_name)
        return f"Key {friendly_name}"

    def format_control_name(self, control_name: str) -> str:
        """Format control name for display"""
        if control_name == 'P1_BUTTON1':
            return 'P1 A Button'
        elif control_name == 'P1_BUTTON2':
            return 'P1 B Button'
        # Add more mappings as needed
        else:
            return control_name


# Main function for command line usage
def main():
    """Main function for precaching from command line"""
    if len(sys.argv) < 2:
        print("Usage: python mame_data_processor.py <rom_name>")
        return 1
    
    rom_name = sys.argv[1]
    
    try:
        processor = MAMEDataProcessor()
        success = processor.precache_game(rom_name)
        return 0 if success else 1
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

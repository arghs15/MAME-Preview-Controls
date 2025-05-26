# mame_data_utils.py
"""
Core data processing utilities for MAME Controls Configuration
Handles gamedata loading, config parsing, mapping conversions, and cache management
"""

import os
import json
import sqlite3
import time
import re
import xml.etree.ElementTree as ET
from io import StringIO
from typing import Dict, Set, Tuple, Optional, List, Any

# ============================================================================
# DATA LOADING AND DATABASE METHODS
# ============================================================================

def load_gamedata_json(gamedata_path: str) -> Tuple[Dict, Dict, Dict]:
    """
    Load gamedata.json from the specified path with improved error handling
    
    Returns:
        Tuple of (gamedata_json, parent_lookup, clone_parents)
    """
    if not os.path.exists(gamedata_path):
        print(f"ERROR: gamedata.json not found at {gamedata_path}")
        return {}, {}, {}
    
    try:
        with open(gamedata_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Process the data for main games and clones
        gamedata_json = {}
        parent_lookup = {}
        clone_parents = {}  # Dictionary to track which parents have which clones
        
        for rom_name, game_data in data.items():
            gamedata_json[rom_name] = game_data
                
            # Build parent-child relationship
            if 'clones' in game_data and isinstance(game_data['clones'], dict):
                # Track all this parent's clones
                clone_parents[rom_name] = list(game_data['clones'].keys())
                
                for clone_name, clone_data in game_data['clones'].items():
                    # Store parent reference
                    clone_data['parent'] = rom_name
                    parent_lookup[clone_name] = rom_name
        
        return gamedata_json, parent_lookup, clone_parents
    
    except json.JSONDecodeError as e:
        print(f"JSON PARSE ERROR in {gamedata_path}:")
        print(f"  Line {e.lineno}, Column {e.colno}: {e.msg}")
        raise
    except FileNotFoundError:
        print(f"File not found: {gamedata_path}")
        raise
    except UnicodeDecodeError as e:
        print(f"Encoding error in {gamedata_path}: {e}")
        raise
    except Exception as e:
        print(f"ERROR loading gamedata.json: {str(e)}")
        raise

def check_db_update_needed(gamedata_path: str, db_path: str) -> bool:
    """Check if the SQLite database needs to be updated based on gamedata.json timestamp"""
    # Ensure gamedata.json exists first
    if not os.path.exists(gamedata_path):
        return False
            
    # Check if database exists
    if not os.path.exists(db_path):
        print(f"Database doesn't exist yet, creating at: {db_path}")
        return True
            
    # Get file modification timestamps
    gamedata_mtime = os.path.getmtime(gamedata_path)
    db_mtime = os.path.getmtime(db_path)
    
    # Compare timestamps - only rebuild if gamedata is newer than database
    return gamedata_mtime > db_mtime

def build_gamedata_db(gamedata_json: Dict, db_path: str) -> bool:
    """Build SQLite database from gamedata.json for faster lookups"""
    print("Building SQLite database...")
    start_time = time.time()
    
    if not gamedata_json:
        print("ERROR: No gamedata available to build database")
        return False
    
    try:
        # Create database connection
        conn = sqlite3.connect(db_path)
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
        for rom_name, game_data in gamedata_json.items():
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
                _insert_controls(cursor, rom_name, game_data['controls'])
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
                        _insert_controls(cursor, clone_name, clone_data['controls'])
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
        if 'conn' in locals():
            conn.close()
        return False

def _insert_controls(cursor, rom_name: str, controls_dict: Dict):
    """Helper method to insert controls into the database"""
    for control_name, control_data in controls_dict.items():
        display_name = control_data.get('name', '')
        if display_name:
            cursor.execute(
                "INSERT INTO game_controls (rom_name, control_name, display_name) VALUES (?, ?, ?)",
                (rom_name, control_name, display_name)
            )

def rom_exists_in_db(romname: str, db_path: str) -> bool:
    """Quick check if ROM exists in database without loading full data"""
    if not os.path.exists(db_path):
        return False
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM games WHERE rom_name = ? LIMIT 1", (romname,))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    except:
        return False

def get_game_data_from_db(romname: str, db_path: str) -> Optional[Dict]:
    """Get control data for a ROM from the SQLite database with better handling of unnamed controls"""
    
    if not os.path.exists(db_path):
        return None
    
    conn = None
    try:
        # Create connection
        conn = sqlite3.connect(db_path)
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
                return get_game_data_from_db(parent_rom, db_path)
            else:
                # No data found
                conn.close()
                return None
        
        # Access columns by index
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
        default_actions = get_default_control_actions()
        
        for control in control_rows:
            control_name = control[0]
            display_name = control[1]
            
            # If display_name is empty, try to use a default
            if not display_name and control_name in default_actions:
                display_name = default_actions[control_name]
            
            # If still no display name, try to extract from control name
            if not display_name:
                parts = control_name.split('_')
                if len(parts) > 1:
                    display_name = parts[-1].replace('_', ' ').title()
                else:
                    display_name = control_name
            
            # Add to appropriate player list
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

def get_game_data(romname: str, gamedata_json: Dict, parent_lookup: Dict, 
                  db_path: str = None, rom_data_cache: Dict = None) -> Optional[Dict]:
    """
    Get game data with integrated database prioritization and improved handling of unnamed controls
    
    Args:
        romname: ROM name to get data for
        gamedata_json: Loaded gamedata.json dictionary
        parent_lookup: Dictionary mapping clone ROM names to parent ROM names
        db_path: Path to SQLite database (optional)
        rom_data_cache: In-memory cache dictionary (optional)
    """
    # Check cache first
    if rom_data_cache and romname in rom_data_cache:
        return rom_data_cache[romname]
    
    # Try database first if available
    if db_path and os.path.exists(db_path):
        db_data = get_game_data_from_db(romname, db_path)
        if db_data:
            # Cache the result
            if rom_data_cache is not None:
                rom_data_cache[romname] = db_data
            return db_data
    
    # Fall back to JSON lookup
    if romname in gamedata_json:
        game_data = gamedata_json[romname]
        converted_data = _convert_gamedata_json_to_standard_format(
            romname, game_data, gamedata_json, parent_lookup
        )
        
        # Cache the result
        if rom_data_cache is not None:
            rom_data_cache[romname] = converted_data
            
        return converted_data
    
    # Try parent lookup before giving up
    if romname in parent_lookup:
        parent_rom = parent_lookup[romname]
        parent_data = get_game_data(parent_rom, gamedata_json, parent_lookup, db_path, rom_data_cache)
        if parent_data:
            # Update with this ROM's info and cache
            parent_data['romname'] = romname
            if romname in gamedata_json:
                parent_data['gamename'] = gamedata_json[romname].get('description', f"{romname} (Clone)")
            
            # Cache and return
            if rom_data_cache is not None:
                rom_data_cache[romname] = parent_data
            return parent_data
    
    # Not found anywhere
    return None

def _convert_gamedata_json_to_standard_format(romname: str, game_data: Dict, 
                                            gamedata_json: Dict, parent_lookup: Dict) -> Dict:
    """Convert gamedata.json format to standard game data format"""
    
    # Simple name defaults - these are the fallback button names if none are specified
    default_actions = get_default_control_actions()
    
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
        
        # Check explicit parent field
        if 'parent' in game_data:
            parent_rom = game_data['parent']
        # Also check parent lookup table for redundancy
        elif romname in parent_lookup:
            parent_rom = parent_lookup[romname]
        
        # If we found a parent, try to get its controls
        if parent_rom and parent_rom in gamedata_json:
            parent_data = gamedata_json[parent_rom]
            if 'controls' in parent_data:
                controls = parent_data['controls']
    
    # Now process the controls (either direct or inherited from parent)
    if controls:
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
                    
                    # ALWAYS add the control
                    control_entry = {
                        'name': control_name,
                        'value': friendly_name
                    }
                    p1_controls.append(control_entry)
        
        # Sort controls by name to ensure consistent order
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

def get_default_control_actions() -> Dict[str, str]:
    """Get default control action mappings"""
    return {
        'P1_JOYSTICK_UP': 'Up',
        'P1_JOYSTICK_DOWN': 'Down',
        'P1_JOYSTICK_LEFT': 'Left',
        'P1_JOYSTICK_RIGHT': 'Right',
        'P2_JOYSTICK_UP': 'Up',
        'P2_JOYSTICK_DOWN': 'Down',
        'P2_JOYSTICK_LEFT': 'Left',
        'P2_JOYSTICK_RIGHT': 'Right',
        'P1_PEDAL': 'Accelerator Pedal',
        'P1_PEDAL2': 'Brake Pedal',  
        'P1_AD_STICK_X': 'Steering Left/Right',
        'P1_AD_STICK_Y': 'Lean Forward/Back',
        'P1_AD_STICK_Z': 'Throttle Control',
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

# ============================================================================
# CONFIG FILE PARSING
# ============================================================================

def load_custom_configs(mame_dir: str) -> Dict[str, str]:
    """Load custom configurations from cfg directory"""
    custom_configs = {}
    cfg_dir = os.path.join(mame_dir, "cfg")
    
    if not os.path.exists(cfg_dir):
        print(f"Config directory not found: {cfg_dir}")
        return custom_configs

    for filename in os.listdir(cfg_dir):
        if filename.endswith(".cfg"):
            game_name = filename[:-4]
            full_path = os.path.join(cfg_dir, filename)
            try:
                # Read as binary first to handle BOM
                with open(full_path, "rb") as f:
                    content = f.read()
                # Decode with UTF-8-SIG to handle BOM
                custom_configs[game_name] = content.decode('utf-8-sig')
            except Exception as e:
                print(f"Error loading {filename}: {e}")

    print(f"Loaded {len(custom_configs)} custom configurations")
    return custom_configs

def load_default_config(mame_dir: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Load the default MAME control configuration
    
    Returns:
        Tuple of (default_controls, original_default_controls)
    """
    cfg_dir = os.path.join(mame_dir, "cfg")
    default_cfg_path = os.path.join(cfg_dir, "default.cfg")
    
    print(f"Looking for default.cfg at: {default_cfg_path}")
    if os.path.exists(default_cfg_path):
        try:
            print(f"Loading default config from: {default_cfg_path}")
            # Read file content
            with open(default_cfg_path, "rb") as f:
                content = f.read()
            
            # Parse the default mappings using the enhanced parser
            default_controls, original_controls = parse_default_cfg(content.decode('utf-8-sig'))
            
            print(f"Loaded {len(default_controls)} default control mappings")
            return default_controls, original_controls
        except Exception as e:
            print(f"Error loading default config: {e}")
            return {}, {}
    else:
        print("No default.cfg found in cfg directory")
        return {}, {}

def parse_default_cfg(cfg_content: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Parse default.cfg to extract all control mappings focusing on XInput format"""
    controls = {}
    original_controls = {}  # Store original mappings for KEYCODE mode
    
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
                    xinput = convert_mapping(part, "xinput")
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

                # Store original mapping for KEYCODE mode
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

                # Store the original mapping for KEYCODE mode
                if original_mapping:
                    original_controls[ctype] = original_mapping

    except Exception as e:
        print(f"Error parsing default.cfg: {e}")
    
    return controls, original_controls

def parse_cfg_controls(cfg_content: str, input_mode: str = 'xinput') -> Dict[str, str]:
    """Parse MAME cfg file to extract control mappings with support for increment/decrement pairs"""
    controls = {}
    try:
        print(f"Parsing CFG content of length: {len(cfg_content)}")
        print(f"Using mapping mode: {input_mode} for parsing CFG")

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
                        xinput_mapping = convert_mapping(part, input_mode)
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
                    xinput_mapping = convert_mapping(mapping_str.strip(), input_mode)
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
            # Find all port elements
            all_ports = input_elem.findall('port')
            print(f"Found {len(all_ports)} total ports in config")

            # Process all port elements regardless of type
            for port in all_ports:
                control_type = port.get('type')
                if control_type:
                    
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

                        # Handle case where only increment exists
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
                                    break
                            
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

    except ET.ParseError as e:
        print(f"XML parsing failed with error: {str(e)}")
        print("First 100 chars of content:", repr(cfg_content[:100]))
    except Exception as e:
        print(f"Unexpected error parsing cfg: {str(e)}")

    print(f"Found {len(controls)} control mappings")
    return controls

# ============================================================================
# MAPPING CONVERSION METHODS
# ============================================================================

# Define specific conversion functions first
def joycode_to_xinput(mapping: str) -> str:
    """Convert JOYCODE to XInput format"""
    xinput_mappings = {
        'JOYCODE_1_BUTTON1': 'XINPUT_1_A',
        'JOYCODE_1_BUTTON2': 'XINPUT_1_B',
        'JOYCODE_1_BUTTON3': 'XINPUT_1_X',
        'JOYCODE_1_BUTTON4': 'XINPUT_1_Y',
        'JOYCODE_1_BUTTON5': 'XINPUT_1_SHOULDER_L',
        'JOYCODE_1_BUTTON6': 'XINPUT_1_SHOULDER_R',
        'JOYCODE_1_BUTTON7': 'XINPUT_1_START',
        'JOYCODE_1_BUTTON8': 'XINPUT_1_BACK',
        'JOYCODE_1_BUTTON9': 'XINPUT_1_THUMB_L',
        'JOYCODE_1_BUTTON10': 'XINPUT_1_THUMB_R',
        'JOYCODE_1_HATUP': 'XINPUT_1_DPAD_UP',
        'JOYCODE_1_HATDOWN': 'XINPUT_1_DPAD_DOWN',
        'JOYCODE_1_HATLEFT': 'XINPUT_1_DPAD_LEFT',
        'JOYCODE_1_HATRIGHT': 'XINPUT_1_DPAD_RIGHT',
        # Player 2 mappings
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
    }
    
    return xinput_mappings.get(mapping, mapping)

def joycode_to_dinput(mapping: str) -> str:
    """Convert JOYCODE to DInput format"""
    dinput_mappings = {
        'JOYCODE_1_BUTTON1': 'DINPUT_1_BUTTON0',
        'JOYCODE_1_BUTTON2': 'DINPUT_1_BUTTON1',
        'JOYCODE_1_BUTTON3': 'DINPUT_1_BUTTON2',
        'JOYCODE_1_BUTTON4': 'DINPUT_1_BUTTON3',
        'JOYCODE_1_BUTTON5': 'DINPUT_1_BUTTON4',
        'JOYCODE_1_BUTTON6': 'DINPUT_1_BUTTON5',
        'JOYCODE_1_BUTTON7': 'DINPUT_1_BUTTON6',
        'JOYCODE_1_BUTTON8': 'DINPUT_1_BUTTON7',
        'JOYCODE_1_BUTTON9': 'DINPUT_1_BUTTON8',
        'JOYCODE_1_BUTTON10': 'DINPUT_1_BUTTON9',
        # Player 2 mappings
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
    }
    
    return dinput_mappings.get(mapping, mapping)

def xinput_to_joycode(mapping: str) -> str:
    """Convert XInput to JOYCODE format"""
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
    }
    
    return reverse_mappings.get(mapping, mapping)

def xinput_to_dinput(mapping: str) -> str:
    """Convert XInput to DInput format"""
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
    }
    
    return mapping_dict.get(mapping, mapping)

def dinput_to_joycode(mapping: str) -> str:
    """Convert DInput to JOYCODE format"""
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
    }
    
    return reverse_mappings.get(mapping, mapping)

def dinput_to_xinput(mapping: str) -> str:
    """Convert DInput to XInput format"""
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
    }
    
    return mapping_dict.get(mapping, mapping)

def convert_mapping(mapping: str, to_mode: str = 'xinput') -> str:
    """Convert between JOYCODE, XInput, and DInput mappings with support for increment/decrement pairs"""
    if not mapping:
        return mapping
    
    # Handle special format for increment/decrement pairs
    if " ||| " in mapping:
        # Split into increment and decrement parts
        inc_mapping, dec_mapping = mapping.split(" ||| ")
        
        # Convert each part separately
        inc_converted = convert_single_mapping(inc_mapping, to_mode)
        dec_converted = convert_single_mapping(dec_mapping, to_mode)
        
        # Return combined converted mapping
        return f"{inc_converted} ||| {dec_converted}"
    
    # For regular mappings, use the original logic
    return convert_single_mapping(mapping, to_mode)

def convert_single_mapping(mapping: str, to_mode: str) -> str:
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
                    return part
            
            # No direct XInput mapping found, try to convert JOYCODE parts
            for part in parts:
                if part.startswith('JOYCODE'):
                    converted = joycode_to_xinput(part.strip())
                    if converted.startswith('XINPUT'):
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
                    converted = joycode_to_dinput(part.strip())
                    if converted.startswith('DINPUT'):
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
                    converted = xinput_to_joycode(part.strip())
                    if converted.startswith('JOYCODE'):
                        return converted
                        
            # Try to convert DInput to JOYCODE
            for part in parts:
                if part.startswith('DINPUT'):
                    converted = dinput_to_joycode(part.strip())
                    if converted.startswith('JOYCODE'):
                        return converted
                    
        # If no conversion found, return the first part
        return parts[0].strip()
    
    # Simple direct conversion for individual mappings
    if mapping.startswith('JOYCODE'):
        if to_mode == 'xinput':
            return joycode_to_xinput(mapping)
        elif to_mode == 'dinput':
            return joycode_to_dinput(mapping)
    elif mapping.startswith('XINPUT'):
        if to_mode == 'joycode':
            return xinput_to_joycode(mapping)
        elif to_mode == 'dinput':
            return xinput_to_dinput(mapping)
    elif mapping.startswith('DINPUT'):
        if to_mode == 'joycode':
            return dinput_to_joycode(mapping)
        elif to_mode == 'xinput':
            return dinput_to_xinput(mapping)
    
    # If already in the right format or if no conversion found, return as is
    return mapping

# Specific conversion functions
def joycode_to_xinput(mapping: str) -> str:
    """Convert JOYCODE to XInput format"""
    xinput_mappings = {
        'JOYCODE_1_BUTTON1': 'XINPUT_1_A',
        'JOYCODE_1_BUTTON2': 'XINPUT_1_B',
        'JOYCODE_1_BUTTON3': 'XINPUT_1_X',
        'JOYCODE_1_BUTTON4': 'XINPUT_1_Y',
        'JOYCODE_1_BUTTON5': 'XINPUT_1_SHOULDER_L',
        'JOYCODE_1_BUTTON6': 'XINPUT_1_SHOULDER_R',
        'JOYCODE_1_BUTTON7': 'XINPUT_1_START',
        'JOYCODE_1_BUTTON8': 'XINPUT_1_BACK',
        'JOYCODE_1_BUTTON9': 'XINPUT_1_THUMB_L',
        'JOYCODE_1_BUTTON10': 'XINPUT_1_THUMB_R',
        'JOYCODE_1_HATUP': 'XINPUT_1_DPAD_UP',
        'JOYCODE_1_HATDOWN': 'XINPUT_1_DPAD_DOWN',
        'JOYCODE_1_HATLEFT': 'XINPUT_1_DPAD_LEFT',
        'JOYCODE_1_HATRIGHT': 'XINPUT_1_DPAD_RIGHT',
        # Player 2 mappings
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
    }
    
    return xinput_mappings.get(mapping, mapping)

def joycode_to_dinput(mapping: str) -> str:
    """Convert JOYCODE to DInput format"""
    dinput_mappings = {
        'JOYCODE_1_BUTTON1': 'DINPUT_1_BUTTON0',
        'JOYCODE_1_BUTTON2': 'DINPUT_1_BUTTON1',
        'JOYCODE_1_BUTTON3': 'DINPUT_1_BUTTON2',
        'JOYCODE_1_BUTTON4': 'DINPUT_1_BUTTON3',
        'JOYCODE_1_BUTTON5': 'DINPUT_1_BUTTON4',
        'JOYCODE_1_BUTTON6': 'DINPUT_1_BUTTON5',
        'JOYCODE_1_BUTTON7': 'DINPUT_1_BUTTON6',
        'JOYCODE_1_BUTTON8': 'DINPUT_1_BUTTON7',
        'JOYCODE_1_BUTTON9': 'DINPUT_1_BUTTON8',
        'JOYCODE_1_BUTTON10': 'DINPUT_1_BUTTON9',
        # Player 2 mappings
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
    }
    
    return dinput_mappings.get(mapping, mapping)

def xinput_to_joycode(mapping: str) -> str:
    """Convert XInput to JOYCODE format"""
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
    }
    
    return reverse_mappings.get(mapping, mapping)

def xinput_to_dinput(mapping: str) -> str:
    """Convert XInput to DInput format"""
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
    }
    
    return mapping_dict.get(mapping, mapping)

def dinput_to_joycode(mapping: str) -> str:
    """Convert DInput to JOYCODE format"""
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
    }
    
    return reverse_mappings.get(mapping, mapping)

def dinput_to_xinput(mapping: str) -> str:
    """Convert DInput to XInput format"""
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
    }
    
    return mapping_dict.get(mapping, mapping)

# ============================================================================
# DISPLAY FORMATTING METHODS
# ============================================================================

def extract_keycode_from_mapping(mapping: str) -> str:
    """Extract KEYCODE from mapping string like 'KEYCODE_LCONTROL OR JOYCODE_1_BUTTON2'"""
    if not mapping:
        return ""
    
    # Handle increment/decrement pairs
    if " ||| " in mapping:
        inc_mapping, dec_mapping = mapping.split(" ||| ")
        inc_keycode = extract_keycode_from_mapping(inc_mapping)
        dec_keycode = extract_keycode_from_mapping(dec_mapping)
        
        if inc_keycode and dec_keycode:
            return f"{inc_keycode} | {dec_keycode}"
        elif inc_keycode:
            return inc_keycode
        elif dec_keycode:
            return dec_keycode
        else:
            return ""
    
    # Handle OR statements - look for KEYCODE part
    if " OR " in mapping:
        parts = mapping.split(" OR ")
        for part in parts:
            part = part.strip()
            if part.startswith('KEYCODE_'):
                return format_keycode_display(part)
        return ""
    
    # Single mapping
    if mapping.startswith('KEYCODE_'):
        return format_keycode_display(mapping)
    
    return ""

def format_keycode_display(mapping: str) -> str:
    """Format KEYCODE mapping string for display"""
    if not mapping or not mapping.startswith("KEYCODE_"):
        return mapping
        
    key_name = mapping.replace("KEYCODE_", "")
    
    # Make common keys more readable
    key_mappings = {
        'LCONTROL': 'Left Ctrl',
        'RCONTROL': 'Right Ctrl',
        'LALT': 'Left Alt',
        'RALT': 'Right Alt', 
        'LSHIFT': 'Left Shift',
        'RSHIFT': 'Right Shift',
        'SPACE': 'Spacebar',
        'ENTER': 'Enter',
        'BACKSPACE': 'Backspace',
        'TAB': 'Tab',
        'ESC': 'Escape',
        'UP': 'Up Arrow',
        'DOWN': 'Down Arrow',
        'LEFT': 'Left Arrow',
        'RIGHT': 'Right Arrow',
        'HOME': 'Home',
        'END': 'End',
        'PGUP': 'Page Up',
        'PGDN': 'Page Down',
        'DEL': 'Delete',
        'INSERT': 'Insert',
        'CAPSLOCK': 'Caps Lock',
        'NUMLOCK': 'Num Lock',
        'SCRLOCK': 'Scroll Lock',
        'PRTSCR': 'Print Screen',
        'PAUSE': 'Pause',
        'MENU': 'Menu',
        'LWIN': 'Left Windows',
        'RWIN': 'Right Windows',
        # Number pad keys
        'NUMPAD0': 'Numpad 0',
        'NUMPAD1': 'Numpad 1',
        'NUMPAD2': 'Numpad 2',
        'NUMPAD3': 'Numpad 3',
        'NUMPAD4': 'Numpad 4',
        'NUMPAD5': 'Numpad 5',
        'NUMPAD6': 'Numpad 6',
        'NUMPAD7': 'Numpad 7',
        'NUMPAD8': 'Numpad 8',
        'NUMPAD9': 'Numpad 9',
        'NUMPADENTER': 'Numpad Enter',
        'NUMPADPLUS': 'Numpad +',
        'NUMPADMINUS': 'Numpad -',
        'NUMPADSTAR': 'Numpad *',
        'NUMPADSLASH': 'Numpad /',
        'NUMPADDOT': 'Numpad .',
        # Function keys
        'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4',
        'F5': 'F5', 'F6': 'F6', 'F7': 'F7', 'F8': 'F8',
        'F9': 'F9', 'F10': 'F10', 'F11': 'F11', 'F12': 'F12',
    }
    
    friendly_name = key_mappings.get(key_name, key_name)
    return f"Key {friendly_name}"

def get_friendly_xinput_name(mapping: str) -> str:
    """Convert an XINPUT mapping code into a human-friendly button/stick name."""
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
        "TRIGGER_L": "Left Trigger",
        "TRIGGER_R": "Right Trigger",
        "THUMB_L": "Left Stick Button",
        "THUMB_R": "Right Stick Button",
        "DPAD_UP": "D-Pad Up",
        "DPAD_DOWN": "D-Pad Down",
        "DPAD_LEFT": "D-Pad Left",
        "DPAD_RIGHT": "D-Pad Right",
        "LEFTX_NEG": "Left Stick (Left)",
        "LEFTX_POS": "Left Stick (Right)",
        "LEFTY_NEG": "Left Stick (Up)",
        "LEFTY_POS": "Left Stick (Down)",
        "RIGHTX_NEG": "Right Stick (Left)",
        "RIGHTX_POS": "Right Stick (Right)",
        "RIGHTY_NEG": "Right Stick (Up)",
        "RIGHTY_POS": "Right Stick (Down)"
    }
    return friendly_map.get(action, action)

def get_friendly_dinput_name(mapping: str) -> str:
    """Convert a DINPUT mapping code into a human-friendly button/stick name."""
    parts = mapping.split('_', 3)
    if len(parts) < 3:
        return mapping
    
    player_num = parts[1]
    action = parts[2]
    
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
    
    return f"DInput {player_num} {action}"

def format_joycode_display(mapping: str) -> str:
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

def format_mapping_display(mapping: str, input_mode: str = 'xinput') -> str:
    """Format the mapping string for display using friendly names for the current input mode."""
    
    # Handle OR statements by finding matching parts
    if " OR " in mapping:
        parts = mapping.split(" OR ")
        
        # Find part matching the current input mode
        for part in parts:
            part = part.strip()
            if input_mode == 'xinput' and "XINPUT" in part:
                mapping = part
                break
            elif input_mode == 'dinput' and "DINPUT" in part:
                mapping = part
                break
            elif input_mode == 'joycode' and "JOYCODE" in part:
                mapping = part
                break
            elif input_mode == 'keycode' and "KEYCODE" in part:
                mapping = part
                break
        
        # If no matching part found, use the first keycode part in keycode mode
        if " OR " in mapping and input_mode == 'keycode':
            for part in parts:
                if "KEYCODE" in part.strip():
                    mapping = part.strip()
                    break
    
    # Format based on the current input mode
    if input_mode == 'keycode':
        if mapping.startswith("KEYCODE"):
            return format_keycode_display(mapping)
        else:
            return "No Key Assigned"
    
    # Format based on the current input mode
    if input_mode == 'xinput':
        if mapping.startswith("XINPUT"):
            return get_friendly_xinput_name(mapping)
        else:
            # Try to convert to XInput
            converted = convert_mapping(mapping, 'xinput')
            if converted.startswith("XINPUT"):
                return get_friendly_xinput_name(converted)
    
    elif input_mode == 'dinput':
        if mapping.startswith("DINPUT"):
            return get_friendly_dinput_name(mapping)
        else:
            # Try to convert to DInput
            converted = convert_mapping(mapping, 'dinput')
            if converted.startswith("DINPUT"):
                return get_friendly_dinput_name(converted)
    
    elif input_mode == 'joycode':
        if "JOYCODE" in mapping:
            return format_joycode_display(mapping)
        else:
            # Try to convert to JOYCODE
            converted = convert_mapping(mapping, 'joycode')
            if "JOYCODE" in converted:
                return format_joycode_display(converted)
    
    # For keyboard mappings, convert to "Key X" format
    if mapping.startswith("KEYCODE"):
        key_name = mapping.replace("KEYCODE_", "")
        return f"Key {key_name}"

    # Fallback to original mapping if no conversion was possible
    return mapping

# ============================================================================
# DATA PROCESSING METHODS
# ============================================================================

def update_game_data_with_custom_mappings(game_data: Dict, cfg_controls: Dict, 
                                        default_controls: Dict, original_default_controls: Dict,
                                        input_mode: str = 'xinput') -> Dict:
    """
    Update game_data to include the custom control mappings with support for multiple input modes
    
    Args:
        game_data: Game data dictionary to update
        cfg_controls: Custom control mappings from ROM CFG
        default_controls: Default control mappings
        original_default_controls: Original default mappings for KEYCODE mode
        input_mode: Current input mode ('xinput', 'dinput', 'joycode', 'keycode')
    
    Returns:
        Updated game_data dictionary
    """
    print(f"DEBUG update_game_data_with_custom_mappings: input_mode={input_mode}")
    
    if not cfg_controls and not default_controls:
        print("DEBUG: No cfg_controls and no default_controls, returning early")
        return game_data
    
    # Get romname from game_data
    romname = game_data.get('romname', '')
    
    # Add flags to the game_data to indicate sources
    if cfg_controls:
        game_data['has_rom_cfg'] = True
        game_data['rom_cfg_file'] = f"{romname}.cfg"
    
    if default_controls:
        game_data['has_default_cfg'] = True
    
    # Combine ROM-specific and default mappings with smart KEYCODE fallback
    all_mappings = {}

    # First, add default mappings
    if default_controls:
        for control, mapping in default_controls.items():
            if input_mode == 'keycode':
                # For keycode mode, use original mapping if available
                if original_default_controls and control in original_default_controls:
                    original_mapping = original_default_controls[control]
                else:
                    original_mapping = mapping  # Fallback to processed mapping
            else:
                # For other modes, convert to current input mode
                original_mapping = convert_mapping(mapping, input_mode)
            all_mappings[control] = {'mapping': original_mapping, 'source': 'Default CFG'}

    # Then process ROM-specific mappings with smart KEYCODE fallback
    for control, mapping in cfg_controls.items():
        if input_mode == 'keycode':
            # For KEYCODE mode, check if ROM CFG has KEYCODE assignments
            rom_keycode = extract_keycode_from_mapping(mapping)
            
            if rom_keycode:
                # ROM CFG has KEYCODE assignments, use them
                all_mappings[control] = {'mapping': mapping, 'source': f"ROM CFG ({romname}.cfg)"}
            else:
                # ROM CFG has no KEYCODE, check if default CFG has KEYCODE for this control
                if (original_default_controls and control in original_default_controls):
                    default_original = original_default_controls[control]
                    default_keycode = extract_keycode_from_mapping(default_original)
                    
                    if default_keycode:
                        # Default CFG has KEYCODE, use it but note the source
                        all_mappings[control] = {
                            'mapping': default_original, 
                            'source': 'Default CFG (fallback)'
                        }
                    else:
                        # Neither has KEYCODE, use ROM CFG anyway (will show "No Key Assigned")
                        all_mappings[control] = {'mapping': mapping, 'source': f"ROM CFG ({romname}.cfg)"}
                else:
                    # No default mapping available, use ROM CFG
                    all_mappings[control] = {'mapping': mapping, 'source': f"ROM CFG ({romname}.cfg)"}
        else:
            # For non-KEYCODE modes, use ROM CFG as-is
            all_mappings[control] = {'mapping': mapping, 'source': f"ROM CFG ({romname}.cfg)"}
    
    # Define functional categories for organizing controls
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
            func_category = 'other'
            for category, controls in functional_categories.items():
                if control_name in controls:
                    func_category = category
                    break
                    
            # Additional catch-all logic for controls not explicitly listed
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
                # Additional categorization logic...
            
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
                label['input_mode'] = input_mode
                
                # Process target_button based on input mode
                _process_target_button_for_label(label, mapping_info['mapping'], input_mode)
                
            else:
                label['is_custom'] = False
            
            # Set display name based on input mode conventions
            _set_display_name_for_label(label, input_mode)
    
    # Add current input mode to game_data
    game_data['input_mode'] = input_mode
    
    return game_data

def _process_target_button_for_label(label: Dict, mapping: str, input_mode: str):
    """Process target_button for a label based on the mapping and input mode"""
    
    # Special handling for increment/decrement pairs
    if " ||| " in mapping:
        inc_mapping, dec_mapping = mapping.split(" ||| ")
        
        if input_mode == 'xinput':
            if 'XINPUT' in inc_mapping and 'XINPUT' in dec_mapping:
                if inc_mapping == "NONE" and dec_mapping != "NONE":
                    dec_friendly = get_friendly_xinput_name(dec_mapping)
                    label['target_button'] = dec_friendly
                elif dec_mapping == "NONE" and inc_mapping != "NONE":
                    inc_friendly = get_friendly_xinput_name(inc_mapping)
                    label['target_button'] = inc_friendly
                else:
                    inc_friendly = get_friendly_xinput_name(inc_mapping)
                    dec_friendly = get_friendly_xinput_name(dec_mapping)
                    label['target_button'] = f"{inc_friendly} | {dec_friendly}"
        elif input_mode == 'dinput':
            inc_converted = convert_mapping(inc_mapping, 'dinput')
            dec_converted = convert_mapping(dec_mapping, 'dinput')
            
            if inc_mapping == "NONE" or inc_converted == "NONE":
                dec_friendly = get_friendly_dinput_name(dec_converted) if 'DINPUT' in dec_converted else dec_converted
                if dec_mapping != "NONE" and dec_friendly != "NONE":
                    label['target_button'] = dec_friendly
            elif dec_mapping == "NONE" or dec_converted == "NONE":
                inc_friendly = get_friendly_dinput_name(inc_converted) if 'DINPUT' in inc_converted else inc_converted
                if inc_mapping != "NONE" and inc_friendly != "NONE":
                    label['target_button'] = inc_friendly
            else:
                inc_friendly = get_friendly_dinput_name(inc_converted) if 'DINPUT' in inc_converted else inc_converted
                dec_friendly = get_friendly_dinput_name(dec_converted) if 'DINPUT' in dec_converted else dec_converted
                label['target_button'] = f"{inc_friendly} | {dec_friendly}"
        elif input_mode == 'keycode':
            inc_keycode = extract_keycode_from_mapping(inc_mapping)
            dec_keycode = extract_keycode_from_mapping(dec_mapping)
            
            if inc_keycode and dec_keycode:
                label['target_button'] = f"{inc_keycode} | {dec_keycode}"
            elif inc_keycode:
                label['target_button'] = inc_keycode
            elif dec_keycode:
                label['target_button'] = dec_keycode
            else:
                label['target_button'] = "No Key Assigned"
        else:  # joycode mode
            if inc_mapping == "NONE":
                label['target_button'] = format_joycode_display(dec_mapping)
            elif dec_mapping == "NONE":
                label['target_button'] = format_joycode_display(inc_mapping)
            else:
                inc_display = format_joycode_display(inc_mapping)
                dec_display = format_joycode_display(dec_mapping)
                label['target_button'] = f"{inc_display} | {dec_display}"
    else:
        # Regular mapping handling for standard controls
        if input_mode == 'xinput' and 'XINPUT' in mapping:
            label['target_button'] = get_friendly_xinput_name(mapping)
        elif input_mode == 'dinput' and 'DINPUT' in mapping:
            label['target_button'] = get_friendly_dinput_name(mapping)
        elif input_mode == 'joycode' and 'JOYCODE' in mapping:
            label['target_button'] = format_joycode_display(mapping)
        elif input_mode == 'keycode':
            keycode_display = extract_keycode_from_mapping(mapping)
            label['target_button'] = keycode_display if keycode_display else "No Key Assigned"
        else:
            # Try conversion if not in the right format
            if input_mode == 'keycode':
                keycode_display = extract_keycode_from_mapping(mapping)
                label['target_button'] = keycode_display if keycode_display else "No Key Assigned"
            else:
                converted = convert_mapping(mapping, input_mode)
                if input_mode == 'xinput' and 'XINPUT' in converted:
                    label['target_button'] = get_friendly_xinput_name(converted)
                elif input_mode == 'dinput' and 'DINPUT' in converted:
                    label['target_button'] = get_friendly_dinput_name(converted)
                elif input_mode == 'joycode' and 'JOYCODE' in converted:
                    label['target_button'] = format_joycode_display(converted)
                else:
                    label['target_button'] = format_mapping_display(mapping, input_mode)

def _set_display_name_for_label(label: Dict, input_mode: str):
    """Set display name for a label based on input mode"""
    control_name = label['name']
    
    if 'target_button' in label:
        # Always use target_button if available from mapping
        if input_mode == 'dinput':
            label['display_name'] = f'P1 {label["target_button"]}'
        elif input_mode == 'joycode':
            label['display_name'] = label["target_button"]
        elif input_mode == 'keycode':
            label['display_name'] = label["target_button"]
        else:
            # XInput format
            label['display_name'] = f'P1 {label["target_button"]}'
    else:
        # No mapping, use default display names based on input mode
        label['display_name'] = format_control_name_for_mode(control_name, input_mode)

def format_control_name_for_mode(control_name: str, input_mode: str) -> str:
    """Convert MAME control names to friendly names based on input mode"""
    if input_mode == 'dinput':
        if control_name.startswith('P1_BUTTON'):
            button_num = int(control_name.replace('P1_BUTTON', '')) - 1
            if button_num < 0:
                button_num = 0
            return f'P1 Button {button_num}'
        elif control_name == 'P1_JOYSTICK_UP':
            return 'P1 POV Up'
        elif control_name == 'P1_JOYSTICK_DOWN':
            return 'P1 POV Down'
        elif control_name == 'P1_JOYSTICK_LEFT':
            return 'P1 POV Left'
        elif control_name == 'P1_JOYSTICK_RIGHT':
            return 'P1 POV Right'
    elif input_mode == 'joycode':
        if control_name.startswith('P1_BUTTON'):
            button_num = control_name.replace('P1_BUTTON', '')
            return f'Joy 1 Button {button_num}'
        elif control_name == 'P1_JOYSTICK_UP':
            return 'Joy Up'
        elif control_name == 'P1_JOYSTICK_DOWN':
            return 'Joy Down'
        elif control_name == 'P1_JOYSTICK_LEFT':
            return 'Joy Left'
        elif control_name == 'P1_JOYSTICK_RIGHT':
            return 'Joy Right'
    elif input_mode == 'keycode':
        return "No Key Assigned"
    else:  # XInput
        control_mappings = {
            'P1_BUTTON1': 'P1 A Button',
            'P1_BUTTON2': 'P1 B Button',
            'P1_BUTTON3': 'P1 X Button',
            'P1_BUTTON4': 'P1 Y Button',
            'P1_BUTTON5': 'P1 LB Button',
            'P1_BUTTON6': 'P1 RB Button',
            'P1_BUTTON7': 'P1 LT Button',
            'P1_BUTTON8': 'P1 RT Button',
            'P1_JOYSTICK_UP': 'P1 LS Up',
            'P1_JOYSTICK_DOWN': 'P1 LS Down',
            'P1_JOYSTICK_LEFT': 'P1 LS Left',
            'P1_JOYSTICK_RIGHT': 'P1 LS Right',
        }
        return control_mappings.get(control_name, control_name)
    
    return control_name

def filter_xinput_controls(game_data: Dict) -> Dict:
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
        'P1_JOYSTICKLEFT_UP', 'P1_JOYSTICKLEFT_DOWN', 'P1_JOYSTICKLEFT_LEFT', 'P1_JOYSTICKLEFT_RIGHT',
        'P1_DPAD_UP', 'P1_DPAD_DOWN', 'P1_DPAD_LEFT', 'P1_DPAD_RIGHT',
        'P1_START', 'P1_SELECT',
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

def scan_roms_directory(mame_dir: str) -> Set[str]:
    """Scan the roms directory for available games with improved path handling"""
    
    roms_dir = os.path.join(mame_dir, "roms")
    available_roms = set()
    
    if not os.path.exists(roms_dir):
        print(f"ROMs directory not found: {roms_dir}")
        return available_roms

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
            available_roms.add(base_name)
            rom_count += 1
            
            if rom_count <= 5:  # Print first 5 ROMs as sample
                print(f"Found ROM: {base_name}")
        
        print(f"Total ROMs found: {len(available_roms)}")
        if len(available_roms) > 0:
            print(f"Sample of available ROMs: {list(available_roms)[:5]}")
        else:
            print("WARNING: No ROMs were found!")
    except Exception as e:
        print(f"Error scanning ROMs directory: {e}")
    
    return available_roms

# ============================================================================
# HELPER FUNCTIONS FOR DATA ANALYSIS
# ============================================================================

def identify_generic_controls(available_roms: Set[str], gamedata_json: Dict, 
                             parent_lookup: Dict, db_path: str = None, 
                             rom_data_cache: Dict = None) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Identify games that only have generic control names"""
    generic_control_games = []
    missing_control_games = []
    
    # Generic action names that indicate default mappings
    generic_actions = [
        "A Button", "B Button", "X Button", "Y Button", 
        "LB Button", "RB Button", "LT Button", "RT Button",
        "Up", "Down", "Left", "Right"
    ]
    
    for rom_name in sorted(available_roms):
        # First check if game data exists at all
        game_data = get_game_data(rom_name, gamedata_json, parent_lookup, db_path, rom_data_cache)
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

def find_unmatched_roms(available_roms: Set[str], gamedata_json: Dict, 
                       parent_lookup: Dict, db_path: str = None, 
                       rom_data_cache: Dict = None) -> Set[str]:
    """Find ROMs that don't have matching control data"""
    matched_roms = set()
    for rom in available_roms:
        if get_game_data(rom, gamedata_json, parent_lookup, db_path, rom_data_cache):
            matched_roms.add(rom)
    return available_roms - matched_roms

def categorize_roms_by_controls(available_roms: Set[str], gamedata_json: Dict, 
                               parent_lookup: Dict, custom_configs: Dict,
                               db_path: str = None, rom_data_cache: Dict = None) -> Dict[str, List[str]]:
    """Categorize ROMs by their control types for sidebar filtering"""
    
    categories = {
        'with_controls': [],
        'missing_controls': [],
        'custom_config': [],
        'generic_controls': [],
        'clone_roms': [],
        'no_buttons': [],
        'specialized': [],
        'analog': [],
        'multiplayer': [],
        'singleplayer': []
    }
    
    # Generic action names
    generic_actions = [
        "A Button", "B Button", "X Button", "Y Button", 
        "LB Button", "RB Button", "LT Button", "RT Button",
        "Up", "Down", "Left", "Right"
    ]
    
    for rom in sorted(available_roms):
        # Check if ROM is a clone
        if rom in parent_lookup:
            categories['clone_roms'].append(rom)
            
        # Check if ROM has custom config
        if rom in custom_configs:
            categories['custom_config'].append(rom)
        
        # Check if ROM has control data
        game_data = get_game_data(rom, gamedata_json, parent_lookup, db_path, rom_data_cache)
        if game_data:
            categories['with_controls'].append(rom)
            
            # Check player count
            player_count = int(game_data.get('numPlayers', 1))
            if player_count == 1:
                categories['singleplayer'].append(rom)
            elif player_count > 1:
                categories['multiplayer'].append(rom)
            
            # Analyze control types
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
            
            # Check controls for each player
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
            
            # Add to appropriate categories
            if has_specialized:
                categories['specialized'].append(rom)
            if has_analog:
                categories['analog'].append(rom)
            if not has_buttons:
                categories['no_buttons'].append(rom)
                
            # Check if controls are generic
            has_custom_controls = False
            for player in game_data.get('players', []):
                for label in player.get('labels', []):
                    action = label['value']
                    if action not in generic_actions:
                        has_custom_controls = True
                        break
                if has_custom_controls:
                    break
            
            if not has_custom_controls:
                categories['generic_controls'].append(rom)
        else:
            categories['missing_controls'].append(rom)
    
    return categories

# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

def clean_cache_directory(cache_dir: str, max_age_days: int = 7, max_files: int = 100) -> bool:
    """Clean old cache files to prevent unlimited growth"""
    try:
        # Skip if directory doesn't exist
        if not os.path.exists(cache_dir):
            print("No cache directory found. Skipping cleanup.")
            return True
            
        # Get all cache files with their modification times
        cache_files = []
        for filename in os.listdir(cache_dir):
            if filename.endswith('_cache.json'):
                filepath = os.path.join(cache_dir, filename)
                mtime = os.path.getmtime(filepath)
                cache_files.append((filepath, mtime))
        
        if not cache_files:
            print("No cache files found. Skipping cleanup.")
            return True
        
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
                    
        print(f"Cache cleanup complete. Directory: {cache_dir}")
        return True
    except Exception as e:
        print(f"Error cleaning cache: {e}")
        return False

def perform_cache_clear(cache_dir: str, all_files: bool = True, rom_name: str = None) -> bool:
    """Perform the actual cache clearing operation"""
    try:
        if not os.path.exists(cache_dir):
            print("No cache directory found.")
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
            
            print(f"Cleared all cache files: {deleted_count} files deleted")
            return deleted_count > 0
        elif rom_name:
            # Clear cache for specific ROM
            cache_file = os.path.join(cache_dir, f"{rom_name}_cache.json")
            if os.path.exists(cache_file):
                os.remove(cache_file)
                print(f"Cleared cache for ROM: {rom_name}")
                return True
            else:
                print(f"No cache file found for ROM: {rom_name}")
                return False
        
        return False
    except Exception as e:
        print(f"Error clearing cache: {e}")
        return False
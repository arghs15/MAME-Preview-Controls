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
    Load gamedata.json from the specified path with improved clone handling
    
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
                    # Store parent reference in the clone data
                    clone_data['parent'] = rom_name
                    parent_lookup[clone_name] = rom_name
                    
                    # IMPORTANT: Add clone to main gamedata for direct lookup
                    if clone_name not in gamedata_json:
                        # Create clone entry that preserves clone's own description
                        clone_entry = {
                            'description': clone_data.get('description', f"{clone_name} (Clone)"),
                            'parent': rom_name,
                            'playercount': clone_data.get('playercount', game_data.get('playercount', '1')),
                            'buttons': clone_data.get('buttons', game_data.get('buttons', '0')),
                            'sticks': clone_data.get('sticks', game_data.get('sticks', '0')),
                            'alternating': clone_data.get('alternating', game_data.get('alternating', False)),
                            # Clone inherits parent's controls unless it has its own
                            'controls': clone_data.get('controls', game_data.get('controls', {}))
                        }
                        gamedata_json[clone_name] = clone_entry
        
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

# Updated sections of mame_data_utils.py to preserve mappings in cache

# 1. Update _convert_gamedata_json_to_standard_format function
def _convert_gamedata_json_to_standard_format(romname: str, game_data: Dict, 
                                            gamedata_json: Dict, parent_lookup: Dict) -> Dict:
    """Convert gamedata.json format to standard game data format - UPDATED to preserve mappings"""
    
    # Pre-allocate result structure
    converted_data = {
        'romname': romname,
        'gamename': game_data.get('description', romname),
        'numPlayers': int(game_data.get('playercount', 1)),
        'alternating': game_data.get('alternating', False),
        'mirrored': False,
        'miscDetails': f"Buttons: {game_data.get('buttons', '?')}, Sticks: {game_data.get('sticks', '?')}",
        'players': [],
        'source': 'gamedata.json'
    }
    
    # PRESERVE MAPPINGS if they exist
    if 'mappings' in game_data and game_data['mappings']:
        converted_data['mappings'] = game_data['mappings']
    
    # Find controls efficiently
    controls = game_data.get('controls')
    if not controls:
        # Try parent controls
        parent_rom = game_data.get('parent') or parent_lookup.get(romname)
        if parent_rom and parent_rom in gamedata_json:
            parent_data = gamedata_json[parent_rom]
            controls = parent_data.get('controls')
            # ALSO GET PARENT MAPPINGS IF CURRENT GAME DOESN'T HAVE THEM
            if not converted_data.get('mappings') and 'mappings' in parent_data:
                converted_data['mappings'] = parent_data.get('mappings', [])
    
    if controls:
        # Pre-allocate lists and get default actions once
        p1_controls = []
        default_actions = get_default_control_actions()
        
        # Control types we care about (pre-defined for efficiency)
        valid_control_types = [
            'JOYSTICK', 'BUTTON', 'PEDAL', 'AD_STICK', 'DIAL', 'PADDLE', 
            'TRACKBALL', 'LIGHTGUN', 'MOUSE', 'POSITIONAL', 'GAMBLE', 'STEER'
        ]
        
        # Single pass through controls
        for control_name, control_data in controls.items():
            # Only process P1 controls and valid types
            if not control_name.startswith('P1_'):
                continue
                
            if not any(control_type in control_name for control_type in valid_control_types):
                continue
            
            # FIXED: Get friendly name efficiently with better fallback handling
            friendly_name = None
            
            # First try to get from control data
            if isinstance(control_data, dict) and 'name' in control_data:
                name_value = control_data.get('name', '').strip()
                if name_value:  # Has custom name
                    friendly_name = name_value
            
            # If no custom name, use default action
            if not friendly_name:
                friendly_name = default_actions.get(control_name)
            
            # If still no name, generate from control name
            if not friendly_name:
                friendly_name = control_name.split('_')[-1].replace('_', ' ').title()
            
            p1_controls.append({
                'name': control_name,
                'value': friendly_name
            })
        
        # Sort once and add to result
        if p1_controls:
            p1_controls.sort(key=lambda x: x['name'])
            converted_data['players'].append({
                'number': 1,
                'numButtons': int(game_data.get('buttons', 1)),  
                'labels': p1_controls
            })
    
    return converted_data

# 2. Update get_game_data_from_db function to include mappings
def get_game_data_from_db(romname: str, db_path: str) -> Optional[Dict]:
    """Get control data from SQLite database with mappings support - UPDATED"""
    
    if not os.path.exists(db_path):
        return None
    
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Updated query to include mappings column
        cursor.execute("""
            SELECT g.rom_name, g.game_name, g.player_count, g.buttons, g.sticks, 
                   g.alternating, g.is_clone, g.parent_rom, g.mappings,
                   c.control_name, c.display_name
            FROM games g
            LEFT JOIN game_controls c ON g.rom_name = c.rom_name
            WHERE g.rom_name = ?
            ORDER BY c.control_name
        """, (romname,))
        
        rows = cursor.fetchall()
        
        if not rows:
            # Try parent lookup if this is a clone
            cursor.execute("""
                SELECT parent_rom FROM games WHERE rom_name = ? AND is_clone = 1
            """, (romname,))
            parent_result = cursor.fetchone()
            
            if parent_result:
                conn.close()
                return get_game_data_from_db(parent_result['parent_rom'], db_path)
            
            conn.close()
            return None
        
        # Process all rows at once
        first_row = rows[0]
        game_data = {
            'romname': romname,
            'gamename': first_row['game_name'],
            'numPlayers': first_row['player_count'],
            'alternating': bool(first_row['alternating']),
            'mirrored': False,
            'miscDetails': f"Buttons: {first_row['buttons']}, Sticks: {first_row['sticks']}",
            'players': [],
            'source': 'gamedata.db'
        }
        
        # ADD MAPPINGS if they exist
        if first_row['mappings']:
            try:
                # Mappings are stored as JSON string in database
                import json
                game_data['mappings'] = json.loads(first_row['mappings'])
            except (json.JSONDecodeError, TypeError):
                # If it's already a list or parsing fails, use as-is
                game_data['mappings'] = first_row['mappings']
        
        # Process controls efficiently in single pass
        p1_controls = []
        p2_controls = []
        
        default_actions = get_default_control_actions()
        
        for row in rows:
            if not row['control_name']:
                continue
                
            control_name = row['control_name']
            display_name = row['display_name']
            
            # Use default if no display name
            if not display_name and control_name in default_actions:
                display_name = default_actions[control_name]
            
            # Generate fallback display name
            if not display_name:
                parts = control_name.split('_')
                if len(parts) > 1:
                    display_name = parts[-1].replace('_', ' ').title()
                else:
                    display_name = control_name
            
            control_entry = {
                'name': control_name,
                'value': display_name
            }
            
            # Add to appropriate player list
            if control_name.startswith('P1_'):
                p1_controls.append(control_entry)
            elif control_name.startswith('P2_'):
                p2_controls.append(control_entry)
        
        # Sort controls once at the end for consistent order
        p1_controls.sort(key=lambda x: x['name'])
        p2_controls.sort(key=lambda x: x['name'])
        
        # Add players if they have controls
        if p1_controls:
            game_data['players'].append({
                'number': 1,
                'numButtons': first_row['buttons'],
                'labels': p1_controls
            })
        
        if p2_controls:
            game_data['players'].append({
                'number': 2,
                'numButtons': first_row['buttons'],
                'labels': p2_controls
            })
        
        conn.close()
        return game_data
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.close()
        return None

# 3. Update build_gamedata_db function to store mappings
def build_gamedata_db(gamedata_json: Dict, db_path: str) -> bool:
    """Build SQLite database from gamedata.json with mappings support - UPDATED"""
    start_time = time.time()
    
    if not gamedata_json:
        print("ERROR: No gamedata available to build database")
        return False
    
    try:
        # Clear any cached connections to the old database
        clear_database_cache()
        
        # Create database connection
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Drop existing tables if they exist (clean slate)
        cursor.execute("DROP TABLE IF EXISTS games")
        cursor.execute("DROP TABLE IF EXISTS game_controls")
        cursor.execute("DROP TABLE IF EXISTS clone_relationships")
        
        # Create tables - UPDATED to include mappings column
        cursor.execute('''
        CREATE TABLE games (
            rom_name TEXT PRIMARY KEY,
            game_name TEXT,
            player_count INTEGER,
            buttons INTEGER,
            sticks INTEGER,
            alternating BOOLEAN,
            is_clone BOOLEAN,
            parent_rom TEXT,
            mappings TEXT
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
        
        # Track processed ROM names to avoid duplicates
        processed_roms = set()
        
        # PASS 1: Process all parent games first
        for rom_name, game_data in gamedata_json.items():
            # Skip if this entry has a 'parent' field (it's a clone)
            if 'parent' in game_data:
                continue
            
            # Skip if already processed
            if rom_name in processed_roms:
                continue
            
            try:
                # Extract basic game properties for parent
                game_name = game_data.get('description', rom_name)
                player_count = int(game_data.get('playercount', 1))
                buttons = int(game_data.get('buttons', 0))
                sticks = int(game_data.get('sticks', 0))
                alternating = 1 if game_data.get('alternating', False) else 0
                is_clone = 0  # Parent entries aren't clones
                parent_rom = None
                
                # HANDLE MAPPINGS - store as JSON string
                mappings_json = None
                if 'mappings' in game_data and game_data['mappings']:
                    import json
                    mappings_json = json.dumps(game_data['mappings'])
                
                # Insert parent game - UPDATED query with mappings
                cursor.execute(
                    "INSERT OR IGNORE INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rom_name, game_name, player_count, buttons, sticks, alternating, is_clone, parent_rom, mappings_json)
                )
                
                if cursor.rowcount > 0:
                    games_inserted += 1
                    processed_roms.add(rom_name)
                
                # Insert parent controls
                if 'controls' in game_data:
                    _insert_controls(cursor, rom_name, game_data['controls'])
                    controls_inserted += len(game_data['controls'])
                    
            except Exception as e:
                continue
        
        # PASS 2: Process all clone games
        for rom_name, game_data in gamedata_json.items():
            # Only process entries that have a 'parent' field (clones)
            if 'parent' not in game_data:
                continue
            
            # Skip if already processed
            if rom_name in processed_roms:
                continue
            
            try:
                parent_rom = game_data['parent']
                
                # Extract clone properties (inherit from parent if not specified)
                clone_game_name = game_data.get('description', rom_name)
                clone_player_count = int(game_data.get('playercount', 1))
                clone_buttons = int(game_data.get('buttons', 0))
                clone_sticks = int(game_data.get('sticks', 0))
                clone_alternating = 1 if game_data.get('alternating', False) else 0
                
                # HANDLE CLONE MAPPINGS - inherit from parent or use own
                mappings_json = None
                if 'mappings' in game_data and game_data['mappings']:
                    import json
                    mappings_json = json.dumps(game_data['mappings'])
                elif parent_rom in gamedata_json and 'mappings' in gamedata_json[parent_rom]:
                    import json
                    mappings_json = json.dumps(gamedata_json[parent_rom]['mappings'])
                
                # Insert clone as a game - UPDATED query with mappings
                cursor.execute(
                    "INSERT OR IGNORE INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rom_name, clone_game_name, clone_player_count, clone_buttons, clone_sticks, 
                    clone_alternating, 1, parent_rom, mappings_json)
                )
                
                if cursor.rowcount > 0:
                    games_inserted += 1
                    processed_roms.add(rom_name)
                    
                    # Add clone relationship
                    cursor.execute(
                        "INSERT OR IGNORE INTO clone_relationships VALUES (?, ?)",
                        (parent_rom, rom_name)
                    )
                    clones_inserted += 1
                    
                    # Insert clone controls
                    if 'controls' in game_data:
                        _insert_controls(cursor, rom_name, game_data['controls'])
                        controls_inserted += len(game_data['controls'])
                        
            except Exception as e:
                continue
        
        # PASS 3: Handle old-style clones (nested under parent's 'clones' key)
        for parent_rom, parent_data in gamedata_json.items():
            if 'parent' in parent_data:  # Skip clones processed above
                continue
                
            if 'clones' in parent_data and isinstance(parent_data['clones'], dict):
                for clone_name, clone_data in parent_data['clones'].items():
                    # Skip if already processed in pass 2
                    if clone_name in processed_roms:
                        continue
                    
                    try:
                        # Extract clone properties (inherit from parent)
                        clone_game_name = clone_data.get('description', clone_name)
                        clone_player_count = int(parent_data.get('playercount', 1))
                        clone_buttons = int(parent_data.get('buttons', 0))
                        clone_sticks = int(parent_data.get('sticks', 0))
                        clone_alternating = 1 if parent_data.get('alternating', False) else 0
                        
                        # HANDLE MAPPINGS for old-style clones
                        mappings_json = None
                        if 'mappings' in clone_data and clone_data['mappings']:
                            import json
                            mappings_json = json.dumps(clone_data['mappings'])
                        elif 'mappings' in parent_data and parent_data['mappings']:
                            import json
                            mappings_json = json.dumps(parent_data['mappings'])
                        
                        # Insert clone as a game - UPDATED query with mappings
                        cursor.execute(
                            "INSERT OR IGNORE INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (clone_name, clone_game_name, clone_player_count, clone_buttons, clone_sticks, 
                            clone_alternating, 1, parent_rom, mappings_json)
                        )
                        
                        if cursor.rowcount > 0:
                            games_inserted += 1
                            processed_roms.add(clone_name)
                            
                            # Add clone relationship
                            cursor.execute(
                                "INSERT OR IGNORE INTO clone_relationships VALUES (?, ?)",
                                (parent_rom, clone_name)
                            )
                            clones_inserted += 1
                            
                            # Clone inherits parent's controls unless it has its own
                            clone_controls = clone_data.get('controls', parent_data.get('controls', {}))
                            if clone_controls:
                                _insert_controls(cursor, clone_name, clone_controls)
                                controls_inserted += len(clone_controls)
                                
                    except Exception as e:
                        continue
        
        # Commit changes and close connection
        conn.commit()
        conn.close()
        
        elapsed_time = time.time() - start_time
        print(f"Database built in {elapsed_time:.2f}s with {games_inserted} games, {controls_inserted} controls, {clones_inserted} clones")
        
        # Clear cache again after building
        clear_database_cache()
        
        return games_inserted > 0
        
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        if 'conn' in locals():
            conn.close()
        clear_database_cache()
        return False
    except Exception as e:
        print(f"ERROR building database: {e}")
        if 'conn' in locals():
            conn.close()
        clear_database_cache()
        return False
    
def get_game_data_from_db_debug(romname: str, db_path: str) -> Optional[Dict]:
    """Debug version of get_game_data_from_db to see what's happening"""
    
    if not os.path.exists(db_path):
        print(f"Database doesn't exist: {db_path}")
        return None
    
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()
        
        # Check if game exists in database
        cursor.execute("SELECT COUNT(*) FROM games WHERE rom_name = ?", (romname,))
        game_count = cursor.fetchone()[0]
        print(f"DEBUG: {romname} - Games table entries: {game_count}")
        
        # Check controls
        cursor.execute("SELECT COUNT(*) FROM game_controls WHERE rom_name = ?", (romname,))
        control_count = cursor.fetchone()[0]
        print(f"DEBUG: {romname} - Control entries: {control_count}")
        
        if control_count > 0:
            cursor.execute("SELECT control_name, display_name FROM game_controls WHERE rom_name = ? LIMIT 5", (romname,))
            sample_controls = cursor.fetchall()
            print(f"DEBUG: {romname} - Sample controls:")
            for control in sample_controls:
                print(f"  {control['control_name']} -> '{control['display_name']}'")
        
        # Single optimized query with JOIN to get all data at once
        cursor.execute("""
            SELECT g.rom_name, g.game_name, g.player_count, g.buttons, g.sticks, 
                   g.alternating, g.is_clone, g.parent_rom,
                   c.control_name, c.display_name
            FROM games g
            LEFT JOIN game_controls c ON g.rom_name = c.rom_name
            WHERE g.rom_name = ?
            ORDER BY c.control_name
        """, (romname,))
        
        rows = cursor.fetchall()
        print(f"DEBUG: {romname} - Query returned {len(rows)} rows")
        
        if not rows:
            # Try parent lookup if this is a clone
            cursor.execute("""
                SELECT parent_rom FROM games WHERE rom_name = ? AND is_clone = 1
            """, (romname,))
            parent_result = cursor.fetchone()
            
            if parent_result:
                print(f"DEBUG: {romname} is a clone of {parent_result['parent_rom']}")
                # Recursively get parent data
                conn.close()
                return get_game_data_from_db_debug(parent_result['parent_rom'], db_path)
            
            print(f"DEBUG: {romname} - No data found in database")
            conn.close()
            return None
        
        # Process all rows at once
        first_row = rows[0]
        game_data = {
            'romname': romname,
            'gamename': first_row['game_name'],
            'numPlayers': first_row['player_count'],
            'alternating': bool(first_row['alternating']),
            'mirrored': False,
            'miscDetails': f"Buttons: {first_row['buttons']}, Sticks: {first_row['sticks']}",
            'players': [],
            'source': 'gamedata.db'
        }
        
        # Process controls efficiently in single pass
        p1_controls = []
        p2_controls = []
        
        default_actions = get_default_control_actions()
        
        controls_processed = 0
        for row in rows:
            if not row['control_name']:  # Skip rows without controls
                continue
                
            control_name = row['control_name']
            display_name = row['display_name']
            
            # Use default if no display name
            if not display_name and control_name in default_actions:
                display_name = default_actions[control_name]
                print(f"DEBUG: Using default for {control_name}: {display_name}")
            
            # Generate fallback display name
            if not display_name:
                parts = control_name.split('_')
                if len(parts) > 1:
                    display_name = parts[-1].replace('_', ' ').title()
                else:
                    display_name = control_name
                print(f"DEBUG: Generated fallback for {control_name}: {display_name}")
            
            control_entry = {
                'name': control_name,
                'value': display_name
            }
            
            # Add to appropriate player list
            if control_name.startswith('P1_'):
                p1_controls.append(control_entry)
                controls_processed += 1
            elif control_name.startswith('P2_'):
                p2_controls.append(control_entry)
                controls_processed += 1
        
        print(f"DEBUG: {romname} - Processed {controls_processed} controls")
        
        # Sort controls once at the end for consistent order
        p1_controls.sort(key=lambda x: x['name'])
        p2_controls.sort(key=lambda x: x['name'])
        
        # Add players if they have controls
        if p1_controls:
            game_data['players'].append({
                'number': 1,
                'numButtons': first_row['buttons'],
                'labels': p1_controls
            })
            print(f"DEBUG: {romname} - Added P1 with {len(p1_controls)} controls")
        
        if p2_controls:
            game_data['players'].append({
                'number': 2,
                'numButtons': first_row['buttons'],
                'labels': p2_controls
            })
            print(f"DEBUG: {romname} - Added P2 with {len(p2_controls)} controls")
        
        if not p1_controls and not p2_controls:
            print(f"DEBUG: {romname} - WARNING: No controls added to players!")
        
        conn.close()
        return game_data
        
    except sqlite3.Error as e:
        print(f"Database error for {romname}: {e}")
        if conn:
            conn.close()
        return None

def _insert_controls(cursor, rom_name: str, controls_dict: Dict):
    """Helper method to insert controls into the database"""
    
    default_actions = get_default_control_actions()
    
    for control_name, control_data in controls_dict.items():
        display_name = ""
        
        # Handle different control_data formats
        if isinstance(control_data, dict):
            display_name = control_data.get('name', '').strip()
        elif isinstance(control_data, str):
            display_name = control_data.strip()
        
        # Use default action if no display name
        if not display_name and control_name in default_actions:
            display_name = default_actions[control_name]
        
        # Generate from control name if still no display name
        if not display_name:
            parts = control_name.split('_')
            if len(parts) > 1:
                display_name = parts[-1].replace('_', ' ').title()
            else:
                display_name = control_name
        
        # Always insert the control
        try:
            cursor.execute(
                "INSERT INTO game_controls (rom_name, control_name, display_name) VALUES (?, ?, ?)",
                (rom_name, control_name, display_name)
            )
        except Exception:
            pass  # Skip errors silently

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

# Global connection cache to avoid repeated database connections
_db_connection_cache = {}

# 2. Update get_game_data_from_db function to include mappings
def get_game_data_from_db(romname: str, db_path: str) -> Optional[Dict]:
    """Get control data from SQLite database with mappings support - UPDATED"""
    
    if not os.path.exists(db_path):
        return None
    
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Updated query to include mappings column
        cursor.execute("""
            SELECT g.rom_name, g.game_name, g.player_count, g.buttons, g.sticks, 
                   g.alternating, g.is_clone, g.parent_rom, g.mappings,
                   c.control_name, c.display_name
            FROM games g
            LEFT JOIN game_controls c ON g.rom_name = c.rom_name
            WHERE g.rom_name = ?
            ORDER BY c.control_name
        """, (romname,))
        
        rows = cursor.fetchall()
        
        if not rows:
            # Try parent lookup if this is a clone
            cursor.execute("""
                SELECT parent_rom FROM games WHERE rom_name = ? AND is_clone = 1
            """, (romname,))
            parent_result = cursor.fetchone()
            
            if parent_result:
                conn.close()
                return get_game_data_from_db(parent_result['parent_rom'], db_path)
            
            conn.close()
            return None
        
        # Process all rows at once
        first_row = rows[0]
        game_data = {
            'romname': romname,
            'gamename': first_row['game_name'],
            'numPlayers': first_row['player_count'],
            'alternating': bool(first_row['alternating']),
            'mirrored': False,
            'miscDetails': f"Buttons: {first_row['buttons']}, Sticks: {first_row['sticks']}",
            'players': [],
            'source': 'gamedata.db'
        }
        
        # ADD MAPPINGS if they exist
        if first_row['mappings']:
            try:
                # Mappings are stored as JSON string in database
                import json
                game_data['mappings'] = json.loads(first_row['mappings'])
            except (json.JSONDecodeError, TypeError):
                # If it's already a list or parsing fails, use as-is
                game_data['mappings'] = first_row['mappings']
        
        # Process controls efficiently in single pass
        p1_controls = []
        p2_controls = []
        
        default_actions = get_default_control_actions()
        
        for row in rows:
            if not row['control_name']:
                continue
                
            control_name = row['control_name']
            display_name = row['display_name']
            
            # Use default if no display name
            if not display_name and control_name in default_actions:
                display_name = default_actions[control_name]
            
            # Generate fallback display name
            if not display_name:
                parts = control_name.split('_')
                if len(parts) > 1:
                    display_name = parts[-1].replace('_', ' ').title()
                else:
                    display_name = control_name
            
            control_entry = {
                'name': control_name,
                'value': display_name
            }
            
            # Add to appropriate player list
            if control_name.startswith('P1_'):
                p1_controls.append(control_entry)
            elif control_name.startswith('P2_'):
                p2_controls.append(control_entry)
        
        # Sort controls once at the end for consistent order
        p1_controls.sort(key=lambda x: x['name'])
        p2_controls.sort(key=lambda x: x['name'])
        
        # Add players if they have controls
        if p1_controls:
            game_data['players'].append({
                'number': 1,
                'numButtons': first_row['buttons'],
                'labels': p1_controls
            })
        
        if p2_controls:
            game_data['players'].append({
                'number': 2,
                'numButtons': first_row['buttons'],
                'labels': p2_controls
            })
        
        conn.close()
        return game_data
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.close()
        return None

# Also UPDATE the cleanup_database_connections function:

def cleanup_database_connections():
    """Clean up cached database connections - UPDATED"""
    global _db_connection_cache
    
    for conn in _db_connection_cache.values():
        try:
            conn.close()
        except:
            pass
    _db_connection_cache.clear()
    print("Cleaned up database connections")

# ADD this new function to force cache clearing when database is rebuilt:

def clear_database_cache():
    """Force clear database connection cache - call this after rebuilding database"""
    global _db_connection_cache
    
    for conn in _db_connection_cache.values():
        try:
            conn.close()
        except:
            pass
    _db_connection_cache.clear()
    print("Forced database connection cache clear")
    
def get_game_data(romname: str, gamedata_json: Dict, parent_lookup: Dict, 
                  db_path: str = None, rom_data_cache: Dict = None) -> Optional[Dict]:
    """
    Get game data with optimized caching and single database hit - NO DEBUG
    """
    # Always check cache first (fastest path)
    if rom_data_cache and romname in rom_data_cache:
        return rom_data_cache[romname]
    
    result = None
    
    # Try database first if available (single optimized query)
    if db_path and os.path.exists(db_path):
        result = get_game_data_from_db(romname, db_path)
        if result:
            # Cache immediately and return
            if rom_data_cache is not None:
                rom_data_cache[romname] = result
            return result
    
    # Fallback to JSON lookup (silently, no debug messages)
    if romname in gamedata_json:
        result = _convert_gamedata_json_to_standard_format(
            romname, gamedata_json[romname], gamedata_json, parent_lookup
        )
    elif romname in parent_lookup:
        # Try parent lookup
        parent_rom = parent_lookup[romname]
        if parent_rom in gamedata_json:
            result = _convert_gamedata_json_to_standard_format(
                parent_rom, gamedata_json[parent_rom], gamedata_json, parent_lookup
            )
            if result:
                # Update with clone info
                result['romname'] = romname
                if romname in gamedata_json:
                    result['gamename'] = gamedata_json[romname].get('description', f"{romname} (Clone)")
    
    # Cache the result if found
    if result and rom_data_cache is not None:
        rom_data_cache[romname] = result
        
    return result

# 1. Update _convert_gamedata_json_to_standard_format function
def _convert_gamedata_json_to_standard_format(romname: str, game_data: Dict, 
                                            gamedata_json: Dict, parent_lookup: Dict) -> Dict:
    """Convert gamedata.json format to standard game data format - UPDATED to preserve mappings"""
    
    # Pre-allocate result structure
    converted_data = {
        'romname': romname,
        'gamename': game_data.get('description', romname),
        'numPlayers': int(game_data.get('playercount', 1)),
        'alternating': game_data.get('alternating', False),
        'mirrored': False,
        'miscDetails': f"Buttons: {game_data.get('buttons', '?')}, Sticks: {game_data.get('sticks', '?')}",
        'players': [],
        'source': 'gamedata.json'
    }
    
    # PRESERVE MAPPINGS if they exist
    if 'mappings' in game_data and game_data['mappings']:
        converted_data['mappings'] = game_data['mappings']
    
    # Find controls efficiently
    controls = game_data.get('controls')
    if not controls:
        # Try parent controls
        parent_rom = game_data.get('parent') or parent_lookup.get(romname)
        if parent_rom and parent_rom in gamedata_json:
            parent_data = gamedata_json[parent_rom]
            controls = parent_data.get('controls')
            # ALSO GET PARENT MAPPINGS IF CURRENT GAME DOESN'T HAVE THEM
            if not converted_data.get('mappings') and 'mappings' in parent_data:
                converted_data['mappings'] = parent_data.get('mappings', [])
    
    if controls:
        # Pre-allocate lists and get default actions once
        p1_controls = []
        default_actions = get_default_control_actions()
        
        # Control types we care about (pre-defined for efficiency)
        valid_control_types = [
            'JOYSTICK', 'BUTTON', 'PEDAL', 'AD_STICK', 'DIAL', 'PADDLE', 
            'TRACKBALL', 'LIGHTGUN', 'MOUSE', 'POSITIONAL', 'GAMBLE', 'STEER'
        ]
        
        # Single pass through controls
        for control_name, control_data in controls.items():
            # Only process P1 controls and valid types
            if not control_name.startswith('P1_'):
                continue
                
            if not any(control_type in control_name for control_type in valid_control_types):
                continue
            
            # FIXED: Get friendly name efficiently with better fallback handling
            friendly_name = None
            
            # First try to get from control data
            if isinstance(control_data, dict) and 'name' in control_data:
                name_value = control_data.get('name', '').strip()
                if name_value:  # Has custom name
                    friendly_name = name_value
            
            # If no custom name, use default action
            if not friendly_name:
                friendly_name = default_actions.get(control_name)
            
            # If still no name, generate from control name
            if not friendly_name:
                friendly_name = control_name.split('_')[-1].replace('_', ' ').title()
            
            p1_controls.append({
                'name': control_name,
                'value': friendly_name
            })
        
        # Sort once and add to result
        if p1_controls:
            p1_controls.sort(key=lambda x: x['name'])
            converted_data['players'].append({
                'number': 1,
                'numButtons': int(game_data.get('buttons', 1)),  
                'labels': p1_controls
            })
    
    return converted_data

# Fix 1: Enhanced get_default_control_actions to include all specialized controls
def get_default_control_actions() -> Dict[str, str]:
    """Get default control action mappings - ENHANCED with all specialized controls"""
    return {
        # Standard joystick directions
        'P1_JOYSTICK_UP': 'Up',
        'P1_JOYSTICK_DOWN': 'Down',
        'P1_JOYSTICK_LEFT': 'Left',
        'P1_JOYSTICK_RIGHT': 'Right',
        'P2_JOYSTICK_UP': 'Up',
        'P2_JOYSTICK_DOWN': 'Down',
        'P2_JOYSTICK_LEFT': 'Left',
        'P2_JOYSTICK_RIGHT': 'Right',
        
        # Standard buttons - extended to 12 buttons
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
        'P1_BUTTON11': 'Button 11',
        'P1_BUTTON12': 'Button 12',
        
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
        'P2_BUTTON11': 'Button 11',
        'P2_BUTTON12': 'Button 12',
        
        # Specialized controls - EXPANDED to include all the ones in your example
        'P1_PEDAL': 'Accelerator Pedal',
        'P1_PEDAL2': 'Brake Pedal',  
        'P1_AD_STICK_X': 'Steering Left/Right',
        'P1_AD_STICK_Y': 'Lean Forward/Back',
        'P1_AD_STICK_Z': 'Throttle Control',
        'P1_DIAL': 'Rotary Dial',
        'P1_DIAL_V': 'Vertical Dial',
        'P1_PADDLE': 'Paddle Controller',  # This was missing!
        'P1_TRACKBALL_X': 'Trackball X-Axis',
        'P1_TRACKBALL_Y': 'Trackball Y-Axis',
        'P1_MOUSE_X': 'Mouse X-Axis',
        'P1_MOUSE_Y': 'Mouse Y-Axis',
        'P1_LIGHTGUN_X': 'Light Gun X-Axis',
        'P1_LIGHTGUN_Y': 'Light Gun Y-Axis',
        'P1_POSITIONAL': 'Positional Control',
        'P1_GAMBLE_HIGH': 'Gamble High',
        'P1_GAMBLE_LOW': 'Gamble Low',
        
        # Player 2 specialized controls
        'P2_PEDAL': 'Accelerator Pedal',
        'P2_PEDAL2': 'Brake Pedal',
        'P2_AD_STICK_X': 'Steering Left/Right',
        'P2_AD_STICK_Y': 'Lean Forward/Back',
        'P2_AD_STICK_Z': 'Throttle Control',
        'P2_DIAL': 'Rotary Dial',
        'P2_DIAL_V': 'Vertical Dial',
        'P2_PADDLE': 'Paddle Controller',
        'P2_TRACKBALL_X': 'Trackball X-Axis',
        'P2_TRACKBALL_Y': 'Trackball Y-Axis',
        
        # System controls
        'P1_START': 'Start Button',
        'P1_SELECT': 'Select/Coin Button',
        'P2_START': 'Start Button',
        'P2_SELECT': 'Select/Coin Button',
        
        # Additional specialized controls
        'P1_STEER': 'Steering Wheel',
        'P2_STEER': 'Steering Wheel',
        
        # Right stick controls
        'P1_JOYSTICKRIGHT_UP': 'Right Stick Up',
        'P1_JOYSTICKRIGHT_DOWN': 'Right Stick Down',
        'P1_JOYSTICKRIGHT_LEFT': 'Right Stick Left',
        'P1_JOYSTICKRIGHT_RIGHT': 'Right Stick Right',
        
        # D-pad controls
        'P1_DPAD_UP': 'D-Pad Up',
        'P1_DPAD_DOWN': 'D-Pad Down',
        'P1_DPAD_LEFT': 'D-Pad Left',
        'P1_DPAD_RIGHT': 'D-Pad Right',
        
        # Additional arcade-specific controls
        'P1_COIN': 'Coin',
        'P1_SERVICE': 'Service Button',
        'SERVICE1': 'Service Button',
        'TEST': 'Test Button',
        'TILT': 'Tilt',
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

def joycode_to_xinput(mapping: str) -> str:
    """Convert JOYCODE to XInput format - UPDATED for latest MAME mappings"""
    xinput_mappings = {
        # Updated button mappings (MAME now uses SELECT/START instead of BUTTON8/9)
        'JOYCODE_1_BUTTON1': 'XINPUT_1_A',
        'JOYCODE_1_BUTTON2': 'XINPUT_1_B',
        'JOYCODE_1_BUTTON3': 'XINPUT_1_X',
        'JOYCODE_1_BUTTON4': 'XINPUT_1_Y',
        'JOYCODE_1_BUTTON5': 'XINPUT_1_SHOULDER_L',
        'JOYCODE_1_BUTTON6': 'XINPUT_1_SHOULDER_R',
        'JOYCODE_1_BUTTON7': 'XINPUT_1_TRIGGER_L',  # Was BUTTON7, now often SLIDER1
        'JOYCODE_1_BUTTON8': 'XINPUT_1_TRIGGER_R',  # Was BUTTON8, now often SLIDER2
        
        # NEW: Modern MAME button names
        'JOYCODE_1_SELECT': 'XINPUT_1_BACK',      # NEW: Replaces BUTTON8
        'JOYCODE_1_START': 'XINPUT_1_START',      # NEW: Replaces BUTTON9
        'JOYCODE_1_BUTTON9': 'XINPUT_1_THUMB_L',
        'JOYCODE_1_BUTTON10': 'XINPUT_1_THUMB_R',
        
        # UPDATED: Hat/D-pad mappings (HAT1 instead of DPAD)
        'JOYCODE_1_HAT1UP': 'XINPUT_1_DPAD_UP',         # NEW: Replaces HATUP
        'JOYCODE_1_HAT1DOWN': 'XINPUT_1_DPAD_DOWN',     # NEW: Replaces HATDOWN
        'JOYCODE_1_HAT1LEFT': 'XINPUT_1_DPAD_LEFT',     # NEW: Replaces HATLEFT
        'JOYCODE_1_HAT1RIGHT': 'XINPUT_1_DPAD_RIGHT',   # NEW: Replaces HATRIGHT
        
        # Legacy D-pad mappings (for backward compatibility)
        'JOYCODE_1_HATUP': 'XINPUT_1_DPAD_UP',
        'JOYCODE_1_HATDOWN': 'XINPUT_1_DPAD_DOWN',
        'JOYCODE_1_HATLEFT': 'XINPUT_1_DPAD_LEFT',
        'JOYCODE_1_HATRIGHT': 'XINPUT_1_DPAD_RIGHT',
        
        # UPDATED: Slider/Trigger mappings
        'JOYCODE_1_SLIDER1': 'XINPUT_1_TRIGGER_L',           # Often used for LT
        'JOYCODE_1_SLIDER2': 'XINPUT_1_TRIGGER_R',           # Often used for RT
        'JOYCODE_1_SLIDER1_NEG_SWITCH': 'XINPUT_1_TRIGGER_L',
        'JOYCODE_1_SLIDER2_NEG_SWITCH': 'XINPUT_1_TRIGGER_R',
        'JOYCODE_1_SLIDER2_POS_SWITCH': 'XINPUT_1_TRIGGER_R',
        
        # Legacy Z-axis mappings (for backward compatibility)
        'JOYCODE_1_ZAXIS_NEG_SWITCH': 'XINPUT_1_TRIGGER_L',  # Old name
        'JOYCODE_1_ZAXIS_POS_SWITCH': 'XINPUT_1_TRIGGER_R',  # Old name
        
        # Player 2 mappings with same updates
        'JOYCODE_2_BUTTON1': 'XINPUT_2_A',
        'JOYCODE_2_BUTTON2': 'XINPUT_2_B',
        'JOYCODE_2_BUTTON3': 'XINPUT_2_X',
        'JOYCODE_2_BUTTON4': 'XINPUT_2_Y',
        'JOYCODE_2_BUTTON5': 'XINPUT_2_SHOULDER_L',
        'JOYCODE_2_BUTTON6': 'XINPUT_2_SHOULDER_R',
        'JOYCODE_2_SELECT': 'XINPUT_2_BACK',      # NEW
        'JOYCODE_2_START': 'XINPUT_2_START',      # NEW
        'JOYCODE_2_BUTTON9': 'XINPUT_2_THUMB_L',
        'JOYCODE_2_BUTTON10': 'XINPUT_2_THUMB_R',
        
        # Player 2 D-pad (new HAT1 names)
        'JOYCODE_2_HAT1UP': 'XINPUT_2_DPAD_UP',
        'JOYCODE_2_HAT1DOWN': 'XINPUT_2_DPAD_DOWN',
        'JOYCODE_2_HAT1LEFT': 'XINPUT_2_DPAD_LEFT',
        'JOYCODE_2_HAT1RIGHT': 'XINPUT_2_DPAD_RIGHT',
    }
    
    return xinput_mappings.get(mapping, mapping)

def joycode_to_dinput(mapping: str) -> str:
    """Convert JOYCODE to DInput format - UPDATED for latest MAME mappings"""
    dinput_mappings = {
        # Standard button mappings (0-based for DInput)
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
        
        # NEW: Modern MAME button names
        'JOYCODE_1_SELECT': 'DINPUT_1_BUTTON7',    # NEW: Maps to button 7 (0-based)
        'JOYCODE_1_START': 'DINPUT_1_BUTTON8',     # NEW: Maps to button 8 (0-based)
        
        # UPDATED: HAT1 mappings (new in latest MAME)
        'JOYCODE_1_HAT1UP': 'DINPUT_1_POV_UP',       # NEW: Replaces HATUP
        'JOYCODE_1_HAT1DOWN': 'DINPUT_1_POV_DOWN',   # NEW: Replaces HATDOWN  
        'JOYCODE_1_HAT1LEFT': 'DINPUT_1_POV_LEFT',   # NEW: Replaces HATLEFT
        'JOYCODE_1_HAT1RIGHT': 'DINPUT_1_POV_RIGHT', # NEW: Replaces HATRIGHT
        
        # Legacy HAT mappings (for backward compatibility)
        'JOYCODE_1_HATUP': 'DINPUT_1_POV_UP',
        'JOYCODE_1_HATDOWN': 'DINPUT_1_POV_DOWN',
        'JOYCODE_1_HATLEFT': 'DINPUT_1_POV_LEFT',
        'JOYCODE_1_HATRIGHT': 'DINPUT_1_POV_RIGHT',
        
        # UPDATED: Slider mappings (SLIDER2 instead of ZAXIS)
        'JOYCODE_1_SLIDER1': 'DINPUT_1_SLIDER0',           # Often used for triggers
        'JOYCODE_1_SLIDER2': 'DINPUT_1_SLIDER1',           # NEW: Replaces ZAXIS
        'JOYCODE_1_SLIDER1_NEG_SWITCH': 'DINPUT_1_SLIDER0_NEG',
        'JOYCODE_1_SLIDER2_NEG_SWITCH': 'DINPUT_1_SLIDER1_NEG',  # NEW
        'JOYCODE_1_SLIDER2_POS_SWITCH': 'DINPUT_1_SLIDER1_POS',  # NEW
        
        # Legacy Z-axis mappings (for backward compatibility)
        'JOYCODE_1_ZAXIS_NEG_SWITCH': 'DINPUT_1_ZAXIS_NEG',  # Old name
        'JOYCODE_1_ZAXIS_POS_SWITCH': 'DINPUT_1_ZAXIS_POS',  # Old name
        
        # Player 2 mappings with same updates
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
        
        # Player 2 NEW button names
        'JOYCODE_2_SELECT': 'DINPUT_2_BUTTON7',    # NEW
        'JOYCODE_2_START': 'DINPUT_2_BUTTON8',     # NEW
        
        # Player 2 HAT1 mappings
        'JOYCODE_2_HAT1UP': 'DINPUT_2_POV_UP',     # NEW
        'JOYCODE_2_HAT1DOWN': 'DINPUT_2_POV_DOWN', # NEW
        'JOYCODE_2_HAT1LEFT': 'DINPUT_2_POV_LEFT', # NEW
        'JOYCODE_2_HAT1RIGHT': 'DINPUT_2_POV_RIGHT', # NEW
    }
    
    return dinput_mappings.get(mapping, mapping)

def xinput_to_joycode(mapping: str) -> str:
    """Convert XInput to JOYCODE format - UPDATED for latest MAME mappings"""
    reverse_mappings = {
        # Standard button mappings
        'XINPUT_1_A': 'JOYCODE_1_BUTTON1',
        'XINPUT_1_B': 'JOYCODE_1_BUTTON2',
        'XINPUT_1_X': 'JOYCODE_1_BUTTON3',
        'XINPUT_1_Y': 'JOYCODE_1_BUTTON4',
        'XINPUT_1_SHOULDER_L': 'JOYCODE_1_BUTTON5',
        'XINPUT_1_SHOULDER_R': 'JOYCODE_1_BUTTON6',
        
        # UPDATED: Prefer new MAME names for SELECT/START
        'XINPUT_1_BACK': 'JOYCODE_1_SELECT',      # NEW: Use SELECT instead of BUTTON8
        'XINPUT_1_START': 'JOYCODE_1_START',      # NEW: Use START instead of BUTTON9
        'XINPUT_1_THUMB_L': 'JOYCODE_1_BUTTON9',
        'XINPUT_1_THUMB_R': 'JOYCODE_1_BUTTON10',
        
        # UPDATED: Prefer new HAT1 names for D-pad
        'XINPUT_1_DPAD_UP': 'JOYCODE_1_HAT1UP',       # NEW: Use HAT1UP instead of HATUP
        'XINPUT_1_DPAD_DOWN': 'JOYCODE_1_HAT1DOWN',   # NEW: Use HAT1DOWN instead of HATDOWN
        'XINPUT_1_DPAD_LEFT': 'JOYCODE_1_HAT1LEFT',   # NEW: Use HAT1LEFT instead of HATLEFT
        'XINPUT_1_DPAD_RIGHT': 'JOYCODE_1_HAT1RIGHT', # NEW: Use HAT1RIGHT instead of HATRIGHT
        
        # UPDATED: Prefer SLIDER2 for triggers
        'XINPUT_1_TRIGGER_L': 'JOYCODE_1_SLIDER1',     # Often mapped to SLIDER1
        'XINPUT_1_TRIGGER_R': 'JOYCODE_1_SLIDER2',     # NEW: Use SLIDER2 instead of ZAXIS
        
        # Player 2 mappings
        'XINPUT_2_A': 'JOYCODE_2_BUTTON1',
        'XINPUT_2_B': 'JOYCODE_2_BUTTON2',
        'XINPUT_2_X': 'JOYCODE_2_BUTTON3',
        'XINPUT_2_Y': 'JOYCODE_2_BUTTON4',
        'XINPUT_2_SHOULDER_L': 'JOYCODE_2_BUTTON5',
        'XINPUT_2_SHOULDER_R': 'JOYCODE_2_BUTTON6',
        'XINPUT_2_BACK': 'JOYCODE_2_SELECT',      # NEW
        'XINPUT_2_START': 'JOYCODE_2_START',      # NEW
        'XINPUT_2_THUMB_L': 'JOYCODE_2_BUTTON9',
        'XINPUT_2_THUMB_R': 'JOYCODE_2_BUTTON10',
        
        # Player 2 D-pad
        'XINPUT_2_DPAD_UP': 'JOYCODE_2_HAT1UP',       # NEW
        'XINPUT_2_DPAD_DOWN': 'JOYCODE_2_HAT1DOWN',   # NEW
        'XINPUT_2_DPAD_LEFT': 'JOYCODE_2_HAT1LEFT',   # NEW
        'XINPUT_2_DPAD_RIGHT': 'JOYCODE_2_HAT1RIGHT', # NEW
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
    """Convert DInput to JOYCODE format - UPDATED for latest MAME mappings"""
    reverse_mappings = {
        # Standard button mappings (convert from 0-based to 1-based)
        'DINPUT_1_BUTTON0': 'JOYCODE_1_BUTTON1',
        'DINPUT_1_BUTTON1': 'JOYCODE_1_BUTTON2',
        'DINPUT_1_BUTTON2': 'JOYCODE_1_BUTTON3',
        'DINPUT_1_BUTTON3': 'JOYCODE_1_BUTTON4',
        'DINPUT_1_BUTTON4': 'JOYCODE_1_BUTTON5',
        'DINPUT_1_BUTTON5': 'JOYCODE_1_BUTTON6',
        'DINPUT_1_BUTTON6': 'JOYCODE_1_BUTTON7',
        
        # UPDATED: Prefer new MAME names
        'DINPUT_1_BUTTON7': 'JOYCODE_1_SELECT',    # NEW: Use SELECT name
        'DINPUT_1_BUTTON8': 'JOYCODE_1_START',     # NEW: Use START name
        'DINPUT_1_BUTTON8': 'JOYCODE_1_BUTTON9',
        'DINPUT_1_BUTTON9': 'JOYCODE_1_BUTTON10',
        
        # UPDATED: Prefer new HAT1 names
        'DINPUT_1_POV_UP': 'JOYCODE_1_HAT1UP',       # NEW
        'DINPUT_1_POV_DOWN': 'JOYCODE_1_HAT1DOWN',   # NEW
        'DINPUT_1_POV_LEFT': 'JOYCODE_1_HAT1LEFT',   # NEW
        'DINPUT_1_POV_RIGHT': 'JOYCODE_1_HAT1RIGHT', # NEW
        
        # UPDATED: Prefer SLIDER2 names
        'DINPUT_1_SLIDER0': 'JOYCODE_1_SLIDER1',
        'DINPUT_1_SLIDER1': 'JOYCODE_1_SLIDER2',     # NEW: Map to SLIDER2
        'DINPUT_1_SLIDER0_NEG': 'JOYCODE_1_SLIDER1_NEG_SWITCH',
        'DINPUT_1_SLIDER1_NEG': 'JOYCODE_1_SLIDER2_NEG_SWITCH', # NEW
        'DINPUT_1_SLIDER1_POS': 'JOYCODE_1_SLIDER2_POS_SWITCH', # NEW
        
        # Player 2 mappings
        'DINPUT_2_BUTTON0': 'JOYCODE_2_BUTTON1',
        'DINPUT_2_BUTTON1': 'JOYCODE_2_BUTTON2',
        'DINPUT_2_BUTTON2': 'JOYCODE_2_BUTTON3',
        'DINPUT_2_BUTTON3': 'JOYCODE_2_BUTTON4',
        'DINPUT_2_BUTTON4': 'JOYCODE_2_BUTTON5',
        'DINPUT_2_BUTTON5': 'JOYCODE_2_BUTTON6',
        'DINPUT_2_BUTTON6': 'JOYCODE_2_BUTTON7',
        'DINPUT_2_BUTTON7': 'JOYCODE_2_SELECT',    # NEW
        'DINPUT_2_BUTTON8': 'JOYCODE_2_START',     # NEW
        
        # Player 2 POV/HAT
        'DINPUT_2_POV_UP': 'JOYCODE_2_HAT1UP',     # NEW
        'DINPUT_2_POV_DOWN': 'JOYCODE_2_HAT1DOWN', # NEW
        'DINPUT_2_POV_LEFT': 'JOYCODE_2_HAT1LEFT', # NEW
        'DINPUT_2_POV_RIGHT': 'JOYCODE_2_HAT1RIGHT', # NEW
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

def format_keycode_display(mapping: str, friendly_names: bool = True) -> str:
    """Format KEYCODE mapping string for display - with friendly/raw toggle"""
    if not mapping or not mapping.startswith("KEYCODE_"):
        return mapping
    
    # If friendly_names is False, return the raw mapping
    if not friendly_names:
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


# Update the get_xinput_directional_alternatives function in mame_data_utils.py

def get_xinput_directional_alternatives(control_name: str) -> str:
    """
    Get XInput alternatives for directional controls showing both D-pad and analog options
    ENHANCED: Now includes P1_JOYSTICKLEFT_* controls and specialized controls
    Returns a formatted string with multiple XInput options
    """
    directional_mappings = {
        # Standard P1 Joystick directions - show both D-pad and Left Stick options
        'P1_JOYSTICK_UP': 'XINPUT_1_DPAD_UP | XINPUT_1_LEFTY_NEG',
        'P1_JOYSTICK_DOWN': 'XINPUT_1_DPAD_DOWN | XINPUT_1_LEFTY_POS', 
        'P1_JOYSTICK_LEFT': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG',
        'P1_JOYSTICK_RIGHT': 'XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        
        # P1 Left Stick directions (MISSING - this is what Black Widow uses!)
        'P1_JOYSTICKLEFT_UP': 'XINPUT_1_DPAD_UP | XINPUT_1_LEFTY_NEG',
        'P1_JOYSTICKLEFT_DOWN': 'XINPUT_1_DPAD_DOWN | XINPUT_1_LEFTY_POS',
        'P1_JOYSTICKLEFT_LEFT': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG',
        'P1_JOYSTICKLEFT_RIGHT': 'XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        
        # P1 Right Stick directions
        'P1_JOYSTICKRIGHT_UP': 'XINPUT_1_RIGHTY_NEG',
        'P1_JOYSTICKRIGHT_DOWN': 'XINPUT_1_RIGHTY_POS',
        'P1_JOYSTICKRIGHT_LEFT': 'XINPUT_1_RIGHTX_NEG', 
        'P1_JOYSTICKRIGHT_RIGHT': 'XINPUT_1_RIGHTX_POS',
        
        # P1 D-pad directions (if explicitly defined)
        'P1_DPAD_UP': 'XINPUT_1_DPAD_UP',
        'P1_DPAD_DOWN': 'XINPUT_1_DPAD_DOWN',
        'P1_DPAD_LEFT': 'XINPUT_1_DPAD_LEFT',
        'P1_DPAD_RIGHT': 'XINPUT_1_DPAD_RIGHT',
        
        # Specialized directional controls
        'P1_AD_STICK_X': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        'P1_AD_STICK_Y': 'XINPUT_1_DPAD_UP | XINPUT_1_LEFTY_NEG | XINPUT_1_DPAD_DOWN | XINPUT_1_LEFTY_POS',
        'P1_AD_STICK_Z': 'XINPUT_1_TRIGGER_L | XINPUT_1_TRIGGER_R',
        
        # Paddle controls (typically left/right movement)
        'P1_PADDLE': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        'P1_PADDLE_V': 'XINPUT_1_DPAD_UP | XINPUT_1_LEFTY_NEG | XINPUT_1_DPAD_DOWN | XINPUT_1_LEFTY_POS',
        
        # Dial controls (rotary, typically left/right)
        'P1_DIAL': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        'P1_DIAL_V': 'XINPUT_1_DPAD_UP | XINPUT_1_LEFTY_NEG | XINPUT_1_DPAD_DOWN | XINPUT_1_LEFTY_POS',
        
        # Trackball (X and Y axes)
        'P1_TRACKBALL_X': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        'P1_TRACKBALL_Y': 'XINPUT_1_DPAD_UP | XINPUT_1_LEFTY_NEG | XINPUT_1_DPAD_DOWN | XINPUT_1_LEFTY_POS',
        
        # Mouse controls
        'P1_MOUSE_X': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        'P1_MOUSE_Y': 'XINPUT_1_DPAD_UP | XINPUT_1_LEFTY_NEG | XINPUT_1_DPAD_DOWN | XINPUT_1_LEFTY_POS',
        
        # Light Gun controls
        'P1_LIGHTGUN_X': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        'P1_LIGHTGUN_Y': 'XINPUT_1_DPAD_UP | XINPUT_1_LEFTY_NEG | XINPUT_1_DPAD_DOWN | XINPUT_1_LEFTY_POS',
        
        # Positional controls
        'P1_POSITIONAL': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        
        # Steering wheel (left/right)
        'P1_STEER': 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS',
        
        # P2 Joystick directions
        'P2_JOYSTICK_UP': 'XINPUT_2_DPAD_UP | XINPUT_2_LEFTY_NEG',
        'P2_JOYSTICK_DOWN': 'XINPUT_2_DPAD_DOWN | XINPUT_2_LEFTY_POS',
        'P2_JOYSTICK_LEFT': 'XINPUT_2_DPAD_LEFT | XINPUT_2_LEFTX_NEG',
        'P2_JOYSTICK_RIGHT': 'XINPUT_2_DPAD_RIGHT | XINPUT_2_LEFTX_POS',
        
        # P2 Left Stick directions
        'P2_JOYSTICKLEFT_UP': 'XINPUT_2_DPAD_UP | XINPUT_2_LEFTY_NEG',
        'P2_JOYSTICKLEFT_DOWN': 'XINPUT_2_DPAD_DOWN | XINPUT_2_LEFTY_POS',
        'P2_JOYSTICKLEFT_LEFT': 'XINPUT_2_DPAD_LEFT | XINPUT_2_LEFTX_NEG',
        'P2_JOYSTICKLEFT_RIGHT': 'XINPUT_2_DPAD_RIGHT | XINPUT_2_LEFTX_POS',
        
        # P2 Right Stick directions  
        'P2_JOYSTICKRIGHT_UP': 'XINPUT_2_RIGHTY_NEG',
        'P2_JOYSTICKRIGHT_DOWN': 'XINPUT_2_RIGHTY_POS',
        'P2_JOYSTICKRIGHT_LEFT': 'XINPUT_2_RIGHTX_NEG',
        'P2_JOYSTICKRIGHT_RIGHT': 'XINPUT_2_RIGHTX_POS',
        
        # P2 Specialized controls
        'P2_AD_STICK_X': 'XINPUT_2_DPAD_LEFT | XINPUT_2_LEFTX_NEG | XINPUT_2_DPAD_RIGHT | XINPUT_2_LEFTX_POS',
        'P2_AD_STICK_Y': 'XINPUT_2_DPAD_UP | XINPUT_2_LEFTY_NEG | XINPUT_2_DPAD_DOWN | XINPUT_2_LEFTY_POS',
        'P2_PADDLE': 'XINPUT_2_DPAD_LEFT | XINPUT_2_LEFTX_NEG | XINPUT_2_DPAD_RIGHT | XINPUT_2_LEFTX_POS',
        'P2_DIAL': 'XINPUT_2_DPAD_LEFT | XINPUT_2_LEFTX_NEG | XINPUT_2_DPAD_RIGHT | XINPUT_2_LEFTX_POS',
        'P2_TRACKBALL_X': 'XINPUT_2_DPAD_LEFT | XINPUT_2_LEFTX_NEG | XINPUT_2_DPAD_RIGHT | XINPUT_2_LEFTX_POS',
        'P2_TRACKBALL_Y': 'XINPUT_2_DPAD_UP | XINPUT_2_LEFTY_NEG | XINPUT_2_DPAD_DOWN | XINPUT_2_LEFTY_POS',
    }
    
    return directional_mappings.get(control_name, '')

# Also update the DInput version
def get_dinput_directional_alternatives(control_name: str) -> str:
    """
    Get DInput alternatives for directional controls with CLEAR, USER-FRIENDLY names
    ENHANCED: Now includes P1_JOYSTICKLEFT_* controls and specialized controls
    """
    directional_mappings = {
        # P1 Joystick directions - show both D-Pad and Stick options with clear names
        'P1_JOYSTICK_UP': 'D-Pad Up | Left Stick Up',
        'P1_JOYSTICK_DOWN': 'D-Pad Down | Left Stick Down', 
        'P1_JOYSTICK_LEFT': 'D-Pad Left | Left Stick Left',
        'P1_JOYSTICK_RIGHT': 'D-Pad Right | Left Stick Right',
        
        # P1 Left Stick directions (MISSING - this is what Black Widow uses!)
        'P1_JOYSTICKLEFT_UP': 'D-Pad Up | Left Stick Up',
        'P1_JOYSTICKLEFT_DOWN': 'D-Pad Down | Left Stick Down',
        'P1_JOYSTICKLEFT_LEFT': 'D-Pad Left | Left Stick Left',
        'P1_JOYSTICKLEFT_RIGHT': 'D-Pad Right | Left Stick Right',
        
        # P1 Right Stick directions (if they exist)
        'P1_JOYSTICKRIGHT_UP': 'Right Stick Up',
        'P1_JOYSTICKRIGHT_DOWN': 'Right Stick Down',
        'P1_JOYSTICKRIGHT_LEFT': 'Right Stick Left', 
        'P1_JOYSTICKRIGHT_RIGHT': 'Right Stick Right',
        
        # Specialized directional controls with friendly names
        'P1_AD_STICK_X': 'D-Pad Left/Right | Left Stick Left/Right',
        'P1_AD_STICK_Y': 'D-Pad Up/Down | Left Stick Up/Down',
        'P1_AD_STICK_Z': 'Left Trigger | Right Trigger',
        
        # Paddle controls
        'P1_PADDLE': 'D-Pad Left/Right | Left Stick Left/Right',
        'P1_PADDLE_V': 'D-Pad Up/Down | Left Stick Up/Down',
        
        # Dial controls
        'P1_DIAL': 'D-Pad Left/Right | Left Stick Left/Right',
        'P1_DIAL_V': 'D-Pad Up/Down | Left Stick Up/Down',
        
        # Trackball
        'P1_TRACKBALL_X': 'D-Pad Left/Right | Left Stick Left/Right',
        'P1_TRACKBALL_Y': 'D-Pad Up/Down | Left Stick Up/Down',
        
        # Mouse controls
        'P1_MOUSE_X': 'D-Pad Left/Right | Left Stick Left/Right',
        'P1_MOUSE_Y': 'D-Pad Up/Down | Left Stick Up/Down',
        
        # Light Gun
        'P1_LIGHTGUN_X': 'D-Pad Left/Right | Left Stick Left/Right',
        'P1_LIGHTGUN_Y': 'D-Pad Up/Down | Left Stick Up/Down',
        
        # Positional and Steering
        'P1_POSITIONAL': 'D-Pad Left/Right | Left Stick Left/Right',
        'P1_STEER': 'D-Pad Left/Right | Left Stick Left/Right',
        
        # P2 Joystick directions
        'P2_JOYSTICK_UP': 'D-Pad Up | Left Stick Up',
        'P2_JOYSTICK_DOWN': 'D-Pad Down | Left Stick Down',
        'P2_JOYSTICK_LEFT': 'D-Pad Left | Left Stick Left',
        'P2_JOYSTICK_RIGHT': 'D-Pad Right | Left Stick Right',
        
        # P2 Left Stick directions
        'P2_JOYSTICKLEFT_UP': 'D-Pad Up | Left Stick Up',
        'P2_JOYSTICKLEFT_DOWN': 'D-Pad Down | Left Stick Down',
        'P2_JOYSTICKLEFT_LEFT': 'D-Pad Left | Left Stick Left',
        'P2_JOYSTICKLEFT_RIGHT': 'D-Pad Right | Left Stick Right',
        
        # P2 Right Stick directions
        'P2_JOYSTICKRIGHT_UP': 'Right Stick Up',
        'P2_JOYSTICKRIGHT_DOWN': 'Right Stick Down',
        'P2_JOYSTICKRIGHT_LEFT': 'Right Stick Left',
        'P2_JOYSTICKRIGHT_RIGHT': 'Right Stick Right',
        
        # P2 Specialized controls
        'P2_AD_STICK_X': 'D-Pad Left/Right | Left Stick Left/Right',
        'P2_AD_STICK_Y': 'D-Pad Up/Down | Left Stick Up/Down',
        'P2_PADDLE': 'D-Pad Left/Right | Left Stick Left/Right',
        'P2_DIAL': 'D-Pad Left/Right | Left Stick Left/Right',
        'P2_TRACKBALL_X': 'D-Pad Left/Right | Left Stick Left/Right',
        'P2_TRACKBALL_Y': 'D-Pad Up/Down | Left Stick Up/Down',
    }
    
    return directional_mappings.get(control_name, '')

def get_friendly_xinput_alternatives(xinput_mapping: str) -> str:
    """
    Convert XInput mapping with alternatives to friendly display names
    ENHANCED: Better handling of multiple alternatives for specialized controls
    Example: 'XINPUT_1_DPAD_LEFT | XINPUT_1_LEFTX_NEG | XINPUT_1_DPAD_RIGHT | XINPUT_1_LEFTX_POS' 
             -> 'D-Pad Left/Right | Left Stick Left/Right'
    """
    if '|' not in xinput_mapping:
        # Single mapping, use existing function
        return get_friendly_xinput_name(xinput_mapping)
    
    # Multiple mappings separated by |
    parts = [part.strip() for part in xinput_mapping.split('|')]
    
    # For specialized controls with 4 parts (left/right or up/down pairs)
    if len(parts) == 4:
        # Group related parts together
        if 'DPAD_LEFT' in parts[0] and 'LEFTX_NEG' in parts[1] and 'DPAD_RIGHT' in parts[2] and 'LEFTX_POS' in parts[3]:
            return 'D-Pad Left/Right | Left Stick Left/Right'
        elif 'DPAD_UP' in parts[0] and 'LEFTY_NEG' in parts[1] and 'DPAD_DOWN' in parts[2] and 'LEFTY_POS' in parts[3]:
            return 'D-Pad Up/Down | Left Stick Up/Down'
        elif 'TRIGGER_L' in parts[0] and 'TRIGGER_R' in parts[1]:
            return 'Left Trigger | Right Trigger'
    
    # For regular 2-part alternatives
    elif len(parts) == 2:
        friendly_parts = []
        for part in parts:
            friendly_name = get_friendly_xinput_name(part)
            friendly_parts.append(friendly_name)
        return ' | '.join(friendly_parts)
    
    # Fallback: convert each part individually
    friendly_parts = []
    for part in parts:
        friendly_name = get_friendly_xinput_name(part)
        friendly_parts.append(friendly_name)
    
    return ' | '.join(friendly_parts)

def get_friendly_xinput_name(mapping: str, friendly_names: bool = True) -> str:
    """Convert an XINPUT mapping code into a human-friendly button/stick name - with toggle"""
    if not mapping or not mapping.startswith('XINPUT_'):
        return mapping
    
    # If friendly_names is False, return the raw mapping
    if not friendly_names:
        return mapping
        
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
        "LEFTX_NEG": "Left Stick Left",
        "LEFTX_POS": "Left Stick Right",
        "LEFTY_NEG": "Left Stick Up",
        "LEFTY_POS": "Left Stick Down",
        "RIGHTX_NEG": "Right Stick Left",
        "RIGHTX_POS": "Right Stick Right",
        "RIGHTY_NEG": "Right Stick Up",
        "RIGHTY_POS": "Right Stick Down",
        "START": "Start Button",
        "BACK": "Back Button"
    }
    return friendly_map.get(action, action)

def get_friendly_dinput_name(mapping: str, friendly_names: bool = True) -> str:
    """Convert a DINPUT mapping code into a human-friendly button/stick name - with toggle"""
    if not mapping or not mapping.startswith('DINPUT_'):
        return mapping
    
    # If friendly_names is False, return the raw mapping
    if not friendly_names:
        return mapping
        
    parts = mapping.split('_', 3)
    if len(parts) < 3:
        return mapping
    
    player_num = parts[1]
    action = parts[2]
    
    # Enhanced button mapping
    if action.startswith("BUTTON"):
        button_num = action[6:]  # Extract number from 'BUTTON0'
        return f"Button {button_num}"
    
    # Enhanced POV/directional mapping
    elif action == "POV_UP" or action == "POVUP":
        return "POV Up"
    elif action == "POV_DOWN" or action == "POVDOWN":
        return "POV Down"
    elif action == "POV_LEFT" or action == "POVLEFT":
        return "POV Left"
    elif action == "POV_RIGHT" or action == "POVRIGHT":
        return "POV Right"
    
    # Enhanced axis mapping
    elif action == "XAXIS_NEG":
        return "X-Axis Left"
    elif action == "XAXIS_POS":
        return "X-Axis Right"
    elif action == "YAXIS_NEG":
        return "Y-Axis Up"
    elif action == "YAXIS_POS":
        return "Y-Axis Down"
    elif action == "ZAXIS_NEG":
        return "Z-Axis Neg"
    elif action == "ZAXIS_POS":
        return "Z-Axis Pos"
    elif action == "RXAXIS_NEG":
        return "RX-Axis Left"
    elif action == "RXAXIS_POS":
        return "RX-Axis Right"
    elif action == "RYAXIS_NEG":
        return "RY-Axis Up"
    elif action == "RYAXIS_POS":
        return "RY-Axis Down"
    
    # Fallback
    return f"DInput {player_num} {action}"

def format_joycode_display(mapping: str, friendly_names: bool = True) -> str:
    """Format JOYCODE mapping string for display - with friendly/raw toggle."""
    if not mapping or not "JOYCODE" in mapping:
        return mapping
    
    # If friendly_names is False, return the raw mapping
    if not friendly_names:
        return mapping
    
    # Handle modern MAME button names
    if "SELECT" in mapping:
        return "Joy Select"
    elif "START" in mapping:
        return "Joy Start"
    
    # Handle modern HAT1 mappings
    elif "HAT1UP" in mapping:
        return "Joy D-Pad Up"
    elif "HAT1DOWN" in mapping:
        return "Joy D-Pad Down"
    elif "HAT1LEFT" in mapping:
        return "Joy D-Pad Left"
    elif "HAT1RIGHT" in mapping:
        return "Joy D-Pad Right"
    
    # Handle modern SLIDER2 mappings
    elif "SLIDER2_NEG" in mapping:
        return "Joy RT"  # Right Trigger
    elif "SLIDER2_POS" in mapping:
        return "Joy RT"  # Right Trigger
    elif "SLIDER2" in mapping:
        return "Joy RT"  # Right Trigger
    elif "SLIDER1" in mapping:
        return "Joy LT"  # Left Trigger
    
    # Legacy HAT mappings (for backward compatibility)
    elif "YAXIS_UP" in mapping or "DPADUP" in mapping or "HATUP" in mapping:
        return "Joy Up"
    elif "YAXIS_DOWN" in mapping or "DPADDOWN" in mapping or "HATDOWN" in mapping:
        return "Joy Down"
    elif "XAXIS_LEFT" in mapping or "DPADLEFT" in mapping or "HATLEFT" in mapping:
        return "Joy Left"
    elif "XAXIS_RIGHT" in mapping or "DPADRIGHT" in mapping or "HATRIGHT" in mapping:
        return "Joy Right"
    
    # Right stick mappings
    elif "RYAXIS_NEG" in mapping:
        return "Joy R-Up"
    elif "RYAXIS_POS" in mapping:
        return "Joy R-Down"
    elif "RXAXIS_NEG" in mapping:
        return "Joy R-Left"
    elif "RXAXIS_POS" in mapping:
        return "Joy R-Right"
    
    # Legacy Z-axis mappings (for backward compatibility)
    elif "ZAXIS_NEG" in mapping:
        return "Joy LT"  # Left Trigger (legacy)
    elif "ZAXIS_POS" in mapping:
        return "Joy RT"  # Right Trigger (legacy)
    
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

def format_mapping_display(mapping: str, input_mode: str = 'xinput', friendly_names: bool = True) -> str:
    """Format the mapping string for display using friendly names for the current input mode - with toggle."""
    
    # If friendly_names is False, return the raw mapping
    if not friendly_names:
        return mapping
    
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
            return format_keycode_display(mapping, friendly_names)
        else:
            return "No Key Assigned" if friendly_names else mapping
    
    # Format based on the current input mode
    if input_mode == 'xinput':
        if mapping.startswith("XINPUT"):
            return get_friendly_xinput_name(mapping, friendly_names)
        else:
            # Try to convert to XInput
            converted = convert_mapping(mapping, 'xinput')
            if converted.startswith("XINPUT"):
                return get_friendly_xinput_name(converted, friendly_names)
    
    elif input_mode == 'dinput':
        if mapping.startswith("DINPUT"):
            return get_friendly_dinput_name(mapping, friendly_names)
        else:
            # Try to convert to DInput
            converted = convert_mapping(mapping, 'dinput')
            if converted.startswith("DINPUT"):
                return get_friendly_dinput_name(converted, friendly_names)
    
    elif input_mode == 'joycode':
        if "JOYCODE" in mapping:
            return format_joycode_display(mapping, friendly_names)
        else:
            # Try to convert to JOYCODE
            converted = convert_mapping(mapping, 'joycode')
            if "JOYCODE" in converted:
                return format_joycode_display(converted, friendly_names)
    
    # For keyboard mappings, convert to "Key X" format
    if mapping.startswith("KEYCODE"):
        if friendly_names:
            key_name = mapping.replace("KEYCODE_", "")
            return f"Key {key_name}"
        else:
            return mapping

    # Fallback to original mapping if no conversion was possible
    return mapping

# ============================================================================
# DATA PROCESSING METHODS
# ============================================================================

def get_default_mame_mappings(input_mode: str = 'xinput') -> Dict[str, str]:
    """
    Get MAME's default control mappings when no cfg files exist
    These mirror what MAME automatically assigns through its input APIs
    """
    
    if input_mode == 'xinput':
        return {
            # Player 1 Standard Buttons
            'P1_BUTTON1': 'XINPUT_1_A',
            'P1_BUTTON2': 'XINPUT_1_B', 
            'P1_BUTTON3': 'XINPUT_1_X',
            'P1_BUTTON4': 'XINPUT_1_Y',
            'P1_BUTTON5': 'XINPUT_1_SHOULDER_L',
            'P1_BUTTON6': 'XINPUT_1_SHOULDER_R',
            'P1_BUTTON7': 'XINPUT_1_TRIGGER_L',
            'P1_BUTTON8': 'XINPUT_1_TRIGGER_R',
            'P1_BUTTON9': 'XINPUT_1_THUMB_L',
            'P1_BUTTON10': 'XINPUT_1_THUMB_R',
            
            # Player 1 Directional Controls
            'P1_JOYSTICK_UP': 'XINPUT_1_DPAD_UP',
            'P1_JOYSTICK_DOWN': 'XINPUT_1_DPAD_DOWN',
            'P1_JOYSTICK_LEFT': 'XINPUT_1_DPAD_LEFT',
            'P1_JOYSTICK_RIGHT': 'XINPUT_1_DPAD_RIGHT',
            'P1_JOYSTICKLEFT_UP': 'XINPUT_1_LEFTY_NEG',
            'P1_JOYSTICKLEFT_DOWN': 'XINPUT_1_LEFTY_POS',
            'P1_JOYSTICKLEFT_LEFT': 'XINPUT_1_LEFTX_NEG',
            'P1_JOYSTICKLEFT_RIGHT': 'XINPUT_1_LEFTX_POS',
            'P1_JOYSTICKRIGHT_UP': 'XINPUT_1_RIGHTY_NEG',
            'P1_JOYSTICKRIGHT_DOWN': 'XINPUT_1_RIGHTY_POS',
            'P1_JOYSTICKRIGHT_LEFT': 'XINPUT_1_RIGHTX_NEG',
            'P1_JOYSTICKRIGHT_RIGHT': 'XINPUT_1_RIGHTX_POS',
            
            # Player 1 System Controls
            'P1_START': 'XINPUT_1_START',
            'P1_SELECT': 'XINPUT_1_BACK',
            
            # Player 1 D-Pad (explicit)
            'P1_DPAD_UP': 'XINPUT_1_DPAD_UP',
            'P1_DPAD_DOWN': 'XINPUT_1_DPAD_DOWN',
            'P1_DPAD_LEFT': 'XINPUT_1_DPAD_LEFT',
            'P1_DPAD_RIGHT': 'XINPUT_1_DPAD_RIGHT',
            
            # Player 1 Specialized Controls (common defaults)
            'P1_PEDAL': 'XINPUT_1_TRIGGER_R',
            'P1_PEDAL2': 'XINPUT_1_TRIGGER_L',
            'P1_AD_STICK_X': 'XINPUT_1_LEFTX_NEG ||| XINPUT_1_LEFTX_POS',
            'P1_AD_STICK_Y': 'XINPUT_1_LEFTY_NEG ||| XINPUT_1_LEFTY_POS',
            'P1_AD_STICK_Z': 'XINPUT_1_TRIGGER_L ||| XINPUT_1_TRIGGER_R',
            'P1_DIAL': 'XINPUT_1_LEFTX_NEG ||| XINPUT_1_LEFTX_POS',
            'P1_DIAL_V': 'XINPUT_1_LEFTY_NEG ||| XINPUT_1_LEFTY_POS',
            'P1_PADDLE': 'XINPUT_1_LEFTX_NEG ||| XINPUT_1_LEFTX_POS',
            'P1_TRACKBALL_X': 'XINPUT_1_LEFTX_NEG ||| XINPUT_1_LEFTX_POS',
            'P1_TRACKBALL_Y': 'XINPUT_1_LEFTY_NEG ||| XINPUT_1_LEFTY_POS',
            'P1_MOUSE_X': 'XINPUT_1_LEFTX_NEG ||| XINPUT_1_LEFTX_POS',
            'P1_MOUSE_Y': 'XINPUT_1_LEFTY_NEG ||| XINPUT_1_LEFTY_POS',
            'P1_LIGHTGUN_X': 'XINPUT_1_LEFTX_NEG ||| XINPUT_1_LEFTX_POS',
            'P1_LIGHTGUN_Y': 'XINPUT_1_LEFTY_NEG ||| XINPUT_1_LEFTY_POS',
            'P1_POSITIONAL': 'XINPUT_1_LEFTX_NEG ||| XINPUT_1_LEFTX_POS',
            'P1_STEER': 'XINPUT_1_LEFTX_NEG ||| XINPUT_1_LEFTX_POS',
            
            # Player 2 Controls (mirror P1)
            'P2_BUTTON1': 'XINPUT_2_A',
            'P2_BUTTON2': 'XINPUT_2_B',
            'P2_BUTTON3': 'XINPUT_2_X', 
            'P2_BUTTON4': 'XINPUT_2_Y',
            'P2_BUTTON5': 'XINPUT_2_SHOULDER_L',
            'P2_BUTTON6': 'XINPUT_2_SHOULDER_R',
            'P2_BUTTON7': 'XINPUT_2_TRIGGER_L',
            'P2_BUTTON8': 'XINPUT_2_TRIGGER_R',
            'P2_BUTTON9': 'XINPUT_2_THUMB_L',
            'P2_BUTTON10': 'XINPUT_2_THUMB_R',
            'P2_JOYSTICK_UP': 'XINPUT_2_DPAD_UP',
            'P2_JOYSTICK_DOWN': 'XINPUT_2_DPAD_DOWN',
            'P2_JOYSTICK_LEFT': 'XINPUT_2_DPAD_LEFT',
            'P2_JOYSTICK_RIGHT': 'XINPUT_2_DPAD_RIGHT',
            'P2_START': 'XINPUT_2_START',
            'P2_SELECT': 'XINPUT_2_BACK',
        }
    
    elif input_mode == 'dinput':
        return {
            # Player 1 Standard Buttons (0-based for DInput)
            'P1_BUTTON1': 'DINPUT_1_BUTTON0',
            'P1_BUTTON2': 'DINPUT_1_BUTTON1',
            'P1_BUTTON3': 'DINPUT_1_BUTTON2',
            'P1_BUTTON4': 'DINPUT_1_BUTTON3',
            'P1_BUTTON5': 'DINPUT_1_BUTTON4',
            'P1_BUTTON6': 'DINPUT_1_BUTTON5',
            'P1_BUTTON7': 'DINPUT_1_BUTTON6',
            'P1_BUTTON8': 'DINPUT_1_BUTTON7',
            'P1_BUTTON9': 'DINPUT_1_BUTTON8',
            'P1_BUTTON10': 'DINPUT_1_BUTTON9',
            
            # Player 1 Directional Controls
            'P1_JOYSTICK_UP': 'DINPUT_1_POV_UP',
            'P1_JOYSTICK_DOWN': 'DINPUT_1_POV_DOWN',
            'P1_JOYSTICK_LEFT': 'DINPUT_1_POV_LEFT',
            'P1_JOYSTICK_RIGHT': 'DINPUT_1_POV_RIGHT',
            'P1_JOYSTICKLEFT_UP': 'DINPUT_1_YAXIS_NEG',
            'P1_JOYSTICKLEFT_DOWN': 'DINPUT_1_YAXIS_POS',
            'P1_JOYSTICKLEFT_LEFT': 'DINPUT_1_XAXIS_NEG',
            'P1_JOYSTICKLEFT_RIGHT': 'DINPUT_1_XAXIS_POS',
            'P1_JOYSTICKRIGHT_UP': 'DINPUT_1_RYAXIS_NEG',
            'P1_JOYSTICKRIGHT_DOWN': 'DINPUT_1_RYAXIS_POS',
            'P1_JOYSTICKRIGHT_LEFT': 'DINPUT_1_RXAXIS_NEG',
            'P1_JOYSTICKRIGHT_RIGHT': 'DINPUT_1_RXAXIS_POS',
            
            # Player 1 System Controls
            'P1_START': 'DINPUT_1_BUTTON8',
            'P1_SELECT': 'DINPUT_1_BUTTON9',
            
            # Player 1 Specialized Controls
            'P1_PEDAL': 'DINPUT_1_ZAXIS_POS',
            'P1_PEDAL2': 'DINPUT_1_ZAXIS_NEG',
            'P1_AD_STICK_X': 'DINPUT_1_XAXIS_NEG ||| DINPUT_1_XAXIS_POS',
            'P1_AD_STICK_Y': 'DINPUT_1_YAXIS_NEG ||| DINPUT_1_YAXIS_POS',
            'P1_DIAL': 'DINPUT_1_XAXIS_NEG ||| DINPUT_1_XAXIS_POS',
            'P1_PADDLE': 'DINPUT_1_XAXIS_NEG ||| DINPUT_1_XAXIS_POS',
            'P1_TRACKBALL_X': 'DINPUT_1_XAXIS_NEG ||| DINPUT_1_XAXIS_POS',
            'P1_TRACKBALL_Y': 'DINPUT_1_YAXIS_NEG ||| DINPUT_1_YAXIS_POS',
            
            # Player 2 Controls (mirror P1)
            'P2_BUTTON1': 'DINPUT_2_BUTTON0',
            'P2_BUTTON2': 'DINPUT_2_BUTTON1',
            'P2_BUTTON3': 'DINPUT_2_BUTTON2',
            'P2_BUTTON4': 'DINPUT_2_BUTTON3',
            'P2_BUTTON5': 'DINPUT_2_BUTTON4',
            'P2_BUTTON6': 'DINPUT_2_BUTTON5',
            'P2_JOYSTICK_UP': 'DINPUT_2_POV_UP',
            'P2_JOYSTICK_DOWN': 'DINPUT_2_POV_DOWN',
            'P2_JOYSTICK_LEFT': 'DINPUT_2_POV_LEFT',
            'P2_JOYSTICK_RIGHT': 'DINPUT_2_POV_RIGHT',
            'P2_START': 'DINPUT_2_BUTTON8',
            'P2_SELECT': 'DINPUT_2_BUTTON9',
        }
    
    elif input_mode == 'keycode':
        return {
            # Player 1 Standard Buttons (common keyboard defaults)
            'P1_BUTTON1': 'KEYCODE_LCONTROL',  # Ctrl = Fire/Primary
            'P1_BUTTON2': 'KEYCODE_LALT',      # Alt = Jump/Secondary  
            'P1_BUTTON3': 'KEYCODE_SPACE',     # Space = Action
            'P1_BUTTON4': 'KEYCODE_LSHIFT',    # Shift = Run/Modifier
            'P1_BUTTON5': 'KEYCODE_Z',         # Z = Button 5
            'P1_BUTTON6': 'KEYCODE_X',         # X = Button 6
            'P1_BUTTON7': 'KEYCODE_C',         # C = Button 7
            'P1_BUTTON8': 'KEYCODE_V',         # V = Button 8
            'P1_BUTTON9': 'KEYCODE_B',         # B = Button 9
            'P1_BUTTON10': 'KEYCODE_N',        # N = Button 10
            
            # Player 1 Directional Controls (Arrow Keys)
            'P1_JOYSTICK_UP': 'KEYCODE_UP',
            'P1_JOYSTICK_DOWN': 'KEYCODE_DOWN',
            'P1_JOYSTICK_LEFT': 'KEYCODE_LEFT',
            'P1_JOYSTICK_RIGHT': 'KEYCODE_RIGHT',
            'P1_JOYSTICKLEFT_UP': 'KEYCODE_UP',
            'P1_JOYSTICKLEFT_DOWN': 'KEYCODE_DOWN',
            'P1_JOYSTICKLEFT_LEFT': 'KEYCODE_LEFT',
            'P1_JOYSTICKLEFT_RIGHT': 'KEYCODE_RIGHT',
            
            # Player 1 System Controls
            'P1_START': 'KEYCODE_1',           # 1 = Start/Coin
            'P1_SELECT': 'KEYCODE_5',          # 5 = Coin
            
            # Player 1 Specialized Controls (use same directional keys)
            'P1_AD_STICK_X': 'KEYCODE_LEFT ||| KEYCODE_RIGHT',
            'P1_AD_STICK_Y': 'KEYCODE_UP ||| KEYCODE_DOWN',
            'P1_DIAL': 'KEYCODE_LEFT ||| KEYCODE_RIGHT',
            'P1_PADDLE': 'KEYCODE_LEFT ||| KEYCODE_RIGHT',
            'P1_TRACKBALL_X': 'KEYCODE_LEFT ||| KEYCODE_RIGHT',
            'P1_TRACKBALL_Y': 'KEYCODE_UP ||| KEYCODE_DOWN',
            'P1_PEDAL': 'KEYCODE_LCONTROL',
            'P1_PEDAL2': 'KEYCODE_LALT',
            
            # Player 2 Controls (WASD + different keys)
            'P2_BUTTON1': 'KEYCODE_A',         # A = P2 Fire
            'P2_BUTTON2': 'KEYCODE_S',         # S = P2 Secondary
            'P2_BUTTON3': 'KEYCODE_Q',         # Q = P2 Button 3
            'P2_BUTTON4': 'KEYCODE_W',         # W = P2 Button 4
            'P2_BUTTON5': 'KEYCODE_E',         # E = P2 Button 5
            'P2_BUTTON6': 'KEYCODE_D',         # D = P2 Button 6
            'P2_JOYSTICK_UP': 'KEYCODE_R',     # R = P2 Up
            'P2_JOYSTICK_DOWN': 'KEYCODE_F',   # F = P2 Down
            'P2_JOYSTICK_LEFT': 'KEYCODE_D',   # D = P2 Left
            'P2_JOYSTICK_RIGHT': 'KEYCODE_G',  # G = P2 Right
            'P2_START': 'KEYCODE_2',           # 2 = P2 Start
            'P2_SELECT': 'KEYCODE_6',          # 6 = P2 Coin
        }
    
    else:  # joycode fallback
        return {
            # Player 1 Standard Buttons
            'P1_BUTTON1': 'JOYCODE_1_BUTTON1',
            'P1_BUTTON2': 'JOYCODE_1_BUTTON2',
            'P1_BUTTON3': 'JOYCODE_1_BUTTON3',
            'P1_BUTTON4': 'JOYCODE_1_BUTTON4',
            'P1_BUTTON5': 'JOYCODE_1_BUTTON5',
            'P1_BUTTON6': 'JOYCODE_1_BUTTON6',
            'P1_BUTTON7': 'JOYCODE_1_BUTTON7',
            'P1_BUTTON8': 'JOYCODE_1_BUTTON8',
            
            # Player 1 Directional Controls
            'P1_JOYSTICK_UP': 'JOYCODE_1_HAT1UP',
            'P1_JOYSTICK_DOWN': 'JOYCODE_1_HAT1DOWN',
            'P1_JOYSTICK_LEFT': 'JOYCODE_1_HAT1LEFT',
            'P1_JOYSTICK_RIGHT': 'JOYCODE_1_HAT1RIGHT',
            
            # Player 1 System Controls
            'P1_START': 'JOYCODE_1_START',
            'P1_SELECT': 'JOYCODE_1_SELECT',
        }

def apply_default_mame_mappings(game_data: Dict, input_mode: str = 'xinput', 
                               friendly_names: bool = True) -> Dict:
    """
    Apply MAME's default mappings when no cfg files exist
    This ensures controls always show proper button names instead of raw control names
    """
    if not game_data or 'players' not in game_data:
        return game_data
    
    # Get the default mappings for current input mode
    default_mappings = get_default_mame_mappings(input_mode)
    
    # Apply to each player's controls
    for player in game_data.get('players', []):
        for label in player.get('labels', []):
            control_name = label['name']
            
            # Only apply if no existing mapping
            if not label.get('mapping') and control_name in default_mappings:
                default_mapping = default_mappings[control_name]
                
                # Apply the default mapping
                label.update({
                    'mapping': default_mapping,
                    'mapping_source': f'MAME Default ({input_mode.upper()})',
                    'is_custom': False,
                    'is_default': True,
                    'input_mode': input_mode
                })
                
                # Process the target button display
                _process_target_button_for_label(label, default_mapping, input_mode, friendly_names)
                _set_display_name_for_label(label, input_mode, friendly_names)
    
    # Mark the game data as having default mappings applied
    game_data['has_default_mappings'] = True
    game_data['default_mapping_mode'] = input_mode
    
    return game_data

def update_game_data_with_custom_mappings(game_data: Dict, cfg_controls: Dict, 
                                        default_controls: Dict, original_default_controls: Dict,
                                        input_mode: str = 'xinput', friendly_names: bool = True) -> Dict:
    """
    Update game_data with custom mappings - ENHANCED with MAME default fallback
    """
    # First apply MAME's built-in defaults as the base layer
    game_data = apply_default_mame_mappings(game_data, input_mode, friendly_names)
    
    # If we have no custom controls or defaults, we're done - MAME defaults are applied
    if not cfg_controls and not default_controls:
        return game_data
    
    # Helper function to extract keycode only for keycode mode
    def filter_mapping_for_mode(mapping: str, mode: str) -> str:
        if mode == 'keycode' and mapping:
            # Extract only the keycode portion from OR statements
            if " OR " in mapping:
                parts = [p.strip() for p in mapping.split(" OR ")]
                for part in parts:
                    if "KEYCODE_" in part:
                        return part
                return "NONE"  # No keycode found
            elif "KEYCODE_" in mapping:
                return mapping
            else:
                return "NONE"  # No keycode in single mapping
        return mapping  # Return as-is for other modes
    
    # Pre-process all mappings in one pass
    all_mappings = {}
    romname = game_data.get('romname', '')
    
    # Process default mappings efficiently (these override MAME defaults)
    if default_controls:
        for control, mapping in default_controls.items():
            processed_mapping = mapping
            if input_mode == 'keycode' and original_default_controls and control in original_default_controls:
                # Use original mapping and filter for keycode
                original_mapping = original_default_controls[control]
                processed_mapping = filter_mapping_for_mode(original_mapping, input_mode)
            else:
                processed_mapping = filter_mapping_for_mode(convert_mapping(mapping, input_mode), input_mode)
            
            all_mappings[control] = {
                'mapping': processed_mapping, 
                'source': 'Default CFG'
            }
    
    # Override with ROM-specific mappings (highest priority)
    for control, mapping in cfg_controls.items():
        processed_mapping = filter_mapping_for_mode(mapping, input_mode)
        
        # Skip if keycode mode and no keycode found
        if input_mode == 'keycode' and processed_mapping == "NONE":
            continue
        
        all_mappings[control] = {
            'mapping': processed_mapping, 
            'source': f"ROM CFG ({romname}.cfg)"
        }
    
    # Apply custom mappings to game data (override defaults where they exist)
    for player in game_data.get('players', []):
        for label in player.get('labels', []):
            control_name = label['name']
            
            if control_name in all_mappings:
                mapping_info = all_mappings[control_name]
                
                # Apply all mapping data at once (this overrides MAME defaults)
                label.update({
                    'mapping': mapping_info['mapping'],
                    'mapping_source': mapping_info['source'],
                    'is_custom': 'ROM CFG' in mapping_info['source'],
                    'is_default': False,  # This is now a custom override
                    'cfg_mapping': True,
                    'input_mode': input_mode
                })
                
                # Process target_button efficiently
                _process_target_button_for_label(label, mapping_info['mapping'], input_mode, friendly_names)
            
            # Set display name for all controls
            _set_display_name_for_label(label, input_mode, friendly_names)
    
    # Update metadata
    game_data['input_mode'] = input_mode
    game_data['friendly_names'] = friendly_names
    if cfg_controls:
        game_data['has_rom_cfg'] = True
        game_data['rom_cfg_file'] = f"{romname}.cfg"
    if default_controls:
        game_data['has_default_cfg'] = True
    
    return game_data

def get_friendly_dinput_alternatives(dinput_mapping: str) -> str:
    """
    Convert DInput mapping with alternatives to friendly display names
    Example: 'POV Up | Y-Axis Up' -> 'POV Up | Y-Axis Up' (already friendly)
    """
    if '|' not in dinput_mapping:
        # Single mapping, return as-is since it's already friendly
        return dinput_mapping
    
    # Multiple mappings are already in friendly format
    return dinput_mapping

def _process_target_button_for_label(label: Dict, mapping: str, input_mode: str, friendly_names: bool = True):
    """Process target_button with friendly names toggle support"""
    
    control_name = label.get('name', '')
    
    if " ||| " in mapping:
        # Handle increment/decrement pairs
        inc_mapping, dec_mapping = mapping.split(" ||| ")
        
        if input_mode == 'xinput':
            xinput_alternatives = get_xinput_directional_alternatives(control_name)
            
            if xinput_alternatives:
                # Use the specialized directional alternatives
                if friendly_names:
                    label['target_button'] = get_friendly_xinput_alternatives(xinput_alternatives)
                else:
                    label['target_button'] = xinput_alternatives
                label['xinput_alternatives'] = xinput_alternatives
            else:
                # Fall back to processing the raw increment/decrement mappings
                inc_friendly = get_friendly_xinput_name(inc_mapping, friendly_names) if inc_mapping != "NONE" else ""
                dec_friendly = get_friendly_xinput_name(dec_mapping, friendly_names) if dec_mapping != "NONE" else ""
                
                if inc_friendly and dec_friendly:
                    label['target_button'] = f"{inc_friendly} | {dec_friendly}"
                else:
                    label['target_button'] = inc_friendly or dec_friendly or "Not Assigned"
                    
        elif input_mode == 'dinput':
            dinput_alternatives = get_dinput_directional_alternatives(control_name)
            
            if dinput_alternatives:
                # Use the specialized directional alternatives
                if friendly_names:
                    label['target_button'] = dinput_alternatives
                else:
                    # For raw mode, show actual DInput codes
                    label['target_button'] = f"DINPUT_1_POV_{control_name.split('_')[-1]}"
                label['dinput_alternatives'] = dinput_alternatives
            else:
                # Fall back to processing raw mappings
                inc_friendly = get_friendly_dinput_name(inc_mapping, friendly_names) if inc_mapping != "NONE" else ""
                dec_friendly = get_friendly_dinput_name(dec_mapping, friendly_names) if dec_mapping != "NONE" else ""
                
                if inc_friendly and dec_friendly:
                    label['target_button'] = f"{inc_friendly} | {dec_friendly}"
                else:
                    label['target_button'] = inc_friendly or dec_friendly or "Not Assigned"
                    
        elif input_mode == 'keycode':
            if friendly_names:
                inc_keycode = extract_keycode_from_mapping(inc_mapping)
                dec_keycode = extract_keycode_from_mapping(dec_mapping)
                
                if inc_keycode and dec_keycode:
                    label['target_button'] = f"{inc_keycode} | {dec_keycode}"
                elif inc_keycode or dec_keycode:
                    label['target_button'] = inc_keycode or dec_keycode
                else:
                    label['target_button'] = "No Key Assigned"
            else:
                # Show raw keycode mappings
                label['target_button'] = f"{inc_mapping} | {dec_mapping}"
        else:
            label['target_button'] = format_mapping_display(mapping, input_mode, friendly_names)
    else:
        # Regular mapping (no increment/decrement pairs)
        if input_mode == 'xinput':
            xinput_alternatives = get_xinput_directional_alternatives(control_name)
            
            if xinput_alternatives:
                if friendly_names:
                    label['target_button'] = get_friendly_xinput_alternatives(xinput_alternatives)
                else:
                    label['target_button'] = xinput_alternatives
                label['xinput_alternatives'] = xinput_alternatives
            elif 'XINPUT' in mapping:
                label['target_button'] = get_friendly_xinput_name(mapping, friendly_names)
            else:
                converted = convert_mapping(mapping, 'xinput')
                if converted.startswith('XINPUT'):
                    xinput_alternatives = get_xinput_directional_alternatives(control_name)
                    if xinput_alternatives:
                        if friendly_names:
                            label['target_button'] = get_friendly_xinput_alternatives(xinput_alternatives)
                        else:
                            label['target_button'] = xinput_alternatives
                        label['xinput_alternatives'] = xinput_alternatives
                    else:
                        label['target_button'] = get_friendly_xinput_name(converted, friendly_names)
                else:
                    label['target_button'] = format_mapping_display(mapping, input_mode, friendly_names)
        
        elif input_mode == 'dinput':
            dinput_alternatives = get_dinput_directional_alternatives(control_name)
            
            if dinput_alternatives:
                if friendly_names:
                    label['target_button'] = dinput_alternatives
                else:
                    # Show raw DInput mapping
                    label['target_button'] = f"DINPUT_1_POV_{control_name.split('_')[-1]}"
                label['dinput_alternatives'] = dinput_alternatives
            elif 'DINPUT' in mapping:
                label['target_button'] = get_friendly_dinput_name(mapping, friendly_names)
            else:
                converted = convert_mapping(mapping, 'dinput')
                if converted.startswith('DINPUT'):
                    label['target_button'] = get_friendly_dinput_name(converted, friendly_names)
                else:
                    # Provide fallback
                    if friendly_names and 'JOYSTICK_UP' in control_name:
                        label['target_button'] = 'D-Pad Up | Left Stick Up'
                    elif friendly_names and 'JOYSTICK_DOWN' in control_name:
                        label['target_button'] = 'D-Pad Down | Left Stick Down'
                    elif friendly_names and 'JOYSTICK_LEFT' in control_name:
                        label['target_button'] = 'D-Pad Left | Left Stick Left'
                    elif friendly_names and 'JOYSTICK_RIGHT' in control_name:
                        label['target_button'] = 'D-Pad Right | Left Stick Right'
                    else:
                        label['target_button'] = format_mapping_display(mapping, input_mode, friendly_names)
        
        elif input_mode == 'keycode':
            if friendly_names:
                keycode_display = extract_keycode_from_mapping(mapping)
                label['target_button'] = keycode_display if keycode_display else "No Key Assigned"
            else:
                # Show raw keycode mapping
                label['target_button'] = mapping if mapping.startswith("KEYCODE") else "No Key Assigned"
        else:
            label['target_button'] = format_mapping_display(mapping, input_mode, friendly_names)

def _set_display_name_for_label(label: Dict, input_mode: str, friendly_names: bool = True):
    """Set display name with friendly names toggle support"""
    
    if 'target_button' in label:
        if input_mode == 'keycode':
            label['display_name'] = label['target_button']
        else:
            target = label['target_button']
            
            # For directional controls with alternatives, format nicely
            if '|' in target and (input_mode == 'xinput' or input_mode == 'dinput'):
                # Already formatted with alternatives, use as-is
                label['display_name'] = target
            elif friendly_names and not target.startswith('P1 '):
                label['display_name'] = f'P1 {target}'
            else:
                label['display_name'] = target
    else:
        # Fallback to control name formatting
        control_name = label['name']
        if input_mode == 'keycode':
            label['display_name'] = "No Key Assigned" if friendly_names else control_name
        elif input_mode == 'xinput':
            # Check for directional alternatives
            xinput_alternatives = get_xinput_directional_alternatives(control_name)
            if xinput_alternatives and friendly_names:
                label['display_name'] = get_friendly_xinput_alternatives(xinput_alternatives)
            elif friendly_names:
                label['display_name'] = f"P1 {control_name.split('_')[-1]}"
            else:
                label['display_name'] = control_name
        elif input_mode == 'dinput':
            # Check for DInput directional alternatives
            dinput_alternatives = get_dinput_directional_alternatives(control_name)
            if dinput_alternatives and friendly_names:
                label['display_name'] = get_friendly_dinput_alternatives(dinput_alternatives)
            elif friendly_names:
                label['display_name'] = f"P1 {control_name.split('_')[-1]}"
            else:
                label['display_name'] = control_name
        else:
            if friendly_names:
                label['display_name'] = f"P1 {control_name.split('_')[-1]}"
            else:
                label['display_name'] = control_name

def cleanup_database_connections():
    """Clean up cached database connections"""
    global _db_connection_cache
    
    for conn in _db_connection_cache.values():
        try:
            conn.close()
        except:
            pass
    _db_connection_cache.clear()
    print("Cleaned up database connections")

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

def load_rom_exclusion_list(mame_dir: str) -> Set[str]:
    """
    Load ROM exclusion list from settings/excluded_roms.txt
    Each line should contain one ROM name to exclude
    """
    settings_dir = os.path.join(mame_dir, "preview", "settings")
    exclusion_file = os.path.join(settings_dir, "excluded_roms.txt")
    excluded_roms = set()
    
    if os.path.exists(exclusion_file):
        try:
            with open(exclusion_file, 'r', encoding='utf-8') as f:
                for line in f:
                    rom_name = line.strip()
                    # Skip empty lines and comments (lines starting with #)
                    if rom_name and not rom_name.startswith('#'):
                        excluded_roms.add(rom_name)
            
            print(f"Loaded {len(excluded_roms)} ROMs from exclusion list")
            if excluded_roms:
                print(f"Sample excluded ROMs: {list(excluded_roms)[:5]}")
        except Exception as e:
            print(f"Error loading ROM exclusion list: {e}")
    else:
        print(f"No ROM exclusion list found at: {exclusion_file}")
        print("Create 'excluded_roms.txt' in the settings folder to exclude specific ROMs")
    
    return excluded_roms

def save_rom_exclusion_list(mame_dir: str, excluded_roms: Set[str]) -> bool:
    """
    Save ROM exclusion list to settings/excluded_roms.txt
    """
    settings_dir = os.path.join(mame_dir, "settings")
    exclusion_file = os.path.join(settings_dir, "excluded_roms.txt")
    
    try:
        # Create settings directory if it doesn't exist
        os.makedirs(settings_dir, exist_ok=True)
        
        with open(exclusion_file, 'w', encoding='utf-8') as f:
            f.write("# ROM Exclusion List\n")
            f.write("# Add one ROM name per line to exclude it from the GUI\n")
            f.write("# Lines starting with # are treated as comments\n")
            f.write("# Example:\n")
            f.write("# badrom1\n")
            f.write("# badrom2\n")
            f.write("\n")
            
            for rom_name in sorted(excluded_roms):
                f.write(f"{rom_name}\n")
        
        print(f"Saved {len(excluded_roms)} ROMs to exclusion list: {exclusion_file}")
        return True
    except Exception as e:
        print(f"Error saving ROM exclusion list: {e}")
        return False

def scan_roms_directory(mame_dir: str, use_exclusion_list: bool = True) -> Set[str]:
    """Scan the roms directory for available games with improved path handling and exclusion support"""
    
    roms_dir = os.path.join(mame_dir, "roms")
    available_roms = set()
    
    if not os.path.exists(roms_dir):
        print(f"ROMs directory not found: {roms_dir}")
        return available_roms

    # Load exclusion list if enabled
    excluded_roms = set()
    if use_exclusion_list:
        excluded_roms = load_rom_exclusion_list(mame_dir)

    rom_count = 0
    excluded_count = 0

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
            
            # Check if ROM is in exclusion list
            if use_exclusion_list and base_name in excluded_roms:
                excluded_count += 1
                if excluded_count <= 5:  # Print first 5 excluded ROMs as sample
                    print(f"Excluded ROM: {base_name}")
                continue
            
            available_roms.add(base_name)
            rom_count += 1
            
            if rom_count <= 5:  # Print first 5 ROMs as sample
                print(f"Found ROM: {base_name}")
        
        print(f"Total ROMs found: {len(available_roms)}")
        if excluded_count > 0:
            print(f"Total ROMs excluded: {excluded_count}")
        if len(available_roms) > 0:
            print(f"Sample of available ROMs: {list(available_roms)[:5]}")
        else:
            print("WARNING: No ROMs were found!")
    except Exception as e:
        print(f"Error scanning ROMs directory: {e}")
    
    return available_roms

def add_rom_to_exclusion_list(mame_dir: str, rom_name: str) -> bool:
    """
    Add a single ROM to the exclusion list
    """
    excluded_roms = load_rom_exclusion_list(mame_dir)
    excluded_roms.add(rom_name)
    return save_rom_exclusion_list(mame_dir, excluded_roms)

def remove_rom_from_exclusion_list(mame_dir: str, rom_name: str) -> bool:
    """
    Remove a single ROM from the exclusion list
    """
    excluded_roms = load_rom_exclusion_list(mame_dir)
    if rom_name in excluded_roms:
        excluded_roms.remove(rom_name)
        return save_rom_exclusion_list(mame_dir, excluded_roms)
    return False

def is_rom_excluded(mame_dir: str, rom_name: str) -> bool:
    """
    Check if a ROM is in the exclusion list
    """
    excluded_roms = load_rom_exclusion_list(mame_dir)
    return rom_name in excluded_roms

def get_exclusion_list_stats(mame_dir: str) -> Dict[str, Any]:
    """
    Get statistics about the exclusion list
    """
    excluded_roms = load_rom_exclusion_list(mame_dir)
    settings_dir = os.path.join(mame_dir, "settings")
    exclusion_file = os.path.join(settings_dir, "excluded_roms.txt")
    
    stats = {
        'total_excluded': len(excluded_roms),
        'exclusion_file_exists': os.path.exists(exclusion_file),
        'exclusion_file_path': exclusion_file,
        'sample_excluded': list(excluded_roms)[:10] if excluded_roms else []
    }
    
    return stats

# ============================================================================
# HELPER FUNCTIONS FOR DATA ANALYSIS
# ============================================================================

def identify_generic_controls(available_roms: Set[str], gamedata_json: Dict, 
                             parent_lookup: Dict, db_path: str = None, 
                             rom_data_cache: Dict = None) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Identify games that only have generic control names - CORRECTED VERSION"""
    generic_control_games = []
    missing_control_games = []
    
    def check_controls_for_names(controls_dict):
        """Check if any controls have non-empty 'name' fields"""
        for control_name, control_data in controls_dict.items():
            if isinstance(control_data, dict) and 'name' in control_data:
                name_value = control_data['name']
                if name_value and name_value.strip():  # Non-empty name
                    return True
        return False
    
    for rom_name in sorted(available_roms):
        # First check if game data exists at all
        game_data = get_game_data(rom_name, gamedata_json, parent_lookup, db_path, rom_data_cache)
        if not game_data:
            missing_control_games.append(rom_name)
            continue
        
        # Check if ROM has controls in gamedata.json
        has_gamedata_controls = False
        has_custom_names = False
        
        # Check ROM directly
        if rom_name in gamedata_json:
            rom_data = gamedata_json[rom_name]
            if 'controls' in rom_data and rom_data['controls']:
                has_gamedata_controls = True
                has_custom_names = check_controls_for_names(rom_data['controls'])
        
        # Check parent if this is a clone
        elif rom_name in parent_lookup:
            parent_rom = parent_lookup[rom_name]
            if parent_rom in gamedata_json:
                parent_data = gamedata_json[parent_rom]
                if 'controls' in parent_data and parent_data['controls']:
                    has_gamedata_controls = True
                    has_custom_names = check_controls_for_names(parent_data['controls'])
        
        # GENERIC = has gamedata controls but NO "name" fields
        if has_gamedata_controls and not has_custom_names:
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
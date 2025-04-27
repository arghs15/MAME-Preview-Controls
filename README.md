# MAME Controls Preview Tool

A comprehensive utility for managing, viewing, and customizing MAME arcade control mappings with a visual preview system. This tool allows you to create control configurations, visual layouts, and export images that show how controls are mapped for specific games.

## Features

- **Control Mapping Visualization**: See how each game's controls are mapped to your controller
- **Interactive Preview**: Create, customize, and save control layout positions
- **Global & ROM-specific Configurations**: Create custom layouts for individual games or set global defaults
- **Visual Customization**: Add logos, bezels, change text colors, apply gradients
- **Export Images**: Generate PNG images of control layouts for reference
- **Control Editing**: Add or modify control mappings directly in the database
- **Batch Processing**: Export control images for multiple games at once
- **MAME Integration**: Show control layouts automatically when pausing a game in MAME

## How It Works

The application combines several key components:

1. **Main UI**: Customtkinter-based interface for browsing games and managing settings
2. **Preview Window**: PyQt5-based display for interactive control visualization
3. **Database**: Uses SQLite and JSON for fast, reliable control data storage
4. **MAME Plugin**: Optional Lua plugin that displays controls when you pause a game

## Installation

### Requirements

The application requires Python 3.6+ and the following major dependencies:

```
customtkinter>=5.0.0
PyQt5>=5.15.0
Pillow>=8.0.0
```

### Installation Methods

#### From Source

1. Clone the repository:
   ```
   https://github.com/arghs15/MAME-Preview-Controls.git
   ```

2. Install dependencies:

3. Run the application:
   ```
   python mame_controls_main.py
   ```

#### Pre-built Package

1. Download the latest release from the [Releases page](https://github.com/yourusername/mame-controls-preview/releases)
2. Extract to your MAME directory (it will create a `preview` folder)
3. Run `MAME_Controls.exe` from the preview folder

## Directory Structure

The application uses the following directory structure:

```
mame/                  # Your MAME installation directory
├── preview/           # Main application directory
│   ├── MAME_Controls.exe      # Main executable
│   ├── settings/             # Configuration and database storage
│   │   ├── gamedata.db       # SQLite database (built from gamedata.json)
│   │   ├── gamedata.json     # Game control data 
│   │   └── info/             # Game info files
│   ├── cache/               # Cached control data
│   ├── images/              # Background and exported images
│   ├── bezels/              # Bezel artwork
│   └── logos/               # Game logos
├── roms/                # Your MAME ROMs
├── plugins/             # MAME Lua plugins directory
│   └── controls.lua     # Controls display plugin
└── cfg/                 # MAME control configuration files
```

## How Game Data Works

The application uses a layered approach to determine control mappings for each game:

1. **ROM-specific .cfg file**: Checked first for custom mappings
2. **gamedata.json**: Contains game-specific button labels and info
3. **default.cfg**: Used as a fallback for unmapped controls

### Control Data Flow

When displaying a game's controls, the application:

1. Loads the game data from either:
   - SQLite database (for speed)
   - Directly from gamedata.json (if database isn't available)
2. Checks for ROM-specific control mappings in the cfg directory
3. Falls back to default mappings for unmapped controls
4. Presents a unified view showing both mappings and labels

## Using the Preview Screen

The Preview screen is where you can create and customize your own control layouts.

### Basic Controls

- **Dragging**: Click and drag control labels to position them
- **Save Buttons**: 
  - "Global Save" - Save positions for all games
  - "ROM Save" - Save positions only for the current game
- **Toggle Buttons**:
  - "Hide Texts" - Toggle visibility of control labels
  - "Joystick" - Toggle visibility of joystick controls
  - "Hide/Show Logo" - Toggle visibility of the game logo
  - "Show/Hide Bezel" - Toggle visibility of the cabinet bezel

### Customization Options

#### Text Appearance

Click "Text Settings" to customize:

- Font family and size
- Text color for buttons and actions
- Gradient effects
- Button prefix visibility (e.g., "A: Jump")
- Bold strength

#### Logo Management

- Click "Center Logo" to center the logo horizontally
- Click and drag the logo to position it manually
- Click and drag the bottom-right corner of the logo to resize it

#### Alignment Grid

- Click "Show Grid" to display an alignment grid
- Use the grid to ensure consistent control positioning

#### Snapping

- Enable/disable snapping with the "Enable/Disable Snap" button
- Hold Shift to temporarily disable snapping while dragging

### Creating Custom Layouts

1. Select a game from the main window
2. Click "Preview Controls" to open the preview window
3. Drag controls to desired positions
4. Add a logo and bezel if desired
5. Adjust text appearance (colors, gradients, etc.)
6. Save your layout (ROM-specific or Global)

The application will automatically apply your layout when viewing the same game in the future.

## MAME Plugin Integration

The included MAME Lua plugin provides seamless integration with MAME:

### Installation

1. For MAME version 0.196 Copy `controls.lua` and `plugin.json` to your MAME plugins directory (usually `mame/plugins/controls`)
2. Enable the plugin in the MAME UI

### Features

- **Automatic Display**: Shows control layout when you pause a game in MAME
- **Menu Integration**: Adds a "Controls" menu to MAME's UI
- **Pre-caching**: Loads control data in the background when a game starts for faster display
- **Pause Handling**: Automatically shows/hides controls when pausing/unpausing games
- **Cross-version Support**: Works with multiple MAME versions (0.196+)

### Usage

1. Start any game in MAME with the plugin enabled
2. Press the pause button (default: P) to pause the game and display controls
3. The control layout will automatically appear
4. Resume the game by pressing any Xinput button, or ESC

### Plugin Configuration

You can modify `controls.lua` to customize its behavior:

- Change which screen the controls display on (for multi-monitor setups)
- Adjust precaching behavior
- Modify automatic pause handling

```lua
-- Example: Change display to second monitor
local command = string.format('"preview\\MAME_Controls.exe" --preview-only --game %s --screen 2 --clean-preview', game_name)
```

### Troubleshooting

- If controls don't appear, check that the plugin is properly loaded (you should see "Controls plugin loaded" in MAME's console)
- Check the downlaoded files are located in the MAME directory under the fodler named preview

## Editing Control Data

The "Analyze Controls" function provides tools to edit the game control database:

1. Click "Analyze Controls" on the main screen
2. Navigate to the appropriate tab (Generic Controls, Missing Controls, Custom Controls)
3. Select a game and click "Edit Selected Game"
4. In the editor, you can:
   - Update game name and properties
   - Define control actions for standard buttons
   - Add custom controls
   - Remove the game entirely from the database

Changes are saved directly to gamedata.json and automatically rebuild the database.

## Batch Exporting Images

To create reference images for multiple games:

1. Click "Batch Export" on the main screen
2. Configure export settings:
   - Select display options (hide buttons, clean mode, etc.)
   - Choose image format (PNG)
   - Select output directory
3. Choose which ROMs to process:
   - All ROMs with controls
   - Custom selection (select specific ROMs)
   - Current ROM only
4. Click "Start Export"

The application will generate images for all selected games with their current control layouts.

## Building the Executable

You can package the application as a standalone executable using PyInstaller:

1. Ensure PyInstaller is installed:
   ```
   pip install pyinstaller
   ```

2. Run the packaging script:
   ```
   python package_with_pyinstaller.py
   ```

This will create a `dist/preview` directory containing the executable and all necessary files. Copy the contents of the preview folder to your MAME directory, and run the executable.

You can edit `python package_with_pyinstaller.py` to create a portable executable, but load times will be increased.
Edit the line below to use onefile

`"--onedir",`         # Create a directory with all files

`"--onefile",`         # Create a portable exectuable

### Custom Packaging Options

You can modify `package_with_pyinstaller.py` to customize the packaging process:

- Change the executable name
- Add custom icons
- Include additional resources
- Specify hidden imports

## Advanced Usage

### Creating Info Files for RetroFE

The "Generate Info Files" function creates game info files compatible with RetroFE:

1. Click "Generate Info Files" on the main screen
2. The application will process all available ROMs
3. Info files will be created in the `preview/settings/info` directory

### Command-Line Options

The application supports several command-line options:

```
mame_controls_main.py [options]

Options:
  --preview-only      Show only the preview window
  --game ROM          Specify the ROM name to preview
  --no-buttons        Hide buttons in preview mode
  --clean-preview     Show preview without drag handles
  --screen NUMBER     Screen number to display preview on
  --export-image      Export image mode (requires --output)
  --output PATH       Output path for exported image
  --format FORMAT     Image format (png or jpg)
  --precache          Precache game data without showing preview
```

### Cache Management

The application caches game data to improve performance:

- Click "Clear Cache" to manage the cache
- You can configure:
  - Maximum cache age (days)
  - Maximum number of cache files
  - Enable/disable automatic cleanup

## Troubleshooting

### Common Issues

1. **Database Not Found**: The application will automatically build a new database from gamedata.json if it can't find one.

2. **ROMs Not Found**: Make sure your ROMs are in the `mame/roms` directory.

3. **Preview Display Problems**: Try using the "Clean Mode" option to disable interactive elements.

4. **Text Font Issues**: Some fonts may appear too small or large. Use the "Bold Strength" and "Font Size" options in Text Settings to adjust.

5. **Image Export Fails**: Ensure the output directory exists and you have write permissions.

6. **MAME Plugin Not Working**: Verify the plugin is installed in the correct directory and is enabled in MAME.

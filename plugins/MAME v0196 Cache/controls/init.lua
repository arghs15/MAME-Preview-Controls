-- license:MIT
-- copyright-holders:Custom
-- MAME Controls Menu Plugin for MAME 0.196 - With Pre-caching Feature
local exports = {}
exports.name = "controls"
exports.version = "0.2.196"
exports.description = "MAME Controls Display Menu with Pre-caching"
exports.license = "MIT"
exports.author = { name = "Custom" }

function exports.startplugin()
    -- Flag to indicate when a pause was caused by the user
    local user_paused = false
    -- Track currently running ROM for pre-caching
    local current_rom = nil
    -- Track if precaching has been done for current ROM
    local rom_precached = false
    
    local function precache_controls(game_name)
        if not game_name or game_name == "" then return end
        
        -- Skip if already precached
        if current_rom == game_name and rom_precached then 
            print("ROM already precached: " .. game_name)
            return 
        end
        
        os.execute("echo Game started: " .. game_name .. " > C:\\mame_plugin_log.txt")
        -- Use the new --precache option to load data in background
        local command = string.format('python "preview\\mame_controls_main.py" --precache --game %s', game_name)
        -- local command = string.format('"preview\\MAME_Controls.exe" --preview-only --game %s --screen 1 --clean-preview', game_name)
        print("Pre-caching controls for: " .. game_name)
        os.execute(command)
        
        -- Mark as precached
        current_rom = game_name
        rom_precached = true
        print("Precaching complete for: " .. game_name)
    end
    
    local function show_controls()
        local game_name = emu.romname()
        print("Showing controls for: " .. (game_name or "nil"))
        
        if game_name and game_name ~= "" then
            -- Show controls
            local command = string.format('python "preview\\mame_controls_main.py" --preview-only --game %s --screen 1 --no-buttons', game_name)
            -- local command = string.format('"preview\\MAME_Controls.exe" --preview-only --game %s --screen 1 --clean-preview', game_name)
            print("Running: " .. command)
            os.execute(command)
            
            -- Unpause MAME if it was paused by the user
            if user_paused then
                print("Unpausing MAME after controls")
                emu.unpause()
                user_paused = false
            end
        end
    end
    
    -- Menu population function
    local function menu_populate()
        local menu = {}
        menu[1] = {"Show Controls", "", 0}
        return menu
    end
    
    -- Menu callback
    local function menu_callback(index, event)
        if event == "select" then
            show_controls()
            return true
        end
        return false
    end
    
    -- Register menu
    emu.register_menu(menu_callback, menu_populate, "Controls")
    
    -- Register pause handler
    if emu.register_pause then
        print("Registering pause handler")
        emu.register_pause(function()
            -- When the user pauses, set our flag and show controls
            if not user_paused then
                user_paused = true
                print("User paused MAME")
                show_controls()
            else
                -- Reset our flag when MAME is unpaused
                user_paused = false
                print("MAME unpaused")
            end
        end)
    else
        print("emu.register_pause not available in this MAME version")
    end
    
    -- NEW: Register start handler for pre-caching
    if emu.register_start then
        print("Registering start handler for pre-caching")
        emu.register_start(function()
            -- When game starts, precache the controls info
            print("Game started, pre-caching controls")
            rom_precached = false  -- Reset precache status for new ROM
            local game_name = emu.romname()
            if game_name and game_name ~= "" then
                -- Direct call without timer
                precache_controls(game_name)
            end
        end)
    else
        print("emu.register_start not available in this MAME version")
    end
    
    -- Reset when game stops
    emu.register_stop(function()
        user_paused = false
        rom_precached = false
        print("Controls plugin reset for next game")
    end)
    
    -- Periodic timer for potentially checking if ROM changed
    local periodic_timer = emu.timer.periodic(5.0, function()
        local current_game = emu.romname()
        if current_game and current_game ~= "" and current_game ~= current_rom then
            print("ROM change detected, pre-caching new ROM: " .. current_game)
            precache_controls(current_game)
        end
        return true  -- Keep timer running
    end)
    
    print("Controls plugin loaded with pre-caching support")
end

return exports
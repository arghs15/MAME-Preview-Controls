-- license:MIT
-- copyright-holders:Custom
-- MAME Controls Menu Plugin for MAME 0.196 - Pause Only Version
local exports = {}
exports.name = "controls"
exports.version = "0.1.196"
exports.description = "MAME Controls Display Menu"
exports.license = "MIT"
exports.author = { name = "Custom" }

function exports.startplugin()
    -- Flag to indicate when a pause was caused by the user
    local user_paused = false
    
    local function show_controls()
        local game_name = emu.romname()
        print("Game: " .. (game_name or "nil"))
        
        if game_name and game_name ~= "" then
            -- Show controls
            local command = string.format('"MAME Controls.exe" --preview-only --game %s --screen 1 --hide-joystick --hide-buttons', game_name)
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
    
    -- Reset when game stops
    emu.register_stop(function()
        user_paused = false
        print("Controls plugin reset for next game")
    end)
    
    print("Controls plugin loaded (pause detection + menu only)")
end

return exports
-- license:MIT
-- copyright-holders:Custom
-- MAME Controls Menu Plugin for MAME 0.196 - With Timer Error Fix
local exports = {}
exports.name = "controls"
exports.version = "0.3.196"
exports.description = "MAME Controls Display Menu - Fixed Version"
exports.license = "MIT"
exports.author = { name = "Custom" }

function exports.startplugin()
    -- Flag to indicate when a pause was caused by the user
    local user_paused = false
    -- Track currently running ROM for pre-caching
    local current_rom = nil
    -- Track if precaching has been done for current ROM
    local rom_precached = false
    -- Flag to check if timer functionality is available
    local has_timer = (emu.timer ~= nil)
    
    -- Print plugin initialization info
    print("Controls plugin initializing...")
    print("Timer functionality available: " .. tostring(has_timer))
    
    local function precache_controls(game_name)
        if not game_name or game_name == "" or game_name == "___empty" then
            print("No valid ROM name available, skipping precache")
            return 
        end
        
        -- Skip if already precached
        if current_rom == game_name and rom_precached then 
            print("ROM already precached: " .. game_name)
            return 
        end
        
        -- Log to file for debugging
        os.execute("echo Game detected: " .. game_name .. " > C:\\mame_plugin_log.txt")
        
        -- Use the new --precache option to load data in background
        local command = string.format('"preview\\MAME_Controls.exe" --precache --game %s', game_name)
        print("Pre-caching controls for: " .. game_name)
        
        -- Try to run the precache command
        local result = os.execute(command)
        if result then
            -- Mark as precached
            current_rom = game_name
            rom_precached = true
            print("Precaching complete for: " .. game_name)
        else
            print("Precaching failed for: " .. game_name)
        end
    end
    
    local function show_controls()
        local game_name = emu.romname()
        if not game_name or game_name == "" or game_name == "___empty" then
            print("No valid ROM name available, cannot show controls")
            return
        end
        
        print("Showing controls for: " .. game_name)
        
        -- Show controls
        local command = string.format('"preview\\MAME_Controls.exe" --preview-only --game %s --screen 1 --clean-preview', game_name)
        print("Running: " .. command)
        os.execute(command)
        
        -- Unpause MAME if it was paused by the user
        if user_paused then
            print("Unpausing MAME after controls")
            emu.unpause()
            user_paused = false
        end
    end
    
    -- Menu population function
    local function menu_populate()
        local menu = {}
        local game_name = emu.romname()
        if game_name and game_name ~= "" and game_name ~= "___empty" then
            menu[1] = {"Show Controls for " .. game_name, "", 0}
        else
            menu[1] = {"Show Controls (No ROM loaded)", "", 0}
        end
        return menu
    end
    
    -- Menu callback
    local function menu_callback(index, event)
        if event == "select" then
            -- Don't try to show controls if no ROM is loaded
            local game_name = emu.romname()
            if game_name and game_name ~= "" and game_name ~= "___empty" then
                show_controls()
                return true
            else
                print("No ROM is currently loaded, cannot show controls")
                return false
            end
        end
        return false
    end
    
    -- Register menu
    emu.register_menu(menu_callback, menu_populate, "Controls")
    
    -- Register pause handler
    if emu.register_pause then
        print("Registering pause handler")
        emu.register_pause(function()
            -- Check if a ROM is running before trying to show controls
            local game_name = emu.romname()
            if not game_name or game_name == "" or game_name == "___empty" then
                print("No ROM is loaded, skipping pause handler")
                return
            end
            
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
    
    -- Register start handler as a fallback but check for timer availability
    if emu.register_start then
        print("Registering start handler")
        emu.register_start(function()
            -- Reset precache status for new ROM
            rom_precached = false
            
            -- Directly check ROM name if timer is not available
            if not has_timer then
                local game_name = emu.romname()
                if game_name and game_name ~= "" and game_name ~= "___empty" then
                    print("ROM detected via start handler (without timer): " .. game_name)
                    precache_controls(game_name)
                else
                    print("No valid ROM name available in start handler")
                end
                return
            end
            
            -- Use a small delay to ensure MAME has fully loaded the ROM (if timer is available)
            emu.timer.pulse(1.0, function()
                local game_name = emu.romname()
                if game_name and game_name ~= "" and game_name ~= "___empty" then
                    print("ROM detected via start handler: " .. game_name)
                    precache_controls(game_name)
                else
                    print("No valid ROM name available in start handler")
                end
                return false  -- Don't repeat this timer
            end)
        end)
    end
    
    -- Reset when game stops
    emu.register_stop(function()
        user_paused = false
        rom_precached = false
        print("Controls plugin reset for next game")
    end)
    
    -- Periodic timer as a final fallback - but only if timer is available
    if has_timer then
        local periodic_timer = emu.timer.periodic(5.0, function()
            local game_name = emu.romname()
            if game_name and game_name ~= "" and game_name ~= "___empty" and game_name ~= current_rom then
                print("ROM change detected via periodic timer: " .. game_name)
                precache_controls(game_name)
            end
            return true  -- Keep timer running
        end)
        print("Periodic timer registered")
    else
        print("Timer functionality not available, skipping periodic checks")
    end
    
    print("Controls plugin loaded with timer error fix")
end

return exports
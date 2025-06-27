-- MAME Controls Menu Plugin with F9 hotkey, Start+RB gamepad support, and Precaching (Legacy API Compatible)
local exports = {}
exports.name = "controls"
exports.version = "0.4"
exports.description = "MAME Controls Display with Precaching"
exports.license = "MIT"
exports.author = { name = "Custom" }

--[[ 
CONTROLLER BUTTON MAPPING REFERENCE:

Xbox Controller / XINPUT Mapping:
  XINPUT_1_A            - A Button
  XINPUT_1_B            - B Button
  XINPUT_1_X            - X Button
  XINPUT_1_Y            - Y Button
  XINPUT_1_SHOULDER_L   - Left Bumper (LB)
  XINPUT_1_SHOULDER_R   - Right Bumper (RB)
  XINPUT_1_TRIGGER_L    - Left Trigger (LT)
  XINPUT_1_TRIGGER_R    - Right Trigger (RT)
  XINPUT_1_THUMB_L      - Left Stick Button (Press L3)
  XINPUT_1_THUMB_R      - Right Stick Button (Press R3)
  XINPUT_1_START        - Start Button
  XINPUT_1_SELECT       - Back/Select Button
  XINPUT_1_DPAD_UP      - D-Pad Up
  XINPUT_1_DPAD_DOWN    - D-Pad Down
  XINPUT_1_DPAD_LEFT    - D-Pad Left
  XINPUT_1_DPAD_RIGHT   - D-Pad Right

Generic Joystick / JOYCODE Mapping:
  JOYCODE_1_BUTTON1     - Usually A Button
  JOYCODE_1_BUTTON2     - Usually B Button
  JOYCODE_1_BUTTON3     - Usually X Button
  JOYCODE_1_BUTTON4     - Usually Y Button
  JOYCODE_1_BUTTON5     - Usually Left Bumper (LB)
  JOYCODE_1_BUTTON6     - Usually Right Bumper (RB)
  JOYCODE_1_BUTTON7     - Usually Left Trigger (LT)
  JOYCODE_1_BUTTON8     - Usually Right Trigger (RT)
  JOYCODE_1_BUTTON9     - Usually Left Stick Button (L3)
  JOYCODE_1_BUTTON10    - Usually Right Stick Button (R3)
  JOYCODE_1_BUTTON11    - Often Back/Select
  JOYCODE_1_BUTTON12    - Often Start
  JOYCODE_1_HATUP       - D-Pad Up
  JOYCODE_1_HATDOWN     - D-Pad Down
  JOYCODE_1_HATLEFT     - D-Pad Left
  JOYCODE_1_HATRIGHT    - D-Pad Right
  
For a different player's controller, change the number after JOYCODE or XINPUT.
Example: XINPUT_2_A or JOYCODE_2_BUTTON1 for player 2's controller.

INSTRUCTIONS TO CHANGE HOTKEY COMBINATION:
1. Find the current hotkey checks in the code (search for "Check Start button" and "Check RB button")
2. Replace the button codes with your preferred buttons from the lists above
3. Update the variable names and comments to match your new button choices
4. Also update the menu text to reflect your new combination

Note: Button mappings can vary between controllers and configurations.
If your hotkey doesn't work, you might need to try different button codes.
]]

function exports.startplugin()
    -- Variables to track key state
    local f9_pressed = false
    
    -- Change these variables if you're changing the button combination
    local start_pressed = false  -- Tracks Start button
    local rb_pressed = false     -- Tracks Right Bumper (RB)
    
    -- Cooldown variables to prevent immediate re-triggering
    local last_show_time = 0
    local cooldown_period = 1.0  -- 1 second cooldown
    local showing_controls = false
    
    -- Configuration variables
    local config = {
        keyboard_key = "KEYCODE_F9",
        gamepad_button1 = "JOYCODE_1_BUTTON10", -- Start button
        gamepad_button2 = "JOYCODE_1_BUTTON6",  -- RB button
        use_single_key = false,
        single_key = "KEYCODE_F9"
    }
    
    -- Menu state
    local menu_state = "main" -- "main", "config", "select_keyboard", "select_gamepad1", "select_gamepad2", "select_single"
    local key_selection_options = {}
    local selection_index = 1
    
    -- Precaching variables (from working older version)
    local user_paused = false
    local current_rom = nil
    local rom_precached = false
    local has_timer = (emu.timer ~= nil)
    
    -- Print plugin initialization info
    print("Controls plugin initializing...")
    print("Timer functionality available: " .. tostring(has_timer))
    
    -- Precaching function (adapted from working older version)
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
        
        -- Use the precache option to load data in background (updated path and executable)
        local command = string.format('"preview\\mame controls.exe" --precache --game %s', game_name)
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

    -- Function to show controls (with cooldown protection)
    local function show_controls()
        -- Get current time (approximate)
        local current_time = os.clock()
        
        -- Check cooldown period
        if current_time - last_show_time < cooldown_period then
            print("Controls cooldown active, ignoring request")
            return
        end
        
        -- Check if already showing controls
        if showing_controls then
            print("Controls already showing, ignoring request")
            return
        end
        
        -- Get the ROM name
        local game_name = emu.romname()

        -- Only proceed if we have a valid game name
        if game_name and game_name ~= "" and game_name ~= "___empty" then
            print("Showing controls for: " .. game_name)
            showing_controls = true
            last_show_time = current_time
            
            -- Pause MAME if the function exists
            if emu.pause then
                emu.pause()
            end
            
            -- Run the controls viewer (updated path and executable)
            local command = string.format('"preview\\mame controls.exe" --preview-only --game %s --screen 1 --clean-preview', game_name)
            print("Running: " .. command)
            os.execute(command)
            
            -- Reset showing flag after command completes
            showing_controls = false
            
            -- Unpause MAME if it was paused by the user
            if user_paused and emu.unpause then
                print("Unpausing MAME after controls")
                emu.unpause()
                user_paused = false
            elseif emu.unpause then
                emu.unpause()
            end
        else
            print("No valid ROM name available, cannot show controls")
        end
    end

    -- Menu population function with configuration support
    local function menu_populate()
        local menu = {}
        local game_name = emu.romname()
        
        if menu_state == "main" then
            if game_name and game_name ~= "" and game_name ~= "___empty" then
                menu[1] = {"Show Controls for " .. game_name, "", 0}
                menu[2] = {"Configure Hotkeys", "", 0}
                menu[3] = {"", "", "off"}  -- Separator
                menu[4] = {"Exit Controls: Any Keyboard or XINPUT Key", "", "off"}
            else
                menu[1] = {"Show Controls (No ROM loaded)", "", 0}
                menu[2] = {"Configure Hotkeys", "", 0}
                menu[3] = {"", "", "off"}  -- Separator
                menu[4] = {"Exit Controls: Any Keyboard or XINPUT Key", "", "off"}
            end
        elseif menu_state == "config" then
            menu[1] = {"← Back to Main Menu", "", 0}
            menu[2] = {"", "", "off"}  -- Separator
            menu[3] = {"Current Keyboard Key: " .. config.keyboard_key:gsub("KEYCODE_", ""), "", "off"}
            menu[4] = {"Current Gamepad Button 1: " .. config.gamepad_button1:gsub("JOYCODE_1_", ""), "", "off"}
            menu[5] = {"Current Gamepad Button 2: " .. config.gamepad_button2:gsub("JOYCODE_1_", ""), "", "off"}
            menu[6] = {"", "", "off"}  -- Separator
            menu[7] = {"Use Single Key Mode: " .. (config.use_single_key and "ON" or "OFF"), "", 0}
            if config.use_single_key then
                menu[8] = {"Single Key: " .. config.single_key:gsub("KEYCODE_", ""), "", "off"}
                menu[9] = {"Change Single Key", "", 0}
            else
                menu[8] = {"Change Keyboard Key", "", 0}
                menu[9] = {"Change Gamepad Button 1", "", 0}
                menu[10] = {"Change Gamepad Button 2", "", 0}
            end
        elseif menu_state == "select_keyboard" then
            menu[1] = {"← Back to Config", "", 0}
            menu[2] = {"", "", "off"}
            menu[3] = {"Select Keyboard Key:", "", "off"}
            local keyboard_options = {
                {"F1", "KEYCODE_F1"}, {"F2", "KEYCODE_F2"}, {"F3", "KEYCODE_F3"}, {"F4", "KEYCODE_F4"},
                {"F5", "KEYCODE_F5"}, {"F6", "KEYCODE_F6"}, {"F7", "KEYCODE_F7"}, {"F8", "KEYCODE_F8"},
                {"F9", "KEYCODE_F9"}, {"F10", "KEYCODE_F10"}, {"F11", "KEYCODE_F11"}, {"F12", "KEYCODE_F12"},
                {"Tab", "KEYCODE_TAB"}, {"Space", "KEYCODE_SPACE"}, {"Enter", "KEYCODE_ENTER"}
            }
            for i, option in ipairs(keyboard_options) do
                menu[i + 3] = {option[1], option[2], 0}
            end
        elseif menu_state == "select_gamepad1" or menu_state == "select_gamepad2" then
            menu[1] = {"← Back to Config", "", 0}
            menu[2] = {"", "", "off"}
            menu[3] = {"Select Gamepad Button:", "", "off"}
            local gamepad_options = {
                {"Button 1 (A)", "JOYCODE_1_BUTTON1"}, {"Button 2 (B)", "JOYCODE_1_BUTTON2"},
                {"Button 3 (X)", "JOYCODE_1_BUTTON3"}, {"Button 4 (Y)", "JOYCODE_1_BUTTON4"},
                {"Button 5 (LB)", "JOYCODE_1_BUTTON5"}, {"Button 6 (RB)", "JOYCODE_1_BUTTON6"},
                {"Button 7 (LT)", "JOYCODE_1_BUTTON7"}, {"Button 8 (RT)", "JOYCODE_1_BUTTON8"},
                {"Button 9 (L3)", "JOYCODE_1_BUTTON9"}, {"Button 10 (Start)", "JOYCODE_1_BUTTON10"},
                {"Button 11 (Select)", "JOYCODE_1_BUTTON11"}, {"Button 12", "JOYCODE_1_BUTTON12"},
                {"D-Pad Up", "JOYCODE_1_HATUP"}, {"D-Pad Down", "JOYCODE_1_HATDOWN"},
                {"D-Pad Left", "JOYCODE_1_HATLEFT"}, {"D-Pad Right", "JOYCODE_1_HATRIGHT"}
            }
            for i, option in ipairs(gamepad_options) do
                menu[i + 3] = {option[1], option[2], 0}
            end
        elseif menu_state == "select_single" then
            menu[1] = {"← Back to Config", "", 0}
            menu[2] = {"", "", "off"}
            menu[3] = {"Select Single Key:", "", "off"}
            local all_options = {
                {"F1", "KEYCODE_F1"}, {"F2", "KEYCODE_F2"}, {"F3", "KEYCODE_F3"}, {"F4", "KEYCODE_F4"},
                {"F5", "KEYCODE_F5"}, {"F6", "KEYCODE_F6"}, {"F7", "KEYCODE_F7"}, {"F8", "KEYCODE_F8"},
                {"F9", "KEYCODE_F9"}, {"F10", "KEYCODE_F10"}, {"F11", "KEYCODE_F11"}, {"F12", "KEYCODE_F12"},
                {"Tab", "KEYCODE_TAB"}, {"Space", "KEYCODE_SPACE"}, {"Enter", "KEYCODE_ENTER"},
                {"Button 1 (A)", "JOYCODE_1_BUTTON1"}, {"Button 2 (B)", "JOYCODE_1_BUTTON2"},
                {"Button 3 (X)", "JOYCODE_1_BUTTON3"}, {"Button 4 (Y)", "JOYCODE_1_BUTTON4"},
                {"Button 5 (LB)", "JOYCODE_1_BUTTON5"}, {"Button 6 (RB)", "JOYCODE_1_BUTTON6"},
                {"Button 10 (Start)", "JOYCODE_1_BUTTON10"}, {"Button 11 (Select)", "JOYCODE_1_BUTTON11"}
            }
            for i, option in ipairs(all_options) do
                menu[i + 3] = {option[1], option[2], 0}
            end
        end
        
        return menu
    end

    -- Menu callback with configuration support
    local function menu_callback(index, event)
        if event == "select" then
            if menu_state == "main" then
                if index == 1 then
                    -- Show controls
                    local game_name = emu.romname()
                    if game_name and game_name ~= "" and game_name ~= "___empty" then
                        show_controls()
                        return true
                    else
                        print("No ROM is currently loaded, cannot show controls")
                        return false
                    end
                elseif index == 2 then
                    -- Go to config menu
                    menu_state = "config"
                    return true
                end
            elseif menu_state == "config" then
                if index == 1 then
                    -- Back to main menu
                    menu_state = "main"
                    return true
                elseif index == 7 then
                    -- Toggle single key mode
                    config.use_single_key = not config.use_single_key
                    print("Single key mode: " .. (config.use_single_key and "ON" or "OFF"))
                    return true
                elseif index == 8 and not config.use_single_key then
                    -- Change keyboard key
                    menu_state = "select_keyboard"
                    return true
                elseif index == 9 then
                    if config.use_single_key then
                        -- Change single key
                        menu_state = "select_single"
                    else
                        -- Change gamepad button 1
                        menu_state = "select_gamepad1"
                    end
                    return true
                elseif index == 10 and not config.use_single_key then
                    -- Change gamepad button 2
                    menu_state = "select_gamepad2"
                    return true
                end
            elseif menu_state == "select_keyboard" then
                if index == 1 then
                    -- Back to config
                    menu_state = "config"
                    return true
                elseif index > 3 then
                    -- Get the menu item and extract the keycode from it
                    local menu = menu_populate()
                    local selected_item = menu[index]
                    if selected_item and selected_item[2] then
                        config.keyboard_key = selected_item[2]
                        print("Keyboard key changed to: " .. config.keyboard_key)
                        menu_state = "config"
                        return true
                    end
                end
            elseif menu_state == "select_gamepad1" then
                if index == 1 then
                    -- Back to config
                    menu_state = "config"
                    return true
                elseif index > 3 then
                    -- Get the menu item and extract the keycode from it
                    local menu = menu_populate()
                    local selected_item = menu[index]
                    if selected_item and selected_item[2] then
                        config.gamepad_button1 = selected_item[2]
                        print("Gamepad button 1 changed to: " .. config.gamepad_button1)
                        menu_state = "config"
                        return true
                    end
                end
            elseif menu_state == "select_gamepad2" then
                if index == 1 then
                    -- Back to config
                    menu_state = "config"
                    return true
                elseif index > 3 then
                    -- Get the menu item and extract the keycode from it
                    local menu = menu_populate()
                    local selected_item = menu[index]
                    if selected_item and selected_item[2] then
                        config.gamepad_button2 = selected_item[2]
                        print("Gamepad button 2 changed to: " .. config.gamepad_button2)
                        menu_state = "config"
                        return true
                    end
                end
            elseif menu_state == "select_single" then
                if index == 1 then
                    -- Back to config
                    menu_state = "config"
                    return true
                elseif index > 3 then
                    -- Get the menu item and extract the keycode from it
                    local menu = menu_populate()
                    local selected_item = menu[index]
                    if selected_item and selected_item[2] then
                        config.single_key = selected_item[2]
                        print("Single key changed to: " .. config.single_key)
                        menu_state = "config"
                        return true
                    end
                end
            end
        end
        return false
    end

    -- Add frame done callback to check for key combinations
    emu.register_frame_done(function()
        -- Only check if we have necessary components
        if not manager or not manager.machine then
            return false
        end
        
        local machine = manager.machine
        if not machine.input then
            return false
        end
        
        -- Get the input manager
        local input = machine.input
        
        -- Check keyboard key (configurable)
        local keyboard_state = false
        if input.seq_pressed then
            local seq = input:seq_from_tokens(config.use_single_key and config.single_key or config.keyboard_key)
            if seq then
                keyboard_state = input:seq_pressed(seq)
            end
        end
        
        if config.use_single_key then
            -- Single key mode - just check the one key
            if keyboard_state and not f9_pressed then
                show_controls()
            end
            f9_pressed = keyboard_state
        else
            -- Original F9 + gamepad combo mode
            -- ======= CONFIGURABLE GAMEPAD BUTTONS WITH FALLBACK MAPPINGS =======
            local button1_state = false
            local button2_state = false
            
            if input.seq_pressed then
                -- Check configured button 1 with multiple fallback mappings
                local seq1_primary = input:seq_from_tokens(config.gamepad_button1)
                if seq1_primary then button1_state = input:seq_pressed(seq1_primary) end
                
                -- Add fallback mappings for button 1 (Start button alternatives)
                if not button1_state and config.gamepad_button1 == "JOYCODE_1_BUTTON10" then
                    local seq1_alt1 = input:seq_from_tokens("JOYCODE_1_BUTTON12")
                    local seq1_alt2 = input:seq_from_tokens("JOYCODE_1_START")
                    if seq1_alt1 then button1_state = button1_state or input:seq_pressed(seq1_alt1) end
                    if seq1_alt2 then button1_state = button1_state or input:seq_pressed(seq1_alt2) end
                end
                
                -- Check configured button 2 with multiple fallback mappings
                local seq2_primary = input:seq_from_tokens(config.gamepad_button2)
                if seq2_primary then button2_state = input:seq_pressed(seq2_primary) end
                
                -- Add fallback mappings for button 2 (RB button alternatives)
                if not button2_state and config.gamepad_button2 == "JOYCODE_1_BUTTON6" then
                    local seq2_alt1 = input:seq_from_tokens("JOYCODE_1_BUTTON5")
                    if seq2_alt1 then button2_state = button2_state or input:seq_pressed(seq2_alt1) end
                end
            end
            
            -- Detect keyboard key press (only on press, not hold)
            if keyboard_state and not f9_pressed then
                show_controls()
            end
            
            -- Detect button combination (only trigger when both are pressed AND at least one wasn't pressed before)
            if button1_state and button2_state and (not start_pressed or not rb_pressed) then
                show_controls()
            end
            
            -- Update pressed states
            f9_pressed = keyboard_state
            start_pressed = button1_state
            rb_pressed = button2_state
        end
        
        return false  -- Keep the callback active
    end)

    -- Register menu using the LEGACY API (from working older version)
    emu.register_menu(menu_callback, menu_populate, "Controls")
    
    -- Register pause handler using LEGACY API (from working older version)
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
    
    -- Register start handler using LEGACY API (from working older version)
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
    
    -- Reset when game stops using LEGACY API (from working older version)
    emu.register_stop(function()
        user_paused = false
        rom_precached = false
        current_rom = nil
        showing_controls = false
        last_show_time = 0
        print("Controls plugin reset for next game")
    end)
    
    -- Periodic timer as a final fallback using LEGACY API (from working older version)
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
    
    print("Controls plugin loaded with precaching and hotkey support (legacy API)")
end

return exports
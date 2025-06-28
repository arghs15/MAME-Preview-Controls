-- MAME Controls Menu Plugin - Clean Version with Raw Input Codes
local exports = {}
exports.name = "controls"
exports.version = "0.7"
exports.description = "MAME Controls Display - Raw Input Codes"
exports.license = "MIT"
exports.author = { name = "Custom" }

function exports.startplugin()
    -- Variables to track key state
    local f9_pressed = false
    local start_pressed = false
    local rb_pressed = false
    
    -- Cooldown variables
    local last_show_time = 0
    local cooldown_period = 1.0
    local showing_controls = false
    
    -- Configuration variables - RAW MAME CODES
    local config = {
        single_input = "KEYCODE_F9",
        combo_button1 = "JOYCODE_1_BUTTON11",
        combo_button2 = "JOYCODE_1_BUTTON6",
        use_combo_mode = false
    }
    
    -- Menu state
    local menu_state = "main"
    local waiting_for_input = false
    local input_timeout = 0
    local input_timeout_max = 10.0
    local input_start_delay = 0
    local input_start_delay_max = 0.5
    local last_menu_key = nil
    local assignment_complete = false
    
    -- Precaching variables
    local user_paused = false
    local current_rom = nil
    local rom_precached = false
    local has_timer = (emu.timer ~= nil)
    
    print("Controls plugin initializing...")
    print("Timer functionality available: " .. tostring(has_timer))
    
    -- Function to show RAW MAME input codes only
    local function input_code_to_name(code)
        if not code then 
            return "Unknown" 
        end
        
        -- Remove KEYCODE_ prefix for keyboard
        if code:match("KEYCODE_") then
            return code:gsub("KEYCODE_", "")
        end
        
        -- Remove JOYCODE_1_ prefix for gamepad, keep raw button name
        if code:match("JOYCODE_1_") then
            return code:gsub("JOYCODE_1_", "")
        end
        
        -- Remove any other JOYCODE prefix
        if code:match("JOYCODE_") then
            return code:gsub("JOYCODE_[0-9]+_", "")
        end
        
        return code
    end
    
    -- Function to detect any pressed input
    local function detect_input()
        if not manager or not manager.machine or not manager.machine.input then
            return nil
        end
        
        local input = manager.machine.input
        if not input.seq_pressed or not input.seq_from_tokens then
            return nil
        end
        
        -- Check keyboard keys
        local keyboard_keys = {
            "KEYCODE_F1", "KEYCODE_F2", "KEYCODE_F3", "KEYCODE_F4", "KEYCODE_F5", "KEYCODE_F6",
            "KEYCODE_F7", "KEYCODE_F8", "KEYCODE_F9", "KEYCODE_F10", "KEYCODE_F11", "KEYCODE_F12",
            "KEYCODE_TAB", "KEYCODE_SPACE", "KEYCODE_ENTER", "KEYCODE_ESC", "KEYCODE_LSHIFT",
            "KEYCODE_RSHIFT", "KEYCODE_LCTRL", "KEYCODE_RCTRL", "KEYCODE_LALT", "KEYCODE_RALT",
            "KEYCODE_A", "KEYCODE_B", "KEYCODE_C", "KEYCODE_D", "KEYCODE_E", "KEYCODE_F",
            "KEYCODE_G", "KEYCODE_H", "KEYCODE_I", "KEYCODE_J", "KEYCODE_K", "KEYCODE_L",
            "KEYCODE_M", "KEYCODE_N", "KEYCODE_O", "KEYCODE_P", "KEYCODE_Q", "KEYCODE_R",
            "KEYCODE_S", "KEYCODE_T", "KEYCODE_U", "KEYCODE_V", "KEYCODE_W", "KEYCODE_X",
            "KEYCODE_Y", "KEYCODE_Z", "KEYCODE_1", "KEYCODE_2", "KEYCODE_3", "KEYCODE_4",
            "KEYCODE_5", "KEYCODE_6", "KEYCODE_7", "KEYCODE_8", "KEYCODE_9", "KEYCODE_0"
        }
        
        for _, key in ipairs(keyboard_keys) do
            local seq = input:seq_from_tokens(key)
            if seq and input:seq_pressed(seq) then
                return key
            end
        end
        
        -- Check gamepad buttons
        for controller = 1, 4 do
            -- Check numbered buttons
            for button = 1, 20 do
                local button_code = string.format("JOYCODE_%d_BUTTON%d", controller, button)
                local seq = input:seq_from_tokens(button_code)
                if seq and input:seq_pressed(seq) then
                    return button_code
                end
            end
            
            -- Check named buttons
            local named_buttons = {"START", "SELECT", "BACK", "GUIDE", "LSTICK", "RSTICK"}
            for _, button_name in ipairs(named_buttons) do
                local button_code = string.format("JOYCODE_%d_%s", controller, button_name)
                local seq = input:seq_from_tokens(button_code)
                if seq and input:seq_pressed(seq) then
                    return button_code
                end
            end
            
            -- Check D-pad
            local hat_directions = {"HATUP", "HATDOWN", "HATLEFT", "HATRIGHT"}
            for _, direction in ipairs(hat_directions) do
                local hat_code = string.format("JOYCODE_%d_%s", controller, direction)
                local seq = input:seq_from_tokens(hat_code)
                if seq and input:seq_pressed(seq) then
                    return hat_code
                end
            end
        end
        
        return nil
    end
    
    -- Precaching function
    local function precache_controls(game_name)
        if not game_name or game_name == "" or game_name == "___empty" then
            print("No valid ROM name available, skipping precache")
            return 
        end
        
        if current_rom == game_name and rom_precached then 
            print("ROM already precached: " .. game_name)
            return 
        end
        
        os.execute("echo Game detected: " .. game_name .. " > C:\\mame_plugin_log.txt")
        
        local command = string.format('"preview\\mame controls.exe" --precache --game %s', game_name)
        print("Pre-caching controls for: " .. game_name)
        
        local result = os.execute(command)
        if result then
            current_rom = game_name
            rom_precached = true
            print("Precaching complete for: " .. game_name)
        else
            print("Precaching failed for: " .. game_name)
        end
    end

    -- Function to show controls
    local function show_controls()
        local current_time = os.clock()
        
        if current_time - last_show_time < cooldown_period then
            print("Controls cooldown active, ignoring request")
            return
        end
        
        if showing_controls then
            print("Controls already showing, ignoring request")
            return
        end
        
        local game_name = emu.romname()

        if game_name and game_name ~= "" and game_name ~= "___empty" then
            print("Showing controls for: " .. game_name)
            showing_controls = true
            last_show_time = current_time
            
            if emu.pause then
                emu.pause()
            end
            
            local command = string.format('"preview\\mame controls.exe" --preview-only --game %s --screen 1 --clean-preview', game_name)
            print("Running: " .. command)
            os.execute(command)
            
            showing_controls = false
            
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

    -- Menu population function
    local function menu_populate()
        local menu = {}
        local game_name = emu.romname()
        
        if menu_state == "main" then
            if game_name and game_name ~= "" and game_name ~= "___empty" then
                menu[1] = {"Show Controls for " .. game_name, "", 0}
                menu[2] = {"Configure Hotkeys", "", 0}
                menu[3] = {"", "", "off"}
                menu[4] = {"Exit Controls: Any Keyboard or XINPUT Key", "", "off"}
            else
                menu[1] = {"Show Controls (No ROM loaded)", "", 0}
                menu[2] = {"Configure Hotkeys", "", 0}
                menu[3] = {"", "", "off"}
                menu[4] = {"Exit Controls: Any Keyboard or XINPUT Key", "", "off"}
            end
        elseif menu_state == "config" then
            menu[1] = {"← Back to Main Menu", "", 0}
            menu[2] = {"", "", "off"}
            menu[3] = {"Current Mode: " .. (config.use_combo_mode and "COMBO MODE" or "SINGLE INPUT MODE"), "", "off"}
            menu[4] = {"", "", "off"}
            if config.use_combo_mode then
                menu[5] = {"Combo Button 1: " .. input_code_to_name(config.combo_button1), "", "off"}
                menu[6] = {"Combo Button 2: " .. input_code_to_name(config.combo_button2), "", "off"}
                menu[7] = {"", "", "off"}
                menu[8] = {"Switch to Single Input Mode", "", 0}
                menu[9] = {"Change Combo Button 1", "", 0}
                menu[10] = {"Change Combo Button 2", "", 0}
            else
                menu[5] = {"Single Input: " .. input_code_to_name(config.single_input), "", "off"}
                menu[6] = {"", "", "off"}
                menu[7] = {"Switch to Combo Mode", "", 0}
                menu[8] = {"Change Single Input", "", 0}
            end
        elseif menu_state == "waiting_single" then
            menu[1] = {"← Back to Config", "", 0}
            menu[2] = {"", "", "off"}
            if input_start_delay < input_start_delay_max then
                menu[3] = {"Starting input detection...", "", "off"}
                menu[4] = {"Please wait " .. math.ceil(input_start_delay_max - input_start_delay) .. " seconds", "", "off"}
            else
                menu[3] = {"Press any key or gamepad button...", "", "off"}
                menu[4] = {"Timeout: " .. math.ceil(input_timeout_max - input_timeout) .. " seconds", "", "off"}
                menu[5] = {"(Input will be assigned when pressed)", "", "off"}
            end
        elseif menu_state == "waiting_combo1" then
            menu[1] = {"← Back to Config", "", 0}
            menu[2] = {"", "", "off"}
            if input_start_delay < input_start_delay_max then
                menu[3] = {"Starting input detection...", "", "off"}
                menu[4] = {"Please wait " .. math.ceil(input_start_delay_max - input_start_delay) .. " seconds", "", "off"}
            else
                menu[3] = {"Press any gamepad button for Combo Button 1...", "", "off"}
                menu[4] = {"Timeout: " .. math.ceil(input_timeout_max - input_timeout) .. " seconds", "", "off"}
                menu[5] = {"(Button will be assigned when pressed)", "", "off"}
            end
        elseif menu_state == "waiting_combo2" then
            menu[1] = {"← Back to Config", "", 0}
            menu[2] = {"", "", "off"}
            if input_start_delay < input_start_delay_max then
                menu[3] = {"Starting input detection...", "", "off"}
                menu[4] = {"Please wait " .. math.ceil(input_start_delay_max - input_start_delay) .. " seconds", "", "off"}
            else
                menu[3] = {"Press any gamepad button for Combo Button 2...", "", "off"}
                menu[4] = {"Timeout: " .. math.ceil(input_timeout_max - input_timeout) .. " seconds", "", "off"}
                menu[5] = {"(Button will be assigned when pressed)", "", "off"}
            end
        end
        
        return menu
    end

    -- Menu callback function
    local function menu_callback(index, event)
        if assignment_complete then
            assignment_complete = false
            menu_state = "config"
            print("Menu callback: Returning to config screen")
            return true
        end
        
        if event == "select" then
            if menu_state == "main" then
                if index == 1 then
                    local game_name = emu.romname()
                    if game_name and game_name ~= "" and game_name ~= "___empty" then
                        show_controls()
                        return true
                    else
                        print("No ROM is currently loaded, cannot show controls")
                        return false
                    end
                elseif index == 2 then
                    menu_state = "config"
                    return true
                end
            elseif menu_state == "config" then
                if index == 1 then
                    menu_state = "main"
                    return true
                elseif index == 7 then
                    config.use_combo_mode = not config.use_combo_mode
                    print("Mode switched to: " .. (config.use_combo_mode and "COMBO" or "SINGLE INPUT"))
                    return true
                elseif index == 8 then
                    if config.use_combo_mode then
                        config.use_combo_mode = false
                        print("Switched to single input mode")
                    else
                        menu_state = "waiting_single"
                        waiting_for_input = true
                        input_timeout = 0
                        input_start_delay = 0
                        last_menu_key = nil
                        print("Starting single input detection...")
                    end
                    return true
                elseif index == 9 and config.use_combo_mode then
                    menu_state = "waiting_combo1"
                    waiting_for_input = true
                    input_timeout = 0
                    input_start_delay = 0
                    last_menu_key = nil
                    print("Starting combo button 1 detection...")
                    return true
                elseif index == 10 and config.use_combo_mode then
                    menu_state = "waiting_combo2"
                    waiting_for_input = true
                    input_timeout = 0
                    input_start_delay = 0
                    last_menu_key = nil
                    print("Starting combo button 2 detection...")
                    return true
                end
            elseif menu_state:match("waiting_") then
                if index == 1 then
                    waiting_for_input = false
                    input_timeout = 0
                    input_start_delay = 0
                    last_menu_key = nil
                    assignment_complete = false
                    menu_state = "config"
                    print("Input detection cancelled")
                    return true
                end
            end
        end
        return false
    end

    -- Frame callback for input detection and hotkey checking
    emu.register_frame_done(function()
        if not manager or not manager.machine then
            return false
        end
        
        local machine = manager.machine
        if not machine.input then
            return false
        end
        
        -- Handle input detection when waiting
        if waiting_for_input then
            if input_start_delay < input_start_delay_max then
                input_start_delay = input_start_delay + 0.016
                return false
            end
            
            input_timeout = input_timeout + 0.016
            
            if input_timeout > input_timeout_max then
                print("Input detection timed out")
                waiting_for_input = false
                input_timeout = 0
                input_start_delay = 0
                last_menu_key = nil
                menu_state = "config"
                return false
            end
            
            local detected_input = detect_input()
            if detected_input then
                print("Raw detected input: " .. detected_input)
                
                local should_ignore = false
                if input_start_delay < 1.0 then
                    if detected_input == "KEYCODE_ENTER" then
                        should_ignore = true
                        print("Ignoring Enter key (used for menu navigation)")
                    end
                end
                
                if should_ignore then
                    return false
                end
                
                print("Processing input: " .. detected_input)
                
                if menu_state == "waiting_single" then
                    config.single_input = detected_input
                    print("SUCCESS: Single input set to: " .. input_code_to_name(detected_input))
                    last_show_time = os.clock()
                    waiting_for_input = false
                    input_timeout = 0
                    input_start_delay = 0
                    last_menu_key = nil
                    assignment_complete = true
                    print("Assignment complete flag set")
                    return false
                elseif menu_state == "waiting_combo1" then
                    if detected_input:match("JOYCODE_") then
                        config.combo_button1 = detected_input
                        print("SUCCESS: Combo button 1 set to: " .. input_code_to_name(detected_input))
                        waiting_for_input = false
                        input_timeout = 0
                        input_start_delay = 0
                        last_menu_key = nil
                        assignment_complete = true
                        print("Assignment complete flag set")
                        return false
                    else
                        print("Rejected: Combo buttons must be gamepad inputs")
                    end
                elseif menu_state == "waiting_combo2" then
                    if detected_input:match("JOYCODE_") then
                        config.combo_button2 = detected_input
                        print("SUCCESS: Combo button 2 set to: " .. input_code_to_name(detected_input))
                        waiting_for_input = false
                        input_timeout = 0
                        input_start_delay = 0
                        last_menu_key = nil
                        assignment_complete = true
                        print("Assignment complete flag set")
                        return false
                    else
                        print("Rejected: Combo buttons must be gamepad inputs")
                    end
                end
            end
            return false
        end
        
        -- Check for hotkey activation
        local input = machine.input
        
        local input_state = false
        if input.seq_pressed then
            local seq = input:seq_from_tokens(config.single_input)
            if seq then
                input_state = input:seq_pressed(seq)
            end
        end
        
        if not config.use_combo_mode then
            -- Single input mode
            if input_state and not f9_pressed then
                show_controls()
            end
            f9_pressed = input_state
        else
            -- Combo mode
            local button1_state = false
            local button2_state = false
            
            if input.seq_pressed then
                local seq1 = input:seq_from_tokens(config.combo_button1)
                if seq1 then button1_state = input:seq_pressed(seq1) end
                
                local seq2 = input:seq_from_tokens(config.combo_button2)
                if seq2 then button2_state = input:seq_pressed(seq2) end
            end
            
            if button1_state and button2_state and (not start_pressed or not rb_pressed) then
                show_controls()
            end
            
            start_pressed = button1_state
            rb_pressed = button2_state
        end
        
        return false
    end)

    -- Register menu
    emu.register_menu(menu_callback, menu_populate, "Controls")
    
    -- Register pause handler
    if emu.register_pause then
        print("Registering pause handler")
        emu.register_pause(function()
            local game_name = emu.romname()
            if not game_name or game_name == "" or game_name == "___empty" then
                print("No ROM is loaded, skipping pause handler")
                return
            end
            
            if not user_paused then
                user_paused = true
                print("User paused MAME")
                show_controls()
            else
                user_paused = false
                print("MAME unpaused")
            end
        end)
    else
        print("emu.register_pause not available in this MAME version")
    end
    
    -- Register start handler
    if emu.register_start then
        print("Registering start handler")
        emu.register_start(function()
            rom_precached = false
            
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
            
            emu.timer.pulse(1.0, function()
                local game_name = emu.romname()
                if game_name and game_name ~= "" and game_name ~= "___empty" then
                    print("ROM detected via start handler: " .. game_name)
                    precache_controls(game_name)
                else
                    print("No valid ROM name available in start handler")
                end
                return false
            end)
        end)
    end
    
    -- Register stop handler
    emu.register_stop(function()
        user_paused = false
        rom_precached = false
        current_rom = nil
        showing_controls = false
        last_show_time = 0
        waiting_for_input = false
        input_timeout = 0
        input_start_delay = 0
        last_menu_key = nil
        assignment_complete = false
        print("Controls plugin reset for next game")
    end)
    
    -- Periodic timer fallback
    if has_timer then
        local periodic_timer = emu.timer.periodic(5.0, function()
            local game_name = emu.romname()
            if game_name and game_name ~= "" and game_name ~= "___empty" and game_name ~= current_rom then
                print("ROM change detected via periodic timer: " .. game_name)
                precache_controls(game_name)
            end
            return true
        end)
        print("Periodic timer registered")
    else
        print("Timer functionality not available, skipping periodic checks")
    end
    
    print("Controls plugin loaded - Raw MAME input codes only")
end

return exports
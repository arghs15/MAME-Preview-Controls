-- MAME Controls Menu Plugin with F9 hotkey and Start+RB gamepad support
local exports = {}
exports.name = "controls"
exports.version = "0.3"
exports.description = "MAME Controls Display"
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

    -- Function to show controls
    local function show_controls()
        -- Get the ROM name
        local game_name = emu.romname()

        -- Only proceed if we have a valid game name
        if game_name and game_name ~= "" and game_name ~= "___empty" then
            -- Pause MAME if the function exists
            if emu.pause then
                emu.pause()
            end
            
            -- Run the controls viewer
            local command = string.format('pythonw "MAME Controls.pyw" --preview-only --game %s --screen 1', game_name)
            os.execute(command)
            
            -- Unpause MAME if the function exists
            if emu.unpause then
                emu.unpause()
            end
        end
    end

    -- Simple menu with one option
    local function make_menu()
        local menu = {}
        -- Update this text if you change the button combination
        menu[1] = {"Show Controls (F9 or Start+RB)", "", 0}
        return menu
    end

    -- Menu callback function - handles menu selections
    local function menu_callback(index, event)
        if event == "select" then
            show_controls()
            return true
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
        
        -- Check F9 key
        local f9_state = false
        if input.seq_pressed then
            -- Create a sequence for F9 key
            local seq = input:seq_from_tokens("KEYCODE_F9")
            if seq then
                f9_state = input:seq_pressed(seq)
            end
        end
        
        -- ======= FIRST HOTKEY BUTTON =======
        -- Check Start button (CHANGE THIS SECTION FOR DIFFERENT BUTTON)
        local start_state = false
        if input.seq_pressed then
            -- Try multiple mappings for Start button
            local seq_start1 = input:seq_from_tokens("JOYCODE_1_BUTTON10")  -- Common mapping
            local seq_start2 = input:seq_from_tokens("JOYCODE_1_START")     -- Alternative mapping
            local seq_start3 = input:seq_from_tokens("JOYCODE_1_BUTTON12")  -- Another common mapping
            local seq_xinput = input:seq_from_tokens("XINPUT_1_START")      -- XInput mapping
            
            -- Check all possible mappings (replace these if using different buttons)
            if seq_start1 then start_state = start_state or input:seq_pressed(seq_start1) end
            if seq_start2 then start_state = start_state or input:seq_pressed(seq_start2) end
            if seq_start3 then start_state = start_state or input:seq_pressed(seq_start3) end
            if seq_xinput then start_state = start_state or input:seq_pressed(seq_xinput) end
        end
        
        -- ======= SECOND HOTKEY BUTTON =======
        -- Check RB button (CHANGE THIS SECTION FOR DIFFERENT BUTTON)
        local rb_state = false
        if input.seq_pressed then
            -- Try multiple mappings for RB button
            local seq_rb1 = input:seq_from_tokens("JOYCODE_1_BUTTON6")         -- Common mapping
            local seq_rb2 = input:seq_from_tokens("XINPUT_1_SHOULDER_R")       -- XInput mapping
            
            -- Check all possible mappings (replace these if using different buttons)
            if seq_rb1 then rb_state = rb_state or input:seq_pressed(seq_rb1) end
            if seq_rb2 then rb_state = rb_state or input:seq_pressed(seq_rb2) end
        end
        
        -- Detect F9 key press
        if f9_state and not f9_pressed then
            show_controls()
        end
        
        -- Detect button combination (only trigger when both are pressed)
        -- CHANGE THIS CONDITION IF USING DIFFERENT BUTTONS
        if start_state and rb_state and (not start_pressed or not rb_pressed) then
            show_controls()
        end
        
        -- Update pressed states
        f9_pressed = f9_state
        start_pressed = start_state
        rb_pressed = rb_state
        
        return false  -- Keep the callback active
    end)

    -- Register our menu with MAME
    emu.register_menu(menu_callback, make_menu, "Controls")
end

return exports
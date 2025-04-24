-- license:BSD-3-Clause
-- copyright-holders:Miodrag Milanovic
-- Universal MAME boot.lua with fallback to Controls-only mode

require('lfs')

-- Set up basic environment
_G._ = emu.lang_translate
_G._p = emu.lang_translate
_G.N_ = function (message) return message end
_G.N_p = function (context, message) return message end

-- Try to load all plugins using the full loader
local success = pcall(function()
    -- add helper to lfs for plugins to use
    function lfs.env_replace(str)
        local pathsep = package.config:sub(1,1)
        local function dorep(val)
            ret = os.getenv(val)
            if ret then
                return ret
            end
            return val
        end
        if pathsep == '\\' then
            str = str:gsub("%%(%w+)%%", dorep)
        else
            str = str:gsub("%$(%w+)", dorep)
        end
        return str
    end
    
    local dir = lfs.env_replace(manager:options().entries.pluginspath:value())
    package.path = dir .. "/?.lua;" .. dir .. "/?/init.lua"
    local json = require('json')
    local function readAll(file)
        local f = io.open(file, "rb")
        local content = f:read("*all")
        f:close()
        return content
    end
    for file in lfs.dir(dir) do
        if (file~="." and file~=".." and lfs.attributes(dir .. "/" .. file,"mode")=="directory") then
            local filename = dir .. "/" .. file .. "/plugin.json"
            if lfs.attributes(filename, "mode") == "file" then
                local content = readAll(filename)
                local meta = json.parse(content)
                if (meta["plugin"]["type"]=="plugin") then
                    local plugin_enabled = false
                    
                    -- Try both ways of checking if a plugin is enabled
                    if mame_manager and mame_manager:plugins().entries[meta["plugin"]["name"]] then
                        plugin_enabled = mame_manager:plugins().entries[meta["plugin"]["name"]]:value()
                    else
                        -- Default to enabled if we can't check
                        plugin_enabled = true
                    end
                    
                    if plugin_enabled then
                        print("Starting plugin " .. meta["plugin"]["name"] .. "...")
                        plugin = require(meta["plugin"]["name"])
                        if plugin.set_folder~=nil then plugin.set_folder(dir .. "/" .. file) end
                        plugin.startplugin();
                    end
                end
            end
        end
    end
end)

-- If the full loading method failed, fall back to Controls-only mode
if not success then
    print("Full plugin loading failed, falling back to Controls-only mode")
    
    -- Create plugin table if it doesn't exist
    if not emu.plugin then
        _G.emu.plugin = {}
    end
    
    -- Hard-code plugin path
    local plugin_path = "plugins"
    
    -- Set up package path
    package.path = plugin_path .. "/?.lua;" .. plugin_path .. "/?/init.lua"
    
    -- Load only the Controls plugin
    local success, controls = pcall(require, "controls")
    if success and controls then
        print("Controls plugin loaded successfully")
        
        if controls.set_folder then
            controls.set_folder(plugin_path .. "/controls")
        end
        
        controls.startplugin()
    else
        print("Failed to load Controls plugin: " .. tostring(controls))
    end
end

print("boot.lua completed")
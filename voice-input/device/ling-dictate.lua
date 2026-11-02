-- 小聆听写 · 设备端界面
-- 作用：在板子屏幕上显示听写状态和最近一句识别结果，按键可开关电脑端听写。
-- 前提：电脑端「小聆听写」已运行且开启联动（默认 8898 端口），板子与电脑在同一 WiFi。
-- 用法：托盘菜单「在设备上开启听写」或
--       adb push ling-dictate.lua /miniapp/ling-dictate.lua
-- 说明：打开本小应用 = 电脑端进入听写模式；退出（长按功能键 3 秒）= 关闭听写。

local PC_HOST = "192.168.1.86"
local PC_PORT = 8898

local BASE_URL = "http://" .. PC_HOST .. ":" .. PC_PORT
local POLL_INTERVAL_MS = 500

local COL_BG = 0x0D1417
local COL_CARD = 0x1B2A30
local COL_LINE = 0x1E2A2E
local COL_TITLE = 0xEAF3EF
local COL_SUB = 0x8FA3A0
local COL_ACCENT = 0x4EE1A0
local COL_WARN = 0xF0B35C
local COL_ERROR = 0xF2646B

local state = "offline"
local armed = false
local last_text = ""
local levels = {}
local pending_id = nil
local wait_ms = 0
local dirty = true

-- 状态文字保持 5 个汉字以内，才能放进右上角胶囊
local function state_label(code)
    if code == "offline" then
        return "未连接", COL_SUB
    end
    if not armed then
        return "待命", COL_SUB
    end
    if code == "listening" then
        return "听写中", COL_ACCENT
    elseif code == "recognizing" then
        return "识别中", COL_WARN
    elseif code == "loading" then
        return "加载中", COL_WARN
    elseif code == "error" then
        return "出错", COL_ERROR
    end
    return "待命", COL_SUB
end

local function level_now()
    local n = #levels
    if n == 0 then
        return 0
    end
    local v = levels[n]
    if type(v) ~= "number" or v < 0 then
        return 0
    end
    if v > 1 then
        return 1
    end
    return v
end

-- 按字节切行，避免把一个 UTF-8 汉字切成两半
local function wrap_text(text, max_bytes, max_lines)
    local lines = {}
    local i = 1
    local n = #text
    while i <= n and #lines < max_lines do
        local stop = i + max_bytes - 1
        if stop >= n then
            lines[#lines + 1] = string.sub(text, i, n)
            break
        end
        while stop > i do
            local b = string.byte(text, stop + 1)
            if b == nil or b < 0x80 or b >= 0xC0 then
                break
            end
            stop = stop - 1
        end
        lines[#lines + 1] = string.sub(text, i, stop)
        i = stop + 1
    end
    if #lines == 0 then
        lines[1] = ""
    end
    return lines
end

-- ===== 绘制兼容层 =====
-- 设备固件是 API 5（圆、弧、圆角、对齐都能用）；
-- LingClaw SDK / 模拟器只到 API 4（只有 begin/rect/text/present），这里自动降级。
local API_VERSION = (app and app.api_version) or 2
local RICH = API_VERSION >= 5 and screen.circle ~= nil

local function text_width(s)
    local w = 0
    local i = 1
    while i <= #s do
        local b = string.byte(s, i)
        if b == nil then
            break
        end
        if b < 0x80 then
            w = w + 8
            i = i + 1
        elseif b < 0xE0 then
            w = w + 8
            i = i + 2
        elseif b < 0xF0 then
            w = w + 16
            i = i + 3
        else
            w = w + 16
            i = i + 4
        end
    end
    return w
end

local function rect(x, y, w, h, color, options)
    if RICH and options then
        screen.rect(x, y, w, h, color, options)
    else
        screen.rect(x, y, w, h, color)
    end
end

local function text(s, x, y, color, options)
    if RICH and options then
        screen.text(s, x, y, color, options)
    else
        screen.text(s, x, y, color)
    end
end

local function text_center(s, box_x, box_w, y, color)
    if RICH then
        text(s, box_x, y, color, { width = box_w, align = "center" })
    else
        local x = box_x + math.floor((box_w - text_width(s)) / 2)
        if x < box_x then
            x = box_x
        end
        text(s, x, y, color)
    end
end

local function draw()
    local label, color = state_label(state)
    local level = level_now()

    if RICH then
        screen.begin(COL_BG, { ordered = true })
    else
        screen.begin(COL_BG)
    end

    -- 标题 + 状态胶囊
    text("小聆听写", 14, 10, COL_TITLE)
    rect(148, 7, 80, 26, COL_CARD, { radius = 13 })
    text_center(label, 148, 80, 12, color)

    -- 麦克风图标：API 5 用圆+弧+圆角；API 4 用矩形拼
    if RICH then
        screen.circle(120, 90, 40, COL_LINE, { fill = false, border_width = 2 })
        if level > 0.02 then
            screen.circle(120, 90, 40, color, {
                fill = false,
                border_width = 4,
                opacity = 60 + math.floor(level * 195),
            })
        end
        screen.circle(120, 90, 30, 0x14232A)
        rect(112, 72, 16, 30, color, { radius = 8 })
        screen.arc(120, 90, 19, 0, 180, color, { width = 3 })
        screen.line(120, 109, 120, 117, color, { width = 3 })
    else
        -- 简单画法：胶囊用三条矩形叠出来，支架用细矩形
        local cap_h = 6 + math.floor(level * 18)
        rect(110, 92 - cap_h, 20, cap_h, color)
        rect(114, 92 - cap_h - 4, 12, 4, color)
        rect(114, 92, 12, 4, color)
        rect(102, 98, 36, 3, color)
        rect(118, 101, 4, 9, color)
    end

    -- 最近一句
    if last_text ~= "" then
        -- 216px 宽约 13 个汉字，按 39 字节切才不会和下一行叠；API 4 每帧最多 8 段文字
        local lines = wrap_text(last_text, 39, RICH and 3 or 2)
        for i = 1, #lines do
            text_center(lines[i], 12, 216, 142 + (i - 1) * 22, COL_TITLE)
        end
    else
        text_center("对着板子说话", 12, 216, 150, COL_SUB)
        text_center("文字会落到光标处", 12, 216, 172, COL_SUB)
    end

    -- 底部提示
    rect(14, 206, 212, 1, COL_LINE)
    text_center("功能键开关　长按3秒退出", 12, 216, 214, COL_SUB)

    screen.present()
    dirty = false
end

local function request_state()
    pending_id = http.get(BASE_URL .. "/state", { timeout_ms = 800 })
end

local function request_mode(on)
    pending_id = http.request({
        url = BASE_URL .. (on and "/arm" or "/disarm"),
        method = "POST",
        headers = { ["Content-Type"] = "application/json" },
        body = "{}",
        timeout_ms = 800,
    })
end

local function request_toggle()
    pending_id = http.request({
        url = BASE_URL .. "/toggle",
        method = "POST",
        headers = { ["Content-Type"] = "application/json" },
        body = "{}",
        timeout_ms = 800,
    })
end

function on_start()
    draw()
    -- 打开本应用 = 开始听写（关闭/退出会回到待命）
    request_mode(true)
end

function on_exit()
    -- 退出小应用 = 关闭听写模式（能发就发，不依赖结果）
    http.request({
        url = BASE_URL .. "/disarm",
        method = "POST",
        headers = { ["Content-Type"] = "application/json" },
        body = "{}",
        timeout_ms = 500,
    })
end

function on_tick(dt_ms)
    if pending_id == nil then
        wait_ms = wait_ms + dt_ms
        if wait_ms >= POLL_INTERVAL_MS then
            wait_ms = 0
            request_state()
        end
    end
    if dirty then
        draw()
    end
end

function on_button_click(button_id)
    if button_id ~= "function" then
        return
    end
    if pending_id ~= nil then
        return
    end
    request_toggle()
end

function on_http_response(request_id, response)
    if request_id ~= pending_id then
        return
    end
    pending_id = nil
    if response.error ~= nil then
        state = "offline"
        dirty = true
        return
    end
    if response.status ~= 200 then
        state = "offline"
        dirty = true
        return
    end
    local data = json.decode(response.body)
    if type(data) ~= "table" then
        state = "offline"
        dirty = true
        return
    end
    if type(data.state) == "string" then
        state = data.state
    end
    if type(data.armed) == "boolean" then
        armed = data.armed
    end
    if type(data.text) == "string" then
        last_text = data.text
    end
    if type(data.levels) == "table" then
        levels = data.levels
    end
    dirty = true
end

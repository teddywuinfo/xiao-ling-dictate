# 固件改动（可选）

本项目对上游 **LISTENAI arcs_mini**（tag `mini-v3.1.0`，board `arcs_mini3`）做了两处小改动，用于：

1. 把云端识别文本通过 UDP 广播给电脑（无线听写）
2. 把「小聆听写」Lua 小应用编进固件，支持语音指令本地启动

**不包含厂商 SDK 本体**——请先自行克隆上游：

```bash
git clone https://cloud.listenai.com/CSKG836746/arcs-sdk/public/arcs_mini
cd arcs_mini
git checkout mini-v3.1.0
```

## 1. 放入新增文件

把 `src/server/lschat_server/` 下的文件复制到上游同名目录：

```
dictate_bridge.c
dictate_bridge.h
dictate_app.c
dictate_app.h
dictate_app_lua.h   ← 由 voice-input/tools/gen_dictate_app_header.py 从 device/ling-dictate.lua 生成
```

## 2. 应用补丁

```bash
git apply firmware-changes.patch
```

补丁内容：

- `voice_cloud.c`：在 `SESSION_VOICE_IAT` 缓存识别文本并调用 `dictate_app_handle_text()`；`IAT_END` / 会话结束时调用 `dictate_bridge_send_text()`
- `CMakeLists.txt`：加入两个新源文件
- `adb_download.ps1`：`adb push` 的 stderr 重定向（修 Windows PowerShell 5.1 中断问题）

## 3. 编译与烧录

> ⚠️ 仓库路径不要带中文，否则 3.1.0 新增的 `objcopy` 步骤会失败。

```powershell
subst X: "D:\path\to"
cd X:\arcs_mini
.\build.ps1 -S .\apps\arcs-mini -B build-dictate3 -DBOARD=arcs_mini3
.\adb_download.ps1 -S res\arcs-mini3 -B build-dictate3 app
```

如果 `adb_download.ps1` 中途中断，手工收尾（顺序不能改）：

```powershell
adb push build-dictate3\arcs-mini.bin /RAW/NAND/600000
adb shell recovery exit
adb -s BOOT-xxxx shell reboot
```

进 Recovery：USB 插着 → 按住功能键 → 短按 RST → 松开功能键。

## 复现 `dictate_app_lua.h`

改了 `voice-input/device/ling-dictate.lua` 之后：

```powershell
python voice-input\tools\gen_dictate_app_header.py
```

## 语音指令

| 说 | 效果 |
| --- | --- |
| 打开听写 / 开始听写 / 启动小聆… | 本地启动听写小应用（命中后掐掉云端那句「没有这个应用」） |
| 关闭听写 / 结束听写 | 退出小应用 |

关键词表在 `dictate_app.c` 的 `is_dictate_subject()` / `is_start_action()` 里。

/*
 * 语音指令拉起内置的「小聆听写」小应用。
 *
 * 设备在云端识别到「打开小聆听写 / 开始听写」这类话时，直接用固件里内置的 Lua
 * 启动小应用；说「关闭听写 / 结束听写」则退出小应用。电脑端只负责收字上屏。
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/** 云端识别的文本进来后调用；不是听写指令就静默返回。 */
void dictate_app_handle_text(const char *text);

#ifdef __cplusplus
}
#endif

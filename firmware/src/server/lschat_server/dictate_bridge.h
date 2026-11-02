/*
 * 无线听写：把云端识别到的文字广播给同一局域网里的电脑端「小聆听写」。
 *
 * 数据格式（UDP，端口 8899，JSON 单行）：
 *   {"app":"xl-dictate","type":"iat","seq":12,"text":"今天下午三点开会"}
 *
 * 默认发往 255.255.255.255；如果 KV 里配置了 user.dictate_ip，会额外单播一份，
 * 用于路由器隔离广播的场景：
 *   adb shell kv set user.dictate_ip string 192.168.1.86
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/** 发送一句识别结果，失败时只记日志，不影响语音主流程。 */
void dictate_bridge_send_text(const char *text);

#ifdef __cplusplus
}
#endif

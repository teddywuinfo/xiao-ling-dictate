/*
 * 无线听写：把云端识别文本通过 UDP 发给电脑端。
 */

#define TAG "dictate-bridge"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "lisa_kv.h"
#include "lisa_log.h"

#include "dictate_bridge.h"

#define DICTATE_PORT        8899
#define DICTATE_TEXT_MAX    900
#define DICTATE_PAYLOAD_MAX 1024
#define KV_KEY_DICTATE_IP   "user.dictate_ip"

static int s_sock = -1;
static uint32_t s_seq;
static char s_unicast_ip[32];
static bool s_unicast_loaded;

static int ensure_socket(void)
{
    if (s_sock >= 0) {
        return s_sock;
    }

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        LOGW("udp socket create failed");
        return -1;
    }

    int enable = 1;
    (void)setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &enable, sizeof(enable));

    int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0) {
        (void)fcntl(sock, F_SETFL, flags | O_NONBLOCK);
    }

    s_sock = sock;
    return s_sock;
}

static const char *unicast_ip(void)
{
    if (!s_unicast_loaded) {
        s_unicast_loaded = true;
        char *value = NULL;
        if (lisa_kv_get_string(KV_KEY_DICTATE_IP, &value) == 0 && value != NULL) {
            strncpy(s_unicast_ip, value, sizeof(s_unicast_ip) - 1U);
            lisa_kv_free(value);
        }
    }
    return s_unicast_ip;
}

static size_t escape_json(const char *text, char *out, size_t out_size)
{
    size_t used = 0;

    for (size_t i = 0; text[i] != '\0'; i++) {
        unsigned char c = (unsigned char)text[i];
        if (c == '"' || c == '\\') {
            if (used + 2U >= out_size) {
                break;
            }
            out[used++] = '\\';
            out[used++] = (char)c;
        } else if (c < 0x20U) {
            if (used + 6U >= out_size) {
                break;
            }
            int written = snprintf(out + used, out_size - used, "\\u%04x", (unsigned)c);
            if (written <= 0) {
                break;
            }
            used += (size_t)written;
        } else {
            if (used + 1U >= out_size) {
                break;
            }
            out[used++] = (char)c;
        }
    }

    out[used] = '\0';
    return used;
}

void dictate_bridge_send_text(const char *text)
{
    if (text == NULL || text[0] == '\0') {
        return;
    }

    int sock = ensure_socket();
    if (sock < 0) {
        return;
    }

    char escaped[DICTATE_TEXT_MAX];
    (void)escape_json(text, escaped, sizeof(escaped));

    char payload[DICTATE_PAYLOAD_MAX];
    int len = snprintf(payload, sizeof(payload),
                       "{\"app\":\"xl-dictate\",\"type\":\"iat\",\"seq\":%u,\"text\":\"%s\"}",
                       (unsigned)(++s_seq), escaped);
    if (len <= 0 || (size_t)len >= sizeof(payload)) {
        LOGW("payload too long, dropped");
        return;
    }

    struct sockaddr_in dst;
    memset(&dst, 0, sizeof(dst));
    dst.sin_family = AF_INET;
    dst.sin_port = htons(DICTATE_PORT);
    dst.sin_addr.s_addr = htonl(INADDR_BROADCAST);
    (void)sendto(sock, payload, (size_t)len, 0, (struct sockaddr *)&dst, sizeof(dst));

    const char *ip = unicast_ip();
    if (ip[0] != '\0') {
        dst.sin_addr.s_addr = inet_addr(ip);
        if (dst.sin_addr.s_addr != INADDR_NONE) {
            (void)sendto(sock, payload, (size_t)len, 0, (struct sockaddr *)&dst, sizeof(dst));
        }
    }

    LOGI("sent iat to pc: %s", text);
}

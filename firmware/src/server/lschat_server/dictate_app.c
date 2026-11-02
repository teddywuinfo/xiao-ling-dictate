/*
 * 语音指令拉起内置的「小聆听写」小应用。
 */

#define TAG "dictate-app"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "FreeRTOS.h"
#include "task.h"

#include "lisa_log.h"
#include "miniapp.h"
#include "voice_msg.h"
#include "voice_player/voice_player_tts.h"

#include "dictate_app.h"
#include "dictate_app_lua.h"

#define DICTATE_APP_TASK_STACK 4096
#define DICTATE_APP_TASK_PRIO  5

static volatile bool s_launching;

static bool has(const char *text, const char *word)
{
    return text != NULL && word != NULL && strstr(text, word) != NULL;
}

/* 只处理明确针对听写的句子，避免把普通对话当成指令 */
static bool is_dictate_subject(const char *text)
{
    return has(text, "听写") || has(text, "小聆") || has(text, "小林") || has(text, "小玲") ||
           has(text, "小琳") || has(text, "语音输入") || has(text, "录音");
}

static bool is_start_action(const char *text)
{
    return has(text, "打开") || has(text, "开始") || has(text, "启动") || has(text, "开启");
}

static bool is_stop_action(const char *text)
{
    return has(text, "关闭") || has(text, "结束") || has(text, "停止") || has(text, "退出");
}

static void dictate_app_task(void *argument)
{
    (void)argument;

    miniapp_package_t package;
    char error[128] = {0};

    memset(&package, 0, sizeof(package));
    strncpy(package.id, DICTATE_APP_ID, sizeof(package.id) - 1U);
    strncpy(package.version, DICTATE_APP_VERSION, sizeof(package.version) - 1U);
    strncpy(package.name, "xiaoling-dictate", sizeof(package.name) - 1U);
    strncpy(package.hash, DICTATE_APP_MD5, sizeof(package.hash) - 1U);
    package.size = DICTATE_APP_LUA_SIZE;

    if (!miniapp_install_begin()) {
        LOGW("install begin rejected, runtime busy");
        s_launching = false;
        vTaskDelete(NULL);
        return;
    }

    if (miniapp_matches(&package)) {
        LOGI("dictate app already running");
    } else if (miniapp_install(&package, (const char *)k_dictate_app_lua, error, sizeof(error)) != 0) {
        LOGW("dictate app install failed: %s", error);
    } else {
        LOGI("dictate app started by voice");
    }

    miniapp_install_end();
    s_launching = false;
    vTaskDelete(NULL);
}

void dictate_app_handle_text(const char *text)
{
    if (text == NULL || text[0] == '\0') {
        return;
    }
    if (!is_dictate_subject(text)) {
        return;
    }

    if (is_stop_action(text) && !is_start_action(text)) {
        LOGI("voice stop dictate: %s", text);
        (void)miniapp_exit();
        return;
    }

    if (!is_start_action(text) || s_launching) {
        return;
    }

    LOGI("voice start dictate: %s", text);

    /*
     * 云端并不认识这个本地小应用，会照常回一句「没有这个应用」。
     * 本地已经把它拉起来了，这里顺手结束这一轮对话并掐掉 TTS，避免自相矛盾。
     */
    voice_player_tts_stop_async();
    voice_msg_pub(VOICE_MSG_CLOUD_MCP_CHAT_EXIT, NULL, 0);

    s_launching = true;
    if (xTaskCreate(dictate_app_task, "dictate_app", DICTATE_APP_TASK_STACK, NULL,
                    DICTATE_APP_TASK_PRIO, NULL) != pdPASS) {
        s_launching = false;
        LOGW("create dictate_app task failed");
    }
}

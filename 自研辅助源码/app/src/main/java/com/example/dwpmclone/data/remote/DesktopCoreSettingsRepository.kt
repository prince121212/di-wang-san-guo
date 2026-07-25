package com.example.dwpmclone.data.remote

import android.content.Context
import java.util.UUID

/**
 * Connection settings for the desktop-authoritative execution core.
 *
 * The API token grants control of the desktop assistant, but it is not a game
 * session/token.  It is stored only in this application's private preferences
 * and is never copied into GameSession.channelExtra or task logs.
 */
data class DesktopCoreSettings(
    val enabled: Boolean,
    val baseUrl: String,
    val apiToken: String,
    val deviceId: String
) {
    val normalizedBaseUrl: String
        get() = baseUrl.trim().trimEnd('/')

    fun validationError(): String? = when {
        !enabled -> "电脑端核心尚未启用"
        normalizedBaseUrl.isBlank() -> "请输入电脑端地址"
        !normalizedBaseUrl.startsWith("http://") && !normalizedBaseUrl.startsWith("https://") ->
            "电脑端地址必须以 http:// 或 https:// 开头"
        apiToken.isBlank() -> "请输入电脑端 Mobile API Token"
        deviceId.isBlank() -> "设备身份不能为空"
        else -> null
    }
}

class DesktopCoreSettingsRepository(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): DesktopCoreSettings {
        val deviceId = prefs.getString(KEY_DEVICE_ID, null)
            ?.takeIf { it.isNotBlank() }
            ?: "android-${UUID.randomUUID()}".also {
                prefs.edit().putString(KEY_DEVICE_ID, it).apply()
            }
        return DesktopCoreSettings(
            enabled = prefs.getBoolean(KEY_ENABLED, false),
            baseUrl = prefs.getString(KEY_BASE_URL, DEFAULT_BASE_URL).orEmpty(),
            apiToken = prefs.getString(KEY_API_TOKEN, "").orEmpty(),
            deviceId = deviceId
        )
    }

    fun save(settings: DesktopCoreSettings) {
        prefs.edit()
            .putBoolean(KEY_ENABLED, settings.enabled)
            .putString(KEY_BASE_URL, settings.normalizedBaseUrl)
            .putString(KEY_API_TOKEN, settings.apiToken.trim())
            .putString(KEY_DEVICE_ID, settings.deviceId.trim())
            .apply()
    }

    companion object {
        private const val PREFS = "dwpm_desktop_core"
        private const val KEY_ENABLED = "enabled"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_API_TOKEN = "api_token"
        private const val KEY_DEVICE_ID = "device_id"
        const val DEFAULT_BASE_URL = "http://127.0.0.1:17351"
    }
}

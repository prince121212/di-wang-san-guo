package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.cloud.CollaborativeMapClient
import com.example.dwpmclone.domain.cloud.CollaborativeMapHttpSettings
import com.example.dwpmclone.domain.cloud.DisabledCollaborativeMapClient
import com.example.dwpmclone.domain.cloud.HttpCollaborativeMapClient
import java.util.UUID

class CollaborativeMapSettingsRepository(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun load(): CollaborativeMapSettings {
        val storedDeviceId = prefs.getString(KEY_DEVICE_ID, null).orEmpty()
        val deviceId = storedDeviceId.ifBlank {
            "android-${UUID.randomUUID()}".also {
                prefs.edit().putString(KEY_DEVICE_ID, it).apply()
            }
        }
        return CollaborativeMapSettings(
            enabled = prefs.getBoolean(KEY_ENABLED, false),
            baseUrl = prefs.getString(KEY_BASE_URL, DEFAULT_BASE_URL).orEmpty(),
            deviceId = deviceId,
            authToken = prefs.getString(KEY_AUTH_TOKEN, "").orEmpty()
        )
    }

    fun save(enabled: Boolean, baseUrl: String, authToken: String): CollaborativeMapSettings {
        val current = load()
        val normalizedUrl = baseUrl.trim().trimEnd('/')
        prefs.edit()
            .putBoolean(KEY_ENABLED, enabled)
            .putString(KEY_BASE_URL, normalizedUrl)
            .putString(KEY_AUTH_TOKEN, authToken.trim())
            .apply()
        return current.copy(enabled = enabled, baseUrl = normalizedUrl, authToken = authToken.trim())
    }

    fun createClient(): CollaborativeMapClient {
        val settings = load()
        if (!settings.enabled || settings.baseUrl.isBlank()) return DisabledCollaborativeMapClient
        return runCatching {
            HttpCollaborativeMapClient(
                CollaborativeMapHttpSettings(
                    baseUrl = settings.baseUrl,
                    deviceId = settings.deviceId,
                    authToken = settings.authToken
                )
            )
        }.getOrElse { DisabledCollaborativeMapClient }
    }

    companion object {
        const val DEFAULT_BASE_URL = "http://127.0.0.1:18080"
        private const val PREFS_NAME = "dwpm_collaborative_map"
        private const val KEY_ENABLED = "enabled"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_AUTH_TOKEN = "auth_token"
    }
}

data class CollaborativeMapSettings(
    val enabled: Boolean,
    val baseUrl: String,
    val deviceId: String,
    val authToken: String
)

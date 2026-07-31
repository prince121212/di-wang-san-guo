package com.example.dwpmclone.data.local

import android.content.Context

/** Persists only the user's explicit choice to keep on-device automation enabled. */
class LocalHostingPreferences(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    fun isEnabled(): Boolean = preferences.getBoolean(KEY_ENABLED, false)

    fun setEnabled(enabled: Boolean) {
        check(preferences.edit().putBoolean(KEY_ENABLED, enabled).commit()) {
            "无法持久化托管启用状态"
        }
    }

    private companion object {
        const val PREFERENCES_NAME = "dwpm_local_hosting"
        const val KEY_ENABLED = "user_enabled"
    }
}

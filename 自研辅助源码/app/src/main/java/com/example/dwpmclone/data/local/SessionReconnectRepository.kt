package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONObject

data class SessionReconnectState(
    val failures: Int = 0,
    val nextAttemptAtMillis: Long = 0L,
    val reason: String = "",
    val failureKind: String = ""
)

class SessionReconnectRepository(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    fun state(accountId: Long): SessionReconnectState {
        val raw = preferences.getString(key(accountId), null) ?: return SessionReconnectState()
        return runCatching { JSONObject(raw) }.getOrNull()?.let { json ->
            SessionReconnectState(
                failures = json.optInt("failures", 0).coerceAtLeast(0),
                nextAttemptAtMillis = json.optLong("nextAttemptAtMillis", 0L).coerceAtLeast(0L),
                reason = json.optString("reason"),
                failureKind = json.optString("failureKind")
            )
        } ?: SessionReconnectState()
    }

    fun replace(accountId: Long, state: SessionReconnectState) {
        if (
            state.failures <= 0 &&
            state.nextAttemptAtMillis <= 0L &&
            state.reason.isBlank() &&
            state.failureKind.isBlank()
        ) {
            reset(accountId)
        } else {
            save(accountId, state.copy(
                failures = state.failures.coerceAtLeast(0),
                nextAttemptAtMillis = state.nextAttemptAtMillis.coerceAtLeast(0L),
                reason = state.reason.take(500),
                failureKind = state.failureKind.take(40)
            ))
        }
    }

    fun reset(accountId: Long) {
        check(preferences.edit().remove(key(accountId)).commit()) { "无法清理自动重连状态" }
    }

    fun delete(accountId: Long) = reset(accountId)

    private fun save(accountId: Long, state: SessionReconnectState) {
        check(
            preferences.edit().putString(
                key(accountId),
                JSONObject()
                    .put("failures", state.failures)
                    .put("nextAttemptAtMillis", state.nextAttemptAtMillis)
                    .put("reason", state.reason)
                    .put("failureKind", state.failureKind)
                    .toString()
            ).commit()
        ) { "无法持久化自动重连状态" }
    }

    private fun key(accountId: Long): String = "account_$accountId"

    private companion object {
        const val PREFERENCES_NAME = "dwpm_session_reconnect"
    }
}

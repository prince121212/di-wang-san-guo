package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONObject

data class SessionReconnectState(
    val failures: Int = 0,
    val nextAttemptAtMillis: Long = 0L,
    val reason: String = ""
)

object SessionReconnectBackoff {
    private val delays = longArrayOf(5_000L, 15_000L, 30_000L, 60_000L, 120_000L, 300_000L)

    fun delayMillis(failureCount: Int): Long = delays[(failureCount - 1).coerceIn(0, delays.lastIndex)]
}

class SessionReconnectRepository(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    fun state(accountId: Long): SessionReconnectState {
        val raw = preferences.getString(key(accountId), null) ?: return SessionReconnectState()
        return runCatching { JSONObject(raw) }.getOrNull()?.let { json ->
            SessionReconnectState(
                failures = json.optInt("failures", 0).coerceAtLeast(0),
                nextAttemptAtMillis = json.optLong("nextAttemptAtMillis", 0L).coerceAtLeast(0L),
                reason = json.optString("reason")
            )
        } ?: SessionReconnectState()
    }

    fun recordFailure(accountId: Long, nowMillis: Long, reason: String): SessionReconnectState {
        val failures = state(accountId).failures + 1
        val next = SessionReconnectState(
            failures = failures,
            nextAttemptAtMillis = nowMillis + SessionReconnectBackoff.delayMillis(failures),
            reason = reason.take(500)
        )
        save(accountId, next)
        return next
    }

    fun requestImmediate(accountId: Long, reason: String) {
        save(accountId, state(accountId).copy(nextAttemptAtMillis = 0L, reason = reason.take(500)))
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
                    .toString()
            ).commit()
        ) { "无法持久化自动重连状态" }
    }

    private fun key(accountId: Long): String = "account_$accountId"

    private companion object {
        const val PREFERENCES_NAME = "dwpm_session_reconnect"
    }
}

package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONObject
import java.util.UUID

/**
 * Small durable journal for the hosting process, independent of task state.
 *
 * It answers a different question from task logs: did the process restart, when
 * was the last scheduler heartbeat, and which wall-clock deadline was armed?
 * Keeping these facts lets the UI and support diagnostics distinguish an OEM
 * process kill from a game/server failure.
 */
class LocalHostingRuntimeRepository(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(
        PREFS,
        Context.MODE_PRIVATE,
    )

    @Synchronized
    fun beginProcess(nowMillis: Long = System.currentTimeMillis()): String {
        val previousActive = preferences.getBoolean(KEY_ACTIVE, false)
        // The heartbeat is about to be reset to "now".  Preserve the last one
        // observed by the dead process first: it is the only evidence of how
        // long hosting was actually down, and it cannot be recovered later.
        val previousHeartbeat = preferences.getLong(KEY_LAST_HEARTBEAT_AT, 0L)
        val generation = UUID.randomUUID().toString()
        val editor = preferences.edit()
            .putBoolean(KEY_ACTIVE, true)
            .putString(KEY_PROCESS_GENERATION, generation)
            .putLong(KEY_PROCESS_STARTED_AT, nowMillis)
            .putLong(KEY_LAST_HEARTBEAT_AT, nowMillis)
            .remove(KEY_STOP_REASON)
        // These two keys describe the interruption *this* start recovered from,
        // so a clean user-initiated start must clear them.  Leaving them behind
        // would re-report a long-resolved kill on every later start.
        if (previousActive) {
            editor.putLong(KEY_INTERRUPTED_AT, nowMillis)
            if (previousHeartbeat > 0L) {
                editor.putLong(KEY_PREVIOUS_HEARTBEAT_AT, previousHeartbeat)
            } else {
                editor.remove(KEY_PREVIOUS_HEARTBEAT_AT)
            }
        } else {
            editor.remove(KEY_INTERRUPTED_AT)
            editor.remove(KEY_PREVIOUS_HEARTBEAT_AT)
        }
        check(editor.commit()) { "无法持久化后台进程启动状态" }
        return generation
    }

    @Synchronized
    fun heartbeat(
        nowMillis: Long = System.currentTimeMillis(),
        tick: Int? = null,
        nextWakeAtMillis: Long? = null,
    ) {
        val editor = preferences.edit()
            .putBoolean(KEY_ACTIVE, true)
            .putLong(KEY_LAST_HEARTBEAT_AT, nowMillis)
        if (tick != null) editor.putInt(KEY_LAST_TICK, tick)
        if (nextWakeAtMillis == null) editor.remove(KEY_NEXT_WAKE_AT)
        else editor.putLong(KEY_NEXT_WAKE_AT, nextWakeAtMillis)
        check(editor.commit()) { "无法持久化后台心跳" }
    }

    @Synchronized
    fun scheduled(
        nextWakeAtMillis: Long?,
        tick: Int? = null,
        nowMillis: Long = System.currentTimeMillis(),
    ) {
        val editor = preferences.edit()
            .putLong(KEY_LAST_HEARTBEAT_AT, nowMillis)
        if (tick != null) editor.putInt(KEY_LAST_TICK, tick)
        if (nextWakeAtMillis == null) editor.remove(KEY_NEXT_WAKE_AT)
        else editor.putLong(KEY_NEXT_WAKE_AT, nextWakeAtMillis)
        check(editor.commit()) { "无法持久化后台调度截止时间" }
    }

    @Synchronized
    fun markStopped(
        nowMillis: Long = System.currentTimeMillis(),
        reason: String,
    ) {
        check(
            preferences.edit()
                .putBoolean(KEY_ACTIVE, false)
                .putLong(KEY_LAST_HEARTBEAT_AT, nowMillis)
                .putString(KEY_STOP_REASON, reason)
                .commit()
        ) { "无法持久化后台停止状态" }
    }

    @Synchronized
    fun interrupted(
        nowMillis: Long = System.currentTimeMillis(),
        reason: String,
    ) {
        check(
            preferences.edit()
                .putBoolean(KEY_ACTIVE, true)
                .putLong(KEY_LAST_HEARTBEAT_AT, nowMillis)
                .putLong(KEY_INTERRUPTED_AT, nowMillis)
                .putString(KEY_STOP_REASON, reason)
                .commit()
        ) { "无法持久化后台中断状态" }
    }

    @Synchronized
    fun snapshot(): JSONObject = JSONObject()
        .put("active", preferences.getBoolean(KEY_ACTIVE, false))
        .put("processGeneration", preferences.getString(KEY_PROCESS_GENERATION, null) ?: JSONObject.NULL)
        .put("processStartedAtMillis", preferences.getLong(KEY_PROCESS_STARTED_AT, 0L))
        .put("lastHeartbeatAtMillis", preferences.getLong(KEY_LAST_HEARTBEAT_AT, 0L))
        .put("lastTick", preferences.getInt(KEY_LAST_TICK, 0))
        .put(
            "nextWakeAtMillis",
            if (preferences.contains(KEY_NEXT_WAKE_AT)) {
                preferences.getLong(KEY_NEXT_WAKE_AT, 0L)
            } else JSONObject.NULL,
        )
        .put(
            "interruptedAtMillis",
            if (preferences.contains(KEY_INTERRUPTED_AT)) {
                preferences.getLong(KEY_INTERRUPTED_AT, 0L)
            } else JSONObject.NULL,
        )
        .put(
            "previousHeartbeatAtMillis",
            if (preferences.contains(KEY_PREVIOUS_HEARTBEAT_AT)) {
                preferences.getLong(KEY_PREVIOUS_HEARTBEAT_AT, 0L)
            } else JSONObject.NULL,
        )
        .put("stopReason", preferences.getString(KEY_STOP_REASON, null) ?: JSONObject.NULL)

    private companion object {
        const val PREFS = "dwpm_hosting_runtime"
        const val KEY_ACTIVE = "active"
        const val KEY_PROCESS_GENERATION = "process_generation"
        const val KEY_PROCESS_STARTED_AT = "process_started_at"
        const val KEY_LAST_HEARTBEAT_AT = "last_heartbeat_at"
        const val KEY_LAST_TICK = "last_tick"
        const val KEY_NEXT_WAKE_AT = "next_wake_at"
        const val KEY_INTERRUPTED_AT = "interrupted_at"
        const val KEY_PREVIOUS_HEARTBEAT_AT = "previous_heartbeat_at"
        const val KEY_STOP_REASON = "stop_reason"
    }
}

package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskType
import org.json.JSONArray
import org.json.JSONObject

/**
 * Structured logcat markers consumed by tools/verify_device_capture_scenarios.py.
 *
 * The prefix is intentionally stable so Frida/logcat capture can prove the self-developed
 * assistant completed the local lifecycle tail of the brush-yellow minimum loop:
 * task stop -> session logout.  These markers do not enable real network sends.
 */
object SelfLifecycleLogFormatter {
    const val PREFIX = "[self-lifecycle-json]"

    fun taskStop(
        accountId: Long,
        sourceMode: Int,
        reason: String,
        stoppedTaskTypes: List<TaskType>,
        logoutRequested: Boolean,
        logoutSucceeded: Boolean,
        logoutMessage: String
    ): String = PREFIX + " " + JSONObject()
        .put("event", "task_stop")
        .put("accountId", accountId)
        .put("sourceMode", sourceMode)
        .put("reason", reason)
        .put("stoppedTaskTypes", JSONArray(stoppedTaskTypes.map { it.name }))
        .put("logoutRequested", logoutRequested)
        .put("logoutSucceeded", logoutSucceeded)
        .put("logoutMessage", logoutMessage)
        .put("realActionNetworkAllowed", false)
        .toString()

    fun sessionLogout(
        accountId: Long,
        sourceMode: Int,
        reason: String,
        logoutRequested: Boolean,
        logoutSucceeded: Boolean,
        logoutMessage: String
    ): String = PREFIX + " " + JSONObject()
        .put("event", "session_logout")
        .put("accountId", accountId)
        .put("sourceMode", sourceMode)
        .put("reason", reason)
        .put("logoutRequested", logoutRequested)
        .put("logoutSucceeded", logoutSucceeded)
        .put("logoutMessage", logoutMessage)
        .put("logoutOnce", true)
        .put("realActionNetworkAllowed", false)
        .toString()
}

package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.scheduler.TaskRuntimeState
import com.example.dwpmclone.domain.scheduler.TaskRuntimeStatus
import org.json.JSONArray
import org.json.JSONObject

class TaskRuntimeStatusRepository(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    @Synchronized
    fun upsert(status: TaskRuntimeStatus) {
        val statuses = readAll().associateByTo(linkedMapOf()) { it.accountId to it.type }
        statuses[status.accountId to status.type] = status
        write(statuses.values)
    }

    @Synchronized
    fun upsertAll(statuses: List<TaskRuntimeStatus>) {
        if (statuses.isEmpty()) return
        val merged = readAll().associateByTo(linkedMapOf()) { it.accountId to it.type }
        statuses.forEach { merged[it.accountId to it.type] = it }
        write(merged.values)
    }

    @Synchronized
    fun reconcileConfigured(
        accountId: Long,
        configuredTypes: Collection<TaskType>,
        nowMillis: Long
    ) {
        val configured = configuredTypes.toSet()
        val merged = readAll().associateByTo(linkedMapOf()) { it.accountId to it.type }
        merged.keys.filter { it.first == accountId && it.second !in configured }.forEach(merged::remove)
        configured.forEach { type ->
            val key = accountId to type
            if (key !in merged) {
                merged[key] = TaskRuntimeStatus(
                    accountId,
                    type,
                    TaskRuntimeState.WAITING,
                    "任务已配置，等待后台首次调度",
                    nowMillis
                )
            }
        }
        write(merged.values)
    }

    @Synchronized
    fun markServiceStopped(nowMillis: Long, message: String) {
        write(readAll().map {
            it.copy(
                state = TaskRuntimeState.SERVICE_STOPPED,
                message = message,
                updatedAtMillis = nowMillis,
                nextRunAtMillis = null
            )
        })
    }

    @Synchronized
    fun list(accountId: Long): List<TaskRuntimeStatus> =
        readAll().filter { it.accountId == accountId }.sortedBy { it.type.ordinal }

    private fun readAll(): List<TaskRuntimeStatus> {
        val array = runCatching {
            JSONArray(prefs.getString(KEY, "[]") ?: "[]")
        }.getOrDefault(JSONArray())
        return (0 until array.length()).mapNotNull { index ->
            val obj = array.optJSONObject(index) ?: return@mapNotNull null
            val type = runCatching { TaskType.valueOf(obj.optString("type")) }.getOrNull()
                ?: return@mapNotNull null
            val state = runCatching { TaskRuntimeState.valueOf(obj.optString("state")) }.getOrNull()
                ?: return@mapNotNull null
            TaskRuntimeStatus(
                accountId = obj.optLong("accountId"),
                type = type,
                state = state,
                message = obj.optString("message"),
                updatedAtMillis = obj.optLong("updatedAtMillis"),
                nextRunAtMillis = obj.optLong("nextRunAtMillis").takeIf {
                    obj.has("nextRunAtMillis") && !obj.isNull("nextRunAtMillis")
                },
                tick = obj.optInt("tick").takeIf { obj.has("tick") && !obj.isNull("tick") }
            )
        }
    }

    private fun write(statuses: Collection<TaskRuntimeStatus>) {
        val array = JSONArray()
        statuses.sortedWith(compareBy<TaskRuntimeStatus> { it.accountId }.thenBy { it.type.ordinal })
            .forEach { status ->
                array.put(
                    JSONObject()
                        .put("accountId", status.accountId)
                        .put("type", status.type.name)
                        .put("state", status.state.name)
                        .put("message", status.message)
                        .put("updatedAtMillis", status.updatedAtMillis)
                        .put("nextRunAtMillis", status.nextRunAtMillis ?: JSONObject.NULL)
                        .put("tick", status.tick ?: JSONObject.NULL)
                )
            }
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    companion object {
        private const val PREFS = "dwpm_clone_task_runtime"
        private const val KEY = "statuses"
    }
}

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
        var changed = false
        merged.keys.filter { it.first == accountId && it.second !in configured }.forEach {
            merged.remove(it)
            changed = true
        }
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
                changed = true
            }
        }
        if (changed) write(merged.values)
    }

    @Synchronized
    fun markServiceStopped(
        nowMillis: Long,
        message: String,
        preserveNextRunAt: Boolean = false
    ) {
        write(readAll().map {
            it.copy(
                state = TaskRuntimeState.SERVICE_STOPPED,
                message = message,
                updatedAtMillis = nowMillis,
                nextRunAtMillis = it.nextRunAtMillis.takeIf { preserveNextRunAt }
            )
        })
    }

    @Synchronized
    fun markAccountStopped(accountId: Long, nowMillis: Long, message: String) {
        write(readAll().map { status ->
            if (status.accountId != accountId) status else status.copy(
                state = TaskRuntimeState.STOPPED,
                message = message,
                updatedAtMillis = nowMillis,
                nextRunAtMillis = null
            )
        })
    }

    @Synchronized
    fun deleteAccount(accountId: Long) {
        write(readAll().filterNot { it.accountId == accountId })
    }

    @Synchronized
    fun list(accountId: Long): List<TaskRuntimeStatus> =
        readAll().filter { it.accountId == accountId }.sortedBy { it.type.ordinal }

    @Synchronized
    fun listAll(): List<TaskRuntimeStatus> = readAll()

    fun configurationSignature(): String? = prefs.getString(KEY_CONFIG_SIGNATURE, null)

    fun setConfigurationSignature(signature: String) {
        require(signature.isNotBlank()) { "任务配置签名不能为空" }
        check(prefs.edit().putString(KEY_CONFIG_SIGNATURE, signature).commit()) {
            "无法持久化任务配置签名"
        }
    }

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
        check(prefs.edit().putString(KEY, array.toString()).commit()) {
            "无法持久化任务运行状态"
        }
    }

    companion object {
        private const val PREFS = "dwpm_clone_task_runtime"
        private const val KEY = "statuses"
        private const val KEY_CONFIG_SIGNATURE = "configuration_signature"
    }
}

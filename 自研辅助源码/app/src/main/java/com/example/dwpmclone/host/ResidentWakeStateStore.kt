package com.example.dwpmclone.host

import android.content.Context
import org.json.JSONObject

/** Durable wall-clock deadlines for the per-account resident wake gate. */
data class ResidentWakeState(
    val nextWakeAtMillis: Long?,
    val pausedForAttention: Boolean,
)

interface ResidentWakeStateStore {
    fun snapshot(): Map<Long, ResidentWakeState>
    fun put(accountId: Long, state: ResidentWakeState)
    fun remove(accountId: Long)
    fun retainAccounts(activeAccountIds: Set<Long>)
    fun clear()
}

/** SharedPreferences store; values are deliberately small and contain no credentials. */
class AndroidResidentWakeStateStore(context: Context) : ResidentWakeStateStore {
    private val preferences = context.applicationContext.getSharedPreferences(
        PREFS,
        Context.MODE_PRIVATE,
    )

    @Synchronized
    override fun snapshot(): Map<Long, ResidentWakeState> {
        val root = read()
        return root.keys().asSequence().mapNotNull { key ->
            val accountId = key.toLongOrNull() ?: return@mapNotNull null
            val value = root.optJSONObject(key) ?: return@mapNotNull null
            accountId to ResidentWakeState(
                nextWakeAtMillis = value.optLong("nextWakeAtMillis").takeIf {
                    value.has("nextWakeAtMillis") && !value.isNull("nextWakeAtMillis")
                },
                pausedForAttention = value.optBoolean("pausedForAttention", false),
            )
        }.toMap()
    }

    @Synchronized
    override fun put(accountId: Long, state: ResidentWakeState) {
        val root = read()
        root.put(
            accountId.toString(),
            JSONObject()
                .put("nextWakeAtMillis", state.nextWakeAtMillis ?: JSONObject.NULL)
                .put("pausedForAttention", state.pausedForAttention),
        )
        write(root)
    }

    @Synchronized
    override fun remove(accountId: Long) {
        val root = read()
        root.remove(accountId.toString())
        write(root)
    }

    @Synchronized
    override fun retainAccounts(activeAccountIds: Set<Long>) {
        val root = read()
        root.keys().asSequence().toList().forEach { key ->
            if (key.toLongOrNull() !in activeAccountIds) root.remove(key)
        }
        write(root)
    }

    @Synchronized
    override fun clear() {
        check(preferences.edit().remove(KEY).commit()) {
            "无法清理常驻唤醒截止时间"
        }
    }

    private fun read(): JSONObject = runCatching {
        JSONObject(preferences.getString(KEY, "{}") ?: "{}")
    }.getOrDefault(JSONObject())

    private fun write(value: JSONObject) {
        check(preferences.edit().putString(KEY, value.toString()).commit()) {
            "无法持久化常驻唤醒截止时间"
        }
    }

    private companion object {
        const val PREFS = "dwpm_resident_wakes"
        const val KEY = "records"
    }
}


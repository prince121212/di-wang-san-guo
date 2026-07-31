package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONArray

/** Persists exact notice identities so a later, newly-timestamped failure can surface again. */
class DismissedNoticeRepository(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    @Synchronized
    fun contains(accountId: Long, key: String): Boolean = identity(accountId, key) in read()

    @Synchronized
    fun dismiss(accountId: Long, key: String) {
        require(accountId > 0L && key.isNotBlank()) { "提示标识无效" }
        val values = read().toMutableList()
        values.remove(identity(accountId, key))
        values += identity(accountId, key)
        val retained = values.takeLast(MAX_DISMISSED)
        check(preferences.edit().putString(KEY, JSONArray(retained).toString()).commit()) {
            "无法持久化已删除提示"
        }
    }

    @Synchronized
    fun clearAccount(accountId: Long) {
        val prefix = "$accountId:"
        val retained = read().filterNot { it.startsWith(prefix) }
        check(preferences.edit().putString(KEY, JSONArray(retained).toString()).commit()) {
            "无法清理账号提示状态"
        }
    }

    private fun read(): List<String> {
        val array = runCatching {
            JSONArray(preferences.getString(KEY, "[]") ?: "[]")
        }.getOrDefault(JSONArray())
        return (0 until array.length()).mapNotNull { array.optString(it).takeIf(String::isNotBlank) }
    }

    private fun identity(accountId: Long, key: String): String = "$accountId:${key.take(180)}"

    private companion object {
        const val PREFERENCES = "dwpm_dismissed_notices"
        const val KEY = "identities"
        const val MAX_DISMISSED = 200
    }
}

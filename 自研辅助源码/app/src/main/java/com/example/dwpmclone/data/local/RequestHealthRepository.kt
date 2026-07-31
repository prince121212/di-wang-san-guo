package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** 一次游戏请求的结果，对应电脑端账号卡里的一个小点。 */
data class RequestHealthEntry(
    val success: Boolean,
    val purpose: String,
    val timeMillis: Long
)

/**
 * 按账号保存最近 [CAPACITY] 次游戏请求的成败，供助手页账号卡的健康点展示。
 *
 * 电脑端由 server.py 在 `acc.recentGameRequests` 里维护同样的 30 条环形记录，
 * 手机端本地执行，因此在本地落一份等价数据。
 */
class RequestHealthRepository(context: Context) {
    private val prefs = context.getSharedPreferences("dwpm_clone_request_health", Context.MODE_PRIVATE)

    fun record(accountId: Long, success: Boolean, purpose: String, timeMillis: Long) {
        if (accountId <= 0L) return
        val key = key(accountId)
        val source = readArray(key)
        source.put(
            JSONObject()
                .put("ok", success)
                .put("purpose", purpose)
                .put("time", timeMillis)
        )
        val trimmed = JSONArray()
        val start = maxOf(0, source.length() - CAPACITY)
        for (index in start until source.length()) {
            trimmed.put(source.optJSONObject(index) ?: continue)
        }
        prefs.edit().putString(key, trimmed.toString()).apply()
    }

    /** 由旧到新返回，最后一个是最新的一次请求。 */
    fun recent(accountId: Long): List<RequestHealthEntry> {
        if (accountId <= 0L) return emptyList()
        val source = readArray(key(accountId))
        return (0 until source.length()).mapNotNull { index ->
            val item = source.optJSONObject(index) ?: return@mapNotNull null
            RequestHealthEntry(
                success = item.optBoolean("ok", false),
                purpose = item.optString("purpose"),
                timeMillis = item.optLong("time")
            )
        }
    }

    fun clear(accountId: Long) {
        prefs.edit().remove(key(accountId)).apply()
    }

    private fun key(accountId: Long): String = "health_$accountId"

    private fun readArray(key: String): JSONArray =
        runCatching { JSONArray(prefs.getString(key, "[]") ?: "[]") }.getOrDefault(JSONArray())

    companion object {
        const val CAPACITY = 30
    }
}

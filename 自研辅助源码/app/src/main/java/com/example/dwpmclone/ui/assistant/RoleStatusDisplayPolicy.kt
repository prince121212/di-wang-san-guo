package com.example.dwpmclone.ui.assistant

import org.json.JSONArray
import org.json.JSONObject

/** Exact current computer-front-end “角色 → 状态” rows and value semantics. */
object RoleStatusDisplayPolicy {
    val statusNames = listOf(
        "休战",
        "军队攻击增加10%",
        "军队防御增加10%",
        "增加抓将的几率",
        "战斗后资源、声望的获取增加50%",
        "将领获取的经验增加50%",
        "加强破坏封地的威力",
        "增加夺取降忠效果",
        "增加夺取收益效果",
        "增加俘虏玩家将领的几率",
        "军队攻击速度增加5%"
    )

    fun rows(vararg rawSources: String?): List<List<String>> {
        val effects = rawSources.firstNotNullOfOrNull(::parseEffects).orEmpty()
        val byName = effects.associateBy { effect ->
            effect.optString("name").ifBlank { effect.optString("label") }
        }
        return statusNames.map { name ->
            val effect = byName[name]
            listOf(name, formatRemaining(effect))
        }
    }

    private fun parseEffects(raw: String?): List<JSONObject>? {
        val text = raw?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        return runCatching {
            val root = if (text.startsWith("{")) JSONObject(text) else null
            val array = when {
                root != null -> root.optJSONArray("statusEffects")
                    ?: root.optJSONArray("effects")
                    ?: return@runCatching null
                text.startsWith("[") -> JSONArray(text)
                else -> return@runCatching null
            }
            (0 until array.length()).mapNotNull(array::optJSONObject)
        }.getOrNull()
    }

    private fun formatRemaining(effect: JSONObject?): String {
        if (effect == null) return "0分钟"
        val keys = listOf("remainingMinutes", "minutes", "remaining")
        val value = keys.firstNotNullOfOrNull { key ->
            if (effect.has(key) && !effect.isNull(key)) effect.opt(key) else null
        } ?: return "0分钟"
        return when (value) {
            is Number -> "${value.toLong()}分钟"
            else -> value.toString().takeIf { it.isNotBlank() } ?: "0分钟"
        }
    }
}

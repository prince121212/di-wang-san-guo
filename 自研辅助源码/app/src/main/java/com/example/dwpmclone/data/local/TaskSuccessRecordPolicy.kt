package com.example.dwpmclone.data.local

data class TaskSuccessRecord(
    val category: String,
    val message: String
)

/**
 * Success records are structured at write time. The exact legacy parser only preserves
 * pre-migration desktop-compatible lines; generic words such as "成功" never qualify.
 */
internal object TaskSuccessRecordPolicy {
    fun resolve(entry: TaskLogEntry): TaskSuccessRecord? {
        val category = entry.successCategory?.trim().orEmpty()
        val message = entry.successMessage?.trim().orEmpty()
        if (category.isNotBlank() && message.isNotBlank()) {
            return TaskSuccessRecord(category, message)
        }
        return fromLegacyMessage(entry.message)
    }

    fun fromLegacyMessage(rawMessage: String): TaskSuccessRecord? {
        val text = rawMessage.replace(Regex("\\s+"), " ").trim()
        Regex("""副本第 \d+ 轮第 (\d+) 条完成：.+? → (.+?第\d+关)，""")
            .find(text)?.let { return TaskSuccessRecord("副本", "编队${it.groupValues[1]} > ${it.groupValues[2]}") }
        Regex("""自动加体完成：(.+?) 使用活血丹1个""")
            .find(text)?.let { return TaskSuccessRecord("加体", "${it.groupValues[1]}使用1枚活血丹") }
        Regex("""粮食转铜完成：兑换(\d+)铜，消耗粮食(\d+)""")
            .find(text)?.let { return TaskSuccessRecord("转铜", "${it.groupValues[2]}粮换${it.groupValues[1]}铜") }
        Regex("""治疗伤兵完成：.*?封地=([^；]+?) 范围=全部伤兵(?:；|$)""")
            .find(text)?.let { return TaskSuccessRecord("治疗", "${it.groupValues[1]} 全部伤兵") }
        Regex("""自动开箱成功：(.+)""").find(text)
            ?.let { return TaskSuccessRecord("开箱", it.groupValues[1]) }

        return prefixed(text, "自动签到完成：", "签到", "今日签到成功")
            ?: prefixed(text, "领竞技币完成：", "领币", "领取竞技币成功")
            ?: donation(text)
            ?: prefixed(text, "领取俸禄完成：", "俸禄", "领取俸禄成功")
            ?: prefixed(text, "国家俸禄完成：", "俸禄", "领取俸禄成功")
            ?: prefixed(text, "国家征收完成：", "国征", "国家征收成功")
            ?: prefixed(text, "城主征收完成：", "城征", "城主征收成功")
            ?: prefixed(text, "名将拜访完成：", "拜访", "名将拜访成功")
            ?: prefixed(text, "名将拜访成功：", "拜访", "名将拜访成功")
    }

    private fun prefixed(
        text: String,
        prefix: String,
        category: String,
        fallback: String
    ): TaskSuccessRecord? {
        if (!text.startsWith(prefix)) return null
        return TaskSuccessRecord(category, text.removePrefix(prefix).trim().ifBlank { fallback })
    }

    private fun donation(text: String): TaskSuccessRecord? {
        if (!text.startsWith("自动捐献完成：") || "失败" in text) return null
        val detail = text.removePrefix("自动捐献完成：")
            .replace(Regex("""^(?:自动捐献完成[:：]\s*)+"""), "")
            .trim()
            .ifBlank { "捐献成功" }
        return TaskSuccessRecord("捐献", detail)
    }
}

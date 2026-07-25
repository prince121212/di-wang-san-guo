package com.example.dwpmclone.domain.scheduler

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Shared daily-state rules migrated from the desktop assistant.
 *
 * A daily activity read is attempted once immediately after login and once after the
 * local date changes. The attempt date must be persisted before network I/O so failures
 * do not cause a retry storm.
 */
class DailyActivityPolicy(
    private val timeZone: TimeZone = TimeZone.getTimeZone("Asia/Shanghai")
) {
    fun localDateKey(nowMillis: Long): String =
        SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).apply {
            timeZone = this@DailyActivityPolicy.timeZone
        }.format(Date(nowMillis))

    fun shouldReadAfterLogin(): Boolean = true

    fun shouldReadAfterMidnight(lastAttemptDate: String?, nowMillis: Long): Boolean =
        lastAttemptDate != localDateKey(nowMillis)
}

data class ArenaRewardResult(
    val success: Boolean,
    val completed: Boolean,
    val message: String
)

object ArenaRewardPolicy {
    const val OPEN_HOUR: Int = 22
    const val UNAVAILABLE_MESSAGE: String =
        "当前不可领取：竞技场每日奖励需在22点后领取，或今日已经领取"

    fun interpret(status: Int?, serverMessage: String?): ArenaRewardResult {
        val message = serverMessage.orEmpty().trim()
        val success = status == 0
        return ArenaRewardResult(
            success = success,
            completed = success,
            message = when {
                success && message.isNotEmpty() -> message
                success -> "竞技奖励领取成功"
                message.isNotEmpty() -> message
                else -> UNAVAILABLE_MESSAGE
            }
        )
    }
}

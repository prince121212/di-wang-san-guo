package com.example.dwpmclone.domain.alarm

import com.example.dwpmclone.domain.model.AlarmNotificationKind
import com.example.dwpmclone.domain.model.AlarmWithdrawConfig
import org.json.JSONObject

data class DetectedAlarmEvent(
    val fingerprint: String,
    val kind: AlarmNotificationKind,
    val text: String,
    val shouldNotify: Boolean,
    val vibrate: Boolean
)

/**
 * Reads the persisted desktop-compatible militaryIntel event shape.
 *
 * It performs no game request and no state-changing action. New-event deduplication is
 * intentionally owned by the long-lived protocol client so a service restart establishes
 * a fresh baseline instead of replaying old notifications.
 */
object MilitaryAlarmEventDetector {
    fun detect(channelExtra: Map<String, String>, config: AlarmWithdrawConfig): List<DetectedAlarmEvent> {
        if (!config.enabled) return emptyList()
        val intel = firstJson(channelExtra["militaryIntelJson"], channelExtra["militaryIntel"])
            ?: return emptyList()
        val events = intel.optJSONArray("events") ?: return emptyList()
        return buildList {
            for (index in 0 until events.length()) {
                val event = events.optJSONObject(index) ?: continue
                val text = event.optString("text").trim()
                if (text.isBlank()) continue
                val time = event.optString("timeText").ifBlank { event.optString("time") }.trim()
                val state = event.optString("state").trim()
                val incomingKeyword = config.keywords.firstOrNull { it.isNotBlank() && text.contains(it) }
                val incoming = config.incomingEnabled && incomingKeyword != null
                val military = config.militaryEnabled && militaryModeMatches(config.militaryMode, state, text)
                val kind = when {
                    incoming -> AlarmNotificationKind.INCOMING
                    military -> AlarmNotificationKind.MILITARY
                    else -> null
                } ?: continue
                add(
                    DetectedAlarmEvent(
                        fingerprint = listOf(time, state, text).joinToString("|"),
                        kind = kind,
                        text = text,
                        shouldNotify = when (kind) {
                            AlarmNotificationKind.INCOMING -> config.incomingMode != "仅日志" &&
                                config.incomingMode != "关闭"
                            AlarmNotificationKind.MILITARY -> true
                            AlarmNotificationKind.ERROR -> config.errorEnabled
                        },
                        vibrate = config.vibrateOnAlarm
                    )
                )
            }
        }
    }

    private fun militaryModeMatches(mode: String, state: String, text: String): Boolean = when (mode) {
        "仅来袭" -> false
        "全部" -> true
        else -> listOf("出征", "返回", "行军", "征", "返").any {
            state.contains(it) || text.contains(it)
        }
    }

    private fun firstJson(vararg rawValues: String?): JSONObject? =
        rawValues.firstNotNullOfOrNull { raw ->
            raw?.trim()?.takeIf { it.startsWith("{") }?.let {
                runCatching { JSONObject(it) }.getOrNull()
            }
        }
}

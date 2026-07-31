package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.GameSession

/** Desktop parity for daily actions that do not apply to the national-citizen office. */
object NationalCitizenDailyPolicy {
    const val OFFICE_NAME: String = "国民"
    const val OFFICE_ID: Int = 0x0100
    const val COMPLETED_MESSAGE: String = "国民跳过"

    fun isNationalCitizen(session: GameSession): Boolean =
        isNationalCitizen(session.channelExtra)

    fun isNationalCitizen(channelExtra: Map<String, String>): Boolean {
        if (TITLE_KEYS.any { channelExtra[it].orEmpty().trim() == OFFICE_NAME }) return true
        return OFFICE_ID_KEYS.any { key ->
            channelExtra[key]?.parseOfficeId()?.and(0xffff) == OFFICE_ID
        }
    }

    fun completedStep(): StepResult = StepResult(
        success = true,
        message = COMPLETED_MESSAGE,
        raw = mapOf(
            "completed" to "true",
            "skipped" to "true",
            "skipReason" to "national-citizen",
            "officeId" to OFFICE_ID.toString(),
            "officeName" to OFFICE_NAME
        )
    )

    private fun String.parseOfficeId(): Int? {
        val value = trim()
        if (value.isEmpty()) return null
        return runCatching {
            when {
                value.startsWith("0x", ignoreCase = true) -> value.substring(2).toInt(16)
                else -> value.toInt()
            }
        }.getOrNull()
    }

    private val TITLE_KEYS = setOf("title", "officeName", "officialTitle")
    private val OFFICE_ID_KEYS = setOf("officeIdUnsigned", "officeId", "officeIdRaw")
}

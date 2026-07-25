package com.example.dwpmclone.ui.assistant

import org.junit.Assert.assertEquals
import org.junit.Test

class RoleStatusDisplayPolicyTest {
    @Test
    fun emitsAllElevenComputerRowsWithZeroMinutesWhenNoEffectsExist() {
        val rows = RoleStatusDisplayPolicy.rows(null)

        assertEquals(11, rows.size)
        assertEquals(listOf("休战", "0分钟"), rows.first())
        assertEquals(listOf("军队攻击速度增加5%", "0分钟"), rows.last())
    }

    @Test
    fun mapsNumericAndStringRemainingValuesLikeComputerJavascript() {
        val rows = RoleStatusDisplayPolicy.rows(
            """
            {
              "statusEffects":[
                {"name":"休战","remainingMinutes":15},
                {"label":"军队攻击增加10%","remaining":"2小时"}
              ]
            }
            """.trimIndent()
        )

        assertEquals(listOf("休战", "15分钟"), rows[0])
        assertEquals(listOf("军队攻击增加10%", "2小时"), rows[1])
        assertEquals(listOf("军队防御增加10%", "0分钟"), rows[2])
    }
}

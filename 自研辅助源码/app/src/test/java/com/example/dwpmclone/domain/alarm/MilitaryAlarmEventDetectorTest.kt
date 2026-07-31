package com.example.dwpmclone.domain.alarm

import com.example.dwpmclone.domain.model.AlarmNotificationKind
import com.example.dwpmclone.domain.model.AlarmConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MilitaryAlarmEventDetectorTest {
    @Test
    fun classifiesIncomingBeforeGeneralMilitaryEvents() {
        val events = MilitaryAlarmEventDetector.detect(
            mapOf(
                "militaryIntelJson" to """{"events":[
                    {"timeText":"12:00","text":"敌军正在掠夺基地","state":"出征"},
                    {"timeText":"12:01","text":"赵云返回封地","state":"返回"}
                ]}"""
            ),
            AlarmConfig(enabled = true)
        )

        assertEquals(2, events.size)
        assertEquals(AlarmNotificationKind.INCOMING, events[0].kind)
        assertEquals(AlarmNotificationKind.MILITARY, events[1].kind)
        assertTrue(events.all { it.shouldNotify })
    }

    @Test
    fun incomingLogOnlyDoesNotRequestSystemNotification() {
        val events = MilitaryAlarmEventDetector.detect(
            mapOf("militaryIntelJson" to """{"events":[{"text":"敌军攻城"}]}"""),
            AlarmConfig(
                enabled = true,
                incomingMode = "仅日志",
                militaryEnabled = false
            )
        )

        assertEquals(1, events.size)
        assertEquals(AlarmNotificationKind.INCOMING, events.single().kind)
        assertFalse(events.single().shouldNotify)
    }

    @Test
    fun onlyIncomingMilitaryModeIgnoresOrdinaryExpeditionEvents() {
        val events = MilitaryAlarmEventDetector.detect(
            mapOf("militaryIntelJson" to """{"events":[{"text":"关羽出征","state":"出征"}]}"""),
            AlarmConfig(
                enabled = true,
                incomingEnabled = false,
                militaryEnabled = true,
                militaryMode = "仅来袭"
            )
        )

        assertTrue(events.isEmpty())
    }
}

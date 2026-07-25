package com.example.dwpmclone.ui.assistant

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MilitaryIntelDisplayMapperTest {
    @Test
    fun mapsDesktopMilitaryIntelEventShape() {
        val display = MilitaryIntelDisplayMapper.map(
            mapOf(
                "militaryIntelJson" to """
                    {
                      "sourceOpcode":"0x3110/0xa110",
                      "updatedAt":1234,
                      "events":[
                        {"timeText":"12:01:02","text":"【返回】赵云返回封地","state":"返回"},
                        {"time":"12:02:03","text":"国家军团开始攻城","state":"征"}
                      ]
                    }
                """.trimIndent()
            )
        )

        assertEquals(2, display.events.size)
        assertEquals("12:01:02", display.events.first().timeText)
        assertEquals("返回", display.events.first().state)
        assertTrue(display.events.last().national)
        assertEquals(1234L, display.updatedAtMillis)
    }

    @Test
    fun fallsBackToBusyGeneralsAndOmitsIdleOnes() {
        val display = MilitaryIntelDisplayMapper.map(
            mapOf(
                "generalsJson" to """
                    [
                      {"id":"1","name":"赵云","status":"0","statusText":"空闲","soldierType":"轻骑兵","soldierCount":"100"},
                      {"id":"2","name":"关羽","status":"1","statusText":"出征","soldierType":"弩兵","soldierCount":"200"}
                    ]
                """.trimIndent()
            )
        )

        assertEquals(1, display.events.size)
        assertEquals("【征】关羽，弩兵 200", display.events.single().text)
        assertEquals("将领实时状态", display.source)
    }

    @Test
    fun nationAndMilitaryTabsUseTheSameComputerFrontendFeed() {
        val display = MilitaryIntelDisplay(
            events = listOf(
                MilitaryIntelEvent("12:00:00", "赵云出征", "征", national = false),
                MilitaryIntelEvent("12:01:00", "国家军团攻城", "征", national = true)
            ),
            updatedAtMillis = 1_234L,
            source = "0x3110/0xa110"
        )

        assertEquals(
            display.events,
            MilitaryIntelTabPolicy.visibleEvents(display, MilitaryIntelTab.MILITARY)
        )
        assertEquals(
            display.events,
            MilitaryIntelTabPolicy.visibleEvents(display, MilitaryIntelTab.NATION)
        )
    }
}

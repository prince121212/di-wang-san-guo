package com.example.dwpmclone.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AutoLootConfigTest {
    @Test
    fun explicitDisabledRowsDoNotFallBackToLegacySingleRule() {
        val config = AutoLootConfig(
            enabled = true,
            selectedFormationIds = setOf(99L),
            targetPlayerName = "旧目标",
            rules = listOf(
                AutoLootRule(
                    enabled = false,
                    generalIds = listOf(1L),
                    playerName = "已停用目标",
                    fiefIndex = 1
                )
            )
        )

        assertTrue(config.enabledRules().isEmpty())
        assertEquals("no loot rule enabled", config.preparationError())
    }

    @Test
    fun legacySingleRuleRemainsCompatibleWhenRowsAreAbsent() {
        val config = AutoLootConfig(
            enabled = true,
            selectedFormationIds = setOf(11L, 12L),
            targetPlayerName = "旧版目标",
            targetFiefIndex = 2
        )

        val rule = config.enabledRules().single()
        assertEquals(setOf(11L, 12L), rule.generalIds.toSet())
        assertEquals("旧版目标", rule.playerName)
        assertEquals(2, rule.fiefIndex)
        assertNull(config.preparationError())
    }

    @Test
    fun preparationRejectsMissingGeneralsAndInvalidTargets() {
        val missingGenerals = AutoLootConfig(
            enabled = true,
            selectedFormationIds = emptySet(),
            rules = listOf(AutoLootRule(true, emptyList(), "目标", 1))
        )
        val missingPlayer = AutoLootConfig(
            enabled = true,
            selectedFormationIds = emptySet(),
            rules = listOf(AutoLootRule(true, listOf(1L), "", 1))
        )
        val invalidFief = AutoLootConfig(
            enabled = true,
            selectedFormationIds = emptySet(),
            rules = listOf(AutoLootRule(true, listOf(1L), "目标", 0))
        )

        assertEquals("loot general missing", missingGenerals.preparationError())
        assertEquals("loot target player/fief invalid", missingPlayer.preparationError())
        assertEquals("loot target player/fief invalid", invalidFief.preparationError())
    }

    @Test
    fun enabledRulesRotateAndSkipDisabledRows() {
        val config = AutoLootConfig(
            enabled = true,
            selectedFormationIds = emptySet(),
            rules = listOf(
                AutoLootRule(true, listOf(1L), "甲", 1),
                AutoLootRule(false, listOf(2L), "停用", 1),
                AutoLootRule(true, listOf(3L), "乙", 2)
            )
        )

        assertEquals("甲", config.selectEnabledRule(0)?.second?.playerName)
        assertEquals("乙", config.selectEnabledRule(1)?.second?.playerName)
        assertEquals("甲", config.selectEnabledRule(2)?.second?.playerName)
        assertEquals("乙", config.selectEnabledRule(-1)?.second?.playerName)
    }
}

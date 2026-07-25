package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.BulkToolAction
import com.example.dwpmclone.domain.model.BulkToolConfig
import com.example.dwpmclone.domain.model.GameSession

/**
 * Builds a representative non-network mock task plan covering the recovered business modules.
 * It is intentionally synthetic; real plans must be built from saved user configs and recovered protocol data.
 */
object MockTaskPlanFactory {
    const val MOCK_ACCOUNT_ID: Long = 1L

    fun session(): GameSession = GameSession(
        accountId = MOCK_ACCOUNT_ID,
        tokenCiphertext = "mock-token",
        expiresAtMillis = null,
        channelExtra = mapOf("source" to "static-mock"),
        sourceMode = 0
    )

    fun configBundle(): AssistantConfigBundle = AssistantConfigBundle(
        guaji = ConfigDefaults.guaji(MOCK_ACCOUNT_ID).copy(autoStart = true),
        shuaHuang = ConfigDefaults.shuaHuang().copy(enabled = true, selectedFormationIds = setOf(1L)),
        mine = ConfigDefaults.mine().copy(backgroundSearch = true, selectedFormationIds = setOf(1L)),
        daily = ConfigDefaults.daily(),
        general = ConfigDefaults.general(),
        formations = listOf(
            ConfigDefaults.formation(formationId = 1L).copy(
                generalIds = listOf(1L),
                autoAssignTroops = true,
                troopType = "mock-troop"
            )
        ),
        internalAffairs = ConfigDefaults.internalAffairs().copy(enabled = true),
        dungeon = ConfigDefaults.dungeon().copy(enabled = true, formationIds = listOf(1L)),
        inventory = ConfigDefaults.inventory().copy(enabled = true, openBoxes = true),
        vip = ConfigDefaults.vip().copy(enabled = true, showVip = true),
        surrenderRelease = ConfigDefaults.surrenderRelease().copy(autoSurrender = true, autoRelease = true),
        resourcePointSendGeneral = ConfigDefaults.resourcePointSendGeneral().copy(
            enabled = true,
            generalId = 1L,
            troopType = "mock-troop",
            formationId = 1L,
            stopAfterMinutes = 1
        ),
        autoLoot = ConfigDefaults.autoLoot().copy(enabled = true, selectedFormationIds = setOf(1L)),
        alarmWithdraw = ConfigDefaults.alarmWithdraw().copy(enabled = true, withdrawDefense = true),
        bulkTools = BulkToolConfig(
            enabledActions = setOf(BulkToolAction.CLAIM_TASK_ACHIEVEMENTS),
            accountIds = setOf(MOCK_ACCOUNT_ID)
        )
    )

    fun tasks() = TaskFactory.buildBackgroundTaskSet(MOCK_ACCOUNT_ID, configBundle())
}

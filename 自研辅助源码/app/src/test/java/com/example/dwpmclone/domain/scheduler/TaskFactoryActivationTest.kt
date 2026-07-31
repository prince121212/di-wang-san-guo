package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.MinistryProtocolCrop
import com.example.dwpmclone.domain.protocol.TaskType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskFactoryActivationTest {
    @Test
    fun disabledSavedPanelsDoNotCreateTasksThatImmediatelyStop() {
        val tasks = TaskFactory.buildBackgroundTaskSet(
            7L,
            AssistantConfigBundle(
                shuaHuang = ConfigDefaults.shuaHuang(),
                mine = ConfigDefaults.mine(),
                daily = ConfigDefaults.daily().copy(enabledSteps = emptySet()),
                general = ConfigDefaults.general().copy(
                    autoHeal = false,
                    autoEnergy = false,
                    keepFullLoyalty = false,
                    autoRescue = false
                ),
                internalAffairs = ConfigDefaults.internalAffairs(),
                dungeon = ConfigDefaults.dungeon(),
                inventory = ConfigDefaults.inventory(),
                autoLoot = ConfigDefaults.autoLoot(),
                sixMinistries = ConfigDefaults.sixMinistries().copy(stealEnabled = true),
                alarm = ConfigDefaults.alarm()
            )
        )

        assertEquals(listOf(TaskType.STATE_REFRESH), tasks.map { it.type })
    }

    @Test
    fun technologyOnlyBackgroundSearchAndVerifiedPlantingRemainRunnable() {
        val tasks = TaskFactory.buildBackgroundTaskSet(
            7L,
            AssistantConfigBundle(
                mine = ConfigDefaults.mine().copy(backgroundSearch = true),
                internalAffairs = ConfigDefaults.internalAffairs().copy(upgradeTechnology = true),
                sixMinistries = ConfigDefaults.sixMinistries().copy(
                    cropEnabled = true,
                    crop = MinistryProtocolCrop.VERIFIED_NAME
                )
            )
        )

        assertEquals(
            setOf(
                TaskType.STATE_REFRESH,
                TaskType.MINE_SEARCH,
                TaskType.INTERNAL,
                TaskType.SIX_MINISTRIES
            ),
            tasks.map { it.type }.toSet()
        )
    }

    @Test
    fun errorOnlyAlarmDoesNotCreateAHeartbeatPollingTask() {
        val tasks = TaskFactory.buildBackgroundTaskSet(
            7L,
            AssistantConfigBundle(
                alarm = ConfigDefaults.alarm().copy(
                    enabled = true,
                    incomingEnabled = false,
                    militaryEnabled = false,
                    errorEnabled = true
                )
            )
        )

        assertEquals(listOf(TaskType.STATE_REFRESH), tasks.map { it.type })
    }

    @Test
    fun enabledBrushAndMiningCreateHiddenIdlePreparationAlongsideMilitaryTasks() {
        val tasks = TaskFactory.buildBackgroundTaskSet(
            7L,
            AssistantConfigBundle(
                shuaHuang = ConfigDefaults.shuaHuang().copy(
                    enabled = true,
                    selectedFormationIds = setOf(7L)
                ),
                mine = ConfigDefaults.mine().copy(
                    enabled = true,
                    selectedFormationIds = setOf(7L)
                )
            )
        )

        assertEquals(
            setOf(
                TaskType.SHUA_HUANG,
                TaskType.BANDIT_PREFETCH,
                TaskType.AUTO_MINING,
                TaskType.MINE_PREFETCH,
                TaskType.STATE_REFRESH
            ),
            tasks.map { it.type }.toSet()
        )
    }
}

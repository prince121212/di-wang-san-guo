package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.DailyStep
import com.example.dwpmclone.domain.model.GeneralConfig
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.General
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GeneralMaintenanceTaskTest {
    @Test
    fun healingRunsOnceForEachDistinctFief() {
        val healCalls = mutableListOf<Long>()
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> =
                ProtocolResult.Ok(
                    listOf(
                        General(7L, "赵云", 90, 100, 80, status = 0, placeId = 1877),
                        General(8L, "关羽", 92, 100, 80, status = 0, placeId = 1877),
                        General(9L, "Ma Chao", 88, 100, 80, status = 0, placeId = 1878)
                    )
                )

            override suspend fun healGeneral(
                session: GameSession,
                generalId: Long
            ): ProtocolResult<StepResult> {
                healCalls += generalId
                return ProtocolResult.Ok(StepResult(true, "ok"))
            }
        }
        val task = GeneralMaintenanceTask(
            1L,
            GeneralConfig(
                autoHeal = true,
                keepFullLoyalty = false,
                autoEnergy = false,
                autoRescue = false
            )
        )

        val decision = SuspendRunner.run { task.step(context(protocol)) }

        assertTrue(decision is TaskDecision.Sleep)
        assertEquals(listOf(7L, 9L), healCalls)
    }

    @Test
    fun healAllRunsOncePerMaintenanceStepInsteadOfOncePerGeneral() {
        val healCalls = mutableListOf<Long>()
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> =
                ProtocolResult.Ok(
                    listOf(
                        General(7L, "赵云", 90, 100, 80, status = 0, placeId = 1877),
                        General(8L, "关羽", 92, 100, 80, status = 0, placeId = 1877)
                    )
                )

            override suspend fun healGeneral(
                session: GameSession,
                generalId: Long
            ): ProtocolResult<StepResult> {
                healCalls += generalId
                return ProtocolResult.Ok(StepResult(true, "治疗全部伤兵成功"))
            }
        }
        val task = GeneralMaintenanceTask(
            1L,
            GeneralConfig(
                autoHeal = true,
                keepFullLoyalty = false,
                autoEnergy = false,
                autoRescue = false
            )
        )
        val context = TaskContext(
            GameSession(1L, "mock", null, emptyMap(), 0),
            protocol,
            nowMillis = 1L
        )

        assertEquals(TaskDecision.Continue, SuspendRunner.run { task.prepare(context) })
        val decision = SuspendRunner.run { task.step(context) }

        assertTrue(decision is TaskDecision.Sleep)
        assertEquals(listOf(7L), healCalls)
    }

    @Test
    fun rejectedHealingStopsBeforeEnergyAndLoyaltyActions() {
        var energyCalls = 0
        var loyaltyCalls = 0
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> =
                ProtocolResult.Ok(
                    listOf(General(7L, "赵云", 90, 90, 20, status = 0, placeId = 1877))
                )

            override suspend fun healGeneral(
                session: GameSession,
                generalId: Long
            ): ProtocolResult<StepResult> =
                ProtocolResult.Ok(StepResult(false, "治疗失败"))

            override suspend fun addEnergy(
                session: GameSession,
                generalId: Long
            ): ProtocolResult<StepResult> {
                energyCalls++
                return ProtocolResult.Ok(StepResult(true, "加体成功"))
            }

            override suspend fun runDailyStep(
                session: GameSession,
                step: DailyStep
            ): ProtocolResult<StepResult> {
                loyaltyCalls++
                return ProtocolResult.Ok(StepResult(true, "加忠成功"))
            }
        }
        val task = GeneralMaintenanceTask(
            1L,
            GeneralConfig(
                autoHeal = true,
                keepFullLoyalty = true,
                autoEnergy = true,
                autoRescue = false
            )
        )

        val decision = SuspendRunner.run { task.step(context(protocol)) }

        assertEquals(TaskDecision.Stop("治疗失败"), decision)
        assertEquals(0, energyCalls)
        assertEquals(0, loyaltyCalls)
    }

    @Test
    fun rejectedEnergyStopsBeforeLoyaltyAndNextGeneral() {
        val energyCalls = mutableListOf<Long>()
        var loyaltyCalls = 0
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> =
                ProtocolResult.Ok(
                    listOf(
                        General(7L, "赵云", 90, 90, 20, status = 0, placeId = 1877),
                        General(8L, "关羽", 92, 90, 20, status = 0, placeId = 1877)
                    )
                )

            override suspend fun addEnergy(
                session: GameSession,
                generalId: Long
            ): ProtocolResult<StepResult> {
                energyCalls += generalId
                return ProtocolResult.Ok(StepResult(false, "加体失败"))
            }

            override suspend fun runDailyStep(
                session: GameSession,
                step: DailyStep
            ): ProtocolResult<StepResult> {
                loyaltyCalls++
                return ProtocolResult.Ok(StepResult(true, "加忠成功"))
            }
        }
        val task = GeneralMaintenanceTask(
            1L,
            GeneralConfig(
                autoHeal = false,
                keepFullLoyalty = true,
                autoEnergy = true,
                autoRescue = false
            )
        )

        val decision = SuspendRunner.run { task.step(context(protocol)) }

        assertEquals(TaskDecision.Stop("加体失败"), decision)
        assertEquals(listOf(7L), energyCalls)
        assertEquals(0, loyaltyCalls)
    }

    private fun context(protocol: GameProtocolClient) = TaskContext(
        GameSession(1L, "mock", null, emptyMap(), 0),
        protocol,
        nowMillis = 1_000L
    )
}

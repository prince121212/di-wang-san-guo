package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.LosslessConfig
import com.example.dwpmclone.domain.model.LosslessRule
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LosslessTaskMigrationTest {
    @Test
    fun savedDynamicLosslessRowsMapToTypedTask() {
        val values = JSONObject()
            .put("enabled", true)
            .put("fullTroops", true)
            .put("dailyLimit", 5)
            .put(
                "rows",
                JSONArray().put(
                    JSONObject()
                        .put("enabled", true)
                        .put("generalId", 7L)
                        .put("generalIds", JSONArray().put(7L).put(8L).put(9L))
                        .put("level", "10级")
                )
            )
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put(
                "configs",
                JSONObject().put(
                    "77::military_lossless",
                    JSONObject().put("values", values)
                )
            )

        val task = SavedConfigTaskPlanFactory.plan(77L, export)
            .tasks.single { it.type == TaskType.LOSSLESS } as LosslessTask

        assertEquals(TaskType.LOSSLESS, task.type)
        assertTrue(task.config.enabled)
        assertEquals(5, task.config.dailyLimit)
        assertEquals(listOf(7L, 8L, 9L), task.config.rules.single().generalIds)
        assertEquals(10, task.config.rules.single().level)
    }

    @Test
    fun taskFactorySchedulesLosslessBeforeBrushAndDungeon() {
        val bundle = AssistantConfigBundle(
            lossless = config(),
            shuaHuang = ConfigDefaults.shuaHuang().copy(
                enabled = true,
                selectedFormationIds = setOf(1L)
            ),
            dungeon = ConfigDefaults.dungeon().copy(
                enabled = true,
                formationIds = listOf(1L)
            )
        )

        val types = TaskFactory.buildBackgroundTaskSet(77L, bundle).map { it.type }

        assertTrue(types.indexOf(TaskType.LOSSLESS) < types.indexOf(TaskType.SHUA_HUANG))
        assertTrue(types.indexOf(TaskType.LOSSLESS) < types.indexOf(TaskType.DUNGEON))
    }

    @Test
    fun missingRealProtocolFailsClosedWithoutPretendingSuccess() {
        val task = LosslessTask(77L, config())
        val context = TaskContext(
            session = GameSession(77L, "token", null, emptyMap(), 1),
            protocol = MockGameProtocolClient(),
            nowMillis = 1_000L
        )

        val prepare = SuspendRunner.run { task.prepare(context) }
        val step = SuspendRunner.run { task.step(context) }

        assertEquals(TaskDecision.Continue, prepare)
        assertEquals(TaskDecision.Stop("无损真实协议尚未完整迁移，已禁止执行"), step)
    }

    @Test
    fun pollingAndRerollDoNotConsumeDailyAttemptOrSuppressSettlementPolling() {
        var calls = 0
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun runLossless(
                session: GameSession,
                config: LosslessConfig
            ): ProtocolResult<StepResult> {
                calls++
                return when (calls) {
                    1 -> ProtocolResult.Ok(StepResult(
                        true, "冷却中",
                        mapOf("phase" to "cooldown", "attemptConsumed" to "false")
                    ))
                    2 -> ProtocolResult.Ok(StepResult(
                        true, "阵容已刷新",
                        mapOf("phase" to "lineup-rerolled", "attemptConsumed" to "false")
                    ))
                    3 -> ProtocolResult.Ok(StepResult(
                        true, "已出征",
                        mapOf("phase" to "fighting", "attemptConsumed" to "true", "consumedTimes" to "1")
                    ))
                    else -> ProtocolResult.Ok(StepResult(
                        true, "待结算轮询",
                        mapOf("phase" to "settled", "attemptConsumed" to "false")
                    ))
                }
            }
        }
        val task = LosslessTask(77L, config().copy(dailyLimit = 1))
        val context = TaskContext(
            session = GameSession(77L, "token", null, emptyMap(), 0),
            protocol = protocol,
            nowMillis = 1_000L
        )

        repeat(3) {
            assertEquals(TaskDecision.Sleep(60_000), SuspendRunner.run { task.step(context) })
        }
        assertEquals(TaskDecision.Sleep(60_000), SuspendRunner.run { task.step(context) })

        assertEquals(4, calls)
    }

    private fun config() = LosslessConfig(
        enabled = true,
        fullTroops = true,
        dailyLimit = 5,
        rules = listOf(LosslessRule(true, listOf(7L), 10))
    )
}

package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AutoMiningActionDryRunServiceLifecycleTest {
    @Test
    fun savedUiAutoMiningConfigRunsOccupyWithoutImmediateWithdrawThroughRealSessionServiceLifecycle() {
        val savedPlan = SavedConfigTaskPlanFactory.plan(10001L, autoMiningSavedConfigExport())
        val originalTask = savedPlan.tasks.single { it.type == TaskType.AUTO_MINING } as MineTask
        val realSession = GameSession(
            accountId = 10001L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            channelExtra = autoMiningChannelExtra(),
            sourceMode = 1
        )
        val aligned = RealSessionTaskPlanAdapter.attachRealSession(savedPlan, realSession)
        val alignedTask = aligned.tasks.single { it.type == TaskType.AUTO_MINING } as MineTask
        val protocol = RecordingAutoMiningProtocol(
            SessionAwareGameProtocolClient(offlineActionFixturesAllowed = true)
        )
        val runner = LocalSchedulerLifecycleRunner(TaskScheduler(protocol))

        val batch = SuspendRunner.run {
            runner.runPlansOnceAndStopOnTerminal(tick = 41, plans = listOf(aligned), nowMillis = 1_000L)
        }
        val report = batch.runReports.single { it.type == TaskType.AUTO_MINING }

        assertEquals(setOf(1L), originalTask.config.selectedFormationIds)
        assertEquals(setOf(3L), alignedTask.config.selectedFormationIds)
        assertEquals(2, batch.runReports.size)
        assertEquals(1, batch.deferredIdleTaskCount)
        assertTrue(batch.runReports.none { it.type == TaskType.MINE_PREFETCH })
        assertEquals(TaskType.AUTO_MINING, report.type)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(5_000)), report.decisions)
        assertEquals(emptyList<TerminalTaskDecision>(), batch.terminalDecisions)
        assertEquals(emptyList<TaskStopReport>(), batch.stopReports)
        assertEquals(
            listOf(
                "validateSession",
                "searchMines",
                "occupyMine:3:257",
                "validateSession",
            ),
            protocol.calls
        )
        assertEquals(false, alignedTask.config.withdrawDefense)
        assertEquals("false", protocol.lastOccupyRaw["resourcePointFirstWrapperNetworkAllowed"])
        assertEquals("false", protocol.lastOccupyRaw["resourcePointSecondWrapperNetworkAllowed"])
        assertEquals("resource point p2=1: 1520010 + 1522010", protocol.lastOccupyRaw["payloadEvidence"])
        assertEquals("false", realSession.channelExtra["realActionNetworkAllowed"])
        assertTrue(aligned.sourceDescription.contains("session-metadata-aligned"))
    }

    private fun autoMiningSavedConfigExport(): JSONObject = JSONObject()
        .put("schema_version", "1.0-local")
        .put(
            "configs",
            JSONObject().put(
                "10001::auto_mining",
                JSONObject().put(
                    "values",
                    JSONObject()
                        .put("APKTOOL_RENAMED_0x7f070075", true) // auto mining enabled
                        .put("APKTOOL_RENAMED_0x7f070174", 11) // start x
                        .put("APKTOOL_RENAMED_0x7f070175", 22) // start y
                        .put("APKTOOL_RENAMED_0x7f070178", true) // hit empty mine
                        .put("APKTOOL_RENAMED_0x7f070172", false) // withdraw defense disabled in dry-run fixture
                        .put("APKTOOL_RENAMED_0x7f070179", true) // gold
                        .put("APKTOOL_RENAMED_0x7f070181", false) // silver
                )
            )
        )

    private fun autoMiningChannelExtra(): Map<String, String> = mapOf(
        "sourceMode" to "1",
        "userId" to "sample-user-10001",
        "serverUrl" to "http://game.example",
        "dm" to "999",
        "roleName" to "打矿样本君主",
        "level" to "42",
        "nation" to "蜀",
        "copper" to "1234567",
        "food" to "6543210",
        "mineTargetsHex" to "0000000001010101000b0016010002D00101000000270F00000000010202020021002c000002D0020200000022B8",
        "mineSelectedFormationIds" to "3",
        "occupyMineResultsJson" to """[
            {
                "mineId":"257",
                "formationId":3,
                "success":true,
                "message":"占矿出征成功",
                "generalIdHexChunks":["0000000000000007"],
                "resourcePointIdHex":"0000000000000101",
                "raw":{"evidence":"p2=1/1520010+1522010","battleId":"445566"}
            }
        ]""",
        "withdrawMineResultsJson" to """[
            {"mineId":"257","success":true,"message":"撤回驻防完成","defenseRecordIdHex":"0000000000000007","raw":{"evidence":"0a15260101"}}
        ]""",
        "networkSendAllowed" to "false",
        "realActionNetworkAllowed" to "false",
        "nativeWrapperNetworkSendAllowed" to "false"
    )
}

private class RecordingAutoMiningProtocol(
    private val delegate: GameProtocolClient
) : GameProtocolClient by delegate {
    val calls = mutableListOf<String>()
    var lastOccupyRaw: Map<String, String> = emptyMap()

    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> {
        calls += "validateSession"
        return delegate.validateSession(session)
    }

    override suspend fun searchMines(session: GameSession, config: MineConfig): ProtocolResult<List<MineSearchResult>> {
        calls += "searchMines"
        return delegate.searchMines(session, config)
    }

    override suspend fun occupyMine(session: GameSession, mine: MineSearchResult, formationId: Long): ProtocolResult<StepResult> {
        calls += "occupyMine:$formationId:${mine.id}"
        val result = delegate.occupyMine(session, mine, formationId)
        if (result is ProtocolResult.Ok) lastOccupyRaw = result.value.raw
        return result
    }

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>,
        maxMarchMinutes: Int,
        formationRules: List<FormationConfig>
    ): ProtocolResult<StepResult> = occupyMine(session, mine, generalIds.first())

    override suspend fun withdrawMineDefense(session: GameSession, battleId: Long): ProtocolResult<StepResult> {
        calls += "withdrawMineDefense:$battleId"
        return delegate.withdrawMineDefense(session, battleId)
    }
}

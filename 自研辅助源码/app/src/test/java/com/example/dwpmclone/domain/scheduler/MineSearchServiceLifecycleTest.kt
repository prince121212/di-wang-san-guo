package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MineSearchServiceLifecycleTest {
    @Test
    fun savedUiMineSearchConfigRunsReadOnlyMineScanThroughRealSessionServiceLifecycle() {
        val savedPlan = SavedConfigTaskPlanFactory.plan(10001L, mineSearchSavedConfigExport())
        val realSession = GameSession(
            accountId = 10001L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            channelExtra = mineSearchChannelExtra(),
            sourceMode = 1
        )
        val aligned = RealSessionTaskPlanAdapter.attachRealSession(savedPlan, realSession)
        val protocol = RecordingMineProtocol(SessionAwareGameProtocolClient())
        val runner = LocalSchedulerLifecycleRunner(TaskScheduler(protocol))

        val batch = SuspendRunner.run {
            runner.runPlansOnceAndStopOnTerminal(tick = 31, plans = listOf(aligned), nowMillis = 1_000L)
        }
        val report = batch.runReports.single { it.type == TaskType.MINE_SEARCH }

        assertEquals(2, batch.runReports.size)
        assertEquals(TaskType.MINE_SEARCH, report.type)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(12 * 60_000L)), report.decisions)
        assertEquals(emptyList<TerminalTaskDecision>(), batch.terminalDecisions)
        assertEquals(emptyList<TaskStopReport>(), batch.stopReports)
        assertEquals(listOf("validateSession", "validateSession", "searchMines"), protocol.calls)
        assertEquals(1, protocol.lastMineCount)
        assertEquals(MineType.GOLD, protocol.lastMineTypes.single())
        assertEquals(MapCoordinate(11, 22), protocol.lastMineCoordinates.single())
        assertTrue(aligned.sourceDescription.contains("session-metadata-aligned"))
    }

    @Test
    fun mineSearchOnlySavedConfigBuildsBackgroundSearchTaskWithoutAutoMineConfig() {
        val plan = SavedConfigTaskPlanFactory.plan(10001L, mineSearchSavedConfigExport())

        assertEquals(
            listOf(TaskType.STATE_REFRESH, TaskType.MINE_SEARCH),
            plan.tasks.map { it.type }
        )
        val task = plan.tasks.single { it.type == TaskType.MINE_SEARCH } as MineTask
        assertEquals(true, task.config.backgroundSearch)
        assertEquals(false, task.config.enabled)
        assertEquals(setOf(MineType.GOLD), task.config.selectedMineTypes)
        assertEquals(12, task.config.searchIntervalMinutes)
        assertEquals(true, task.config.onlyEmptyMine)
    }

    private fun mineSearchSavedConfigExport(): JSONObject = JSONObject()
        .put("schema_version", "1.0-local")
        .put(
            "configs",
            JSONObject().put(
                "10001::mine_search",
                JSONObject().put(
                    "values",
                    JSONObject()
                        .put("APKTOOL_RENAMED_0x7f07013f", 12) // search interval minutes
                        .put("APKTOOL_RENAMED_0x7f070141", true) // relogin on disconnect
                        .put("APKTOOL_RENAMED_0x7f070140", false) // stop on disconnect
                        .put("APKTOOL_RENAMED_0x7f0700ee", true) // only empty mine
                        .put("APKTOOL_RENAMED_0x7f0700c8", false) // only defended mine
                        .put("APKTOOL_RENAMED_0x7f0700f4", true) // gold
                        .put("APKTOOL_RENAMED_0x7f0701d4", false) // silver
                )
            )
        )

    private fun mineSearchChannelExtra(): Map<String, String> = mapOf(
        "sourceMode" to "1",
        "userId" to "sample-user-10001",
        "serverUrl" to "http://game.example",
        "dm" to "999",
        "roleName" to "找矿样本君主",
        "level" to "42",
        "nation" to "蜀",
        "copper" to "1234567",
        "food" to "6543210",
        "mineTargetsHex" to "0000000001010101000b0016010002D00101000000270F00000000010202020021002c000002D0020200000022B8",
        "selectedMineTypes" to "GOLD,SILVER",
        "onlyEmptyMine" to "true",
        "mineSelectedFormationIds" to "3",
        "networkSendAllowed" to "false",
        "realActionNetworkAllowed" to "false",
        "nativeWrapperNetworkSendAllowed" to "false"
    )
}

private class RecordingMineProtocol(
    private val delegate: GameProtocolClient
) : GameProtocolClient by delegate {
    val calls = mutableListOf<String>()
    var lastMineCount: Int = 0
    var lastMineTypes: List<MineType> = emptyList()
    var lastMineCoordinates: List<MapCoordinate> = emptyList()

    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> {
        calls += "validateSession"
        return delegate.validateSession(session)
    }

    override suspend fun searchMines(session: GameSession, config: MineConfig): ProtocolResult<List<MineSearchResult>> {
        calls += "searchMines"
        val result = delegate.searchMines(session, config)
        if (result is ProtocolResult.Ok) {
            lastMineCount = result.value.size
            lastMineTypes = result.value.map { it.mineType }
            lastMineCoordinates = result.value.map { it.coordinate }
        }
        return result
    }
}

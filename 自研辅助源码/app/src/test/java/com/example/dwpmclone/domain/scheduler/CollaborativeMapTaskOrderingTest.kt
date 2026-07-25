package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.cloud.CloudFirstMapCoordinator
import com.example.dwpmclone.domain.cloud.CloudMapResult
import com.example.dwpmclone.domain.cloud.CloudTarget
import com.example.dwpmclone.domain.cloud.CollaborativeMapClient
import com.example.dwpmclone.domain.cloud.ExpeditionResultReceipt
import com.example.dwpmclone.domain.cloud.ExpeditionResultRequest
import com.example.dwpmclone.domain.cloud.ObservationUploadRequest
import com.example.dwpmclone.domain.cloud.TargetRecommendationRequest
import com.example.dwpmclone.domain.cloud.UploadReceipt
import com.example.dwpmclone.domain.model.FormationFilterMode
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineConfig
import com.example.dwpmclone.domain.model.MineType
import com.example.dwpmclone.domain.model.ShuaHuangConfig
import com.example.dwpmclone.domain.protocol.BattleResult
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.MapSearchPolicy
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.protocol.MineSearchResult
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CollaborativeMapTaskOrderingTest {
    @Test
    fun shuaHuangUploadFailureNeverRecommendsOrDispatches() {
        val events = mutableListOf<String>()
        val protocol = OrderingProtocol(events)
        val cloud = OrderingCloudClient(events, uploadFailure = true)

        val decision = SuspendRunner.run {
            shuaTask().step(context(protocol, cloud))
        }

        assertEquals(TaskDecision.RetryAfter(10_000), decision)
        assertTrue(events.contains("scan-bandit"))
        assertTrue(events.contains("upload-BANDIT"))
        assertFalse(events.any { it.startsWith("recommend") })
        assertFalse(events.contains("dispatch-bandit"))
    }

    @Test
    fun mineRecommendationFailureNeverOccupies() {
        val events = mutableListOf<String>()
        val protocol = OrderingProtocol(events)
        val cloud = OrderingCloudClient(events, recommendationFailure = true)

        val decision = SuspendRunner.run {
            mineTask().step(context(protocol, cloud))
        }

        assertEquals(TaskDecision.RetryAfter(10_000), decision)
        assertEquals(
            listOf("scan-mine", "upload-MINE", "recommend-MINE"),
            events.filter { it in setOf("scan-mine", "upload-MINE", "recommend-MINE", "occupy-mine") }
        )
        assertFalse(events.contains("occupy-mine"))
    }

    @Test
    fun mismatchedCloudRevisionBlocksBothExpeditionTypes() {
        val banditEvents = mutableListOf<String>()
        val mineEvents = mutableListOf<String>()

        val banditDecision = SuspendRunner.run {
            shuaTask().step(
                context(
                    OrderingProtocol(banditEvents),
                    OrderingCloudClient(banditEvents, mismatchedRevision = true)
                )
            )
        }
        val mineDecision = SuspendRunner.run {
            mineTask().step(
                context(
                    OrderingProtocol(mineEvents),
                    OrderingCloudClient(mineEvents, mismatchedRevision = true)
                )
            )
        }

        assertEquals(TaskDecision.RetryAfter(10_000), banditDecision)
        assertEquals(TaskDecision.RetryAfter(10_000), mineDecision)
        assertFalse(banditEvents.contains("dispatch-bandit"))
        assertFalse(mineEvents.contains("occupy-mine"))
    }

    @Test
    fun successfulBanditAndMineTasksScanUploadRecommendThenExpedition() {
        val banditEvents = mutableListOf<String>()
        val mineEvents = mutableListOf<String>()

        val banditDecision = SuspendRunner.run {
            shuaTask().step(context(OrderingProtocol(banditEvents), OrderingCloudClient(banditEvents)))
        }
        val mineDecision = SuspendRunner.run {
            mineTask().step(context(OrderingProtocol(mineEvents), OrderingCloudClient(mineEvents)))
        }

        assertEquals(TaskDecision.Sleep(1_000), banditDecision)
        assertEquals(TaskDecision.Sleep(30_000), mineDecision)
        assertOrdered(banditEvents, "scan-bandit", "upload-BANDIT", "recommend-BANDIT", "dispatch-bandit", "report-BANDIT")
        assertOrdered(mineEvents, "scan-mine", "upload-MINE", "recommend-MINE", "occupy-mine", "report-MINE")
    }

    @Test
    fun failedResultReportStaysPendingAndNeverRedispatchesBeforeCloudAcceptsIt() {
        val events = mutableListOf<String>()
        val protocol = OrderingProtocol(events)
        val cloud = OrderingCloudClient(events, reportFailure = true)
        val task = mineTask()

        val first = SuspendRunner.run { task.step(context(protocol, cloud)) }
        val second = SuspendRunner.run { task.step(context(protocol, cloud)) }

        assertEquals(TaskDecision.RetryAfter(10_000), first)
        assertEquals(TaskDecision.RetryAfter(10_000), second)
        assertEquals(1, events.count { it == "occupy-mine" })
        assertEquals(2, events.count { it == "report-MINE" })
        assertEquals(1, events.count { it == "scan-mine" })
    }

    private fun context(protocol: GameProtocolClient, client: CollaborativeMapClient) =
        TaskContext(
            session = GameSession(
                accountId = 77L,
                tokenCiphertext = "token",
                expiresAtMillis = null,
                channelExtra = mapOf(
                    "collaborativeMapRequired" to "true",
                    "serverKey" to "351"
                ),
                sourceMode = 1
            ),
            protocol = protocol,
            nowMillis = 1_234L,
            cloudMap = CloudFirstMapCoordinator(client)
        )

    private fun shuaTask() = ShuaHuangTask(
        accountId = 77L,
        config = ShuaHuangConfig(
            enabled = true,
            dailyLimit = 500,
            start = MapCoordinate(10, 20),
            targetType = HuangTargetType.SHAN_ZEI,
            selectedFormationIds = setOf(1L),
            formationFilterMode = FormationFilterMode.UNIFIED,
            deleteMailForSpeed = false,
            autoConvertFoodToCopper = false
        )
    )

    private fun mineTask() = MineSearchMockTask(
        accountId = 77L,
        config = MineConfig(
            enabled = true,
            start = MapCoordinate(10, 20),
            hitEmptyMine = true,
            withdrawDefense = false,
            resourcePointLimit = 2,
            selectedMineTypes = setOf(MineType.GOLD),
            acceleratedMineTypes = emptySet(),
            selectedFormationIds = setOf(1L),
            backgroundSearch = false,
            reloginOnDisconnect = true,
            stopOnDisconnect = false,
            vibrateOnEmptyGold = false,
            vibrateOnEmptyRare = false,
            onlyEmptyMine = true,
            onlyDefendedMine = false
        )
    )

    private fun assertOrdered(events: List<String>, vararg expected: String) {
        val positions = expected.map(events::indexOf)
        assertTrue("missing/incorrect events: $events", positions.all { it >= 0 })
        assertEquals("incorrect event order: $events", positions.sorted(), positions)
    }
}

private class OrderingProtocol(
    private val events: MutableList<String>
) : GameProtocolClient by MockGameProtocolClient() {
    override suspend fun searchMap(
        session: GameSession,
        start: MapCoordinate,
        policy: MapSearchPolicy
    ): ProtocolResult<List<MapTarget>> {
        events += "scan-bandit"
        return ProtocolResult.Ok(
            listOf(MapTarget(101L, MapCoordinate(11, 21), HuangTargetType.SHAN_ZEI.name))
        )
    }

    override suspend fun dispatchFormation(
        session: GameSession,
        formationId: Long,
        target: MapTarget
    ): ProtocolResult<BattleResult> {
        events += "dispatch-bandit"
        return ProtocolResult.Ok(BattleResult(true, 1))
    }

    override suspend fun searchMines(
        session: GameSession,
        config: MineConfig
    ): ProtocolResult<List<MineSearchResult>> {
        events += "scan-mine"
        return ProtocolResult.Ok(
            listOf(
                MineSearchResult(
                    id = 201L,
                    coordinate = MapCoordinate(12, 22),
                    mineType = MineType.GOLD,
                    level = 5,
                    reserve = 999L,
                    isEmpty = true,
                    defenseCount = 0
                )
            )
        )
    }

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        formationId: Long
    ): ProtocolResult<StepResult> {
        events += "occupy-mine"
        return ProtocolResult.Ok(StepResult(true, "occupied"))
    }
}

private class OrderingCloudClient(
    private val events: MutableList<String>,
    private val uploadFailure: Boolean = false,
    private val recommendationFailure: Boolean = false,
    private val mismatchedRevision: Boolean = false,
    private val reportFailure: Boolean = false
) : CollaborativeMapClient {
    override suspend fun upload(request: ObservationUploadRequest): CloudMapResult<UploadReceipt> {
        events += "upload-${request.kind.name}"
        if (uploadFailure) return CloudMapResult.Err("OFFLINE", "offline", true)
        return CloudMapResult.Ok(
            UploadReceipt(
                accepted = request.observations.size,
                serverRevision = "rev-1",
                clientBatchId = request.clientBatchId
            )
        )
    }

    override suspend fun recommend(request: TargetRecommendationRequest): CloudMapResult<CloudTarget?> {
        events += "recommend-${request.kind.name}"
        if (recommendationFailure) return CloudMapResult.Err("RECOMMEND_FAILED", "failed", true)
        return CloudMapResult.Ok(
            CloudTarget(
                targetId = if (request.kind.name == "BANDIT") 901L else 902L,
                coordinate = MapCoordinate(13, 23),
                targetType = if (request.kind.name == "BANDIT") HuangTargetType.SHAN_ZEI.name else MineType.GOLD.name,
                level = 5,
                serverRevision = if (mismatchedRevision) "stale-rev" else request.acceptedRevision,
                raw = if (request.kind.name == "MINE") {
                    mapOf("reserve" to "999", "isEmpty" to "true", "defenseCount" to "0")
                } else {
                    emptyMap()
                }
            )
        )
    }

    override suspend fun reportExpedition(
        request: ExpeditionResultRequest
    ): CloudMapResult<ExpeditionResultReceipt> {
        events += "report-${request.kind.name}"
        if (reportFailure) return CloudMapResult.Err("REPORT_OFFLINE", "offline", true)
        return CloudMapResult.Ok(
            ExpeditionResultReceipt(
                accepted = true,
                serverRevision = "${request.acceptedRevision}-result",
                targetId = request.targetId
            )
        )
    }
}

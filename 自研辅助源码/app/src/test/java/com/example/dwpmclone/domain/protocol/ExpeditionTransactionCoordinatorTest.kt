package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.FormationRuntime
import com.example.dwpmclone.domain.model.FormationRuntimeStatus
import com.example.dwpmclone.domain.scheduler.SuspendRunner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ExpeditionTransactionCoordinatorTest {
    private var now = 1_000L
    private val store = InMemoryExpeditionTransactionStore()
    private val coordinator = ExpeditionTransactionCoordinator(store) { now }

    @Test
    fun overlappingGeneralsAreBlockedBeforeSecondNetworkSend() {
        val first = coordinator.begin(7L, "刷黄", "target-1", snapshot(1_000L, idle = true))
        val second = coordinator.begin(7L, "打矿", "target-2", snapshot(1_001L, idle = true))

        assertTrue(first is ProtocolResult.Ok)
        assertEquals("EXPEDITION_TRANSACTION_UNRESOLVED", (second as ProtocolResult.Err).code)
        assertTrue(second.retryable)
        assertEquals(1, store.list(7L).size)
    }

    @Test
    fun disjointGeneralsMayOwnIndependentTransactions() {
        val first = coordinator.begin(7L, "刷黄", "target-1", snapshot(1_000L, idle = true, generalId = 11L))
        val second = coordinator.begin(7L, "打矿", "target-2", snapshot(1_000L, idle = true, generalId = 12L))

        assertTrue(first is ProtocolResult.Ok)
        assertTrue(second is ProtocolResult.Ok)
        assertEquals(2, store.list(7L).size)
    }

    @Test
    fun uncertainSendSurvivesUntilFreshIdleSafetyWindow() {
        val started = coordinator.begin(7L, "刷黄", "target-1", snapshot(1_000L, idle = true)) as ProtocolResult.Ok
        coordinator.markUncertain(started.value, "socket timeout")

        now = 120_999L
        coordinator.reconcile(7L, snapshot(now, idle = true))
        assertEquals(ExpeditionTransactionState.UNCERTAIN, store.list(7L).single().state)

        now = 121_000L
        coordinator.reconcile(7L, snapshot(now, idle = true))
        assertTrue(store.list(7L).isEmpty())
    }

    @Test
    fun freshBusyStatePromotesUncertainSendToAccepted() {
        val started = coordinator.begin(7L, "副本", "stage-5", snapshot(1_000L, idle = true)) as ProtocolResult.Ok
        coordinator.markUncertain(started.value, "response lost")

        now = 2_000L
        coordinator.reconcile(7L, snapshot(now, idle = false))

        assertEquals(ExpeditionTransactionState.ACCEPTED, store.list(7L).single().state)
    }

    @Test
    fun acceptedSendClearsOnlyAfterFreshIdleConfirmation() {
        val started = coordinator.begin(7L, "掠夺", "fief-9", snapshot(1_000L, idle = true)) as ProtocolResult.Ok
        coordinator.markAccepted(started.value, "0x8522 accepted")

        now = 10_999L
        coordinator.reconcile(7L, snapshot(now, idle = true))
        assertEquals(1, store.list(7L).size)

        now = 11_000L
        coordinator.reconcile(7L, snapshot(now, idle = true))
        assertTrue(store.list(7L).isEmpty())
    }

    @Test
    fun durableTaskCanRecoverAndResolveItsLatestAcceptedTransaction() {
        val started = coordinator.begin(
            7L,
            "副本",
            "chapter=3,stage=12,code=49,chest=2,mode=clear",
            snapshot(1_000L, idle = true)
        ) as ProtocolResult.Ok
        coordinator.markAccepted(started.value, "0x8522 accepted")

        assertEquals(started.value.id, coordinator.latestUnresolved(7L, "副本")?.id)
        coordinator.resolve(7L, "副本")
        assertTrue(store.list(7L).isEmpty())
    }

    @Test
    fun ownershipRevokedBeforeSocketSendDoesNotLeaveAnUncertainGuard() {
        val result = SuspendRunner.run {
            coordinator.execute<StepResult>(
                accountId = 7L,
                action = "副本",
                targetKey = "stage-5",
                snapshot = snapshot(1_000L, idle = true),
                exceptionCode = "SEND_FAILED",
                exceptionLabel = "副本正式出征异常"
            ) {
                throw ExecutionRevokedBeforeNetworkException("dungeon/expedition")
            }
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("EXECUTION_REVOKED", (result as ProtocolResult.Err).code)
        assertTrue(store.list(7L).isEmpty())
    }

    private fun snapshot(
        observedAt: Long,
        idle: Boolean,
        generalId: Long = 11L
    ): ExpeditionPreflightSnapshot {
        val general = General(
            id = generalId,
            name = "将领$generalId",
            growth = 90,
            loyalty = 100,
            energy = 100,
            status = if (idle) 0 else 2,
            troopLimit = 2_000,
            raw = mapOf(
                "soldierTypeCode" to "3",
                "soldierCount" to "2000",
                "liveStateMillis" to observedAt.toString()
            )
        )
        val formation = FormationRuntime(
            id = generalId,
            name = "编队$generalId",
            generalIds = listOf(generalId),
            status = if (idle) FormationRuntimeStatus.IDLE else FormationRuntimeStatus.MARCHING,
            troopCount = 2_000
        )
        return ExpeditionPreflightSnapshot(
            generalIds = listOf(generalId),
            generalNames = listOf(general.name),
            generals = listOf(general),
            formations = listOf(formation),
            observedAtMillis = observedAt
        )
    }
}

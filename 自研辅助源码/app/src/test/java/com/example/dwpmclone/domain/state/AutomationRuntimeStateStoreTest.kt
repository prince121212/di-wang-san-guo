package com.example.dwpmclone.domain.state

import com.example.dwpmclone.domain.model.FormationRuntime
import com.example.dwpmclone.domain.model.FormationRuntimeStatus
import com.example.dwpmclone.domain.protocol.General
import com.example.dwpmclone.domain.protocol.TaskType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AutomationRuntimeStateStoreTest {
    @Test
    fun dispatchAcceptedLeaseBlocksSameGeneralForAnotherTask() {
        val store = AutomationRuntimeStateStore(defaultBusyLeaseMillis = 300_000L)
        val gate = store.commandGate
        val formation = formation(id = 10L, generalIds = listOf(101L))

        assertTrue(gate.tryReserveFormationForDispatch(1L, TaskType.SHUA_HUANG, "brush-1", formation, 1_000L, "brush yellow").isAllowed())
        gate.markDispatchAccepted(1L, TaskType.SHUA_HUANG, "brush-1", formation.id, 2_000L)

        val blocked = gate.tryReserveFormationForDispatch(1L, TaskType.DUNGEON, "dungeon-1", formation, 3_000L, "dungeon")

        assertTrue(blocked is GateResult.Blocked)
        assertTrue((blocked as GateResult.Blocked).reason.contains("locked by SHUA_HUANG/brush-1"))
        assertEquals(RuntimeGeneralState.MARCHING, store.generalLease(1L, 101L, 3_000L)?.state)
    }

    @Test
    fun recoveredState8004CannotReleasePostDispatchLease() {
        val store = AutomationRuntimeStateStore(defaultBusyLeaseMillis = 300_000L, serverIdleConfirmMillis = 10_000L)
        val gate = store.commandGate
        val formation = formation(id = 10L, generalIds = listOf(101L))
        gate.tryReserveFormationForDispatch(1L, TaskType.SHUA_HUANG, "brush-1", formation, 1_000L, "brush yellow")
        gate.markDispatchAccepted(1L, TaskType.SHUA_HUANG, "brush-1", formation.id, 2_000L)

        gate.reconcileServerState(
            accountId = 1L,
            generals = listOf(general(101L, raw = mapOf("source" to "recovered-state8004"))),
            formations = listOf(formation.copy(status = FormationRuntimeStatus.IDLE, raw = mapOf("source" to "state8004"))),
            nowMillis = 20_000L
        )

        val blocked = gate.tryReserveFormationForDispatch(1L, TaskType.DUNGEON, "dungeon-1", formation, 21_000L, "dungeon")
        assertTrue(blocked is GateResult.Blocked)
        assertEquals(RuntimeGeneralState.MARCHING, store.generalLease(1L, 101L, 21_000L)?.state)
    }

    @Test
    fun freshLiveIdleStateReleasesPostDispatchLease() {
        val store = AutomationRuntimeStateStore(defaultBusyLeaseMillis = 300_000L, serverIdleConfirmMillis = 10_000L)
        val gate = store.commandGate
        val formation = formation(id = 10L, generalIds = listOf(101L))
        gate.tryReserveFormationForDispatch(1L, TaskType.SHUA_HUANG, "brush-1", formation, 1_000L, "brush yellow")
        gate.markDispatchAccepted(1L, TaskType.SHUA_HUANG, "brush-1", formation.id, 2_000L)

        gate.reconcileServerState(
            accountId = 1L,
            generals = listOf(general(101L, raw = mapOf("liveStateMillis" to "15000"))),
            formations = listOf(formation.copy(status = FormationRuntimeStatus.IDLE, raw = mapOf("liveStateMillis" to "15000"))),
            nowMillis = 15_000L
        )

        assertNull(store.generalLease(1L, 101L, 15_000L))
        assertTrue(gate.tryReserveFormationForDispatch(1L, TaskType.DUNGEON, "dungeon-1", formation, 16_000L, "dungeon").isAllowed())
    }

    @Test
    fun unknownFormationStatusIsNotDispatchable() {
        val store = AutomationRuntimeStateStore(defaultBusyLeaseMillis = 300_000L)
        val unknown = formation(id = 10L, generalIds = listOf(101L)).copy(status = FormationRuntimeStatus.UNKNOWN)

        val result = store.commandGate.tryReserveFormationForDispatch(1L, TaskType.SHUA_HUANG, "brush-1", unknown, 1_000L, "brush yellow")

        assertTrue(result is GateResult.Blocked)
        assertTrue((result as GateResult.Blocked).reason.contains("server status is UNKNOWN"))
    }

    @Test
    fun brushPersistedAndLocalCountsResetWhenLocalCalendarDayChanges() {
        val store = AutomationRuntimeStateStore()
        val dayOne = java.util.Calendar.getInstance().apply {
            set(2026, java.util.Calendar.JULY, 12, 23, 59, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }.timeInMillis
        val dayTwo = java.util.Calendar.getInstance().apply {
            set(2026, java.util.Calendar.JULY, 13, 0, 1, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }.timeInMillis

        assertEquals(
            4,
            store.persistedBrushCountForDay(1L, TaskType.SHUA_HUANG, 4, dayOne)
        )
        assertEquals(
            2,
            store.addBrushConsumed(1L, TaskType.SHUA_HUANG, 2, dayOne)
        )
        // 即使 immutable session 仍携带昨日的4次，跨日后的基线和本地增量都必须归零。
        assertEquals(
            0,
            store.persistedBrushCountForDay(1L, TaskType.SHUA_HUANG, 4, dayTwo)
        )
        assertEquals(
            0,
            store.brushConsumedCount(1L, TaskType.SHUA_HUANG, dayTwo)
        )
    }

    @Test
    fun successfulBrushAndDungeonCountsAreForwardedToPersistentStatsSink() {
        val recorded = mutableListOf<List<Any>>()
        val store = AutomationRuntimeStateStore(
            dailySuccessSink = { accountId, type, count, nowMillis ->
                recorded += listOf(accountId, type, count, nowMillis)
            }
        )

        store.addBrushConsumed(7L, TaskType.SHUA_HUANG, 2, 1_000L)
        store.recordDailySuccess(7L, TaskType.DUNGEON, 1, 2_000L)

        assertEquals(
            listOf(
                listOf(7L, TaskType.SHUA_HUANG, 2, 1_000L),
                listOf(7L, TaskType.DUNGEON, 1, 2_000L)
            ),
            recorded
        )
    }

    private fun GateResult.isAllowed(): Boolean = this is GateResult.Allowed

    private fun formation(id: Long, generalIds: List<Long>) = FormationRuntime(
        id = id,
        name = "formation-$id",
        generalIds = generalIds,
        status = FormationRuntimeStatus.IDLE,
        troopCount = 100,
        raw = emptyMap()
    )

    private fun general(id: Long, raw: Map<String, String>) = General(
        id = id,
        name = "general-$id",
        growth = null,
        loyalty = null,
        energy = null,
        status = 0,
        raw = raw
    )
}

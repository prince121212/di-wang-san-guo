package com.example.dwpmclone.data.local

import com.example.dwpmclone.domain.localmap.LocalMapKind
import com.example.dwpmclone.domain.localmap.LocalMapQueryKey
import com.example.dwpmclone.domain.localmap.LocalMapSnapshot
import com.example.dwpmclone.domain.localmap.LocalMapTargetRecord
import com.example.dwpmclone.domain.model.MapCoordinate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalMapPersistenceTest {
    @Test
    fun jsonRoundTripKeepsRequiredMapMetadata() {
        val source = listOf(snapshot(
            query = query("qzone_351", "10,20|SHAN_ZEI"),
            scannedAtMillis = 2_000L,
            targets = listOf(record(
                id = 101L,
                first = 1_000L,
                last = 2_000L,
                invalidatedAt = 2_100L,
                reason = "dispatch-rejected"
            ))
        ))

        val restored = LocalMapJsonCodec.decode(LocalMapJsonCodec.encode(source)).single()
        val target = restored.targets.single()

        assertEquals("qzone_351", restored.query.serverId)
        assertEquals(MapCoordinate(11, 21), target.coordinate)
        assertEquals(3, target.level)
        assertEquals("3210", target.filterFields["compositionCode"])
        assertEquals(1_000L, target.firstDiscoveredAtMillis)
        assertEquals(2_000L, target.lastValidatedAtMillis)
        assertEquals(2_100L, target.invalidatedAtMillis)
        assertEquals("dispatch-rejected", target.invalidReason)
    }

    @Test
    fun rescanPreservesFirstDiscoveryAndMarksMissingTargetInvalid() {
        val query = query("qzone_351", "10,20|SHAN_ZEI")
        val original = snapshot(query, 1_000L, listOf(
            record(101L, first = 500L, last = 1_000L),
            record(102L, first = 700L, last = 1_000L)
        ))
        val rescan = snapshot(query, 2_000L, listOf(
            record(101L, first = 2_000L, last = 2_000L)
        ))

        val merged = LocalMapSnapshotReducer.replace(listOf(original), rescan).single()
        val stillVisible = merged.targets.single { it.targetId == 101L }
        val missing = merged.targets.single { it.targetId == 102L }

        assertEquals(500L, stillVisible.firstDiscoveredAtMillis)
        assertEquals(2_000L, stillVisible.lastValidatedAtMillis)
        assertTrue(stillVisible.active)
        assertEquals(2_000L, missing.invalidatedAtMillis)
        assertEquals("missing-from-rescan", missing.invalidReason)
    }

    @Test
    fun invalidationIsServerScopedAndExhaustedQueriesBecomeStale() {
        val nearby = snapshot(query("qzone_351", "nearby"), 1_000L, listOf(record(101L)))
        val nationwide = snapshot(query("qzone_351", "nationwide"), 1_100L, listOf(record(101L)))
        val otherServer = snapshot(query("qzone_999", "nearby"), 1_200L, listOf(record(101L)))

        val updated = LocalMapSnapshotReducer.invalidate(
            listOf(nearby, nationwide, otherServer),
            nearby.query,
            targetId = 101L,
            invalidatedAtMillis = 2_000L,
            reason = "occupied"
        )

        val sameServer = updated.filter { it.query.serverId == "qzone_351" }
        assertTrue(sameServer.all { it.scannedAtMillis == 0L })
        assertTrue(sameServer.flatMap { it.targets }.none { it.active })
        assertFalse(updated.single { it.query.serverId == "qzone_999" }.targets.single().active.not())
        assertNull(updated.single { it.query.serverId == "qzone_999" }.targets.single().invalidatedAtMillis)
    }

    private fun query(serverId: String, fingerprint: String) = LocalMapQueryKey(
        accountId = 7L,
        serverId = serverId,
        kind = LocalMapKind.BANDIT,
        fingerprint = fingerprint
    )

    private fun snapshot(
        query: LocalMapQueryKey,
        scannedAtMillis: Long,
        targets: List<LocalMapTargetRecord>
    ) = LocalMapSnapshot(query, scannedAtMillis, targets)

    private fun record(
        id: Long,
        first: Long = 500L,
        last: Long = 1_000L,
        invalidatedAt: Long? = null,
        reason: String? = null
    ) = LocalMapTargetRecord(
        targetId = id,
        coordinate = MapCoordinate(11, 21),
        type = "山贼",
        level = 3,
        filterFields = mapOf("compositionCode" to "3210"),
        firstDiscoveredAtMillis = first,
        lastValidatedAtMillis = last,
        invalidatedAtMillis = invalidatedAt,
        invalidReason = reason
    )
}

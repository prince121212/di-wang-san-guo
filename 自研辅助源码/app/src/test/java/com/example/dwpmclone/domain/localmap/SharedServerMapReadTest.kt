package com.example.dwpmclone.domain.localmap

import com.example.dwpmclone.domain.model.MapCoordinate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Two accounts on one server observe one map, so they must read one map.
 *
 * Reading per-account made them rediscover it independently: on a real device
 * account 176 held 215 cached bandits while account 202 held 5, both on
 * qzone_352 scanning from the same start point, so the second account swept
 * five coordinates per tick to relearn what the first already knew. It is also
 * why sharing needed a cloud round trip that the same process could answer for
 * free.
 */
class SharedServerMapReadTest {
    private val store = MemoryLocalMapStore()

    private fun key(accountId: Long) = LocalMapQueryKey(
        accountId = accountId,
        serverId = "qzone_352",
        kind = LocalMapKind.BANDIT,
        fingerprint = "91,26|SHAN_ZEI"
    )

    private fun record(
        id: Long,
        x: Int,
        lastValidated: Long = 1_000L,
        invalidatedAt: Long? = null
    ) = LocalMapTargetRecord(
        targetId = id,
        coordinate = MapCoordinate(x, 26),
        type = "山贼",
        level = 8,
        filterFields = mapOf("compositionCode" to "3100"),
        firstDiscoveredAtMillis = 500L,
        lastValidatedAtMillis = lastValidated,
        invalidatedAtMillis = invalidatedAt
    )

    @Test
    fun apeersDiscoveriesAreVisibleToEveryAccountOnThatServer() {
        store.replace(
            LocalMapSnapshot(key(176L), 2_000L, listOf(record(1, 100), record(2, 101)))
        )
        store.replace(LocalMapSnapshot(key(202L), 1_000L, listOf(record(3, 102))))

        val shared = store.readShared(key(202L))

        assertEquals(3, shared!!.targets.size)
        // The freshest contributing scan sets the timestamp, so the caller's
        // staleness check behaves as if it had scanned that recently itself.
        assertEquals(2_000L, shared.scannedAtMillis)
    }

    @Test
    fun aTargetOneAccountFoundGoneIsGoneForEveryone() {
        store.replace(LocalMapSnapshot(key(176L), 2_000L, listOf(record(1, 100))))
        store.replace(
            LocalMapSnapshot(
                key(202L),
                3_000L,
                listOf(record(1, 100, lastValidated = 900L, invalidatedAt = 2_500L))
            )
        )

        val shared = store.readShared(key(176L))

        assertEquals(1, shared!!.targets.size)
        assertTrue(shared.targets.single().active.not())
    }

    @Test
    fun adifferentServerOrRegionIsNeverMerged() {
        store.replace(LocalMapSnapshot(key(176L), 2_000L, listOf(record(1, 100))))

        val otherServer = key(202L).copy(serverId = "qzone_999")
        val otherRegion = key(202L).copy(fingerprint = "10,20|SHAN_ZEI")
        val otherKind = key(202L).copy(kind = LocalMapKind.MINE)

        assertNull(store.readShared(otherServer))
        assertNull(store.readShared(otherRegion))
        assertNull(store.readShared(otherKind))
    }

    @Test
    fun anUnscannedRegionStillReportsNothing() {
        assertNull(store.readShared(key(176L)))
    }
}

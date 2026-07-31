package com.example.dwpmclone.ui.web

import com.example.dwpmclone.domain.localmap.LocalMapTargetRecord
import com.example.dwpmclone.domain.model.MapCoordinate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalMapApiMapperTest {
    @Test
    fun banditResponseContainsOnlyFreshActiveLocalRecords() {
        val active = record(
            id = 101L,
            type = "山贼",
            last = 9_500L,
            fields = mapOf(
                "level" to "3",
                "compositionCode" to "3210",
                "resource" to "资源、装备",
                "lootIds" to "[12,13]"
            )
        )
        val stale = record(102L, "山贼", last = 1_000L)
        val invalid = record(103L, "山贼", last = 9_800L, invalidatedAt = 9_900L)

        val payload = LocalMapApiMapper.bandits(
            serverId = "qzone_351",
            records = listOf(active, stale, invalid),
            nowMillis = 10_000L,
            ttlMillis = 1_000L
        )
        val points = payload.getJSONArray("points")
        val point = points.getJSONObject(0)

        assertEquals("qzone_351", payload.getString("serverKey"))
        assertEquals(1, points.length())
        assertEquals(101L, point.getLong("id"))
        assertEquals(3, point.getInt("level"))
        assertEquals("3210", point.getString("compositionCode"))
        assertEquals(listOf("资源", "装备"), (0 until point.getJSONArray("dropCategories").length()).map {
            point.getJSONArray("dropCategories").getString(it)
        })
        assertFalse(point.getBoolean("selectedForAttack"))
    }

    @Test
    fun mineResponseUsesSharedPageSchemaAndLocalTtl() {
        val payload = LocalMapApiMapper.mines(
            serverId = "qzone_351",
            records = listOf(record(
                id = 201L,
                type = "CRYSTAL",
                last = 9_500L,
                fields = mapOf(
                    "level" to "5",
                    "reserve" to "800",
                    "isEmpty" to "false",
                    "defenseCount" to "2",
                    "ownerName" to "玩家甲"
                )
            )),
            nowMillis = 10_000L,
            ttlMillis = 1_000L
        )
        val point = payload.getJSONArray("points").getJSONObject(0)

        assertEquals(1_000L, payload.getLong("ttlMs"))
        assertEquals("水晶矿", point.getString("kind"))
        assertEquals(800L, point.getLong("amountA"))
        assertEquals(2, point.getInt("defenderCount"))
        assertTrue(point.getBoolean("playerOccupied"))
        assertEquals(500L, point.getLong("remainingMs"))
    }

    private fun record(
        id: Long,
        type: String,
        last: Long,
        fields: Map<String, String> = emptyMap(),
        invalidatedAt: Long? = null
    ) = LocalMapTargetRecord(
        targetId = id,
        coordinate = MapCoordinate(11, 21),
        type = type,
        level = fields["level"]?.toIntOrNull(),
        filterFields = fields,
        firstDiscoveredAtMillis = last - 100L,
        lastValidatedAtMillis = last,
        invalidatedAtMillis = invalidatedAt,
        invalidReason = invalidatedAt?.let { "invalid" }
    )
}

package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class BrushCenterRecommendationPolicyTest {
    @Test
    fun choosesMajorityFiefAndClampsOnlyUiCenter() {
        val recommendation = BrushCenterRecommendationPolicy.recommend(
            generalIds = listOf(11L, 12L, 13L),
            generals = listOf(
                BrushCenterGeneral(11L, "甲", 101L),
                BrushCenterGeneral(12L, "乙", 202L),
                BrushCenterGeneral(13L, "丙", 202L)
            ),
            fiefs = listOf(
                BrushFiefLocation(101L, "一号封地", "洛阳", 30, 20),
                BrushFiefLocation(202L, "二号封地", "成都", 190, 72)
            )
        )

        assertEquals(202L, recommendation.fiefId)
        assertEquals(186, recommendation.x)
        assertEquals(55, recommendation.y)
        assertEquals(186, recommendation.worldX)
        assertEquals(72, recommendation.worldY)
        assertEquals(mapOf(101L to 1, 202L to 2), recommendation.fiefCounts)
    }

    @Test
    fun tieUsesFirstSelectedGeneralFiefLikeDesktop() {
        val recommendation = BrushCenterRecommendationPolicy.recommend(
            generalIds = listOf(12L, 11L),
            generals = listOf(
                BrushCenterGeneral(11L, "甲", 101L),
                BrushCenterGeneral(12L, "乙", 202L)
            ),
            fiefs = listOf(
                BrushFiefLocation(101L, "一号封地", "洛阳", 30, 20),
                BrushFiefLocation(202L, "二号封地", "成都", 40, 25)
            )
        )

        assertEquals(202L, recommendation.fiefId)
        assertEquals(40, recommendation.x)
        assertEquals(25, recommendation.y)
    }

    @Test
    fun missingCoordinateFailsInsteadOfReturningFakeDefault() {
        val error = assertThrows(IllegalStateException::class.java) {
            BrushCenterRecommendationPolicy.recommend(
                generalIds = listOf(11L),
                generals = listOf(BrushCenterGeneral(11L, "甲", 101L)),
                fiefs = emptyList()
            )
        }

        assertEquals("登录缓存中没有封地ID 101 的世界坐标，请重新启动该账号", error.message)
    }
}

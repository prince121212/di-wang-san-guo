package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.DailyStep
import org.junit.Assert.assertEquals
import org.junit.Test

class DailyProtocolShapesTest {
    @Test
    fun buildExecutionPlanUsesRecoveredDailyOrderInsteadOfInputSetOrder() {
        val plan = DailyProtocolShapes.buildExecutionPlan(
            enabledSteps = linkedSetOf(
                DailyStep.DONATE_TECH,
                DailyStep.SURPRISE_BOX,
                DailyStep.SIGN_IN,
                DailyStep.DONATE_COPPER,
                DailyStep.ADD_LOYALTY
            ),
            donationFactorFz = 2
        )

        assertEquals(
            listOf(
                DailyStep.SIGN_IN,
                DailyStep.SURPRISE_BOX,
                DailyStep.ADD_LOYALTY,
                DailyStep.DONATE_COPPER,
                DailyStep.DONATE_TECH
            ),
            plan.map { it.step }
        )
        assertEquals(
            listOf("000000000000000000006202"),
            plan.first { it.step == DailyStep.SIGN_IN }.payloads
        )
        assertEquals("已领取惊喜宝箱！", plan.first { it.step == DailyStep.SURPRISE_BOX }.successLog)
        assertEquals(1_000L, plan.first { it.step == DailyStep.DONATE_COPPER }.delayAfterMillis)
    }

    @Test
    fun donationPayloadsUseRecoveredFzAmountFormula() {
        assertEquals("00000000000000000018140c00000000000007d000000000000000000000000000000000", DailyProtocolShapes.donateCopper(fz = 2))
        assertEquals("00000000000000000018140c000000000000000000000000000017700000000000000000", DailyProtocolShapes.donateFood(fz = 2))
        assertEquals("00000000000000000005140a00000007d0", DailyProtocolShapes.donateTech(fz = 2))
    }

    @Test
    fun convertHalfFoodToCopperIsRecoveredAsDelegatedDailyStep() {
        val plan = DailyProtocolShapes.buildExecutionPlan(
            enabledSteps = linkedSetOf(DailyStep.CONVERT_HALF_FOOD_TO_COPPER)
        )

        assertEquals(listOf(DailyStep.CONVERT_HALF_FOOD_TO_COPPER), plan.map { it.step })
        assertEquals(emptyList<String>(), plan.single().payloads)
        assertEquals("已转换一半粮食到铜钱！", plan.single().successLog)
        assertEquals(true, DailyStep.CONVERT_HALF_FOOD_TO_COPPER in DailyProtocolShapes.recoveredSteps)
    }
}

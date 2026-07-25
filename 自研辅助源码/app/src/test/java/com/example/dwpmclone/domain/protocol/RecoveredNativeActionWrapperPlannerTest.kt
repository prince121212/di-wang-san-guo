package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RecoveredNativeActionWrapperPlannerTest {
    @Test
    fun plansBrushYellowExpeditionWrapperAsDryRunOnly() {
        val gameHex = "0000000000000000001a15200a02000000000000000100000000000000020000000000000065"

        val plan = RecoveredNativeActionWrapperPlanner.plan(gameHex)

        assertEquals(GameHexCategory.EXPEDITION_ACTION, plan.descriptor.category)
        assertEquals("lx + key + gameHex + lb", plan.bodyShape)
        assertEquals("application/x-www-form-urlencoded", plan.contentType)
        assertEquals("/kingWapServer/HttpClient", plan.endpointPath)
        assertEquals(listOf("lx", "key", "lb"), plan.requiredNativeFields)
        assertEquals(listOf("lx", "key", "lb"), plan.missingNativeFields)
        assertFalse(plan.networkSendAllowed)
        assertTrue(plan.blocker.contains("禁止真实发送"))
    }

    @Test
    fun masksConcatCandidateWhenNativeFieldsAreProvidedButStillBlocksSend() {
        val gameHex = "000000000000000000006200"

        val plan = RecoveredNativeActionWrapperPlanner.plan(
            gameHex,
            RecoveredNativeWrapperFields(lx = "lx-secret", key = "key-secret", lb = "lb-secret")
        )

        assertEquals(GameHexCategory.STATE_CHANGING_ACTION, plan.descriptor.category)
        assertTrue(plan.missingNativeFields.isEmpty())
        assertNotNull(plan.maskedRawConcatCandidate)
        assertTrue(plan.maskedRawConcatCandidate!!.contains(plan.descriptor.normalizedHex))
        assertFalse(plan.maskedRawConcatCandidate!!.contains("secret"))
        assertFalse(plan.networkSendAllowed)
    }

    @Test
    fun readOnlyGameHexIsRoutedAwayFromNativeActionWrapper() {
        val plan = RecoveredNativeActionWrapperPlanner.plan(GameCoordinateCodec.buildTargetSearch(6, 6))

        assertEquals(GameHexCategory.READ_ONLY_QUERY, plan.descriptor.category)
        assertFalse(plan.networkSendAllowed)
        assertTrue(plan.blocker.contains("041540/041542 allow-list gate"))
    }

    @Test
    fun batchRefill1229NativeWrapperPlanIsStateChangingDryRunOnly() {
        val plan = RecoveredNativeActionWrapperPlanner.plan(
            BatchRefillTroopsShape.build(listOf("6b4dac", "686b99")),
            RecoveredNativeWrapperFields(lx = "lxVALUE", key = "keyVALUE", lb = "lbVALUE")
        )

        assertEquals("1229", plan.descriptor.opcodeHex)
        assertEquals(GameHexCategory.STATE_CHANGING_ACTION, plan.descriptor.category)
        assertTrue(plan.missingNativeFields.isEmpty())
        assertNotNull(plan.maskedRawConcatCandidate)
        assertFalse(plan.networkSendAllowed)
        assertTrue(plan.blocker.contains("禁止真实发送"))
    }

    @Test
    fun extractsWrapperFieldsFromImportedNativeTraceExtras() {
        val fields = RecoveredNativeWrapperFieldExtractor.from(
            mapOf(
                "nativeWrapperLx" to "lxVALUE",
                "recoveredNativeKey" to "keyVALUE",
                "nativeWrapperLb" to "lbVALUE",
                "recoveredNativeSession" to "sessionVALUE",
                "recoveredNativePassCode" to "passVALUE"
            )
        )

        assertEquals("lxVALUE", fields.lx)
        assertEquals("keyVALUE", fields.key)
        assertEquals("lbVALUE", fields.lb)
        assertEquals("sessionVALUE", fields.session)
        assertEquals("passVALUE", fields.passCode)
    }

    @Test
    fun extractsDerivedWrapperFieldsFromImportedRawBodyCalibration() {
        val fields = RecoveredNativeWrapperFieldExtractor.from(
            mapOf(
                "derivedNativeWrapperLx" to "lxVALUE",
                "derivedNativeWrapperKey" to "keyVALUE",
                "derivedNativeWrapperLb" to "lbVALUE"
            )
        )

        assertEquals("lxVALUE", fields.lx)
        assertEquals("keyVALUE", fields.key)
        assertEquals("lbVALUE", fields.lb)
    }

}

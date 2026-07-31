package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.GameSession
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NationalCitizenDailyPolicyTest {
    @Test
    fun detectsLiveTitleAndBothDecimalAndHexOfficeIds() {
        assertTrue(NationalCitizenDailyPolicy.isNationalCitizen(session(mapOf("title" to "国民"))))
        assertTrue(NationalCitizenDailyPolicy.isNationalCitizen(session(mapOf("officeId" to "256"))))
        assertTrue(NationalCitizenDailyPolicy.isNationalCitizen(session(mapOf("officeIdRaw" to "0x0100"))))
        assertFalse(NationalCitizenDailyPolicy.isNationalCitizen(session(mapOf("title" to "太守"))))
    }

    private fun session(extra: Map<String, String>) = GameSession(
        accountId = 1L,
        tokenCiphertext = "real",
        expiresAtMillis = null,
        channelExtra = extra,
        sourceMode = 1
    )
}

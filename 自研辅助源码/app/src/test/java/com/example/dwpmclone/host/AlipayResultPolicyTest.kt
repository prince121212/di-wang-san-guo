package com.example.dwpmclone.host

import org.junit.Assert.assertTrue
import org.junit.Test

class AlipayResultPolicyTest {
    @Test fun sdkSuccessStillRequiresServerConfirmation() {
        assertTrue(AlipayResultPolicy.message("9000").contains("服务器确认"))
    }
    @Test fun unknownAndCanceledResultsKeepOriginalOrder() {
        for (status in listOf("8000", "6004", "6002", "6001", "4000", null)) {
            assertTrue(AlipayResultPolicy.message(status).contains("原订单"))
        }
    }
}

package com.example.dwpmclone.host

import org.junit.Assert.*
import org.junit.Test

class MembershipPlansTest {
    @Test fun approvedPricesAndTerms() {
        assertEquals(listOf("9.90", "25.90", "49.90"), MembershipPlans.all.map { it.price })
        assertEquals(listOf(30, 90, 365), MembershipPlans.all.map { it.days })
        assertNull(MembershipPlans.find("unknown"))
    }
}

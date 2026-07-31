package com.example.dwpmclone.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionSecretPolicyTest {
    @Test
    fun `separates authentication material from public session metadata`() {
        val source = linkedMapOf(
            "dm" to "778899",
            "userId" to "login-user",
            "accountWithSuffix" to "login-user@example",
            "accessToken" to "token-value",
            "serverUrl" to "http://game.example",
            "roleId" to "42",
            "roleName" to "测试君主"
        )

        val secrets = SessionSecretPolicy.secretFields(source)
        val public = SessionSecretPolicy.publicFields(source)

        assertEquals(setOf("dm", "userId", "accountWithSuffix", "accessToken"), secrets.keys)
        assertTrue(public.keys.containsAll(setOf("serverUrl", "roleId", "roleName")))
        assertFalse(public.keys.any(SessionSecretPolicy::isSensitiveKey))
    }
}

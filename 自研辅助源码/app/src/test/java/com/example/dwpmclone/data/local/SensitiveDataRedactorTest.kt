package com.example.dwpmclone.data.local

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SensitiveDataRedactorTest {
    @Test
    fun `redacts json assignments query tokens bearer tokens and session ids`() {
        val raw = """
            {"password":"secret-pass","token":"abc.def","dm":987,"gameHttp":"http://game/private"}
            password=another dm:12345 gameHttp=http://game/HttpClient
            GET /path?token=query-secret&dm=5566 Authorization: Bearer header.secret.value
        """.trimIndent()

        val redacted = SensitiveDataRedactor.redact(raw)

        listOf(
            "secret-pass",
            "abc.def",
            "another",
            "12345",
            "http://game/private",
            "http://game/HttpClient",
            "query-secret",
            "5566",
            "header.secret.value"
        ).forEach { secret -> assertFalse("leaked $secret in $redacted", redacted.contains(secret)) }
        assertTrue(redacted.contains("[REDACTED]"))
    }

    @Test
    fun `keeps ordinary account action and result text`() {
        val text = "账号 42 刷黄出征成功，目标=山贼(91,26)"
        assertTrue(SensitiveDataRedactor.redact(text) == text)
    }
}

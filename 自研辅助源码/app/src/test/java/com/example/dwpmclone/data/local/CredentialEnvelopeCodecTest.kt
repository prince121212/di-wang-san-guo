package com.example.dwpmclone.data.local

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CredentialEnvelopeCodecTest {
    @Test
    fun versionedEnvelopeRoundTripsWithoutPlaintext() {
        val iv = ByteArray(12) { it.toByte() }
        val ciphertext = byteArrayOf(0x01, 0x23, 0x45, 0x67)

        val encoded = CredentialEnvelopeCodec.encode(iv, ciphertext)
        val decoded = CredentialEnvelopeCodec.decode(encoded)

        assertTrue(encoded.startsWith("v1:"))
        assertArrayEquals(iv, decoded.iv)
        assertArrayEquals(ciphertext, decoded.ciphertext)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsUnknownEnvelopeVersion() {
        CredentialEnvelopeCodec.decode("v2:000102030405060708090a0b:0123")
    }
}

package com.example.dwpmclone.data.local

import android.content.Context

interface CredentialVault {
    fun savePassword(accountId: Long, password: String)
    fun loadPassword(accountId: Long): String?
    fun hasPassword(accountId: Long): Boolean
    fun delete(accountId: Long)
    fun clear()
}

/** Passwords are stored only as AES-GCM ciphertext backed by an Android Keystore key. */
class KeystoreCredentialVault(context: Context) : CredentialVault {
    private val store = KeystoreAesGcmStore(
        context = context,
        preferencesName = PREFERENCES_NAME,
        keyAlias = KEY_ALIAS,
        legacyKeyAliases = listOf(LEGACY_KEY_ALIAS)
    )

    override fun savePassword(accountId: Long, password: String) {
        require(accountId > 0L) { "账号 ID 无效" }
        require(password.isNotEmpty()) { "密码不能为空" }
        store.put(key(accountId), password)
    }

    override fun loadPassword(accountId: Long): String? =
        store.get(key(accountId))

    override fun hasPassword(accountId: Long): Boolean =
        store.contains(key(accountId))

    override fun delete(accountId: Long) = store.remove(key(accountId))

    override fun clear() = store.clear()

    private fun key(accountId: Long): String = "password_$accountId"

    private companion object {
        const val PREFERENCES_NAME = "dwpm_secure_credentials"
        const val KEY_ALIAS = "dwpm_local_credentials_v2"
        const val LEGACY_KEY_ALIAS = "dwpm_local_credentials_v1"
    }
}

data class CredentialEnvelope(val iv: ByteArray, val ciphertext: ByteArray)

object CredentialEnvelopeCodec {
    private const val VERSION = "v1"

    fun encode(iv: ByteArray, ciphertext: ByteArray): String {
        require(iv.size == 12) { "AES-GCM IV 必须为12字节" }
        require(ciphertext.isNotEmpty()) { "凭据密文不能为空" }
        return "$VERSION:${iv.toHex()}:${ciphertext.toHex()}"
    }

    fun decode(value: String): CredentialEnvelope {
        val parts = value.split(':')
        require(parts.size == 3 && parts[0] == VERSION) { "凭据密文版本无效" }
        val iv = parts[1].hexToBytes()
        val ciphertext = parts[2].hexToBytes()
        require(iv.size == 12 && ciphertext.isNotEmpty()) { "凭据密文格式无效" }
        return CredentialEnvelope(iv, ciphertext)
    }

    private fun ByteArray.toHex(): String = joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }

    private fun String.hexToBytes(): ByteArray {
        require(length % 2 == 0 && all { it.isDigit() || it.lowercaseChar() in 'a'..'f' }) {
            "十六进制密文无效"
        }
        return ByteArray(length / 2) { index ->
            substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
    }
}

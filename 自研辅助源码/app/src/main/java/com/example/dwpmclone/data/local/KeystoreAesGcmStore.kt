package com.example.dwpmclone.data.local

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Small encrypted-preferences primitive shared by the password and session-secret repositories.
 * The key never leaves Android Keystore; ciphertext writes use commit because the caller treats
 * persistence as a safety gate before enabling unattended execution.
 */
internal class KeystoreAesGcmStore(
    context: Context,
    private val preferencesName: String,
    private val keyAlias: String,
    private val legacyKeyAliases: List<String> = emptyList()
) {
    private val preferences = context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)

    fun put(key: String, plaintext: String) {
        require(key.isNotBlank()) { "加密字段 key 不能为空" }
        require(plaintext.isNotEmpty()) { "加密内容不能为空" }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, encryptionKey())
        val ciphertext = cipher.doFinal(plaintext.toByteArray(StandardCharsets.UTF_8))
        check(
            preferences.edit()
                .putString(key, CredentialEnvelopeCodec.encode(cipher.iv, ciphertext))
                .commit()
        ) { "无法持久化加密字段" }
    }

    fun get(key: String): String? {
        val encoded = preferences.getString(key, null) ?: return null
        val envelope = CredentialEnvelopeCodec.decode(encoded)
        (listOf(keyAlias) + legacyKeyAliases).forEach { alias ->
            val keyMaterial = existingKey(alias) ?: return@forEach
            val plaintext = runCatching {
                Cipher.getInstance(TRANSFORMATION).apply {
                    init(
                        Cipher.DECRYPT_MODE,
                        keyMaterial,
                        GCMParameterSpec(GCM_TAG_BITS, envelope.iv)
                    )
                }.doFinal(envelope.ciphertext)
            }.getOrNull() ?: return@forEach
            return String(plaintext, StandardCharsets.UTF_8)
        }
        // A pre-V1 key may be authentication-bound or invalidated after an OS upgrade.
        // Treat it as unavailable so the UI can ask for a fresh login; never crash Activity
        // startup or expose a plaintext fallback.
        return null
    }

    fun contains(key: String): Boolean = get(key) != null

    fun remove(key: String) {
        check(preferences.edit().remove(key).commit()) { "无法删除加密字段" }
    }

    fun clear() {
        check(preferences.edit().clear().commit()) { "无法清理加密字段" }
    }

    private fun encryptionKey(): SecretKey {
        existingKey(keyAlias)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE_PROVIDER)
        val spec = KeyGenParameterSpec.Builder(
            keyAlias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .setUserAuthenticationRequired(false)
            .build()
        generator.init(spec)
        return generator.generateKey()
    }

    private fun existingKey(alias: String): SecretKey? {
        val keyStore = KeyStore.getInstance(KEYSTORE_PROVIDER).apply { load(null) }
        return keyStore.getKey(alias, null) as? SecretKey
    }

    private companion object {
        const val KEYSTORE_PROVIDER = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_TAG_BITS = 128
    }
}

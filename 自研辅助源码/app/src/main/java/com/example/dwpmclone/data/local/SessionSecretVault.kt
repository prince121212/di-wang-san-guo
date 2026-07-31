package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONObject

/** Fields required to rebuild a live game session after the process is recreated. */
interface SessionSecretVault {
    fun save(accountId: Long, values: Map<String, String>)
    fun load(accountId: Long): Map<String, String>
    fun delete(accountId: Long)
    fun clear()
}

/**
 * Session authentication material is deliberately separated from the account JSON.  The account
 * repository can therefore export/display metadata without ever serializing dm/userId/etc.
 */
class KeystoreSessionSecretVault(context: Context) : SessionSecretVault {
    private val store = KeystoreAesGcmStore(
        context = context,
        preferencesName = PREFERENCES_NAME,
        keyAlias = KEY_ALIAS,
        legacyKeyAliases = listOf(LEGACY_KEY_ALIAS)
    )

    override fun save(accountId: Long, values: Map<String, String>) {
        require(accountId > 0L) { "账号 ID 无效" }
        val normalized = values.filterKeys(SessionSecretPolicy::isSensitiveKey)
            .filterValues(String::isNotBlank)
        if (normalized.isEmpty()) {
            delete(accountId)
            return
        }
        val json = JSONObject().apply {
            normalized.toSortedMap().forEach { (key, value) -> put(key, value) }
        }
        store.put(key(accountId), json.toString())
    }

    override fun load(accountId: Long): Map<String, String> {
        val raw = store.get(key(accountId)) ?: return emptyMap()
        val json = runCatching { JSONObject(raw) }.getOrNull() ?: return emptyMap()
        return json.keys().asSequence()
            .filter(SessionSecretPolicy::isSensitiveKey)
            .mapNotNull { key -> json.optString(key).takeIf(String::isNotBlank)?.let { key to it } }
            .toMap()
    }

    override fun delete(accountId: Long) = store.remove(key(accountId))

    override fun clear() = store.clear()

    private fun key(accountId: Long): String = "session_$accountId"

    private companion object {
        const val PREFERENCES_NAME = "dwpm_secure_session_secrets"
        const val KEY_ALIAS = "dwpm_local_session_v2"
        const val LEGACY_KEY_ALIAS = "dwpm_local_session_v1"
    }
}

object SessionSecretPolicy {
    private val exactSensitiveKeys = setOf(
        "dm",
        "userId",
        "accountWithSuffix",
        "token",
        "sessionToken",
        "accessToken",
        "authToken",
        "cookie",
        "gameAuthSign"
    )

    fun isSensitiveKey(key: String): Boolean {
        val trimmed = key.trim()
        if (trimmed in exactSensitiveKeys) return true
        val lower = trimmed.lowercase()
        return lower.contains("password") || lower.contains("token") ||
            lower.contains("cookie") || lower.contains("secret") ||
            lower.contains("authsign")
    }

    fun publicFields(values: Map<String, String>): Map<String, String> =
        values.filterKeys { !isSensitiveKey(it) }

    fun secretFields(values: Map<String, String>): Map<String, String> =
        values.filterKeys(::isSensitiveKey)
}

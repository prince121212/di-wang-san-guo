package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.model.Channel
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.GameVersion
import org.json.JSONArray
import org.json.JSONObject

/**
 * Local account repository.
 *
 * Account/session fields are allowed to be persisted only after a real protocol login succeeds.
 * Do not write placeholders, inferred role data, or reversed/plain password stand-ins here.
 */
class LocalAccountRepository(
    context: Context,
    private val sessionSecrets: SessionSecretVault = KeystoreSessionSecretVault(context)
) {
    private val prefs = context.getSharedPreferences("dwpm_clone_accounts", Context.MODE_PRIVATE)

    init {
        migrateLegacySecrets()
    }

    fun listAccounts(): List<GameAccount> {
        val root = JSONObject(prefs.getString(KEY_ACCOUNTS, "{\"accounts\":[]}") ?: "{\"accounts\":[]}")
        val arr = root.optJSONArray("accounts") ?: JSONArray()
        return (0 until arr.length())
            .mapNotNull { index -> arr.optJSONObject(index)?.toGameAccount() }
            .map { it.withSessionSecrets() }
    }

    fun upsert(account: GameAccount) {
        saveSessionSecrets(account)
        val accounts = listAccounts().filterNot { it.id == account.id } + account
        saveAll(accounts.sortedBy { it.id })
    }

    fun get(accountId: Long): GameAccount? =
        listAccounts().firstOrNull { it.id == accountId }

    fun setEnabled(accountId: Long, enabled: Boolean, loginState: String? = null) {
        val account = get(accountId) ?: return
        upsert(account.copy(
            enabled = enabled,
            loginState = loginState ?: account.loginState
        ))
    }

    fun updateLoginState(accountId: Long, loginState: String, extra: Map<String, String> = emptyMap()) {
        val account = get(accountId) ?: return
        val session = account.session
        upsert(account.copy(
            loginState = loginState,
            session = if (session == null || extra.isEmpty()) {
                session
            } else {
                session.copy(channelExtra = session.channelExtra + extra)
            }
        ))
    }

    fun delete(accountId: Long) {
        sessionSecrets.delete(accountId)
        saveAll(listAccounts().filterNot { it.id == accountId })
    }

    fun clear() {
        sessionSecrets.clear()
        check(prefs.edit().remove(KEY_ACCOUNTS).commit()) { "无法清理账号数据" }
    }

    fun exportAll(): JSONObject = JSONObject()
        .put("schema_version", EXPORT_SCHEMA_VERSION)
        .put("accounts", JSONArray().also { arr -> listAccounts().forEach { arr.put(it.toJson()) } })

    fun importAll(json: JSONObject, clearExisting: Boolean = false): ImportResult {
        if (json.optString("schema_version") != EXPORT_SCHEMA_VERSION) {
            return ImportResult(false, 0, "unsupported account schema_version: ${json.optString("schema_version")}")
        }
        val arr = json.optJSONArray("accounts") ?: return ImportResult(false, 0, "missing accounts array")
        val imported = (0 until arr.length()).mapNotNull { arr.optJSONObject(it)?.toGameAccount() }
        val merged = if (clearExisting) imported else (listAccounts().filterNot { old -> imported.any { it.id == old.id } } + imported)
        if (clearExisting) sessionSecrets.clear()
        imported.forEach(::saveSessionSecrets)
        saveAll(merged.sortedBy { it.id })
        return ImportResult(true, imported.size, "imported ${imported.size} account entries")
    }

    private fun saveAll(accounts: List<GameAccount>) {
        check(
            prefs.edit().putString(KEY_ACCOUNTS, JSONObject()
                .put("schema_version", EXPORT_SCHEMA_VERSION)
                .put("accounts", JSONArray().also { arr -> accounts.forEach { arr.put(it.toJson()) } })
                .toString()
            ).commit()
        ) { "无法持久化账号数据" }
    }

    /** Encrypts session secrets left by pre-V1 builds before removing their plaintext copies. */
    private fun migrateLegacySecrets() {
        val raw = prefs.getString(KEY_ACCOUNTS, null) ?: return
        val root = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val array = root.optJSONArray("accounts") ?: return
        var changed = false
        for (index in 0 until array.length()) {
            val account = array.optJSONObject(index) ?: continue
            val accountId = account.optLong("id", -1L)
            if (account.has("encryptedPassword")) {
                account.remove("encryptedPassword")
                changed = true
            }
            val session = account.optJSONObject("session") ?: continue
            val token = session.optString("tokenCiphertext")
            if (token.isNotBlank() && token != SESSION_PRESENT_MARKER) {
                session.put("tokenCiphertext", SESSION_PRESENT_MARKER)
                changed = true
            }
            val extra = session.optJSONObject("channelExtra") ?: continue
            val keys = extra.keys().asSequence().toList()
            val secrets = keys
                .filter(SessionSecretPolicy::isSensitiveKey)
                .associateWith { key -> extra.optString(key) }
                .filterValues(String::isNotBlank)
            if (accountId > 0L && secrets.isNotEmpty()) {
                val migrated = runCatching {
                    sessionSecrets.save(accountId, secrets)
                }.isSuccess
                secrets.keys.forEach(extra::remove)
                if (!migrated) {
                    // An authentication-bound legacy key can be unavailable during an
                    // OEM unlock transition. Never retain plaintext or pretend the
                    // Session is recoverable; require a fresh explicit login instead.
                    session.put("tokenCiphertext", "")
                        .put("sourceMode", 0)
                    account.put("enabled", false)
                        .put("loginState", "RELOGIN_REQUIRED")
                }
                changed = true
            }
        }
        if (changed) {
            check(prefs.edit().putString(KEY_ACCOUNTS, root.toString()).commit()) {
                "无法清理历史明文 Session 字段"
            }
        }
    }

    private fun saveSessionSecrets(account: GameAccount) {
        val session = account.session ?: return
        val secrets = SessionSecretPolicy.secretFields(session.channelExtra)
        if (secrets.isNotEmpty()) sessionSecrets.save(account.id, secrets)
    }

    private fun GameAccount.withSessionSecrets(): GameAccount {
        val current = session ?: return this
        val decrypted = runCatching { sessionSecrets.load(id) }.getOrDefault(emptyMap())
        if (decrypted.isEmpty()) return this
        return copy(session = current.copy(channelExtra = current.channelExtra + decrypted))
    }

    private fun JSONObject.toGameAccount(): GameAccount? = runCatching {
        GameAccount(
            id = optLong("id", DEFAULT_ACCOUNT_ID),
            displayName = optString("displayName").ifBlank { null },
            username = optString("username"),
            serverName = optString("serverName"),
            serverId = optString("serverId").ifBlank { null },
            gameVersion = runCatching { GameVersion.valueOf(optString("gameVersion")) }.getOrDefault(GameVersion.OTHER),
            channel = runCatching { Channel.valueOf(optString("channel")) }.getOrDefault(Channel.UNKNOWN),
            session = optJSONObject("session")?.toGameSession(),
            enabled = optBoolean("enabled", true),
            monarchName = optString("monarchName").ifBlank { null },
            nation = optString("nation").ifBlank { null },
            loginState = optString("loginState", "NO_REAL_PROTOCOL_LOGIN"),
            gameAuthSignEvidence = optString("gameAuthSignEvidence").ifBlank {
                optString("gameAuthSignPlaceholder")
            }.ifBlank { null }
        )
    }.getOrNull()

    private fun GameAccount.toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("displayName", displayName)
        .put("username", username)
        .put("serverName", serverName)
        .put("serverId", serverId)
        .put("gameVersion", gameVersion.name)
        .put("channel", channel.name)
        .put("session", session?.toJson())
        .put("enabled", enabled)
        .put("monarchName", monarchName)
        .put("nation", nation)
        .put("loginState", loginState)
        .put("gameAuthSignEvidence", gameAuthSignEvidence)

    private fun JSONObject.toGameSession(): GameSession = GameSession(
        accountId = optLong("accountId"),
        tokenCiphertext = optString("tokenCiphertext"),
        expiresAtMillis = if (has("expiresAtMillis") && !isNull("expiresAtMillis")) optLong("expiresAtMillis") else null,
        channelExtra = optJSONObject("channelExtra")?.let { extra ->
            extra.keys().asSequence().associateWith { key -> extra.optString(key) }
        } ?: emptyMap(),
        sourceMode = optInt("sourceMode", 0)
    )

    private fun GameSession.toJson(): JSONObject = JSONObject()
        .put("accountId", accountId)
        .put("tokenCiphertext", if (sourceMode == 1) SESSION_PRESENT_MARKER else "")
        .put("expiresAtMillis", expiresAtMillis)
        .put("channelExtra", JSONObject().also { obj ->
            SessionSecretPolicy.publicFields(channelExtra).toSortedMap()
                .forEach { (key, value) -> obj.put(key, value) }
        })
        .put("sourceMode", sourceMode)

    companion object {
        const val EXPORT_SCHEMA_VERSION = "0.2-real-protocol-accounts"
        const val DEFAULT_ACCOUNT_ID = 1L
        const val SESSION_PRESENT_MARKER = "keystore-managed-login"
        private const val KEY_ACCOUNTS = "accounts_json"
    }
}

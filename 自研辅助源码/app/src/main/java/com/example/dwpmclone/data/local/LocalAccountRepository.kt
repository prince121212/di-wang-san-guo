package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.host.SharedPythonCoreHost
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
    private val sessionSecrets: SessionSecretVault = KeystoreSessionSecretVault(context),
    private val sharedAccounts: SharedAccountStateGateway = SharedPythonCoreHost.get(context)
) {
    private val prefs = context.getSharedPreferences("dwpm_clone_accounts", Context.MODE_PRIVATE)

    init {
        migrateLegacySecrets()
        migrateLegacyAccountsToSharedCore()
    }

    fun listAccounts(): List<GameAccount> {
        return accountArray(sharedAccounts.accountRecordsSnapshot())
            .map { it.withSessionSecrets() }
    }

    /** UI/local reads must not decrypt Keystore Session fields. */
    fun listPublicAccounts(): List<GameAccount> {
        return accountArray(sharedAccounts.accountRecordsPresentationSnapshot())
    }

    fun upsert(account: GameAccount) {
        saveSessionSecrets(account)
        val result = sharedAccounts.accountRecordUpsert(account.toSharedJson())
        check(result.optBoolean("ok", false)) {
            result.optJSONObject("error")?.optString("message")
                ?: "无法写入共享账号状态"
        }
    }

    fun get(accountId: Long): GameAccount? = accountFromResult(
        sharedAccounts.accountRecord(accountId.toString())
    )?.withSessionSecrets()

    fun getPublic(accountId: Long): GameAccount? = accountFromResult(
        sharedAccounts.accountRecordPresentation(accountId.toString())
    )

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
        val result = sharedAccounts.accountRecordDelete(accountId.toString())
        check(result.optBoolean("ok", false)) {
            result.optJSONObject("error")?.optString("message")
                ?: "无法删除共享账号状态"
        }
    }

    fun deleteSessionSecrets(accountId: Long) {
        sessionSecrets.delete(accountId)
    }

    fun clear() {
        sessionSecrets.clear()
        val result = sharedAccounts.accountRecordsClear()
        check(result.optBoolean("ok", false)) {
            result.optJSONObject("error")?.optString("message")
                ?: "无法清理共享账号状态"
        }
    }

    fun exportAll(): JSONObject = JSONObject()
        .put("schema_version", EXPORT_SCHEMA_VERSION)
        .put("accounts", JSONArray().also { arr -> listPublicAccounts().forEach { arr.put(it.toJson()) } })

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
        val records = JSONArray().also { output ->
            accounts.sortedBy { it.id }.forEach { output.put(it.toSharedJson()) }
        }
        val result = sharedAccounts.accountRecordsReplace(records)
        check(result.optBoolean("ok", false)) {
            result.optJSONObject("error")?.optString("message")
                ?: "无法替换共享账号状态"
        }
    }

    private fun accountArray(snapshot: JSONObject): List<GameAccount> {
        check(snapshot.optBoolean("ok", false)) {
            snapshot.optJSONObject("error")?.optString("message")
                ?: "无法读取共享账号状态"
        }
        val records = snapshot.optJSONArray("accounts") ?: JSONArray()
        return (0 until records.length())
            .mapNotNull { index -> records.optJSONObject(index)?.toGameAccount() }
    }

    private fun accountFromResult(result: JSONObject): GameAccount? {
        check(result.optBoolean("ok", false)) {
            result.optJSONObject("error")?.optString("message")
                ?: "无法读取共享账号状态"
        }
        return result.optJSONObject("account")?.toGameAccount()
    }

    private fun migrateLegacyAccountsToSharedCore() {
        if (prefs.getBoolean(KEY_SHARED_MIGRATION_DONE, false)) return
        val raw = prefs.getString(KEY_ACCOUNTS, null) ?: return
        val root = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val oldAccounts = root.optJSONArray("accounts") ?: return
        val publicRecords = JSONArray().also { output ->
            (0 until oldAccounts.length())
                .mapNotNull { index -> oldAccounts.optJSONObject(index)?.toGameAccount() }
                .forEach { output.put(it.toSharedJson()) }
        }
        val result = sharedAccounts.accountRecordsImportIfEmpty(publicRecords)
        check(result.optBoolean("ok", false)) {
            result.optJSONObject("error")?.optString("message")
                ?: "旧账号迁移到共享核心失败"
        }
        check(prefs.edit().putBoolean(KEY_SHARED_MIGRATION_DONE, true).commit()) {
            "无法记录共享账号迁移状态"
        }
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
        val parsedChannel = runCatching {
            Channel.valueOf(optString("channel"))
        }.getOrDefault(Channel.UNKNOWN)
        val rawPlatform = optString("platform").trim()
        val platformKey = optString("platformKey").trim().ifBlank {
            if (
                parsedChannel == Channel.DANGLE ||
                rawPlatform.contains("当乐", ignoreCase = true) ||
                rawPlatform.equals("downjoy", ignoreCase = true)
            ) "downjoy" else "sglm"
        }
        GameAccount(
            id = optLong("id", DEFAULT_ACCOUNT_ID),
            displayName = optString("displayName").ifBlank { null },
            username = optString("username"),
            serverName = optString("serverName"),
            serverId = optString("serverId").ifBlank { null },
            gameVersion = runCatching { GameVersion.valueOf(optString("gameVersion")) }.getOrDefault(GameVersion.OTHER),
            channel = parsedChannel,
            session = optJSONObject("session")?.toGameSession(),
            enabled = optBoolean("enabled", true),
            monarchName = optString("monarchName").ifBlank { null },
            nation = optString("nation").ifBlank { null },
            loginState = optString("loginState", "NO_REAL_PROTOCOL_LOGIN"),
            gameAuthSignEvidence = optString("gameAuthSignEvidence").ifBlank {
                optString("gameAuthSignPlaceholder")
            }.ifBlank { null },
            platform = rawPlatform.ifBlank {
                if (platformKey == "downjoy") "当乐帝王三国" else "热血三国联盟"
            },
            platformKey = platformKey,
            serial = optString("serial", "0").trim().ifBlank { "0" },
            serverQuery = optString("serverQuery").trim().ifBlank {
                optString("serverName")
            }
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
        .put("platform", platform)
        .put("platformKey", platformKey)
        .put("serial", serial)
        .put("serverQuery", serverQuery)

    private fun JSONObject.toGameSession(): GameSession = GameSession(
        accountId = optLong("accountId"),
        tokenCiphertext = if (optInt("sourceMode", 0) == 1) SESSION_PRESENT_MARKER else "",
        expiresAtMillis = if (has("expiresAtMillis") && !isNull("expiresAtMillis")) optLong("expiresAtMillis") else null,
        channelExtra = (optJSONObject("publicState") ?: optJSONObject("channelExtra"))?.let { extra ->
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

    private fun GameAccount.toSharedJson(): JSONObject = JSONObject()
        .put("accountRef", id.toString())
        .put("id", id)
        .put("displayName", displayName)
        .put("username", username)
        .put("serverName", serverName)
        .put("serverId", serverId)
        .put("gameVersion", gameVersion.name)
        .put("channel", channel.name)
        .put("session", session?.toSharedJson())
        .put("enabled", enabled)
        .put("monarchName", monarchName)
        .put("nation", nation)
        .put("loginState", loginState)
        .put("gameAuthSignEvidence", gameAuthSignEvidence)
        .put("platform", platform)
        .put("platformKey", platformKey)
        .put("serial", serial)
        .put("serverQuery", serverQuery)

    private fun GameSession.toSharedJson(): JSONObject = JSONObject()
        .put("accountId", accountId)
        .put("expiresAtMillis", expiresAtMillis)
        .put("publicState", JSONObject().also { obj ->
            SessionSecretPolicy.publicFields(channelExtra).toSortedMap()
                .forEach { (key, value) -> obj.put(key, value) }
        })
        .put("sourceMode", sourceMode)

    companion object {
        const val EXPORT_SCHEMA_VERSION = "0.2-real-protocol-accounts"
        const val DEFAULT_ACCOUNT_ID = 1L
        const val SESSION_PRESENT_MARKER = "keystore-managed-login"
        private const val KEY_ACCOUNTS = "accounts_json"
        private const val KEY_SHARED_MIGRATION_DONE = "shared_python_accounts_v1_migrated"
    }
}

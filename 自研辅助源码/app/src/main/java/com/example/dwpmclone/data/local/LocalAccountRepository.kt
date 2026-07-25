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
class LocalAccountRepository(context: Context) {
    private val prefs = context.getSharedPreferences("dwpm_clone_accounts", Context.MODE_PRIVATE)

    fun listAccounts(): List<GameAccount> {
        val root = JSONObject(prefs.getString(KEY_ACCOUNTS, "{\"accounts\":[]}") ?: "{\"accounts\":[]}")
        val arr = root.optJSONArray("accounts") ?: JSONArray()
        return (0 until arr.length()).mapNotNull { index -> arr.optJSONObject(index)?.toGameAccount() }
    }

    fun upsert(account: GameAccount) {
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
        saveAll(listAccounts().filterNot { it.id == accountId })
    }

    fun clear() {
        prefs.edit().remove(KEY_ACCOUNTS).apply()
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
        saveAll(merged.sortedBy { it.id })
        return ImportResult(true, imported.size, "imported ${imported.size} account entries")
    }

    @Deprecated("Account-processing UI must not create placeholder accounts; persist only RealGameProtocolClient success results.")
    fun upsertFromAccountProcessingValues(@Suppress("UNUSED_PARAMETER") values: JSONObject, @Suppress("UNUSED_PARAMETER") accountId: Long = DEFAULT_ACCOUNT_ID): GameAccount {
        throw UnsupportedOperationException("真实协议登录成功前禁止保存账号占位数据")
    }

    private fun saveAll(accounts: List<GameAccount>) {
        prefs.edit().putString(KEY_ACCOUNTS, JSONObject()
            .put("schema_version", EXPORT_SCHEMA_VERSION)
            .put("accounts", JSONArray().also { arr -> accounts.forEach { arr.put(it.toJson()) } })
            .toString()
        ).apply()
    }

    private fun JSONObject.toGameAccount(): GameAccount? = runCatching {
        GameAccount(
            id = optLong("id", DEFAULT_ACCOUNT_ID),
            displayName = optString("displayName").ifBlank { null },
            username = optString("username"),
            encryptedPassword = optString("encryptedPassword").ifBlank { null },
            serverName = optString("serverName"),
            serverId = optString("serverId").ifBlank { null },
            gameVersion = runCatching { GameVersion.valueOf(optString("gameVersion")) }.getOrDefault(GameVersion.OTHER),
            channel = runCatching { Channel.valueOf(optString("channel")) }.getOrDefault(Channel.UNKNOWN),
            session = optJSONObject("session")?.toGameSession(),
            enabled = optBoolean("enabled", true),
            monarchName = optString("monarchName").ifBlank { null },
            nation = optString("nation").ifBlank { null },
            loginState = optString("loginState", "NO_REAL_PROTOCOL_LOGIN"),
            gameAuthSignPlaceholder = optString("gameAuthSignPlaceholder").ifBlank { null },
            antiBanIpEnabled = optBoolean("antiBanIpEnabled", false)
        )
    }.getOrNull()

    private fun GameAccount.toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("displayName", displayName)
        .put("username", username)
        .put("encryptedPassword", encryptedPassword)
        .put("serverName", serverName)
        .put("serverId", serverId)
        .put("gameVersion", gameVersion.name)
        .put("channel", channel.name)
        .put("session", session?.toJson())
        .put("enabled", enabled)
        .put("monarchName", monarchName)
        .put("nation", nation)
        .put("loginState", loginState)
        .put("gameAuthSignPlaceholder", gameAuthSignPlaceholder)
        .put("antiBanIpEnabled", antiBanIpEnabled)

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
        .put("tokenCiphertext", tokenCiphertext)
        .put("expiresAtMillis", expiresAtMillis)
        .put("channelExtra", JSONObject().also { obj ->
            channelExtra.toSortedMap().forEach { (key, value) -> obj.put(key, value) }
        })
        .put("sourceMode", sourceMode)

    private fun parseVersion(text: String): GameVersion = when {
        text.contains("腾讯") || text.contains("QQ", ignoreCase = true) -> GameVersion.TENCENT_CLASSIC
        text.contains("官方") -> GameVersion.OFFICIAL_CLASSIC
        text.contains("繁") || text.contains("傳") -> GameVersion.TRADITIONAL
        else -> GameVersion.OTHER
    }

    private fun parseChannel(text: String): Channel = when {
        text.contains("微信") -> Channel.WECHAT
        text.contains("QQ", ignoreCase = true) || text.contains("腾讯") -> Channel.QQ
        text.contains("360") -> Channel.QIHOO_360
        text.contains("UC", ignoreCase = true) || text.contains("九游") -> Channel.UC_9GAME
        text.contains("当乐") -> Channel.DANGLE
        text.contains("官方") -> Channel.OFFICIAL
        else -> Channel.UNKNOWN
    }

    companion object {
        const val EXPORT_SCHEMA_VERSION = "0.2-real-protocol-accounts"
        const val DEFAULT_ACCOUNT_ID = 1L
        private const val KEY_ACCOUNTS = "accounts_json"
    }
}

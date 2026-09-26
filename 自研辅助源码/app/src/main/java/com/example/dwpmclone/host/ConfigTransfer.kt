package com.example.dwpmclone.host

import java.security.GeneralSecurityException
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/**
 * One game account in a manual "换手机" export: identity, public routing fields and settings.
 *
 * Import matches accounts by platform + game account + server (the same rule as manual add),
 * never by password, so settings still attach after the game password changes.
 */
data class ConfigBackupAccount(
    val platformKey: String,
    val platform: String,
    val username: String,
    val serverName: String,
    val serverQuery: String,
    val serverId: String?,
    val serial: String,
    val displayName: String?,
    val configs: Map<String, JSONObject>,
) {
    val label: String get() = "$username@$serverQuery"
}

data class ConfigBackup(
    val exportedAt: Long,
    val deviceName: String,
    val appVersion: String,
    val accounts: List<ConfigBackupAccount>,
    val secrets: JSONObject,
)

/**
 * Export document codec. Accounts and settings stay readable JSON (the server encrypts the
 * stored document at rest); game passwords are sealed here with a key derived from the member
 * password and bound to the member id, so the cloud can never read them.
 */
class ConfigBackupCodec(
    private val iterations: Int = DEFAULT_ITERATIONS,
    private val random: SecureRandom = SecureRandom(),
) {
    fun encode(
        accounts: List<ConfigBackupAccount>,
        passwords: List<String?>,
        memberId: String,
        memberPassword: String,
        deviceName: String,
        appVersion: String,
        exportedAt: Long,
    ): String {
        require(accounts.isNotEmpty()) { "本机还没有游戏账号，无需导出" }
        require(passwords.size == accounts.size) { "游戏密码与账号数量不一致" }
        require(memberPassword.isNotEmpty() && memberId.isNotBlank()) { "请先登录会员并输入会员密码" }
        val salt = ByteArray(16).also(random::nextBytes)
        val iv = ByteArray(12).also(random::nextBytes)
        val plain = JSONArray().apply { passwords.forEach { put(it ?: JSONObject.NULL) } }
            .toString().toByteArray(Charsets.UTF_8)
        val sealed = try {
            Cipher.getInstance(CIPHER).run {
                init(Cipher.ENCRYPT_MODE, SecretKeySpec(pbkdf2Sha256(memberPassword, salt, iterations), "AES"),
                    GCMParameterSpec(TAG_BITS, iv))
                updateAAD(aad(memberId))
                doFinal(plain)
            }
        } finally {
            plain.fill(0)
        }
        return JSONObject()
            .put("format", FORMAT)
            .put("version", VERSION)
            .put("exportedAt", exportedAt)
            .put("deviceName", deviceName)
            .put("appVersion", appVersion)
            .put("accounts", JSONArray().apply { accounts.forEach { put(it.toJson()) } })
            .put("secrets", JSONObject()
                .put("algorithm", ALGORITHM)
                .put("iterations", iterations)
                .put("salt", hex(salt))
                .put("iv", hex(iv))
                .put("ciphertext", hex(sealed)))
            .toString()
    }

    fun decode(raw: String): ConfigBackup {
        val root = try { JSONObject(raw) } catch (_: JSONException) {
            throw IllegalArgumentException("云端配置格式无效")
        }
        require(root.optString("format") == FORMAT) { "云端配置格式无效" }
        require(root.optInt("version") == VERSION) { "云端配置来自不同版本，请先把两台手机的 App 升级到最新版" }
        val list = root.optJSONArray("accounts") ?: throw IllegalArgumentException("云端配置缺少游戏账号")
        val accounts = (0 until list.length()).map { index ->
            try { accountFromJson(list.getJSONObject(index)) } catch (_: JSONException) {
                throw IllegalArgumentException("云端配置里的第 ${index + 1} 个账号格式无效")
            }
        }
        require(accounts.isNotEmpty()) { "云端配置没有游戏账号" }
        return ConfigBackup(
            exportedAt = root.optLong("exportedAt"),
            deviceName = root.optString("deviceName"),
            appVersion = root.optString("appVersion"),
            accounts = accounts,
            secrets = root.optJSONObject("secrets") ?: JSONObject(),
        )
    }

    /** Null when the document was sealed for another member or with another member password. */
    fun openPasswords(backup: ConfigBackup, memberId: String, memberPassword: String): List<String?>? {
        val secrets = backup.secrets
        val rounds = secrets.optInt("iterations")
        if (secrets.optString("algorithm") != ALGORITHM || rounds !in MIN_ITERATIONS..MAX_ITERATIONS ||
            memberPassword.isEmpty()) return null
        return try {
            val plain = Cipher.getInstance(CIPHER).run {
                init(Cipher.DECRYPT_MODE,
                    SecretKeySpec(pbkdf2Sha256(memberPassword, unhex(secrets.getString("salt")), rounds), "AES"),
                    GCMParameterSpec(TAG_BITS, unhex(secrets.getString("iv"))))
                updateAAD(aad(memberId))
                doFinal(unhex(secrets.getString("ciphertext")))
            }
            val values = try { JSONArray(String(plain, Charsets.UTF_8)) } finally { plain.fill(0) }
            if (values.length() != backup.accounts.size) return null
            (0 until values.length()).map { index ->
                if (values.isNull(index)) null else values.getString(index).takeIf(String::isNotEmpty)
            }
        } catch (_: GeneralSecurityException) {
            null
        } catch (_: JSONException) {
            null
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    private fun ConfigBackupAccount.toJson(): JSONObject = JSONObject()
        .put("identity", JSONObject()
            .put("platformKey", platformKey)
            .put("username", username)
            .put("serverQuery", serverQuery)
            .put("serial", serial))
        .put("account", JSONObject()
            .put("platform", platform)
            .put("serverName", serverName)
            .put("serverId", serverId ?: JSONObject.NULL)
            .put("displayName", displayName ?: JSONObject.NULL))
        .put("configs", JSONObject().apply { configs.forEach { (feature, config) -> put(feature, config) } })

    private fun accountFromJson(value: JSONObject): ConfigBackupAccount {
        val identity = value.getJSONObject("identity")
        val account = value.optJSONObject("account") ?: JSONObject()
        val configs = value.optJSONObject("configs") ?: JSONObject()
        val serverQuery = identity.getString("serverQuery")
        return ConfigBackupAccount(
            platformKey = identity.getString("platformKey"),
            platform = account.optString("platform"),
            username = identity.getString("username"),
            serverName = account.optString("serverName").ifBlank { serverQuery },
            serverQuery = serverQuery,
            serverId = account.optString("serverId").takeUnless { it.isBlank() || it == "null" },
            serial = identity.optString("serial", "0").ifBlank { "0" },
            displayName = account.optString("displayName").takeUnless { it.isBlank() || it == "null" },
            configs = configs.keys().asSequence().associateWith { configs.getJSONObject(it) },
        )
    }

    companion object {
        const val FORMAT = "dwpm-config-backup"
        const val VERSION = 1
        const val DEFAULT_ITERATIONS = 600_000
        private const val MIN_ITERATIONS = 1_000
        private const val MAX_ITERATIONS = 2_000_000
        private const val ALGORITHM = "PBKDF2-HMAC-SHA256/AES-256-GCM"
        private const val CIPHER = "AES/GCM/NoPadding"
        private const val TAG_BITS = 128

        private fun aad(memberId: String): ByteArray =
            "dwpm-config-backup-v1\u0000$memberId".toByteArray(Charsets.UTF_8)

        /**
         * PBKDF2-HMAC-SHA256 (RFC 8018) for one 32-byte block. The platform
         * PBKDF2WithHmacSHA256 provider needs API 26, but minSdk is 24.
         */
        internal fun pbkdf2Sha256(password: String, salt: ByteArray, rounds: Int): ByteArray {
            val mac = Mac.getInstance("HmacSHA256")
            val secret = password.toByteArray(Charsets.UTF_8)
            try {
                mac.init(SecretKeySpec(secret, "HmacSHA256"))
            } finally {
                secret.fill(0)
            }
            mac.update(salt)
            mac.update(byteArrayOf(0, 0, 0, 1))
            var block = mac.doFinal()
            val output = block.copyOf()
            repeat(rounds - 1) {
                block = mac.doFinal(block)
                for (index in output.indices) output[index] = (output[index].toInt() xor block[index].toInt()).toByte()
            }
            return output
        }

        private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }

        private fun unhex(value: String): ByteArray {
            require(value.length % 2 == 0 && value.all { it in '0'..'9' || it in 'a'..'f' }) { "invalid hex" }
            return ByteArray(value.length / 2) { value.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        }
    }
}

/** Where an import lands: the host's account ledger, credential vault and settings store. */
interface ConfigImportTarget {
    /** Canonical local account for this identity (same rule as manual add), or null when unsupported. */
    fun resolve(account: ConfigBackupAccount): ResolvedImportAccount?
    fun hasPassword(accountId: Long): Boolean
    fun savePassword(accountId: Long, password: String)
    /** Create the stopped account, storing its password first when one was restored. */
    fun create(resolved: ResolvedImportAccount, account: ConfigBackupAccount, password: String?)
    fun saveConfig(accountId: Long, featureId: String, config: JSONObject)
}

data class ResolvedImportAccount(val accountId: Long, val exists: Boolean, val draft: JSONObject)

data class ConfigImportSummary(
    val added: List<String>,
    val merged: List<String>,
    val skipped: List<String>,
    val passwordsRestored: Int,
    val passwordsMissing: List<String>,
    val configsRestored: Int,
)

object ConfigBackupImporter {
    /**
     * Apply an export. An account already on this phone keeps its local password (it was entered
     * here and may be newer); an exported password only fills a missing one. Exported settings
     * replace the same feature's local settings; other local features stay untouched.
     */
    fun apply(backup: ConfigBackup, passwords: List<String?>?, target: ConfigImportTarget): ConfigImportSummary {
        val added = mutableListOf<String>()
        val merged = mutableListOf<String>()
        val skipped = mutableListOf<String>()
        val missing = mutableListOf<String>()
        var restored = 0
        var configCount = 0
        backup.accounts.forEachIndexed { index, account ->
            val resolved = target.resolve(account)
            if (resolved == null) {
                skipped += account.label
                return@forEachIndexed
            }
            val password = passwords?.getOrNull(index)
            if (resolved.exists) {
                merged += account.label
                if (!target.hasPassword(resolved.accountId)) {
                    if (password != null) {
                        target.savePassword(resolved.accountId, password)
                        restored++
                    } else {
                        missing += account.label
                    }
                }
            } else {
                target.create(resolved, account, password)
                added += account.label
                if (password != null) restored++ else missing += account.label
            }
            account.configs.forEach { (featureId, config) ->
                target.saveConfig(resolved.accountId, featureId, config)
                configCount++
            }
        }
        return ConfigImportSummary(added, merged, skipped, restored, missing, configCount)
    }
}

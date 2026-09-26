package com.example.dwpmclone.host

import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ConfigTransferTest {
    private val codec = ConfigBackupCodec(iterations = 1_000)

    private fun account(username: String, server: String = "周年服351区(新服)", platformKey: String = "sglm") =
        ConfigBackupAccount(
            platformKey = platformKey,
            platform = "热血三国联盟",
            username = username,
            serverName = server,
            serverQuery = server,
            serverId = "351",
            serial = "0",
            displayName = "$username@$server",
            configs = mapOf(
                "brush" to JSONObject().put("values", JSONObject().put("enabled", true).put("level", 7)),
                "mine" to JSONObject().put("values", JSONObject().put("rows", 2)),
            ),
        )

    private fun export(vararg accounts: Pair<ConfigBackupAccount, String?>, password: String = "member-password-1") =
        codec.decode(codec.encode(accounts.map { it.first }, accounts.map { it.second }, "member-a", password,
            "Xiaomi 22081212C", "V0.0.119", 1_790_000_000_000L))

    @Test
    fun pbkdf2MatchesTheJdkImplementationIncludingNonAsciiPasswords() {
        val salt = ByteArray(16) { it.toByte() }
        for (password in listOf("member-password-1", "会员密码-測試-🔑")) {
            val expected = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                .generateSecret(PBEKeySpec(password.toCharArray(), salt, 1_000, 256)).encoded
            assertArrayEquals(expected, ConfigBackupCodec.pbkdf2Sha256(password, salt, 1_000))
        }
    }

    @Test
    fun exportRoundTripsAccountsSettingsAndSealedPasswords() {
        val backup = export(account("1608601") to "game-pass-1", account("1608602", "周年服352区") to null)
        assertEquals(listOf("1608601@周年服351区(新服)", "1608602@周年服352区"), backup.accounts.map { it.label })
        assertEquals("Xiaomi 22081212C", backup.deviceName)
        assertEquals(7, backup.accounts[0].configs.getValue("brush").getJSONObject("values").getInt("level"))
        assertEquals("351", backup.accounts[1].serverId)
        assertEquals(listOf("game-pass-1", null), codec.openPasswords(backup, "member-a", "member-password-1"))
    }

    @Test
    fun gamePasswordsNeverAppearInTheDocument() {
        val raw = codec.encode(listOf(account("1608601")), listOf("game-pass-1"), "member-a", "member-password-1",
            "phone", "V0.0.119", 1L)
        assertTrue(!raw.contains("game-pass-1") && !raw.contains("member-password-1"))
    }

    @Test
    fun wrongMemberPasswordOtherMemberOrTamperingCannotOpenPasswords() {
        val backup = export(account("1608601") to "game-pass-1")
        assertNull(codec.openPasswords(backup, "member-a", "another-password"))
        assertNull(codec.openPasswords(backup, "member-b", "member-password-1"))
        val secrets = JSONObject(backup.secrets.toString())
        val sealed = secrets.getString("ciphertext")
        secrets.put("ciphertext", (if (sealed[0] == '0') "1" else "0") + sealed.substring(1))
        assertNull(codec.openPasswords(backup.copy(secrets = secrets), "member-a", "member-password-1"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun decodeRejectsForeignDocuments() {
        codec.decode(JSONObject().put("format", "something-else").put("version", 1).toString())
    }

    @Test(expected = IllegalArgumentException::class)
    fun decodeRejectsFutureVersions() {
        val raw = JSONObject(codec.encode(listOf(account("1608601")), listOf(null), "member-a", "member-password-1",
            "phone", "V0.0.119", 1L)).put("version", 2)
        codec.decode(raw.toString())
    }

    private class FakeTarget(existing: Map<String, Pair<Long, String?>>) : ConfigImportTarget {
        val accounts = existing.mapValues { it.value.first }.toMutableMap()
        val passwords = existing.values.mapNotNull { (id, password) -> password?.let { id to it } }.toMap().toMutableMap()
        val configs = mutableMapOf<Pair<Long, String>, JSONObject>()
        val created = mutableListOf<Long>()
        override fun resolve(account: ConfigBackupAccount): ResolvedImportAccount? {
            if (account.platformKey !in setOf("sglm", "downjoy")) return null
            val key = "${account.platformKey}|${account.username}|${account.serverQuery}"
            val id = accounts[key] ?: (1_000L + key.hashCode().toLong().and(0xffff))
            return ResolvedImportAccount(id, accounts.containsKey(key), JSONObject().put("key", key))
        }
        override fun hasPassword(accountId: Long) = passwords.containsKey(accountId)
        override fun savePassword(accountId: Long, password: String) { passwords[accountId] = password }
        override fun create(resolved: ResolvedImportAccount, account: ConfigBackupAccount, password: String?) {
            password?.let { passwords[resolved.accountId] = it }
            accounts[resolved.draft.getString("key")] = resolved.accountId
            created += resolved.accountId
        }
        override fun saveConfig(accountId: Long, featureId: String, config: JSONObject) {
            configs[accountId to featureId] = config
        }
    }

    @Test
    fun importMatchesByIdentityAndNeverOverwritesALocalPassword() {
        val backup = export(
            account("new-user") to "new-pass",
            account("kept-user") to "old-exported-pass",
            account("filled-user") to "filled-pass",
            account("other-platform", platformKey = "unknown") to "x-pass",
        )
        val target = FakeTarget(mapOf(
            "sglm|kept-user|周年服351区(新服)" to (11L to "changed-on-new-phone"),
            "sglm|filled-user|周年服351区(新服)" to (12L to null),
        ))
        val summary = ConfigBackupImporter.apply(backup, codec.openPasswords(backup, "member-a", "member-password-1"), target)

        assertEquals(listOf("new-user@周年服351区(新服)"), summary.added)
        assertEquals(listOf("kept-user@周年服351区(新服)", "filled-user@周年服351区(新服)"), summary.merged)
        assertEquals(listOf("other-platform@周年服351区(新服)"), summary.skipped)
        assertEquals("changed-on-new-phone", target.passwords[11L])
        assertEquals("filled-pass", target.passwords[12L])
        assertEquals("new-pass", target.passwords[target.created.single()])
        assertEquals(2, summary.passwordsRestored)
        assertEquals(emptyList<String>(), summary.passwordsMissing)
        assertEquals(6, summary.configsRestored)
        assertEquals(7, target.configs.getValue(11L to "brush").getJSONObject("values").getInt("level"))
    }

    @Test
    fun importWithoutReadablePasswordsStillRestoresAccountsAndSettings() {
        val backup = export(account("new-user") to "new-pass", account("filled-user") to "filled-pass")
        val target = FakeTarget(mapOf("sglm|filled-user|周年服351区(新服)" to (12L to null)))
        val summary = ConfigBackupImporter.apply(backup, codec.openPasswords(backup, "member-a", "reset-password"), target)

        assertEquals(1, summary.added.size)
        assertEquals(0, summary.passwordsRestored)
        assertEquals(listOf("new-user@周年服351区(新服)", "filled-user@周年服351区(新服)"), summary.passwordsMissing)
        assertTrue(target.passwords.isEmpty())
        assertEquals(4, summary.configsRestored)
    }

    @Test
    fun sameGameAccountOnAnotherServerIsADifferentAccount() {
        val backup = export(account("1608601") to "p1", account("1608601", "周年服352区") to "p2")
        val target = FakeTarget(emptyMap())
        val summary = ConfigBackupImporter.apply(backup, codec.openPasswords(backup, "member-a", "member-password-1"), target)
        assertEquals(2, summary.added.size)
        assertEquals(setOf("p1", "p2"), target.passwords.values.toSet())
    }
}

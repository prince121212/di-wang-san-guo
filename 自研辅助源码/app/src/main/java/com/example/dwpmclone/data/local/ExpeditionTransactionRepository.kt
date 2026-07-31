package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.protocol.ExpeditionTransactionRecord
import com.example.dwpmclone.domain.protocol.ExpeditionTransactionState
import com.example.dwpmclone.domain.protocol.ExpeditionTransactionStore
import org.json.JSONArray
import org.json.JSONObject

/** SharedPreferences-backed action ledger; writes use commit because they precede network sends. */
class ExpeditionTransactionRepository(context: Context) : ExpeditionTransactionStore {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    @Synchronized
    override fun list(accountId: Long): List<ExpeditionTransactionRecord> =
        loadAll().filter { it.accountId == accountId }

    @Synchronized
    override fun save(record: ExpeditionTransactionRecord) {
        val records = loadAll().filterNot { it.id == record.id } + record
        check(saveAll(records)) { "无法持久化出征事务，已禁止发送" }
    }

    @Synchronized
    override fun delete(recordId: String) {
        check(saveAll(loadAll().filterNot { it.id == recordId })) { "无法清理出征事务" }
    }

    @Synchronized
    override fun deleteAccount(accountId: Long) {
        check(saveAll(loadAll().filterNot { it.accountId == accountId })) { "无法清理账号出征事务" }
    }

    private fun loadAll(): List<ExpeditionTransactionRecord> {
        val raw = preferences.getString(KEY_RECORDS, null) ?: return emptyList()
        val array = runCatching { JSONArray(raw) }.getOrNull() ?: return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                val json = array.optJSONObject(index) ?: continue
                val record = runCatching {
                    ExpeditionTransactionRecord(
                        id = json.getString("id"),
                        accountId = json.getLong("accountId"),
                        action = json.getString("action"),
                        targetKey = json.optString("targetKey"),
                        generalIds = json.optJSONArray("generalIds").toLongList(),
                        state = ExpeditionTransactionState.valueOf(json.getString("state")),
                        createdAtMillis = json.getLong("createdAtMillis"),
                        updatedAtMillis = json.getLong("updatedAtMillis"),
                        reason = json.optString("reason")
                    )
                }.getOrNull() ?: continue
                if (record.id.isNotBlank() && record.accountId > 0L && record.generalIds.isNotEmpty()) add(record)
            }
        }
    }

    private fun saveAll(records: List<ExpeditionTransactionRecord>): Boolean {
        val array = JSONArray().apply {
            records.sortedWith(compareBy(ExpeditionTransactionRecord::accountId, ExpeditionTransactionRecord::createdAtMillis))
                .forEach { record ->
                    put(JSONObject()
                        .put("id", record.id)
                        .put("accountId", record.accountId)
                        .put("action", record.action)
                        .put("targetKey", record.targetKey)
                        .put("generalIds", JSONArray(record.generalIds))
                        .put("state", record.state.name)
                        .put("createdAtMillis", record.createdAtMillis)
                        .put("updatedAtMillis", record.updatedAtMillis)
                        .put("reason", record.reason))
                }
        }
        return preferences.edit().putString(KEY_RECORDS, array.toString()).commit()
    }

    private fun JSONArray?.toLongList(): List<Long> {
        val array = this ?: return emptyList()
        return buildList {
            for (index in 0 until array.length()) array.optLong(index).takeIf { it > 0L }?.let(::add)
        }.distinct()
    }

    private companion object {
        const val PREFERENCES_NAME = "dwpm_expedition_transactions"
        const val KEY_RECORDS = "records"
    }
}

package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONObject

/** Account-scoped JSON configuration store shared by the page mapper and scheduler. */
class LocalConfigRepository(context: Context) {
    private val prefs = context.getSharedPreferences("dwpm_clone_configs", Context.MODE_PRIVATE)

    fun saveFeatureConfig(accountId: Long, featureId: String, json: JSONObject) {
        check(prefs.edit().putString(key(accountId, featureId), json.toString()).commit()) {
            "无法持久化任务配置"
        }
    }

    fun loadFeatureConfig(accountId: Long, featureId: String): JSONObject? =
        prefs.getString(key(accountId, featureId), null)?.let { JSONObject(it) }

    fun deleteFeatureConfig(accountId: Long, featureId: String) {
        check(prefs.edit().remove(key(accountId, featureId)).commit()) { "无法删除任务配置" }
    }

    fun deleteAccountConfigs(accountId: Long) {
        val prefix = "$accountId::"
        val editor = prefs.edit()
        prefs.all.keys.filter { it.startsWith(prefix) }.forEach { editor.remove(it) }
        check(editor.commit()) { "无法删除账号任务配置" }
    }

    fun exportAll(): JSONObject {
        val configs = JSONObject()
        prefs.all.toSortedMap().forEach { (key, value) ->
            if (value is String) configs.put(key, JSONObject(value))
        }
        return JSONObject()
            .put("schema_version", EXPORT_SCHEMA_VERSION)
            .put("format", "dwpm_local_configs")
            .put("configs", configs)
    }

    fun importAll(exportJson: JSONObject, clearExisting: Boolean = false): ImportResult {
        val version = exportJson.optString("schema_version")
        if (version !in SUPPORTED_IMPORT_VERSIONS) {
            return ImportResult(false, 0, "unsupported schema_version: $version")
        }
        val configs = exportJson.optJSONObject("configs")
            ?: return ImportResult(false, 0, "missing configs object")
        val editor = prefs.edit()
        if (clearExisting) editor.clear()
        var count = 0
        configs.keys().forEach { key ->
            editor.putString(key, configs.getJSONObject(key).toString())
            count += 1
        }
        if (!editor.commit()) return ImportResult(false, 0, "failed to persist imported configs")
        return ImportResult(true, count, "imported $count config entries")
    }

    private fun key(accountId: Long, featureId: String): String = "$accountId::$featureId"

    companion object {
        const val EXPORT_SCHEMA_VERSION = "1.0-local"
        private val SUPPORTED_IMPORT_VERSIONS = setOf(EXPORT_SCHEMA_VERSION, "0.1-static-mock")
    }
}

data class ImportResult(
    val success: Boolean,
    val importedCount: Int,
    val message: String
)

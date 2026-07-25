package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONObject

/**
 * Raw JSON config persistence for the rebuild skeleton.
 *
 * The original APK supports 导入/导出挂机设置, but the exact proprietary file format is
 * hidden in the packed DEX. This repository provides a safe replacement format that can
 * persist screen/feature config JSON blobs until real schemas are recovered.
 */
class LocalConfigRepository(context: Context) {
    private val prefs = context.getSharedPreferences("dwpm_clone_configs", Context.MODE_PRIVATE)

    fun saveFeatureConfig(accountId: Long, featureId: String, json: JSONObject) {
        prefs.edit().putString(key(accountId, featureId), json.toString()).apply()
    }

    fun loadFeatureConfig(accountId: Long, featureId: String): JSONObject? =
        prefs.getString(key(accountId, featureId), null)?.let { JSONObject(it) }

    fun deleteFeatureConfig(accountId: Long, featureId: String) {
        prefs.edit().remove(key(accountId, featureId)).apply()
    }

    fun deleteAccountConfigs(accountId: Long) {
        val prefix = "$accountId::"
        val editor = prefs.edit()
        prefs.all.keys.filter { it.startsWith(prefix) }.forEach { editor.remove(it) }
        editor.apply()
    }

    fun exportAll(): JSONObject {
        val configs = JSONObject()
        prefs.all.toSortedMap().forEach { (key, value) ->
            if (value is String) configs.put(key, JSONObject(value))
        }
        return JSONObject()
            .put("schema_version", EXPORT_SCHEMA_VERSION)
            .put("format", "dwpm_clone_static_mock_configs")
            .put("configs", configs)
    }

    fun importAll(exportJson: JSONObject, clearExisting: Boolean = false): ImportResult {
        val version = exportJson.optString("schema_version")
        if (version != EXPORT_SCHEMA_VERSION) {
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
        editor.apply()
        return ImportResult(true, count, "imported $count config entries")
    }

    private fun key(accountId: Long, featureId: String): String = "$accountId::$featureId"

    companion object {
        const val EXPORT_SCHEMA_VERSION = "0.1-static-mock"
    }
}

data class ImportResult(
    val success: Boolean,
    val importedCount: Int,
    val message: String
)

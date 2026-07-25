package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONObject

data class LocalRoleState(
    val roleName: String,
    val remark: String,
    val level: String,
    val exp: String,
    val nation: String,
    val copper: String,
    val food: String,
    val population: String,
    val resourcePoint: String,
    val generals: String,
    val troops: String,
    val treasures: String,
    val buffs: String,
    val source: String,
    val syncedAt: String
)

class LocalRoleStateRepository(context: Context) {
    private val prefs = context.getSharedPreferences("dwpm_clone_role_state", Context.MODE_PRIVATE)

    fun load(): LocalRoleState? {
        val raw = prefs.getString(KEY_STATE, null) ?: return null
        return runCatching {
            JSONObject(raw).let {
                LocalRoleState(
                    roleName = it.optString("roleName"),
                    remark = it.optString("remark"),
                    level = it.optString("level"),
                    exp = it.optString("exp"),
                    nation = it.optString("nation"),
                    copper = it.optString("copper"),
                    food = it.optString("food"),
                    population = it.optString("population"),
                    resourcePoint = it.optString("resourcePoint"),
                    generals = it.optString("generals"),
                    troops = it.optString("troops"),
                    treasures = it.optString("treasures"),
                    buffs = it.optString("buffs"),
                    source = it.optString("source"),
                    syncedAt = it.optString("syncedAt")
                )
            }
        }.getOrNull()
    }

    fun save(state: LocalRoleState) {
        prefs.edit().putString(KEY_STATE, JSONObject()
            .put("roleName", state.roleName)
            .put("remark", state.remark)
            .put("level", state.level)
            .put("exp", state.exp)
            .put("nation", state.nation)
            .put("copper", state.copper)
            .put("food", state.food)
            .put("population", state.population)
            .put("resourcePoint", state.resourcePoint)
            .put("generals", state.generals)
            .put("troops", state.troops)
            .put("treasures", state.treasures)
            .put("buffs", state.buffs)
            .put("source", state.source)
            .put("syncedAt", state.syncedAt)
            .toString()
        ).apply()
    }

    fun clear() {
        prefs.edit().remove(KEY_STATE).apply()
    }

    companion object {
        private const val KEY_STATE = "latest_role_state_json"
    }
}

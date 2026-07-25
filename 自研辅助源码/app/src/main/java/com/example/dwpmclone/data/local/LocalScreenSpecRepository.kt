package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Reads the generated static screen spec asset (`screen_specs.json`). */
class LocalScreenSpecRepository(private val context: Context) {
    fun loadAll(): List<ScreenSpec> {
        val root = JSONObject(readAssetText("screen_specs.json"))
        val recoveredScreens = root.getJSONArray("screens")
            .toList { item -> item.toScreenSpec() }
            .filterNot { it.featureId in EXCLUDED_V1_FEATURE_IDS }
        val existingIds = recoveredScreens.mapTo(mutableSetOf()) { it.featureId }
        return recoveredScreens + supplementalV1Screens().filterNot { it.featureId in existingIds }
    }

    fun findByFeatureId(featureId: String): List<ScreenSpec> =
        loadAll().filter { it.featureId == featureId }

    fun findByLayout(layout: String): ScreenSpec? =
        loadAll().firstOrNull { it.layout == layout }

    private fun JSONObject.toScreenSpec(): ScreenSpec = ScreenSpec(
        layout = getString("layout"),
        featureId = getString("feature_id"),
        featureNameZh = getString("feature_name_zh"),
        controls = getJSONArray("controls").toList { it.toScreenControl() },
        inputs = getJSONArray("inputs").toList { it.toScreenControl() },
        toggles = getJSONArray("toggles").toList { it.toScreenControl() },
        actions = getJSONArray("actions").toList { it.toScreenControl() },
        staticRules = optJSONArray("static_rules")?.toStringList().orEmpty()
    )

    private fun JSONObject.toScreenControl(): ScreenControl = ScreenControl(
        widget = getString("widget"),
        id = optNullableString("id"),
        label = optString("label"),
        text = optString("text"),
        hint = optString("hint"),
        checked = optNullableString("checked"),
        visibility = optNullableString("visibility"),
        inputType = optNullableString("inputType"),
        onClick = optNullableString("onClick"),
        role = optString("role")
    )

    private fun JSONObject.optNullableString(key: String): String? =
        if (!has(key) || isNull(key)) null else optString(key).ifBlank { null }

    private fun <T> JSONArray.toList(transform: (JSONObject) -> T): List<T> =
        (0 until length()).map { index -> transform(getJSONObject(index)) }

    private fun JSONArray.toStringList(): List<String> =
        (0 until length()).map { index -> getString(index) }

    private fun readAssetText(path: String): String =
        context.assets.open(path).bufferedReader(Charsets.UTF_8).use { it.readText() }

    private fun supplementalV1Screens(): List<ScreenSpec> = listOf(
        ScreenSpec(
            layout = "kotlin/supplemental_auto_loot.xml",
            featureId = "auto_loot",
            featureNameZh = "自动掠夺",
            controls = listOf(
                ScreenControl("TextView", null, "自动掠夺配置", "", "", null, null, null, null, "note"),
                ScreenControl("Switch", "auto_loot_enabled", "开启自动掠夺", "", "", "false", null, null, null, "toggle"),
                ScreenControl("CheckBox", "auto_loot_formation_1", "使用编队1", "", "", "true", null, null, null, "toggle"),
                ScreenControl("EditText", "auto_loot_target_player", "目标玩家", "", "请输入玩家名称", null, null, "text", null, "input"),
                ScreenControl("EditText", "auto_loot_fief_index", "封地序号", "1", "按目标玩家封地列表的序号", null, null, "number", null, "input"),
                ScreenControl("Button", null, "保存掠夺设置", "", "", null, null, null, "onMockAutoLootPlan", "action")
            ),
            inputs = emptyList(),
            toggles = emptyList(),
            actions = emptyList(),
            staticRules = listOf("将领必须为空闲、体力充足且配兵有效", "将领回闲后继续循环掠夺")
        ),
        ScreenSpec(
            layout = "kotlin/supplemental_alarm_withdraw.xml",
            featureId = "alarm_withdraw",
            featureNameZh = "警报扫描 / 撤防",
            controls = listOf(
                ScreenControl("TextView", null, "警报扫描配置：匹配掠夺、夺取、攻城、敌军等关键词；撤防动作仅记录本地计划。", "", "", null, null, null, null, "note"),
                ScreenControl("Switch", "alarm_withdraw_enabled", "开启警报扫描", "", "", "false", null, null, null, "toggle"),
                ScreenControl("EditText", "alarm_keywords", "警报关键词", "掠夺,夺取,攻城,敌军", "逗号分隔", null, null, "text", null, "input"),
                ScreenControl("CheckBox", "alarm_vibrate", "命中后震动/通知", "", "", "true", null, null, null, "toggle"),
                ScreenControl("CheckBox", "alarm_withdraw_defense", "命中后撤防（仅记录计划）", "", "", "false", null, null, null, "toggle"),
                ScreenControl("Button", null, "执行本地警报扫描", "", "", null, null, null, "onMockAlarmScan", "action")
            ),
            inputs = emptyList(),
            toggles = emptyList(),
            actions = emptyList(),
            staticRules = listOf("当前调度不执行真实撤防", "撤防相关真实请求必须经过额外授权和确认")
        )
    )

    companion object {
        private val EXCLUDED_V1_FEATURE_IDS = setOf(
            "shuai_search",
            "shuai_result",
            "shuai_result_row",
            "license",
            "enter_gate"
        )
    }
}

data class ScreenSpec(
    val layout: String,
    val featureId: String,
    val featureNameZh: String,
    val controls: List<ScreenControl>,
    val inputs: List<ScreenControl>,
    val toggles: List<ScreenControl>,
    val actions: List<ScreenControl>,
    val staticRules: List<String>
)

data class ScreenControl(
    val widget: String,
    val id: String?,
    val label: String,
    val text: String,
    val hint: String,
    val checked: String?,
    val visibility: String?,
    val inputType: String?,
    val onClick: String?,
    val role: String
)

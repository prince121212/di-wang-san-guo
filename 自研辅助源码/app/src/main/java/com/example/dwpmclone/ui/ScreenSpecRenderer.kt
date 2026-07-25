package com.example.dwpmclone.ui

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.RadioButton
import android.widget.Spinner
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import com.example.dwpmclone.data.local.ScreenControl
import com.example.dwpmclone.data.local.ScreenSpec
import org.json.JSONObject

/** Programmatic renderer for recovered screen specs, styled for production read-only configuration. */
class ScreenSpecRenderer(private val context: Context) {
    fun render(
        spec: ScreenSpec,
        savedConfig: JSONObject? = null,
        onLocalAction: ((String) -> Unit)? = null
    ): RenderedScreen {
        val bindings = mutableListOf<FormBinding>()
        val values = savedConfig?.optJSONObject("values")
        val formCard = card().apply {
            if (spec.staticRules.isNotEmpty()) addView(rules(spec.staticRules))
            spec.controls.forEach { control ->
                val view = renderControl(control, values, onLocalAction)
                if (view != null) {
                    if (control.isValueBearing()) bindings += FormBinding(control, view)
                    addView(view)
                }
            }
        }
        val root = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(16), dp(16), dp(24))
            addView(titleCard(spec))
            addView(formCard)
        }
        return RenderedScreen(root = root, spec = spec, bindings = bindings)
    }


    fun renderEmbedded(
        spec: ScreenSpec,
        savedConfig: JSONObject? = null,
        onLocalAction: ((String) -> Unit)? = null
    ): RenderedScreen {
        val bindings = mutableListOf<FormBinding>()
        val values = savedConfig?.optJSONObject("values")
        val root = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), dp(8), dp(10), dp(8))
            if (spec.staticRules.isNotEmpty()) addView(rules(spec.staticRules))
        }
        addCompactControls(root, spec.controls, values, onLocalAction, bindings)
        return RenderedScreen(root = root, spec = spec, bindings = bindings)
    }

    private fun addCompactControls(
        root: LinearLayout,
        controls: List<ScreenControl>,
        values: JSONObject?,
        onLocalAction: ((String) -> Unit)?,
        bindings: MutableList<FormBinding>
    ) {
        var index = 0
        while (index < controls.size) {
            val control = controls[index]
            val next = controls.getOrNull(index + 1)
            val label = cleanLabel(control.label.ifBlank { control.text }.ifBlank { control.id ?: control.widget })
            if (control.widget == "TextView" && next != null && next.isValueBearing() && label.length <= 18) {
                val row = compactRow()
                row.addView(compactLabel(label))
                renderControl(next, values, onLocalAction)?.let { view ->
                    if (next.isValueBearing()) bindings += FormBinding(next, view)
                    row.addView(view, LinearLayout.LayoutParams(0, dp(42), 1f).apply { setMargins(dp(6), 0, dp(6), 0) })
                }
                val nextLabel = controls.getOrNull(index + 2)
                val nextValue = controls.getOrNull(index + 3)
                if (nextLabel?.widget == "TextView" && nextValue != null && nextValue.isValueBearing()) {
                    val label2 = cleanLabel(nextLabel.label.ifBlank { nextLabel.text })
                    if (label2.length <= 8) {
                        row.addView(compactLabel(label2))
                        renderControl(nextValue, values, onLocalAction)?.let { view ->
                            if (nextValue.isValueBearing()) bindings += FormBinding(nextValue, view)
                            row.addView(view, LinearLayout.LayoutParams(0, dp(42), 1f))
                        }
                        index += 4
                    } else {
                        index += 2
                    }
                } else {
                    index += 2
                }
                root.addView(row)
            } else if (control.widget in setOf("CheckBox", "RadioButton")) {
                val row = compactRow()
                repeat(2) { offset ->
                    controls.getOrNull(index + offset)?.takeIf { it.widget in setOf("CheckBox", "RadioButton") }?.let { c ->
                        renderControl(c, values, onLocalAction)?.let { view ->
                            if (c.isValueBearing()) bindings += FormBinding(c, view)
                            row.addView(view, LinearLayout.LayoutParams(0, dp(42), 1f))
                        }
                    }
                }
                root.addView(row)
                index += row.childCount
            } else if (control.widget == "Button") {
                val row = compactRow()
                var count = 0
                while (count < 3 && controls.getOrNull(index + count)?.widget == "Button") {
                    val c = controls[index + count]
                    renderControl(c, values, onLocalAction)?.let { view ->
                        row.addView(view, LinearLayout.LayoutParams(0, dp(42), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
                    }
                    count++
                }
                root.addView(row)
                index += count
            } else {
                renderControl(control, values, onLocalAction)?.let { view ->
                    if (control.isValueBearing()) bindings += FormBinding(control, view)
                    root.addView(view)
                }
                index++
            }
        }
    }

    private fun compactRow(): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = android.view.Gravity.CENTER_VERTICAL
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(238, 238, 238))
        setPadding(dp(6), dp(4), dp(6), dp(4))
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    private fun compactLabel(label: String): TextView = TextView(context).apply {
        text = label
        textSize = 15f
        setTextColor(COLOR_TEXT)
        gravity = android.view.Gravity.CENTER_VERTICAL
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(42))
    }

    private fun renderControl(
        control: ScreenControl,
        values: JSONObject?,
        onLocalAction: ((String) -> Unit)?
    ): View? {
        val label = cleanLabel(control.label.ifBlank { control.text }.ifBlank { control.id ?: control.widget })
        val key = control.key()
        return when (control.widget) {
            "TextView" -> if (label.isBlank()) null else TextView(context).apply {
                text = label
                textSize = if (label.endsWith("：") || label.endsWith(":")) 14.5f else 14f
                typeface = if (label.endsWith("：") || label.endsWith(":")) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
                setTextColor(if (label.startsWith("【") || label.startsWith("①")) COLOR_SUBTEXT else COLOR_TEXT)
                setPadding(0, dp(12), 0, dp(4))
                setLineSpacing(2f, 1.0f)
            }
            "Button" -> Button(context).apply {
                val actionName = control.onClick ?: label
                text = label.ifBlank { "执行操作" }
                isAllCaps = false
                textSize = 15f
                setTextColor(COLOR_PRIMARY)
                background = roundedStroke(Color.WHITE, 12f, COLOR_BORDER)
                setOnClickListener {
                    onLocalAction?.invoke(actionName)
                        ?: Toast.makeText(context, "local action: $actionName", Toast.LENGTH_SHORT).show()
                }
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    dp(48)
                ).apply { setMargins(0, dp(10), 0, 0) }
            }
            "EditText" -> EditText(context).apply {
                setText(values.optSavedString(key) ?: control.text.takeUnless { it.startsWith("hint:") }.orEmpty())
                hint = control.hint.ifBlank { label.removeSuffix("：") }
                textSize = 15f
                setTextColor(COLOR_TEXT)
                setHintTextColor(COLOR_MUTED)
                setSingleLine(control.inputType != "textMultiLine")
                inputType = when (control.inputType) {
                    "number" -> InputType.TYPE_CLASS_NUMBER
                    "textMultiLine" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
                    "textPersonName" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PERSON_NAME
                    else -> InputType.TYPE_CLASS_TEXT
                }
                background = roundedStroke(Color.rgb(248, 250, 252), 10f, COLOR_BORDER)
                setPadding(dp(12), 0, dp(12), 0)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    if (control.inputType == "textMultiLine") dp(96) else dp(48)
                ).apply { setMargins(0, dp(6), 0, dp(4)) }
            }
            "CheckBox" -> CheckBox(context).apply {
                text = label
                textSize = 15f
                setTextColor(COLOR_TEXT)
                isChecked = values?.optBoolean(key, control.checked == "true") ?: (control.checked == "true")
                setPadding(0, dp(4), 0, dp(4))
            }
            "Switch" -> Switch(context).apply {
                text = label.ifBlank { "开关" }
                textSize = 15f
                setTextColor(COLOR_TEXT)
                isChecked = values?.optBoolean(key, control.checked == "true") ?: (control.checked == "true")
                setPadding(0, dp(6), 0, dp(6))
            }
            "RadioButton" -> RadioButton(context).apply {
                text = label
                textSize = 15f
                setTextColor(COLOR_TEXT)
                isChecked = values?.optBoolean(key, control.checked == "true") ?: (control.checked == "true")
                setPadding(0, dp(4), 0, dp(4))
            }
            "Spinner" -> Spinner(context).apply {
                val saved = values.optSavedString(key)
                val entries = listOfNotNull(saved, label.ifBlank { "请选择" }).distinct()
                adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, entries)
                background = roundedStroke(Color.rgb(248, 250, 252), 10f, COLOR_BORDER)
                setPadding(dp(10), 0, dp(10), 0)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    dp(48)
                ).apply { setMargins(0, dp(6), 0, dp(4)) }
            }
            "ListView" -> ListView(context).apply {
                val rows = listOf(label.ifBlank { "暂无列表数据" })
                adapter = ArrayAdapter(context, android.R.layout.simple_list_item_1, rows)
                background = roundedStroke(Color.rgb(248, 250, 252), 10f, COLOR_BORDER)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    dp(88)
                ).apply { setMargins(0, dp(8), 0, dp(4)) }
            }
            else -> if (label.isBlank()) null else TextView(context).apply {
                text = label
                textSize = 14f
                setTextColor(COLOR_SUBTEXT)
                setPadding(0, dp(8), 0, dp(4))
            }
        }
    }

    private fun titleCard(spec: ScreenSpec): LinearLayout = card().apply {
        addView(TextView(context).apply {
            text = spec.featureNameZh
            textSize = 22f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(COLOR_TEXT)
        })
        addView(TextView(context).apply {
            text = "生产配置页 · 保存后参与本地任务调度"
            textSize = 13f
            setTextColor(COLOR_SUBTEXT)
            setPadding(0, dp(8), 0, 0)
        })
    }

    private fun rules(rules: List<String>): TextView = TextView(context).apply {
        text = rules.joinToString(prefix = "提示\n", separator = "\n") { "• $it" }
        textSize = 13f
        setTextColor(COLOR_SUBTEXT)
        background = rounded(Color.rgb(239, 246, 255), 12f)
        setPadding(dp(12), dp(12), dp(12), dp(12))
        setLineSpacing(2f, 1.0f)
    }

    private fun card(): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(18), dp(18), dp(18), dp(18))
        background = rounded(Color.WHITE, 18f)
        elevation = dp(2).toFloat()
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, 0, 0, dp(14)) }
    }

    private fun cleanLabel(value: String): String = value
        .removePrefix("hint:")
        .replace("APKTOOL_RENAMED_", "字段")
        .trim()

    private fun rounded(color: Int, radiusDp: Float): GradientDrawable = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        setColor(color)
        cornerRadius = dp(radiusDp.toInt()).toFloat()
    }

    private fun roundedStroke(color: Int, radiusDp: Float, strokeColor: Int): GradientDrawable = rounded(color, radiusDp).apply {
        setStroke(dp(1), strokeColor)
    }

    private fun dp(value: Int): Int = (value * context.resources.displayMetrics.density).toInt()

    companion object {
        private val COLOR_TEXT = Color.rgb(31, 41, 55)
        private val COLOR_SUBTEXT = Color.rgb(107, 114, 128)
        private val COLOR_MUTED = Color.rgb(148, 163, 184)
        private val COLOR_PRIMARY = Color.rgb(46, 111, 242)
        private val COLOR_BORDER = Color.rgb(226, 232, 240)
    }
}

data class RenderedScreen(
    val root: LinearLayout,
    val spec: ScreenSpec,
    private val bindings: List<FormBinding>
) {
    fun collectValues(): JSONObject {
        val values = JSONObject()
        bindings.forEach { binding ->
            values.put(binding.control.key(), binding.readValue())
        }
        return JSONObject()
            .put("schema_version", "0.1-static-screen-form")
            .put("feature_id", spec.featureId)
            .put("feature_name_zh", spec.featureNameZh)
            .put("layout", spec.layout)
            .put("values", values)
    }
}

data class FormBinding(val control: ScreenControl, val view: View) {
    fun readValue(): Any? = when (view) {
        is EditText -> view.text?.toString().orEmpty()
        is CheckBox -> view.isChecked
        is Switch -> view.isChecked
        is RadioButton -> view.isChecked
        is Spinner -> view.selectedItem?.toString().orEmpty()
        else -> null
    }
}

private fun ScreenControl.isValueBearing(): Boolean =
    widget in setOf("EditText", "CheckBox", "Switch", "RadioButton", "Spinner")

private fun JSONObject?.optSavedString(key: String): String? =
    if (this != null && has(key) && !isNull(key)) optString(key) else null

private fun ScreenControl.key(): String =
    id ?: onClick ?: label.ifBlank { widget }.take(64)

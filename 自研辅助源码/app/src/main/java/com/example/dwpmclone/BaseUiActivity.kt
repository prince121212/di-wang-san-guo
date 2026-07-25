package com.example.dwpmclone

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import com.example.dwpmclone.data.local.ScreenSpec

/** Shared programmatic UI helpers extracted from MainActivity. */
open class BaseUiActivity : Activity() {
    protected val COLOR_BG: Int = Color.rgb(246, 248, 252)
    protected val COLOR_PRIMARY: Int = Color.rgb(46, 111, 242)
    protected val COLOR_PRIMARY_DARK: Int = Color.rgb(31, 83, 191)
    protected val COLOR_TEXT: Int = Color.rgb(31, 41, 55)
    protected val COLOR_SUBTEXT: Int = Color.rgb(107, 114, 128)
    protected val COLOR_BORDER: Int = Color.rgb(226, 232, 240)

    protected fun pageTitle(textValue: String): TextView = TextView(this).apply {
        text = textValue
        gravity = Gravity.CENTER
        textSize = 18f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(COLOR_TEXT)
        setPadding(0, dp(44), 0, dp(14))
    }

    protected fun inputLp(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        dp(52)
    ).apply { setMargins(0, dp(10), 0, 0) }

    protected fun panelHeader(title: String, desc: String): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        addView(TextView(this@BaseUiActivity).apply {
            text = title
            textSize = 21f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(COLOR_TEXT)
        })
        addView(bodyText(desc).apply { setPadding(0, dp(5), 0, dp(10)) })
    }

    protected fun dataSection(title: String, rows: List<Pair<String, String>>): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(0, dp(8), 0, dp(8))
        addView(TextView(this@BaseUiActivity).apply {
            text = title
            textSize = 16f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(COLOR_TEXT)
        })
        rows.forEach { addView(dataRow(it.first, it.second)) }
    }

    protected fun dataRow(name: String, value: String): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        setPadding(0, dp(7), 0, 0)
        addView(TextView(this@BaseUiActivity).apply {
            text = name
            textSize = 14f
            setTextColor(COLOR_SUBTEXT)
            layoutParams = LinearLayout.LayoutParams(dp(92), ViewGroup.LayoutParams.WRAP_CONTENT)
        })
        addView(TextView(this@BaseUiActivity).apply {
            text = value
            textSize = 14f
            setTextColor(COLOR_TEXT)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        })
    }

    protected fun flowStep(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 14f
        setTextColor(COLOR_TEXT)
        setPadding(dp(10), dp(8), dp(10), dp(8))
        background = rounded(Color.rgb(248, 250, 252), 10f)
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, dp(6), 0, 0) }
    }

    protected fun smallChip(label: String, bg: Int, fg: Int): TextView = TextView(this).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 14f
        setTextColor(fg)
        background = rounded(bg, 5f)
        layoutParams = LinearLayout.LayoutParams(dp(58), dp(28))
    }

    protected fun smallAction(label: String, bg: Int, fg: Int, onClick: (() -> Unit)? = null): TextView = TextView(this).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 14f
        setTextColor(fg)
        background = rounded(bg, 5f)
        setOnClickListener { onClick?.invoke() ?: Toast.makeText(this@BaseUiActivity, "$label：真实执行接口未启用", Toast.LENGTH_SHORT).show() }
        layoutParams = LinearLayout.LayoutParams(0, dp(29), 1f).apply { setMargins(dp(5), 0, dp(5), 0) }
    }

    protected fun fieldBox(label: String): TextView = TextView(this).apply {
        text = label
        gravity = Gravity.CENTER_VERTICAL
        textSize = 15f
        setTextColor(Color.rgb(80, 80, 80))
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(210, 210, 210))
        setPadding(dp(8), 0, dp(8), 0)
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(24)
        ).apply { setMargins(dp(8), dp(6), dp(38), 0) }
    }

    protected fun pageRoot(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), 0, dp(4), dp(8))
    }

    protected fun card(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(4))
        background = rounded(Color.WHITE, 18f)
        elevation = dp(2).toFloat()
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, 0, 0, dp(14)) }
    }

    protected fun sectionTitle(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 18f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(COLOR_TEXT)
        setPadding(0, 0, 0, dp(8))
    }

    protected fun bodyText(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 14f
        setTextColor(COLOR_SUBTEXT)
        setLineSpacing(2f, 1.0f)
    }

    protected fun featureButton(spec: ScreenSpec, onClick: () -> Unit): Button = outlineButton("${spec.featureNameZh}  ›", onClick).apply {
        setTextColor(COLOR_TEXT)
        textAlignment = Button.TEXT_ALIGNMENT_TEXT_START
        setPadding(dp(16), 0, dp(16), 0)
    }

    protected fun primaryButton(textValue: String, onClick: () -> Unit): Button = Button(this).apply {
        text = textValue
        isAllCaps = false
        textSize = 15f
        setTextColor(Color.WHITE)
        background = rounded(COLOR_PRIMARY, 12f)
        setOnClickListener { onClick() }
        layoutParams = buttonLp()
    }

    protected fun outlineButton(textValue: String, onClick: () -> Unit): Button = Button(this).apply {
        text = textValue
        isAllCaps = false
        textSize = 15f
        setTextColor(COLOR_PRIMARY)
        background = roundedStroke(Color.WHITE, 12f, COLOR_BORDER)
        setOnClickListener { onClick() }
        layoutParams = buttonLp()
    }

    protected fun buttonLp(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        dp(48)
    ).apply { setMargins(0, dp(10), 0, 0) }

    protected fun rounded(color: Int, radiusDp: Float): GradientDrawable = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        setColor(color)
        cornerRadius = dp(radiusDp.toInt()).toFloat()
    }

    protected fun roundedStroke(color: Int, radiusDp: Float, strokeColor: Int): GradientDrawable = rounded(color, radiusDp).apply {
        setStroke(dp(1), strokeColor)
    }

    protected fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}

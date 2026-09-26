package com.example.dwpmclone.ui.hosting

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.example.dwpmclone.data.local.TaskLogRepository

/** Explanatory UI only: never self-grants permissions or starts game tasks. */
class HostingPermissionGuideActivity : Activity() {
    private lateinit var coordinator: BackgroundHostingPermissionCoordinator
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        coordinator = BackgroundHostingPermissionCoordinator(this) { TaskLogRepository(this).append(it, tag = "scheduler-health") }
    }
    override fun onResume() { super.onResume(); if (::coordinator.isInitialized) render() }
    private fun render() {
        val state = BackgroundHostingPermissionState.read(this)
        val body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(22), dp(42), dp(22), dp(40)) }
        fun text(value: String, size: Float = 15f): TextView = TextView(this).apply {
            text = value; textSize = size; setTextColor(Color.rgb(35, 53, 69)); setPadding(0, dp(8), 0, dp(8))
        }
        body.addView(text("后台运行设置", 25f))
        body.addView(text(if (state.reliableHostingReady) "后台运行建议已满足" else "未开启也可启动账号和任务", 19f))
        body.addView(text("以下均为后台稳定运行建议，只在你点击按钮时请求。暂不开启也可正常使用；切到后台或锁屏后，系统可能暂停网络或停止应用。"))
        val items = state.toJson().getJSONArray("items")
        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            val granted = !item.isNull("granted") && item.optBoolean("granted")
            val requirement = "建议/按需"
            val status = if (item.isNull("granted")) "需手动核对" else if (granted) "已完成" else "未开启"
            body.addView(text("${item.getString("title")} · $requirement · $status", 17f))
            body.addView(text(item.optString("detail"), 13f))
            body.addView(Button(this).apply {
                text = if (granted) "查看设置" else "去设置"
                setOnClickListener { coordinator.open(item.getString("action")) }
            })
        }
        val guidance = VendorBackgroundGuidance.forManufacturer(android.os.Build.MANUFACTURER).toJson()
        if (state.vendorManualReviewRequired) {
            body.addView(text("${state.vendorFamily}手动设置提示", 18f))
            for (key in listOf("autostartSteps", "batterySteps")) {
                val steps = guidance.optJSONArray(key) ?: continue
                for (i in 0 until steps.length()) body.addView(text("• ${steps.getString(i)}", 13f))
            }
            body.addView(text(guidance.optString("pathCaveat"), 12f))
        }
        body.addView(Button(this).apply { text = "重新检测"; setOnClickListener { render() } })
        body.addView(Button(this).apply { text = "返回应用"; setOnClickListener { finish() } })
        setContentView(ScrollView(this).apply { setBackgroundColor(Color.rgb(246,248,250)); addView(body)
            if (android.os.Build.VERSION.SDK_INT >= 30) setOnApplyWindowInsetsListener { v, insets ->
                val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.displayCutout())
                v.setPadding(bars.left,bars.top,bars.right,bars.bottom); insets
            }
        })
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (coordinator.onRequestPermissionsResult(requestCode)) render()
        else super.onRequestPermissionsResult(requestCode, permissions, grantResults)
    }
}

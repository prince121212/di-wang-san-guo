package com.example.dwpmclone

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.example.dwpmclone.host.MembershipClient
import com.example.dwpmclone.host.MembershipPlans
import java.util.concurrent.Executors
import org.json.JSONObject

/** Real pre-order storefront: works before onboarding, never invents an order. */
class MembershipStoreActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val ink = Color.rgb(27, 47, 49)
    private val muted = Color.rgb(105, 119, 118)
    private val green = Color.rgb(26, 102, 85)
    private val cream = Color.rgb(246, 247, 243)
    private var selection: MembershipPlans.Plan? = null
    private var busy = false
    private var closed = false
    private lateinit var content: LinearLayout
    private lateinit var statusText: TextView
    private lateinit var payButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        @Suppress("DEPRECATION")
        window.statusBarColor = cream
        @Suppress("DEPRECATION")
        window.navigationBarColor = cream
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
        selection = MembershipPlans.find(savedInstanceState?.getString("plan"))
        render()
    }
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun shape(color: Int, stroke: Int? = null) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(18).toFloat()
        if (stroke != null) setStroke(dp(1), stroke)
    }
    private fun label(value: String, size: Float = 15f, color: Int = ink, bold: Boolean = false) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color); setLineSpacing(dp(4).toFloat(), 1f)
        if (bold) typeface = Typeface.DEFAULT_BOLD
    }
    private fun add(parent: LinearLayout, view: View, top: Int = 0) {
        parent.addView(view, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(top) })
    }
    private fun card(parent: LinearLayout, color: Int = Color.WHITE): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(14), dp(20), dp(14))
        background = shape(color); add(parent, this, 10)
    }
    private fun action(title: String, run: () -> Unit) = Button(this).apply {
        text = title; textSize = 16f; isAllCaps = false; setTextColor(Color.WHITE)
        background = shape(green); minHeight = dp(46); setOnClickListener { if (!busy) run() }
    }
    private fun render() {
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(22), dp(16), dp(22), dp(32))
        }
        setContentView(ScrollView(this).apply { setBackgroundColor(cream); isFillViewport = true; addView(content) })
        val selected = selection
        add(content, label(if (selected == null) "‹  返回会员中心" else "‹  返回套餐选择", 14f, green).apply {
            setPadding(0, dp(8), 0, dp(8))
            setOnClickListener { if (!busy) { if (selection == null) finish() else { selection = null; render() } } }
        })
        add(content, label("帝三资料库", 14f, muted), 8)
        add(content, label(if (selected == null) "选择适合你的会员" else "确认购买", 26f, ink, true), 6)
        add(content, label(if (selected == null) "攻略资料 · 游戏辅助工具会员" else "核对套餐后，使用支付宝付款", 14f, muted), 8)
        if (selected == null) {
            val hero = card(content, Color.rgb(225, 237, 227))
            add(hero, label("一份会员，安心使用", 19f, green, true))
            add(hero, label("单手机授权  /  本机双账号\n游戏辅助与自动化功能 · 配置本地保存", 14f, green), 8)
            for (plan in MembershipPlans.all) {
                val box = card(content)
                val row = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
                row.addView(label("${plan.title}  ·  ${plan.days}天", 20f, ink, true), LinearLayout.LayoutParams(0, -2, 1f))
                row.addView(label("¥${plan.price}", 27f, green, true))
                add(box, row); add(box, label(plan.note, 13f, muted), 4)
                add(box, action("选择${plan.title}") { selection = plan; render() }, 10)
            }
            add(content, label("一次购买 · 不自动续费\n付款成功后开通或顺延会员；实际订单金额由服务端核定。", 12f, muted), 18)
            add(content, label("选择套餐后确认支付方式，收款状态以确认页为准。", 12f, muted), 10)
        } else {
            val order = card(content)
            add(order, label("会员套餐", 13f, muted))
            add(order, label("帝三资料库 · ${selected.title}", 21f, ink, true), 8)
            add(order, label("有效期 ${selected.days}天   /   单手机 · 双账号", 14f, muted), 8)
            add(order, label("应付金额", 13f, muted), 24)
            add(order, label("¥${selected.price}", 38f, green, true), 4)
            add(order, label("一次性购买，不自动续费", 13f, muted), 6)
            val method = card(content)
            add(method, label("支付方式", 14f, muted))
            add(method, label("支付宝                          ✓", 22f, Color.rgb(22, 119, 255), true), 12)
            add(method, label("通过支付宝官方收银台完成付款\n本应用不获取你的支付宝支付密码", 13f, muted), 10)
            val details = card(content)
            add(details, label("购买说明", 16f, ink, true))
            add(details, label("• 会员用于本应用游戏辅助与自动化功能\n• 付款前需登录你的会员账号\n• 到账以服务器确认结果为准\n• 未确认到账时，请勿重复付款", 13f, muted), 8)
            statusText = label("正在检查在线收款状态…", 13f, muted)
            add(content, statusText, 18)
            payButton = action("支付宝付款 ¥${selected.price}") { submit(selected) }
            payButton.isEnabled = false
            payButton.alpha = 0.55f
            add(content, payButton, 12)
            add(content, label("尚未提交订单，未扣款", 12f, muted).apply { gravity = Gravity.CENTER }, 12)
            checkAvailability(selected)
        }
    }
    private fun available(plan: MembershipPlans.Plan): Boolean {
        val c = MembershipClient.get(this).handle("payment-catalog", JSONObject())
        if (!c.optBoolean("enabled") || c.optString("mode") != "production") return false
        val plans = c.optJSONArray("plans") ?: return false
        return (0 until plans.length()).map { plans.getJSONObject(it) }.any {
            it.optString("plan") == plan.id && it.optString("totalAmount") == plan.price && it.optInt("days") == plan.days
        }
    }
    private fun checkAvailability(plan: MembershipPlans.Plan) {
        worker.execute {
            val ready = runCatching { available(plan) }.getOrDefault(false)
            runOnUiThread {
                if (!closed && selection == plan) {
                    payButton.isEnabled = ready
                    payButton.alpha = if (ready) 1f else 0.55f
                    statusText.text = if (ready) "请选择支付宝付款，金额将在下单时再次核对。" else
                        "在线收款暂未开放或套餐尚未同步，当前不会扣款。"
                }
            }
        }
    }
    private fun submit(plan: MembershipPlans.Plan) {
        busy = true; payButton.isEnabled = false; statusText.text = "正在核对会员账号和订单…"
        worker.execute {
            val result = runCatching {
                val client = MembershipClient.get(this)
                check(client.status().optBoolean("authenticated")) { "请先返回会员中心登录，再购买套餐。" }
                check(available(plan)) { "套餐或收款状态已变化，请稍后重新查看。" }
                val created = client.handle("payment-create", JSONObject().put("plan", plan.id))
                check(created.optBoolean("ok")) { created.optString("error", "下单结果待确认，请查询原订单。") }
                val order = created.getJSONObject("order")
                check(order.optString("mode") == "production" && order.optString("totalAmount") == plan.price && order.optString("plan") == plan.id) {
                    "订单金额已变化，未调起付款。请返回会员中心核对原订单。"
                }
                val opened = client.handle("payment-open", JSONObject())
                check(opened.optBoolean("ok")) { opened.optString("error", "无法打开支付，请查询原订单。") }
            }
            runOnUiThread {
                if (!closed) {
                    busy = false
                    statusText.text = result.exceptionOrNull()?.message ?: "已打开支付宝付款流程，请勿重复下单。"
                    // Require re-entering checkout after an attempt; original order remains queryable.
                }
            }
        }
    }
    override fun onSaveInstanceState(outState: Bundle) { outState.putString("plan", selection?.id); super.onSaveInstanceState(outState) }
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() { if (!busy && selection != null) { selection = null; render() } else if (!busy) super.onBackPressed() }
    override fun onDestroy() { closed = true; worker.shutdown(); super.onDestroy() }
}

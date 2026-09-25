package com.example.dwpmclone

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.alipay.sdk.app.EnvUtils
import com.alipay.sdk.app.PayTask
import com.example.dwpmclone.host.AlipayResultPolicy
import com.example.dwpmclone.host.MembershipClient
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Order strings stay in native memory. SDK callback never grants membership. */
class AlipayPaymentActivity : Activity() {
    private val work = Executors.newSingleThreadScheduledExecutor()
    private lateinit var text: TextView
    private lateinit var queryButton: Button
    private lateinit var orderId: String
    @Volatile private var closed = false
    private val querying = AtomicBoolean(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        orderId = intent.getStringExtra("orderId").orEmpty()
        if (!Regex("DW[SP][a-f0-9]{32}").matches(orderId)) { finish(); return }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val padding = (24 * resources.displayMetrics.density).toInt()
            setPadding(padding, padding * 2, padding, padding)
        }
        text = TextView(this).apply { textSize = 18f; text = "正在准备支付宝订单…" }
        queryButton = Button(this).apply { text = "查询付款结果"; setOnClickListener { query(0) } }
        layout.addView(text); layout.addView(queryButton)
        layout.addView(Button(this).apply { text = "返回会员页"; setOnClickListener { finish() } })
        setContentView(layout)
        // Recreated screens query only: never silently repeat a payment prompt.
        if (savedInstanceState != null || paying.get()) { query(0); return }
        work.execute {
            try {
                val response = MembershipClient.get(this).nativePaymentOrder(orderId)
                val sandbox = response.getString("mode") == "sandbox"
                val amount = response.getJSONObject("order").getString("totalAmount")
                val orderStr = response.getString("orderStr")
                require(orderStr.isNotBlank())
                runOnUiThread {
                    if (!closed && !isFinishing) AlertDialog.Builder(this)
                        .setTitle(if (sandbox) "支付宝沙箱测试" else "支付宝购买会员")
                        .setMessage("订单金额 ¥$amount。\n" + if (sandbox)
                            "需要独立的支付宝沙箱钱包和测试账号，普通支付宝不能支付。不会扣真实资金或增加真实会员时长。" else
                            "继续将调用支付宝官方SDK处理订单及支付所需设备、网络信息。付款需要你在支付宝确认；不自动续费。")
                        .setNegativeButton("暂不支付") { _, _ -> query(0) }
                        .setPositiveButton("继续支付宝付款") { _, _ -> pay(orderStr, sandbox) }
                        .setOnCancelListener { query(0) }.show()
                }
            } catch (_: Exception) {
                show("无法准备付款：订单可能已超时、已支付或服务未开放。请查询原订单，不要重复付款。")
                query(0)
            }
        }
    }

    private fun pay(orderStr: String, sandbox: Boolean) {
        if (!paying.compareAndSet(false, true)) { show("已有支付操作进行中，请稍后查询原订单。"); return }
        show("正在打开支付宝，请在支付宝内确认。")
        work.execute {
            try {
                require(!sandbox || BuildConfig.DEBUG)
                EnvUtils.setEnv(if (sandbox) EnvUtils.EnvEnum.SANDBOX else EnvUtils.EnvEnum.ONLINE)
                val result = PayTask(this).payV2(orderStr, true)
                show(AlipayResultPolicy.message(result["resultStatus"]))
            } catch (_: Exception) {
                show("暂未收到支付宝结果，请查询原订单，不要重复付款。")
            } finally {
                paying.set(false)
                // Still reconcile if the screen was closed while SDK was running.
                runCatching { MembershipClient.get(this).refreshPayment(orderId) }
                if (!closed) query(0)
            }
        }
    }

    private fun query(attempt: Int) {
        if (closed || !querying.compareAndSet(false, true)) return
        work.execute {
            var retry = true
            try {
                val result = MembershipClient.get(this).refreshPayment(orderId)
                if (!result.optBoolean("ok")) {
                    show("暂时无法核实到账，请稍后查询原订单；不要重复付款。")
                } else {
                    val order = result.getJSONObject("order")
                    val status = order.getString("status")
                    retry = status == "PENDING" || (status == "PAID" && !order.optBoolean("fulfilled"))
                    show(when (status) {
                        "PAID" -> if (order.optString("mode") == "sandbox") "沙箱付款已确认，未增加真实会员时长。"
                            else if (order.optBoolean("membershipApplied")) "付款成功，会员已开通或顺延。请返回会员页。" else "到账已确认，会员权益同步中…"
                        "CLOSED" -> "原订单已关闭。返回会员页可以重新选择套餐。"
                        "REFUNDED" -> "该订单已退款。"
                        "REFUND_PENDING" -> "该订单退款处理中，请联系客服核对。"
                        else -> "尚未确认付款。若已付款请勿重复支付，可稍后查询。"
                    })
                }
            } catch (_: Exception) {
                show("暂时无法查询原订单，请返回会员页核对账号及网络。")
            } finally {
                querying.set(false)
            }
            if (retry && attempt < 4 && !closed) work.schedule({ query(attempt + 1) }, 6, TimeUnit.SECONDS)
        }
    }

    private fun show(message: String) = runOnUiThread { if (!closed && !isFinishing) text.text = message }
    override fun onDestroy() {
        closed = true
        // Do not interrupt an in-flight SDK call or its final reconciliation.
        work.shutdown()
        super.onDestroy()
    }
    companion object { private val paying = AtomicBoolean(false) }
}

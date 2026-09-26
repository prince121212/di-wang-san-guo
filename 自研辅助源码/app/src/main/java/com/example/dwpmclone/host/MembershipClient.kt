package com.example.dwpmclone.host

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.SystemClock
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.example.dwpmclone.AssistantWebActivity
import com.example.dwpmclone.AlipayPaymentActivity
import com.example.dwpmclone.BuildConfig
import com.example.dwpmclone.data.local.KeystoreAesGcmStore
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.Signature
import java.util.UUID
import org.json.JSONObject

/** Device-wide membership session. Never saves passwords or exposes bearer tokens to WebView/Python. */
class MembershipClient private constructor(private val context: Context) {
    private val vault = KeystoreAesGcmStore(context, "dwpm_membership_v1", "dwpm_membership_aes_v1", emptyList())
    private var saved: JSONObject = runCatching { JSONObject(vault.get("session") ?: "{}") }.getOrDefault(JSONObject())
    private var leaseDeadlineElapsed = 0L // A process restart MUST revalidate online.
    private var serverBaseMillis = 0L
    private var serverBaseElapsed = 0L
    private var nextRetryElapsed = 0L
    private var code = saved.optString("pauseCode").takeIf { it in TERMINAL_CODES }
        ?: if (saved.optString("sessionToken").isBlank()) "MEMBER_LOGIN_REQUIRED" else "MEMBER_CHECK_REQUIRED"
    private var message = saved.optString("pauseMessage").ifBlank {
        if (code == "MEMBER_LOGIN_REQUIRED") "请先登录会员账号" else "需要验证会员授权"
    }
    private var lastDetails = saved.optJSONObject("pauseDetails") ?: JSONObject()
    private var lastNotice = saved.optString("lastNotice")

    private fun persist() { vault.put("session", saved.toString()) }
    private fun keyStore(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    private fun ensureDeviceKey(): KeyStore {
        var store = keyStore()
        if (!store.containsAlias(DEVICE_KEY)) {
            KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, "AndroidKeyStore").apply {
                initialize(KeyGenParameterSpec.Builder(DEVICE_KEY, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .setKeySize(2048).setDigests(KeyProperties.DIGEST_SHA256)
                    .setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1).build())
            }.generateKeyPair()
            store = keyStore()
        }
        return store
    }
    private fun deviceId(): String = MessageDigest.getInstance("SHA-256")
        .digest(ensureDeviceKey().getCertificate(DEVICE_KEY).publicKey.encoded).joinToString("") { "%02x".format(it.toInt() and 255) }

    @Synchronized fun status(): JSONObject {
        val allowed = saved.optString("sessionToken").isNotBlank() && leaseDeadlineElapsed > SystemClock.elapsedRealtime()
        return JSONObject().put("ok", true).put("required", true).put("allowed", allowed)
            .put("authenticated", saved.optString("sessionToken").isNotBlank())
            .put("code", if (!allowed && code == "MEMBER_ACTIVE") "MEMBER_CHECK_REQUIRED" else code)
            .put("message", if (!allowed && code == "MEMBER_ACTIVE") "授权已到检查时间，需要联网验证" else message)
            .put("member", saved.optJSONObject("member") ?: JSONObject())
            .put("paymentOrder", saved.optJSONObject("paymentOrder")?.optJSONObject("order") ?: JSONObject())
            .put("maxGameAccounts", 2).put("remainingMillis", (leaseDeadlineElapsed - SystemClock.elapsedRealtime()).coerceAtLeast(0))
            .put("details", JSONObject(lastDetails.toString())).put("configTransfer", true)
    }

    @Synchronized fun memberId(): String? = saved.optJSONObject("member")?.optString("id")
        ?.takeIf { it.isNotBlank() && saved.optString("sessionToken").isNotBlank() }

    /** Manual 换手机 export: the signed payload carries only the document hash, the document rides beside it. */
    @Synchronized fun configBackupPut(password: String, backup: String): JSONObject = configBackupCall {
        signed("config-backup-put", JSONObject().put("sessionToken", saved.getString("sessionToken"))
            .put("password", password).put("backupSha256", sha256Hex(backup)), extra = JSONObject().put("backup", backup)).body
    }

    @Synchronized fun configBackupGet(password: String): JSONObject = configBackupCall {
        signed("config-backup-get", JSONObject().put("sessionToken", saved.getString("sessionToken"))
            .put("password", password), maxResponseChars = CONFIG_BACKUP_RESPONSE_CHARS).body
    }

    private fun configBackupCall(call: () -> JSONObject): JSONObject {
        if (saved.optString("sessionToken").isBlank()) {
            return JSONObject().put("ok", false).put("code", "MEMBER_LOGIN_REQUIRED").put("error", "请先登录会员账号")
        }
        return try { call() } catch (failure: MemberFailure) {
            if (failure.code in TERMINAL_CODES) deny(failure.code, failure.message ?: "会员授权不可用", failure.details)
            JSONObject().put("ok", false).put("code", failure.code).put("error", failure.message)
        } catch (_: Exception) {
            JSONObject().put("ok", false).put("code", "MEMBER_NETWORK_UNAVAILABLE").put("error", "会员服务连接失败，请稍后重试")
        }
    }

    private fun sha256Hex(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it.toInt() and 255) }

    @Synchronized fun cloudDataToken(): String =
        if (check(false).optBoolean("allowed")) saved.optString("cloudToken").takeUnless { it == "null" }.orEmpty() else ""

    @Synchronized fun check(force: Boolean = false): JSONObject {
        if (saved.optString("sessionToken").isBlank()) return status().put("allowed", false)
        if (!force && leaseDeadlineElapsed > SystemClock.elapsedRealtime()) return status()
        if (!force && (code in TERMINAL_CODES || SystemClock.elapsedRealtime() < nextRetryElapsed)) return status().put("allowed", false)
        return try {
            val result = signed("renew", JSONObject().put("sessionToken", saved.getString("sessionToken")))
            accept(result)
            status()
        } catch (failure: MemberFailure) {
            deny(failure.code, failure.message ?: "会员授权不可用", failure.details)
            status().put("allowed", false)
        } catch (_: Exception) {
            code = "MEMBER_NETWORK_UNAVAILABLE"
            message = "暂时无法验证会员授权，请检查网络；原授权到期后自动任务暂停"
            nextRetryElapsed = SystemClock.elapsedRealtime() + 60_000L
            if (leaseDeadlineElapsed <= SystemClock.elapsedRealtime()) notifyPaused()
            status().put("allowed", false)
        }
    }

    @Synchronized fun handle(action: String, body: JSONObject): JSONObject {
        if (action == "status") return status()
        if (action == "check") return check(force = body.optBoolean("force", true))
        if (action == "logout") {
            runCatching { if (saved.optString("sessionToken").isNotBlank()) signed("logout", JSONObject().put("sessionToken", saved.getString("sessionToken"))) }
            saved = JSONObject(); leaseDeadlineElapsed = 0; lastDetails = JSONObject(); code = "MEMBER_LOGIN_REQUIRED"
            message = "已退出会员登录，自动任务暂停；本机游戏数据仍保留"; persist()
            return status()
        }
        return try {
            when (action) {
                "payment-acceptance-create" -> {
                    require(BuildConfig.DEBUG) { "仅验收包支持测试入口" }
                    require(saved.optString("sessionToken").isNotBlank()) { "请先登录独立测试会员账号" }
                    val purchaseId = body.getString("purchaseId")
                    require(UUID.fromString(purchaseId).toString() == purchaseId)
                    val previous = saved.optJSONObject("paymentOrder")
                    require(previous == null || previous.optString("purchaseId") == purchaseId ||
                        previous.optJSONObject("order")?.optString("status") in setOf("PAID", "CLOSED", "REFUNDED")) { "请先核对原订单，不能覆盖待处理订单" }
                    val pending = JSONObject().put("plan", "month").put("purchaseId", purchaseId).put("channel", "app")
                    saved.put("paymentOrder", pending); persist()
                    val result = signed("payment-create", JSONObject().put("sessionToken", saved.getString("sessionToken"))
                        .put("plan", "month").put("purchaseId", purchaseId).put("channel", "app")).body
                    val order = result.getJSONObject("order")
                    pending.put("order", order); persist()
                    require(order.optBoolean("acceptance") && order.optString("totalAmount") == "0.01" && order.optInt("days") == 0) {
                        "服务端未返回一分钱验收单，不调起付款"
                    }
                    JSONObject().put("ok", true).put("order", order)
                }
                "payment-store-open" -> {
                    context.startActivity(Intent(context, com.example.dwpmclone.MembershipStoreActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    JSONObject().put("ok", true)
                }
                "payment-catalog" -> exchange("GET", "/v1/payments/catalog", null).also { catalog ->
                    val channels = catalog.optJSONArray("channels")
                    val nativeEnabled = channels != null && (0 until channels.length()).any { channels.optString(it) == "app" }
                    // Release builds never offer a sandbox payment to ordinary users.
                    if (!nativeEnabled || (!BuildConfig.DEBUG && catalog.optString("mode") != "production")) catalog.put("enabled", false)
                }
                "payment-create" -> {
                    require(saved.optString("sessionToken").isNotBlank()) { "请先登录会员" }
                    val plan = body.optString("plan")
                    require(plan in setOf("month", "quarter", "year"))
                    val previous = saved.optJSONObject("paymentOrder")
                    val priorStatus = previous?.optJSONObject("order")?.optString("status").orEmpty()
                    if (previous != null && priorStatus !in setOf("PAID", "CLOSED", "REFUNDED")) {
                        require(previous.optString("plan") == plan) { "请先查询上一笔订单" }
                    }
                    val purchaseId = if (previous != null && priorStatus !in setOf("PAID", "CLOSED", "REFUNDED"))
                        previous.getString("purchaseId") else UUID.randomUUID().toString()
                    val channel = if (previous != null && priorStatus !in setOf("PAID", "CLOSED", "REFUNDED"))
                        previous.optString("channel", "web") else "app"
                    val pending = JSONObject().put("plan", plan).put("purchaseId", purchaseId).put("channel", channel)
                    saved.put("paymentOrder", pending); persist() // Persist BEFORE sending: a lost reply reuses this id.
                    val result = signed(action, JSONObject().put("sessionToken", saved.getString("sessionToken"))
                        .put("plan", plan).put("purchaseId", purchaseId).put("channel", channel)).body
                    pending.put("order", result.getJSONObject("order"))
                    if (result.has("checkoutUrl")) pending.put("checkoutUrl", result.getString("checkoutUrl"))
                    persist()
                    JSONObject().put("ok", true).put("order", result.getJSONObject("order"))
                }
                "payment-status" -> {
                    val pending = saved.optJSONObject("paymentOrder") ?: return JSONObject().put("ok", false).put("error", "本机没有待查询订单")
                    val order = pending.optJSONObject("order") ?: return JSONObject().put("ok", false).put("error", "上次下单结果未确认，请选择原套餐重试")
                    val result = signed(action, JSONObject().put("sessionToken", saved.getString("sessionToken"))
                        .put("orderId", order.getString("id"))).body
                    pending.put("order", result.getJSONObject("order")); persist()
                    if (result.getJSONObject("order").optBoolean("membershipApplied")) check(force = true)
                    JSONObject().put("ok", true).put("order", result.getJSONObject("order"))
                }
                "payment-open" -> {
                    val pending = saved.optJSONObject("paymentOrder") ?: error("没有支付订单")
                    if (pending.optString("channel", "web") == "app") {
                        context.startActivity(Intent(context, AlipayPaymentActivity::class.java)
                            .putExtra("orderId", pending.getJSONObject("order").getString("id"))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        return JSONObject().put("ok", true)
                    }
                    val target = Uri.parse(pending.getString("checkoutUrl"))
                    val base = Uri.parse(BuildConfig.CLOUD_SHARED_DATA_URL)
                    require(target.scheme == "https" && target.host == base.host && target.port == base.port &&
                        target.userInfo == null && target.path == "/pay/start" &&
                        target.getQueryParameter("order") == pending.getJSONObject("order").getString("id"))
                    // Only the server-issued checkout link leaves the app. No member
                    // session, password or arbitrary WebView URL reaches the browser.
                    context.startActivity(Intent(Intent.ACTION_VIEW, target).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    JSONObject().put("ok", true)
                }
                "send-code" -> exchange("POST", "/v1/member/send-code", JSONObject()
                    .put("email", body.optString("email").trim().lowercase()).put("purpose", body.optString("purpose"))
                    .put("requestId", body.optString("requestId").ifBlank { UUID.randomUUID().toString() }))
                "register", "reset-password" -> signed(action, JSONObject()
                    .put("email", body.optString("email").trim().lowercase()).put("password", body.optString("password"))
                    .put("challengeId", body.optString("challengeId")).put("code", body.optString("code"))).body.also {
                        if (action == "reset-password") {
                            saved.remove("sessionToken"); leaseDeadlineElapsed = 0; code = "MEMBER_LOGIN_REQUIRED"
                            message = "密码已重置，请使用新密码登录"; persist()
                        }
                    }
                "login" -> {
                    leaseDeadlineElapsed = 0
                    val result = signed("login", JSONObject().put("email", body.optString("email").trim().lowercase())
                        .put("password", body.optString("password")).put("deviceName", "${Build.MANUFACTURER} ${Build.MODEL}"))
                    val previousMember = saved.optJSONObject("member")?.optString("id")
                    accept(result)
                    if (previousMember != result.body.getJSONObject("member").getString("id")) { saved.remove("paymentOrder"); persist() }
                    status()
                }
                else -> JSONObject().put("ok", false).put("code", "NOT_FOUND").put("error", "会员操作不存在")
            }
        } catch (failure: MemberFailure) {
            JSONObject().put("ok", false).put("code", failure.code).put("error", failure.message)
        } catch (failure: IllegalArgumentException) {
            JSONObject().put("ok", false).put("code", "PAYMENT_INVALID_STATE").put("error", failure.message ?: "请先查询原订单")
        } catch (_: Exception) {
            JSONObject().put("ok", false).put("code", "MEMBER_NETWORK_UNAVAILABLE").put("error", "会员服务连接失败，请稍后重试")
        }
    }

    /** Called only by the non-exported native payment screen, never by WebView. */
    @Synchronized fun nativePaymentOrder(expectedId: String): JSONObject {
        val pending = saved.optJSONObject("paymentOrder") ?: error("没有支付订单")
        require(pending.getJSONObject("order").getString("id") == expectedId) { "当前订单已变化，请返回会员页" }
        require(pending.optString("channel") == "app") { "请使用原订单支付入口" }
        val result = signed("payment-app-order", JSONObject().put("sessionToken", saved.getString("sessionToken"))
            .put("orderId", expectedId)).body
        require(result.getJSONObject("order").getString("id") == expectedId)
        require(result.optString("mode") in setOf("sandbox", "production"))
        require(BuildConfig.DEBUG || result.getString("mode") == "production") { "正式APK不接受沙箱订单" }
        return result
    }

    @Synchronized fun refreshPayment(expectedId: String): JSONObject {
        require(saved.optJSONObject("paymentOrder")?.optJSONObject("order")?.optString("id") == expectedId) { "当前账号或订单已变化" }
        return handle("payment-status", JSONObject())
    }

    private data class SignedResult(val body: JSONObject, val requestId: String, val elapsed: Long)
    private fun signed(action: String, data: JSONObject, extra: JSONObject? = null,
        maxResponseChars: Int = DEFAULT_RESPONSE_CHARS): SignedResult {
        if (serverBaseMillis == 0L) exchange("GET", "/v1/member/info", null)
        val started = SystemClock.elapsedRealtime()
        val nonce = UUID.randomUUID().toString()
        val payload = JSONObject(data.toString()).put("requestId", nonce)
            .put("timestamp", serverBaseMillis + (started - serverBaseElapsed)).toString()
        val path = "/v1/member/$action"
        val store = ensureDeviceKey()
        val signer = Signature.getInstance("SHA256withRSA")
        signer.initSign(store.getKey(DEVICE_KEY, null) as PrivateKey)
        signer.update("DWPM-MEMBER-V1\n$path\n$payload".toByteArray(Charsets.UTF_8))
        val request = JSONObject().put("payload", payload)
            .put("publicKey", Base64.encodeToString(store.getCertificate(DEVICE_KEY).publicKey.encoded, Base64.NO_WRAP))
            .put("signature", Base64.encodeToString(signer.sign(), Base64.NO_WRAP))
        extra?.keys()?.forEach { key -> request.put(key, extra.get(key)) }
        val result = exchange("POST", path, request, maxResponseChars)
        return SignedResult(result, nonce, SystemClock.elapsedRealtime() - started)
    }

    private fun exchange(method: String, path: String, payload: JSONObject?,
        maxResponseChars: Int = DEFAULT_RESPONSE_CHARS): JSONObject {
        val base = BuildConfig.CLOUD_SHARED_DATA_URL.trim().trimEnd('/')
        require(URL(base).protocol == "https") { "会员服务只允许HTTPS" }
        val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method; connectTimeout = 5_000; readTimeout = 12_000; instanceFollowRedirects = false
            setRequestProperty("Content-Type", "application/json; charset=utf-8"); setRequestProperty("Accept", "application/json")
        }
        return try {
            if (payload != null) {
                val bytes = payload.toString().toByteArray(Charsets.UTF_8)
                connection.doOutput = true; connection.setFixedLengthStreamingMode(bytes.size)
                connection.outputStream.use { it.write(bytes) }
            }
            val status = connection.responseCode
            val raw = (if (status in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            require(raw.length <= maxResponseChars) { "会员响应过大" }
            val value = JSONObject(raw)
            val serverTime = value.optLong("serverTimeMillis")
            if (serverTime > 0) { serverBaseMillis = serverTime; serverBaseElapsed = SystemClock.elapsedRealtime() }
            if (status !in 200..299 || !value.optBoolean("ok")) {
                if (status >= 500) throw java.io.IOException("membership service unavailable")
                throw MemberFailure(value.optString("code", "MEMBER_ERROR"), value.optString("error", "会员操作失败"), value)
            }
            value
        } finally { connection.disconnect() }
    }

    private fun accept(result: SignedResult) {
        val response = result.body
        val member = response.getJSONObject("member")
        val token = response.getString("sessionToken")
        val sessionId = response.getString("sessionId")
        var remaining = 0L
        val lease = response.optString("lease").takeUnless { it == "null" || it.isBlank() }
        if (lease != null) {
            val parts = lease.split('.')
            require(parts.size == 2) { "会员授权格式无效" }
            remaining = MembershipLeaseVerifier.verify(
                Base64.decode(BuildConfig.MEMBER_LEASE_PUBLIC_KEY, Base64.DEFAULT), parts[0],
                Base64.decode(parts[0], Base64.URL_SAFE or Base64.NO_WRAP), Base64.decode(parts[1], Base64.URL_SAFE or Base64.NO_WRAP),
                member.getString("id"), sessionId, deviceId(), result.requestId, response.getLong("serverTimeMillis"), result.elapsed
            )
        }
        saved.put("sessionToken", token).put("member", member).put("sessionId", sessionId).put("lease", lease)
            .put("cloudToken", response.optString("cloudToken"))
        saved.remove("pauseCode"); saved.remove("pauseMessage"); saved.remove("pauseDetails")
        leaseDeadlineElapsed = if (remaining > 0) SystemClock.elapsedRealtime() + remaining else 0
        nextRetryElapsed = 0; lastDetails = JSONObject()
        code = if (remaining > 0) "MEMBER_ACTIVE" else "MEMBER_EXPIRED"
        message = if (remaining > 0) "会员授权有效" else "会员未开通或已到期，请联系管理员开通/续期"
        if (remaining > 0) { lastNotice = ""; saved.remove("lastNotice") } else notifyPaused()
        persist()
    }

    private fun deny(reason: String, text: String, details: JSONObject) {
        leaseDeadlineElapsed = 0; code = reason; message = text
        lastDetails = JSONObject().put("otherLoginAtMillis", details.optLong("otherLoginAtMillis"))
            .put("otherDeviceName", details.optString("otherDeviceName"))
            .put("sameDevice", details.optBoolean("sameDevice"))
        nextRetryElapsed = SystemClock.elapsedRealtime() + 60_000L
        saved.put("pauseCode", code).put("pauseMessage", message).put("pauseDetails", lastDetails)
        notifyPaused(); persist()
    }
    private fun notifyPaused() {
        val key = "$code:${lastDetails.optLong("otherLoginAtMillis")}:${saved.optString("sessionId")}"
        if (key == lastNotice) return
        lastNotice = key; saved.put("lastNotice", key)
        runCatching {
            val manager = context.getSystemService(NotificationManager::class.java)
            val channel = "membership_authorization"
            if (Build.VERSION.SDK_INT >= 26) manager.createNotificationChannel(NotificationChannel(channel, "会员授权提醒", NotificationManager.IMPORTANCE_HIGH))
            val intent = PendingIntent.getActivity(context, 7109, Intent(context, AssistantWebActivity::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val builder = if (Build.VERSION.SDK_INT >= 26) android.app.Notification.Builder(context, channel) else android.app.Notification.Builder(context)
            manager.notify(7109, builder.setSmallIcon(android.R.drawable.ic_dialog_alert).setContentTitle("会员授权已暂停")
                .setContentText(message).setStyle(android.app.Notification.BigTextStyle().bigText("$message。游戏账号、设置和记录已保留。"))
                .setContentIntent(intent).setAutoCancel(true).build())
        }
    }
    private class MemberFailure(val code: String, message: String, val details: JSONObject) : RuntimeException(message)
    companion object {
        private const val DEVICE_KEY = "dwpm_member_device_rsa_v1"
        private const val DEFAULT_RESPONSE_CHARS = 65_536
        // A 512 KB export can double in size once JSON-escaped inside the response.
        private const val CONFIG_BACKUP_RESPONSE_CHARS = 2 * 1024 * 1024
        private val TERMINAL_CODES = setOf("MEMBER_SESSION_REPLACED", "MEMBER_SESSION_REVOKED", "MEMBER_PASSWORD_CHANGED",
            "MEMBER_DISABLED", "MEMBER_EXPIRED", "MEMBER_SESSION_INVALID", "MEMBER_SESSION_EXPIRED")
        @Volatile private var instance: MembershipClient? = null
        fun get(context: Context): MembershipClient = instance ?: synchronized(this) {
            instance ?: MembershipClient(context.applicationContext).also { instance = it }
        }
    }
}

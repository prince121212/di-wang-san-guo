package com.example.dwpmclone.host

import android.Manifest
import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import com.example.dwpmclone.AssistantWebActivity
import com.example.dwpmclone.data.local.KeystoreCredentialVault
import com.example.dwpmclone.data.local.KeystoreSessionSecretVault
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.LocalMapRepository
import com.example.dwpmclone.data.local.RequestHealthRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.service.AssistantForegroundService
import com.example.dwpmclone.ui.web.AssistantApiRequest
import com.example.dwpmclone.ui.web.AssistantApiResponse
import com.example.dwpmclone.ui.web.LocalProtocolOperationService
import java.util.ArrayDeque
import java.util.concurrent.atomic.AtomicInteger
import org.json.JSONArray
import org.json.JSONObject

/**
 * Narrow Android capability object called by Python through Chaquopy.
 *
 * It contains no opcode, task choice or success judgement. Passwords remain in
 * Android Keystore and are returned only for the explicit account reference the
 * shared core requests; event/log JSON is redacted again by TaskLogRepository.
 */
@Suppress("unused")
class AndroidSharedCorePortBridge(context: Context) {
    private val appContext = context.applicationContext
    private val credentials = KeystoreCredentialVault(appContext)
    private val sessionSecrets = KeystoreSessionSecretVault(appContext)
    private val logs = TaskLogRepository(appContext)
    private val sharedNetworkOperations by lazy {
        LocalProtocolOperationService(
            context = appContext,
            accounts = LocalAccountRepository(appContext),
            logs = logs,
            requestHealth = RequestHealthRepository(appContext),
            dailyStats = LocalDailySuccessStatsRepository(appContext),
            localMaps = LocalMapRepository(appContext)
        )
    }

    fun dataDirectory(): String = appContext.filesDir.absolutePath

    fun savePassword(accountRef: String, password: String) {
        accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?.let { credentials.savePassword(it, password) }
            ?: throw IllegalArgumentException("账号 ID 无效")
    }

    fun loadPassword(accountRef: String): String? =
        accountRef.trim().toLongOrNull()?.takeIf { it > 0L }?.let(credentials::loadPassword)

    fun deleteCredential(accountRef: String) {
        accountRef.trim().toLongOrNull()?.takeIf { it > 0L }?.let(credentials::delete)
    }

    fun saveSessionSecrets(accountRef: String, valuesJson: String) {
        val accountId = accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?: throw IllegalArgumentException("账号 ID 无效")
        val payload = JSONObject(valuesJson)
        val values = payload.keys().asSequence()
            .associateWith { key -> payload.optString(key) }
            .filterValues(String::isNotBlank)
        sessionSecrets.save(accountId, values)
    }

    fun loadSessionSecrets(accountRef: String): String {
        val accountId = accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?: return "{}"
        return JSONObject(sessionSecrets.load(accountId)).toString()
    }

    fun deleteSessionSecrets(accountRef: String) {
        accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?.let(sessionSecrets::delete)
    }

    fun networkAvailable(): Boolean {
        val manager = appContext.getSystemService(ConnectivityManager::class.java) ?: return false
        val network = manager.activeNetwork ?: return false
        val capabilities = manager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    fun executionOwnerActive(): Boolean = AssistantForegroundService.isExecutionOwnerActive()

    fun executeNetworkOperation(
        method: String,
        path: String,
        bodyJson: String,
        contextJson: String
    ): String {
        val normalizedMethod = method.uppercase()
        val normalizedPath = path.substringBefore('?')
        val body = runCatching { JSONObject(bodyJson) }.getOrDefault(JSONObject())
        val context = runCatching { JSONObject(contextJson) }.getOrDefault(JSONObject())
        if (normalizedMethod != "GET" || normalizedPath != "/api/military/intel") {
            return AssistantApiResponse(
                id = context.optString("requestId").ifBlank { "shared-network" },
                status = 404,
                body = JSONObject()
                    .put("ok", false)
                    .put("error", "Android 网络适配路由未开放：$normalizedMethod $normalizedPath")
            ).toJson().toString()
        }
        val accountId = sequenceOf(
            body.optString("accountRef"),
            body.optString("accountId"),
            body.optString("sessionId")
        ).firstOrNull { it.isNotBlank() && it.toLongOrNull()?.let { id -> id > 0L } == true }
            ?: return AssistantApiResponse(
                id = context.optString("requestId").ifBlank { "shared-network" },
                status = 400,
                body = JSONObject().put("ok", false).put("error", "共享网络 operation 缺少账号")
            ).toJson().toString()
        val request = AssistantApiRequest(
            id = context.optString("requestId").ifBlank { "shared-network-$accountId" },
            method = normalizedMethod,
            path = "$normalizedPath?sessionId=${java.net.URLEncoder.encode(accountId, "UTF-8")}",
            body = body
        )
        return sharedNetworkOperations.handleSharedCoreNetwork(request).toJson().toString()
    }

    fun writeLog(eventJson: String) {
        val event = runCatching { JSONObject(eventJson) }.getOrDefault(JSONObject())
        logs.append(
            event.optString("message").ifBlank { event.toString() },
            tag = "shared-core"
        )
    }

    fun publishEvent(eventJson: String) {
        SharedCoreEventBuffer.publish(eventJson)
    }

    fun notifyEvent(eventJson: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            appContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            writeLog(JSONObject().put("message", "共享核心通知未展示：未授予通知权限").toString())
            return
        }
        val event = runCatching { JSONObject(eventJson) }.getOrDefault(JSONObject())
        val manager = appContext.getSystemService(NotificationManager::class.java) ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    NOTIFICATION_CHANNEL_ID,
                    "共享核心任务通知",
                    NotificationManager.IMPORTANCE_DEFAULT
                )
            )
        }
        val launch = PendingIntent.getActivity(
            appContext,
            0,
            Intent(appContext, AssistantWebActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or immutableFlag()
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(appContext, NOTIFICATION_CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(appContext)
        }
        val title = event.optString("title").ifBlank { "帝王三国辅助" }
        val message = event.optString("message")
            .ifBlank { event.optString("text") }
            .ifBlank { "共享核心任务状态已更新" }
        manager.notify(
            notificationIds.incrementAndGet(),
            builder
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(Notification.BigTextStyle().bigText(message))
                .setContentIntent(launch)
                .setAutoCancel(true)
                .build()
        )
    }

    fun scheduleWake(accountRef: String, wakeAtMillis: Long) {
        val manager = appContext.getSystemService(AlarmManager::class.java) ?: return
        val triggerAt = maxOf(System.currentTimeMillis(), wakeAtMillis)
        val pending = wakePendingIntent(accountRef)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pending)
        } else {
            manager.set(AlarmManager.RTC_WAKEUP, triggerAt, pending)
        }
    }

    fun cancelWake(accountRef: String) {
        appContext.getSystemService(AlarmManager::class.java)
            ?.cancel(wakePendingIntent(accountRef))
    }

    fun eventsSnapshot(): String = SharedCoreEventBuffer.snapshot().toString()

    private fun wakePendingIntent(accountRef: String): PendingIntent = PendingIntent.getService(
        appContext,
        accountRef.hashCode(),
        Intent(appContext, AssistantForegroundService::class.java)
            .setAction(AssistantForegroundService.ACTION_SCHEDULED_TICK)
            .putExtra("sharedCoreAccountRef", accountRef),
        PendingIntent.FLAG_UPDATE_CURRENT or immutableFlag()
    )

    private fun immutableFlag(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0

    private companion object {
        const val NOTIFICATION_CHANNEL_ID = "shared_python_core_events"
        val notificationIds = AtomicInteger(30_000)
    }
}

internal object SharedCoreEventBuffer {
    private const val MAX_EVENTS = 200
    private val lock = Any()
    private val events = ArrayDeque<JSONObject>()

    fun publish(eventJson: String) = synchronized(lock) {
        val event = runCatching { JSONObject(eventJson) }.getOrElse {
            JSONObject().put("type", "invalid-event").put("raw", eventJson.take(2_000))
        }
        events.addLast(event)
        while (events.size > MAX_EVENTS) events.removeFirst()
    }

    fun snapshot(): JSONArray = synchronized(lock) {
        JSONArray().also { output -> events.forEach(output::put) }
    }
}

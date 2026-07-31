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
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.service.AssistantForegroundService
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
    private val logs = TaskLogRepository(appContext)

    fun dataDirectory(): String = appContext.filesDir.absolutePath

    fun loadPassword(accountRef: String): String? =
        accountRef.trim().toLongOrNull()?.takeIf { it > 0L }?.let(credentials::loadPassword)

    fun deleteCredential(accountRef: String) {
        accountRef.trim().toLongOrNull()?.takeIf { it > 0L }?.let(credentials::delete)
    }

    fun networkAvailable(): Boolean {
        val manager = appContext.getSystemService(ConnectivityManager::class.java) ?: return false
        val network = manager.activeNetwork ?: return false
        val capabilities = manager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
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

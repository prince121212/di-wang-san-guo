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
import android.os.SystemClock
import com.example.dwpmclone.AssistantWebActivity
import com.example.dwpmclone.BuildConfig
import com.example.dwpmclone.data.local.KeystoreCredentialVault
import com.example.dwpmclone.data.local.KeystoreSessionSecretVault
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.LocalMapRepository
import com.example.dwpmclone.data.local.LogAudiencePolicy
import com.example.dwpmclone.data.local.RequestHealthRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.domain.localmap.LocalMapKind
import com.example.dwpmclone.domain.localmap.LocalMapQueryKey
import com.example.dwpmclone.domain.localmap.LocalMapSnapshot
import com.example.dwpmclone.domain.localmap.LocalMapTargetRecord
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.state.AccountOperationLockRegistry
import com.example.dwpmclone.service.AssistantForegroundService
import java.util.ArrayDeque
import java.io.IOException
import java.util.concurrent.ThreadLocalRandom
import java.util.concurrent.atomic.AtomicLong
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
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
    // SharedPythonCoreHost constructs this bridge before publishing its singleton.
    // Resolving LocalAccountRepository eagerly would call SharedPythonCoreHost.get()
    // again from inside that constructor and recurse. Defer it until the core is live.
    private val accounts by lazy { LocalAccountRepository(appContext) }
    private val mapSnapshots = LocalMapRepository(appContext)
    private val dailyCompletions = LocalDailySuccessStatsRepository(appContext)
    private val requestHealth = RequestHealthRepository(appContext)

    fun dataDirectory(): String = appContext.filesDir.absolutePath

    fun checkMembership(force: Boolean): String = MembershipClient.get(appContext).check(force).toString()

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

    fun cloudSharedDataConfigured(): Boolean {
        val rawUrl = BuildConfig.CLOUD_SHARED_DATA_URL.trim()
        if (rawUrl.isBlank()) return false
        return runCatching {
            val url = URL(rawUrl)
            url.host.isNotBlank() && (
                url.protocol == "https" ||
                    (BuildConfig.DEBUG && url.protocol == "http" &&
                        url.host in setOf("127.0.0.1", "localhost", "::1"))
                )
        }.getOrDefault(false)
    }

    /** Fixed-path JSON transport; endpoint and runtime token never enter Python. */
    fun executeCloudRequest(requestJson: String): String {
        check(cloudSharedDataConfigured()) { "共享云端数据未配置" }
        val request = JSONObject(requestJson)
        val method = request.optString("method", "POST").uppercase()
        require(method == "GET" || method == "POST") { "共享云端数据仅支持 GET/POST" }
        val path = request.optString("path").trim()
        require(path in CLOUD_SHARED_DATA_PATHS) { "共享云端数据接口路径无效" }
        val dataToken = if (path == "/v1/client/config") "" else MembershipClient.get(appContext).cloudDataToken()
        check(path == "/v1/client/config" || dataToken.isNotBlank()) { "会员数据授权不可用" }
        val baseUrl = BuildConfig.CLOUD_SHARED_DATA_URL.trim().trimEnd('/')
        val url = URL(baseUrl + path)
        val encoded = (request.optJSONObject("body") ?: JSONObject())
            .toString()
            .toByteArray(Charsets.UTF_8)
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 5_000
            readTimeout = 8_000
            if (dataToken.isNotBlank()) setRequestProperty("Authorization", "Bearer $dataToken")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("User-Agent", "DWPM-Cloud-Shared-Data/1.0")
            if (method == "POST") {
                doOutput = true
                setFixedLengthStreamingMode(encoded.size)
            }
        }
        return try {
            if (method == "POST") connection.outputStream.use { it.write(encoded) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val responseText = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val responseBody = runCatching { JSONObject(responseText.ifBlank { "{}" }) }
                .getOrElse { throw IllegalStateException("共享云端数据返回了无效 JSON", it) }
            JSONObject().put("status", status).put("body", responseBody).toString()
        } finally {
            connection.disconnect()
        }
    }

    /** Byte-only HTTP transport. Python owns every URL field, opcode and parser. */
    fun executeRawHttp(requestJson: String): String {
        val request = JSONObject(requestJson)
        if (request.optBoolean("requireExecutionOwner", false) &&
            !AssistantForegroundService.isExecutionOwnerActive()
        ) {
            throw IllegalStateException("手机后台执行权已撤销，未发送游戏请求")
        }
        val method = request.optString("method", "GET").uppercase()
        require(method == "GET" || method == "POST") { "共享 HTTP 传输仅支持 GET/POST" }
        val rawUrl = request.optString("url").trim()
        require(rawUrl.isNotEmpty()) { "共享 HTTP 传输缺少 URL" }
        val query = request.optJSONObject("query")
        val queryString = query?.keys()?.asSequence()?.toList()?.sorted()?.joinToString("&") { key ->
            "${URLEncoder.encode(key, "UTF-8")}=" +
                URLEncoder.encode(query.optString(key), "UTF-8")
        }.orEmpty()
        val finalUrl = rawUrl + when {
            queryString.isEmpty() -> ""
            rawUrl.contains('?') -> "&$queryString"
            else -> "?$queryString"
        }
        val url = URL(finalUrl)
        require(url.protocol == "https" || url.protocol == "http") {
            "共享 HTTP 传输拒绝非 HTTP(S) URL"
        }
        require(url.host.isNotBlank()) { "共享 HTTP 传输 URL 主机无效" }
        val bodyHex = request.optString("bodyHex")
        require(bodyHex.length % 2 == 0 && bodyHex.all { it.isDigit() || it.lowercaseChar() in 'a'..'f' }) {
            "共享 HTTP 传输 bodyHex 无效"
        }
        val body = ByteArray(bodyHex.length / 2) { index ->
            bodyHex.substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
        val connectTimeoutMillis = request.optInt("connectTimeoutMillis", 15_000)
            .coerceIn(1_000, 60_000)
        val readTimeoutMillis = request.optInt("readTimeoutMillis", 25_000)
            .coerceIn(1_000, 120_000)
        val readOnly = request.optBoolean("readOnly", false)
        val maximumAttempts = if (readOnly) {
            request.optInt("transportMaxAttempts", 1).coerceIn(1, 3)
        } else {
            1
        }
        val paceBeforeMillis = if (readOnly) {
            request.optLong("transportPaceBeforeMillis", 0L).coerceIn(0L, 5_000L)
        } else {
            0L
        }
        val paceJitterMillis = if (readOnly) {
            request.optLong("transportPaceJitterMillis", 0L).coerceIn(0L, 5_000L)
        } else {
            0L
        }
        val retryBaseDelayMillis = if (readOnly) {
            request.optLong("transportRetryBaseDelayMillis", 0L).coerceIn(0L, 10_000L)
        } else {
            0L
        }
        val retryJitterMillis = if (readOnly) {
            request.optLong("transportRetryJitterMillis", 0L).coerceIn(0L, 5_000L)
        } else {
            0L
        }
        val headers = request.optJSONObject("headers")

        fun openConnection(): HttpURLConnection =
            (url.openConnection() as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = connectTimeoutMillis
                readTimeout = readTimeoutMillis
                headers?.keys()?.asSequence()?.forEach { key ->
                    setRequestProperty(key, headers.optString(key))
                }
                if (method == "POST") {
                    doOutput = true
                    setFixedLengthStreamingMode(body.size)
                }
            }

        fun jitter(maximumMillis: Long): Long =
            if (maximumMillis <= 0L) 0L
            else ThreadLocalRandom.current().nextLong(maximumMillis + 1L)

        fun ensureExecutionOwner() {
            if (request.optBoolean("requireExecutionOwner", false) &&
                !AssistantForegroundService.isExecutionOwnerActive()
            ) {
                throw IllegalStateException("手机后台执行权已撤销，未发送游戏请求")
            }
        }
        val accountId = request.optString("accountRef").trim().toLongOrNull()
            ?.takeIf { it > 0L }
        val purpose = request.optString("phase")
            .trim()
            .take(160)
            .ifBlank { "shared-raw-http" }
        ensureExecutionOwner()
        if (paceBeforeMillis > 0L || paceJitterMillis > 0L) {
            SystemClock.sleep(paceBeforeMillis + jitter(paceJitterMillis))
            ensureExecutionOwner()
        }
        var lastTransportError: Throwable? = null
        for (attempt in 1..maximumAttempts) {
            if (attempt > 1) {
                val retryDelay = retryBaseDelayMillis * (attempt - 1L) +
                    jitter(retryJitterMillis)
                if (retryDelay > 0L) SystemClock.sleep(retryDelay)
                ensureExecutionOwner()
            }
            val connection = openConnection()
            try {
                if (method == "POST") connection.outputStream.use { it.write(body) }
                val status = connection.responseCode
                val stream = if (status in 200..299) {
                    connection.inputStream
                } else {
                    connection.errorStream
                }
                val responseBody = stream?.use { it.readBytes() } ?: ByteArray(0)
                val succeeded = status in 200..299
                accountId?.let {
                    requestHealth.record(it, succeeded, purpose, System.currentTimeMillis())
                }
                if (
                    readOnly && attempt < maximumAttempts &&
                    status in RETRYABLE_READ_ONLY_HTTP_STATUSES
                ) {
                    continue
                }
                return JSONObject()
                    .put("status", status)
                    .put("bodyHex", responseBody.joinToString("") { byte ->
                        "%02x".format(byte.toInt() and 0xff)
                    })
                    .toString()
            } catch (error: Throwable) {
                accountId?.let {
                    requestHealth.record(it, false, purpose, System.currentTimeMillis())
                }
                lastTransportError = error
                if (!readOnly || attempt >= maximumAttempts || error !is IOException) {
                    throw error
                }
            } finally {
                connection.disconnect()
            }
        }
        throw lastTransportError ?: IllegalStateException("只读游戏请求重试结束但没有返回结果")
    }

    /** Android needs no duplicate account mirror: the shared ledger is authoritative. */
    fun commitAccountRuntime(
        previousAccountRef: String,
        accountRef: String,
        runtimeJson: String,
        mode: String
    ) {
        require(accountRef.toLongOrNull()?.let { it > 0L } == true) { "共享登录返回账号无效" }
        // Parse once so a malformed Python/JVM boundary fails before hosting starts.
        JSONObject(runtimeJson)
        require(mode == "add" || mode == "start") { "共享登录模式无效" }
        if (previousAccountRef != accountRef) {
            logs.append("共享登录已将账号引用 $previousAccountRef 更新为 $accountRef", "account", accountRef.toLong())
        }
    }

    fun startAccountHosting(accountRef: String) {
        require(accountRef.toLongOrNull()?.let { it > 0L } == true) { "共享托管账号无效" }
        AssistantForegroundService.start(appContext)
    }

    /**
     * Runtime ownership is process/service state, never a persisted account flag.
     *
     * The Android foreground service owns every enabled account in this process;
     * when its execution gate is closed, no account is currently hosted even if
     * an older APK left `enabled=true` in the durable ledger.
     */
    fun isAccountHosting(accountRef: String): Boolean {
        require(accountRef.toLongOrNull()?.let { it > 0L } == true) { "共享托管账号无效" }
        return AssistantForegroundService.isExecutionOwnerActive()
    }

    /** Two-phase mutation gate: Python persists requestSent only after this lock succeeds. */
    fun tryAcquireNetworkOperation(accountRef: String): Boolean =
        accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?.let(AccountOperationLockRegistry::tryAcquire)
            ?: false

    fun releaseNetworkOperation(accountRef: String) {
        val accountId = accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?: throw IllegalArgumentException("账号 ID 无效")
        AccountOperationLockRegistry.release(accountId)
    }

    fun writeLog(eventJson: String) {
        val event = runCatching { JSONObject(eventJson) }.getOrDefault(JSONObject())
        val accountId = event.optString("accountRef").toLongOrNull()
        val message = event.optString("message")
        val audience = LogAudiencePolicy.forCoreEvent(message, event.optString("audience"))
        logs.append(
            message.ifBlank { event.toString() },
            tag = if (event.optString("event") == "alarm") "alarm" else "shared-core",
            accountId = accountId,
            audience = audience,
        )
    }

    fun publishEvent(eventJson: String) {
        SharedCoreEventBuffer.publish(eventJson)
    }

    fun dailyCompletionCount(
        accountRef: String,
        key: String,
        nowMillis: Long
    ): Int {
        val accountId = accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?: throw IllegalArgumentException("每日完成状态账号无效")
        val normalizedKey = key.trim().take(80)
        require(normalizedKey.isNotBlank()) { "每日完成状态 key 为空" }
        require(nowMillis > 0L) { "每日完成状态时间无效" }
        return dailyCompletions.count(accountId, normalizedKey, nowMillis)
    }

    fun addDailyCompletion(
        accountRef: String,
        key: String,
        count: Int,
        nowMillis: Long
    ): Int {
        val accountId = accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?: throw IllegalArgumentException("每日完成状态账号无效")
        val normalizedKey = key.trim().take(80)
        require(normalizedKey.isNotBlank()) { "每日完成状态 key 为空" }
        require(count > 0) { "每日完成状态增量必须大于 0" }
        require(nowMillis > 0L) { "每日完成状态时间无效" }
        return dailyCompletions.add(accountId, normalizedKey, count, nowMillis)
    }

    /**
     * Resolve the exact storage identity a snapshot is written under.
     *
     * A read must reproduce this byte for byte, server-id fallback chain
     * included: a loader that resolves a different server id silently misses
     * every cached target, and the account rescans the same map forever.
     */
    private fun mapSnapshotKey(
        accountRef: String,
        kindName: String,
        fingerprint: String,
    ): LocalMapQueryKey {
        val accountId = accountRef.trim().toLongOrNull()?.takeIf { it > 0L }
            ?: throw IllegalArgumentException("地图快照账号无效")
        val account = accounts.get(accountId)
            ?: throw IllegalArgumentException("地图快照账号不存在")
        val serverId = account.serverId
            ?: account.session?.channelExtra?.get("serverKey")
            ?: account.session?.channelExtra?.get("serverId")
            ?: account.serverName.takeIf(String::isNotBlank)
            ?: "account:$accountId"
        val kind = runCatching {
            LocalMapKind.valueOf(kindName.trim().uppercase())
        }.getOrElse { throw IllegalArgumentException("地图快照类型无效") }
        val normalized = fingerprint.trim().take(500)
        require(normalized.isNotBlank()) { "地图快照指纹为空" }
        return LocalMapQueryKey(accountId, serverId, kind, normalized)
    }

    /** Returns the stored snapshot as JSON, or "{}" when nothing is cached. */
    fun loadMapSnapshot(
        accountRef: String,
        kindName: String,
        fingerprint: String,
    ): String {
        val key = runCatching {
            mapSnapshotKey(accountRef, kindName, fingerprint)
        }.getOrElse { return "{}" }
        // Shared across accounts on purpose: where a bandit stands is a fact
        // about the server, not about who happened to scan it first.
        val snapshot = mapSnapshots.readShared(key) ?: return "{}"
        val targets = JSONArray()
        // Only live records: a target the game already reported gone is not a
        // candidate, and shipping it wastes a whole dispatch attempt.
        snapshot.targets.filter { it.active }.forEach { record ->
            val fields = JSONObject()
            record.filterFields.forEach { (name, value) -> fields.put(name, value) }
            targets.put(
                JSONObject()
                    .put("targetId", record.targetId)
                    .put("x", record.coordinate.x)
                    .put("y", record.coordinate.y)
                    .put("type", record.type)
                    .put("level", record.level ?: JSONObject.NULL)
                    .put("filterFields", fields)
                    .put("firstDiscoveredAtMillis", record.firstDiscoveredAtMillis)
            )
        }
        return JSONObject()
            .put("accountRef", accountRef)
            .put("kind", key.kind.name)
            .put("fingerprint", key.fingerprint)
            .put("scannedAtMillis", snapshot.scannedAtMillis)
            .put("targets", targets)
            .toString()
    }

    /** Persists only normalized observations; Python owns scan/filter/cache-key decisions. */
    fun saveMapSnapshot(snapshotJson: String) {
        val root = JSONObject(snapshotJson)
        val accountId = root.optString("accountRef").toLongOrNull()?.takeIf { it > 0L }
            ?: throw IllegalArgumentException("地图快照账号无效")
        val account = accounts.get(accountId)
            ?: throw IllegalArgumentException("地图快照账号不存在")
        val serverId = root.optString("serverId").trim().ifBlank {
            account.serverId
                ?: account.session?.channelExtra?.get("serverKey")
                ?: account.session?.channelExtra?.get("serverId")
                ?: account.serverName.takeIf(String::isNotBlank)
                ?: "account:$accountId"
        }
        val kind = runCatching {
            LocalMapKind.valueOf(root.getString("kind").trim().uppercase())
        }.getOrElse { throw IllegalArgumentException("地图快照类型无效") }
        val fingerprint = root.getString("fingerprint").trim().take(500)
        require(fingerprint.isNotBlank()) { "地图快照指纹为空" }
        val scannedAt = root.getLong("scannedAtMillis").takeIf { it > 0L }
            ?: throw IllegalArgumentException("地图快照时间无效")
        val rows = root.optJSONArray("targets") ?: JSONArray()
        val targets = (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index)
            val targetId = row.getLong("targetId").takeIf { it > 0L }
                ?: throw IllegalArgumentException("第${index + 1}个地图目标 ID 无效")
            val fields = row.optJSONObject("filterFields") ?: JSONObject()
            val normalizedFields = linkedMapOf<String, String>()
            fields.keys().forEach { key ->
                if (normalizedFields.size >= 48) return@forEach
                val normalizedKey = key.trim().take(64)
                val lower = normalizedKey.lowercase()
                if (
                    normalizedKey.isBlank() ||
                    lower.contains("password") || lower.contains("token") ||
                    lower.contains("session") || lower.contains("payload") ||
                    lower == "rawrecord" || lower == "tailhex"
                ) return@forEach
                val value = fields.opt(key)
                if (value == null || value == JSONObject.NULL) return@forEach
                normalizedFields[normalizedKey] = value.toString().trim().take(256)
            }
            LocalMapTargetRecord(
                targetId = targetId,
                coordinate = MapCoordinate(row.getInt("x"), row.getInt("y")),
                type = row.getString("type").trim().take(120),
                level = row.optInt("level").takeIf { row.has("level") && !row.isNull("level") },
                filterFields = normalizedFields,
                firstDiscoveredAtMillis = row.optLong("firstDiscoveredAtMillis", scannedAt),
                lastValidatedAtMillis = scannedAt
            )
        }
        mapSnapshots.replace(
            LocalMapSnapshot(
                query = LocalMapQueryKey(accountId, serverId, kind, fingerprint),
                scannedAtMillis = scannedAt,
                targets = targets
            )
        )
    }

    fun invalidateMapTarget(
        accountRef: String,
        kindName: String,
        targetId: Long,
        reason: String,
        invalidatedAtMillis: Long
    ) {
        val accountId = accountRef.toLongOrNull()?.takeIf { it > 0L }
            ?: throw IllegalArgumentException("地图失效账号无效")
        val account = accounts.get(accountId)
            ?: throw IllegalArgumentException("地图失效账号不存在")
        val serverId = account.serverId
            ?: account.session?.channelExtra?.get("serverKey")
            ?: account.session?.channelExtra?.get("serverId")
            ?: account.serverName.takeIf(String::isNotBlank)
            ?: "account:$accountId"
        val kind = runCatching { LocalMapKind.valueOf(kindName.trim().uppercase()) }
            .getOrElse { throw IllegalArgumentException("地图失效类型无效") }
        require(targetId > 0L) { "地图失效目标 ID 无效" }
        mapSnapshots.invalidateAcrossKind(
            accountId,
            serverId,
            kind,
            targetId,
            invalidatedAtMillis,
            reason
        )
    }

    fun notifyEvent(eventJson: String) {
        val event = runCatching { JSONObject(eventJson) }.getOrDefault(JSONObject())
        if (!event.optBoolean("showNotification", false)) return
        if (Build.VERSION.SDK_INT >= 33 &&
            appContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            writeLog(
                JSONObject()
                    .put("message", "共享核心通知未展示：未授予通知权限")
                    .put("accountRef", event.optString("accountRef"))
                    .toString()
            )
            return
        }
        val manager = appContext.getSystemService(NotificationManager::class.java) ?: return
        val vibrate = event.optBoolean("vibrate", false)
        val channelId = if (vibrate) ALARM_ALERT_CHANNEL_ID else ALARM_NOTICE_CHANNEL_ID
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    channelId,
                    if (vibrate) "共享核心警报" else "共享核心军情",
                    if (vibrate) NotificationManager.IMPORTANCE_HIGH
                    else NotificationManager.IMPORTANCE_DEFAULT
                ).apply {
                    enableVibration(vibrate)
                    if (vibrate) vibrationPattern = ALARM_VIBRATION_PATTERN
                }
            )
        }
        val accountRef = event.optString("accountRef")
        val launch = PendingIntent.getActivity(
            appContext,
            accountRef.hashCode(),
            Intent(appContext, AssistantWebActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or immutableFlag()
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(appContext, channelId)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(appContext)
        }
        val title = event.optString("title").ifBlank { BuildConfig.APP_NAME }
        val message = event.optString("message")
            .ifBlank { event.optString("text") }
            .ifBlank { "共享核心任务状态已更新" }
        val notification = builder
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(Notification.BigTextStyle().bigText(message))
                .setContentIntent(launch)
                .setAutoCancel(true)
                .apply {
                    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
                        @Suppress("DEPRECATION")
                        setPriority(Notification.PRIORITY_HIGH)
                        if (vibrate) setVibrate(ALARM_VIBRATION_PATTERN)
                    }
                }
                .build()
        val fingerprint = event.optString("fingerprint").ifBlank {
            "${event.optString("type")}|$accountRef|$title|$message"
        }
        manager.notify(fingerprint.hashCode(), notification)
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
        val RETRYABLE_READ_ONLY_HTTP_STATUSES = setOf(502, 503, 504)
        val CLOUD_SHARED_DATA_PATHS = setOf(
            "/v1/presence/heartbeat",
            "/v1/client/config",
            "/v1/servers/catalog",
            "/v1/servers/directory/sync",
            "/v1/servers/directory/query",
            "/v1/maps/targets/query",
            "/v1/maps/targets/sync",
            "/v1/maps/targets/changes",
            "/v1/maps/scans/claim",
            "/v1/maps/scans/release",
            "/v1/maps/observations",
            "/v1/maps/targets/reserve",
            "/v1/maps/targets/status",
        )
        const val ALARM_ALERT_CHANNEL_ID = "shared_python_core_alarm_alert"
        const val ALARM_NOTICE_CHANNEL_ID = "shared_python_core_alarm_notice"
        val ALARM_VIBRATION_PATTERN = longArrayOf(0L, 250L, 180L, 350L)
    }
}

internal object SharedCoreEventBuffer {
    private const val MAX_EVENTS = 200
    private val lock = Any()
    private val events = ArrayDeque<JSONObject>()
    private val eventIds = AtomicLong(0L)
    private val listenerIds = AtomicLong(0L)
    private val listeners = linkedMapOf<Long, (String) -> Unit>()

    fun publish(eventJson: String) {
        val event = runCatching { JSONObject(eventJson) }.getOrElse {
            JSONObject().put("type", "invalid-event").put("raw", eventJson.take(2_000))
        }
        val callbacks = synchronized(lock) {
            // The Android host owns ordering. Never trust or reuse an ID supplied by a
            // producer because that could make page-side stale-event rejection ambiguous.
            event.put("eventId", eventIds.incrementAndGet())
            events.addLast(JSONObject(event.toString()))
            while (events.size > MAX_EVENTS) events.removeFirst()
            listeners.values.toList()
        }
        val encoded = event.toString()
        callbacks.forEach { listener -> runCatching { listener(encoded) } }
    }

    fun snapshot(): JSONArray = synchronized(lock) {
        JSONArray().also { output -> events.forEach(output::put) }
    }

    fun subscribe(listener: (String) -> Unit): Long = synchronized(lock) {
        listenerIds.incrementAndGet().also { listeners[it] = listener }
    }

    fun unsubscribe(subscriptionId: Long) = synchronized(lock) {
        listeners.remove(subscriptionId)
        Unit
    }
}

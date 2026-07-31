package com.example.dwpmclone.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.AlarmManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.os.UserManager
import com.example.dwpmclone.AssistantWebActivity
import com.example.dwpmclone.data.account.AccountLoginState
import com.example.dwpmclone.data.account.AccountSessionRecovery
import com.example.dwpmclone.data.account.LocalAccountLoginService
import com.example.dwpmclone.data.account.RealSessionHealthProbe
import com.example.dwpmclone.data.local.KeystoreCredentialVault
import com.example.dwpmclone.data.local.ExpeditionTransactionRepository
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.AssistantBehaviorContractAssetLoader
import com.example.dwpmclone.data.local.LocalConfigRepository
import com.example.dwpmclone.data.local.LocalHostingPreferences
import com.example.dwpmclone.data.local.LocalMapRepository
import com.example.dwpmclone.data.local.RequestHealthRepository
import com.example.dwpmclone.data.local.SessionReconnectRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.local.TaskRuntimeStatusRepository
import com.example.dwpmclone.data.protocol.GameRequestHealthSink
import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.data.protocol.RealGameProtocolClient
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.protocol.userFacingName
import com.example.dwpmclone.domain.model.AlarmNotificationEvent
import com.example.dwpmclone.domain.model.AlarmNotificationKind
import com.example.dwpmclone.domain.localmap.LocalTargetCache
import com.example.dwpmclone.domain.scheduler.SavedConfigTaskPlanFactory
import com.example.dwpmclone.domain.scheduler.HostingNotificationText
import com.example.dwpmclone.domain.scheduler.ResidentTaskActivationPolicy
import com.example.dwpmclone.domain.scheduler.SchedulerTickPolicy
import com.example.dwpmclone.domain.scheduler.SchedulerExecutionOwnershipPolicy
import com.example.dwpmclone.domain.scheduler.SelfLifecycleLogFormatter
import com.example.dwpmclone.domain.scheduler.SavedTaskPlan
import com.example.dwpmclone.domain.scheduler.LocalSchedulerLifecycleRunner
import com.example.dwpmclone.domain.scheduler.SuspendRunner
import com.example.dwpmclone.domain.scheduler.TaskRunReport
import com.example.dwpmclone.domain.scheduler.TaskScheduler
import com.example.dwpmclone.domain.scheduler.TaskStopReport
import com.example.dwpmclone.domain.scheduler.TaskRunSuppressionRegistry
import com.example.dwpmclone.domain.scheduler.TaskRuntimeStatusMapper
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import com.example.dwpmclone.domain.state.AutomationRuntimeStateStore
import com.example.dwpmclone.domain.state.AccountOperationLockRegistry
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.Executors

/**
 * Foreground host for persisted assistant task plans, network keepalive, task logs and alerts.
 * Every real mutation remains gated and audited by SessionAwareGameProtocolClient.
 */
class AssistantForegroundService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var logs: TaskLogRepository
    private lateinit var configs: LocalConfigRepository
    private lateinit var accounts: LocalAccountRepository
    private lateinit var scheduler: TaskScheduler
    private lateinit var lifecycleRunner: LocalSchedulerLifecycleRunner
    private lateinit var taskRuntimeStatuses: TaskRuntimeStatusRepository
    private lateinit var requestHealth: RequestHealthRepository
    private lateinit var hostingPreferences: LocalHostingPreferences
    private lateinit var sessionRecovery: AccountSessionRecovery
    private lateinit var behaviorContract: AssistantBehaviorContract
    private val taskSuppressions = TaskRunSuppressionRegistry()
    private val worker = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "assistant-scheduler").apply { isDaemon = true }
    }
    private var wakeLock: PowerManager.WakeLock? = null
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    @Volatile private var running = false
    @Volatile private var schedulerBusy = false
    @Volatile private var networkUsable = false
    @Volatile private var networkStateInitialized = false
    @Volatile private var activeNetworkId: String? = null
    @Volatile private var forceSessionValidation = true
    @Volatile private var waitingForFirstUnlock = false
    @Volatile private var immediateTickRequested = false
    private val networkGeneration = AtomicInteger(0)
    private val tickScheduleLock = Any()
    private var tickCount = 0
    private var taskSuppressionRestored = false
    private var scheduledTickAtElapsedMillis = Long.MAX_VALUE

    private val tickRunnable = object : Runnable {
        override fun run() {
            if (!running) return
            scheduledTickAtElapsedMillis = Long.MAX_VALUE
            tickCount += 1
            runLocalSchedulerTick(tickCount)
        }
    }

    override fun onCreate() {
        super.onCreate()
        logs = TaskLogRepository(this)
        configs = LocalConfigRepository(this)
        accounts = LocalAccountRepository(this)
        taskRuntimeStatuses = TaskRuntimeStatusRepository(this)
        hostingPreferences = LocalHostingPreferences(this)
        behaviorContract = AssistantBehaviorContractAssetLoader.load(this)
        val serviceExecutionAllowed = { executionAllowedForCurrentAccount() }
        val serviceReadOnlyProtocol = RealGameProtocolClient(
            executionAllowed = serviceExecutionAllowed
        )
        sessionRecovery = AccountSessionRecovery(
            accounts = accounts,
            loginService = LocalAccountLoginService(
                accounts = accounts,
                credentials = KeystoreCredentialVault(this),
                logs = logs,
                protocol = serviceReadOnlyProtocol
            ),
            reconnects = SessionReconnectRepository(this),
            logs = logs,
            probe = RealSessionHealthProbe(serviceReadOnlyProtocol),
            heartbeatIntervalMillis = behaviorContract.accountLifecycle.heartbeatIntervalMillis
        )
        // 后台是绝大多数真实游戏请求的来源，这里也安装一次采集入口，
        // 保证开机自启（未打开界面）时账号卡的健康点依然有数据。
        requestHealth = RequestHealthRepository(this)
        GameRequestHealthSink.writer = { accountId, success, purpose, timeMillis ->
            requestHealth.record(accountId, success, purpose, timeMillis)
        }
        val dailyStats = LocalDailySuccessStatsRepository(this)
        scheduler = TaskScheduler(
            SessionAwareGameProtocolClient(
                behaviorContract = behaviorContract,
                expeditionTransactionStore = ExpeditionTransactionRepository(this),
                actionAudit = { message ->
                    logs.append(
                        message,
                        tag = "real-action",
                        accountId = GameRequestHealthSink.currentAccountId()
                    )
                },
                alarmEventSink = { event ->
                    logs.append(
                        "警报事件：account=${event.accountId} kind=${event.kind} text=${event.text}",
                        tag = "alarm"
                    )
                    if (event.showNotification) postAlarmNotification(event)
                },
                sessionExtraSink = { accountId, updates ->
                    val account = accounts.listAccounts().firstOrNull { it.id == accountId }
                    val session = account?.session
                    if (account != null && session != null && session.sourceMode == 1) {
                        accounts.upsert(
                            account.copy(
                                session = session.copy(
                                    channelExtra = session.channelExtra + updates
                                )
                            )
                        )
                        logs.append(
                            "军情状态已刷新并保存：账号=$accountId，更新${updates.size}项",
                            tag = "military-intel"
                        )
                    }
                },
                executionAllowed = serviceExecutionAllowed
            ),
            runtime = AutomationRuntimeStateStore(
                timezoneId = behaviorContract.timezoneId,
                eventSink = { message -> logs.append(message, tag = "state-machine") },
                dailySuccessSink = { accountId, type, count, nowMillis ->
                    val total = dailyStats.add(accountId, type, count, nowMillis)
                    logs.append(
                        "账号$accountId ${type.userFacingName()} 今日成功次数=$total",
                        tag = "daily-stats"
                    )
                },
                dailySuccessSource = { accountId, type, nowMillis ->
                    dailyStats.current(accountId, type, nowMillis)
                }
            ),
            localMap = LocalTargetCache(
                banditTtlMillis = behaviorContract.mapSearch.targetCacheTtlMillis,
                banditEmptyTtlMillis = behaviorContract.mapSearch.scanCoordinateCacheTtlMillis,
                mineTtlMillis = behaviorContract.mine.targetCacheTtlMillis,
                store = LocalMapRepository(this)
            ),
            promptSink = { accountId, type, message ->
                val roleName = accounts.listAccounts()
                    .firstOrNull { it.id == accountId }
                    ?.displayName
                    ?.takeIf { it.isNotBlank() }
                    ?: "账号$accountId"
                logs.append(
                    "$roleName—提示：${type.userFacingName()}：$message",
                    tag = "prompt",
                    accountId = accountId
                )
            },
            dailyCompletions = dailyStats,
            behaviorContract = behaviorContract,
            successSink = { accountId, category, message ->
                logs.appendSuccess(accountId, category, message)
            },
            executionAllowed = serviceExecutionAllowed
        )
        lifecycleRunner = LocalSchedulerLifecycleRunner(scheduler)
        connectivityManager = getSystemService(ConnectivityManager::class.java)
        ensureNotificationChannel()
        ensureAlarmNotificationChannels()
        logs.append("service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return when (intent?.action ?: ACTION_RESTORE) {
            ACTION_START -> {
                executionOwnerActive = true
                hostingPreferences.setEnabled(true)
                if (running) requestImmediateSchedulerTick() else startLocalHosting()
                START_STICKY
            }
            ACTION_RESTORE -> {
                if (hostingPreferences.isEnabled()) {
                    executionOwnerActive = true
                    if (running) requestImmediateSchedulerTick() else startLocalHosting()
                    START_STICKY
                } else {
                    executionOwnerActive = false
                    stopSelf(startId)
                    START_NOT_STICKY
                }
            }
            ACTION_STOP -> {
                executionOwnerActive = false
                hostingPreferences.setEnabled(false)
                stopLocalHosting(reason = "explicit stop action", requestLogout = true)
                stopSelf(startId)
                START_NOT_STICKY
            }
            ACTION_CLEAR_LOGS -> {
                logs.clear()
                stopSelf(startId)
                START_NOT_STICKY
            }
            ACTION_REFRESH -> {
                if (hostingPreferences.isEnabled()) {
                    executionOwnerActive = true
                    if (running) requestImmediateSchedulerTick() else startLocalHosting()
                    START_STICKY
                } else {
                    executionOwnerActive = false
                    stopSelf(startId)
                    START_NOT_STICKY
                }
            }
            ACTION_SCHEDULED_TICK -> {
                consumeScheduledWakeup()
                if (hostingPreferences.isEnabled()) {
                    executionOwnerActive = true
                    if (running) {
                        acquireWakeLock()
                        requestImmediateSchedulerTick()
                    } else {
                        startLocalHosting()
                    }
                    START_STICKY
                } else {
                    executionOwnerActive = false
                    stopSelf(startId)
                    START_NOT_STICKY
                }
            }
            else -> START_NOT_STICKY
        }
    }

    override fun onDestroy() {
        executionOwnerActive = false
        stopLocalHosting(reason = "service destroyed", requestLogout = true)
        GameRequestHealthSink.reset()
        logs.append("service destroyed")
        worker.shutdown()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startLocalHosting() {
        if (running) {
            logs.append("service already running")
            return
        }
        running = true
        executionOwnerActive = true
        tickCount = 0
        cancelScheduledWakeup()
        startForeground(NOTIFICATION_ID, buildNotification(currentHostingNotificationText()))
        acquireWakeLock()
        refreshNetworkAvailability("service-start")
        registerNetworkMonitor()
        logs.append("local scheduling started")
        immediateTickRequested = false
        scheduleNextTick(0L)
    }

    private fun stopLocalHosting(reason: String = "stop requested", requestLogout: Boolean = false) {
        executionOwnerActive = false
        if (!running) return
        running = false
        immediateTickRequested = false
        handler.removeCallbacks(tickRunnable)
        scheduledTickAtElapsedMillis = Long.MAX_VALUE
        cancelScheduledWakeup()
        unregisterNetworkMonitor()
        releaseWakeLock()
        logs.append("local scheduling stopped at tick=$tickCount reason=$reason")
        taskRuntimeStatuses.markServiceStopped(
            System.currentTimeMillis(),
            "后台已停止：$reason",
            preserveNextRunAt = reason != "explicit stop action"
        )
        if (schedulerBusy) {
            logs.append("stop requested while scheduler tick is still active", tag = "local-scheduler")
        }
        if (requestLogout) {
            requestStopAllAndLogout(reason)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
    }

    private fun requestStopAllAndLogout(reason: String) {
        worker.execute {
            try {
                val exportedConfigs = configs.exportAll()
                taskSuppressions.onConfiguration(
                    taskConfigurationSignature(exportedConfigs)
                )
                val plans = loadPlans(exportedConfigs)
                logs.append(
                    "stop/logout requested for ${plans.size} account plan(s); reason=$reason",
                    tag = "local-scheduler"
                )
                val stopReports = SuspendRunner.run {
                    plans.map { plan ->
                        scheduler.stopAll(plan.session, plan.tasks, reason)
                    }
                }
                plans.zip(stopReports).forEach { (plan, report) ->
                    logs.append(report.toLogLine(), tag = "local-task-stop")
                    logs.append(
                        SelfLifecycleLogFormatter.taskStop(
                            accountId = report.accountId,
                            sourceMode = plan.session.sourceMode,
                            reason = reason,
                            stoppedTaskTypes = report.stoppedTaskTypes,
                            logoutRequested = report.logoutRequested,
                            logoutSucceeded = report.logoutSucceeded,
                            logoutMessage = report.logoutMessage
                        ),
                        tag = "self-lifecycle"
                    )
                    logs.append(
                        SelfLifecycleLogFormatter.sessionLogout(
                            accountId = report.accountId,
                            sourceMode = plan.session.sourceMode,
                            reason = reason,
                            logoutRequested = report.logoutRequested,
                            logoutSucceeded = report.logoutSucceeded,
                            logoutMessage = report.logoutMessage
                        ),
                        tag = "self-lifecycle"
                    )
                }
            } catch (t: Throwable) {
                logs.append("stop/logout error: ${t.message}", tag = "local-scheduler")
            }
        }
    }

    @android.annotation.SuppressLint("WakelockTimeout")
    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(PowerManager::class.java)
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dwpmclone:assistant_keepalive").apply {
            setReferenceCounted(false)
            // This is a user-started foreground service. Keep the CPU available
            // across long screen-off periods and release deterministically in
            // stopLocalHosting()/onDestroy() instead of silently expiring at 10m.
            acquire()
        }
        logs.append("wakelock acquired for background keepalive", tag = "keepalive")
    }

    private fun releaseWakeLock() {
        runCatching {
            if (wakeLock?.isHeld == true) wakeLock?.release()
        }
        wakeLock = null
        logs.append("wakelock released", tag = "keepalive")
    }

    private fun registerNetworkMonitor() {
        if (networkCallback != null) return
        val cm = connectivityManager ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                handleNetworkEvent("available:$network")
            }

            override fun onLost(network: Network) {
                handleNetworkEvent("lost:$network")
            }

            override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) {
                handleNetworkEvent("capabilities:$network")
            }
        }
        networkCallback = callback
        cm.registerNetworkCallback(
            NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build(),
            callback
        )
        logs.append("network monitor registered", tag = "network")
    }

    private fun handleNetworkEvent(reason: String) {
        val before = networkGeneration.get()
        refreshNetworkAvailability(reason)
        if (networkGeneration.get() != before) requestImmediateSchedulerTick()
    }

    private fun requestImmediateSchedulerTick() {
        val scheduleNow = synchronized(tickScheduleLock) {
            if (!running) return@synchronized false
            immediateTickRequested = true
            if (!schedulerBusy) {
                immediateTickRequested = false
                true
            } else {
                false
            }
        }
        if (scheduleNow) scheduleNextTick(0L)
    }

    private fun scheduleNextTick(delayMillis: Long) {
        val requestedDelay = delayMillis.coerceAtLeast(0L)
        handler.post {
            if (!running) return@post
            val now = SystemClock.elapsedRealtime()
            val requestedAt = if (Long.MAX_VALUE - now < requestedDelay) {
                Long.MAX_VALUE
            } else {
                now + requestedDelay
            }
            if (requestedAt >= scheduledTickAtElapsedMillis) return@post
            handler.removeCallbacks(tickRunnable)
            cancelScheduledWakeup(resetSchedule = false)
            scheduledTickAtElapsedMillis = requestedAt
            if (SchedulerTickPolicy.requiresContinuousWakeLock(requestedDelay)) {
                acquireWakeLock()
                handler.postDelayed(tickRunnable, requestedDelay)
            } else if (scheduleWakeupAlarm(requestedAt)) {
                releaseWakeLock()
            } else {
                // AlarmManager should be available on every supported device. If an OEM
                // rejects the inexact wakeup, preserve correctness with the existing lock.
                acquireWakeLock()
                handler.postDelayed(tickRunnable, requestedDelay)
            }
        }
    }

    private fun scheduleWakeupAlarm(triggerAtElapsedMillis: Long): Boolean = runCatching {
        val manager = getSystemService(AlarmManager::class.java) ?: return@runCatching false
        manager.setAndAllowWhileIdle(
            AlarmManager.ELAPSED_REALTIME_WAKEUP,
            triggerAtElapsedMillis,
            schedulerWakeupIntent()
        )
        true
    }.getOrDefault(false)

    private fun consumeScheduledWakeup() {
        handler.removeCallbacks(tickRunnable)
        scheduledTickAtElapsedMillis = Long.MAX_VALUE
        cancelScheduledWakeup(resetSchedule = false)
    }

    private fun cancelScheduledWakeup(resetSchedule: Boolean = true) {
        getSystemService(AlarmManager::class.java)?.cancel(schedulerWakeupIntent())
        if (resetSchedule) scheduledTickAtElapsedMillis = Long.MAX_VALUE
    }

    private fun schedulerWakeupIntent(): PendingIntent {
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val intent = Intent(this, AssistantForegroundService::class.java).setAction(ACTION_SCHEDULED_TICK)
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            PendingIntent.getForegroundService(this, SCHEDULER_WAKEUP_REQUEST_CODE, intent, flags)
        } else {
            PendingIntent.getService(this, SCHEDULER_WAKEUP_REQUEST_CODE, intent, flags)
        }
    }

    private fun unregisterNetworkMonitor() {
        val callback = networkCallback ?: return
        runCatching { connectivityManager?.unregisterNetworkCallback(callback) }
        networkCallback = null
        logs.append("network monitor unregistered", tag = "network")
    }

    private fun refreshNetworkAvailability(reason: String): Boolean {
        val networkId = usableNetworkId()
        updateNetworkAvailability(networkId, reason)
        return networkId != null
    }

    @Synchronized
    private fun updateNetworkAvailability(networkId: String?, reason: String) {
        val usable = networkId != null
        val networkSwitched = networkStateInitialized && networkUsable && usable && activeNetworkId != networkId
        if (networkStateInitialized && networkUsable == usable && !networkSwitched) return
        networkStateInitialized = true
        networkUsable = usable
        activeNetworkId = networkId
        forceSessionValidation = true
        networkGeneration.incrementAndGet()
        if (usable) {
            if (networkSwitched) {
                sessionRecovery.markNetworkPaused(System.currentTimeMillis(), reason)
            }
            logs.append(
                if (networkSwitched) {
                    "active network switched; account sessions must be rechecked before scheduling"
                } else {
                    "network validated; account sessions must be rechecked before scheduling"
                },
                tag = "network"
            )
        } else {
            sessionRecovery.markNetworkPaused(System.currentTimeMillis(), reason)
            logs.append("network unavailable; all real account actions paused", tag = "network")
        }
    }

    private fun usableNetworkId(): String? {
        val cm = connectivityManager ?: return null
        val network = cm.activeNetwork ?: return null
        val caps = cm.getNetworkCapabilities(network) ?: return null
        val internet = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        val validated = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        return network.toString().takeIf { internet && validated }
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "自研服务本地调度",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "手机本地托管和任务调度状态"
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun ensureAlarmNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                ALARM_ALERT_CHANNEL_ID,
                "自研服务警报",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "来袭、军情及任务异常提醒"
                enableVibration(true)
                vibrationPattern = longArrayOf(0L, 250L, 180L, 350L)
            }
        )
        manager.createNotificationChannel(
            NotificationChannel(
                ALARM_NOTICE_CHANNEL_ID,
                "自研服务军情",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "不震动的军情通知"
                enableVibration(false)
            }
        )
    }

    @Suppress("DEPRECATION")
    private fun postAlarmNotification(event: AlarmNotificationEvent) {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            logs.append(
                "警报通知未展示：尚未授予通知权限 account=${event.accountId} kind=${event.kind}",
                tag = "alarm"
            )
            return
        }
        val launchIntent = Intent(this, AssistantWebActivity::class.java)
        val pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT or
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0
        val pendingIntent = PendingIntent.getActivity(
            this,
            event.accountId.toInt(),
            launchIntent,
            pendingFlags
        )
        val title = when (event.kind) {
            AlarmNotificationKind.INCOMING -> "来袭警报"
            AlarmNotificationKind.MILITARY -> "军情提醒"
            AlarmNotificationKind.ERROR -> "任务异常"
        }
        val channelId = if (event.vibrate) ALARM_ALERT_CHANNEL_ID else ALARM_NOTICE_CHANNEL_ID
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, channelId)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        val notification = builder
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle(title)
            .setContentText(event.text)
            .setStyle(Notification.BigTextStyle().bigText(event.text))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setOngoing(false)
            .setWhen(System.currentTimeMillis())
            .apply {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
                    @Suppress("DEPRECATION")
                    setPriority(Notification.PRIORITY_HIGH)
                    if (event.vibrate) setVibrate(longArrayOf(0L, 250L, 180L, 350L))
                }
            }
            .build()
        getSystemService(NotificationManager::class.java)
            .notify(alarmNotificationIds.incrementAndGet(), notification)
    }

    @Suppress("DEPRECATION")
    private fun buildNotification(contentText: String): Notification {
        val launchIntent = Intent(this, AssistantWebActivity::class.java)
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val pendingIntent = PendingIntent.getActivity(this, 0, launchIntent, flags)
        val stopIntent = PendingIntent.getService(
            this,
            1,
            Intent(this, AssistantForegroundService::class.java).setAction(ACTION_STOP),
            flags
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("自研服务")
            .setContentText(contentText)
            .setContentIntent(pendingIntent)
            .addAction(android.R.drawable.ic_media_pause, "停止托管", stopIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setWhen(System.currentTimeMillis())
            .setShowWhen(false)
            .apply {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
                    @Suppress("DEPRECATION")
                    setPriority(Notification.PRIORITY_LOW)
                }
            }
            .build()
    }

    private fun runLocalSchedulerTick(tick: Int) {
        val mayRun = synchronized(tickScheduleLock) {
            if (schedulerBusy) {
                immediateTickRequested = true
                false
            } else {
                schedulerBusy = true
                true
            }
        }
        if (!mayRun) return
        worker.execute schedulerTick@{
            var nextDelayMillis = SchedulerTickPolicy.MAX_IDLE_DELAY_MILLIS
            var ranWork: Boolean
            try {
                if (!isUserUnlocked()) {
                    if (!waitingForFirstUnlock) {
                        waitingForFirstUnlock = true
                        logs.append("device has not completed first unlock; credential recovery is deferred", tag = "session-recovery")
                    }
                    return@schedulerTick
                }
                if (waitingForFirstUnlock) {
                    waitingForFirstUnlock = false
                    forceSessionValidation = true
                    logs.append("first unlock completed; account recovery resumed", tag = "session-recovery")
                }
                if (!refreshNetworkAvailability("scheduler-tick-$tick")) return@schedulerTick
                if (!running || !executionOwnerActive) return@schedulerTick

                val exportedConfigs = configs.exportAll()
                val nowMillis = System.currentTimeMillis()
                restoreOrUpdateTaskSuppression(exportedConfigs, nowMillis)
                val validationGeneration = networkGeneration.get()
                val forcedValidation = forceSessionValidation
                val recovery = sessionRecovery.reconcile(nowMillis, forcedValidation)
                if (!running || !executionOwnerActive) return@schedulerTick
                ranWork = forcedValidation || recovery.paused > 0 || recovery.relogged > 0
                if (forcedValidation && recovery.paused == 0 && recovery.waitingToRetry == 0 &&
                    networkUsable && networkGeneration.get() == validationGeneration
                ) {
                    forceSessionValidation = false
                }
                if (forcedValidation || recovery.paused > 0 || recovery.waitingToRetry > 0 || recovery.relogged > 0) {
                    logs.append(
                        "tick=$tick session_recovery online=${recovery.online} paused=${recovery.paused} waiting=${recovery.waitingToRetry} relogged=${recovery.relogged}",
                        tag = "session-recovery"
                    )
                }
                if (!networkUsable || networkGeneration.get() != validationGeneration) {
                    logs.append(
                        "tick=$tick network changed during session validation; scheduler batch deferred",
                        tag = "network"
                    )
                    return@schedulerTick
                }
                val allPlans = loadPlans(exportedConfigs)
                allPlans.forEach { plan ->
                    taskRuntimeStatuses.reconcileConfigured(
                        accountId = plan.session.accountId,
                        configuredTypes = plan.tasks.map { it.type },
                        nowMillis = nowMillis
                    )
                }
                val plans = allPlans.map { plan ->
                    plan.copy(
                        tasks = taskSuppressions.filter(
                            plan.session.accountId,
                            plan.tasks,
                            nowMillis
                        )
                    )
                }
                if (plans.any { it.tasks.isNotEmpty() } || forcedValidation) {
                    val accountIds = plans.map { it.session.accountId }
                    logs.append(
                        "tick=$tick loaded ${accountIds.size} account plan(s) from LocalConfigRepository",
                        tag = "local-scheduler"
                    )
                    plans.forEach { plan ->
                        logs.append(
                            "tick=$tick account=${plan.session.accountId} source=${plan.sourceDescription} tasks=${plan.tasks.size}",
                            tag = "local-scheduler"
                        )
                    }
                }
                val lifecycleBatch = SuspendRunner.run {
                    lifecycleRunner.runPlansOnceAndStopOnTerminal(
                        tick = tick,
                        plans = plans,
                        reasonPrefix = "service lifecycle terminal",
                        beforeAccount = { accountId ->
                            AccountOperationLockRegistry.acquire(accountId)
                            GameRequestHealthSink.bindAccount(accountId)
                        },
                        afterAccount = { accountId ->
                            GameRequestHealthSink.clearAccount()
                            AccountOperationLockRegistry.release(accountId)
                        }
                    )
                }
                if (!running || !executionOwnerActive) {
                    logs.append(
                        "调度轮次=$tick 已在停止边界结束，旧批次结果不再写回任务栈",
                        tag = "local-scheduler"
                    )
                    taskRuntimeStatuses.markServiceStopped(
                        System.currentTimeMillis(),
                        "后台已停止：执行权已撤销",
                        preserveNextRunAt = false
                    )
                    return@schedulerTick
                }
                val reports = lifecycleBatch.runReports
                ranWork = ranWork || reports.isNotEmpty()
                if (reports.isNotEmpty()) {
                    logs.append("tick=$tick completed ${reports.size} task reports", tag = "local-scheduler")
                }
                if (lifecycleBatch.deferredIdleTaskCount > 0) {
                    logs.append(
                        "调度轮次=$tick：军事任务优先，本轮已让行" +
                            "${lifecycleBatch.deferredIdleTaskCount}个闲时任务；立即进入下一轮",
                        tag = "local-scheduler"
                    )
                }
                updateHostingNotification(reports.map { it.type })
                reports.forEach { report ->
                    // A military batch can spend minutes in protocol I/O. Starting a Sleep /
                    // RetryAfter deadline from the tick's old start time makes it already expired
                    // when the batch ends, so the immediate idle-lane pass runs military again and
                    // starves every idle task. Deadlines must begin at the task decision boundary.
                    val decisionAtMillis = report.completedAtMillis ?: System.currentTimeMillis()
                    taskSuppressions.record(report, decisionAtMillis)
                    taskRuntimeStatuses.upsert(
                        TaskRuntimeStatusMapper.fromReport(report, decisionAtMillis, tick)
                    )
                    logs.append(report.toLogLine(), tag = "local-task")
                }
                lifecycleBatch.localStopReports.forEach { report ->
                    taskSuppressions.suppress(report)
                    logs.append(
                        "任务停止：账号=${report.accountId}，类型=${report.type.userFacingName()}，" +
                            "原因=${report.reason}；账号保持在线",
                        tag = "local-task-stop"
                    )
                }
                val terminalDecisions = lifecycleBatch.terminalDecisions
                if (terminalDecisions.isNotEmpty()) {
                    logs.append(
                        "tick=$tick terminal_decisions=${terminalDecisions.size}; stop/logout executed by lifecycle runner",
                        tag = "local-task-terminal"
                    )
                    val errorNotifiedAccounts = mutableSetOf<Long>()
                    terminalDecisions.forEach { terminal ->
                        logs.append(
                            "调度轮次=$tick，账号=${terminal.accountId}，" +
                                "任务=${terminal.type.userFacingName()}，终止原因=${terminal.decision.summary()}",
                            tag = "local-task-terminal"
                        )
                        if (errorNotifiedAccounts.add(terminal.accountId) &&
                            isErrorAlarmEnabled(terminal.accountId)
                        ) {
                            postAlarmNotification(
                                AlarmNotificationEvent(
                                    accountId = terminal.accountId,
                                    kind = AlarmNotificationKind.ERROR,
                                    text = "${terminal.type.userFacingName()}：${terminal.decision.summary()}",
                                    vibrate = true
                                )
                            )
                        }
                        when (val decision = terminal.decision) {
                            is TaskDecision.NeedRelogin -> sessionRecovery.markNeedsRelogin(
                                terminal.accountId,
                                decision.reason
                            )
                            is TaskDecision.Stop -> accounts.updateLoginState(
                                terminal.accountId,
                                AccountLoginState.STOPPED,
                                mapOf(
                                    "lastStoppedAt" to System.currentTimeMillis().toString(),
                                    "lastStoppedReason" to decision.reason
                                )
                            ).also {
                                accounts.setEnabled(terminal.accountId, false, AccountLoginState.STOPPED)
                            }
                            else -> Unit
                        }
                    }
                    lifecycleBatch.accounts.forEach { account ->
                        val stop = account.lifecycleReport.stopReport ?: return@forEach
                        logs.append(stop.toLogLine(), tag = "local-task-stop")
                        logs.append(
                            SelfLifecycleLogFormatter.taskStop(
                                accountId = stop.accountId,
                                sourceMode = account.sourceMode,
                                reason = "service lifecycle terminal tick=$tick source=${account.sourceDescription}",
                                stoppedTaskTypes = stop.stoppedTaskTypes,
                                logoutRequested = stop.logoutRequested,
                                logoutSucceeded = stop.logoutSucceeded,
                                logoutMessage = stop.logoutMessage
                            ),
                            tag = "self-lifecycle"
                        )
                        logs.append(
                            SelfLifecycleLogFormatter.sessionLogout(
                                accountId = stop.accountId,
                                sourceMode = account.sourceMode,
                                reason = "service lifecycle terminal tick=$tick source=${account.sourceDescription}",
                                logoutRequested = stop.logoutRequested,
                                logoutSucceeded = stop.logoutSucceeded,
                                logoutMessage = stop.logoutMessage
                            ),
                            tag = "self-lifecycle"
                        )
                    }
                    logs.append(
                        "tick=$tick invalid sessions queued for account-level recovery; foreground service remains active",
                        tag = "session-recovery"
                    )
                }
                val earliestDeadline = listOfNotNull(
                    taskSuppressions.earliestNextRunAtMillis(),
                    sessionRecovery.earliestRetryAtMillis(System.currentTimeMillis()),
                    sessionRecovery.earliestValidationAtMillis(System.currentTimeMillis())
                ).minOrNull()
                nextDelayMillis = if (lifecycleBatch.deferredIdleTaskCount > 0) {
                    0L
                } else {
                    SchedulerTickPolicy.nextDelayMillis(
                        nowMillis = System.currentTimeMillis(),
                        earliestDeadlineMillis = earliestDeadline,
                        ranWork = ranWork
                    )
                }
            } catch (t: Throwable) {
                nextDelayMillis = SchedulerTickPolicy.ACTIVE_FALLBACK_MILLIS
                logs.append("tick=$tick scheduler error: ${t.message}", tag = "local-scheduler")
                val accountId = accounts.listAccounts().firstOrNull {
                    it.enabled && isErrorAlarmEnabled(it.id)
                }?.id
                if (accountId != null) {
                    postAlarmNotification(
                        AlarmNotificationEvent(
                            accountId = accountId,
                            kind = AlarmNotificationKind.ERROR,
                            text = "后台调度异常：${t.message ?: t::class.java.simpleName}",
                            vibrate = true
                        )
                    )
                }
            } finally {
                val delay = synchronized(tickScheduleLock) {
                    schedulerBusy = false
                    if (immediateTickRequested) {
                        immediateTickRequested = false
                        0L
                    } else {
                        nextDelayMillis
                    }
                }
                scheduleNextTick(delay)
            }
        }
    }

    private fun isErrorAlarmEnabled(accountId: Long): Boolean {
        val values = configs.loadFeatureConfig(accountId, "alarm_withdraw")
            ?.optJSONObject("values")
            ?: return false
        val anyAlarmEnabled = values.optBoolean("alarm_withdraw_enabled", false) ||
            values.optBoolean("incomingEnabled", false) ||
            values.optBoolean("militaryEnabled", false) ||
            values.optBoolean("errorEnabled", false)
        return anyAlarmEnabled && values.optBoolean("errorEnabled", true)
    }

    /**
     * The service may remain alive for another account after one account is stopped. Network
     * ownership therefore has two dimensions: the global foreground host and the account bound
     * to this worker thread. This mirrors the desktop helper's per-session stopEvent.
     */
    private fun executionAllowedForCurrentAccount(): Boolean {
        return SchedulerExecutionOwnershipPolicy.allowed(
            hostActive = running && executionOwnerActive,
            boundAccountId = GameRequestHealthSink.currentAccountId(),
            accountEnabled = { accountId -> accounts.get(accountId)?.enabled == true }
        )
    }

    private fun currentHostingNotificationText(taskTypes: List<TaskType> = emptyList()): String {
        val labels = accounts.listAccounts()
            .filter { it.enabled && it.session?.sourceMode == 1 }
            .map { it.displayName?.takeIf(String::isNotBlank) ?: it.monarchName ?: "账号${it.id}" }
        return HostingNotificationText.format(labels, taskTypes)
    }

    private fun updateHostingNotification(taskTypes: List<TaskType>) {
        if (!running) return
        getSystemService(NotificationManager::class.java)?.notify(
            NOTIFICATION_ID,
            buildNotification(currentHostingNotificationText(taskTypes))
        )
    }

    private fun restoreOrUpdateTaskSuppression(
        exportedConfigs: org.json.JSONObject,
        nowMillis: Long
    ) {
        val signature = taskConfigurationSignature(exportedConfigs)
        if (!taskSuppressionRestored) {
            taskSuppressions.restore(
                signature = signature,
                persistedSignature = taskRuntimeStatuses.configurationSignature(),
                statuses = taskRuntimeStatuses.listAll(),
                nowMillis = nowMillis
            )
            taskRuntimeStatuses.setConfigurationSignature(signature)
            taskSuppressionRestored = true
        } else if (taskSuppressions.onConfiguration(signature)) {
            taskRuntimeStatuses.setConfigurationSignature(signature)
        }
    }

    /** A code upgrade may fix a previously terminal decision, so it starts a fresh suppression epoch. */
    private fun taskConfigurationSignature(exportedConfigs: org.json.JSONObject): String {
        val versionCode = runCatching {
            val info = packageManager.getPackageInfo(packageName, 0)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                info.longVersionCode
            } else {
                @Suppress("DEPRECATION")
                info.versionCode.toLong()
            }
        }.getOrDefault(0L)
        return TaskRunSuppressionRegistry.configurationSignature(
            "appVersionCode=$versionCode\n$exportedConfigs"
        )
    }

    private fun loadPlans(exportedConfigs: org.json.JSONObject): List<SavedTaskPlan> {
        return accounts.listAccounts()
            .asSequence()
            .filter(sessionRecovery::isRunnable)
            .mapNotNull { account ->
                SavedConfigTaskPlanFactory.planForRealAccount(
                    account,
                    exportedConfigs,
                    behaviorContract
                )?.let { plan ->
                    val extra = account.session?.channelExtra.orEmpty()
                    val activeKeys = ResidentTaskActivationPolicy.activeKeys(
                        extra,
                        behaviorContract.scheduler.residentPriority.keys
                    )
                    plan.copy(tasks = plan.tasks.filter { task ->
                        behaviorContract.scheduler.residentKey(task.type)?.let { it in activeKeys } ?: true
                    })
                }
            }
            .toList()
    }

    private fun isUserUnlocked(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.N ||
            getSystemService(UserManager::class.java)?.isUserUnlocked != false

    private fun TaskRunReport.toLogLine(): String =
        "${type.userFacingName()} 账号=$accountId 执行结果=${decisions.joinToString { it.summary() }}${error?.let { " 错误=$it" } ?: ""}"

    private fun TaskStopReport.toLogLine(): String =
        "停止账号=$accountId，任务=${stoppedTaskTypes.joinToString { it.userFacingName() }}，" +
            "已请求退出=$logoutRequested，退出成功=$logoutSucceeded，说明=$logoutMessage"

    private fun TaskDecision.summary(): String = when (this) {
        TaskDecision.Continue -> "继续"
        is TaskDecision.Sleep -> "等待${millis}毫秒"
        is TaskDecision.RetryAfter -> "${millis}毫秒后重试${reason?.takeIf(String::isNotBlank)?.let { "：$it" }.orEmpty()}"
        is TaskDecision.NeedRelogin -> "需要重新登录：$reason"
        is TaskDecision.Stop -> "停止：$reason"
    }

    companion object {
        const val ACTION_START = "com.example.dwpmclone.action.START_LOCAL_HOSTING"
        const val ACTION_STOP = "com.example.dwpmclone.action.STOP_LOCAL_HOSTING"
        const val ACTION_RESTORE = "com.example.dwpmclone.action.RESTORE_LOCAL_HOSTING"
        const val ACTION_CLEAR_LOGS = "com.example.dwpmclone.action.CLEAR_LOCAL_LOGS"
        const val ACTION_REFRESH = "com.example.dwpmclone.action.REFRESH_LOCAL_HOSTING"
        const val ACTION_SCHEDULED_TICK = "com.example.dwpmclone.action.SCHEDULED_LOCAL_TICK"
        private const val CHANNEL_ID = "dwpm_clone_local_hosting"
        private const val ALARM_ALERT_CHANNEL_ID = "dwpm_clone_alarm_alert"
        private const val ALARM_NOTICE_CHANNEL_ID = "dwpm_clone_alarm_notice"
        private const val NOTIFICATION_ID = 1001
        private const val SCHEDULER_WAKEUP_REQUEST_CODE = 1002
        private val alarmNotificationIds = AtomicInteger(2000)
        @Volatile private var executionOwnerActive = false

        fun isExecutionOwnerActive(): Boolean = executionOwnerActive

        fun start(context: Context) {
            executionOwnerActive = true
            LocalHostingPreferences(context).setEnabled(true)
            val intent = Intent(context, AssistantForegroundService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            executionOwnerActive = false
            LocalHostingPreferences(context).setEnabled(false)
            context.startService(Intent(context, AssistantForegroundService::class.java).setAction(ACTION_STOP))
        }

        fun refresh(context: Context) {
            if (!LocalHostingPreferences(context).isEnabled()) return
            executionOwnerActive = true
            val intent = Intent(context, AssistantForegroundService::class.java).setAction(ACTION_REFRESH)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun resumeIfEnabled(context: Context): Boolean {
            if (!LocalHostingPreferences(context).isEnabled()) return false
            executionOwnerActive = true
            val intent = Intent(context, AssistantForegroundService::class.java).setAction(ACTION_RESTORE)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            return true
        }

        fun clearLogs(context: Context) {
            context.startService(Intent(context, AssistantForegroundService::class.java).setAction(ACTION_CLEAR_LOGS))
        }
    }
}

package com.example.dwpmclone.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
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
import com.example.dwpmclone.MainActivity
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.CollaborativeMapSettingsRepository
import com.example.dwpmclone.data.local.LocalConfigRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.local.TaskRuntimeStatusRepository
import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.model.AlarmNotificationEvent
import com.example.dwpmclone.domain.model.AlarmNotificationKind
import com.example.dwpmclone.domain.scheduler.SavedConfigTaskPlanFactory
import com.example.dwpmclone.domain.scheduler.SelfLifecycleLogFormatter
import com.example.dwpmclone.domain.scheduler.SavedTaskPlan
import com.example.dwpmclone.domain.scheduler.LocalSchedulerLifecycleRunner
import com.example.dwpmclone.domain.scheduler.RealSessionTaskPlanAdapter
import com.example.dwpmclone.domain.scheduler.SuspendRunner
import com.example.dwpmclone.domain.scheduler.TaskRunReport
import com.example.dwpmclone.domain.scheduler.TaskScheduler
import com.example.dwpmclone.domain.scheduler.TaskStopReport
import com.example.dwpmclone.domain.scheduler.TaskRunSuppressionRegistry
import com.example.dwpmclone.domain.scheduler.TaskRuntimeStatusMapper
import com.example.dwpmclone.domain.state.AutomationRuntimeStateStore
import com.example.dwpmclone.domain.cloud.CloudFirstMapCoordinator
import java.util.concurrent.atomic.AtomicInteger

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
    private val taskSuppressions = TaskRunSuppressionRegistry()
    private var wakeLock: PowerManager.WakeLock? = null
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    @Volatile private var running = false
    @Volatile private var schedulerBusy = false
    private var tickCount = 0

    private val tickRunnable = object : Runnable {
        override fun run() {
            if (!running) return
            tickCount += 1
            val configCount = configs.exportAll().optJSONObject("configs")?.length() ?: 0
            logs.append("tick=$tickCount config_entries=$configCount; starting local scheduler")
            updateEnabledAccountKeepaliveStates(tickCount)
            runLocalSchedulerTick(tickCount)
            handler.postDelayed(this, TICK_INTERVAL_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        logs = TaskLogRepository(this)
        configs = LocalConfigRepository(this)
        accounts = LocalAccountRepository(this)
        taskRuntimeStatuses = TaskRuntimeStatusRepository(this)
        scheduler = TaskScheduler(
            SessionAwareGameProtocolClient(
                actionAudit = { message -> logs.append(message, tag = "real-action") },
                alarmEventSink = { event ->
                    logs.append(
                        "警报事件：account=${event.accountId} kind=${event.kind} text=${event.text}",
                        tag = "alarm"
                    )
                    postAlarmNotification(event)
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
                            "已持久化 0x3110/0xa110 军情刷新：account=$accountId keys=${updates.keys.joinToString()}",
                            tag = "military-intel"
                        )
                    }
                }
            ),
            runtime = AutomationRuntimeStateStore(
                eventSink = { message -> logs.append(message, tag = "state-machine") },
                dailySuccessSink = { accountId, type, count, nowMillis ->
                    val total = LocalDailySuccessStatsRepository(this)
                        .add(accountId, type, count, nowMillis)
                    logs.append(
                        "账号$accountId ${type.name} 今日成功次数=$total",
                        tag = "daily-stats"
                    )
                }
            ),
            cloudMap = CloudFirstMapCoordinator(
                CollaborativeMapSettingsRepository(this).createClient()
            ),
            promptSink = { accountId, type, message ->
                val roleName = accounts.listAccounts()
                    .firstOrNull { it.id == accountId }
                    ?.displayName
                    ?.takeIf { it.isNotBlank() }
                    ?: "账号$accountId"
                logs.append(
                    "$roleName—提示：${type.name}：$message",
                    tag = "prompt",
                    accountId = accountId
                )
            }
        )
        lifecycleRunner = LocalSchedulerLifecycleRunner(scheduler)
        connectivityManager = getSystemService(ConnectivityManager::class.java)
        ensureNotificationChannel()
        ensureAlarmNotificationChannels()
        logs.append("service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return when (intent?.action ?: ACTION_START) {
            ACTION_START -> {
                startLocalHosting()
                START_STICKY
            }
            ACTION_STOP -> {
                stopLocalHosting(reason = "explicit stop action", requestLogout = true)
                stopSelf(startId)
                START_NOT_STICKY
            }
            ACTION_CLEAR_LOGS -> {
                logs.clear()
                stopSelf(startId)
                START_NOT_STICKY
            }
            else -> START_NOT_STICKY
        }
    }

    override fun onDestroy() {
        stopLocalHosting(reason = "service destroyed", requestLogout = true)
        logs.append("service destroyed")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startLocalHosting() {
        if (running) {
            logs.append("service already running")
            return
        }
        running = true
        tickCount = 0
        startForeground(NOTIFICATION_ID, buildNotification("本地调度运行中"))
        acquireWakeLock()
        registerNetworkMonitor()
        logs.append("local scheduling started")
        handler.removeCallbacks(tickRunnable)
        handler.post(tickRunnable)
    }

    private fun stopLocalHosting(reason: String = "stop requested", requestLogout: Boolean = false) {
        if (!running) return
        running = false
        handler.removeCallbacks(tickRunnable)
        unregisterNetworkMonitor()
        releaseWakeLock()
        logs.append("local scheduling stopped at tick=$tickCount reason=$reason")
        taskRuntimeStatuses.markServiceStopped(
            System.currentTimeMillis(),
            "后台已停止：$reason"
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
        Thread {
            try {
                val exportedConfigs = configs.exportAll()
                taskSuppressions.onConfiguration(exportedConfigs.toString())
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
        }.start()
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(PowerManager::class.java)
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dwpmclone:assistant_keepalive").apply {
            setReferenceCounted(false)
            acquire(10 * 60 * 1000L)
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
                logs.append("network available: $network", tag = "network")
            }

            override fun onLost(network: Network) {
                logs.append("network lost: $network; next service tick should report offline/relogin decision", tag = "network")
            }

            override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) {
                val internet = networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                val validated = networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
                logs.append("network changed: internet=$internet validated=$validated", tag = "network")
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

    private fun unregisterNetworkMonitor() {
        val callback = networkCallback ?: return
        runCatching { connectivityManager?.unregisterNetworkCallback(callback) }
        networkCallback = null
        logs.append("network monitor unregistered", tag = "network")
    }

    private fun updateEnabledAccountKeepaliveStates(tick: Int) {
        val enabledAccounts = accounts.listAccounts().filter { it.enabled && it.session?.sourceMode == 1 }
        if (enabledAccounts.isEmpty()) return
        val online = hasUsableNetwork()
        val now = System.currentTimeMillis().toString()
        enabledAccounts.forEach { account ->
            if (online) {
                accounts.updateLoginState(
                    account.id,
                    "REAL_PROTOCOL_ONLINE",
                    mapOf(
                        "lastKeepaliveAt" to now,
                        "lastKeepaliveMessage" to "network validated; foreground service tick=$tick"
                    )
                )
            } else {
                accounts.updateLoginState(
                    account.id,
                    "REAL_PROTOCOL_OFFLINE",
                    mapOf(
                        "lastKeepaliveAt" to now,
                        "lastKeepaliveMessage" to "network unavailable; foreground service tick=$tick"
                    )
                )
            }
        }
        logs.append(
            "keepalive tick=$tick accounts=${enabledAccounts.size} network=${if (online) "online" else "offline"}",
            tag = "keepalive"
        )
    }

    private fun hasUsableNetwork(): Boolean {
        val cm = connectivityManager ?: return true
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        val internet = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        val validated = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        return internet && validated
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "自研服务本地调度",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Read-only sync and local scheduler status"
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
        val launchIntent = Intent(this, MainActivity::class.java)
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

    private fun buildNotification(contentText: String): Notification {
        val launchIntent = Intent(this, MainActivity::class.java)
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val pendingIntent = PendingIntent.getActivity(this, 0, launchIntent, flags)
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
        if (schedulerBusy) {
            logs.append("tick=$tick skipped; previous scheduler run still active", tag = "local-scheduler")
            return
        }
        schedulerBusy = true
        Thread {
            try {
                val exportedConfigs = configs.exportAll()
                val nowMillis = System.currentTimeMillis()
                taskSuppressions.onConfiguration(exportedConfigs.toString())
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
                val lifecycleBatch = SuspendRunner.run {
                    lifecycleRunner.runPlansOnceAndStopOnTerminal(
                        tick = tick,
                        plans = plans,
                        reasonPrefix = "service lifecycle terminal"
                    )
                }
                val reports = lifecycleBatch.runReports
                logs.append("tick=$tick completed ${reports.size} task reports", tag = "local-scheduler")
                reports.forEach { report ->
                    taskSuppressions.record(report, nowMillis)
                    taskRuntimeStatuses.upsert(
                        TaskRuntimeStatusMapper.fromReport(report, nowMillis, tick)
                    )
                    logs.append(report.toLogLine(), tag = "local-task")
                }
                lifecycleBatch.localStopReports.forEach { report ->
                    taskSuppressions.suppress(report)
                    logs.append(
                        "TASK_STOP account=${report.accountId} type=${report.type.name} reason=${report.reason}; account remains online",
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
                        logs.append("tick=$tick account=${terminal.accountId} type=${terminal.type.name} terminal=${terminal.decision}", tag = "local-task-terminal")
                        if (errorNotifiedAccounts.add(terminal.accountId) &&
                            isErrorAlarmEnabled(terminal.accountId)
                        ) {
                            postAlarmNotification(
                                AlarmNotificationEvent(
                                    accountId = terminal.accountId,
                                    kind = AlarmNotificationKind.ERROR,
                                    text = "${terminal.type.name}：${terminal.decision.summary()}",
                                    vibrate = true
                                )
                            )
                        }
                        when (val decision = terminal.decision) {
                            is TaskDecision.NeedRelogin -> accounts.updateLoginState(
                                terminal.accountId,
                                "REAL_PROTOCOL_OFFLINE",
                                mapOf(
                                    "lastOfflineAt" to System.currentTimeMillis().toString(),
                                    "lastOfflineReason" to decision.reason
                                )
                            )
                            is TaskDecision.Stop -> accounts.updateLoginState(
                                terminal.accountId,
                                "REAL_PROTOCOL_STOPPED",
                                mapOf(
                                    "lastStoppedAt" to System.currentTimeMillis().toString(),
                                    "lastStoppedReason" to decision.reason
                                )
                            ).also {
                                accounts.setEnabled(terminal.accountId, false, "REAL_PROTOCOL_STOPPED")
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
                    handler.post {
                        if (running) {
                            stopLocalHosting(
                                reason = "terminal decision tick=$tick",
                                requestLogout = false
                            )
                            stopSelf()
                        }
                    }
                }
            } catch (t: Throwable) {
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
                schedulerBusy = false
            }
        }.start()
    }

    private fun isErrorAlarmEnabled(accountId: Long): Boolean {
        val values = configs.loadFeatureConfig(accountId, "alarm_withdraw")
            ?.optJSONObject("values")
            ?: return false
        return values.optBoolean("alarm_withdraw_enabled", false) &&
            values.optBoolean("errorEnabled", true)
    }

    private fun loadPlans(exportedConfigs: org.json.JSONObject): List<SavedTaskPlan> {
        val realAccountsById = accounts.listAccounts()
            .filter { it.enabled && it.session != null }
            .associateBy { it.id }
        val savedConfigAccountIds = SavedConfigTaskPlanFactory.accountIds(exportedConfigs)
        val accountIds = if (realAccountsById.isNotEmpty()) {
            // 真机产品路径只调度当前真实登录账号。旧版本/测试遗留的 764、1 等配置
            // 不能再生成 mock 任务，否则用户点击保存后会看到无关账号的 SHUA_HUANG
            // 先跑一遍，甚至触发 terminal stop，表现像当前账号流程异常。
            realAccountsById.keys.toList()
        } else {
            savedConfigAccountIds
        }
        return accountIds.map { accountId ->
            val realAccount = realAccountsById[accountId]
            val savedPlan = SavedConfigTaskPlanFactory.plan(accountId, exportedConfigs, realAccount)
            val realSession = realAccount?.session
            if (realSession != null && savedPlan.session.sourceMode != 1) {
                RealSessionTaskPlanAdapter.attachRealSession(savedPlan, realSession)
            } else {
                savedPlan
            }
        }
    }

    private fun TaskRunReport.toLogLine(): String =
        "${type.name} account=$accountId decisions=${decisions.joinToString { it.summary() }}${error?.let { " error=$it" } ?: ""}"

    private fun TaskStopReport.toLogLine(): String =
        "STOP account=$accountId tasks=${stoppedTaskTypes.joinToString { it.name }} logoutRequested=$logoutRequested logoutSucceeded=$logoutSucceeded message=$logoutMessage"

    private fun TaskDecision.summary(): String = when (this) {
        TaskDecision.Continue -> "Continue"
        is TaskDecision.Sleep -> "Sleep(${millis}ms)"
        is TaskDecision.RetryAfter -> "RetryAfter(${millis}ms)"
        is TaskDecision.NeedRelogin -> "NeedRelogin($reason)"
        is TaskDecision.Stop -> "Stop($reason)"
    }

    companion object {
        const val ACTION_START = "com.example.dwpmclone.action.START_MOCK_HOSTING"
        const val ACTION_STOP = "com.example.dwpmclone.action.STOP_MOCK_HOSTING"
        const val ACTION_CLEAR_LOGS = "com.example.dwpmclone.action.CLEAR_MOCK_LOGS"
        private const val CHANNEL_ID = "dwpm_clone_mock_hosting"
        private const val ALARM_ALERT_CHANNEL_ID = "dwpm_clone_alarm_alert"
        private const val ALARM_NOTICE_CHANNEL_ID = "dwpm_clone_alarm_notice"
        private const val NOTIFICATION_ID = 1001
        private const val TICK_INTERVAL_MS = 5_000L
        private val alarmNotificationIds = AtomicInteger(2000)

        fun start(context: Context) {
            val intent = Intent(context, AssistantForegroundService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.startService(Intent(context, AssistantForegroundService::class.java).setAction(ACTION_STOP))
        }

        fun clearLogs(context: Context) {
            context.startService(Intent(context, AssistantForegroundService::class.java).setAction(ACTION_CLEAR_LOGS))
        }
    }
}

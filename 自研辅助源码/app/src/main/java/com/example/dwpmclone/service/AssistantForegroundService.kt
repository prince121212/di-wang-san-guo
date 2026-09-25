package com.example.dwpmclone.service

import com.example.dwpmclone.ui.hosting.BackgroundHostingPermissionState

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.AlarmManager
import android.app.Service
import android.content.Context
import android.content.Intent
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
import com.example.dwpmclone.BuildConfig
import com.example.dwpmclone.data.account.AccountLoginState
import com.example.dwpmclone.data.account.AccountSessionRecovery
import com.example.dwpmclone.host.ResidentLivenessWatchdog
import com.example.dwpmclone.host.SharedPythonCoreHost
import com.example.dwpmclone.host.SharedResidentAutomationAdapter
import com.example.dwpmclone.host.SharedResidentTickResult
import com.example.dwpmclone.host.SharedResidentTaskStatusMapper
import com.example.dwpmclone.host.SharedResidentWakeGate
import com.example.dwpmclone.host.AndroidResidentWakeStateStore
import com.example.dwpmclone.host.PendingOperationWakeLease
import com.example.dwpmclone.data.local.ExpeditionTransactionRepository
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.AssistantBehaviorContractAssetLoader
import com.example.dwpmclone.data.local.LocalConfigRepository
import com.example.dwpmclone.data.local.LocalHostingPreferences
import com.example.dwpmclone.data.local.HostingInterruptionReport
import com.example.dwpmclone.data.local.LocalHostingRuntimeRepository
import com.example.dwpmclone.data.local.ProcessExitReader
import com.example.dwpmclone.data.local.LocalMapRepository
import com.example.dwpmclone.data.local.LogAudience
import com.example.dwpmclone.data.local.NetworkOutageRepository
import com.example.dwpmclone.data.local.ScheduledNetworkOutageDetector
import com.example.dwpmclone.data.local.RequestHealthRepository
import com.example.dwpmclone.data.local.SessionReconnectRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.local.TaskRuntimeStatusRepository
import com.example.dwpmclone.data.protocol.GameRequestHealthSink
import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.protocol.userFacingName
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
import com.example.dwpmclone.domain.scheduler.TaskRuntimeState
import com.example.dwpmclone.domain.scheduler.TaskRuntimeStatus
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import com.example.dwpmclone.domain.state.AutomationRuntimeStateStore
import com.example.dwpmclone.domain.state.AccountOperationLockRegistry
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.Executors
import com.example.dwpmclone.ui.web.LocalSettingsConfigMapper

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
    private lateinit var sharedPythonCore: SharedPythonCoreHost
    private lateinit var sharedResidentAutomation: SharedResidentAutomationAdapter
    private lateinit var sharedResidentWakeGate: SharedResidentWakeGate
    /** Independent of every scheduling mechanism, so it survives their bugs. */
    private val residentLiveness = ResidentLivenessWatchdog()
    private lateinit var hostingRuntime: LocalHostingRuntimeRepository
    private lateinit var networkOutages: NetworkOutageRepository
    private val taskSuppressions = TaskRunSuppressionRegistry()
    private val worker = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "assistant-scheduler").apply { isDaemon = true }
    }
    private var wakeLock: PowerManager.WakeLock? = null
    /** When the held lock's platform timeout fires; 0 when no lock is held. */
    private var wakeLockExpiresAtElapsedMillis = 0L
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
    private var inexactAlarmWarningLogged = false
    private val pendingOperationWakeLease = PendingOperationWakeLease(
        PENDING_OPERATION_WAKE_LEASE_MILLIS,
    )
    private var pendingWakeLeaseExpiredLogged = false

    private val tickRunnable = object : Runnable {
        override fun run() {
            val scheduledAt = synchronized(tickScheduleLock) {
                scheduledTickAtElapsedMillis
            }
            if (scheduledAt == Long.MAX_VALUE) return
            consumeAndRunScheduledTick(scheduledAt, "handler")
        }
    }

    override fun onCreate() {
        super.onCreate()
        logs = TaskLogRepository(this)
        configs = LocalConfigRepository(this)
        accounts = LocalAccountRepository(this)
        taskRuntimeStatuses = TaskRuntimeStatusRepository(this)
        hostingPreferences = LocalHostingPreferences(this)
        hostingRuntime = LocalHostingRuntimeRepository(this)
        networkOutages = NetworkOutageRepository(this)
        behaviorContract = AssistantBehaviorContractAssetLoader.load(this)
        sharedPythonCore = SharedPythonCoreHost.get(this)
        sharedResidentAutomation = SharedResidentAutomationAdapter(sharedPythonCore)
        sharedResidentWakeGate = SharedResidentWakeGate(
            store = AndroidResidentWakeStateStore(this),
        )
        val serviceExecutionAllowed = { executionAllowedForCurrentAccount() }
        sessionRecovery = AccountSessionRecovery(
            accounts = accounts,
            reloginSource = sharedPythonCore,
            reconnects = SessionReconnectRepository(this),
            logs = logs,
            lifecycleDecisions = sharedPythonCore,
            stateTransitions = sharedPythonCore,
            probe = sharedPythonCore,
        )
        sessionRecovery.prepareProcessRecovery(System.currentTimeMillis())
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
        logs.append("service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return when (intent?.action ?: ACTION_RESTORE) {
            ACTION_START -> {
                sharedResidentWakeGate.clear()
                hostingPreferences.setEnabled(true)
                if (running) {
                    // The service is already in the foreground in this branch;
                    // republish the execution lease before accepting a new
                    // scheduler wake.
                    activateExecutionOwner()
                    requestImmediateSchedulerTick()
                } else {
                    startLocalHosting()
                }
                START_STICKY
            }
            ACTION_RESTORE -> {
                // A wake deadline persisted by an older scheduler build may
                // be later than a durable pending record's next read-only
                // observation.  Recompute it on every process/boot restore;
                // clearing this host-side hint cannot replay a mutation because
                // the shared Python operation ledger owns the send boundary.
                sharedResidentWakeGate.clear()
                if (hostingPreferences.isEnabled()) {
                    if (running) {
                        activateExecutionOwner()
                        requestImmediateSchedulerTick()
                    } else {
                        startLocalHosting()
                    }
                    START_STICKY
                } else {
                    deactivateExecutionOwner()
                    stopSelf(startId)
                    START_NOT_STICKY
                }
            }
            ACTION_STOP -> {
                deactivateExecutionOwner()
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
                sharedResidentWakeGate.clear()
                if (hostingPreferences.isEnabled()) {
                    if (running) {
                        activateExecutionOwner()
                        requestImmediateSchedulerTick()
                    } else {
                        startLocalHosting()
                    }
                    START_STICKY
                } else {
                    deactivateExecutionOwner()
                    stopSelf(startId)
                    START_NOT_STICKY
                }
            }
            ACTION_EXECUTION_WATCHDOG -> {
                if (hostingPreferences.isEnabled()) {
                    if (running) {
                        activateExecutionOwner()
                        // A watchdog firing while the worker is still busy is
                        // expected for a slow network operation. Keep a new
                        // lease armed; if the process disappeared, this branch
                        // is reached in a fresh process and startLocalHosting()
                        // below rebuilds the scheduler from durable state.
                        if (schedulerBusy) {
                            armExecutionWatchdog()
                        } else {
                            requestImmediateSchedulerTick()
                        }
                    } else {
                        startLocalHosting()
                    }
                    START_STICKY
                } else {
                    cancelExecutionWatchdog()
                    deactivateExecutionOwner()
                    stopSelf(startId)
                    START_NOT_STICKY
                }
            }
            ACTION_SCHEDULED_TICK -> {
                if (hostingPreferences.isEnabled()) {
                    if (running) {
                        activateExecutionOwner()
                        val scheduledAt = intent?.getLongExtra(
                            EXTRA_SCHEDULED_AT_ELAPSED,
                            Long.MIN_VALUE,
                        ) ?: Long.MIN_VALUE
                        consumeAndRunScheduledTick(scheduledAt, "alarm")
                    } else {
                        startLocalHosting()
                    }
                    START_STICKY
                } else {
                    deactivateExecutionOwner()
                    stopSelf(startId)
                    START_NOT_STICKY
                }
            }
            else -> START_NOT_STICKY
        }
    }

    override fun onDestroy() {
        deactivateExecutionOwner()
        // onDestroy is not a user stop boundary. OEMs may destroy a service
        // while the user-enabled lease is still valid; logging out here would
        // turn a recoverable process death into irreversible task loss.
        val restoreExpected = running && hostingPreferences.isEnabled()
        stopLocalHosting(
            reason = "service destroyed",
            requestLogout = false,
            preserveRecoveryAlarm = restoreExpected,
            preserveRuntimeLease = restoreExpected,
        )
        if (restoreExpected) {
            armRecoveryAlarm(PROCESS_RESTART_DELAY_MILLIS)
        }
        GameRequestHealthSink.reset()
        logs.append("service destroyed")
        worker.shutdown()
        super.onDestroy()
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Removing the launcher task is not the same as the user pressing
        // “停止托管”. Keep the durable preference and let the next watchdog
        // alarm recreate the foreground service when the platform permits it.
        if (hostingPreferences.isEnabled()) {
            logs.append("launcher task removed; hosting remains enabled", tag = "lifecycle")
            armRecoveryAlarm(TASK_REMOVED_RESTART_DELAY_MILLIS)
        }
        super.onTaskRemoved(rootIntent)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startLocalHosting() {
        if (running) {
            logs.append("service already running")
            return
        }
        cancelExecutionWatchdog()
        pendingOperationWakeLease.clear()
        pendingWakeLeaseExpiredLogged = false
        running = true
        tickCount = 0
        cancelScheduledWakeup()
        startForeground(NOTIFICATION_ID, buildNotification(currentHostingNotificationText()))
        val permissionState = BackgroundHostingPermissionState.read(this)
        if (!permissionState.reliableHostingReady) {
            logs.append(
                permissionState.blockingIssueMessage()
                    ?: "后台托管未启动：必要后台权限不完整；请在攻略-后台运行设置中完成授权后重试",
                tag = "scheduler-health",
            )
            stopLocalHosting(
                reason = "required background permission missing",
                requestLogout = false,
            )
            stopSelf()
            return
        }
        // Publish the host execution lease only after Android has accepted the
        // foreground notification and all standard prerequisites are present.
        // Python may be warmed up earlier, but queued operations must not
        // start during that pre-foreground window.
        activateExecutionOwner()
        hostingRuntime.beginProcess(System.currentTimeMillis())
        // beginProcess is what decides whether this start recovered from an
        // interruption, so attribution has to read the journal afterwards.  On a
        // user's phone this log line is the only way to tell an OEM process kill
        // apart from a game-side failure.
        reportPreviousInterruption()
        refreshNetworkAvailability("service-start")
        registerNetworkMonitor()
        logs.append("local scheduling started")
        immediateTickRequested = false
        scheduleNextTick(0L)
    }

    private fun stopLocalHosting(
        reason: String = "stop requested",
        requestLogout: Boolean = false,
        preserveRecoveryAlarm: Boolean = false,
        preserveRuntimeLease: Boolean = false,
    ) {
        deactivateExecutionOwner()
        if (!running) return
        running = false
        immediateTickRequested = false
        handler.removeCallbacks(tickRunnable)
        scheduledTickAtElapsedMillis = Long.MAX_VALUE
        cancelExecutionWatchdog()
        pendingOperationWakeLease.clear()
        pendingWakeLeaseExpiredLogged = false
        if (!preserveRecoveryAlarm) cancelScheduledWakeup()
        unregisterNetworkMonitor()
        releaseWakeLock()
        if (preserveRuntimeLease) {
            hostingRuntime.interrupted(System.currentTimeMillis(), reason)
        } else {
            hostingRuntime.markStopped(System.currentTimeMillis(), reason)
        }
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
    private fun acquireWakeLock(timeoutMillis: Long = TICK_WAKELOCK_TIMEOUT_MILLIS) {
        if (wakeLock?.isHeld == true) return
        val bounded = timeoutMillis.coerceIn(1_000L, MAX_TICK_WAKELOCK_TIMEOUT_MILLIS)
        val pm = getSystemService(PowerManager::class.java)
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dwpmclone:assistant_keepalive").apply {
            setReferenceCounted(false)
            // A wake lock is a bounded lease: it covers a tick, an operation
            // still executing, or a deadline the scheduler has named, and
            // expires on its own if this process forgets to release it.
            acquire(bounded)
        }
        wakeLockExpiresAtElapsedMillis = SystemClock.elapsedRealtime() + bounded
        logs.append("wakelock acquired for scheduler window", tag = "keepalive")
    }

    /**
     * Extend the lease without ever passing through a released state, and
     * never shorten it.
     *
     * In deep Doze the kernel suspends within the same millisecond the last
     * wake lock is dropped, so a release-then-acquire renew left a window in
     * which the device slept mid-operation (device log: `released reason=renew`
     * at 09:24:16, matching `acquired` only at 09:25:50 when the alarm fired).
     * A non-reference-counted lock re-arms its timeout on a repeated acquire,
     * which is exactly the primitive a renew needs; taking the longer of the
     * current and requested expiry keeps every reason for holding the CPU
     * satisfied at once.
     */
    @android.annotation.SuppressLint("WakelockTimeout")
    private fun renewWakeLock(timeoutMillis: Long) {
        val bounded = timeoutMillis.coerceIn(1_000L, MAX_TICK_WAKELOCK_TIMEOUT_MILLIS)
        val held = wakeLock
        if (held?.isHeld != true) {
            acquireWakeLock(bounded)
            return
        }
        val nowElapsed = SystemClock.elapsedRealtime()
        val remaining = wakeLockExpiresAtElapsedMillis - nowElapsed
        if (remaining >= bounded) return
        held.acquire(bounded)
        wakeLockExpiresAtElapsedMillis = nowElapsed + bounded
    }

    private fun releaseWakeLock(reason: String = "scheduler window finished") {
        runCatching {
            if (wakeLock?.isHeld == true) wakeLock?.release()
        }
        wakeLock = null
        wakeLockExpiresAtElapsedMillis = 0L
        logs.append("wakelock released reason=$reason", tag = "keepalive")
    }

    /**
     * Keep the CPU awake for two bounded reasons only: a shared Python
     * operation is known to still be executing, or the scheduler has already
     * declared that the next tick is imminent.  Business state and replay
     * safety remain owned by the durable operation ledger.
     *
     * @param nextDelayMillis the gap the scheduler chose before the next tick,
     *   or null when no follow-up tick will be scheduled.
     */
    private fun finishSchedulerWakeWindow(nextDelayMillis: Long?) {
        val nowElapsed = SystemClock.elapsedRealtime()
        val lease = pendingOperationWakeLease.snapshot(nowElapsed)
        // Two independent reasons keep the CPU: an operation still executing,
        // and a deadline the scheduler has named.  Either one suffices; the
        // lease is the longer of what the two ask for.  The Handler only fires
        // while the CPU is awake, and the alarm behind it is Doze-deferred by
        // minutes, so a named deadline handed to the alarm is a missed deadline.
        val tickHoldMillis = nextDelayMillis
            ?.takeIf { SchedulerTickPolicy.shouldHoldWakeLockAcross(it) }
            ?.let { SchedulerTickPolicy.wakeHoldTimeoutMillis(it) }
        when {
            lease.active -> {
                val remaining = ((lease.deadlineElapsedMillis ?: nowElapsed) - nowElapsed)
                    .coerceAtLeast(1_000L)
                // Renewing re-arms the platform timeout up to the operation's
                // hard deadline, or to the next tick if that is further out.
                renewWakeLock(maxOf(remaining, tickHoldMillis ?: 0L))
                pendingWakeLeaseExpiredLogged = false
                logs.append(
                    "pending operation wake lease active operations=" +
                        "${lease.pendingOperationIds.size} remainingMillis=$remaining",
                    tag = "keepalive",
                )
            }
            tickHoldMillis != null -> {
                renewWakeLock(tickHoldMillis)
                logs.append(
                    "wakelock held across imminent tick delayMillis=$nextDelayMillis",
                    tag = "keepalive",
                )
                if (lease.expired && !pendingWakeLeaseExpiredLogged) {
                    // The operation's own budget is spent; the CPU stays only
                    // because the next tick - the one that will observe its
                    // terminal state - is already due.
                    pendingWakeLeaseExpiredLogged = true
                    logs.append(
                        "pending operation wake lease expired; CPU kept for the scheduled tick, durable recovery owns the operation",
                        tag = "scheduler-health",
                    )
                }
            }
            lease.expired -> {
                releaseWakeLock(reason = "pending-operation lease hard limit reached")
                if (!pendingWakeLeaseExpiredLogged) {
                    pendingWakeLeaseExpiredLogged = true
                    logs.append(
                        "pending operation wake lease expired; relying on alarm watchdog and durable recovery",
                        tag = "scheduler-health",
                    )
                }
            }
            else -> {
                releaseWakeLock(reason = "no pending operation")
                pendingWakeLeaseExpiredLogged = false
            }
        }
    }

    /**
     * Log why the previous hosting process ended, once per process start.
     *
     * Diagnostics must never be able to stop hosting, so every failure here is
     * swallowed: a missing attribution is a worse report, not a worse service.
     */
    private fun reportPreviousInterruption() {
        runCatching {
            val report = HostingInterruptionReport.of(
                runtime = hostingRuntime.snapshot(),
                exits = ProcessExitReader.read(this),
                nowMillis = System.currentTimeMillis(),
                mainProcessName = packageName,
                lastUpdateTimeMillis = ProcessExitReader.lastUpdateTimeMillis(this),
            )
            if (!report.interrupted) return@runCatching
            logs.append(
                report.summaryLine() +
                    "（attribution=${report.attribution}" +
                    " exitReason=${report.exitReasonCode ?: "未知"}）",
                tag = "scheduler-health",
            )
        }.onFailure { error ->
            logs.append(
                "后台中断归因读取失败：${error.message ?: error.javaClass.simpleName}",
                tag = "scheduler-health",
            )
        }
    }

    private fun requiredBackgroundPermissionsReady(): Boolean {
        return BackgroundHostingPermissionState.read(this).reliableHostingReady
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
            // Correctness cannot depend on one Android timing primitive:
            // - Handler is the low-latency path while this process is runnable.
            // - ELAPSED_REALTIME_WAKEUP is the watchdog if the OEM freezes the app or the
            //   device suspends between two business deadlines.
            handler.postDelayed(tickRunnable, requestedDelay)
            hostingRuntime.scheduled(
                nextWakeAtMillis = System.currentTimeMillis() + requestedDelay,
                tick = tickCount,
            )
            // Even an immediate follow-up gets a one-second system fallback.
            // The Handler normally wins and cancels it; if the process dies in
            // that tiny hand-over window, the alarm recreates the service.
            val alarmDelay = if (requestedDelay == 0L) {
                SchedulerTickPolicy.MIN_DELAY_MILLIS
            } else {
                requestedDelay
            }
            val alarmAt = if (Long.MAX_VALUE - now < alarmDelay) {
                Long.MAX_VALUE
            } else {
                now + alarmDelay
            }
            if (
                (SchedulerTickPolicy.shouldArmAlarmWatchdog(requestedDelay) || requestedDelay == 0L) &&
                alarmAt != Long.MAX_VALUE &&
                !scheduleWakeupAlarm(alarmAt)
            ) {
                logs.append(
                    "调度看门狗闹钟设置失败；下一次可运行时将由 Handler 补偿",
                    tag = "scheduler-health",
                )
            }
        }
    }

    private fun scheduleWakeupAlarm(triggerAtElapsedMillis: Long): Boolean = runCatching {
        scheduleWakeupAlarm(
            triggerAtElapsedMillis,
            schedulerWakeupIntent(triggerAtElapsedMillis),
        )
    }.getOrDefault(false)

    /**
     * Keeps a separate recovery trigger only while a Python operation is
     * executing. The normal deadline alarm is intentionally cancelled when a
     * tick starts, so this lease closes the otherwise unprotected kill window.
     */
    private fun armExecutionWatchdog() {
        val now = SystemClock.elapsedRealtime()
        val triggerAt = if (Long.MAX_VALUE - now < EXECUTION_WATCHDOG_DELAY_MILLIS) {
            Long.MAX_VALUE
        } else {
            now + EXECUTION_WATCHDOG_DELAY_MILLIS
        }
        if (
            triggerAt != Long.MAX_VALUE &&
            !scheduleWakeupAlarm(triggerAt, executionWatchdogIntent())
        ) {
            logs.append(
                "执行窗口恢复看门狗设置失败；将依赖前台服务 START_STICKY 和持久化 operation",
                tag = "scheduler-health",
            )
        }
    }

    private fun cancelExecutionWatchdog() {
        getSystemService(AlarmManager::class.java)?.cancel(executionWatchdogIntent())
    }

    private fun scheduleWakeupAlarm(
        triggerAtElapsedMillis: Long,
        intent: PendingIntent,
    ): Boolean = runCatching {
        val manager = getSystemService(AlarmManager::class.java)
            ?: return@runCatching false
        val exactAllowed = Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            runCatching { manager.canScheduleExactAlarms() }.getOrDefault(false)
        if (exactAllowed) {
            manager.setExactAndAllowWhileIdle(
                AlarmManager.ELAPSED_REALTIME_WAKEUP,
                triggerAtElapsedMillis,
                intent,
            )
        } else {
            manager.setAndAllowWhileIdle(
                AlarmManager.ELAPSED_REALTIME_WAKEUP,
                triggerAtElapsedMillis,
                intent,
            )
            if (!inexactAlarmWarningLogged) {
                inexactAlarmWarningLogged = true
                logs.append(
                    "尚未授予精确闹钟权限；看门狗暂用可延迟闹钟，请在攻略-后台运行设置中完成授权",
                    tag = "scheduler-health",
                )
            }
        }
        true
    }.getOrDefault(false)

    private fun armRecoveryAlarm(delayMillis: Long) {
        val delay = delayMillis.coerceAtLeast(1_000L)
        val nowElapsed = SystemClock.elapsedRealtime()
        val triggerAt = if (Long.MAX_VALUE - nowElapsed < delay) {
            Long.MAX_VALUE
        } else {
            nowElapsed + delay
        }
        hostingRuntime.scheduled(
            nextWakeAtMillis = System.currentTimeMillis() + delay,
            tick = tickCount,
        )
        if (!scheduleWakeupAlarm(triggerAt)) {
            logs.append("后台恢复闹钟设置失败；等待系统 START_STICKY 或下次用户打开应用", tag = "scheduler-health")
        }
    }

    private fun consumeAndRunScheduledTick(
        expectedAtElapsedMillis: Long,
        source: String,
    ) {
        val accepted = synchronized(tickScheduleLock) {
            if (
                !running ||
                expectedAtElapsedMillis == Long.MIN_VALUE ||
                scheduledTickAtElapsedMillis != expectedAtElapsedMillis
            ) {
                false
            } else {
                scheduledTickAtElapsedMillis = Long.MAX_VALUE
                true
            }
        }
        if (!accepted) return
        handler.removeCallbacks(tickRunnable)
        // Establish the execution recovery lease before removing the normal
        // deadline alarm. If the process is killed in this hand-over, at least
        // one system trigger remains armed and can recreate the service.
        armExecutionWatchdog()
        cancelScheduledWakeup(resetSchedule = false)
        val overdueMillis = (SystemClock.elapsedRealtime() - expectedAtElapsedMillis)
            .coerceAtLeast(0L)
        if (overdueMillis >= SchedulerTickPolicy.OVERDUE_LOG_THRESHOLD_MILLIS) {
            logs.append(
                "调度逾期 source=$source overdueMillis=$overdueMillis " +
                    "expectedElapsed=$expectedAtElapsedMillis actualElapsed=${SystemClock.elapsedRealtime()}",
                tag = "scheduler-health",
            )
        }
        tickCount += 1
        // The tick itself always gets a full window, whatever remains of the
        // lease that carried the CPU across the gap.
        renewWakeLock(TICK_WAKELOCK_TIMEOUT_MILLIS)
        runLocalSchedulerTick(tickCount)
    }

    private fun cancelScheduledWakeup(resetSchedule: Boolean = true) {
        getSystemService(AlarmManager::class.java)?.cancel(schedulerWakeupIntent())
        if (resetSchedule) scheduledTickAtElapsedMillis = Long.MAX_VALUE
    }

    private fun schedulerWakeupIntent(
        triggerAtElapsedMillis: Long = Long.MIN_VALUE,
    ): PendingIntent {
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val intent = Intent(this, AssistantForegroundService::class.java)
            .setAction(ACTION_SCHEDULED_TICK)
            .putExtra(EXTRA_SCHEDULED_AT_ELAPSED, triggerAtElapsedMillis)
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            PendingIntent.getForegroundService(this, SCHEDULER_WAKEUP_REQUEST_CODE, intent, flags)
        } else {
            PendingIntent.getService(this, SCHEDULER_WAKEUP_REQUEST_CODE, intent, flags)
        }
    }

    private fun executionWatchdogIntent(): PendingIntent {
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val intent = Intent(this, AssistantForegroundService::class.java)
            .setAction(ACTION_EXECUTION_WATCHDOG)
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            PendingIntent.getForegroundService(this, EXECUTION_WATCHDOG_REQUEST_CODE, intent, flags)
        } else {
            PendingIntent.getService(this, EXECUTION_WATCHDOG_REQUEST_CODE, intent, flags)
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
        // Record the blackout before anything else can fail: this journal is
        // the only evidence that hosting was up while the phone had no network,
        // which is what separates a vendor timed-Wi-Fi switch from a kill.
        recordNetworkAvailabilityChange(usable, transitionObserved = networkStateInitialized)
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

    /**
     * Journal one network availability change, and narrate a long blackout.
     *
     * Best-effort by construction: a diagnostic journal must never be able to
     * stop hosting, and a failed write only costs a worse report later.
     */
    private fun recordNetworkAvailabilityChange(usable: Boolean, transitionObserved: Boolean) {
        runCatching {
            val now = System.currentTimeMillis()
            if (!usable) {
                networkOutages.noteUnusable(now, transitionObserved)
                return@runCatching
            }
            val closed = networkOutages.noteUsable(now, transitionObserved) ?: return@runCatching
            val minutes = closed.durationMillis / 60_000L
            if (minutes < ScheduledNetworkOutageDetector.LONG_OUTAGE_MINUTES) return@runCatching
            // Worth the user's attention even before it becomes a pattern:
            // hosting ran the whole time and could not send a single request.
            logs.append(
                "手机断网约${minutes}分钟后已恢复，期间托管在运行但无法出征；" +
                    "如每天同一时间重复，请在攻略-后台运行设置查看处理方法",
                tag = "network",
                audience = LogAudience.USER,
            )
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
                "${BuildConfig.APP_NAME}本地调度",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "手机本地托管和任务调度状态"
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
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
            .setContentTitle(BuildConfig.APP_NAME)
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
        // A duplicate handler/alarm notification can arrive while the worker
        // owns the current execution lease. It must not release that lease or
        // cancel its watchdog; doing so would reopen the exact process-kill
        // window this watchdog is meant to cover.
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
                if (!requiredBackgroundPermissionsReady()) {
                    val permissionState = BackgroundHostingPermissionState.read(this)
                    logs.append(
                        permissionState.blockingIssueMessage(prefix = "后台托管已暂停")
                            ?.plus("；不再发送游戏请求")
                            ?: "后台托管已暂停：运行期间的必要权限被关闭；不再发送游戏请求",
                        tag = "scheduler-health",
                    )
                    handler.post {
                        if (running && !requiredBackgroundPermissionsReady()) {
                            stopLocalHosting(
                                reason = "required background permission revoked",
                                requestLogout = false,
                            )
                            stopSelf()
                        }
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
                val ownerGeneration = currentExecutionGeneration() ?: return@schedulerTick

                val exportedConfigs = configs.exportAll()
                val nowMillis = System.currentTimeMillis()
                restoreOrUpdateTaskSuppression(exportedConfigs, nowMillis)
                val validationGeneration = networkGeneration.get()
                val forcedValidation = forceSessionValidation
                val recovery = sessionRecovery.reconcile(nowMillis, forcedValidation)
                if (!running || currentExecutionGeneration() != ownerGeneration) {
                    return@schedulerTick
                }
                ranWork = forcedValidation || recovery.paused > 0 ||
                    recovery.degraded > 0 || recovery.relogged > 0
                if (forcedValidation && recovery.paused == 0 && recovery.waitingToRetry == 0 &&
                    networkUsable && networkGeneration.get() == validationGeneration
                ) {
                    forceSessionValidation = false
                }
                if (
                    forcedValidation || recovery.paused > 0 || recovery.degraded > 0 ||
                    recovery.waitingToRetry > 0 || recovery.relogged > 0
                ) {
                    logs.append(
                        "tick=$tick session_recovery online=${recovery.online} " +
                            "degraded=${recovery.degraded} paused=${recovery.paused} " +
                            "waiting=${recovery.waitingToRetry} relogged=${recovery.relogged}",
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
                    val configuredTypes = plan.tasks.map { it.type }.toMutableSet()
                    if (sharedGeneralMaintenanceEnabled(sharedAccountHabits(plan.session.accountId))) {
                        configuredTypes += TaskType.GENERAL
                    }
                    if (sharedDomesticEnabled(sharedAccountHabits(plan.session.accountId))) {
                        configuredTypes += TaskType.INTERNAL
                    }
                    if (sharedInventoryEnabled(sharedAccountHabits(plan.session.accountId))) {
                        configuredTypes += TaskType.INVENTORY
                    }
                    taskRuntimeStatuses.reconcileConfigured(
                        accountId = plan.session.accountId,
                        configuredTypes = configuredTypes,
                        nowMillis = nowMillis,
                        executionGeneration = ownerGeneration,
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
                val sharedResidentResults = runSharedResidentTicks(
                    allPlans,
                    tick,
                    ownerGeneration,
                )
                ranWork = ranWork || sharedResidentResults.any {
                    it.feature != null || it.requestSent
                }
                val legacyPlans = plans.map { plan ->
                    plan.copy(tasks = plan.tasks.filterNot {
                        it.type in SHARED_RESIDENT_TASK_TYPES
                    })
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
                        plans = legacyPlans,
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
                if (!running || currentExecutionGeneration() != ownerGeneration) {
                    logs.append(
                        "调度轮次=$tick 已越过执行代次边界，旧批次结果不再写回任务栈",
                        tag = "local-scheduler"
                    )
                    if (!running || !executionOwnerActive) {
                        taskRuntimeStatuses.markServiceStopped(
                            System.currentTimeMillis(),
                            "后台已停止：执行权已撤销",
                            preserveNextRunAt = false
                        )
                    }
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
                        TaskRuntimeStatusMapper.fromReport(report, decisionAtMillis, tick).copy(
                            executionGeneration = ownerGeneration,
                        )
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
                        if (errorNotifiedAccounts.add(terminal.accountId)) {
                            emitSharedHostErrorAlarm(
                                terminal.accountId,
                                "${terminal.type.userFacingName()}：${terminal.decision.summary()}",
                                "android-task-terminal",
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
                    sharedResidentResults.mapNotNull {
                        it.nextWakeAtMillis
                    }.minOrNull(),
                    sharedResidentWakeGate.earliestDeadlineMillis(
                        allPlans.map { it.session.accountId }.toSet()
                    ),
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
                accounts.listAccounts().filter { it.enabled }.forEach { account ->
                    emitSharedHostErrorAlarm(
                        account.id,
                        "后台调度异常：${t.message ?: t::class.java.simpleName}",
                        "android-scheduler",
                    )
                }
            } finally {
                // Keep the execution watchdog armed while Python still owns
                // an in-flight operation.  The normal deadline alarm is
                // recreated below, but cancelling both triggers in this
                // hand-over would reopen the exact OEM-kill window we are
                // trying to cover.  Once the operation reaches a terminal
                // state the next tick observes that fact and cancels the
                // watchdog.
                if (!pendingOperationWakeLease.snapshot(SystemClock.elapsedRealtime()).active) {
                    cancelExecutionWatchdog()
                } else {
                    armExecutionWatchdog()
                }
                val delay = synchronized(tickScheduleLock) {
                    schedulerBusy = false
                    if (immediateTickRequested) {
                        immediateTickRequested = false
                        0L
                    } else {
                        nextDelayMillis
                    }
                }
                val willScheduleNext =
                    running && executionOwnerActive && hostingPreferences.isEnabled()
                // Decide the CPU lease with the real gap in hand: a short gap
                // keeps the lock, a long one (or no follow-up) releases it.
                finishSchedulerWakeWindow(if (willScheduleNext) delay else null)
                if (willScheduleNext) {
                    hostingRuntime.heartbeat(
                        nowMillis = System.currentTimeMillis(),
                        tick = tick,
                        nextWakeAtMillis = System.currentTimeMillis() + delay,
                    )
                    scheduleNextTick(delay)
                }
            }
        }
    }

    private fun emitSharedHostErrorAlarm(
        accountId: Long,
        message: String,
        source: String,
    ) {
        runCatching {
            sharedPythonCore.emitHostAlarmError(
                accountId.toString(),
                message,
                source,
            )
        }.onFailure { error ->
            logs.append(
                "共享核心异常警报决策失败：${error.message ?: error.javaClass.simpleName}",
                tag = "alarm",
                accountId = accountId,
            )
        }
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

    private fun sharedAccountHabits(accountId: Long): org.json.JSONObject =
        LocalSettingsConfigMapper.accountHabits { featureId ->
            configs.loadFeatureConfig(accountId, featureId)
                ?.optJSONObject("values")
        }

    private fun sharedGeneralMaintenanceEnabled(habits: org.json.JSONObject): Boolean {
        val general = habits.optJSONObject("general") ?: return false
        return general.optBoolean("autoHeal", false) ||
            general.optBoolean("autoEnergy", false) ||
            general.optBoolean("keepFullLoyalty", false)
    }

    private fun sharedDomesticEnabled(habits: org.json.JSONObject): Boolean {
        val domestic = habits.optJSONObject("config")
            ?.optJSONObject("domestic") ?: return false
        return domestic.optBoolean("enabled", false) ||
            domestic.optBoolean("upgradeTechnology", false)
    }

    private fun sharedInventoryEnabled(habits: org.json.JSONObject): Boolean {
        val config = habits.optJSONObject("config") ?: return false
        val autoOpen = config.optBoolean("autoOpenEnabled", false) &&
            config.optJSONArray("autoOpenItemNames")?.length()?.let { it > 0 } == true
        val cleanup = config.optBoolean("cleanInventory", false) && (
            config.optString("discardItemNames").isNotBlank() ||
                config.optBoolean("discardEquipment", false)
            )
        return autoOpen || cleanup
    }

    private fun runSharedResidentTicks(
        plans: List<SavedTaskPlan>,
        tick: Int,
        ownerGeneration: String,
    ): List<SharedResidentTickResult> {
        val distinctPlans = plans.distinctBy { it.session.accountId }
        val activeAccountIds = distinctPlans.map { it.session.accountId }.toSet()
        sharedResidentWakeGate.retainAccounts(activeAccountIds)
        residentLiveness.retainAccounts(activeAccountIds)
        return distinctPlans.mapNotNull { plan ->
            val accountId = plan.session.accountId
            val startedAtMillis = System.currentTimeMillis()
            val wakePermit = sharedResidentWakeGate.permit(
                accountId,
                startedAtMillis,
            ) ?: run {
                // A gated tick produced no output at all, so an account that
                // had stopped scheduling looked exactly like an account with
                // nothing due.  One real account was completely idle for over
                // three hours before anything distinguished the two.
                residentLiveness.reportSilence(accountId, startedAtMillis)
                    ?.let { silentMillis ->
                        logs.append(
                            "常驻车道已静默${silentMillis / 60_000}分钟" +
                                " account=$accountId tick=$tick" +
                                " 门禁截止=${sharedResidentWakeGate.deadlineMillis(accountId)}" +
                                " 待人工确认=${sharedResidentWakeGate.awaitingAttention(accountId)}",
                            tag = "scheduler-health",
                            accountId = accountId,
                        )
                    }
                return@mapNotNull null
            }
            residentLiveness.recordTick(accountId, startedAtMillis)
            val habits = sharedAccountHabits(accountId)
            val result = sharedResidentAutomation.runOnce(
                accountId,
                habits,
                "android-resident-$accountId-$tick-$startedAtMillis",
            )
            if (!running || currentExecutionGeneration() != ownerGeneration) {
                logs.append(
                    "共享常驻 tick=$tick account=$accountId 已越过执行代次边界，丢弃旧结果",
                    tag = "shared-resident",
                    accountId = accountId,
                )
                return@mapNotNull null
            }
            result.operationId?.let { operationId ->
                pendingOperationWakeLease.observe(
                    operationId = operationId,
                    pending = result.state in PENDING_OPERATION_STATES,
                    nowElapsedMillis = SystemClock.elapsedRealtime(),
                )
            }
            sharedResidentWakeGate.record(
                result,
                System.currentTimeMillis(),
                wakePermit,
            )
            logs.append(
                "共享常驻 tick=$tick account=$accountId " +
                    "feature=${result.feature ?: "idle"} state=${result.state} " +
                    "via=${result.decidedVia ?: "?"} " +
                    (result.blockedFeatures?.let { "blocked=$it " } ?: "") +
                    (result.candidateFeatures?.let { "cand=$it " } ?: "") +
                    (result.isolatedFeatures?.let { "isolated=$it " } ?: "") +
                    (result.isolatedAttentionFeatures?.let { "attention=$it " } ?: "") +
                    (result.stalledFeatures?.let { "STALLED=$it " } ?: "") +
                    "nextWakeAt=${result.nextWakeAtMillis ?: "none"} " +
                    "message=${result.message}",
                tag = "shared-resident",
                accountId = accountId,
            )
            val resultType = SharedResidentTaskStatusMapper.typeFor(
                result.feature,
                result.dailyKey,
            )
            // A transport/configuration failure without feature evidence is
            // account-level health, not proof that every configured task
            // failed. Preserve the individual task states until the adapter
            // can attribute the failure to one concrete resident feature.
            val statusRows = linkedMapOf<TaskType, TaskRuntimeStatus>()
            resultType?.let { type ->
                statusRows[type] = TaskRuntimeStatus(
                    accountId = accountId,
                    type = type,
                    state = SharedResidentTaskStatusMapper.stateFor(result),
                    message = result.message,
                    updatedAtMillis = System.currentTimeMillis(),
                    nextRunAtMillis = result.taskNextWakeAtMillis
                        ?: result.nextWakeAtMillis,
                    tick = tick,
                    executionGeneration = ownerGeneration,
                    skipped = result.skipped,
                    skipReason = result.skipReason,
                    statusText = result.statusText,
                )
            }
            // `isolatedAttentionFeatures` is the subset of pending features
            // whose ledger still needs a human.  Ordinary read-only polling
            // also appears in `isolatedFeatures`, but must remain a cooldown,
            // not an error badge.  Persist each true hold as its own ERROR row
            // so the role/task and notice pages name the blocked feature
            // without turning the whole account offline.
            SharedResidentTaskStatusMapper.isolatedTypes(
                result.isolatedAttentionFeatures
            )
                .forEach { type ->
                    statusRows.putIfAbsent(
                        type,
                        TaskRuntimeStatus(
                            accountId = accountId,
                            type = type,
                            state = TaskRuntimeState.ERROR,
                            message = SharedResidentTaskStatusMapper.isolatedMessage(type),
                            updatedAtMillis = System.currentTimeMillis(),
                            nextRunAtMillis = null,
                            tick = tick,
                            executionGeneration = ownerGeneration,
                        ),
                    )
                }
            if (statusRows.isNotEmpty()) {
                taskRuntimeStatuses.upsertAll(statusRows.values.toList())
            }
            result
        }
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
        const val ACTION_EXECUTION_WATCHDOG = "com.example.dwpmclone.action.EXECUTION_WATCHDOG"
        const val ACTION_SCHEDULED_TICK = "com.example.dwpmclone.action.SCHEDULED_LOCAL_TICK"
        private const val CHANNEL_ID = "dwpm_clone_local_hosting"
        private const val NOTIFICATION_ID = 1001
        private const val SCHEDULER_WAKEUP_REQUEST_CODE = 1002
        private const val EXECUTION_WATCHDOG_REQUEST_CODE = 1003
        private const val TICK_WAKELOCK_TIMEOUT_MILLIS = 90_000L
        // The hard cap is a leak guard, so it sits just above the longest lease
        // the policy can legitimately ask for; a smaller cap would silently
        // truncate a hold across the longest named deadline.
        private const val MAX_TICK_WAKELOCK_TIMEOUT_MILLIS =
            SchedulerTickPolicy.MAX_WAKE_HOLD_TIMEOUT_MILLIS
        private const val PENDING_OPERATION_WAKE_LEASE_MILLIS = 2L * 60L * 1_000L
        private const val EXECUTION_WATCHDOG_DELAY_MILLIS = 2L * 60L * 1_000L
        private const val TASK_REMOVED_RESTART_DELAY_MILLIS = 5_000L
        private const val PROCESS_RESTART_DELAY_MILLIS = 10_000L
        private const val EXTRA_SCHEDULED_AT_ELAPSED =
            "com.example.dwpmclone.extra.SCHEDULED_AT_ELAPSED"
        private val SHARED_BRUSH_TASK_TYPES = setOf(
            TaskType.SHUA_HUANG,
            TaskType.BANDIT_PREFETCH,
        )
        private val SHARED_MINE_TASK_TYPES = setOf(
            TaskType.AUTO_MINING,
            TaskType.MINE_SEARCH,
            TaskType.MINE_PREFETCH,
        )
        private val SHARED_DAILY_TASK_TYPES = setOf(
            TaskType.DAILY,
            TaskType.DAILY_SIGN_IN,
            TaskType.DAILY_ARENA_COINS,
            TaskType.DAILY_DONATE,
            TaskType.DAILY_SALARY,
            TaskType.DAILY_NATIONAL_COLLECT,
            TaskType.DAILY_CITY_LORD_COLLECT,
            TaskType.DAILY_GENERAL_VISIT,
        )
        private val SHARED_RESIDENT_TASK_TYPES =
            SHARED_BRUSH_TASK_TYPES + SHARED_MINE_TASK_TYPES + setOf(
                TaskType.AUTO_LOOT,
                TaskType.LOSSLESS,
                TaskType.DUNGEON,
                TaskType.GENERAL,
                TaskType.SIX_MINISTRIES,
                TaskType.INTERNAL,
                TaskType.INVENTORY,
                TaskType.ALARM,
            ) + SHARED_DAILY_TASK_TYPES
        private val PENDING_OPERATION_STATES = setOf(
            "queued",
            "running",
            // A lost status response does not prove that the operation ended;
            // retain the short lease until a later read establishes a terminal
            // state.
            "status-unavailable",
        )
        @Volatile private var executionOwnerActive = false
        @Volatile private var executionGeneration: String? = null
        private val executionOwnerLock = Any()

        fun isExecutionOwnerActive(): Boolean = executionOwnerActive

        fun currentExecutionGeneration(): String? =
            executionGeneration.takeIf { executionOwnerActive }

        private fun activateExecutionOwner() = synchronized(executionOwnerLock) {
            if (!executionOwnerActive || executionGeneration == null) {
                executionGeneration = UUID.randomUUID().toString()
            }
            executionOwnerActive = true
        }

        private fun deactivateExecutionOwner() = synchronized(executionOwnerLock) {
            executionOwnerActive = false
            executionGeneration = null
        }

        fun start(context: Context) {
            LocalHostingPreferences(context).setEnabled(true)
            val intent = Intent(context, AssistantForegroundService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            deactivateExecutionOwner()
            LocalHostingPreferences(context).setEnabled(false)
            context.startService(Intent(context, AssistantForegroundService::class.java).setAction(ACTION_STOP))
        }

        fun refresh(context: Context) {
            if (!LocalHostingPreferences(context).isEnabled()) return
            val intent = Intent(context, AssistantForegroundService::class.java).setAction(ACTION_REFRESH)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun resumeIfEnabled(context: Context): Boolean {
            if (!LocalHostingPreferences(context).isEnabled()) return false
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

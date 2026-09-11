package com.example.dwpmclone.ui.web

import android.content.Context
import com.example.dwpmclone.data.local.ExpeditionTransactionRepository
import com.example.dwpmclone.data.local.AssistantBehaviorContractAssetLoader
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.RequestHealthRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.protocol.GameRequestHealthSink
import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.host.SharedPythonCoreHost
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.scheduler.SuspendRunner
import com.example.dwpmclone.domain.state.AccountOperationLockRegistry
import com.example.dwpmclone.service.AssistantForegroundService

/**
 * Single local entry point for foreground UI operations.
 *
 * The scheduler and the WebView must use the same protocol semantics. This runner therefore
 * constructs the same SessionAwareGameProtocolClient, applies the same account-level mutex to
 * mutating operations, and never creates a mock session for a real account. Explicit foreground
 * read-only requests may bypass the long-running scheduler mutex, matching the desktop API.
 */
class LocalProtocolOperationRunner(
    context: Context,
    private val accounts: LocalAccountRepository,
    private val logs: TaskLogRepository,
    private val requestHealth: RequestHealthRepository
) {
    private val appContext = context.applicationContext
    private val behaviorContract: AssistantBehaviorContract =
        AssistantBehaviorContractAssetLoader.load(appContext)
    private val sharedPythonCore = SharedPythonCoreHost.get(appContext)

    init {
        // The service installs the same sink during normal hosting. Installing it here also
        // keeps manual UI actions observable when the service has not been started yet.
        if (GameRequestHealthSink.writer == null) {
            GameRequestHealthSink.writer = { accountId, success, purpose, timeMillis ->
                requestHealth.record(accountId, success, purpose, timeMillis)
            }
        }
    }

    fun <T> execute(
        accountId: Long,
        label: String,
        block: suspend (GameSession, GameProtocolClient) -> ProtocolResult<T>
    ): ProtocolResult<T> = executeInternal(
        accountId = accountId,
        label = label,
        acquireAccountLock = true,
        block = block
    )

    /**
     * Runs an explicitly read-only UI query without rejecting it merely because the scheduler is
     * active for the account. This must never be used for an operation that changes game state.
     */
    fun <T> executeImmediateReadOnly(
        accountId: Long,
        label: String,
        block: suspend (GameSession, GameProtocolClient) -> ProtocolResult<T>
    ): ProtocolResult<T> = executeInternal(
        accountId = accountId,
        label = label,
        acquireAccountLock = false,
        lifecycleOwnedBySharedCore = false,
        block = block
    )

    /**
     * Read-only transport invoked by a shared Python operation after the shared lifecycle gate.
     * The local adapter still rechecks persisted start/session facts immediately before I/O. It
     * must never wait for a JVM account lock while Python is synchronously calling the host bridge;
     * after the lock is acquired, same-thread shared-account reads remain reentrant and local.
     */
    fun <T> executeSharedCoreReadOnly(
        accountId: Long,
        label: String,
        block: suspend (GameSession, GameProtocolClient) -> ProtocolResult<T>
    ): ProtocolResult<T> {
        // This method is entered synchronously from Python. Never block here while waiting for
        // the scheduler: the scheduler may hold this account lock and call shared Python while it
        // persists refreshed account metadata, which would otherwise create a JVM-lock/Python-GIL
        // cycle. A busy result is retried with cancellation-aware backoff by the Python operation
        // lane. Once acquired, executeInternal reloads account state and rechecks ownership and
        // Session immediately before I/O.
        if (!AccountOperationLockRegistry.tryAcquire(accountId)) {
            return ProtocolResult.Err(
                "LOCAL_ACCOUNT_BUSY",
                "账号网络执行通道正在处理后台任务，请继续等待",
                true
            )
        }
        return try {
            executeInternal(
                accountId = accountId,
                label = label,
                acquireAccountLock = false,
                lifecycleOwnedBySharedCore = true,
                block = block
            )
        } finally {
            AccountOperationLockRegistry.release(accountId)
        }
    }

    /** Mutation transport entered after Python acquired the JVM account lock in phase one. */
    fun <T> executeSharedCoreLockedMutation(
        accountId: Long,
        label: String,
        block: suspend (GameSession, GameProtocolClient) -> ProtocolResult<T>
    ): ProtocolResult<T> {
        check(AccountOperationLockRegistry.isHeldByCurrentThread(accountId)) {
            "共享 mutation 未持有账号执行锁"
        }
        return executeInternal(
            accountId = accountId,
            label = label,
            acquireAccountLock = false,
            lifecycleOwnedBySharedCore = true,
            block = block
        )
    }

    private fun <T> executeInternal(
        accountId: Long,
        label: String,
        acquireAccountLock: Boolean,
        lifecycleOwnedBySharedCore: Boolean = false,
        block: suspend (GameSession, GameProtocolClient) -> ProtocolResult<T>
    ): ProtocolResult<T> {
        val account = accounts.get(accountId)
            ?: return ProtocolResult.Err("LOCAL_ACCOUNT_NOT_FOUND", "账号不存在：$accountId", false)
        val session = account.session
            ?: return ProtocolResult.Err("LOCAL_SESSION_MISSING", "账号尚未完成真实登录", false)
        if (lifecycleOwnedBySharedCore) {
            if (
                !AssistantForegroundService.isExecutionOwnerActive() ||
                !account.enabled ||
                session.sourceMode != 1
            ) {
                return ProtocolResult.Err(
                    "LOCAL_ACCOUNT_NOT_RUNNING",
                    "共享核心执行前 Android 执行所有者已停止、账号已停止或 Session 已失效",
                    false
                )
            }
        } else {
            val lifecycle = sharedPythonCore.accountLifecycleDecision(
                accountEnabled = account.enabled,
                executionOwnerActive = AssistantForegroundService.isExecutionOwnerActive(),
                loginState = account.loginState,
                sourceMode = session.sourceMode,
                forceValidation = false,
                lastValidatedAtMillis = session.channelExtra["lastValidatedAt"]?.toLongOrNull(),
                nowMillis = System.currentTimeMillis()
            )
            if (!lifecycle.mayUseLiveSession) {
                return ProtocolResult.Err(
                    "LOCAL_ACCOUNT_NOT_RUNNING",
                    "当前账号未启动且未在线，已拒绝发送游戏请求",
                    false
                )
            }
        }
        if (acquireAccountLock && !AccountOperationLockRegistry.tryAcquire(accountId)) {
            return ProtocolResult.Err(
                "LOCAL_ACCOUNT_BUSY",
                "后台正在执行该账号的任务，请稍后再试",
                true
            )
        }
        GameRequestHealthSink.bindAccount(accountId)
        return try {
            logs.append("本地手动操作开始：$label", tag = "manual-operation", accountId = accountId)
            val client = SessionAwareGameProtocolClient(
                behaviorContract = behaviorContract,
                expeditionTransactionStore = ExpeditionTransactionRepository(appContext),
                actionAudit = { message -> logs.append(message, tag = "real-action", accountId = accountId) },
                sessionExtraSink = { id, updates ->
                    val current = accounts.get(id)
                    val currentSession = current?.session
                    if (current != null && currentSession != null) {
                        accounts.upsert(current.copy(session = currentSession.copy(
                            channelExtra = currentSession.channelExtra + updates
                        )))
                    }
                }
            )
            // Manual UI operations use the same real session as the scheduler, but they do
            // not pass through SavedConfigTaskPlanFactory (where the read-only map gate and
            // recovered one-general formation hint are normally attached).  Add only those
            // deterministic local hints here; mutation scopes and credentials remain exactly
            // those from the persisted login session.
            val operationSession = session.copy(
                channelExtra = session.channelExtra + mapOf(
                    "recoveredReadOnlyLiveGate" to "true",
                    "allowRecoveredGeneralFallbackFormation" to "true",
                    "inventoryLiveRefreshAllowed" to "true"
                )
            )
            val result = SuspendRunner.run { block(operationSession, client) }
            when (result) {
                is ProtocolResult.Ok -> logs.append(
                    "本地手动操作完成：$label",
                    tag = "manual-operation",
                    accountId = accountId
                )
                is ProtocolResult.Err -> logs.append(
                    "本地手动操作失败：$label code=${result.code} message=${result.message}",
                    tag = "manual-operation",
                    accountId = accountId
                )
            }
            result
        } catch (error: Throwable) {
            logs.append("本地手动操作异常：$label ${error.message}", tag = "manual-operation", accountId = accountId)
            ProtocolResult.Err("LOCAL_OPERATION_EXCEPTION", "$label：${error.message ?: error::class.java.simpleName}", true)
        } finally {
            GameRequestHealthSink.clearAccount()
            if (acquireAccountLock) {
                AccountOperationLockRegistry.release(accountId)
            }
        }
    }
}

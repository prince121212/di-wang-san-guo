package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.FormationRuntimeStatus
import java.util.UUID
import java.util.concurrent.CancellationException

/**
 * The caller revoked automation ownership before a network request started.
 *
 * This is deliberately different from an I/O failure: the game server cannot have accepted
 * the request, so an expedition send guard must be deleted instead of being left UNCERTAIN.
 */
class ExecutionRevokedBeforeNetworkException(
    val phase: String
) : IllegalStateException("后台执行权已撤销，已取消请求：$phase")

enum class ExpeditionTransactionState {
    SENDING,
    UNCERTAIN,
    ACCEPTED
}

data class ExpeditionTransactionRecord(
    val id: String,
    val accountId: Long,
    val action: String,
    val targetKey: String,
    val generalIds: List<Long>,
    val state: ExpeditionTransactionState,
    val createdAtMillis: Long,
    val updatedAtMillis: Long,
    val reason: String
)

enum class ExpeditionSendDisposition {
    ACCEPTED,
    REJECTED,
    UNCERTAIN
}

/** Result of exactly one state-changing expedition request. */
data class ExpeditionSendResult<T>(
    val result: ProtocolResult<T>,
    val disposition: ExpeditionSendDisposition,
    val reason: String
) {
    companion object {
        fun <T> accepted(result: ProtocolResult<T>, reason: String): ExpeditionSendResult<T> =
            ExpeditionSendResult(result, ExpeditionSendDisposition.ACCEPTED, reason)

        fun <T> rejected(result: ProtocolResult<T>, reason: String): ExpeditionSendResult<T> =
            ExpeditionSendResult(result, ExpeditionSendDisposition.REJECTED, reason)

        fun <T> uncertain(result: ProtocolResult<T>, reason: String): ExpeditionSendResult<T> =
            ExpeditionSendResult(result, ExpeditionSendDisposition.UNCERTAIN, reason)
    }
}

/** Implementations must make [save] durable before returning. */
interface ExpeditionTransactionStore {
    fun list(accountId: Long): List<ExpeditionTransactionRecord>
    fun save(record: ExpeditionTransactionRecord)
    fun delete(recordId: String)
    fun deleteAccount(accountId: Long)
}

class InMemoryExpeditionTransactionStore : ExpeditionTransactionStore {
    private val records = linkedMapOf<String, ExpeditionTransactionRecord>()

    @Synchronized
    override fun list(accountId: Long): List<ExpeditionTransactionRecord> =
        records.values.filter { it.accountId == accountId }

    @Synchronized
    override fun save(record: ExpeditionTransactionRecord) {
        records[record.id] = record
    }

    @Synchronized
    override fun delete(recordId: String) {
        records.remove(recordId)
    }

    @Synchronized
    override fun deleteAccount(accountId: Long) {
        records.entries.removeIf { it.value.accountId == accountId }
    }
}

/** Durable idempotency coordinator for real expedition sends. */
class ExpeditionTransactionCoordinator(
    private val store: ExpeditionTransactionStore,
    private val nowMillis: () -> Long = System::currentTimeMillis
) {
    /** Latest durable send guard for recovering an interrupted task after process/login restart. */
    @Synchronized
    fun latestUnresolved(accountId: Long, action: String): ExpeditionTransactionRecord? =
        store.list(accountId)
            .filter { it.action == action }
            .maxByOrNull { it.createdAtMillis }

    /** A server-confirmed settlement closes the send guard immediately. */
    @Synchronized
    fun resolve(accountId: Long, action: String) {
        store.list(accountId)
            .filter { it.action == action }
            .forEach { store.delete(it.id) }
    }

    @Synchronized
    fun begin(
        accountId: Long,
        action: String,
        targetKey: String,
        snapshot: ExpeditionPreflightSnapshot
    ): ProtocolResult<ExpeditionTransactionRecord> {
        require(accountId > 0L) { "账号 ID 无效" }
        require(action.isNotBlank()) { "出征动作不能为空" }
        require(snapshot.generalIds.isNotEmpty()) { "出征将领不能为空" }
        reconcile(accountId, snapshot)
        val conflict = store.list(accountId)
            .firstOrNull { record -> record.generalIds.any(snapshot.generalIds::contains) }
        if (conflict != null) {
            return ProtocolResult.Err(
                "EXPEDITION_TRANSACTION_UNRESOLVED",
                "${conflict.action}仍处于${conflict.state.name}，已阻止${action}重复使用将领",
                retryable = true
            )
        }
        val now = nowMillis()
        val record = ExpeditionTransactionRecord(
            id = UUID.randomUUID().toString(),
            accountId = accountId,
            action = action.take(80),
            targetKey = targetKey.take(200),
            generalIds = snapshot.generalIds.distinct(),
            state = ExpeditionTransactionState.SENDING,
            createdAtMillis = now,
            updatedAtMillis = now,
            reason = "durably recorded before network send"
        )
        store.save(record)
        return ProtocolResult.Ok(record)
    }

    /**
     * Persists the guard before invoking [send], then resolves it from explicit evidence.
     * Cancellation is rethrown after recording an uncertain outcome so task shutdown stays
     * cooperative without allowing a reconstructed client to repeat the request.
     */
    suspend fun <T> execute(
        accountId: Long,
        action: String,
        targetKey: String,
        snapshot: ExpeditionPreflightSnapshot,
        exceptionCode: String,
        exceptionLabel: String,
        send: suspend () -> ExpeditionSendResult<T>
    ): ProtocolResult<T> {
        val record = when (val started = begin(accountId, action, targetKey, snapshot)) {
            is ProtocolResult.Ok -> started.value
            is ProtocolResult.Err -> return started
        }
        return try {
            val completed = send()
            when (completed.disposition) {
                ExpeditionSendDisposition.ACCEPTED -> markAccepted(record, completed.reason)
                ExpeditionSendDisposition.REJECTED -> markRejected(record)
                ExpeditionSendDisposition.UNCERTAIN -> markUncertain(record, completed.reason)
            }
            completed.result
        } catch (cancelled: CancellationException) {
            markUncertain(record, "cancelled during network send: ${cancelled.message.orEmpty()}")
            throw cancelled
        } catch (revoked: ExecutionRevokedBeforeNetworkException) {
            // The shared protocol boundary checks ownership before opening the connection (or
            // invoking an injected transport), so this request definitely never reached the
            // server. Keeping an UNCERTAIN record here would incorrectly freeze the generals.
            markRejected(record)
            ProtocolResult.Err(
                "EXECUTION_REVOKED",
                revoked.message ?: "后台执行权已撤销，$exceptionLabel 已取消",
                retryable = false
            )
        } catch (error: Throwable) {
            markUncertain(record, "network send exception: ${error::class.java.simpleName}: ${error.message.orEmpty()}")
            ProtocolResult.Err(
                exceptionCode,
                "$exceptionLabel：${error.message ?: error::class.java.simpleName}",
                retryable = true
            )
        }
    }

    @Synchronized
    fun markAccepted(record: ExpeditionTransactionRecord, reason: String) {
        update(record, ExpeditionTransactionState.ACCEPTED, reason)
    }

    @Synchronized
    fun markUncertain(record: ExpeditionTransactionRecord, reason: String) {
        update(record, ExpeditionTransactionState.UNCERTAIN, reason)
    }

    @Synchronized
    fun markRejected(record: ExpeditionTransactionRecord) {
        store.delete(record.id)
    }

    @Synchronized
    fun reconcile(accountId: Long, snapshot: ExpeditionPreflightSnapshot) {
        val observedAt = snapshot.observedAtMillis ?: return
        val generalById = snapshot.generals.associateBy { it.id }
        val records = store.list(accountId)
            .filter { record -> record.generalIds.all(generalById::containsKey) }
        for (record in records) {
            if (observedAt <= record.createdAtMillis) continue
            val allGeneralsIdle = record.generalIds.all { generalById[it]?.status == 0 }
            val allFormationsIdle = record.generalIds.all { generalId ->
                snapshot.formations.any { formation ->
                    (formation.id == generalId || generalId in formation.generalIds) &&
                        formation.status == FormationRuntimeStatus.IDLE
                }
            }
            val idle = allGeneralsIdle && allFormationsIdle
            if (!idle) {
                if (record.state != ExpeditionTransactionState.ACCEPTED) {
                    update(record, ExpeditionTransactionState.ACCEPTED, "fresh server state shows expedition busy")
                }
                continue
            }
            val minimumAge = when (record.state) {
                ExpeditionTransactionState.ACCEPTED -> ACCEPTED_IDLE_CONFIRM_MILLIS
                ExpeditionTransactionState.SENDING,
                ExpeditionTransactionState.UNCERTAIN -> UNCERTAIN_IDLE_CONFIRM_MILLIS
            }
            if (observedAt - record.createdAtMillis >= minimumAge) {
                store.delete(record.id)
            }
        }
    }

    @Synchronized
    fun deleteAccount(accountId: Long) {
        store.deleteAccount(accountId)
    }

    private fun update(
        record: ExpeditionTransactionRecord,
        state: ExpeditionTransactionState,
        reason: String
    ) {
        store.save(
            record.copy(
                state = state,
                updatedAtMillis = nowMillis(),
                reason = reason.take(500)
            )
        )
    }

    companion object {
        const val ACCEPTED_IDLE_CONFIRM_MILLIS = 10_000L
        const val UNCERTAIN_IDLE_CONFIRM_MILLIS = 120_000L
    }
}

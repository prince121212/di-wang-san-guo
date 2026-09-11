package com.example.dwpmclone.host

/**
 * Per-account wake ownership for the blocking shared resident adapter.
 *
 * Other Android scheduler lanes may wake the foreground service before the
 * Python core's business deadline. Those wakeups must not resubmit the same
 * resident operation.
 *
 * A result needing attention used to hold the account until an explicit start
 * or configuration refresh cleared the gate. That indefinite hold was both
 * redundant and dangerous. Redundant because replay safety is owned by the
 * core's durable send-boundary ledger, which refuses to replay an ambiguous
 * mutation on its own and reports the feature as isolated; a tick is only a
 * read-only decision, so blocking every tick protects nothing the core was not
 * already protecting. Dangerous because a conclusion with no expiry and no
 * re-evaluation outlives its cause: one real account sat completely idle for
 * over three hours, with no log line saying why, after a single definitive
 * item rejection. The hold is therefore bounded, and the core decides afresh
 * on each tick what may actually run.
 */
class SharedResidentWakeGate(
    private val minimumIntervalMillis: Long = 1_000L,
    private val store: ResidentWakeStateStore? = null,
    private val attentionRetryMillis: Long = ATTENTION_RETRY_MILLIS,
) {
    private data class AccountWake(
        val nextWakeAtMillis: Long?,
        val pausedForAttention: Boolean,
    )

    private val wakes = mutableMapOf<Long, AccountWake>()
    private var generation = 0L

    init {
        require(minimumIntervalMillis > 0L) {
            "minimumIntervalMillis must be positive"
        }
        store?.snapshot()?.forEach { (accountId, state) ->
            wakes[accountId] = AccountWake(
                // A stored indefinite hold was written by a build that could
                // not release it. Reading it back as "due now" is what lets an
                // account that was already stuck resume by itself.
                nextWakeAtMillis = state.nextWakeAtMillis,
                pausedForAttention = state.pausedForAttention,
            )
        }
    }

    @Synchronized
    fun shouldRun(accountId: Long, nowMillis: Long): Boolean =
        permit(accountId, nowMillis) != null

    /** Returns a generation token so an in-flight pre-refresh result stays stale. */
    @Synchronized
    fun permit(accountId: Long, nowMillis: Long): Long? {
        val wake = wakes[accountId]
        // Only a deadline gates a tick. `pausedForAttention` is retained as a
        // report of what the last tick concluded, never as an indefinite stop.
        if (wake?.nextWakeAtMillis?.let { nowMillis < it } == true) return null
        return generation
    }

    /** True while the last recorded tick for this account asked for a human. */
    @Synchronized
    fun awaitingAttention(accountId: Long): Boolean =
        wakes[accountId]?.pausedForAttention == true

    /** The deadline currently gating this account, for reporting only. */
    @Synchronized
    fun deadlineMillis(accountId: Long): Long? = wakes[accountId]?.nextWakeAtMillis

    @Synchronized
    fun record(
        result: SharedResidentTickResult,
        completedAtMillis: Long,
        permitGeneration: Long = generation,
    ) {
        if (permitGeneration != generation) return
        if (result.requiresAttention) {
            // Back off, do not stop. The next tick costs one read-only
            // decision, and it is the core - not this gate - that knows
            // whether anything is safe to run.
            val state = AccountWake(
                nextWakeAtMillis = completedAtMillis + attentionRetryMillis,
                pausedForAttention = true,
            )
            wakes[result.accountId] = state
            store?.put(result.accountId, state.toPersisted())
            return
        }
        val requested = result.nextWakeAtMillis
        if (requested == null) {
            wakes.remove(result.accountId)
            store?.remove(result.accountId)
            return
        }
        val minimumWake = if (
            completedAtMillis > Long.MAX_VALUE - minimumIntervalMillis
        ) {
            Long.MAX_VALUE
        } else {
            completedAtMillis + minimumIntervalMillis
        }
        val state = AccountWake(
            nextWakeAtMillis = maxOf(requested, minimumWake),
            pausedForAttention = false,
        )
        wakes[result.accountId] = state
        store?.put(result.accountId, state.toPersisted())
    }

    @Synchronized
    fun earliestDeadlineMillis(activeAccountIds: Set<Long>): Long? = wakes
        .asSequence()
        .filter { (accountId, _) -> accountId in activeAccountIds }
        .mapNotNull { (_, wake) -> wake.nextWakeAtMillis }
        .minOrNull()

    @Synchronized
    fun retainAccounts(activeAccountIds: Set<Long>) {
        wakes.keys.retainAll(activeAccountIds)
        store?.retainAccounts(activeAccountIds)
    }

    @Synchronized
    fun clear() {
        wakes.clear()
        generation += 1L
        store?.clear()
    }

    @Synchronized
    fun clear(accountId: Long) {
        wakes.remove(accountId)
        generation += 1L
        store?.remove(accountId)
    }

    private fun AccountWake.toPersisted(): ResidentWakeState = ResidentWakeState(
        nextWakeAtMillis = nextWakeAtMillis,
        pausedForAttention = pausedForAttention,
    )

    companion object {
        /** How long an attention result holds the account before it retries. */
        const val ATTENTION_RETRY_MILLIS = 5L * 60L * 1_000L
    }
}

package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.TaskType

/**
 * Keeps task-local Stop decisions stopped across foreground-service ticks.
 *
 * Saved configuration is rebuilt every tick. Without this registry a stopped task would
 * be recreated five seconds later. Any configuration signature change clears suppression,
 * which is equivalent to the desktop behavior of saving a new task configuration.
 */
class TaskRunSuppressionRegistry {
    private val stopped = linkedSetOf<Pair<Long, TaskType>>()
    private val nextRunAtMillis = linkedMapOf<Pair<Long, TaskType>, Long>()
    private var configSignature: String? = null

    @Synchronized
    fun onConfiguration(signature: String) {
        if (configSignature != signature) {
            configSignature = signature
            stopped.clear()
            nextRunAtMillis.clear()
        }
    }

    @Synchronized
    fun suppress(report: TaskLocalStopReport) {
        val key = report.accountId to report.type
        stopped += key
        nextRunAtMillis.remove(key)
    }

    @Synchronized
    fun record(report: TaskRunReport, nowMillis: Long = System.currentTimeMillis()) {
        val key = report.accountId to report.type
        when (val decision = report.decisions.lastOrNull()) {
            is com.example.dwpmclone.domain.protocol.TaskDecision.Sleep -> {
                stopped.remove(key)
                nextRunAtMillis[key] = safeAdd(nowMillis, decision.millis)
            }
            is com.example.dwpmclone.domain.protocol.TaskDecision.RetryAfter -> {
                stopped.remove(key)
                nextRunAtMillis[key] = safeAdd(nowMillis, decision.millis)
            }
            is com.example.dwpmclone.domain.protocol.TaskDecision.Stop -> {
                stopped += key
                nextRunAtMillis.remove(key)
            }
            is com.example.dwpmclone.domain.protocol.TaskDecision.NeedRelogin -> {
                nextRunAtMillis.remove(key)
            }
            com.example.dwpmclone.domain.protocol.TaskDecision.Continue -> {
                stopped.remove(key)
                nextRunAtMillis.remove(key)
            }
            null -> Unit
        }
    }

    @Synchronized
    fun filter(
        accountId: Long,
        tasks: List<AssistantTask<*>>,
        nowMillis: Long = System.currentTimeMillis()
    ): List<AssistantTask<*>> =
        tasks.filter { task ->
            val key = accountId to task.type
            key !in stopped && (nextRunAtMillis[key] ?: Long.MIN_VALUE) <= nowMillis
        }

    @Synchronized
    fun nextRunAt(accountId: Long, type: TaskType): Long? =
        nextRunAtMillis[accountId to type]

    private fun safeAdd(nowMillis: Long, delayMillis: Long): Long {
        val delay = delayMillis.coerceAtLeast(0L)
        return if (Long.MAX_VALUE - nowMillis < delay) Long.MAX_VALUE else nowMillis + delay
    }
}

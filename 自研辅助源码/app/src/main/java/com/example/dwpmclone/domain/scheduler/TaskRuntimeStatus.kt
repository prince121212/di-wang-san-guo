package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType

enum class TaskRuntimeState {
    WAITING,
    RUNNING,
    SLEEPING,
    RETRYING,
    STOPPED,
    NEED_RELOGIN,
    ERROR,
    SERVICE_STOPPED,
}

data class TaskRuntimeStatus(
    val accountId: Long,
    val type: TaskType,
    val state: TaskRuntimeState,
    val message: String,
    val updatedAtMillis: Long,
    val nextRunAtMillis: Long? = null,
    val tick: Int? = null,
) {
    fun displayText(nowMillis: Long = System.currentTimeMillis()): String = when (state) {
        TaskRuntimeState.WAITING -> "等待调度"
        TaskRuntimeState.RUNNING -> "执行中"
        TaskRuntimeState.SLEEPING -> nextRunAtMillis?.let {
            val seconds = ((it - nowMillis).coerceAtLeast(0L) + 999L) / 1_000L
            "等待 ${seconds}秒"
        } ?: "等待下次执行"
        TaskRuntimeState.RETRYING -> nextRunAtMillis?.let {
            val seconds = ((it - nowMillis).coerceAtLeast(0L) + 999L) / 1_000L
            "重试倒计时 ${seconds}秒"
        } ?: "等待重试"
        TaskRuntimeState.STOPPED -> "已停止"
        TaskRuntimeState.NEED_RELOGIN -> "需要重新登录"
        TaskRuntimeState.ERROR -> "执行异常"
        TaskRuntimeState.SERVICE_STOPPED -> "后台未运行"
    }
}

object TaskRuntimeStatusMapper {
    fun fromReport(
        report: TaskRunReport,
        nowMillis: Long,
        tick: Int? = null
    ): TaskRuntimeStatus {
        val decision = report.decisions.lastOrNull()
        val recoveredError = !report.error.isNullOrBlank()
        val state = when {
            recoveredError && decision !is TaskDecision.Sleep &&
                decision !is TaskDecision.RetryAfter &&
                decision !is TaskDecision.NeedRelogin -> TaskRuntimeState.ERROR
            decision == TaskDecision.Continue -> TaskRuntimeState.RUNNING
            decision is TaskDecision.Sleep && decision.keepRunning -> TaskRuntimeState.RUNNING
            decision is TaskDecision.Sleep -> TaskRuntimeState.SLEEPING
            decision is TaskDecision.RetryAfter -> TaskRuntimeState.RETRYING
            decision is TaskDecision.Stop -> TaskRuntimeState.STOPPED
            decision is TaskDecision.NeedRelogin -> TaskRuntimeState.NEED_RELOGIN
            else -> TaskRuntimeState.WAITING
        }
        val nextRun = when (decision) {
            is TaskDecision.Sleep -> safeAdd(nowMillis, decision.millis)
            is TaskDecision.RetryAfter -> safeAdd(nowMillis, decision.millis)
            else -> null
        }
        val decisionMessage = when (decision) {
            TaskDecision.Continue -> "任务本轮继续"
            is TaskDecision.Sleep -> decision.reason?.takeIf(String::isNotBlank)
                ?: if (decision.keepRunning) "任务执行中，${decision.millis}毫秒后刷新" else "本轮完成，等待${decision.millis}毫秒"
            is TaskDecision.RetryAfter -> decision.reason?.takeIf(String::isNotBlank)
                ?: "本轮需要重试：${decision.millis}毫秒后"
            is TaskDecision.Stop -> decision.reason
            is TaskDecision.NeedRelogin -> decision.reason
            null -> "尚未产生调度决策"
        }
        val message = if (recoveredError) {
            if (state == TaskRuntimeState.ERROR) report.error!!
            else "任务异常：${report.error}；已安排恢复：$decisionMessage"
        } else {
            decisionMessage
        }
        return TaskRuntimeStatus(
            report.accountId,
            report.type,
            state,
            message,
            nowMillis,
            nextRun,
            tick
        )
    }

    private fun safeAdd(nowMillis: Long, delayMillis: Long): Long {
        val delay = delayMillis.coerceAtLeast(0L)
        return if (Long.MAX_VALUE - nowMillis < delay) Long.MAX_VALUE else nowMillis + delay
    }
}

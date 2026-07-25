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
        if (!report.error.isNullOrBlank()) {
            return TaskRuntimeStatus(
                report.accountId,
                report.type,
                TaskRuntimeState.ERROR,
                report.error,
                nowMillis,
                tick = tick
            )
        }
        val decision = report.decisions.lastOrNull()
        val state = when (decision) {
            TaskDecision.Continue -> TaskRuntimeState.RUNNING
            is TaskDecision.Sleep -> TaskRuntimeState.SLEEPING
            is TaskDecision.RetryAfter -> TaskRuntimeState.RETRYING
            is TaskDecision.Stop -> TaskRuntimeState.STOPPED
            is TaskDecision.NeedRelogin -> TaskRuntimeState.NEED_RELOGIN
            null -> TaskRuntimeState.WAITING
        }
        val nextRun = when (decision) {
            is TaskDecision.Sleep -> safeAdd(nowMillis, decision.millis)
            is TaskDecision.RetryAfter -> safeAdd(nowMillis, decision.millis)
            else -> null
        }
        val message = when (decision) {
            TaskDecision.Continue -> "任务本轮继续"
            is TaskDecision.Sleep -> "本轮完成，等待${decision.millis}毫秒"
            is TaskDecision.RetryAfter -> "本轮需要重试：${decision.millis}毫秒后"
            is TaskDecision.Stop -> decision.reason
            is TaskDecision.NeedRelogin -> decision.reason
            null -> "尚未产生调度决策"
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

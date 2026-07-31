package com.example.dwpmclone.ui.web

import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.scheduler.TaskRuntimeState
import com.example.dwpmclone.domain.scheduler.TaskRuntimeStatus

internal data class LocalTaskPresentationSpec(
    val key: String,
    val name: String,
    val category: String,
    val completionKey: String? = null
)

/** Shared-Web presentation vocabulary for persisted Android scheduler states. */
internal object LocalTaskPresentation {
    val residentSpecs = listOf(
        LocalTaskPresentationSpec("mine", "打矿", "resident"),
        LocalTaskPresentationSpec("lossless", "无损", "resident"),
        LocalTaskPresentationSpec("brushYellow", "刷黄", "resident"),
        LocalTaskPresentationSpec("raid", "掠夺", "resident"),
        LocalTaskPresentationSpec("dungeon", "副本", "resident"),
        LocalTaskPresentationSpec("ministry", "六部", "resident")
    )

    val dailySpecs = listOf(
        LocalTaskPresentationSpec("autoSignIn", "自动签到", "daily", "autoSignIn"),
        LocalTaskPresentationSpec("arenaCoins", "领竞技币", "daily", "arenaCoins"),
        LocalTaskPresentationSpec("autoDonate", "自动捐献", "daily", "autoDonate"),
        LocalTaskPresentationSpec("salary", "领取俸禄", "daily", "salary"),
        LocalTaskPresentationSpec("nationalCollect", "国家征收", "daily", "nationalCollect"),
        LocalTaskPresentationSpec("cityLordCollect", "城主征收", "daily", "cityLordCollect"),
        LocalTaskPresentationSpec("generalVisit", "名将拜访", "daily", "generalVisit")
    )

    fun spec(type: TaskType): LocalTaskPresentationSpec = when (type) {
        TaskType.DAILY_SIGN_IN -> daily("autoSignIn")
        TaskType.DAILY_ARENA_COINS -> daily("arenaCoins")
        TaskType.DAILY_DONATE -> daily("autoDonate")
        TaskType.DAILY_SALARY -> daily("salary")
        TaskType.DAILY_NATIONAL_COLLECT -> daily("nationalCollect")
        TaskType.DAILY_CITY_LORD_COLLECT -> daily("cityLordCollect")
        TaskType.DAILY_GENERAL_VISIT -> daily("generalVisit")
        TaskType.SHUA_HUANG -> resident("brushYellow")
        TaskType.BANDIT_PREFETCH -> LocalTaskPresentationSpec("banditPrefetch", "闲时找山贼", "hidden")
        TaskType.MINE_SEARCH, TaskType.AUTO_MINING -> resident("mine")
        TaskType.MINE_PREFETCH -> LocalTaskPresentationSpec("minePrefetch", "闲时找资源点", "hidden")
        TaskType.DUNGEON -> resident("dungeon")
        TaskType.AUTO_LOOT -> resident("raid")
        TaskType.LOSSLESS -> resident("lossless")
        TaskType.SIX_MINISTRIES -> resident("ministry")
        TaskType.STATE_REFRESH -> LocalTaskPresentationSpec("stateRefresh", "角色军情刷新", "other")
        TaskType.FORMATION -> LocalTaskPresentationSpec("formations", "配兵", "military")
        TaskType.GENERAL -> LocalTaskPresentationSpec("generalMaintenance", "将领维护", "daily")
        TaskType.FOOD_TO_COPPER -> LocalTaskPresentationSpec("foodToCopper", "粮食转铜", "daily")
        TaskType.INTERNAL -> LocalTaskPresentationSpec("autoDomestic", "自动内政", "daily")
        TaskType.INVENTORY -> LocalTaskPresentationSpec("inventory", "背包整理", "daily")
        TaskType.ALARM -> LocalTaskPresentationSpec("alarm", "警报/军情", "other")
        TaskType.DAILY -> LocalTaskPresentationSpec("daily", "日常任务", "daily")
    }

    fun schedulerState(
        status: TaskRuntimeStatus?,
        completed: Boolean = false,
        nowMillis: Long = System.currentTimeMillis()
    ): String = when {
        status == null -> if (completed) "daily_done" else "idle"
        completed && status.state == TaskRuntimeState.SLEEPING -> "daily_done"
        status.state == TaskRuntimeState.WAITING -> "queued"
        status.state == TaskRuntimeState.RUNNING -> "running"
        status.state == TaskRuntimeState.SLEEPING -> if (
            status.nextRunAtMillis?.let { it <= nowMillis } == true
        ) "queued" else "cooldown"
        // A retry deadline means the instruction remains in the executable queue.
        // Desktop uses waiting_target only for an explicit target-search state.
        status.state == TaskRuntimeState.RETRYING -> "queued"
        status.state == TaskRuntimeState.NEED_RELOGIN -> "waiting_account"
        status.state == TaskRuntimeState.ERROR -> "error"
        status.state in setOf(TaskRuntimeState.STOPPED, TaskRuntimeState.SERVICE_STOPPED) -> "stopped"
        else -> "queued"
    }

    fun isActive(status: TaskRuntimeStatus?): Boolean = status != null && status.state !in setOf(
        TaskRuntimeState.STOPPED,
        TaskRuntimeState.SERVICE_STOPPED,
        TaskRuntimeState.ERROR
    )

    /** Desktop task stack contains only active instructions, never today's completed rows. */
    fun isTaskStackVisible(
        status: TaskRuntimeStatus?,
        completed: Boolean,
        schedulerActive: Boolean = true,
        nowMillis: Long = System.currentTimeMillis()
    ): Boolean =
        schedulerActive && !completed &&
            status?.let {
                if (it.type in setOf(
                        TaskType.STATE_REFRESH,
                        TaskType.BANDIT_PREFETCH,
                        TaskType.MINE_PREFETCH
                    )
                ) return@let false
                // 配兵是一次性前置动作。成功后调度器用长 Sleep 防止重复配兵，
                // 但电脑端此时已经把该指令移出任务栈，不能展示成数千小时冷却。
                if (it.type == TaskType.FORMATION && it.state == TaskRuntimeState.SLEEPING) {
                    return@let false
                }
                when (it.state) {
                    TaskRuntimeState.WAITING,
                    TaskRuntimeState.RUNNING,
                    TaskRuntimeState.RETRYING,
                    TaskRuntimeState.NEED_RELOGIN -> true
                    // 自身冷却尚未到期不是“排队”；到期后若正在给军事任务让行，
                    // 它才是真正等待执行的队列指令。
                    TaskRuntimeState.SLEEPING ->
                        it.nextRunAtMillis?.let { deadline -> deadline <= nowMillis } == true
                    TaskRuntimeState.STOPPED,
                    TaskRuntimeState.ERROR,
                    TaskRuntimeState.SERVICE_STOPPED -> false
                }
            } == true

    fun taskStackStatus(status: TaskRuntimeStatus): String =
        if (status.state == TaskRuntimeState.RUNNING) "running" else "queued"

    fun latestByKey(statuses: List<TaskRuntimeStatus>): Map<String, TaskRuntimeStatus> =
        statuses.groupBy { spec(it.type).key }.mapValues { (_, values) ->
            values.maxBy { it.updatedAtMillis }
        }

    private fun resident(key: String): LocalTaskPresentationSpec =
        residentSpecs.first { it.key == key }

    private fun daily(key: String): LocalTaskPresentationSpec =
        dailySpecs.first { it.key == key }
}

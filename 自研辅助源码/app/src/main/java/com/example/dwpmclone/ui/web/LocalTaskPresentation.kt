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
    private val retiredRuntimeTypes = setOf(
        TaskType.BANDIT_PREFETCH,
        TaskType.MINE_PREFETCH,
        TaskType.STATE_REFRESH,
        TaskType.FOOD_TO_COPPER,
        TaskType.FORMATION,
    )

    val residentSpecs = listOf(
        LocalTaskPresentationSpec("mine", "打矿", "resident"),
        LocalTaskPresentationSpec("lossless", "无损", "resident"),
        LocalTaskPresentationSpec("brushYellow", "刷黄", "resident"),
        LocalTaskPresentationSpec("raid", "掠夺", "resident"),
        LocalTaskPresentationSpec("dungeon", "副本", "resident"),
        LocalTaskPresentationSpec("general", "将领维护", "resident"),
        LocalTaskPresentationSpec("ministry", "六部", "resident"),
        LocalTaskPresentationSpec("domestic", "自动内政", "resident"),
        LocalTaskPresentationSpec("inventory", "背包整理", "resident")
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
        TaskType.GENERAL -> resident("general")
        TaskType.FOOD_TO_COPPER -> LocalTaskPresentationSpec("foodToCopper", "粮食转铜", "daily")
        TaskType.INTERNAL -> resident("domestic")
        TaskType.INVENTORY -> resident("inventory")
        TaskType.ALARM -> LocalTaskPresentationSpec("alarm", "警报/军情", "other")
        TaskType.DAILY -> LocalTaskPresentationSpec("daily", "日常任务", "daily")
    }

    fun schedulerState(
        status: TaskRuntimeStatus?,
        completed: Boolean = false,
        schedulerActive: Boolean = true,
        nowMillis: Long = System.currentTimeMillis()
    ): String = when {
        status == null -> if (completed) "daily_done" else "idle"
        status.skipped -> "daily_done"
        completed -> "daily_done"
        !schedulerActive || isRetiredRuntimeType(status.type) ->
            if (completed) "daily_done" else "stopped"
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

    fun isActive(
        status: TaskRuntimeStatus?,
        schedulerActive: Boolean = true,
    ): Boolean = schedulerActive && status != null &&
        !isRetiredRuntimeType(status.type) && status.state !in setOf(
            TaskRuntimeState.STOPPED,
            TaskRuntimeState.SERVICE_STOPPED,
            TaskRuntimeState.ERROR
        )

    fun schedulerActive(
        accountEnabled: Boolean,
        savedTasksStarted: Boolean,
        executionOwnerActive: Boolean,
    ): Boolean = accountEnabled && savedTasksStarted && executionOwnerActive

    fun isRetiredRuntimeType(type: TaskType): Boolean = type in retiredRuntimeTypes

    /** Desktop task stack contains only active instructions, never today's completed rows. */
    fun isTaskStackVisible(
        status: TaskRuntimeStatus?,
        completed: Boolean,
        schedulerActive: Boolean = true,
        nowMillis: Long = System.currentTimeMillis()
    ): Boolean =
        schedulerActive && !completed && status?.skipped != true &&
            status?.let {
                if (isRetiredRuntimeType(it.type)) return@let false
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

    /**
     * Persisted rows remain available for restart recovery, but the live queue may only project
     * rows written by the current foreground execution owner. This keeps an earlier Kotlin run
     * from copying one stale error onto unrelated shared-core tasks.
     */
    fun forExecutionGeneration(
        statuses: List<TaskRuntimeStatus>,
        executionGeneration: String?,
    ): List<TaskRuntimeStatus> = if (executionGeneration.isNullOrBlank()) {
        statuses
    } else {
        statuses.filter { it.executionGeneration == executionGeneration }
    }

    fun latestByKey(statuses: List<TaskRuntimeStatus>): Map<String, TaskRuntimeStatus> =
        statuses.filterNot { isRetiredRuntimeType(it.type) }
            .groupBy { spec(it.type).key }.mapValues { (_, values) ->
            values.maxBy { it.updatedAtMillis }
        }

    private fun resident(key: String): LocalTaskPresentationSpec =
        residentSpecs.first { it.key == key }

    private fun daily(key: String): LocalTaskPresentationSpec =
        dailySpecs.first { it.key == key }
}

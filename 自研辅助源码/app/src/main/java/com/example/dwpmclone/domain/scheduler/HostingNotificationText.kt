package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskType

/** Pure formatter for the user-visible foreground service state. */
object HostingNotificationText {
    fun format(accountLabels: List<String>, taskTypes: List<TaskType>): String {
        val distinctAccounts = accountLabels.filter(String::isNotBlank).distinct()
        val shownAccounts = distinctAccounts.take(3)
        val accountText = when {
            shownAccounts.isEmpty() -> "本地托管"
            distinctAccounts.size > shownAccounts.size -> shownAccounts.joinToString("、") + "等"
            else -> shownAccounts.joinToString("、")
        }
        val tasks = taskTypes.distinct().map(::taskLabel).distinct().take(3)
        val taskText = if (tasks.isEmpty()) "等待调度" else tasks.joinToString("、")
        return "账号：$accountText · 当前：$taskText"
    }

    private fun taskLabel(type: TaskType): String = when (type) {
        TaskType.SHUA_HUANG -> "刷黄"
        TaskType.BANDIT_PREFETCH -> "找山贼"
        TaskType.MINE_SEARCH, TaskType.AUTO_MINING -> "打矿"
        TaskType.MINE_PREFETCH -> "找资源点"
        TaskType.DUNGEON -> "副本"
        TaskType.AUTO_LOOT -> "掠夺"
        TaskType.LOSSLESS -> "无损"
        TaskType.DAILY, TaskType.DAILY_SIGN_IN, TaskType.DAILY_ARENA_COINS,
        TaskType.DAILY_DONATE, TaskType.DAILY_SALARY,
        TaskType.DAILY_NATIONAL_COLLECT, TaskType.DAILY_CITY_LORD_COLLECT,
        TaskType.DAILY_GENERAL_VISIT -> "日常"
        TaskType.GENERAL -> "将领维护"
        TaskType.FOOD_TO_COPPER -> "粮食转铜"
        TaskType.FORMATION -> "配兵"
        TaskType.INTERNAL -> "内政"
        TaskType.INVENTORY -> "背包"
        TaskType.SIX_MINISTRIES -> "六部"
        TaskType.STATE_REFRESH -> "数据刷新"
        TaskType.ALARM -> "军情"
    }
}

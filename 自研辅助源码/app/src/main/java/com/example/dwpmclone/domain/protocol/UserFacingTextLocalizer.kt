package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.DailyStep

/** Chinese names for task identifiers that remain English internally for persistence. */
fun TaskType.userFacingName(): String = when (this) {
    TaskType.SHUA_HUANG -> "刷黄"
    TaskType.BANDIT_PREFETCH -> "闲时找山贼"
    TaskType.MINE_SEARCH -> "找矿"
    TaskType.AUTO_MINING -> "自动打矿"
    TaskType.MINE_PREFETCH -> "闲时找资源点"
    TaskType.DAILY -> "日常任务"
    TaskType.DAILY_SIGN_IN -> "每日签到"
    TaskType.DAILY_ARENA_COINS -> "每日领竞技币"
    TaskType.DAILY_DONATE -> "每日捐献"
    TaskType.DAILY_SALARY -> "每日领取俸禄"
    TaskType.DAILY_NATIONAL_COLLECT -> "每日国家征收"
    TaskType.DAILY_CITY_LORD_COLLECT -> "每日城主征收"
    TaskType.DAILY_GENERAL_VISIT -> "每日名将拜访"
    TaskType.GENERAL -> "将领维护"
    TaskType.FOOD_TO_COPPER -> "粮食转铜"
    TaskType.FORMATION -> "配兵"
    TaskType.INTERNAL -> "自动内政"
    TaskType.DUNGEON -> "副本"
    TaskType.LOSSLESS -> "无损"
    TaskType.INVENTORY -> "背包整理"
    TaskType.AUTO_LOOT -> "自动掠夺"
    TaskType.SIX_MINISTRIES -> "六部"
    TaskType.STATE_REFRESH -> "角色军情刷新"
    TaskType.ALARM -> "军情警报"
}

fun DailyStep.userFacingName(): String = when (this) {
    DailyStep.SIGN_IN -> "每日签到"
    DailyStep.SURPRISE_BOX -> "领取惊喜宝箱"
    DailyStep.SALARY -> "领取俸禄"
    DailyStep.ARENA_REWARD -> "领取竞技币"
    DailyStep.COLLECT_TAX -> "每日征收"
    DailyStep.DONATE_TECH -> "科技积分捐献"
    DailyStep.DONATE_COPPER -> "铜钱捐献"
    DailyStep.DONATE_FOOD -> "粮食捐献"
    DailyStep.ADD_LOYALTY -> "将领加忠"
    DailyStep.DELETE_MAIL -> "清理邮件"
    DailyStep.ACHIEVEMENT_REWARD -> "领取成就奖励"
    DailyStep.TASK_REWARD -> "领取任务奖励"
    DailyStep.LEVEL_GIFT -> "领取等级礼包"
    DailyStep.CONVERT_HALF_FOOD_TO_COPPER -> "粮食转铜"
}

/**
 * Keeps wire/protocol identifiers intact in storage while translating the copy shown by the app.
 * This also makes older persisted log lines readable after upgrading.
 */
object UserFacingTextLocalizer {
    private val exactMessages = mapOf(
        "wakelock acquired for background keepalive" to "已获取后台保活锁",
        "wakelock released" to "已释放后台保活锁",
        "network validated; account sessions must be rechecked before scheduling" to
            "网络已确认可用，调度前将重新检查账号会话",
        "network monitor registered" to "网络监听已启用",
        "local scheduling started" to "手机本地调度已启动",
        "local scheduling stopped" to "手机本地调度已停止"
    )

    private val commonReplacements = listOf(
        "real-session+saved-screen-config:" to "真实会话+已保存配置:",
        "real-session-from-account-repo" to "账号本地真实会话",
        "session-metadata-aligned" to "会话信息已对齐",
        "account plan(s) from LocalConfigRepository" to "个账号任务方案（本地配置）",
        "task reports" to "个任务报告",
        "session_recovery" to "会话恢复",
        "city-lord/list" to "城主城池列表",
        "formation_troop" to "配兵",
        "daily_basic" to "每日任务",
        "shua_huang" to "刷黄",
        "dungeon" to "副本",
        "lossless" to "无损",
        "mine" to "打矿",
        "RetryAfter(" to "稍后重试(",
        "NeedRelogin(" to "需要重新登录(",
        "Continue" to "继续",
        "Sleep(" to "等待(",
        "Stop(" to "停止(",
        "LOGGED_OUT" to "已退出",
        "RUNNING" to "运行中",
        "WAITING_RELOGIN" to "等待重新登录",
        "PAUSED_NETWORK" to "网络暂停",
        "STOPPING" to "正在停止",
        "STOPPED" to "已停止",
        " loaded " to " 已加载 ",
        " completed " to " 已完成 ",
        " online=" to " 在线=",
        " paused=" to " 暂停=",
        " waiting=" to " 等待=",
        " relogged=" to " 已重登=",
        "tick=" to "调度轮次=",
        "account=" to "账号=",
        "source=" to "来源=",
        "tasks=" to "任务数=",
        "decisions=" to "执行结果=",
        "features=" to "功能=",
        "actions=" to "军情数=",
        "generals=" to "将领数=",
        "captives=" to "被俘将领数=",
        "unparsedTailBytes=" to "未解析尾部字节=",
        "responses=" to "响应=",
        "opcodes=" to "响应指令=",
        "opcode=" to "指令=",
        "keys=" to "字段=",
        "role=" to "角色=",
        "general=" to "将领=",
        "copper=" to "铜钱=",
        "food=" to "粮食=",
        "code=" to "编号=",
        "phase=" to "阶段=",
        "target=" to "目标=",
        "error=" to "错误=",
        "Lv." to "等级",
        "ms)" to "毫秒)"
    )

    fun localize(message: String): String {
        if (message.isBlank()) return message
        exactMessages[message]?.let { return it }
        var result = message
        TaskType.entries.sortedByDescending { it.name.length }.forEach { type ->
            result = result.replace(type.name, type.userFacingName())
        }
        DailyStep.entries.sortedByDescending { it.name.length }.forEach { step ->
            result = result.replace(step.name, step.userFacingName())
        }
        commonReplacements.forEach { (source, replacement) ->
            result = result.replace(source, replacement)
        }
        return result
    }
}

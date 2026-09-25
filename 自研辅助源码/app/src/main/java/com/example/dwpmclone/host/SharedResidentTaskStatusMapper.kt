package com.example.dwpmclone.host

import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.protocol.userFacingName
import com.example.dwpmclone.domain.scheduler.TaskRuntimeState

/**
 * Projects one shared-core resident result onto the Android task-status model.
 *
 * The shared core deliberately scopes an uncertain/blocked result to the
 * feature that owns it.  Android must preserve that scope: an inventory
 * ledger waiting for a human is an error on 背包整理, not proof that 副本 or
 * 刷黄 stopped.  Keeping this reducer pure makes that boundary testable without
 * constructing the foreground service.
 */
internal object SharedResidentTaskStatusMapper {
    private val featureErrorStates = setOf(
        "blocked",
        "defeat-paused",
        "clear-unconfirmed",
        // These terminal states can still carry a concrete feature when the
        // operation adapter recovered the owner from progress/error details.
        "uncertain",
        "timeout",
        "missing",
        "invalid",
    )

    fun typeFor(feature: String?, dailyKey: String? = null): TaskType? {
        return when (feature?.trim()) {
            "brush", "brushYellow" -> TaskType.SHUA_HUANG
            "mine" -> TaskType.AUTO_MINING
            "raid" -> TaskType.AUTO_LOOT
            "lossless" -> TaskType.LOSSLESS
            "dungeon" -> TaskType.DUNGEON
            "general" -> TaskType.GENERAL
            "ministry" -> TaskType.SIX_MINISTRIES
            "domestic" -> TaskType.INTERNAL
            "inventory" -> TaskType.INVENTORY
            "alarm" -> TaskType.ALARM
            "daily" -> when (dailyKey?.trim()) {
                "autoSignIn" -> TaskType.DAILY_SIGN_IN
                "arenaCoins" -> TaskType.DAILY_ARENA_COINS
                "autoDonate" -> TaskType.DAILY_DONATE
                "salary" -> TaskType.DAILY_SALARY
                "nationalCollect" -> TaskType.DAILY_NATIONAL_COLLECT
                "cityLordCollect" -> TaskType.DAILY_CITY_LORD_COLLECT
                "generalVisit" -> TaskType.DAILY_GENERAL_VISIT
                else -> TaskType.DAILY
            }
            else -> null
        }
    }

    /** Map a concrete result; account-level attention is handled elsewhere. */
    fun stateFor(result: SharedResidentTickResult): TaskRuntimeState {
        val state = result.state.trim().lowercase()
        return when {
            result.skipped -> TaskRuntimeState.SLEEPING
            state in featureErrorStates || result.requiresAttention ->
                TaskRuntimeState.ERROR
            state in setOf("retry", "failed", "waiting-resources", "waiting-dependency") ->
                TaskRuntimeState.RETRYING
            state in setOf("dispatched", "fighting", "running") ->
                TaskRuntimeState.RUNNING
            result.nextWakeAtMillis != null -> TaskRuntimeState.SLEEPING
            else -> TaskRuntimeState.WAITING
        }
    }

    /**
     * The core serializes isolated keys with `|` so the field stays compact
     * across the Python/JVM boundary.  Ignore malformed/unknown keys rather
     * than inventing a task row for them.
     */
    fun isolatedTypes(raw: String?): List<TaskType> = raw
        ?.split('|')
        ?.asSequence()
        ?.map(String::trim)
        ?.filter(String::isNotBlank)
        ?.mapNotNull { typeFor(it) }
        ?.distinct()
        ?.toList()
        .orEmpty()

    fun isolatedMessage(type: TaskType): String =
        "${type.userFacingName()}存在未确认操作，已隔离并禁止自动重发；请人工核对后处理"
}

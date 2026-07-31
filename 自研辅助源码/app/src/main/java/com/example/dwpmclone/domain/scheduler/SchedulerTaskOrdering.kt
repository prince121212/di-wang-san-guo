package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.SchedulerBehaviorContract
import com.example.dwpmclone.domain.protocol.TaskType

enum class SchedulerTaskLane {
    MILITARY,
    OBSERVATION,
    IDLE
}

/** Cross-platform task lanes plus the resident priority table from the shared contract. */
object SchedulerTaskOrdering {
    fun order(
        tasks: List<AssistantTask<*>>,
        contract: SchedulerBehaviorContract
    ): List<AssistantTask<*>> = orderValues(tasks, contract) { it.type }

    fun <T> orderValues(
        values: List<T>,
        contract: SchedulerBehaviorContract,
        typeOf: (T) -> TaskType
    ): List<T> = values.withIndex()
        .sortedWith(
            compareBy<IndexedValue<T>> { lane(typeOf(it.value), contract).ordinal }
                .thenByDescending { taskPriority(typeOf(it.value), contract) }
                .thenBy { it.index }
        )
        .map { it.value }

    fun lane(type: TaskType, contract: SchedulerBehaviorContract): SchedulerTaskLane = when {
        type == TaskType.FORMATION -> SchedulerTaskLane.MILITARY
        type in MILITARY_RESIDENT_TYPES && contract.residentPriority(type) != null ->
            SchedulerTaskLane.MILITARY
        type == TaskType.STATE_REFRESH || type == TaskType.ALARM ->
            SchedulerTaskLane.OBSERVATION
        else -> SchedulerTaskLane.IDLE
    }

    private fun taskPriority(type: TaskType, contract: SchedulerBehaviorContract): Int =
        if (type == TaskType.FORMATION) Int.MAX_VALUE
        else contract.residentPriority(type) ?: 0

    private val MILITARY_RESIDENT_TYPES = setOf(
        TaskType.AUTO_MINING,
        TaskType.LOSSLESS,
        TaskType.SHUA_HUANG,
        TaskType.AUTO_LOOT,
        TaskType.DUNGEON
    )
}

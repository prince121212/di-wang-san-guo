package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.model.MineConfig
import com.example.dwpmclone.domain.protocol.AssistantTask
import org.json.JSONObject

/**
 * Aligns saved UI task plans with metadata recovered from a real read-only session.
 *
 * Saved screen configs still contain several placeholder defaults from the static UI rebuild
 * (notably formation id 1).  A sourceMode=1 session, however, may carry recovered Xiaohuang
 * prefs such as bianduihao0=000...0003.  This adapter makes the service/UI path consume that
 * recovered session metadata before the scheduler runs, without enabling network action send.
 */
object RealSessionTaskPlanAdapter {
    fun attachRealSession(savedPlan: SavedTaskPlan, realSession: GameSession): SavedTaskPlan {
        if (savedPlan.sourceDescription.startsWith("synthetic-defaults:no-saved-config")) {
            val sessionDerivedTasks = sessionDerivedBrushYellowTasks(realSession)
            return savedPlan.copy(
                session = realSession,
                tasks = sessionDerivedTasks,
                sourceDescription = if (sessionDerivedTasks.isEmpty()) {
                    "real-session-from-account-repo;no-saved-config;no-background-tasks"
                } else {
                    "real-session-from-account-repo;no-saved-config;session-derived-brush-yellow-task"
                }
            )
        }
        if (realSession.sourceMode != 1) {
            return savedPlan.copy(
                session = realSession,
                sourceDescription = savedPlan.sourceDescription + ";non-real-session-from-account-repo"
            )
        }
        val alignedTasks = savedPlan.tasks.map { task -> alignTaskWithSession(task, realSession) }
        return savedPlan.copy(
            session = realSession,
            tasks = alignedTasks,
            sourceDescription = savedPlan.sourceDescription + ";real-session-from-account-repo;session-metadata-aligned"
        )
    }

    private fun alignTaskWithSession(task: AssistantTask<*>, session: GameSession): AssistantTask<*> = when (task) {
        is ShuaHuangTask -> ShuaHuangTask(task.accountId, task.config.alignShuaHuang(session))
        is MineSearchMockTask -> MineSearchMockTask(task.accountId, task.config.alignMine(session))
        else -> task
    }

    private fun sessionDerivedBrushYellowTasks(session: GameSession): List<AssistantTask<*>> {
        if (session.sourceMode != 1) return emptyList()
        if (!brushYellowRealActionGateReady(session.channelExtra)) return emptyList()
        val recoveredFormationIds = recoverShuaHuangFormationIds(session.channelExtra)
        if (recoveredFormationIds.isEmpty()) return emptyList()
        val recoveredTargetType = session.channelExtra["shuaHuangTargetType"]
            ?.let { runCatching { HuangTargetType.valueOf(it.trim()) }.getOrNull() }
            ?: HuangTargetType.SHAN_ZEI
        val dailyLimit = session.channelExtra["shuaHuangDailyLimit"]?.toIntOrNull()?.coerceIn(1, 500) ?: 1
        val startX = session.channelExtra["shuaHuangStartX"]?.toIntOrNull() ?: 0
        val startY = session.channelExtra["shuaHuangStartY"]?.toIntOrNull() ?: 0
        val config = ConfigDefaults.shuaHuang().copy(
            enabled = true,
            dailyLimit = dailyLimit,
            start = com.example.dwpmclone.domain.model.MapCoordinate(startX, startY),
            targetType = recoveredTargetType,
            selectedFormationIds = recoveredFormationIds,
            deleteMailForSpeed = false,
            autoConvertFoodToCopper = false
        )
        return listOf(ShuaHuangTask(session.accountId, config))
    }

    private fun com.example.dwpmclone.domain.model.ShuaHuangConfig.alignShuaHuang(session: GameSession): com.example.dwpmclone.domain.model.ShuaHuangConfig {
        val recoveredFormationIds = recoverShuaHuangFormationIds(session.channelExtra)
        val recoveredTargetType = session.channelExtra["shuaHuangTargetType"]
            ?.let { runCatching { HuangTargetType.valueOf(it.trim()) }.getOrNull() }
        return copy(
            selectedFormationIds = recoveredFormationIds.ifEmpty { selectedFormationIds },
            targetType = recoveredTargetType ?: targetType
        )
    }

    private fun MineConfig.alignMine(session: GameSession): MineConfig {
        val recoveredFormationIds = parseLongSet(
            session.channelExtra["mineSelectedFormationIds"]
                ?: session.channelExtra["selectedMineFormationIds"]
                ?: session.channelExtra["selectedFormationIds"]
        )
        return copy(selectedFormationIds = recoveredFormationIds.ifEmpty { selectedFormationIds })
    }

    fun recoverShuaHuangFormationIds(extra: Map<String, String>): Set<Long> {
        val out = linkedSetOf<Long>()
        parseLongSet(extra["shuaHuangSelectedFormationIds"] ?: extra["selectedFormationIds"]).forEach(out::add)
        val prefs = recoveredPreferenceMap(extra)
        selectedRecoveredFormationSlots(prefs).forEach { slot ->
            val suffix = slot.toString()
            prefs.firstValue(
                "bianduihao$suffix",
                "bianduihao_$suffix",
                "bianduihao.$suffix",
                "bianduihao[$suffix]",
                "formationId$suffix",
                "formationId_$suffix"
            )?.parseLongFlexible()?.takeIf { it > 0L }?.let(out::add)
        }
        return out
    }

    private fun brushYellowRealActionGateReady(extra: Map<String, String>): Boolean =
        extra["realActionNetworkAllowed"].equals("true", ignoreCase = true) &&
            extra["realActionSendReady"].equals("true", ignoreCase = true) &&
            (
                extra["realActionScope"].equals("brush-yellow", ignoreCase = true) ||
                    extra["realActionBrushYellowOnly"].equals("true", ignoreCase = true)
                )

    private fun recoveredPreferenceMap(extra: Map<String, String>): Map<String, String> {
        val out = linkedMapOf<String, String>()
        out.putAll(extra)
        listOf("xiaohuangPrefsJson", "sharedPrefsJson", "guajiPrefsJson", "recoveredPrefsJson").forEach { key ->
            val raw = extra[key]?.takeIf { it.isNotBlank() } ?: return@forEach
            runCatching {
                val obj = JSONObject(raw)
                obj.keys().forEach { nestedKey -> out[nestedKey] = obj.optString(nestedKey) }
            }
        }
        return out
    }

    private fun selectedRecoveredFormationSlots(prefs: Map<String, String>): List<Int> {
        val slots = linkedSetOf<Int>()
        prefs.forEach { (key, value) ->
            val match = Regex("""shuahuangChuzhengBiandui(?:_|\.|\[)?(\d+)\]?""").matchEntire(key)
            if (match != null && value.parseBoolFlexible()) {
                slots += match.groupValues[1].toInt()
            }
        }
        if (slots.isEmpty()) {
            prefs.keys.forEach { key ->
                Regex("""bianduihao(?:_|\.|\[)?(\d+)\]?""").matchEntire(key)?.groupValues?.get(1)?.toIntOrNull()?.let(slots::add)
            }
        }
        return slots.sorted()
    }

    private fun parseLongSet(raw: String?): Set<Long> = raw
        ?.split(Regex("""[,，;；|/\s]+"""))
        ?.mapNotNull { it.trim().takeIf { token -> token.isNotBlank() }?.parseLongFlexible() }
        ?.filter { it > 0L }
        ?.toCollection(linkedSetOf())
        ?: emptySet()

    private fun Map<String, String>.firstValue(vararg keys: String): String? {
        for (key in keys) this[key]?.takeIf { it.isNotBlank() }?.let { return it }
        return null
    }

    private fun String.parseBoolFlexible(): Boolean = when (trim().lowercase()) {
        "1", "true", "yes", "y", "on", "checked", "选中" -> true
        else -> false
    }

    private fun String.parseLongFlexible(): Long? {
        val text = trim().trim('"', '\'')
        if (text.isBlank()) return null
        if (text.startsWith("0x", ignoreCase = true)) return text.drop(2).toLongOrNull(16)
        if (text.length > 1 && text.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' } && text.any { it in 'a'..'f' || it in 'A'..'F' }) {
            return text.toLongOrNull(16)
        }
        if (text.length >= 8 && text.all { it in '0'..'9' }) {
            text.trimStart('0').takeIf { it.isNotEmpty() }?.toLongOrNull(16)?.let { return it }
        }
        return text.toLongOrNull()
    }
}

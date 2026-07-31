package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.FormationConfig
import com.example.dwpmclone.domain.model.FormationRuntime
import com.example.dwpmclone.domain.model.FormationRuntimeStatus
import com.example.dwpmclone.domain.model.GameSession

data class ExpeditionPreflightPolicy(
    val autoEnergy: Boolean,
    val minimumEnergy: Int,
    val healWounded: Boolean = false
) {
    init {
        require(minimumEnergy in 1..100) { "出征体力阈值必须为1..100" }
    }

    companion object {
        fun from(session: GameSession): ExpeditionPreflightPolicy {
            val extra = session.channelExtra
            val autoEnergy = extra.firstBoolean("expeditionAutoEnergy", "autoEnergy") ?: false
            val minimumEnergy = extra.firstInt("expeditionMinimumEnergy", "energyThreshold", "minEnergy")
                ?.coerceIn(1, 100)
                ?: DEFAULT_MINIMUM_ENERGY
            val healWounded = extra.firstBoolean("expeditionHealWounded", "healWounded", "autoHeal")
                ?: false
            return ExpeditionPreflightPolicy(autoEnergy, minimumEnergy, healWounded)
        }

        const val DEFAULT_MINIMUM_ENERGY = 20
    }
}

data class ExpeditionPreflightRequest(
    val label: String,
    val generalIds: List<Long> = emptyList(),
    val formationId: Long? = null,
    val requireFullLoyalty: Boolean = false,
    // The desktop dispatcher does not invent a positive-loyalty prerequisite. Only an
    // explicitly configured full-loyalty action may mutate/check loyalty before dispatch.
    val requirePositiveLoyalty: Boolean = false,
    val requirePositiveTroops: Boolean = true,
    val refillToFull: Boolean = false,
    val formationRules: List<FormationConfig> = emptyList()
)

data class ExpeditionTroops(
    val typeCode: Int,
    val count: Int
)

data class ExpeditionPreflightSnapshot(
    val generalIds: List<Long>,
    val generalNames: List<String>,
    val generals: List<General>,
    val formations: List<FormationRuntime>,
    val observedAtMillis: Long?
)

/**
 * The single action gate shared by every expedition feature.
 *
 * Corrections are deliberately two-phase: after energy or troop mutation succeeds this
 * method returns a retryable result. The next scheduler pass must fetch fresh server state
 * and pass this gate again before an expedition may be sent.
 */
class ExpeditionPreflight(
    private val protocol: GameProtocolClient,
    private val maximumGenerals: Int = DEFAULT_MAX_GENERALS
) {
    suspend fun check(
        session: GameSession,
        request: ExpeditionPreflightRequest,
        policy: ExpeditionPreflightPolicy = ExpeditionPreflightPolicy.from(session)
    ): ProtocolResult<ExpeditionPreflightSnapshot> {
        if (request.label.isBlank()) return blocked("EXPEDITION_LABEL_EMPTY", "出征类型不能为空")
        if (request.generalIds.any { it <= 0L } || request.formationId?.let { it <= 0L } == true) {
            return blocked("EXPEDITION_SELECTION_INVALID", "${request.label}包含无效将领或编队 ID")
        }

        when (val validation = protocol.validateSession(session)) {
            is ProtocolResult.Err -> return validation
            is ProtocolResult.Ok -> if (!validation.value.valid) {
                return blocked(
                    "EXPEDITION_SESSION_INVALID",
                    validation.value.reason?.let { "${request.label} Session 无效：$it" }
                        ?: "${request.label} Session 无效"
                )
            }
        }

        val generals = when (val result = protocol.queryGenerals(session)) {
            is ProtocolResult.Err -> return result
            is ProtocolResult.Ok -> result.value
        }
        val formations = when (val result = protocol.queryFormations(session)) {
            is ProtocolResult.Err -> return result
            is ProtocolResult.Ok -> result.value
        }
        val selectedIds = resolveGeneralIds(request, generals.map { it.id }.toSet(), formations)
            ?: return blocked(
                "EXPEDITION_GENERALS_EMPTY",
                "${request.label}未找到可校验的出征将领"
            )
        if (selectedIds.size > maximumGenerals) {
            return blocked(
                "EXPEDITION_GENERALS_OVER_LIMIT",
                "${request.label}一次最多出征${maximumGenerals}名将领"
            )
        }
        val byId = generals.associateBy { it.id }
        val selected = selectedIds.map { id ->
            byId[id] ?: return blocked(
                "EXPEDITION_GENERAL_NOT_FOUND",
                "${request.label}未找到将领 ID=$id"
            )
        }

        // Desktop prepare_military_generals() heals first, then applies energy, and only then
        // repairs the saved formation. Keep the same phase boundary so an account with both
        // wounded troops and low energy cannot take a different path on Android.
        if (policy.healWounded) {
            var stateChanged = false
            for (general in selected.distinctBy { it.placeId ?: it.id }) {
                when (val result = protocol.healGeneral(session, general.id)) {
                    is ProtocolResult.Err -> return result
                    is ProtocolResult.Ok -> {
                        if (!result.value.success) {
                            return deferred(
                                "EXPEDITION_HEAL_UNAVAILABLE",
                                "${request.label}出征前治疗未完成：${result.value.message}"
                            )
                        }
                        if (result.value.raw["skipped"] != "no-wounded-soldiers") {
                            stateChanged = true
                        }
                    }
                }
            }
            if (stateChanged) {
                return deferred(
                    "EXPEDITION_HEAL_APPLIED",
                    "${request.label}出征前治疗已完成，等待刷新真实兵力"
                )
            }
        }

        selected.forEach { general ->
            val status = general.status
                ?: return blocked(
                    "EXPEDITION_GENERAL_STATUS_UNKNOWN",
                    "${request.label}无法确认将领${general.name}状态"
                )
            if (status != IDLE_GENERAL_STATUS) {
                return deferred(
                    "EXPEDITION_GENERAL_BUSY",
                    "${request.label}等待将领${general.name}回闲"
                )
            }
            val energy = general.energy
                ?: return blocked(
                    "EXPEDITION_GENERAL_ENERGY_UNKNOWN",
                    "${request.label}无法确认将领${general.name}体力"
                )
            val requiredEnergy = maxOf(policy.minimumEnergy, MINIMUM_DISPATCH_ENERGY)
            if (energy < requiredEnergy && !policy.autoEnergy) {
                return deferred(
                    "EXPEDITION_GENERAL_ENERGY_LOW",
                    "${request.label}等待将领${general.name}恢复体力：$energy/$requiredEnergy"
                )
            }
            if (request.requireFullLoyalty || request.requirePositiveLoyalty) {
                val loyalty = general.loyalty
                    ?: return blocked(
                        "EXPEDITION_GENERAL_LOYALTY_UNKNOWN",
                        "${request.label}无法确认将领${general.name}忠诚度"
                    )
                val requiredLoyalty = if (request.requireFullLoyalty) FULL_LOYALTY else MINIMUM_DISPATCH_LOYALTY
                if (loyalty < requiredLoyalty) {
                    if (request.requireFullLoyalty) {
                        val delta = requiredLoyalty - loyalty
                        when (val result = protocol.addLoyalty(session, general.id, delta)) {
                            is ProtocolResult.Err -> return result
                            is ProtocolResult.Ok -> if (!result.value.success) {
                                return deferred(
                                    "EXPEDITION_FULL_LOYALTY_UNAVAILABLE",
                                    "${request.label}满忠未完成：${result.value.message}"
                                )
                            }
                        }
                        return deferred(
                            "EXPEDITION_FULL_LOYALTY_APPLIED",
                            "${request.label}已为${general.name}补满忠诚，等待刷新真实状态"
                        )
                    }
                    return deferred(
                        "EXPEDITION_GENERAL_LOYALTY_LOW",
                        "${request.label}等待将领${general.name}忠诚度恢复：$loyalty/$requiredLoyalty"
                    )
                }
            }
        }

        val selectedIdSet = selectedIds.toSet()
        val lowEnergyThreshold = maxOf(policy.minimumEnergy, MINIMUM_DISPATCH_ENERGY)
        val lowEnergy = selected.filter { (it.energy ?: 0) < lowEnergyThreshold }
        if (policy.autoEnergy && lowEnergy.isNotEmpty()) {
            for (general in lowEnergy) {
                when (val result = protocol.addEnergy(session, general.id)) {
                    is ProtocolResult.Err -> return result
                    is ProtocolResult.Ok -> if (!result.value.success) {
                        return deferred(
                            "EXPEDITION_AUTO_ENERGY_UNAVAILABLE",
                            "${request.label}自动加体未完成：${result.value.message}"
                        )
                    }
                }
            }
            return deferred(
                "EXPEDITION_AUTO_ENERGY_APPLIED",
                "${request.label}已为${lowEnergy.joinToString("、") { it.name }}自动加体，等待刷新真实状态"
            )
        }

        val formationRepairs = request.formationRules.mapNotNull { rule ->
            if (!rule.autoAssignTroops || rule.troopCount <= 0) return@mapNotNull null
            val applicableIds = rule.generalIds
                .ifEmpty { listOf(rule.formationId) }
                .filter(selectedIdSet::contains)
                .distinct()
            if (applicableIds.isEmpty()) return@mapNotNull null
            val targetTypeCode = formationTroopTypeCode(rule.troopType)
            val mismatch = applicableIds.any { generalId ->
                val general = byId.getValue(generalId)
                val expectedCount = general.troopLimit
                    ?.takeIf { it > 0 }
                    ?.let { minOf(rule.troopCount, it) }
                    ?: rule.troopCount
                val current = general.assignedTroopsOrNull()
                current?.typeCode != targetTypeCode || current.count != expectedCount
            }
            rule.copy(
                formationId = applicableIds.first(),
                generalIds = applicableIds
            ).takeIf { mismatch }
        }
        if (formationRepairs.isNotEmpty()) {
            for (rule in formationRepairs) {
                when (val result = protocol.updateFormation(session, rule)) {
                    is ProtocolResult.Err -> return result
                    is ProtocolResult.Ok -> if (!result.value.success) {
                        return deferred(
                            "EXPEDITION_FORMATION_REPAIR_UNAVAILABLE",
                            "${request.label}按保存规则配兵未完成：${result.value.message}"
                        )
                    }
                }
            }
            return deferred(
                "EXPEDITION_FORMATION_REPAIR_APPLIED",
                "${request.label}已按保存规则恢复配兵，等待刷新真实兵力"
            )
        }

        if (!request.requirePositiveTroops) {
            return ProtocolResult.Ok(
                ExpeditionPreflightSnapshot(
                    selectedIds,
                    selected.map { it.name },
                    selected,
                    emptyList(),
                    selected.freshObservationMillis()
                )
            )
        }

        val selectedFormations = selected.map { general ->
            formations.firstOrNull { formation ->
                (request.formationId != null && formation.id == request.formationId) ||
                    formation.id == general.id || general.id in formation.generalIds
            } ?: return blocked(
                "EXPEDITION_FORMATION_NOT_FOUND",
                "${request.label}缺少将领${general.name}的真实配兵状态"
            )
        }.distinctBy { it.id }

        selectedFormations.forEach { formation ->
            if (formation.status == FormationRuntimeStatus.UNKNOWN) {
                return blocked(
                    "EXPEDITION_FORMATION_STATUS_UNKNOWN",
                    "${request.label}无法确认编队${formation.name ?: formation.id}状态"
                )
            }
            if (formation.status != FormationRuntimeStatus.IDLE) {
                return deferred(
                    "EXPEDITION_FORMATION_BUSY",
                    "${request.label}等待编队${formation.name ?: formation.id}回闲"
                )
            }
            val count = formation.troopCount
                ?: return blocked(
                    "EXPEDITION_TROOP_COUNT_UNKNOWN",
                    "${request.label}无法确认编队${formation.name ?: formation.id}兵力"
                )
            if (count <= 0) {
                return blocked(
                    "EXPEDITION_TROOPS_EMPTY",
                    "${request.label}编队${formation.name ?: formation.id}没有可用兵力"
                )
            }
        }

        val troopState = selected.associateWith { it.assignedTroopsOrNull() }
        troopState.forEach { (general, troops) ->
            if (troops == null) {
                return blocked(
                    "EXPEDITION_TROOP_TYPE_UNKNOWN",
                    "${request.label}无法确认将领${general.name}的兵种和兵力"
                )
            }
            if (troops.count <= 0) {
                return blocked(
                    "EXPEDITION_TROOPS_EMPTY",
                    "${request.label}将领${general.name}没有可用兵力"
                )
            }
        }

        val needsRefill = if (request.refillToFull) {
            selected.filter { general ->
                val limit = general.troopLimit
                    ?: return blocked(
                        "EXPEDITION_TROOP_LIMIT_UNKNOWN",
                        "${request.label}无法确认将领${general.name}带兵上限"
                    )
                troopState.getValue(general)!!.count < limit
            }
        } else {
            emptyList()
        }
        if (needsRefill.isNotEmpty()) {
            val refill = protocol.updateFormation(
                session,
                FormationConfig(
                    formationId = request.formationId ?: selectedIds.first(),
                    generalIds = selectedIds,
                    autoAssignTroops = false,
                    troopType = "",
                    troopCount = 0,
                    fillToMaxWhenAutoAssignDisabled = true
                )
            )
            when (refill) {
                is ProtocolResult.Err -> return refill
                is ProtocolResult.Ok -> if (!refill.value.success) {
                    return blocked(
                        "EXPEDITION_REFILL_FAILED",
                        "${request.label}补兵失败：${refill.value.message}"
                    )
                }
            }
            return deferred(
                "EXPEDITION_REFILL_APPLIED",
                "${request.label}已为${needsRefill.joinToString("、") { it.name }}补兵，等待刷新真实状态"
            )
        }

        return ProtocolResult.Ok(
            ExpeditionPreflightSnapshot(
                selectedIds,
                selected.map { it.name },
                selected,
                selectedFormations,
                selected.freshObservationMillis()
            )
        )
    }

    private fun resolveGeneralIds(
        request: ExpeditionPreflightRequest,
        knownGeneralIds: Set<Long>,
        formations: List<FormationRuntime>
    ): List<Long>? {
        request.generalIds.filter { it > 0L }.distinct().takeIf { it.isNotEmpty() }?.let { return it }
        val formationId = request.formationId ?: return null
        val formation = formations.firstOrNull { it.id == formationId }
        formation?.generalIds?.filter { it > 0L }?.distinct()?.takeIf { it.isNotEmpty() }?.let { return it }
        return listOf(formationId).takeIf { formationId in knownGeneralIds }
    }

    private fun blocked(code: String, message: String): ProtocolResult.Err =
        ProtocolResult.Err(code, message, retryable = false)

    private fun deferred(code: String, message: String): ProtocolResult.Err =
        ProtocolResult.Err(code, message, retryable = true)

    companion object {
        const val DEFAULT_MAX_GENERALS = 5
        private const val IDLE_GENERAL_STATUS = 0
        // Desktop requires energy > 20 before 0x1522.  Energy=20 must be repaired,
        // not sent into a predictable server rejection.
        private const val MINIMUM_DISPATCH_ENERGY = 21
        private const val MINIMUM_DISPATCH_LOYALTY = 1
        private const val FULL_LOYALTY = 100

        private fun formationTroopTypeCode(name: String): Int = when (name.trim()) {
            "民兵" -> 0
            "弩兵" -> 1
            "弓兵" -> 2
            "轻骑兵" -> 3
            "弩车" -> 4
            "冲城车" -> 5
            "轻步兵" -> 6
            "近卫兵" -> 7
            "重步兵" -> 8
            "弩骑兵" -> 9
            "重骑兵" -> 10
            "铁骑兵" -> 11
            "投石车" -> 12
            "重弩车" -> 13
            "强弩兵" -> 14
            "骁骑兵" -> 15
            else -> name.trim().toIntOrNull() ?: 3
        }
    }
}

private fun List<General>.freshObservationMillis(): Long? {
    if (isEmpty()) return null
    val values = map { general ->
        general.raw.entries.firstNotNullOfOrNull { (key, value) ->
            if (key.contains("liveStateMillis", true) || key.contains("syncedAtMillis", true)) {
                value.toLongOrNull()
            } else {
                null
            }
        } ?: return null
    }
    return values.minOrNull()
}

fun General.assignedTroopsOrNull(): ExpeditionTroops? {
    val typeCode = raw.firstInt(
        "soldierTypeCode",
        "troopTypeCode",
        "assignedSoldierTypeCode",
        "assignedType"
    ) ?: return null
    val count = raw.firstInt(
        "soldierCount",
        "troopCount",
        "currentSoldierCount",
        "currentTroopCount",
        "bingli",
        "assignedSoldierCount"
    ) ?: return null
    return ExpeditionTroops(typeCode, count)
}

private fun Map<String, String>.firstInt(vararg keys: String): Int? {
    for (key in keys) {
        this[key]
            ?.trim()
            ?.filter { it == '-' || it.isDigit() }
            ?.takeIf { it.isNotBlank() && it != "-" }
            ?.toIntOrNull()
            ?.let { return it }
    }
    return null
}

private fun Map<String, String>.firstBoolean(vararg keys: String): Boolean? {
    for (key in keys) {
        val value = this[key]?.trim()?.lowercase() ?: continue
        return when (value) {
            "true", "1", "yes", "on", "开启" -> true
            "false", "0", "no", "off", "关闭" -> false
            else -> continue
        }
    }
    return null
}

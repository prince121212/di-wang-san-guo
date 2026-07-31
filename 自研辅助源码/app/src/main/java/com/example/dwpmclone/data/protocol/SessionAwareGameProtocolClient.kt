package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import com.example.dwpmclone.domain.alarm.MilitaryAlarmEventDetector
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentHashMap

/**
 * Local scheduler protocol boundary. `sourceMode == 1` identifies a real login/session;
 * unsupported calls fail closed. Other source modes are rejected unless a debug test
 * explicitly injects a fake client.
 */
data class DirectBinaryResponse(
    val phase: String,
    val httpCode: Int,
    val ok: Boolean,
    val responseBytes: Int,
    val responseHex: String,
    val textPreview: String,
    val responseOpcodes: List<Int> = emptyList(),
    val responsePayloads: List<DirectBinaryPayload> = emptyList()
) {
    /**
     * Returns the payload owned by one response opcode.
     *
     * A game HTTP response commonly contains the requested receipt followed by 0x880d
     * or another asynchronous state packet. [responseHex] intentionally keeps the full
     * concatenation for diagnostics, but a protocol parser must never consume that
     * concatenation as one packet. Older injected transports did not expose packet
     * payloads, so the fallback is allowed only when the requested opcode is present.
     */
    fun payloadHexFor(opcode: Int): String? =
        responsePayloads.firstOrNull { it.opcode == opcode }?.payloadHex
            ?: responseHex.takeIf { responsePayloads.isEmpty() && opcode in responseOpcodes }

    fun payloadBytesFor(opcode: Int): ByteArray? =
        payloadHexFor(opcode)?.let { hex ->
            val normalized = hex.filterNot(Char::isWhitespace)
            runCatching {
                require(normalized.length % 2 == 0)
                normalized.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
            }.getOrNull()
        }

    fun requirePayloadBytesFor(opcode: Int): ByteArray =
        requireNotNull(payloadBytesFor(opcode)) {
            "0x${opcode.toString(16)}负载缺失或格式无效"
        }
}

data class DirectBinaryPayload(
    val opcode: Int,
    val payloadHex: String
)

class SessionAwareGameProtocolClient(
    private val fallback: GameProtocolClient = UnsupportedSessionProtocolClient(),
    private val recoveredReadOnlyExecutor: RecoveredReadOnlyExecutor = RealRecoveredReadOnlyExecutor(),
    private val actionAudit: ((String) -> Unit)? = null,
    private val alarmEventSink: ((AlarmNotificationEvent) -> Unit)? = null,
    private val sessionExtraSink: ((Long, Map<String, String>) -> Unit)? = null,
    private val heartbeat3110Executor: Heartbeat3110Executor = RealHeartbeat3110Executor(),
    private val directBinaryTransport: ((
        gameHttp: String,
        dm: Long,
        gameHex: String,
        phase: String
    ) -> DirectBinaryResponse)? = null,
    expeditionTransactionStore: ExpeditionTransactionStore = InMemoryExpeditionTransactionStore(),
    private val offlineActionFixturesAllowed: Boolean = false,
    private val behaviorContract: AssistantBehaviorContract = AssistantBehaviorContract.defaults(),
    /** Dynamic foreground-service ownership gate. Manual/debug clients keep the true default. */
    private val executionAllowed: () -> Boolean = { true }
) : GameProtocolClient {
    private val liveStateCache = ConcurrentHashMap<String, LiveStateBundle>()
    private val liveStateErrors = ConcurrentHashMap<String, String>()
    private val liveSessionExtraCache = ConcurrentHashMap<Long, Map<String, String>>()
    private val pendingDungeons = ConcurrentHashMap<Long, DungeonPendingRun>()
    private val dungeonPollBattleIds = ConcurrentHashMap<Long, Long>()
    private val losslessRuleCursors = ConcurrentHashMap<Long, Int>()
    private val losslessRerollCounts = ConcurrentHashMap<String, Int>()
    private val lootRuleCursors = ConcurrentHashMap<Long, Int>()
    private val internalTechnologyTurns = ConcurrentHashMap<Long, Boolean>()
    private val seenAlarmFingerprints = ConcurrentHashMap<Long, MutableSet<String>>()
    private val lastHeartbeat3110AttemptAt = ConcurrentHashMap<Long, Long>()
    private val expeditionPreflight by lazy {
        ExpeditionPreflight(this, behaviorContract.brushYellow.maximumGeneralsPerFormation)
    }
    private val expeditionTransactions = ExpeditionTransactionCoordinator(expeditionTransactionStore)

    private data class LiveStateBundle(
        val state: RealGameProtocolClient.RoleState,
        val roleJson: JSONObject,
        val resourceJson: JSONObject,
        val responseOpcodes: List<String>,
        val refreshedAtMillis: Long
    )

    override suspend fun login(account: GameAccount): ProtocolResult<GameSession> =
        account.session?.let { ProtocolResult.Ok(it) }
            ?: ProtocolResult.Err("NO_SESSION", "账号尚未通过真实协议登录", retryable = false)

    override suspend fun logout(session: GameSession): ProtocolResult<StepResult> =
        if (session.isRealSession()) ProtocolResult.Ok(StepResult(true, "real session marked logged out locally"))
        else fallback.logout(session)

    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> =
        if (!session.isRealSession()) {
            fallback.validateSession(session)
        } else if (session.tokenCiphertext.isBlank()) {
            ProtocolResult.Ok(LoginState(valid = false, reason = "empty real session token"))
        } else if (session.channelExtra["userId"].isNullOrBlank() || session.channelExtra["serverUrl"].isNullOrBlank()) {
            ProtocolResult.Ok(LoginState(valid = false, reason = "missing real session userId/serverUrl"))
        } else {
            val live = session.liveStateBundleOrNull()
            val liveError = if (live == null) session.liveStateErrorOrNull() else null
            if (liveError != null && liveError.looksLikeExpiredRoleSession()) {
                ProtocolResult.Ok(LoginState(valid = false, reason = "真实 session 已过期：$liveError"))
            } else {
                ProtocolResult.Ok(LoginState(valid = true, reason = liveError?.let { "live state refresh pending/retryable: $it" }))
            }
        }

    override suspend fun queryMonarch(session: GameSession): ProtocolResult<MonarchProfile> =
        if (!session.isRealSession()) {
            fallback.queryMonarch(session)
        } else {
            val live = session.liveStateBundleOrNull()
            if (live == null) session.liveStateErrorOrNull()?.let {
                return ProtocolResult.Err("REAL_LIVE_STATE_REFRESH_FAILED", "真实 0x1016 状态刷新失败：$it", retryable = true)
            }
            val role = live?.roleJson ?: session.extraJsonObject("roleStateJson", "monarchJson") ?: session.firstRecoveredRoleResourceObject()
            val name = session.extraString(role, "roleName", "name", "monarchName").orEmpty()
            val level = session.extraInt(role, "level", "rank")
            val nation = session.extraString(role, "nation", "country")?.ifBlank { null }
            if (name.isBlank() || level == null) {
                ProtocolResult.Err("REAL_MONARCH_METADATA_MISSING", "真实 session 缺少 roleName/level 元数据", retryable = false)
            } else {
                ProtocolResult.Ok(
                    MonarchProfile(
                        level = level,
                        nation = nation,
                        name = name,
                        roleId = session.extraLong(role, "roleId", "id"),
                        title = session.extraString(role, "title", "officialTitle")?.ifBlank { null },
                        prestige = session.extraLong(role, "prestige", "shengwang"),
                        populationCurrent = session.extraLong(role, "populationCurrent", "population", "renkou"),
                        populationCap = session.extraLong(role, "populationCap", "populationLimit"),
                        resourcePointCurrent = session.extraInt(role, "resourcePointCurrent", "resourcePoint", "resourcePointUsed"),
                        resourcePointCap = session.extraInt(role, "resourcePointCap", "resourcePointLimit"),
                        raw = (role?.toStringMap() ?: emptyMap()) + session.channelExtra.filterKeys { it in ROLE_RESOURCE_KEYS }
                    )
                )
            }
        }

    override suspend fun queryResourceState(session: GameSession): ProtocolResult<ResourceState> =
        if (!session.isRealSession()) {
            fallback.queryResourceState(session)
        } else {
            val live = session.liveStateBundleOrNull()
            if (live == null) session.liveStateErrorOrNull()?.let {
                return ProtocolResult.Err("REAL_LIVE_STATE_REFRESH_FAILED", "真实 0x1016 状态刷新失败：$it", retryable = true)
            }
            val resource = live?.resourceJson ?: session.extraJsonObject("resourceStateJson", "roleStateJson") ?: session.firstRecoveredRoleResourceObject()
            val copper = session.extraLong(resource, "copper", "money", "tongqian")
            val food = session.extraLong(resource, "food", "liangshi")
            if (copper == null || food == null) {
                ProtocolResult.Err("REAL_RESOURCE_METADATA_MISSING", "真实 session 缺少 copper/food 元数据", retryable = false)
            } else {
                ProtocolResult.Ok(
                    ResourceState(
                        copper = copper,
                        food = food,
                        prestige = session.extraLong(resource, "prestige", "shengwang"),
                        copperPerHour = session.extraInt(resource, "copperPerHour", "moneyPerHour"),
                        foodPerHour = session.extraInt(resource, "foodPerHour"),
                        populationCurrent = session.extraLong(resource, "populationCurrent", "population", "renkou"),
                        populationCap = session.extraLong(resource, "populationCap", "populationLimit"),
                        resourcePointCurrent = session.extraInt(resource, "resourcePointCurrent", "resourcePoint", "resourcePointUsed"),
                        resourcePointCap = session.extraInt(resource, "resourcePointCap", "resourcePointLimit"),
                        raw = (resource?.toStringMap() ?: emptyMap()) + session.channelExtra.filterKeys { it in ROLE_RESOURCE_KEYS }
                    )
                )
            }
        }

    override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> =
        if (!session.isRealSession()) {
            fallback.queryGenerals(session)
        } else {
            val live = session.liveStateBundleOrNull()
            if (live == null) session.liveStateErrorOrNull()?.let {
                return ProtocolResult.Err("REAL_LIVE_STATE_REFRESH_FAILED", "真实 0x1016 状态刷新失败：$it", retryable = true)
            }
            if (live != null) {
                ProtocolResult.Ok(parseGeneralsFromLiveState(live))
            } else {
                val raw = liveSessionExtraCache[session.accountId]?.get("generalsJson")
                    ?: session.firstRecoveredGeneralRaw()
                if (raw.isNullOrBlank()) {
                    unrecovered("REAL_GENERALS_METADATA_MISSING", "真实 session 暂无 generalsJson/jiangLingData/state8004TailUtf8Preview；需继续恢复 0x8004 后段或将领接口")
                } else {
                    runCatching { ProtocolResult.Ok(parseGeneralsFlexible(raw)) }
                        .getOrElse { ProtocolResult.Err("REAL_GENERALS_METADATA_INVALID", "generalsJson/jiangLingData 解析失败：${it.message}", retryable = false) }
                }
            }
        }

    override suspend fun queryFormations(session: GameSession): ProtocolResult<List<FormationRuntime>> =
        if (!session.isRealSession()) {
            fallback.queryFormations(session)
        } else {
            val raw = session.channelExtra["formationsJson"]
            if (!raw.isNullOrBlank()) {
                runCatching {
                    val parsed = parseFormations(raw)
                    val generals = queryGeneralListForFormationStatus(session)
                    ProtocolResult.Ok((parsed + session.recoveredGeneralFallbackFormations(generals)).dedupeByFormationId())
                }
                    .getOrElse { ProtocolResult.Err("REAL_FORMATIONS_METADATA_INVALID", "formationsJson 解析失败：${it.message}", retryable = false) }
            } else {
                val live = session.liveStateBundleOrNull()
                if (live == null) session.liveStateErrorOrNull()?.let {
                    return ProtocolResult.Err("REAL_LIVE_STATE_REFRESH_FAILED", "真实 0x1016 状态刷新失败：$it", retryable = true)
                }
                val prefs = session.recoveredPreferenceMap()
                val recovered = runCatching {
                    val generals = live?.let { parseGeneralsFromLiveState(it) }
                        ?: runCatching { queryGeneralListForFormationStatus(session) }.getOrDefault(emptyList())
                    val recoveredPrefsFormations = parseRecoveredShuaHuangFormations(prefs, generals)
                    val fallbackFormations = session.recoveredGeneralFallbackFormations(generals)
                    val formations = (recoveredPrefsFormations + fallbackFormations)
                        .dedupeByFormationId()
                    formations.let {
                        if (live != null) formations.map { it.withLiveState(live.refreshedAtMillis) } else formations
                    }
                }.getOrElse {
                    return ProtocolResult.Err("REAL_FORMATIONS_METADATA_INVALID", "shuahuangChuzhengBiandui/bianduiDejiangling 解析失败：${it.message}", retryable = false)
                }
                if (recovered.isEmpty()) {
                unrecovered("REAL_FORMATIONS_METADATA_MISSING", "真实 session 暂无 formationsJson；需继续恢复 shuahuangChuzhengBiandui/bianduiDejiangling/bianduihao")
                } else {
                    ProtocolResult.Ok(recovered)
                }
            }
        }

    override suspend fun searchMap(session: GameSession, start: MapCoordinate, policy: MapSearchPolicy): ProtocolResult<List<MapTarget>> =
        if (!session.isRealSession()) {
            fallback.searchMap(session, start, policy)
        } else {
            val raw = session.channelExtra["mapTargetsJson"]
            val rawHex = session.channelExtra["mapTargetsHex"]
                ?: session.channelExtra["targetSearchResponseHex"]
                ?: session.channelExtra["targetSearchResponse"]
            if (!raw.isNullOrBlank()) {
                runCatching {
                    ProtocolResult.Ok(parseMapTargets(raw).filterByPolicy(policy))
                }.getOrElse {
                    ProtocolResult.Err("REAL_MAP_TARGETS_METADATA_INVALID", "mapTargetsJson 解析失败：${it.message}", retryable = false)
                }
            } else if (!rawHex.isNullOrBlank()) {
                runCatching {
                    ProtocolResult.Ok(TargetSearchResponseParser.parse(rawHex).filterByPolicy(policy))
                }.getOrElse {
                    ProtocolResult.Err("REAL_MAP_TARGETS_RESPONSE_INVALID", "041540 响应解析失败：${it.message}", retryable = false)
                }
            } else {
                executeRecoveredTargetSearch(session, start, policy)
                    ?: unrecovered("REAL_MAP_TARGETS_METADATA_MISSING", "真实 session 暂无 mapTargetsJson/mapTargetsHex；需继续恢复 041540 找黄/地图扫描响应")
            }
        }

    override suspend fun dispatchFormation(
        session: GameSession,
        formationId: Long,
        target: MapTarget
    ): ProtocolResult<BattleResult> = dispatchFormationInternal(
        session,
        formationId,
        emptyList(),
        target,
        emptyList()
    )

    override suspend fun dispatchFormation(
        session: GameSession,
        formation: FormationRuntime,
        target: MapTarget
    ): ProtocolResult<BattleResult> = dispatchFormationInternal(
        session,
        formation.id,
        formation.generalIds,
        target,
        emptyList()
    )

    override suspend fun dispatchFormation(
        session: GameSession,
        formation: FormationRuntime,
        target: MapTarget,
        formationRules: List<FormationConfig>
    ): ProtocolResult<BattleResult> = dispatchFormationInternal(
        session,
        formation.id,
        formation.generalIds,
        target,
        formationRules
    )

    private suspend fun dispatchFormationInternal(
        session: GameSession,
        formationId: Long,
        requestedGeneralIds: List<Long>,
        target: MapTarget,
        formationRules: List<FormationConfig>
    ): ProtocolResult<BattleResult> {
        if (!session.isRealSession()) {
            return if (requestedGeneralIds.isEmpty()) {
                fallback.dispatchFormation(session, formationId, target)
            } else {
                fallback.dispatchFormation(
                    session,
                    FormationRuntime(
                        formationId,
                        null,
                        requestedGeneralIds,
                        FormationRuntimeStatus.IDLE,
                        null
                    ),
                    target
                )
            }
        }
        executeRecoveredBrushYellowLiveAction(
            session,
            formationId,
            requestedGeneralIds,
            target,
            formationRules
        )?.let { return it }
        if (!offlineActionFixturesAllowed) {
            return unrecovered(
                "REAL_DISPATCH_LIVE_UNAVAILABLE",
                "真实刷黄发送条件不完整；生产路径禁止使用离线出征回执"
            )
        }
        val raw = session.channelExtra["dispatchResultsJson"]
        return if (raw.isNullOrBlank()) {
            unrecovered("REAL_DISPATCH_METADATA_MISSING", "测试夹具缺少 dispatchResultsJson")
        } else {
            runCatching { parseDispatchResult(raw, formationId, target, session) }
                .getOrElse { ProtocolResult.Err("REAL_DISPATCH_METADATA_INVALID", "dispatchResultsJson 解析失败：${it.message}", retryable = false) }
        }
    }

    override suspend fun clearBrushPendingRecovery(
        session: GameSession
    ): ProtocolResult<StepResult> {
        expeditionTransactions.resolve(session.accountId, "刷黄")
        sessionExtraSink?.invoke(
            session.accountId,
            mapOf(BrushPendingRecovery.SESSION_KEY to "{}")
        )
        return ProtocolResult.Ok(StepResult(true, "刷黄战后治疗和配兵维护已完成"))
    }

    override suspend fun convertFoodToCopper(session: GameSession, mode: ConvertMode): ProtocolResult<ResourceState> {
        if (!session.isRealSession()) return fallback.convertFoodToCopper(session, mode)
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed || !sendReady) return recoveredConvertFoodToCopper(session, mode)
        if (!session.hasRealActionScope("resource-conversion") && !session.hasRealActionScope("brush-yellow")) {
            return ProtocolResult.Err("REAL_CONVERT_SCOPE_NOT_CONFIRMED", "真实粮食转铜需要 resource-conversion 作用域", false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_CONVERT_GAME_HTTP_MISSING", "真实粮食转铜缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_CONVERT_DM_MISSING", "真实粮食转铜缺少 dm", false)
        val current = when (val result = queryResourceState(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val amount = when (mode) {
            ConvertMode.FOOD_TO_COPPER_HALF -> {
                current.food / 2L
            }
            ConvertMode.FOOD_TO_COPPER_THRESHOLD -> {
                val wan = (
                    session.channelExtra["copperFloorWan"]
                        ?: session.channelExtra["foodToCopperWan"]
                    )?.toIntOrNull()
                    ?.takeIf { it in setOf(1, 10, 20, 50) }
                    ?: 1
                val floor = wan * 10_000L
                if (current.copper >= floor) {
                    return ProtocolResult.Ok(current.copy(
                        raw = current.raw + mapOf(
                            "source" to "food-to-copper-floor",
                            "converted" to "false",
                            "copperFloor" to floor.toString()
                        )
                    ))
                }
                val deficit = floor - current.copper
                val copperAmount = maxOf(3_000L, ((deficit + 2_999L) / 3_000L) * 3_000L)
                copperAmount / 3_000L * 10_000L
            }
        }
        return executeFoodToCopperAmount(gameHttp, dm, current, amount)
    }

    private fun executeFoodToCopperAmount(
        gameHttp: String,
        dm: Long,
        current: ResourceState,
        amount: Long,
        reserveFood: Long = 0L
    ): ProtocolResult<ResourceState> {
        if (amount <= 0L || current.food < amount + reserveFood) {
            return ProtocolResult.Err(
                "REAL_CONVERT_FOOD_INSUFFICIENT",
                "粮食不足：当前${current.food}，本次兑换需要$amount，另需预留$reserveFood",
                false
            )
        }
        val response = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(0x1152, GeneralProtocolShapes.buildFoodToCopperPayload(amount)),
                phase = "resource/food-to-copper"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_CONVERT_SEND_EXCEPTION", "粮食转铜异常：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实粮食转铜：food=$amount opcode=0x1152 http=${response.httpCode} " +
                "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!response.ok) return ProtocolResult.Err("REAL_CONVERT_HTTP_FAILED", "粮食转铜 HTTP ${response.httpCode}", false)
        if (0x8152 !in response.responseOpcodes) {
            return ProtocolResult.Err("REAL_CONVERT_RESPONSE_MISSING", "未收到 0x8152 粮食转铜响应", false)
        }
        val bytes = runCatching { response.requirePayloadBytesFor(0x8152) }.getOrNull()
            ?: return ProtocolResult.Err("REAL_CONVERT_RESPONSE_INVALID", "0x8152 响应无法解析", false)
        if (bytes.isEmpty() || bytes[0].toInt() != 0) {
            return ProtocolResult.Err(
                "REAL_CONVERT_REJECTED",
                "粮食转铜被服务器拒绝，状态=${bytes.firstOrNull()?.toInt() ?: "未知"}",
                false
            )
        }
        if (bytes.size < 17) {
            return ProtocolResult.Err("REAL_CONVERT_RESPONSE_SHORT", "0x8152 成功响应缺少最新资源数据", false)
        }
        fun longAt(offset: Int): Long = java.nio.ByteBuffer.wrap(bytes, offset, 8).long
        return ProtocolResult.Ok(ResourceState(
            copper = longAt(1),
            food = longAt(9),
            raw = mapOf(
                "source" to "live/0x1152/0x8152",
                "convertedFood" to amount.toString(),
                "expectedCopperGain" to (amount * 3 / 10).toString()
            )
        ))
    }

    private suspend fun ensureInternalResources(
        session: GameSession,
        required: InternalResourceCost,
        context: String
    ): ProtocolResult<ResourceState> {
        val current = when (val result = queryResourceState(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val floorWan = (
            session.channelExtra["copperFloorWan"]
                ?: session.channelExtra["foodToCopperWan"]
            )?.toIntOrNull()
            ?.takeIf { it in setOf(1, 10, 20, 50) }
            ?: 1
        val floor = maxOf(required.copper, floorWan * 10_000L)
        if (current.copper >= required.copper && current.food >= required.food &&
            current.copper >= floor
        ) {
            return ProtocolResult.Ok(current)
        }
        if (session.channelExtra["foodToCopperEnabled"].asLooseBoolean() == false) {
            return ProtocolResult.Err(
                "REAL_INTERNAL_RESOURCES_INSUFFICIENT",
                "$context 需要铜钱${required.copper}/粮食${required.food}，" +
                    "当前铜钱${current.copper}/粮食${current.food}，粮食转铜未开启",
                false
            )
        }
        if (!session.hasRealActionScope("resource-conversion")) {
            return ProtocolResult.Err(
                "REAL_INTERNAL_CONVERT_SCOPE_NOT_CONFIRMED",
                "$context 资源不足，自动兑换需要 resource-conversion 作用域",
                false
            )
        }
        if (current.food < required.food) {
            return ProtocolResult.Err(
                "REAL_INTERNAL_FOOD_RESERVE_INSUFFICIENT",
                "$context 需要预留粮食${required.food}，当前仅${current.food}",
                false
            )
        }
        if (current.copper >= floor) return ProtocolResult.Ok(current)
        val deficit = floor - current.copper
        val copperAmount = maxOf(3_000L, ((deficit + 2_999L) / 3_000L) * 3_000L)
        val foodAmount = copperAmount / 3_000L * 10_000L
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_CONVERT_GAME_HTTP_MISSING", "$context 缺少gameHttp", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_CONVERT_DM_MISSING", "$context 缺少dm", false)
        return executeFoodToCopperAmount(
            gameHttp,
            dm,
            current,
            foodAmount,
            reserveFood = required.food
        )
    }

    override suspend fun searchMines(session: GameSession, config: MineConfig): ProtocolResult<List<MineSearchResult>> =
        if (!session.isRealSession()) {
            fallback.searchMines(session, config)
        } else {
            val raw = session.channelExtra["mineTargetsJson"]
            val rawHex = session.channelExtra["mineTargetsHex"]
                ?: session.channelExtra["resourcePointSearchResponseHex"]
                ?: session.channelExtra["resourcePointSearchResponse"]
            if (!raw.isNullOrBlank()) {
                runCatching { ProtocolResult.Ok(parseMineSearchResults(raw).filterByMineConfig(config)) }
                    .getOrElse { ProtocolResult.Err("REAL_MINE_TARGETS_METADATA_INVALID", "mineTargetsJson 解析失败：${it.message}", retryable = false) }
            } else if (!rawHex.isNullOrBlank()) {
                runCatching { ProtocolResult.Ok(ResourcePointSearchResponseParser.parse(rawHex).filterByMineConfig(config)) }
                    .getOrElse { ProtocolResult.Err("REAL_MINE_TARGETS_RESPONSE_INVALID", "041542 响应解析失败：${it.message}", retryable = false) }
            } else {
                executeRecoveredMineSearch(session, config)
                    ?: unrecovered("REAL_MINE_TARGETS_METADATA_MISSING", "真实 session 暂无 mineTargetsJson/mineTargetsHex；需继续恢复 041542 找矿/资源点扫描响应")
            }
        }

    override suspend fun revalidateMineTarget(
        session: GameSession,
        mine: MineSearchResult,
        config: MineConfig
    ): ProtocolResult<MineSearchResult> {
        if (!session.isRealSession()) return fallback.revalidateMineTarget(session, mine, config)
        val exactConfig = config.copy(
            start = mine.coordinate,
            searchScope = "定点"
        )
        val result = executeRecoveredMineSearch(session, exactConfig)
            ?: searchMines(session, exactConfig)
        return when (result) {
            is ProtocolResult.Err -> result
            is ProtocolResult.Ok -> result.value.firstOrNull { candidate ->
                candidate.id == mine.id &&
                    candidate.coordinate == mine.coordinate &&
                    MineTargetFilterPolicy.matches(
                        candidate,
                        exactConfig,
                        behaviorContract.mine
                    )
            }?.let { ProtocolResult.Ok(it) }
                ?: ProtocolResult.Err(
                    "REAL_MINE_TARGET_STALE",
                    "矿点(${mine.coordinate.x},${mine.coordinate.y})复核后已失效或不再符合规则",
                    retryable = true
                )
        }
    }

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        formationId: Long
    ): ProtocolResult<StepResult> = occupyMine(session, mine, listOf(formationId))

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>
    ): ProtocolResult<StepResult> = occupyMine(session, mine, generalIds, 45)

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>,
        maxMarchMinutes: Int
    ): ProtocolResult<StepResult> = occupyMine(
        session,
        mine,
        generalIds,
        maxMarchMinutes,
        emptyList()
    )

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>,
        maxMarchMinutes: Int,
        formationRules: List<FormationConfig>
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.occupyMine(session, mine, generalIds)
        val ids = generalIds.distinct()
        if (ids.isEmpty()) {
            return ProtocolResult.Err("REAL_MINE_GENERALS_EMPTY", "真实打矿至少需要选择1名出征将领", false)
        }
        executeRecoveredMineOccupyLiveAction(
            session,
            mine,
            ids,
            maxMarchMinutes.coerceAtLeast(1),
            formationRules
        )?.let { return it }
        if (!offlineActionFixturesAllowed) {
            return unrecovered(
                "REAL_OCCUPY_MINE_LIVE_UNAVAILABLE",
                "真实打矿发送条件不完整；生产路径禁止使用离线占矿回执"
            )
        }
        val raw = session.channelExtra["occupyMineResultsJson"]
        return if (raw.isNullOrBlank()) {
            unrecovered("REAL_OCCUPY_MINE_METADATA_MISSING", "真实 session 暂无 occupyMineResultsJson；资源点 p2=1 payload 形状已恢复，但真实 request wrapper/native/session 仍未接入")
        } else {
            // 历史离线证据按单将领索引；真实联网路径在上方按完整 generalIds 编码。
            runCatching { parseOccupyMineResult(raw, mine, ids.first(), session) }
                .getOrElse { ProtocolResult.Err("REAL_OCCUPY_MINE_METADATA_INVALID", "occupyMineResultsJson 解析失败：${it.message}", retryable = false) }
        }
    }

    private suspend fun executeRecoveredMineOccupyLiveAction(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>,
        maxMarchMinutes: Int,
        formationRules: List<FormationConfig>
    ): ProtocolResult<StepResult>? {
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed && !sendReady) return null
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err(
                "REAL_MINE_GATE_NOT_READY",
                "真实打矿 gate 未同时开启：network=$networkAllowed send=$sendReady",
                false
            )
        }
        if (!session.hasRealActionScope("mine")) {
            return ProtocolResult.Err(
                "REAL_MINE_SCOPE_NOT_CONFIRMED",
                "真实打矿需要独立 mine 作用域",
                false
            )
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_MINE_GAME_HTTP_MISSING", "真实打矿缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_MINE_DM_MISSING", "真实打矿缺少 dm", false)
        if (generalIds.isEmpty() || generalIds.size > 255 || generalIds.any { it <= 0L } || mine.id <= 0L) {
            return ProtocolResult.Err("REAL_MINE_TARGET_INVALID", "真实打矿将领或资源点ID无效", false)
        }
        val preflight = when (val result = expeditionPreflight.check(
            session,
            ExpeditionPreflightRequest(
                label = "打矿",
                generalIds = generalIds,
                formationId = generalIds.firstOrNull(),
                requireFullLoyalty = session.channelExtra["mineRequireFullLoyalty"].asLooseBoolean() == true,
                refillToFull = session.channelExtra["mineReplenishTroops"].asLooseBoolean() == true,
                formationRules = formationRules
            )
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val mineContract = behaviorContract.mine
        if (generalIds.size > mineContract.maximumGeneralsPerFormation) {
            return ProtocolResult.Err(
                "REAL_MINE_GENERALS_OVER_LIMIT",
                "打矿一次最多选择${mineContract.maximumGeneralsPerFormation}名将领",
                false
            )
        }
        val effectiveMaxMarchMinutes = maxMarchMinutes.takeIf {
            it in mineContract.allowedMaxMarchMinutes
        } ?: mineContract.defaultMaxMarchMinutes
        val preparePayload = MineProtocolShapes.buildPreparePayload(
            generalIds,
            mine.id,
            mineContract
        )
        val expeditionPayload = MineProtocolShapes.buildDispatchPayload(
            generalIds,
            mine.id,
            mineContract
        )

        fun send(opcode: Int, payload: ByteArray, phase: String): ProtocolResult<DirectBinaryResponse> {
            val response = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(opcode, payload),
                    phase
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_MINE_SEND_EXCEPTION", "$phase 异常：${it.message}", false)
            }
            if (!response.ok) {
                return ProtocolResult.Err("REAL_MINE_HTTP_FAILED", "$phase HTTP ${response.httpCode}", false)
            }
            return ProtocolResult.Ok(response)
        }

        val prepare = when (val result = send(mineContract.prepareOpcode, preparePayload, "mine/prepare")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val prepareResponseHex = prepare.payloadHexFor(mineContract.prepareResponseOpcode)
        if (mineContract.prepareResponseOpcode !in prepare.responseOpcodes ||
            prepareResponseHex?.filter(Char::isLetterOrDigit).equals("ff0000", true)
        ) {
            return ProtocolResult.Ok(StepResult(
                false,
                "打矿预出征未获得0x${mineContract.prepareResponseOpcode.toString(16)}成功确认"
            ))
        }
        val preview = MineProtocolShapes.parsePreview(
            prepare.requirePayloadBytesFor(mineContract.prepareResponseOpcode),
            mineContract
        )
            ?: return ProtocolResult.Ok(StepResult(false, "打矿预出征0x8520格式无效，已禁止正式出征"))
        if (mineContract.preview.requireTargetCoordinateMatch &&
            (preview.x != mine.coordinate.x || preview.y != mine.coordinate.y)
        ) {
            return ProtocolResult.Ok(StepResult(
                false,
                "打矿预览坐标(${preview.x},${preview.y})与目标(${mine.coordinate.x},${mine.coordinate.y})不一致，已禁止正式出征"
            ))
        }
        if (preview.marchSeconds > effectiveMaxMarchMinutes * 60) {
            val minutes = preview.marchSeconds / 60.0
            return ProtocolResult.Ok(StepResult(
                false,
                "预计到达目标需要${"%.1f".format(java.util.Locale.US, minutes)}分钟，超过设定的${effectiveMaxMarchMinutes}分钟，已禁止正式出征"
            ))
        }
        return expeditionTransactions.execute(
            accountId = session.accountId,
            action = "打矿",
            targetKey = "${mine.id}@${mine.coordinate.x},${mine.coordinate.y}",
            snapshot = preflight,
            exceptionCode = "REAL_MINE_DISPATCH_EXCEPTION",
            exceptionLabel = "打矿正式出征异常"
        ) {
            val expedition = sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(mineContract.dispatchOpcode, expeditionPayload),
                "mine/dispatch"
            )
            if (!expedition.ok) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_MINE_DISPATCH_HTTP_FAILED",
                        "打矿正式出征 HTTP ${expedition.httpCode}，已冻结将领等待状态确认",
                        true
                    ),
                    "HTTP ${expedition.httpCode}; request acceptance is unknown"
                )
            }
            if (mineContract.dispatchResponseOpcode !in expedition.responseOpcodes) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_MINE_DISPATCH_RECEIPT_MISSING",
                        "打矿出征未收到0x${mineContract.dispatchResponseOpcode.toString(16)}，已冻结将领等待状态确认",
                        true
                    ),
                    "2xx response without 0x8522"
                )
            }
            val expeditionResponseHex = expedition.payloadHexFor(mineContract.dispatchResponseOpcode)
            val parsed = BrushYellowDispatchResponseParser.parse(responseHex = expeditionResponseHex)
                ?: BrushYellowDispatchResponseParser.parse(responseText = expedition.textPreview)
            val battleId = parsed?.battleId?.takeIf { it > 0L }
            val success = parsed?.success == true &&
                (!mineContract.dispatchSuccessRequiresPositiveBattleId || battleId != null)
            val step = ProtocolResult.Ok(StepResult(
                success,
                if (success) {
                    "打矿出征已确认：${preflight.generalNames.joinToString("/")} → ${mine.mineType.name}(${mine.coordinate.x},${mine.coordinate.y})"
                } else {
                    parsed?.message ?: "0x8522未确认打矿出征结果，已冻结将领等待状态确认"
                },
                buildMap {
                    put("generalIds", generalIds.joinToString(","))
                    put("generalId", generalIds.first().toString())
                    put("mineId", mine.id.toString())
                    battleId?.let { put("battleId", it.toString()) }
                    put("preparePayloadHex", preparePayload.toHex())
                    put("expeditionPayloadHex", expeditionPayload.toHex())
                    put("prepareResponseHex", prepareResponseHex.orEmpty().take(512))
                    put("expeditionResponseHex", expeditionResponseHex.orEmpty().take(512))
                    put("marchSeconds", preview.marchSeconds.toString())
                    put("maxMarchMinutes", effectiveMaxMarchMinutes.toString())
                    put("parsedEvidence", parsed?.evidence ?: "none")
                }
            ))
            if (success && battleId != null) {
                sessionExtraSink?.invoke(
                    session.accountId,
                    mapOf(
                        "minePendingGarrisonJson" to MinePendingGarrison(
                            battleId = battleId,
                            mineId = mine.id,
                            generalIds = generalIds,
                            x = mine.coordinate.x,
                            y = mine.coordinate.y,
                            targetName = mine.mineType.name,
                            dispatchAtMillis = System.currentTimeMillis(),
                            marchSeconds = preview.marchSeconds
                        ).toJson().toString()
                    )
                )
            }
            when {
                success -> ExpeditionSendResult.accepted(
                    step,
                    "explicit 0x${mineContract.dispatchResponseOpcode.toString(16)} success battleId=$battleId"
                )
                parsed?.success == false -> ExpeditionSendResult.rejected(
                    step,
                    "explicit 0x${mineContract.dispatchResponseOpcode.toString(16)} rejection: ${parsed.evidence}"
                )
                else -> ExpeditionSendResult.uncertain(
                    step,
                    "0x${mineContract.dispatchResponseOpcode.toString(16)} receipt lacks confirmed battleId"
                )
            }
        }
    }

    override suspend fun withdrawMineDefense(
        session: GameSession,
        battleId: Long
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.withdrawMineDefense(session, battleId)
        if (battleId <= 0L) {
            return ProtocolResult.Err("REAL_WITHDRAW_BATTLE_ID_INVALID", "撤防缺少有效驻防战斗 battleId", false)
        }
        if (session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() != true ||
            session.channelExtra["realActionSendReady"].asLooseBoolean() != true
        ) {
            return ProtocolResult.Err("REAL_WITHDRAW_MINE_GATE_NOT_READY", "真实撤防动作 gate 未开启", false)
        }
        if (!session.hasRealActionScope("mine")) {
            return ProtocolResult.Err("REAL_WITHDRAW_MINE_SCOPE_NOT_CONFIRMED", "真实撤防需要 mine 作用域", false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_WITHDRAW_MINE_GAME_HTTP_MISSING", "真实撤防缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_WITHDRAW_MINE_DM_MISSING", "真实撤防缺少 dm", false)
        val withdrawContract = behaviorContract.mine.withdraw
        val payload = MineProtocolShapes.buildWithdrawPayload(battleId, withdrawContract)
        val response = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(withdrawContract.requestOpcode, payload),
                "mine/withdraw:$battleId"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_WITHDRAW_MINE_SEND_EXCEPTION", "撤防请求异常：${it.message}", true)
        }
        actionAudit?.invoke(
            "真实撤防请求：battleId=$battleId opcode=0x${withdrawContract.requestOpcode.toString(16)} http=${response.httpCode} " +
                "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!response.ok) {
            return ProtocolResult.Err("REAL_WITHDRAW_MINE_HTTP_FAILED", "撤防 HTTP ${response.httpCode}", true)
        }
        if (withdrawContract.responseOpcode !in response.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_WITHDRAW_MINE_RESPONSE_MISSING",
                "撤防未收到 0x${withdrawContract.responseOpcode.toString(16)} 回执",
                true
            )
        }
        val receipt = MineProtocolShapes.parseWithdrawReceipt(
            response.requirePayloadBytesFor(withdrawContract.responseOpcode),
            battleId,
            withdrawContract
        )
        if (!receipt.success) {
            return ProtocolResult.Ok(
                StepResult(
                    false,
                    receipt.message,
                    mapOf(
                        "battleId" to battleId.toString(),
                        "requestPayloadHex" to payload.toHex(),
                        "responseHex" to response.payloadHexFor(withdrawContract.responseOpcode).orEmpty().take(1024)
                    )
                )
            )
        }
        val pending = MinePendingGarrison.fromJson(session.channelExtra["minePendingGarrisonJson"])
        if (pending != null && pending.battleId == battleId) {
            sessionExtraSink?.invoke(
                session.accountId,
                mapOf(
                    "minePendingGarrisonJson" to pending.copy(
                        recallRequestedAtMillis = System.currentTimeMillis()
                    ).toJson().toString()
                )
            )
        }
        return ProtocolResult.Ok(
            StepResult(
                true,
                receipt.message,
                mapOf(
                    "battleId" to receipt.battleId.toString(),
                    "recallRequestedAtMillis" to System.currentTimeMillis().toString(),
                    "requestPayloadHex" to payload.toHex(),
                    "responseHex" to response.payloadHexFor(withdrawContract.responseOpcode).orEmpty().take(1024),
                    "responseOpcode" to "0x${withdrawContract.responseOpcode.toString(16)}"
                )
            )
        )
    }

    override suspend fun accelerateMineMarch(
        session: GameSession,
        battleId: Long,
        remainingSeconds: Int
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) {
            return fallback.accelerateMineMarch(session, battleId, remainingSeconds)
        }
        if (battleId <= 0L || remainingSeconds < 0) {
            return ProtocolResult.Err("REAL_MINE_SPEED_INPUT_INVALID", "打矿加速参数无效", false)
        }
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err("REAL_MINE_SPEED_GATE_NOT_READY", "真实打矿加速 gate 未开启", false)
        }
        if (!session.hasRealActionScope("mine")) {
            return ProtocolResult.Err("REAL_MINE_SPEED_SCOPE_NOT_CONFIRMED", "真实打矿加速需要 mine 作用域", false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_MINE_SPEED_GAME_HTTP_MISSING", "真实打矿加速缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_MINE_SPEED_DM_MISSING", "真实打矿加速缺少 dm", false)
        val contract = behaviorContract.mine.speed
        val inventory = when (val result = queryInventory(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return ProtocolResult.Ok(
                StepResult(
                    false,
                    "智能加速跳过：读取行军符库存失败；${result.message}",
                    mapOf("skipped" to "true")
                )
            )
        }
        val counts = inventory
            .filter { it.id.toInt() in contract.itemSeconds }
            .groupingBy { it.id.toInt() }
            .fold(0) { total, item -> total + item.count }
        val choices = MineProtocolShapes.chooseSpeedItems(
            remainingSeconds,
            counts,
            contract
        )
        if (choices.isEmpty()) {
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    if (remainingSeconds <= contract.stopBelowSeconds) {
                        "行军剩余时间已不超过${contract.stopBelowSeconds}秒，无需加速"
                    } else {
                        "宝库中没有可用行军符，跳过加速"
                    },
                    mapOf("skipped" to "true", "battleId" to battleId.toString())
                )
            )
        }
        var estimatedRemaining = remainingSeconds
        val actionSummaries = mutableListOf<String>()
        choices.forEach { itemId ->
            if (estimatedRemaining <= contract.stopBelowSeconds) return@forEach
            val payload = MineProtocolShapes.buildSpeedPayload(battleId, itemId)
            val response = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(contract.requestOpcode, payload),
                    "mine/speed:$battleId:$itemId"
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_MINE_SPEED_SEND_EXCEPTION",
                    "使用行军符#${itemId}异常：${it.message}",
                    true
                )
            }
            actionAudit?.invoke(
                "真实打矿加速：battleId=$battleId item=$itemId " +
                    "opcode=0x${contract.requestOpcode.toString(16)} http=${response.httpCode}"
            )
            if (!response.ok || contract.responseOpcode !in response.responseOpcodes) {
                return ProtocolResult.Ok(
                    StepResult(
                        false,
                        "使用行军符#${itemId}未收到0x${contract.responseOpcode.toString(16)}确认",
                        mapOf("battleId" to battleId.toString(), "actions" to actionSummaries.joinToString(";"))
                    )
                )
            }
            val receipt = MineProtocolShapes.parseSpeedReceipt(
                response.requirePayloadBytesFor(contract.responseOpcode)
            ) ?: return ProtocolResult.Ok(
                StepResult(false, "行军加速回执为空", mapOf("battleId" to battleId.toString()))
            )
            actionSummaries += "$itemId:${receipt.status}"
            if (receipt.finished) {
                return ProtocolResult.Ok(
                    StepResult(
                        true,
                        receipt.message,
                        mapOf("battleId" to battleId.toString(), "actions" to actionSummaries.joinToString(";"))
                    )
                )
            }
            if (!receipt.success) {
                return ProtocolResult.Ok(
                    StepResult(
                        false,
                        receipt.message,
                        mapOf("battleId" to battleId.toString(), "actions" to actionSummaries.joinToString(";"))
                    )
                )
            }
            estimatedRemaining = (
                estimatedRemaining - contract.itemSeconds.getValue(itemId)
            ).coerceAtLeast(0)
        }
        return ProtocolResult.Ok(
            StepResult(
                true,
                "智能加速完成，预计剩余${estimatedRemaining}秒",
                mapOf(
                    "battleId" to battleId.toString(),
                    "estimatedRemainingSeconds" to estimatedRemaining.toString(),
                    "actions" to actionSummaries.joinToString(";")
                )
            )
        )
    }

    override suspend fun clearMinePendingGarrison(
        session: GameSession,
        battleId: Long
    ): ProtocolResult<StepResult> {
        val pending = MinePendingGarrison.fromJson(session.channelExtra["minePendingGarrisonJson"])
        if (pending == null || pending.battleId == battleId) {
            expeditionTransactions.resolve(session.accountId, "打矿")
            sessionExtraSink?.invoke(session.accountId, mapOf("minePendingGarrisonJson" to "{}"))
        }
        return ProtocolResult.Ok(
            StepResult(
                true,
                "打矿驻守状态已清理",
                mapOf("battleId" to battleId.toString())
            )
        )
    }

    override suspend fun runDailyStep(session: GameSession, step: DailyStep): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.runDailyStep(session, step)
        if (step == DailyStep.SALARY && NationalCitizenDailyPolicy.isNationalCitizen(session)) {
            return ProtocolResult.Ok(NationalCitizenDailyPolicy.completedStep())
        }
        executeRecoveredDailyLiveAction(session, step)?.let { return it }
        if (!offlineActionFixturesAllowed) {
            return unrecovered(
                "REAL_DAILY_LIVE_UNAVAILABLE",
                "${step.name} 真实执行条件不完整；生产路径禁止使用离线日常回执"
            )
        }
        val raw = session.channelExtra["dailyStepResultsJson"]
        return if (raw.isNullOrBlank()) {
            unrecovered("REAL_DAILY_METADATA_MISSING", "真实 session 暂无 dailyStepResultsJson；已恢复一键日常 payload 形状，但真实 request wrapper/native/session 仍未接入")
        } else {
            val donationFactorFz = session.channelExtra["dailyDonationFactorFz"]?.toIntOrNull() ?: 1
            runCatching { parseDailyStepResult(raw, step, donationFactorFz, session) }
                .getOrElse { ProtocolResult.Err("REAL_DAILY_METADATA_INVALID", "dailyStepResultsJson 解析失败：${it.message}", retryable = false) }
        }
    }

    override suspend fun queryNationalCities(
        session: GameSession,
        kind: NationalCityKind
    ): ProtocolResult<List<NationalCity>> {
        if (!session.isRealSession()) return fallback.queryNationalCities(session, kind)
        if (NationalCitizenDailyPolicy.isNationalCitizen(session)) {
            return ProtocolResult.Ok(emptyList())
        }
        val contract = behaviorContract.dailyActions.nationalCollect
        val category = when (kind) {
            // 0x1404 captured filters are one based: 1=州城, 2=郡城,
            // 3=县城, 4=小城.  The latter is intentionally never sent.
            NationalCityKind.STATE -> 1
            NationalCityKind.COMMANDERY -> 2
            NationalCityKind.COUNTY -> 3
            // The product rule is explicit: small cities must never be queried.
            NationalCityKind.SMALL,
            NationalCityKind.UNKNOWN -> {
                return ProtocolResult.Ok(emptyList())
            }
        }
        if (category !in contract.includedListCategories) {
            return ProtocolResult.Err(
                "REAL_NATIONAL_CITY_CATEGORY_NOT_ALLOWED",
                "国家征收契约禁止查询分类$category",
                false
            )
        }
        val transport = when (val result = featureTransport(session, "国家城池列表")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val cities = mutableListOf<NationalCity>()
        var page = 1
        var totalPages = 1
        while (page <= totalPages && page <= MAX_FEATURE_PAGES) {
            val response = when (val result = sendFeatureCommand(
                transport,
                contract.cityListRequestOpcode,
                DailyFeatureProtocolShapes.buildNationalCityListPayload(category, page),
                setOf(contract.cityListResponseOpcode),
                "national/list/category=$category/page=$page"
            )) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> return result
            }
            val parsed = runCatching {
                DailyFeatureProtocolShapes.parseNationalCityPage(
                    response.requirePayloadBytesFor(contract.cityListResponseOpcode),
                    category,
                    contract
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_NATIONAL_CITY_PARSE_FAILED",
                    "国家城池列表解析失败 category=$category page=$page：${it.message}",
                    false
                )
            }
            if (parsed.status != 0) {
                return ProtocolResult.Err(
                    "REAL_NATIONAL_CITY_QUERY_REJECTED",
                    "国家城池列表被服务器拒绝：status=${parsed.status}",
                    false
                )
            }
            totalPages = parsed.totalPages.coerceAtLeast(1)
            cities += parsed.cities
            if (parsed.cities.size < contract.pageSize && page >= totalPages) break
            page += 1
        }
        return ProtocolResult.Ok(cities.distinctBy { it.name })
    }

    override suspend fun queryNationalCollectStatus(
        session: GameSession,
        city: NationalCity
    ): ProtocolResult<NationalCollectStatus> {
        if (!session.isRealSession()) return fallback.queryNationalCollectStatus(session, city)
        val contract = behaviorContract.dailyActions.nationalCollect
        val transport = when (val result = featureTransport(session, "国家征收状态")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val response = when (val result = sendFeatureCommand(
            transport,
            contract.statusRequestOpcode,
            DailyFeatureProtocolShapes.buildNationalCityStatusPayload(city.name),
            setOf(contract.statusResponseOpcode),
            "national/status/${city.name}"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            ProtocolResult.Ok(
                DailyFeatureProtocolShapes.parseNationalCollectStatus(
                    response.requirePayloadBytesFor(contract.statusResponseOpcode)
                )
            )
        }.getOrElse {
            ProtocolResult.Err(
                "REAL_NATIONAL_STATUS_PARSE_FAILED",
                "国家征收状态解析失败 ${city.name}：${it.message}",
                false
            )
        }
    }

    override suspend fun collectNationalCity(
        session: GameSession,
        city: NationalCity
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.collectNationalCity(session, city)
        val contract = behaviorContract.dailyActions.nationalCollect
        val transport = when (val result = featureTransport(session, "国家征收")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val response = when (val result = sendFeatureCommand(
            transport,
            contract.collectRequestOpcode,
            DailyFeatureProtocolShapes.buildNationalCollectPayload(city.name),
            setOf(contract.collectResponseOpcode),
            "national/collect/${city.name}"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            val receipt = DailyFeatureProtocolShapes.parseNationalCollectReceipt(
                response.requirePayloadBytesFor(contract.collectResponseOpcode)
            )
            ProtocolResult.Ok(
                StepResult(
                    receipt.success,
                    receipt.message.ifBlank { "国家征收${if (receipt.success) "成功" else "失败"}：${city.name}" },
                    mapOf(
                        "city" to city.name,
                        "currentCopper" to (receipt.values.getOrNull(0)?.toString() ?: ""),
                        "currentFood" to (receipt.values.getOrNull(2)?.toString() ?: ""),
                        "status" to receipt.status.toString()
                    )
                )
            )
        }.getOrElse {
            ProtocolResult.Err(
                "REAL_NATIONAL_COLLECT_PARSE_FAILED",
                "国家征收回执解析失败 ${city.name}：${it.message}",
                false
            )
        }
    }

    override suspend fun queryOwnedFiefs(session: GameSession): ProtocolResult<List<LootTargetFief>> {
        if (!session.isRealSession()) return fallback.queryOwnedFiefs(session)
        val contract = behaviorContract.dailyActions.cityLordCollect
        val transport = when (val result = featureTransport(session, "城主城池列表")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val roleId = session.channelExtra["roleId"]?.parseLongFlexible() ?: session.accountId
        val response = when (val result = sendFeatureCommand(
            transport,
            contract.ownedCityRequestOpcode,
            DailyFeatureProtocolShapes.buildOwnedCityListPayload(
                roleId,
                contract.ownedCityPayloadSuffix
            ),
            setOf(contract.ownedCityResponseOpcode),
            "city-lord/list"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            ProtocolResult.Ok(
                DailyFeatureProtocolShapes.parseOwnedCityList(
                    response.requirePayloadBytesFor(contract.ownedCityResponseOpcode)
                ).map { city ->
                    LootTargetFief(
                        index = city.index,
                        targetId = city.id,
                        name = city.name,
                        cityName = city.name
                    )
                }
            )
        }.getOrElse {
            ProtocolResult.Err(
                "REAL_OWNED_CITY_PARSE_FAILED",
                "自有城池列表解析失败：${it.message}",
                false
            )
        }
    }

    override suspend fun queryRaidFiefs(
        session: GameSession,
        playerName: String
    ): ProtocolResult<List<LootTargetFief>> {
        if (!session.isRealSession()) return fallback.queryRaidFiefs(session, playerName)
        val normalizedName = playerName.trim()
        if (normalizedName.isBlank()) {
            return ProtocolResult.Err("RAID_TARGET_PLAYER_MISSING", "请填写要掠夺的玩家名称", false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_RAID_GAME_HTTP_MISSING", "真实掠夺查询缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_RAID_DM_MISSING", "真实掠夺查询缺少 dm", false)
        val raidContract = behaviorContract.raid
        val payload = runCatching {
            LootProtocolShapes.buildRaidFiefListPayload(normalizedName, raidContract)
        }.getOrElse {
            return ProtocolResult.Err("RAID_TARGET_PLAYER_INVALID", it.message ?: "目标玩家名称无效", false)
        }
        val response = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(raidContract.fiefQueryOpcode, payload),
                "raid/fiefs:$normalizedName"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_RAID_FIEF_QUERY_EXCEPTION", "查询掠夺目标封地异常：${it.message}", true)
        }
        if (!response.ok) {
            return ProtocolResult.Err("REAL_RAID_FIEF_QUERY_HTTP_FAILED", "查询掠夺目标封地 HTTP ${response.httpCode}", true)
        }
        if (raidContract.fiefQueryResponseOpcode !in response.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_RAID_FIEF_QUERY_RESPONSE_MISSING",
                "查询掠夺目标封地未收到 0x${raidContract.fiefQueryResponseOpcode.toString(16)} 回执",
                true
            )
        }
        return runCatching {
            ProtocolResult.Ok(
                LootProtocolShapes.parseFiefList(
                    response.requirePayloadBytesFor(raidContract.fiefQueryResponseOpcode)
                )
            )
        }.getOrElse {
            ProtocolResult.Err("REAL_RAID_FIEF_QUERY_PARSE_FAILED", "掠夺目标封地解析失败：${it.message}", false)
        }
    }

    override suspend fun collectCityLord(
        session: GameSession,
        fief: LootTargetFief
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.collectCityLord(session, fief)
        val contract = behaviorContract.dailyActions.cityLordCollect
        val transport = when (val result = featureTransport(session, "城主征收")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val response = when (val result = sendFeatureCommand(
            transport,
            contract.collectRequestOpcode,
            DailyFeatureProtocolShapes.buildCityLordCollectPayload(fief.cityName),
            setOf(contract.collectResponseOpcode),
            "city-lord/collect/${fief.cityName}"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            val receipt = DailyFeatureProtocolShapes.parseCityLordCollectReceipt(
                response.requirePayloadBytesFor(contract.collectResponseOpcode)
            )
            ProtocolResult.Ok(
                StepResult(
                    receipt.success,
                    receipt.message.ifBlank { "城主征收${if (receipt.success) "成功" else "失败"}：${fief.cityName}" },
                    mapOf("city" to fief.cityName, "status" to receipt.status.toString())
                )
            )
        }.getOrElse {
            ProtocolResult.Err(
                "REAL_CITY_LORD_COLLECT_PARSE_FAILED",
                "城主征收回执解析失败 ${fief.cityName}：${it.message}",
                false
            )
        }
    }

    override suspend fun queryVisitGenerals(session: GameSession): ProtocolResult<GeneralVisitQuery> {
        if (!session.isRealSession()) return fallback.queryVisitGenerals(session)
        if (NationalCitizenDailyPolicy.isNationalCitizen(session)) {
            return ProtocolResult.Ok(
                GeneralVisitQuery(
                    candidates = emptyList(),
                    completed = true,
                    alreadyVisited = false,
                    message = NationalCitizenDailyPolicy.COMPLETED_MESSAGE
                )
            )
        }
        val contract = behaviorContract.dailyActions.generalVisit
        val transport = when (val result = featureTransport(session, "名将列表")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val pageSize = contract.pageSize
        val pages = mutableListOf<GeneralVisitCandidate>()
        var page = 1
        while (page <= MAX_FEATURE_PAGES) {
            val response = when (val result = sendFeatureCommand(
                transport,
                contract.listRequestOpcode,
                DailyFeatureProtocolShapes.buildGeneralListPayload(page, pageSize),
                setOf(contract.listResponseOpcode),
                "general-visit/list/page=$page"
            )) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> return result
            }
            val parsed = runCatching {
                DailyFeatureProtocolShapes.parseGeneralVisitPage(
                    response.requirePayloadBytesFor(contract.listResponseOpcode),
                    contract
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_GENERAL_VISIT_LIST_PARSE_FAILED",
                    "名将列表解析失败 page=$page：${it.message}",
                    false
                )
            }
            if (parsed.alreadyVisited) {
                return ProtocolResult.Ok(
                    GeneralVisitQuery(
                        candidates = emptyList(),
                        completed = true,
                        alreadyVisited = true,
                        message = parsed.message.ifBlank { "本日已经完成名将拜访" }
                    )
                )
            }
            if (parsed.status != 0 && parsed.candidates.isEmpty()) {
                return ProtocolResult.Err(
                    "REAL_GENERAL_VISIT_LIST_REJECTED",
                    "名将列表被服务器拒绝：${parsed.message.ifBlank { "status=${parsed.status}" }}",
                    false
                )
            }
            pages += parsed.candidates.map {
                it.copy(raw = it.raw + mapOf("page" to page.toString(), "pageSize" to pageSize.toString()))
            }
            if (parsed.candidates.size < pageSize || parsed.pageSize <= 0 || page >= 100) break
            page += 1
        }
        return ProtocolResult.Ok(GeneralVisitQuery(candidates = pages.distinctBy { it.id }))
    }

    override suspend fun visitGeneral(
        session: GameSession,
        candidate: GeneralVisitCandidate
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.visitGeneral(session, candidate)
        val contract = behaviorContract.dailyActions.generalVisit
        val transport = when (val result = featureTransport(session, "名将拜访")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val page = candidate.raw["page"]?.toIntOrNull()?.coerceAtLeast(1) ?: 1
        val pageSize = candidate.raw["pageSize"]?.toIntOrNull()
            ?.coerceIn(1, 100)
            ?: DailyFeatureProtocolShapes.DEFAULT_GENERAL_PAGE_SIZE
        val response = when (val result = sendFeatureCommand(
            transport,
            contract.visitRequestOpcode,
            DailyFeatureProtocolShapes.buildGeneralVisitPayload(candidate.id, page, pageSize),
            setOf(contract.visitResponseOpcode),
            "general-visit/${candidate.id}"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            val receipt = DailyFeatureProtocolShapes.parseGeneralVisitReceipt(
                response.requirePayloadBytesFor(contract.visitResponseOpcode),
                contract
            )
            ProtocolResult.Ok(
                StepResult(
                    receipt.completed,
                    receipt.message.ifBlank { "名将拜访${if (receipt.success) "成功" else "失败"}：${candidate.name}" },
                    mapOf(
                        "generalId" to candidate.id.toString(),
                        "generalName" to candidate.name,
                        "status" to receipt.status.toString(),
                        "page" to page.toString(),
                        "alreadyVisited" to receipt.alreadyVisited.toString(),
                        "invitationResolved" to receipt.invitationResolved.toString(),
                        "invitationRejected" to receipt.invitationRejected.toString(),
                        "recruited" to receipt.recruited.toString()
                    )
                )
            )
        }.getOrElse {
            ProtocolResult.Err(
                "REAL_GENERAL_VISIT_PARSE_FAILED",
                "名将拜访回执解析失败 ${candidate.name}：${it.message}",
                false
            )
        }
    }

    private data class FeatureTransport(val gameHttp: String, val dm: Long)

    private fun featureTransport(
        session: GameSession,
        feature: String
    ): ProtocolResult<FeatureTransport> {
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err(
                "REAL_DAILY_FEATURE_GATE_NOT_READY",
                "${feature}真实动作 gate 未同时开启：network=$networkAllowed send=$sendReady",
                false
            )
        }
        if (!session.hasRealActionScope("daily")) {
            return ProtocolResult.Err(
                "REAL_DAILY_FEATURE_SCOPE_NOT_CONFIRMED",
                "${feature}需要 daily 作用域",
                false
            )
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_DAILY_FEATURE_GAME_HTTP_MISSING", "${feature}缺少gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_DAILY_FEATURE_DM_MISSING", "${feature}缺少dm", false)
        return ProtocolResult.Ok(FeatureTransport(gameHttp, dm))
    }

    private fun sendFeatureCommand(
        transport: FeatureTransport,
        opcode: Int,
        payload: ByteArray,
        expectedOpcodes: Set<Int>,
        phase: String
    ): ProtocolResult<DirectBinaryResponse> {
        val response = runCatching {
            sendBinaryMappedGameHex(
                transport.gameHttp,
                transport.dm,
                buildDirectGameHex(opcode, payload),
                phase
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_DAILY_FEATURE_SEND_EXCEPTION", "${phase}异常：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实日常扩展请求：$phase opcode=0x${opcode.toString(16)} http=${response.httpCode} " +
                "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!response.ok) {
            return ProtocolResult.Err("REAL_DAILY_FEATURE_HTTP_FAILED", "$phase HTTP ${response.httpCode}", false)
        }
        if (expectedOpcodes.isNotEmpty() && response.responseOpcodes.none { it in expectedOpcodes }) {
            return ProtocolResult.Err(
                "REAL_DAILY_FEATURE_RESPONSE_MISSING",
                "${phase}未收到${expectedOpcodes.joinToString { "0x${it.toString(16)}" }}",
                false
            )
        }
        return ProtocolResult.Ok(response)
    }

    private fun executeRecoveredDailyLiveAction(
        session: GameSession,
        step: DailyStep
    ): ProtocolResult<StepResult>? {
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed && !sendReady) return null
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err(
                "REAL_DAILY_GATE_NOT_READY",
                "真实日常 gate 未同时开启：realActionNetworkAllowed=$networkAllowed realActionSendReady=$sendReady",
                retryable = false
            )
        }
        if (!session.hasRealActionScope("daily")) {
            return ProtocolResult.Err(
                "REAL_DAILY_SCOPE_NOT_CONFIRMED",
                "真实日常需要独立 realActionScope=daily；不会借用其他功能权限发送",
                retryable = false
            )
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_DAILY_GAME_HTTP_MISSING", "真实日常 session 缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_DAILY_DM_MISSING", "真实日常 session 缺少 dm", false)
        data class DailyCommand(
            val opcode: Int,
            val payload: ByteArray,
            val expectedOpcodes: Set<Int>,
            val requiredForStep: Boolean = true
        )
        val signInContract = behaviorContract.signIn
        val dailyActions = behaviorContract.dailyActions
        val commands = when (step) {
            DailyStep.SIGN_IN -> listOf(
                DailyCommand(
                    signInContract.requestOpcode,
                    ByteArray(0),
                    signInContract.acceptedResponseOpcodes
                ),
                DailyCommand(
                    signInContract.diamondBox.requestOpcode,
                    signInContract.diamondBox.payload,
                    setOf(signInContract.diamondBox.responseOpcode),
                    requiredForStep = false
                )
            )
            DailyStep.ARENA_REWARD -> listOf(
                DailyCommand(dailyActions.arenaCoins.readRequestOpcode, ByteArray(0), emptySet()),
                DailyCommand(
                    dailyActions.arenaCoins.claimRequestOpcode,
                    ByteArray(0),
                    setOf(dailyActions.arenaCoins.claimResponseOpcode)
                )
            )
            DailyStep.SALARY -> listOf(
                DailyCommand(
                    dailyActions.salary.requestOpcode,
                    dailyActions.salary.payload,
                    setOf(dailyActions.salary.responseOpcode)
                )
            )
            DailyStep.DONATE_COPPER,
            DailyStep.DONATE_FOOD,
            DailyStep.DONATE_TECH -> {
                val level = session.channelExtra["level"]?.toIntOrNull()
                    ?: return ProtocolResult.Err("REAL_DAILY_LEVEL_MISSING", "自动捐献无法读取角色等级", false)
                when (step) {
                    DailyStep.DONATE_COPPER -> listOf(
                        DailyCommand(
                            dailyActions.donate.resourceRequestOpcode,
                            DailyFeatureProtocolShapes.buildDonateCopperPayload(
                                level.toLong() * dailyActions.donate.copperPerLevel
                            ),
                            setOf(dailyActions.donate.resourceResponseOpcode)
                        )
                    )
                    DailyStep.DONATE_FOOD -> listOf(
                        DailyCommand(
                            dailyActions.donate.resourceRequestOpcode,
                            DailyFeatureProtocolShapes.buildDonateFoodPayload(
                                level.toLong() * dailyActions.donate.foodPerLevel
                            ),
                            setOf(dailyActions.donate.resourceResponseOpcode)
                        )
                    )
                    DailyStep.DONATE_TECH -> listOf(
                        DailyCommand(
                            dailyActions.donate.technologyRequestOpcode,
                            DailyFeatureProtocolShapes.buildDonateTechPayload(
                                level * dailyActions.donate.technologyPerLevel
                            ),
                            setOf(dailyActions.donate.technologyResponseOpcode)
                        )
                    )
                    else -> emptyList()
                }
            }
            DailyStep.DELETE_MAIL -> listOf(
                DailyCommand(
                    0x1116,
                    DailyProtocolShapes.buildDeleteAllMailPayload(),
                    setOf(0x8116)
                )
            )
            else -> return null
        }
        val responses = mutableListOf<DirectBinaryResponse>()
        var optionalFailure: String? = null
        var signInReceipt: SignInReceipt? = null
        fun commandPayload(
            command: DailyCommand,
            response: DirectBinaryResponse
        ): ByteArray {
            val opcode = command.expectedOpcodes.firstOrNull { it in response.responseOpcodes }
                ?: error("日常响应缺少目标指令负载")
            return response.requirePayloadBytesFor(opcode)
        }
        for (command in commands) {
            val response = try {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(command.opcode, command.payload),
                    phase = "daily/${command.opcode.toString(16)}"
                )
            } catch (error: Throwable) {
                if (!command.requiredForStep) {
                    val failure = "每日金钻宝箱请求异常：${error.message}"
                    optionalFailure = failure
                    actionAudit?.invoke(failure)
                    break
                }
                return ProtocolResult.Err(
                    "REAL_DAILY_SEND_EXCEPTION",
                    "日常请求 0x${command.opcode.toString(16)} 异常：${error.message}",
                    false
                )
            }
            responses += response
            actionAudit?.invoke(
                "真实日常请求：step=${step.name} opcode=0x${command.opcode.toString(16)} " +
                    "http=${response.httpCode} responses=${response.responseOpcodes.joinToString()}"
            )
            if (!response.ok) {
                if (!command.requiredForStep) {
                    optionalFailure = "每日金钻宝箱请求 HTTP ${response.httpCode}"
                    break
                }
                return ProtocolResult.Err(
                    "REAL_DAILY_HTTP_FAILED",
                    "日常请求 0x${command.opcode.toString(16)} HTTP ${response.httpCode}",
                    false
                )
            }
            if (command.expectedOpcodes.isNotEmpty() &&
                response.responseOpcodes.none { it in command.expectedOpcodes }
            ) {
                if (!command.requiredForStep) {
                    optionalFailure = "每日金钻宝箱未返回 " +
                        command.expectedOpcodes.joinToString { "0x${it.toString(16)}" }
                    break
                }
                return ProtocolResult.Ok(
                    StepResult(
                        false,
                        "日常请求0x${command.opcode.toString(16)}未返回 " +
                            command.expectedOpcodes.joinToString { "0x${it.toString(16)}" },
                        mapOf(
                            "requestOpcode" to "0x${command.opcode.toString(16)}",
                            "responseOpcodes" to response.responseOpcodes.joinToString { "0x${it.toString(16)}" }
                        )
                    )
                )
            }
            if (step == DailyStep.SIGN_IN && command.opcode == signInContract.requestOpcode) {
                val receiptOpcode = when {
                    signInContract.activityResponseOpcode in response.responseOpcodes ->
                        signInContract.activityResponseOpcode
                    signInContract.legacyResponseOpcode in response.responseOpcodes ->
                        signInContract.legacyResponseOpcode
                    else -> null
                }
                val receipt = DailySignInReceiptParser.parse(
                    responseOpcodes = response.responseOpcodes,
                    payload = receiptOpcode?.let(response::requirePayloadBytesFor) ?: byteArrayOf(),
                    contract = signInContract
                )
                signInReceipt = receipt
                if (!receipt.success) {
                    return ProtocolResult.Ok(StepResult(
                        false,
                        receipt.message.ifBlank { "签到失败：服务器未确认成功" },
                        mapOf(
                            "responseOpcode" to receipt.responseOpcode?.let { "0x${it.toString(16)}" }.orEmpty(),
                            "serverMessage" to receipt.serverMessage,
                            "alreadyClaimed" to receipt.alreadyClaimed.toString(),
                            "duplicateClaim" to receipt.duplicateClaim.toString()
                        )
                    ))
                }
            }
        }
        val finalReceipt = if (step == DailyStep.ARENA_REWARD) {
            runCatching {
                DailyProtocolShapes.parseArenaCoinClaimResponse(
                    commandPayload(commands[responses.lastIndex], responses.last())
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_DAILY_RECEIPT_INVALID",
                    "ARENA_REWARD回执解析失败：${it.message}",
                    false
                )
            }
        } else {
            null
        }
        val deleteMailReceipt = if (step == DailyStep.DELETE_MAIL) {
            runCatching {
                DailyProtocolShapes.parseDeleteAllMailReceipt(
                    commandPayload(commands[responses.lastIndex], responses.last())
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_DELETE_MAIL_RECEIPT_INVALID",
                    "清空邮件0x8116回执解析失败：${it.message}",
                    false
                )
            }
        } else {
            null
        }
        val salaryReceipt = if (step == DailyStep.SALARY) {
            runCatching {
                DailyFeatureProtocolShapes.parseSalaryReceipt(
                    commandPayload(commands[responses.lastIndex], responses.last()),
                    dailyActions.salary
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_SALARY_RECEIPT_INVALID",
                    "国家俸禄回执解析失败：${it.message}",
                    false
                )
            }
        } else {
            null
        }
        val donationStatusSigned = if (step in setOf(
                DailyStep.DONATE_COPPER,
                DailyStep.DONATE_FOOD,
                DailyStep.DONATE_TECH
            )
        ) {
            commandPayload(commands[responses.lastIndex], responses.last()).firstOrNull()?.toInt()
        } else {
            null
        }
        val donationStatusUnsigned = donationStatusSigned?.and(0xff)
        if (step == DailyStep.ARENA_REWARD && finalReceipt?.success != true) {
                return ProtocolResult.Ok(StepResult(
                    false,
                    finalReceipt?.message?.ifBlank {
                        com.example.dwpmclone.domain.scheduler.ArenaRewardPolicy.UNAVAILABLE_MESSAGE
                    } ?: com.example.dwpmclone.domain.scheduler.ArenaRewardPolicy.UNAVAILABLE_MESSAGE,
                    mapOf("status" to (finalReceipt?.status?.toString() ?: "unknown"))
                ))
        }
        if (step == DailyStep.DELETE_MAIL && deleteMailReceipt?.success != true) {
            return ProtocolResult.Ok(StepResult(
                false,
                "邮件清理响应异常 action=${deleteMailReceipt?.action ?: "未知"} " +
                    "box=${deleteMailReceipt?.boxType ?: "未知"}",
                mapOf(
                    "action" to (deleteMailReceipt?.action?.toString() ?: "unknown"),
                    "boxType" to (deleteMailReceipt?.boxType?.toString() ?: "unknown")
                )
            ))
        }
        if (step == DailyStep.SALARY && salaryReceipt?.success != true) {
            return ProtocolResult.Ok(
                StepResult(
                    false,
                    salaryReceipt?.message?.ifBlank { "当前不能领取俸禄：状态=${salaryReceipt.status}" }
                        ?: "国家俸禄回执为空",
                    mapOf(
                        "status" to (salaryReceipt?.status?.toString() ?: "unknown"),
                        "extra" to (salaryReceipt?.extra?.toString() ?: "unknown")
                    )
                )
            )
        }
        val donationQuotaAlreadyUsed = when (step) {
            // 手机真机上重复执行已捐献账号的回执：
            // 0x840c -3 = 当日资源捐献额度限制；
            // 0x840a -4 = 超过个人单日科技积分捐献额度。
            DailyStep.DONATE_COPPER, DailyStep.DONATE_FOOD -> donationStatusSigned == -3
            DailyStep.DONATE_TECH -> donationStatusSigned == -4
            else -> false
        }
        if (donationQuotaAlreadyUsed) {
            val label = when (step) {
                DailyStep.DONATE_COPPER -> "铜钱"
                DailyStep.DONATE_FOOD -> "粮食"
                DailyStep.DONATE_TECH -> "科技积分"
                else -> ""
            }
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    "${label}今日捐献额度已用完，按已完成处理",
                    mapOf(
                        "alreadyCompleted" to "true",
                        "completionReason" to "daily-donation-quota-used",
                        "statusSigned" to donationStatusSigned.toString(),
                        "status" to donationStatusUnsigned.toString()
                    )
                )
            )
        }
        if (donationStatusSigned != null && donationStatusSigned != 0) {
            return ProtocolResult.Ok(
                StepResult(
                    false,
                    "${step.name}被服务器拒绝，状态=$donationStatusUnsigned",
                    mapOf(
                        "statusSigned" to donationStatusSigned.toString(),
                        "status" to donationStatusUnsigned.toString()
                    )
                )
            )
        }
        val message = when (step) {
            DailyStep.SIGN_IN -> {
                val boxResponse = responses.getOrNull(1)
                val boxReceipt = if (boxResponse != null && optionalFailure == null) {
                    runCatching {
                        DailySignInReceiptParser.parseDiamondBox(
                            commandPayload(commands[1], boxResponse),
                            signInContract
                        )
                    }.getOrNull()
                } else {
                    null
                }
                val signMessage = signInReceipt?.message?.ifBlank { "签到请求已确认" }
                    ?: "签到请求已确认"
                if (boxReceipt?.success == true) {
                    "$signMessage；${boxReceipt.message.ifBlank { "每日金钻宝箱已领取" }}"
                } else {
                    "$signMessage；每日金钻宝箱未领取：" +
                        (optionalFailure
                            ?: boxReceipt?.message
                            ?: "回执无法确认")
                }
            }
            DailyStep.ARENA_REWARD -> finalReceipt?.message?.ifBlank { "竞技奖励领取成功" }
                ?: "竞技奖励领取成功"
            DailyStep.SALARY -> salaryReceipt?.message?.ifBlank { "国家俸禄领取成功" }
                ?: "国家俸禄领取成功"
            DailyStep.DONATE_COPPER -> "已按角色等级最高额度捐献铜钱"
            DailyStep.DONATE_FOOD -> "已按角色等级最高额度捐献粮食"
            DailyStep.DONATE_TECH -> "已按角色等级最高额度捐献科技积分"
            DailyStep.DELETE_MAIL -> "邮件清理完成，剩余${deleteMailReceipt?.remaining ?: 0}封"
            else -> "日常任务完成"
        }
        return ProtocolResult.Ok(StepResult(
            true,
            message,
            mapOf(
                "sender" to "direct-binary-game-command",
                "realActionScope" to "daily",
                "remainingMail" to (deleteMailReceipt?.remaining?.toString() ?: ""),
                "signInAlreadyClaimed" to (signInReceipt?.alreadyClaimed?.toString() ?: ""),
                "signInDuplicateClaim" to (signInReceipt?.duplicateClaim?.toString() ?: ""),
                "arenaAlreadyClaimed" to (finalReceipt?.alreadyClaimed?.toString() ?: ""),
                "arenaDuplicateClaim" to (finalReceipt?.duplicateClaim?.toString() ?: ""),
                "responseOpcodes" to responses
                    .flatMap { it.responseOpcodes }
                    .joinToString { "0x${it.toString(16)}" }
            )
        ))
    }

    override suspend fun healGeneral(session: GameSession, generalId: Long): ProtocolResult<StepResult> =
        if (!session.isRealSession()) {
            fallback.healGeneral(session, generalId)
        } else {
            executeRecoveredHealWoundedLiveAction(session, generalId)
                ?: unrecovered("REAL_HEAL_GATE_CLOSED", "真实治疗需要 brush-yellow 专用动作 gate；当前未开启")
        }

    override suspend fun addEnergy(session: GameSession, generalId: Long): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.addEnergy(session, generalId)
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err("REAL_ENERGY_GATE_NOT_READY", "真实加体动作 gate 未开启", false)
        }
        if (!session.hasRealActionScope("general-maintenance") && !session.hasRealActionScope("brush-yellow")) {
            return ProtocolResult.Err(
                "REAL_ENERGY_SCOPE_NOT_CONFIRMED",
                "真实加体需要 general-maintenance 或 brush-yellow 作用域",
                false
            )
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_ENERGY_GAME_HTTP_MISSING", "真实加体缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_ENERGY_DM_MISSING", "真实加体缺少 dm", false)
        if (generalId <= 0) {
            return ProtocolResult.Err("REAL_ENERGY_GENERAL_INVALID", "真实加体缺少有效将领 ID", false)
        }
        val general = when (val result = queryGenerals(session)) {
            is ProtocolResult.Ok -> result.value.firstOrNull { it.id == generalId }
                ?: return ProtocolResult.Err("REAL_ENERGY_GENERAL_NOT_FOUND", "未找到加体将领 ID=$generalId", false)
            is ProtocolResult.Err -> return result
        }
        if (general.status == null) {
            return ProtocolResult.Err("REAL_ENERGY_STATUS_UNKNOWN", "无法确认将领${general.name}状态，未使用活血丹", false)
        }
        if (general.status != 0) {
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    "将领${general.name}当前非闲，暂不使用活血丹",
                    mapOf("phase" to "waiting-general", "generalId" to generalId.toString())
                )
            )
        }
        val inventory = when (val result = queryInventory(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val energyItem = inventory.firstOrNull { it.id == 12L || it.name == "活血丹" }
        if (energyItem == null || energyItem.count <= 0) {
            return ProtocolResult.Ok(StepResult(false, "宝库没有可用活血丹，未执行加体"))
        }
        val response = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(0x1218, GeneralProtocolShapes.buildAddEnergyPayload(generalId)),
                phase = "general/1218"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_ENERGY_SEND_EXCEPTION", "使用活血丹异常：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实加体请求：general=$generalId item=活血丹 opcode=0x1218 " +
                "http=${response.httpCode} responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!response.ok) {
            return ProtocolResult.Err("REAL_ENERGY_HTTP_FAILED", "使用活血丹 HTTP ${response.httpCode}", false)
        }
        if (0x8218 !in response.responseOpcodes) {
            return ProtocolResult.Ok(StepResult(false, "未收到 0x8218 活血丹响应"))
        }
        val receipt = runCatching {
            GeneralProtocolShapes.parseAddEnergyResponse(response.requirePayloadBytesFor(0x8218))
        }.getOrElse {
            return ProtocolResult.Err(
                "REAL_ENERGY_RECEIPT_INVALID",
                "0x8218 活血丹回执解析失败：${it.message}",
                false
            )
        }
        return ProtocolResult.Ok(StepResult(
            success = receipt.success,
            message = receipt.message,
            raw = mapOf(
                "status" to receipt.status.toString(),
                "generalId" to generalId.toString(),
                "inventoryTrailingBytes" to receipt.trailingBytes.toString()
            )
        ))
    }

    override suspend fun addLoyalty(
        session: GameSession,
        generalId: Long,
        delta: Int
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.addLoyalty(session, generalId, delta)
        if (generalId <= 0L || delta !in 1..0xffff) {
            return ProtocolResult.Err("REAL_LOYALTY_VALUE_INVALID", "加忠将领或数值无效", false)
        }
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err("REAL_LOYALTY_GATE_NOT_READY", "真实加忠动作 gate 未开启", false)
        }
        if (!session.hasRealActionScope("general-maintenance") &&
            !session.hasRealActionScope("mine") &&
            !session.hasRealActionScope("raid")
        ) {
            return ProtocolResult.Err(
                "REAL_LOYALTY_SCOPE_NOT_CONFIRMED",
                "真实加忠需要 general-maintenance、mine 或 raid 作用域",
                false
            )
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_LOYALTY_GAME_HTTP_MISSING", "真实加忠缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_LOYALTY_DM_MISSING", "真实加忠缺少 dm", false)
        val payload = GeneralProtocolShapes.buildAddLoyaltyPayload(generalId, delta)
        val response = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(0x121F, payload),
                "general/add-loyalty:$generalId"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_LOYALTY_SEND_EXCEPTION", "加忠请求异常：${it.message}", true)
        }
        actionAudit?.invoke(
            "真实加忠请求：general=$generalId delta=$delta opcode=0x121f " +
                "http=${response.httpCode} responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!response.ok) {
            return ProtocolResult.Err("REAL_LOYALTY_HTTP_FAILED", "加忠 HTTP ${response.httpCode}", true)
        }
        if (0x821F !in response.responseOpcodes) {
            return ProtocolResult.Ok(StepResult(false, "未收到 0x821f 加忠回执"))
        }
        val receipt = runCatching {
            GeneralProtocolShapes.parseAddLoyaltyResponse(response.requirePayloadBytesFor(0x821F))
        }.getOrElse {
            return ProtocolResult.Err(
                "REAL_LOYALTY_RECEIPT_INVALID",
                "0x821f 加忠回执解析失败：${it.message}",
                false
            )
        }
        val updated = receipt.generals.firstOrNull { it.generalId == generalId }
        val full = receipt.success && updated != null && updated.loyalty >= updated.loyaltyLimit
        return ProtocolResult.Ok(
            StepResult(
                success = full,
                message = when {
                    !receipt.success -> receipt.message
                    updated == null -> "加忠回执未包含将领 ID=$generalId"
                    !full -> "加忠后仍为 ${updated.loyalty}/${updated.loyaltyLimit}"
                    else -> "将领加忠完成：${updated.loyalty}/${updated.loyaltyLimit}"
                },
                raw = buildMap {
                    put("generalId", generalId.toString())
                    put("delta", delta.toString())
                    put("actualCost", receipt.actualCost.toString())
                    put("copper", receipt.copper.toString())
                    updated?.let {
                        put("loyalty", it.loyalty.toString())
                        put("loyaltyLimit", it.loyaltyLimit.toString())
                    }
                }
            )
        )
    }

    override suspend fun updateFormation(session: GameSession, config: FormationConfig): ProtocolResult<StepResult> =
        if (!session.isRealSession()) {
            fallback.updateFormation(session, config)
        } else {
            executeRecoveredFormationUpdateLiveAction(session, config)
                ?: unrecovered("REAL_UPDATE_FORMATION_GATE_CLOSED", "真实配兵/补兵需要 brush-yellow 专用动作 gate；当前未开启")
        }

    override suspend fun runInternalAffairs(session: GameSession, config: InternalAffairsConfig): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.runInternalAffairs(session, config)
        if (!config.enabled && !config.upgradeTechnology) {
            return ProtocolResult.Ok(StepResult(false, "自动内政与升级科技均未启用"))
        }
        if (config.upgradeTechnology && config.technologyIds.isEmpty()) {
            return ProtocolResult.Err("REAL_INTERNAL_TECH_NONE_SELECTED", "升级科技已开启但没有选择科技", false)
        }
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err("REAL_INTERNAL_GATE_NOT_READY", "真实内政动作 gate 未开启", false)
        }
        if (!session.hasRealActionScope("internal-affairs")) {
            return ProtocolResult.Err("REAL_INTERNAL_SCOPE_NOT_CONFIRMED", "真实内政需要 internal-affairs 作用域", false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_INTERNAL_GAME_HTTP_MISSING", "真实内政缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_INTERNAL_DM_MISSING", "真实内政缺少 dm", false)
        val generals = when (val result = queryGenerals(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val fiefIds = generals.mapNotNull { it.placeId?.takeIf { id -> id > 0L } }.distinct().toMutableList()
        val roleName = session.channelExtra["roleName"].orEmpty().trim()
        if (roleName.isNotEmpty()) {
            val ownFiefs = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(0x1310, LootProtocolShapes.buildFiefListPayload(roleName)),
                    phase = "internal/query-owned-fiefs"
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_INTERNAL_OWNED_FIEFS_EXCEPTION",
                    "读取自有封地列表异常：${it.message}",
                    false
                )
            }
            if (!ownFiefs.ok || 0x8310 !in ownFiefs.responseOpcodes) {
                return ProtocolResult.Err(
                    "REAL_INTERNAL_OWNED_FIEFS_FAILED",
                    "读取自有封地列表未收到0x8310",
                    false
                )
            }
            val discovered = runCatching {
                LootProtocolShapes.parseFiefList(
                    requireNotNull(ownFiefs.payloadBytesFor(0x8310)) { "0x8310负载缺失" }
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_INTERNAL_OWNED_FIEFS_INVALID",
                    "自有封地列表解析失败：${it.message}",
                    false
                )
            }
            discovered.map { it.targetId }.filter { it > 0L }.forEach {
                if (it !in fiefIds) fiefIds += it
            }
        }
        if (fiefIds.isEmpty()) {
            return ProtocolResult.Err("REAL_INTERNAL_FIEFS_MISSING", "无法从当前角色数据确认封地 ID，未执行内政", false)
        }
        val fiefStates = mutableListOf<InternalFiefState>()
        for (fiefId in fiefIds) {
            val query = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(0x1246, InternalAffairsProtocolShapes.buildFiefQueryPayload(fiefId)),
                    phase = "internal/query-fief"
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_INTERNAL_QUERY_EXCEPTION", "读取封地${fiefId}建筑异常：${it.message}", false)
            }
            actionAudit?.invoke(
                "真实内政请求：读取封地$fiefId opcode=0x1246 http=${query.httpCode} " +
                    "responses=${query.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
            )
            if (!query.ok || 0x8246 !in query.responseOpcodes) {
                return ProtocolResult.Err("REAL_INTERNAL_QUERY_FAILED", "读取封地${fiefId}未收到0x8246", false)
            }
            val fief = runCatching {
                InternalAffairsProtocolShapes.parseFiefState(
                    requireNotNull(query.payloadBytesFor(0x8246)) { "0x8246负载缺失" },
                    fiefId
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_INTERNAL_BUILDINGS_INVALID", "解析封地${fiefId}建筑失败：${it.message}", false)
            }
            fiefStates += fief
        }
        data class BuildingAction(
            val fief: InternalFiefState,
            val slot: Int,
            val type: Int,
            val previousLevel: Int?,
            val description: String
        )
        fun hasQueue(fief: InternalFiefState): Boolean =
            fief.buildings.count { it.busy } < fief.buildQueueCapacity
        // 电脑端建筑与科技是两个独立 worker。手机端共用一个任务时按轮次交替，
        // 避免持续存在建筑动作时科技任务永远得不到执行。
        val runBuildingsThisCycle = config.enabled &&
            !(config.upgradeTechnology && internalTechnologyTurns[session.accountId] == true)

        val hallAction = if (runBuildingsThisCycle) {
            fiefStates
                .filter(::hasQueue)
                .mapNotNull { fief ->
                    fief.buildings.firstOrNull { it.typeId == 0 }
                        ?.takeIf { InternalAffairsProtocolShapes.hallMustUpgradeFirst(fief) }
                        ?.let { hall ->
                            BuildingAction(
                                fief, hall.slotOrIndex, 0, hall.rank,
                                "优先升级大厅${hall.rank}→${hall.rank + 1}"
                            )
                        }
                }
                .minWithOrNull(compareBy<BuildingAction> { it.previousLevel ?: Int.MAX_VALUE }.thenBy { it.fief.fiefId })
        } else {
            null
        }

        val emptyType = config.buildWhenEmpty?.let(InternalAffairsProtocolShapes::buildingTypeId) ?: -1
        val emptyAction = if (runBuildingsThisCycle && hallAction == null && emptyType >= 0) {
            fiefStates.asSequence()
                .filter(::hasQueue)
                .mapNotNull { fief ->
                    val occupied = fief.buildings.map { it.slotOrIndex }.toSet()
                    (1..12).firstOrNull { it !in occupied }?.let { slot ->
                        BuildingAction(
                            fief, slot, emptyType, null,
                            "空地建造${InternalAffairsProtocolShapes.buildingName(emptyType)}"
                        )
                    }
                }
                .firstOrNull()
        } else {
            null
        }
        val priorityIds = config.buildingPriority
            .map(InternalAffairsProtocolShapes::buildingTypeId)
            .filter { it >= 0 }
        val upgradeAction = if (
            runBuildingsThisCycle && config.upgradeBuildings &&
            hallAction == null && emptyAction == null
        ) {
            fiefStates.asSequence()
                .filter(::hasQueue)
                .flatMap { fief ->
                    fief.buildings.asSequence()
                        .filter { InternalAffairsProtocolShapes.buildingCanFollowHall(fief, it) }
                        .map { building -> fief to building }
                }
                .sortedWith(
                    compareBy<Pair<InternalFiefState, InternalBuildingShape>> {
                        priorityIds.indexOf(it.second.typeId)
                            .takeIf { index -> index >= 0 } ?: Int.MAX_VALUE
                    }.thenBy {
                        if (config.upgradeLowestFirst) it.second.rank else -it.second.rank
                    }.thenBy { it.first.fiefId }.thenBy { it.second.slotOrIndex }
                )
                .firstOrNull()
                ?.let { (fief, building) ->
                    BuildingAction(
                        fief, building.slotOrIndex, building.typeId, building.rank,
                        "升级${InternalAffairsProtocolShapes.buildingName(building.typeId)}" +
                            "${building.rank}→${building.rank + 1}"
                    )
                }
        } else {
            null
        }
        val action = hallAction ?: emptyAction ?: upgradeAction
        if (action != null) run {
            if (config.upgradeTechnology) internalTechnologyTurns[session.accountId] = true
            data class BuildingAttempt(
                val receipt: InternalBuildingActionReceipt,
                val confirmedBy: String?
            )
            fun attempt(phaseSuffix: String): ProtocolResult<BuildingAttempt> {
                val response = runCatching {
                    sendBinaryMappedGameHex(
                        gameHttp,
                        dm,
                        buildDirectGameHex(
                            0x1200,
                            InternalAffairsProtocolShapes.buildBuildingActionPayload(
                                action.fief.fiefId,
                                action.slot,
                                action.type
                            )
                        ),
                        phase = "internal/build-$phaseSuffix"
                    )
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_INTERNAL_ACTION_EXCEPTION",
                        "${action.description}异常：${it.message}",
                        false
                    )
                }
                if (!response.ok || 0x8200 !in response.responseOpcodes) {
                    return ProtocolResult.Err(
                        "REAL_INTERNAL_ACTION_FAILED",
                        "${action.description}未收到0x8200",
                        false
                    )
                }
                val receipt = runCatching {
                    InternalAffairsProtocolShapes.parseBuildingActionResponse(
                        requireNotNull(response.payloadBytesFor(0x8200)) { "0x8200负载缺失" }
                    )
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_INTERNAL_ACTION_RECEIPT_INVALID",
                        "${action.description}回执解析失败：${it.message}",
                        false
                    )
                }
                var confirmedBy = if (InternalAffairsProtocolShapes.actionWasApplied(
                        receipt,
                        action.fief.fiefId,
                        action.slot,
                        action.type,
                        action.previousLevel
                    )
                ) {
                    "0x8200建筑同步"
                } else {
                    null
                }
                if (receipt.success && confirmedBy == null) {
                    val recheck = runCatching {
                        sendBinaryMappedGameHex(
                            gameHttp,
                            dm,
                            buildDirectGameHex(
                                0x1246,
                                InternalAffairsProtocolShapes.buildFiefQueryPayload(action.fief.fiefId)
                            ),
                            phase = "internal/verify-fief-$phaseSuffix"
                        )
                    }.getOrNull()
                    if (recheck?.ok == true && 0x8246 in recheck.responseOpcodes) {
                        val checked = runCatching {
                            InternalAffairsProtocolShapes.parseFiefState(
                                requireNotNull(recheck.payloadBytesFor(0x8246)) { "0x8246负载缺失" },
                                action.fief.fiefId
                            )
                        }.getOrNull()
                        val checkedBuilding = checked?.buildings?.firstOrNull {
                            it.slotOrIndex == action.slot && it.typeId == action.type
                        }
                        if (checkedBuilding != null &&
                            (action.previousLevel == null ||
                                checkedBuilding.rank > action.previousLevel ||
                                checkedBuilding.busy)
                        ) {
                            confirmedBy = "提交后0x8246复查"
                        }
                    }
                }
                return ProtocolResult.Ok(BuildingAttempt(receipt, confirmedBy))
            }
            var buildingAttempt = when (val first = attempt("first")) {
                is ProtocolResult.Ok -> first.value
                is ProtocolResult.Err -> return first
            }
            var convertedFood: String? = null
            if (!buildingAttempt.receipt.success || buildingAttempt.confirmedBy == null) {
                val targetLevel = (action.previousLevel ?: 0) + 1
                val cost = InternalAffairsCostTable.building(action.type, targetLevel)
                    ?: return ProtocolResult.Err(
                        "REAL_INTERNAL_BUILDING_COST_MISSING",
                        "${action.description}缺少建筑成本表：类型${action.type} 等级$targetLevel",
                        false
                    )
                val resources = when (val ensured = ensureInternalResources(
                    session,
                    cost,
                    "${action.description}失败后"
                )) {
                    is ProtocolResult.Ok -> ensured.value
                    is ProtocolResult.Err -> return ensured
                }
                convertedFood = resources.raw["convertedFood"]
                if (convertedFood != null &&
                    resources.copper >= cost.copper &&
                    resources.food >= cost.food
                ) {
                    buildingAttempt = when (val retried = attempt("after-convert")) {
                        is ProtocolResult.Ok -> retried.value
                        is ProtocolResult.Err -> return retried
                    }
                }
            }
            if (!buildingAttempt.receipt.success || buildingAttempt.confirmedBy == null) {
                return ProtocolResult.Ok(StepResult(
                    false,
                    if (!buildingAttempt.receipt.success) {
                        "${action.description}被服务器拒绝，状态=" +
                            "${buildingAttempt.receipt.status}/${buildingAttempt.receipt.substatus}"
                    } else {
                        "${action.description}回执未证明建筑状态已变化"
                    },
                    mapOf(
                        "phase" to "not-confirmed",
                        "convertedFood" to (convertedFood ?: "0")
                    )
                ))
            }
            return ProtocolResult.Ok(StepResult(
                true,
                "${action.description}已确认",
                mapOf(
                    "actionSubmitted" to "true",
                    "actionKind" to "building",
                    "fiefId" to action.fief.fiefId.toString(),
                    "fiefName" to action.fief.name,
                    "slot" to action.slot.toString(),
                    "buildingType" to action.type.toString(),
                    "confirmedBy" to (buildingAttempt.confirmedBy ?: "unknown"),
                    "convertedFood" to (convertedFood ?: "0"),
                    "nextDelayMillis" to
                        InternalAffairsProtocolShapes.nextCheckDelayMillis(fiefStates).toString()
                )
            ))
        }
        if (config.upgradeTechnology) {
            if (config.enabled) internalTechnologyTurns[session.accountId] = false
            val stateHex = session.liveStateBundleOrNull()?.state?.payloadHex
                ?.takeIf { it.isNotBlank() }
                ?: session.channelExtra["state8004PayloadHex"]?.takeIf { it.isNotBlank() }
                ?: return ProtocolResult.Err(
                    "REAL_INTERNAL_TECH_STATE_MISSING",
                    "升级科技缺少最新0x8004科技状态表",
                    false
                )
            val technologyStates = runCatching {
                InternalAffairsProtocolShapes.parseTechnologyStatesFrom8004(
                    stateHex.hexToBytesLocal()
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_INTERNAL_TECH_STATE_INVALID",
                    "0x8004科技状态解析失败：${it.message}",
                    false
                )
            }
            val occupiedAcademies = technologyStates
                .filter { it.researching }
                .mapNotNullTo(mutableSetOf()) { it.academyInstanceId }
            val academies = fiefStates.flatMap { fief ->
                fief.buildings
                    .filter {
                        it.typeId == 3 && !it.busy &&
                            it.instanceId !in occupiedAcademies
                    }
                    .map { fief to it }
            }
            if (academies.isEmpty()) {
                return ProtocolResult.Ok(StepResult(
                    true,
                    "所有书院均被建筑任务或科技研究占用，等待下次检查",
                    mapOf(
                        "nextDelayMillis" to
                            InternalAffairsProtocolShapes.nextCheckDelayMillis(fiefStates).toString()
                    )
                ))
            }
            val selectedOrder = config.technologyIds
                .filter { it in 0..21 }
                .toList()
            val researchingIds = technologyStates
                .filter { it.researching }
                .mapTo(mutableSetOf()) { it.technologyId }
            data class TechnologyCandidate(
                val fief: InternalFiefState,
                val academy: InternalBuildingShape,
                val technology: InternalTechnologyState
            )
            val candidate = academies.asSequence()
                .flatMap { (fief, academy) ->
                    technologyStates.asSequence()
                        .filter {
                            it.technologyId in selectedOrder &&
                                it.technologyId !in researchingIds &&
                                it.level < academy.rank
                        }
                        .map { TechnologyCandidate(fief, academy, it) }
                }
                .minWithOrNull(
                    compareBy<TechnologyCandidate> { it.technology.level }
                        .thenBy { selectedOrder.indexOf(it.technology.technologyId) }
                        .thenBy { it.fief.fiefId }
                )
                ?: return ProtocolResult.Ok(StepResult(
                    true,
                    "所选科技均已达到空闲书院等级或正在其他封地升级",
                    mapOf(
                        "nextDelayMillis" to
                            InternalAffairsProtocolShapes.nextCheckDelayMillis(fiefStates).toString()
                    )
                ))
            val targetLevel = candidate.technology.level + 1
            val technologyCost = InternalAffairsCostTable.technology(
                candidate.technology.technologyId,
                targetLevel
            ) ?: return ProtocolResult.Err(
                "REAL_INTERNAL_TECH_COST_MISSING",
                "科技${candidate.technology.technologyId}缺少$targetLevel 级成本表",
                false
            )
            val ensuredResources = when (val ensured = ensureInternalResources(
                session,
                technologyCost,
                "升级科技${candidate.technology.technologyId}前"
            )) {
                is ProtocolResult.Ok -> ensured.value
                is ProtocolResult.Err -> return ensured
            }
            if (ensuredResources.copper < technologyCost.copper ||
                ensuredResources.food < technologyCost.food
            ) {
                return ProtocolResult.Err(
                    "REAL_INTERNAL_TECH_RESOURCES_STILL_INSUFFICIENT",
                    "升级科技${candidate.technology.technologyId}兑换后仍不足：" +
                        "需要铜钱${technologyCost.copper}/粮食${technologyCost.food}，" +
                        "当前铜钱${ensuredResources.copper}/粮食${ensuredResources.food}",
                    false
                )
            }
            val response = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(
                        0x123F,
                        InternalAffairsProtocolShapes.buildTechnologyUpgradePayload(
                            candidate.fief.fiefId,
                            candidate.academy.slotOrIndex,
                            candidate.technology.technologyId,
                            targetLevel
                        )
                    ),
                    phase = "internal/upgrade-technology"
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_INTERNAL_TECH_SEND_EXCEPTION",
                    "升级科技异常：${it.message}",
                    false
                )
            }
            if (!response.ok || 0x823F !in response.responseOpcodes) {
                return ProtocolResult.Err(
                    "REAL_INTERNAL_TECH_RESPONSE_MISSING",
                    "升级科技未收到0x823f",
                    false
                )
            }
            val receipt = runCatching {
                DailyProtocolShapes.parseStatusMessage(
                    requireNotNull(response.payloadBytesFor(0x823F)) { "0x823f负载缺失" }
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_INTERNAL_TECH_RECEIPT_INVALID",
                    "科技升级回执解析失败：${it.message}",
                    false
                )
            }
            if (!receipt.success) {
                return ProtocolResult.Ok(StepResult(
                    false,
                    receipt.message.ifBlank { "科技升级失败，状态=${receipt.status}" },
                    mapOf(
                        "technologyId" to candidate.technology.technologyId.toString(),
                        "status" to receipt.status.toString(),
                        "convertedFood" to (ensuredResources.raw["convertedFood"] ?: "0")
                    )
                ))
            }
            return ProtocolResult.Ok(StepResult(
                true,
                receipt.message.ifBlank {
                    "科技${candidate.technology.technologyId}" +
                        "${candidate.technology.level}→${targetLevel}级已提交"
                },
                mapOf(
                    "actionSubmitted" to "true",
                    "actionKind" to "technology",
                    "technologyId" to candidate.technology.technologyId.toString(),
                    "fromLevel" to candidate.technology.level.toString(),
                    "targetLevel" to targetLevel.toString(),
                    "fiefId" to candidate.fief.fiefId.toString(),
                    "academySlot" to candidate.academy.slotOrIndex.toString(),
                    "requiredCopper" to technologyCost.copper.toString(),
                    "requiredFood" to technologyCost.food.toString(),
                    "convertedFood" to (ensuredResources.raw["convertedFood"] ?: "0"),
                    "nextDelayMillis" to
                        InternalAffairsProtocolShapes.nextCheckDelayMillis(fiefStates).toString()
                )
            ))
        }
        return ProtocolResult.Ok(StepResult(
            true,
            "当前封地没有可执行的内政操作",
            mapOf(
                "nextDelayMillis" to
                    InternalAffairsProtocolShapes.nextCheckDelayMillis(fiefStates).toString()
            )
        ))
    }

    override suspend fun runSixMinistries(
        session: GameSession,
        config: SixMinistriesConfig
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.runSixMinistries(session, config)
        config.preparationError()?.let {
            return ProtocolResult.Err("REAL_MINISTRY_CONFIG_UNSUPPORTED", it, false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_MINISTRY_GAME_HTTP_MISSING", "六部缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_MINISTRY_DM_MISSING", "六部缺少 dm", false)

        if (session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() != true ||
            session.channelExtra["realActionSendReady"].asLooseBoolean() != true
        ) {
            return ProtocolResult.Err("REAL_MINISTRY_GATE_NOT_READY", "真实六部种菜动作 gate 未开启", false)
        }
        if (!session.hasRealActionScope("ministry-plant")) {
            return ProtocolResult.Err(
                "REAL_MINISTRY_SCOPE_NOT_CONFIRMED",
                "真实六部种菜需要 ministry-plant 作用域",
                false
            )
        }

        fun queryStatus(phase: String): ProtocolResult<MinistryGardenStatus> {
            val response = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(0x6320, MinistryProtocolShapes.buildStatusQueryPayload()),
                    phase
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_MINISTRY_STATUS_EXCEPTION", "读取六部菜地异常：${it.message}", false)
            }
            actionAudit?.invoke(
                "真实六部请求：查询菜地 opcode=0x6320 http=${response.httpCode} " +
                    "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
            )
            if (!response.ok || 0xe320 !in response.responseOpcodes) {
                return ProtocolResult.Err("REAL_MINISTRY_STATUS_FAILED", "六部菜地未收到0xe320", false)
            }
            return runCatching {
                ProtocolResult.Ok(
                    MinistryProtocolShapes.parseGardenStatus(response.requirePayloadBytesFor(0xe320))
                )
            }.getOrElse {
                ProtocolResult.Err("REAL_MINISTRY_STATUS_INVALID", "六部菜地状态解析失败：${it.message}", false)
            }
        }

        val before = when (val result = queryStatus("ministry/status-before")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (before.emptyCount == 0) {
            val unsupported = buildList {
                if (config.stealEnabled) add("偷菜动作")
                if (config.courtesyEnabled) add("礼部任务")
                if (config.salaryRefresh) add("俸禄刷新")
            }
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    "六部菜地已满；收菜、偷菜和礼部动作未确认，等待下次检查",
                    mapOf(
                        "phase" to "garden-full",
                        "occupied" to before.occupiedCount.toString(),
                        "plots" to before.plotCount.toString(),
                        "networkMutation" to "false",
                        "unsupportedEnabled" to unsupported.joinToString(",")
                    )
                )
            )
        }
        val plant = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(0x6328, MinistryProtocolShapes.buildPlantPayload(config.crop)),
                "ministry/plant"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_MINISTRY_PLANT_EXCEPTION", "六部种菜异常：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实六部请求：种${config.crop} opcode=0x6328 http=${plant.httpCode} " +
                "responses=${plant.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!plant.ok || 0xe328 !in plant.responseOpcodes) {
            return ProtocolResult.Err("REAL_MINISTRY_PLANT_FAILED", "六部种菜未收到0xe328", false)
        }
        val receipt = runCatching {
            MinistryProtocolShapes.parsePlantResponse(plant.requirePayloadBytesFor(0xe328))
        }.getOrElse {
            return ProtocolResult.Err("REAL_MINISTRY_PLANT_RECEIPT_INVALID", "六部种菜回执解析失败：${it.message}", false)
        }
        if (!receipt.success) {
            return ProtocolResult.Ok(StepResult(false, "六部种菜失败：${receipt.message}"))
        }
        val after = when (val result = queryStatus("ministry/status-after")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (after.occupiedCount != before.occupiedCount + 1 ||
            after.emptyCount != before.emptyCount - 1
        ) {
            return ProtocolResult.Err(
                "REAL_MINISTRY_PLANT_NOT_CONFIRMED",
                "0xe328返回成功，但0xe320未确认菜地占用数增加，禁止视为成功",
                false
            )
        }
        val unsupported = buildList {
            if (config.stealEnabled) add("偷菜动作")
            if (config.courtesyEnabled) add("礼部任务")
            if (config.salaryRefresh) add("俸禄刷新")
        }
        return ProtocolResult.Ok(
            StepResult(
                true,
                "已种植${config.crop}，菜地${after.occupiedCount}/${after.plotCount}",
                mapOf(
                    "phase" to "planted",
                    "crop" to config.crop,
                    "cropId" to MinistryProtocolCrop.VERIFIED_ID.toString(),
                    "occupiedBefore" to before.occupiedCount.toString(),
                    "occupiedAfter" to after.occupiedCount.toString(),
                    "unsupportedEnabled" to unsupported.joinToString(",")
                )
            )
        )
    }

    override suspend fun runDungeon(session: GameSession, config: DungeonConfig): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.runDungeon(session, config)
        if (!config.enabled) return ProtocolResult.Ok(StepResult(false, "副本任务未启用"))
        val contract = behaviorContract.dungeon
        if (config.formationIds.isEmpty()) {
            return ProtocolResult.Err("REAL_DUNGEON_GENERALS_MISSING", "副本至少需要选择一个将领", false)
        }
        if (config.formationIds.distinct().size > contract.maximumGeneralsPerFormation) {
            return ProtocolResult.Err(
                "REAL_DUNGEON_GENERALS_OVER_LIMIT",
                "副本最多选择${contract.maximumGeneralsPerFormation}名将领",
                false
            )
        }
        if (config.boxPosition !in contract.chestNames.indices) {
            return ProtocolResult.Err("REAL_DUNGEON_CHEST_INVALID", "副本宝箱位置必须为左、中、右", false)
        }
        if (config.mode !in contract.allowedModes) {
            return ProtocolResult.Err("REAL_DUNGEON_MODE_INVALID", "副本模式无效：${config.mode}", false)
        }
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err("REAL_DUNGEON_GATE_NOT_READY", "真实副本动作 gate 未开启", false)
        }
        if (!session.hasRealActionScope("dungeon")) {
            return ProtocolResult.Err("REAL_DUNGEON_SCOPE_NOT_CONFIRMED", "真实副本需要 dungeon 作用域", false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_DUNGEON_GAME_HTTP_MISSING", "真实副本缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_DUNGEON_DM_MISSING", "真实副本缺少 dm", false)
        val generals = when (val result = queryGenerals(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        // The computer helper persists the current stage and always settles that stage before
        // selecting another one. Android uses the session field first, then the durable send
        // ledger as a second source so a fresh login/process restart cannot lose an accepted run.
        val recoveredPending = pendingDungeonFor(session)
            ?: recoverPendingDungeonFromTransaction(session, config)
        val activeDungeonMode = recoveredPending?.mode ?: config.mode
        val selectedGeneralIds = recoveredPending?.generalIds ?: config.formationIds
        val selected = selectedGeneralIds.map { id ->
            generals.firstOrNull { it.id == id }
                ?: return ProtocolResult.Err("REAL_DUNGEON_GENERAL_NOT_FOUND", "副本未找到将领 ID=$id", false)
        }

        var missingBattleStateAssumedIdle = false
        var missingBattleStateWithPending = false
        fun queryBattleState(): ProtocolResult<DungeonBattleStatus> {
            val response = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(contract.stateRequestOpcode, byteArrayOf()),
                    "dungeon/state"
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_DUNGEON_STATE_EXCEPTION", "读取副本状态异常：${it.message}", true)
            }
            if (!response.ok) {
                return ProtocolResult.Err(
                    "REAL_DUNGEON_STATE_HTTP_FAILED",
                    "读取副本状态请求失败（HTTP ${response.httpCode}）",
                    true
                )
            }
            if (contract.stateResponseOpcode !in response.responseOpcodes) {
                // Desktop parity: the desktop helper treats a missing 0x8938 packet as
                // active=false and proceeds to the live catalog. This is safe only when
                // there is no persisted launch awaiting settlement; otherwise another
                // dispatch could duplicate an already accepted dungeon run.
                if (recoveredPending == null) {
                    missingBattleStateAssumedIdle = true
                    return ProtocolResult.Ok(DungeonBattleStatus(DungeonBattlePhase.IDLE))
                }
                missingBattleStateWithPending = true
                return ProtocolResult.Ok(DungeonBattleStatus(DungeonBattlePhase.IDLE))
            }
            return runCatching {
                ProtocolResult.Ok(
                    DungeonProtocolShapes.parseBattleState(
                        requireNotNull(response.payloadBytesFor(contract.stateResponseOpcode)) {
                            "0x${contract.stateResponseOpcode.toString(16)}负载缺失"
                        }
                    )
                )
            }.getOrElse {
                ProtocolResult.Err("REAL_DUNGEON_STATE_INVALID", "副本状态解析失败：${it.message}", false)
            }
        }

        fun openConfiguredChest(reason: String): ProtocolResult<StepResult> {
            val pending = pendingDungeonFor(session)
            val chestPosition = pending?.chestPosition ?: config.boxPosition
            val mode = pending?.mode ?: config.mode
            if (pending?.chestOpened != true) {
                val chest = sendDungeonCommand(
                    gameHttp, dm, contract.chestRequestOpcode,
                    DungeonProtocolShapes.buildOpenChestPayload(chestPosition),
                    expectedOpcode = contract.chestResponseOpcode,
                    phase = "dungeon/open-chest"
                )
                if (chest is ProtocolResult.Err) return chest
                val chestStep = (chest as ProtocolResult.Ok).value
                if (!chestStep.success) return chest
                // The desktop task persists its current stage. Persist the chest phase before
                // the follow-up catalog query as well, so a restart cannot claim it twice.
                pending?.let { persistPendingDungeon(session, it.copy(chestOpened = true)) }
            }
            var completionEvidence = reason + if (pending?.chestOpened == true) {
                "+persisted-chest-opened"
            } else {
                "+0x${contract.chestResponseOpcode.toString(16)}"
            }
            if (mode == "clear" && contract.clearModeRequiresCatalogConfirmation) {
                if (pending == null) {
                    return ProtocolResult.Ok(
                        StepResult(
                            false,
                            "打通副本宝箱已开启，但缺少本轮关卡状态，无法确认通关；已暂停避免重复出征",
                            mapOf("phase" to "clear-confirmation-missing")
                        )
                    )
                }
                val catalogResponse = runCatching {
                    sendBinaryMappedGameHex(
                        gameHttp,
                        dm,
                        buildDirectGameHex(contract.catalogRequestOpcode, byteArrayOf()),
                        "dungeon/confirm-clear-stage"
                    )
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_DUNGEON_CLEAR_CONFIRM_EXCEPTION",
                        "打通副本开箱后读取目录异常：${it.message}",
                        true
                    )
                }
                if (!catalogResponse.ok ||
                    contract.catalogResponseOpcode !in catalogResponse.responseOpcodes
                ) {
                    return ProtocolResult.Err(
                        "REAL_DUNGEON_CLEAR_CONFIRM_UNCONFIRMED",
                        "打通副本开箱后未收到目录确认",
                        true
                    )
                }
                val catalog = runCatching {
                    DungeonProtocolShapes.parseCatalog(
                        requireNotNull(catalogResponse.payloadBytesFor(contract.catalogResponseOpcode)) {
                            "0x${contract.catalogResponseOpcode.toString(16)}负载缺失"
                        }
                    )
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_DUNGEON_CLEAR_CONFIRM_INVALID",
                        "打通副本开箱后目录解析失败：${it.message}",
                        false
                    )
                }
                if (DungeonProtocolShapes.stageCompleted(
                        catalog,
                        pending.chapter,
                        pending.stage,
                        contract
                    ) != true
                ) {
                    clearPendingDungeon(session)
                    return ProtocolResult.Ok(
                        StepResult(
                            false,
                            "第${pending.chapter + 1}章第${pending.stage}关战斗结束，但目录未确认通关；打通副本已暂停",
                            mapOf(
                                "phase" to "clear-unconfirmed",
                                "chapter" to pending.chapter.toString(),
                                "stage" to pending.stage.toString()
                            )
                        )
                    )
                }
                completionEvidence += "+catalog-result-confirmed"
            }
            clearPendingDungeon(session)
            return ProtocolResult.Ok(StepResult(
                true,
                "副本完成并已开启${contract.chestNames[chestPosition]}侧宝箱",
                mapOf(
                    "phase" to "chest-opened",
                    "chapter" to (pending?.chapter ?: config.chapter).toString(),
                    "stage" to (pending?.stage ?: config.stage).toString(),
                    "completionEvidence" to completionEvidence,
                    "nextDelayMillis" to contract.schedule.postCompletionMillis.toString()
                )
            ))
        }

        fun openAfterIdleGenerals(
            expectedBattleId: Long?,
            completionEvidence: String,
            terminalStateStatus: Int? = null
        ): ProtocolResult<StepResult> {
            val pending = pendingDungeonFor(session)

            // Desktop parity: once 0x8938 says the battle is no longer active and every
            // selected general is idle, 0x193d is diagnostic only. A persisted launch older
            // than the safety window must try its configured chest before catalog confirmation;
            // otherwise status 0/3 can hold an accepted run forever after a restart.
            fun recoverTerminalPending(rewardEvidence: String): ProtocolResult<StepResult>? {
                if (pending == null || terminalStateStatus !in setOf(0, 3)) return null
                if (pending.chestOpened) {
                    return openConfiguredChest(
                        "$completionEvidence+$rewardEvidence+persisted-chest-receipt"
                    )
                }
                val pendingAge = (System.currentTimeMillis() - pending.launchedAtMillis)
                    .coerceAtLeast(0L)
                if (pendingAge < DUNGEON_STALE_RECOVERY_MILLIS) {
                    val remaining = DUNGEON_STALE_RECOVERY_MILLIS - pendingAge
                    return ProtocolResult.Ok(
                        StepResult(
                            true,
                            "副本战斗已结束且将领已回闲，等待安全窗口后自动开箱",
                            mapOf(
                                "phase" to "fighting",
                                "stateStatus" to terminalStateStatus.toString(),
                                "pendingAgeMillis" to pendingAge.toString(),
                                "nextDelayMillis" to remaining.coerceAtMost(
                                    contract.schedule.battlePollMillis
                                ).coerceAtLeast(1L).toString(),
                                "completionEvidence" to
                                    "$completionEvidence+$rewardEvidence+safety-window"
                            )
                        )
                    )
                }
                return openConfiguredChest(
                    "$completionEvidence+$rewardEvidence+desktop-nonactive-recovery"
                )
            }

            val reward = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(contract.rewardRequestOpcode, byteArrayOf()),
                    "dungeon/reward-state"
                )
            }.getOrElse {
                return recoverTerminalPending("0x893d-request-exception")
                    ?: ProtocolResult.Err(
                        "REAL_DUNGEON_REWARD_EXCEPTION",
                        "读取副本奖励状态异常：${it.message}",
                        true
                    )
            }
            if (!reward.ok || contract.rewardResponseOpcode !in reward.responseOpcodes) {
                return recoverTerminalPending("0x893d-missing")
                    ?: ProtocolResult.Err(
                        "REAL_DUNGEON_REWARD_UNCONFIRMED",
                        "将领已回闲但未收到副本奖励状态，继续等待",
                        true
                    )
            }
            val parsedReward = runCatching {
                DungeonProtocolShapes.parseRewardState(
                    requireNotNull(reward.payloadBytesFor(contract.rewardResponseOpcode)) {
                        "0x${contract.rewardResponseOpcode.toString(16)}负载缺失"
                    }
                )
            }.getOrElse {
                return recoverTerminalPending("0x893d-invalid")
                    ?: ProtocolResult.Err(
                        "REAL_DUNGEON_REWARD_INVALID",
                        "副本奖励状态解析失败：${it.message}",
                        false
                    )
            }
            recoverTerminalPending("0x893d-status-${parsedReward.status}")?.let { return it }
            if (parsedReward.status != 1) {
                if (pending?.chestOpened == true) {
                    return openConfiguredChest("$completionEvidence+persisted-chest-receipt")
                }
                return ProtocolResult.Err(
                    "REAL_DUNGEON_REWARD_NOT_READY",
                    "副本奖励尚未就绪（状态=${parsedReward.status}），继续等待",
                    true
                )
            }
            if (expectedBattleId != null &&
                parsedReward.battleId != null &&
                parsedReward.battleId != expectedBattleId
            ) {
                return ProtocolResult.Err(
                    "REAL_DUNGEON_REWARD_BATTLE_MISMATCH",
                    "副本奖励 battleId 与当前战斗不一致，禁止开箱",
                    false
                )
            }
            return openConfiguredChest(completionEvidence)
        }

        val battleState = when (val result = queryBattleState()) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (battleState.phase == DungeonBattlePhase.UNKNOWN) {
            return ProtocolResult.Err(
                "REAL_DUNGEON_STATE_UNKNOWN",
                "副本返回暂未识别的状态=${battleState.rawStatus}，等待刷新后重试",
                true
            )
        }
        val selectedDefinitelyIdle = selected.all { it.status == 0 }
        if ((recoveredPending != null && battleState.phase == DungeonBattlePhase.IDLE) ||
            battleState.phase == DungeonBattlePhase.PENDING_SETTLEMENT
        ) {
            val idleEvidence = if (missingBattleStateWithPending) {
                "missing-0x${contract.stateResponseOpcode.toString(16)}"
            } else {
                "0x${contract.stateResponseOpcode.toString(16)}-status-${battleState.rawStatus}"
            }
            if (!selectedDefinitelyIdle) {
                return ProtocolResult.Ok(
                    StepResult(
                        true,
                        "副本已有待结算记录，出征将领仍在忙，继续等待",
                        mapOf(
                            "phase" to "fighting",
                            "stateEvidence" to "$idleEvidence+pending-run+generals-busy",
                            "nextDelayMillis" to contract.schedule.battlePollMillis.toString()
                        )
                    )
                )
            }
            return openAfterIdleGenerals(
                recoveredPending?.battleId,
                "$idleEvidence+${if (recoveredPending != null) "pending-run+" else ""}" +
                    "generals-idle+0x${contract.rewardResponseOpcode.toString(16)}",
                terminalStateStatus = battleState.rawStatus.takeUnless {
                    missingBattleStateWithPending
                }
            )
        }
        if (battleState.phase == DungeonBattlePhase.SETTLEMENT) {
            return openConfiguredChest("0x8938-status-4")
        }
        if (battleState.phase == DungeonBattlePhase.FIGHTING) {
            val battleId = battleState.battleId
                ?: return ProtocolResult.Err("REAL_DUNGEON_BATTLE_ID_MISSING", "副本战斗状态缺少 battleId", false)
            recoveredPending?.takeIf { it.battleId == null }?.let {
                persistPendingDungeon(session, it.copy(battleId = battleId))
            }
            if (selectedDefinitelyIdle) {
                return openAfterIdleGenerals(battleId, "generals-idle+0x893d")
            }
            val firstPoll = dungeonPollBattleIds.put(session.accountId, battleId) != battleId
            val poll = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(
                        contract.battlePollRequestOpcode,
                        DungeonProtocolShapes.buildBattlePollPayload(firstPoll, battleId)
                    ),
                    "dungeon/battle-poll"
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_DUNGEON_POLL_EXCEPTION", "副本战况轮询异常：${it.message}", true)
            }
            if (!poll.ok || contract.battlePollResponseOpcode !in poll.responseOpcodes) {
                return ProtocolResult.Err(
                    "REAL_DUNGEON_POLL_UNCONFIRMED",
                    "副本战况轮询未收到0x${contract.battlePollResponseOpcode.toString(16)}",
                    true
                )
            }
            if (activeDungeonMode == "clear" && contract.clearModePausesOnDefeat) {
                val battleText = poll.textPreview.ifBlank {
                    poll.payloadBytesFor(contract.battlePollResponseOpcode)
                        ?.toString(Charsets.UTF_8)
                        .orEmpty()
                }
                val defeat = contract.defeatMarkers.firstOrNull(battleText::contains)
                if (defeat != null) {
                    clearPendingDungeon(session)
                    return ProtocolResult.Ok(
                        StepResult(
                            false,
                            "打通副本检测到明确战败（$defeat），已暂停；重新保存副本设置后才会继续",
                            mapOf(
                                "phase" to "defeat-paused",
                                "battleId" to battleId.toString(),
                                "defeatMarker" to defeat
                            )
                        )
                    )
                }
            }
            return ProtocolResult.Ok(StepResult(
                true,
                "副本战斗中，已完成一次战况轮询",
                mapOf(
                    "phase" to "fighting",
                    "battleId" to battleId.toString(),
                    "pollPhase" to if (firstPoll) "2" else "1",
                    "nextDelayMillis" to contract.schedule.battlePollMillis.toString()
                )
            ))
        }

        val preflight = when (val result = expeditionPreflight.check(
            session,
            ExpeditionPreflightRequest(
                label = "副本",
                generalIds = config.formationIds,
                // Desktop dungeon preflight deliberately ignores loyalty. The live
                // desktop account can dispatch with 0/100 loyalty, so treating zero as
                // a mobile-only blocker leaves the same valid formation retrying forever.
                requirePositiveLoyalty = false,
                formationRules = config.formationRules
            )
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }

        val catalogResponse = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(contract.catalogRequestOpcode, byteArrayOf()),
                "dungeon/catalog"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_DUNGEON_CATALOG_EXCEPTION", "读取副本目录异常：${it.message}", true)
        }
        if (!catalogResponse.ok || contract.catalogResponseOpcode !in catalogResponse.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_DUNGEON_CATALOG_UNCONFIRMED",
                "读取副本目录未收到0x${contract.catalogResponseOpcode.toString(16)}",
                true
            )
        }
        val catalog = runCatching {
                DungeonProtocolShapes.parseCatalog(
                    requireNotNull(catalogResponse.payloadBytesFor(contract.catalogResponseOpcode)) {
                        "0x${contract.catalogResponseOpcode.toString(16)}负载缺失"
                    }
                )
        }.getOrElse {
            return ProtocolResult.Err("REAL_DUNGEON_CATALOG_INVALID", "副本目录解析失败：${it.message}", false)
        }
        val clearStage = if (config.mode == "clear") {
            DungeonProtocolShapes.firstUncompletedStage(catalog, contract)
        } else {
            null
        }
        if (config.mode == "clear" && clearStage == null) {
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    "所有可单人挑战的副本关卡均已通关（各章最后一关为多人副本）",
                    mapOf(
                        "phase" to "all-clear",
                        "nextDelayMillis" to contract.schedule.dailyDonePollMillis.toString()
                    )
                )
            )
        }
        if (clearStage != null && (!clearStage.available || clearStage.stageCode == null)) {
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    "当前首个未通关关卡为第${clearStage.chapter + 1}章第${clearStage.displayStage}关，尚未解锁",
                    mapOf(
                        "phase" to "waiting-unlock",
                        "chapter" to clearStage.chapter.toString(),
                        "stage" to clearStage.displayStage.toString(),
                        "nextDelayMillis" to contract.schedule.waitingUnlockMillis.toString()
                    )
                )
            )
        }
        val effectiveChapter = clearStage?.chapter ?: config.chapter
        val effectiveStage = clearStage?.displayStage ?: config.stage
        val stageCode = clearStage?.stageCode ?: runCatching {
            DungeonProtocolShapes.resolveStageCode(
                catalog,
                effectiveChapter,
                effectiveStage,
                contract
            )
        }.getOrElse {
            return ProtocolResult.Err(
                "REAL_DUNGEON_STAGE_INVALID",
                "副本章节/关卡无效：${it.message}",
                false
            )
        }

        val generalIds = preflight.generalIds
        val prepare = sendDungeonCommand(
            gameHttp, dm, contract.prepareOpcode,
            DungeonProtocolShapes.buildPreparePayload(generalIds, stageCode, contract),
            expectedOpcode = contract.prepareResponseOpcode,
            phase = "dungeon/prepare"
        )
        if (prepare is ProtocolResult.Err || (prepare as ProtocolResult.Ok).value.success.not()) return prepare
        // 0x1520 is only preparation. Ownership can be revoked while it is in flight, so check
        // again before creating the durable send guard and, most importantly, before 0x1522.
        if (!executionAllowed()) {
            actionAudit?.invoke("后台执行权已撤销，副本准备完成后已阻止正式出征 0x${contract.dispatchOpcode.toString(16)}")
            return ProtocolResult.Err(
                "EXECUTION_REVOKED",
                "后台已停止，副本准备已完成但正式出征未发送",
                retryable = false
            )
        }
        return expeditionTransactions.execute(
            accountId = session.accountId,
            action = "副本",
            targetKey = "chapter=$effectiveChapter,stage=$effectiveStage,code=$stageCode," +
                "chest=${config.boxPosition},mode=${config.mode}",
            snapshot = preflight,
            exceptionCode = "REAL_DUNGEON_LAUNCH_EXCEPTION",
            exceptionLabel = "副本正式出征异常"
        ) {
            val response = sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(
                    contract.dispatchOpcode,
                    DungeonProtocolShapes.buildExpeditionPayload(generalIds, stageCode, contract)
                ),
                "dungeon/expedition"
            )
            actionAudit?.invoke(
                "真实副本请求：dungeon/expedition opcode=0x${contract.dispatchOpcode.toString(16)} http=${response.httpCode} " +
                    "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
            )
            if (!response.ok) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_DUNGEON_LAUNCH_HTTP_FAILED",
                        "副本正式出征 HTTP ${response.httpCode}，已冻结将领等待状态确认",
                        true
                    ),
                    "HTTP ${response.httpCode}; request acceptance is unknown"
                )
            }
            if (contract.dispatchResponseOpcode !in response.responseOpcodes) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_DUNGEON_LAUNCH_RECEIPT_MISSING",
                        "副本正式出征未收到0x${contract.dispatchResponseOpcode.toString(16)}，已冻结将领等待状态确认",
                        true
                    ),
                    "2xx response without 0x8522"
                )
            }
            val receipt = runCatching {
                DungeonProtocolShapes.parseLaunchResponse(
                    requireNotNull(response.payloadBytesFor(contract.dispatchResponseOpcode)) {
                        "0x${contract.dispatchResponseOpcode.toString(16)}负载缺失"
                    },
                    contract
                )
            }.getOrElse {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_DUNGEON_LAUNCH_RECEIPT_INVALID",
                        "副本0x8522回执解析失败，已冻结将领等待状态确认：${it.message}",
                        true
                    ),
                    "0x8522 receipt parse failed: ${it.message.orEmpty()}"
                )
            }
            if (!receipt.success) {
                return@execute ExpeditionSendResult.rejected(
                    ProtocolResult.Ok(StepResult(false, "副本正式出征被游戏服拒绝：${receipt.message}")),
                    "explicit 0x8522 rejection: ${receipt.message}"
                )
            }
            persistPendingDungeon(
                session,
                DungeonPendingRun(
                    generalIds = generalIds,
                    chapter = effectiveChapter,
                    stage = effectiveStage,
                    chestPosition = config.boxPosition,
                    mode = config.mode,
                    launchedAtMillis = System.currentTimeMillis()
                )
            )
            ExpeditionSendResult.accepted(
                ProtocolResult.Ok(StepResult(
                    true,
                    "${if (config.mode == "clear") "打通副本" else "副本"}第${effectiveChapter + 1}章第${effectiveStage}关已发起",
                    mapOf(
                        "phase" to "fighting",
                        "mode" to config.mode,
                        "chapter" to effectiveChapter.toString(),
                        "stage" to effectiveStage.toString(),
                        "stageCode" to stageCode.toString(),
                        "stateEvidence" to if (missingBattleStateAssumedIdle) {
                            "missing-0x${contract.stateResponseOpcode.toString(16)}-assumed-idle"
                        } else {
                            "0x${contract.stateResponseOpcode.toString(16)}-idle"
                        },
                        "nextDelayMillis" to contract.schedule.postLaunchPollMillis.toString()
                    )
                )),
                "explicit 0x8522 success"
            )
        }
    }

    private fun pendingDungeonFor(session: GameSession): DungeonPendingRun? =
        pendingDungeons[session.accountId]
            ?: DungeonPendingRun.fromJson(session.channelExtra[DUNGEON_PENDING_RUN_KEY])
                ?.also { pendingDungeons[session.accountId] = it }

    private fun recoverPendingDungeonFromTransaction(
        session: GameSession,
        config: DungeonConfig
    ): DungeonPendingRun? {
        val record = expeditionTransactions.latestUnresolved(session.accountId, "副本")
            ?: return null
        val fields = record.targetKey
            .split(',')
            .mapNotNull { token ->
                val key = token.substringBefore('=', "").trim()
                val value = token.substringAfter('=', "").trim()
                (key to value).takeIf { key.isNotBlank() && value.isNotBlank() }
            }
            .toMap()
        val chapter = fields["chapter"]?.toIntOrNull()?.takeIf { it >= 0 } ?: return null
        val stage = fields["stage"]?.toIntOrNull()?.takeIf { it > 0 } ?: return null
        val chestPosition = fields["chest"]?.toIntOrNull()?.takeIf { it in 0..2 }
            ?: config.boxPosition
        val mode = fields["mode"]?.takeIf { it in behaviorContract.dungeon.allowedModes }
            ?: config.mode
        return DungeonPendingRun(
            generalIds = record.generalIds,
            chapter = chapter,
            stage = stage,
            chestPosition = chestPosition,
            mode = mode,
            launchedAtMillis = record.createdAtMillis,
            recoveredFromTransaction = true
        ).also { persistPendingDungeon(session, it) }
    }

    private fun persistPendingDungeon(session: GameSession, pending: DungeonPendingRun) {
        pendingDungeons[session.accountId] = pending
        sessionExtraSink?.invoke(
            session.accountId,
            mapOf(DUNGEON_PENDING_RUN_KEY to pending.toJson().toString())
        )
    }

    private fun clearPendingDungeon(session: GameSession) {
        pendingDungeons.remove(session.accountId)
        dungeonPollBattleIds.remove(session.accountId)
        expeditionTransactions.resolve(session.accountId, "副本")
        sessionExtraSink?.invoke(
            session.accountId,
            mapOf(DUNGEON_PENDING_RUN_KEY to "{}")
        )
    }

    private fun sendDungeonCommand(
        gameHttp: String,
        dm: Long,
        opcode: Int,
        payload: ByteArray,
        expectedOpcode: Int,
        phase: String,
        requireZeroStatus: Boolean = false
    ): ProtocolResult<StepResult> {
        val response = runCatching {
            sendBinaryMappedGameHex(gameHttp, dm, buildDirectGameHex(opcode, payload), phase)
        }.getOrElse {
            return ProtocolResult.Err("REAL_DUNGEON_SEND_EXCEPTION", "$phase 请求异常：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实副本请求：$phase opcode=0x${opcode.toString(16)} http=${response.httpCode} " +
                "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!response.ok) {
            return ProtocolResult.Err("REAL_DUNGEON_HTTP_FAILED", "$phase HTTP ${response.httpCode}", false)
        }
        if (expectedOpcode !in response.responseOpcodes) {
            return ProtocolResult.Ok(StepResult(false, "$phase 未收到 0x${expectedOpcode.toString(16)} 确认"))
        }
        if (expectedOpcode == behaviorContract.dungeon.chestResponseOpcode) {
            val receipt = runCatching {
                DungeonProtocolShapes.parseChestResponse(
                    requireNotNull(response.payloadBytesFor(expectedOpcode)) {
                        "0x${expectedOpcode.toString(16)}负载缺失"
                    }
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_DUNGEON_CHEST_RECEIPT_INVALID",
                    "$phase 0x893e解析失败：${it.message}",
                    false
                )
            }
            if (!receipt.success) {
                return ProtocolResult.Ok(StepResult(false, "$phase 被游戏服拒绝：${receipt.message}"))
            }
        } else if (requireZeroStatus &&
            response.payloadHexFor(expectedOpcode)?.take(2)?.toIntOrNull(16) != 0
        ) {
            return ProtocolResult.Ok(StepResult(false, "$phase 被游戏服拒绝"))
        }
        return ProtocolResult.Ok(StepResult(true, "$phase 成功"))
    }

    override suspend fun runLossless(
        session: GameSession,
        config: LosslessConfig
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.runLossless(session, config)
        if (!config.enabled) return ProtocolResult.Ok(StepResult(false, "无损任务未启用"))
        val contract = behaviorContract.lossless
        val rules = config.rules.filter { it.enabled }
        if (rules.isEmpty()) {
            return ProtocolResult.Err("REAL_LOSSLESS_RULE_MISSING", "无损没有启用的编队", false)
        }
        if (rules.any {
                it.generalIds.isEmpty() ||
                    it.generalIds.size > contract.maximumGeneralsPerFormation ||
                    it.level !in contract.minimumLevel..contract.maximumLevel
            }
        ) {
            return ProtocolResult.Err("REAL_LOSSLESS_RULE_INVALID", "无损编队、将领数量或等级配置无效", false)
        }
        if (session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() != true ||
            session.channelExtra["realActionSendReady"].asLooseBoolean() != true
        ) {
            return ProtocolResult.Err("REAL_LOSSLESS_GATE_NOT_READY", "真实无损动作 gate 未开启", false)
        }
        if (!session.hasRealActionScope("lossless")) {
            return ProtocolResult.Err("REAL_LOSSLESS_SCOPE_NOT_CONFIRMED", "真实无损需要 lossless 作用域", false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_LOSSLESS_GAME_HTTP_MISSING", "真实无损缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_LOSSLESS_DM_MISSING", "真实无损缺少 dm", false)

        val statusResponse = sendLosslessCommand(
            gameHttp,
            dm,
            contract.statusRequestOpcode,
            contract.queryPayload,
            "lossless/status"
        )
            ?: return ProtocolResult.Err("REAL_LOSSLESS_STATUS_EXCEPTION", "读取无损状态异常", true)
        if (!statusResponse.ok || contract.statusResponseOpcode !in statusResponse.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_LOSSLESS_STATUS_UNCONFIRMED",
                "读取无损状态未收到0x${contract.statusResponseOpcode.toString(16)}",
                true
            )
        }
        val status = runCatching {
            LosslessProtocolShapes.parseStatus(
                statusResponse.requirePayloadBytesFor(contract.statusResponseOpcode),
                contract
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_LOSSLESS_STATUS_PARSE_FAILED", "无损状态解析失败：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实无损状态：phase=${status.phase} mode=${status.mode} " +
                "remaining=${status.remainingAttempts} stage=${status.stageId}"
        )

        if (status.phase == LosslessPhase.SETTLEMENT) {
            val response = sendLosslessCommand(
                gameHttp,
                dm,
                contract.settlementRequestOpcode,
                contract.queryPayload,
                "lossless/settlement"
            ) ?: return ProtocolResult.Err("REAL_LOSSLESS_SETTLEMENT_EXCEPTION", "无损结算请求异常", true)
            if (!response.ok || contract.settlementResponseOpcode !in response.responseOpcodes) {
                return ProtocolResult.Err(
                    "REAL_LOSSLESS_SETTLEMENT_UNCONFIRMED",
                    "无损结算未收到0x${contract.settlementResponseOpcode.toString(16)}",
                    true
                )
            }
            val settlement = runCatching {
                LosslessProtocolShapes.parseSettlement(
                    response.requirePayloadBytesFor(contract.settlementResponseOpcode)
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_LOSSLESS_SETTLEMENT_PARSE_FAILED", "无损结算解析失败：${it.message}", false)
            }
            if (!settlement.success) {
                return ProtocolResult.Ok(StepResult(
                    false,
                    settlement.message,
                    mapOf("phase" to "settlement-rejected", "attemptConsumed" to "false")
                ))
            }
            return ProtocolResult.Ok(StepResult(
                true,
                settlement.message,
                mapOf(
                    "phase" to "settled",
                    "attemptConsumed" to "false",
                    "battleId" to settlement.battleId.toString(),
                    "battleFailed" to settlement.battleFailed.toString(),
                    "nextDelayMillis" to contract.schedule.settlementRecheckMillis.toString()
                )
            ))
        }
        when (status.phase) {
            LosslessPhase.DAILY_DONE -> return ProtocolResult.Ok(StepResult(
                true, "今日无损次数已用完",
                mapOf(
                    "phase" to "daily-done",
                    "attemptConsumed" to "false",
                    "remainingAttempts" to "0",
                    "nextDelayMillis" to contract.schedule.cooldownPollMaxMillis.toString()
                )
            ))
            LosslessPhase.COOLDOWN -> return ProtocolResult.Ok(StepResult(
                true, "无损冷却中",
                mapOf(
                    "phase" to "cooldown",
                    "attemptConsumed" to "false",
                    "cooldownMillis" to (status.cooldownMillis ?: 0).toString(),
                    "nextDelayMillis" to (status.cooldownMillis ?: contract.schedule.cooldownPollMinMillis)
                        .coerceIn(
                            contract.schedule.cooldownPollMinMillis,
                            contract.schedule.cooldownPollMaxMillis
                        ).toString()
                )
            ))
            LosslessPhase.FIGHTING -> return ProtocolResult.Ok(StepResult(
                true, "无损战斗进行中",
                mapOf(
                    "phase" to "fighting",
                    "attemptConsumed" to "false",
                    "nextDelayMillis" to contract.schedule.fightingPollMillis.toString()
                )
            ))
            LosslessPhase.UNKNOWN -> return ProtocolResult.Err(
                "REAL_LOSSLESS_STATUS_UNKNOWN",
                "无损返回未知状态：mode=${status.mode} progress=${status.progressCode}",
                false
            )
            else -> Unit
        }

        val serverUsedAttempts = (contract.serverDailyLimit - status.remainingAttempts)
            .coerceIn(0, contract.serverDailyLimit)
        if (serverUsedAttempts >= config.dailyLimit.coerceAtMost(contract.serverDailyLimit)) {
            return ProtocolResult.Ok(StepResult(
                true,
                "已达到配置的无损每日上限：$serverUsedAttempts/${config.dailyLimit}",
                mapOf(
                    "phase" to "configured-daily-limit",
                    "attemptConsumed" to "false",
                    "serverUsedAttempts" to serverUsedAttempts.toString(),
                    "remainingAttempts" to status.remainingAttempts.toString()
                )
            ))
        }

        val cursor = losslessRuleCursors[session.accountId] ?: 0
        val ruleIndex = cursor.mod(rules.size)
        val rule = rules[ruleIndex]
        if (status.selectedLevel != rule.level) {
            val selected = selectLosslessLevel(gameHttp, dm, rule.level, contract)
            if (selected is ProtocolResult.Err) return selected
            val value = (selected as ProtocolResult.Ok).value
            if (!value.success || value.selectedLevel != rule.level) {
                return ProtocolResult.Ok(StepResult(
                    false,
                    "选择${rule.level}级无损失败：${value.message}",
                    mapOf("phase" to "select-rejected", "attemptConsumed" to "false")
                ))
            }
        }

        val lineupResponse = sendLosslessCommand(
            gameHttp, dm, contract.lineupRequestOpcode, contract.queryPayload, "lossless/lineup"
        ) ?: return ProtocolResult.Err("REAL_LOSSLESS_LINEUP_EXCEPTION", "读取无损阵容异常", true)
        if (!lineupResponse.ok || contract.lineupResponseOpcode !in lineupResponse.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_LOSSLESS_LINEUP_UNCONFIRMED",
                "读取无损阵容未收到0x${contract.lineupResponseOpcode.toString(16)}",
                true
            )
        }
        val lineup = runCatching {
            LosslessProtocolShapes.parseLineup(
                lineupResponse.requirePayloadBytesFor(contract.lineupResponseOpcode)
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_LOSSLESS_LINEUP_PARSE_FAILED", "无损阵容解析失败：${it.message}", false)
        }
        if (!lineup.success) {
            return ProtocolResult.Ok(StepResult(
                false, "游戏服拒绝返回无损阵容，状态=${lineup.status}",
                mapOf("phase" to "lineup-rejected", "attemptConsumed" to "false")
            ))
        }
        val rerollKey = "${session.accountId}:$ruleIndex"
        if (rule.level == contract.level10Guard.level) {
            val verdict = LosslessProtocolShapes.evaluateLevel10Guard(lineup, contract)
            if (!verdict.qualified) {
                val rerolls = losslessRerollCounts[rerollKey] ?: 0
                val maxRerolls = rule.maxLineupRerolls.coerceIn(
                    1,
                    contract.level10Guard.maximumMaxRerolls
                )
                if (rerolls >= maxRerolls) {
                    return ProtocolResult.Err(
                        "REAL_LOSSLESS_REROLL_LIMIT_REACHED",
                        "连续筛选${rerolls + 1}次仍未找到符合条件的10级卫兵阵容",
                        false
                    )
                }
                // A single alternate-level round trip rerolls the lineup. The next scheduler
                // tick re-reads and re-evaluates it; never dispatch an unqualified lineup.
                val alternate = selectLosslessLevel(
                    gameHttp,
                    dm,
                    contract.level10Guard.alternateLevel,
                    contract
                )
                if (alternate is ProtocolResult.Err || !(alternate as ProtocolResult.Ok).value.success) {
                    return ProtocolResult.Err(
                        "REAL_LOSSLESS_REROLL_SWITCH_FAILED",
                        "刷新10级无损阵容时切换7级失败",
                        false
                    )
                }
                val restored = selectLosslessLevel(
                    gameHttp,
                    dm,
                    contract.level10Guard.level,
                    contract
                )
                if (restored is ProtocolResult.Err || !(restored as ProtocolResult.Ok).value.success) {
                    return ProtocolResult.Err(
                        "REAL_LOSSLESS_REROLL_RESTORE_FAILED",
                        "刷新10级无损阵容时切回10级失败",
                        false
                    )
                }
                losslessRerollCounts[rerollKey] = rerolls + 1
                return ProtocolResult.Ok(StepResult(
                    true,
                    "10级卫兵阵容不符合无损筛选条件，已安全刷新：${verdict.reason}",
                    mapOf(
                        "phase" to "lineup-rerolled",
                        "attemptConsumed" to "false",
                        "rerolls" to (rerolls + 1).toString(),
                        "nextDelayMillis" to contract.schedule.rerollNextCheckMillis.toString()
                    )
                ))
            }
        }
        losslessRerollCounts.remove(rerollKey)

        val monarch = when (val result = queryMonarch(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val roleId = monarch.roleId
            ?: return ProtocolResult.Err("REAL_LOSSLESS_ROLE_ID_MISSING", "无损出征缺少角色ID", false)
        val preflight = when (val result = expeditionPreflight.check(
            session,
            ExpeditionPreflightRequest(
                label = "无损",
                generalIds = rule.generalIds,
                refillToFull = config.fullTroops,
                formationRules = config.formationRules
            )
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }

        val prepare = sendLosslessCommand(
            gameHttp, dm, contract.prepareOpcode,
            LosslessProtocolShapes.buildPreparePayload(rule.generalIds, roleId, contract),
            "lossless/prepare"
        ) ?: return ProtocolResult.Err("REAL_LOSSLESS_PREPARE_EXCEPTION", "无损预出征异常", true)
        if (!prepare.ok || contract.prepareResponseOpcode !in prepare.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_LOSSLESS_PREPARE_UNCONFIRMED",
                "无损预出征未收到0x${contract.prepareResponseOpcode.toString(16)}",
                false
            )
        }
        return expeditionTransactions.execute(
            accountId = session.accountId,
            action = "无损",
            targetKey = "level=${rule.level},stage=${lineup.stageId}",
            snapshot = preflight,
            exceptionCode = "REAL_LOSSLESS_DISPATCH_EXCEPTION",
            exceptionLabel = "无损正式出征异常"
        ) {
            val expedition = sendLosslessCommand(
                gameHttp,
                dm,
                contract.dispatchOpcode,
                LosslessProtocolShapes.buildExpeditionPayload(preflight.generalIds, roleId, contract),
                "lossless/expedition"
            ) ?: return@execute ExpeditionSendResult.uncertain(
                ProtocolResult.Err(
                    "REAL_LOSSLESS_DISPATCH_EXCEPTION",
                    "无损正式出征异常，已冻结将领等待状态确认",
                    true
                ),
                "transport exception without a response"
            )
            if (!expedition.ok) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_LOSSLESS_DISPATCH_HTTP_FAILED",
                        "无损正式出征 HTTP ${expedition.httpCode}，已冻结将领等待状态确认",
                        true
                    ),
                    "HTTP ${expedition.httpCode}; request acceptance is unknown"
                )
            }
            if (contract.dispatchResponseOpcode !in expedition.responseOpcodes) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_LOSSLESS_DISPATCH_RECEIPT_MISSING",
                        "无损正式出征未收到0x${contract.dispatchResponseOpcode.toString(16)}，已冻结将领等待状态确认",
                        true
                    ),
                    "2xx response without 0x8522"
                )
            }
            val dispatch = BrushYellowDispatchResponseParser.parse(
                responseHex = expedition.payloadHexFor(contract.dispatchResponseOpcode)
            )
                ?: BrushYellowDispatchResponseParser.parse(responseText = expedition.textPreview)
            if (dispatch?.success == false) {
                return@execute ExpeditionSendResult.rejected(
                    ProtocolResult.Ok(StepResult(
                        false,
                        dispatch.message.orEmpty().ifBlank { "游戏服拒绝无损出征" },
                        mapOf(
                            "phase" to "dispatch-rejected",
                            "attemptConsumed" to "true",
                            "consumedTimes" to "1"
                        )
                    )),
                    "explicit 0x8522 rejection: ${dispatch.evidence}"
                )
            }
            if (dispatch?.success != true) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_LOSSLESS_DISPATCH_PARSE_FAILED",
                        "无损0x8522回执无法确认，已冻结将领等待状态确认",
                        true
                    ),
                    "0x8522 receipt could not be parsed"
                )
            }
            losslessRuleCursors[session.accountId] = (cursor + 1).mod(rules.size)
            ExpeditionSendResult.accepted(
                ProtocolResult.Ok(StepResult(
                    true,
                    "已派${preflight.generalNames.joinToString(",")}挑战${rule.level}级无损",
                    mapOf(
                        "phase" to "fighting",
                        "attemptConsumed" to "true",
                        "consumedTimes" to "1",
                        "stageId" to lineup.stageId.toString(),
                        "battleId" to dispatch.battleId.toString(),
                        "nextDelayMillis" to contract.schedule.postDispatchPollMillis.toString()
                    )
                )),
                "explicit 0x8522 success"
            )
        }
    }

    private fun selectLosslessLevel(
        gameHttp: String,
        dm: Long,
        level: Int,
        contract: LosslessBehaviorContract = behaviorContract.lossless
    ): ProtocolResult<LosslessSelectResult> {
        val response = sendLosslessCommand(
            gameHttp, dm, contract.selectRequestOpcode,
            LosslessProtocolShapes.buildSelectLevelPayload(level, contract),
            "lossless/select-$level"
        ) ?: return ProtocolResult.Err("REAL_LOSSLESS_SELECT_EXCEPTION", "选择${level}级无损异常", true)
        if (!response.ok || contract.selectResponseOpcode !in response.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_LOSSLESS_SELECT_UNCONFIRMED",
                "选择${level}级无损未收到0x${contract.selectResponseOpcode.toString(16)}",
                false
            )
        }
        return runCatching {
            ProtocolResult.Ok(
                LosslessProtocolShapes.parseSelect(
                    response.requirePayloadBytesFor(contract.selectResponseOpcode)
                )
            )
        }.getOrElse {
            ProtocolResult.Err("REAL_LOSSLESS_SELECT_PARSE_FAILED", "选择${level}级无损响应解析失败：${it.message}", false)
        }
    }

    private fun sendLosslessCommand(
        gameHttp: String,
        dm: Long,
        opcode: Int,
        payload: ByteArray,
        phase: String
    ): DirectBinaryResponse? = runCatching {
        sendBinaryMappedGameHex(gameHttp, dm, buildDirectGameHex(opcode, payload), phase)
    }.onSuccess { response ->
        actionAudit?.invoke(
            "真实无损请求：$phase opcode=0x${opcode.toString(16)} http=${response.httpCode} " +
                "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
    }.getOrNull()

    override suspend fun queryInventory(session: GameSession): ProtocolResult<List<InventoryItem>> {
        if (!session.isRealSession()) return fallback.queryInventory(session)
        val live = if (session.channelExtra["inventoryLiveRefreshAllowed"].asLooseBoolean() == true) {
            session.gameHttpOrNull()?.let { gameHttp ->
                session.dmOrNull()?.let { dm ->
                    runCatching {
                        requireExecutionAllowed("inventory/live-refresh")
                        RealGameProtocolClient().refreshInventoryState(gameHttp, dm)
                    }.getOrNull()
                }
            }
        } else null
        if (live != null) {
            return ProtocolResult.Ok(
                live.items.map { it.toInventoryItem() } +
                    live.equipment.map { it.toInventoryItem() }
            )
        }
        val raw = session.channelExtra["inventoryJson"]
            ?: return ProtocolResult.Err(
                "REAL_INVENTORY_METADATA_MISSING",
                "实时读取背包失败且登录缓存中没有 inventoryJson",
                retryable = true
            )
        return runCatching {
            val arr = JSONArray(raw)
            ProtocolResult.Ok((0 until arr.length()).mapNotNull { index ->
                arr.optJSONObject(index)?.toInventoryItem()
            })
        }.getOrElse {
            ProtocolResult.Err("REAL_INVENTORY_METADATA_INVALID", "inventoryJson 解析失败：${it.message}", false)
        }
    }

    private fun RealGameProtocolClient.InventoryStack.toInventoryItem(): InventoryItem =
        InventoryItem(
            id = itemId.toLong(),
            name = name,
            type = normalizedInventoryType(name, typeLabel),
            quality = null,
            level = null,
            enhanced = false,
            equipped = false,
            count = count
        )

    private fun RealGameProtocolClient.InventoryEquipment.toInventoryItem(): InventoryItem {
        val mappedQuality = EquipmentQuality.entries.getOrNull(quality)
        return InventoryItem(
            id = instanceId,
            name = name,
            type = "equipment",
            quality = mappedQuality,
            level = level,
            enhanced = strengthen > 0,
            equipped = false,
            count = 1,
            templateId = templateId,
            famous = famous,
            extraText = extraText,
            equipmentMetadataComplete = instanceId > 0L &&
                typeCode >= 0 && level > 0 && mappedQuality != null
        )
    }

    private fun JSONObject.toInventoryItem(): InventoryItem? {
        val id = optLong("itemId", optLong("id", -1L))
        val count = optInt("count", 0)
        if (id < 0L || count <= 0) return null
        val name = optString("name").ifBlank { ItemDictionary.nameFor(id.toInt()) ?: "道具#$id" }
        val type = normalizedInventoryType(name, optString("type"))
        val rawQuality = if (has("quality")) optInt("quality", -1) else -1
        val quality = EquipmentQuality.entries.getOrNull(rawQuality)
        return InventoryItem(
            id = id,
            name = name,
            type = type,
            quality = quality,
            level = optInt("level", 0).takeIf { it > 0 },
            enhanced = optBoolean("enhanced", optInt("strengthen", 0) > 0),
            equipped = optBoolean("equipped", false),
            count = count,
            templateId = optInt("templateId", -1).takeIf { it >= 0 },
            famous = optBoolean("famous", false),
            extraText = optString("extraText"),
            equipmentMetadataComplete = type != "equipment" ||
                optBoolean("equipmentMetadataComplete", false)
        )
    }

    private fun normalizedInventoryType(name: String, rawType: String?): String = when {
        name.contains("宝箱") || name.endsWith("箱") -> "box"
        name.contains("银票") -> "silver-ticket"
        rawType?.contains("装备") == true -> "equipment"
        else -> "item"
    }

    override suspend fun useOrDiscardItem(
        session: GameSession,
        itemId: Long,
        action: InventoryAction,
        count: Int
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.useOrDiscardItem(session, itemId, action, count)
        if (count <= 0) {
            return ProtocolResult.Err("REAL_INVENTORY_COUNT_INVALID", "背包动作数量必须大于 0", false)
        }
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err(
                "REAL_INVENTORY_GATE_NOT_READY",
                "真实背包动作 gate 未同时开启：realActionNetworkAllowed=$networkAllowed realActionSendReady=$sendReady",
                false
            )
        }
        if (!session.hasRealActionScope("inventory")) {
            return ProtocolResult.Err(
                "REAL_INVENTORY_SCOPE_NOT_CONFIRMED",
                "真实背包动作需要独立 realActionScope=inventory",
                false
            )
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_INVENTORY_GAME_HTTP_MISSING", "真实背包动作缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_INVENTORY_DM_MISSING", "真实背包动作缺少 dm", false)

        val (opcode, expected, payload) = when (action) {
            InventoryAction.OPEN, InventoryAction.USE -> {
                if (itemId !in 0..0xffff || count > 0xffff) {
                    return ProtocolResult.Err("REAL_INVENTORY_VALUE_OUT_OF_RANGE", "道具编号或使用数量超出协议范围", false)
                }
                Triple(0x3144, 0xA144, InventoryProtocolShapes.buildUsePayload(itemId, count))
            }
            InventoryAction.DISCARD -> Triple(
                0x1103,
                0x8103,
                InventoryProtocolShapes.buildDiscardPayload(kind = 0, objectId = itemId, count = count)
            )
            InventoryAction.DISCARD_EQUIPMENT -> {
                if (count != 1) {
                    return ProtocolResult.Err(
                        "REAL_INVENTORY_EQUIPMENT_COUNT_INVALID",
                        "装备必须按实例逐件丢弃",
                        false
                    )
                }
                Triple(
                    0x1103,
                    0x8103,
                    InventoryProtocolShapes.buildDiscardPayload(kind = 1, objectId = itemId, count = 1)
                )
            }
        }
        val response = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(opcode, payload),
                phase = "inventory/${opcode.toString(16)}"
            )
        }.getOrElse {
            return ProtocolResult.Err(
                "REAL_INVENTORY_SEND_EXCEPTION",
                "背包请求 0x${opcode.toString(16)} 异常：${it.message}",
                false
            )
        }
        actionAudit?.invoke(
            "真实背包请求：action=${action.name} item=$itemId count=$count " +
                "opcode=0x${opcode.toString(16)} http=${response.httpCode} " +
                "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!response.ok) {
            return ProtocolResult.Err("REAL_INVENTORY_HTTP_FAILED", "背包请求 HTTP ${response.httpCode}", false)
        }
        if (expected !in response.responseOpcodes) {
            return ProtocolResult.Ok(StepResult(
                false,
                "服务器未返回 0x${expected.toString(16)} 确认",
                mapOf("responseOpcodes" to response.responseOpcodes.joinToString { "0x${it.toString(16)}" })
            ))
        }
        val receipt = runCatching {
            InventoryProtocolShapes.parseActionResponse(response.requirePayloadBytesFor(expected))
        }.getOrElse {
            return ProtocolResult.Err(
                "REAL_INVENTORY_RECEIPT_INVALID",
                "0x${expected.toString(16)} 背包回执解析失败：${it.message}",
                false
            )
        }
        if (!receipt.success) {
            return ProtocolResult.Ok(
                StepResult(
                    false,
                    receipt.message.ifBlank { "背包动作被服务器拒绝，状态=${receipt.status}" },
                    mapOf(
                        "opcode" to "0x${opcode.toString(16)}",
                        "responseOpcode" to "0x${expected.toString(16)}",
                        "status" to receipt.status.toString()
                    )
                )
            )
        }
        return ProtocolResult.Ok(StepResult(
            true,
            receipt.message.ifBlank { when (action) {
                InventoryAction.OPEN, InventoryAction.USE -> "使用道具成功"
                InventoryAction.DISCARD -> "丢弃道具成功"
                InventoryAction.DISCARD_EQUIPMENT -> "丢弃装备成功"
            } },
            mapOf(
                "opcode" to "0x${opcode.toString(16)}",
                "itemId" to itemId.toString(),
                "count" to count.toString(),
                "status" to receipt.status.toString(),
                "trailingBytes" to receipt.trailingBytes.toString()
            )
        ))
    }

    override suspend fun setVipFeature(session: GameSession, config: VipFeatureConfig): ProtocolResult<StepResult> =
        if (session.isRealSession()) unrecovered("REAL_VIP_NOT_IMPLEMENTED", "真实 VIP 协议尚未接入") else fallback.setVipFeature(session, config)

    override suspend fun surrenderOrReleaseGenerals(session: GameSession, config: SurrenderReleaseConfig): ProtocolResult<StepResult> =
        if (session.isRealSession()) unrecovered("REAL_SURRENDER_RELEASE_NOT_IMPLEMENTED", "真实劝降/释放协议尚未接入") else fallback.surrenderOrReleaseGenerals(session, config)

    override suspend fun sendGeneralToResourcePoint(session: GameSession, config: ResourcePointSendGeneralConfig): ProtocolResult<StepResult> =
        if (session.isRealSession()) unrecovered("REAL_SEND_GENERAL_NOT_IMPLEMENTED", "真实资源点送将协议尚未接入") else fallback.sendGeneralToResourcePoint(session, config)

    override suspend fun runAutoLoot(session: GameSession, config: AutoLootConfig): ProtocolResult<StepResult> =
        if (!session.isRealSession()) {
            fallback.runAutoLoot(session, config)
        } else {
            runRealAutoLoot(session, config)
        }

    private suspend fun runRealAutoLoot(
        session: GameSession,
        config: AutoLootConfig
    ): ProtocolResult<StepResult> {
        if (!config.enabled) return ProtocolResult.Ok(StepResult(false, "掠夺任务未启用"))
        val rules = config.enabledRules()
        if (rules.isEmpty()) {
            return ProtocolResult.Err("REAL_LOOT_RULE_MISSING", "掠夺没有启用的有效规则", false)
        }
        val cursor = lootRuleCursors[session.accountId] ?: 0
        val (ruleIndex, rule) = config.selectEnabledRule(cursor)
            ?: return ProtocolResult.Err("REAL_LOOT_RULE_MISSING", "掠夺没有启用的有效规则", false)
        val generalIds = rule.generalIds.filter { it > 0 }.distinct()
        if (generalIds.isEmpty()) {
            return ProtocolResult.Err("REAL_LOOT_GENERALS_MISSING", "掠夺至少需要选择一个将领", false)
        }
        if (rule.playerName.isBlank() || rule.fiefIndex <= 0) {
            return ProtocolResult.Err("REAL_LOOT_TARGET_INVALID", "请填写目标玩家和正确的封地序号", false)
        }
        if (session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() != true ||
            session.channelExtra["realActionSendReady"].asLooseBoolean() != true
        ) {
            return ProtocolResult.Err("REAL_LOOT_GATE_NOT_READY", "真实掠夺动作 gate 未开启", false)
        }
        if (!session.hasRealActionScope("raid")) {
            return ProtocolResult.Err("REAL_LOOT_SCOPE_NOT_CONFIRMED", "真实掠夺需要 raid 作用域", false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_LOOT_GAME_HTTP_MISSING", "真实掠夺缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_LOOT_DM_MISSING", "真实掠夺缺少 dm", false)
        val raidContract = behaviorContract.raid
        if (generalIds.size > raidContract.maximumGeneralsPerFormation) {
            return ProtocolResult.Err(
                "REAL_LOOT_GENERALS_OVER_LIMIT",
                "掠夺一次最多选择${raidContract.maximumGeneralsPerFormation}名将领",
                false
            )
        }
        val preflight = when (val result = expeditionPreflight.check(
            session,
            ExpeditionPreflightRequest(
                label = "掠夺",
                generalIds = generalIds,
                requireFullLoyalty = config.fullLoyalty,
                refillToFull = config.fullTroops,
                formationRules = config.formationRules
            )
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val query = runCatching {
            sendBinaryMappedGameHex(
                gameHttp, dm,
                buildDirectGameHex(
                    raidContract.fiefQueryOpcode,
                    LootProtocolShapes.buildRaidFiefListPayload(rule.playerName, raidContract)
                ),
                "loot/query-fiefs"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_LOOT_QUERY_EXCEPTION", "查询目标封地异常：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实掠夺请求：查询${rule.playerName}封地 " +
                "opcode=0x${raidContract.fiefQueryOpcode.toString(16)} http=${query.httpCode}"
        )
        if (!query.ok || raidContract.fiefQueryResponseOpcode !in query.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_LOOT_QUERY_FAILED",
                "查询目标封地未收到0x${raidContract.fiefQueryResponseOpcode.toString(16)}",
                false
            )
        }
        val fiefs = runCatching {
            LootProtocolShapes.parseFiefList(
                query.requirePayloadBytesFor(raidContract.fiefQueryResponseOpcode)
            )
        }
            .getOrElse {
                return ProtocolResult.Err("REAL_LOOT_FIEF_PARSE_FAILED", "目标封地解析失败：${it.message}", false)
            }
        val target = fiefs.getOrNull(rule.fiefIndex - 1)
            ?: return ProtocolResult.Err(
                "REAL_LOOT_FIEF_INDEX_INVALID",
                "${rule.playerName}只返回${fiefs.size}个封地，无法选择第${rule.fiefIndex}个",
                false
            )
        val prepare = sendLootCommand(
            gameHttp, dm, raidContract.prepareOpcode,
            LootProtocolShapes.buildPreparePayload(generalIds, target.targetId, raidContract),
            raidContract.prepareResponseOpcode, "loot/prepare"
        )
        if (prepare is ProtocolResult.Err || !(prepare as ProtocolResult.Ok).value.success) return prepare
        return expeditionTransactions.execute(
            accountId = session.accountId,
            action = "掠夺",
            targetKey = "${rule.playerName}:${target.targetId}",
            snapshot = preflight,
            exceptionCode = "REAL_LOOT_DISPATCH_EXCEPTION",
            exceptionLabel = "掠夺正式出征异常"
        ) {
            val response = sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(
                    raidContract.dispatchOpcode,
                    LootProtocolShapes.buildExpeditionPayload(
                        preflight.generalIds,
                        target.targetId,
                        raidContract
                    )
                ),
                "loot/expedition"
            )
            actionAudit?.invoke(
                "真实掠夺请求：loot/expedition " +
                    "opcode=0x${raidContract.dispatchOpcode.toString(16)} http=${response.httpCode} " +
                    "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
            )
            if (!response.ok) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_LOOT_DISPATCH_HTTP_FAILED",
                        "掠夺正式出征 HTTP ${response.httpCode}，已冻结将领等待状态确认",
                        true
                    ),
                    "HTTP ${response.httpCode}; request acceptance is unknown"
                )
            }
            if (raidContract.dispatchResponseOpcode !in response.responseOpcodes) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_LOOT_DISPATCH_RECEIPT_MISSING",
                        "掠夺正式出征未收到0x${raidContract.dispatchResponseOpcode.toString(16)}" +
                            "，已冻结将领等待状态确认",
                        true
                    ),
                    "2xx response without 0x8522"
                )
            }
            val parsed = BrushYellowDispatchResponseParser.parse(
                responseHex = response.payloadHexFor(raidContract.dispatchResponseOpcode)
            ) ?: BrushYellowDispatchResponseParser.parse(responseText = response.textPreview)
            val battleId = parsed?.battleId?.takeIf { it > 0L }
            val success = parsed?.success == true &&
                (!raidContract.dispatchSuccessRequiresPositiveBattleId || battleId != null)
            if (parsed?.success == false) {
                return@execute ExpeditionSendResult.rejected(
                    ProtocolResult.Ok(StepResult(
                        false,
                        parsed.message ?: "掠夺正式出征被游戏服拒绝"
                    )),
                    "explicit 0x${raidContract.dispatchResponseOpcode.toString(16)} rejection: ${parsed.evidence}"
                )
            }
            if (!success) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_LOOT_DISPATCH_BATTLE_ID_MISSING",
                        "掠夺0x${raidContract.dispatchResponseOpcode.toString(16)}未返回正数 battleId" +
                            "，已冻结将领等待状态确认",
                        true
                    ),
                    "dispatch receipt did not confirm a positive battle id"
                )
            }
            lootRuleCursors[session.accountId] = (ruleIndex + 1).mod(rules.size)
            ExpeditionSendResult.accepted(
                ProtocolResult.Ok(StepResult(
                    true,
                    "已派${preflight.generalNames.joinToString(",")}立即掠夺${rule.playerName}的${target.name}",
                    mapOf(
                        "phase" to "launched",
                        "targetId" to target.targetId.toString(),
                        "targetName" to target.name,
                        "fiefIndex" to target.index.toString(),
                        "ruleIndex" to ruleIndex.toString(),
                        "battleId" to battleId.toString(),
                        "parsedEvidence" to (parsed?.evidence ?: "positive-battle-id")
                    )
                )),
                "explicit 0x${raidContract.dispatchResponseOpcode.toString(16)} success battleId=$battleId"
            )
        }
    }

    private fun sendLootCommand(
        gameHttp: String,
        dm: Long,
        opcode: Int,
        payload: ByteArray,
        expectedOpcode: Int,
        phase: String
    ): ProtocolResult<StepResult> {
        val response = runCatching {
            sendBinaryMappedGameHex(gameHttp, dm, buildDirectGameHex(opcode, payload), phase)
        }.getOrElse {
            return ProtocolResult.Err("REAL_LOOT_SEND_EXCEPTION", "$phase 请求异常：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实掠夺请求：$phase opcode=0x${opcode.toString(16)} http=${response.httpCode} " +
                "responses=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }}"
        )
        if (!response.ok || expectedOpcode !in response.responseOpcodes) {
            return ProtocolResult.Ok(StepResult(false, "$phase 未收到0x${expectedOpcode.toString(16)}确认"))
        }
        return ProtocolResult.Ok(StepResult(true, "$phase 成功"))
    }

    override suspend fun scanAlarms(
        session: GameSession,
        config: AlarmConfig
    ): ProtocolResult<StepResult> {
        if (!session.isRealSession()) return fallback.scanAlarms(session, config)
        var scanExtra = session.channelExtra
        var refreshSummary = "使用已持久化军情快照"
        if (session.channelExtra["militaryIntelLiveGate"].asLooseBoolean() == true) {
            val now = System.currentTimeMillis()
            val previous = lastHeartbeat3110AttemptAt[session.accountId] ?: 0L
            if (now - previous >= HEARTBEAT_3110_MIN_INTERVAL_MS) {
                lastHeartbeat3110AttemptAt[session.accountId] = now
                val gameHttp = session.gameHttpOrNull()
                val dm = session.dmOrNull()
                if (gameHttp == null || dm == null) {
                    refreshSummary = "0x3110 未发送：缺少 gameHttp/dm"
                } else {
                    val refresh = runCatching {
                        requireExecutionAllowed("military-intel/heartbeat-3110")
                        heartbeat3110Executor.execute(gameHttp, dm)
                    }
                    refresh.onSuccess { result ->
                        val snapshot = Heartbeat3110ResponseParser.parse(result.responsePayloadHex)
                        if (snapshot.sessionInvalid) {
                            return ProtocolResult.Err(
                                "REAL_HEARTBEAT_SESSION_INVALID",
                                "0x3110/0xa110 返回会话失效 fffc0000",
                                retryable = false
                            )
                        }
                        val militaryIntelJson = Heartbeat3110ResponseParser.mergeMilitaryIntel(
                            existingJson = session.channelExtra["militaryIntelJson"]
                                ?: session.channelExtra["militaryIntel"],
                            snapshot = snapshot,
                            updatedAtMillis = now
                        )
                        val updates = buildMap {
                            put("militaryIntelJson", militaryIntelJson)
                            put("militaryIntel", militaryIntelJson)
                            put("militaryIntelSourceOpcode", "0x3110/0xa110")
                            put("lastMilitaryIntelRefreshAt", now.toString())
                            put("lastMilitaryIntelResponseOpcodes", result.responseOpcodes.joinToString(","))
                            snapshot.copper?.let { put("copper", it.toString()) }
                            snapshot.food?.let { put("food", it.toString()) }
                        }
                        scanExtra = session.channelExtra + updates
                        sessionExtraSink?.invoke(session.accountId, updates)
                        refreshSummary = "0x3110/0xa110 刷新成功：广播${snapshot.broadcasts.size}条"
                        actionAudit?.invoke(
                            "真实军情刷新：account=${session.accountId} request=0x3110/0100 " +
                                "responses=${result.responseOpcodes.joinToString()} broadcasts=${snapshot.broadcasts.size} " +
                                "copper=${snapshot.copper} food=${snapshot.food}"
                        )
                    }.onFailure { error ->
                        refreshSummary = "0x3110 刷新失败，保留旧快照：${error.message}"
                        actionAudit?.invoke(
                            "真实军情刷新失败：account=${session.accountId} ${error.message}"
                        )
                    }
                }
            } else {
                refreshSummary = "0x3110 刷新限频，使用最近快照"
            }
        }
        val detected = MilitaryAlarmEventDetector.detect(scanExtra, config)
        val currentFingerprints = detected.mapTo(linkedSetOf()) { it.fingerprint }
        val seen = seenAlarmFingerprints.putIfAbsent(
            session.accountId,
            currentFingerprints.toMutableSet()
        )
        if (seen == null) {
            return ProtocolResult.Ok(
                StepResult(
                    success = true,
                    message = "$refreshSummary；真实军情警报基线已建立：${currentFingerprints.size}条；未重放历史通知"
                )
            )
        }
        val newEvents = synchronized(seen) {
            val previous = seen.toSet()
            val fresh = detected
                .distinctBy { it.fingerprint }
                .filter { it.fingerprint !in previous }
            // The persisted feed is bounded; keep the dedupe set bounded to the same
            // live window instead of leaking fingerprints for the whole service life.
            seen.clear()
            seen.addAll(currentFingerprints)
            fresh
        }
        newEvents.forEach { event ->
            alarmEventSink?.invoke(
                AlarmNotificationEvent(
                    accountId = session.accountId,
                    kind = event.kind,
                    text = event.text,
                    vibrate = event.vibrate,
                    showNotification = event.shouldNotify
                )
            )
        }
        actionAudit?.invoke(
            "真实军情警报扫描：account=${session.accountId} detected=${detected.size} " +
                "new=${newEvents.size} notified=${newEvents.count { it.shouldNotify }}"
        )
        return ProtocolResult.Ok(
            StepResult(
                success = true,
                message = "$refreshSummary；真实军情警报扫描完成：新增${newEvents.size}条，通知${newEvents.count { it.shouldNotify }}条",
                raw = mapOf(
                    "newEvents" to newEvents.size.toString(),
                    "notifiedEvents" to newEvents.count { it.shouldNotify }.toString(),
                    "trackedFingerprints" to currentFingerprints.size.toString()
                )
            )
        )
    }

    override suspend fun queryMilitarySnapshot(session: GameSession): ProtocolResult<MilitarySnapshot> {
        if (!session.isRealSession()) return fallback.queryMilitarySnapshot(session)
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_MILITARY_SNAPSHOT_GAME_HTTP_MISSING", "军情快照缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_MILITARY_SNAPSHOT_DM_MISSING", "军情快照缺少 dm", false)
        val contract = behaviorContract.militarySnapshot
        val response = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(contract.requestOpcode, contract.requestPayload),
                "military/snapshot"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_MILITARY_SNAPSHOT_EXCEPTION", "刷新军情快照异常：${it.message}", true)
        }
        if (!response.ok) {
            return ProtocolResult.Err("REAL_MILITARY_SNAPSHOT_HTTP_FAILED", "刷新军情快照 HTTP ${response.httpCode}", true)
        }
        if (contract.responseOpcode !in response.responseOpcodes) {
            return ProtocolResult.Err(
                "REAL_MILITARY_SNAPSHOT_RESPONSE_MISSING",
                "刷新军情快照未收到 0x${contract.responseOpcode.toString(16)} 回执",
                true
            )
        }
        val militaryPayloads = response.responsePayloads
            .asSequence()
            .filter { it.opcode == contract.responseOpcode }
            .map { it.payloadHex.hexToBytesLocal() }
            .toList()
            .ifEmpty { listOf(response.requirePayloadBytesFor(contract.responseOpcode)) }
        val generalNamesById = runCatching {
            queryGeneralListForFormationStatus(session)
                .filter { it.id > 0L && it.name.isNotBlank() }
                .associate { it.id to it.name }
        }.getOrDefault(emptyMap())
        val snapshot = MilitarySnapshotProtocolShapes.parseAll(
            payloads = militaryPayloads,
            responded = true,
            generalNamesById = generalNamesById
        )
        val json = snapshot.toJson()
        val refreshedAtMillis = System.currentTimeMillis()
        val updates = buildMap {
            put("militarySnapshotJson", json.toString())
            put("militarySnapshot", json.toString())
            put("militarySnapshotUpdatedAt", refreshedAtMillis.toString())
            if (snapshot.generalStatusRecords.isNotEmpty()) {
                put(
                    "militaryGeneralStatusJson",
                    JSONArray().apply {
                        snapshot.generalStatusRecords.forEach { put(JSONObject(it)) }
                    }.toString()
                )
                put(
                    "generalsJson",
                    mergeMilitaryGeneralEvidence(session, snapshot.generalStatusRecords, refreshedAtMillis)
                )
                put("generalsParserVersion", State8004GeneralEvidenceParser.PARSER_VERSION)
                put("lastMilitaryGeneralRefreshAt", refreshedAtMillis.toString())
            }
            if (snapshot.captiveGeneralRecords.isNotEmpty()) {
                put(
                    "captiveGeneralsJson",
                    JSONArray().apply {
                        snapshot.captiveGeneralRecords.forEach { put(JSONObject(it)) }
                    }.toString()
                )
            }
        }
        liveSessionExtraCache.compute(session.accountId) { _, current ->
            current.orEmpty() + updates
        }
        sessionExtraSink?.invoke(
            session.accountId,
            updates
        )
        actionAudit?.invoke(
            "真实军情快照刷新：account=${session.accountId} actions=${snapshot.actions.size} " +
                "generals=${snapshot.generalStatusRecords.size} " +
                "captives=${snapshot.captiveGeneralRecords.size} " +
                "unparsedTailBytes=${snapshot.unparsedTailByteCount} " +
                "response=0x${contract.responseOpcode.toString(16)}"
        )
        return ProtocolResult.Ok(snapshot)
    }

    private fun mergeMilitaryGeneralEvidence(
        session: GameSession,
        evidence: List<Map<String, String>>,
        refreshedAtMillis: Long
    ): String {
        val currentRaw = liveSessionExtraCache[session.accountId]?.get("generalsJson")
            ?: session.channelExtra["generalsJson"]
        val byId = linkedMapOf<Long, JSONObject>()
        runCatching { JSONArray(currentRaw ?: "[]") }.getOrDefault(JSONArray()).let { current ->
            for (index in 0 until current.length()) {
                val record = current.optJSONObject(index) ?: continue
                val id = record.optLong("id").takeIf { it > 0L } ?: continue
                byId[id] = JSONObject(record.toString())
            }
        }
        evidence.forEach { fields ->
            val id = fields["id"]?.toLongOrNull()?.takeIf { it > 0L } ?: return@forEach
            val merged = byId[id] ?: JSONObject()
            fields.forEach { (key, value) -> merged.put(key, value) }
            merged.put("liveStateMillis", refreshedAtMillis)
            merged.put("syncedAtMillis", refreshedAtMillis)
            merged.put("source", "0x8600-owned-general-tail")
            byId[id] = merged
        }
        return JSONArray().apply { byId.values.forEach(::put) }.toString()
    }

    override suspend fun runBulkToolAction(session: GameSession, action: BulkToolAction): ProtocolResult<StepResult> =
        if (session.isRealSession()) unrecovered("REAL_BULK_TOOL_NOT_IMPLEMENTED", "真实批量工具协议尚未接入") else fallback.runBulkToolAction(session, action)

    override suspend fun queryOpenServer(query: OpenServerQuery): ProtocolResult<OpenServerResult> = fallback.queryOpenServer(query)

    override suspend fun searchDefendedCities(session: GameSession, config: CityDefenseSearchConfig): ProtocolResult<List<CitySearchResult>> =
        if (session.isRealSession()) unrecovered("REAL_CITY_SEARCH_NOT_IMPLEMENTED", "真实城池搜索协议尚未接入") else fallback.searchDefendedCities(session, config)

    override suspend fun searchTreasures(session: GameSession, config: TreasureFilterConfig): ProtocolResult<List<TreasureSearchResult>> =
        if (session.isRealSession()) unrecovered("REAL_TREASURE_SEARCH_NOT_IMPLEMENTED", "真实宝藏搜索协议尚未接入") else fallback.searchTreasures(session, config)

    override suspend fun applyLicense(config: LicenseConfig, action: LicenseAction): ProtocolResult<LicenseStatus> = fallback.applyLicense(config, action)

    private fun GameSession.isRealSession(): Boolean = sourceMode == 1

    private fun GameSession.hasRealActionScope(scope: String): Boolean {
        if (channelExtra["realActionScope"].equals(scope, ignoreCase = true)) return true
        return channelExtra["realActionScopes"]
            .orEmpty()
            .split(',', ';', '|')
            .any { it.trim().equals(scope, ignoreCase = true) }
    }

    private fun <T> unrecovered(code: String, message: String): ProtocolResult<T> =
        ProtocolResult.Err(code, message, retryable = false)

    /**
     * Optional live calibration bridge for recovered read-only 041540/041542 searches.
     *
     * This path stays closed unless the persisted real session explicitly contains one of:
     * - recoveredReadOnlyLiveGate=true
     * - enableRecoveredReadOnlyLive=true
     * - readOnlyLiveGate=true
     *
     * It only executes the already allow-listed 0x1540/0x1542 queries through
     * RealGameProtocolClient. Expedition/action opcodes are still rejected before network
     * by RealGameProtocolClient.planRecoveredReadOnlyGameHex/executeRecoveredReadOnlyGameHex.
     */
    private fun executeRecoveredTargetSearch(
        session: GameSession,
        start: MapCoordinate,
        policy: MapSearchPolicy
    ): ProtocolResult<List<MapTarget>>? {
        if (!session.recoveredReadOnlyLiveGateEnabled()) return null
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_READONLY_GAME_HTTP_MISSING", "已开启 041540 live gate，但真实 session 缺少 gameHttp/serverUrl", retryable = false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_READONLY_DM_MISSING", "已开启 041540 live gate，但真实 session 缺少 dm", retryable = false)

        val targets = mutableListOf<MapTarget>()
        val rawAudit = mutableListOf<String>()
        for (request in session.recoveredReadOnlyRequests(RecoveredSearchKind.TARGET_041540, start)) {
            val result = runCatching {
                requireExecutionAllowed("map-search/041540")
                recoveredReadOnlyExecutor.execute(gameHttp, dm, request.gameHex, liveGate = true)
            }.getOrElse {
                return ProtocolResult.Err("REAL_READONLY_TARGET_SEARCH_EXCEPTION", "041540 真实只读找黄异常：${it.message}", retryable = false)
            }
            rawAudit += "${request.coordinate.x},${request.coordinate.y}:${result.code}:${result.responseOpcodes.joinToString("|")}"
            if (!result.success) {
                return ProtocolResult.Err("REAL_READONLY_TARGET_SEARCH_FAILED", "041540 真实只读找黄失败：${result.code} ${result.message}", retryable = false)
            }
            targets += result.parsedTargets
        }
        return ProtocolResult.Ok(
            targets
                .distinctBy { it.id to it.coordinate }
                .map { target ->
                    target.copy(raw = target.raw + mapOf("liveAudit" to rawAudit.joinToString(";"), "liveGate" to "041540"))
                }
                .filterByPolicy(policy)
        )
    }

    private fun executeRecoveredMineSearch(session: GameSession, config: MineConfig): ProtocolResult<List<MineSearchResult>>? {
        if (!session.recoveredReadOnlyLiveGateEnabled()) return null
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_READONLY_GAME_HTTP_MISSING", "已开启 041542 live gate，但真实 session 缺少 gameHttp/serverUrl", retryable = false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_READONLY_DM_MISSING", "已开启 041542 live gate，但真实 session 缺少 dm", retryable = false)

        val mines = mutableListOf<MineSearchResult>()
        val rawAudit = mutableListOf<String>()
        for (request in session.recoveredMineReadOnlyRequests(config)) {
            val result = runCatching {
                requireExecutionAllowed("mine-search/041542")
                recoveredReadOnlyExecutor.execute(gameHttp, dm, request.gameHex, liveGate = true)
            }.getOrElse {
                return ProtocolResult.Err("REAL_READONLY_MINE_SEARCH_EXCEPTION", "041542 真实只读找矿异常：${it.message}", retryable = false)
            }
            rawAudit += "${request.coordinate.x},${request.coordinate.y}:${result.code}:${result.responseOpcodes.joinToString("|")}"
            if (!result.success) {
                return ProtocolResult.Err("REAL_READONLY_MINE_SEARCH_FAILED", "041542 真实只读找矿失败：${result.code} ${result.message}", retryable = false)
            }
            mines += result.parsedMines
        }
        return ProtocolResult.Ok(
            mines
                .distinctBy { it.id to it.coordinate }
                .map { mine -> mine.copy(raw = mine.raw + mapOf("liveAudit" to rawAudit.joinToString(";"), "liveGate" to "041542")) }
                .filterByMineConfig(config)
        )
    }

    private fun GameSession.recoveredReadOnlyLiveGateEnabled(): Boolean =
        listOf("recoveredReadOnlyLiveGate", "enableRecoveredReadOnlyLive", "readOnlyLiveGate")
            .any { channelExtra[it].asLooseBoolean() == true }


    private fun GameSession.liveStateKeyOrNull(): String? {
        val dm = dmOrNull() ?: return null
        val roleId = channelExtra["roleId"]?.parseLongFlexible() ?: accountId
        return "$accountId:$dm:$roleId"
    }

    private fun GameSession.liveStateErrorOrNull(): String? = liveStateKeyOrNull()?.let { liveStateErrors[it] }

    private fun GameSession.liveStateBundleOrNull(): LiveStateBundle? {
        if (!liveStateRefreshEnabled()) return null
        val gameHttp = gameHttpOrNull() ?: return null
        val dm = dmOrNull() ?: return null
        val roleId = channelExtra["roleId"]?.parseLongFlexible() ?: accountId
        val key = liveStateKeyOrNull() ?: return null
        val now = System.currentTimeMillis()
        liveStateCache[key]?.takeIf { now - it.refreshedAtMillis <= LIVE_STATE_CACHE_MS }?.let { return it }
        return runCatching {
            requireExecutionAllowed("role-state/1016")
            val result = RealGameProtocolClient().refreshRoleState(gameHttp, dm, roleId)
            val bundle = result.toLiveStateBundle()
            liveStateCache[key] = bundle
            liveStateErrors.remove(key)
            persistLiveStateBundle(this, bundle)
            actionAudit?.invoke(
                "真实 0x1016 状态刷新成功：role=${bundle.state.roleName} Lv.${bundle.state.level} " +
                    "copper=${bundle.state.copper} food=${bundle.state.food} opcodes=${bundle.responseOpcodes.joinToString()}"
            )
            bundle
        }.getOrElse {
            val message = it.message ?: it::class.java.simpleName
            liveStateErrors[key] = message
            actionAudit?.invoke("真实 0x1016 状态刷新失败：$message")
            null
        }
    }


    private fun String.looksLikeExpiredRoleSession(): Boolean =
        contains("没有角色信息") ||
            contains("沒有角色信息") ||
            contains("0x8016", ignoreCase = true)

    private fun GameSession.liveStateRefreshEnabled(): Boolean {
        val explicit = listOf("liveStateRefreshEnabled", "realStateLiveRefresh", "enableLive1016Refresh")
            .firstNotNullOfOrNull { channelExtra[it].asLooseBoolean() }
        if (explicit != null) return explicit
        val gameHttp = gameHttpOrNull().orEmpty()
        val hasRealSessionFields = dmOrNull() != null &&
            (channelExtra["roleId"]?.parseLongFlexible() ?: accountId) > 0L &&
            gameHttp.isNotBlank()
        val looksLikeFixture = gameHttp.contains("example", ignoreCase = true) || gameHttp.contains("localhost", ignoreCase = true)
        return hasRealSessionFields && !looksLikeFixture
    }

    private fun RealGameProtocolClient.LiveStateRefreshResult.toLiveStateBundle(): LiveStateBundle {
        val state = state
        val roleJson = JSONObject()
            .put("roleId", state.roleId)
            .put("roleName", state.roleName)
            .put("level", state.level)
            .put("prestige", state.prestige)
            .put("populationCurrent", state.populationCurrent)
            .put("populationCap", state.populationCap)
            .put("fiefLimit", state.fiefLimit)
            .put("generalLimit", state.generalLimit)
            .put("resourcePointCurrent", state.resourcePointCurrent)
            .put("resourcePointCap", state.resourcePointCap)
            .put("officeFieldFlag", state.officeFieldFlag ?: JSONObject.NULL)
            .put("officeId", state.officeIdUnsigned ?: JSONObject.NULL)
            .put("officeIdRaw", state.officeIdRaw ?: JSONObject.NULL)
            .put("officeIdUnsigned", state.officeIdUnsigned ?: JSONObject.NULL)
            .put("officeName", state.officeName)
            .put("sourceOpcode", state.sourceOpcode)
            .put("state8004PayloadByteCount", state.payloadByteCount)
            .put("state8004ParsedHeadByteCount", state.parsedHeadByteCount)
            .put("state8004TailByteCount", state.tailByteCount)
            .put("liveStateMillis", refreshedAtMillis)
            .put("syncedAtMillis", refreshedAtMillis)
        val resourceJson = JSONObject()
            .put("copper", state.copper)
            .put("food", state.food)
            .put("prestige", state.prestige)
            .put("copperPerHour", state.copperPerHour)
            .put("foodPerHour", state.foodPerHour)
            .put("populationCurrent", state.populationCurrent)
            .put("populationCap", state.populationCap)
            .put("resourcePointCurrent", state.resourcePointCurrent)
            .put("resourcePointCap", state.resourcePointCap)
            .put("sourceOpcode", state.sourceOpcode)
            .put("liveStateMillis", refreshedAtMillis)
            .put("syncedAtMillis", refreshedAtMillis)
        return LiveStateBundle(state, roleJson, resourceJson, responseOpcodes, refreshedAtMillis)
    }

    private fun persistLiveStateBundle(session: GameSession, live: LiveStateBundle) {
        val state = live.state
        val generalRecords = State8004GeneralEvidenceParser.recoverBestAvailableRecords(
            state.tailHex,
            state.payloadHex
        )
        val statusRecords = State8004StatusEvidenceParser.recoverRecords(state.payloadHex)
        val armyRows = State8004ArmyEvidenceParser.recover(state.payloadHex)
        val updates = buildMap {
                put("roleId", state.roleId.toString())
                put("roleName", state.roleName)
                put("level", state.level.toString())
                put("copper", state.copper.toString())
                put("food", state.food.toString())
                put("prestige", state.prestige.toString())
                put("populationCurrent", state.populationCurrent.toString())
                put("populationCap", state.populationCap.toString())
                put("resourcePointCurrent", state.resourcePointCurrent.toString())
                put("resourcePointCap", state.resourcePointCap.toString())
                put("officeFieldFlag", state.officeFieldFlag?.toString().orEmpty())
                put("officeId", state.officeIdUnsigned?.toString().orEmpty())
                put("officeIdRaw", state.officeIdRaw?.toString().orEmpty())
                put("officeIdUnsigned", state.officeIdUnsigned?.toString().orEmpty())
                put("officeName", state.officeName)
                put("officialTitle", state.officeName)
                put("roleStateJson", live.roleJson.toString())
                put("resourceStateJson", live.resourceJson.toString())
                put("state8004PayloadHex", state.payloadHex)
                put("state8004TailHex", state.tailHex)
                put("lastValidatedAt", live.refreshedAtMillis.toString())
                if (generalRecords.isNotEmpty()) {
                    put("generalsJson", JSONArray().apply {
                        generalRecords.forEach { put(JSONObject(it)) }
                    }.toString())
                    put("state8004GeneralRecordCount", generalRecords.size.toString())
                    put("generalsParserVersion", State8004GeneralEvidenceParser.PARSER_VERSION)
                }
                if (statusRecords.isNotEmpty()) {
                    put("statusJson", JSONArray().apply {
                        statusRecords.forEach { put(JSONObject(it)) }
                    }.toString())
                    put("state8004StatusRecordCount", statusRecords.size.toString())
                }
                if (armyRows.isNotEmpty()) {
                    put("armyJson", State8004ArmyEvidenceParser.toJson(armyRows))
                    put("armySource", "live/0x8004-compact-army")
                    put("armyRecordCount", armyRows.size.toString())
                }
            }
        liveSessionExtraCache.compute(session.accountId) { _, current -> current.orEmpty() + updates }
        sessionExtraSink?.invoke(session.accountId, updates)
    }

    private fun parseGeneralsFromLiveState(live: LiveStateBundle): List<General> =
        parseGeneralsFlexible(live.state.payloadHex).map { general ->
            general.copy(
                raw = general.raw + mapOf(
                    "liveStateMillis" to live.refreshedAtMillis.toString(),
                    "syncedAtMillis" to live.refreshedAtMillis.toString(),
                    "source" to "live-1016-state8004"
                )
            )
        }

    private fun FormationRuntime.withLiveState(refreshedAtMillis: Long): FormationRuntime =
        copy(
            raw = raw + mapOf(
                "liveStateMillis" to refreshedAtMillis.toString(),
                "syncedAtMillis" to refreshedAtMillis.toString(),
                "source" to "live-1016-recovered-formation"
            )
        )

    private fun GameSession.gameHttpOrNull(): String? {
        val gameHttp = channelExtra["gameHttp"]?.takeIf { it.isNotBlank() }
            ?: channelExtra["gameHttpUrl"]?.takeIf { it.isNotBlank() }
            ?: channelExtra["serverUrl"]?.takeIf { it.isNotBlank() }
                ?.trimEnd('/')
                ?.plus("/kingWapServer/HttpClient")
            ?: return null
        return gameHttp
    }

    private fun GameSession.dmOrNull(): Long? = channelExtra["dm"]?.parseLongFlexible()

    private suspend fun executeRecoveredBrushYellowLiveAction(
        session: GameSession,
        formationId: Long,
        requestedGeneralIds: List<Long>,
        target: MapTarget,
        formationRules: List<FormationConfig>
    ): ProtocolResult<BattleResult>? {
        val brushContract = behaviorContract.brushYellow
        val expeditionContract = behaviorContract.expedition
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed && !sendReady) return null
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err(
                "REAL_ACTION_GATE_NOT_READY",
                "真实动作 gate 未同时开启：realActionNetworkAllowed=$networkAllowed realActionSendReady=$sendReady",
                retryable = false
            )
        }
        val brushYellowScopeConfirmed =
            session.hasRealActionScope("brush-yellow") ||
                session.channelExtra["realActionBrushYellowOnly"].asLooseBoolean() == true
        if (!brushYellowScopeConfirmed) {
            return ProtocolResult.Err(
                "REAL_ACTION_SCOPE_NOT_CONFIRMED",
                "真实动作 gate 已开启，但缺少 realActionScope=brush-yellow 或 realActionBrushYellowOnly=true；已阻止真实发送",
                retryable = false
            )
        }

        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_ACTION_GAME_HTTP_MISSING", "真实动作 gate 已开启，但 session 缺少 gameHttp/serverUrl", retryable = false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_ACTION_DM_MISSING", "真实动作 gate 已开启，但 session 缺少 dm", retryable = false)
        val monarch = when (val result = queryMonarch(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (monarch.level < brushContract.minimumRoleLevel) {
            return ProtocolResult.Err(
                "REAL_ACTION_ROLE_LEVEL_LOW",
                "请${brushContract.minimumRoleLevel}级之后再开启刷黄！",
                retryable = false
            )
        }
        val preflight = when (val result = expeditionPreflight.check(
            session,
            ExpeditionPreflightRequest(
                label = "刷黄",
                generalIds = requestedGeneralIds,
                formationId = formationId,
                refillToFull = session.channelExtra["brushReplenishTroops"].asLooseBoolean() == true,
                formationRules = formationRules
            )
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (preflight.generalIds.size > brushContract.maximumGeneralsPerFormation) {
            return ProtocolResult.Err(
                "REAL_ACTION_TOO_MANY_GENERALS",
                "刷黄编队最多选择${brushContract.maximumGeneralsPerFormation}名出征将领",
                retryable = false
            )
        }
        val generalChunks = preflight.generalIds.map { it.toString(16).padStart(16, '0') }
        val targetHex = target.actionTargetHex()
        val payloads = runCatching {
            BrushYellowDispatchPayloadBuilder.buildBrushYellowPayloads(
                generalIdHexChunks = generalChunks,
                targetIdHex = targetHex,
                actionType = brushContract.actionType
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_ACTION_PAYLOAD_BUILD_FAILED", "真实刷黄 payload 构造失败：${it.message}", retryable = false)
        }

        actionAudit?.invoke(
            "真实刷黄二进制 sender 准备发送：formation=$formationId target=${target.id} " +
                "targetHex=$targetHex generals=${generalChunks.size} scope=brush-yellow gates=true variant=${payloads.variant}"
        )

        val prepare = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                payloads.preparePayload,
                phase = "brush-yellow/prepare/p2=${payloads.variant}"
            )
        }.getOrElse {
            actionAudit?.invoke("真实刷黄 prepare 异常：p2=${payloads.variant} ${it.message}")
            return ProtocolResult.Err(
                "REAL_ACTION_PREPARE_EXCEPTION",
                "${payloads.prepareOpcode} 发送异常：${it.message}",
                retryable = true
            )
        }
        actionAudit?.invoke(
            "真实刷黄 prepare 返回：p2=${payloads.variant} opcode=${payloads.prepareOpcode} " +
                "http=${prepare.httpCode} bytes=${prepare.responseBytes} " +
                "text=${prepare.textPreview.take(80)} hex=${prepare.responseHex.take(64)}"
        )
        if (!prepare.ok) {
            return ProtocolResult.Err(
                "REAL_ACTION_PREPARE_HTTP_FAILED",
                "${payloads.prepareOpcode} HTTP ${prepare.httpCode}: ${prepare.textPreview.take(160)}",
                retryable = true
            )
        }
        val prepareResponseHex = prepare.payloadHexFor(expeditionContract.prepareResponseOpcode)
        if (expeditionContract.prepareResponseOpcode !in prepare.responseOpcodes ||
            prepareResponseHex?.filter(Char::isLetterOrDigit).equals(
                expeditionContract.softRejectPayload.toHex(),
                ignoreCase = true
            )
        ) {
            return ProtocolResult.Ok(
                BattleResult(
                    success = false,
                    consumedTimes = 0,
                    raw = mapOf(
                        "message" to "刷黄预出征未获得0x${expeditionContract.prepareResponseOpcode.toString(16)}" +
                            "成功确认，已禁止正式出征",
                        "payloadVariant" to payloads.variant.toString(),
                        "prepareResponseHex" to prepareResponseHex.orEmpty().take(2048)
                    )
                )
            )
        }

        return expeditionTransactions.execute(
            accountId = session.accountId,
            action = "刷黄",
            targetKey = "${target.id}@${target.coordinate.x},${target.coordinate.y}",
            snapshot = preflight,
            exceptionCode = "REAL_ACTION_EXPEDITION_EXCEPTION",
            exceptionLabel = "${payloads.expeditionOpcode} 发送异常"
        ) {
            val pendingRecovery = BrushPendingRecovery(
                generalIds = preflight.generalIds,
                formationId = formationId,
                targetId = target.id,
                targetX = target.coordinate.x,
                targetY = target.coordinate.y,
                createdAtMillis = System.currentTimeMillis(),
                // Persist before network I/O. A process death in the send boundary must
                // recover conservatively and perform maintenance before another brush run.
                sendState = "sending"
            )
            persistBrushPendingRecovery(session, pendingRecovery)
            val expedition = sendBinaryMappedGameHex(
                gameHttp,
                dm,
                payloads.expeditionPayload,
                phase = "brush-yellow/expedition/p2=${payloads.variant}"
            )
            val expeditionResponseHex = expedition.payloadHexFor(
                expeditionContract.dispatchResponseOpcode
            )
            val parsed = BrushYellowDispatchResponseParser.parse(
                responseHex = expeditionResponseHex,
                contract = expeditionContract
            ) ?: BrushYellowDispatchResponseParser.parse(
                responseText = expedition.textPreview,
                contract = expeditionContract
            )
            actionAudit?.invoke(
                "真实刷黄 expedition 返回：p2=${payloads.variant} opcode=${payloads.expeditionOpcode} " +
                    "http=${expedition.httpCode} bytes=${expedition.responseBytes} " +
                    "success=${parsed?.success ?: "unknown"} msg=${parsed?.message?.take(60) ?: ""} " +
                    "hex=${expedition.responseHex.take(64)}"
            )
            if (!expedition.ok) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_ACTION_EXPEDITION_HTTP_FAILED",
                        "${payloads.expeditionOpcode} HTTP ${expedition.httpCode}: ${expedition.textPreview.take(160)}",
                        retryable = true
                    ),
                    "HTTP ${expedition.httpCode}; request acceptance is unknown"
                )
            }
            if (expeditionContract.dispatchResponseOpcode !in expedition.responseOpcodes) {
                return@execute ExpeditionSendResult.uncertain(
                    ProtocolResult.Err(
                        "REAL_ACTION_EXPEDITION_RECEIPT_MISSING",
                        "刷黄出征未收到0x${expeditionContract.dispatchResponseOpcode.toString(16)}" +
                            "，已冻结编队等待真实状态确认",
                        retryable = true
                    ),
                    "2xx response without 0x${expeditionContract.dispatchResponseOpcode.toString(16)}"
                )
            }

            val success = parsed?.isSuccessForCurrentTarget(
                target,
                requirePositiveBattleId = expeditionContract.dispatchSuccessRequiresPositiveBattleId
            ) == true
            val contextualMessage = when {
                parsed?.success == true && !success ->
                    "响应中出现战报成功文本，但未匹配本次目标坐标/ID，已冻结编队等待确认"
                else -> parsed?.message
            }
            val battle = ProtocolResult.Ok(
                BattleResult(
                    success = success,
                    consumedTimes = parsed?.consumedTimes ?: if (success) 1 else 0,
                    raw = buildMap {
                        put("realActionNetworkAllowed", "true")
                        put("realActionSendReady", "true")
                        put("realActionScope", "brush-yellow")
                        put("sender", "direct-binary-game-command")
                        put("formationId", formationId.toString())
                        put("targetId", target.id.toString())
                        put("targetHex", targetHex)
                        put("payloadVariant", payloads.variant.toString())
                        put("actionType", brushContract.actionType.toString())
                        put("attemptedPayloadVariants", payloads.variant.toString())
                        put("preparePayload", payloads.preparePayload)
                        put("expeditionPayload", payloads.expeditionPayload)
                        put("prepareOpcode", payloads.prepareOpcode)
                        put("expeditionOpcode", payloads.expeditionOpcode)
                        put("prepareHttpCode", prepare.httpCode.toString())
                        put("expeditionHttpCode", expedition.httpCode.toString())
                        put("prepareResponseHex", prepareResponseHex.orEmpty().take(2048))
                        put("expeditionResponseHex", expeditionResponseHex.orEmpty().take(2048))
                        put("prepareResponseText", prepare.textPreview.take(512))
                        put("expeditionResponseText", expedition.textPreview.take(512))
                        contextualMessage?.let { put("message", it) }
                        put("responseHex", expeditionResponseHex.orEmpty().take(2048))
                        putAll(parsed?.toRawMap("expeditionParsed").orEmpty())
                        put(
                            "binaryMapping",
                            "shared-contract actionType=${brushContract.actionType}; exactly one " +
                                "0x${expeditionContract.dispatchOpcode.toString(16)} mutation request"
                        )
                    }
                )
            )
            when {
                success -> {
                    persistBrushPendingRecovery(
                        session,
                        pendingRecovery.copy(sendState = "accepted")
                    )
                    ExpeditionSendResult.accepted(battle, "explicit 0x8522 success")
                }
                parsed?.success == false -> {
                    sessionExtraSink?.invoke(
                        session.accountId,
                        mapOf(BrushPendingRecovery.SESSION_KEY to "{}")
                    )
                    ExpeditionSendResult.rejected(
                        battle,
                        "explicit 0x8522 rejection: ${parsed.evidence}"
                    )
                }
                else -> {
                    persistBrushPendingRecovery(
                        session,
                        pendingRecovery.copy(sendState = "uncertain")
                    )
                    ExpeditionSendResult.uncertain(
                        battle,
                        "0x8522 receipt could not be tied to the current target"
                    )
                }
            }
        }
    }

    private fun persistBrushPendingRecovery(
        session: GameSession,
        pending: BrushPendingRecovery
    ) {
        sessionExtraSink?.invoke(
            session.accountId,
            mapOf(BrushPendingRecovery.SESSION_KEY to pending.toJson().toString())
        )
    }

    private fun BrushYellowDispatchResponse.isSuccessForCurrentTarget(
        target: MapTarget,
        requirePositiveBattleId: Boolean
    ): Boolean {
        if (success != true) return false
        if (requirePositiveBattleId && (battleId ?: 0L) <= 0L) return false
        if (evidence.startsWith("hex-8522-status-0")) return true
        if (rawText.contains("刷黄出征成功") || rawText.contains("出征成功") || rawText.contains("success", ignoreCase = true)) {
            return true
        }
        if (!rawText.contains("消灭") &&
            !rawText.contains("消滅") &&
            !rawText.contains("战斗胜利") &&
            !rawText.contains("戰鬥勝利")
        ) {
            return true
        }
        val x = target.coordinate.x
        val y = target.coordinate.y
        val targetIdHex = target.id.toString(16)
        return rawText.contains("($x,$y)") ||
            rawText.contains("（$x,$y）") ||
            rawText.contains("$x,$y") ||
            rawText.contains(target.id.toString()) ||
            rawText.contains(targetIdHex, ignoreCase = true)
    }

    private fun executeRecoveredFormationUpdateLiveAction(
        session: GameSession,
        config: FormationConfig
    ): ProtocolResult<StepResult>? {
        val gate = session.brushYellowActionGateOrError() ?: return null
        if (gate is ProtocolResult.Err) return gate
        val contract = behaviorContract.formation
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_FORMATION_GAME_HTTP_MISSING", "真实配兵 gate 已开启，但 session 缺少 gameHttp/serverUrl", retryable = false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_FORMATION_DM_MISSING", "真实配兵 gate 已开启，但 session 缺少 dm", retryable = false)
        val generalIds = config.generalIds.ifEmpty {
            listOf(config.formationId).filter { it > 0L }
        }.filter { it > 0L }
        if (generalIds.isEmpty()) {
            return ProtocolResult.Err("REAL_FORMATION_GENERAL_MISSING", "真实配兵缺少将领 ID", retryable = false)
        }
        if (!config.autoAssignTroops &&
            !config.fillToMaxWhenAutoAssignDisabled &&
            config.clearOtherGeneralIds.isEmpty() &&
            !config.clearAllIdleTroops
        ) {
            return ProtocolResult.Ok(StepResult(true, "配兵未启用，跳过真实 0x1226/0x1229", raw = mapOf("skipped" to "true")))
        }

        val raw = linkedMapOf<String, String>(
            "realActionNetworkAllowed" to "true",
            "realActionScope" to "brush-yellow",
            "troopType" to config.troopType,
            "troopCount" to config.troopCount.toString(),
            "generalIds" to generalIds.joinToString(","),
            "batchRefillOnly" to (!config.autoAssignTroops && config.fillToMaxWhenAutoAssignDisabled).toString(),
            "clearOtherGeneralIds" to config.clearOtherGeneralIds.joinToString(","),
            "clearAllIdleTroops" to config.clearAllIdleTroops.toString()
        )
        val currentGenerals = queryGeneralListForFormationStatus(session).associateBy(General::id)
        val idleSoldiers = session.idleSoldierCounts()?.toMutableMap()

        if (config.clearOtherGeneralIds.isNotEmpty() || config.clearAllIdleTroops) {
            var cleared = 0
            var skipped = 0
            currentGenerals.values
                .filter { config.clearAllIdleTroops || it.id !in config.clearOtherGeneralIds }
                .forEach { general ->
                    val current = general.currentAssignedTroops() ?: return@forEach
                    if (current.count <= 0) return@forEach
                    if (general.status != contract.idleGeneralStatus) {
                        skipped += 1
                        raw["clear.${general.id}.skipped"] = "status=${general.status ?: "unknown"}"
                        return@forEach
                    }
                    val outcome = runCatching {
                        sendFormationAssignment(
                            gameHttp = gameHttp,
                            dm = dm,
                            generalId = general.id,
                            soldierType = current.typeCode,
                            soldierCount = 0,
                            phase = "formation/clear-other",
                            contract = contract
                        )
                    }.getOrElse { error ->
                        raw["clear.${general.id}.error"] = error.message.orEmpty()
                        actionAudit?.invoke("解除其他将领配兵异常：general=${general.id} ${error.message}")
                        return@forEach
                    }
                    raw.recordFormationAssignment("clear.${general.id}", outcome)
                    if (outcome.confirmed && outcome.receipt.assignedCount == 0) {
                        cleared += 1
                        idleSoldiers?.merge(current.typeCode, current.count, Int::plus)
                    } else {
                        raw["clear.${general.id}.skipped"] = outcome.message
                    }
                }
            raw["clear.clearedCount"] = cleared.toString()
            raw["clear.skippedCount"] = skipped.toString()
            invalidateLiveState(session)
        }

        if (config.autoAssignTroops) {
            val targetCode = soldierTypeCode(config.troopType)
            generalIds.forEach { generalId ->
                val general = currentGenerals[generalId]
                    ?: return ProtocolResult.Err(
                        "REAL_FORMATION_GENERAL_NOT_FOUND",
                        "真实配兵未找到将领 ID=$generalId",
                        false
                    )
                if (general.status != contract.idleGeneralStatus) {
                    return ProtocolResult.Ok(
                        StepResult(false, "将领${general.name}当前不是空闲状态，未执行配兵", raw)
                    )
                }
                val effectiveCount = if (contract.clampCountToTroopLimit) {
                    general.troopLimit?.takeIf { it > 0 }?.let { minOf(config.troopCount, it) }
                        ?: config.troopCount
                } else {
                    config.troopCount
                }
                raw["assign.${generalId}.requestedCount"] = config.troopCount.toString()
                raw["assign.${generalId}.effectiveCount"] = effectiveCount.toString()
                val current = general.currentAssignedTroops()
                if (current != null && current.typeCode == targetCode && current.count == effectiveCount) {
                    raw["assign.${generalId}.skipped"] = "already-satisfied"
                    raw["assign.${generalId}.assignedType"] = current.typeCode.toString()
                    raw["assign.${generalId}.assignedCount"] = current.count.toString()
                    raw["assign.${generalId}.message"] = "当前将领已精确满足 ${effectiveCount}${config.troopType}，跳过 0x1226"
                    actionAudit?.invoke(
                        "真实配兵跳过：general=$generalId 当前=${current.count}${config.troopType}(code=${current.typeCode}) 已精确满足目标"
                    )
                    return@forEach
                }

                val alreadyCarryingTarget = current
                    ?.takeIf { it.typeCode == targetCode }
                    ?.count
                    ?: 0
                if (contract.precheckIdleSoldierInventory && alreadyCarryingTarget < effectiveCount) {
                    val inventory = idleSoldiers
                        ?: return ProtocolResult.Ok(
                            StepResult(false, "无法确认当前闲兵数量，已保持${general.name}原配兵不变", raw)
                        )
                    val available = alreadyCarryingTarget + (inventory[targetCode] ?: 0)
                    if (available < effectiveCount) {
                        return ProtocolResult.Ok(
                            StepResult(
                                false,
                                "${general.name}缺少${effectiveCount - available}${config.troopType}；" +
                                    "目标$effectiveCount，可用$available，已保持原配兵不变",
                                raw
                            )
                        )
                    }
                }

                val outcome = runCatching {
                    sendFormationAssignment(
                        gameHttp = gameHttp,
                        dm = dm,
                        generalId = generalId,
                        soldierType = targetCode,
                        soldierCount = effectiveCount,
                        phase = "formation/assign",
                        contract = contract
                    )
                }.getOrElse { error ->
                    actionAudit?.invoke("真实配兵异常：general=$generalId ${error.message}")
                    return ProtocolResult.Err(
                        "REAL_FORMATION_ASSIGN_EXCEPTION",
                        "配兵发送异常：${error.message}",
                        retryable = false
                    )
                }
                raw.recordFormationAssignment("assign.$generalId", outcome)
                val exact = outcome.confirmed &&
                    outcome.receipt.assignedType == targetCode &&
                    outcome.receipt.assignedCount == effectiveCount
                if (!exact) {
                    return ProtocolResult.Ok(
                        StepResult(
                            false,
                            "真实配兵未达到配置：需要 $effectiveCount${config.troopType}；${outcome.message}",
                            raw
                        )
                    )
                }
                current?.takeIf { it.count > 0 }?.let {
                    idleSoldiers?.merge(it.typeCode, it.count, Int::plus)
                }
                idleSoldiers?.computeIfPresent(targetCode) { _, count ->
                    (count - effectiveCount).coerceAtLeast(0)
                }
            }

            invalidateLiveState(session)
            if (session.liveStateRefreshEnabled()) {
                val refreshed = session.liveStateBundleOrNull()
                    ?: return ProtocolResult.Err(
                        "REAL_FORMATION_VERIFY_REFRESH_FAILED",
                        "配兵成功回执后无法刷新0x8004复核",
                        retryable = true
                    )
                val byId = parseGeneralsFromLiveState(refreshed).associateBy(General::id)
                generalIds.forEach { generalId ->
                    val general = byId[generalId]
                        ?: return ProtocolResult.Err(
                            "REAL_FORMATION_VERIFY_GENERAL_MISSING",
                            "配兵后刷新未找到将领 ID=$generalId",
                            false
                        )
                    val expected = general.troopLimit?.takeIf { it > 0 }?.let { minOf(config.troopCount, it) }
                        ?: config.troopCount
                    val actual = general.currentAssignedTroops()
                    if (actual?.typeCode != targetCode || actual.count != expected) {
                        return ProtocolResult.Ok(
                            StepResult(false, "配兵后复核不一致：${general.name}需要$expected${config.troopType}", raw)
                        )
                    }
                }
            }
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    "真实配兵完成：${generalIds.joinToString(",")} → ${config.troopCount}${config.troopType}",
                    raw
                )
            )
        }

        if (!config.fillToMaxWhenAutoAssignDisabled) {
            return ProtocolResult.Ok(StepResult(true, "其他将领配兵清理完成", raw))
        }
        val refillPayload = buildRefillPayload(generalIds)
        val refillResponse = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(contract.refillRequestOpcode, refillPayload),
                phase = "formation/refill"
            )
        }.getOrElse {
            actionAudit?.invoke("真实补兵异常：${it.message}")
            return ProtocolResult.Err("REAL_FORMATION_REFILL_EXCEPTION", "补兵发送异常：${it.message}", retryable = false)
        }
        val refillOpcodeConfirmed = contract.refillResponseOpcode in refillResponse.responseOpcodes
        val refillPayloadHex = refillResponse.payloadHexFor(contract.refillResponseOpcode).orEmpty()
        val refillParsed = Formation122xResponseParser.parse8229(refillPayloadHex)
        val refillIds = refillParsed.entries.map { it.generalId }.toSet()
        val refillEntriesComplete = generalIds.all { it in refillIds }
        raw["refill.payloadHex"] = refillPayload.toHex()
        raw["refill.http"] = refillResponse.httpCode.toString()
        raw["refill.responseOpcodes"] =
            refillResponse.responseOpcodes.joinToString { "0x${it.toString(16)}" }
        raw["refill.responseHex"] = refillPayloadHex.take(512)
        raw["refill.status"] = refillParsed.status?.toString().orEmpty()
        raw["refill.message"] = refillParsed.message
        raw["refill.entries"] = refillParsed.entries.joinToString(";") {
            "${it.generalId}:${it.soldierType}:${it.soldierCount}"
        }
        raw["refill.success"] = (
            refillResponse.ok && refillOpcodeConfirmed && refillParsed.success && refillEntriesComplete
            ).toString()
        actionAudit?.invoke(
            "真实补兵 0x1229 返回：generals=${generalIds.joinToString(",")} " +
                "opcodeConfirmed=$refillOpcodeConfirmed entriesComplete=$refillEntriesComplete " +
                "success=${refillParsed.success} msg=${refillParsed.message} http=${refillResponse.httpCode}"
        )
        val success = refillResponse.ok && refillOpcodeConfirmed &&
            refillParsed.success && refillEntriesComplete
        val message = when {
            success && !config.autoAssignTroops ->
                "真实批量补满完成：${generalIds.joinToString(",")}"
            success -> "真实配兵/补兵完成：${generalIds.joinToString(",")} → ${config.troopCount}${config.troopType}"
            !refillOpcodeConfirmed -> "真实补兵 0x1229 未收到 0x8229；失败关闭"
            !refillEntriesComplete -> "真实补兵 0x8229 未返回全部将领结果；失败关闭"
            !refillParsed.success -> "真实补兵 0x1229 未确认成功：${refillParsed.message}"
            else -> "真实配兵/补兵未确认成功"
        }
        return ProtocolResult.Ok(StepResult(success, message, raw))
    }

    private data class FormationAssignmentOutcome(
        val payload: ByteArray,
        val response: DirectBinaryResponse,
        val receipt: FormationAssign8226Result,
        val opcodeConfirmed: Boolean,
        val confirmed: Boolean,
        val message: String
    )

    private fun sendFormationAssignment(
        gameHttp: String,
        dm: Long,
        generalId: Long,
        soldierType: Int,
        soldierCount: Int,
        phase: String,
        contract: FormationBehaviorContract
    ): FormationAssignmentOutcome {
        val payload = buildAssignTroopsPayload(generalId, soldierType, soldierCount, group = 0)
        val response = sendBinaryMappedGameHex(
            gameHttp,
            dm,
            buildDirectGameHex(contract.assignRequestOpcode, payload),
            phase = phase
        )
        val opcodeConfirmed = contract.assignResponseOpcode in response.responseOpcodes
        val receipt = Formation122xResponseParser.parse8226(
            response.payloadHexFor(contract.assignResponseOpcode).orEmpty()
        )
        val generalMatches = receipt.generalId == generalId
        val confirmed = response.ok && opcodeConfirmed && receipt.success && generalMatches
        val message = when {
            !response.ok -> "配兵 HTTP ${response.httpCode}"
            !opcodeConfirmed -> "配兵未收到 0x${contract.assignResponseOpcode.toString(16)}"
            !generalMatches -> "配兵回执将领ID不匹配：${receipt.generalId}"
            else -> receipt.message
        }
        actionAudit?.invoke(
            "真实配兵返回：phase=$phase general=$generalId target=$soldierCount/type=$soldierType " +
                "confirmed=$confirmed actual=${receipt.assignedCount}/type=${receipt.assignedType} " +
                "http=${response.httpCode}"
        )
        return FormationAssignmentOutcome(payload, response, receipt, opcodeConfirmed, confirmed, message)
    }

    private fun MutableMap<String, String>.recordFormationAssignment(
        prefix: String,
        outcome: FormationAssignmentOutcome
    ) {
        this["$prefix.payloadHex"] = outcome.payload.toHex()
        this["$prefix.http"] = outcome.response.httpCode.toString()
        this["$prefix.responseOpcodes"] = outcome.response.responseOpcodes.joinToString { "0x${it.toString(16)}" }
        this["$prefix.responseHex"] = outcome.response.responseHex.take(512)
        this["$prefix.status"] = outcome.receipt.status?.toString().orEmpty()
        this["$prefix.previousType"] = outcome.receipt.previousType?.toString().orEmpty()
        this["$prefix.previousCount"] = outcome.receipt.previousCount?.toString().orEmpty()
        this["$prefix.assignedType"] = outcome.receipt.assignedType?.toString().orEmpty()
        this["$prefix.assignedCount"] = outcome.receipt.assignedCount?.toString().orEmpty()
        this["$prefix.confirmed"] = outcome.confirmed.toString()
        this["$prefix.message"] = outcome.message
    }

    private fun GameSession.idleSoldierCounts(): Map<Int, Int>? {
        val raw = liveSessionExtraCache[accountId]?.get("armyJson")
            ?: channelExtra["armyJson"]
            ?: return null
        val rows = runCatching { JSONArray(raw) }.getOrNull() ?: return null
        val counts = linkedMapOf<Int, Int>()
        for (index in 0 until rows.length()) {
            val row = rows.optJSONObject(index) ?: continue
            val type = row.optInt("soldierTypeCode", -1)
            val count = row.optInt("idleCount", row.optInt("count", row.optInt("amount", 0)))
            if (type >= 0 && count > 0) counts.merge(type, count, Int::plus)
        }
        return counts
    }

    private fun invalidateLiveState(session: GameSession) {
        session.liveStateKeyOrNull()?.let(liveStateCache::remove)
    }

    private data class CurrentAssignedTroops(val typeCode: Int, val count: Int)

    private fun General.currentAssignedTroops(): CurrentAssignedTroops? {
        val typeCode = raw.firstIntValue(
            "soldierTypeCode",
            "troopTypeCode",
            "assignedSoldierTypeCode",
            "assignedType"
        ) ?: soldierTypeCode(
            raw["soldierType"]
                ?: raw["troopType"]
                ?: raw["soldierTypeName"]
                ?: raw["troopTypeName"]
                ?: return null
        )
        val count = raw.firstIntValue(
            "soldierCount",
            "troopCount",
            "currentSoldierCount",
            "currentTroopCount",
            "bingli",
            "assignedSoldierCount"
        ) ?: return null
        return CurrentAssignedTroops(typeCode, count)
    }

    private fun Map<String, String>.firstIntValue(vararg keys: String): Int? {
        for (key in keys) {
            this[key]?.filter { it == '-' || it.isDigit() }?.takeIf { it.isNotBlank() }?.toIntOrNull()?.let { return it }
        }
        return null
    }

    private fun executeRecoveredHealWoundedLiveAction(
        session: GameSession,
        generalId: Long
    ): ProtocolResult<StepResult>? {
        val networkAllowed = session.channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = session.channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed && !sendReady) return null
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err(
                "REAL_HEAL_GATE_NOT_READY",
                "真实治疗 gate 未同时开启：realActionNetworkAllowed=$networkAllowed realActionSendReady=$sendReady",
                false
            )
        }
        if (!session.hasRealActionScope("general-maintenance") &&
            !session.hasRealActionScope("brush-yellow")
        ) {
            return ProtocolResult.Err(
                "REAL_HEAL_SCOPE_NOT_CONFIRMED",
                "真实治疗需要 general-maintenance 或 brush-yellow 作用域",
                false
            )
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_HEAL_GAME_HTTP_MISSING", "真实治疗 gate 已开启，但 session 缺少 gameHttp/serverUrl", retryable = false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_HEAL_DM_MISSING", "真实治疗 gate 已开启，但 session 缺少 dm", retryable = false)
        val armyRows = session.liveStateBundleOrNull()?.state?.payloadHex
            ?.let(State8004ArmyEvidenceParser::recover)
            .orEmpty()
        if (armyRows.isNotEmpty() && armyRows.sumOf { it.woundedCount } <= 0) {
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    "当前没有伤兵，跳过治疗请求",
                    mapOf("skipped" to "no-wounded-soldiers")
                )
            )
        }
        val general = queryGeneralListForFormationStatus(session).firstOrNull { it.id == generalId }
            ?: return ProtocolResult.Err(
                "REAL_HEAL_GENERAL_NOT_FOUND",
                "未找到治疗代表将领 ID=$generalId",
                false
            )
        val fiefId = general.placeId
            ?: session.channelExtra["fiefId"]?.parseLongFlexible()
            ?: session.channelExtra["placeID"]?.parseLongFlexible()
            ?: session.channelExtra["placeId"]?.parseLongFlexible()
            ?: return ProtocolResult.Err("REAL_HEAL_FIEF_MISSING", "真实治疗缺少 fiefId/placeID，无法构造 0x1231/0x1230", retryable = false)

        // 与电脑端已验证逻辑保持一致：伤兵精确数量未稳定恢复时，使用客户端“治疗全部”语义：
        // 0x1231: long fiefId, short -1, int -1；0x1230: long fiefId, byte 2, short 0, int -1, byte 0。
        val prePayload = GeneralProtocolShapes.buildHealAllPreInfoPayload(fiefId)
        val pre = runCatching {
            sendBinaryMappedGameHex(gameHttp, dm, buildDirectGameHex(0x1231, prePayload), phase = "heal/1231")
        }.getOrElse {
            actionAudit?.invoke("真实治疗预估 0x1231 异常：general=$generalId ${it.message}")
            return ProtocolResult.Err("REAL_HEAL_PREINFO_EXCEPTION", "0x1231 发送异常：${it.message}", retryable = false)
        }
        if (!pre.ok || 0x8231 !in pre.responseOpcodes) {
            return ProtocolResult.Ok(
                StepResult(
                    success = false,
                    message = "真实治疗预估未收到0x8231确认",
                    raw = mapOf(
                        "generalId" to generalId.toString(),
                        "fiefId" to fiefId.toString(),
                        "prePayloadHex" to prePayload.toHex(),
                        "preHttp" to pre.httpCode.toString(),
                        "preResponseHex" to pre.responseHex.take(512)
                    )
                )
            )
        }
        val preReceipt = runCatching {
            GeneralProtocolShapes.parseHealPreInfoResponse(
                pre.requirePayloadBytesFor(0x8231),
                expectedFiefId = fiefId,
                expectedSoldierType = -1
            )
        }.getOrElse {
            return ProtocolResult.Err(
                "REAL_HEAL_PREINFO_INVALID",
                "0x8231 治疗预估解析失败：${it.message}",
                false
            )
        }
        val healPayload = GeneralProtocolShapes.buildHealAllPayload(fiefId)
        val heal = runCatching {
            sendBinaryMappedGameHex(gameHttp, dm, buildDirectGameHex(0x1230, healPayload), phase = "heal/1230")
        }.getOrElse {
            actionAudit?.invoke("真实治疗 0x1230 异常：general=$generalId ${it.message}")
            return ProtocolResult.Err("REAL_HEAL_EXCEPTION", "0x1230 发送异常：${it.message}", retryable = false)
        }
        if (!heal.ok || 0x8230 !in heal.responseOpcodes) {
            return ProtocolResult.Ok(
                StepResult(
                    false,
                    "真实治疗未收到0x8230确认",
                    mapOf("generalId" to generalId.toString(), "fiefId" to fiefId.toString())
                )
            )
        }
        val parsed = runCatching {
            GeneralProtocolShapes.parseHealResponse(heal.requirePayloadBytesFor(0x8230))
        }.getOrElse {
            return ProtocolResult.Err(
                "REAL_HEAL_RECEIPT_INVALID",
                "0x8230 治疗回执解析失败：${it.message}",
                false
            )
        }
        actionAudit?.invoke("真实治疗 0x1230 返回：general=$generalId fief=$fiefId success=${parsed.success} msg=${parsed.message} http=${heal.httpCode}")
        if (parsed.success) invalidateLiveState(session)
        return ProtocolResult.Ok(
            StepResult(
                success = parsed.success,
                message = parsed.message,
                raw = mapOf(
                    "generalId" to generalId.toString(),
                    "fiefId" to fiefId.toString(),
                    "prePayloadHex" to prePayload.toHex(),
                    "healPayloadHex" to healPayload.toHex(),
                    "preHttp" to pre.httpCode.toString(),
                    "healHttp" to heal.httpCode.toString(),
                    "copperCost" to preReceipt.copperCost.toString(),
                    "goldCost" to preReceipt.goldCost.toString(),
                    "status" to parsed.status.toString(),
                    "preResponseHex" to pre.responseHex.take(512),
                    "healResponseHex" to heal.responseHex.take(512)
                )
            )
        )
    }

    private fun GameSession.brushYellowActionGateOrError(): ProtocolResult<StepResult>? {
        val networkAllowed = channelExtra["realActionNetworkAllowed"].asLooseBoolean() == true
        val sendReady = channelExtra["realActionSendReady"].asLooseBoolean() == true
        if (!networkAllowed && !sendReady) return null
        if (!networkAllowed || !sendReady) {
            return ProtocolResult.Err(
                "REAL_ACTION_GATE_NOT_READY",
                "真实动作 gate 未同时开启：realActionNetworkAllowed=$networkAllowed realActionSendReady=$sendReady",
                retryable = false
            )
        }
        val brushYellowScopeConfirmed =
            hasRealActionScope("brush-yellow") ||
                channelExtra["realActionBrushYellowOnly"].asLooseBoolean() == true
        if (!brushYellowScopeConfirmed) {
            return ProtocolResult.Err(
                "REAL_ACTION_SCOPE_NOT_CONFIRMED",
                "真实动作 gate 已开启，但缺少 realActionScope=brush-yellow 或 realActionBrushYellowOnly=true",
                retryable = false
            )
        }
        return ProtocolResult.Ok(StepResult(true, "brush-yellow action gate ready"))
    }

    private fun buildAssignTroopsPayload(generalId: Long, soldierTypeCode: Int, count: Int, group: Int): ByteArray {
        val bos = ByteArrayOutputStream()
        val dos = DataOutputStream(bos)
        dos.writeLong(generalId)
        dos.writeByte(group)
        dos.writeShort(soldierTypeCode)
        dos.writeInt(count)
        return bos.toByteArray()
    }

    private fun buildRefillPayload(generalIds: List<Long>): ByteArray {
        val bos = ByteArrayOutputStream()
        val dos = DataOutputStream(bos)
        dos.writeByte(generalIds.size)
        generalIds.forEach { dos.writeLong(it) }
        return bos.toByteArray()
    }

    private fun buildHealPreInfoPayload(fiefId: Long, soldierType: Int, count: Int): ByteArray {
        val bos = ByteArrayOutputStream()
        val dos = DataOutputStream(bos)
        dos.writeLong(fiefId)
        dos.writeShort(soldierType)
        dos.writeInt(count)
        return bos.toByteArray()
    }

    private fun buildHealPayload(fiefId: Long, group: Int, soldierType: Int, count: Int, useGold: Boolean): ByteArray {
        val bos = ByteArrayOutputStream()
        val dos = DataOutputStream(bos)
        dos.writeLong(fiefId)
        dos.writeByte(group)
        dos.writeShort(soldierType)
        dos.writeInt(count)
        dos.writeByte(if (useGold) 1 else 0)
        return bos.toByteArray()
    }

    private fun buildDirectGameHex(opcode: Int, payload: ByteArray): String =
        "000000000000000000" +
            payload.size.toString(16).padStart(2, '0') +
            opcode.toString(16).padStart(4, '0') +
            payload.toHex()

    private fun soldierTypeCode(name: String): Int = when (name.trim()) {
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

    private fun parseHealPreInfoPayload(hex: String): Boolean {
        val bytes = runCatching { hex.filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }.hexToBytesLocal() }.getOrNull()
            ?: return false
        return bytes.size >= 26
    }

    private fun parseHealPayload(hex: String): Pair<Boolean, String> {
        val bytes = runCatching { hex.filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }.hexToBytesLocal() }.getOrNull()
            ?: return false to "0x8230 响应 hex 无效"
        if (bytes.size < 18) return false to "0x8230 响应过短"
        val status = bytes[0].toInt()
        val message = when (status) {
            0 -> "治疗成功"
            -1 -> "铜钱不足"
            -2 -> "治疗失败"
            -3 -> "黄金不足"
            else -> "未知治疗状态 $status"
        }
        return (status == 0) to message
    }

    private fun MapTarget.actionTargetHex(): String {
        val rawRecord = raw["rawRecord"]?.filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }?.lowercase()
        if (raw["source"] == "8540-structured" && !rawRecord.isNullOrBlank() && rawRecord.length >= 16) {
            // Desktop canonical rule: a structured 0x8540 record begins with the exact
            // 8-byte target id. Including the following UTF-name length creates a different
            // long and can make 0x8522 return ff0000.
            return rawRecord.take(16)
        }
        if (!rawRecord.isNullOrBlank() && rawRecord.length >= 18) {
            // Live calibration 2026-07-07: 041540 record candidate succeeded when using
            // the first 18 hex chars and taking the trailing 16 chars as expedition target id.
            return rawRecord.take(18).takeLast(16)
        }
        return (
            raw["targetIdHex"]
                ?: raw["idHex"]
                ?: raw["targetHex"]
                ?: id.toString(16)
            )
            .removePrefix("0x")
            .removePrefix("0X")
            .padStart(16, '0')
            .lowercase()
    }

    private fun GameSession.generalChunksForFormation(formationId: Long): List<String> {
        val formations = runCatching {
            val raw = channelExtra["formationsJson"]
            if (!raw.isNullOrBlank()) {
                parseFormations(raw)
            } else {
                val generals = queryGeneralListForFormationStatus(this)
                (parseRecoveredShuaHuangFormations(recoveredPreferenceMap(), generals) +
                    recoveredGeneralFallbackFormations(generals))
                    .dedupeByFormationId()
            }
        }.getOrDefault(emptyList())
        val formation = formations.firstOrNull { it.id == formationId }
            ?: if (channelExtra["allowRecoveredGeneralFallbackFormation"].asLooseBoolean() == true && formationId > 0L) {
                // SavedConfigTaskPlanFactory can use a real general id as a temporary
                // one-general "formation id" until the original shuahuangChuzhengBiandui
                // SharedPreferences are recovered on-device.  The wire payload wants
                // 8-byte general-id chunks, so this fallback is equivalent to a single
                // recovered fallback formation.
                return listOf(formationId.toString(16).padStart(16, '0'))
            } else {
                return emptyList()
            }
        return formation.generalIds
            .filter { it > 0L }
            .map { it.toString(16).padStart(16, '0') }
    }

    private fun sendBinaryMappedGameHex(
        gameHttp: String,
        dm: Long,
        gameHex: String,
        phase: String
    ): DirectBinaryResponse {
        requireExecutionAllowed(phase)
        directBinaryTransport?.let { return it(gameHttp, dm, gameHex, phase) }
        val normalized = gameHex.filterNot { it.isWhitespace() }.lowercase()
        require(normalized.startsWith("000000000000000000")) { "unsupported gameHex prefix for $phase" }
        val body = normalized.drop(18)
        require(body.length >= 6) { "gameHex too short for $phase" }
        val opcode = body.substring(2, 6).toInt(16)
        val payload = body.drop(6).hexToBytesLocal()
        val requestBody = makeBinaryGamePacket(dm, opcode, payload)
        val purpose = GameOpcodePurpose.of(opcode)
        val conn = (URL(gameHttp).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 25_000
            requestMethod = "POST"
            doOutput = true
            setRequestProperty("Content-Type", "application/octet-stream")
            setRequestProperty("User-Agent", "DWPMClone/1.0 direct-binary-action")
            setFixedLengthStreamingMode(requestBody.size)
        }
        return try {
            conn.outputStream.use { it.write(requestBody) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val bytes = stream?.use { it.readBytes() } ?: ByteArray(0)
            val packets = runCatching { parseBinaryGameResponse(bytes) }.getOrDefault(emptyList())
            val responsePayload = packets.joinToString(separator = "") { it.payload.toHex() }
            val responseText = packets.joinToString(separator = " ") { it.payload.toPrintableTextPreview() }
            DirectBinaryResponse(
                phase = phase,
                httpCode = code,
                ok = code in 200..299,
                responseBytes = bytes.size,
                responseHex = responsePayload.ifBlank { bytes.toHex() },
                textPreview = responseText.ifBlank { bytes.toPrintableTextPreview() },
                responseOpcodes = packets.map { it.opcode },
                responsePayloads = packets.map { DirectBinaryPayload(it.opcode, it.payload.toHex()) }
            ).also { GameRequestHealthSink.record(it.ok, purpose) }
        } catch (error: Throwable) {
            GameRequestHealthSink.record(false, purpose)
            throw error
        } finally {
            conn.disconnect()
        }
    }

    /**
     * A foreground stop cannot interrupt bytes already handed to the socket, but it must prevent
     * every later request in the same scheduler batch. The check intentionally sits immediately
     * before each network implementation or injected transport.
     */
    private fun requireExecutionAllowed(phase: String) {
        if (executionAllowed()) return
        actionAudit?.invoke("后台执行权已撤销，已阻止请求：$phase")
        throw ExecutionRevokedBeforeNetworkException(phase)
    }

    private fun makeBinaryGamePacket(dm: Long, opcode: Int, payload: ByteArray): ByteArray {
        val bos = ByteArrayOutputStream()
        val dos = DataOutputStream(bos)
        dos.writeUtfBytesCompat("1660606`7054`0000480502")
        dos.writeLong(System.currentTimeMillis())
        dos.writeByte(1)
        dos.writeLong(dm)
        dos.writeLong(0L)
        dos.writeShort(payload.size)
        dos.writeShort(opcode)
        dos.writeUtfBytesCompat("")
        dos.write(payload)
        return bos.toByteArray()
    }

    private fun DataOutputStream.writeUtfBytesCompat(value: String) {
        val bytes = value.toByteArray(Charsets.UTF_8)
        writeShort(bytes.size)
        write(bytes)
    }

    private data class BinaryGamePacket(val opcode: Int, val payload: ByteArray)

    private fun parseBinaryGameResponse(data: ByteArray): List<BinaryGamePacket> {
        var p = 0
        fun u8(): Int = data[p++].toInt() and 0xff
        fun i64(): Long {
            var v = 0L
            repeat(8) { v = (v shl 8) or (data[p++].toLong() and 0xffL) }
            return v
        }
        fun i32(): Int {
            val v = ((data[p].toInt() and 0xff) shl 24) or
                ((data[p + 1].toInt() and 0xff) shl 16) or
                ((data[p + 2].toInt() and 0xff) shl 8) or
                (data[p + 3].toInt() and 0xff)
            p += 4
            return v
        }
        fun u16(): Int {
            val v = ((data[p].toInt() and 0xff) shl 8) or (data[p + 1].toInt() and 0xff)
            p += 2
            return v
        }
        fun bytes(len: Int): ByteArray {
            val out = data.copyOfRange(p, p + len)
            p += len
            return out
        }
        val packets = mutableListOf<BinaryGamePacket>()
        repeat(u8()) {
            repeat(u8()) {
                i64()
                i64()
                u8()
                val len = i32()
                val opcode = u16()
                u8()
                packets += BinaryGamePacket(opcode, bytes(len))
            }
        }
        return packets
    }

    private fun sendNativeWrappedGameHex(
        gameHttp: String,
        fields: RecoveredNativeWrapperFields,
        gameHex: String,
        phase: String
    ): DirectBinaryResponse {
        requireExecutionAllowed(phase)
        val body = fields.lx!! + fields.key!! + gameHex + fields.lb!!
        val bodyBytes = body.toByteArray(Charsets.UTF_8)
        val conn = (URL(gameHttp).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 25_000
            requestMethod = "POST"
            doOutput = true
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            setRequestProperty("Accept", "*/*")
            setRequestProperty("User-Agent", "DWPMClone/1.0 native-wrapper")
            setFixedLengthStreamingMode(bodyBytes.size)
        }
        conn.outputStream.use { it.write(bodyBytes) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val bytes = stream?.use { it.readBytes() } ?: ByteArray(0)
        return DirectBinaryResponse(
            phase = phase,
            httpCode = code,
            ok = code in 200..299,
            responseBytes = bytes.size,
            responseHex = bytes.toHex(),
            textPreview = bytes.toPrintableTextPreview()
        )
    }

    private fun GameSession.recoveredReadOnlyRequests(
        kind: RecoveredSearchKind,
        start: MapCoordinate
    ): List<RecoveredSearchRequest> {
        val contract = behaviorContract.mapSearch
        val mode = channelExtra["recoveredReadOnlyScanMode"]?.uppercase().orEmpty()
        val threadCount = channelExtra["recoveredReadOnlyThreadCount"]?.toIntOrNull()?.coerceAtLeast(1) ?: 1
        val limit = channelExtra["recoveredReadOnlyScanLimit"]?.toIntOrNull()?.coerceAtLeast(1)
        val requests = when (mode) {
            "SINGLE", "EXACT" -> listOf(RecoveredMapScanPlanner.singleRequest(kind, start, contract))
            "FULL", "FULL_SCAN" -> RecoveredMapScanPlanner
                .fullScanRequestsDeduped(kind, threadCount, contract)
                .take(contract.fullRequestLimit)
            else -> RecoveredMapScanPlanner.nearbyRequests(
                kind,
                start,
                contract.nearbyRequestLimit,
                contract
            )
        }
        return limit?.let { requests.take(it) } ?: requests
    }

    private fun GameSession.recoveredMineReadOnlyRequests(
        config: MineConfig
    ): List<RecoveredSearchRequest> {
        val requests = RecoveredMapScanPlanner.mineScopeRequests(
            RecoveredSearchKind.RESOURCE_POINT_041542,
            config.start,
            config.searchScope,
            behaviorContract.mapSearch
        )
        val explicitLimit = channelExtra["recoveredReadOnlyScanLimit"]
            ?.toIntOrNull()
            ?.coerceAtLeast(1)
        return explicitLimit?.let(requests::take) ?: requests
    }




    internal fun parseOccupyMineResult(raw: String, mine: MineSearchResult, formationId: Long, session: GameSession? = null): ProtocolResult<StepResult> {
        val arr = JSONArray(raw)
        for (index in 0 until arr.length()) {
            val obj = arr.getJSONObject(index)
            val candidateMineId = obj.longAlias("mineId", "resourceId", "id")
            val candidateFormationId = obj.longAlias("formationId", "bianduihao")
            if (candidateMineId == mine.id && candidateFormationId == formationId) {
                val success = obj.optBoolean("success", false)
                val message = obj.stringAlias("message", "msg") ?: if (success) "占矿/资源点出征成功" else "占矿/资源点出征失败"
                val nestedRaw = obj.optJSONObject("raw")?.toStringMap() ?: emptyMap()
                val topLevelRaw = obj.toStringMap().filterKeys { it != "raw" }
                return ProtocolResult.Ok(StepResult(success, message, nestedRaw + topLevelRaw + obj.buildResourcePointExpeditionPayloadRaw(mine, session)))
            }
        }
        return ProtocolResult.Err(
            "REAL_OCCUPY_MINE_METADATA_NOT_FOUND",
            "occupyMineResultsJson 未找到 mineId=${mine.id} formationId=$formationId 的动作结果",
            retryable = false
        )
    }

    internal fun parseWithdrawMineResult(raw: String, mineId: Long): ProtocolResult<StepResult> {
        val arr = JSONArray(raw)
        for (index in 0 until arr.length()) {
            val obj = arr.getJSONObject(index)
            val candidateMineId = obj.longAlias("mineId", "resourceId", "id")
            if (candidateMineId == mineId) {
                val success = obj.optBoolean("success", false)
                val message = obj.stringAlias("message", "msg") ?: if (success) "撤回驻防完成" else "撤回驻防失败"
                val nestedRaw = obj.optJSONObject("raw")?.toStringMap() ?: emptyMap()
                val topLevelRaw = obj.toStringMap().filterKeys { it != "raw" }
                val defenseRecordId = obj.stringAlias("defenseRecordIdHex", "defenseRecordId", "generalIdHex")
                val payloadRaw = defenseRecordId?.takeIf { it.isNotBlank() }?.let {
                    mapOf(
                        "withdrawPayload" to RemainingAutomationProtocolShapes.withdrawDefenseShape(it),
                        "payloadEvidence" to "withdraw defense: 0a15260101 + defenseRecordId"
                    )
                } ?: emptyMap()
                return ProtocolResult.Ok(StepResult(success, message, nestedRaw + topLevelRaw + payloadRaw))
            }
        }
        return ProtocolResult.Err(
            "REAL_WITHDRAW_MINE_METADATA_NOT_FOUND",
            "withdrawMineResultsJson 未找到 mineId=$mineId 的撤防结果",
            retryable = false
        )
    }

    internal fun parseDailyStepResult(
        raw: String,
        step: DailyStep,
        donationFactorFz: Int = 1,
        session: GameSession? = null
    ): ProtocolResult<StepResult> {
        val arr = JSONArray(raw)
        val shape = DailyProtocolShapes.shapeFor(step, donationFactorFz)
        for (index in 0 until arr.length()) {
            val obj = arr.getJSONObject(index)
            val candidateStep = obj.optString("step").ifBlank { obj.optString("dailyStep") }
            if (candidateStep.equals(step.name, ignoreCase = true)) {
                val success = obj.optBoolean("success", false)
                val message = obj.optString("message").ifBlank { if (success) shape.successLog else "daily step failed: ${step.name}" }
                val nestedRaw = obj.optJSONObject("raw")?.toStringMap() ?: emptyMap()
                val topLevelRaw = obj.toStringMap().filterKeys { it != "raw" }
                val shapeRaw = mapOf(
                    "payloads" to shape.payloads.joinToString(separator = ","),
                    "successLog" to shape.successLog,
                    "evidence" to shape.evidence,
                    "delayAfterMillis" to shape.delayAfterMillis.toString()
                ) + obj.buildDailyNativeWrapperRaw(shape.payloads, session)
                return ProtocolResult.Ok(StepResult(success = success, message = message, raw = nestedRaw + topLevelRaw + shapeRaw))
            }
        }
        return ProtocolResult.Err(
            "REAL_DAILY_METADATA_NOT_FOUND",
            "dailyStepResultsJson 未找到 step=${step.name} 的一键日常结果",
            retryable = false
        )
    }

    private suspend fun recoveredConvertFoodToCopper(session: GameSession, mode: ConvertMode): ProtocolResult<ResourceState> {
        if (!offlineActionFixturesAllowed) {
            return unrecovered(
                "REAL_CONVERT_LIVE_UNAVAILABLE",
                "真实资源转换条件不完整；生产路径禁止使用离线转换回执"
            )
        }
        val raw = session.channelExtra["dailyStepResultsJson"]
            ?: return unrecovered("REAL_CONVERT_NOT_IMPLEMENTED", "真实资源转换协议尚未接入")
        val donationFactorFz = session.channelExtra["dailyDonationFactorFz"]?.toIntOrNull() ?: 1
        val step = when (mode) {
            ConvertMode.FOOD_TO_COPPER_HALF -> DailyStep.CONVERT_HALF_FOOD_TO_COPPER
            ConvertMode.FOOD_TO_COPPER_THRESHOLD -> DailyStep.CONVERT_HALF_FOOD_TO_COPPER
        }
        val result = when (val parsed = parseDailyStepResult(raw, step, donationFactorFz, session)) {
            is ProtocolResult.Ok -> parsed.value
            is ProtocolResult.Err -> return ProtocolResult.Err(parsed.code, parsed.message, retryable = false)
        }
        if (!result.success) {
            return ProtocolResult.Err("REAL_CONVERT_FAILED", result.message, retryable = false)
        }
        parseConvertedResourceState(session, result.raw)?.let { return ProtocolResult.Ok(it) }
        return when (val state = queryResourceState(session)) {
            is ProtocolResult.Ok -> ProtocolResult.Ok(
                state.value.copy(
                    raw = state.value.raw + result.raw + mapOf(
                        "convertMode" to mode.name,
                        "convertEvidence" to "dailyStepResultsJson:${step.name}",
                        "networkSendAllowed" to "false"
                    )
                )
            )
            is ProtocolResult.Err -> ProtocolResult.Err(state.code, state.message, state.retryable)
        }
    }

    private fun JSONObject.buildDailyNativeWrapperRaw(payloads: List<String>, session: GameSession? = null): Map<String, String> {
        if (payloads.isEmpty()) {
            return mapOf(
                "dailyPayloadCount" to "0",
                "dailyWrapperNetworkAllowed" to "false",
                "dailyWrapperEvidence" to "no gameHex payload for delegated/non-request daily step"
            )
        }
        val rawObject = optJSONObject("raw")
        val wrapperFields = RecoveredNativeWrapperFieldExtractor.from((session?.channelExtra ?: emptyMap()) + toStringMap() + (rawObject?.toStringMap() ?: emptyMap()))
        val plans = payloads.map { payload -> RecoveredNativeActionWrapperPlanner.plan(payload, wrapperFields) }
        return mapOf(
            "nativeWrapperShape" to plans.first().bodyShape,
            "dailyPayloadCount" to payloads.size.toString(),
            "dailyWrapperNetworkAllowed" to plans.all { it.networkSendAllowed }.toString(),
            "dailyWrapperMissingFields" to plans.flatMap { it.missingNativeFields }.distinct().joinToString(","),
            "dailyWrapperPayloadCategories" to plans.map { it.descriptor.category.name }.distinct().joinToString(","),
            "dailyWrapperMaskedCandidateFirst" to (plans.first().maskedRawConcatCandidate ?: ""),
            "dailyWrapperBlocker" to plans.first().blocker,
            "dailyWrapperEvidence" to "daily gameHex payloads use lx + key + gameHex + lb dry-run only"
        )
    }

    private fun parseConvertedResourceState(session: GameSession, raw: Map<String, String>): ResourceState? {
        val obj = session.extraJsonObject(
            "convertedResourceStateJson",
            "resourceStateAfterConvertJson",
            "resourceAfterConvertJson"
        )
        val copper = obj?.longAlias("copper", "convertedCopper", "money")
            ?: session.channelExtra["convertedCopper"]?.parseLongFlexible()
            ?: raw["convertedCopper"]?.parseLongFlexible()
            ?: return null
        val food = obj?.longAlias("food", "convertedFood")
            ?: session.channelExtra["convertedFood"]?.parseLongFlexible()
            ?: raw["convertedFood"]?.parseLongFlexible()
            ?: session.channelExtra["food"]?.parseLongFlexible()
            ?: 0L
        return ResourceState(
            copper = copper,
            food = food,
            prestige = obj?.longAlias("prestige"),
            copperPerHour = obj?.intAlias("copperPerHour", "moneyPerHour"),
            foodPerHour = obj?.intAlias("foodPerHour"),
            populationCurrent = obj?.longAlias("populationCurrent", "population", "renkou"),
            populationCap = obj?.longAlias("populationCap", "populationLimit"),
            resourcePointCurrent = obj?.intAlias("resourcePointCurrent", "resourcePoint", "resourcePointUsed"),
            resourcePointCap = obj?.intAlias("resourcePointCap", "resourcePointLimit"),
            raw = ((obj?.toStringMap() ?: emptyMap()) + raw + mapOf("networkSendAllowed" to "false", "convertEvidence" to "converted-resource-state-metadata"))
        )
    }

    internal fun parseDispatchResult(raw: String, formationId: Long, target: MapTarget, session: GameSession? = null): ProtocolResult<BattleResult> {
        val arr = JSONArray(raw)
        for (index in 0 until arr.length()) {
            val obj = arr.getJSONObject(index)
            val rawObject = obj.optJSONObject("raw")
            val candidateFormationId = obj.longAlias(
                "formationId",
                "formationID",
                "formation",
                "formationNo",
                "formationIdHex",
                "bianduihao",
                "biandui"
            ) ?: rawObject?.longAlias(
                "formationId",
                "formationID",
                "formation",
                "formationNo",
                "formationIdHex",
                "bianduihao",
                "biandui"
            )
            val candidateTargetId = obj.longAlias(
                "targetId",
                "targetID",
                "id",
                "target",
                "targetPointId",
                "enemyId",
                "targetIdHex",
                "idHex"
            ) ?: rawObject?.longAlias(
                "targetId",
                "targetID",
                "id",
                "target",
                "targetPointId",
                "enemyId",
                "targetIdHex",
                "idHex"
            )
            if (candidateFormationId == formationId && candidateTargetId == target.id) {
                val nestedRaw = rawObject?.toStringMap() ?: emptyMap()
                val response = BrushYellowDispatchResponseParser.parse(
                    responseText = obj.stringAlias(
                        "responseText",
                        "response",
                        "rawResponse",
                        "bodyText",
                        "body",
                        "responseBody",
                        "resultText",
                        "rawText",
                        "dispatchResponse"
                    ) ?: rawObject?.stringAlias(
                        "responseText",
                        "response",
                        "rawResponse",
                        "bodyText",
                        "body",
                        "responseBody",
                        "resultText",
                        "rawText",
                        "dispatchResponse"
                    ),
                    responseHex = obj.stringAlias("responseHex", "rawResponseHex", "bodyHex", "responseBodyHex", "rawHex")
                        ?: rawObject?.stringAlias("responseHex", "rawResponseHex", "bodyHex", "responseBodyHex", "rawHex")
                )
                val responseSuccess = response?.isSuccessForCurrentTarget(
                    target,
                    behaviorContract.expedition.dispatchSuccessRequiresPositiveBattleId
                )
                val success = responseSuccess
                    ?: obj.successAlias("success", "ok", "dispatchSuccess", "result", "status", "state")
                    ?: rawObject?.successAlias("success", "ok", "dispatchSuccess", "result", "status", "state")
                    ?: false
                val consumedTimes = obj.intAlias("consumedTimes", "times", "usedAount", "usedAmount", "usedCount", "count")
                    ?: rawObject?.intAlias("consumedTimes", "times", "usedAount", "usedAmount", "usedCount", "count")
                    ?: response?.usedAount
                    ?: if (success) 1 else 0
                val topLevelRaw = obj.toStringMap().filterKeys { it != "raw" }
                val responseRaw = response?.toRawMap().orEmpty()
                val payloadRaw = obj.buildBrushYellowPayloadRaw(target, session)
                val contextualRaw = if (response?.success == true && responseSuccess == false) {
                    mapOf("message" to "响应中出现战报成功文本，但未匹配本次目标坐标/ID，已按非本次成功处理")
                } else {
                    emptyMap()
                }
                return ProtocolResult.Ok(
                    BattleResult(
                        success = success,
                        consumedTimes = consumedTimes,
                        raw = nestedRaw + topLevelRaw + responseRaw + contextualRaw + payloadRaw
                    )
                )
            }
        }
        return ProtocolResult.Err(
            "REAL_DISPATCH_METADATA_NOT_FOUND",
            "dispatchResultsJson 未找到 formationId=$formationId targetId=${target.id} 的刷黄出征结果",
            retryable = false
        )
    }

    internal fun parseGenerals(raw: String): List<General> {
        val arr = JSONArray(raw)
        return (0 until arr.length()).map { index ->
            parseGeneralObject(arr.getJSONObject(index))
        }
    }

    internal fun parseGeneralsFlexible(raw: String): List<General> {
        val text = raw.trim()
        if (text.isBlank()) return emptyList()
        if (text.startsWith("[")) return parseGenerals(text)
        if (text.startsWith("{")) return listOf(parseGeneralObject(JSONObject(text)))

        val recoveredRecords = State8004GeneralEvidenceParser.recoverRecords(text)
        if (recoveredRecords.isNotEmpty()) {
            return recoveredRecords.map { parseGeneralObject(JSONObject(it)) }
        }

        return splitRecoveredRecords(text)
            .mapNotNull { record ->
                val map = parseRecoveredKeyValueRecord(record)
                if (map.isEmpty()) null else parseGeneralObject(JSONObject(map))
            }
    }

    private fun parseGeneralObject(obj: JSONObject): General {
        val rawMap = obj.toStringMap()
        val rawSource = rawMap["source"]
        val parsedEnergy = obj.intAlias("energy", "tili")
        val energy = if (rawSource == "state8004-binary-name-candidate" && parsedEnergy == 0) {
            // In the conservative binary-name candidate shape, the byte after
            // status is not yet proven to be tili.  Treat 0 as unknown instead
            // of exhausting the general and blocking explicit fallback
            // formations; non-zero calibration evidence is still preserved.
            null
        } else {
            parsedEnergy
        }
        return General(
            id = obj.longAlias("id", "generalId", "jiangLingId") ?: 0L,
            name = obj.stringAlias("name", "generalName", "jiangLingName").orEmpty(),
            growth = obj.intAlias("growth", "chengzhang"),
            loyalty = obj.intAlias("loyalty", "zhongcheng", "zhongChengdu"),
            energy = energy,
            rank = obj.intAlias("rank", "level"),
            kind = obj.stringAlias("kind", "type", "category"),
            status = obj.intAlias("status"),
            placeId = obj.longAlias("placeId", "placeID", "fiefId"),
            attack = obj.intAlias("attack", "gongji"),
            defense = obj.intAlias("defense", "fangyu"),
            strength = obj.intAlias("strength", "wuli"),
            intelligence = obj.intAlias("intelligence", "zhili"),
            command = obj.intAlias("command", "tongshuai"),
            energyLimit = obj.intAlias("energyLimit", "tiliLimit"),
            troopLimit = obj.intAlias("troopLimit", "daiBingLimit", "maxTroopCount", "maxSoldierCount"),
            exp = obj.longAlias("exp", "jingyan"),
            expLimit = obj.longAlias("expLimit", "jingyanLimit"),
            isFulu = obj.boolAlias("isFulu", "fulu"),
            isPeiBingFail = obj.boolAlias("isPeiBingFail", "peiBingFail"),
            raw = rawMap + mapOf("source" to (rawSource ?: "recovered-jiangling"))
        )
    }

    internal fun parseFormations(raw: String): List<FormationRuntime> {
        val arr = JSONArray(raw)
        return (0 until arr.length()).map { index ->
            val obj = arr.getJSONObject(index)
            val status = parseFormationStatus(obj)
            FormationRuntime(
                id = obj.longAlias("id", "formationId", "bianduihao") ?: 0L,
                name = obj.stringAlias("name", "formationName", "bianduiName")?.ifBlank { null },
                generalIds = obj.optJSONArray("generalIds")?.let { ids ->
                    (0 until ids.length()).mapNotNull { ids.optString(it).parseLongFlexible() }.filter { it > 0L }
                } ?: emptyList(),
                status = status,
                troopCount = obj.intAlias("troopCount", "soldierCount", "bingli"),
                raw = (obj.optJSONObject("raw")?.toStringMap() ?: emptyMap()) + obj.toStringMap()
            )
        }
    }

    internal fun parseRecoveredShuaHuangFormations(
        prefs: Map<String, String>,
        generals: List<General> = emptyList()
    ): List<FormationRuntime> {
        if (prefs.isEmpty()) return emptyList()
        val generalById = generals.associateBy { it.id }
        val selected = selectedRecoveredFormationSlots(prefs)
        return selected.mapNotNull { slot ->
            val rawSlot = slot.toString()
            val id = prefs.firstValue(
                "bianduihao$rawSlot",
                "bianduihao_$rawSlot",
                "bianduihao.$rawSlot",
                "bianduihao[$rawSlot]",
                "formationId$rawSlot",
                "formationId_$rawSlot"
            )?.parseLongFlexible()
                ?: slot.toLong()

            val generalIds = prefs.firstValue(
                "bianduiDejiangling$rawSlot",
                "bianduiDejiangling_$rawSlot",
                "bianduiDejiangling.$rawSlot",
                "bianduiDejiangling[$rawSlot]",
                "formationGeneralIds$rawSlot",
                "formationGeneralIds_$rawSlot"
            )?.parseFlexibleLongList()
                ?: prefs.firstValue(
                    "bianduiDejiangling${id}",
                    "bianduiDejiangling_$id",
                    "formationGeneralIds${id}",
                    "formationGeneralIds_$id"
                )?.parseFlexibleLongList()
                ?: emptyList()

            val statusText = prefs.firstValue(
                "bianduiStatus$rawSlot",
                "bianduiStatus_$rawSlot",
                "formationStatus$rawSlot",
                "formationStatus_$rawSlot"
            )
            val status = statusText?.let { parseFormationStatus(JSONObject(mapOf("status" to it))) }
                ?: inferFormationStatusFromGenerals(generalIds, generalById)
            val peiBingFail = generalIds.any { generalById[it]?.isPeiBingFail == true }
            FormationRuntime(
                id = id,
                name = prefs.firstValue("bianduiName$rawSlot", "bianduiName_$rawSlot", "formationName$rawSlot")
                    ?: "刷黄编队$id",
                generalIds = generalIds,
                status = if (peiBingFail) FormationRuntimeStatus.BUSY else status,
                troopCount = prefs.firstValue("bingli$rawSlot", "troopCount$rawSlot", "soldierCount$rawSlot")?.toIntOrNull(),
                raw = mapOf(
                    "source" to "recovered-shuahuang-shared-prefs",
                    "slot" to rawSlot,
                    "shuahuangChuzhengBiandui" to (prefs.firstValue("shuahuangChuzhengBiandui$rawSlot", "shuahuangChuzhengBiandui_$rawSlot") ?: "true"),
                    "bianduihao" to id.toString(),
                    "bianduiDejiangling" to generalIds.joinToString(","),
                    "isPeiBingFail" to peiBingFail.toString()
                )
            )
        }
    }

    private fun GameSession.recoveredGeneralFallbackFormations(generals: List<General>): List<FormationRuntime> {
        if (channelExtra["allowRecoveredGeneralFallbackFormation"].asLooseBoolean() != true &&
            channelExtra["unifiedExpeditionPreflight"].asLooseBoolean() != true
        ) return emptyList()
        val selectedGeneralIds = selectedRecoveredGeneralFallbackIds()
        return generals
            .asSequence()
            .filter { it.id > 0L }
            // If the UI saved a real general id as selectedFormationIds/shuaHuangSelectedFormationIds,
            // make sure queryFormations exposes that exact id as a one-general formation even when
            // recovered shuahuangChuzhengBiandui prefs already produced unrelated slot ids.  This is
            // the bridge used by the phone UI's "保存设置" flow: selected id == general id.
            .filter { selectedGeneralIds.isEmpty() || it.id in selectedGeneralIds }
            .filter { it.status == null || it.status == 0 }
            .filter { it.energy == null || it.energy > 0 }
            .filter { it.isPeiBingFail != true }
            .map { general ->
                FormationRuntime(
                    id = general.id,
                    name = "候选刷黄编队-${general.name.ifBlank { general.id.toString() }}",
                    generalIds = listOf(general.id),
                    status = FormationRuntimeStatus.IDLE,
                    troopCount = general.currentAssignedTroops()?.count,
                    raw = mapOf(
                        "source" to "recovered-state8004-general-fallback",
                        "generalId" to general.id.toString(),
                        "generalName" to general.name,
                        "requiresExplicitFlag" to "allowRecoveredGeneralFallbackFormation"
                    )
                )
            }
            .toList()
    }

    private fun List<FormationRuntime>.dedupeByFormationId(): List<FormationRuntime> {
        val seen = linkedSetOf<Long>()
        return filter { formation ->
            // Preserve parsed SharedPreferences formations first; append fallback only for ids
            // that were not already present.
            formation.id > 0L && seen.add(formation.id)
        }
    }

    private fun GameSession.selectedRecoveredGeneralFallbackIds(): Set<Long> =
        listOf("shuaHuangSelectedFormationIds", "selectedFormationIds")
            .flatMap { key -> channelExtra[key].parseFlexibleLongListLoose() }
            .filter { it > 0L }
            .toSet()


    internal fun parseMineSearchResults(raw: String): List<MineSearchResult> {
        val arr = JSONArray(raw)
        return (0 until arr.length()).mapNotNull { index ->
            val obj = arr.getJSONObject(index)
            val mineType = parseMineType(obj.stringAlias("mineType", "type", "kind", "fA")) ?: return@mapNotNull null
            val defenseCount = obj.intAlias("defenseCount", "defenders", "guardCount", "kC", "kD")
            val playerOccupied = obj.boolAlias(
                "playerOccupied",
                "occupied",
                "isPlayerOccupied"
            ) ?: false
            MineSearchResult(
                id = obj.longAlias("id", "mineId", "resourceId") ?: 0L,
                coordinate = MapCoordinate(
                    x = obj.intAlias("x", "kx", "kv", "kA") ?: 0,
                    y = obj.intAlias("y", "ky", "kw", "kB") ?: 0
                ),
                mineType = mineType,
                level = obj.intAlias("level", "rank", "fz"),
                reserve = obj.longAlias("reserve", "amount", "kz"),
                isEmpty = obj.boolAlias("isEmpty", "empty") ?: (defenseCount == 0),
                defenseCount = defenseCount,
                raw = obj.toStringMap(),
                playerOccupied = playerOccupied,
                ownerName = obj.stringAlias("ownerName", "playerName", "owner")
            )
        }
    }

    private fun List<MineSearchResult>.filterByMineConfig(config: MineConfig): List<MineSearchResult> =
        filter { MineTargetFilterPolicy.matches(it, config, behaviorContract.mine) }

    private fun parseMineType(raw: String?): MineType? {
        val value = raw?.trim().orEmpty()
        if (value.isBlank()) return null
        runCatching { return MineType.valueOf(value.uppercase()) }
        return when {
            value.contains("金") -> MineType.GOLD
            value.contains("银") -> MineType.SILVER
            value.contains("冰玉") -> MineType.BING_YU
            value.contains("仙芝") -> MineType.XIAN_ZHI
            value.contains("玄铁") || value.contains("玄鐵") -> MineType.XUAN_TIE
            value.contains("玉露") -> MineType.YU_LU
            value.contains("牧") && value.contains("1") -> MineType.PASTURE_LV1
            value.contains("牧") && value.contains("2") -> MineType.PASTURE_LV2
            value.contains("牧") && value.contains("3") -> MineType.PASTURE_LV3
            value.contains("水晶") || value.contains("晶") -> MineType.CRYSTAL
            value.contains("灵草") || value.contains("靈草") -> MineType.LING_CAO
            value.contains("镔铁") || value.contains("鑌鐵") || value.contains("宾铁") -> MineType.BIN_TIE
            value.contains("浆果") || value.contains("漿果") -> MineType.JIANG_GUO
            else -> null
        }
    }

    internal fun parseMapTargets(raw: String): List<MapTarget> {
        val arr = JSONArray(raw)
        return (0 until arr.length()).map { index ->
            val obj = arr.getJSONObject(index)
            val rawMap = obj.toStringMap()
            val type = obj.stringAlias("type", "kind", "targetType", "targetKind", "name").orEmpty()
            MapTarget(
                id = obj.longAlias("id", "targetId", "targetID", "idHex", "targetIdHex") ?: 0L,
                coordinate = MapCoordinate(
                    x = obj.intAlias("x", "kv", "coordX", "coordinateX", "kA") ?: 0,
                    y = obj.intAlias("y", "kw", "coordY", "coordinateY", "kB") ?: 0
                ),
                type = type,
                raw = rawMap
            )
        }
    }

    private fun List<MapTarget>.filterByPolicy(policy: MapSearchPolicy): List<MapTarget> {
        val expected = policy.targetType ?: return this
        val accepted = when (expected) {
            HuangTargetType.SHAN_ZEI -> setOf("SHAN_ZEI", "山贼", "山賊")
            HuangTargetType.HUANG_JIN -> setOf(
                "HUANG_JIN",
                "黄巾",
                "黃巾",
                "渠帅",
                "渠帥",
                "主将",
                "主將",
                "主帅",
                "主帥"
            )
        }
        return filter { target ->
            val candidates = listOf(
                target.type,
                target.raw["type"].orEmpty(),
                target.raw["targetType"].orEmpty(),
                target.raw["kind"].orEmpty(),
                target.raw["targetKind"].orEmpty(),
                target.raw["name"].orEmpty()
            )
            candidates.any { value -> accepted.any { it.equals(value, ignoreCase = true) || value.contains(it) } }
        }
    }



    private fun JSONObject.buildResourcePointExpeditionPayloadRaw(mine: MineSearchResult, session: GameSession? = null): Map<String, String> {
        val rawObject = optJSONObject("raw")
        val generalChunks = optJSONArray("generalIdHexChunks") ?: rawObject?.optJSONArray("generalIdHexChunks") ?: return emptyMap()
        val targetHex = stringAlias("resourcePointIdHex", "mineIdHex", "targetIdHex")
            ?: rawObject?.stringAlias("resourcePointIdHex", "mineIdHex", "targetIdHex")
            ?: mine.raw["resourcePointIdHex"]
            ?: mine.raw["idHex"]
            ?: return emptyMap()
        val chunks = (0 until generalChunks.length()).map { generalChunks.optString(it) }.filter { it.isNotBlank() }
        if (chunks.isEmpty()) return emptyMap()
        val firstPayload = RemainingAutomationProtocolShapes.resourceSendGeneralFirstStage(chunks, targetHex)
        val secondPayload = RemainingAutomationProtocolShapes.resourceSendGeneralSecondStage(chunks, targetHex)
        val wrapperFields = RecoveredNativeWrapperFieldExtractor.from((session?.channelExtra ?: emptyMap()) + toStringMap() + (rawObject?.toStringMap() ?: emptyMap()))
        val firstWrapperPlan = RecoveredNativeActionWrapperPlanner.plan(firstPayload, wrapperFields)
        val secondWrapperPlan = RecoveredNativeActionWrapperPlanner.plan(secondPayload, wrapperFields)
        return mapOf(
            "resourcePointFirstPayload" to firstPayload,
            "resourcePointSecondPayload" to secondPayload,
            "payloadEvidence" to "resource point p2=1: 1520010 + 1522010",
            "nativeWrapperShape" to firstWrapperPlan.bodyShape,
            "resourcePointFirstWrapperNetworkAllowed" to firstWrapperPlan.networkSendAllowed.toString(),
            "resourcePointSecondWrapperNetworkAllowed" to secondWrapperPlan.networkSendAllowed.toString(),
            "resourcePointFirstWrapperMissingFields" to firstWrapperPlan.missingNativeFields.joinToString(","),
            "resourcePointSecondWrapperMissingFields" to secondWrapperPlan.missingNativeFields.joinToString(","),
            "resourcePointFirstWrapperMaskedCandidate" to (firstWrapperPlan.maskedRawConcatCandidate ?: ""),
            "resourcePointSecondWrapperMaskedCandidate" to (secondWrapperPlan.maskedRawConcatCandidate ?: ""),
            "nativeWrapperBlocker" to secondWrapperPlan.blocker
        )
    }

    private fun JSONObject.buildBrushYellowPayloadRaw(target: MapTarget, session: GameSession? = null): Map<String, String> {
        val rawObject = optJSONObject("raw")
        val generalChunks = optJSONArray("generalIdHexChunks") ?: rawObject?.optJSONArray("generalIdHexChunks") ?: return emptyMap()
        val targetHex = stringAlias("targetIdHex", "idHex", "targetHex")
            ?: rawObject?.stringAlias("targetIdHex", "idHex", "targetHex")
            ?: target.raw["targetIdHex"]
            ?: target.raw["idHex"]
            ?: target.id.toString(16).padStart(16, '0')
        if (targetHex.isBlank()) return emptyMap()
        val normalizedTargetHex = targetHex.removePrefix("0x").removePrefix("0X").padStart(16, '0')

        val chunks = (0 until generalChunks.length()).map { generalChunks.optString(it) }.filter { it.isNotBlank() }
        if (chunks.isEmpty()) return emptyMap()
        val payloads = BrushYellowDispatchPayloadBuilder.buildBrushYellowPayloads(
            chunks,
            normalizedTargetHex,
            behaviorContract.brushYellow.actionType
        )
        val passiveWirePlan = BrushYellowPassiveWireDryRunPlanner.plan(
            generalIds = chunks,
            targetWireId = normalizedTargetHex,
            includeBatchRefill = true,
            actionType = behaviorContract.brushYellow.actionType
        )
        val wrapperFields = RecoveredNativeWrapperFieldExtractor.from((session?.channelExtra ?: emptyMap()) + toStringMap() + (rawObject?.toStringMap() ?: emptyMap()))
        val prepareWrapperPlan = RecoveredNativeActionWrapperPlanner.plan(payloads.preparePayload, wrapperFields)
        val expeditionWrapperPlan = RecoveredNativeActionWrapperPlanner.plan(payloads.expeditionPayload, wrapperFields)
        return mapOf(
            "preparePayload" to payloads.preparePayload,
            "expeditionPayload" to payloads.expeditionPayload,
            "payloadEvidence" to (
                "shared-contract shuahuang actionType=${behaviorContract.brushYellow.actionType}: " +
                    "${payloads.prepareOpcode} + ${payloads.expeditionOpcode}"
                ),
            "passiveWireEvidence" to passiveWirePlan.evidence,
            "passiveWireNetworkAllowed" to passiveWirePlan.networkSendAllowed.toString(),
            "passiveWireBlocker" to passiveWirePlan.blocker,
            "batchRefill1229GameHex" to passiveWirePlan.refillGameHex.orEmpty(),
            "batchRefill1229CapturedWireTail" to passiveWirePlan.refillCapturedWireTail.orEmpty(),
            "prepare1520GameHex" to passiveWirePlan.prepareGameHex,
            "prepare1520CapturedWireTail" to passiveWirePlan.prepareCapturedWireTail,
            "dispatch1522GameHex" to passiveWirePlan.dispatchGameHex,
            "dispatch1522CapturedWireTail" to passiveWirePlan.dispatchCapturedWireTail,
            "nativeWrapperShape" to prepareWrapperPlan.bodyShape,
            "nativeWrapperContentType" to prepareWrapperPlan.contentType,
            "nativeWrapperEndpointPath" to prepareWrapperPlan.endpointPath,
            "prepareWrapperNetworkAllowed" to prepareWrapperPlan.networkSendAllowed.toString(),
            "expeditionWrapperNetworkAllowed" to expeditionWrapperPlan.networkSendAllowed.toString(),
            "prepareWrapperMissingFields" to prepareWrapperPlan.missingNativeFields.joinToString(","),
            "expeditionWrapperMissingFields" to expeditionWrapperPlan.missingNativeFields.joinToString(","),
            "nativeWrapperMaskedCandidate" to (expeditionWrapperPlan.maskedRawConcatCandidate ?: ""),
            "nativeWrapperBlocker" to expeditionWrapperPlan.blocker
        )
    }


    private fun parseFormationStatus(obj: JSONObject): FormationRuntimeStatus {
        val text = obj.stringAlias("status", "state")?.trim().orEmpty()
        if (text.isNotBlank()) {
            runCatching { return FormationRuntimeStatus.valueOf(text.uppercase()) }
            return when {
                text == "0" || text.contains("空闲") || text.equals("idle", ignoreCase = true) -> FormationRuntimeStatus.IDLE
                text.contains("返回") -> FormationRuntimeStatus.RETURNING
                text.contains("战") -> FormationRuntimeStatus.BATTLE
                text.contains("行军") || text.contains("出征") -> FormationRuntimeStatus.MARCHING
                text.contains("忙") -> FormationRuntimeStatus.BUSY
                else -> FormationRuntimeStatus.UNKNOWN
            }
        }
        return when (obj.intAlias("status", "state")) {
            0 -> FormationRuntimeStatus.IDLE
            1 -> FormationRuntimeStatus.BUSY
            2 -> FormationRuntimeStatus.MARCHING
            3 -> FormationRuntimeStatus.BATTLE
            4 -> FormationRuntimeStatus.RETURNING
            else -> FormationRuntimeStatus.UNKNOWN
        }
    }

    private fun inferFormationStatusFromGenerals(generalIds: List<Long>, generalById: Map<Long, General>): FormationRuntimeStatus {
        if (generalIds.isEmpty()) return FormationRuntimeStatus.UNKNOWN
        val known = generalIds.mapNotNull { generalById[it] }
        if (known.isEmpty()) return FormationRuntimeStatus.UNKNOWN
        return if (known.all { it.status == null || it.status == 0 }) FormationRuntimeStatus.IDLE else FormationRuntimeStatus.BUSY
    }

    private fun selectedRecoveredFormationSlots(prefs: Map<String, String>): List<Int> {
        val direct = prefs.firstValue("shuahuangChuzhengBiandui", "shuaHuangChuzhengBiandui")
            ?.parseFlexibleLongList()
            ?.map { it.toInt() }
            .orEmpty()
        val keyed = prefs.entries.mapNotNull { (key, value) ->
            val normalized = key.replace("[", "").replace("]", "").replace(".", "").replace("_", "")
            val prefix = "shuahuangChuzhengBiandui"
            if (!normalized.startsWith(prefix, ignoreCase = true)) return@mapNotNull null
            val suffix = normalized.substring(prefix.length)
            if (suffix.isBlank()) return@mapNotNull null
            val enabled = value.asLooseBoolean() ?: (value.trim().isNotBlank() && value.trim() != "0")
            suffix.toIntOrNull()?.takeIf { enabled }
        }
        return (direct + keyed).distinct().sorted()
    }

    private fun queryGeneralListForFormationStatus(session: GameSession): List<General> {
        val raw = session.firstRecoveredGeneralRaw()
        return raw?.takeIf { it.isNotBlank() }?.let { parseGeneralsFlexible(it) } ?: emptyList()
    }

    private fun GameSession.firstRecoveredGeneralRaw(): String? {
        // Raw 0x8004 is the source of truth. Prefer it over persisted generalsJson
        // so parser/layout fixes can heal old cached records after an app update.
        for (key in listOf("state8004TailHex", "state8004PayloadHex")) {
            val recovered = channelExtra[key]?.let { State8004GeneralEvidenceParser.recoverRecordText(it) }
            if (!recovered.isNullOrBlank()) return recovered
            val decoded = channelExtra[key]?.decodeHexUtf8ForKeyValueEvidence()
            if (!decoded.isNullOrBlank()) return decoded
        }
        val directKeys = listOf(
            "generalsJson",
            "jiangLingJson",
            "jianglingsJson",
            "jiangLingData",
            "jiangLingRaw",
            "wuJiangData",
            "generalsRaw",
            "state8004TailUtf8",
            "state8004TailText",
            "state8004TailUtf8Preview",
            "state8004PayloadUtf8",
            "state8004PayloadText"
        )
        for (key in directKeys) {
            channelExtra[key]?.takeIf { it.isNotBlank() }?.let { return it }
        }
        return null
    }

    private fun GameSession.firstRecoveredRoleResourceObject(): JSONObject? {
        val directKeys = listOf(
            "roleResourceStateText",
            "roleResourceStateRaw",
            "state8004HeadText",
            "state8004PayloadUtf8",
            "state8004PayloadText",
            "state8004TailUtf8",
            "state8004TailText",
            "state8004TailUtf8Preview"
        )
        for (key in directKeys) {
            val recovered = channelExtra[key]?.takeIf { it.isNotBlank() }?.let { State8004RoleResourceEvidenceParser.recover(it) }
            if (!recovered.isNullOrEmpty()) return JSONObject(recovered)
        }
        for (key in listOf("state8004PayloadHex", "state8004TailHex")) {
            val recovered = channelExtra[key]?.let { State8004RoleResourceEvidenceParser.recover(it) }
            if (!recovered.isNullOrEmpty()) return JSONObject(recovered)
        }
        return null
    }

    private fun GameSession.recoveredPreferenceMap(): Map<String, String> {
        val out = linkedMapOf<String, String>()
        out.putAll(channelExtra)
        listOf("xiaohuangPrefsJson", "sharedPrefsJson", "guajiPrefsJson", "recoveredPrefsJson").forEach { key ->
            val raw = channelExtra[key]?.takeIf { it.isNotBlank() } ?: return@forEach
            runCatching {
                val obj = JSONObject(raw)
                obj.keys().forEach { nestedKey -> out[nestedKey] = obj.optString(nestedKey) }
            }
        }
        return out
    }

    private fun splitRecoveredRecords(text: String): List<String> =
        text.split(Regex("""\r?\n|;;|\|\|"""))
            .map { it.trim() }
            .filter { it.isNotBlank() }

    private fun parseRecoveredKeyValueRecord(record: String): Map<String, String> {
        val clean = record
            .removePrefix("JiangLing")
            .trim()
            .removePrefix("{")
            .removeSuffix("}")
        val regex = Regex("""([A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fa5]+)\s*[:=]\s*('[^']*'|"[^"]*"|[^,;|\s]+)""")
        return regex.findAll(clean)
            .associate { match ->
                val key = match.groupValues[1]
                val value = match.groupValues[2].trim().trim('"', '\'')
                key to value
            }
    }

    private fun Map<String, String>.firstValue(vararg keys: String): String? {
        for (key in keys) {
            this[key]?.takeIf { it.isNotBlank() }?.let { return it }
        }
        return null
    }

    private fun String.parseFlexibleLongList(): List<Long> =
        split(Regex("""[,，;；|/\s]+"""))
            .mapNotNull { it.trim().takeIf { token -> token.isNotBlank() }?.parseLongFlexible() }
            .filter { it > 0L }
            .distinct()

    private fun String?.parseFlexibleLongListLoose(): List<Long> {
        val raw = this?.trim()?.takeIf { it.isNotBlank() } ?: return emptyList()
        val jsonArrayValues = runCatching {
            val arr = JSONArray(raw)
            (0 until arr.length()).mapNotNull { index -> arr.optString(index).parseLongFlexible() }
        }.getOrNull()
        if (!jsonArrayValues.isNullOrEmpty()) return jsonArrayValues.filter { it > 0L }.distinct()
        return raw
            .trim('[', ']', '{', '}', '"', '\'')
            .split(Regex("""[,，;；|/\s]+"""))
            .mapNotNull { token ->
                token.trim()
                    .trim('"', '\'', '[', ']', '{', '}')
                    .takeIf { it.isNotBlank() }
                    ?.parseLongFlexible()
            }
            .filter { it > 0L }
            .distinct()
    }

    private fun String.decodeHexUtf8ForKeyValueEvidence(): String? {
        val hex = trim().removePrefix("0x").removePrefix("0X")
        if (hex.length < 2 || hex.length % 2 != 0 || !hex.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) {
            return null
        }
        val bytes = runCatching {
            ByteArray(hex.length / 2) { index -> hex.substring(index * 2, index * 2 + 2).toInt(16).toByte() }
        }.getOrNull() ?: return null
        val text = String(bytes, Charsets.UTF_8)
            .map { ch -> if (ch.code in 0x20..0x7e || ch in '\u4e00'..'\u9fff') ch else '|' }
            .joinToString(separator = "")
        return text.takeIf { it.contains("=") || it.contains(":") }
    }

    private fun String.hexToBytesLocal(): ByteArray {
        require(length % 2 == 0) { "hex length must be even" }
        return ByteArray(length / 2) { index ->
            substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
    }

    private fun ByteArray.toHex(): String = joinToString(separator = "") { byte ->
        (byte.toInt() and 0xff).toString(16).padStart(2, '0')
    }

    private fun ByteArray.toPrintableTextPreview(maxChars: Int = 2048): String =
        String(this, Charsets.UTF_8)
            .map { ch -> if (ch.code in 0x20..0x7e || ch in '\u4e00'..'\u9fff') ch else ' ' }
            .joinToString(separator = "")
            .replace(Regex("""\s+"""), " ")
            .trim()
            .take(maxChars)

    private fun GameSession.extraJsonObject(vararg keys: String): JSONObject? {
        for (key in keys) {
            val raw = channelExtra[key]
            if (!raw.isNullOrBlank()) return runCatching { JSONObject(raw) }.getOrNull()
        }
        return null
    }

    private fun GameSession.extraString(obj: JSONObject?, vararg names: String): String? {
        for (name in names) {
            obj?.optString(name)?.takeIf { it.isNotBlank() }?.let { return it }
            channelExtra[name]?.takeIf { it.isNotBlank() }?.let { return it }
        }
        return null
    }

    private fun GameSession.extraLong(obj: JSONObject?, vararg names: String): Long? {
        for (name in names) {
            obj?.valueAsString(name)?.parseLongFlexible()?.let { return it }
            channelExtra[name]?.parseLongFlexible()?.let { return it }
        }
        return null
    }

    private fun GameSession.extraInt(obj: JSONObject?, vararg names: String): Int? =
        extraLong(obj, *names)?.toInt()

    private fun JSONObject.stringAlias(vararg names: String): String? {
        for (name in names) valueAsString(name)?.takeIf { it.isNotBlank() }?.let { return it }
        return null
    }

    private fun JSONObject.longAlias(vararg names: String): Long? {
        for (name in names) valueAsString(name)?.parseLongFlexible()?.let { return it }
        return null
    }

    private fun JSONObject.intAlias(vararg names: String): Int? = longAlias(*names)?.toInt()

    private fun JSONObject.boolAlias(vararg names: String): Boolean? {
        for (name in names) {
            if (!has(name) || isNull(name)) continue
            val value = opt(name)
            when (value) {
                is Boolean -> return value
                is Number -> return value.toInt() != 0
                is String -> when (value.trim().lowercase()) {
                    "true", "1", "yes", "y" -> return true
                    "false", "0", "no", "n" -> return false
                }
            }
        }
        return null
    }

    private fun JSONObject.successAlias(vararg names: String): Boolean? {
        for (name in names) {
            if (!has(name) || isNull(name)) continue
            val value = opt(name)
            when (value) {
                is Boolean -> return value
                is Number -> return value.toInt() != 0
                is String -> {
                    val text = value.trim()
                    when (text.lowercase()) {
                        "true", "1", "yes", "y", "ok", "success", "succeeded", "done" -> return true
                        "false", "0", "no", "n", "fail", "failed", "error" -> return false
                    }
                    if (text.contains("成功")) return true
                    if (
                        text.contains("失败") ||
                        text.contains("不可出征") ||
                        text.contains("不能出征") ||
                        text.contains("无法出征")
                    ) return false
                }
            }
        }
        return null
    }

    private fun JSONObject.valueAsString(name: String): String? =
        if (has(name) && !isNull(name)) optString(name) else null

    private fun String.parseLongFlexible(): Long? {
        val value = trim()
        if (value.isBlank()) return null
        val explicitHex = value.startsWith("0x") || value.startsWith("0X")
        val hex = value.removePrefix("0x").removePrefix("0X")
        val hasHexLetters = hex.any { it in 'a'..'f' || it in 'A'..'F' }
        val allHexChars = hex.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
        val allDigits = hex.all { it in '0'..'9' }
        val looksLikeProtocolHexChunk = allHexChars && (
            hasHexLetters ||
                // 8- or 16-byte protocol chunks are usually zero padded.  Do not treat
                // ordinary UI-saved decimal ids such as 12966648 as hex just because they
                // are 8 digits long.
                (allDigits && hex.length >= 8 && hex.startsWith("0"))
            )
        if (explicitHex || looksLikeProtocolHexChunk) {
            runCatching { java.lang.Long.parseUnsignedLong(hex, 16) }.getOrNull()?.let { return it }
        }
        value.toLongOrNull()?.let { return it }
        return if (allHexChars) {
            runCatching { java.lang.Long.parseUnsignedLong(hex, 16) }.getOrNull()
        } else {
            null
        }
    }

    private fun JSONObject.nullableInt(name: String): Int? =
        if (has(name) && !isNull(name)) optInt(name) else null

    private fun String?.asLooseBoolean(): Boolean? {
        val value = this?.trim()?.lowercase() ?: return null
        return when (value) {
            "true", "1", "yes", "y", "on", "enabled" -> true
            "false", "0", "no", "n", "off", "disabled" -> false
            else -> null
        }
    }

    private fun JSONObject.toStringMap(): Map<String, String> =
        keys().asSequence().associateWith { key -> optString(key) }
    companion object {
        private const val MAX_FEATURE_PAGES: Int = 100
        private const val LIVE_STATE_CACHE_MS: Long = 2_000L
        private const val HEARTBEAT_3110_MIN_INTERVAL_MS: Long = 20_000L
        private const val DUNGEON_PENDING_RUN_KEY: String = "dungeonPendingRunJson"
        private const val DUNGEON_STALE_RECOVERY_MILLIS: Long = 60_000L
        private val ROLE_RESOURCE_KEYS = setOf(
            "roleId", "roleName", "level", "nation", "title", "copper", "food", "prestige",
            "copperPerHour", "foodPerHour", "populationCurrent", "populationCap",
            "resourcePointCurrent", "resourcePointCap", "sourceOpcode", "syncedAt"
        )
    }

}

interface RecoveredReadOnlyExecutor {
    fun execute(
        gameHttp: String,
        dm: Long,
        gameHex: String,
        liveGate: Boolean
    ): RealGameProtocolClient.RecoveredReadOnlyExecutionResult
}

private class RealRecoveredReadOnlyExecutor(
    private val client: RealGameProtocolClient = RealGameProtocolClient()
) : RecoveredReadOnlyExecutor {
    override fun execute(
        gameHttp: String,
        dm: Long,
        gameHex: String,
        liveGate: Boolean
    ): RealGameProtocolClient.RecoveredReadOnlyExecutionResult =
        client.executeRecoveredReadOnlyGameHex(gameHttp, dm, gameHex, liveGate)
}

interface Heartbeat3110Executor {
    fun execute(gameHttp: String, dm: Long): RealGameProtocolClient.Heartbeat3110Result
}

private class RealHeartbeat3110Executor(
    private val client: RealGameProtocolClient = RealGameProtocolClient()
) : Heartbeat3110Executor {
    override fun execute(
        gameHttp: String,
        dm: Long
    ): RealGameProtocolClient.Heartbeat3110Result =
        client.refreshHeartbeat3110(gameHttp, dm)
}

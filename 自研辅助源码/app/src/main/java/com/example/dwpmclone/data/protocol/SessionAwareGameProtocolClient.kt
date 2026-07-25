package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import com.example.dwpmclone.domain.alarm.MilitaryAlarmEventDetector
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.net.HttpURLConnection
import java.net.Proxy
import java.net.URL
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentHashMap

/**
 * Local scheduler protocol boundary that prefers real read-only session metadata.
 *
 * Source modes:
 * - sourceMode == 1: session was created by RealGameProtocolClient login/sync. Only
 *   read-only fields that were saved from real responses are exposed. Mutating or still
 *   unrecovered calls return explicit REAL_*_NOT_IMPLEMENTED errors instead of silently
 *   falling back to mock behavior.
 * - other sourceMode values: delegate to MockGameProtocolClient for local UI/scheduler smoke tests.
 */
data class DirectBinaryResponse(
    val phase: String,
    val httpCode: Int,
    val ok: Boolean,
    val responseBytes: Int,
    val responseHex: String,
    val textPreview: String,
    val responseOpcodes: List<Int> = emptyList()
)

class SessionAwareGameProtocolClient(
    private val mock: GameProtocolClient = MockGameProtocolClient(),
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
    ) -> DirectBinaryResponse)? = null
) : GameProtocolClient {
    private val liveStateCache = ConcurrentHashMap<String, LiveStateBundle>()
    private val liveStateErrors = ConcurrentHashMap<String, String>()
    private val pendingDungeons = ConcurrentHashMap<Long, PendingDungeon>()
    private val dungeonPollBattleIds = ConcurrentHashMap<Long, Long>()
    private val losslessRuleCursors = ConcurrentHashMap<Long, Int>()
    private val lootRuleCursors = ConcurrentHashMap<Long, Int>()
    private val internalTechnologyTurns = ConcurrentHashMap<Long, Boolean>()
    private val seenAlarmFingerprints = ConcurrentHashMap<Long, MutableSet<String>>()
    private val lastHeartbeat3110AttemptAt = ConcurrentHashMap<Long, Long>()

    private data class LiveStateBundle(
        val state: RealGameProtocolClient.RoleState,
        val roleJson: JSONObject,
        val resourceJson: JSONObject,
        val responseOpcodes: List<String>,
        val refreshedAtMillis: Long
    )

    private data class PendingDungeon(
        val generalIds: List<Long>,
        val chapter: Int,
        val stage: Int,
        val chestPosition: Int,
        val launchedAtMillis: Long
    )

    override suspend fun login(account: GameAccount): ProtocolResult<GameSession> =
        account.session?.let { ProtocolResult.Ok(it) }
            ?: ProtocolResult.Err("NO_SESSION", "账号尚未通过真实协议登录", retryable = false)

    override suspend fun logout(session: GameSession): ProtocolResult<StepResult> =
        if (session.isRealReadOnly()) ProtocolResult.Ok(StepResult(true, "real read-only session marked logged out locally"))
        else mock.logout(session)

    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> =
        if (!session.isRealReadOnly()) {
            mock.validateSession(session)
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
        if (!session.isRealReadOnly()) {
            mock.queryMonarch(session)
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
        if (!session.isRealReadOnly()) {
            mock.queryResourceState(session)
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
        if (!session.isRealReadOnly()) {
            mock.queryGenerals(session)
        } else {
            val live = session.liveStateBundleOrNull()
            if (live == null) session.liveStateErrorOrNull()?.let {
                return ProtocolResult.Err("REAL_LIVE_STATE_REFRESH_FAILED", "真实 0x1016 状态刷新失败：$it", retryable = true)
            }
            if (live != null) {
                ProtocolResult.Ok(parseGeneralsFromLiveState(live))
            } else {
                val raw = session.firstRecoveredGeneralRaw()
                if (raw.isNullOrBlank()) {
                    unrecovered("REAL_GENERALS_METADATA_MISSING", "真实 session 暂无 generalsJson/jiangLingData/state8004TailUtf8Preview；需继续恢复 0x8004 后段或将领接口")
                } else {
                    runCatching { ProtocolResult.Ok(parseGeneralsFlexible(raw)) }
                        .getOrElse { ProtocolResult.Err("REAL_GENERALS_METADATA_INVALID", "generalsJson/jiangLingData 解析失败：${it.message}", retryable = false) }
                }
            }
        }

    override suspend fun queryFormations(session: GameSession): ProtocolResult<List<FormationRuntime>> =
        if (!session.isRealReadOnly()) {
            mock.queryFormations(session)
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
        if (!session.isRealReadOnly()) {
            mock.searchMap(session, start, policy)
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

    override suspend fun dispatchFormation(session: GameSession, formationId: Long, target: MapTarget): ProtocolResult<BattleResult> =
        if (!session.isRealReadOnly()) {
            mock.dispatchFormation(session, formationId, target)
        } else {
            val raw = session.channelExtra["dispatchResultsJson"]
            if (raw.isNullOrBlank()) {
                executeRecoveredBrushYellowLiveAction(session, formationId, target)
                    ?: unrecovered("REAL_DISPATCH_METADATA_MISSING", "真实 session 暂无 dispatchResultsJson；已恢复 p2=0 payload 公式，但真实 request wrapper/native/session 仍未接入")
            } else {
                runCatching { parseDispatchResult(raw, formationId, target, session) }
                    .getOrElse { ProtocolResult.Err("REAL_DISPATCH_METADATA_INVALID", "dispatchResultsJson 解析失败：${it.message}", retryable = false) }
            }
        }

    override suspend fun convertFoodToCopper(session: GameSession, mode: ConvertMode): ProtocolResult<ResourceState> {
        if (!session.isRealReadOnly()) return mock.convertFoodToCopper(session, mode)
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
        val bytes = runCatching { response.responseHex.hexToBytesLocal() }.getOrNull()
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
        if (!session.isRealReadOnly()) {
            mock.searchMines(session, config)
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

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        formationId: Long
    ): ProtocolResult<StepResult> = occupyMine(session, mine, listOf(formationId))

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>
    ): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.occupyMine(session, mine, generalIds)
        val ids = generalIds.distinct()
        if (ids.isEmpty()) {
            return ProtocolResult.Err("REAL_MINE_GENERALS_EMPTY", "真实打矿至少需要选择1名出征将领", false)
        }
        executeRecoveredMineOccupyLiveAction(session, mine, ids)?.let { return it }
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
        generalIds: List<Long>
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
        val generals = when (val result = queryGenerals(session)) {
            is ProtocolResult.Ok -> {
                val byId = result.value.associateBy { it.id }
                generalIds.map { id ->
                    byId[id]
                        ?: return ProtocolResult.Err("REAL_MINE_GENERAL_NOT_FOUND", "未找到打矿将领ID=$id", false)
                }
            }
            is ProtocolResult.Err -> return result
        }
        for (general in generals) {
            if (general.status == null) {
                return ProtocolResult.Err("REAL_MINE_GENERAL_STATUS_UNKNOWN", "无法确认将领${general.name}状态", false)
            }
            if (general.status != 0) {
                return ProtocolResult.Ok(StepResult(false, "将领${general.name}当前非空闲，等待返回"))
            }
            if (general.energy == null) {
                return ProtocolResult.Err("REAL_MINE_GENERAL_ENERGY_UNKNOWN", "无法确认将领${general.name}体力", false)
            }
            if (general.energy <= 0) {
                return ProtocolResult.Ok(StepResult(false, "将领${general.name}体力不足，未发起打矿"))
            }
            val troops = general.currentAssignedTroops()
                ?: return ProtocolResult.Err("REAL_MINE_TROOPS_UNKNOWN", "无法确认将领${general.name}当前兵力", false)
            if (troops.count <= 0) {
                return ProtocolResult.Ok(StepResult(false, "将领${general.name}没有可用兵力，未发起打矿"))
            }
        }
        val preparePayload = ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeByte(2)
                out.writeByte(generalIds.size)
                generalIds.forEach(out::writeLong)
                out.writeLong(mine.id)
            }
        }.toByteArray()
        val expeditionPayload = preparePayload + ByteBuffer.allocate(11)
            .putLong(-1L)
            .put(0)
            .put(0)
            .put(0)
            .array()

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

        val prepare = when (val result = send(0x1520, preparePayload, "mine/prepare")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (0x8520 !in prepare.responseOpcodes ||
            prepare.responseHex.filter(Char::isLetterOrDigit).equals("ff0000", true)
        ) {
            return ProtocolResult.Ok(StepResult(false, "打矿预出征未获得0x8520成功确认"))
        }
        val expedition = when (val result = send(0x1522, expeditionPayload, "mine/dispatch")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (0x8522 !in expedition.responseOpcodes) {
            return ProtocolResult.Ok(StepResult(false, "打矿出征未收到0x8522"))
        }
        val parsed = BrushYellowDispatchResponseParser.parse(responseHex = expedition.responseHex)
            ?: BrushYellowDispatchResponseParser.parse(responseText = expedition.textPreview)
        val success = parsed?.success == true
        return ProtocolResult.Ok(StepResult(
            success,
            if (success) {
                "打矿出征已确认：${generals.joinToString("/") { it.name }} → ${mine.mineType.name}(${mine.coordinate.x},${mine.coordinate.y})"
            } else {
                parsed?.message ?: "0x8522未确认打矿出征成功"
            },
            mapOf(
                "generalIds" to generalIds.joinToString(","),
                "generalId" to generalIds.first().toString(),
                "mineId" to mine.id.toString(),
                "preparePayloadHex" to preparePayload.toHex(),
                "expeditionPayloadHex" to expeditionPayload.toHex(),
                "prepareResponseHex" to prepare.responseHex.take(512),
                "expeditionResponseHex" to expedition.responseHex.take(512),
                "parsedEvidence" to (parsed?.evidence ?: "none")
            )
        ))
    }

    override suspend fun withdrawMineDefense(session: GameSession, mineId: Long): ProtocolResult<StepResult> =
        if (!session.isRealReadOnly()) {
            mock.withdrawMineDefense(session, mineId)
        } else {
            val raw = session.channelExtra["withdrawMineResultsJson"]
            if (raw.isNullOrBlank()) {
                unrecovered("REAL_WITHDRAW_MINE_METADATA_MISSING", "真实 session 暂无 withdrawMineResultsJson；撤防 payload 形状已恢复，但真实 request wrapper/native/session 仍未接入")
            } else {
                runCatching { parseWithdrawMineResult(raw, mineId) }
                    .getOrElse { ProtocolResult.Err("REAL_WITHDRAW_MINE_METADATA_INVALID", "withdrawMineResultsJson 解析失败：${it.message}", retryable = false) }
            }
        }

    override suspend fun runDailyStep(session: GameSession, step: DailyStep): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.runDailyStep(session, step)
        executeRecoveredDailyLiveAction(session, step)?.let { return it }
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
        if (!session.isRealReadOnly()) return mock.queryNationalCities(session, kind)
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
                DailyFeatureProtocolShapes.NATIONAL_LIST_OPCODE,
                DailyFeatureProtocolShapes.buildNationalCityListPayload(category, page),
                setOf(0x8404),
                "national/list/category=$category/page=$page"
            )) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> return result
            }
            val parsed = runCatching {
                DailyFeatureProtocolShapes.parseNationalCityPage(
                    response.responseHex.hexToBytesLocal(),
                    category
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
            if (parsed.cities.size < DailyFeatureProtocolShapes.NATIONAL_LIST_PAGE_SIZE && page >= totalPages) break
            page += 1
        }
        return ProtocolResult.Ok(cities.distinctBy { it.name })
    }

    override suspend fun queryNationalCollectStatus(
        session: GameSession,
        city: NationalCity
    ): ProtocolResult<NationalCollectStatus> {
        if (!session.isRealReadOnly()) return mock.queryNationalCollectStatus(session, city)
        val transport = when (val result = featureTransport(session, "国家征收状态")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val response = when (val result = sendFeatureCommand(
            transport,
            DailyFeatureProtocolShapes.NATIONAL_STATUS_OPCODE,
            DailyFeatureProtocolShapes.buildNationalCityStatusPayload(city.name),
            setOf(0x8332),
            "national/status/${city.name}"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            ProtocolResult.Ok(
                DailyFeatureProtocolShapes.parseNationalCollectStatus(
                    response.responseHex.hexToBytesLocal()
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
        if (!session.isRealReadOnly()) return mock.collectNationalCity(session, city)
        val transport = when (val result = featureTransport(session, "国家征收")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val response = when (val result = sendFeatureCommand(
            transport,
            DailyFeatureProtocolShapes.NATIONAL_COLLECT_OPCODE,
            DailyFeatureProtocolShapes.buildNationalCollectPayload(city.name),
            setOf(0x8334),
            "national/collect/${city.name}"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            val receipt = DailyFeatureProtocolShapes.parseNationalCollectReceipt(
                response.responseHex.hexToBytesLocal()
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
        if (!session.isRealReadOnly()) return mock.queryOwnedFiefs(session)
        val transport = when (val result = featureTransport(session, "城主城池列表")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val roleName = session.channelExtra["roleName"]?.takeIf { it.isNotBlank() }
        val roleId = session.channelExtra["roleId"]?.parseLongFlexible() ?: session.accountId
        val response = when (val result = sendFeatureCommand(
            transport,
            DailyFeatureProtocolShapes.CITY_LORD_LIST_OPCODE,
            DailyFeatureProtocolShapes.buildOwnedFiefListPayload(roleName, roleId),
            setOf(0x8310),
            "city-lord/list"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            ProtocolResult.Ok(LootProtocolShapes.parseFiefList(response.responseHex.hexToBytesLocal()))
        }.getOrElse {
            ProtocolResult.Err(
                "REAL_OWNED_FIEF_PARSE_FAILED",
                "自有城池列表解析失败：${it.message}",
                false
            )
        }
    }

    override suspend fun collectCityLord(
        session: GameSession,
        fief: LootTargetFief
    ): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.collectCityLord(session, fief)
        val transport = when (val result = featureTransport(session, "城主征收")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val response = when (val result = sendFeatureCommand(
            transport,
            DailyFeatureProtocolShapes.CITY_LORD_COLLECT_OPCODE,
            DailyFeatureProtocolShapes.buildCityLordCollectPayload(fief.cityName),
            setOf(0x8330),
            "city-lord/collect/${fief.cityName}"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            val receipt = DailyFeatureProtocolShapes.parseCityLordCollectReceipt(
                response.responseHex.hexToBytesLocal()
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

    override suspend fun queryVisitGenerals(session: GameSession): ProtocolResult<List<GeneralVisitCandidate>> {
        if (!session.isRealReadOnly()) return mock.queryVisitGenerals(session)
        val transport = when (val result = featureTransport(session, "名将列表")) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val pageSize = DailyFeatureProtocolShapes.DEFAULT_GENERAL_PAGE_SIZE
        val pages = mutableListOf<GeneralVisitCandidate>()
        var page = 1
        while (page <= MAX_FEATURE_PAGES) {
            val response = when (val result = sendFeatureCommand(
                transport,
                DailyFeatureProtocolShapes.GENERAL_LIST_OPCODE,
                DailyFeatureProtocolShapes.buildGeneralListPayload(page, pageSize),
                setOf(0xA271),
                "general-visit/list/page=$page"
            )) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> return result
            }
            val parsed = runCatching {
                DailyFeatureProtocolShapes.parseGeneralVisitPage(response.responseHex.hexToBytesLocal())
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_GENERAL_VISIT_LIST_PARSE_FAILED",
                    "名将列表解析失败 page=$page：${it.message}",
                    false
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
        return ProtocolResult.Ok(pages.distinctBy { it.id })
    }

    override suspend fun visitGeneral(
        session: GameSession,
        candidate: GeneralVisitCandidate
    ): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.visitGeneral(session, candidate)
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
            DailyFeatureProtocolShapes.GENERAL_VISIT_OPCODE,
            DailyFeatureProtocolShapes.buildGeneralVisitPayload(candidate.id, page, pageSize),
            setOf(0xA273),
            "general-visit/${candidate.id}"
        )) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        return runCatching {
            val receipt = DailyFeatureProtocolShapes.parseGeneralVisitReceipt(
                response.responseHex.hexToBytesLocal()
            )
            ProtocolResult.Ok(
                StepResult(
                    receipt.success,
                    receipt.message.ifBlank { "名将拜访${if (receipt.success) "成功" else "失败"}：${candidate.name}" },
                    mapOf(
                        "generalId" to candidate.id.toString(),
                        "generalName" to candidate.name,
                        "status" to receipt.status.toString(),
                        "page" to page.toString()
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
        val commands = when (step) {
            DailyStep.SIGN_IN -> listOf(
                DailyCommand(0x6202, ByteArray(0), setOf(0xE202)),
                DailyCommand(
                    0x1134,
                    DailyProtocolShapes.buildDailyDiamondBoxPayload(),
                    setOf(0x8134),
                    requiredForStep = false
                )
            )
            DailyStep.ARENA_REWARD -> listOf(
                DailyCommand(0x6260, ByteArray(0), emptySet()),
                DailyCommand(0x6266, ByteArray(0), setOf(0xE266))
            )
            DailyStep.SALARY -> listOf(
                DailyCommand(
                    0x314B,
                    DailyFeatureProtocolShapes.buildSalaryPayload(),
                    setOf(0xA14B)
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
                            0x140C,
                            DailyFeatureProtocolShapes.buildDonateCopperPayload(level * 1_000L),
                            setOf(0x840C)
                        )
                    )
                    DailyStep.DONATE_FOOD -> listOf(
                        DailyCommand(
                            0x140C,
                            DailyFeatureProtocolShapes.buildDonateFoodPayload(level * 3_000L),
                            setOf(0x840C)
                        )
                    )
                    DailyStep.DONATE_TECH -> listOf(
                        DailyCommand(
                            0x140A,
                            DailyFeatureProtocolShapes.buildDonateTechPayload(level * 1_000),
                            setOf(0x840A)
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
            if (step == DailyStep.SIGN_IN && command.opcode == 0x6202) {
                val receipt = runCatching {
                    DailyProtocolShapes.parseStatusMessage(response.responseHex.hexToBytesLocal())
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_DAILY_RECEIPT_INVALID",
                        "SIGN_IN回执解析失败：${it.message}",
                        false
                    )
                }
                if (!receipt.success) {
                    return ProtocolResult.Ok(StepResult(
                        false,
                        receipt.message.ifBlank { "签到失败：状态=${receipt.status}" },
                        mapOf("status" to receipt.status.toString())
                    ))
                }
            }
        }
        val finalReceipt = if (step == DailyStep.ARENA_REWARD) {
            runCatching {
                DailyProtocolShapes.parseStatusMessage(responses.last().responseHex.hexToBytesLocal())
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
                    responses.last().responseHex.hexToBytesLocal()
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
                    responses.last().responseHex.hexToBytesLocal()
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
        val donationStatus = if (step in setOf(
                DailyStep.DONATE_COPPER,
                DailyStep.DONATE_FOOD,
                DailyStep.DONATE_TECH
            )
        ) {
            responses.last().responseHex.hexToBytesLocal().firstOrNull()?.toInt()?.and(0xff)
        } else {
            null
        }
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
                    salaryReceipt?.message?.ifBlank { "当前不能领取俸禄：状态=${salaryReceipt?.status}" }
                        ?: "国家俸禄回执为空",
                    mapOf(
                        "status" to (salaryReceipt?.status?.toString() ?: "unknown"),
                        "extra" to (salaryReceipt?.extra?.toString() ?: "unknown")
                    )
                )
            )
        }
        if (donationStatus != null && donationStatus != 0) {
            return ProtocolResult.Ok(
                StepResult(
                    false,
                    "${step.name}被服务器拒绝，状态=$donationStatus",
                    mapOf("status" to donationStatus.toString())
                )
            )
        }
        val message = when (step) {
            DailyStep.SIGN_IN -> {
                val boxResponse = responses.getOrNull(1)
                val boxReceipt = if (boxResponse != null && optionalFailure == null) {
                    runCatching {
                        DailyProtocolShapes.parseStatusMessage(boxResponse.responseHex.hexToBytesLocal())
                    }.getOrNull()
                } else {
                    null
                }
                if (boxReceipt?.success == true) {
                    "签到请求已确认；每日金钻宝箱已领取"
                } else {
                    "签到请求已确认；每日金钻宝箱未领取：" +
                        (optionalFailure
                            ?: boxReceipt?.message?.ifBlank { "状态=${boxReceipt.status}" }
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
                "responseOpcodes" to responses
                    .flatMap { it.responseOpcodes }
                    .joinToString { "0x${it.toString(16)}" }
            )
        ))
    }

    override suspend fun healGeneral(session: GameSession, generalId: Long): ProtocolResult<StepResult> =
        if (!session.isRealReadOnly()) {
            mock.healGeneral(session, generalId)
        } else {
            executeRecoveredHealWoundedLiveAction(session, generalId)
                ?: unrecovered("REAL_HEAL_GATE_CLOSED", "真实治疗需要 brush-yellow 专用动作 gate；当前未开启")
        }

    override suspend fun addEnergy(session: GameSession, generalId: Long): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.addEnergy(session, generalId)
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
            GeneralProtocolShapes.parseAddEnergyResponse(response.responseHex.hexToBytesLocal())
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

    override suspend fun updateFormation(session: GameSession, config: FormationConfig): ProtocolResult<StepResult> =
        if (!session.isRealReadOnly()) {
            mock.updateFormation(session, config)
        } else {
            executeRecoveredFormationUpdateLiveAction(session, config)
                ?: unrecovered("REAL_UPDATE_FORMATION_GATE_CLOSED", "真实配兵/补兵需要 brush-yellow 专用动作 gate；当前未开启")
        }

    override suspend fun runInternalAffairs(session: GameSession, config: InternalAffairsConfig): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.runInternalAffairs(session, config)
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
                LootProtocolShapes.parseFiefList(ownFiefs.responseHex.hexToBytesLocal())
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
                InternalAffairsProtocolShapes.parseFiefState(query.responseHex.hexToBytesLocal(), fiefId)
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
        val upgradeAction = if (runBuildingsThisCycle && hallAction == null && emptyAction == null) {
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
                        response.responseHex.hexToBytesLocal()
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
                                recheck.responseHex.hexToBytesLocal(),
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
                DailyProtocolShapes.parseStatusMessage(response.responseHex.hexToBytesLocal())
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
        if (!session.isRealReadOnly()) return mock.runSixMinistries(session, config)
        config.preparationError()?.let {
            return ProtocolResult.Err("REAL_MINISTRY_CONFIG_UNSUPPORTED", it, false)
        }
        val gameHttp = session.gameHttpOrNull()
            ?: return ProtocolResult.Err("REAL_MINISTRY_GAME_HTTP_MISSING", "六部缺少 gameHttp/serverUrl", false)
        val dm = session.dmOrNull()
            ?: return ProtocolResult.Err("REAL_MINISTRY_DM_MISSING", "六部缺少 dm", false)

        fun scanStealTargets(): ProtocolResult<Pair<List<MinistryStealTarget>, Int>> {
            if (session.channelExtra["recoveredReadOnlyLiveGate"].asLooseBoolean() != true) {
                return ProtocolResult.Err(
                    "REAL_MINISTRY_STEAL_SCAN_GATE_NOT_READY",
                    "六部偷菜候选只读扫描 gate 未开启",
                    false
                )
            }
            val targetList = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(0x6322, MinistryProtocolShapes.buildStealTargetListPayload()),
                    "ministry/steal-targets"
                )
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_MINISTRY_STEAL_TARGETS_EXCEPTION",
                    "读取偷菜候选异常：${it.message}",
                    false
                )
            }
            if (!targetList.ok || 0xe322 !in targetList.responseOpcodes) {
                return ProtocolResult.Err(
                    "REAL_MINISTRY_STEAL_TARGETS_FAILED",
                    "偷菜候选未收到0xe322",
                    false
                )
            }
            val stealTargets = runCatching {
                MinistryProtocolShapes.parseStealTargets(targetList.responseHex.hexToBytesLocal())
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_MINISTRY_STEAL_TARGETS_INVALID",
                    "偷菜候选解析失败：${it.message}",
                    false
                )
            }
            var scannedTargetGardens = 0
            for (target in stealTargets) {
                val garden = runCatching {
                    sendBinaryMappedGameHex(
                        gameHttp,
                        dm,
                        buildDirectGameHex(
                            0x6323,
                            MinistryProtocolShapes.buildTargetGardenPayload(target.roleId)
                        ),
                        "ministry/steal-garden"
                    )
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_MINISTRY_TARGET_GARDEN_EXCEPTION",
                        "读取${target.name}菜地异常：${it.message}",
                        false
                    )
                }
                if (!garden.ok || 0xe323 !in garden.responseOpcodes) {
                    return ProtocolResult.Err(
                        "REAL_MINISTRY_TARGET_GARDEN_FAILED",
                        "读取${target.name}菜地未收到0xe323",
                        false
                    )
                }
                runCatching {
                    MinistryProtocolShapes.parseTargetGardenHeader(
                        garden.responseHex.hexToBytesLocal(),
                        target.roleId
                    )
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_MINISTRY_TARGET_GARDEN_INVALID",
                        "${target.name}菜地响应解析失败：${it.message}",
                        false
                    )
                }
                scannedTargetGardens += 1
            }
            actionAudit?.invoke(
                "六部偷菜只读扫描：0x6322候选=${stealTargets.size}，0x6323菜地=$scannedTargetGardens；未发送偷菜动作"
            )
            return ProtocolResult.Ok(stealTargets to scannedTargetGardens)
        }

        if (!config.cropEnabled) {
            val (stealTargets, scannedTargetGardens) = when (val scan = scanStealTargets()) {
                is ProtocolResult.Ok -> scan.value
                is ProtocolResult.Err -> return scan
            }
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    "已只读扫描${stealTargets.size}个偷菜候选；偷菜动作协议未确认，未执行",
                    mapOf(
                        "phase" to "steal-scan",
                        "targetCount" to stealTargets.size.toString(),
                        "gardenCount" to scannedTargetGardens.toString(),
                        "networkMutation" to "false"
                    )
                )
            )
        }
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
                    MinistryProtocolShapes.parseGardenStatus(response.responseHex.hexToBytesLocal())
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
            val (stealTargets, scannedTargetGardens) = if (config.stealEnabled) {
                when (val scan = scanStealTargets()) {
                    is ProtocolResult.Ok -> scan.value
                    is ProtocolResult.Err -> return scan
                }
            } else {
                emptyList<MinistryStealTarget>() to 0
            }
            val unsupported = buildList {
                if (config.stealEnabled) add("偷菜动作")
                if (config.courtesyEnabled) add("礼部任务")
                if (config.salaryRefresh) add("俸禄刷新")
            }
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    if (config.stealEnabled) {
                        "六部菜地已满；已只读扫描${stealTargets.size}个偷菜候选，未发送偷菜动作"
                    } else {
                        "六部菜地已满；收菜协议未确认，等待下次检查"
                    },
                    mapOf(
                        "phase" to "garden-full",
                        "occupied" to before.occupiedCount.toString(),
                        "plots" to before.plotCount.toString(),
                        "stealTargetCount" to stealTargets.size.toString(),
                        "stealGardenCount" to scannedTargetGardens.toString(),
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
            MinistryProtocolShapes.parsePlantResponse(plant.responseHex.hexToBytesLocal())
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
                    "stealTargetCount" to "0",
                    "stealScanDeferred" to config.stealEnabled.toString(),
                    "unsupportedEnabled" to unsupported.joinToString(",")
                )
            )
        )
    }

    override suspend fun runDungeon(session: GameSession, config: DungeonConfig): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.runDungeon(session, config)
        if (!config.enabled) return ProtocolResult.Ok(StepResult(false, "副本任务未启用"))
        if (config.formationIds.isEmpty()) {
            return ProtocolResult.Err("REAL_DUNGEON_GENERALS_MISSING", "副本至少需要选择一个将领", false)
        }
        if (config.boxPosition !in 0..2) {
            return ProtocolResult.Err("REAL_DUNGEON_CHEST_INVALID", "副本宝箱位置必须为左、中、右", false)
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
        val selected = config.formationIds.map { id ->
            generals.firstOrNull { it.id == id }
                ?: return ProtocolResult.Err("REAL_DUNGEON_GENERAL_NOT_FOUND", "副本未找到将领 ID=$id", false)
        }

        fun queryBattleState(): ProtocolResult<DungeonBattleStatus> {
            val response = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(0x1938, byteArrayOf()),
                    "dungeon/state"
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_DUNGEON_STATE_EXCEPTION", "读取副本状态异常：${it.message}", true)
            }
            if (!response.ok || 0x8938 !in response.responseOpcodes) {
                return ProtocolResult.Err("REAL_DUNGEON_STATE_UNCONFIRMED", "读取副本状态未收到0x8938", true)
            }
            return runCatching {
                ProtocolResult.Ok(
                    DungeonProtocolShapes.parseBattleState(response.responseHex.hexToBytesLocal())
                )
            }.getOrElse {
                ProtocolResult.Err("REAL_DUNGEON_STATE_INVALID", "副本状态解析失败：${it.message}", false)
            }
        }

        fun openConfiguredChest(reason: String): ProtocolResult<StepResult> {
            val chest = sendDungeonCommand(
                gameHttp, dm, 0x193E,
                DungeonProtocolShapes.buildOpenChestPayload(config.boxPosition),
                expectedOpcode = 0x893E,
                phase = "dungeon/open-chest"
            )
            if (chest is ProtocolResult.Err) return chest
            val chestStep = (chest as ProtocolResult.Ok).value
            if (!chestStep.success) return chest
            pendingDungeons.remove(session.accountId)
            dungeonPollBattleIds.remove(session.accountId)
            return ProtocolResult.Ok(StepResult(
                true,
                "副本完成并已开启${listOf("左", "中", "右")[config.boxPosition]}侧宝箱",
                mapOf(
                    "phase" to "chest-opened",
                    "chapter" to config.chapter.toString(),
                    "stage" to config.stage.toString(),
                    "completionEvidence" to reason
                )
            ))
        }

        val battleState = when (val result = queryBattleState()) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (battleState.phase == DungeonBattlePhase.UNKNOWN) {
            return ProtocolResult.Err(
                "REAL_DUNGEON_STATE_UNKNOWN",
                "副本返回未知状态=${battleState.rawStatus}，已中断",
                false
            )
        }
        val selectedDefinitelyIdle = selected.all { it.status == 0 }
        if (battleState.phase == DungeonBattlePhase.SETTLEMENT) {
            return openConfiguredChest("0x8938-status-4")
        }
        if (battleState.phase == DungeonBattlePhase.FIGHTING) {
            val battleId = battleState.battleId
                ?: return ProtocolResult.Err("REAL_DUNGEON_BATTLE_ID_MISSING", "副本战斗状态缺少 battleId", false)
            if (selectedDefinitelyIdle) {
                val reward = runCatching {
                    sendBinaryMappedGameHex(
                        gameHttp,
                        dm,
                        buildDirectGameHex(0x193D, byteArrayOf()),
                        "dungeon/reward-state"
                    )
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_DUNGEON_REWARD_EXCEPTION",
                        "读取副本奖励状态异常：${it.message}",
                        true
                    )
                }
                if (!reward.ok || 0x893D !in reward.responseOpcodes) {
                    return ProtocolResult.Err(
                        "REAL_DUNGEON_REWARD_UNCONFIRMED",
                        "将领已回闲但副本奖励状态未收到0x893d，禁止开箱",
                        true
                    )
                }
                val parsedReward = runCatching {
                    DungeonProtocolShapes.parseRewardState(reward.responseHex.hexToBytesLocal())
                }.getOrElse {
                    return ProtocolResult.Err(
                        "REAL_DUNGEON_REWARD_INVALID",
                        "副本奖励状态解析失败：${it.message}",
                        false
                    )
                }
                if (parsedReward.battleId != null && parsedReward.battleId != battleId) {
                    return ProtocolResult.Err(
                        "REAL_DUNGEON_REWARD_BATTLE_MISMATCH",
                        "副本奖励 battleId 与当前战斗不一致，禁止开箱",
                        false
                    )
                }
                return openConfiguredChest("generals-idle+0x893d")
            }
            val firstPoll = dungeonPollBattleIds.put(session.accountId, battleId) != battleId
            val poll = runCatching {
                sendBinaryMappedGameHex(
                    gameHttp,
                    dm,
                    buildDirectGameHex(
                        0x1702,
                        DungeonProtocolShapes.buildBattlePollPayload(firstPoll, battleId)
                    ),
                    "dungeon/battle-poll"
                )
            }.getOrElse {
                return ProtocolResult.Err("REAL_DUNGEON_POLL_EXCEPTION", "副本战况轮询异常：${it.message}", true)
            }
            if (!poll.ok || 0x8702 !in poll.responseOpcodes) {
                return ProtocolResult.Err("REAL_DUNGEON_POLL_UNCONFIRMED", "副本战况轮询未收到0x8702", true)
            }
            return ProtocolResult.Ok(StepResult(
                true,
                "副本战斗中，已完成一次战况轮询",
                mapOf(
                    "phase" to "fighting",
                    "battleId" to battleId.toString(),
                    "pollPhase" to if (firstPoll) "2" else "1"
                )
            ))
        }

        selected.forEach { general ->
            if (general.status == null) {
                return ProtocolResult.Err("REAL_DUNGEON_STATUS_UNKNOWN", "无法确认将领${general.name}状态，已中断副本", false)
            }
            if (general.status != 0) {
                return ProtocolResult.Ok(StepResult(
                    true,
                    "将领${general.name}当前非闲，等待回闲后继续副本",
                    mapOf("phase" to "waiting-general")
                ))
            }
            if (general.energy == null) {
                return ProtocolResult.Err("REAL_DUNGEON_ENERGY_UNKNOWN", "无法确认将领${general.name}体力，已中断副本", false)
            }
            if (general.energy <= 0) {
                return ProtocolResult.Ok(StepResult(false, "将领${general.name}体力不足，暂不发起副本"))
            }
        }
        val formations = when (val result = queryFormations(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        selected.forEach { general ->
            val formation = formations.firstOrNull { it.id == general.id || general.id in it.generalIds }
                ?: return ProtocolResult.Err(
                    "REAL_DUNGEON_FORMATION_MISSING",
                    "将领${general.name}没有可校验的配兵信息，已中断副本",
                    false
                )
            if (formation.status != FormationRuntimeStatus.IDLE) {
                return ProtocolResult.Ok(StepResult(
                    true,
                    "将领${general.name}编队非空闲，等待回闲后继续副本",
                    mapOf("phase" to "waiting-formation")
                ))
            }
            if ((formation.troopCount ?: 0) <= 0) {
                return ProtocolResult.Err("REAL_DUNGEON_TROOPS_EMPTY", "将领${general.name}没有可用兵力，已中断副本", false)
            }
        }

        val catalogResponse = runCatching {
            sendBinaryMappedGameHex(
                gameHttp,
                dm,
                buildDirectGameHex(0x1930, byteArrayOf()),
                "dungeon/catalog"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_DUNGEON_CATALOG_EXCEPTION", "读取副本目录异常：${it.message}", true)
        }
        if (!catalogResponse.ok || 0x8930 !in catalogResponse.responseOpcodes) {
            return ProtocolResult.Err("REAL_DUNGEON_CATALOG_UNCONFIRMED", "读取副本目录未收到0x8930", true)
        }
        val catalog = runCatching {
            DungeonProtocolShapes.parseCatalog(catalogResponse.responseHex.hexToBytesLocal())
        }.getOrElse {
            return ProtocolResult.Err("REAL_DUNGEON_CATALOG_INVALID", "副本目录解析失败：${it.message}", false)
        }
        val stageCode = runCatching {
            DungeonProtocolShapes.resolveStageCode(catalog, config.chapter, config.stage)
        }.getOrElse {
            return ProtocolResult.Err("REAL_DUNGEON_STAGE_INVALID", "副本章节/关卡无效：${it.message}", false)
        }

        val generalIds = selected.map { it.id }
        val prepare = sendDungeonCommand(
            gameHttp, dm, 0x1520,
            DungeonProtocolShapes.buildPreparePayload(generalIds, stageCode),
            expectedOpcode = 0x8520,
            phase = "dungeon/prepare"
        )
        if (prepare is ProtocolResult.Err || (prepare as ProtocolResult.Ok).value.success.not()) return prepare
        val expedition = sendDungeonCommand(
            gameHttp, dm, 0x1522,
            DungeonProtocolShapes.buildExpeditionPayload(generalIds, stageCode),
            expectedOpcode = 0x8522,
            phase = "dungeon/expedition"
        )
        if (expedition is ProtocolResult.Err || (expedition as ProtocolResult.Ok).value.success.not()) return expedition
        pendingDungeons[session.accountId] = PendingDungeon(
            generalIds, config.chapter, config.stage, config.boxPosition, System.currentTimeMillis()
        )
        return ProtocolResult.Ok(StepResult(
            true,
            "副本第${config.chapter + 1}章第${config.stage}关已发起",
            mapOf("phase" to "fighting", "stageCode" to stageCode.toString())
        ))
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
        if (expectedOpcode == 0x8522) {
            val receipt = runCatching {
                DungeonProtocolShapes.parseLaunchResponse(response.responseHex.hexToBytesLocal())
            }.getOrElse {
                return ProtocolResult.Err(
                    "REAL_DUNGEON_LAUNCH_RECEIPT_INVALID",
                    "$phase 0x8522解析失败：${it.message}",
                    false
                )
            }
            if (!receipt.success) {
                return ProtocolResult.Ok(StepResult(false, "$phase 被游戏服拒绝：${receipt.message}"))
            }
        } else if (expectedOpcode == 0x893E) {
            val receipt = runCatching {
                DungeonProtocolShapes.parseChestResponse(response.responseHex.hexToBytesLocal())
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
        } else if (requireZeroStatus && response.responseHex.take(2).toIntOrNull(16) != 0) {
            return ProtocolResult.Ok(StepResult(false, "$phase 被游戏服拒绝"))
        }
        return ProtocolResult.Ok(StepResult(true, "$phase 成功"))
    }

    override suspend fun runLossless(
        session: GameSession,
        config: LosslessConfig
    ): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.runLossless(session, config)
        if (!config.enabled) return ProtocolResult.Ok(StepResult(false, "无损任务未启用"))
        val rules = config.rules.filter { it.enabled }
        if (rules.isEmpty()) {
            return ProtocolResult.Err("REAL_LOSSLESS_RULE_MISSING", "无损没有启用的编队", false)
        }
        if (rules.any { it.generalIds.isEmpty() || it.generalIds.size > 5 || it.level !in 1..10 }) {
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

        val statusResponse = sendLosslessCommand(gameHttp, dm, 0x1900, LosslessProtocolShapes.QUERY_PAYLOAD, "lossless/status")
            ?: return ProtocolResult.Err("REAL_LOSSLESS_STATUS_EXCEPTION", "读取无损状态异常", true)
        if (!statusResponse.ok || 0x8900 !in statusResponse.responseOpcodes) {
            return ProtocolResult.Err("REAL_LOSSLESS_STATUS_UNCONFIRMED", "读取无损状态未收到0x8900", true)
        }
        val status = runCatching {
            LosslessProtocolShapes.parseStatus(statusResponse.responseHex.hexToBytesLocal())
        }.getOrElse {
            return ProtocolResult.Err("REAL_LOSSLESS_STATUS_PARSE_FAILED", "无损状态解析失败：${it.message}", false)
        }
        actionAudit?.invoke(
            "真实无损状态：phase=${status.phase} mode=${status.mode} " +
                "remaining=${status.remainingAttempts} stage=${status.stageId}"
        )

        if (status.phase == LosslessPhase.SETTLEMENT) {
            val response = sendLosslessCommand(
                gameHttp, dm, 0x1902, LosslessProtocolShapes.QUERY_PAYLOAD, "lossless/settlement"
            ) ?: return ProtocolResult.Err("REAL_LOSSLESS_SETTLEMENT_EXCEPTION", "无损结算请求异常", true)
            if (!response.ok || 0x8902 !in response.responseOpcodes) {
                return ProtocolResult.Err("REAL_LOSSLESS_SETTLEMENT_UNCONFIRMED", "无损结算未收到0x8902", true)
            }
            val settlement = runCatching {
                LosslessProtocolShapes.parseSettlement(response.responseHex.hexToBytesLocal())
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
                    "battleFailed" to settlement.battleFailed.toString()
                )
            ))
        }
        when (status.phase) {
            LosslessPhase.DAILY_DONE -> return ProtocolResult.Ok(StepResult(
                true, "今日无损次数已用完",
                mapOf("phase" to "daily-done", "attemptConsumed" to "false", "remainingAttempts" to "0")
            ))
            LosslessPhase.COOLDOWN -> return ProtocolResult.Ok(StepResult(
                true, "无损冷却中",
                mapOf(
                    "phase" to "cooldown",
                    "attemptConsumed" to "false",
                    "cooldownMillis" to (status.cooldownMillis ?: 0).toString()
                )
            ))
            LosslessPhase.FIGHTING -> return ProtocolResult.Ok(StepResult(
                true, "无损战斗进行中",
                mapOf("phase" to "fighting", "attemptConsumed" to "false")
            ))
            LosslessPhase.UNKNOWN -> return ProtocolResult.Err(
                "REAL_LOSSLESS_STATUS_UNKNOWN",
                "无损返回未知状态：mode=${status.mode} progress=${status.progressCode}",
                false
            )
            else -> Unit
        }

        val serverUsedAttempts = (LOSSLESS_SERVER_DAILY_LIMIT - status.remainingAttempts)
            .coerceIn(0, LOSSLESS_SERVER_DAILY_LIMIT)
        if (serverUsedAttempts >= config.dailyLimit.coerceAtMost(LOSSLESS_SERVER_DAILY_LIMIT)) {
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
        val rule = rules[cursor.mod(rules.size)]
        if (status.selectedLevel != rule.level) {
            val selected = selectLosslessLevel(gameHttp, dm, rule.level)
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
            gameHttp, dm, 0x1906, LosslessProtocolShapes.QUERY_PAYLOAD, "lossless/lineup"
        ) ?: return ProtocolResult.Err("REAL_LOSSLESS_LINEUP_EXCEPTION", "读取无损阵容异常", true)
        if (!lineupResponse.ok || 0x8906 !in lineupResponse.responseOpcodes) {
            return ProtocolResult.Err("REAL_LOSSLESS_LINEUP_UNCONFIRMED", "读取无损阵容未收到0x8906", true)
        }
        val lineup = runCatching {
            LosslessProtocolShapes.parseLineup(lineupResponse.responseHex.hexToBytesLocal())
        }.getOrElse {
            return ProtocolResult.Err("REAL_LOSSLESS_LINEUP_PARSE_FAILED", "无损阵容解析失败：${it.message}", false)
        }
        if (!lineup.success) {
            return ProtocolResult.Ok(StepResult(
                false, "游戏服拒绝返回无损阵容，状态=${lineup.status}",
                mapOf("phase" to "lineup-rejected", "attemptConsumed" to "false")
            ))
        }
        if (rule.level == 10) {
            val verdict = LosslessProtocolShapes.evaluateLevel10Guard(lineup)
            if (!verdict.qualified) {
                // A single alternate-level round trip rerolls the lineup. The next scheduler
                // tick re-reads and re-evaluates it; never dispatch an unqualified lineup.
                val alternate = selectLosslessLevel(gameHttp, dm, 7)
                if (alternate is ProtocolResult.Err || !(alternate as ProtocolResult.Ok).value.success) {
                    return ProtocolResult.Err(
                        "REAL_LOSSLESS_REROLL_SWITCH_FAILED",
                        "刷新10级无损阵容时切换7级失败",
                        false
                    )
                }
                val restored = selectLosslessLevel(gameHttp, dm, 10)
                if (restored is ProtocolResult.Err || !(restored as ProtocolResult.Ok).value.success) {
                    return ProtocolResult.Err(
                        "REAL_LOSSLESS_REROLL_RESTORE_FAILED",
                        "刷新10级无损阵容时切回10级失败",
                        false
                    )
                }
                return ProtocolResult.Ok(StepResult(
                    true,
                    "10级卫兵阵容不符合无损筛选条件，已安全刷新：${verdict.reason}",
                    mapOf(
                        "phase" to "lineup-rerolled",
                        "attemptConsumed" to "false",
                        "nextDelayMillis" to "4000"
                    )
                ))
            }
        }

        val monarch = when (val result = queryMonarch(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val roleId = monarch.roleId
            ?: return ProtocolResult.Err("REAL_LOSSLESS_ROLE_ID_MISSING", "无损出征缺少角色ID", false)
        val generals = when (val result = queryGenerals(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val selectedGenerals = rule.generalIds.map { id ->
            generals.firstOrNull { it.id == id }
                ?: return ProtocolResult.Err("REAL_LOSSLESS_GENERAL_NOT_FOUND", "无损未找到将领ID=$id", false)
        }
        selectedGenerals.forEach { general ->
            if (general.status == null) {
                return ProtocolResult.Err("REAL_LOSSLESS_GENERAL_STATUS_UNKNOWN", "无法确认将领${general.name}状态", false)
            }
            if (general.status != 0) {
                return ProtocolResult.Ok(StepResult(
                    true, "将领${general.name}未回闲，等待后再执行无损",
                    mapOf("phase" to "waiting-general", "attemptConsumed" to "false")
                ))
            }
            if (general.energy == null || general.energy <= 0) {
                return ProtocolResult.Ok(StepResult(
                    false, "将领${general.name}体力不足或无法确认",
                    mapOf("phase" to "energy-blocked", "attemptConsumed" to "false")
                ))
            }
        }
        val formations = when (val result = queryFormations(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        selectedGenerals.forEach { general ->
            val formation = formations.firstOrNull { it.id == general.id || general.id in it.generalIds }
                ?: return ProtocolResult.Err(
                    "REAL_LOSSLESS_FORMATION_MISSING",
                    "将领${general.name}没有可校验的配兵信息",
                    false
                )
            if (formation.status != FormationRuntimeStatus.IDLE) {
                return ProtocolResult.Ok(StepResult(
                    true, "将领${general.name}编队未回闲",
                    mapOf("phase" to "waiting-formation", "attemptConsumed" to "false")
                ))
            }
            if ((formation.troopCount ?: 0) <= 0) {
                return ProtocolResult.Err("REAL_LOSSLESS_TROOPS_EMPTY", "将领${general.name}没有可用兵力", false)
            }
        }

        val prepare = sendLosslessCommand(
            gameHttp, dm, 0x1520,
            LosslessProtocolShapes.buildPreparePayload(rule.generalIds, roleId),
            "lossless/prepare"
        ) ?: return ProtocolResult.Err("REAL_LOSSLESS_PREPARE_EXCEPTION", "无损预出征异常", true)
        if (!prepare.ok || 0x8520 !in prepare.responseOpcodes) {
            return ProtocolResult.Err("REAL_LOSSLESS_PREPARE_UNCONFIRMED", "无损预出征未收到0x8520", false)
        }
        val expedition = sendLosslessCommand(
            gameHttp, dm, 0x1522,
            LosslessProtocolShapes.buildExpeditionPayload(rule.generalIds, roleId),
            "lossless/expedition"
        ) ?: return ProtocolResult.Err("REAL_LOSSLESS_DISPATCH_EXCEPTION", "无损出征异常", true)
        if (!expedition.ok || 0x8522 !in expedition.responseOpcodes) {
            return ProtocolResult.Err("REAL_LOSSLESS_DISPATCH_UNCONFIRMED", "无损出征未收到0x8522", false)
        }
        val dispatch = BrushYellowDispatchResponseParser.parse(expedition.responseHex)
            ?: return ProtocolResult.Err("REAL_LOSSLESS_DISPATCH_PARSE_FAILED", "无损出征响应无法解析", false)
        if (dispatch.success != true) {
            return ProtocolResult.Ok(StepResult(
                false,
                dispatch.message.orEmpty().ifBlank { "游戏服拒绝无损出征" },
                mapOf("phase" to "dispatch-rejected", "attemptConsumed" to "true", "consumedTimes" to "1")
            ))
        }
        losslessRuleCursors[session.accountId] = (cursor + 1).mod(rules.size)
        return ProtocolResult.Ok(StepResult(
            true,
            "已派${selectedGenerals.joinToString(",") { it.name }}挑战${rule.level}级无损",
            mapOf(
                "phase" to "fighting",
                "attemptConsumed" to "true",
                "consumedTimes" to "1",
                "stageId" to lineup.stageId.toString()
            )
        ))
    }

    private fun selectLosslessLevel(
        gameHttp: String,
        dm: Long,
        level: Int
    ): ProtocolResult<LosslessSelectResult> {
        val response = sendLosslessCommand(
            gameHttp, dm, 0x1908,
            LosslessProtocolShapes.buildSelectLevelPayload(level),
            "lossless/select-$level"
        ) ?: return ProtocolResult.Err("REAL_LOSSLESS_SELECT_EXCEPTION", "选择${level}级无损异常", true)
        if (!response.ok || 0x8908 !in response.responseOpcodes) {
            return ProtocolResult.Err("REAL_LOSSLESS_SELECT_UNCONFIRMED", "选择${level}级无损未收到0x8908", false)
        }
        return runCatching {
            ProtocolResult.Ok(LosslessProtocolShapes.parseSelect(response.responseHex.hexToBytesLocal()))
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
        if (!session.isRealReadOnly()) return mock.queryInventory(session)
        val live = if (session.channelExtra["inventoryLiveRefreshAllowed"].asLooseBoolean() == true) {
            session.gameHttpOrNull()?.let { gameHttp ->
                session.dmOrNull()?.let { dm ->
                    runCatching { RealGameProtocolClient().refreshInventoryState(gameHttp, dm) }.getOrNull()
                }
            }
        } else null
        if (live != null) {
            return ProtocolResult.Ok(live.items.map { it.toInventoryItem() })
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

    private fun JSONObject.toInventoryItem(): InventoryItem? {
        val id = optLong("itemId", optLong("id", -1L))
        val count = optInt("count", 0)
        if (id < 0L || count <= 0) return null
        val name = optString("name").ifBlank { ItemDictionary.nameFor(id.toInt()) ?: "道具#$id" }
        return InventoryItem(
            id = id,
            name = name,
            type = normalizedInventoryType(name, optString("type")),
            quality = null,
            level = null,
            enhanced = false,
            equipped = false,
            count = count
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
        if (!session.isRealReadOnly()) return mock.useOrDiscardItem(session, itemId, action, count)
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
            InventoryProtocolShapes.parseActionResponse(response.responseHex.hexToBytesLocal())
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
        if (session.isRealReadOnly()) unrecovered("REAL_VIP_NOT_IMPLEMENTED", "真实 VIP 协议尚未接入") else mock.setVipFeature(session, config)

    override suspend fun surrenderOrReleaseGenerals(session: GameSession, config: SurrenderReleaseConfig): ProtocolResult<StepResult> =
        if (session.isRealReadOnly()) unrecovered("REAL_SURRENDER_RELEASE_NOT_IMPLEMENTED", "真实劝降/释放协议尚未接入") else mock.surrenderOrReleaseGenerals(session, config)

    override suspend fun sendGeneralToResourcePoint(session: GameSession, config: ResourcePointSendGeneralConfig): ProtocolResult<StepResult> =
        if (session.isRealReadOnly()) unrecovered("REAL_SEND_GENERAL_NOT_IMPLEMENTED", "真实资源点送将协议尚未接入") else mock.sendGeneralToResourcePoint(session, config)

    override suspend fun runAutoLoot(session: GameSession, config: AutoLootConfig): ProtocolResult<StepResult> =
        if (!session.isRealReadOnly()) {
            mock.runAutoLoot(session, config)
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
        val generals = when (val result = queryGenerals(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        val selected = generalIds.map { id ->
            generals.firstOrNull { it.id == id }
                ?: return ProtocolResult.Err("REAL_LOOT_GENERAL_NOT_FOUND", "掠夺未找到将领 ID=$id", false)
        }
        selected.forEach { general ->
            if (general.status == null) {
                return ProtocolResult.Err("REAL_LOOT_STATUS_UNKNOWN", "无法确认将领${general.name}状态", false)
            }
            if (general.status != 0) {
                return ProtocolResult.Ok(StepResult(
                    true, "将领${general.name}当前非闲，等待回闲后继续掠夺",
                    mapOf("phase" to "waiting-general")
                ))
            }
            if (general.energy == null) {
                return ProtocolResult.Err("REAL_LOOT_ENERGY_UNKNOWN", "无法确认将领${general.name}体力", false)
            }
            if (general.energy <= 0) {
                return ProtocolResult.Ok(StepResult(false, "将领${general.name}体力不足，掠夺已中断"))
            }
            if (config.fullLoyalty) {
                if (general.loyalty == null) {
                    return ProtocolResult.Err(
                        "REAL_LOOT_LOYALTY_UNKNOWN",
                        "勾选满忠但无法确认将领${general.name}忠诚度",
                        false
                    )
                }
                if (general.loyalty < 100) {
                    return ProtocolResult.Ok(StepResult(
                        true,
                        "将领${general.name}忠诚度${general.loyalty}/100，等待满忠后掠夺",
                        mapOf("phase" to "waiting-loyalty")
                    ))
                }
            }
        }
        var formations = when (val result = queryFormations(session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return result
        }
        if (config.fullTroops) {
            selected.forEach { general ->
                val formation = formations.firstOrNull { it.id == general.id || general.id in it.generalIds }
                    ?: return ProtocolResult.Err(
                        "REAL_LOOT_FORMATION_MISSING",
                        "将领${general.name}没有可校验的配兵信息",
                        false
                    )
                val targetCount = general.troopLimit
                    ?: return ProtocolResult.Err(
                        "REAL_LOOT_TROOP_LIMIT_UNKNOWN",
                        "勾选满兵但无法确认将领${general.name}带兵上限",
                        false
                    )
                if ((formation.troopCount ?: 0) < targetCount) {
                    val current = general.currentAssignedTroops()
                        ?: return ProtocolResult.Err(
                            "REAL_LOOT_TROOP_TYPE_UNKNOWN",
                            "勾选满兵但无法确认将领${general.name}当前兵种",
                            false
                        )
                    when (val refill = updateFormation(
                        session,
                        FormationConfig(
                            formationId = general.id,
                            generalIds = listOf(general.id),
                            autoAssignTroops = true,
                            troopType = current.typeCode.toString(),
                            troopCount = targetCount,
                            fillToMaxWhenAutoAssignDisabled = true
                        )
                    )) {
                        is ProtocolResult.Err -> return refill
                        is ProtocolResult.Ok -> if (!refill.value.success) {
                            return ProtocolResult.Ok(StepResult(
                                false,
                                "掠夺前补满${general.name}失败：${refill.value.message}",
                                refill.value.raw + ("phase" to "refill-failed")
                            ))
                        }
                    }
                }
            }
            formations = when (val result = queryFormations(session)) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> return result
            }
        }
        selected.forEach { general ->
            val formation = formations.firstOrNull { it.id == general.id || general.id in it.generalIds }
                ?: return ProtocolResult.Err("REAL_LOOT_FORMATION_MISSING", "将领${general.name}没有可校验的配兵信息", false)
            if (formation.status != FormationRuntimeStatus.IDLE) {
                return ProtocolResult.Ok(StepResult(
                    true, "将领${general.name}编队非空闲，等待回闲后继续掠夺",
                    mapOf("phase" to "waiting-formation")
                ))
            }
            if ((formation.troopCount ?: 0) <= 0) {
                return ProtocolResult.Err("REAL_LOOT_TROOPS_EMPTY", "将领${general.name}没有可用兵力", false)
            }
            if (config.fullTroops) {
                val targetCount = general.troopLimit
                    ?: return ProtocolResult.Err(
                        "REAL_LOOT_TROOP_LIMIT_UNKNOWN",
                        "勾选满兵但无法确认将领${general.name}带兵上限",
                        false
                    )
                if ((formation.troopCount ?: 0) < targetCount) {
                    return ProtocolResult.Err(
                        "REAL_LOOT_REFILL_NOT_CONFIRMED",
                        "补兵后仍未确认将领${general.name}满兵，禁止掠夺出征",
                        false
                    )
                }
            }
        }
        val query = runCatching {
            sendBinaryMappedGameHex(
                gameHttp, dm,
                buildDirectGameHex(0x1310, LootProtocolShapes.buildFiefListPayload(rule.playerName)),
                "loot/query-fiefs"
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_LOOT_QUERY_EXCEPTION", "查询目标封地异常：${it.message}", false)
        }
        actionAudit?.invoke("真实掠夺请求：查询${rule.playerName}封地 opcode=0x1310 http=${query.httpCode}")
        if (!query.ok || 0x8310 !in query.responseOpcodes) {
            return ProtocolResult.Err("REAL_LOOT_QUERY_FAILED", "查询目标封地未收到0x8310", false)
        }
        val fiefs = runCatching { LootProtocolShapes.parseFiefList(query.responseHex.hexToBytesLocal()) }
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
            gameHttp, dm, 0x1520,
            LootProtocolShapes.buildPreparePayload(generalIds, target.targetId),
            0x8520, "loot/prepare"
        )
        if (prepare is ProtocolResult.Err || !(prepare as ProtocolResult.Ok).value.success) return prepare
        val expedition = sendLootCommand(
            gameHttp, dm, 0x1522,
            LootProtocolShapes.buildExpeditionPayload(generalIds, target.targetId),
            0x8522, "loot/expedition"
        )
        if (expedition is ProtocolResult.Err || !(expedition as ProtocolResult.Ok).value.success) return expedition
        lootRuleCursors[session.accountId] = (ruleIndex + 1).mod(rules.size)
        return ProtocolResult.Ok(StepResult(
            true,
            "已派${selected.joinToString(",") { it.name }}立即掠夺${rule.playerName}的${target.name}",
            mapOf(
                "phase" to "launched",
                "targetId" to target.targetId.toString(),
                "targetName" to target.name,
                "fiefIndex" to target.index.toString(),
                "ruleIndex" to ruleIndex.toString()
            )
        ))
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
        if (opcode == 0x1522 && response.responseHex.take(2).toIntOrNull(16) != 0) {
            return ProtocolResult.Ok(StepResult(false, "$phase 被游戏服拒绝"))
        }
        return ProtocolResult.Ok(StepResult(true, "$phase 成功"))
    }

    override suspend fun scanAlarmAndMaybeWithdraw(
        session: GameSession,
        config: AlarmWithdrawConfig
    ): ProtocolResult<StepResult> {
        if (!session.isRealReadOnly()) return mock.scanAlarmAndMaybeWithdraw(session, config)
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
            detected.filter { seen.add(it.fingerprint) }
        }
        newEvents.filter { it.shouldNotify }.forEach { event ->
            alarmEventSink?.invoke(
                AlarmNotificationEvent(
                    accountId = session.accountId,
                    kind = event.kind,
                    text = event.text,
                    vibrate = event.vibrate
                )
            )
        }
        actionAudit?.invoke(
            "真实军情警报扫描：account=${session.accountId} detected=${detected.size} " +
                "new=${newEvents.size} notified=${newEvents.count { it.shouldNotify }} withdraw=false"
        )
        return ProtocolResult.Ok(
            StepResult(
                success = true,
                message = "$refreshSummary；真实军情警报扫描完成：新增${newEvents.size}条，通知${newEvents.count { it.shouldNotify }}条；自动撤防保持关闭",
                raw = mapOf(
                    "newEvents" to newEvents.size.toString(),
                    "notifiedEvents" to newEvents.count { it.shouldNotify }.toString(),
                    "withdrawDefense" to "false"
                )
            )
        )
    }

    override suspend fun runBulkToolAction(session: GameSession, action: BulkToolAction): ProtocolResult<StepResult> =
        if (session.isRealReadOnly()) unrecovered("REAL_BULK_TOOL_NOT_IMPLEMENTED", "真实批量工具协议尚未接入") else mock.runBulkToolAction(session, action)

    override suspend fun queryOpenServer(query: OpenServerQuery): ProtocolResult<OpenServerResult> = mock.queryOpenServer(query)

    override suspend fun searchDefendedCities(session: GameSession, config: CityDefenseSearchConfig): ProtocolResult<List<CitySearchResult>> =
        if (session.isRealReadOnly()) unrecovered("REAL_CITY_SEARCH_NOT_IMPLEMENTED", "真实城池搜索协议尚未接入") else mock.searchDefendedCities(session, config)

    override suspend fun searchTreasures(session: GameSession, config: TreasureFilterConfig): ProtocolResult<List<TreasureSearchResult>> =
        if (session.isRealReadOnly()) unrecovered("REAL_TREASURE_SEARCH_NOT_IMPLEMENTED", "真实宝藏搜索协议尚未接入") else mock.searchTreasures(session, config)

    override suspend fun applyLicense(config: LicenseConfig, action: LicenseAction): ProtocolResult<LicenseStatus> = mock.applyLicense(config, action)

    private fun GameSession.isRealReadOnly(): Boolean = sourceMode == 1

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
            val result = RealGameProtocolClient().refreshRoleState(gameHttp, dm, roleId)
            val bundle = result.toLiveStateBundle()
            liveStateCache[key] = bundle
            liveStateErrors.remove(key)
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
        channelExtra["dm"]?.parseLongFlexible()?.let { dm ->
            GameNetworkRouteRegistry.register(this, gameHttp, dm)
        }
        return gameHttp
    }

    private fun GameSession.dmOrNull(): Long? = channelExtra["dm"]?.parseLongFlexible()

    private fun executeRecoveredBrushYellowLiveAction(
        session: GameSession,
        formationId: Long,
        target: MapTarget
    ): ProtocolResult<BattleResult>? {
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
        val generalChunks = session.generalChunksForFormation(formationId)
        if (generalChunks.isEmpty()) {
            return ProtocolResult.Err(
                "REAL_ACTION_FORMATION_GENERAL_MISSING",
                "真实动作 gate 已开启，但 formationId=$formationId 未恢复可用将领 ID",
                retryable = false
            )
        }
        val targetHex = target.actionTargetHex()
        val payloadVariants = runCatching {
            BrushYellowDispatchPayloadBuilder.buildAllBrushYellowPayloadVariants(
                generalIdHexChunks = generalChunks,
                targetIdHex = targetHex
            )
        }.getOrElse {
            return ProtocolResult.Err("REAL_ACTION_PAYLOAD_BUILD_FAILED", "真实刷黄 payload 构造失败：${it.message}", retryable = false)
        }

        actionAudit?.invoke(
            "真实刷黄二进制 sender 准备发送：formation=$formationId target=${target.id} targetHex=$targetHex generals=${generalChunks.size} scope=brush-yellow gates=true variants=${payloadVariants.joinToString { it.variant.toString() }}"
        )

        var selectedPayloads: BrushYellowDispatchPayloads? = null
        var selectedPrepare: DirectBinaryResponse? = null
        var selectedExpedition: DirectBinaryResponse? = null
        var selectedParsed: BrushYellowDispatchResponse? = null
        val variantAttempts = mutableMapOf<String, String>()
        for (payloads in payloadVariants) {
            val variantPrefix = "variant${payloads.variant}"
            val prepare = runCatching {
                sendBinaryMappedGameHex(gameHttp, dm, payloads.preparePayload, phase = "prepare/${payloads.prepareOpcode}/p2=${payloads.variant}")
            }.getOrElse {
                actionAudit?.invoke("真实刷黄 prepare 异常：p2=${payloads.variant} ${it.message}")
                return ProtocolResult.Err("REAL_ACTION_PREPARE_EXCEPTION", "${payloads.prepareOpcode} 发送异常：${it.message}", retryable = false)
            }
            variantAttempts["${variantPrefix}PrepareHttpCode"] = prepare.httpCode.toString()
            variantAttempts["${variantPrefix}PrepareResponseHex"] = prepare.responseHex.take(512)
            actionAudit?.invoke(
                "真实刷黄 prepare 返回：p2=${payloads.variant} opcode=${payloads.prepareOpcode} http=${prepare.httpCode} bytes=${prepare.responseBytes} text=${prepare.textPreview.take(80)} hex=${prepare.responseHex.take(64)}"
            )
            if (!prepare.ok) {
                return ProtocolResult.Err(
                    "REAL_ACTION_PREPARE_HTTP_FAILED",
                    "${payloads.prepareOpcode} HTTP ${prepare.httpCode}: ${prepare.textPreview.take(160)}",
                    retryable = false
                )
            }

            val expedition = runCatching {
                sendBinaryMappedGameHex(gameHttp, dm, payloads.expeditionPayload, phase = "expedition/${payloads.expeditionOpcode}/p2=${payloads.variant}")
            }.getOrElse {
                actionAudit?.invoke("真实刷黄 expedition 异常：p2=${payloads.variant} ${it.message}")
                return ProtocolResult.Err("REAL_ACTION_EXPEDITION_EXCEPTION", "${payloads.expeditionOpcode} 发送异常：${it.message}", retryable = false)
            }
            // Native game responses can contain a compact 0x8522 status payload while the
            // decoded text preview also carries historical battle-report text.  If we parse
            // text first, a stale "消灭..." line can be misclassified as a success for a
            // different target and the saved-settings flow stops with "未匹配本次目标".
            // For direct binary brush-yellow actions the authoritative signal is the 0x8522
            // hex payload, especially status=0; only fall back to text if hex parsing is empty.
            val parsed = BrushYellowDispatchResponseParser.parse(responseHex = expedition.responseHex)
                ?: BrushYellowDispatchResponseParser.parse(responseText = expedition.textPreview)
            variantAttempts["${variantPrefix}ExpeditionHttpCode"] = expedition.httpCode.toString()
            variantAttempts["${variantPrefix}ExpeditionResponseHex"] = expedition.responseHex.take(512)
            variantAttempts["${variantPrefix}ParsedSuccess"] = parsed?.success?.toString() ?: "unknown"
            parsed?.message?.let { variantAttempts["${variantPrefix}ParsedMessage"] = it.take(160) }
            actionAudit?.invoke(
                "真实刷黄 expedition 返回：p2=${payloads.variant} opcode=${payloads.expeditionOpcode} http=${expedition.httpCode} bytes=${expedition.responseBytes} success=${parsed?.success ?: "unknown"} msg=${parsed?.message?.take(60) ?: ""} hex=${expedition.responseHex.take(64)}"
            )
            if (!expedition.ok) {
                return ProtocolResult.Err(
                    "REAL_ACTION_EXPEDITION_HTTP_FAILED",
                    "${payloads.expeditionOpcode} HTTP ${expedition.httpCode}: ${expedition.textPreview.take(160)}",
                    retryable = false
                )
            }
            selectedPayloads = payloads
            selectedPrepare = prepare
            selectedExpedition = expedition
            selectedParsed = parsed
            if (parsed?.success == true) break
            if (expedition.responseHex.lowercase() != "ff0000") break
        }

        val payloads = selectedPayloads ?: payloadVariants.first()
        val prepare = selectedPrepare ?: return ProtocolResult.Err("REAL_ACTION_PREPARE_EMPTY", "真实刷黄 prepare 未产生响应", retryable = false)
        val expedition = selectedExpedition ?: return ProtocolResult.Err("REAL_ACTION_EXPEDITION_EMPTY", "真实刷黄 expedition 未产生响应", retryable = false)
        val parsed = selectedParsed

        val success = parsed?.isSuccessForCurrentTarget(target) == true
        val contextualMessage = when {
            parsed?.success == true && !success ->
                "响应中出现战报成功文本，但未匹配本次目标坐标/ID，已按非本次成功处理"
            else -> parsed?.message
        }
        return ProtocolResult.Ok(
            BattleResult(
                success = success,
                consumedTimes = parsed?.consumedTimes ?: if (success) 1 else 0,
                raw = buildMap {
                    put("realActionNetworkAllowed", "true")
                    put("realActionSendReady", "true")
                    put("realActionScope", "brush-yellow")
                    put("sender", "native-wrapper-string")
                    put("sender", "direct-binary-game-command")
                    put("endpoint", gameHttp)
                    put("formationId", formationId.toString())
                    put("targetId", target.id.toString())
                    put("targetHex", targetHex)
                    put("payloadVariant", payloads.variant.toString())
                    put("attemptedPayloadVariants", payloadVariants.joinToString { it.variant.toString() })
                    put("preparePayload", payloads.preparePayload)
                    put("expeditionPayload", payloads.expeditionPayload)
                    put("prepareOpcode", payloads.prepareOpcode)
                    put("expeditionOpcode", payloads.expeditionOpcode)
                    put("prepareHttpCode", prepare.httpCode.toString())
                    put("expeditionHttpCode", expedition.httpCode.toString())
                    put("prepareResponseHex", prepare.responseHex.take(2048))
                    put("expeditionResponseHex", expedition.responseHex.take(2048))
                    put("prepareResponseText", prepare.textPreview.take(512))
                    put("expeditionResponseText", expedition.textPreview.take(512))
                    contextualMessage?.let { put("message", it) }
                    put("responseHex", expedition.responseHex.take(2048))
                    putAll(parsed?.toRawMap("expeditionParsed").orEmpty())
                    putAll(variantAttempts)
                    put("binaryMapping", "gameHex prefix/len stripped; opcode=0x1520/0x1522; payload starts with p2 + count; p2=0/1/2/3/4 variants attempted until success/non-ff0000")
                }
            )
        )
    }

    private fun BrushYellowDispatchResponse.isSuccessForCurrentTarget(target: MapTarget): Boolean {
        if (success != true) return false
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
        if (!config.autoAssignTroops && !config.fillToMaxWhenAutoAssignDisabled) {
            return ProtocolResult.Ok(StepResult(true, "配兵未启用，跳过真实 0x1226/0x1229", raw = mapOf("skipped" to "true")))
        }

        val raw = linkedMapOf<String, String>(
            "realActionNetworkAllowed" to "true",
            "realActionScope" to "brush-yellow",
            "troopType" to config.troopType,
            "troopCount" to config.troopCount.toString(),
            "generalIds" to generalIds.joinToString(","),
            "batchRefillOnly" to (!config.autoAssignTroops && config.fillToMaxWhenAutoAssignDisabled).toString()
        )
        var allAssignOk = true
        var assignedEnough = true
        if (config.autoAssignTroops) {
            val targetCode = soldierTypeCode(config.troopType)
            val currentGenerals = queryGeneralListForFormationStatus(session).associateBy { it.id }
            generalIds.forEach { generalId ->
                val current = currentGenerals[generalId]?.currentAssignedTroops()
                if (current != null && current.typeCode == targetCode && current.count >= config.troopCount) {
                    raw["assign.${generalId}.skipped"] = "already-satisfied"
                    raw["assign.${generalId}.assignedType"] = current.typeCode.toString()
                    raw["assign.${generalId}.assignedCount"] = current.count.toString()
                    raw["assign.${generalId}.message"] = "当前将领已满足 ${config.troopCount}${config.troopType}，跳过 0x1226"
                    actionAudit?.invoke(
                        "真实配兵 0x1226 跳过：general=$generalId 当前=${current.count}${config.troopType}(code=${current.typeCode}) 已满足目标 ${config.troopCount}${config.troopType}"
                    )
                    return@forEach
                }
                val payload = buildAssignTroopsPayload(generalId, targetCode, config.troopCount, group = 0)
                val gameHex = buildDirectGameHex(0x1226, payload)
                val response = runCatching {
                    sendBinaryMappedGameHex(gameHttp, dm, gameHex, phase = "formation/1226")
                }.getOrElse {
                    actionAudit?.invoke("真实配兵 0x1226 异常：general=$generalId ${it.message}")
                    return ProtocolResult.Err("REAL_FORMATION_ASSIGN_EXCEPTION", "0x1226 发送异常：${it.message}", retryable = false)
                }
                val opcodeConfirmed = 0x8226 in response.responseOpcodes
                val parsed = Formation122xResponseParser.parse8226(response.responseHex)
                val responseMatchesGeneral = parsed.generalId == generalId
                val assignmentConfirmed = response.ok && opcodeConfirmed && parsed.success &&
                    responseMatchesGeneral
                raw["assign.${generalId}.payloadHex"] = payload.toHex()
                raw["assign.${generalId}.http"] = response.httpCode.toString()
                raw["assign.${generalId}.responseOpcodes"] =
                    response.responseOpcodes.joinToString { "0x${it.toString(16)}" }
                raw["assign.${generalId}.responseHex"] = response.responseHex.take(512)
                raw["assign.${generalId}.status"] = parsed.status?.toString().orEmpty()
                raw["assign.${generalId}.previousType"] = parsed.previousType?.toString().orEmpty()
                raw["assign.${generalId}.previousCount"] = parsed.previousCount?.toString().orEmpty()
                raw["assign.${generalId}.assignedType"] = parsed.assignedType?.toString().orEmpty()
                raw["assign.${generalId}.assignedCount"] = parsed.assignedCount?.toString().orEmpty()
                raw["assign.${generalId}.message"] = when {
                    !response.ok -> "0x1226 HTTP ${response.httpCode}"
                    !opcodeConfirmed -> "0x1226 未收到 0x8226"
                    !responseMatchesGeneral -> "0x8226 将领ID不匹配：${parsed.generalId}"
                    else -> parsed.message
                }
                actionAudit?.invoke(
                    "真实配兵 0x1226 返回：general=$generalId target=${config.troopCount}${config.troopType} " +
                        "confirmed=$assignmentConfirmed previous=${parsed.previousCount} actual=${parsed.assignedCount} " +
                        "opcodes=${response.responseOpcodes.joinToString { "0x${it.toString(16)}" }} http=${response.httpCode}"
                )
                allAssignOk = allAssignOk && assignmentConfirmed
                if (parsed.assignedType != null && parsed.assignedCount != null) {
                    assignedEnough = assignedEnough && parsed.assignedType == targetCode && parsed.assignedCount >= config.troopCount
                } else {
                    assignedEnough = false
                }
            }

            if (!allAssignOk || !assignedEnough) {
                val message = if (!assignedEnough) {
                    "真实配兵未达到配置：需要 ${config.troopCount}${config.troopType}；未发送 0x1229"
                } else {
                    "真实配兵 0x1226 未取得完整 0x8226 确认；未发送 0x1229"
                }
                return ProtocolResult.Ok(StepResult(false, message, raw))
            }
        }

        val refillPayload = buildRefillPayload(generalIds)
        val refillResponse = runCatching {
            sendBinaryMappedGameHex(gameHttp, dm, buildDirectGameHex(0x1229, refillPayload), phase = "formation/1229")
        }.getOrElse {
            actionAudit?.invoke("真实补兵 0x1229 异常：${it.message}")
            return ProtocolResult.Err("REAL_FORMATION_REFILL_EXCEPTION", "0x1229 发送异常：${it.message}", retryable = false)
        }
        val refillOpcodeConfirmed = 0x8229 in refillResponse.responseOpcodes
        val refillParsed = Formation122xResponseParser.parse8229(refillResponse.responseHex)
        val refillIds = refillParsed.entries.map { it.generalId }.toSet()
        val refillEntriesComplete = generalIds.all { it in refillIds }
        raw["refill.payloadHex"] = refillPayload.toHex()
        raw["refill.http"] = refillResponse.httpCode.toString()
        raw["refill.responseOpcodes"] =
            refillResponse.responseOpcodes.joinToString { "0x${it.toString(16)}" }
        raw["refill.responseHex"] = refillResponse.responseHex.take(512)
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
                pre.responseHex.hexToBytesLocal(),
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
            GeneralProtocolShapes.parseHealResponse(heal.responseHex.hexToBytesLocal())
        }.getOrElse {
            return ProtocolResult.Err(
                "REAL_HEAL_RECEIPT_INVALID",
                "0x8230 治疗回执解析失败：${it.message}",
                false
            )
        }
        actionAudit?.invoke("真实治疗 0x1230 返回：general=$generalId fief=$fiefId success=${parsed.success} msg=${parsed.message} http=${heal.httpCode}")
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
        if (raw["source"] == "8540-structured" && !rawRecord.isNullOrBlank() && rawRecord.length >= 20) {
            // 2026-07-08 live matrix: 山贼 dispatch with actionType=10 was accepted when
            // using the first 10 bytes of the 0x8540 record and taking its trailing 8 bytes
            // as the target long (id low bytes + UTF name length). Desktop keeps both this
            // and first-8-id candidates; mobile uses the accepted candidate first.
            return rawRecord.take(20).takeLast(16)
        }
        if (raw["source"] == "8540-structured" && !rawRecord.isNullOrBlank() && rawRecord.length >= 16) {
            // Conservative fallback: structured 0x8540 records start with the 8-byte
            // target id followed by the UTF name length.
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
        directBinaryTransport?.let { return it(gameHttp, dm, gameHex, phase) }
        val normalized = gameHex.filterNot { it.isWhitespace() }.lowercase()
        require(normalized.startsWith("000000000000000000")) { "unsupported gameHex prefix for $phase" }
        val body = normalized.drop(18)
        require(body.length >= 6) { "gameHex too short for $phase" }
        val opcode = body.substring(2, 6).toInt(16)
        val payload = body.drop(6).hexToBytesLocal()
        val requestBody = makeBinaryGamePacket(dm, opcode, payload)
        val conn = (GameNetworkRouteRegistry.route(gameHttp, dm).open(URL(gameHttp)) as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 25_000
            requestMethod = "POST"
            doOutput = true
            setRequestProperty("Content-Type", "application/octet-stream")
            setRequestProperty("User-Agent", "DWPMClone/1.0 direct-binary-action")
            setFixedLengthStreamingMode(requestBody.size)
        }
        conn.outputStream.use { it.write(requestBody) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val bytes = stream?.use { it.readBytes() } ?: ByteArray(0)
        val packets = runCatching { parseBinaryGameResponse(bytes) }.getOrDefault(emptyList())
        val responsePayload = packets.joinToString(separator = "") { it.payload.toHex() }
        val responseText = packets.joinToString(separator = " ") { it.payload.toPrintableTextPreview() }
        return DirectBinaryResponse(
            phase = phase,
            httpCode = code,
            ok = code in 200..299,
            responseBytes = bytes.size,
            responseHex = responsePayload.ifBlank { bytes.toHex() },
            textPreview = responseText.ifBlank { bytes.toPrintableTextPreview() },
            responseOpcodes = packets.map { it.opcode }
        )
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
        val body = fields.lx!! + fields.key!! + gameHex + fields.lb!!
        val bodyBytes = body.toByteArray(Charsets.UTF_8)
        val conn = (URL(gameHttp).openConnection(Proxy.NO_PROXY) as HttpURLConnection).apply {
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
        val mode = channelExtra["recoveredReadOnlyScanMode"]?.uppercase().orEmpty()
        val threadCount = channelExtra["recoveredReadOnlyThreadCount"]?.toIntOrNull()?.coerceAtLeast(1) ?: 1
        val limit = channelExtra["recoveredReadOnlyScanLimit"]?.toIntOrNull()?.coerceAtLeast(1)
        val requests = when (mode) {
            "FULL", "FULL_SCAN" -> RecoveredMapScanPlanner.fullScanRequestsDeduped(kind, threadCount)
            else -> listOf(RecoveredMapScanPlanner.singleRequest(kind, start))
        }
        return limit?.let { requests.take(it) } ?: requests
    }

    private fun GameSession.recoveredMineReadOnlyRequests(
        config: MineConfig
    ): List<RecoveredSearchRequest> {
        val requests = RecoveredMapScanPlanner.mineScopeRequests(
            RecoveredSearchKind.RESOURCE_POINT_041542,
            config.start,
            config.searchScope
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
                val responseSuccess = response?.isSuccessForCurrentTarget(target)
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
        if (channelExtra["allowRecoveredGeneralFallbackFormation"].asLooseBoolean() != true) return emptyList()
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
                    troopCount = general.troopLimit,
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
                raw = obj.toStringMap()
            )
        }
    }

    private fun List<MineSearchResult>.filterByMineConfig(config: MineConfig): List<MineSearchResult> =
        asSequence()
            .filter { config.selectedMineTypes.isEmpty() || it.mineType in config.selectedMineTypes }
            .filter { !config.onlyEmptyMine || it.isEmpty }
            .filter { !config.onlyDefendedMine || (!it.isEmpty || (it.defenseCount ?: 0) > 0) }
            .toList()

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
        val payloads = BrushYellowDispatchPayloadBuilder.buildBrushYellowPayloads(chunks, normalizedTargetHex)
        val passiveWirePlan = BrushYellowPassiveWireDryRunPlanner.plan(
            generalIds = chunks,
            targetWireId = normalizedTargetHex,
            includeBatchRefill = true
        )
        val wrapperFields = RecoveredNativeWrapperFieldExtractor.from((session?.channelExtra ?: emptyMap()) + toStringMap() + (rawObject?.toStringMap() ?: emptyMap()))
        val prepareWrapperPlan = RecoveredNativeActionWrapperPlanner.plan(payloads.preparePayload, wrapperFields)
        val expeditionWrapperPlan = RecoveredNativeActionWrapperPlanner.plan(payloads.expeditionPayload, wrapperFields)
        return mapOf(
            "preparePayload" to payloads.preparePayload,
            "expeditionPayload" to payloads.expeditionPayload,
            "payloadEvidence" to "shuahuang actionType=10: 15200a0 + 15220a0",
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
        private const val LOSSLESS_SERVER_DAILY_LIMIT: Int = 5
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

package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.protocol.GameHexDryRunDescriptor
import com.example.dwpmclone.domain.protocol.GameHexDryRunParser
import com.example.dwpmclone.domain.protocol.ItemDictionary
import com.example.dwpmclone.domain.protocol.EquipmentTemplateDictionary
import com.example.dwpmclone.domain.protocol.ExecutionRevokedBeforeNetworkException
import com.example.dwpmclone.domain.protocol.LootProtocolShapes
import com.example.dwpmclone.domain.protocol.LootTargetFief
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.protocol.MineSearchResult
import com.example.dwpmclone.domain.protocol.ResourcePointSearchResponseParser
import com.example.dwpmclone.domain.protocol.TargetSearchResponseParser
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.Charset
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Real read-only protocol client restored from /帝王三国接口.md.
 *
 * Implemented request chain:
 * 1) passport /common/area/list.action
 * 2) passport /common/area/enter.action
 * 3) game 0x1003 loginBaseinfo
 * 4) game 0x1004 gameLogin
 * 5) game 0x1016 init aggregate, used only to refresh the same read-only role state.
 *
 * This class deliberately does not implement any state-changing game action.
 */
class RealGameProtocolClient(
    /** Dynamic service ownership gate; interactive callers and parser tests default to enabled. */
    private val executionAllowed: () -> Boolean = { true }
) {
    data class Area(
        val target: String,
        val areaId: String,
        val areaName: String,
        val serverUrl: String,
        val resUrl: String,
        val serverVer: String,
        val lowestVer: String,
        val serverStatus: String,
        val updateUrl: String,
        val flag: String,
        val clientVersion: String,
        val serverKey: String,
        val raw: String
    )

    data class RoleBrief(
        val roleId: Long,
        val roleName: String,
        val levelCandidate: Int,
        val country: String,
        val title: String
    )

    data class RoleState(
        val roleId: Long,
        val roleName: String,
        val level: Int,
        val copper: Long,
        val food: Long,
        val prestige: Long,
        val prestigePrevThreshold: Long,
        val prestigeNextThreshold: Long,
        val copperPerHour: Int,
        val foodPerHour: Int,
        val populationCurrent: Long,
        val populationCap: Long,
        val fiefLimit: Int,
        val generalLimit: Int,
        val resourcePointCurrent: Int,
        val resourcePointCap: Int,
        val officeFieldFlag: Int?,
        val officeIdRaw: Int?,
        val officeIdUnsigned: Int?,
        val officeName: String,
        val serverTimeMillis: Long,
        val sourceOpcode: String,
        val payloadByteCount: Int,
        val parsedHeadByteCount: Int,
        val tailByteCount: Int,
        val payloadHex: String,
        val tailHex: String,
        val tailUtf8Preview: String
    )

    data class LiveStateRefreshResult(
        val state: RoleState,
        val responseOpcodes: List<String>,
        val refreshedAtMillis: Long
    )

    data class InventoryStack(
        val itemId: Int,
        val name: String,
        val count: Int,
        val typeLabel: String?,
        val nameSource: String,
        val rawTailHex: String
    )

    data class InventoryEquipment(
        val instanceId: Long,
        val templateId: Int,
        val name: String,
        val level: Int,
        val typeCode: Int,
        val famous: Boolean,
        val quality: Int,
        val strengthen: Int,
        val extraText: String,
        val attributes: List<Int>,
        val rawHex: String
    )

    data class InventoryState(
        val capacity: Int,
        val itemCount: Int,
        val items: List<InventoryStack>,
        val equipment: List<InventoryEquipment>,
        val equipmentParseError: String?,
        val sourceOpcode: String,
        val payloadByteCount: Int,
        val payloadHex: String,
        val parsedItemByteCount: Int,
        val tailHex: String
    )

    data class LoginResult(
        val username: String,
        val session: String,
        val userId: String,
        val accountWithSuffix: String?,
        val area: Area,
        val dm: Long,
        val roles: List<RoleBrief>,
        val selectedRole: RoleBrief,
        val state: RoleState,
        val responseOpcodes: List<String>,
        val syncedAt: String,
        val inventoryState: InventoryState?,
        val dailyActivityState: DailyActivityState?,
        val ownedFiefLocations: List<LootTargetFief>,
        val ownedFiefLocationError: String?
    )

    data class RecoveredReadOnlyGameHexPlan(
        val descriptor: GameHexDryRunDescriptor,
        val opcode: Int?,
        val opcodeHex: String?,
        val payloadHex: String,
        val payloadByteCount: Int?,
        val currentBinaryRequestHex: String?,
        val canBuildCurrentBinaryRequest: Boolean,
        val networkSendAllowed: Boolean,
        val blocker: String
    )

    data class RecoveredReadOnlyExecutionResult(
        val plan: RecoveredReadOnlyGameHexPlan,
        val networkSendAttempted: Boolean,
        val success: Boolean,
        val code: String,
        val message: String,
        val responseOpcodes: List<String> = emptyList(),
        val responsePayloadHex: String = "",
        val parsedTargets: List<MapTarget> = emptyList(),
        val parsedMines: List<MineSearchResult> = emptyList()
    )

    data class Heartbeat3110Result(
        val responseOpcodes: List<String>,
        val responsePayloadHex: String
    )

    fun loginAndFetchState(username: String, password: String, serverQuery: String): LoginResult {
        val passportText = httpGet(
            PASSPORT + "common/area/list.action",
            mapOf(
                "username" to username,
                "password" to password,
                "channelId" to CHANNEL_NUM,
                "source" to SOURCE,
                "cType" to CTYPE,
                "cVersion" to VERSION,
                "gameKey" to GAME_KEY,
                "target" to TARGETS
            )
        )
        val lines = passportText.lineSequence().map { it.trim() }.filter { it.isNotEmpty() }.toList()
        require(lines.isNotEmpty()) { "passport 未返回内容" }
        val head = lines.first().split('`')
        require(head.size >= 2) { "passport 首行格式异常：${lines.first()}" }
        val session = head[0]
        val userId = head[1]
        val accountWithSuffix = runCatching {
            httpGet(
                PASSPORT + "system/user/validate.action",
                mapOf("session" to session, "target" to "1,2")
            ).trim().split('`').getOrNull(1)
        }.getOrNull()

        val areas = lines.drop(1).mapNotNull { parseAreaLine(it) }
        require(areas.isNotEmpty()) { "passport 未返回区服列表" }
        val area = selectArea(areas, serverQuery)
        val enter = httpGet(
            PASSPORT + "common/area/enter.action",
            mapOf("session" to session, "areaKey" to area.serverKey)
        ).trim()
        require(enter == "1") { "进入区服失败：$enter（${area.areaName}/${area.serverKey}）" }

        val gameHttp = area.serverUrl.trimEnd('/') + GAME_PATH
        val loginPayload = PacketWriter().apply {
            utf(userId)
            utf(session)
            utf(CHANNEL_NUM)
        }.toByteArray()
        val loginPackets = postGame(gameHttp, listOf(GameCommand(0x1003, loginPayload)), dm = 0L)
        val p8003 = loginPackets.firstOrNull { it.opcode == 0x8003 }
            ?: error("0x1003 未返回 0x8003，实际=${loginPackets.map { it.hexOpcode() }}")
        val loginInfo = parse8003(p8003.payload)
        require(loginInfo.status == 0) { "游戏登录基础信息失败：${loginInfo.message}" }
        require(loginInfo.roles.isNotEmpty()) { "账号下没有角色" }
        val selectedRole = loginInfo.roles.getOrNull(loginInfo.selectedIndex.coerceAtLeast(0)) ?: loginInfo.roles.first()
        // 0x1003 回执后才能确定角色 ID。从此处绑定后续登录同步请求，
        // 让手机端刚登录完就能像电脑端一样显示接口状态点。
        val previousHealthAccountId = GameRequestHealthSink.currentAccountId()
        GameRequestHealthSink.bindAccount(selectedRole.roleId)
        try {

        val statePackets1004 = postGame(
            gameHttp,
            listOf(GameCommand(0x1004, PacketWriter().apply { long(-1L) }.toByteArray())),
            dm = loginInfo.dm
        )
        val state1004 = statePackets1004.firstOrNull { it.opcode == 0x8004 }?.let {
            parse8004Head(it.payload, "0x1004/0x8004")
        }

        val initPackets = postGame(
            gameHttp,
            listOf(GameCommand(0x1016, PacketWriter().apply { long(selectedRole.roleId) }.toByteArray())),
            dm = loginInfo.dm
        )
        val state1016 = initPackets.firstOrNull { it.opcode == 0x8004 }?.let {
            parse8004Head(it.payload, "0x1016/0x8004")
        }
        val state = state1016 ?: state1004 ?: error("0x1004/0x1016 均未返回 0x8004 角色状态")
        val inventoryPackets = runCatching {
            postGame(gameHttp, listOf(GameCommand(0x1104, byteArrayOf(0x00))), dm = loginInfo.dm)
        }.getOrElse { emptyList() }
        val inventoryState = inventoryPackets.firstOrNull { it.opcode == 0x8104 }?.let {
            parse8104Inventory(it.payload, "0x1104/0x8104")
        }
        // Desktop parity: read 0x6200 once during login for role-page daily treasure
        // progress. Failure remains non-fatal and never creates a repeated request loop.
        val dailyActivityPackets = runCatching {
            postGame(gameHttp, listOf(GameCommand(0x6200, byteArrayOf())), dm = loginInfo.dm)
        }.getOrElse { emptyList() }
        val dailyActivityState = dailyActivityPackets.firstOrNull { it.opcode == 0xE200 }?.let {
            runCatching {
                DailyActivityE200Parser.parse(it.payload, "live/0x6200/0xe200")
            }.getOrNull()
        }
        var ownedFiefLocationError: String? = null
        val ownedFiefPackets = runCatching {
            postGame(
                gameHttp,
                listOf(GameCommand(0x1310, LootProtocolShapes.buildRaidFiefListPayload(state.roleName))),
                dm = loginInfo.dm
            )
        }.getOrElse { error ->
            ownedFiefLocationError = error.message ?: error::class.java.simpleName
            emptyList()
        }
        val ownedFiefLocations = ownedFiefPackets.firstOrNull { it.opcode == 0x8310 }?.let { packet ->
            runCatching { LootProtocolShapes.parseFiefList(packet.payload) }
                .onFailure { error ->
                    ownedFiefLocationError = "0x8310封地坐标解析失败：${error.message ?: error::class.java.simpleName}"
                }
                .getOrDefault(emptyList())
        } ?: emptyList<LootTargetFief>().also {
            if (ownedFiefLocationError == null) {
                ownedFiefLocationError = "0x1310未返回0x8310封地坐标"
            }
        }
        val allOpcodes = (
            loginPackets + statePackets1004 + initPackets +
                inventoryPackets + dailyActivityPackets + ownedFiefPackets
            ).map { it.hexOpcode() }

        return LoginResult(
            username = username,
            session = session,
            userId = userId,
            accountWithSuffix = accountWithSuffix,
            area = area,
            dm = loginInfo.dm,
            roles = loginInfo.roles,
            selectedRole = selectedRole,
            state = state,
            responseOpcodes = allOpcodes,
            syncedAt = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA).format(Date()),
            inventoryState = inventoryState,
            dailyActivityState = dailyActivityState,
            ownedFiefLocations = ownedFiefLocations,
            ownedFiefLocationError = ownedFiefLocationError
        )
        } finally {
            if (previousHealthAccountId != null) {
                GameRequestHealthSink.bindAccount(previousHealthAccountId)
            } else {
                GameRequestHealthSink.clearAccount()
            }
        }
    }


    fun refreshRoleState(gameHttp: String, dm: Long, roleId: Long): LiveStateRefreshResult {
        val packets = postGame(
            gameHttp,
            listOf(GameCommand(0x1016, PacketWriter().apply { long(roleId) }.toByteArray())),
            dm = dm
        )
        val p8004 = packets.firstOrNull { it.opcode == 0x8004 }
            ?: error(
                "0x1016 未返回 0x8004，实际=${packets.map { it.hexOpcode() }}" +
                    packets.joinToString(prefix = "，payload=", separator = ";") { packet ->
                        "${packet.hexOpcode()}:${packet.payload.toUtf8Preview(120)}"
                    }
            )
        return LiveStateRefreshResult(
            state = parse8004Head(p8004.payload, "live/0x1016/0x8004"),
            responseOpcodes = packets.map { it.hexOpcode() },
            refreshedAtMillis = System.currentTimeMillis()
        )
    }

    fun refreshInventoryState(gameHttp: String, dm: Long): InventoryState {
        val packets = postGame(
            gameHttp,
            listOf(GameCommand(0x1104, byteArrayOf(0x00))),
            dm
        )
        val response = packets.firstOrNull { it.opcode == 0x8104 }
            ?: error("0x1104 未返回 0x8104，实际=${packets.map { it.hexOpcode() }}")
        return parse8104Inventory(response.payload, "live/0x1104/0x8104")
    }

    /**
     * Confirmed read-only heartbeat/status query observed in live captures.
     * Request: 0x3110 payload 01 00; expected response: 0xa110.
     */
    fun refreshHeartbeat3110(gameHttp: String, dm: Long): Heartbeat3110Result {
        val packets = postGame(
            gameHttp,
            listOf(GameCommand(0x3110, byteArrayOf(0x01, 0x00))),
            dm
        )
        val response = packets.firstOrNull { it.opcode == 0xa110 }
            ?: error("0x3110 未返回 0xa110，实际=${packets.map { it.hexOpcode() }}")
        return Heartbeat3110Result(
            responseOpcodes = packets.map { it.hexOpcode() },
            responsePayloadHex = response.payload.toHex()
        )
    }

    internal fun describeRecoveredGameHex(gameHex: String): GameHexDryRunDescriptor =
        GameHexDryRunParser.describe(gameHex)

    /**
     * Guarded bridge from 小黄点 recovered gameHex to the self-developed binary
     * GameCommand envelope. This is intentionally build-only: the returned request
     * bytes are for audit/dry-run and are not sent until a response parser and an
     * explicit live gate are added.
     */
    internal fun planRecoveredReadOnlyGameHex(
        gameHex: String,
        dm: Long,
        allowedOpcodes: Set<Int> = READ_ONLY_GAME_HEX_OPCODE_ALLOWLIST
    ): RecoveredReadOnlyGameHexPlan {
        val descriptor = describeRecoveredGameHex(gameHex)
        val opcode = descriptor.opcodeHex?.toIntOrNull(radix = 16)
        val allowListed = opcode != null && opcode in allowedOpcodes
        if (!descriptor.binaryCommandCandidate) {
            return RecoveredReadOnlyGameHexPlan(
                descriptor = descriptor,
                opcode = opcode,
                opcodeHex = descriptor.opcodeHex,
                payloadHex = descriptor.payloadHex,
                payloadByteCount = descriptor.payloadByteCount,
                currentBinaryRequestHex = null,
                canBuildCurrentBinaryRequest = false,
                networkSendAllowed = false,
                blocker = descriptor.blocker
            )
        }
        if (!allowListed) {
            return RecoveredReadOnlyGameHexPlan(
                descriptor = descriptor,
                opcode = opcode,
                opcodeHex = descriptor.opcodeHex,
                payloadHex = descriptor.payloadHex,
                payloadByteCount = descriptor.payloadByteCount,
                currentBinaryRequestHex = null,
                canBuildCurrentBinaryRequest = false,
                networkSendAllowed = false,
                blocker = "只读 opcode 0x${descriptor.opcodeHex} 尚未进入真机候选白名单；当前仅允许 0x1540 找黄/地图扫描与 0x1542 找矿/资源点扫描"
            )
        }

        val payload = descriptor.payloadHex.hexToBytes()
        val concreteOpcode = requireNotNull(opcode) { "allow-listed opcode must not be null" }
        val requestBody = makePacket(listOf(GameCommand(concreteOpcode, payload)), dm)
        return RecoveredReadOnlyGameHexPlan(
            descriptor = descriptor,
            opcode = opcode,
            opcodeHex = descriptor.opcodeHex,
            payloadHex = descriptor.payloadHex,
            payloadByteCount = payload.size,
            currentBinaryRequestHex = requestBody.toHex(),
            canBuildCurrentBinaryRequest = true,
            networkSendAllowed = false,
            blocker = "已构建当前二进制 GameCommand 候选，但网络发送仍关闭：需要 0x1540/0x1542 响应 parser、真机 feature gate 与审计日志"
        )
    }

    /**
     * Default-off live gate for recovered read-only searches.
     *
     * This only permits the allow-listed 0x1540/0x1542 search opcodes. State-changing
     * actions and expedition opcodes are rejected before any network attempt. The method
     * stays closed unless the caller explicitly passes liveGate=true.
     */
    internal fun executeRecoveredReadOnlyGameHex(
        gameHttp: String,
        dm: Long,
        gameHex: String,
        liveGate: Boolean = false
    ): RecoveredReadOnlyExecutionResult {
        val plan = planRecoveredReadOnlyGameHex(gameHex, dm)
        if (!plan.canBuildCurrentBinaryRequest || plan.opcode == null) {
            return RecoveredReadOnlyExecutionResult(
                plan = plan,
                networkSendAttempted = false,
                success = false,
                code = "READ_ONLY_GAME_HEX_NOT_ALLOWED",
                message = plan.blocker
            )
        }
        if (!liveGate) {
            return RecoveredReadOnlyExecutionResult(
                plan = plan,
                networkSendAttempted = false,
                success = false,
                code = "READ_ONLY_LIVE_GATE_DISABLED",
                message = "041540/041542 真实只读发送 gate 默认关闭；需要显式 liveGate=true、真机审计日志和响应校准后才能发送"
            )
        }
        if (gameHttp.isBlank()) {
            return RecoveredReadOnlyExecutionResult(
                plan = plan,
                networkSendAttempted = false,
                success = false,
                code = "READ_ONLY_GAME_HTTP_MISSING",
                message = "缺少 gameHttp，不能执行真实只读请求"
            )
        }

        val payload = plan.payloadHex.hexToBytes()
        val packets = postGame(gameHttp, listOf(GameCommand(plan.opcode, payload)), dm)
        val responseHex = packets.joinToString(separator = "") { it.payload.toHex() }
        // Match desktop semantics: only 0x8540/0x8542 payloads belong to the map
        // parser. Concatenating heartbeat/status payloads in front of them can shift the
        // structured header and silently force the old marker fallback.
        val targets = if (plan.opcode == 0x1540) {
            packets.asSequence()
                .filter { it.opcode == 0x8540 }
                .flatMap { TargetSearchResponseParser.parse(it.payload.toHex()).asSequence() }
                .distinctBy { it.id to it.coordinate }
                .toList()
        } else {
            emptyList()
        }
        val mines = if (plan.opcode == 0x1542) {
            packets.asSequence()
                .filter { it.opcode == 0x8542 }
                .flatMap { ResourcePointSearchResponseParser.parse(it.payload.toHex()).asSequence() }
                .distinctBy { it.id to it.coordinate }
                .toList()
        } else {
            emptyList()
        }
        return RecoveredReadOnlyExecutionResult(
            plan = plan,
            networkSendAttempted = true,
            success = true,
            code = "READ_ONLY_EXECUTED",
            message = "已执行 allow-listed 只读查询；parsedTargets=${targets.size}, parsedMines=${mines.size}",
            responseOpcodes = packets.map { it.hexOpcode() },
            responsePayloadHex = responseHex,
            parsedTargets = targets,
            parsedMines = mines
        )
    }

    internal fun parseAreaLine(line: String): Area? {
        val p = line.split('`')
        if (p.size < 12) return null
        return Area(
            target = p[0], areaId = p[1], areaName = p[2], serverUrl = p[3], resUrl = p[4],
            serverVer = p[5], lowestVer = p[6], serverStatus = p[7], updateUrl = p[8],
            flag = p[9], clientVersion = p[10], serverKey = p[11], raw = line
        )
    }

    internal fun selectArea(areas: List<Area>, query: String): Area {
        val normalizedQuery = normalize(query.ifBlank { "周年服351区" })
        return areas.firstOrNull { normalize(it.areaName) == normalizedQuery }
            ?: areas.firstOrNull { normalize(it.areaName).contains(normalizedQuery) || normalizedQuery.contains(normalize(it.areaName)) }
            ?: areas.firstOrNull { it.serverKey.equals(query, ignoreCase = true) }
            ?: areas.firstOrNull { it.serverKey == "qzone_351" }
            ?: areas.firstOrNull { it.areaName.contains("351") }
            ?: error("未找到区服：$query，可选示例：${areas.take(5).joinToString { it.areaName }}")
    }

    private fun normalize(s: String): String = s
        .replace("（", "(")
        .replace("）", ")")
        .replace(" ", "")
        .trim()
        .lowercase(Locale.ROOT)

    private fun httpGet(base: String, params: Map<String, String>): String {
        requireExecutionAllowed("passport/get")
        val qs = params.entries.joinToString("&") { (k, v) ->
            URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8")
        }
        val url = URL(base + if (base.contains('?')) "&$qs" else "?$qs")
        val conn = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 20_000
            requestMethod = "GET"
            setRequestProperty("User-Agent", "DWPMClone/1.0 real-protocol")
        }
        return try {
            readResponse(conn)
        } finally {
            conn.disconnect()
        }
    }

    private fun postGame(gameHttp: String, commands: List<GameCommand>, dm: Long): List<GamePacket> {
        val opcodeLabel = commands.firstOrNull()?.opcode?.let { "0x${it.toString(16)}" } ?: "empty"
        requireExecutionAllowed("real-protocol/$opcodeLabel")
        // 所有真实游戏请求的唯一出口：在这里统一记录成败，供助手页账号卡的
        // “最近30次请求”健康点展示（对齐电脑端 acc.recentGameRequests）。
        val purpose = GameOpcodePurpose.of(commands.firstOrNull()?.opcode)
        var connection: HttpURLConnection? = null
        try {
            val body = makePacket(commands, dm)
            val url = URL(gameHttp)
            val conn = (url.openConnection() as HttpURLConnection).apply {
                connectTimeout = 15_000
                readTimeout = 25_000
                requestMethod = "POST"
                doOutput = true
                setRequestProperty("Content-Type", "application/octet-stream")
                setRequestProperty("User-Agent", "DWPMClone/1.0 real-protocol")
                setFixedLengthStreamingMode(body.size)
            }
            connection = conn
            conn.outputStream.use { it.write(body) }
            val bytes = readResponseBytes(conn)
            val packets = parseGameResponse(bytes)
            GameRequestHealthSink.record(true, purpose)
            return packets
        } catch (error: Throwable) {
            GameRequestHealthSink.record(false, purpose)
            throw error
        } finally {
            connection?.disconnect()
        }
    }

    private fun requireExecutionAllowed(phase: String) {
        if (!executionAllowed()) throw ExecutionRevokedBeforeNetworkException(phase)
    }

    private fun readResponse(conn: HttpURLConnection): String = String(readResponseBytes(conn), UTF8)

    private fun readResponseBytes(conn: HttpURLConnection): ByteArray {
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val bytes = stream?.use { it.readBytes() } ?: ByteArray(0)
        if (code !in 200..299) {
            throw IllegalStateException("HTTP $code: ${String(bytes, UTF8).take(200)}")
        }
        return bytes
    }

    private fun makePacket(commands: List<GameCommand>, dm: Long): ByteArray {
        val out = PacketWriter()
        out.utf(PROTOCOL_HEADER)
        out.long(System.currentTimeMillis())
        out.byte(commands.size)
        commands.forEach { cmd ->
            out.long(dm)
            out.long(0L) // gm
            out.short(cmd.payload.size)
            out.short(cmd.opcode)
            out.utf("") // signature: empty string verified by captures/replay
            out.raw(cmd.payload)
        }
        return out.toByteArray()
    }

    private fun parseGameResponse(data: ByteArray): List<GamePacket> {
        val c = PacketCursor(data)
        val packets = mutableListOf<GamePacket>()
        val outer = c.u8()
        repeat(outer) { outerIndex ->
            val inner = c.u8()
            repeat(inner) { innerIndex ->
                val long0 = c.i64()
                val long1 = c.i64()
                val obf = c.u8()
                val len = c.i32()
                val opcode = c.u16()
                val frag = c.u8()
                val payload = c.bytes(len)
                packets += GamePacket(outerIndex, innerIndex, long0, long1, obf, len, opcode, frag, payload)
            }
        }
        return packets
    }

    private data class Parsed8003(
        val status: Int,
        val message: String,
        val dm: Long,
        val selectedIndex: Int,
        val roles: List<RoleBrief>
    )

    private fun parse8003(payload: ByteArray): Parsed8003 {
        val c = PacketCursor(payload)
        val status = c.i8()
        val message = c.utf()
        val dm = c.i64()
        var selected = 0
        val roles = mutableListOf<RoleBrief>()
        if (status == 0) {
            c.i64() // y6_unknown
            selected = c.i32()
            val count = c.i32()
            repeat(count) {
                val roleId = c.i64()
                c.i16()
                val roleName = c.utf()
                val levelCandidate = c.i8()
                val country = c.utf()
                val title = c.utf()
                roles += RoleBrief(roleId, roleName, levelCandidate, country, title)
            }
        }
        return Parsed8003(status, message, dm, selected, roles)
    }

    internal fun parse8004Head(payload: ByteArray, sourceOpcode: String): RoleState {
        val c = PacketCursor(payload)
        c.i8() // status1
        c.i8() // status2
        val serverTime = c.i64()
        val roleId = c.i64()
        val roleName = c.utf()
        c.i8() // B_unknown
        val level = c.i8()
        val copper = c.i64()
        val food = c.i64()
        c.i64() // field_f_unknown
        c.i8() // g_unknown
        c.i16() // official/title candidate
        c.i8() // x_unknown
        val prestige = c.i64()
        val prestigePrev = c.i64()
        val prestigeNext = c.i64()
        c.i64() // skip_long
        c.i8() // l_unknown
        val copperPerHour = c.i32()
        val foodPerHour = c.i32()
        c.i64() // battle merit candidate
        c.i64() // p_unknown
        val populationCurrent = c.i64()
        val populationCap = c.i64()
        val fiefLimit = c.i8()
        val generalLimit = c.i8()
        val resourcePointCurrent = c.i8()
        val resourcePointCap = c.i8()
        // 对齐电脑端 parse_8004_head：资源点上限后是一个保留 byte
        // 和真正的官职 short。前面头像后的 short 是头像编号，不是官职。
        val officeFieldFlag = if (c.remaining >= 3) c.i8() else null
        val officeIdRaw = if (officeFieldFlag != null) c.i16() else null
        val officeIdUnsigned = officeIdRaw?.and(0xffff)
        val parsedHeadByteCount = c.position
        val tail = payload.copyOfRange(parsedHeadByteCount, payload.size)
        return RoleState(
            roleId = roleId,
            roleName = roleName,
            level = level,
            copper = copper,
            food = food,
            prestige = prestige,
            prestigePrevThreshold = prestigePrev,
            prestigeNextThreshold = prestigeNext,
            copperPerHour = copperPerHour,
            foodPerHour = foodPerHour,
            populationCurrent = populationCurrent,
            populationCap = populationCap,
            fiefLimit = fiefLimit,
            generalLimit = generalLimit,
            resourcePointCurrent = resourcePointCurrent,
            resourcePointCap = resourcePointCap,
            officeFieldFlag = officeFieldFlag,
            officeIdRaw = officeIdRaw,
            officeIdUnsigned = officeIdUnsigned,
            officeName = officeIdUnsigned?.let(OFFICE_NAMES_BY_ID::get).orEmpty(),
            serverTimeMillis = serverTime,
            sourceOpcode = sourceOpcode,
            payloadByteCount = payload.size,
            parsedHeadByteCount = parsedHeadByteCount,
            tailByteCount = tail.size,
            payloadHex = payload.toHex(),
            tailHex = tail.toHex(),
            tailUtf8Preview = tail.toUtf8Preview()
        )
    }

    /**
     * Replays the stable 0x8004 head parser against a payload already persisted by an
     * older APK. This is local-only and performs no network request.
     */
    internal fun parsePersisted8004HeadHex(
        payloadHex: String,
        sourceOpcode: String = "persisted/0x8004"
    ): RoleState = parse8004Head(payloadHex.hexToBytes(), sourceOpcode)

    internal fun parse8104Inventory(payload: ByteArray, sourceOpcode: String): InventoryState {
        require(payload.size >= 18) { "0x8104 背包响应过短：${payload.size}" }
        val capacity = payload.u16At(14)
        val itemCount = payload.u16At(16)
        require(itemCount in 0..512) { "0x8104 背包条目数异常：$itemCount" }
        val itemsEnd = 18 + itemCount * INVENTORY_ITEM_RECORD_LEN
        require(itemsEnd <= payload.size) {
            "0x8104 背包条目越界：count=$itemCount end=$itemsEnd size=${payload.size}"
        }
        val items = (0 until itemCount).map { index ->
            val offset = 18 + index * INVENTORY_ITEM_RECORD_LEN
            val itemId = payload.u16At(offset)
            val count = payload.u16At(offset + 2)
            val rawTail = payload.copyOfRange(offset + 4, offset + INVENTORY_ITEM_RECORD_LEN).toHex()
            val mappedName = ItemDictionary.nameFor(itemId)
            InventoryStack(
                itemId = itemId,
                name = mappedName ?: "道具#$itemId",
                count = count,
                typeLabel = ItemDictionary.typeLabelFor(itemId),
                nameSource = if (mappedName == null) "raw-item-id" else "scriptItem.sc",
                rawTailHex = rawTail
            )
        }
        val equipmentResult = parse8104Equipment(payload, itemsEnd)
        return InventoryState(
            capacity = capacity,
            itemCount = itemCount,
            items = items,
            equipment = equipmentResult.items,
            equipmentParseError = equipmentResult.error,
            sourceOpcode = sourceOpcode,
            payloadByteCount = payload.size,
            payloadHex = payload.toHex(),
            parsedItemByteCount = itemsEnd,
            tailHex = payload.copyOfRange(itemsEnd, payload.size).toHex()
        )
    }

    private data class EquipmentParseResult(
        val items: List<InventoryEquipment>,
        val endOffset: Int,
        val error: String?
    )

    /** V5 equipment block immediately following the fixed 12-byte item records. */
    private fun parse8104Equipment(payload: ByteArray, offset: Int): EquipmentParseResult {
        if (offset + 2 > payload.size) {
            return EquipmentParseResult(emptyList(), offset, "缺少装备数量")
        }
        val count = payload.u16At(offset)
        if (count > 1000) {
            return EquipmentParseResult(emptyList(), offset, "装备数量异常：$count")
        }
        var p = offset + 2
        val equipment = mutableListOf<InventoryEquipment>()
        return try {
            repeat(count) { index ->
                if (p + 11 > payload.size) error("第 ${index + 1} 条装备记录不完整")
                val recordOffset = p
                var instanceId = 0L
                repeat(8) {
                    instanceId = (instanceId shl 8) or (payload[p++].toLong() and 0xffL)
                }
                val templateId = payload.u16At(p)
                p += 2
                val attributeLength = payload[p++].toInt() and 0xff
                if (attributeLength > 64 || p + attributeLength + 10 > payload.size) {
                    error("第 ${index + 1} 条装备属性长度异常：$attributeLength")
                }
                val attributes = payload.copyOfRange(p, p + attributeLength)
                    .map { it.toInt() and 0xff }
                p += attributeLength
                p += 2 // strengthen effect
                p += 2 // two risk bytes
                p += 2 // protocol J
                p += 2 // pity current
                p += 2 // pity target
                val textLength = payload.u16At(p)
                p += 2
                if (p + textLength > payload.size) {
                    error("第 ${index + 1} 条装备额外描述越界：$textLength")
                }
                val extraText = String(payload, p, textLength, Charsets.UTF_8)
                p += textLength
                val template = EquipmentTemplateDictionary.templateFor(templateId)
                equipment += InventoryEquipment(
                    instanceId = instanceId,
                    templateId = templateId,
                    name = template?.name ?: "装备#$templateId",
                    level = template?.level ?: 0,
                    typeCode = template?.typeCode ?: -1,
                    famous = template?.famous ?: false,
                    quality = attributes.getOrNull(0) ?: -1,
                    strengthen = attributes.getOrNull(1) ?: 0,
                    extraText = extraText,
                    attributes = attributes,
                    rawHex = payload.copyOfRange(recordOffset, p).toHex()
                )
            }
            EquipmentParseResult(equipment, p, null)
        } catch (error: Exception) {
            EquipmentParseResult(equipment, p, error.message ?: "装备记录解析失败")
        }
    }

    private class PacketWriter {
        private val bos = ByteArrayOutputStream()
        private val dos = DataOutputStream(bos)
        fun byte(v: Int) { dos.writeByte(v) }
        fun short(v: Int) { dos.writeShort(v) }
        fun long(v: Long) { dos.writeLong(v) }
        fun utf(s: String) {
            val b = s.toByteArray(UTF8)
            require(b.size <= 65535) { "UTF 字段过长" }
            dos.writeShort(b.size)
            dos.write(b)
        }
        fun raw(bytes: ByteArray) { dos.write(bytes) }
        fun toByteArray(): ByteArray = bos.toByteArray()
    }

    private class PacketCursor(private val data: ByteArray) {
        private var p = 0
        val position: Int get() = p
        val remaining: Int get() = data.size - p
        fun u8(): Int = data[p++].toInt() and 0xff
        fun i8(): Int = data[p++].toInt()
        fun u16(): Int {
            ensure(2)
            val v = ((data[p].toInt() and 0xff) shl 8) or (data[p + 1].toInt() and 0xff)
            p += 2
            return v
        }
        fun i16(): Int {
            val v = u16()
            return if (v > 0x7fff) v - 0x10000 else v
        }
        fun i32(): Int {
            ensure(4)
            val v = ((data[p].toInt() and 0xff) shl 24) or
                ((data[p + 1].toInt() and 0xff) shl 16) or
                ((data[p + 2].toInt() and 0xff) shl 8) or
                (data[p + 3].toInt() and 0xff)
            p += 4
            return v
        }
        fun i64(): Long {
            ensure(8)
            var v = 0L
            repeat(8) { v = (v shl 8) or (data[p++].toLong() and 0xffL) }
            return v
        }
        fun utf(): String {
            val len = u16()
            val s = String(bytes(len), UTF8)
            return s
        }
        fun bytes(len: Int): ByteArray {
            ensure(len)
            val out = data.copyOfRange(p, p + len)
            p += len
            return out
        }
        private fun ensure(n: Int) {
            if (p + n > data.size) throw IllegalStateException("协议解析越界：pos=$p need=$n size=${data.size}")
        }
    }

    private data class GameCommand(val opcode: Int, val payload: ByteArray)
    private data class GamePacket(
        val outer: Int,
        val inner: Int,
        val long0: Long,
        val long1: Long,
        val obf: Int,
        val len: Int,
        val opcode: Int,
        val frag: Int,
        val payload: ByteArray
    ) {
        fun hexOpcode(): String = "0x" + opcode.toString(16).padStart(4, '0')
    }

    companion object {
        private val UTF8: Charset = Charsets.UTF_8
        private const val PASSPORT = "https://sglmpass.3gking.net:12443/"
        private const val GAME_PATH = "/kingWapServer/HttpClient"
        private const val CHANNEL_NUM = "0000480502"
        private const val SOURCE = "diwang.sanguo"
        private const val GAME_KEY = "diwang.sanguo"
        private const val CTYPE = "7054"
        private const val VERSION = "1660606"
        private const val PROTOCOL_HEADER = "1660606`7054`0000480502"
        private const val TARGETS = "1,2,3,5,11,12,13,14,15,16,17,18,19,20,21,31,32,33,34,41,91"
        private const val INVENTORY_ITEM_RECORD_LEN = 12
        private val READ_ONLY_GAME_HEX_OPCODE_ALLOWLIST = setOf(0x1540, 0x1542)
        private val OFFICE_NAMES_BY_ID: Map<Int, String> = buildMap {
            put(0x0000, "游民")
            put(0x0001, "细作")
            put(0x0100, "国民")
            repeat(0x19) { index ->
                put(0x0200 + index, "侍郎")
                put(0x0280 + index, "都尉")
            }
            put(0x0300, "兵部尚书")
            put(0x0301, "吏部尚书")
            put(0x0302, "民部尚书")
            put(0x0303, "刑部尚书")
            put(0x0304, "工部尚书")
            put(0x0305, "户部尚书")
            put(0x0306, "礼部尚书")
            put(0x0307, "学部尚书")
            put(0x0380, "虎威将军")
            put(0x0381, "破虏将军")
            put(0x0382, "奋武将军")
            put(0x0383, "抚远将军")
            put(0x0384, "征东将军")
            put(0x0385, "平西将军")
            put(0x0386, "镇北将军")
            put(0x0387, "定南将军")
            put(0x0400, "丞相")
            put(0x0401, "丞相")
            put(0x0480, "大都督")
            put(0x0481, "大都督")
            put(0x0500, "国王")
        }

    }
}

private fun String.hexToBytes(): ByteArray {
    require(length % 2 == 0) { "hex length must be even" }
    return ByteArray(length / 2) { index ->
        substring(index * 2, index * 2 + 2).toInt(16).toByte()
    }
}

private fun ByteArray.u16At(index: Int): Int {
    require(index >= 0 && index + 1 < size) { "u16At 越界：index=$index size=$size" }
    return ((this[index].toInt() and 0xff) shl 8) or (this[index + 1].toInt() and 0xff)
}

private fun ByteArray.toHex(): String = joinToString(separator = "") { byte ->
    (byte.toInt() and 0xff).toString(16).padStart(2, '0')
}

private fun ByteArray.toUtf8Preview(maxChars: Int = 4096): String =
    String(this, Charsets.UTF_8)
        .map { ch -> if (ch.code in 0x20..0x7e || ch in '\u4e00'..'\u9fff') ch else ' ' }
        .joinToString(separator = "")
        .replace(Regex("""\s+"""), " ")
        .trim()
        .take(maxChars)

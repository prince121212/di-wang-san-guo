package com.example.dwpmclone.domain.protocol

import org.json.JSONArray
import org.json.JSONObject

/** A single live entry returned by the desktop-compatible 0x1600/0x8600 query. */
data class MilitarySnapshotAction(
    val tag: String,
    val state: String,
    val text: String,
    val battleId: Long,
    val generalIds: List<Long>,
    val targetId: Long,
    val targetType: Int,
    val targetName: String,
    val x: Int,
    val y: Int,
    val marchKind: Int? = null,
    val marchValue: Long? = null,
    val eventTimeMillis: Long? = null,
    val incoming: Boolean = false,
    val direction: String = if (incoming) "incoming" else "outgoing",
    val sourceSection: Int = 0,
    val recordId: Long? = null,
    val attackerName: String? = null,
    val actionType: Int? = null,
    val actionTypeText: String? = null,
    val targetTypeText: String = targetTypeText(targetType, incoming),
    val generalFlags: List<Int> = emptyList(),
    val generalNames: List<String> = emptyList(),
    val recordKind: Int? = null
) {
    fun toJson(): JSONObject = JSONObject()
        .put("tag", tag)
        .put("state", state)
        .put("text", text)
        .put("incoming", incoming)
        .put("direction", direction)
        .put("sourceSection", sourceSection)
        .put("generalIds", JSONArray(generalIds))
        .put("generalFlags", JSONArray(generalFlags))
        .put("generalNames", JSONArray(generalNames))
        .put("targetId", targetId)
        .put("targetType", targetType)
        .put("targetTypeText", targetTypeText)
        .put("targetName", targetName)
        .put("x", x)
        .put("y", y)
        .put("hasCoord", x != 0 || y != 0)
        .also { json ->
            if (battleId > 0L) json.put("battleId", battleId)
            recordId?.takeIf { it > 0L }?.let { json.put("recordId", it) }
            attackerName?.takeIf { it.isNotBlank() }?.let { json.put("attackerName", it) }
            actionType?.let { json.put("actionType", it) }
            actionTypeText?.takeIf { it.isNotBlank() }?.let { json.put("actionTypeText", it) }
            recordKind?.let { json.put("recordKind", it) }
            marchKind?.let {
                json.put("marchKind", it)
                json.put("marchKindText", marchKindText(it, incoming))
            }
            marchValue?.let { json.put("marchValue", it) }
            eventTimeMillis?.let { json.put("eventTimeMs", it) }
        }

    companion object {
        private fun targetTypeText(targetType: Int, incoming: Boolean): String = when {
            incoming -> "我方封地"
            targetType == 0x01 -> "封地"
            targetType == 0x02 -> "野外目标"
            targetType == 0x03 -> "山贼"
            targetType == 0x0E -> "副本关卡"
            else -> ""
        }

        private fun marchKindText(kind: Int, incoming: Boolean): String = when {
            incoming -> "来袭"
            kind == 0x09 || kind == 0x0B -> "去程"
            kind == 0x0D -> "回程"
            kind == 0x17 -> "副本"
            else -> ""
        }
    }
}

data class MilitaryBattleReference(
    val battleId: Long,
    val flag: Int
) {
    fun toJson(): JSONObject = JSONObject()
        .put("battleId", battleId)
        .put("flag", flag)
}

data class MilitarySnapshot(
    val actions: List<MilitarySnapshotAction>,
    val responded: Boolean,
    val payloadHex: String,
    val activeBattleReferences: List<MilitaryBattleReference> = emptyList(),
    val generalStatusRecords: List<Map<String, String>> = emptyList(),
    val captiveGeneralRecords: List<Map<String, String>> = emptyList(),
    val troopAssignmentCount: Int = 0,
    val trailingEvidenceParsed: Boolean = false,
    val unparsedTailByteCount: Int = 0,
    val trailingParseError: String? = null
) {
    fun toJson(): JSONObject = JSONObject()
        .put("sourceOpcode", "0x1600/0x8600")
        .put("actions", JSONArray().apply { actions.forEach { put(it.toJson()) } })
        .put("actionCount", actions.size)
        .put("incomingCount", actions.count { it.incoming })
        .put("activeBattleReferences", JSONArray().apply {
            activeBattleReferences.forEach { put(it.toJson()) }
        })
        .put("generalStatusRecords", JSONArray().apply {
            generalStatusRecords.forEach { put(JSONObject(it)) }
        })
        .put("generalStatusCount", generalStatusRecords.size)
        .put("captiveGeneralRecords", JSONArray().apply {
            captiveGeneralRecords.forEach { put(JSONObject(it)) }
        })
        .put("captiveGeneralCount", captiveGeneralRecords.size)
        .put("troopAssignmentCount", troopAssignmentCount)
        .put("trailingEvidenceParsed", trailingEvidenceParsed)
        .put("unparsedTailByteCount", unparsedTailByteCount)
        .put("responded", responded)
        .put("updatedAt", System.currentTimeMillis())
        .also { json ->
            trailingParseError?.takeIf(String::isNotBlank)?.let {
                json.put("trailingParseError", it)
            }
        }
}

/**
 * Strict 0x8600 parser matching the computer helper's original-client read order.
 *
 * The response is split into three sections rather than a flat sequence of UTF strings:
 *
 * 1. our outgoing/fighting/returning formations;
 * 2. incoming enemy movements (the display sentence is assembled client-side);
 * 3. our garrison formations.
 *
 * A previous Android-only UTF-anchor heuristic could not see section 2 at all and could
 * pair the wrong text with a formation when several records were present. Any structural
 * boundary failure now rejects that payload, exactly like the computer helper, instead of
 * manufacturing a partial military snapshot.
 */
object MilitarySnapshotProtocolShapes {
    const val REQUEST_OPCODE = 0x1600
    const val RESPONSE_OPCODE = 0x8600
    val REQUEST_PAYLOAD: ByteArray = "07000000000000000000000014".hexBytes()

    private const val MAX_SECTION_ITEMS = 512
    private const val JIANGLING_BODY_LENGTH = 114
    private const val JIANGLING_ENERGY_OFFSET = 0x1B
    private const val JIANGLING_ENERGY_LIMIT_OFFSET = 0x1D
    private const val JIANGLING_TROOP_LIMIT_OFFSET = 0x23
    private const val JIANGLING_LOYALTY_OFFSET = 0x27
    private const val JIANGLING_PLACE_ID_OFFSET = 0x32
    private const val JIANGLING_STATUS_OFFSET = 0x56
    private const val TROOP_ASSIGNMENT_LENGTH = 21
    private const val MIN_MARCH_TIMESTAMP = 1_600_000_000_000L
    private const val MAX_MARCH_TIMESTAMP = 2_000_000_000_000L

    fun parse(
        payload: ByteArray,
        responded: Boolean = true,
        generalNamesById: Map<Long, String> = emptyMap()
    ): MilitarySnapshot = parseAll(listOf(payload), responded, generalNamesById)

    fun parseAll(
        payloads: List<ByteArray>,
        responded: Boolean = payloads.isNotEmpty(),
        generalNamesById: Map<Long, String> = emptyMap()
    ): MilitarySnapshot {
        val seen = linkedSetOf<Pair<String, Long>>()
        val parsedPayloads = payloads.map { parsePayload(it, generalNamesById) }
        val actions = parsedPayloads.flatMap { it.actions }
            .filter { action ->
                val identity = if (action.incoming) {
                    "incoming" to (action.recordId ?: 0L)
                } else {
                    "battle" to action.battleId
                }
                identity.second > 0L && seen.add(identity)
            }
        val stateOrder = mapOf(
            "来袭" to 0,
            "战斗" to 1,
            "出征" to 2,
            "驻守" to 3,
            "返回" to 4,
            "备战" to 5
        )
        val sorted = actions.sortedWith(
            compareBy<MilitarySnapshotAction> { stateOrder[it.state] ?: 3 }
                .thenBy { it.recordId ?: it.battleId }
        )
        val activeReferences = parsedPayloads
            .flatMap { it.tail.activeBattleReferences }
            .distinctBy { it.battleId }
        val generalRecords = parsedPayloads
            .flatMap { it.tail.generalStatusRecords }
            .associateBy { it["id"].orEmpty() }
            .values
            .toList()
        val captiveRecords = parsedPayloads
            .flatMap { it.tail.captiveGeneralRecords }
            .associateBy { it["id"].orEmpty() }
            .values
            .toList()
        val tailErrors = parsedPayloads.mapNotNull { it.tail.parseError }
        return MilitarySnapshot(
            actions = sorted,
            responded = responded,
            payloadHex = payloads.joinToString("") { it.toHex() },
            activeBattleReferences = activeReferences,
            generalStatusRecords = generalRecords,
            captiveGeneralRecords = captiveRecords,
            troopAssignmentCount = parsedPayloads.sumOf { it.tail.troopAssignmentCount },
            trailingEvidenceParsed = parsedPayloads.any { it.tail.parsed },
            unparsedTailByteCount = parsedPayloads.sumOf { it.tail.unparsedByteCount },
            trailingParseError = tailErrors.takeIf(List<String>::isNotEmpty)?.joinToString("；")
        )
    }

    private data class ParsedPayload(
        val actions: List<MilitarySnapshotAction> = emptyList(),
        val tail: TrailingEvidence = TrailingEvidence()
    )

    private data class TrailingEvidence(
        val activeBattleReferences: List<MilitaryBattleReference> = emptyList(),
        val generalStatusRecords: List<Map<String, String>> = emptyList(),
        val captiveGeneralRecords: List<Map<String, String>> = emptyList(),
        val troopAssignmentCount: Int = 0,
        val parsed: Boolean = false,
        val unparsedByteCount: Int = 0,
        val parseError: String? = null
    )

    private fun parsePayload(
        payload: ByteArray,
        generalNamesById: Map<Long, String>
    ): ParsedPayload = runCatching {
        val cursor = Cursor(payload)
        val actions = mutableListOf<MilitarySnapshotAction>()
        val headerPairCount = cursor.count16("headerPairCount")
        repeat(headerPairCount) { index ->
            cursor.u8("headerPairs[$index].kind")
            cursor.u16("headerPairs[$index].value")
        }
        val sectionCount = cursor.count8("sectionCount")
        repeat(sectionCount) { sectionIndex ->
            val sectionType = cursor.u8("sections[$sectionIndex].type")
            requireShape(sectionType in 1..3) { "未知分区类型：$sectionType" }
            val descriptors = parseDescriptors(cursor, sectionType)
            if (sectionType == 2) {
                actions += parseIncomingRecords(cursor)
            } else {
                actions += parseFormationRecords(
                    cursor = cursor,
                    sectionType = sectionType,
                    descriptors = descriptors,
                    generalNamesById = generalNamesById
                )
            }
        }
        val trailing = if (cursor.remaining == 0) {
            TrailingEvidence()
        } else {
            runCatching { parseTrailingEvidence(cursor, payload) }
                .getOrElse { error ->
                    TrailingEvidence(
                        unparsedByteCount = cursor.remaining,
                        parseError = error.message ?: error::class.java.simpleName
                    )
                }
        }
        ParsedPayload(actions, trailing)
    }.getOrElse { error ->
        ParsedPayload(
            tail = TrailingEvidence(
                unparsedByteCount = payload.size,
                parseError = error.message ?: error::class.java.simpleName
            )
        )
    }

    /**
     * 0x8600 appends the same structured general block used by the live role state:
     * active battle references, owned generals, captured generals with their fief, and
     * the Lo/a.S5 troop-assignment table.  Earlier parsers stopped after section three
     * and silently discarded this entire block.
     */
    private fun parseTrailingEvidence(
        cursor: Cursor,
        payload: ByteArray
    ): TrailingEvidence {
        val activeReferences = List(cursor.count16("tail.activeBattleReferenceCount")) { index ->
            MilitaryBattleReference(
                battleId = cursor.u64("tail.activeBattleReferences[$index].battleId"),
                flag = cursor.u8("tail.activeBattleReferences[$index].flag")
            )
        }
        cursor.u8("tail.generalBlockFlag")

        val ownedStart = cursor.offset
        repeat(cursor.count16("tail.ownedGeneralCount")) { index ->
            cursor.u64("tail.ownedGenerals[$index].id")
            cursor.utf("tail.ownedGenerals[$index].name")
            cursor.bytes(JIANGLING_BODY_LENGTH, "tail.ownedGenerals[$index].body")
        }
        val ownedEnd = cursor.offset

        val captiveRecords = mutableListOf<Map<String, String>>()
        repeat(cursor.count8("tail.captiveGeneralCount")) { index ->
            val id = cursor.u64("tail.captiveGenerals[$index].id")
            val name = cursor.utf("tail.captiveGenerals[$index].name").value
            val body = cursor.bytes(
                JIANGLING_BODY_LENGTH,
                "tail.captiveGenerals[$index].body"
            )
            cursor.u64("tail.captiveGenerals[$index].ownerId")
            val fiefId = cursor.u16("tail.captiveGenerals[$index].fiefId")
            val fiefName = cursor.utf("tail.captiveGenerals[$index].fiefName").value
            cursor.u64("tail.captiveGenerals[$index].reservedId")
            cursor.u16("tail.captiveGenerals[$index].reservedFlag")
            val status = body.u8At(JIANGLING_STATUS_OFFSET)
            captiveRecords += buildMap {
                put("id", id.toString())
                put("idHex", id.toString(16).padStart(16, '0'))
                put("name", name)
                put("source", "0x8600-captive-general-tail")
                put("militarySnapshotFresh", "true")
                put("status", status.toString())
                put("statusText", generalStatusText(status))
                put("tili", body.u16At(JIANGLING_ENERGY_OFFSET).toString())
                put("tiliLimit", body.u16At(JIANGLING_ENERGY_LIMIT_OFFSET).toString())
                put("loyalty", body.u8At(JIANGLING_LOYALTY_OFFSET).toString())
                put("troopLimit", body.u32At(JIANGLING_TROOP_LIMIT_OFFSET).toString())
                put("placeID", body.u64At(JIANGLING_PLACE_ID_OFFSET).toString())
                put("captureFiefId", fiefId.toString())
                put("captureFiefName", fiefName)
            }
        }

        val troopStart = cursor.offset
        val troopAssignmentCount = cursor.count8("tail.troopAssignmentCount")
        repeat(troopAssignmentCount) { index ->
            cursor.bytes(TROOP_ASSIGNMENT_LENGTH, "tail.troopAssignments[$index]")
        }
        val troopEnd = cursor.offset

        val ownedEvidence = payload.copyOfRange(ownedStart, ownedEnd) +
            payload.copyOfRange(troopStart, troopEnd)
        val ownedRecords = State8004GeneralEvidenceParser.recoverRecords(ownedEvidence.toHex())
            .map { record ->
                record + mapOf(
                    "source" to "0x8600-owned-general-tail",
                    "militarySnapshotFresh" to "true"
                )
            }
        return TrailingEvidence(
            activeBattleReferences = activeReferences,
            generalStatusRecords = ownedRecords,
            captiveGeneralRecords = captiveRecords,
            troopAssignmentCount = troopAssignmentCount,
            parsed = true,
            unparsedByteCount = cursor.remaining
        )
    }

    private data class Descriptor(
        val text: String,
        val offset: Int,
        val recordIndexes: List<Int> = emptyList()
    )

    private fun parseDescriptors(cursor: Cursor, sectionType: Int): List<Descriptor> {
        val count = cursor.count16("section$sectionType.descriptorCount")
        return List(count) { index ->
            val text = cursor.utf("section$sectionType.descriptors[$index].text")
            val valueCount = cursor.count16("section$sectionType.descriptors[$index].valueCount")
            if (sectionType == 1 || sectionType == 3) {
                Descriptor(
                    text = text.value,
                    offset = text.offset,
                    recordIndexes = List(valueCount) { valueIndex ->
                        cursor.u16("section$sectionType.descriptors[$index].values[$valueIndex]")
                    }
                )
            } else {
                cursor.u64("section2.descriptors[$index].objectId")
                cursor.u16("section2.descriptors[$index].width")
                cursor.u16("section2.descriptors[$index].height")
                val updateCount = cursor.count16("section2.descriptors[$index].updateCount")
                repeat(updateCount) { updateIndex ->
                    cursor.u16("section2.descriptors[$index].updates[$updateIndex]")
                }
                Descriptor(text.value, text.offset)
            }
        }
    }

    private fun parseFormationRecords(
        cursor: Cursor,
        sectionType: Int,
        descriptors: List<Descriptor>,
        generalNamesById: Map<Long, String>
    ): List<MilitarySnapshotAction> {
        val count = cursor.count16("section$sectionType.recordCount")
        return buildList {
            repeat(count) { index ->
                val battleId = cursor.u64("section$sectionType.records[$index].battleId")
                val generalCount = cursor.u8("section$sectionType.records[$index].generalCount")
                requireShape(generalCount in 1..32) {
                    "section$sectionType 将领数异常：$generalCount"
                }
                val generalIds = ArrayList<Long>(generalCount)
                val generalFlags = ArrayList<Int>(generalCount)
                repeat(generalCount) { generalIndex ->
                    generalIds += cursor.u64(
                        "section$sectionType.records[$index].generals[$generalIndex].id"
                    )
                    generalFlags += cursor.u8(
                        "section$sectionType.records[$index].generals[$generalIndex].flag"
                    )
                }
                val targetId = cursor.u64("section$sectionType.records[$index].targetId")
                val targetType = cursor.u8("section$sectionType.records[$index].targetType")
                val target = cursor.utf("section$sectionType.records[$index].targetName")
                val x = cursor.u16("section$sectionType.records[$index].x")
                val y = cursor.u16("section$sectionType.records[$index].y")
                val recordKind: Int?
                val march: March?
                if (sectionType == 1) {
                    recordKind = cursor.u8("section1.records[$index].recordKind")
                    val marchValue = cursor.u32("section1.records[$index].marchValue")
                    val eventTimeMillis = cursor.u64("section1.records[$index].eventTimeMs")
                    march = validateMarch(recordKind, marchValue, eventTimeMillis)
                } else {
                    cursor.u64("section3.records[$index].serverTimeReference")
                    recordKind = null
                    march = null
                }
                val descriptor = descriptors.firstOrNull { index in it.recordIndexes }
                    ?: descriptors.getOrNull(index)
                    ?: Descriptor("", 0)
                val text = descriptor.text
                val tag = actionTag(text)
                if (
                    tag.isBlank() ||
                    battleId <= 0L ||
                    targetId <= 0L ||
                    target.value.isBlank() ||
                    generalIds.any { it <= 0L }
                ) return@repeat
                add(
                    MilitarySnapshotAction(
                        tag = tag,
                        state = deriveState(tag, text, march),
                        text = text,
                        battleId = battleId,
                        generalIds = generalIds,
                        targetId = targetId,
                        targetType = targetType,
                        targetName = target.value,
                        x = x,
                        y = y,
                        marchKind = march?.kind,
                        marchValue = march?.value,
                        eventTimeMillis = march?.timeMillis,
                        incoming = false,
                        sourceSection = sectionType,
                        generalFlags = generalFlags,
                        generalNames = generalIds.map { generalNamesById[it].orEmpty() },
                        recordKind = recordKind
                    )
                )
            }
        }
    }

    private fun parseIncomingRecords(cursor: Cursor): List<MilitarySnapshotAction> {
        val count = cursor.count16("section2.incomingCount")
        return buildList {
            repeat(count) { index ->
                val recordId = cursor.u64("section2.incoming[$index].recordId")
                val attacker = cursor.utf("section2.incoming[$index].attackerName")
                val actionType = cursor.u8("section2.incoming[$index].actionType")
                val target = cursor.utf("section2.incoming[$index].targetName")
                val targetId = cursor.u64("section2.incoming[$index].targetId")
                val remainingMillis = cursor.u32("section2.incoming[$index].remainingMs")
                val eventTimeMillis = cursor.u64("section2.incoming[$index].eventTimeMs")
                if (
                    recordId <= 0L ||
                    targetId <= 0L ||
                    attacker.value.isBlank() ||
                    target.value.isBlank()
                ) return@repeat
                val known = incomingAction(actionType)
                val tag = known?.first ?: "来袭"
                val actionTypeText = known?.first ?: "未知类型 $actionType"
                val text = known?.let {
                    "【${it.first}】${attacker.value}${it.second}${target.value}"
                } ?: "【来袭】${attacker.value}对${target.value}发起军事行动（类型 $actionType）"
                add(
                    MilitarySnapshotAction(
                        tag = tag,
                        state = "来袭",
                        text = text,
                        battleId = 0L,
                        generalIds = emptyList(),
                        targetId = targetId,
                        targetType = 0,
                        targetName = target.value,
                        x = 0,
                        y = 0,
                        marchValue = remainingMillis,
                        eventTimeMillis = eventTimeMillis,
                        incoming = true,
                        sourceSection = 2,
                        recordId = recordId,
                        attackerName = attacker.value,
                        actionType = actionType,
                        actionTypeText = actionTypeText
                    )
                )
            }
        }
    }

    private data class March(val kind: Int, val value: Long, val timeMillis: Long)

    private fun generalStatusText(status: Int): String = when (status) {
        0 -> "空闲"
        1 -> "出征"
        2 -> "驻防"
        3 -> "被俘"
        4 -> "阵亡"
        5 -> "修炼"
        6 -> "作战中"
        7 -> "待招募"
        8 -> "返回"
        9 -> "解雇"
        else -> "状态$status"
    }

    private fun validateMarch(kind: Int, value: Long, timeMillis: Long): March? =
        if (
            kind in setOf(0x09, 0x0B, 0x0D, 0x17) &&
            timeMillis in (MIN_MARCH_TIMESTAMP + 1) until MAX_MARCH_TIMESTAMP
        ) {
            March(kind, value, timeMillis)
        } else {
            null
        }

    private fun actionTag(text: String): String {
        if (!text.startsWith('【')) return ""
        val end = text.indexOf('】')
        return if (end > 1) text.substring(1, end) else ""
    }

    private fun deriveState(tag: String, text: String, march: March?): String = when {
        tag == "副本" && text.contains("战斗进行中") -> "战斗"
        tag == "副本" -> "备战"
        tag == "驻守" -> "驻守"
        tag == "返回" -> "返回"
        tag in setOf("攻占", "夺取", "掠夺", "消灭") &&
            march?.kind in setOf(0x09, 0x0B) && (march?.value ?: 0L) > 0L -> "出征"
        tag in setOf("攻占", "夺取", "掠夺", "消灭") -> "战斗"
        else -> tag
    }

    private fun incomingAction(type: Int): Pair<String, String>? = when (type) {
        0x01 -> "掠夺" to "夺取"
        else -> null
    }

    private class Cursor(private val payload: ByteArray) {
        var offset: Int = 0
            private set

        fun u8(field: String): Int = take(1, field)[0].toInt() and 0xff

        fun u16(field: String): Int {
            val bytes = take(2, field)
            return ((bytes[0].toInt() and 0xff) shl 8) or
                (bytes[1].toInt() and 0xff)
        }

        fun u32(field: String): Long {
            val bytes = take(4, field)
            return ((bytes[0].toLong() and 0xff) shl 24) or
                ((bytes[1].toLong() and 0xff) shl 16) or
                ((bytes[2].toLong() and 0xff) shl 8) or
                (bytes[3].toLong() and 0xff)
        }

        fun u64(field: String): Long {
            val bytes = take(8, field)
            var value = 0L
            bytes.forEach { value = (value shl 8) or (it.toLong() and 0xff) }
            return value
        }

        fun count8(field: String): Int = checkedCount(u8(field), field)

        fun count16(field: String): Int = checkedCount(u16(field), field)

        val remaining: Int
            get() = payload.size - offset

        fun bytes(size: Int, field: String): ByteArray = take(size, field)

        fun utf(field: String): UtfValue {
            val start = offset
            val length = u16("$field.length")
            val raw = take(length, field)
            val text = raw.toString(Charsets.UTF_8)
            requireShape(text.toByteArray(Charsets.UTF_8).contentEquals(raw)) {
                "$field 不是合法 UTF-8"
            }
            return UtfValue(text, start)
        }

        private fun checkedCount(value: Int, field: String): Int {
            requireShape(value in 0..MAX_SECTION_ITEMS) { "$field 数量异常：$value" }
            return value
        }

        private fun take(size: Int, field: String): ByteArray {
            requireShape(size >= 0 && offset + size <= payload.size) {
                "$field 越界：offset=$offset size=$size payload=${payload.size}"
            }
            val start = offset
            offset += size
            return payload.copyOfRange(start, offset)
        }
    }

    private data class UtfValue(val value: String, val offset: Int)

    private fun ByteArray.u8At(index: Int): Int = this[index].toInt() and 0xff

    private fun ByteArray.u16At(index: Int): Int =
        (u8At(index) shl 8) or u8At(index + 1)

    private fun ByteArray.u32At(index: Int): Long =
        (u8At(index).toLong() shl 24) or
            (u8At(index + 1).toLong() shl 16) or
            (u8At(index + 2).toLong() shl 8) or
            u8At(index + 3).toLong()

    private fun ByteArray.u64At(index: Int): Long {
        var value = 0L
        repeat(8) { offset -> value = (value shl 8) or u8At(index + offset).toLong() }
        return value
    }

    private inline fun requireShape(condition: Boolean, lazyMessage: () -> String) {
        if (!condition) throw IllegalArgumentException("0x8600 ${lazyMessage()}")
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it.toInt() and 0xff) }

    private fun String.hexBytes(): ByteArray = ByteArray(length / 2) { index ->
        substring(index * 2, index * 2 + 2).toInt(16).toByte()
    }
}

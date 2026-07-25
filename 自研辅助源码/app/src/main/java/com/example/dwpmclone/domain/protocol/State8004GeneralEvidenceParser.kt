package com.example.dwpmclone.domain.protocol

/**
 * Evidence bridge for the still-incomplete 0x8004 tail/bF[JiangLing] schema.
 *
 * The real 小黄点 client stores parsed generals in `Landroid/o/ۥ;->bF:[JiangLing]` and
 * confirmed field names include id/name/kind/rank/status/placeID/gongji/fangyu/wuli/
 * zhili/tongshuai/tili/tiliLimit/daiBingLimit/jingyan/jingyanLimit/isFulu/
 * isPeiBingFail. Until the exact binary tail layout is fully recovered, this parser
 * extracts two safe forms from persisted 0x8004 evidence:
 *
 * 1. JiangLing/key-value text embedded in tail previews or decoded hex.
 * 2. Confirmed binary JiangLing records in the 0x8004 tail/full payload:
 *    `i64 id + u16 utf8 name + 114-byte body`, where the body repeats the id at
 *    offset 0x3a and ends with 0xffff.  This layout is calibrated against live
 *    passive bridge100 captures and the recovered JiangLing constructor.
 * 3. Conservative binary candidates shaped as `i64 id + u16 utf8 name`, which is the
 *    same primitive encoding already used by the recovered login role parser.
 *
 * It never performs network I/O and should be treated as calibration/evidence parsing,
 * not as proof that the full 0x8004 schema is known.
 */
object State8004GeneralEvidenceParser {
    private data class SoldierType(val code: Int, val unitId: Int, val name: String, val category: Int, val level: Int)
    private data class BinaryJiangLingRecord(
        val id: Long,
        val idHex: String,
        val name: String,
        val bodyOffset: Int,
        val body: ByteArray,
        val fields: LinkedHashMap<String, String>
    )

    private data class S5TroopAssignment(
        val generalId: Long,
        val soldierTypeCode: Int,
        val currentSoldierCount: Int,
        val offset: Int,
        val count: Int
    )

    private val KEY_VALUE_REGEX = Regex("""([\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z0-9_]*)\s*[:=]\s*('[^']*'|"[^"]*"|[^,;|\s{}]+)""")
    private val ID_KEY_REGEX = Regex("""(?:^|[|,;\s{}])((?:id|generalId|jiangLingId|编号|將領ID|将领ID|武将ID|武將ID|将ID|將ID)\s*[:=])""", RegexOption.IGNORE_CASE)
    private val HEX_REGEX = Regex("""^(?:0x)?[0-9a-fA-F\s|:_-]{8,}$""")
    private const val JIANGLING_BODY_LEN = 114
    private const val JIANGLING_BODY_REPEATED_ID_OFFSET = 58
    private const val JIANGLING_BODY_PROFESSION_OFFSET = 0x03
    private const val JIANGLING_BODY_GROWTH_OFFSET = 0x06
    private const val JIANGLING_BODY_LEVEL_OFFSET = 0x08
    private const val JIANGLING_BODY_ATTACK_OFFSET = 0x17
    private const val JIANGLING_BODY_DEFENSE_OFFSET = 0x19
    private const val JIANGLING_BODY_ENERGY_OFFSET = 0x1b
    private const val JIANGLING_BODY_ENERGY_LIMIT_OFFSET = 0x1d
    private const val JIANGLING_BODY_TROOP_LIMIT_OFFSET = 0x23
    private const val JIANGLING_BODY_LOYALTY_OFFSET = 0x27
    private const val JIANGLING_BODY_LOYALTY_LIMIT_OFFSET = 0x28
    private const val JIANGLING_BODY_SALARY_OFFSET = 0x29
    private const val JIANGLING_BODY_BREAKOUT_OFFSET = 0x2b
    private const val JIANGLING_BODY_PLACE_ID_OFFSET = 0x32
    private const val JIANGLING_BODY_FO_RAW_OFFSET = 0x3a
    private const val JIANGLING_BODY_STATUS_OFFSET = 0x58
    private const val JIANGLING_BODY_CULTIVATION_COUNT_OFFSET = 0x66
    private const val JIANGLING_BODY_CULTIVATION_LIMIT_OFFSET = 0x68
    private const val S5_ENTRY_LEN = 21
    // Lo/a.S5.Pm is not the scriptSoldier id. It is the zero-based row index in
    // assets/script/scriptSoldier.sc. Example confirmed by live UI: Pm=3 => id=9 轻骑兵.
    private val SOLDIER_TYPES_BY_CODE = listOf(
        SoldierType(0, 1, "民兵", 1, 1),
        SoldierType(1, 6, "弩兵", 2, 2),
        SoldierType(2, 5, "弓兵", 2, 1),
        SoldierType(3, 9, "轻骑兵", 3, 1),
        SoldierType(4, 13, "弩车", 4, 1),
        SoldierType(5, 16, "冲城车", 4, 3),
        SoldierType(6, 2, "轻步兵", 1, 2),
        SoldierType(7, 4, "近卫兵", 1, 4),
        SoldierType(8, 3, "重步兵", 1, 3),
        SoldierType(9, 8, "弩骑兵", 2, 4),
        SoldierType(10, 10, "重骑兵", 3, 2),
        SoldierType(11, 11, "铁骑兵", 3, 3),
        SoldierType(12, 15, "投石车", 4, 4),
        SoldierType(13, 14, "重弩车", 4, 2),
        SoldierType(14, 7, "强弩兵", 2, 3),
        SoldierType(15, 12, "骁骑兵", 3, 4)
    ).associateBy { it.code }

    fun recoverRecordText(raw: String): String? {
        val records = recoverRecords(raw)
        if (records.isEmpty()) return null
        return records.joinToString(separator = "\n") { record ->
            record.entries.joinToString(separator = "|") { (key, value) -> "$key=$value" }
        }
    }

    fun recoverRecords(raw: String): List<Map<String, String>> {
        val textRecords = recoverTextRecords(raw)
        if (textRecords.isNotEmpty()) return textRecords
        val bytes = raw.hexToBytesOrNull() ?: return emptyList()
        val decodedTextRecords = recoverTextRecords(bytes.toDelimitedUtf8Text())
        if (decodedTextRecords.isNotEmpty()) return decodedTextRecords.map { it + ("source" to "state8004-hex-keyvalue") }
        val binaryJiangLingRecords = recoverBinaryJiangLingRecords(bytes)
        if (binaryJiangLingRecords.isNotEmpty()) return binaryJiangLingRecords
        return recoverLengthPrefixedNameCandidates(bytes)
    }

    private fun recoverTextRecords(raw: String): List<Map<String, String>> {
        val normalized = raw.normalizeEvidenceText()
        val explicitJiangLing = Regex("""JiangLing\s*\{([^}]*)\}""", RegexOption.IGNORE_CASE)
            .findAll(normalized)
            .mapNotNull { parseKeyValueMap(it.groupValues[1]) }
            .toList()
        if (explicitJiangLing.isNotEmpty()) return explicitJiangLing

        val idMatches = ID_KEY_REGEX.findAll(normalized).map { it.groups[1]?.range?.first ?: it.range.first }.toList()
        if (idMatches.size >= 2) {
            return idMatches.indices.mapNotNull { index ->
                val start = idMatches[index]
                val end = idMatches.getOrNull(index + 1) ?: normalized.length
                parseKeyValueMap(normalized.substring(start, end))
            }
        }

        return normalized
            .split(Regex("""\r?\n|;;|\|\||\u0000"""))
            .mapNotNull { parseKeyValueMap(it) }
    }

    private fun parseKeyValueMap(record: String): Map<String, String>? {
        val map = KEY_VALUE_REGEX.findAll(record)
            .associate { match ->
                val key = normalizeGeneralKey(match.groupValues[1])
                val value = normalizeGeneralValue(key, match.groupValues[2].trim().trim('\'', '"'))
                key to value
            }
            .toMutableMap()
        if (map.isEmpty()) return null
        val hasId = map.keys.any { it.equals("id", true) || it.equals("generalId", true) || it.equals("jiangLingId", true) }
        val hasUsefulGeneralField = map.keys.any { key ->
            key.equals("name", true) ||
                key.equals("generalName", true) ||
                key.equals("jiangLingName", true) ||
                key.equals("tili", true) ||
                key.equals("status", true) ||
                key.equals("daiBingLimit", true)
        }
        if (!hasId || !hasUsefulGeneralField) return null
        map.putIfAbsent("source", "recovered-jiangling")
        return map
    }

    private fun normalizeGeneralKey(raw: String): String {
        val key = raw.trim()
        return when {
            key.equals("id", true) ||
                key.equals("generalId", true) ||
                key.equals("jiangLingId", true) ||
                key in setOf("编号", "將領ID", "将领ID", "武将ID", "武將ID", "将ID", "將ID") -> "id"

            key.equals("name", true) ||
                key.equals("generalName", true) ||
                key.equals("jiangLingName", true) ||
                key in setOf("名字", "姓名", "名称", "名稱", "将领名", "將領名", "武将名", "武將名") -> "name"

            key.equals("tili", true) ||
                key.equals("energy", true) ||
                key in setOf("体力", "體力") -> "tili"

            key.equals("status", true) ||
                key.equals("state", true) ||
                key in setOf("状态", "狀態") -> "status"

            key.equals("daiBingLimit", true) ||
                key.equals("troopLimit", true) ||
                key in setOf("带兵上限", "帶兵上限", "带兵", "帶兵") -> "daiBingLimit"

            key.equals("tiliLimit", true) ||
                key.equals("energyLimit", true) ||
                key in setOf("体力上限", "體力上限") -> "tiliLimit"

            key.equals("zhongChengdu", true) ||
                key.equals("loyalty", true) ||
                key in setOf("忠诚", "忠誠", "忠诚度", "忠誠度") -> "zhongChengdu"

            key.equals("rank", true) ||
                key.equals("level", true) ||
                key in setOf("等级", "等級", "级别", "級別") -> "rank"

            key.equals("kind", true) ||
                key.equals("type", true) ||
                key in setOf("类型", "類型", "兵种", "兵種") -> "kind"

            key.equals("placeID", true) ||
                key.equals("placeId", true) ||
                key.equals("fiefId", true) ||
                key in setOf("封地ID", "所在封地", "所在地") -> "placeID"

            key.equals("gongji", true) ||
                key.equals("attack", true) ||
                key in setOf("攻击", "攻擊") -> "gongji"

            key.equals("fangyu", true) ||
                key.equals("defense", true) ||
                key in setOf("防御", "防禦") -> "fangyu"

            key.equals("wuli", true) ||
                key.equals("strength", true) ||
                key in setOf("武力") -> "wuli"

            key.equals("zhili", true) ||
                key.equals("intelligence", true) ||
                key in setOf("智力") -> "zhili"

            key.equals("tongshuai", true) ||
                key.equals("command", true) ||
                key in setOf("统帅", "統帥", "统率", "統率") -> "tongshuai"

            key.equals("jingyan", true) ||
                key.equals("exp", true) ||
                key in setOf("经验", "經驗") -> "jingyan"

            key.equals("jingyanLimit", true) ||
                key.equals("expLimit", true) ||
                key in setOf("经验上限", "經驗上限") -> "jingyanLimit"

            key.equals("isFulu", true) ||
                key.equals("fulu", true) ||
                key in setOf("俘虏", "俘虜", "是否俘虏", "是否俘虜") -> "isFulu"

            key.equals("isPeiBingFail", true) ||
                key.equals("peiBingFail", true) ||
                key in setOf("配兵失败", "配兵失敗", "是否配兵失败", "是否配兵失敗") -> "isPeiBingFail"

            else -> key
        }
    }

    private fun normalizeGeneralValue(key: String, raw: String): String {
        val value = raw.trim()
        if (key == "status") {
            return when {
                value == "空闲" || value == "空閒" || value.equals("idle", true) -> "0"
                value.contains("返回") || value.equals("returning", true) -> "4"
                value.contains("战") || value.contains("戰") || value.equals("battle", true) -> "3"
                value.contains("行军") || value.contains("行軍") || value.contains("出征") || value.equals("marching", true) -> "2"
                value.contains("忙") || value.equals("busy", true) -> "1"
                else -> value
            }
        }
        if (key == "isFulu" || key == "isPeiBingFail") {
            return when {
                value.equals("true", true) || value == "1" || value == "是" || value == "真" ||
                    value.contains("失败") || value.contains("失敗") || value.contains("俘虏") || value.contains("俘虜") -> "true"
                value.equals("false", true) || value == "0" || value == "否" || value == "假" ||
                    value.contains("正常") || value.contains("成功") -> "false"
                else -> value
            }
        }
        return value
    }

    private fun recoverBinaryJiangLingRecords(bytes: ByteArray): List<Map<String, String>> {
        val candidates = mutableListOf<BinaryJiangLingRecord>()
        for (nameLenOffset in 8 until bytes.size - 2) {
            val nameLen = bytes.u16AtOrNull(nameLenOffset) ?: continue
            if (nameLen !in 2..24) continue
            val nameOffset = nameLenOffset + 2
            val bodyOffset = nameOffset + nameLen
            if (bodyOffset + JIANGLING_BODY_LEN > bytes.size) continue
            val nameBytes = bytes.copyOfRange(nameOffset, bodyOffset)
            val name = runCatching { String(nameBytes, Charsets.UTF_8) }.getOrNull()?.trim() ?: continue
            if (!name.looksLikeGeneralName()) continue

            val idOffset = nameLenOffset - 8
            val idBytes = bytes.copyOfRange(idOffset, nameLenOffset)
            val id = bytes.i64AtOrNull(idOffset)?.takeIf { it > 0L } ?: continue
            val body = bytes.copyOfRange(bodyOffset, bodyOffset + JIANGLING_BODY_LEN)
            if (!body.looksLikeConfirmedJiangLingBody(idBytes)) continue

            val status = body.u8OrNull(JIANGLING_BODY_STATUS_OFFSET)
            val professionCode = body.u8OrNull(JIANGLING_BODY_PROFESSION_OFFSET)
            // Recovered b6 common layout:
            //   go/body+0x03 = role profession/class (scriptRoleProf.sc)
            //   jo/body+0x08 = level
            //   vo/body+0x23 = daiBingLimit / max troop capacity (u32)
            //   wo/xo body+0x27/0x28 = loyalty current/limit (u8/u8)
            // The current soldier count and soldier type are not in this 114-byte
            // JiangLing body; they are patched from the following Lo/a.S5 state table.
            val growth = body.u16AtOrNull(JIANGLING_BODY_GROWTH_OFFSET)
            val level = body.u8OrNull(JIANGLING_BODY_LEVEL_OFFSET)
            val troopLimit = body.u32AtOrNull(JIANGLING_BODY_TROOP_LIMIT_OFFSET)
            val loyalty = body.u8OrNull(JIANGLING_BODY_LOYALTY_OFFSET)
            val loyaltyLimit = body.u8OrNull(JIANGLING_BODY_LOYALTY_LIMIT_OFFSET)
            val record = linkedMapOf(
                "id" to id.toString(),
                "idHex" to idBytes.toHex(),
                "name" to name,
                "source" to "state8004-binary-jiangling",
                "layout" to "i64_id_u16_name_114_body_b6_common_v20260708b",
                "nameUtf8Offset" to nameLenOffset.toString(),
                "bodyOffset" to bodyOffset.toString(),
                "professionCode" to (professionCode?.toString() ?: ""),
                "kindCode" to (professionCode?.toString() ?: ""),
                "categoryCode" to (professionCode?.toString() ?: ""),
                "kind" to roleProfessionLabel(professionCode),
                "category" to roleProfessionLabel(professionCode),
                "level" to (level?.toString() ?: ""),
                "rank" to (level?.toString() ?: ""),
                "growth" to (growth?.toString() ?: ""),
                "progression" to (growth?.toString() ?: ""),
                "progressionRawCode" to (body.u16AtOrNull(4)?.toString() ?: ""),
                "jingyan" to (body.u32AtOrNull(9)?.toString() ?: ""),
                "jingyanLimit" to (body.u32AtOrNull(13)?.toString() ?: ""),
                "wuli" to (body.u16AtOrNull(17)?.toString() ?: ""),
                "zhili" to (body.u16AtOrNull(19)?.toString() ?: ""),
                "tongshuai" to (body.u16AtOrNull(21)?.toString() ?: ""),
                "gongji" to (body.u16AtOrNull(JIANGLING_BODY_ATTACK_OFFSET)?.toString() ?: ""),
                "fangyu" to (body.u16AtOrNull(JIANGLING_BODY_DEFENSE_OFFSET)?.toString() ?: ""),
                "tili" to (body.u16AtOrNull(JIANGLING_BODY_ENERGY_OFFSET)?.toString() ?: ""),
                "tiliLimit" to (body.u16AtOrNull(JIANGLING_BODY_ENERGY_LIMIT_OFFSET)?.toString() ?: ""),
                "zhongChengdu" to (loyalty?.toString() ?: ""),
                "loyalty" to (loyalty?.toString() ?: ""),
                "loyaltyLimit" to (loyaltyLimit?.toString() ?: ""),
                "daiBingLimit" to (troopLimit?.toString() ?: ""),
                "troopLimit" to (troopLimit?.toString() ?: ""),
                "maxTroopCount" to (troopLimit?.toString() ?: ""),
                "maxSoldierCount" to (troopLimit?.toString() ?: ""),
                "salary" to (body.u16AtOrNull(JIANGLING_BODY_SALARY_OFFSET)?.toString() ?: ""),
                "aoBreakout" to (body.u16AtOrNull(JIANGLING_BODY_BREAKOUT_OFFSET)?.toString() ?: ""),
                "foRawLong" to (body.i64AtOrNull(JIANGLING_BODY_FO_RAW_OFFSET)?.toString() ?: ""),
                "cultivationCount" to (body.u16AtOrNull(JIANGLING_BODY_CULTIVATION_COUNT_OFFSET)?.toString() ?: ""),
                "cultivationLimit" to (body.u16AtOrNull(JIANGLING_BODY_CULTIVATION_LIMIT_OFFSET)?.toString() ?: ""),
                "status" to (status?.toString() ?: ""),
                "statusText" to statusLabel(status),
                "placeID" to (body.i64AtOrNull(JIANGLING_BODY_PLACE_ID_OFFSET)?.toString() ?: ""),
                "bodyHeadHex" to body.copyOfRange(0, 46).toHex()
            )
            candidates += BinaryJiangLingRecord(
                id = id,
                idHex = idBytes.toHex(),
                name = name,
                bodyOffset = bodyOffset,
                body = body,
                fields = linkedMapOf<String, String>().apply {
                    record.filterValues { it.isNotBlank() }.forEach { (key, value) -> this[key] = value }
                }
            )
        }
        val distinct = candidates.distinctBy { it.id to it.name }
        val minS5Offset = distinct.maxOfOrNull { it.bodyOffset + JIANGLING_BODY_LEN } ?: 0
        val troopAssignments = recoverS5TroopAssignments(
            bytes = bytes,
            generalIds = distinct.map { it.id }.toSet(),
            minOffset = minS5Offset
        )
        distinct.forEach { record ->
            val assignment = troopAssignments[record.id] ?: return@forEach
            val soldierType = SOLDIER_TYPES_BY_CODE[assignment.soldierTypeCode]
            record.fields["troopCount"] = assignment.currentSoldierCount.toString()
            record.fields["soldierCount"] = assignment.currentSoldierCount.toString()
            record.fields["currentTroopCount"] = assignment.currentSoldierCount.toString()
            record.fields["currentSoldierCount"] = assignment.currentSoldierCount.toString()
            record.fields["bingli"] = assignment.currentSoldierCount.toString()
            record.fields["troopTypeCode"] = assignment.soldierTypeCode.toString()
            record.fields["soldierTypeCode"] = assignment.soldierTypeCode.toString()
            record.fields["troopTypeSource"] = "Lo/a.S5.Pm"
            record.fields["troopCountSource"] = "Lo/a.S5.Qm"
            record.fields["s5Offset"] = assignment.offset.toString()
            record.fields["s5Count"] = assignment.count.toString()
            if (soldierType != null) {
                record.fields["troopType"] = soldierType.name
                record.fields["soldierType"] = soldierType.name
                record.fields["troopTypeName"] = soldierType.name
                record.fields["soldierTypeName"] = soldierType.name
                record.fields["troopUnitId"] = soldierType.unitId.toString()
                record.fields["soldierUnitId"] = soldierType.unitId.toString()
                record.fields["troopCategoryCode"] = soldierType.category.toString()
                record.fields["troopLevel"] = soldierType.level.toString()
            } else {
                record.fields["troopType"] = "兵种code=${assignment.soldierTypeCode}"
                record.fields["soldierType"] = "兵种code=${assignment.soldierTypeCode}"
            }
        }
        return distinct.map { it.fields }
    }

    private fun ByteArray.looksLikeConfirmedJiangLingBody(idBytes: ByteArray): Boolean {
        if (size < JIANGLING_BODY_LEN) return false
        if (!copyOfRange(JIANGLING_BODY_REPEATED_ID_OFFSET, JIANGLING_BODY_REPEATED_ID_OFFSET + 8).contentEquals(idBytes)) {
            return false
        }
        if (this[112].toInt() != -1 || this[113].toInt() != -1) return false
        val profession = u8OrNull(JIANGLING_BODY_PROFESSION_OFFSET) ?: return false
        val growth = u16AtOrNull(JIANGLING_BODY_GROWTH_OFFSET) ?: return false
        val level = u8OrNull(JIANGLING_BODY_LEVEL_OFFSET) ?: return false
        val tili = u16AtOrNull(JIANGLING_BODY_ENERGY_OFFSET) ?: return false
        val tiliLimit = u16AtOrNull(JIANGLING_BODY_ENERGY_LIMIT_OFFSET) ?: return false
        val troopLimit = u32AtOrNull(JIANGLING_BODY_TROOP_LIMIT_OFFSET) ?: return false
        val loyalty = u8OrNull(JIANGLING_BODY_LOYALTY_OFFSET) ?: return false
        val loyaltyLimit = u8OrNull(JIANGLING_BODY_LOYALTY_LIMIT_OFFSET) ?: return false
        val status = u8OrNull(JIANGLING_BODY_STATUS_OFFSET) ?: return false
        return growth in 1..200 &&
            level in 1..200 &&
            profession in 0..8 &&
            tili in 0..300 &&
            tiliLimit in 1..300 &&
            troopLimit in 0L..50000L &&
            loyalty in 0..200 &&
            loyaltyLimit in 1..200 &&
            status in 0..16
    }

    private fun recoverS5TroopAssignments(
        bytes: ByteArray,
        generalIds: Set<Long>,
        minOffset: Int
    ): Map<Long, S5TroopAssignment> {
        if (generalIds.isEmpty()) return emptyMap()
        val candidates = mutableListOf<Pair<Int, List<S5TroopAssignment>>>()
        for (pos in minOffset until bytes.size) {
            val count = bytes.u8OrNull(pos) ?: continue
            if (count !in 1..30) continue
            val end = pos + 1 + count * S5_ENTRY_LEN
            if (end > bytes.size) continue
            val assignments = mutableListOf<S5TroopAssignment>()
            var allEntriesPlausible = true
            for (index in 0 until count) {
                val offset = pos + 1 + index * S5_ENTRY_LEN
                val nm = bytes.i64AtOrNull(offset)
                if (nm == null) {
                    allEntriesPlausible = false
                    break
                }
                val om = bytes.i64AtOrNull(offset + 8)
                if (om == null) {
                    allEntriesPlausible = false
                    break
                }
                val soldierTypeCode = bytes.u8OrNull(offset + 16)
                if (soldierTypeCode == null) {
                    allEntriesPlausible = false
                    break
                }
                val soldierCount = bytes.i32AtOrNull(offset + 17)
                if (soldierCount == null) {
                    allEntriesPlausible = false
                    break
                }
                if (soldierTypeCode !in 0..32 || soldierCount !in 0..500000) {
                    allEntriesPlausible = false
                    break
                }
                if (nm == om && nm in generalIds) {
                    assignments += S5TroopAssignment(
                        generalId = nm,
                        soldierTypeCode = soldierTypeCode,
                        currentSoldierCount = soldierCount,
                        offset = pos,
                        count = count
                    )
                }
            }
            if (allEntriesPlausible && assignments.isNotEmpty()) {
                candidates += pos to assignments
            }
        }
        val best = candidates.maxWithOrNull(
            compareBy<Pair<Int, List<S5TroopAssignment>>> { it.second.size }
                .thenBy { if (it.second.firstOrNull()?.count == it.second.size) 1 else 0 }
                .thenBy { -it.first }
        ) ?: return emptyMap()
        return best.second.associateBy { it.generalId }
    }

    private fun roleProfessionLabel(code: Int?): String =
        when (code) {
            0 -> "步将"
            1 -> "弓将"
            2 -> "骑将"
            4 -> "勇士"
            null -> ""
            else -> "职业$code"
        }

    private fun statusLabel(status: Int?): String =
        when (status) {
            0 -> "空闲"
            1 -> "出征"
            2 -> "驻防"
            3 -> "被俘"
            4 -> "返回"
            null -> ""
            else -> "状态$status"
        }

    private fun recoverLengthPrefixedNameCandidates(bytes: ByteArray): List<Map<String, String>> {
        val out = mutableListOf<Map<String, String>>()
        for (pos in 8 until bytes.size - 2) {
            val len = bytes.u16At(pos)
            if (len !in 2..24 || pos + 2 + len > bytes.size) continue
            val nameBytes = bytes.copyOfRange(pos + 2, pos + 2 + len)
            val name = runCatching { String(nameBytes, Charsets.UTF_8) }.getOrNull()?.trim() ?: continue
            if (!name.looksLikeGeneralName()) continue
            val id = bytes.i64At(pos - 8)
            if (id <= 0L) continue
            val after = pos + 2 + len
            val raw = mutableMapOf(
                "id" to id.toString(),
                "name" to name,
                "source" to "state8004-binary-name-candidate",
                "idHex" to bytes.copyOfRange(pos - 8, pos).toHex(),
                "nameUtf8Offset" to pos.toString()
            )
            bytes.u8OrNull(after)?.takeIf { it in 0..8 }?.let { raw["status"] = it.toString() }
            bytes.u8OrNull(after + 1)?.takeIf { it in 0..200 }?.let { raw["tili"] = it.toString() }
            out += raw
        }
        return out.distinctBy { it["id"] to it["name"] }
    }

    private fun String.normalizeEvidenceText(): String =
        map { ch ->
            when {
                ch == '\u0000' -> '|'
                ch.code in 0x20..0x7e -> ch
                ch in '\u4e00'..'\u9fff' -> ch
                ch == '\n' || ch == '\r' || ch == '\t' -> ch
                else -> '|'
            }
        }.joinToString(separator = "")

    private fun String.hexToBytesOrNull(): ByteArray? {
        if (!HEX_REGEX.matches(trim())) return null
        val hex = trim()
            .removePrefix("0x")
            .removePrefix("0X")
            .filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
        if (hex.length < 2 || hex.length % 2 != 0) return null
        return runCatching {
            ByteArray(hex.length / 2) { index -> hex.substring(index * 2, index * 2 + 2).toInt(16).toByte() }
        }.getOrNull()
    }

    private fun ByteArray.toDelimitedUtf8Text(): String =
        String(this, Charsets.UTF_8).normalizeEvidenceText()

    private fun String.looksLikeGeneralName(): Boolean {
        if (isBlank() || length > 8) return false
        if (contains("id", ignoreCase = true) || contains("http", ignoreCase = true)) return false
        val chineseCount = count { it in '\u4e00'..'\u9fff' }
        return chineseCount >= 1 && all { it in '\u4e00'..'\u9fff' || it.isLetterOrDigit() || it == '·' }
    }

    private fun ByteArray.u8OrNull(index: Int): Int? =
        if (index in indices) this[index].toInt() and 0xff else null

    private fun ByteArray.u16At(index: Int): Int =
        ((this[index].toInt() and 0xff) shl 8) or (this[index + 1].toInt() and 0xff)

    private fun ByteArray.u16AtOrNull(index: Int): Int? =
        if (index >= 0 && index + 1 < size) u16At(index) else null

    private fun ByteArray.u32AtOrNull(index: Int): Long? {
        if (index < 0 || index + 3 >= size) return null
        return ((this[index].toLong() and 0xffL) shl 24) or
            ((this[index + 1].toLong() and 0xffL) shl 16) or
            ((this[index + 2].toLong() and 0xffL) shl 8) or
            (this[index + 3].toLong() and 0xffL)
    }

    private fun ByteArray.i32AtOrNull(index: Int): Int? {
        if (index < 0 || index + 3 >= size) return null
        return ((this[index].toInt() and 0xff) shl 24) or
            ((this[index + 1].toInt() and 0xff) shl 16) or
            ((this[index + 2].toInt() and 0xff) shl 8) or
            (this[index + 3].toInt() and 0xff)
    }

    private fun ByteArray.i64AtOrNull(index: Int): Long? =
        if (index >= 0 && index + 7 < size) i64At(index) else null

    private fun ByteArray.i64At(index: Int): Long {
        var value = 0L
        for (offset in 0 until 8) value = (value shl 8) or (this[index + offset].toLong() and 0xffL)
        return value
    }

    private fun ByteArray.toHex(): String = joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
}

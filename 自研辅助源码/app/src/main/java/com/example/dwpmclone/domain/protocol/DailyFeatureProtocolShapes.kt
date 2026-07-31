package com.example.dwpmclone.domain.protocol

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

/**
 * The city-kind byte in each 0x8404 record is zero based.  The list-filter
 * byte is one based (1=州城 ... 4=小城); they are deliberately kept as two
 * separate mappings because the captured protocol uses both representations.
 */
enum class NationalCityKind(val wireKind: Int, val priority: Int) {
    STATE(0, 0),
    COMMANDERY(1, 1),
    COUNTY(2, 2),
    SMALL(3, 3),
    UNKNOWN(0, 99);

    companion object {
        fun fromWire(value: Int): NationalCityKind = entries.firstOrNull { it.wireKind == value } ?: UNKNOWN

        /** The list request categories observed in 0x1404/0x8404. */
        fun fromListCategory(category: Int): NationalCityKind = when (category) {
            1 -> STATE
            2 -> COMMANDERY
            3 -> COUNTY
            4 -> SMALL
            else -> UNKNOWN
        }
    }
}

data class NationalCity(
    val name: String,
    val kind: NationalCityKind,
    val x: Int,
    val y: Int,
    val ownerLabel: String,
    val listCategory: Int,
    val rawTailHex: String = ""
)

data class NationalCityPage(
    val status: Int,
    val category: Int,
    val totalPages: Int,
    val page: Int,
    val cities: List<NationalCity>
)

data class NationalCollectStatus(
    val status: Int,
    val availability: Int,
    val usedCount: Int,
    val limit: Int,
    val currentCopper: Long,
    val copperCap: Long,
    val currentFood: Long,
    val foodCap: Long
) {
    val canCollect: Boolean
        get() = status == 0 && availability == 0 && usedCount < limit && currentCopper > 0L

    val quotaExhausted: Boolean
        get() = usedCount >= limit
}

data class SalaryReceipt(
    val status: Int,
    val extra: Int?,
    val message: String,
    val values: List<Long>,
    val success: Boolean,
    val completed: Boolean,
    val alreadyClaimed: Boolean,
    val noOffice: Boolean,
    val copper: Long?,
    val food: Long?
)

data class NationalCollectReceipt(
    val status: Int,
    val extra: Int?,
    val message: String,
    val values: List<Long>,
    val success: Boolean
)

data class CityLordCollectReceipt(
    val status: Int,
    val extra: Int?,
    val message: String,
    val values: List<Long>,
    val success: Boolean
)

data class OwnedCityRecord(
    val index: Int,
    val id: Long,
    val kindCode: Int,
    val name: String,
    val x: Int,
    val y: Int,
    val ownerName: String = "",
    val ownerLevel: Int? = null
)

data class GeneralVisitCandidate(
    val id: Long,
    val name: String,
    val level: Int,
    val fiefName: String,
    val cityName: String,
    val captiveState: Int,
    val ownerName: String,
    val salaryStars: Int,
    val loyalty: Int,
    val growth: Int,
    val breakout: Int,
    val strengthBase: Int,
    val strengthTotal: Int,
    val intelligenceBase: Int,
    val intelligenceTotal: Int,
    val command: Int,
    val troopLimit: Int,
    val exp: Long,
    val expLimit: Long,
    val job: Int,
    val portrait: Int,
    val raw: Map<String, String> = emptyMap()
)

data class GeneralVisitPage(
    val status: Int,
    val message: String,
    val pageSize: Int,
    val page: Int,
    val candidates: List<GeneralVisitCandidate>,
    val completed: Boolean = false,
    val alreadyVisited: Boolean = false,
    val shortReceipt: Boolean = false
)

data class GeneralVisitQuery(
    val candidates: List<GeneralVisitCandidate>,
    val completed: Boolean = false,
    val alreadyVisited: Boolean = false,
    val message: String = ""
)

data class GeneralVisitReceipt(
    val status: Int,
    val message: String,
    val success: Boolean,
    val completed: Boolean,
    val recruited: Boolean,
    val alreadyVisited: Boolean,
    val invitationResolved: Boolean,
    val invitationRejected: Boolean,
    val refreshedPage: GeneralVisitPage? = null
)

object DailyFeatureProtocolShapes {
    const val NATIONAL_LIST_OPCODE = 0x1404
    const val NATIONAL_STATUS_OPCODE = 0x1332
    const val NATIONAL_COLLECT_OPCODE = 0x1334
    const val SALARY_OPCODE = 0x314B
    const val CITY_LORD_LIST_OPCODE = 0x1318
    const val CITY_LORD_COLLECT_OPCODE = 0x1330
    const val GENERAL_LIST_OPCODE = 0x3271
    const val GENERAL_VISIT_OPCODE = 0x3273

    const val DEFAULT_GENERAL_PAGE_SIZE = 4
    const val NATIONAL_LIST_PAGE_SIZE = 10
    const val NATIONAL_RESPONSE_HEADER_BYTES = 7
    const val NATIONAL_RECORD_TAIL_BYTES = 34

    fun buildDonationResourcePayload(copper: Long, food: Long): ByteArray =
        ByteBuffer.allocate(24).putLong(copper).putLong(food).putLong(0L).array()

    fun buildDonateCopperPayload(amount: Long): ByteArray =
        buildDonationResourcePayload(amount, 0L)

    fun buildDonateFoodPayload(amount: Long): ByteArray =
        buildDonationResourcePayload(0L, amount)

    /** 0x140a: mode byte followed by the integer contribution amount. */
    fun buildDonateTechPayload(amount: Int): ByteArray =
        ByteBuffer.allocate(5).put(0).putInt(amount).array()

    fun buildSalaryPayload(): ByteArray = byteArrayOf(1)

    /** 0x1404: long 1, list category byte, one-based page short. */
    fun buildNationalCityListPayload(category: Int, page: Int): ByteArray {
        require(category in 0..255) { "城池分类超出 byte 范围: $category" }
        require(page in 1..Short.MAX_VALUE) { "城池页码无效: $page" }
        return ByteBuffer.allocate(11)
            .putLong(1L)
            .put(category.toByte())
            .putShort(page.toShort())
            .array()
    }

    fun buildNationalCityStatusPayload(cityName: String): ByteArray = buildCityNamePayload(cityName)

    fun buildNationalCollectPayload(cityName: String): ByteArray = buildCityNamePayload(cityName)

    /** Captured 0x1318 owned-city request: role id followed by u16 zero. */
    fun buildOwnedCityListPayload(
        roleId: Long,
        suffix: ByteArray = CityLordCollectBehaviorContract.defaults().ownedCityPayloadSuffix
    ): ByteArray {
        require(roleId >= 0L) { "自有城池查询 roleId 无效" }
        require(suffix.isNotEmpty()) { "自有城池查询后缀不能为空" }
        return ByteBuffer.allocate(Long.SIZE_BYTES + suffix.size)
            .putLong(roleId)
            .put(suffix)
            .array()
    }

    /** Captured 0x1330 shape: name selector + UTF city name + trailing mode byte 0. */
    fun buildCityLordCollectPayload(cityName: String): ByteArray =
        ByteArrayOutputStream().also { bytes ->
            DataOutputStream(bytes).use { out ->
                out.writeByte(1)
                out.writeUTF(cityName.trim())
                out.writeByte(0)
            }
        }.toByteArray()

    fun buildGeneralListPayload(page: Int, pageSize: Int = DEFAULT_GENERAL_PAGE_SIZE): ByteArray =
        ByteBuffer.allocate(4).putShort(page.toShort()).putShort(pageSize.toShort()).array()

    fun buildGeneralVisitPayload(
        generalId: Long,
        page: Int,
        pageSize: Int = DEFAULT_GENERAL_PAGE_SIZE
    ): ByteArray = ByteBuffer.allocate(12)
        .putLong(generalId)
        .putShort(page.toShort())
        .putShort(pageSize.toShort())
        .array()

    fun parseSalaryReceipt(
        payload: ByteArray,
        contract: SalaryBehaviorContract = SalaryBehaviorContract.defaults()
    ): SalaryReceipt {
        require(payload.isNotEmpty()) { "0xa14b响应为空" }
        val status = payload[0].toInt()
        var extra: Int? = payload.getOrNull(1)?.toInt()?.and(0xff)
        val preferred = readUtfAt(payload, 2)
        val fallback = readUtfAt(payload, 1)
        val parsed = preferred ?: fallback?.also { extra = null }
        val message = parsed?.first.orEmpty()
        val offset = parsed?.second ?: 1
        val values = buildList {
            var cursor = offset
            while (cursor + Long.SIZE_BYTES <= payload.size) {
                add(ByteBuffer.wrap(payload, cursor, Long.SIZE_BYTES).long)
                cursor += Long.SIZE_BYTES
            }
        }
        val alreadyClaimed = contract.alreadyClaimedMarkers.any(message::contains)
        val noOffice = contract.noOfficeMarkers.any(message::contains)
        val successByText = contract.successMarkers.any(message::contains)
        val copper = extractAmount(message, "铜钱")
        val food = extractAmount(message, "粮食")
        val success = status == 1 ||
            (status == 0 && (extra == 1 || successByText || copper != null || food != null) && !noOffice) ||
            alreadyClaimed
        return SalaryReceipt(
            status = status,
            extra = extra,
            message = message,
            values = values,
            success = success,
            completed = success || alreadyClaimed,
            alreadyClaimed = alreadyClaimed,
            noOffice = noOffice,
            copper = copper,
            food = food
        )
    }

    fun parseNationalCityPage(
        payload: ByteArray,
        requestedCategory: Int,
        contract: NationalCollectBehaviorContract = NationalCollectBehaviorContract.defaults()
    ): NationalCityPage {
        require(contract.responseHeaderBytes == NATIONAL_RESPONSE_HEADER_BYTES) {
            "0x8404响应头契约必须为7字节"
        }
        val cursor = Cursor(payload)
        val status = cursor.u8()
        val responseCategory = cursor.u8()
        val totalPages = cursor.u16()
        val page = cursor.u16()
        val count = cursor.u8()
        // Desktop parity: only an explicit one-based response category is
        // authoritative.  A zero/unknown byte falls back to the requested
        // filter so broad replies cannot lose their hierarchy classification.
        val category = if (responseCategory in 1..5) responseCategory else requestedCategory
        val cities = buildList(count) {
            repeat(count) {
                val name = cursor.utf()
                val kind = NationalCityKind.fromWire(cursor.u8())
                val x = cursor.i16()
                val y = cursor.i16()
                val owner = cursor.utf()
                val tail = cursor.bytes(contract.recordTailBytes)
                add(
                    NationalCity(
                        name = name,
                        kind = kind,
                        x = x,
                        y = y,
                        ownerLabel = owner,
                        listCategory = category,
                        rawTailHex = tail.toHex()
                    )
                )
            }
        }
        return NationalCityPage(status, category, totalPages, page, cities)
    }

    fun parseNationalCityList(payload: ByteArray, requestedCategory: Int): List<NationalCity> =
        parseNationalCityPage(payload, requestedCategory).cities

    /**
     * Parse the captured 0x8318 owned-city response used by city-lord collection.
     * The server sometimes declares count=0 while still appending one city detail,
     * so the body itself remains authoritative just as in the desktop parser.
     */
    fun parseOwnedCityList(payload: ByteArray): List<OwnedCityRecord> {
        require(payload.isNotEmpty()) { "0x8318响应为空" }
        val status = payload[0].toInt() and 0xff
        // The live server returns a one-byte status=1 receipt when the role owns no city.
        // Treat it as the same terminal no-city result as the desktop parser instead of
        // demanding a count byte that is deliberately absent from this business receipt.
        if (status == 1) return emptyList()
        require(payload.size >= 2) { "0x8318响应过短: ${payload.size}" }
        val declaredCount = payload[1].toInt() and 0xff

        fun recordAt(start: Int, index: Int): Pair<OwnedCityRecord, Int>? {
            if (start < 0 || start + 13 > payload.size) return null
            val id = ByteBuffer.wrap(payload, start, Long.SIZE_BYTES).long
            val kindCode = payload[start + Long.SIZE_BYTES].toInt() and 0xff
            val nameField = readUtfAt(payload, start + Long.SIZE_BYTES + 1) ?: return null
            val coordinateOffset = nameField.second
            if (coordinateOffset + 4 > payload.size) return null
            val x = readU16(payload, coordinateOffset)
            val y = readU16(payload, coordinateOffset + 2)
            val minimumEnd = coordinateOffset + 4
            var ownerName = ""
            var ownerLevel: Int? = null
            val ownerScanEnd = minOf(payload.size - 2, minimumEnd + 64)
            for (probe in minimumEnd..ownerScanEnd) {
                val field = readUtfAt(payload, probe) ?: continue
                val text = field.first
                if (text.length !in 1..30 || text.none { it in '\u4e00'..'\u9fff' }) continue
                ownerName = text
                ownerLevel = payload.getOrNull(field.second)?.toInt()?.and(0xff)
                break
            }
            return OwnedCityRecord(
                index = index,
                id = id,
                kindCode = kindCode,
                name = nameField.first,
                x = x,
                y = y,
                ownerName = ownerName,
                ownerLevel = ownerLevel
            ) to minimumEnd
        }

        val records = mutableListOf<OwnedCityRecord>()
        var cursor = 2
        val expected = if (declaredCount > 0) declaredCount else 1
        for (zeroIndex in 0 until expected) {
            val parsed = recordAt(cursor, zeroIndex + 1) ?: break
            records += parsed.first
            if (zeroIndex + 1 >= expected) break
            cursor = findNextOwnedCityRecordStart(payload, parsed.second) ?: break
        }
        return records
    }

    fun parseNationalCollectStatus(payload: ByteArray): NationalCollectStatus {
        require(payload.size >= 36) { "0x8332响应过短: ${payload.size}" }
        val cursor = Cursor(payload)
        return NationalCollectStatus(
            status = cursor.u8(),
            availability = cursor.u8(),
            usedCount = cursor.u8(),
            limit = cursor.u8(),
            currentCopper = cursor.i64(),
            copperCap = cursor.i64(),
            currentFood = cursor.i64(),
            foodCap = cursor.i64()
        )
    }

    fun parseNationalCollectReceipt(payload: ByteArray): NationalCollectReceipt {
        val compact = parseCompactDailyReceipt(payload, successStatus = 1)
        return NationalCollectReceipt(
            status = compact.status,
            extra = null,
            message = compact.message,
            values = compact.values,
            success = compact.success
        )
    }

    fun parseCityLordCollectReceipt(payload: ByteArray): CityLordCollectReceipt {
        val compact = parseCompactDailyReceipt(payload, successStatus = 1)
        return CityLordCollectReceipt(
            status = compact.status,
            extra = null,
            message = compact.message,
            values = compact.values,
            success = compact.success
        )
    }

    fun parseGeneralVisitPage(
        payload: ByteArray,
        contract: GeneralVisitBehaviorContract = GeneralVisitBehaviorContract.defaults()
    ): GeneralVisitPage {
        require(payload.size >= 3) { "0xa271响应过短: ${payload.size}" }
        val status = payload[0].toInt()
        val cursor = Cursor(payload, 1)
        val message = cursor.utfOrEmpty()
        val alreadyVisited = status == contract.alreadyVisitedStatus &&
            contract.alreadyVisitedMarkers.any(message::contains)
        if (cursor.remaining < 5) {
            return GeneralVisitPage(
                status = status,
                message = message,
                pageSize = 0,
                page = 0,
                candidates = emptyList(),
                completed = alreadyVisited,
                alreadyVisited = alreadyVisited,
                shortReceipt = true
            )
        }
        val pageSize = cursor.u16()
        val page = cursor.u16()
        val count = cursor.u8()
        val candidates = buildList(count) {
            repeat(count) { add(parseGeneral(cursor)) }
        }
        return GeneralVisitPage(
            status = status,
            message = message,
            pageSize = pageSize,
            page = page,
            candidates = candidates,
            completed = alreadyVisited,
            alreadyVisited = alreadyVisited
        )
    }

    fun parseGeneralVisitReceipt(
        payload: ByteArray,
        contract: GeneralVisitBehaviorContract = GeneralVisitBehaviorContract.defaults()
    ): GeneralVisitReceipt {
        val cursor = Cursor(payload)
        val status = cursor.i32()
        val message = cursor.utfOrEmpty()
        val alreadyVisited = status == contract.alreadyVisitedStatus &&
            contract.alreadyVisitedMarkers.any(message::contains)
        val invitationResolved = status == 0 &&
            contract.invitationResolvedMarkers.any(message::contains)
        val recruited = status == 1
        val invitationRejected = invitationResolved && "拒绝了阁下的邀请" in message
        val success = recruited || invitationResolved
        val refreshed = if (cursor.remaining >= 5) {
            runCatching { parseGeneralVisitListBody(cursor.remainingBytes()) }.getOrNull()
        } else {
            null
        }
        return GeneralVisitReceipt(
            status = status,
            message = message,
            success = success,
            completed = success || alreadyVisited,
            recruited = recruited,
            alreadyVisited = alreadyVisited,
            invitationResolved = invitationResolved,
            invitationRejected = invitationRejected,
            refreshedPage = refreshed
        )
    }

    /**
     * 0xA273 appends the same page body used by 0xA271 after its own int+UTF receipt,
     * but without another status/message prefix.
     */
    fun parseGeneralVisitListBody(payload: ByteArray): GeneralVisitPage {
        val cursor = Cursor(payload)
        val pageSize = cursor.u16()
        val page = cursor.u16()
        val count = cursor.u8()
        val candidates = buildList(count) {
            repeat(count) { add(parseGeneral(cursor)) }
        }
        return GeneralVisitPage(
            status = 0,
            message = "",
            pageSize = pageSize,
            page = page,
            candidates = candidates
        )
    }

    fun mergeGeneralPages(pages: List<GeneralVisitPage>): List<GeneralVisitCandidate> =
        pages.flatMap { it.candidates }.distinctBy { it.id }

    private fun buildCityNamePayload(cityName: String): ByteArray =
        ByteArrayOutputStream().also { bytes ->
            DataOutputStream(bytes).use { out ->
                out.writeByte(1)
                out.writeUTF(cityName.trim())
            }
        }.toByteArray()

    private fun parseGeneral(cursor: Cursor): GeneralVisitCandidate {
        val id = cursor.i64()
        val name = cursor.utf()
        cursor.u8() // unknown
        cursor.u8() // unknown
        val level = cursor.u8()
        val job = cursor.u8()
        val portrait = cursor.i16()
        val fiefName = cursor.utf()
        val cityName = cursor.utf()
        val captiveState = cursor.u8()
        val ownerName = cursor.utf()
        val salaryStars = cursor.i16()
        val loyalty = cursor.u8()
        val exp = cursor.i64()
        val expLimit = cursor.i64()
        cursor.i16() // unknown
        cursor.i16() // unknown
        val growth = cursor.i16()
        val breakout = cursor.i16()
        val strengthBase = cursor.i16()
        val strengthTotal = cursor.i16()
        val intelligenceBase = cursor.i16()
        val intelligenceTotal = cursor.i16()
        val command = cursor.i16()
        val troopLimit = cursor.i16()
        return GeneralVisitCandidate(
            id = id,
            name = name,
            level = level,
            fiefName = fiefName,
            cityName = cityName,
            captiveState = captiveState,
            ownerName = ownerName,
            salaryStars = salaryStars,
            loyalty = loyalty,
            growth = growth,
            breakout = breakout,
            strengthBase = strengthBase,
            strengthTotal = strengthTotal,
            intelligenceBase = intelligenceBase,
            intelligenceTotal = intelligenceTotal,
            command = command,
            troopLimit = troopLimit,
            exp = exp,
            expLimit = expLimit,
            job = job,
            portrait = portrait
        )
    }

    private fun containsFailure(message: String): Boolean {
        val text = message.trim()
        if (text.isBlank()) return false
        return listOf("无法", "不能", "拒绝", "被俘", "已经被结交", "已被结交", "次数已满", "额度已满")
            .any(text::contains)
    }

    private fun containsSuccess(message: String): Boolean {
        val text = message.trim()
        if (text.isBlank()) return false
        return listOf("成功", "获得", "领取完毕").any(text::contains)
    }

    private data class CompactDailyReceipt(
        val status: Int,
        val message: String,
        val values: List<Long>,
        val success: Boolean
    )

    private fun parseCompactDailyReceipt(
        payload: ByteArray,
        successStatus: Int
    ): CompactDailyReceipt {
        require(payload.isNotEmpty()) { "日常回执为空" }
        val status = payload[0].toInt()
        val parsed = readUtfAt(payload, 1)
        val message = parsed?.first.orEmpty()
        val values = buildList {
            var offset = parsed?.second ?: 1
            while (offset + Long.SIZE_BYTES <= payload.size) {
                add(ByteBuffer.wrap(payload, offset, Long.SIZE_BYTES).long)
                offset += Long.SIZE_BYTES
            }
        }
        return CompactDailyReceipt(
            status = status,
            message = message,
            values = values,
            success = status == successStatus
        )
    }

    private fun extractAmount(message: String, label: String): Long? =
        Regex("${Regex.escape(label)}\\s*([0-9,，]+)")
            .find(message)
            ?.groupValues
            ?.getOrNull(1)
            ?.replace(",", "")
            ?.replace("，", "")
            ?.toLongOrNull()

    private fun readU16(bytes: ByteArray, offset: Int): Int {
        require(offset >= 0 && offset + 2 <= bytes.size) { "u16字段越界 offset=$offset" }
        return ((bytes[offset].toInt() and 0xff) shl 8) or
            (bytes[offset + 1].toInt() and 0xff)
    }

    private fun readUtfAt(bytes: ByteArray, offset: Int): Pair<String, Int>? {
        if (offset < 0 || offset + 2 > bytes.size) return null
        val length = readU16(bytes, offset)
        val end = offset + 2 + length
        if (length < 0 || end > bytes.size) return null
        val value = decodeUtf8Strict(bytes, offset + 2, end) ?: return null
        return value to end
    }

    private fun findNextOwnedCityRecordStart(bytes: ByteArray, from: Int): Int? {
        var scan = from.coerceAtLeast(0)
        while (scan + 11 <= bytes.size) {
            val nameLength = readU16(bytes, scan + 9)
            val end = scan + 11 + nameLength
            if (nameLength in 1..30 && end <= bytes.size) {
                val text = decodeUtf8Strict(bytes, scan + 11, end).orEmpty()
                if (text.any { it in '\u4e00'..'\u9fff' }) return scan
            }
            scan++
        }
        return null
    }

    /** Reject malformed byte ranges instead of silently inserting U+FFFD replacement chars. */
    private fun decodeUtf8Strict(bytes: ByteArray, start: Int, end: Int): String? = runCatching {
        Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes, start, end - start))
            .toString()
    }.getOrNull()

    private class Cursor(private val bytes: ByteArray, private var position: Int = 0) {
        val remaining: Int
            get() = bytes.size - position

        fun u8(): Int {
            require(remaining >= 1) { "响应缺少 byte，offset=$position" }
            return bytes[position++].toInt() and 0xff
        }

        fun i16(): Int {
            require(remaining >= 2) { "响应缺少 short，offset=$position" }
            val value = ByteBuffer.wrap(bytes, position, 2).short.toInt()
            position += 2
            return value
        }

        fun u16(): Int {
            require(remaining >= 2) { "响应缺少 unsigned short，offset=$position" }
            val value = ((bytes[position].toInt() and 0xff) shl 8) or
                (bytes[position + 1].toInt() and 0xff)
            position += 2
            return value
        }

        fun i32(): Int {
            require(remaining >= 4) { "响应缺少 int，offset=$position" }
            val value = ByteBuffer.wrap(bytes, position, 4).int
            position += 4
            return value
        }

        fun i64(): Long {
            require(remaining >= 8) { "响应缺少 long，offset=$position" }
            val value = ByteBuffer.wrap(bytes, position, 8).long
            position += 8
            return value
        }

        fun utf(): String {
            val length = u16()
            require(remaining >= length) { "UTF字段越界，length=$length offset=$position" }
            val value = bytes.copyOfRange(position, position + length).toString(Charsets.UTF_8)
            position += length
            return value
        }

        fun utfOrEmpty(): String = if (remaining >= 2) utf() else ""

        fun bytes(length: Int): ByteArray {
            require(length >= 0 && remaining >= length) { "响应尾部不完整，length=$length offset=$position" }
            return bytes.copyOfRange(position, position + length).also { position += length }
        }

        fun longsRemaining(): List<Long> {
            val count = remaining / 8
            return List(count) { i64() }
        }

        fun remainingBytes(): ByteArray = bytes.copyOfRange(position, bytes.size)
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
}

package com.example.dwpmclone.domain.protocol

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.nio.ByteBuffer

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
    val extra: Int,
    val message: String,
    val values: List<Long>,
    val success: Boolean
)

data class NationalCollectReceipt(
    val status: Int,
    val extra: Int,
    val message: String,
    val values: List<Long>,
    val success: Boolean
)

data class CityLordCollectReceipt(
    val status: Int,
    val extra: Int,
    val message: String,
    val values: List<Long>,
    val success: Boolean
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
    val candidates: List<GeneralVisitCandidate>
)

data class GeneralVisitReceipt(
    val status: Int,
    val message: String,
    val success: Boolean,
    val refreshedPage: GeneralVisitPage? = null
)

object DailyFeatureProtocolShapes {
    const val NATIONAL_LIST_OPCODE = 0x1404
    const val NATIONAL_STATUS_OPCODE = 0x1332
    const val NATIONAL_COLLECT_OPCODE = 0x1334
    const val SALARY_OPCODE = 0x314B
    const val CITY_LORD_LIST_OPCODE = 0x1310
    const val CITY_LORD_COLLECT_OPCODE = 0x1330
    const val GENERAL_LIST_OPCODE = 0x3271
    const val GENERAL_VISIT_OPCODE = 0x3273

    const val DEFAULT_GENERAL_PAGE_SIZE = 4
    const val NATIONAL_LIST_PAGE_SIZE = 10
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

    /**
     * reqRoleFiefList type=4.  The recovered client writes a fixed mode byte 1,
     * followed by a target selector: 1 + UTF name, or 0 + long role id.
     */
    fun buildOwnedFiefListPayload(roleName: String? = null, roleId: Long = 0L): ByteArray =
        ByteArrayOutputStream().also { bytes ->
            DataOutputStream(bytes).use { out ->
                out.writeByte(1)
                if (!roleName.isNullOrBlank()) {
                    out.writeByte(1)
                    out.writeUTF(roleName.trim())
                } else {
                    out.writeByte(0)
                    out.writeLong(roleId)
                }
            }
        }.toByteArray()

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

    fun parseSalaryReceipt(payload: ByteArray): SalaryReceipt {
        val cursor = Cursor(payload)
        val status = cursor.u8()
        val extra = cursor.u8()
        val message = cursor.utfOrEmpty()
        val values = cursor.longsRemaining()
        val success = status == 0 && !containsFailure(message) &&
            (extra == 1 || containsSuccess(message))
        return SalaryReceipt(status, extra, message, values, success)
    }

    fun parseNationalCityPage(payload: ByteArray, requestedCategory: Int): NationalCityPage {
        val cursor = Cursor(payload)
        val status = cursor.u8()
        cursor.u8() // reserved; captured as 0
        val responseCategory = cursor.u8()
        val totalPages = cursor.u16()
        val page = cursor.u16()
        val count = cursor.u8()
        // Captured responses use 0 for the unfiltered/all list and 1..4 for
        // the four hierarchy filters.  Preserve 0 instead of replacing it
        // with the requested category; callers use it to distinguish a broad
        // response from a filtered page.
        val category = if (responseCategory in 0..4) responseCategory else requestedCategory
        val cities = buildList(count) {
            repeat(count) {
                val name = cursor.utf()
                val kind = NationalCityKind.fromWire(cursor.u8())
                val x = cursor.i16()
                val y = cursor.i16()
                val owner = cursor.utf()
                val tail = cursor.bytes(NATIONAL_RECORD_TAIL_BYTES)
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
        val cursor = Cursor(payload)
        val status = cursor.u8()
        val extra = cursor.u8()
        val message = cursor.utfOrEmpty()
        val values = cursor.longsRemaining()
        val success = status == 0 && !containsFailure(message) &&
            (extra == 1 || containsSuccess(message))
        return NationalCollectReceipt(status, extra, message, values, success)
    }

    fun parseCityLordCollectReceipt(payload: ByteArray): CityLordCollectReceipt {
        val cursor = Cursor(payload)
        val status = cursor.u8()
        val extra = cursor.u8()
        val message = cursor.utfOrEmpty()
        val values = cursor.longsRemaining()
        val success = status == 0 && !containsFailure(message) &&
            (extra == 1 || containsSuccess(message))
        return CityLordCollectReceipt(status, extra, message, values, success)
    }

    fun parseGeneralVisitPage(payload: ByteArray): GeneralVisitPage {
        val cursor = Cursor(payload)
        val status = cursor.u8()
        val message = cursor.utfOrEmpty()
        val pageSize = cursor.u16()
        val page = cursor.u16()
        val count = cursor.u8()
        val candidates = buildList(count) {
            repeat(count) { add(parseGeneral(cursor)) }
        }
        return GeneralVisitPage(status, message, pageSize, page, candidates)
    }

    fun parseGeneralVisitReceipt(payload: ByteArray): GeneralVisitReceipt {
        val cursor = Cursor(payload)
        val status = cursor.i32()
        val message = cursor.utfOrEmpty()
        val failure = containsFailure(message) || status in setOf(-7, -6)
        // Recovered La0/a.A1 treats status=1 as the successful branch.  Captures
        // include status=0 with an explicit refusal, so non-negative is not enough.
        val success = !failure && status == 1
        val refreshed = if (cursor.remaining >= 5) {
            runCatching { parseGeneralVisitListBody(cursor.remainingBytes()) }.getOrNull()
        } else {
            null
        }
        return GeneralVisitReceipt(status, message, success, refreshed)
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

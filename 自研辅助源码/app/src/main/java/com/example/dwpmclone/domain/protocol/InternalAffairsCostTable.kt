package com.example.dwpmclone.domain.protocol

/**
 * Resource costs recovered from the same game-rule tables used by the desktop helper:
 * - building_level_cost_rules.csv
 * - tech_levels.json
 *
 * Only copper/food are represented here because those are the two resources that the
 * desktop "粮食转铜" recovery path can satisfy. Cost-C items remain server-authoritative.
 */
data class InternalResourceCost(
    val copper: Long,
    val food: Long
)

object InternalAffairsCostTable {
    private val buildingCopper = mapOf(
        0 to longArrayOf(0L, 180L, 540L, 1080L, 2160L, 4320L, 6480L, 9720L, 12636L, 16425L, 33728L, 56192L, 84753L, 120425L, 164300L),
        1 to longArrayOf(26L, 78L, 234L, 468L, 936L, 1872L, 2808L, 4212L, 5475L, 7118L, 11111L, 16295L, 22886L, 31118L, 41243L),
        2 to longArrayOf(20L, 60L, 180L, 360L, 720L, 1440L, 2160L, 3240L, 4212L, 5475L, 9468L, 14652L, 21243L, 29475L, 39600L),
        3 to longArrayOf(44L, 132L, 396L, 792L, 1584L, 3168L, 4752L, 7128L, 9266L, 12045L, 20829L, 32234L, 46734L, 64845L, 87120L),
        4 to longArrayOf(30L, 90L, 270L, 540L, 1080L, 2160L, 3240L, 4860L, 6318L, 8212L),
        5 to longArrayOf(30L, 90L, 270L, 540L, 1080L, 2160L, 3240L, 4860L, 6318L, 8212L),
        6 to longArrayOf(36L, 108L, 326L, 653L, 1306L, 2613L, 3920L, 5880L, 7643L, 9936L),
        8 to longArrayOf(33L, 99L, 297L, 594L, 1188L, 2376L, 3564L, 5346L, 6949L, 9033L)
    )
    private val buildingFood = mapOf(
        0 to longArrayOf(0L, 450L, 1350L, 2700L, 5400L, 10800L, 16200L, 24300L, 31590L, 41067L, 77004L, 123660L, 182979L, 257067L, 348192L),
        1 to longArrayOf(65L, 195L, 585L, 1170L, 2340L, 4680L, 7020L, 10530L, 13689L, 17796L, 27113L, 39209L, 54588L, 73796L, 97421L),
        2 to longArrayOf(50L, 150L, 450L, 900L, 1800L, 3600L, 5400L, 8100L, 10530L, 13689L, 20344L, 28984L, 39969L, 53689L, 70564L),
        3 to longArrayOf(110L, 330L, 990L, 1980L, 3960L, 7920L, 11880L, 17820L, 23166L, 30115L, 44756L, 63764L, 87931L, 118115L, 155240L),
        4 to longArrayOf(75L, 225L, 675L, 1350L, 2700L, 5400L, 8100L, 12150L, 15795L, 20533L),
        5 to longArrayOf(75L, 225L, 675L, 1350L, 2700L, 5400L, 8100L, 12150L, 15795L, 20533L),
        6 to longArrayOf(90L, 271L, 742L, 1633L, 3267L, 6534L, 9801L, 14701L, 19111L, 24838L),
        8 to longArrayOf(82L, 247L, 742L, 1485L, 2970L, 5940L, 8910L, 13365L, 17374L, 22586L)
    )

    private val technologyCopperBase = longArrayOf(
        20000L, 20000L, 2400L, 22000L, 2400L, 2400L, 28000L, 25000L,
        25000L, 20000L, 20000L, 20000L, 20000L, 30000L, 4000L
    )
    private val plantingTechnologyCopper = longArrayOf(
        2400L, 4320L, 7776L, 13997L, 25194L,
        45350L, 81629L, 146933L, 264479L, 476062L
    )
    private val foodTechnologyCosts = longArrayOf(1000L, 3000L, 8000L, 20000L, 50000L)
    private val storageTechnologyFood = longArrayOf(300L, 900L, 2400L, 6000L, 15000L)

    fun building(buildingTypeId: Int, targetLevel: Int): InternalResourceCost? {
        if (targetLevel <= 0) return null
        val copper = buildingCopper[buildingTypeId]?.getOrNull(targetLevel - 1) ?: return null
        val food = buildingFood[buildingTypeId]?.getOrNull(targetLevel - 1) ?: return null
        return InternalResourceCost(copper, food)
    }

    fun technology(technologyId: Int, targetLevel: Int): InternalResourceCost? {
        if (technologyId !in 0..21 || targetLevel <= 0) return null
        if (technologyId == 2) {
            return plantingTechnologyCopper.getOrNull(targetLevel - 1)
                ?.let { InternalResourceCost(it, 0L) }
        }
        if (technologyId == 15) {
            return storageTechnologyFood.getOrNull(targetLevel - 1)
                ?.let { InternalResourceCost(0L, it) }
        }
        if (technologyId in 16..20) {
            val food = if (targetLevel <= 5) {
                foodTechnologyCosts[targetLevel - 1]
            } else {
                0L
            }
            return InternalResourceCost(0L, food)
        }
        if (technologyId == 21) return InternalResourceCost(0L, 0L)
        val base = technologyCopperBase.getOrNull(technologyId) ?: return null
        val copper = if (technologyId == 0 && targetLevel > 10) {
            0L
        } else {
            base * (1L shl (targetLevel - 1).coerceAtMost(30))
        }
        return InternalResourceCost(copper, 0L)
    }
}

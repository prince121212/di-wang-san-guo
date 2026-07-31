package com.example.dwpmclone.domain.protocol

data class BrushCenterGeneral(
    val id: Long,
    val name: String,
    val fiefId: Long?
)

data class BrushFiefLocation(
    val fiefId: Long,
    val fiefName: String,
    val cityName: String,
    val x: Int?,
    val y: Int?
)

data class SelectedBrushGeneral(
    val generalId: Long,
    val generalName: String,
    val fiefId: Long
)

data class BrushCenterRecommendation(
    val x: Int,
    val y: Int,
    val worldX: Int,
    val worldY: Int,
    val fiefId: Long,
    val fiefName: String,
    val cityName: String,
    val selectedGenerals: List<SelectedBrushGeneral>,
    val fiefCounts: Map<Long, Int>
)

/** Pure desktop-parity policy; it never performs game I/O or invents a fallback coordinate. */
object BrushCenterRecommendationPolicy {
    fun recommend(
        generalIds: List<Long>,
        generals: List<BrushCenterGeneral>,
        fiefs: List<BrushFiefLocation>
    ): BrushCenterRecommendation {
        require(generalIds.isNotEmpty()) { "当前刷黄编队没有已选将领" }

        val byGeneralId = generals.associateBy(BrushCenterGeneral::id)
        val selected = generalIds.map { generalId ->
            val general = byGeneralId[generalId]
                ?: throw IllegalStateException("无法读取将领 $generalId 的所在封地")
            val fiefId = general.fiefId?.takeIf { it > 0L }
                ?: throw IllegalStateException("将领 ${general.name.ifBlank { generalId.toString() }} 没有可识别的所在封地")
            SelectedBrushGeneral(generalId, general.name.ifBlank { generalId.toString() }, fiefId)
        }

        val counts = linkedMapOf<Long, Int>()
        selected.forEach { general -> counts[general.fiefId] = (counts[general.fiefId] ?: 0) + 1 }
        val highest = counts.values.maxOrNull() ?: error("当前刷黄编队没有已选将领")
        val tied = counts.filterValues { it == highest }.keys
        val chosenFiefId = selected.first { it.fiefId in tied }.fiefId
        val chosen = fiefs.firstOrNull { it.fiefId == chosenFiefId }
        if (chosen?.x == null || chosen.y == null) {
            throw IllegalStateException("登录缓存中没有封地ID $chosenFiefId 的世界坐标，请重新启动该账号")
        }

        val worldX = chosen.x.coerceIn(0, 186)
        val worldY = chosen.y.coerceAtLeast(0)
        return BrushCenterRecommendation(
            x = worldX,
            y = worldY.coerceAtMost(55),
            worldX = worldX,
            worldY = worldY,
            fiefId = chosenFiefId,
            fiefName = chosen.fiefName,
            cityName = chosen.cityName,
            selectedGenerals = selected,
            fiefCounts = counts
        )
    }
}

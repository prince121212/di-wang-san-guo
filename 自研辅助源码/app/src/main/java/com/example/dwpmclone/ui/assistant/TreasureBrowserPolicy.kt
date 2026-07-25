package com.example.dwpmclone.ui.assistant

data class TreasureBrowserResult(
    val rows: List<List<String>>,
    val countText: String
)

/** Current computer-front-end filtering and two-column display policy. */
object TreasureBrowserPolicy {
    fun filter(sourceRows: List<List<String>>, query: String): TreasureBrowserResult {
        val normalized = query.trim()
        val filtered = sourceRows.filter { row ->
            normalized.isBlank() ||
                row.firstOrNull().orEmpty().contains(normalized, ignoreCase = true)
        }
        return TreasureBrowserResult(
            // IDs remain available in the source mapper for protocol diagnostics, but
            // app.js renders only 名称/数量 on the user-facing treasure page.
            rows = filtered.map { row -> listOf(row.getOrElse(0) { "—" }, row.getOrElse(1) { "—" }) },
            countText = if (normalized.isBlank()) {
                "共 ${sourceRows.size} 种宝物"
            } else {
                "找到 ${filtered.size} 种 / 共 ${sourceRows.size} 种宝物"
            }
        )
    }
}

package com.example.dwpmclone.domain.protocol

import java.io.File
import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class InternalAffairsCostParityTest {
    @Test
    fun everySupportedBuildingCostMatchesTheDesktopGameRuleTable() {
        val file = ruleFile("building_level_cost_rules.csv")
        file.readLines(Charsets.UTF_8)
            .drop(1)
            .filter(String::isNotBlank)
            .forEach { line ->
                val columns = line.removePrefix("\uFEFF").split(',')
                val type = columns[0].toInt()
                val level = columns[2].toInt()
                val expected = InternalResourceCost(columns[3].toLong(), columns[4].toLong())

                assertEquals("building type=$type level=$level", expected,
                    InternalAffairsCostTable.building(type, level))
            }
    }

    @Test
    fun everySupportedTechnologyCostMatchesTheDesktopGameRuleTable() {
        val rows = JSONArray(ruleFile("tech_levels.json").readText())
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            val technologyId = row.getInt("tech_id")
            val level = row.getInt("等级")
            val expected = InternalResourceCost(
                row.optLong("成本A", 0L),
                row.optLong("成本B", 0L)
            )
            val actual = InternalAffairsCostTable.technology(technologyId, level)

            assertNotNull("technology=$technologyId level=$level", actual)
            assertEquals("technology=$technologyId level=$level", expected, actual)
        }
    }

    private fun ruleFile(name: String): File = listOf(
        File("../reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/tables/parsed/$name"),
        File("../../reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/tables/parsed/$name"),
        File("reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/tables/parsed/$name")
    ).firstOrNull(File::exists) ?: error("missing desktop game rule table: $name")
}

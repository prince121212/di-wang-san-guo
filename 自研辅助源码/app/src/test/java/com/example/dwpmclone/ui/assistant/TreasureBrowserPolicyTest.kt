package com.example.dwpmclone.ui.assistant

import org.junit.Assert.assertEquals
import org.junit.Test

class TreasureBrowserPolicyTest {
    private val rows = listOf(
        listOf("传音符", "5", "9"),
        listOf("青铜宝箱", "2", "101"),
        listOf("青铜钥匙", "3", "102")
    )

    @Test
    fun blankQueryUsesComputerCountAndHidesProtocolIdColumn() {
        val result = TreasureBrowserPolicy.filter(rows, "")

        assertEquals("共 3 种宝物", result.countText)
        assertEquals(
            listOf(
                listOf("传音符", "5"),
                listOf("青铜宝箱", "2"),
                listOf("青铜钥匙", "3")
            ),
            result.rows
        )
    }

    @Test
    fun queryUsesComputerMatchCountWording() {
        val result = TreasureBrowserPolicy.filter(rows, "青铜")

        assertEquals("找到 2 种 / 共 3 种宝物", result.countText)
        assertEquals(listOf("青铜宝箱", "青铜钥匙"), result.rows.map { it.first() })
    }
}

package com.example.dwpmclone.ui.assistant

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DynamicRowCopyPolicyTest {
    private data class Row(val name: String, val checked: Boolean)

    @Test
    fun copiesEveryCheckedRowInOriginalOrder() {
        val rows = listOf(Row("A", true), Row("B", false), Row("C", true))

        val result = copySelectedOrFirstRows(rows, { it.checked }, { it.copy() })

        assertEquals(listOf("A", "B", "C", "A", "C"), result.map { it.name })
        assertEquals(5, result.size)
    }

    @Test
    fun copiesFirstRowWhenNothingIsChecked() {
        val rows = listOf(Row("A", false), Row("B", false))

        val result = copySelectedOrFirstRows(rows, { it.checked }, { it.copy() })

        assertEquals(listOf("A", "B", "A"), result.map { it.name })
    }

    @Test
    fun emptyInputRemainsEmpty() {
        val result = copySelectedOrFirstRows(emptyList<Row>(), { it.checked }, { it.copy() })

        assertTrue(result.isEmpty())
    }
}

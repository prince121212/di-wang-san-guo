package com.example.dwpmclone.ui.assistant

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class FutureMilitaryGeneralSelectionCodecTest {
    @Test
    fun readsDesktopMultiGeneralRowsInOrderAndRemovesInvalidDuplicates() {
        val row = JSONObject()
            .put("generalId", 99L)
            .put("generalIds", JSONArray().put(7L).put(8L).put(7L).put(0L))

        assertEquals(listOf(7L, 8L), FutureMilitaryGeneralSelectionCodec.read(row))
    }

    @Test
    fun oldSingleGeneralRowsRemainCompatible() {
        assertEquals(
            listOf(99L),
            FutureMilitaryGeneralSelectionCodec.read(JSONObject().put("generalId", 99L))
        )
    }

    @Test
    fun writesAllSelectedGeneralsWithoutCollapsingToFirst() {
        val written = FutureMilitaryGeneralSelectionCodec.write(listOf(7L, 8L, 7L, -1L))

        assertEquals(2, written.length())
        assertEquals(7L, written.getLong(0))
        assertEquals(8L, written.getLong(1))
    }
}

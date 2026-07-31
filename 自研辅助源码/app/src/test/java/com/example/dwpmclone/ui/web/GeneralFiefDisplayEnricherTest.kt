package com.example.dwpmclone.ui.web

import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Test

class GeneralFiefDisplayEnricherTest {
    @Test
    fun joinsGeneralPlaceIdToOwnedFiefNamesLikeDesktopSessionEnrichment() {
        val generals = JSONArray(
            """[{"id":7,"name":"赵云","placeID":"205"},{"id":8,"name":"马超","placeID":637}]"""
        )
        val fiefs = JSONArray(
            """[
                {"targetId":205,"fiefName":"测试基地","cityName":"洛阳"},
                {"fiefId":637,"name":"广成关封地","cityName":"广成关"}
            ]""".trimIndent()
        )

        val enriched = GeneralFiefDisplayEnricher.enrich(generals, fiefs)

        assertEquals(205L, enriched.getJSONObject(0).getLong("fiefId"))
        assertEquals("测试基地", enriched.getJSONObject(0).getString("fiefName"))
        assertEquals("洛阳", enriched.getJSONObject(0).getString("cityName"))
        assertEquals("广成关封地", enriched.getJSONObject(1).getString("fiefName"))
    }

    @Test
    fun keepsAnAlreadyResolvedGeneralLabel() {
        val enriched = GeneralFiefDisplayEnricher.enrich(
            JSONArray("""[{"id":7,"placeID":205,"fiefName":"现有名称"}]"""),
            JSONArray("""[{"fiefId":205,"fiefName":"新名称"}]""")
        )

        assertEquals("现有名称", enriched.getJSONObject(0).getString("fiefName"))
    }
}

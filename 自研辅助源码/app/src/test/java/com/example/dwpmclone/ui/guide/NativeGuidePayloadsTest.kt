package com.example.dwpmclone.ui.guide

import com.example.dwpmclone.domain.model.FamousGeneral
import com.example.dwpmclone.domain.model.GuideArticle
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeGuidePayloadsTest {
    @Test
    fun `famous general payload preserves original searchable fields`() {
        val payload = NativeGuidePayloads.famousGenerals(listOf(
            FamousGeneral("诸葛亮", 99, "智勇", "蜀"),
            FamousGeneral("未知将", null, null, null)
        ))

        assertTrue(payload.getBoolean("ok"))
        assertEquals(2, payload.getInt("total"))
        val first = payload.getJSONArray("items").getJSONObject(0)
        assertEquals("诸葛亮", first.getString("name"))
        assertEquals(99, first.getInt("breakthrough"))
        assertEquals("智勇", first.getString("attribute"))
        assertEquals("蜀", first.getString("nation"))
        assertTrue(payload.getJSONArray("items").getJSONObject(1).isNull("attribute"))
    }

    @Test
    fun `guide index stays compact while detail returns the original body`() {
        val article = GuideArticle("demo", "测试攻略", "第一行\n第二行", "guidetxts/demo.txt")
        val index = NativeGuidePayloads.guideArticles(listOf(article))
        val row = index.getJSONArray("items").getJSONObject(0)

        assertEquals("demo", row.getString("id"))
        assertEquals("测试攻略", row.getString("title"))
        assertFalse(row.has("body"))
        assertEquals(
            "第一行\n第二行",
            NativeGuidePayloads.guideArticle(article)
                .getJSONObject("article")
                .getString("body")
        )
    }

    @Test
    fun `missing guide returns an explicit non-success payload`() {
        val payload = NativeGuidePayloads.guideArticle(null)
        assertFalse(payload.getBoolean("ok"))
        assertTrue(payload.getString("error").isNotBlank())
    }

    @Test
    fun `open server payload keeps all versions and recovered anchor math`() {
        val options = NativeGuidePayloads.openServerOptions()
        assertEquals(7, options.getJSONArray("versions").length())
        assertTrue(options.getJSONArray("versions").getJSONObject(4).getInt("upcomingServer") > 113)

        val result = NativeGuidePayloads.openServerCalculation(versionIndex = 4, server = 114)
        assertEquals("三国联盟", result.getString("versionLabel"))
        assertEquals("2017/5/31", result.getString("dateText"))
        assertEquals(14, result.getJSONObject("rule").getInt("intervalDays"))
    }
}

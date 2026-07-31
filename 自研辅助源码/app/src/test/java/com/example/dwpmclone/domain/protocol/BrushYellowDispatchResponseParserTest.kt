package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BrushYellowDispatchResponseParserTest {
    @Test
    fun parsesRecoveredSuccessTextAndUsedAountTypo() {
        val parsed = BrushYellowDispatchResponseParser.parseText("刷黄出征成功！继续搜索... usedAount=17")

        assertEquals(true, parsed.success)
        assertEquals("刷黄出征成功！继续搜索... usedAount=17", parsed.message)
        assertEquals(17, parsed.usedAount)
        assertEquals(17, parsed.consumedTimes)
        assertEquals("success-marker:刷黄出征成功", parsed.evidence)
    }

    @Test
    fun failureMarkerWinsOverGenericSuccess() {
        val parsed = BrushYellowDispatchResponseParser.parseText("{\"success\":false,\"error\":\"体力不足，出征失败\"}")

        assertEquals(false, parsed.success)
        assertEquals("体力不足，出征失败", parsed.message)
        assertEquals(0, parsed.consumedTimes)
        assertEquals("failure-marker:error", parsed.evidence)
    }

    @Test
    fun parsesExplicitSuccessFalseWithoutErrorMarker() {
        val parsed = BrushYellowDispatchResponseParser.parseText("{\"success\":false,\"message\":\"没有可以出征的刷黄编队了\"}")

        assertEquals(false, parsed.success)
        assertEquals("没有可以出征的刷黄编队了", parsed.message)
        assertEquals(0, parsed.consumedTimes)
        assertEquals("failure-marker:success=false", parsed.evidence)
    }

    @Test
    fun parsesUtf8HexCapture() {
        val parsed = BrushYellowDispatchResponseParser.parseHex("E588B7E9BB84E587BAE5BE81E68890E58A9F")

        assertEquals(true, parsed.success)
        assertEquals("刷黄出征成功", parsed.message)
        assertEquals("hex->success-marker:刷黄出征成功", parsed.evidence)
    }

    @Test
    fun parsesBinaryFf0000AsRejectedDispatch() {
        val parsed = BrushYellowDispatchResponseParser.parseHex("ff0000")

        assertEquals(false, parsed.success)
        assertEquals("游戏服拒绝出征(0x8522=ff0000)，通常是将领体力/兵力/出征状态/目标状态不满足", parsed.message)
        assertEquals(0, parsed.consumedTimes)
        assertEquals("hex-8522-ff0000-rejected", parsed.evidence)
    }

    @Test
    fun binary8522SuccessRequiresAndExposesPositiveBattleId() {
        val parsed = BrushYellowDispatchResponseParser.parseHex(
            "000000000000000000007b"
        )

        assertEquals(true, parsed.success)
        assertEquals(123L, parsed.battleId)
        assertEquals("123", parsed.toRawMap()["dispatchResponseBattleId"])
    }

    @Test
    fun statusZeroWithoutBattleIdIsNotAcceptedAsDispatchSuccess() {
        val parsed = BrushYellowDispatchResponseParser.parseHex("000000")

        assertEquals(false, parsed.success)
        assertNull(parsed.battleId)
        assertEquals("出征响应缺少有效 battleId", parsed.message)
        assertEquals("hex-8522-status-0-battle-id-missing", parsed.evidence)
    }

    @Test
    fun returnsUnknownForUnrecognizedText() {
        val parsed = BrushYellowDispatchResponseParser.parseText("opaque-binary-preview")

        assertNull(parsed.success)
        assertEquals("opaque-binary-preview", parsed.message)
        assertEquals(0, parsed.consumedTimes)
        assertEquals("no-known-marker", parsed.evidence)
    }
}

package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RankListResponseParserTest {
    @Test
    fun parsesPassive1170PrestigeRankCapture() {
        val parsed = RankListResponseParser.parseHex(FLOW_008_RESP_HEX)

        assertEquals(10, parsed.entries.size)
        assertEquals("仙女", parsed.entries[0].name)
        assertEquals("赶路人", parsed.entries[1].name)
        assertEquals("渣哥", parsed.entries[2].name)
        assertEquals("康康", parsed.entries[8].name)
        assertEquals("怪咖", parsed.entries[9].name)
        assertEquals("00000000057f225e", parsed.entries[0].scoreHex)
        assertEquals(0x057f225eL, parsed.entries[0].scoreOrCount)
        assertTrue(parsed.evidence.contains("lengthPrefixedUtf8NamePlusUint64"))
    }

    @Test
    fun parsesPassive1170CityRankCaptureAndNormalizesTrailingDot() {
        val parsed = RankListResponseParser.parseHex(FLOW_010_RESP_HEX)

        assertEquals(10, parsed.entries.size)
        assertEquals("赶路人", parsed.entries[0].name)
        assertEquals("赊刀人", parsed.entries[1].name)
        assertEquals("爱新游", parsed.entries[2].name)
        assertEquals("仙女", parsed.entries[7].name)
        assertEquals("仙女.", parsed.entries[7].rawName)
        assertEquals("天罡星", parsed.entries[9].name)
        assertEquals("0000000000000081", parsed.entries[0].scoreHex)
        assertEquals(129L, parsed.entries[0].scoreOrCount)
        assertEquals(20L, parsed.entries[9].scoreOrCount)
    }

    @Test
    fun diagnosticsSummaryShowsTopRankEntries() {
        val parsed = RankListResponseParser.parseHex(FLOW_008_RESP_HEX)

        val summary = ProtocolDiagnosticsReportBuilder.rankListSummary(parsed, maxEntries = 2)

        assertTrue(summary.contains("1170-rank entries=10"))
        assertTrue(summary.contains("1.仙女=00000000057f225e"))
        assertTrue(summary.contains("2.赶路人=00000000057f225e"))
    }

    private companion object {
        val FLOW_008_RESP_HEX = """
            01015d7d75d8b4204a8819f3dc2f9930366d00000000c181700000003200010a
            000000000003a4c0000000e70006e4bb99e5a5b300000000057f225e
            0009e8b5b6e8b7afe4baba00000000057f225e
            0006e6b8a3e593a500000000057f225e
            0009e788b1e696b0e6b8b800000000057f225e
            0006e9babbe5ad9000000000057f225e
            0009e5b08fe9a38ee69c8800000000057f225e
            0009e8b58ae58880e4baba00000000057f225e
            0009e58d97e5b1b1e99baa00000000057f225e
            0006e5bab7e5bab700000000057f225e
            0006e680aae5929600000000057f225e
        """.trimIndent()

        val FLOW_010_RESP_HEX = """
            01015d7d75d8b4204a8819f3dc3316f037fe00000000c581700003003200010a
            0000000000000000000002fc0009e8b5b6e8b7afe4baba0000000000000081
            0009e8b58ae58880e4baba000000000000005b
            0009e788b1e696b0e6b8b80000000000000053
            0006e680aae592960000000000000042
            0006e5bab7e5bab70000000000000040
            0006e891a3e58d93000000000000001f
            0009e58d97e5b1b1e99baa000000000000001c
            0007e4bb99e5a5b32e0000000000000018
            0009e5a4a9e99b84e6989f0000000000000015
            0009e5a4a9e7bda1e6989f0000000000000014
        """.trimIndent()
    }
}

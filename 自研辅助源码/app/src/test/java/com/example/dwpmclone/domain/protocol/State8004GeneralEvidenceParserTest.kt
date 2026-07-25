package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class State8004GeneralEvidenceParserTest {
    @Test
    fun extractsMultipleJiangLingObjectsFromMixedText() {
        val raw = "prefix\u0000JiangLing{id=0000000000000007,name=赵云,status=0,tili=49,daiBingLimit=1999}\u0000" +
            "JiangLing{id=0000000000000008,name=马超,status=1,tili=0,isPeiBingFail=true}"

        val records = State8004GeneralEvidenceParser.recoverRecords(raw)

        assertEquals(2, records.size)
        assertEquals("0000000000000007", records[0]["id"])
        assertEquals("赵云", records[0]["name"])
        assertEquals("49", records[0]["tili"])
        assertEquals("0000000000000008", records[1]["id"])
        assertEquals("马超", records[1]["name"])
    }

    @Test
    fun extractsRepeatedIdKeyValueRecordsWithoutLineBreaks() {
        val raw = "id=0000000000000007|name=赵云|status=0|tili=49|id=0000000000000008|name=马超|status=1|tili=0"

        val text = State8004GeneralEvidenceParser.recoverRecordText(raw)!!

        assertTrue(text.contains("id=0000000000000007|name=赵云"))
        assertTrue(text.contains("id=0000000000000008|name=马超"))
    }

    @Test
    fun extractsLengthPrefixedNameCandidateFromHexTail() {
        val id = "0000000000000007"
        val nameBytes = "赵云".toByteArray(Charsets.UTF_8)
        val nameLen = nameBytes.size.toString(16).padStart(4, '0')
        val hex = id + nameLen + nameBytes.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') } + "0031"

        val records = State8004GeneralEvidenceParser.recoverRecords(hex)

        assertEquals(1, records.size)
        assertEquals("7", records.single()["id"])
        assertEquals("赵云", records.single()["name"])
        assertEquals("0", records.single()["status"])
        assertEquals("49", records.single()["tili"])
        assertEquals("state8004-binary-name-candidate", records.single()["source"])
    }

    @Test
    fun extractsConfirmedBinaryJiangLingRecordsFromReal8004ResponseHex() {
        val sample = listOf(
            File("docs/protocol/samples/1016_role_world_bootstrap_passive/resp.hex"),
            File("../docs/protocol/samples/1016_role_world_bootstrap_passive/resp.hex")
        ).first { it.exists() }
        val hex = sample
            .readText()
            .trim()

        val records = State8004GeneralEvidenceParser.recoverRecords(hex)

        assertEquals(12, records.size)
        val first = records.first()
        assertEquals("state8004-binary-jiangling", first["source"])
        assertEquals("7066187", first["id"])
        assertEquals("00000000006bd24b", first["idHex"])
        assertEquals("何颜鸥", first["name"])
        assertEquals("1", first["professionCode"])
        assertEquals("弓将", first["category"])
        assertEquals("弓将", first["kind"])
        assertEquals("1", first["level"])
        assertEquals("69", first["growth"])
        assertEquals("69", first["progression"])
        assertEquals("0", first["status"])
        assertEquals("空闲", first["statusText"])
        assertEquals("99", first["tili"])
        assertEquals("100", first["tiliLimit"])
        assertEquals("48", first["zhongChengdu"])
        assertEquals("100", first["loyaltyLimit"])
        assertEquals("1", first["troopCount"])
        assertEquals("1", first["soldierCount"])
        assertEquals("198", first["daiBingLimit"])
        assertEquals("198", first["troopLimit"])
        assertEquals("198", first["maxTroopCount"])
        assertEquals("3", first["troopTypeCode"])
        assertEquals("轻骑兵", first["troopType"])
        assertEquals("Lo/a.S5.Pm", first["troopTypeSource"])
        assertEquals("Lo/a.S5.Qm", first["troopCountSource"])
    }

    @Test
    fun extractsB6FieldsAndS5TroopsFromLatestThreeGeneralTail() {
        val niChuBody = "0000010202d1003201000000000000000f0046003a004e0046003a0064006400000000000000cc3c640005004f000000000000000000000009860000000000c4a33300000000000000000000000000000000000000000000000000000000000000000000000000030000007d00000000ffff"
        val bu1Body = "0000000002dc003601000000000000000f003c00380040003c00380064006400000000000000a23c6400050047000000000000000000000009860000000000c4a33200000000000000000000000000000000000000000000000000000000000000000000000000030000007d00000000ffff"
        val qi1Body = "0000010202d6003c01000000000000000f004e004e004e004e004e0064006400000000000000cc3c6400050050320000000000000000000009860000000000c4a33100000000000000000000000000000000000000000000000000000000000000000000000000050000007d00000000ffff"
        val hex =
            "0000000000c4a3330006e580aae5889d$niChuBody" +
                "0000000000c4a3320004e6ada531$bu1Body" +
                "0000000000c4a3310004e9aa9131$qi1Body" +
                "01" +
                "0000000000c4a331" +
                "0000000000c4a331" +
                "03" +
                "000000c8"

        val records = State8004GeneralEvidenceParser.recoverRecords(hex)

        assertEquals(3, records.size)
        val niChu = records.first { it["name"] == "倪初" }
        val bu1 = records.first { it["name"] == "步1" }
        val qi1 = records.first { it["name"] == "骑1" }
        assertEquals("骑将", niChu["category"])
        assertEquals("60", niChu["zhongChengdu"])
        assertEquals("204", niChu["daiBingLimit"])
        assertEquals(null, niChu["troopCount"])
        assertEquals("步将", bu1["category"])
        assertEquals("60", bu1["zhongChengdu"])
        assertEquals("162", bu1["daiBingLimit"])
        assertEquals("骑将", qi1["category"])
        assertEquals("60", qi1["zhongChengdu"])
        assertEquals("204", qi1["daiBingLimit"])
        assertEquals("200", qi1["troopCount"])
        assertEquals("3", qi1["troopTypeCode"])
        assertEquals("轻骑兵", qi1["troopType"])
    }

    @Test
    fun normalizesChineseGeneralAliasesAndStatusValues() {
        val raw = "将领ID=0000000000000007|姓名=赵云|状态=空闲|体力=49|带兵上限=1999|配兵失败=否|" +
            "将领ID=0000000000000008|姓名=马超|状态=出征|体力=0|配兵失败=是"

        val records = State8004GeneralEvidenceParser.recoverRecords(raw)

        assertEquals(2, records.size)
        assertEquals("0000000000000007", records[0]["id"])
        assertEquals("赵云", records[0]["name"])
        assertEquals("0", records[0]["status"])
        assertEquals("49", records[0]["tili"])
        assertEquals("1999", records[0]["daiBingLimit"])
        assertEquals("false", records[0]["isPeiBingFail"])
        assertEquals("0000000000000008", records[1]["id"])
        assertEquals("马超", records[1]["name"])
        assertEquals("2", records[1]["status"])
        assertEquals("true", records[1]["isPeiBingFail"])
    }
}

package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class State8004GeneralEvidenceParserTest {
    @Test
    fun richestPayloadWinsOverShortParseableTail() {
        val shortTail = "id=7|name=尾段将领|status=0"
        val fullPayload = listOf(
            "id=7|name=将领一|status=0",
            "id=8|name=将领二|status=0",
            "id=9|name=将领三|status=1"
        ).joinToString("\n")

        val records = State8004GeneralEvidenceParser.recoverBestAvailableRecords(
            shortTail,
            fullPayload
        )

        assertEquals(3, records.size)
        assertEquals(listOf("7", "8", "9"), records.map { it["id"] })
    }

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
        assertEquals("8", first["status"])
        assertEquals("返回", first["statusText"])
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
    fun extractsStandaloneGeneralWhenFoFieldDoesNotRepeatGeneralId() {
        val hex = binaryGeneralRecord(
            id = 5_354_585L,
            name = "A-1 统弓",
            foRaw = 5_354_586L,
            energy = 305,
            status = 1
        )

        val records = State8004GeneralEvidenceParser.recoverRecords(hex)

        assertEquals(1, records.size)
        assertEquals("5354585", records.single()["id"])
        assertEquals("A-1 统弓", records.single()["name"])
        assertEquals("5354586", records.single()["foRawLong"])
        assertEquals("305", records.single()["tili"])
        assertEquals("1", records.single()["status"])
        assertEquals("出征", records.single()["statusText"])
        assertEquals("0", records.single()["rawStatus58"])
        assertEquals("i64_id_u16_name_114_body_b6_common_v20260728", records.single()["layout"])
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

    private fun binaryGeneralRecord(
        id: Long,
        name: String,
        foRaw: Long,
        energy: Int = 100,
        status: Int = 0
    ): String {
        val nameBytes = name.toByteArray(Charsets.UTF_8)
        val body = ByteArray(114)
        body[3] = 1
        body.putU16(6, 65)
        body[8] = 1
        body.putU16(27, energy)
        body.putU16(29, energy)
        body.putU32(35, 207)
        body[39] = 51
        body[40] = 100
        body.putI64(58, foRaw)
        body[86] = status.toByte()
        body[88] = 0
        body[112] = 0xff.toByte()
        body[113] = 0xff.toByte()
        return id.toString(16).padStart(16, '0') +
            nameBytes.size.toString(16).padStart(4, '0') +
            nameBytes.toHex() +
            body.toHex()
    }

    private fun ByteArray.putU16(offset: Int, value: Int) {
        this[offset] = (value ushr 8).toByte()
        this[offset + 1] = value.toByte()
    }

    private fun ByteArray.putU32(offset: Int, value: Int) {
        repeat(4) { index -> this[offset + index] = (value ushr ((3 - index) * 8)).toByte() }
    }

    private fun ByteArray.putI64(offset: Int, value: Long) {
        repeat(8) { index -> this[offset + index] = (value ushr ((7 - index) * 8)).toByte() }
    }

    private fun ByteArray.toHex(): String = joinToString("") {
        (it.toInt() and 0xff).toString(16).padStart(2, '0')
    }
}

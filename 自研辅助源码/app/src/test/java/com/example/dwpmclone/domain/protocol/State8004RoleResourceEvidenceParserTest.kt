package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class State8004RoleResourceEvidenceParserTest {
    @Test
    fun recoversChineseRoleAndResourceAliasesFromTextEvidence() {
        val raw = "君主名=测试君主|君主等级=42|国家=蜀国|官职=大将军|" +
            "铜钱=123456|粮食=654321|声望=2000|铜钱产量=88|粮食产量=99|" +
            "人口=111|人口上限=222|资源点占用=5|资源点上限=8"

        val recovered = State8004RoleResourceEvidenceParser.recover(raw)

        assertEquals("测试君主", recovered["roleName"])
        assertEquals("42", recovered["level"])
        assertEquals("蜀", recovered["nation"])
        assertEquals("大将军", recovered["title"])
        assertEquals("123456", recovered["copper"])
        assertEquals("654321", recovered["food"])
        assertEquals("2000", recovered["prestige"])
        assertEquals("88", recovered["copperPerHour"])
        assertEquals("99", recovered["foodPerHour"])
        assertEquals("111", recovered["populationCurrent"])
        assertEquals("222", recovered["populationCap"])
        assertEquals("5", recovered["resourcePointCurrent"])
        assertEquals("8", recovered["resourcePointCap"])
    }

    @Test
    fun recoversRoleAndResourceEvidenceFromHexText() {
        val text = "roleName=Hex君主|level=51|copper=777|food=888"
        val hex = text.toByteArray(Charsets.UTF_8).joinToString(separator = "") {
            (it.toInt() and 0xff).toString(16).padStart(2, '0')
        }

        val recovered = State8004RoleResourceEvidenceParser.recover(hex)

        assertEquals("Hex君主", recovered["roleName"])
        assertEquals("51", recovered["level"])
        assertEquals("777", recovered["copper"])
        assertEquals("888", recovered["food"])
        assertEquals("state8004-role-resource-hex-keyvalue", recovered["source"])
    }

    @Test
    fun recoversJsonLikeRoleAndResourceEvidenceFromLogLine() {
        val raw = """[readonly-response-json] {"opcode":"0x8004","roleName":"日志君主","level":52,"copper":777000,"food":888000}"""

        val recovered = State8004RoleResourceEvidenceParser.recover(raw)

        assertEquals("日志君主", recovered["roleName"])
        assertEquals("52", recovered["level"])
        assertEquals("777000", recovered["copper"])
        assertEquals("888000", recovered["food"])
    }

    @Test
    fun ignoresGenericGeneralNameAndRankEvidenceToAvoidMonarchMisclassification() {
        val raw = "JiangLing{id=0000000000000007,name=赵云,rank=30,status=0,tili=49}"

        val recovered = State8004RoleResourceEvidenceParser.recover(raw)

        assertFalse(recovered.containsKey("roleName"))
        assertFalse(recovered.containsKey("level"))
        assertFalse(recovered.containsKey("copper"))
    }
}

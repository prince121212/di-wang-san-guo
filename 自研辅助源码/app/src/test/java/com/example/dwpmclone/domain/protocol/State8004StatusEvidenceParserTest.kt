package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

class State8004StatusEvidenceParserTest {
    @Test
    fun recoversFiefCityAndPolicyBuffTextWithoutInventingTimers() {
        val payload = ByteArrayOutputStream().apply {
            write(ByteArray(8))
            utf("董全基地")
            write(ByteArray(12))
            write(ByteArray(8)); write(byteArrayOf(0x03, 0x13)); utf("建业")
            write(byteArrayOf(0x00, 0xaa.toByte(), 0x00, 0x0a, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03))
            write(byteArrayOf(0x00, 0x01, 0x2f, 0x0d)); utf("神农"); utf("降低20%伤兵治疗费用")
            write(byteArrayOf(0x00, 0x02, 0x2f, 0x0c)); utf("蚩尤"); utf("守军攻防提升10%")
            write(byteArrayOf(0x00, 0x03, 0x2f, 0x0b)); utf("风后"); utf("铜钱粮食产能提升30%")
        }.toByteArray()

        val records = State8004StatusEvidenceParser.recoverRecords(payload)

        assertEquals("董全基地", records.first { it["kind"] == "fiefName" }["detail"])
        assertEquals("建业", records.first { it["kind"] == "cityName" }["detail"])
        val buffs = records.filter { it["kind"] == "policyBuff" }
        assertEquals(listOf("神农", "蚩尤", "风后"), buffs.map { it["name"] })
        assertTrue(buffs.any { it["effect"] == "铜钱粮食产能提升30%" })
        assertEquals("2f0d", buffs.first()["timerRawHex"])
    }

    private fun ByteArrayOutputStream.utf(value: String) {
        val data = value.toByteArray(Charsets.UTF_8)
        val out = DataOutputStream(this)
        out.writeShort(data.size)
        out.write(data)
    }
}

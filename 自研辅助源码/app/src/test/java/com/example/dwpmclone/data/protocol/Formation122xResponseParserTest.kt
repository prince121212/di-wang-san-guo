package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.protocol.BatchRefillTroopsShape
import com.example.dwpmclone.domain.protocol.GeneralProtocolShapes
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class Formation122xResponseParserTest {
    @Test
    fun sharedFixtureMatchesAndroidAssignmentAndRefillShapes() {
        val file = listOf(
            File("../shared_core/protocol_parity_fixtures.json"),
            File("../../shared_core/protocol_parity_fixtures.json"),
            File("shared_core/protocol_parity_fixtures.json")
        ).first(File::exists)
        val fixtures = JSONObject(file.readText()).getJSONObject("fixtures")
        val assignment = fixtures.getJSONObject("formationAssign1226")
        val assignmentExpected = assignment.getJSONObject("expected")
        val assignmentPayload = GeneralProtocolShapes.formationAssignShape(
            assignment.getLong("generalId").toString(16),
            assignment.getInt("soldierTypeCode").toString(16),
            assignment.getInt("soldierCount")
        ).substringAfter("1226")
        val assignmentReceipt = Formation122xResponseParser.parse8226(
            assignment.getString("successResponseHex")
        )

        assertEquals(assignment.getString("requestPayloadHex"), assignmentPayload)
        assertEquals(assignmentExpected.getBoolean("success"), assignmentReceipt.success)
        assertEquals(assignmentExpected.getInt("previousType"), assignmentReceipt.previousType)
        assertEquals(assignmentExpected.getInt("previousCount"), assignmentReceipt.previousCount)
        assertEquals(assignmentExpected.getInt("assignedType"), assignmentReceipt.assignedType)
        assertEquals(assignmentExpected.getInt("assignedCount"), assignmentReceipt.assignedCount)

        val refill = fixtures.getJSONObject("formationRefill1229")
        val refillExpected = refill.getJSONObject("expected")
        val ids = refill.getJSONArray("generalIds")
        val refillPayload = BatchRefillTroopsShape.build(
            (0 until ids.length()).map { ids.getLong(it).toString(16) }
        ).substringAfter("1229")
        val refillReceipt = Formation122xResponseParser.parse8229(refill.getString("successResponseHex"))

        assertEquals(refill.getString("requestPayloadHex"), refillPayload)
        assertEquals(refillExpected.getBoolean("success"), refillReceipt.success)
        assertEquals(refillExpected.getString("message"), refillReceipt.message)
        assertEquals(refillExpected.getInt("entryCount"), refillReceipt.entries.size)
        assertEquals(refillExpected.getInt("firstSoldierType"), refillReceipt.entries.first().soldierType)
        assertEquals(refillExpected.getInt("firstSoldierCount"), refillReceipt.entries.first().soldierCount)
    }

    @Test
    fun captured8226UsesNewTypeAndCountRatherThanPreviousPair() {
        val capturedPayload = "0100000000006b4d9a0008007200080085010300000004"

        val result = Formation122xResponseParser.parse8226(capturedPayload)

        assertTrue(result.success)
        assertEquals(0x6b4d9aL, result.generalId)
        assertEquals(8, result.previousType)
        assertEquals(114, result.previousCount)
        assertEquals(8, result.assignedType)
        assertEquals(133, result.assignedCount)
    }

    @Test
    fun captured8229ParsesSuccessTextAndEveryRefilledGeneral() {
        val capturedPayload =
            "000012e689b9e9878fe8a1a5e6bba1e68890e58a9f" +
                "02" +
                "00000000006b4dae0100000096" +
                "00000000006b4d9a080000000a" +
                "00000000000007550103000000c0"

        val result = Formation122xResponseParser.parse8229(capturedPayload)

        assertTrue(result.success)
        assertEquals("批量补满成功", result.message)
        assertEquals(2, result.entries.size)
        assertEquals(FormationRefillEntry(0x6b4daeL, 1, 150), result.entries[0])
        assertEquals(FormationRefillEntry(0x6b4d9aL, 8, 10), result.entries[1])
    }

    @Test
    fun shortOrNonConfirming8229FailsClosed() {
        assertFalse(Formation122xResponseParser.parse8229("00").success)
        assertFalse(
            Formation122xResponseParser.parse8229(
                "00000ce689b9e9878fe5a4b1e8b4a500"
            ).success
        )
    }
}

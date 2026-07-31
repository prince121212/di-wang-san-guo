package com.example.dwpmclone.domain.protocol

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

class DailyProtocolParityFixtureTest {
    @Test
    fun nationalCity8404SamplesMatchSharedFixtures() {
        val names = listOf(
            "dailyNationalCity8404State",
            "dailyNationalCity8404Commandery",
            "dailyNationalCity8404County",
            "dailyNationalCity8404Small"
        )
        names.forEach { name ->
            val fixture = fixture(name)
            val expected = fixture.getJSONObject("expected")
            val page = DailyFeatureProtocolShapes.parseNationalCityPage(
                fixture.getString("responseHex").hexBytes(),
                fixture.getInt("requestedCategory")
            )
            val city = page.cities.single()

            assertEquals(expected.getInt("category"), page.category)
            assertEquals(expected.getString("name"), city.name)
            assertEquals(expected.getString("kind"), city.kind.name.lowercase())
            assertEquals(expected.getInt("x"), city.x)
            assertEquals(expected.getInt("y"), city.y)
        }
    }

    @Test
    fun ownedCity8318SampleMatchesSharedFixture() {
        val fixture = fixture("dailyOwnedCity8318Nanhua")
        val expected = fixture.getJSONObject("expected")
        val city = DailyFeatureProtocolShapes.parseOwnedCityList(
            fixture.getString("responseHex").hexBytes()
        ).single()

        assertEquals(
            fixture.getString("requestHex"),
            DailyFeatureProtocolShapes.buildOwnedCityListPayload(
                fixture.getLong("roleId")
            ).toHex()
        )
        assertEquals(expected.getLong("id"), city.id)
        assertEquals(expected.getInt("kindCode"), city.kindCode)
        assertEquals(expected.getString("name"), city.name)
        assertEquals(expected.getInt("x"), city.x)
        assertEquals(expected.getInt("y"), city.y)
        assertEquals(expected.getString("ownerName"), city.ownerName)
        assertEquals(expected.getInt("ownerLevel"), city.ownerLevel)
    }

    @Test
    fun ownedCityOneByteNoCityReceiptIsAnEmptyTerminalList() {
        assertEquals(
            emptyList<OwnedCityRecord>(),
            DailyFeatureProtocolShapes.parseOwnedCityList(byteArrayOf(1))
        )
    }

    @Test
    fun salaryA14bSampleMatchesSharedFixture() {
        val fixture = fixture("dailySalaryA14bSuccess")
        val expected = fixture.getJSONObject("expected")
        val receipt = DailyFeatureProtocolShapes.parseSalaryReceipt(
            fixture.getString("responseHex").hexBytes()
        )

        assertEquals(fixture.getString("requestHex"), DailyFeatureProtocolShapes.buildSalaryPayload().toHex())
        assertEquals(expected.getInt("status"), receipt.status)
        assertEquals(expected.getInt("extra"), receipt.extra)
        assertEquals(expected.getBoolean("success"), receipt.success)
        assertEquals(expected.getBoolean("completed"), receipt.completed)
        assertEquals(expected.getLong("copper"), receipt.copper)
        assertEquals(expected.getLong("food"), receipt.food)
    }

    @Test
    fun generalVisitA273SamplesMatchSharedFixtures() {
        listOf(
            "dailyGeneralVisitA273Rejected",
            "dailyGeneralVisitA273AlreadyVisited"
        ).forEach { name ->
            val fixture = fixture(name)
            val expected = fixture.getJSONObject("expected")
            val receipt = DailyFeatureProtocolShapes.parseGeneralVisitReceipt(
                fixture.getString("responseHex").hexBytes()
            )

            assertEquals(expected.getInt("status"), receipt.status)
            assertEquals(expected.getString("message"), receipt.message)
            assertEquals(expected.getBoolean("success"), receipt.success)
            assertEquals(expected.getBoolean("completed"), receipt.completed)
            assertEquals(expected.getBoolean("recruited"), receipt.recruited)
            assertEquals(expected.getBoolean("alreadyVisited"), receipt.alreadyVisited)
            assertEquals(expected.getBoolean("invitationResolved"), receipt.invitationResolved)
            assertEquals(expected.getBoolean("invitationRejected"), receipt.invitationRejected)
        }
    }

    @Test
    fun generalVisitA271DuplicateMatchesSharedFixture() {
        val fixture = fixture("dailyGeneralVisitA271AlreadyVisited")
        val expected = fixture.getJSONObject("expected")
        val page = DailyFeatureProtocolShapes.parseGeneralVisitPage(
            fixture.getString("responseHex").hexBytes()
        )

        assertEquals(expected.getInt("status"), page.status)
        assertEquals(expected.getString("message"), page.message)
        assertEquals(expected.getBoolean("completed"), page.completed)
        assertEquals(expected.getBoolean("alreadyVisited"), page.alreadyVisited)
        assertEquals(expected.getInt("candidateCount"), page.candidates.size)
    }

    private fun fixture(name: String): JSONObject = fixtures().getJSONObject(name)

    private fun fixtures(): JSONObject {
        val file = listOf(
            File("../shared_core/protocol_parity_fixtures.json"),
            File("../../shared_core/protocol_parity_fixtures.json"),
            File("shared_core/protocol_parity_fixtures.json")
        ).firstOrNull(File::exists)
            ?: error("shared_core/protocol_parity_fixtures.json is missing")
        return JSONObject(file.readText()).getJSONObject("fixtures")
    }

    private fun String.hexBytes(): ByteArray {
        require(length % 2 == 0) { "hex length must be even" }
        return chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    }

    private fun ByteArray.toHex(): String =
        joinToString("") { "%02x".format(it.toInt() and 0xff) }
}

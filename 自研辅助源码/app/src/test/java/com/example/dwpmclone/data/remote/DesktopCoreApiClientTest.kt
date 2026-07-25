package com.example.dwpmclone.data.remote

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DesktopCoreApiClientTest {
    private val settings = DesktopCoreSettings(
        enabled = true,
        baseUrl = "http://192.168.1.10:17351/",
        apiToken = "mobile-token",
        deviceId = "android-test"
    )

    @Test
    fun healthUsesBearerTokenDeviceIdAndNormalizedBaseUrl() {
        val requests = mutableListOf<DesktopCoreHttpRequest>()
        val client = DesktopCoreApiClient(settings) { request ->
            requests += request
            DesktopCoreHttpResponse(200, """{"ok":true,"apiVersion":"v1"}""")
        }

        val result = client.health()

        assertTrue(result is DesktopCoreResult.Ok)
        assertEquals("GET", requests.single().method)
        assertEquals("http://192.168.1.10:17351/api/v1/mobile/health", requests.single().url)
        assertEquals("Bearer mobile-token", requests.single().headers["Authorization"])
        assertEquals("android-test", requests.single().headers["X-Device-Id"])
    }

    @Test
    fun accountListMapsOpaqueReferencesWithoutGameSessionFields() {
        val client = DesktopCoreApiClient(settings) {
            DesktopCoreHttpResponse(
                200,
                JSONObject()
                    .put("ok", true)
                    .put("accounts", JSONArray().put(
                        JSONObject()
                            .put("accountRef", "opaque-ref")
                            .put("username", "1608600")
                            .put("roleName", "测试角色")
                            .put("areaName", "352区")
                            .put("status", "online")
                            .put("started", true)
                            .put("hasLiveSession", true)
                    ))
                    .toString()
            )
        }

        val result = client.listAccounts()

        assertTrue(result is DesktopCoreResult.Ok)
        val account = (result as DesktopCoreResult.Ok).value.single()
        assertEquals("opaque-ref", account.accountRef)
        assertEquals("1608600", account.username)
        assertTrue(account.online)
    }

    @Test
    fun generalVisitPreservesSelectionOrderAndCapsAtFour() {
        var request: DesktopCoreHttpRequest? = null
        val client = DesktopCoreApiClient(settings) {
            request = it
            DesktopCoreHttpResponse(200, """{"ok":true}""")
        }

        client.dailyAction(
            accountRef = "opaque-ref",
            feature = DesktopCoreApiClient.DailyFeature.GENERAL_VISIT,
            orderedGeneralIds = listOf("9", "3", "9", "5", "8", "7"),
            idempotencyKey = "visit-once"
        )

        val body = JSONObject(request!!.body!!)
        val ids = body.getJSONArray("generalVisitGeneralIds")
        assertEquals(listOf("9", "3", "5", "8"), (0 until ids.length()).map(ids::getString))
        assertEquals("visit-once", request!!.headers["Idempotency-Key"])
    }

    @Test
    fun revisionConflictIsReturnedAsStructuredError() {
        val client = DesktopCoreApiClient(settings) {
            DesktopCoreHttpResponse(
                409,
                """{"ok":false,"code":"SETTINGS_REVISION_CONFLICT","error":"reload"}"""
            )
        }

        val result = client.patchSettings(
            accountRef = "opaque-ref",
            scope = "common.daily",
            patch = JSONObject().put("dailyTasks", JSONObject().put("salary", true)),
            revision = "old",
            idempotencyKey = "settings-once"
        )

        assertTrue(result is DesktopCoreResult.Err)
        result as DesktopCoreResult.Err
        assertEquals("SETTINGS_REVISION_CONFLICT", result.code)
        assertEquals(409, result.status)
        assertTrue(result.retryable)
    }

    @Test
    fun disabledSettingsFailClosedBeforeNetworkCall() {
        var called = false
        val client = DesktopCoreApiClient(settings.copy(enabled = false)) {
            called = true
            DesktopCoreHttpResponse(200, "{}")
        }

        val result = client.health()

        assertTrue(result is DesktopCoreResult.Err)
        assertFalse(called)
    }
}

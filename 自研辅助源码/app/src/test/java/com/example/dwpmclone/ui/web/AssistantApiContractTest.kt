package com.example.dwpmclone.ui.web

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantApiContractTest {
    @Test
    fun decodesVersionedAllowListedRequestShape() {
        val request = AssistantApiMessageCodec.decode(
            JSONObject()
                .put("apiVersion", "v1")
                .put("id", "android-1")
                .put("method", "post")
                .put("path", "/api/accounts/start")
                .put("body", JSONObject().put("sessionId", "7"))
                .toString()
        )

        assertEquals("android-1", request.id)
        assertEquals("POST", request.method)
        assertEquals("7", request.body?.optString("sessionId"))
    }

    @Test
    fun rejectsTraversalAndUnsupportedMethods() {
        val traversal = requestJson(method = "GET", path = "/api/../secret")
        val delete = requestJson(method = "DELETE", path = "/api/accounts")

        assertTrue(runCatching { AssistantApiMessageCodec.decode(traversal) }.isFailure)
        assertTrue(runCatching { AssistantApiMessageCodec.decode(delete) }.isFailure)
    }

    @Test
    fun errorResponseNeverReflectsInvalidRequestId() {
        val response = AssistantApiMessageCodec.error("');alert(1);//", 400, "bad")
        val json = response.toJson()

        assertEquals("invalid", json.getString("id"))
        assertFalse(json.getJSONObject("body").getBoolean("ok"))
    }

    private fun requestJson(method: String, path: String): String = JSONObject()
        .put("apiVersion", "v1")
        .put("id", "request-1")
        .put("method", method)
        .put("path", path)
        .put("body", JSONObject())
        .toString()
}

package com.example.dwpmclone.ui.web

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ResourceWaitNoticeProjectionTest {
    private fun envelope(retryAt: Long = 60_000L) = JSONObject()
        .put("ok", true)
        .put("notices", JSONArray().put(JSONObject()
            .put("key", "resource:brushYellow:1000")
            .put("feature", "brushYellow")
            .put("title", "刷黄等待资源")
            .put("message", "粮食转铜失败，其他任务继续运行")
            .put("nextRetryAt", retryAt)))

    @Test
    fun durableWarningNeedsNoRuntimeFailureOrLogRow() {
        val projected = ResourceWaitNoticeProjection.from(envelope()) { false }
        assertEquals(setOf("brushYellow"), projected.features)
        assertEquals(1, projected.visible.size)
        assertTrue(projected.visible.single().getString("message").contains("粮食转铜失败"))
    }

    @Test
    fun dismissedEpisodeStillSuppressesLegacyDuplicatesOnLaterRetries() {
        for (retryAt in listOf(60_000L, 180_000L, 420_000L)) {
            val projected = ResourceWaitNoticeProjection.from(envelope(retryAt)) {
                it == "resource:brushYellow:1000"
            }
            assertTrue(projected.visible.isEmpty())
            assertEquals(setOf("brushYellow"), projected.features)
        }
    }

    @Test
    fun recoveredOrUnavailableProjectionDoesNotHideNewTaskErrors() {
        for (value in listOf(
            JSONObject().put("ok", true).put("notices", JSONArray()),
            JSONObject().put("ok", false).put("notices", envelope().getJSONArray("notices")),
            JSONObject(),
        )) {
            val projected = ResourceWaitNoticeProjection.from(value) { false }
            assertTrue(projected.features.isEmpty())
            assertTrue(projected.visible.isEmpty())
        }
    }

    @Test
    fun independentBrushTeamWarningStaysVisibleAndDismissible() {
        val value = JSONObject().put("ok", true).put("notices", JSONArray()
            .put(JSONObject()
                .put("key", "brush-lane:brush:team-2")
                .put("feature", "brushYellow")
                .put("title", "刷黄编队2需核对")
                .put("message", "该队回执不明，其他独立编队继续运行"))
            .put(JSONObject().put("key", "untrusted:other").put("feature", "brushYellow")))
        val visible = ResourceWaitNoticeProjection.from(value) { false }
        assertEquals(1, visible.visible.size)
        assertEquals("刷黄编队2需核对", visible.visible.single().getString("title"))
        val dismissed = ResourceWaitNoticeProjection.from(value) { it.startsWith("brush-lane:") }
        assertTrue(dismissed.visible.isEmpty())
        assertEquals(setOf("brushYellow"), dismissed.features)
    }
}

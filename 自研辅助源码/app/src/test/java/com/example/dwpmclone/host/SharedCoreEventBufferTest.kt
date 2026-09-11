package com.example.dwpmclone.host

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedCoreEventBufferTest {
    @Test
    fun subscriptionsReceiveMonotonicHostIdsAndStopAfterUnsubscribe() {
        val token = "event-buffer-${System.nanoTime()}"
        val received = mutableListOf<JSONObject>()
        val subscription = SharedCoreEventBuffer.subscribe { encoded ->
            val event = JSONObject(encoded)
            if (event.optString("testToken") == token) received += event
        }

        SharedCoreEventBuffer.publish(
            JSONObject()
                .put("testToken", token)
                .put("step", 1)
                .put("eventId", -999)
                .toString()
        )
        SharedCoreEventBuffer.publish(
            JSONObject().put("testToken", token).put("step", 2).toString()
        )
        SharedCoreEventBuffer.unsubscribe(subscription)
        SharedCoreEventBuffer.publish(
            JSONObject().put("testToken", token).put("step", 3).toString()
        )

        assertEquals(listOf(1, 2), received.map { it.getInt("step") })
        val ids = received.map { it.getLong("eventId") }
        assertTrue(ids[0] > 0L)
        assertTrue(ids[1] > ids[0])
        assertNotEquals(-999L, ids[0])

        val snapshotMatches = SharedCoreEventBuffer.snapshot()
            .let { snapshot ->
                (0 until snapshot.length())
                    .map { snapshot.getJSONObject(it) }
                    .filter { it.optString("testToken") == token }
            }
        assertEquals(listOf(1, 2, 3), snapshotMatches.map { it.getInt("step") })
    }
}

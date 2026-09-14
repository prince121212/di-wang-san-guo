package com.example.dwpmclone.host

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test


class SharedResidentAutomationAdapterTest {
    @Test
    fun oneShotAdapterDoesNotSpinWhileOperationIsRunning() {
        var submissions = 0
        var statusReads = 0
        var pauses = 0
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ ->
                submissions += 1
                JSONObject().put("operationId", "op-running")
            },
            status = {
                statusReads += 1
                JSONObject().put("operation", JSONObject()
                    .put("status", "RUNNING")
                    .put("requestSent", false)
                    .put("progressDetails", JSONObject().put("phase", "resident-brush-search")))
            },
            nowMillis = { 1_000L },
            pause = { pauses += 1 },
        )

        val result = adapter.runOnce(7, JSONObject(), "tick-one-shot")

        assertEquals(1, submissions)
        assertEquals(1, statusReads)
        assertEquals(0, pauses)
        assertEquals("running", result.state)
        assertEquals(6_000L, result.nextWakeAtMillis)
        assertEquals("brush", result.feature)
    }

    @Test
    fun oneShotAdapterResumesDurableOperationWithoutResubmitting() {
        val store = InMemoryResidentOperationStore().apply {
            putOperation(7, "op-existing", "tick-before-process-death")
        }
        var submissions = 0
        var readId = ""
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ ->
                submissions += 1
                JSONObject().put("operationId", "must-not-submit")
            },
            status = { operationId ->
                readId = operationId
                JSONObject().put("operation", JSONObject()
                    .put("status", "SUCCEEDED")
                    .put("requestSent", false)
                    .put("result", JSONObject()
                        .put("state", "idle")
                        .put("message", "recovered")))
            },
            operationStore = store,
            pause = {},
        )

        val result = adapter.runOnce(7, JSONObject(), "new-process-tick")

        assertEquals(0, submissions)
        assertEquals("op-existing", readId)
        assertEquals("recovered", result.message)
        assertNull(store.get(7))
    }

    @Test
    fun submitResponseLossReusesTheSameIdempotencyKey() {
        val store = InMemoryResidentOperationStore()
        val observedKeys = mutableListOf<String>()
        var attempt = 0
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, key, _ ->
                observedKeys += key
                attempt += 1
                if (attempt == 1) error("response lost")
                JSONObject().put("operationId", "op-deduplicated")
            },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "RUNNING")
                    .put("requestSent", true))
            },
            operationStore = store,
            nowMillis = { 1_000L },
            pause = {},
        )

        adapter.runOnce(7, JSONObject(), "tick-original")
        val result = adapter.runOnce(7, JSONObject(), "tick-new")

        assertEquals(listOf("tick-original", "tick-original"), observedKeys)
        assertEquals("op-deduplicated", result.operationId)
        assertEquals("tick-original", store.get(7)?.tickKey)
    }

    @Test
    fun configuresSubmitsAndConsumesPythonDeadline() {
        var configured = false
        var submitted = false
        var allowedFeatures = emptyList<String>()
        val adapter = SharedResidentAutomationAdapter(
            configure = { accountRef, habits ->
                configured = accountRef == "7" && habits.optBoolean("fixture")
                JSONObject().put("ok", true)
            },
            submit = { accountRef, key, context ->
                submitted = accountRef == "7" && key == "tick-1"
                allowedFeatures = context.getJSONArray("allowedFeatures")
                    .let { array -> (0 until array.length()).map(array::getString) }
                JSONObject().put("operationId", "op-1")
            },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "SUCCEEDED")
                    .put("requestSent", true)
                    .put("result", JSONObject()
                        .put("feature", "mine")
                        .put("state", "waiting")
                        .put("message", "等待驻守")
                        .put("nextWakeAtMillis", 12_345L)))
            },
            pause = {},
        )

        val result = adapter.run(7, JSONObject().put("fixture", true), "tick-1")

        assertTrue(configured)
        assertTrue(submitted)
        assertEquals(
            listOf("mine", "lossless", "brush", "raid", "dungeon", "general", "ministry", "captives", "domestic", "inventory", "alarm", "daily"),
            allowedFeatures
        )
        assertEquals("mine", result.feature)
        assertNull(result.dailyKey)
        assertEquals(12_345L, result.nextWakeAtMillis)
        assertTrue(result.requestSent)
        assertFalse(result.requiresAttention)
    }

    @Test
    fun projectsStructuredDailySkipMetadataForRoleTaskUi() {
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-skip") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "SUCCEEDED")
                    .put("requestSent", false)
                    .put("result", JSONObject()
                        .put("feature", "daily")
                        .put("dailyKey", "salary")
                        .put("state", "completed")
                        .put("success", true)
                        .put("completed", true)
                        .put("skipped", true)
                        .put("skipReason", "national-citizen")
                        .put("statusText", "已做（国民跳过）")
                        .put("cycleKey", 123L)
                        .put("message", "国民跳过")
                        .put("nextWakeAtMillis", 456L)))
            },
            pause = {},
        )

        val result = adapter.run(7, JSONObject(), "tick-skip")

        assertEquals("daily", result.feature)
        assertEquals("salary", result.dailyKey)
        assertTrue(result.skipped)
        assertEquals("national-citizen", result.skipReason)
        assertEquals("已做（国民跳过）", result.statusText)
        assertEquals(123L, result.cycleKey)
    }

    @Test
    fun projectsFeatureScopedAttentionSeparatelyFromOrdinaryIsolation() {
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-isolated") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "SUCCEEDED")
                    .put("requestSent", false)
                    .put("result", JSONObject()
                        .put("feature", "brush")
                        .put("state", "waiting")
                        .put("isolatedPendingFeatures", JSONArray(listOf("brush", "inventory")))
                        .put("isolatedAttentionFeatures", JSONArray(listOf("inventory")))
                        .put("message", "等待将领回闲")))
            },
            pause = {},
        )

        val result = adapter.runOnce(7, JSONObject(), "tick-isolated")

        assertEquals("brush|inventory", result.isolatedFeatures)
        assertEquals("inventory", result.isolatedAttentionFeatures)
    }

    @Test
    fun uncertainMutationNeverSchedulesAutomaticReplay() {
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-u") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "UNCERTAIN")
                    .put("requestSent", true)
                    .put("error", JSONObject().put("message", "回执不明")))
            },
            pause = {},
        )

        val result = adapter.run(7, JSONObject(), "tick-u")

        assertEquals("uncertain", result.state)
        assertTrue(result.requiresAttention)
        assertNull(result.nextWakeAtMillis)
    }

    @Test
    fun failureBeforeSendUsesBoundedRetry() {
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-f") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "FAILED")
                    .put("requestSent", false)
                    .put("error", JSONObject().put("message", "断网")))
            },
            nowMillis = { 1_000L },
            pause = {},
        )

        val result = adapter.run(7, JSONObject(), "tick-f")

        assertEquals(11_000L, result.nextWakeAtMillis)
        assertFalse(result.requiresAttention)
    }

    @Test
    fun aServerRejectionAfterSendIsAKnownResultNotAnOpenQuestion() {
        // The exact operation that stopped a real account for three hours:
        // 将领维护 sent a 活血丹 use, the server answered "使用失败状态 -1",
        // and because a request had crossed the send boundary the whole
        // account was held for a human - including 副本 and 刷黄, which had
        // nothing to do with the item and were both mid-flight.
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-energy") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "FAILED")
                    .put("requestSent", true)
                    .put("error", JSONObject()
                        .put("message", "使用失败状态 -1")
                        .put("details", JSONObject().put("feature", "general"))))
            },
            nowMillis = { 1_000L },
            pause = {},
        )

        val result = adapter.run(7, JSONObject(), "tick-energy-rejected")

        assertEquals("general", result.feature)
        assertFalse(result.requiresAttention)
        assertEquals(11_000L, result.nextWakeAtMillis)
    }

    @Test
    fun anUnknownOutcomeOwnedByOneFeatureDoesNotStopTheAccount() {
        // The core isolates the feature itself and keeps scheduling the rest,
        // so an account-scoped gate must not act on a feature-scoped fact.
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-uf") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "UNCERTAIN")
                    .put("requestSent", true)
                    .put("error", JSONObject()
                        .put("message", "出征回执不明")
                        .put("details", JSONObject().put("feature", "dungeon"))))
            },
            nowMillis = { 1_000L },
            pause = {},
        )

        val result = adapter.run(7, JSONObject(), "tick-uncertain-feature")

        assertEquals("dungeon", result.feature)
        assertFalse(result.requiresAttention)
        assertEquals(11_000L, result.nextWakeAtMillis)
    }

    @Test
    fun failedMapScanIsAttributedOnlyToBrushFeature() {
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-map") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "FAILED")
                    .put("requestSent", false)
                    .put("progressDetails", JSONObject()
                        .put("phase", "scanning-bandit-map")
                        .put("requestIndex", 2))
                    .put("error", JSONObject().put("message", "timeout")))
            },
            pause = {},
        )

        val result = adapter.run(7, JSONObject(), "tick-map")

        assertEquals("brush", result.feature)
        assertEquals("failed", result.state)
    }

    @Test
    fun unattributedTransportFailureDoesNotPretendEveryTaskFailed() {
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-network") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "FAILED")
                    .put("requestSent", false)
                    .put("error", JSONObject().put("message", "timeout")))
            },
            pause = {},
        )

        val result = adapter.run(7, JSONObject(), "tick-network")

        assertNull(result.feature)
    }

    @Test
    fun configurationFailureDoesNotSubmitNetworkTick() {
        var submissions = 0
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> error("本地配置无效") },
            submit = { _, _, _ ->
                submissions += 1
                JSONObject().put("operationId", "must-not-submit")
            },
            status = { JSONObject() },
            nowMillis = { 1_000L },
            pause = {},
        )

        val result = adapter.run(7, JSONObject(), "tick-config-failed")

        assertEquals(0, submissions)
        assertEquals("retry", result.state)
        assertEquals(11_000L, result.nextWakeAtMillis)
        assertFalse(result.requestSent)
    }

    @Test
    fun unresolvedRunningOperationTimesOutWithoutAutomaticDeadline() {
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-running") },
            status = {
                JSONObject().put("operation", JSONObject()
                    .put("status", "RUNNING")
                    .put("requestSent", true))
            },
            pause = {},
            maximumPolls = 1,
        )

        val result = adapter.run(7, JSONObject(), "tick-timeout")

        assertEquals("timeout", result.state)
        assertTrue(result.requiresAttention)
        assertTrue(result.requestSent)
        assertNull(result.nextWakeAtMillis)
    }

    @Test
    fun freshSubmitSettlesInsideTheCurrentWakeupInsteadOfArmingAnotherAlarm() {
        var settleReads = 0
        var plainReads = 0
        var observedBudget = -1L
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "op-settles") },
            status = {
                plainReads += 1
                JSONObject().put("operation", JSONObject()
                    .put("status", "RUNNING")
                    .put("requestSent", false))
            },
            nowMillis = { 1_000L },
            pause = {},
            settleStatus = { _, budget ->
                settleReads += 1
                observedBudget = budget
                JSONObject().put("operation", JSONObject()
                    .put("status", "SUCCEEDED")
                    .put("requestSent", true)
                    .put("result", JSONObject()
                        .put("state", "idle")
                        .put("message", "settled in window")
                        .put("nextWakeAtMillis", 31_000L)))
            },
        )

        val result = adapter.runOnce(7, JSONObject(), "tick-settling")

        assertEquals(1, settleReads)
        assertEquals(0, plainReads)
        assertEquals(SharedResidentAutomationAdapter.SETTLE_BUDGET_MILLIS, observedBudget)
        assertEquals("settled in window", result.message)
        // The business deadline survives; no PENDING_POLL_MILLIS re-read is armed.
        assertEquals(31_000L, result.nextWakeAtMillis)
    }

    @Test
    fun resumedOperationKeepsTheNonBlockingReadPath() {
        val store = InMemoryResidentOperationStore().apply {
            putOperation(7, "op-long-running", "tick-before-process-death")
        }
        var settleReads = 0
        var plainReads = 0
        val adapter = SharedResidentAutomationAdapter(
            configure = { _, _ -> JSONObject().put("ok", true) },
            submit = { _, _, _ -> JSONObject().put("operationId", "must-not-submit") },
            status = {
                plainReads += 1
                JSONObject().put("operation", JSONObject()
                    .put("status", "RUNNING")
                    .put("requestSent", true))
            },
            nowMillis = { 1_000L },
            pause = {},
            operationStore = store,
            settleStatus = { _, _ ->
                settleReads += 1
                JSONObject()
            },
        )

        val result = adapter.runOnce(7, JSONObject(), "tick-resumed")

        assertEquals(0, settleReads)
        assertEquals(1, plainReads)
        assertEquals("running", result.state)
        assertEquals(
            1_000L + SharedResidentAutomationAdapter.PENDING_POLL_MILLIS,
            result.nextWakeAtMillis,
        )
    }
}

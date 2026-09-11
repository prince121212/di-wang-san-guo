package com.example.dwpmclone.data.local

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HostingInterruptionReportTest {
    private fun runtime(
        interruptedAtMillis: Long? = null,
        previousHeartbeatAtMillis: Long? = null,
        stopReason: String? = null,
    ) = JSONObject().apply {
        put("interruptedAtMillis", interruptedAtMillis ?: JSONObject.NULL)
        put("previousHeartbeatAtMillis", previousHeartbeatAtMillis ?: JSONObject.NULL)
        put("stopReason", stopReason ?: JSONObject.NULL)
    }

    @Test
    fun cleanStartIsNotReportedAsAnInterruption() {
        val report = HostingInterruptionReport.of(
            runtime = runtime(stopReason = "explicit stop action"),
            exits = listOf(
                ProcessExitRecord(1_000L, HostingInterruptionReport.REASON_USER_REQUESTED),
            ),
            nowMillis = 10_000L,
        )

        assertFalse(report.interrupted)
        assertEquals("none", report.attribution)
        assertNull(report.gapMillis)
        assertFalse(report.userActionable)
    }

    @Test
    fun vendorKillIsAttributedAndMarkedUserActionable() {
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 700_000L,
                previousHeartbeatAtMillis = 400_000L,
            ),
            exits = listOf(
                ProcessExitRecord(
                    timestampMillis = 500_000L,
                    reasonCode = HostingInterruptionReport.REASON_OTHER,
                    description = "cleaner",
                ),
            ),
            nowMillis = 700_500L,
        )

        assertTrue(report.interrupted)
        assertEquals("system-killed", report.attribution)
        assertTrue(report.userActionable)
        assertEquals(300_000L, report.gapMillis)
        assertEquals(HostingInterruptionReport.REASON_OTHER, report.exitReasonCode)
        assertTrue(report.summaryLine().contains("5分0秒"))
        assertTrue(report.summaryLine().contains("建议检查自启动"))
    }

    @Test
    fun ownAppUpdateIsNotBlamedOnTheVendor() {
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 200_000L,
                previousHeartbeatAtMillis = 190_000L,
            ),
            exits = listOf(
                ProcessExitRecord(195_000L, HostingInterruptionReport.REASON_PACKAGE_UPDATED),
            ),
            nowMillis = 200_100L,
        )

        assertEquals("package-updated", report.attribution)
        assertFalse(report.userActionable)
        assertFalse(report.summaryLine().contains("建议检查"))
    }

    @Test
    fun staleExitRecordBeforeTheLastHeartbeatIsIgnored() {
        // A force-stop from days ago must not be blamed for tonight's gap.
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 900_000L,
                previousHeartbeatAtMillis = 800_000L,
                stopReason = "service destroyed",
            ),
            exits = listOf(
                ProcessExitRecord(10_000L, HostingInterruptionReport.REASON_USER_REQUESTED),
            ),
            nowMillis = 900_500L,
        )

        assertTrue(report.interrupted)
        assertNull(report.exitReasonCode)
        assertEquals("recorded-stop", report.attribution)
        assertTrue(report.attributionText.contains("service destroyed"))
        assertEquals(100_000L, report.gapMillis)
    }

    @Test
    fun futureExitRecordIsIgnored() {
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 500_000L,
                previousHeartbeatAtMillis = 400_000L,
            ),
            exits = listOf(
                ProcessExitRecord(9_000_000L, HostingInterruptionReport.REASON_LOW_MEMORY),
            ),
            nowMillis = 500_100L,
        )

        assertNull(report.exitReasonCode)
        assertEquals("unknown", report.attribution)
    }

    @Test
    fun newestEligibleExitWinsOverOlderOnes() {
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 800_000L,
                previousHeartbeatAtMillis = 400_000L,
            ),
            exits = listOf(
                ProcessExitRecord(450_000L, HostingInterruptionReport.REASON_CRASH),
                ProcessExitRecord(600_000L, HostingInterruptionReport.REASON_LOW_MEMORY),
            ),
            nowMillis = 800_100L,
        )

        assertEquals("low-memory", report.attribution)
        assertTrue(report.userActionable)
    }

    @Test
    fun missingHeartbeatEvidenceStillAttributesWithoutADuration() {
        val report = HostingInterruptionReport.of(
            runtime = runtime(interruptedAtMillis = 600_000L),
            exits = listOf(
                ProcessExitRecord(550_000L, HostingInterruptionReport.REASON_SIGNALED),
            ),
            nowMillis = 600_100L,
        )

        assertTrue(report.interrupted)
        assertEquals("system-killed", report.attribution)
        assertNull(report.gapMillis)
        assertTrue(report.summaryLine().contains("中断时长未知"))
    }

    @Test
    fun crashIsSurfacedAsADeveloperIssueNotASettingsIssue() {
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 300_000L,
                previousHeartbeatAtMillis = 299_000L,
            ),
            exits = listOf(
                ProcessExitRecord(299_500L, HostingInterruptionReport.REASON_ANR),
            ),
            nowMillis = 300_100L,
        )

        assertEquals("anr", report.attribution)
        assertFalse(report.userActionable)
        assertTrue(report.attributionText.contains("需要开发定位"))
    }

    @Test
    fun webViewRendererExitIsNotMistakenForAHostKill() {
        // Real trace from a Xiaomi device: the newest record was the WebView
        // sandbox renderer being reaped (reason 13), while the host process had
        // exited for a benign reason. Taking the newest record unfiltered
        // reported a vendor kill that never happened.
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 700_000L,
                previousHeartbeatAtMillis = 400_000L,
            ),
            exits = listOf(
                ProcessExitRecord(
                    timestampMillis = 690_000L,
                    reasonCode = HostingInterruptionReport.REASON_OTHER,
                    description = "isolated not needed",
                    processName = "com.example.dwpmclone:sandboxed_process0",
                ),
                ProcessExitRecord(
                    timestampMillis = 500_000L,
                    reasonCode = HostingInterruptionReport.REASON_LOW_MEMORY,
                    processName = "com.example.dwpmclone",
                ),
            ),
            nowMillis = 700_500L,
            mainProcessName = "com.example.dwpmclone",
        )

        assertEquals("low-memory", report.attribution)
        assertEquals(HostingInterruptionReport.REASON_LOW_MEMORY, report.exitReasonCode)
    }

    @Test
    fun ourOwnInstallIsNotBlamedOnTheVendor() {
        // An `adb install -r` / store update force-stops the app, which the
        // platform records as USER_REQUESTED. Without the update timestamp this
        // read as a user or ROM action and produced misleading advice.
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 700_000L,
                previousHeartbeatAtMillis = 690_000L,
            ),
            exits = listOf(
                ProcessExitRecord(
                    timestampMillis = 695_000L,
                    reasonCode = HostingInterruptionReport.REASON_USER_REQUESTED,
                    description = "stop com.example.dwpmclone due to installPackageLI",
                    processName = "com.example.dwpmclone",
                ),
            ),
            nowMillis = 700_500L,
            mainProcessName = "com.example.dwpmclone",
            lastUpdateTimeMillis = 695_200L,
        )

        assertEquals("package-updated", report.attribution)
        assertFalse(report.userActionable)
    }

    @Test
    fun aRealKillLongAfterAnUpdateIsStillAttributedToTheSystem() {
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 900_000L,
                previousHeartbeatAtMillis = 800_000L,
            ),
            exits = listOf(
                ProcessExitRecord(
                    timestampMillis = 850_000L,
                    reasonCode = HostingInterruptionReport.REASON_OTHER,
                    processName = "com.example.dwpmclone",
                ),
            ),
            nowMillis = 900_500L,
            mainProcessName = "com.example.dwpmclone",
            // Update happened hours earlier; it cannot explain this exit.
            lastUpdateTimeMillis = 100_000L,
        )

        assertEquals("system-killed", report.attribution)
        assertTrue(report.userActionable)
    }

    @Test
    fun recordsWithoutAProcessNameAreStillUsable() {
        // API 30 devices and defensive fallbacks may omit the process name; the
        // filter must not throw that evidence away.
        val report = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 700_000L,
                previousHeartbeatAtMillis = 400_000L,
            ),
            exits = listOf(
                ProcessExitRecord(500_000L, HostingInterruptionReport.REASON_FREEZER),
            ),
            nowMillis = 700_500L,
            mainProcessName = "com.example.dwpmclone",
        )

        assertEquals("freezer", report.attribution)
    }

    @Test
    fun reportSerialisesEveryFieldTheAssistantPageNeeds() {
        val json = HostingInterruptionReport.of(
            runtime = runtime(
                interruptedAtMillis = 7_400_000L,
                previousHeartbeatAtMillis = 3_800_000L,
            ),
            exits = listOf(
                ProcessExitRecord(
                    timestampMillis = 4_000_000L,
                    reasonCode = HostingInterruptionReport.REASON_FREEZER,
                    description = "freezer",
                ),
            ),
            nowMillis = 7_400_100L,
        ).toJson()

        assertTrue(json.getBoolean("interrupted"))
        assertEquals(3_600_000L, json.getLong("gapMillis"))
        assertEquals("freezer", json.getString("attribution"))
        assertTrue(json.getBoolean("userActionable"))
        assertEquals(HostingInterruptionReport.REASON_FREEZER, json.getInt("exitReasonCode"))
        assertEquals("freezer", json.getString("exitDescription"))
        assertTrue(json.getString("summary").contains("1小时0分"))
    }
}

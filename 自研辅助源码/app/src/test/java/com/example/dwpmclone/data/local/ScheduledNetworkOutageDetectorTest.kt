package com.example.dwpmclone.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The claim "your system turns the network off on a timer" has to be earned.
 *
 * Observed on a real phone: Wi-Fi went off ~23:10 and came back ~07:35 every
 * night for two weeks while hosting stayed alive, which read as a broken
 * assistant. Nothing in Android can report that switch, so the shape of the
 * outage is the only evidence — and it has to be strong enough that a router
 * reboot never produces this message.
 */
class ScheduledNetworkOutageDetectorTest {
    private val zone = 8 * 60 * 60 * 1000L
    private val day = 86_400_000L

    /** 2026-09-01 00:00 UTC+8. */
    private val baseDay = 1_787_500_800_000L - (1_787_500_800_000L % day) - zone

    private fun at(dayOffset: Int, hour: Int, minute: Int): Long =
        baseDay + dayOffset * day + hour * 3_600_000L + minute * 60_000L

    private fun window(
        startDay: Int,
        startHour: Int,
        startMinute: Int,
        endDay: Int,
        endHour: Int,
        endMinute: Int,
        startObserved: Boolean = true,
        endObserved: Boolean = true,
    ) = NetworkOutageWindow(
        startAtMillis = at(startDay, startHour, startMinute),
        endAtMillis = at(endDay, endHour, endMinute),
        startObserved = startObserved,
        endObserved = endObserved,
    )

    private fun detect(windows: List<NetworkOutageWindow>, nowDayOffset: Int = 3) =
        ScheduledNetworkOutageDetector.detect(
            windows,
            nowMillis = at(nowDayOffset, 12, 0),
            zoneOffsetMillis = zone,
        )

    @Test
    fun theRealNightlyPatternIsReported() {
        val schedule = detect(
            listOf(
                window(0, 23, 15, 1, 7, 27),
                window(1, 23, 12, 2, 7, 29),
                window(2, 23, 10, 3, 7, 35),
            )
        )
        requireNotNull(schedule)
        assertEquals(3, schedule.occurrences)
        assertEquals(3, schedule.observedDays)
        assertEquals("23:12", schedule.startClock)
        assertEquals("07:29", schedule.endClock)
        // ~8.3 hours; the median of 8h12m / 8h17m / 8h25m.
        assertEquals(8 * 60 + 17, schedule.durationMinutes)
        assertEquals(at(2, 23, 10), schedule.lastStartAtMillis)
        assertTrue(schedule.summaryLine().contains("23:12"))
        assertTrue(schedule.summaryLine().contains("07:29"))
        assertTrue(schedule.summaryLine().contains("8.3小时"))
        assertTrue(ScheduledNetworkOutageDetector.needsReview(schedule, schedule.lastEndAtMillis - 1L))
        assertTrue(!ScheduledNetworkOutageDetector.needsReview(schedule, schedule.lastEndAtMillis))
        assertTrue(!ScheduledNetworkOutageDetector.needsReview(schedule, schedule.lastEndAtMillis + 1L))
    }

    @Test
    fun oneLongOutageIsAnIncidentNotASchedule() {
        assertNull(detect(listOf(window(0, 23, 15, 1, 7, 27))))
    }

    @Test
    fun twoOutagesInTheSameNightAreOneIncident() {
        // Same local date, so this is one bad night rather than a daily habit.
        assertNull(
            detect(
                listOf(
                    window(0, 1, 0, 0, 2, 30),
                    window(0, 3, 0, 0, 4, 30),
                )
            )
        )
    }

    @Test
    fun randomOutagesWithoutAConsistentEndAreNotASchedule() {
        // Both start around midnight, but the network comes back after wildly
        // different delays — a flaky router, not a timer.
        assertNull(
            detect(
                listOf(
                    window(0, 23, 40, 1, 1, 10),
                    window(1, 23, 20, 2, 7, 30),
                )
            )
        )
    }

    @Test
    fun shortOutagesAreIgnoredEvenWhenPerfectlyRegular() {
        // A 20-minute nightly blip is not worth sending anyone into settings.
        assertNull(
            detect(
                listOf(
                    window(0, 23, 0, 0, 23, 20),
                    window(1, 23, 0, 1, 23, 20),
                    window(2, 23, 0, 2, 23, 20),
                )
            )
        )
    }

    @Test
    fun inferredBoundariesCannotCreateASchedule() {
        // Both windows were only inherited at process start, so their times
        // describe when the app was reopened, not when the network changed.
        assertNull(
            detect(
                listOf(
                    window(0, 23, 15, 1, 7, 27, startObserved = false),
                    window(1, 23, 12, 2, 7, 29, endObserved = false),
                )
            )
        )
    }

    @Test
    fun outagesOlderThanTheLookbackAreDropped() {
        assertNull(
            detect(
                listOf(
                    window(-30, 23, 15, -29, 7, 27),
                    window(-29, 23, 12, -28, 7, 29),
                ),
                nowDayOffset = 3,
            )
        )
    }

    @Test
    fun clockTextAndDurationTextStayReadable() {
        assertEquals("00:05", ScheduledNetworkOutage.clockText(5))
        assertEquals("23:59", ScheduledNetworkOutage.clockText(1439))
        // Wraps instead of throwing, so a median across midnight is printable.
        assertEquals("00:00", ScheduledNetworkOutage.clockText(1440))
        assertEquals("23:00", ScheduledNetworkOutage.clockText(-60))
        assertEquals("45分钟", ScheduledNetworkOutage.durationText(45))
        assertEquals("1.5小时", ScheduledNetworkOutage.durationText(90))
    }

    @Test
    fun aScheduleStraddlingMidnightKeepsItsOwnClockTime() {
        // Starts before midnight, ends after: the medians must not average to
        // the middle of the day.
        val schedule = detect(
            listOf(
                window(0, 23, 50, 1, 0, 55),
                window(1, 23, 55, 2, 1, 5),
            )
        )
        requireNotNull(schedule)
        assertEquals("23:52", schedule.startClock)
        assertEquals("01:00", schedule.endClock)
    }
}

package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.DailyCityLordCollectConfig
import com.example.dwpmclone.domain.model.DailyDonateConfig
import com.example.dwpmclone.domain.model.DailyGeneralVisitConfig
import com.example.dwpmclone.domain.model.DailyNationalCollectConfig
import com.example.dwpmclone.domain.model.DailySalaryConfig
import com.example.dwpmclone.domain.model.DailyStep
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.GeneralVisitCandidate
import com.example.dwpmclone.domain.protocol.GeneralVisitQuery
import com.example.dwpmclone.domain.protocol.LootTargetFief
import com.example.dwpmclone.domain.protocol.NationalCity
import com.example.dwpmclone.domain.protocol.NationalCityKind
import com.example.dwpmclone.domain.protocol.NationalCollectStatus
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.state.InMemoryDailyCompletionStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DailyFeatureTerminalSemanticsTest {
    @Test
    fun donationAttemptsAllThreeEndpointsAndPartialSuccessRemainsRetryable() {
        val calls = mutableListOf<DailyStep>()
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun runDailyStep(
                session: GameSession,
                step: DailyStep
            ): ProtocolResult<StepResult> {
                calls += step
                return ProtocolResult.Ok(
                    StepResult(step != DailyStep.DONATE_FOOD, "${step.name} result")
                )
            }
        }
        val completions = InMemoryDailyCompletionStore()
        val decision = SuspendRunner.run {
            DailyDonateTask(1L, DailyDonateConfig(true)).step(context(protocol, completions))
        }

        assertEquals(
            listOf(DailyStep.DONATE_COPPER, DailyStep.DONATE_FOOD, DailyStep.DONATE_TECH),
            calls
        )
        assertEquals(TaskDecision.Sleep(60_000L), decision)
        assertFalse(completions.isCompleted(1L, "autoDonate", NOW))
    }

    @Test
    fun donationQuotaTerminalReceiptsMarkTheDailyTaskDone() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun runDailyStep(
                session: GameSession,
                step: DailyStep
            ): ProtocolResult<StepResult> = ProtocolResult.Ok(
                StepResult(
                    true,
                    "${step.name}今日额度已用完",
                    mapOf("alreadyCompleted" to "true")
                )
            )
        }
        val completions = InMemoryDailyCompletionStore()

        val decision = SuspendRunner.run {
            DailyDonateTask(1L, DailyDonateConfig(true)).step(context(protocol, completions))
        }

        assertTrue(completions.isCompleted(1L, "autoDonate", NOW))
        assertTrue(decision is TaskDecision.Sleep)
        assertTrue((decision as TaskDecision.Sleep).millis > 60_000L)
    }

    @Test
    fun rejectedSalaryReceiptDoesNotCreateACompletionMarker() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun runDailyStep(
                session: GameSession,
                step: DailyStep
            ): ProtocolResult<StepResult> = ProtocolResult.Ok(
                StepResult(false, "当前不能领取俸禄")
            )
        }
        val completions = InMemoryDailyCompletionStore()

        val decision = SuspendRunner.run {
            DailySalaryTask(1L, DailySalaryConfig(true)).step(context(protocol, completions))
        }

        assertEquals(TaskDecision.Sleep(60_000L), decision)
        assertFalse(completions.isCompleted(1L, "salary", NOW))
    }

    @Test
    fun nationalCollectionRequiresEveryAttemptedReceiptToReachSuccess() {
        val city = NationalCity("测试州", NationalCityKind.STATE, 1, 2, "", 1)
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryNationalCities(
                session: GameSession,
                kind: NationalCityKind
            ): ProtocolResult<List<NationalCity>> = ProtocolResult.Ok(
                if (kind == NationalCityKind.STATE) listOf(city) else emptyList()
            )

            override suspend fun queryNationalCollectStatus(
                session: GameSession,
                city: NationalCity
            ): ProtocolResult<NationalCollectStatus> = ProtocolResult.Ok(
                NationalCollectStatus(0, 0, 0, 1, 10_000L, 20_000L, 0L, 0L)
            )

            override suspend fun collectNationalCity(
                session: GameSession,
                city: NationalCity
            ): ProtocolResult<StepResult> = ProtocolResult.Ok(
                StepResult(false, "服务器未确认国家征收")
            )
        }
        val completions = InMemoryDailyCompletionStore()

        val decision = SuspendRunner.run {
            DailyNationalCollectTask(1L, DailyNationalCollectConfig(true))
                .step(context(protocol, completions))
        }

        assertEquals(TaskDecision.Sleep(60_000L), decision)
        assertFalse(completions.isCompleted(1L, "nationalCollect", NOW))
    }

    @Test
    fun cityLordCollectionAcceptsOnlySuccessOrDesktopTerminalMarkers() {
        val fief = LootTargetFief(0, 7L, "测试城", "测试城")
        fun protocol(message: String) = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryOwnedFiefs(
                session: GameSession
            ): ProtocolResult<List<LootTargetFief>> = ProtocolResult.Ok(listOf(fief))

            override suspend fun collectCityLord(
                session: GameSession,
                fief: LootTargetFief
            ): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(false, message))
        }

        val rejected = InMemoryDailyCompletionStore()
        assertEquals(
            TaskDecision.Sleep(60_000L),
            SuspendRunner.run {
                DailyCityLordCollectTask(1L, DailyCityLordCollectConfig(true))
                    .step(context(protocol("临时错误"), rejected))
            }
        )
        assertFalse(rejected.isCompleted(1L, "cityLordCollect", NOW))

        val already = InMemoryDailyCompletionStore()
        assertTrue(
            SuspendRunner.run {
                DailyCityLordCollectTask(1L, DailyCityLordCollectConfig(true))
                    .step(context(protocol("今日已经征收"), already))
            } is TaskDecision.Sleep
        )
        assertTrue(already.isCompleted(1L, "cityLordCollect", NOW))
    }

    @Test
    fun cityLordNoOwnedCityMarksTodayCompleted() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryOwnedFiefs(
                session: GameSession
            ): ProtocolResult<List<LootTargetFief>> = ProtocolResult.Ok(emptyList())
        }
        val completions = InMemoryDailyCompletionStore()

        val decision = SuspendRunner.run {
            DailyCityLordCollectTask(1L, DailyCityLordCollectConfig(true))
                .step(context(protocol, completions))
        }

        assertTrue(completions.isCompleted(1L, "cityLordCollect", NOW))
        assertTrue(decision is TaskDecision.Sleep)
        assertTrue((decision as TaskDecision.Sleep).millis > 60_000L)
    }

    @Test
    fun generalVisitNeedsAResolvedInteractionBeforeCompletion() {
        val candidate = candidate(88L)
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryVisitGenerals(
                session: GameSession
            ): ProtocolResult<GeneralVisitQuery> = ProtocolResult.Ok(
                GeneralVisitQuery(listOf(candidate))
            )

            override suspend fun visitGeneral(
                session: GameSession,
                candidate: GeneralVisitCandidate
            ): ProtocolResult<StepResult> = ProtocolResult.Ok(
                StepResult(false, "名将当前不可拜访")
            )
        }
        val completions = InMemoryDailyCompletionStore()

        val decision = SuspendRunner.run {
            DailyGeneralVisitTask(1L, DailyGeneralVisitConfig(true, listOf(88L)))
                .step(context(protocol, completions))
        }

        assertEquals(TaskDecision.Sleep(60_000L), decision)
        assertFalse(completions.isCompleted(1L, "generalVisit", NOW))
    }

    @Test
    fun generalVisitWithoutConfiguredSelectionUsesFirstEligibleCandidateAndCompletesToday() {
        val attempted = mutableListOf<Long>()
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryVisitGenerals(
                session: GameSession
            ): ProtocolResult<GeneralVisitQuery> = ProtocolResult.Ok(
                GeneralVisitQuery(
                    listOf(
                        candidate(77L, captiveState = 1),
                        candidate(88L, captiveState = 0)
                    )
                )
            )

            override suspend fun visitGeneral(
                session: GameSession,
                candidate: GeneralVisitCandidate
            ): ProtocolResult<StepResult> {
                attempted += candidate.id
                return ProtocolResult.Ok(
                    StepResult(
                        true,
                        "${candidate.name}拒绝了阁下的邀请，请再接再厉",
                        mapOf("invitationResolved" to "true")
                    )
                )
            }
        }
        val completions = InMemoryDailyCompletionStore()

        val decision = SuspendRunner.run {
            DailyGeneralVisitTask(1L, DailyGeneralVisitConfig(true))
                .step(context(protocol, completions))
        }

        assertEquals(listOf(88L), attempted)
        assertTrue(completions.isCompleted(1L, "generalVisit", NOW))
        assertTrue(decision is TaskDecision.Sleep)
        assertTrue((decision as TaskDecision.Sleep).millis > 60_000L)
    }

    private fun context(
        protocol: GameProtocolClient,
        completions: InMemoryDailyCompletionStore
    ) = TaskContext(
        session = GameSession(1L, "real", null, emptyMap(), 1),
        protocol = protocol,
        nowMillis = NOW,
        dailyCompletions = completions
    )

    private fun candidate(id: Long, captiveState: Int = 0) = GeneralVisitCandidate(
        id = id,
        name = "测试名将",
        level = 1,
        fiefName = "",
        cityName = "",
        captiveState = captiveState,
        ownerName = "",
        salaryStars = 0,
        loyalty = 0,
        growth = 0,
        breakout = 0,
        strengthBase = 0,
        strengthTotal = 0,
        intelligenceBase = 0,
        intelligenceTotal = 0,
        command = 0,
        troopLimit = 0,
        exp = 0L,
        expLimit = 0L,
        job = 0,
        portrait = 0
    )

    private companion object {
        const val NOW: Long = 1_000L
    }
}

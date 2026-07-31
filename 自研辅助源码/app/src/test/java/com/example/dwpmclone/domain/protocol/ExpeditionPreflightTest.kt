package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.FormationConfig
import com.example.dwpmclone.domain.model.FormationRuntime
import com.example.dwpmclone.domain.model.FormationRuntimeStatus
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.scheduler.SuspendRunner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ExpeditionPreflightTest {
    @Test
    fun readyRequiresFreshIdleGeneralAndKnownTroops() {
        val protocol = FakePreflightProtocol()
        val result = SuspendRunner.run { ExpeditionPreflight(protocol).check(session(), request()) }

        assertTrue(result is ProtocolResult.Ok)
        val snapshot = (result as ProtocolResult.Ok).value
        assertEquals(listOf(11L), snapshot.generalIds)
        assertEquals(listOf("赵云"), snapshot.generalNames)
        assertEquals(1, protocol.validations)
    }

    @Test
    fun unknownGeneralStatusFailsClosed() {
        val protocol = FakePreflightProtocol(
            generals = listOf(general(status = null))
        )
        val result = SuspendRunner.run { ExpeditionPreflight(protocol).check(session(), request()) }

        assertEquals("EXPEDITION_GENERAL_STATUS_UNKNOWN", (result as ProtocolResult.Err).code)
        assertFalse(result.retryable)
    }

    @Test
    fun busyGeneralDefersWithoutApplyingCorrections() {
        val protocol = FakePreflightProtocol(
            generals = listOf(general(status = 2))
        )
        val result = SuspendRunner.run { ExpeditionPreflight(protocol).check(session(), request()) }

        assertEquals("EXPEDITION_GENERAL_BUSY", (result as ProtocolResult.Err).code)
        assertTrue(result.retryable)
        assertEquals(0, protocol.energyCalls)
        assertEquals(0, protocol.refillCalls)
    }

    @Test
    fun dungeonParityCanIgnoreZeroLoyalty() {
        val protocol = FakePreflightProtocol(
            generals = listOf(general(loyalty = 0))
        )

        val result = SuspendRunner.run {
            ExpeditionPreflight(protocol).check(
                session(),
                request().copy(
                    label = "副本",
                    requirePositiveLoyalty = false
                )
            )
        }

        assertTrue(result is ProtocolResult.Ok)
    }

    @Test
    fun desktopParityDoesNotInventPositiveLoyaltyRequirement() {
        val protocol = FakePreflightProtocol(
            generals = listOf(general(loyalty = 0))
        )

        val result = SuspendRunner.run {
            ExpeditionPreflight(protocol).check(session(), request())
        }

        assertTrue(result is ProtocolResult.Ok)
    }

    @Test
    fun autoEnergyIsTwoPhaseAndNeverDispatchesOnStaleState() {
        val protocol = FakePreflightProtocol(
            generals = listOf(general(energy = 10))
        )
        val result = SuspendRunner.run {
            ExpeditionPreflight(protocol).check(
                session(),
                request(),
                ExpeditionPreflightPolicy(autoEnergy = true, minimumEnergy = 20)
            )
        }

        assertEquals("EXPEDITION_AUTO_ENERGY_APPLIED", (result as ProtocolResult.Err).code)
        assertTrue(result.retryable)
        assertEquals(1, protocol.energyCalls)
        assertEquals(0, protocol.refillCalls)
    }

    @Test
    fun exactlyTwentyEnergyUsesOneItemBecauseDispatchRequiresMoreThanTwenty() {
        val protocol = FakePreflightProtocol(
            generals = listOf(general(energy = 20))
        )

        val result = SuspendRunner.run {
            ExpeditionPreflight(protocol).check(
                session(),
                request(),
                ExpeditionPreflightPolicy(autoEnergy = true, minimumEnergy = 20)
            )
        }

        assertEquals("EXPEDITION_AUTO_ENERGY_APPLIED", (result as ProtocolResult.Err).code)
        assertEquals(1, protocol.energyCalls)
        assertEquals(0, protocol.refillCalls)
    }

    @Test
    fun refillIsTwoPhaseAndUsesSelectedGenerals() {
        val protocol = FakePreflightProtocol(
            generals = listOf(general(troopLimit = 2_000, troopCount = 1_000)),
            formations = listOf(formation(troopCount = 1_000))
        )
        val result = SuspendRunner.run {
            ExpeditionPreflight(protocol).check(
                session(),
                request().copy(refillToFull = true)
            )
        }

        assertEquals("EXPEDITION_REFILL_APPLIED", (result as ProtocolResult.Err).code)
        assertTrue(result.retryable)
        assertEquals(1, protocol.refillCalls)
        assertEquals(listOf(11L), protocol.lastRefill?.generalIds)
    }

    @Test
    fun dungeonRestoresSavedFormationBeforeDispatch() {
        val protocol = FakePreflightProtocol(
            generals = listOf(general(troopCount = 1_000))
        )
        val savedRule = FormationConfig(
            formationId = 11L,
            generalIds = listOf(11L),
            autoAssignTroops = true,
            troopType = "重步兵",
            troopCount = 500,
            fillToMaxWhenAutoAssignDisabled = false
        )

        val result = SuspendRunner.run {
            ExpeditionPreflight(protocol).check(
                session(),
                request().copy(
                    label = "副本",
                    formationRules = listOf(savedRule)
                )
            )
        }

        assertEquals("EXPEDITION_FORMATION_REPAIR_APPLIED", (result as ProtocolResult.Err).code)
        assertTrue(result.retryable)
        assertEquals(1, protocol.refillCalls)
        assertEquals("重步兵", protocol.lastRefill?.troopType)
        assertEquals(500, protocol.lastRefill?.troopCount)
    }

    @Test
    fun enabledHealingIsTwoPhaseBeforeAnyExpeditionMutation() {
        val protocol = FakePreflightProtocol(healChanged = true)

        val result = SuspendRunner.run {
            ExpeditionPreflight(protocol).check(
                session(),
                request(),
                ExpeditionPreflightPolicy(
                    autoEnergy = false,
                    minimumEnergy = 20,
                    healWounded = true
                )
            )
        }

        assertEquals("EXPEDITION_HEAL_APPLIED", (result as ProtocolResult.Err).code)
        assertTrue(result.retryable)
        assertEquals(1, protocol.healCalls)
        assertEquals(0, protocol.energyCalls)
        assertEquals(0, protocol.refillCalls)
    }

    @Test
    fun desktopPhaseOrderHealsThenAddsEnergyBeforeRepairingFormation() {
        val savedRule = FormationConfig(
            formationId = 11L,
            generalIds = listOf(11L),
            autoAssignTroops = true,
            troopType = "重步兵",
            troopCount = 500,
            fillToMaxWhenAutoAssignDisabled = false
        )

        val healing = FakePreflightProtocol(
            generals = listOf(general(energy = 10, troopCount = 1_000)),
            healChanged = true
        )
        val healResult = SuspendRunner.run {
            ExpeditionPreflight(healing).check(
                session(),
                request().copy(formationRules = listOf(savedRule)),
                ExpeditionPreflightPolicy(autoEnergy = true, minimumEnergy = 20, healWounded = true)
            )
        }
        assertEquals("EXPEDITION_HEAL_APPLIED", (healResult as ProtocolResult.Err).code)
        assertEquals(0, healing.energyCalls)
        assertEquals(0, healing.refillCalls)

        val energy = FakePreflightProtocol(
            generals = listOf(general(energy = 10, troopCount = 1_000))
        )
        val energyResult = SuspendRunner.run {
            ExpeditionPreflight(energy).check(
                session(),
                request().copy(formationRules = listOf(savedRule)),
                ExpeditionPreflightPolicy(autoEnergy = true, minimumEnergy = 20)
            )
        }
        assertEquals("EXPEDITION_AUTO_ENERGY_APPLIED", (energyResult as ProtocolResult.Err).code)
        assertEquals(1, energy.energyCalls)
        assertEquals(0, energy.refillCalls)
    }

    @Test
    fun invalidSessionStopsBeforeReadingArmyState() {
        val protocol = FakePreflightProtocol(sessionValid = false)
        val result = SuspendRunner.run { ExpeditionPreflight(protocol).check(session(), request()) }

        assertEquals("EXPEDITION_SESSION_INVALID", (result as ProtocolResult.Err).code)
        assertEquals(0, protocol.generalQueries)
        assertEquals(0, protocol.formationQueries)
    }

    private fun session() = GameSession(
        accountId = 7L,
        tokenCiphertext = "keystore-managed-login",
        expiresAtMillis = null,
        channelExtra = emptyMap(),
        sourceMode = 1
    )

    private fun request() = ExpeditionPreflightRequest(
        label = "刷黄",
        generalIds = listOf(11L),
        formationId = 11L
    )

    private fun general(
        status: Int? = 0,
        energy: Int? = 100,
        loyalty: Int? = 100,
        troopLimit: Int? = 2_000,
        troopCount: Int = 2_000
    ) = General(
        id = 11L,
        name = "赵云",
        growth = 90,
        loyalty = loyalty,
        energy = energy,
        status = status,
        troopLimit = troopLimit,
        raw = mapOf("soldierTypeCode" to "3", "soldierCount" to troopCount.toString())
    )

    private fun formation(troopCount: Int = 2_000) = FormationRuntime(
        id = 11L,
        name = "赵云编队",
        generalIds = listOf(11L),
        status = FormationRuntimeStatus.IDLE,
        troopCount = troopCount
    )

    private inner class FakePreflightProtocol(
        private val sessionValid: Boolean = true,
        private val generals: List<General> = listOf(general()),
        private val formations: List<FormationRuntime> = listOf(formation()),
        private val healChanged: Boolean = false
    ) : GameProtocolClient by MockGameProtocolClient() {
        var validations = 0
        var generalQueries = 0
        var formationQueries = 0
        var energyCalls = 0
        var healCalls = 0
        var refillCalls = 0
        var lastRefill: FormationConfig? = null

        override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> {
            validations += 1
            return ProtocolResult.Ok(LoginState(sessionValid, if (sessionValid) null else "expired"))
        }

        override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> {
            generalQueries += 1
            return ProtocolResult.Ok(generals)
        }

        override suspend fun queryFormations(session: GameSession): ProtocolResult<List<FormationRuntime>> {
            formationQueries += 1
            return ProtocolResult.Ok(formations)
        }

        override suspend fun addEnergy(session: GameSession, generalId: Long): ProtocolResult<StepResult> {
            energyCalls += 1
            return ProtocolResult.Ok(StepResult(true, "已加体"))
        }

        override suspend fun healGeneral(
            session: GameSession,
            generalId: Long
        ): ProtocolResult<StepResult> {
            healCalls += 1
            return ProtocolResult.Ok(
                StepResult(
                    true,
                    if (healChanged) "已治疗" else "无伤兵",
                    if (healChanged) emptyMap() else mapOf("skipped" to "no-wounded-soldiers")
                )
            )
        }

        override suspend fun updateFormation(
            session: GameSession,
            config: FormationConfig
        ): ProtocolResult<StepResult> {
            refillCalls += 1
            lastRefill = config
            return ProtocolResult.Ok(StepResult(true, "已补兵"))
        }
    }
}

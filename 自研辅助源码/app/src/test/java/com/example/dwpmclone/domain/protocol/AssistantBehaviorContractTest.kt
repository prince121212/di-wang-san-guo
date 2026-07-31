package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

class AssistantBehaviorContractTest {
    @Test
    fun repositoryContractIsLoadedAndMatchesDesktopOpcodes() {
        val file = listOf(
            File("../shared_core/assistant_behavior_contract.json"),
            File("../../shared_core/assistant_behavior_contract.json"),
            File("shared_core/assistant_behavior_contract.json")
        ).firstOrNull(File::exists)
            ?: error("shared_core/assistant_behavior_contract.json is missing")
        val contract = AssistantBehaviorContract.fromJson(file.readText())
        assertEquals(0x6202, contract.signIn.requestOpcode)
        assertEquals(0x8134, contract.signIn.activityResponseOpcode)
        assertEquals(0xE202, contract.signIn.legacyResponseOpcode)
        assertEquals("Asia/Shanghai", contract.timezoneId)
        assertEquals(60_000L, contract.dailySchedule.failedFeatureRetryMillis)
        assertEquals("nextChinaDay", contract.dailySchedule.completedFeatureSleep)
        assertTrue(contract.dailyFeaturesAreIndependent)
        assertTrue(contract.oneDailyFailureMustNotBlockSiblings)
        assertTrue(contract.accountLifecycle.startedRequiresExecutionOwner)
        assertTrue(contract.accountLifecycle.startRunsFreshLogin)
        assertEquals(20_000L, contract.accountLifecycle.heartbeatIntervalMillis)
        assertEquals("开启", contract.accountLifecycle.statusText["online"])
        assertEquals("检测中", contract.accountLifecycle.statusText["checking"])
        assertEquals("掉线", contract.accountLifecycle.statusText["offline"])
        assertEquals("未开启", contract.accountLifecycle.statusText["stopped"])
        assertEquals(
            listOf("mine", "lossless", "brushYellow", "raid", "dungeon", "ministry"),
            contract.scheduler.residentPriority.entries
                .sortedByDescending { it.value }
                .map { it.key }
        )
        assertTrue(contract.scheduler.sameGeneralMutualExclusionRequired)
        assertTrue(contract.scheduler.onlyRunnableResidentBlocksLowerPriority)
        assertFalse(contract.scheduler.formationPrerequisiteRunsFirst)
        assertFalse(contract.scheduler.dailyFeaturesRunBeforeResidents)
        assertTrue(contract.scheduler.militaryLaneRunsBeforeIdleLane)
        assertTrue(contract.scheduler.expeditionPreparationIsTaskScoped)
        assertTrue(contract.scheduler.idleLaneMustYieldToDueMilitaryWork)
        assertTrue(contract.scheduler.observationRefreshMayRunBetweenLanes)
        assertTrue(contract.scheduler.waitStatePersistsAcrossProcess)
        assertTrue(contract.scheduler.dayBoundaryUsesContractTimezone)
        assertEquals(0x6260, contract.dailyActions.arenaCoins.readRequestOpcode)
        assertEquals(0x6266, contract.dailyActions.arenaCoins.claimRequestOpcode)
        assertEquals(0xE266, contract.dailyActions.arenaCoins.claimResponseOpcode)
        assertEquals(0x140C, contract.dailyActions.donate.resourceRequestOpcode)
        assertEquals(0x840C, contract.dailyActions.donate.resourceResponseOpcode)
        assertEquals(0x140A, contract.dailyActions.donate.technologyRequestOpcode)
        assertEquals(0x840A, contract.dailyActions.donate.technologyResponseOpcode)
        assertEquals(1_000, contract.dailyActions.donate.copperPerLevel)
        assertEquals(3_000, contract.dailyActions.donate.foodPerLevel)
        assertEquals(0x314B, contract.dailyActions.salary.requestOpcode)
        assertEquals(0xA14B, contract.dailyActions.salary.responseOpcode)
        assertEquals("01", contract.dailyActions.salary.payload.toHex())
        assertEquals(0x1404, contract.dailyActions.nationalCollect.cityListRequestOpcode)
        assertEquals(0x8404, contract.dailyActions.nationalCollect.cityListResponseOpcode)
        assertEquals(7, contract.dailyActions.nationalCollect.responseHeaderBytes)
        assertEquals(listOf(1, 2, 3), contract.dailyActions.nationalCollect.includedListCategories)
        assertEquals(0x1318, contract.dailyActions.cityLordCollect.ownedCityRequestOpcode)
        assertEquals(0x8318, contract.dailyActions.cityLordCollect.ownedCityResponseOpcode)
        assertEquals("0000", contract.dailyActions.cityLordCollect.ownedCityPayloadSuffix.toHex())
        assertEquals(0x3271, contract.dailyActions.generalVisit.listRequestOpcode)
        assertEquals(0xA271, contract.dailyActions.generalVisit.listResponseOpcode)
        assertEquals(0x3273, contract.dailyActions.generalVisit.visitRequestOpcode)
        assertEquals(0xA273, contract.dailyActions.generalVisit.visitResponseOpcode)
        assertEquals(-2, contract.dailyActions.generalVisit.alreadyVisitedStatus)
        assertTrue("拒绝了阁下的邀请" in contract.dailyActions.generalVisit.invitationResolvedMarkers)
        assertEquals(0x1520, contract.expedition.prepareOpcode)
        assertEquals(0x8520, contract.expedition.prepareResponseOpcode)
        assertEquals(0x1522, contract.expedition.dispatchOpcode)
        assertEquals(0x8522, contract.expedition.dispatchResponseOpcode)
        assertTrue(contract.expedition.dispatchSuccessRequiresPositiveBattleId)
        assertEquals("ff0000", contract.expedition.softRejectPayload.toHex())
        assertEquals(0x1226, contract.formation.assignRequestOpcode)
        assertEquals(0x8226, contract.formation.assignResponseOpcode)
        assertEquals(0x1229, contract.formation.refillRequestOpcode)
        assertEquals(0x8229, contract.formation.refillResponseOpcode)
        assertTrue(contract.formation.clampCountToTroopLimit)
        assertTrue(contract.formation.precheckIdleSoldierInventory)
        assertTrue(contract.formation.exactAssignedTypeAndCountRequired)
        assertTrue(contract.formation.clearOtherGeneralsSkipsBusy)
        assertTrue(contract.formation.assignmentDoesNotImplicitlyRefill)
        assertEquals(31_536_000_000L, contract.formation.completedSleepMillis)
        assertEquals(0x1540, contract.mapSearch.banditRequestOpcode)
        assertEquals(0x8540, contract.mapSearch.banditResponseOpcode)
        assertEquals(0, contract.mapSearch.world.xMin)
        assertEquals(186, contract.mapSearch.world.xMax)
        assertEquals(0, contract.mapSearch.world.yMin)
        assertEquals(66, contract.mapSearch.world.yMax)
        assertEquals(6, contract.mapSearch.world.step)
        assertEquals(80, contract.mapSearch.nearbyRequestLimit)
        assertEquals(384, contract.mapSearch.fullRequestLimit)
        assertEquals(120_000L, contract.mapSearch.scanCoordinateCacheTtlMillis)
        assertEquals(1_800_000L, contract.mapSearch.targetCacheTtlMillis)
        assertEquals(30, contract.brushYellow.minimumRoleLevel)
        assertEquals(5, contract.brushYellow.maximumGeneralsPerFormation)
        assertEquals(3, contract.brushYellow.actionType)
        assertTrue(contract.brushYellow.exactSelectedLevelsRequired)
        assertEquals(10_000L, contract.brushYellow.schedule.transientRetryMillis)
        assertEquals(30_000L, contract.brushYellow.schedule.postDispatchPollMillis)
        assertEquals(0x1520, contract.mine.prepareOpcode)
        assertEquals(0x8520, contract.mine.prepareResponseOpcode)
        assertEquals(0x1522, contract.mine.dispatchOpcode)
        assertEquals(0x8522, contract.mine.dispatchResponseOpcode)
        assertTrue(contract.mine.dispatchSuccessRequiresPositiveBattleId)
        assertEquals(0x1526, contract.mine.withdraw.requestOpcode)
        assertEquals(0x8526, contract.mine.withdraw.responseOpcode)
        assertEquals("0101", contract.mine.withdraw.payloadPrefix.toHex())
        assertEquals("00", contract.mine.withdraw.payloadSuffix.toHex())
        assertTrue(contract.mine.withdraw.requireExactBattleIdMatch)
        assertEquals(0x1310, contract.raid.fiefQueryOpcode)
        assertEquals(0x8310, contract.raid.fiefQueryResponseOpcode)
        assertEquals("0001", contract.raid.targetPayloadPrefix.toHex())
        assertEquals(0x1600, contract.militarySnapshot.requestOpcode)
        assertEquals(0x8600, contract.militarySnapshot.responseOpcode)
        assertEquals("07000000000000000000000014", contract.militarySnapshot.requestPayload.toHex())
        assertEquals(11, contract.lossless.actionType)
        assertEquals(5, contract.lossless.serverDailyLimit)
        assertEquals(0x1900, contract.lossless.statusRequestOpcode)
        assertEquals(0x8900, contract.lossless.statusResponseOpcode)
        assertEquals(0x1520, contract.lossless.prepareOpcode)
        assertEquals(0x8520, contract.lossless.prepareResponseOpcode)
        assertEquals(0x1522, contract.lossless.dispatchOpcode)
        assertEquals(0x8522, contract.lossless.dispatchResponseOpcode)
        assertFalse(contract.lossless.fullTroopsDefault)
        assertTrue(contract.lossless.level10Guard.lastChariotMustBeCatapult)
        assertEquals(14, contract.dungeon.actionType)
        assertEquals(listOf("loop", "clear"), contract.dungeon.allowedModes)
        assertEquals(0x1930, contract.dungeon.catalogRequestOpcode)
        assertEquals(0x8930, contract.dungeon.catalogResponseOpcode)
        assertEquals(0x193E, contract.dungeon.chestRequestOpcode)
        assertEquals(0x893E, contract.dungeon.chestResponseOpcode)
        assertTrue(contract.dungeon.clearModeSkipsMultiplayerFinals)
        assertTrue(contract.dungeon.clearModeRequiresCatalogConfirmation)
        assertTrue(contract.dungeon.clearModePausesOnDefeat)
    }

    @Test
    fun live8134FreshAndDuplicateReceiptsBothComplete() {
        val contract = AssistantBehaviorContract.defaults().signIn
        val freshPayload = utfPayload("铜钱:10000获得成功。粮食:30000获得成功。")
        val fresh = DailySignInReceiptParser.parse(
            listOf(contract.activityResponseOpcode),
            freshPayload,
            contract
        )
        val duplicate = DailySignInReceiptParser.parse(
            listOf(contract.activityResponseOpcode),
            utfPayload("本日已签到"),
            contract
        )

        assertTrue(fresh.success)
        assertFalse(fresh.alreadyClaimed)
        assertEquals("铜钱:10000获得成功；粮食:30000获得成功", fresh.message)
        assertTrue(duplicate.success)
        assertTrue(duplicate.alreadyClaimed)
        assertTrue(duplicate.duplicateClaim)
        assertEquals(contract.duplicateMessage, duplicate.message)
    }

    @Test
    fun legacyE202EmptyReceiptCompletes() {
        val receipt = DailySignInReceiptParser.parse(
            listOf(0xE202),
            ByteArray(0),
            AssistantBehaviorContract.defaults().signIn
        )
        assertTrue(receipt.success)
        assertEquals("签到请求已由服务器确认", receipt.message)
    }

    @Test
    fun expiredDiamondBoxIsIdempotentSuccess() {
        val contract = AssistantBehaviorContract.defaults().signIn
        val receipt = DailySignInReceiptParser.parseDiamondBox(
            utfPayload("操作失败，活动已过期。"),
            contract
        )
        assertTrue(receipt.success)
        assertTrue(receipt.alreadyClaimed)
        assertEquals("每日金钻宝箱已经领取过了！", receipt.message)
    }

    private fun utfPayload(message: String): ByteArray =
        ByteArrayOutputStream().also { output ->
            DataOutputStream(output).use { data ->
                data.writeShort(0)
                data.writeShort(message.toByteArray(Charsets.UTF_8).size)
                data.write(message.toByteArray(Charsets.UTF_8))
            }
        }.toByteArray()

    private fun ByteArray.toHex(): String =
        joinToString("") { "%02x".format(it.toInt() and 0xff) }
}

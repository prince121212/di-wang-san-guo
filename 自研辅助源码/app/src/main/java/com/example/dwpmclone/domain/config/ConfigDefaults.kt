package com.example.dwpmclone.domain.config

import com.example.dwpmclone.domain.model.*

/** Defaults reconstructed from layout text/default values. */
object ConfigDefaults {
    val zeroCoordinate = MapCoordinate(0, 0)

    fun guaji(accountId: Long) = GuajiConfig(
        accountId = accountId,
        autoStart = false,
        reconnectDelaySeconds = 10,
        antiIpBanEnabled = false,
        requestDelayMillis = 100,
        sameServerMutex = true,
        protectBackgroundHintAcknowledged = false
    )

    fun shuaHuang() = ShuaHuangConfig(
        enabled = false,
        dailyLimit = 500,
        start = zeroCoordinate,
        minCopperWan = 0,
        targetType = HuangTargetType.SHAN_ZEI,
        selectedFormationIds = emptySet(),
        formationFilterMode = FormationFilterMode.UNIFIED,
        replenishTroops = true,
        deleteMailForSpeed = false,
        autoConvertFoodToCopper = true
    )

    fun mine() = MineConfig(
        enabled = false,
        start = zeroCoordinate,
        hitEmptyMine = true,
        withdrawDefense = true,
        resourcePointLimit = 0,
        selectedMineTypes = setOf(MineType.GOLD),
        acceleratedMineTypes = emptySet(),
        selectedFormationIds = emptySet(),
        backgroundSearch = false,
        searchIntervalMinutes = 12,
        reloginOnDisconnect = false,
        stopOnDisconnect = false,
        vibrateOnEmptyGold = false,
        vibrateOnEmptyRare = false,
        onlyEmptyMine = false,
        onlyDefendedMine = false
    )

    fun daily() = DailyConfig(
        enabledSteps = setOf(DailyStep.SIGN_IN, DailyStep.SURPRISE_BOX),
        vibrateOnAlarm = false,
        stopOnStepFailure = false
    )

    fun general() = GeneralConfig(
        autoHeal = true,
        keepFullLoyalty = false,
        autoEnergy = true,
        minEnergy = 50,
        autoRescue = true,
        requireChineseNamePrefix = true
    )

    fun formation(formationId: Long = 0L) = FormationConfig(
        formationId = formationId,
        generalIds = emptyList(),
        autoAssignTroops = false,
        troopType = "",
        troopCount = 1999,
        fillToMaxWhenAutoAssignDisabled = true
    )

    fun internalAffairs() = InternalAffairsConfig(
        enabled = false,
        upgradeLowestFirst = true,
        buildingPriority = emptyList(),
        buildWhenEmpty = null,
        upgradeTechnology = false,
        technologyIds = setOf(5)
    )

    fun sixMinistries() = SixMinistriesConfig(
        cropEnabled = false,
        crop = MinistryProtocolCrop.VERIFIED_NAME,
        highPriority = true,
        stealEnabled = false,
        courtesyEnabled = false,
        salaryRefresh = false
    )

    fun dungeon() = DungeonConfig(
        enabled = false,
        dailyTimes = 999,
        boxPosition = 0,
        chapter = 0,
        stage = 1,
        formationIds = emptyList(),
        autoUnlockUntilTarget = true
    )

    fun inventory() = InventoryConfig(
        enabled = false,
        openBoxes = false,
        openSilverTickets = false,
        discardEquipmentQualities = emptySet(),
        discardBelowLevel = 0,
        neverDiscardEnhancedOrEquipped = true,
        discardItems = emptySet()
    )

    fun surrenderRelease() = SurrenderReleaseConfig(
        autoSurrender = false,
        surrenderGrowthAbove = 80,
        useGoldForSurrender = false,
        autoRelease = false,
        releaseGrowthBelow = 45
    )

    fun vip() = VipFeatureConfig(
        enabled = false,
        showVip = false,
        autoEnergy = false,
        autoDonate = false,
        autoInternalAffairs = false,
        autoTechnology = false,
        autoRescueSoldiers = false,
        timedAddLoyalty = false,
        autoSurrender = false,
        autoRescueGeneral = false
    )

    fun resourcePointSendGeneral() = ResourcePointSendGeneralConfig(
        enabled = false,
        target = zeroCoordinate,
        generalId = 0L,
        troopType = "",
        formationId = 0L,
        stopAfterMinutes = 0,
        requiresKeepFullLoyaltyOff = true
    )

    fun autoLoot() = AutoLootConfig(
        enabled = false,
        selectedFormationIds = emptySet(),
        targetKeyword = null,
        requireSecondConfirmForRealRun = true,
        fullTroops = true,
        fullLoyalty = false,
        rules = emptyList()
    )

    fun alarmWithdraw() = AlarmWithdrawConfig(
        enabled = false,
        keywords = setOf("掠夺", "夺取", "攻城", "敌军"),
        vibrateOnAlarm = true,
        withdrawDefense = false,
        mockOnlyProtection = true
    )

    val discardableItemNames: Set<String> = setOf(
        "青铜宝箱", "精铁宝箱", "传音符", "青铜钥匙", "山贼头巾", "火药桶", "屯田令", "通商令", "令牌",
        "镔铁", "浆果", "水晶", "灵草", "高级通商令", "高级屯田令", "战鼓", "八卦图", "小还丹", "活血丹",
        "重置丹", "神农符", "财神符", "鲁公手册", "鲁公图册", "鲁公古籍"
    )
}

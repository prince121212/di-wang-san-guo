package com.example.dwpmclone.ui.assistant

import com.example.dwpmclone.data.local.LocalRoleState
import com.example.dwpmclone.domain.model.Channel
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.GameVersion
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantRealtimeAccountDisplayMapperTest {
    @Test
    fun noRealSessionShowsEmptyStateAndNoRoleRows() {
        val staleState = localState(roleName = "旧角色", source = "本地模板")

        val display = AssistantRealtimeAccountDisplayMapper.build(emptyList(), staleState)

        assertFalse(display.hasRealtimeAccount)
        assertEquals(AssistantRealtimeAccountDisplayMapper.EMPTY_ACCOUNT_LABEL, display.pickerLabel)
        assertEquals("账号：暂无真实协议登录返回。", display.accountSummary)
        assertTrue(display.roleRows.isEmpty())
        assertTrue(display.heroRows.isEmpty())
        assertTrue(display.armyRows.isEmpty())
        assertNull(display.realAccount)
    }

    @Test
    fun mockSessionIsNotDisplayedAsAccountData() {
        val mockAccount = account(
            sourceMode = 0,
            extra = mapOf("roleName" to "Mock君主", "level" to "99", "copper" to "123456")
        )

        val display = AssistantRealtimeAccountDisplayMapper.build(
            listOf(mockAccount),
            localState(roleName = "Mock君主", source = "真实协议 0x1016")
        )

        assertFalse(display.hasRealtimeAccount)
        assertEquals(AssistantRealtimeAccountDisplayMapper.EMPTY_ACCOUNT_LABEL, display.pickerLabel)
        assertTrue(display.roleRows.isEmpty())
        assertFalse(display.accountSummary.contains("Mock君主"))
    }

    @Test
    fun realSessionDisplaysOnlyProtocolSyncedFields() {
        val realAccount = account(
            id = 77L,
            username = "real-user",
            serverName = "S1",
            sourceMode = 1,
            extra = mapOf(
                "roleName" to "接口君主",
                "level" to "42",
                "copper" to "321000",
                "copperPerHour" to "31",
                "food" to "654000",
                "foodPerHour" to "62",
                "populationCurrent" to "123",
                "populationCap" to "456",
                "resourcePointCurrent" to "6",
                "resourcePointCap" to "9",
                "treasureOccupied" to "2",
                "treasureLimit" to "5",
                "shuaHuangUsedCount" to "12",
                "dungeonCount" to "3",
                "fiefLimit" to "8",
                "generalLimit" to "20",
                "syncedAt" to "2026-07-08T02:00:00+08:00",
                "generalsJson" to """[{"id":7,"name":"接口将领","status":"空闲","tili":49,"tiliLimit":100,"zhongChengdu":88,"tongshuai":99,"daiBingLimit":1999,"troopType":"兵种10"}]""",
                "formationsJson" to """[{"id":3,"name":"接口编队","generalIds":[7],"status":"IDLE","troopCount":1999}]"""
            )
        )
        val state = localState(
            roleName = "接口君主",
            level = "42",
            copper = "321000（+31/小时）",
            food = "654000（+62/小时）",
            population = "123 / 456",
            resourcePoint = "6 / 9",
            source = "真实协议 0x1016",
            syncedAt = "2026-07-08T02:00:00+08:00"
        )

        val display = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), state)

        assertTrue(display.hasRealtimeAccount)
        assertEquals("real-user@S1 · 接口君主 · Lv.42", display.pickerLabel)
        assertTrue(display.accountSummary.contains("接口君主"))
        assertEquals("real-user", display.roleRows.first { it.first == "账号" }.second)
        assertEquals("S1", display.roleRows.first { it.first == "服务器" }.second)
        assertEquals("321000（+31/小时）", display.roleRows.first { it.first == "铜钱" }.second)
        assertEquals("123 / 456", display.roleRows.first { it.first == "人口" }.second)
        assertEquals("2 / 5", display.roleRows.first { it.first == "宝藏" }.second)
        assertEquals("12", display.roleRows.first { it.first == "刷黄次数" }.second)
        assertEquals("3", display.roleRows.first { it.first == "副本次数" }.second)
        assertEquals("8", display.roleRows.first { it.first == "封地上限" }.second)
        assertEquals("20", display.roleRows.first { it.first == "将领上限" }.second)
        assertEquals(listOf("接口将领", "闲", "—", "—", "—", "49 / 100", "88", "— / 1999", "重骑兵"), display.heroRows.single())
        assertEquals(listOf("接口编队", "7", "IDLE", "1999"), display.formationRows.single())
        assertFalse(display.troopRowsDerivedFromGenerals)
    }

    @Test
    fun staleLocalStateForDifferentRoleIsIgnoredAndSessionExtraIsUsed() {
        val realAccount = account(
            sourceMode = 1,
            displayName = "接口君主",
            monarchName = "接口君主",
            extra = mapOf("roleName" to "接口君主", "level" to "12", "food" to "900")
        )
        val staleState = localState(roleName = "另一个旧角色", level = "99", food = "111", source = "真实协议 0x1016")

        val display = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), staleState)

        assertTrue(display.hasRealtimeAccount)
        assertEquals("接口君主", display.roleRows.first { it.first == "君主" }.second)
        assertEquals("12", display.roleRows.first { it.first == "等级" }.second)
        assertEquals("900", display.roleRows.first { it.first == "粮食" }.second)
        assertFalse(display.roleRows.any { it.second == "另一个旧角色" || it.second == "99" || it.second == "111" })
    }

    @Test
    fun sessionExtraWinsOverOlderMatchingLocalRoleState() {
        val realAccount = account(
            sourceMode = 1,
            displayName = "董全",
            monarchName = "董全",
            extra = mapOf(
                "roleName" to "董全",
                "level" to "12",
                "copper" to "19659",
                "copperPerHour" to "1315",
                "food" to "46844",
                "foodPerHour" to "1160",
                "prestige" to "4943",
                "populationCurrent" to "672",
                "populationCap" to "515",
                "syncedAt" to "2026-07-08 06:40:50",
                "sourceOpcode" to "refresh/0x1016/0x8004"
            )
        )
        val staleState = localState(
            roleName = "董全",
            level = "7",
            copper = "51134（+1320/小时）",
            food = "71118（+1160/小时）",
            population = "200 / 515",
            source = "真实协议 0x1016/0x8004",
            syncedAt = "2026-07-08 05:06:54"
        )

        val display = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), staleState)

        assertEquals("u@s · 董全 · Lv.12", display.pickerLabel)
        assertEquals("12", display.roleRows.first { it.first == "等级" }.second)
        assertEquals("19659（+1315/小时）", display.roleRows.first { it.first == "铜钱" }.second)
        assertEquals("4943", display.roleRows.first { it.first == "声望" }.second)
        assertEquals("672 / 515", display.roleRows.first { it.first == "人口" }.second)
        assertEquals("2026-07-08 06:40:50", display.syncedAt)
    }

    @Test
    fun cachedBinaryJiangLingRowsUseRankTierAsLevelInsteadOfGrowth() {
        val realAccount = account(
            sourceMode = 1,
            extra = mapOf(
                "roleName" to "接口君主",
                "level" to "42",
                "generalsJson" to """[{"id":7066187,"name":"何颜鸥","source":"state8004-binary-jiangling","level":69,"rank":69,"rankTier":1,"tili":99,"tiliLimit":100,"zhongChengdu":84,"troopCount":2569,"troopType":"兵种10","bodyHeadHex":"0000000102da004501000000000000000f003f0054004c003f00540063006400000000000000c630640005005400"}]"""
            )
        )

        val display = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), null)

        assertEquals("1", display.heroRows.single()[4])
        assertEquals("99 / 100", display.heroRows.single()[5])
        assertEquals("48 / 100", display.heroRows.single()[6])
        assertEquals("— / 198", display.heroRows.single()[7])
        assertEquals("—", display.heroRows.single()[8])
    }

    @Test
    fun missingFormationsFallsBackToConfirmedGeneralTroopRows() {
        val realAccount = account(
            sourceMode = 1,
            extra = mapOf(
                "roleName" to "接口君主",
                "generalsJson" to """[{"id":12886833,"name":"骑1","source":"state8004-binary-jiangling","status":0,"statusText":"空闲","category":"骑将","level":5,"tili":120,"tiliLimit":120,"loyalty":60,"loyaltyLimit":100,"troopCount":21,"daiBingLimit":296,"troopTypeCode":3,"troopTypeName":"轻骑兵","troopTypeSource":"Lo/a.S5.Pm","troopCountSource":"Lo/a.S5.Qm"}]"""
            )
        )

        val display = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), null)

        assertTrue(display.troopRowsDerivedFromGenerals)
        assertEquals(listOf("骑1", "闲", "21 / 296", "轻骑兵"), display.formationRows.single())
    }

    @Test
    fun heroRowsMatchDesktopFiefColumnAndCompactStatusLabels() {
        val realAccount = account(
            sourceMode = 1,
            extra = mapOf(
                "roleName" to "接口君主",
                "generalsJson" to """[
                    {"id":7,"name":"甲将","statusText":"驻防","fiefName":"洛阳一号封地","level":9},
                    {"id":8,"name":"乙将","status":4,"placeID":9988,"level":8}
                ]"""
            )
        )

        val rows = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), null).heroRows

        assertEquals(9, rows[0].size)
        assertEquals(listOf("甲将", "防", "洛阳一号封地"), rows[0].take(3))
        assertEquals(listOf("乙将", "返", "封地#9988"), rows[1].take(3))
    }

    @Test
    fun inventoryRowsShowRealItemNameCountAndId() {
        val realAccount = account(
            sourceMode = 1,
            extra = mapOf(
                "roleName" to "接口君主",
                "inventoryJson" to """[{"itemId":9,"name":"传音符","count":5,"source":"0x1104/0x8104"}]"""
            )
        )

        val display = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), null)

        assertEquals(listOf("传音符", "5", "9"), display.treasureRows.single())
    }

    @Test
    fun armyRowsMatchDesktopIdleWoundedAndFiefColumns() {
        val realAccount = account(
            sourceMode = 1,
            extra = mapOf(
                "roleName" to "接口君主",
                "armyJson" to """[
                    {"soldierTypeCode":10,"idleCount":735,"woundedCount":12,"fiefName":"董全基地"},
                    {"soldierType":"弩车","amount":44,"hurtSoldierCount":3,"fiefId":8}
                ]"""
            )
        )

        val display = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), null)

        assertEquals(listOf("重骑兵", "735", "12", "董全基地"), display.armyRows[0])
        assertEquals(listOf("弩车", "44", "3", "封地8"), display.armyRows[1])
    }

    @Test
    fun statusRowsDoNotMixFiefCityAndPolicyEvidenceIntoComputerStatusList() {
        val realAccount = account(
            sourceMode = 1,
            extra = mapOf(
                "roleName" to "接口君主",
                "statusJson" to """[
                    {"name":"基地/封地","detail":"董全基地","kind":"fiefName"},
                    {"name":"城池","detail":"建业","kind":"cityName"},
                    {"name":"神农","effect":"降低20%伤兵治疗费用","kind":"policyBuff"}
                ]"""
            )
        )

        val display = AssistantRealtimeAccountDisplayMapper.build(listOf(realAccount), null)

        assertEquals(11, display.statusRows.size)
        assertEquals(listOf("休战", "0分钟"), display.statusRows.first())
        assertFalse(display.statusRows.any { it.first() in setOf("基地/封地", "城池", "神农") })
    }

    private fun account(
        id: Long = 1L,
        username: String = "u",
        serverName: String = "s",
        displayName: String? = null,
        monarchName: String? = displayName,
        sourceMode: Int,
        extra: Map<String, String> = emptyMap()
    ): GameAccount = GameAccount(
        id = id,
        displayName = displayName,
        username = username,
        encryptedPassword = null,
        serverName = serverName,
        serverId = "srv",
        gameVersion = GameVersion.TENCENT_CLASSIC,
        channel = Channel.QQ,
        session = GameSession(id, "token", null, extra, sourceMode),
        enabled = true,
        monarchName = monarchName,
        nation = extra["nation"],
        loginState = if (sourceMode == 1) "REAL_PROTOCOL_LOGIN_OK" else "MOCK"
    )

    private fun localState(
        roleName: String,
        level: String = "1",
        copper: String = "",
        food: String = "",
        population: String = "",
        resourcePoint: String = "",
        source: String,
        syncedAt: String = ""
    ): LocalRoleState = LocalRoleState(
        roleName = roleName,
        remark = "接口备注",
        level = level,
        exp = "声望 0 / 0",
        nation = "接口国家",
        copper = copper,
        food = food,
        population = population,
        resourcePoint = resourcePoint,
        generals = "",
        troops = "",
        treasures = "",
        buffs = "待继续解析 0x8004 后段",
        source = source,
        syncedAt = syncedAt
    )
}

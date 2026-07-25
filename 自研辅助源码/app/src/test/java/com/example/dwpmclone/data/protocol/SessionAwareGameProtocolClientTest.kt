package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.model.DailyStep
import com.example.dwpmclone.domain.model.AlarmWithdrawConfig
import com.example.dwpmclone.domain.model.AutoLootConfig
import com.example.dwpmclone.domain.model.BuildingType
import com.example.dwpmclone.domain.model.BulkToolAction
import com.example.dwpmclone.domain.model.CityDefenseSearchConfig
import com.example.dwpmclone.domain.model.DungeonConfig
import com.example.dwpmclone.domain.model.FormationRuntimeStatus
import com.example.dwpmclone.domain.model.FormationConfig
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.InternalAffairsConfig
import com.example.dwpmclone.domain.model.LosslessConfig
import com.example.dwpmclone.domain.model.LosslessRule
import com.example.dwpmclone.domain.model.MineConfig
import com.example.dwpmclone.domain.model.MineType
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.ResourcePointSendGeneralConfig
import com.example.dwpmclone.domain.model.SurrenderReleaseConfig
import com.example.dwpmclone.domain.model.SixMinistriesConfig
import com.example.dwpmclone.domain.model.TreasureFilterConfig
import com.example.dwpmclone.domain.model.TreasureKind
import com.example.dwpmclone.domain.model.VipFeatureConfig
import com.example.dwpmclone.domain.protocol.GameCoordinateCodec
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.protocol.MineSearchResult
import com.example.dwpmclone.domain.protocol.RemainingAutomationProtocolShapes
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.protocol.ConvertMode
import com.example.dwpmclone.domain.protocol.InventoryAction
import com.example.dwpmclone.domain.protocol.MapSearchPolicy
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.scheduler.SuspendRunner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

class SessionAwareGameProtocolClientTest {
    private val client = SessionAwareGameProtocolClient()

    @Test
    fun realMinistryPlantingFailsClosedBeforeAnyNetworkWhenGateIsMissing() {
        val result = SuspendRunner.run {
            client.runSixMinistries(
                realSession(),
                SixMinistriesConfig(
                    cropEnabled = true,
                    crop = "金银花",
                    highPriority = true,
                    stealEnabled = false,
                    courtesyEnabled = false,
                    salaryRefresh = false
                )
            )
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_MINISTRY_GATE_NOT_READY", (result as ProtocolResult.Err).code)
        assertFalse(result.retryable)
    }

    @Test
    fun realMinistryStealScanFailsClosedBeforeNetworkWhenReadGateIsMissing() {
        val result = SuspendRunner.run {
            client.runSixMinistries(
                realSession(),
                SixMinistriesConfig(
                    cropEnabled = false,
                    crop = "金银花",
                    highPriority = true,
                    stealEnabled = true,
                    courtesyEnabled = false,
                    salaryRefresh = false
                )
            )
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals(
            "REAL_MINISTRY_STEAL_SCAN_GATE_NOT_READY",
            (result as ProtocolResult.Err).code
        )
        assertFalse(result.retryable)
    }

    @Test
    fun realDungeonUsesLiveCatalogBeforeLaunchingAndAcceptsCaptured8522SuccessText() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1938 to listOf(0x8938 to "00"),
                0x1930 to listOf(0x8930 to CAPTURED_DUNGEON_CATALOG),
                0x1520 to listOf(0x8520 to "00"),
                0x1522 to listOf(
                    0x8522 to "d8001be58d95e4babae589afe69cace590afe58aa8e68890e58a9fefbc81"
                )
            )
        )
        val dungeonClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)

        val result = SuspendRunner.run {
            dungeonClient.runDungeon(dungeonSession(status = 0), dungeonConfig())
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("fighting", step.raw["phase"])
        assertEquals("5", step.raw["stageCode"])
        assertEquals(listOf(0x1938, 0x1930, 0x1520, 0x1522), transport.opcodes)
    }

    @Test
    fun realDungeonActiveBattlePolls1702WithCapturedBattleId() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1938 to listOf(0x8938 to "010000000000038f4c00"),
                0x1702 to listOf(0x8702 to "000100030100000000002af8")
            )
        )
        val dungeonClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)

        val result = SuspendRunner.run {
            dungeonClient.runDungeon(dungeonSession(status = 3), dungeonConfig())
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertEquals("fighting", step.raw["phase"])
        assertEquals("2", step.raw["pollPhase"])
        assertEquals(listOf(0x1938, 0x1702), transport.opcodes)
        assertTrue(transport.gameHexes.last().endsWith("020000000000038f4c"))
    }

    @Test
    fun realDungeonOnlyOpensChestAfterIdleGeneralsAndMatchingRewardBattle() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1938 to listOf(0x8938 to "010000000000038f4c00"),
                0x193d to listOf(0x893d to "010000000000038f4c00000500000022"),
                0x193e to listOf(0x893e to "00")
            )
        )
        val dungeonClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)

        val result = SuspendRunner.run {
            dungeonClient.runDungeon(dungeonSession(status = 0), dungeonConfig())
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertEquals("chest-opened", step.raw["phase"])
        assertEquals("generals-idle+0x893d", step.raw["completionEvidence"])
        assertEquals(listOf(0x1938, 0x193d, 0x193e), transport.opcodes)
    }

    @Test
    fun realSessionExposesReadOnlyMonarchAndResourceMetadata() {
        val session = realSession()

        val valid = SuspendRunner.run { client.validateSession(session) }
        val monarch = SuspendRunner.run { client.queryMonarch(session) }
        val resources = SuspendRunner.run { client.queryResourceState(session) }

        assertTrue((valid as ProtocolResult.Ok).value.valid)
        assertEquals("测试君主", (monarch as ProtocolResult.Ok).value.name)
        assertEquals(42, monarch.value.level)
        assertEquals("蜀", monarch.value.nation)
        assertEquals(123456L, (resources as ProtocolResult.Ok).value.copper)
        assertEquals(654321L, resources.value.food)
    }


    @Test
    fun realSessionCanReadNestedRoleAndResourceStateJson() {
        val session = realSession(
            extras = mapOf(
                "roleName" to "",
                "level" to "",
                "copper" to "",
                "food" to "",
                "roleStateJson" to """{
                    "roleId":10001,
                    "roleName":"嵌套君主",
                    "level":55,
                    "nation":"魏",
                    "title":"大将军",
                    "prestige":98765,
                    "populationCurrent":333,
                    "populationCap":999,
                    "resourcePointCurrent":4,
                    "resourcePointCap":8
                }""",
                "resourceStateJson" to """{
                    "copper":777,
                    "food":888,
                    "prestige":98765,
                    "copperPerHour":11,
                    "foodPerHour":22,
                    "populationCurrent":333,
                    "populationCap":999,
                    "resourcePointCurrent":4,
                    "resourcePointCap":8
                }"""
            )
        )

        val monarch = SuspendRunner.run { client.queryMonarch(session) }
        val resources = SuspendRunner.run { client.queryResourceState(session) }

        assertTrue(monarch is ProtocolResult.Ok)
        val profile = (monarch as ProtocolResult.Ok).value
        assertEquals("嵌套君主", profile.name)
        assertEquals(55, profile.level)
        assertEquals("魏", profile.nation)
        assertEquals(10001L, profile.roleId)
        assertEquals("大将军", profile.title)
        assertEquals(98765L, profile.prestige)
        assertEquals(4, profile.resourcePointCurrent)
        assertTrue(resources is ProtocolResult.Ok)
        val resource = (resources as ProtocolResult.Ok).value
        assertEquals(777L, resource.copper)
        assertEquals(888L, resource.food)
        assertEquals(11, resource.copperPerHour)
        assertEquals(22, resource.foodPerHour)
        assertEquals(333L, resource.populationCurrent)
        assertEquals(8, resource.resourcePointCap)
    }

    @Test
    fun realSessionCanReadRoleAndResourceFromPersisted8004TextEvidence() {
        val session = realSession(
            extras = mapOf(
                "roleName" to "",
                "level" to "",
                "copper" to "",
                "food" to "",
                "state8004TailUtf8Preview" to "君主名=证据君主|君主等级=47|国家=吴国|官职=太守|" +
                    "铜钱=321000|粮食=654000|声望=9876|铜钱产量=31|粮食产量=62|" +
                    "人口=123|人口上限=456|资源点占用=6|资源点上限=9"
            )
        )

        val monarch = SuspendRunner.run { client.queryMonarch(session) }
        val resources = SuspendRunner.run { client.queryResourceState(session) }

        assertTrue(monarch is ProtocolResult.Ok)
        val profile = (monarch as ProtocolResult.Ok).value
        assertEquals("证据君主", profile.name)
        assertEquals(47, profile.level)
        assertEquals("吴", profile.nation)
        assertEquals("太守", profile.title)
        assertEquals(9876L, profile.prestige)
        assertEquals(6, profile.resourcePointCurrent)
        assertTrue(resources is ProtocolResult.Ok)
        val resource = (resources as ProtocolResult.Ok).value
        assertEquals(321000L, resource.copper)
        assertEquals(654000L, resource.food)
        assertEquals(31, resource.copperPerHour)
        assertEquals(62, resource.foodPerHour)
        assertEquals(456L, resource.populationCap)
    }

    @Test
    fun realSessionCanReadRoleAndResourceFromPersisted8004PayloadHexEvidence() {
        val text = "roleName=Hex证据君主|level=52|copper=777000|food=888000"
        val hex = text.toByteArray(Charsets.UTF_8).joinToString(separator = "") {
            (it.toInt() and 0xff).toString(16).padStart(2, '0')
        }
        val session = realSession(
            extras = mapOf(
                "roleName" to "",
                "level" to "",
                "copper" to "",
                "food" to "",
                "state8004PayloadHex" to hex
            )
        )

        val monarch = SuspendRunner.run { client.queryMonarch(session) }
        val resources = SuspendRunner.run { client.queryResourceState(session) }

        assertTrue(monarch is ProtocolResult.Ok)
        assertEquals("Hex证据君主", (monarch as ProtocolResult.Ok).value.name)
        assertEquals(52, monarch.value.level)
        assertTrue(resources is ProtocolResult.Ok)
        assertEquals(777000L, (resources as ProtocolResult.Ok).value.copper)
        assertEquals(888000L, resources.value.food)
    }

    @Test
    fun realSessionWithoutMapTargetsDoesNotFallBackToMock() {
        val result = SuspendRunner.run {
            client.searchMap(realSession(), MapCoordinate(1, 2), MapSearchPolicy(targetType = HuangTargetType.HUANG_JIN))
        }

        assertTrue(result is ProtocolResult.Err)
        val err = result as ProtocolResult.Err
        assertEquals("REAL_MAP_TARGETS_METADATA_MISSING", err.code)
        assertFalse(err.retryable)
    }


    @Test
    fun realSessionWithoutMineTargetsDoesNotFallBackToMock() {
        val result = SuspendRunner.run { client.searchMines(realSession(), mineConfig()) }

        assertTrue(result is ProtocolResult.Err)
        val err = result as ProtocolResult.Err
        assertEquals("REAL_MINE_TARGETS_METADATA_MISSING", err.code)
        assertFalse(err.retryable)
    }

    @Test
    fun realSessionCanExposeRecoveredMineTargetsAndFilterByConfig() {
        val session = realSession(
            extras = mapOf(
                "mineTargetsJson" to """[
                    {"id":"0000000000000101","kv":11,"kw":22,"kind":"金矿","rank":5,"kz":9999,"isEmpty":true,"defenseCount":0},
                    {"id":"0000000000000102","kv":33,"kw":44,"kind":"银矿","rank":4,"kz":8888,"isEmpty":false,"defenseCount":3}
                ]"""
            )
        )

        val result = SuspendRunner.run {
            client.searchMines(
                session,
                mineConfig(selectedMineTypes = setOf(MineType.GOLD), onlyEmptyMine = true)
            )
        }

        assertTrue(result is ProtocolResult.Ok)
        val mines = (result as ProtocolResult.Ok).value
        assertEquals(1, mines.size)
        assertEquals(0x101L, mines.single().id)
        assertEquals(MapCoordinate(11, 22), mines.single().coordinate)
        assertEquals(MineType.GOLD, mines.single().mineType)
        assertEquals(5, mines.single().level)
        assertEquals(9999L, mines.single().reserve)
        assertTrue(mines.single().isEmpty)
    }

    @Test
    fun realSessionCanExposeRecovered041542MineResponseAndFilterByConfig() {
        val session = realSession(
            extras = mapOf(
                "mineTargetsHex" to listOf(
                    "0000000001010101000b0016010002D00101000000270F",
                    "00000000010202020021002c000002D0020200000022B8"
                ).joinToString("")
            )
        )

        val result = SuspendRunner.run {
            client.searchMines(
                session,
                mineConfig(selectedMineTypes = setOf(MineType.GOLD), onlyEmptyMine = true)
            )
        }

        assertTrue(result is ProtocolResult.Ok)
        val mines = (result as ProtocolResult.Ok).value
        assertEquals(1, mines.size)
        assertEquals(0x101L, mines.single().id)
        assertEquals(MapCoordinate(11, 22), mines.single().coordinate)
        assertEquals(MineType.GOLD, mines.single().mineType)
        assertEquals(1, mines.single().level)
        assertTrue(mines.single().isEmpty)
        assertEquals("041542-response-parser", mines.single().raw["source"])
    }

    @Test
    fun realSessionCanExposeRecoveredMapTargetsAndFilterByPolicy() {
        val session = realSession(
            extras = mapOf(
                "mapTargetsJson" to """[
                    {"id":"101","x":11,"y":22,"type":"黄巾","rank":3,"kind":"黄巾"},
                    {"id":"102","x":33,"y":44,"type":"山贼","rank":4,"kind":"山贼"}
                ]"""
            )
        )

        val huang = SuspendRunner.run {
            client.searchMap(session, MapCoordinate(0, 0), MapSearchPolicy(targetType = HuangTargetType.HUANG_JIN))
        }
        val shan = SuspendRunner.run {
            client.searchMap(session, MapCoordinate(0, 0), MapSearchPolicy(targetType = HuangTargetType.SHAN_ZEI))
        }

        assertTrue(huang is ProtocolResult.Ok)
        assertEquals(101L, (huang as ProtocolResult.Ok).value.single().id)
        assertEquals(MapCoordinate(11, 22), huang.value.single().coordinate)
        assertEquals("3", huang.value.single().raw["rank"])
        assertTrue(shan is ProtocolResult.Ok)
        assertEquals(102L, (shan as ProtocolResult.Ok).value.single().id)
    }

    @Test
    fun realSessionCanExposeRecoveredMapTargetsFromAliasFields() {
        val session = realSession(
            extras = mapOf(
                "mapTargetsJson" to """[
                    {
                      "targetIdHex":"0000000000000065",
                      "coordX":11,
                      "coordY":22,
                      "targetKind":"渠帅",
                      "targetLevel":11,
                      "rawRecord":"041540-captured-target"
                    },
                    {
                      "targetID":"102",
                      "kv":33,
                      "kw":44,
                      "kind":"山贼",
                      "level":4
                    }
                ]"""
            )
        )

        val huang = SuspendRunner.run {
            client.searchMap(session, MapCoordinate(0, 0), MapSearchPolicy(targetType = HuangTargetType.HUANG_JIN))
        }
        val shan = SuspendRunner.run {
            client.searchMap(session, MapCoordinate(0, 0), MapSearchPolicy(targetType = HuangTargetType.SHAN_ZEI))
        }

        assertTrue(huang is ProtocolResult.Ok)
        val huangTarget = (huang as ProtocolResult.Ok).value.single()
        assertEquals(101L, huangTarget.id)
        assertEquals(MapCoordinate(11, 22), huangTarget.coordinate)
        assertEquals("渠帅", huangTarget.type)
        assertEquals("11", huangTarget.raw["targetLevel"])
        assertEquals("041540-captured-target", huangTarget.raw["rawRecord"])
        assertTrue(shan is ProtocolResult.Ok)
        val shanTarget = (shan as ProtocolResult.Ok).value.single()
        assertEquals(102L, shanTarget.id)
        assertEquals(MapCoordinate(33, 44), shanTarget.coordinate)
        assertEquals("山贼", shanTarget.type)
    }

    @Test
    fun realSessionCanExposeRecovered041540TargetResponseAndFilterByPolicy() {
        val session = realSession(
            extras = mapOf(
                "mapTargetsHex" to listOf(
                    "000000000065030005000b0016E9BB84E5B7BE",
                    "0000000000660400060021002cE5B1B1E8B4BC"
                ).joinToString("|")
            )
        )

        val huang = SuspendRunner.run {
            client.searchMap(session, MapCoordinate(0, 0), MapSearchPolicy(targetType = HuangTargetType.HUANG_JIN))
        }
        val shan = SuspendRunner.run {
            client.searchMap(session, MapCoordinate(0, 0), MapSearchPolicy(targetType = HuangTargetType.SHAN_ZEI))
        }

        assertTrue(huang is ProtocolResult.Ok)
        val huangTarget = (huang as ProtocolResult.Ok).value.single()
        assertEquals(101L, huangTarget.id)
        assertEquals(MapCoordinate(11, 22), huangTarget.coordinate)
        assertEquals("黄巾", huangTarget.type)
        assertEquals("041540-response-parser", huangTarget.raw["source"])
        assertTrue(shan is ProtocolResult.Ok)
        assertEquals(102L, (shan as ProtocolResult.Ok).value.single().id)
    }

    @Test
    fun realSessionCanExposeRecoveredGeneralAndFormationMetadataWhenPresent() {
        val session = realSession(
            extras = mapOf(
                "generalsJson" to """[{"id":7,"name":"赵云","growth":90,"loyalty":100,"energy":88}]""",
                "formationsJson" to """[{"id":3,"name":"刷黄编队1","generalIds":[7],"status":"IDLE","troopCount":1999,"raw":{"evidence":"shuahuangChuzhengBiandui"}}]"""
            )
        )

        val generals = SuspendRunner.run { client.queryGenerals(session) }
        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(generals is ProtocolResult.Ok)
        assertEquals(7L, (generals as ProtocolResult.Ok).value.single().id)
        assertEquals("赵云", generals.value.single().name)
        assertTrue(formations is ProtocolResult.Ok)
        assertEquals(3L, (formations as ProtocolResult.Ok).value.single().id)
        assertTrue(formations.value.single().canDispatch)
        assertEquals(listOf(7L), formations.value.single().generalIds)
    }


    @Test
    fun realSessionCanParseJiangLingStyleGeneralAndFormationFields() {
        val session = realSession(
            extras = mapOf(
                "generalsJson" to """[
                    {
                      "id":"0000000000000007",
                      "name":"赵云",
                      "kind":"名将",
                      "rank":12,
                      "status":0,
                      "placeID":"0000000000000064",
                      "gongji":101,
                      "fangyu":88,
                      "wuli":95,
                      "zhili":70,
                      "tongshuai":99,
                      "tili":49,
                      "tiliLimit":100,
                      "daiBingLimit":1999,
                      "jingyan":1234,
                      "jingyanLimit":2000,
                      "isFulu":true,
                      "isPeiBingFail":false
                    }
                ]""",
                "formationsJson" to """[
                    {"bianduihao":"0000000000000003","bianduiName":"刷黄编队1","generalIds":["0000000000000007"],"status":"0","bingli":1999}
                ]"""
            )
        )

        val generals = SuspendRunner.run { client.queryGenerals(session) }
        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(generals is ProtocolResult.Ok)
        val general = (generals as ProtocolResult.Ok).value.single()
        assertEquals(7L, general.id)
        assertEquals("赵云", general.name)
        assertEquals("名将", general.kind)
        assertEquals(12, general.rank)
        assertEquals(0, general.status)
        assertEquals(100L, general.placeId)
        assertEquals(49, general.energy)
        assertEquals(100, general.energyLimit)
        assertEquals(1999, general.troopLimit)
        assertEquals(true, general.isFulu)
        assertEquals(false, general.isPeiBingFail)
        assertTrue(formations is ProtocolResult.Ok)
        val formation = (formations as ProtocolResult.Ok).value.single()
        assertEquals(3L, formation.id)
        assertEquals("刷黄编队1", formation.name)
        assertEquals(listOf(7L), formation.generalIds)
        assertEquals(FormationRuntimeStatus.IDLE, formation.status)
        assertTrue(formation.canDispatch)
    }

    @Test
    fun realSessionKeepsEightDigitUiSavedIdsAsDecimalNotHex() {
        val session = realSession(
            extras = mapOf(
                "generalsJson" to """[
                    {"id":12966648,"name":"勇民2","status":0,"energy":99,"troopLimit":177}
                ]""",
                "formationsJson" to """[
                    {"id":12966648,"name":"UI单将领编队","generalIds":[12966648],"status":"IDLE","troopCount":177}
                ]"""
            )
        )

        val generals = SuspendRunner.run { client.queryGenerals(session) }
        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(generals is ProtocolResult.Ok)
        assertEquals(12966648L, (generals as ProtocolResult.Ok).value.single().id)
        assertTrue(formations is ProtocolResult.Ok)
        assertEquals(12966648L, (formations as ProtocolResult.Ok).value.single().id)
        assertEquals(listOf(12966648L), formations.value.single().generalIds)
    }

    @Test
    fun realSessionCanParseRecoveredJiangLingDataText() {
        val session = realSession(
            extras = mapOf(
                "jiangLingData" to """
                    id=0000000000000007|name=赵云|kind=名将|rank=12|status=0|placeID=0000000000000064|gongji=101|fangyu=88|wuli=95|zhili=70|tongshuai=99|tili=49|tiliLimit=100|daiBingLimit=1999|zhongChengdu=100|jingyan=1234|jingyanLimit=2000|isFulu=false|isPeiBingFail=false
                    id=0000000000000008|name=马超|kind=名将|rank=11|status=1|tili=0|daiBingLimit=1800|isPeiBingFail=true
                """.trimIndent()
            )
        )

        val generals = SuspendRunner.run { client.queryGenerals(session) }

        assertTrue(generals is ProtocolResult.Ok)
        val list = (generals as ProtocolResult.Ok).value
        assertEquals(2, list.size)
        assertEquals(7L, list[0].id)
        assertEquals("赵云", list[0].name)
        assertEquals(49, list[0].energy)
        assertEquals(1999, list[0].troopLimit)
        assertEquals(100, list[0].loyalty)
        assertEquals("recovered-jiangling", list[0].raw["source"])
        assertEquals(1, list[1].status)
        assertEquals(true, list[1].isPeiBingFail)
    }

    @Test
    fun realSessionCanParseGeneralsFromPersisted8004TailPreview() {
        val session = realSession(
            extras = mapOf(
                "state8004TailUtf8Preview" to "id=0000000000000007|name=赵云|status=0|tili=49|daiBingLimit=1999"
            )
        )

        val generals = SuspendRunner.run { client.queryGenerals(session) }

        assertTrue(generals is ProtocolResult.Ok)
        val general = (generals as ProtocolResult.Ok).value.single()
        assertEquals(7L, general.id)
        assertEquals("赵云", general.name)
        assertEquals(0, general.status)
        assertEquals(49, general.energy)
    }

    @Test
    fun realSessionCanParseGeneralsFromChinese8004TailAliases() {
        val session = realSession(
            extras = mapOf(
                "state8004TailUtf8Preview" to "将领ID=0000000000000007|姓名=赵云|状态=空闲|体力=49|带兵上限=1999|配兵失败=否"
            )
        )

        val generals = SuspendRunner.run { client.queryGenerals(session) }

        assertTrue(generals is ProtocolResult.Ok)
        val general = (generals as ProtocolResult.Ok).value.single()
        assertEquals(7L, general.id)
        assertEquals("赵云", general.name)
        assertEquals(0, general.status)
        assertEquals(49, general.energy)
        assertEquals(1999, general.troopLimit)
        assertEquals(false, general.isPeiBingFail)
    }

    @Test
    fun realSessionCanParseGeneralsFromPersisted8004TailHexWhenItContainsKeyValueEvidence() {
        val evidence = "id=0000000000000007|name=赵云|status=0|tili=49"
        val hex = evidence.toByteArray(Charsets.UTF_8).joinToString(separator = "") {
            (it.toInt() and 0xff).toString(16).padStart(2, '0')
        }
        val session = realSession(extras = mapOf("state8004TailHex" to hex))

        val generals = SuspendRunner.run { client.queryGenerals(session) }

        assertTrue(generals is ProtocolResult.Ok)
        assertEquals(7L, (generals as ProtocolResult.Ok).value.single().id)
    }

    @Test
    fun realSessionCanParseMultipleJiangLingObjectsFromPersisted8004TailPreview() {
        val session = realSession(
            extras = mapOf(
                "state8004TailUtf8Preview" to "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49,daiBingLimit=1999}JiangLing{id=0000000000000008,name=马超,status=1,tili=0}"
            )
        )

        val generals = SuspendRunner.run { client.queryGenerals(session) }

        assertTrue(generals is ProtocolResult.Ok)
        val list = (generals as ProtocolResult.Ok).value
        assertEquals(2, list.size)
        assertEquals(7L, list[0].id)
        assertEquals("赵云", list[0].name)
        assertEquals(1999, list[0].troopLimit)
        assertEquals(8L, list[1].id)
        assertEquals(1, list[1].status)
    }

    @Test
    fun realSessionCanParseLengthPrefixedGeneralCandidateFromPersisted8004TailHex() {
        val idHex = "0000000000000007"
        val nameBytes = "赵云".toByteArray(Charsets.UTF_8)
        val nameLenHex = nameBytes.size.toString(16).padStart(4, '0')
        val nameHex = nameBytes.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
        val session = realSession(extras = mapOf("state8004TailHex" to idHex + nameLenHex + nameHex + "0031"))

        val generals = SuspendRunner.run { client.queryGenerals(session) }

        assertTrue(generals is ProtocolResult.Ok)
        val general = (generals as ProtocolResult.Ok).value.single()
        assertEquals(7L, general.id)
        assertEquals("赵云", general.name)
        assertEquals(0, general.status)
        assertEquals(49, general.energy)
        assertEquals("state8004-binary-name-candidate", general.raw["source"])
    }

    @Test
    fun realSessionTreatsZeroTiliOnBinaryNameCandidateAsUnknownEnergy() {
        val idHex = "0000000000000007"
        val nameBytes = "赵云".toByteArray(Charsets.UTF_8)
        val nameLenHex = nameBytes.size.toString(16).padStart(4, '0')
        val nameHex = nameBytes.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
        val session = realSession(extras = mapOf("state8004TailHex" to idHex + nameLenHex + nameHex + "0000"))

        val generals = SuspendRunner.run { client.queryGenerals(session) }

        assertTrue(generals is ProtocolResult.Ok)
        val general = (generals as ProtocolResult.Ok).value.single()
        assertEquals(7L, general.id)
        assertEquals(0, general.status)
        assertEquals(null, general.energy)
        assertEquals("0", general.raw["tili"])
    }

    @Test
    fun realSessionCanBuildRecoveredShuaHuangFormationsFromSharedPrefsKeys() {
        val session = realSession(
            extras = mapOf(
                "jiangLingData" to "id=0000000000000007|name=赵云|status=0|tili=49|isPeiBingFail=false",
                "xiaohuangPrefsJson" to """{
                    "shuahuangChuzhengBiandui0": true,
                    "bianduihao0": "0000000000000003",
                    "bianduiDejiangling0": "0000000000000007",
                    "bingli0": "1999"
                }"""
            )
        )

        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(formations is ProtocolResult.Ok)
        val formation = (formations as ProtocolResult.Ok).value.single()
        assertEquals(3L, formation.id)
        assertEquals("刷黄编队3", formation.name)
        assertEquals(listOf(7L), formation.generalIds)
        assertEquals(FormationRuntimeStatus.IDLE, formation.status)
        assertEquals(1999, formation.troopCount)
        assertEquals("recovered-shuahuang-shared-prefs", formation.raw["source"])
        assertTrue(formation.canDispatch)
    }

    @Test
    fun realSessionAppendsSelectedGeneralFallbackWhenRecoveredPrefsHaveDifferentFormationIds() {
        val session = realSession(
            extras = mapOf(
                "allowRecoveredGeneralFallbackFormation" to "true",
                "selectedFormationIds" to "7",
                "shuaHuangSelectedFormationIds" to "[7]",
                "jiangLingData" to """
                    id=0000000000000007|name=赵云|status=0|tili=49|daiBingLimit=200|isPeiBingFail=false
                    id=0000000000000008|name=马超|status=0|tili=49|daiBingLimit=200|isPeiBingFail=false
                """.trimIndent(),
                "xiaohuangPrefsJson" to """{
                    "shuahuangChuzhengBiandui0": true,
                    "bianduihao0": "0000000000000003",
                    "bianduiDejiangling0": "0000000000000008",
                    "bingli0": "1999"
                }"""
            )
        )

        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(formations is ProtocolResult.Ok)
        val list = (formations as ProtocolResult.Ok).value
        assertTrue(list.any { it.id == 3L && it.generalIds == listOf(8L) })
        val selectedGeneralFallback = list.single { it.id == 7L }
        assertEquals("候选刷黄编队-赵云", selectedGeneralFallback.name)
        assertEquals(listOf(7L), selectedGeneralFallback.generalIds)
        assertEquals(FormationRuntimeStatus.IDLE, selectedGeneralFallback.status)
        assertEquals(200, selectedGeneralFallback.troopCount)
        assertEquals("recovered-state8004-general-fallback", selectedGeneralFallback.raw["source"])
    }

    @Test
    fun realSessionAppendsSelectedGeneralFallbackWhenFormationsJsonExists() {
        val session = realSession(
            extras = mapOf(
                "allowRecoveredGeneralFallbackFormation" to "true",
                "selectedFormationIds" to "7",
                "generalsJson" to """[
                    {"id":7,"name":"赵云","status":0,"energy":49,"troopLimit":200,"isPeiBingFail":false},
                    {"id":8,"name":"马超","status":0,"energy":49,"troopLimit":200,"isPeiBingFail":false}
                ]""",
                "formationsJson" to """[
                    {"id":3,"name":"旧编队","generalIds":[8],"status":"IDLE","troopCount":1999}
                ]"""
            )
        )

        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(formations is ProtocolResult.Ok)
        val list = (formations as ProtocolResult.Ok).value
        assertTrue(list.any { it.id == 3L && it.generalIds == listOf(8L) })
        assertTrue(list.any { it.id == 7L && it.generalIds == listOf(7L) })
    }

    @Test
    fun realSessionCanBuildExplicitFallbackFormationFromRecoveredIdleGeneralCandidate() {
        val idHex = "0000000000000007"
        val nameBytes = "赵云".toByteArray(Charsets.UTF_8)
        val nameLenHex = nameBytes.size.toString(16).padStart(4, '0')
        val nameHex = nameBytes.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
        val session = realSession(
            extras = mapOf(
                "allowRecoveredGeneralFallbackFormation" to "true",
                "state8004TailHex" to idHex + nameLenHex + nameHex + "0031"
            )
        )

        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(formations is ProtocolResult.Ok)
        val formation = (formations as ProtocolResult.Ok).value.single()
        assertEquals(7L, formation.id)
        assertEquals("候选刷黄编队-赵云", formation.name)
        assertEquals(listOf(7L), formation.generalIds)
        assertEquals(FormationRuntimeStatus.IDLE, formation.status)
        assertTrue(formation.canDispatch)
        assertEquals("recovered-state8004-general-fallback", formation.raw["source"])
    }

    @Test
    fun realSessionCanBuildFallbackFormationFromZeroTiliBinaryNameCandidate() {
        val idHex = "0000000000000007"
        val nameBytes = "赵云".toByteArray(Charsets.UTF_8)
        val nameLenHex = nameBytes.size.toString(16).padStart(4, '0')
        val nameHex = nameBytes.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
        val session = realSession(
            extras = mapOf(
                "allowRecoveredGeneralFallbackFormation" to "true",
                "state8004TailHex" to idHex + nameLenHex + nameHex + "0000"
            )
        )

        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(formations is ProtocolResult.Ok)
        val formation = (formations as ProtocolResult.Ok).value.single()
        assertEquals(7L, formation.id)
        assertEquals(listOf(7L), formation.generalIds)
        assertEquals(FormationRuntimeStatus.IDLE, formation.status)
        assertTrue(formation.canDispatch)
    }

    @Test
    fun realSessionDoesNotBuildFallbackFormationWithoutExplicitFlag() {
        val idHex = "0000000000000007"
        val nameBytes = "赵云".toByteArray(Charsets.UTF_8)
        val nameLenHex = nameBytes.size.toString(16).padStart(4, '0')
        val nameHex = nameBytes.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
        val session = realSession(
            extras = mapOf("state8004TailHex" to idHex + nameLenHex + nameHex + "0031")
        )

        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(formations is ProtocolResult.Err)
        assertEquals("REAL_FORMATIONS_METADATA_MISSING", (formations as ProtocolResult.Err).code)
    }

    @Test
    fun recoveredShuaHuangFormationBecomesBusyWhenGeneralIsNotIdle() {
        val session = realSession(
            extras = mapOf(
                "jiangLingData" to "id=0000000000000008|name=马超|status=1|tili=0|isPeiBingFail=true",
                "shuahuangChuzhengBiandui1" to "true",
                "bianduihao1" to "4",
                "bianduiDejiangling1" to "0000000000000008"
            )
        )

        val formations = SuspendRunner.run { client.queryFormations(session) }

        assertTrue(formations is ProtocolResult.Ok)
        val formation = (formations as ProtocolResult.Ok).value.single()
        assertEquals(4L, formation.id)
        assertEquals(listOf(8L), formation.generalIds)
        assertEquals(FormationRuntimeStatus.BUSY, formation.status)
        assertFalse(formation.canDispatch)
        assertEquals("true", formation.raw["isPeiBingFail"])
    }

    @Test
    fun realSessionWithoutGeneralMetadataStopsExplicitly() {
        val result = SuspendRunner.run { client.queryGenerals(realSession()) }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_GENERALS_METADATA_MISSING", (result as ProtocolResult.Err).code)
    }




    @Test
    fun realSessionWithoutOccupyOrWithdrawMetadataDoesNotFallbackToMock() {
        val mine = unitMine()

        val occupy = SuspendRunner.run { client.occupyMine(realSession(), mine, formationId = 3L) }
        val withdraw = SuspendRunner.run { client.withdrawMineDefense(realSession(), mineId = mine.id) }

        assertTrue(occupy is ProtocolResult.Err)
        assertEquals("REAL_OCCUPY_MINE_METADATA_MISSING", (occupy as ProtocolResult.Err).code)
        assertFalse(occupy.retryable)
        assertTrue(withdraw is ProtocolResult.Err)
        assertEquals("REAL_WITHDRAW_MINE_METADATA_MISSING", (withdraw as ProtocolResult.Err).code)
        assertFalse(withdraw.retryable)
    }

    @Test
    fun realSessionCanReturnRecoveredOccupyMineResultWithP2OnePayloadShape() {
        val session = realSession(
            extras = mapOf(
                "occupyMineResultsJson" to """[
                    {
                      "mineId":"257",
                      "formationId":3,
                      "success":true,
                      "message":"占矿出征成功",
                      "generalIdHexChunks":["0000000000000007"],
                      "resourcePointIdHex":"0000000000000101",
                      "raw":{"evidence":"p2=1/1520010+1522010"}
                    }
                ]"""
            )
        )

        val result = SuspendRunner.run { client.occupyMine(session, unitMine(), formationId = 3L) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("占矿出征成功", step.message)
        assertEquals("p2=1/1520010+1522010", step.raw["evidence"])
        assertEquals(
            "000000000000000000121520010100000000000000070000000000000101",
            step.raw["resourcePointFirstPayload"]
        )
        assertEquals(
            "0000000000000000001d1522010100000000000000070000000000000101ffffffffffffffff000000",
            step.raw["resourcePointSecondPayload"]
        )
    }

    @Test
    fun realSessionOccupyWrapperConsumesImportedNativeFieldsButStillBlocksNetwork() {
        val session = realSession(
            extras = mapOf(
                "nativeWrapperLx" to "lxVALUE",
                "nativeWrapperKey" to "keyVALUE",
                "nativeWrapperLb" to "lbVALUE",
                "occupyMineResultsJson" to """[
                    {
                      "mineId":"257",
                      "formationId":3,
                      "success":true,
                      "message":"占矿出征成功",
                      "generalIdHexChunks":["0000000000000007"],
                      "resourcePointIdHex":"0000000000000101"
                    }
                ]"""
            )
        )

        val result = SuspendRunner.run { client.occupyMine(session, unitMine(), formationId = 3L) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertEquals("", step.raw["resourcePointFirstWrapperMissingFields"])
        assertEquals("", step.raw["resourcePointSecondWrapperMissingFields"])
        assertEquals("false", step.raw["resourcePointFirstWrapperNetworkAllowed"])
        assertEquals("false", step.raw["resourcePointSecondWrapperNetworkAllowed"])
        assertTrue(step.raw["resourcePointSecondWrapperMaskedCandidate"]!!.contains("1522010"))
        assertFalse(step.raw["resourcePointSecondWrapperMaskedCandidate"]!!.contains("VALUE"))
    }

    @Test
    fun realSessionCanReturnRecoveredWithdrawMineResultWithPayloadShape() {
        val session = realSession(
            extras = mapOf(
                "withdrawMineResultsJson" to """[
                    {"mineId":"257","success":true,"message":"撤回驻防完成","defenseRecordIdHex":"0000000000000007","raw":{"evidence":"0a15260101"}}
                ]"""
            )
        )

        val result = SuspendRunner.run { client.withdrawMineDefense(session, mineId = 257L) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("撤回驻防完成", step.message)
        assertEquals("0a15260101", step.raw["evidence"])
        assertEquals(
            "0000000000000000000a152601010000000000000007",
            step.raw["withdrawPayload"]
        )
    }

    @Test
    fun remainingAutomationP2OneShapesUseRecoveredResourcePointFormula() {
        val ids = listOf("0000000000000007")
        val resourcePointId = "0000000000000101"

        assertEquals(
            "000000000000000000121520010100000000000000070000000000000101",
            RemainingAutomationProtocolShapes.resourceSendGeneralFirstStage(ids, resourcePointId)
        )
        assertEquals(
            "0000000000000000001d1522010100000000000000070000000000000101ffffffffffffffff000000",
            RemainingAutomationProtocolShapes.resourceSendGeneralSecondStage(ids, resourcePointId)
        )
    }

    @Test
    fun realSessionWithoutDailyMetadataDoesNotFallBackToMock() {
        val result = SuspendRunner.run { client.runDailyStep(realSession(), DailyStep.SIGN_IN) }

        assertTrue(result is ProtocolResult.Err)
        val err = result as ProtocolResult.Err
        assertEquals("REAL_DAILY_METADATA_MISSING", err.code)
        assertFalse(err.retryable)
    }

    @Test
    fun realInventoryUsesLoginCacheWithExactCountsAndNormalizedBoxType() {
        val session = realSession(
            extras = mapOf(
                "inventoryJson" to """[
                    {"itemId":9,"name":"传音符","count":27,"type":"道具"},
                    {"itemId":58,"name":"青铜宝箱","count":3,"type":"道具"}
                ]"""
            )
        )

        val result = SuspendRunner.run { client.queryInventory(session) }

        assertTrue(result is ProtocolResult.Ok)
        val items = (result as ProtocolResult.Ok).value
        assertEquals(27, items.first { it.name == "传音符" }.count)
        assertEquals("box", items.first { it.name == "青铜宝箱" }.type)
        assertEquals(3, items.first { it.name == "青铜宝箱" }.count)
    }

    @Test
    fun realInventoryWithoutCacheReturnsRetryableMissingStateInsteadOfMockData() {
        val result = SuspendRunner.run { client.queryInventory(realSession()) }

        assertTrue(result is ProtocolResult.Err)
        val error = result as ProtocolResult.Err
        assertEquals("REAL_INVENTORY_METADATA_MISSING", error.code)
        assertTrue(error.retryable)
    }

    @Test
    fun realInventoryActionRequiresIndependentInventoryScopeBeforeNetworkSend() {
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        val result = SuspendRunner.run {
            client.useOrDiscardItem(session, itemId = 58L, action = InventoryAction.OPEN)
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_INVENTORY_SCOPE_NOT_CONFIRMED", (result as ProtocolResult.Err).code)
    }

    @Test
    fun realInventoryActionRejectsZeroCountBeforeNetworkSend() {
        val result = SuspendRunner.run {
            client.useOrDiscardItem(realSession(), itemId = 58L, action = InventoryAction.OPEN, count = 0)
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_INVENTORY_COUNT_INVALID", (result as ProtocolResult.Err).code)
    }

    @Test
    fun realInventoryActionAcceptsScopeFromMultiScopeSet() {
        val session = realSession(
            extras = mapOf(
                "dm" to "",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "brush-yellow",
                "realActionScopes" to "brush-yellow,daily,inventory"
            )
        )

        val result = SuspendRunner.run {
            client.useOrDiscardItem(session, itemId = 58L, action = InventoryAction.OPEN)
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_INVENTORY_DM_MISSING", (result as ProtocolResult.Err).code)
    }

    @Test
    fun realInventoryDiscardRequiresCaptured8103SuccessReceipt() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x1103 to listOf(0x8103 to "00000fe4b8a2e5bc83e68890e58a9fefbc81"))
        )
        val inventoryClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "inventory"
            )
        )

        val result = SuspendRunner.run {
            inventoryClient.useOrDiscardItem(session, 9L, InventoryAction.DISCARD, 27)
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("丢弃成功！", step.message)
        assertEquals(listOf(0x1103), transport.opcodes)
        assertTrue(transport.gameHexes.single().endsWith("0000000000000000090000001bffffffffffffffff"))
    }

    @Test
    fun realInventoryOpcodeAloneCannotTurnRejectedReceiptIntoSuccess() {
        val rejectedMessage = "服务器拒绝".toByteArray(Charsets.UTF_8)
        val payload = byteArrayOf(
            -1,
            ((rejectedMessage.size ushr 8) and 0xff).toByte(),
            (rejectedMessage.size and 0xff).toByte()
        ) + rejectedMessage
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x3144 to listOf(0xa144 to payload.joinToString("") { "%02x".format(it.toInt() and 0xff) }))
        )
        val inventoryClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "inventory"
            )
        )

        val result = SuspendRunner.run {
            inventoryClient.useOrDiscardItem(session, 58L, InventoryAction.OPEN, 1)
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertFalse(step.success)
        assertEquals("服务器拒绝", step.message)
    }

    @Test
    fun realHealUsesCaptured8231Then8230AndAcceptsGeneralMaintenanceScope() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1231 to listOf(
                    0x8231 to "0000000000000755ffff00000000000000010000000000000079"
                ),
                0x1230 to listOf(
                    0x8230 to "00000000000000007900000000000a8dc900000000000000075501030000000300"
                )
            )
        )
        val maintenanceClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "general-maintenance",
                "generalsJson" to """
                    [{"id":7,"name":"赵云","status":0,"tili":40,"placeID":1877}]
                """.trimIndent()
            )
        )

        val result = SuspendRunner.run { maintenanceClient.healGeneral(session, 7L) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("治疗成功", step.message)
        assertEquals("1", step.raw["copperCost"])
        assertEquals(listOf(0x1231, 0x1230), transport.opcodes)
        assertTrue(transport.gameHexes[0].endsWith("0000000000000755ffffffffffff"))
        assertTrue(transport.gameHexes[1].endsWith("0000000000000755020000ffffffff00"))
    }

    @Test
    fun realHealPreInfoFiefMismatchStopsBeforeMutation() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1231 to listOf(
                    0x8231 to "0000000000000756ffff00000000000000010000000000000079"
                )
            )
        )
        val maintenanceClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "general-maintenance",
                "generalsJson" to """
                    [{"id":7,"name":"赵云","status":0,"tili":40,"placeID":1877}]
                """.trimIndent()
            )
        )

        val result = SuspendRunner.run { maintenanceClient.healGeneral(session, 7L) }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_HEAL_PREINFO_INVALID", (result as ProtocolResult.Err).code)
        assertEquals(listOf(0x1231), transport.opcodes)
    }

    @Test
    fun realAddEnergyChecksIdleGeneralInventoryAnd8218Receipt() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x1218 to listOf(0x8218 to "00010203"))
        )
        val maintenanceClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "general-maintenance",
                "generalsJson" to """
                    [{"id":7,"name":"赵云","status":0,"tili":40,"placeID":1877}]
                """.trimIndent(),
                "inventoryJson" to """
                    [{"itemId":12,"name":"活血丹","count":2,"type":"道具"}]
                """.trimIndent()
            )
        )

        val result = SuspendRunner.run { maintenanceClient.addEnergy(session, 7L) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("活血丹使用成功", step.message)
        assertEquals(listOf(0x1218), transport.opcodes)
        assertTrue(transport.gameHexes.single().endsWith("0000000000000007000c0001"))
    }

    @Test
    fun realDailyActionRequiresIndependentDailyScopeBeforeNetworkSend() {
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "brush-yellow"
            )
        )

        val result = SuspendRunner.run { client.runDailyStep(session, DailyStep.SIGN_IN) }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_DAILY_SCOPE_NOT_CONFIRMED", (result as ProtocolResult.Err).code)
    }

    @Test
    fun realDailyActionRequiresDmBeforeNetworkSend() {
        val session = realSession(
            extras = mapOf(
                "dm" to "",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        val result = SuspendRunner.run { client.runDailyStep(session, DailyStep.ARENA_REWARD) }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_DAILY_DM_MISSING", (result as ProtocolResult.Err).code)
    }

    @Test
    fun realDonationRequiresRoleLevelBeforeNetworkSend() {
        val session = realSession(
            extras = mapOf(
                "level" to "",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        val result = SuspendRunner.run { client.runDailyStep(session, DailyStep.DONATE_COPPER) }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_DAILY_LEVEL_MISSING", (result as ProtocolResult.Err).code)
    }

    @Test
    fun realDonationAttemptsSelectedResourceEvenWhenSiblingResourceIsShort() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x140c to listOf(0x840c to "00"))
        )
        val donationClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "level" to "38",
                "copper" to "38000",
                "food" to "113999",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        // The desktop-aligned scheduled donation task calls copper, food and
        // technology independently.  A shortage in food must not suppress the
        // selected copper endpoint (nor turn a transport success into a pair
        // preflight failure).
        val result = SuspendRunner.run { donationClient.runDailyStep(session, DailyStep.DONATE_COPPER) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals(listOf(0x140c), transport.opcodes)
    }

    @Test
    fun realInternalAffairsDiscoversOwnedFiefsPrioritizesHallAndConfirms8200Sync() {
        val fiefId = 0x0a79L
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1310 to listOf(0x8310 to ownedFiefListPayload("测试君主", fiefId).testHex()),
                0x1246 to listOf(0x8246 to fiefStatePayload(fiefId, hallLevel = 1).testHex()),
                0x1200 to listOf(0x8200 to buildingActionPayload(fiefId, hallLevel = 2).testHex())
            )
        )
        val internalClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "internal-affairs",
                "generalsJson" to """
                    [{"id":7,"name":"赵云","status":0,"placeID":$fiefId}]
                """.trimIndent()
            )
        )

        val result = SuspendRunner.run {
            internalClient.runInternalAffairs(
                session,
                InternalAffairsConfig(
                    enabled = true,
                    upgradeLowestFirst = true,
                    buildingPriority = emptyList(),
                    buildWhenEmpty = null
                )
            )
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertTrue(step.message.contains("优先升级大厅1→2已确认"))
        assertEquals("0x8200建筑同步", step.raw["confirmedBy"])
        assertEquals(listOf(0x1310, 0x1246, 0x1200), transport.opcodes)
        assertTrue(transport.gameHexes.last().endsWith("000000000000000a7900000000"))
    }

    @Test
    fun realTechnologyUpgradeUsesSelectedLowestTechnologyAnd823fReceipt() {
        val fiefId = 0x0a79L
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1310 to listOf(0x8310 to ownedFiefListPayload("测试君主", fiefId).testHex()),
                0x1246 to listOf(
                    0x8246 to fiefStatePayload(fiefId, hallLevel = 6, academyLevel = 5).testHex()
                ),
                0x123F to listOf(0x823F to "000000")
            )
        )
        val internalClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "internal-affairs",
                "generalsJson" to """
                    [{"id":7,"name":"赵云","status":0,"placeID":$fiefId}]
                """.trimIndent(),
                "state8004PayloadHex" to technologyStatePayload(
                    levels = mapOf(5 to 2)
                ).testHex()
            )
        )

        val result = SuspendRunner.run {
            internalClient.runInternalAffairs(
                session,
                InternalAffairsConfig(
                    enabled = false,
                    upgradeLowestFirst = true,
                    buildingPriority = emptyList(),
                    buildWhenEmpty = null,
                    upgradeTechnology = true,
                    technologyIds = setOf(5)
                )
            )
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("5", step.raw["technologyId"])
        assertEquals("2", step.raw["fromLevel"])
        assertEquals("3", step.raw["targetLevel"])
        assertEquals(listOf(0x1310, 0x1246, 0x123F), transport.opcodes)
        assertTrue(transport.gameHexes.last().endsWith("0000000000000a79030005030000"))
    }

    @Test
    fun combinedInternalAndTechnologyTaskAlternatesSoTechnologyCannotStarve() {
        val fiefId = 0x0a79L
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1310 to listOf(0x8310 to ownedFiefListPayload("测试君主", fiefId).testHex()),
                0x1246 to listOf(
                    0x8246 to fiefStatePayload(fiefId, hallLevel = 1, academyLevel = 5).testHex()
                ),
                0x1200 to listOf(0x8200 to buildingActionPayload(fiefId, hallLevel = 2).testHex()),
                0x123F to listOf(0x823F to "000000")
            )
        )
        val internalClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "internal-affairs",
                "generalsJson" to """[{"id":7,"name":"赵云","status":0,"placeID":$fiefId}]""",
                "state8004PayloadHex" to technologyStatePayload(mapOf(5 to 2)).testHex()
            )
        )
        val config = InternalAffairsConfig(
            enabled = true,
            upgradeLowestFirst = true,
            buildingPriority = emptyList(),
            buildWhenEmpty = null,
            upgradeTechnology = true,
            technologyIds = setOf(5)
        )

        val first = SuspendRunner.run { internalClient.runInternalAffairs(session, config) }
        val second = SuspendRunner.run { internalClient.runInternalAffairs(session, config) }

        assertTrue((first as ProtocolResult.Ok).value.message.contains("大厅"))
        assertEquals("5", (second as ProtocolResult.Ok).value.raw["technologyId"])
        assertEquals(
            listOf(0x1310, 0x1246, 0x1200, 0x1310, 0x1246, 0x123F),
            transport.opcodes
        )
    }

    @Test
    fun technologyUpgradeConvertsOnlyRequiredFoodBefore123fWhenCopperIsBelowCost() {
        val fiefId = 0x0a79L
        val converted = ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeByte(0)
                out.writeLong(10_000L)
                out.writeLong(970_000L)
            }
        }.toByteArray()
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1310 to listOf(0x8310 to ownedFiefListPayload("测试君主", fiefId).testHex()),
                0x1246 to listOf(
                    0x8246 to fiefStatePayload(fiefId, hallLevel = 6, academyLevel = 5).testHex()
                ),
                0x1152 to listOf(0x8152 to converted.testHex()),
                0x123F to listOf(0x823F to "000000")
            )
        )
        val internalClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "copper" to "1000",
                "food" to "1000000",
                "copperFloorWan" to "1",
                "foodToCopperEnabled" to "true",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "internal-affairs,resource-conversion",
                "generalsJson" to """[{"id":7,"name":"赵云","status":0,"placeID":$fiefId}]""",
                "state8004PayloadHex" to technologyStatePayload(mapOf(5 to 2)).testHex()
            )
        )

        val result = SuspendRunner.run {
            internalClient.runInternalAffairs(
                session,
                InternalAffairsConfig(
                    enabled = false,
                    upgradeLowestFirst = true,
                    buildingPriority = emptyList(),
                    buildWhenEmpty = null,
                    upgradeTechnology = true,
                    technologyIds = setOf(5)
                )
            )
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("30000", step.raw["convertedFood"])
        assertEquals("9600", step.raw["requiredCopper"])
        assertEquals(listOf(0x1310, 0x1246, 0x1152, 0x123F), transport.opcodes)
        assertTrue(transport.gameHexes[2].endsWith("010000000000007530"))
    }

    @Test
    fun buildingFailureConvertsFromRecoveredCostAndRetriesExactlyOnce() {
        val fiefId = 0x0a79L
        val converted = ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeByte(0)
                out.writeLong(10_000L)
                out.writeLong(970_000L)
            }
        }.toByteArray()
        val transport = SequentialDirectBinaryTransport(
            mapOf(
                0x1310 to listOf(listOf(0x8310 to ownedFiefListPayload("测试君主", fiefId).testHex())),
                0x1246 to listOf(listOf(0x8246 to fiefStatePayload(fiefId, hallLevel = 1).testHex())),
                0x1200 to listOf(
                    listOf(0x8200 to buildingActionPayload(fiefId, hallLevel = 1, status = 1).testHex()),
                    listOf(0x8200 to buildingActionPayload(fiefId, hallLevel = 2).testHex())
                ),
                0x1152 to listOf(listOf(0x8152 to converted.testHex()))
            )
        )
        val internalClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "copper" to "1000",
                "food" to "1000000",
                "copperFloorWan" to "1",
                "foodToCopperEnabled" to "true",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "internal-affairs,resource-conversion",
                "generalsJson" to """[{"id":7,"name":"赵云","status":0,"placeID":$fiefId}]"""
            )
        )

        val result = SuspendRunner.run {
            internalClient.runInternalAffairs(
                session,
                InternalAffairsConfig(
                    enabled = true,
                    upgradeLowestFirst = true,
                    buildingPriority = emptyList(),
                    buildWhenEmpty = null
                )
            )
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("30000", step.raw["convertedFood"])
        assertEquals(
            listOf(0x1310, 0x1246, 0x1200, 0x1152, 0x1200),
            transport.opcodes
        )
        assertEquals(2, transport.opcodes.count { it == 0x1200 })
    }

    @Test
    fun buildingFailureDoesNotRetryWhenFoodCannotCoverConversionAndBuildingReserve() {
        val fiefId = 0x0a79L
        val transport = SequentialDirectBinaryTransport(
            mapOf(
                0x1310 to listOf(listOf(0x8310 to ownedFiefListPayload("测试君主", fiefId).testHex())),
                0x1246 to listOf(listOf(0x8246 to fiefStatePayload(fiefId, hallLevel = 1).testHex())),
                0x1200 to listOf(
                    listOf(0x8200 to buildingActionPayload(fiefId, hallLevel = 1, status = 1).testHex())
                )
            )
        )
        val internalClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "copper" to "1000",
                // 大厅2级需预留450粮，补足1万铜还需兑换30000粮。
                "food" to "30000",
                "copperFloorWan" to "1",
                "foodToCopperEnabled" to "true",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "internal-affairs,resource-conversion",
                "generalsJson" to """[{"id":7,"name":"赵云","status":0,"placeID":$fiefId}]"""
            )
        )

        val result = SuspendRunner.run {
            internalClient.runInternalAffairs(
                session,
                InternalAffairsConfig(
                    enabled = true,
                    upgradeLowestFirst = true,
                    buildingPriority = emptyList(),
                    buildWhenEmpty = null
                )
            )
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_CONVERT_FOOD_INSUFFICIENT", (result as ProtocolResult.Err).code)
        assertEquals(listOf(0x1310, 0x1246, 0x1200), transport.opcodes)
        assertEquals(1, transport.opcodes.count { it == 0x1200 })
        assertEquals(0, transport.opcodes.count { it == 0x1152 })
    }

    @Test
    fun buildingFailureDoesNotConvertOrRetryWithoutResourceConversionScope() {
        val fiefId = 0x0a79L
        val transport = SequentialDirectBinaryTransport(
            mapOf(
                0x1310 to listOf(listOf(0x8310 to ownedFiefListPayload("测试君主", fiefId).testHex())),
                0x1246 to listOf(listOf(0x8246 to fiefStatePayload(fiefId, hallLevel = 1).testHex())),
                0x1200 to listOf(
                    listOf(0x8200 to buildingActionPayload(fiefId, hallLevel = 1, status = 1).testHex())
                )
            )
        )
        val internalClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "copper" to "1000",
                "food" to "1000000",
                "copperFloorWan" to "1",
                "foodToCopperEnabled" to "true",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "internal-affairs",
                "generalsJson" to """[{"id":7,"name":"赵云","status":0,"placeID":$fiefId}]"""
            )
        )

        val result = SuspendRunner.run {
            internalClient.runInternalAffairs(
                session,
                InternalAffairsConfig(
                    enabled = true,
                    upgradeLowestFirst = true,
                    buildingPriority = emptyList(),
                    buildWhenEmpty = null
                )
            )
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals(
            "REAL_INTERNAL_CONVERT_SCOPE_NOT_CONFIRMED",
            (result as ProtocolResult.Err).code
        )
        assertEquals(listOf(0x1310, 0x1246, 0x1200), transport.opcodes)
        assertEquals(1, transport.opcodes.count { it == 0x1200 })
        assertEquals(0, transport.opcodes.count { it == 0x1152 })
    }

    @Test
    fun realFoodToCopperTreatsWanAsCopperFloorAndRoundsToThreeThousandCopperUnits() {
        val response = ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeByte(0)
                out.writeLong(102_500L)
                out.writeLong(20_000L)
            }
        }.toByteArray()
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x1152 to listOf(0x8152 to response.testHex()))
        )
        val conversionClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "copper" to "93500",
                "food" to "50000",
                "copperFloorWan" to "10",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "resource-conversion"
            )
        )

        val result = SuspendRunner.run {
            conversionClient.convertFoodToCopper(session, ConvertMode.FOOD_TO_COPPER_THRESHOLD)
        }

        assertTrue(result is ProtocolResult.Ok)
        val state = (result as ProtocolResult.Ok).value
        assertEquals(102_500L, state.copper)
        assertEquals(20_000L, state.food)
        assertEquals("30000", state.raw["convertedFood"])
        assertEquals(listOf(0x1152), transport.opcodes)
        assertTrue(transport.gameHexes.single().endsWith("010000000000007530"))
    }

    @Test
    fun realFoodToCopperDoesNotSendWhenCopperAlreadyMeetsFloor() {
        val transport = ScriptedDirectBinaryTransport(emptyMap())
        val conversionClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "copper" to "100000",
                "food" to "50000",
                "copperFloorWan" to "10",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "resource-conversion"
            )
        )

        val result = SuspendRunner.run {
            conversionClient.convertFoodToCopper(session, ConvertMode.FOOD_TO_COPPER_THRESHOLD)
        }

        assertTrue(result is ProtocolResult.Ok)
        assertEquals("false", (result as ProtocolResult.Ok).value.raw["converted"])
        assertEquals(emptyList<Int>(), transport.opcodes)
    }

    @Test
    fun realDailySignInConfirmsSignInBeforeClaimingDailyDiamondBox() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x6202 to listOf(0xE202 to "000000"),
                0x1134 to listOf(0x8134 to "000000")
            )
        )
        val dailyClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        val result = SuspendRunner.run { dailyClient.runDailyStep(session, DailyStep.SIGN_IN) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("签到请求已确认；每日金钻宝箱已领取", step.message)
        assertEquals(listOf(0x6202, 0x1134), transport.opcodes)
        assertTrue(transport.gameHexes.last().endsWith("00000000000de2b100"))
    }

    @Test
    fun realDailySignInDoesNotClaimDiamondBoxWithoutE202Confirmation() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x6202 to listOf(0x9999 to "000000"))
        )
        val dailyClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        val result = SuspendRunner.run { dailyClient.runDailyStep(session, DailyStep.SIGN_IN) }

        assertTrue(result is ProtocolResult.Ok)
        assertFalse((result as ProtocolResult.Ok).value.success)
        assertEquals(listOf(0x6202), transport.opcodes)
    }

    @Test
    fun realDailySignInRemainsSuccessfulWhenOptionalDiamondBoxFails() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x6202 to listOf(0xE202 to "000000"),
                0x1134 to listOf(0x9999 to "010000")
            )
        )
        val dailyClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        val result = SuspendRunner.run { dailyClient.runDailyStep(session, DailyStep.SIGN_IN) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertTrue(step.message.contains("金钻宝箱未领取"))
        assertEquals(listOf(0x6202, 0x1134), transport.opcodes)
    }

    @Test
    fun realDailyArenaRewardParsesCapturedStatusAndUtfMessage() {
        val capturedArenaReceipt =
            "000037e9939ce992b13a3530303030e88eb7e5be97e68890e58a9fe38082" +
                "e7ab9ee68a80e5b8813a313030e88eb7e5be97e68890e58a9fe38082" +
                "0100000000000a91b600000064"
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x6260 to emptyList(),
                0x6266 to listOf(0xE266 to capturedArenaReceipt)
            )
        )
        val dailyClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        val result = SuspendRunner.run { dailyClient.runDailyStep(session, DailyStep.ARENA_REWARD) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("铜钱:50000获得成功。竞技币:100获得成功。", step.message)
        assertEquals(listOf(0x6260, 0x6266), transport.opcodes)
    }

    @Test
    fun realBrushMaintenanceDeleteMailUsesDesktopPayloadAndStrict8116Receipt() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x1116 to listOf(0x8116 to "00010003"))
        )
        val dailyClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScopes" to "brush-yellow,daily"
            )
        )

        val result = SuspendRunner.run {
            dailyClient.runDailyStep(session, DailyStep.DELETE_MAIL)
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("邮件清理完成，剩余3封", step.message)
        assertEquals("3", step.raw["remainingMail"])
        assertEquals(listOf(0x1116), transport.opcodes)
        assertTrue(transport.gameHexes.single().endsWith("0001ffffffffffffffff"))
    }

    @Test
    fun realBrushMaintenanceDeleteMailRejectsMismatchedBoxReceipt() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x1116 to listOf(0x8116 to "00020000"))
        )
        val dailyClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "daily"
            )
        )

        val result = SuspendRunner.run {
            dailyClient.runDailyStep(session, DailyStep.DELETE_MAIL)
        }

        assertTrue(result is ProtocolResult.Ok)
        assertFalse((result as ProtocolResult.Ok).value.success)
        assertEquals(listOf(0x1116), transport.opcodes)
    }

    @Test
    fun realBatchRefillOnlySends1229WithoutReassigningTroopType() {
        val first = 0x6b4daeL
        val second = 0x6b4d9aL
        val captured8229 =
            "000012e689b9e9878fe8a1a5e6bba1e68890e58a9f" +
                "02" +
                "00000000006b4dae0100000096" +
                "00000000006b4d9a080000000a" +
                "00000000000007550103000000c0"
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x1229 to listOf(0x8229 to captured8229))
        )
        val formationClient = SessionAwareGameProtocolClient(
            directBinaryTransport = transport::execute
        )
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "brush-yellow"
            )
        )

        val result = SuspendRunner.run {
            formationClient.updateFormation(
                session,
                FormationConfig(
                    formationId = first,
                    generalIds = listOf(first, second),
                    autoAssignTroops = false,
                    troopType = "",
                    troopCount = 0,
                    fillToMaxWhenAutoAssignDisabled = true
                )
            )
        }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("true", step.raw["batchRefillOnly"])
        assertEquals(listOf(0x1229), transport.opcodes)
        assertEquals(0, transport.opcodes.count { it == 0x1226 })
        assertTrue(
            transport.gameHexes.single()
                .endsWith("0200000000006b4dae00000000006b4d9a")
        )
    }

    @Test
    fun realMineOccupyUsesP2TwoPrepareAndDispatchWithStrict8522Success() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1520 to listOf(0x8520 to "000000"),
                0x1522 to listOf(0x8522 to "000000")
            )
        )
        val mineClient = SessionAwareGameProtocolClient(
            directBinaryTransport = transport::execute
        )
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "mine",
                "generalsJson" to
                    """[{"id":7,"name":"赵云","status":0,"tili":50,"soldierTypeCode":1,"soldierCount":100}]"""
            )
        )
        val mine = MineSearchResult(
            id = 99L,
            coordinate = MapCoordinate(18, 22),
            mineType = MineType.GOLD,
            level = 5,
            reserve = 1000L,
            isEmpty = true,
            defenseCount = 0
        )

        val result = SuspendRunner.run {
            mineClient.occupyMine(session, mine, 7L)
        }

        assertTrue(result is ProtocolResult.Ok)
        assertTrue((result as ProtocolResult.Ok).value.success)
        assertEquals(listOf(0x1520, 0x1522), transport.opcodes)
        assertTrue(
            transport.gameHexes[0]
                .endsWith("020100000000000000070000000000000063")
        )
        assertTrue(
            transport.gameHexes[1]
                .endsWith("020100000000000000070000000000000063ffffffffffffffff000000")
        )
    }

    @Test
    fun realMineOccupyDoesNotDispatchWithout8520Confirmation() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(0x1520 to listOf(0x9999 to "000000"))
        )
        val mineClient = SessionAwareGameProtocolClient(
            directBinaryTransport = transport::execute
        )
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "mine",
                "generalsJson" to
                    """[{"id":7,"name":"赵云","status":0,"tili":50,"soldierTypeCode":1,"soldierCount":100}]"""
            )
        )
        val mine = MineSearchResult(
            99L,
            MapCoordinate(18, 22),
            MineType.GOLD,
            5,
            1000L,
            true,
            0
        )

        val result = SuspendRunner.run {
            mineClient.occupyMine(session, mine, 7L)
        }

        assertTrue(result is ProtocolResult.Ok)
        assertFalse((result as ProtocolResult.Ok).value.success)
        assertEquals(listOf(0x1520), transport.opcodes)
    }

    @Test
    fun realMineOccupyEncodesAndValidatesEverySelectedGeneral() {
        val transport = ScriptedDirectBinaryTransport(
            mapOf(
                0x1520 to listOf(0x8520 to "000000"),
                0x1522 to listOf(0x8522 to "000000")
            )
        )
        val mineClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "mine",
                "generalsJson" to """[
                    {"id":7,"name":"赵云","status":0,"tili":50,"soldierTypeCode":1,"soldierCount":100},
                    {"id":8,"name":"关羽","status":0,"tili":40,"soldierTypeCode":2,"soldierCount":80}
                ]"""
            )
        )
        val mine = MineSearchResult(99L, MapCoordinate(18, 22), MineType.GOLD, 5, 1000L, true, 0)

        val result = SuspendRunner.run { mineClient.occupyMine(session, mine, listOf(7L, 8L)) }

        assertTrue(result is ProtocolResult.Ok && result.value.success)
        assertEquals(listOf(0x1520, 0x1522), transport.opcodes)
        assertTrue(
            transport.gameHexes[0].endsWith(
                "0202000000000000000700000000000000080000000000000063"
            )
        )
        assertTrue(
            transport.gameHexes[1].endsWith(
                "0202000000000000000700000000000000080000000000000063ffffffffffffffff000000"
            )
        )
    }

    @Test
    fun realMineOccupyBlocksAllNetworkWhenAnySelectedGeneralIsNotReady() {
        val transport = ScriptedDirectBinaryTransport(emptyMap())
        val mineClient = SessionAwareGameProtocolClient(directBinaryTransport = transport::execute)
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "mine",
                "generalsJson" to """[
                    {"id":7,"name":"赵云","status":0,"tili":50,"soldierTypeCode":1,"soldierCount":100},
                    {"id":8,"name":"关羽","status":1,"tili":40,"soldierTypeCode":2,"soldierCount":80}
                ]"""
            )
        )
        val mine = MineSearchResult(99L, MapCoordinate(18, 22), MineType.GOLD, 5, 1000L, true, 0)

        val result = SuspendRunner.run { mineClient.occupyMine(session, mine, listOf(7L, 8L)) }

        assertTrue(result is ProtocolResult.Ok)
        assertFalse((result as ProtocolResult.Ok).value.success)
        assertEquals(emptyList<Int>(), transport.opcodes)
    }

    @Test
    fun realSessionCanReturnRecoveredDailyStepResultWithPayloadShape() {
        val session = realSession(
            extras = mapOf(
                "dailyStepResultsJson" to """[
                    {"step":"SIGN_IN","success":true,"message":"已完成签到！","raw":{"source":"recovered-daily"}}
                ]"""
            )
        )

        val result = SuspendRunner.run { client.runDailyStep(session, DailyStep.SIGN_IN) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("已完成签到！", step.message)
        assertEquals("recovered-daily", step.raw["source"])
        assertEquals("000000000000000000006202", step.raw["payloads"])
        assertFalse(step.raw["payloads"]!!.contains("000000000000000000006200,"))
        assertEquals("已完成签到！", step.raw["successLog"])
        assertEquals("lx + key + gameHex + lb", step.raw["nativeWrapperShape"])
        assertEquals("false", step.raw["dailyWrapperNetworkAllowed"])
        assertEquals("lx,key,lb", step.raw["dailyWrapperMissingFields"])
        assertEquals("1", step.raw["dailyPayloadCount"])
        assertEquals("daily gameHex payloads use lx + key + gameHex + lb dry-run only", step.raw["dailyWrapperEvidence"])
    }

    @Test
    fun realSessionDailyWrapperConsumesImportedNativeFieldsButStillBlocksNetwork() {
        val session = realSession(
            extras = mapOf(
                "nativeWrapperLx" to "lxVALUE",
                "recoveredNativeKey" to "keyVALUE",
                "nativeWrapperLb" to "lbVALUE",
                "dailyStepResultsJson" to """[
                    {"step":"SURPRISE_BOX","success":true,"message":"已领取惊喜宝箱！"}
                ]"""
            )
        )

        val result = SuspendRunner.run { client.runDailyStep(session, DailyStep.SURPRISE_BOX) }

        assertTrue(result is ProtocolResult.Ok)
        val step = (result as ProtocolResult.Ok).value
        assertTrue(step.success)
        assertEquals("", step.raw["dailyWrapperMissingFields"])
        assertEquals("false", step.raw["dailyWrapperNetworkAllowed"])
        assertTrue(step.raw["dailyWrapperMaskedCandidateFirst"]!!.contains("00000000000000000009113400000000000de2b100"))
        assertFalse(step.raw["dailyWrapperMaskedCandidateFirst"]!!.contains("VALUE"))
    }

    @Test
    fun realSessionDailyStepMustMatchRequestedStep() {
        val session = realSession(
            extras = mapOf(
                "dailyStepResultsJson" to """[{"step":"SURPRISE_BOX","success":true}]"""
            )
        )

        val result = SuspendRunner.run { client.runDailyStep(session, DailyStep.SIGN_IN) }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_DAILY_METADATA_NOT_FOUND", (result as ProtocolResult.Err).code)
    }

    @Test
    fun realSessionWithoutDispatchMetadataDoesNotFallBackToMock() {
        val result = SuspendRunner.run {
            client.dispatchFormation(
                realSession(),
                formationId = 3L,
                target = MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name)
            )
        }

        assertTrue(result is ProtocolResult.Err)
        val err = result as ProtocolResult.Err
        assertEquals("REAL_DISPATCH_METADATA_MISSING", err.code)
        assertFalse(err.retryable)
    }

    @Test
    fun realActionDispatchRequiresExplicitBrushYellowScopeWhenBothSendGatesAreOpen() {
        val session = realSession(
            extras = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "formationsJson" to """[{"id":3,"name":"刷黄编队1","generalIds":[7],"status":"IDLE"}]"""
            )
        )

        val result = SuspendRunner.run {
            client.dispatchFormation(
                session,
                formationId = 3L,
                target = MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name)
            )
        }

        assertTrue(result is ProtocolResult.Err)
        val err = result as ProtocolResult.Err
        assertEquals("REAL_ACTION_SCOPE_NOT_CONFIRMED", err.code)
        assertFalse(err.retryable)
        assertTrue(err.message.contains("realActionScope=brush-yellow"))
    }

    @Test
    fun realActionDispatchAcceptsBrushYellowOnlyAliasAndThenRequiresDmBeforeNetworkSend() {
        val session = realSession(
            extras = mapOf(
                "dm" to "",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionBrushYellowOnly" to "true",
                "formationsJson" to """[{"id":3,"name":"刷黄编队1","generalIds":[7],"status":"IDLE"}]"""
            )
        )

        val result = SuspendRunner.run {
            client.dispatchFormation(
                session,
                formationId = 3L,
                target = MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name)
            )
        }

        assertTrue(result is ProtocolResult.Err)
        val err = result as ProtocolResult.Err
        assertEquals("REAL_ACTION_DM_MISSING", err.code)
        assertFalse(err.retryable)
    }

    @Test
    fun realSessionCanReturnRecoveredDispatchResultAndComputedBrushYellowPayloads() {
        val session = realSession(
            extras = mapOf(
                "dispatchResultsJson" to """[
                    {
                      "formationId":3,
                      "targetId":"101",
                      "success":true,
                      "consumedTimes":1,
                      "message":"刷黄出征成功！",
                      "targetIdHex":"0000000000000065",
                      "generalIdHexChunks":["0000000000000001","0000000000000002"],
                      "raw":{"evidence":"p2=0/1520030+1522030"}
                    }
                ]"""
            )
        )
        val target = MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name)

        val result = SuspendRunner.run { client.dispatchFormation(session, 3L, target) }

        assertTrue(result is ProtocolResult.Ok)
        val battle = (result as ProtocolResult.Ok).value
        assertTrue(battle.success)
        assertEquals(1, battle.consumedTimes)
        assertEquals("p2=0/1520030+1522030", battle.raw["evidence"])
        assertEquals("刷黄出征成功！", battle.raw["message"])
        assertEquals("lx + key + gameHex + lb", battle.raw["nativeWrapperShape"])
        assertEquals("application/x-www-form-urlencoded", battle.raw["nativeWrapperContentType"])
        assertEquals("false", battle.raw["prepareWrapperNetworkAllowed"])
        assertEquals("false", battle.raw["expeditionWrapperNetworkAllowed"])
        assertEquals("lx,key,lb", battle.raw["prepareWrapperMissingFields"])
        assertTrue(battle.raw["nativeWrapperBlocker"]!!.contains("禁止真实发送"))
        assertEquals(
            "0000000000000000001a15200a02000000000000000100000000000000020000000000000065",
            battle.raw["preparePayload"]
        )
        assertEquals(
            "0000000000000000002515220a02000000000000000100000000000000020000000000000065ffffffffffffffff000000",
            battle.raw["expeditionPayload"]
        )
        assertEquals("2026-07-08 bridge100 flows #30/#31/#32 and #38/#39", battle.raw["passiveWireEvidence"])
        assertEquals("false", battle.raw["passiveWireNetworkAllowed"])
        assertTrue(battle.raw["passiveWireBlocker"]!!.contains("未进入真实发送 allowlist"))
        assertEquals(
            "0000000000000000001112290200000000000000010000000000000002",
            battle.raw["batchRefill1229GameHex"]
        )
        assertEquals(
            "00000000000000000011122900000200000000000000010000000000000002",
            battle.raw["batchRefill1229CapturedWireTail"]
        )
        assertEquals(
            "0000000000000000001a15200a02000000000000000100000000000000020000000000000065",
            battle.raw["prepare1520GameHex"]
        )
        assertEquals(
            "0000000000000000001a152000000a02000000000000000100000000000000020000000000000065",
            battle.raw["prepare1520CapturedWireTail"]
        )
        assertEquals(
            "0000000000000000002515220a02000000000000000100000000000000020000000000000065ffffffffffffffff000000",
            battle.raw["dispatch1522GameHex"]
        )
        assertEquals(
            "00000000000000000025152200000a02000000000000000100000000000000020000000000000065ffffffffffffffff000000",
            battle.raw["dispatch1522CapturedWireTail"]
        )
    }

    @Test
    fun realSessionDispatchResultCanParseCapturedBrushYellowResponseText() {
        val session = realSession(
            extras = mapOf(
                "dispatchResultsJson" to """[
                    {
                      "formationId":3,
                      "targetId":"101",
                      "responseText":"刷黄出征成功！继续搜索... usedAount=18",
                      "targetIdHex":"0000000000000065",
                      "generalIdHexChunks":["0000000000000001"]
                    }
                ]"""
            )
        )

        val result = SuspendRunner.run {
            client.dispatchFormation(session, 3L, MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name))
        }

        assertTrue(result is ProtocolResult.Ok)
        val battle = (result as ProtocolResult.Ok).value
        assertTrue(battle.success)
        assertEquals(18, battle.consumedTimes)
        assertEquals("true", battle.raw["dispatchResponseSuccess"])
        assertEquals("18", battle.raw["dispatchResponseUsedAount"])
        assertEquals("success-marker:刷黄出征成功", battle.raw["dispatchResponseEvidence"])
        assertEquals("false", battle.raw["expeditionWrapperNetworkAllowed"])
    }

    @Test
    fun realSessionDispatchConsumesToolGeneratedInferredFormationEvidence() {
        val session = realSession(
            extras = mapOf(
                "nativeWrapperLx" to "lxVALUE",
                "nativeWrapperKey" to "keyVALUE",
                "nativeWrapperLb" to "lbVALUE",
                "dispatchResultsJson" to """[
                    {
                      "formationId":3,
                      "targetId":"101",
                      "targetIdHex":"0000000000000065",
                      "generalIdHexChunks":["0000000000000007"],
                      "success":true,
                      "consumedTimes":2,
                      "responseText":"刷黄出征成功！继续搜索... usedAount=2",
                      "raw":{
                        "source":"tools/calibrate_action_responses.py",
                        "opcode":"1522030",
                        "action":"brush-yellow-expedition",
                        "evidence":"success-marker:刷黄出征成功",
                        "formationIdInferred":true
                      }
                    }
                ]"""
            )
        )

        val result = SuspendRunner.run {
            client.dispatchFormation(session, 3L, MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name))
        }

        assertTrue(result is ProtocolResult.Ok)
        val battle = (result as ProtocolResult.Ok).value
        assertTrue(battle.success)
        assertEquals(2, battle.consumedTimes)
        assertEquals("tools/calibrate_action_responses.py", battle.raw["source"])
        assertEquals("1522030", battle.raw["opcode"])
        assertEquals("brush-yellow-expedition", battle.raw["action"])
        assertEquals("true", battle.raw["formationIdInferred"])
        assertEquals("success-marker:刷黄出征成功", battle.raw["dispatchResponseEvidence"])
        assertEquals("", battle.raw["prepareWrapperMissingFields"])
        assertEquals("", battle.raw["expeditionWrapperMissingFields"])
        assertEquals("false", battle.raw["expeditionWrapperNetworkAllowed"])
        val expectedPayloads = BrushYellowDispatchPayloadBuilder.buildBrushYellowPayloads(
            generalIdHexChunks = listOf("0000000000000007"),
            targetIdHex = "0000000000000065"
        )
        assertEquals(
            expectedPayloads.preparePayload,
            battle.raw["preparePayload"]
        )
        assertEquals(
            expectedPayloads.expeditionPayload,
            battle.raw["expeditionPayload"]
        )
    }

    @Test
    fun realSessionDispatchResultCanMatchAliasFieldsAndBuildPayloadFromTargetId() {
        val session = realSession(
            extras = mapOf(
                "dispatchResultsJson" to """[
                    {
                      "bianduihao":"0000000000000003",
                      "targetIdHex":"0000000000000065",
                      "status":"成功",
                      "usedCount":2,
                      "responseBody":"刷黄出征成功！继续搜索... usedCount=2",
                      "generalIdHexChunks":["0000000000000001"]
                    }
                ]"""
            )
        )

        val result = SuspendRunner.run {
            client.dispatchFormation(session, 3L, MapTarget(101L, MapCoordinate(11, 22), "渠帅"))
        }

        assertTrue(result is ProtocolResult.Ok)
        val battle = (result as ProtocolResult.Ok).value
        assertTrue(battle.success)
        assertEquals(2, battle.consumedTimes)
        assertEquals("成功", battle.raw["status"])
        assertEquals("2", battle.raw["usedCount"])
        assertEquals("success-marker:刷黄出征成功", battle.raw["dispatchResponseEvidence"])
        assertEquals(
            BrushYellowDispatchPayloadBuilder.buildBrushYellowPayloads(
                generalIdHexChunks = listOf("0000000000000001"),
                targetIdHex = "0000000000000065"
            ).preparePayload,
            battle.raw["preparePayload"]
        )
        assertEquals("false", battle.raw["expeditionWrapperNetworkAllowed"])
    }

    @Test
    fun realSessionDispatchDoesNotTreatStaleBattleReportAsCurrentSuccess() {
        val session = realSession(
            extras = mapOf(
                "dispatchResultsJson" to """[
                    {
                      "formationId":3,
                      "targetId":"101",
                      "targetIdHex":"0000000000000065",
                      "responseText":"消灭 车1消灭1级山贼(157,42)",
                      "generalIdHexChunks":["0000000000000007"]
                    }
                ]"""
            )
        )

        val result = SuspendRunner.run {
            client.dispatchFormation(session, 3L, MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name))
        }

        assertTrue(result is ProtocolResult.Ok)
        val battle = (result as ProtocolResult.Ok).value
        assertFalse(battle.success)
        assertEquals(0, battle.consumedTimes)
        assertEquals("响应中出现战报成功文本，但未匹配本次目标坐标/ID，已按非本次成功处理", battle.raw["message"])
    }

    @Test
    fun realSessionDispatchWrapperPlanConsumesImportedNativeTraceExtrasButStillBlocksNetwork() {
        val session = realSession(
            extras = mapOf(
                "nativeWrapperLx" to "lxVALUE",
                "recoveredNativeKey" to "keyVALUE",
                "nativeWrapperLb" to "lbVALUE",
                "dispatchResultsJson" to """[
                    {
                      "formationId":3,
                      "targetId":"101",
                      "success":true,
                      "consumedTimes":1,
                      "targetIdHex":"0000000000000065",
                      "generalIdHexChunks":["0000000000000001"],
                      "raw":{"evidence":"imported-native-trace"}
                    }
                ]"""
            )
        )

        val result = SuspendRunner.run {
            client.dispatchFormation(session, 3L, MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name))
        }

        assertTrue(result is ProtocolResult.Ok)
        val battle = (result as ProtocolResult.Ok).value
        assertEquals("", battle.raw["prepareWrapperMissingFields"])
        assertEquals("", battle.raw["expeditionWrapperMissingFields"])
        assertTrue(battle.raw["nativeWrapperMaskedCandidate"]!!.contains("000000000000000000"))
        assertFalse(battle.raw["nativeWrapperMaskedCandidate"]!!.contains("VALUE"))
        assertEquals("false", battle.raw["expeditionWrapperNetworkAllowed"])
    }

    @Test
    fun realSessionDispatchResultMustMatchFormationAndTarget() {
        val session = realSession(
            extras = mapOf(
                "dispatchResultsJson" to """[{"formationId":4,"targetId":"999","success":true,"consumedTimes":1}]"""
            )
        )

        val result = SuspendRunner.run {
            client.dispatchFormation(session, 3L, MapTarget(101L, MapCoordinate(11, 22), HuangTargetType.HUANG_JIN.name))
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_DISPATCH_METADATA_NOT_FOUND", (result as ProtocolResult.Err).code)
    }

    @Test
    fun brushYellowPayloadBuilderUsesRecoveredP2ZeroFormula() {
        val payloads = BrushYellowDispatchPayloadBuilder.buildBrushYellowPayloads(
            generalIdHexChunks = listOf("0000000000000001", "0000000000000002"),
            targetIdHex = "0000000000000065"
        )

        assertEquals(
            "0000000000000000001a15200a02000000000000000100000000000000020000000000000065",
            payloads.preparePayload
        )
        assertEquals(
            "0000000000000000002515220a02000000000000000100000000000000020000000000000065ffffffffffffffff000000",
            payloads.expeditionPayload
        )
    }

    @Test
    fun brushYellowPayloadBuilderCanBuildAllRecoveredP2Variants() {
        val variants = BrushYellowDispatchPayloadBuilder.buildAllBrushYellowPayloadVariants(
            generalIdHexChunks = listOf("0000000000000007"),
            targetIdHex = "0000000000000101"
        )

        assertEquals(listOf(10, 0, 1, 2, 3, 4), variants.map { it.variant })
        assertEquals(
            "0000000000000000001215200a0100000000000000070000000000000101",
            variants[0].preparePayload
        )
        assertEquals(
            "0000000000000000001d15220a0100000000000000070000000000000101ffffffffffffffff000000",
            variants[0].expeditionPayload
        )
        assertEquals(
            "000000000000000000121520030100000000000000070000000000000101",
            variants[1].preparePayload
        )
        assertEquals(
            "0000000000000000001d1522030100000000000000070000000000000101ffffffffffffffff000000",
            variants[1].expeditionPayload
        )
        assertEquals(
            "0000000000000000001215200201000000000000000700000000000000000101",
            variants[2].preparePayload
        )
        assertEquals(
            "0000000000000000001d15220201000000000000000700000000000000000101ffffffffffffffff000000",
            variants[2].expeditionPayload
        )
        assertEquals(
            "0000000000000000001615200e010000000000000007ffffffff00040000000000000101",
            variants[3].preparePayload
        )
        assertEquals(
            "0000000000000000002115220e010000000000000007ffffffff00040000000000000101ffffffffffffffff000000",
            variants[3].expeditionPayload
        )
        assertEquals(
            "000000000000000000101520010100000000000000070000000000000101",
            variants[4].preparePayload
        )
        assertEquals(
            "0000000000000000001b1522010100000000000000070000000000000101ffffffffffffffff000000",
            variants[4].expeditionPayload
        )
        assertEquals(
            "0000000000000000001015200b0100000000000000070000000000000101",
            variants[5].preparePayload
        )
        assertEquals(
            "0000000000000000001b15220b0100000000000000070000000000000101ffffffffffffffff000000",
            variants[5].expeditionPayload
        )
    }

    @Test
    fun realSessionCanUseExplicitLiveGateForSingle041540TargetSearch() {
        val executor = FakeRecoveredReadOnlyExecutor(
            targets = listOf(MapTarget(101L, MapCoordinate(11, 22), "黄巾", raw = mapOf("rank" to "3")))
        )
        val liveClient = SessionAwareGameProtocolClient(recoveredReadOnlyExecutor = executor)
        val session = realSession(
            extras = mapOf(
                "recoveredReadOnlyLiveGate" to "true",
                "gameHttp" to "http://game.example/kingWapServer/HttpClient"
            )
        )

        val result = SuspendRunner.run {
            liveClient.searchMap(session, MapCoordinate(6, 6), MapSearchPolicy(targetType = HuangTargetType.HUANG_JIN))
        }

        assertTrue(result is ProtocolResult.Ok)
        val target = (result as ProtocolResult.Ok).value.single()
        assertEquals(101L, target.id)
        assertEquals("041540", target.raw["liveGate"])
        assertEquals("http://game.example/kingWapServer/HttpClient", executor.calls.single().gameHttp)
        assertEquals(999L, executor.calls.single().dm)
        assertEquals(GameCoordinateCodec.buildTargetSearch(6, 6), executor.calls.single().gameHex)
        assertTrue(executor.calls.single().liveGate)
    }

    @Test
    fun realSessionCanUseExplicitLiveGateForLimitedFull041540Scan() {
        val executor = FakeRecoveredReadOnlyExecutor(
            targets = listOf(MapTarget(101L, MapCoordinate(0, 0), "黄巾"))
        )
        val liveClient = SessionAwareGameProtocolClient(recoveredReadOnlyExecutor = executor)
        val session = realSession(
            extras = mapOf(
                "recoveredReadOnlyLiveGate" to "true",
                "recoveredReadOnlyScanMode" to "FULL",
                "recoveredReadOnlyScanLimit" to "2"
            )
        )

        val result = SuspendRunner.run {
            liveClient.searchMap(session, MapCoordinate(6, 6), MapSearchPolicy(targetType = HuangTargetType.HUANG_JIN))
        }

        assertTrue(result is ProtocolResult.Ok)
        assertEquals(2, executor.calls.size)
        assertEquals(GameCoordinateCodec.buildTargetSearch(0, 0), executor.calls[0].gameHex)
        assertEquals(GameCoordinateCodec.buildTargetSearch(0, 6), executor.calls[1].gameHex)
    }

    @Test
    fun realSessionLiveGateRequiresDmBefore041540NetworkAttempt() {
        val executor = FakeRecoveredReadOnlyExecutor()
        val liveClient = SessionAwareGameProtocolClient(recoveredReadOnlyExecutor = executor)
        val session = realSession(
            extras = mapOf(
                "dm" to "",
                "recoveredReadOnlyLiveGate" to "true"
            )
        )

        val result = SuspendRunner.run {
            liveClient.searchMap(session, MapCoordinate(6, 6), MapSearchPolicy(targetType = HuangTargetType.HUANG_JIN))
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_READONLY_DM_MISSING", (result as ProtocolResult.Err).code)
        assertTrue(executor.calls.isEmpty())
    }

    @Test
    fun realSessionCanUseExplicitLiveGateForSingle041542MineSearch() {
        val executor = FakeRecoveredReadOnlyExecutor(
            mines = listOf(
                MineSearchResult(
                    id = 257L,
                    coordinate = MapCoordinate(11, 22),
                    mineType = MineType.GOLD,
                    level = 5,
                    reserve = 9999L,
                    isEmpty = true,
                    defenseCount = 0
                )
            )
        )
        val liveClient = SessionAwareGameProtocolClient(recoveredReadOnlyExecutor = executor)
        val session = realSession(extras = mapOf("enableRecoveredReadOnlyLive" to "true"))

        val result = SuspendRunner.run {
            liveClient.searchMines(
                session,
                mineConfig(
                    selectedMineTypes = setOf(MineType.GOLD),
                    onlyEmptyMine = true
                ).copy(searchScope = "定点")
            )
        }

        assertTrue(result is ProtocolResult.Ok)
        val mine = (result as ProtocolResult.Ok).value.single()
        assertEquals(257L, mine.id)
        assertEquals("041542", mine.raw["liveGate"])
        assertEquals("http://game.example/kingWapServer/HttpClient", executor.calls.single().gameHttp)
        assertEquals(GameCoordinateCodec.buildResourcePointSearch(0, 0), executor.calls.single().gameHex)
    }

    @Test
    fun realSessionUnrecoveredActionInterfacesNeverFallbackToMockSuccess() {
        val session = realSession()
        val checks = listOf(
            "REAL_CONVERT_NOT_IMPLEMENTED" to SuspendRunner.run {
                client.convertFoodToCopper(session, ConvertMode.FOOD_TO_COPPER_HALF)
            },
            "REAL_HEAL_GATE_CLOSED" to SuspendRunner.run { client.healGeneral(session, 7L) },
            "REAL_ENERGY_GATE_NOT_READY" to SuspendRunner.run { client.addEnergy(session, 7L) },
            "REAL_UPDATE_FORMATION_GATE_CLOSED" to SuspendRunner.run {
                client.updateFormation(
                    session,
                    FormationConfig(
                        formationId = 3L,
                        generalIds = listOf(7L),
                        autoAssignTroops = false,
                        troopType = "步兵",
                        troopCount = 1999,
                        fillToMaxWhenAutoAssignDisabled = true
                    )
                )
            },
            "REAL_INTERNAL_GATE_NOT_READY" to SuspendRunner.run {
                client.runInternalAffairs(
                    session,
                    InternalAffairsConfig(
                        enabled = true,
                        upgradeLowestFirst = true,
                        buildingPriority = listOf(BuildingType.MONEY),
                        buildWhenEmpty = BuildingType.MONEY
                    )
                )
            },
            "REAL_DUNGEON_GATE_NOT_READY" to SuspendRunner.run {
                client.runDungeon(
                    session,
                    DungeonConfig(
                        enabled = true,
                        dailyTimes = 1,
                        boxPosition = 1,
                        chapter = 1,
                        stage = 1,
                        formationIds = listOf(3L),
                        autoUnlockUntilTarget = false
                    )
                )
            },
            "REAL_LOSSLESS_GATE_NOT_READY" to SuspendRunner.run {
                client.runLossless(
                    session,
                    LosslessConfig(
                        enabled = true,
                        fullTroops = true,
                        dailyLimit = 5,
                        rules = listOf(LosslessRule(true, listOf(3L), 10))
                    )
                )
            },
            "REAL_VIP_NOT_IMPLEMENTED" to SuspendRunner.run {
                client.setVipFeature(
                    session,
                    VipFeatureConfig(
                        enabled = true,
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
                )
            },
            "REAL_SURRENDER_RELEASE_NOT_IMPLEMENTED" to SuspendRunner.run {
                client.surrenderOrReleaseGenerals(
                    session,
                    SurrenderReleaseConfig(
                        autoSurrender = true,
                        surrenderGrowthAbove = 80,
                        useGoldForSurrender = false,
                        autoRelease = true,
                        releaseGrowthBelow = 45
                    )
                )
            },
            "REAL_SEND_GENERAL_NOT_IMPLEMENTED" to SuspendRunner.run {
                client.sendGeneralToResourcePoint(
                    session,
                    ResourcePointSendGeneralConfig(
                        enabled = true,
                        target = MapCoordinate(11, 22),
                        generalId = 7L,
                        troopType = "步兵",
                        formationId = 3L,
                        stopAfterMinutes = 30
                    )
                )
            },
            "REAL_LOOT_GATE_NOT_READY" to SuspendRunner.run {
                client.runAutoLoot(
                    session,
                    AutoLootConfig(
                        enabled = true,
                        selectedFormationIds = setOf(3L),
                        targetPlayerName = "测试目标",
                        targetFiefIndex = 1
                    )
                )
            },
            "REAL_BULK_TOOL_NOT_IMPLEMENTED" to SuspendRunner.run {
                client.runBulkToolAction(session, BulkToolAction.GENERAL_TOKEN_ADD_COMMAND)
            },
            "REAL_CITY_SEARCH_NOT_IMPLEMENTED" to SuspendRunner.run {
                client.searchDefendedCities(session, CityDefenseSearchConfig(enabled = true))
            },
            "REAL_TREASURE_SEARCH_NOT_IMPLEMENTED" to SuspendRunner.run {
                client.searchTreasures(
                    session,
                    TreasureFilterConfig(enabledKinds = setOf(TreasureKind.FOOD_STORAGE), nameKeyword = null)
                )
            }
        )

        checks.forEach { (expectedCode, result) ->
            assertTrue("$expectedCode should be an explicit real-session boundary", result is ProtocolResult.Err)
            val err = result as ProtocolResult.Err
            assertEquals(expectedCode, err.code)
            assertFalse("$expectedCode must not be retryable/mock fallback", err.retryable)
        }
    }

    @Test
    fun realAlarmScanBaselinesHistoryThenEmitsOnlyNewMilitaryEvent() {
        val notifications = mutableListOf<com.example.dwpmclone.domain.model.AlarmNotificationEvent>()
        val alarmClient = SessionAwareGameProtocolClient(alarmEventSink = notifications::add)
        val baseline = realSession(
            extras = mapOf(
                "militaryIntelJson" to """{"events":[
                    {"timeText":"12:00","text":"赵云出征","state":"出征"}
                ]}"""
            )
        )
        val updated = realSession(
            extras = mapOf(
                "militaryIntelJson" to """{"events":[
                    {"timeText":"12:00","text":"赵云出征","state":"出征"},
                    {"timeText":"12:01","text":"敌军正在掠夺基地","state":"征"}
                ]}"""
            )
        )
        val config = AlarmWithdrawConfig(enabled = true)

        val first = SuspendRunner.run { alarmClient.scanAlarmAndMaybeWithdraw(baseline, config) }
        val second = SuspendRunner.run { alarmClient.scanAlarmAndMaybeWithdraw(updated, config) }

        assertTrue(first is ProtocolResult.Ok)
        assertTrue(second is ProtocolResult.Ok)
        assertTrue((first as ProtocolResult.Ok).value.message.contains("基线"))
        assertEquals("1", (second as ProtocolResult.Ok).value.raw["newEvents"])
        assertEquals(1, notifications.size)
        assertEquals("敌军正在掠夺基地", notifications.single().text)
        assertEquals(com.example.dwpmclone.domain.model.AlarmNotificationKind.INCOMING, notifications.single().kind)
    }

    @Test
    fun realAlarmScanActivelyQueries3110AndPersistsA110SnapshotWhenGateEnabled() {
        val text = "蜀汉在县城陈仓击败南楚，国王刘备奋力守城。"
        val payload = heartbeatPayload(888_888L, 999_999L, text)
        val persisted = mutableListOf<Map<String, String>>()
        val heartbeat = object : Heartbeat3110Executor {
            override fun execute(
                gameHttp: String,
                dm: Long
            ): RealGameProtocolClient.Heartbeat3110Result {
                assertEquals("http://game.example/kingWapServer/HttpClient", gameHttp)
                assertEquals(999L, dm)
                return RealGameProtocolClient.Heartbeat3110Result(
                    responseOpcodes = listOf("0xa110"),
                    responsePayloadHex = payload
                )
            }
        }
        val alarmClient = SessionAwareGameProtocolClient(
            sessionExtraSink = { _, updates -> persisted += updates },
            heartbeat3110Executor = heartbeat
        )
        val session = realSession(extras = mapOf("militaryIntelLiveGate" to "true"))

        val result = SuspendRunner.run {
            alarmClient.scanAlarmAndMaybeWithdraw(session, AlarmWithdrawConfig(enabled = true))
        }

        assertTrue(result is ProtocolResult.Ok)
        assertEquals(1, persisted.size)
        assertEquals("888888", persisted.single()["copper"])
        assertEquals("999999", persisted.single()["food"])
        assertTrue(persisted.single()["militaryIntelJson"].orEmpty().contains(text))
        assertEquals("0x3110/0xa110", persisted.single()["militaryIntelSourceOpcode"])
    }

    @Test
    fun realAlarmScanTurnsCapturedFffcHeartbeatIntoExplicitSessionFailure() {
        val heartbeat = object : Heartbeat3110Executor {
            override fun execute(
                gameHttp: String,
                dm: Long
            ) = RealGameProtocolClient.Heartbeat3110Result(
                responseOpcodes = listOf("0xa110"),
                responsePayloadHex = "0101aabbccfffc0000"
            )
        }
        val alarmClient = SessionAwareGameProtocolClient(heartbeat3110Executor = heartbeat)
        val session = realSession(extras = mapOf("militaryIntelLiveGate" to "true"))

        val result = SuspendRunner.run {
            alarmClient.scanAlarmAndMaybeWithdraw(session, AlarmWithdrawConfig(enabled = true))
        }

        assertTrue(result is ProtocolResult.Err)
        assertEquals("REAL_HEARTBEAT_SESSION_INVALID", (result as ProtocolResult.Err).code)
        assertFalse(result.retryable)
    }

    @Test
    fun mockSessionStillSupportsLocalSmokeBehavior() {
        val result = SuspendRunner.run {
            client.queryResourceState(GameSession(1L, "mock", null, emptyMap(), sourceMode = 0))
        }

        assertTrue(result is ProtocolResult.Ok)
        assertEquals(1_000_000L, (result as ProtocolResult.Ok).value.copper)
    }

    @Test
    fun realSessionCanReplayRecoveredDailyFoodConversionWithoutMockFallback() {
        val session = realSession(
            extras = mapOf(
                "dailyStepResultsJson" to """[
                    {"step":"CONVERT_HALF_FOOD_TO_COPPER","success":true,"message":"已转换一半粮食到铜钱！"}
                ]""",
                "convertedResourceStateJson" to """{"copper":999999,"food":111111}"""
            )
        )

        val result = SuspendRunner.run { client.convertFoodToCopper(session, ConvertMode.FOOD_TO_COPPER_HALF) }

        assertTrue(result is ProtocolResult.Ok)
        val state = (result as ProtocolResult.Ok).value
        assertEquals(999999L, state.copper)
        assertEquals(111111L, state.food)
        assertEquals("converted-resource-state-metadata", state.raw["convertEvidence"])
        assertEquals("false", state.raw["networkSendAllowed"])
    }



    private fun unitMine(): MineSearchResult = MineSearchResult(
        id = 257L,
        coordinate = MapCoordinate(11, 22),
        mineType = MineType.GOLD,
        level = 5,
        reserve = 9999L,
        isEmpty = true,
        defenseCount = 0,
        raw = mapOf("idHex" to "0000000000000101")
    )

    private fun mineConfig(
        selectedMineTypes: Set<MineType> = emptySet(),
        onlyEmptyMine: Boolean = false,
        onlyDefendedMine: Boolean = false
    ): MineConfig = MineConfig(
        enabled = true,
        start = MapCoordinate(0, 0),
        hitEmptyMine = true,
        withdrawDefense = false,
        resourcePointLimit = 5,
        selectedMineTypes = selectedMineTypes,
        acceleratedMineTypes = emptySet(),
        selectedFormationIds = setOf(1L),
        backgroundSearch = true,
        searchIntervalMinutes = 12,
        reloginOnDisconnect = false,
        stopOnDisconnect = false,
        vibrateOnEmptyGold = false,
        vibrateOnEmptyRare = false,
        onlyEmptyMine = onlyEmptyMine,
        onlyDefendedMine = onlyDefendedMine
    )

    private fun realSession(extras: Map<String, String> = emptyMap()): GameSession = GameSession(
        accountId = 10001L,
        tokenCiphertext = "real-session-token",
        expiresAtMillis = null,
        channelExtra = mapOf(
            "userId" to "u10001",
            "serverUrl" to "http://game.example",
            "dm" to "999",
            "roleName" to "测试君主",
            "level" to "42",
            "nation" to "蜀",
            "copper" to "123456",
            "food" to "654321"
        ) + extras,
        sourceMode = 1
    )

    private fun dungeonSession(status: Int): GameSession = realSession(
        extras = mapOf(
            "realActionNetworkAllowed" to "true",
            "realActionSendReady" to "true",
            "realActionScopes" to "dungeon",
            "generalsJson" to """
                [{"id":7,"name":"赵云","growth":90,"loyalty":100,"energy":88,"status":$status}]
            """.trimIndent(),
            "formationsJson" to """
                [{"id":7,"name":"副本编队","generalIds":[7],"status":"IDLE","troopCount":1999}]
            """.trimIndent()
        )
    )

    private fun dungeonConfig(): DungeonConfig = DungeonConfig(
        enabled = true,
        dailyTimes = 5,
        boxPosition = 2,
        chapter = 0,
        stage = 5,
        formationIds = listOf(7L),
        autoUnlockUntilTarget = false
    )

    private fun heartbeatPayload(copper: Long, food: Long, text: String): String {
        val bytes = ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeByte(1)
                out.writeLong(copper)
                out.writeLong(food)
                out.write(ByteArray(62))
                val encoded = text.toByteArray(Charsets.UTF_8)
                out.writeShort(encoded.size)
                out.write(encoded)
            }
        }.toByteArray()
        return bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun ownedFiefListPayload(roleName: String, fiefId: Long): ByteArray =
        ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeShort(0)
                out.writeUTF(roleName)
                out.writeUTF(roleName)
                out.writeByte(1)
                out.writeLong(fiefId)
                out.writeUTF("自有封地")
                out.writeByte(0)
                out.writeUTF("测试城")
                out.write(ByteArray(5))
            }
        }.toByteArray()

    private fun fiefStatePayload(
        fiefId: Long,
        hallLevel: Int,
        academyLevel: Int? = null
    ): ByteArray =
        ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeByte(0)
                out.writeLong(fiefId)
                out.writeByte(1)
                out.writeByte(0)
                out.writeUTF("测试封地")
                out.writeLong(0)
                out.writeInt(0)
                out.writeInt(0)
                out.writeShort(0)
                out.writeShort(0)
                out.writeByte(2)
                out.writeShort(0)
                out.writeShort(0)
                out.writeByte(0)
                repeat(5) { out.writeByte(0) }
                writeBuildingList(out, hallLevel, academyLevel)
            }
        }.toByteArray()

    private fun buildingActionPayload(
        fiefId: Long,
        hallLevel: Int,
        status: Int = 0
    ): ByteArray =
        ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeByte(status)
                out.writeByte(0)
                out.writeLong(fiefId)
                writeBuildingList(out, hallLevel, academyLevel = null)
            }
        }.toByteArray()

    private fun writeBuildingList(
        out: DataOutputStream,
        hallLevel: Int,
        academyLevel: Int?
    ) {
        out.writeByte(if (academyLevel == null) 2 else 3)
        fun record(slot: Int, instanceId: Long, type: Int, level: Int) {
            out.writeByte(slot)
            out.writeLong(instanceId)
            out.writeByte(type)
            out.writeByte(level)
            out.writeInt(0)
            out.writeInt(0)
            out.writeLong(0)
            out.writeByte(0)
            out.writeLong(instanceId)
        }
        record(0, 100, 0, hallLevel)
        record(1, 101, 1, 1)
        academyLevel?.let { record(3, 200, 3, it) }
    }

    private fun technologyStatePayload(
        levels: Map<Int, Int> = emptyMap(),
        researching: Set<Int> = emptySet()
    ): ByteArray = ByteArrayOutputStream().also { bos ->
        DataOutputStream(bos).use { out ->
            out.write(ByteArray(7) { 0x55 })
            repeat(22) { technologyId ->
                out.writeByte(technologyId)
                out.writeByte(levels[technologyId] ?: 0)
                out.writeByte(if (technologyId in researching) 0 else 2)
                if (technologyId in researching) {
                    out.writeLong(0x0a79)
                    out.writeLong(200)
                    out.writeLong(123456789)
                } else {
                    out.writeLong(-1)
                    out.writeLong(-1)
                    out.writeLong(0)
                }
            }
            out.writeByte(0x33)
        }
    }.toByteArray()

    private fun ByteArray.testHex(): String =
        joinToString("") { "%02x".format(it.toInt() and 0xff) }

    companion object {
        private const val CAPTURED_DUNGEON_CATALOG =
            "000700000f130f010f12000ce5b1b1e8b4bce4b98be4b9b1010c00000103000101010002010100040101000501ff000600ff000700ff000800ff000900ff000a00ff000b00ff000c00ff00010f150efc0ef70009e7acace4ba8ce7aba00000020f180efe0efb000ce995bfe5ae89e4b98be4b9b10000030f1a0f000ef9000ce5be90e5b79ee4b98be4ba8900000410b1106010b0000ce4bcaae5b89de8a281e69caf0000051aaa1a931a8f0015e5ae98e6b8a1e4b98be68898efbc88e4b88aefbc890000061aaa1a941a910015e5ae98e6b8a1e4b98be68898efbc88e4b88befbc8900"
    }
}

private class ScriptedDirectBinaryTransport(
    private val responses: Map<Int, List<Pair<Int, String>>>
) {
    val opcodes = mutableListOf<Int>()
    val gameHexes = mutableListOf<String>()

    fun execute(
        gameHttp: String,
        dm: Long,
        gameHex: String,
        phase: String
    ): DirectBinaryResponse {
        check(gameHttp.isNotBlank())
        check(dm > 0)
        val normalized = gameHex.filterNot(Char::isWhitespace).lowercase()
        val opcode = normalized.substring(20, 24).toInt(16)
        opcodes += opcode
        gameHexes += normalized
        val scripted = responses[opcode] ?: error("unexpected opcode 0x${opcode.toString(16)}")
        return DirectBinaryResponse(
            phase = phase,
            httpCode = 200,
            ok = true,
            responseBytes = scripted.sumOf { it.second.length / 2 },
            responseHex = scripted.joinToString("") { it.second },
            textPreview = "",
            responseOpcodes = scripted.map { it.first }
        )
    }
}

private class SequentialDirectBinaryTransport(
    private val responses: Map<Int, List<List<Pair<Int, String>>>>
) {
    val opcodes = mutableListOf<Int>()
    val gameHexes = mutableListOf<String>()
    private val cursors = mutableMapOf<Int, Int>()

    fun execute(
        gameHttp: String,
        dm: Long,
        gameHex: String,
        phase: String
    ): DirectBinaryResponse {
        check(gameHttp.isNotBlank())
        check(dm > 0)
        val normalized = gameHex.filterNot(Char::isWhitespace).lowercase()
        val opcode = normalized.substring(20, 24).toInt(16)
        opcodes += opcode
        gameHexes += normalized
        val sequence = responses[opcode] ?: error("unexpected opcode 0x${opcode.toString(16)}")
        val cursor = cursors.getOrDefault(opcode, 0)
        check(cursor < sequence.size) { "no scripted response left for 0x${opcode.toString(16)}" }
        cursors[opcode] = cursor + 1
        val scripted = sequence[cursor]
        return DirectBinaryResponse(
            phase = phase,
            httpCode = 200,
            ok = true,
            responseBytes = scripted.sumOf { it.second.length / 2 },
            responseHex = scripted.joinToString("") { it.second },
            textPreview = "",
            responseOpcodes = scripted.map { it.first }
        )
    }
}

private class FakeRecoveredReadOnlyExecutor(
    private val targets: List<MapTarget> = emptyList(),
    private val mines: List<MineSearchResult> = emptyList(),
    private val success: Boolean = true
) : RecoveredReadOnlyExecutor {
    data class Call(val gameHttp: String, val dm: Long, val gameHex: String, val liveGate: Boolean)

    val calls = mutableListOf<Call>()
    private val planner = RealGameProtocolClient()

    override fun execute(
        gameHttp: String,
        dm: Long,
        gameHex: String,
        liveGate: Boolean
    ): RealGameProtocolClient.RecoveredReadOnlyExecutionResult {
        calls += Call(gameHttp, dm, gameHex, liveGate)
        return RealGameProtocolClient.RecoveredReadOnlyExecutionResult(
            plan = planner.planRecoveredReadOnlyGameHex(gameHex, dm),
            networkSendAttempted = liveGate,
            success = success,
            code = if (success) "READ_ONLY_EXECUTED" else "READ_ONLY_FAILED",
            message = if (success) "fake live read-only result" else "fake failure",
            responseOpcodes = if (success) listOf("0x1540") else emptyList(),
            parsedTargets = targets,
            parsedMines = mines
        )
    }
}

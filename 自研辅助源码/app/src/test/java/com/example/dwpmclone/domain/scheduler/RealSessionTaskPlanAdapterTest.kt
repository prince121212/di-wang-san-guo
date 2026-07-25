package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RealSessionTaskPlanAdapterTest {
    @Test
    fun recoversShuaHuangFormationIdsFromNestedXiaohuangPrefs() {
        val ids = RealSessionTaskPlanAdapter.recoverShuaHuangFormationIds(fullOfflineReplayChannelExtraSample())

        assertEquals(setOf(3L), ids)
    }

    @Test
    fun alignsSavedUiPlanWithRealSessionFormationAndTargetMetadata() {
        val savedPlan = SavedConfigTaskPlanFactory.plan(10001L, shuaHuangSavedConfigExport())
        val originalShua = savedPlan.tasks.single { it.type == TaskType.SHUA_HUANG } as ShuaHuangTask
        val realSession = GameSession(
            accountId = 10001L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            channelExtra = fullOfflineReplayChannelExtraSample(),
            sourceMode = 1
        )

        val aligned = RealSessionTaskPlanAdapter.attachRealSession(savedPlan, realSession)
        val alignedShua = aligned.tasks.single { it.type == TaskType.SHUA_HUANG } as ShuaHuangTask

        assertEquals(setOf(1L), originalShua.config.selectedFormationIds)
        assertEquals(setOf(3L), alignedShua.config.selectedFormationIds)
        assertEquals(HuangTargetType.HUANG_JIN, alignedShua.config.targetType)
        assertEquals(1, aligned.session.sourceMode)
        assertTrue(aligned.sourceDescription.contains("session-metadata-aligned"))
    }

    @Test
    fun alignedSavedUiPlanRunsBrushYellowClosedLoopThroughServiceLifecycleRunner() {
        val savedPlan = SavedConfigTaskPlanFactory.plan(10001L, shuaHuangSavedConfigExport())
        val realSession = GameSession(
            accountId = 10001L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            channelExtra = fullOfflineReplayChannelExtraSample(),
            sourceMode = 1
        )
        val aligned = RealSessionTaskPlanAdapter.attachRealSession(savedPlan, realSession)
        val runner = LocalSchedulerLifecycleRunner(TaskScheduler(SessionAwareGameProtocolClient()))

        val batch = SuspendRunner.run {
            runner.runPlansOnceAndStopOnTerminal(tick = 12, plans = listOf(aligned), nowMillis = 1_000L)
        }

        assertEquals(1, batch.runReports.size)
        assertEquals(TaskType.SHUA_HUANG, batch.runReports.single().type)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000)), batch.runReports.single().decisions)
        assertEquals(emptyList<TerminalTaskDecision>(), batch.terminalDecisions)
        assertEquals(emptyList<TaskStopReport>(), batch.stopReports)
    }


    @Test
    fun realSessionWithoutSavedConfigDoesNotRunSyntheticDefaultTasks() {
        val savedPlan = SavedConfigTaskPlanFactory.plan(764L, JSONObject().put("schema_version", "0.1-static-mock").put("configs", JSONObject()))
        val realSession = GameSession(
            accountId = 764L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            channelExtra = mapOf("serverUrl" to "http://game.example", "dm" to "999", "roleId" to "764"),
            sourceMode = 1
        )

        val aligned = RealSessionTaskPlanAdapter.attachRealSession(savedPlan, realSession)

        assertEquals(1, aligned.session.sourceMode)
        assertEquals(emptyList<TaskType>(), aligned.tasks.map { it.type })
        assertTrue(aligned.sourceDescription.contains("no-background-tasks"))
    }

    @Test
    fun realSessionWithoutSavedConfigDerivesBrushYellowTaskOnlyWhenExplicitGateAndFormationExist() {
        val savedPlan = SavedConfigTaskPlanFactory.plan(764L, JSONObject().put("schema_version", "0.1-static-mock").put("configs", JSONObject()))
        val realSession = GameSession(
            accountId = 764L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            channelExtra = mapOf(
                "serverUrl" to "http://game.example",
                "dm" to "999",
                "roleId" to "764",
                "selectedFormationIds" to "7066185",
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "brush-yellow",
                "shuaHuangDailyLimit" to "1"
            ),
            sourceMode = 1
        )

        val aligned = RealSessionTaskPlanAdapter.attachRealSession(savedPlan, realSession)
        val task = aligned.tasks.single() as ShuaHuangTask

        assertEquals(1, aligned.session.sourceMode)
        assertEquals(TaskType.SHUA_HUANG, task.type)
        assertEquals(setOf(7066185L), task.config.selectedFormationIds)
        assertEquals(1, task.config.dailyLimit)
        assertTrue(aligned.sourceDescription.contains("session-derived-brush-yellow-task"))
    }

    private fun shuaHuangSavedConfigExport(): JSONObject = JSONObject()
        .put("schema_version", "0.1-static-mock")
        .put(
            "configs",
            JSONObject().put(
                "10001::shua_huang",
                JSONObject().put(
                    "values",
                    JSONObject()
                        .put("APKTOOL_RENAMED_0x7f070073", true)
                        .put("APKTOOL_RENAMED_0x7f070163", 500)
                        .put("APKTOOL_RENAMED_0x7f070165", 11)
                        .put("APKTOOL_RENAMED_0x7f070166", 22)
                        .put("APKTOOL_RENAMED_0x7f070164", 1)
                        .put("APKTOOL_RENAMED_0x7f070188", true)
                )
            )
        )

    private fun fullOfflineReplayChannelExtraSample(): Map<String, String> = mapOf(
        "sourceMode" to "1",
        "userId" to "sample-user-10001",
        "serverUrl" to "http://game.example",
        "dm" to "999",
        "roleName" to "样本君主",
        "level" to "42",
        "nation" to "蜀",
        "copper" to "1234567",
        "food" to "6543210",
        "prestige" to "98765",
        "state8004TailUtf8Preview" to "君主名=样本君主|君主等级=42|国家=蜀|铜钱=1234567|粮食=6543210|" +
            "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49,daiBingLimit=1999,isPeiBingFail=false}",
        "xiaohuangPrefsJson" to """{"shuahuangChuzhengBiandui0":true,"bianduihao0":"0000000000000003","bianduiDejiangling0":"0000000000000007","bingli0":"1999"}""",
        "mapTargetsJson" to """[
            {"targetIdHex":"0000000000000065","coordX":11,"coordY":22,"targetKind":"渠帅","targetLevel":11,"rawRecord":"sample-041540-huang-target"},
            {"targetID":"102","kv":33,"kw":44,"kind":"山贼","level":4}
        ]""",
        "dispatchResultsJson" to """[
            {
                "bianduihao":"0000000000000003",
                "targetIdHex":"0000000000000065",
                "targetId":"101",
                "status":"成功",
                "usedCount":1,
                "responseBody":"刷黄出征成功！继续搜索... usedCount=1",
                "generalIdHexChunks":["0000000000000007"]
            }
        ]""",
        "selectedFormationIds" to "3",
        "shuaHuangTargetType" to "HUANG_JIN",
        "networkSendAllowed" to "false",
        "realActionNetworkAllowed" to "false",
        "nativeWrapperNetworkSendAllowed" to "false"
    )
}

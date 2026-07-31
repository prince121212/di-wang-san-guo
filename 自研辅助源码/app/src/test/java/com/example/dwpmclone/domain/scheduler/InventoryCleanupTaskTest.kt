package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.EquipmentQuality
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.InventoryConfig
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.InventoryAction
import com.example.dwpmclone.domain.protocol.InventoryItem
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryCleanupTaskTest {
    @Test
    fun equipmentDiscardRequiresCompleteMetadataAndPreservesProtectedInstances() {
        val calls = mutableListOf<Pair<Long, InventoryAction>>()
        val equipment = listOf(
            InventoryItem(
                0xC95F8L, "短剑", "equipment", EquipmentQuality.GOOD, 1,
                enhanced = false, equipped = false, templateId = 0,
                equipmentMetadataComplete = true
            ),
            InventoryItem(
                2L, "名品", "equipment", EquipmentQuality.NORMAL, 1,
                enhanced = false, equipped = false, famous = true,
                equipmentMetadataComplete = true
            ),
            InventoryItem(
                3L, "强化装备", "equipment", EquipmentQuality.NORMAL, 1,
                enhanced = true, equipped = false, equipmentMetadataComplete = true
            ),
            InventoryItem(
                4L, "炼魂装备", "equipment", EquipmentQuality.NORMAL, 1,
                enhanced = false, equipped = false, extraText = "炼魂+1",
                equipmentMetadataComplete = true
            ),
            InventoryItem(
                5L, "高等级装备", "equipment", EquipmentQuality.NORMAL, 80,
                enhanced = false, equipped = false, equipmentMetadataComplete = true
            ),
            InventoryItem(
                6L, "未知装备", "equipment", EquipmentQuality.NORMAL, 1,
                enhanced = false, equipped = false, equipmentMetadataComplete = false
            )
        )
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryInventory(session: GameSession) = ProtocolResult.Ok(equipment)

            override suspend fun useOrDiscardItem(
                session: GameSession,
                itemId: Long,
                action: InventoryAction,
                count: Int
            ): ProtocolResult<StepResult> {
                calls += itemId to action
                return ProtocolResult.Ok(StepResult(true, "ok"))
            }
        }
        val task = InventoryCleanupTask(
            77L,
            InventoryConfig(
                enabled = true,
                openBoxes = false,
                openSilverTickets = false,
                discardEquipmentQualities = setOf(EquipmentQuality.NORMAL, EquipmentQuality.GOOD),
                discardBelowLevel = 100,
                discardItems = emptySet()
            )
        )

        SuspendRunner.run {
            task.step(TaskContext(GameSession(77L, "token", null, emptyMap(), 1), protocol, 1_000L))
        }

        assertEquals(listOf(0xC95F8L to InventoryAction.DISCARD_EQUIPMENT), calls)
    }

    @Test
    fun rejectedUseReceiptStopsImmediatelyAndDoesNotTouchNextSelectedItem() {
        val calls = mutableListOf<Long>()
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryInventory(session: GameSession) = ProtocolResult.Ok(
                listOf(
                    InventoryItem(50L, "50两银票", "silver-ticket", null, null, false, false, 1),
                    InventoryItem(100L, "100两银票", "silver-ticket", null, null, false, false, 1)
                )
            )

            override suspend fun useOrDiscardItem(
                session: GameSession,
                itemId: Long,
                action: InventoryAction,
                count: Int
            ): ProtocolResult<StepResult> {
                calls += itemId
                return ProtocolResult.Ok(StepResult(false, "服务器拒绝使用"))
            }
        }
        val task = InventoryCleanupTask(
            77L,
            InventoryConfig(
                enabled = true,
                openBoxes = false,
                openSilverTickets = true,
                autoOpenItemNames = setOf("50两银票", "100两银票"),
                discardEquipmentQualities = emptySet<EquipmentQuality>(),
                discardBelowLevel = null,
                discardItems = emptySet()
            )
        )

        val decision = SuspendRunner.run {
            task.step(TaskContext(GameSession(77L, "token", null, emptyMap(), 1), protocol, nowMillis = 1_000L))
        }

        assertTrue(decision is TaskDecision.Stop)
        assertEquals("服务器拒绝使用", (decision as TaskDecision.Stop).reason)
        assertEquals(listOf(50L), calls)
    }

    @Test
    fun retryableTransportFailureReturnsRetryWithoutTouchingNextItem() {
        val calls = mutableListOf<Long>()
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryInventory(session: GameSession) = ProtocolResult.Ok(
                listOf(
                    InventoryItem(58L, "惊喜宝箱", "box", null, null, false, false, 1),
                    InventoryItem(59L, "实木宝箱", "box", null, null, false, false, 1)
                )
            )

            override suspend fun useOrDiscardItem(
                session: GameSession,
                itemId: Long,
                action: InventoryAction,
                count: Int
            ): ProtocolResult<StepResult> {
                calls += itemId
                return ProtocolResult.Err("NETWORK", "临时网络失败", retryable = true)
            }
        }
        val task = InventoryCleanupTask(
            77L,
            InventoryConfig(
                enabled = true,
                openBoxes = true,
                openSilverTickets = false,
                autoOpenItemNames = setOf("惊喜宝箱", "实木宝箱"),
                discardEquipmentQualities = emptySet(),
                discardBelowLevel = null,
                discardItems = emptySet()
            )
        )

        val decision = SuspendRunner.run {
            task.step(TaskContext(GameSession(77L, "token", null, emptyMap(), 1), protocol, nowMillis = 1_000L))
        }

        assertEquals(TaskDecision.RetryAfter(BaseAssistantTask.DEFAULT_RETRY_MS), decision)
        assertEquals(listOf(58L), calls)
    }
}

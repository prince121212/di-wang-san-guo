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
        val task = InventoryCleanupMockTask(
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
        val task = InventoryCleanupMockTask(
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

        assertEquals(TaskDecision.RetryAfter(BaseMockTask.DEFAULT_RETRY_MS), decision)
        assertEquals(listOf(58L), calls)
    }
}

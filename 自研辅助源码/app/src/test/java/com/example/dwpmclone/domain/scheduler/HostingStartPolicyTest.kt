package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.Channel
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.GameVersion
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HostingStartPolicyTest {
    @Test
    fun deniesStartWithoutEnabledRealReadOnlySession() {
        assertFalse(HostingStartPolicy.evaluate(emptyList()).allowed)
        assertFalse(HostingStartPolicy.evaluate(listOf(account(session = null))).allowed)
        assertFalse(HostingStartPolicy.evaluate(listOf(account(session = session(sourceMode = 0)))).allowed)
    }

    @Test
    fun allowsStartWithRealSessionAndSafeNetworkFlags() {
        val decision = HostingStartPolicy.evaluate(
            listOf(
                account(
                    session = session(
                        sourceMode = 1,
                        extra = mapOf(
                            "networkSendAllowed" to "false",
                            "realActionNetworkAllowed" to "false",
                            "nativeWrapperNetworkSendAllowed" to "false"
                        )
                    )
                )
            )
        )

        assertTrue(decision.allowed)
        assertTrue(decision.message.contains("真实 session"))
    }

    @Test
    fun deniesStartWhenRealActionNetworkAllowedWithoutBrushYellowScopeConfirmation() {
        val decision = HostingStartPolicy.evaluate(
            listOf(account(session = session(sourceMode = 1, extra = mapOf("realActionNetworkAllowed" to "true", "realActionSendReady" to "true"))))
        )

        assertFalse(decision.allowed)
        assertTrue(decision.message.contains("已阻止"))
    }

    @Test
    fun allowsStartWhenBrushYellowRealActionGateIsExplicitlyConfirmed() {
        val decision = HostingStartPolicy.evaluate(
            listOf(account(session = session(sourceMode = 1, extra = mapOf(
                "realActionNetworkAllowed" to "true",
                "realActionSendReady" to "true",
                "realActionScope" to "brush-yellow"
            ))))
        )

        assertTrue(decision.allowed)
        assertTrue(decision.message.contains("刷黄真实动作 gate 已确认"))
    }

    private fun account(session: GameSession?, enabled: Boolean = true): GameAccount = GameAccount(
        id = 10001L,
        displayName = "测试账号",
        username = "user",
        serverName = "测试区",
        gameVersion = GameVersion.OTHER,
        channel = Channel.UNKNOWN,
        session = session,
        enabled = enabled
    )

    private fun session(sourceMode: Int, extra: Map<String, String> = emptyMap()): GameSession = GameSession(
        accountId = 10001L,
        tokenCiphertext = "token",
        expiresAtMillis = null,
        channelExtra = extra,
        sourceMode = sourceMode
    )
}

package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.GameAccount

/** UI-facing safety gate for starting the local foreground scheduler. */
object HostingStartPolicy {
    private val hardBlockedNetworkFlagKeys = setOf(
        "networkSendAllowed",
        "nativeWrapperNetworkSendAllowed",
        "deviceRegressionNetworkSendAllowed",
        "actionResponseCalibrationNetworkSendAllowed",
        "sampleNetworkSendAllowed"
    )

    fun evaluate(accounts: List<GameAccount>): HostingStartDecision {
        val enabled = accounts.filter { it.enabled }
        if (enabled.isEmpty()) {
            return HostingStartDecision(false, "没有启用账号，不能启动后台托管")
        }
        val realSessionAccounts = enabled.filter { it.session?.sourceMode == 1 }
        if (realSessionAccounts.isEmpty()) {
            return HostingStartDecision(false, "没有 sourceMode=1 的真实只读 session，不能启动后台托管")
        }
        val unsafe = realSessionAccounts.firstOrNull { account ->
            val extra = account.session?.channelExtra.orEmpty()
            hardBlockedNetworkFlagKeys.any { key -> extra[key].equals("true", ignoreCase = true) } ||
                (extra["realActionNetworkAllowed"].equals("true", ignoreCase = true) && !brushYellowRealActionGateReady(extra))
        }
        if (unsafe != null) {
            return HostingStartDecision(false, "账号 ${unsafe.id} 存在未确认的真实网络/动作开关=true，已阻止后台托管")
        }
        val actionReady = realSessionAccounts.any { brushYellowRealActionGateReady(it.session?.channelExtra.orEmpty()) }
        val suffix = if (actionReady) "；刷黄真实动作 gate 已确认" else "；真实动作发送仍由协议 gate 禁止"
        return HostingStartDecision(true, "允许启动本地调度：${realSessionAccounts.size} 个真实只读 session$suffix")
    }

    private fun brushYellowRealActionGateReady(extra: Map<String, String>): Boolean =
        extra["realActionNetworkAllowed"].equals("true", ignoreCase = true) &&
            extra["realActionSendReady"].equals("true", ignoreCase = true) &&
            (
                extra["realActionScope"].equals("brush-yellow", ignoreCase = true) ||
                    extra["realActionBrushYellowOnly"].equals("true", ignoreCase = true)
                )

}

data class HostingStartDecision(
    val allowed: Boolean,
    val message: String
)

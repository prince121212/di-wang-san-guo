package com.example.dwpmclone.domain.protocol

/**
 * Small domain-level formatter for protocol evidence that can be written to task logs
 * or shown in a diagnostics page without depending on Android UI classes.
 */
object ProtocolDiagnosticsReportBuilder {
    fun rankListSummary(response: RankListResponse, maxEntries: Int = 5): String {
        val names = response.entries
            .take(maxEntries)
            .joinToString(separator = "、") { "${it.rank}.${it.name}=${it.scoreHex}" }
            .ifBlank { "empty" }
        return "1170-rank entries=${response.entries.size} $names evidence=${response.evidence}"
    }

    fun brushYellowWireSummary(raw: Map<String, String>): String? {
        val evidence = raw["passiveWireEvidence"] ?: raw["payloadEvidence"] ?: return null
        val networkAllowed = raw["passiveWireNetworkAllowed"] ?: raw["expeditionWrapperNetworkAllowed"] ?: "false"
        val refill = raw["batchRefill1229CapturedWireTail"]?.take(48).orEmpty()
        val prepare = raw["prepare1520CapturedWireTail"]?.take(48).orEmpty()
        val dispatch = raw["dispatch1522CapturedWireTail"]?.take(48).orEmpty()
        return "dispatch-dry-run evidence=$evidence networkAllowed=$networkAllowed " +
            "1229=${refill.ifBlank { "n/a" }} 1520=${prepare.ifBlank { "n/a" }} 1522=${dispatch.ifBlank { "n/a" }}"
    }

    fun brushYellowWireSummary(plan: BrushYellowPassiveWireDryRunPlan): String =
        brushYellowWireSummary(
            mapOf(
                "passiveWireEvidence" to plan.evidence,
                "passiveWireNetworkAllowed" to plan.networkSendAllowed.toString(),
                "batchRefill1229CapturedWireTail" to plan.refillCapturedWireTail.orEmpty(),
                "prepare1520CapturedWireTail" to plan.prepareCapturedWireTail,
                "dispatch1522CapturedWireTail" to plan.dispatchCapturedWireTail
            )
        ).orEmpty()
}

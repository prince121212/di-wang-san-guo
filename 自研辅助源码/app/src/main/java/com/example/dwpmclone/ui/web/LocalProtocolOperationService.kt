package com.example.dwpmclone.ui.web

import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import org.json.JSONArray
import org.json.JSONObject

/**
 * Local-only presentation adapter for the shared Web UI.
 *
 * Game requests are deliberately absent. State refresh, heartbeat and military
 * intelligence are durable shared-Python workflows over Android's byte-only
 * HTTP port.
 */
class LocalProtocolOperationService(
    private val accounts: LocalAccountRepository,
    private val dailyStats: LocalDailySuccessStatsRepository,
    private val taskOverviewProvider: (Long) -> JSONObject = { JSONObject() }
) {
    /** Returns null for routes owned by the shared core or the local controller. */
    fun tryHandle(request: AssistantApiRequest): AssistantApiResponse? {
        val route = request.path.substringBefore('?')
        return when (request.method to route) {
            "GET" to "/api/dashboard" -> dashboard(request)
            else -> null
        }
    }

    private fun dashboard(request: AssistantApiRequest): AssistantApiResponse = success(
        request,
        JSONObject()
            .put("accounts", JSONArray().apply {
                accounts.listPublicAccounts().forEach { account ->
                    val session = account.session
                    val extra = session?.channelExtra.orEmpty()
                    val roleState = jsonObject(extra["roleStateJson"])
                    val generals = jsonArray(extra["generalsJson"])
                    val snapshot = jsonObject(extra["militarySnapshotJson"])
                    put(JSONObject()
                        .put("sessionId", account.id.toString())
                        .put("username", account.username)
                        .put("displayName", account.displayName ?: account.username)
                        .put("serverQuery", account.serverName)
                        .put("areaName", account.serverName)
                        .put("status", if (account.enabled) "online" else "stopped")
                        .put("statusText", if (account.enabled) "开启" else "未启动")
                        .put("roleName", extra["roleName"] ?: account.monarchName ?: account.displayName)
                        .put("level", extra["level"]?.toIntOrNull() ?: roleState.optInt("level", 0))
                        .put("country", extra["nation"] ?: account.nation)
                        .put("role", roleState)
                        .put("generals", generals)
                        .put("militarySnapshot", snapshot)
                        .put("taskOverview", taskOverviewProvider(account.id))
                        .put("dailyStats", dailyStatsJson(account.id, extra))
                    )
                }
            })
            .put("updatedAt", System.currentTimeMillis())
    )

    private fun dailyStatsJson(accountId: Long, extra: Map<String, String>): JSONObject {
        val fallback = dailyStats.stats(accountId)
        val projected = SharedResidentDailyCountProjection.project(
            residentDailyCountsJson = extra["residentDailyCountsJson"],
            residentConfigJson = extra["residentAutomationConfigJson"],
            residentStateJson = extra["residentAutomationStateJson"],
            fallbackBrushYellowCount = fallback.brushYellowCount,
            fallbackDungeonCount = fallback.dungeonCount,
            nowMillis = System.currentTimeMillis(),
        )
        return JSONObject()
            .put("brushYellowCount", projected.brushYellowCount)
            .put("dungeonCount", projected.dungeonCount)
    }

    private fun jsonObject(raw: String?): JSONObject = raw?.trim()
        ?.takeIf { it.startsWith("{") }
        ?.let { runCatching { JSONObject(it) }.getOrNull() }
        ?: JSONObject()

    private fun jsonArray(raw: String?): JSONArray = raw?.trim()
        ?.takeIf { it.startsWith("[") }
        ?.let { runCatching { JSONArray(it) }.getOrNull() }
        ?: JSONArray()

    private fun success(
        request: AssistantApiRequest,
        data: JSONObject,
    ): AssistantApiResponse {
        data.put("ok", true)
        return AssistantApiResponse(request.id, 200, data)
    }
}

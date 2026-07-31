package com.example.dwpmclone.ui.web

import android.content.Context
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.AssistantBehaviorContractAssetLoader
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.LocalMapRepository
import com.example.dwpmclone.data.local.RequestHealthRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.localmap.BanditCacheKey
import com.example.dwpmclone.domain.localmap.LocalMapKind
import com.example.dwpmclone.domain.localmap.LocalTargetCache
import com.example.dwpmclone.domain.localmap.MineCacheKey
import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

/**
 * Real operation adapter for the shared Web UI.
 *
 * The WebView is intentionally not allowed to know how a packet is built.  This class only
 * translates the desktop request/response contract to the typed local protocol client; the
 * scheduler and manual actions consequently use the same SessionAwareGameProtocolClient.
 */
class LocalProtocolOperationService(
    context: Context,
    private val accounts: LocalAccountRepository,
    private val logs: TaskLogRepository,
    requestHealth: RequestHealthRepository,
    private val dailyStats: LocalDailySuccessStatsRepository,
    private val localMaps: LocalMapRepository,
    private val taskOverviewProvider: (Long) -> JSONObject = { JSONObject() }
) {
    private val appContext = context.applicationContext
    private val runner = LocalProtocolOperationRunner(
        appContext,
        accounts = accounts,
        logs = logs,
        requestHealth = requestHealth
    )
    private val behaviorContract = AssistantBehaviorContractAssetLoader.load(appContext)
    private val mapCache = LocalTargetCache(
        banditTtlMillis = behaviorContract.mapSearch.targetCacheTtlMillis,
        banditEmptyTtlMillis = behaviorContract.mapSearch.scanCoordinateCacheTtlMillis,
        mineTtlMillis = behaviorContract.mine.targetCacheTtlMillis,
        store = localMaps
    )

    /** Returns null for routes intentionally owned by LocalAssistantApiController. */
    fun tryHandle(request: AssistantApiRequest): AssistantApiResponse? {
        val route = request.path.substringBefore('?')
        return when (request.method to route) {
            "GET" to "/api/state/refresh" -> stateRefresh(request)
            "GET" to "/api/dashboard" -> dashboard(request)
            "GET" to "/api/heartbeat" -> heartbeat(request)
            "GET" to "/api/military/intel" -> militaryIntel(request)
            "POST" to "/api/brush/search" -> brushSearch(request)
            "POST" to "/api/brush/execute" -> brushExecute(request)
            "POST" to "/api/brush/recommended-center" -> recommendedBrushCenter(request)
            "POST" to "/api/mine/search" -> mineSearch(request)
            "POST" to "/api/mine/execute" -> mineExecute(request)
            "POST" to "/api/daily/sign-in/claim" -> dailySingle(request, DailyStep.SIGN_IN, "autoSignIn")
            "POST" to "/api/daily/arena-coins/claim" -> dailySingle(request, DailyStep.ARENA_REWARD, "arenaCoins")
            "POST" to "/api/daily/salary/claim" -> dailySingle(
                request,
                DailyStep.SALARY,
                "salary",
                skipIfCompleted = true
            )
            "POST" to "/api/daily/donate/claim" -> dailyDonate(request)
            "POST" to "/api/daily/donate/custom" -> dailyCustomDonate(request)
            "POST" to "/api/daily/national-collect/claim" -> nationalCollect(request)
            "POST" to "/api/daily/city-lord-collect/claim" -> cityLordCollect(request)
            "POST" to "/api/daily/general-visit/candidates" -> generalVisitCandidates(request)
            "POST" to "/api/daily/general-visit/claim" -> generalVisitClaim(request)
            "POST" to "/api/inventory/open-one" -> inventoryOpenOne(request)
            "POST" to "/api/troops/assign" -> troopsAssign(request)
            "POST" to "/api/troops/refill" -> troopsRefill(request)
            "POST" to "/api/troops/heal" -> troopsHeal(request)
            "POST" to "/api/formations/unassign-all" -> unassignAllTroops(request)
            "POST" to "/api/raid/fiefs" -> raidFiefs(request)
            // /api/raid/execute is a settings-save endpoint in the shared UI.  It remains
            // owned by LocalAssistantApiController so saving a rule does not unexpectedly
            // launch a real raid immediately.
            else -> null
        }
    }

    private fun stateRefresh(request: AssistantApiRequest): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val scope = query(request.path)["scope"].orEmpty().ifBlank { "all" }
        val result = runner.executeImmediateReadOnly(accountId, "state/refresh:$scope") { session, client ->
            val roleResult = if (scope in setOf("all", "role", "role-queues", "generals", "status")) {
                client.queryMonarch(session)
            } else null
            val resourceResult = if (scope in setOf("all", "role")) client.queryResourceState(session) else null
            val generalsResult = if (scope in setOf("all", "role", "role-queues", "generals", "army", "status")) {
                client.queryGenerals(session)
            } else null
            val formationsResult = if (scope in setOf("all", "role-queues", "generals", "army", "status")) {
                client.queryFormations(session)
            } else null
            val inventoryResult = if (scope in setOf("all", "inventory")) client.queryInventory(session) else null
            val militaryResult = if (scope in setOf("all", "military", "status")) {
                client.queryMilitarySnapshot(session)
            } else null

            firstError(roleResult, resourceResult, generalsResult, formationsResult, inventoryResult, militaryResult)?.let {
                return@executeImmediateReadOnly it
            }
            val role = (roleResult as? ProtocolResult.Ok)?.value
            val resources = (resourceResult as? ProtocolResult.Ok)?.value
            val generals = (generalsResult as? ProtocolResult.Ok)?.value
            val formations = (formationsResult as? ProtocolResult.Ok)?.value
            val inventory = (inventoryResult as? ProtocolResult.Ok)?.value
            val military = (militaryResult as? ProtocolResult.Ok)?.value
            val inventoryView = inventoryView(
                refreshed = inventory,
                cached = session.channelExtra["inventoryJson"],
                extra = session.channelExtra
            )
            val extra = accounts.get(accountId)?.session?.channelExtra ?: session.channelExtra
            val account = accounts.get(accountId)
            val mergedRoleState = jsonObject(extra["roleStateJson"]).apply {
                mergeFrom(jsonObject(extra["resourceStateJson"]))
                mergeFrom(roleStateJson(role, resources))
            }
            val roleView = role?.let(::monarchJson) ?: JSONObject()
                .put("roleId", extra["roleId"]?.toLongOrNull() ?: accountId)
                .put("roleName", extra["roleName"] ?: account?.monarchName ?: account?.displayName.orEmpty())
                .put("level", extra["level"]?.toIntOrNull() ?: mergedRoleState.optInt("level", 0))
                .put("country", extra["nation"] ?: account?.nation ?: JSONObject.NULL)
                .put("title", extra["title"] ?: JSONObject.NULL)
            val generalView = generals?.let { JSONArray(it.map(::generalJson)) }
                ?: jsonArray(extra["generalsJson"])
            val formationView = formations?.let { JSONArray(it.map(::formationJson)) }
                ?: jsonArray(extra["formationsJson"])
            val militaryView = military?.toJson()
                ?: jsonObject(extra["militarySnapshotJson"] ?: extra["militarySnapshot"])
            ProtocolResult.Ok(
                JSONObject()
                    .put("role", roleView)
                    .put("roleState", mergedRoleState)
                    .put("generals", generalView)
                    .put("formations", formationView)
                    .put("army", jsonArray(extra["armyJson"]))
                    .put("inventory", inventoryView)
                    .put(
                        "militaryIntel",
                        jsonObject(extra["militaryIntelJson"] ?: extra["militaryIntel"])
                            .takeIf { it.length() > 0 }
                            ?: JSONObject().put("events", JSONArray()).put("statusByName", JSONObject())
                    )
                    .put(
                        "militarySnapshot",
                        militaryView.takeIf { it.length() > 0 }
                            ?: JSONObject().put("actions", JSONArray()).put("actionCount", 0).put("responded", false)
                    )
                    .put("dailyActivity", jsonObject(extra["dailyActivityJson"]))
                    .put("dailyStats", dailyStatsJson(accountId))
                    .put("updatedAt", System.currentTimeMillis())
            )
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                persistState(accountId, result.value)
                success(request, result.value.put("taskOverview", taskOverviewProvider(accountId)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun brushSearch(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少找黄参数")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val start = body.coordinate("startX", "startY")
        val targetType = parseHuangType(body.optString("targetKind", "山贼"))
        val policy = MapSearchPolicy(targetType = targetType)
        val result = runner.execute(accountId, "brush/search") { session, client ->
            when (val response = client.searchMap(session, start, policy)) {
                is ProtocolResult.Ok -> ProtocolResult.Ok(response.value.filterBrushTargets(body, start))
                is ProtocolResult.Err -> response
            }
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                val targets = result.value
                val session = accounts.get(accountId)?.session
                if (session != null) {
                    mapCache.saveBandits(
                        BanditCacheKey.from(session, start, targetType),
                        targets,
                        System.currentTimeMillis()
                    )
                }
                success(request, JSONObject()
                    .put("targets", JSONArray(targets.map(::mapTargetJson)))
                    .put("points", JSONArray(targets.map(::mapTargetJson)))
                    .put("count", targets.size)
                    .put("updatedAt", System.currentTimeMillis())
                    .put("taskOverview", taskOverviewProvider(accountId)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun brushExecute(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少出征参数")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val targetObject = body.optJSONObject("target") ?: body
        val target = targetObject.toMapTarget()
            ?: return failure(request, 400, "目标缺少有效 ID 或坐标")
        val formationId = body.longValue("formationId", "generalId")
            ?: body.optJSONArray("generalIds")?.optLong(0, 0L)?.takeIf { it > 0L }
            ?: return failure(request, 400, "缺少出征将领/编队")
        val generalIds = body.longList("generalIds").distinct()
        if (generalIds.size > behaviorContract.brushYellow.maximumGeneralsPerFormation) {
            return failure(
                request,
                400,
                "刷黄编队最多选择" +
                    "${behaviorContract.brushYellow.maximumGeneralsPerFormation}名出征将领"
            )
        }
        val result = runner.execute(accountId, "brush/execute") { session, client ->
            if (generalIds.isEmpty()) {
                client.dispatchFormation(session, formationId, target)
            } else {
                client.dispatchFormation(
                    session,
                    FormationRuntime(
                        id = formationId,
                        name = "手动刷黄编队",
                        generalIds = generalIds,
                        status = FormationRuntimeStatus.IDLE,
                        troopCount = null
                    ),
                    target
                )
            }
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                val battle = result.value
                if (battle.success) {
                    accounts.get(accountId)?.session?.let { session ->
                        val start = body.coordinate("startX", "startY")
                        mapCache.invalidateBandit(
                            BanditCacheKey.from(session, start, parseHuangType(target.type)),
                            target.id,
                            reason = "manual-dispatch"
                        )
                    }
                    logs.appendSuccess(
                        accountId,
                        "刷黄",
                        "编队$formationId > ${target.type}(${target.coordinate.x}，${target.coordinate.y})",
                        tag = "manual-success"
                    )
                }
                success(request, JSONObject()
                    .put("success", battle.success)
                    .put("consumedTimes", battle.consumedTimes)
                    .put("battleText", battle.raw["message"] ?: battle.raw["expeditionParsed.message"].orEmpty())
                    .put("target", mapTargetJson(target))
                    .put("raw", JSONObject(battle.raw))
                    .put("dailyBrushCount", dailyStats.current(accountId, TaskType.SHUA_HUANG))
                    .put("dailyStats", dailyStatsJson(accountId))
                    .put("taskOverview", taskOverviewProvider(accountId)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun recommendedBrushCenter(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少参数")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val generalIds = body.longListPreservingOrder("generalIds")
        val result = runner.execute(accountId, "brush/recommended-center") { session, _ ->
            runCatching {
                val generalsJson = jsonArray(session.channelExtra["generalsJson"])
                val generals = (0 until generalsJson.length()).mapNotNull { index ->
                    val item = generalsJson.optJSONObject(index) ?: return@mapNotNull null
                    val id = item.longValue("id", "generalId", "jiangLingId") ?: return@mapNotNull null
                    BrushCenterGeneral(
                        id = id,
                        name = item.optString("name", item.optString("generalName", id.toString())),
                        fiefId = item.longValue("fiefId", "placeID", "placeId")
                    )
                }
                val locations = cachedBrushFiefLocations(session.channelExtra, generalsJson)
                ProtocolResult.Ok(BrushCenterRecommendationPolicy.recommend(generalIds, generals, locations))
            }.getOrElse { error ->
                ProtocolResult.Err(
                    "BRUSH_CENTER_UNAVAILABLE",
                    error.message ?: "无法计算刷黄推荐中心",
                    retryable = false
                )
            }
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                val recommendation = result.value
                success(request, JSONObject()
                    .put("x", recommendation.x)
                    .put("y", recommendation.y)
                    .put("centerX", recommendation.x)
                    .put("centerY", recommendation.y)
                    .put("worldX", recommendation.worldX)
                    .put("worldY", recommendation.worldY)
                    .put("fiefId", recommendation.fiefId)
                    .put("fiefName", recommendation.fiefName)
                    .put("cityName", recommendation.cityName)
                    .put("selectedGenerals", JSONArray(recommendation.selectedGenerals.map { general ->
                        JSONObject()
                            .put("generalId", general.generalId)
                            .put("generalName", general.generalName)
                            .put("fiefId", general.fiefId)
                    }))
                    .put("fiefCounts", JSONObject().apply {
                        recommendation.fiefCounts.forEach { (fiefId, count) -> put(fiefId.toString(), count) }
                    })
                    .put("source", "login-owned-fief-cache"))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun mineSearch(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少找矿参数")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val config = mineConfig(body)
        val result = runner.execute(accountId, "mine/search") { session, client ->
            client.searchMines(session, config)
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                val session = accounts.get(accountId)?.session
                if (session != null) {
                    mapCache.saveMines(MineCacheKey.from(session, config), result.value, System.currentTimeMillis())
                }
                success(request, JSONObject()
                    .put("mines", JSONArray(result.value.map(::mineJson)))
                    .put("points", JSONArray(result.value.map(::mineJson)))
                    .put("count", result.value.size)
                    .put("updatedAt", System.currentTimeMillis()))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun mineExecute(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少打矿参数")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val mine = (body.optJSONObject("mine") ?: body).toMineSearchResult()
            ?: return failure(request, 400, "资源点缺少有效 ID、坐标或资源类型")
        val generalIds = body.longList("generalIds").ifEmpty {
            body.longValue("generalId", "formationId")?.let(::listOf).orEmpty()
        }
        if (generalIds.isEmpty()) return failure(request, 400, "打矿至少需要一个将领")
        val maxMarch = body.optInt("maxMarchMinutes", 45).coerceIn(1, 180)
        val result = runner.execute(accountId, "mine/execute") { session, client ->
            client.occupyMine(session, mine, generalIds, maxMarch)
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    accounts.get(accountId)?.session?.let { session ->
                        mapCache.invalidateMine(
                            MineCacheKey.from(session, mineConfig(body)),
                            mine.id,
                            reason = "manual-occupy"
                        )
                    }
                    logs.appendSuccess(
                        accountId,
                        "打矿",
                        "出征 > ${mine.mineType.name}(${mine.coordinate.x}，${mine.coordinate.y})",
                        tag = "manual-success"
                    )
                }
                success(request, JSONObject()
                    .put("success", result.value.success)
                    .put("message", result.value.message)
                    .put("raw", JSONObject(result.value.raw))
                    .put("mine", mineJson(mine))
                    .put("taskOverview", taskOverviewProvider(accountId)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun dailySingle(
        request: AssistantApiRequest,
        step: DailyStep,
        completionKey: String,
        skipIfCompleted: Boolean = false
    ): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少账号")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val alreadyCompleted = dailyStats.isCompleted(accountId, completionKey)
        if (alreadyCompleted && skipIfCompleted) {
            return success(
                request,
                JSONObject()
                    .put(
                        "result",
                        JSONObject()
                            .put("success", true)
                            .put("completed", true)
                            .put("message", "今日已经完成${dailyFeatureLabel(completionKey)}")
                    )
                    .put("alreadyCompleted", true)
                    .put("completionKey", completionKey)
                    .put("taskOverview", taskOverviewProvider(accountId))
            )
        }
        val result = runner.execute(accountId, "daily/${step.name}") { session, client ->
            client.runDailyStep(session, step)
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                val stepResult = result.value
                if (stepResult.success) {
                    dailyStats.markCompleted(accountId, completionKey)
                    logs.appendSuccess(
                        accountId = accountId,
                        category = dailyFeatureCategory(completionKey),
                        message = stepResult.message.ifBlank { "${dailyFeatureLabel(completionKey)}成功" },
                        tag = "daily-manual"
                    )
                } else {
                    logs.append(
                        "${dailyFeatureLabel(completionKey)}失败：${stepResult.message}",
                        tag = "daily-manual",
                        accountId = accountId
                    )
                }
                success(request, JSONObject()
                    .put("result", stepResultJson(stepResult))
                    .put("alreadyCompleted", alreadyCompleted)
                    .put("completionKey", completionKey)
                    .put("taskOverview", taskOverviewProvider(accountId)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun dailyDonate(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少账号")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        if (dailyStats.isCompleted(accountId, "autoDonate")) {
            return completedDailyResponse(request, accountId, "autoDonate")
        }
        val steps = listOf(DailyStep.DONATE_COPPER, DailyStep.DONATE_FOOD, DailyStep.DONATE_TECH)
        val outcomes = JSONArray()
        var successful = 0
        var alreadyCompletedByQuota = 0
        for (step in steps) {
            when (val result = runner.execute(accountId, "daily/${step.name}") { session, client ->
                client.runDailyStep(session, step)
            }) {
                is ProtocolResult.Ok -> {
                    outcomes.put(stepResultJson(result.value).put("step", step.name))
                    if (result.value.success) {
                        successful++
                        if (result.value.raw["alreadyCompleted"] == "true") {
                            alreadyCompletedByQuota++
                        }
                    }
                }
                is ProtocolResult.Err -> outcomes.put(JSONObject()
                    .put("step", step.name)
                    .put("success", false)
                    .put("code", result.code)
                    .put("message", result.message))
            }
        }
        val complete = successful == steps.size
        val completionMessage = when {
            !complete -> "三项捐献完成${successful}/${steps.size}"
            alreadyCompletedByQuota == steps.size -> "三项今日捐献额度均已用完，自动捐献按已做处理"
            alreadyCompletedByQuota > 0 -> "三项捐献均已成功或达到今日额度"
            else -> "三项捐献完成"
        }
        if (complete) {
            dailyStats.markCompleted(accountId, "autoDonate")
            logs.append("自动捐献完成：$completionMessage", tag = "daily-manual", accountId = accountId)
            logs.appendSuccess(accountId, "捐献", completionMessage, tag = "daily-manual")
        } else {
            logs.append(
                "自动捐献失败：三项捐献完成${successful}/${steps.size}",
                tag = "daily-manual",
                accountId = accountId
            )
        }
        return success(request, JSONObject()
            .put("alreadyCompleted", false)
            .put("result", JSONObject()
                .put("success", complete)
                .put("completed", complete)
                .put("message", completionMessage)
                .put("actions", outcomes))
            .put("taskOverview", taskOverviewProvider(accountId)))
    }

    private fun dailyCustomDonate(request: AssistantApiRequest): AssistantApiResponse {
        // The current typed client intentionally derives the verified desktop maximum from the
        // role level.  Do not silently pretend arbitrary amounts were sent; route custom values
        // through the same verified steps and report the requested values for the UI.
        val body = request.body ?: return failure(request, 400, "缺少账号")
        body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val result = dailyDonate(request)
        if (result.status in 200..299) {
            result.body.put("requestedCopper", body.optLong("copper", 0L))
                .put("requestedFood", body.optLong("food", 0L))
                .put("customAmountMode", "verified-level-limit")
        }
        return result
    }

    private fun nationalCollect(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少账号")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        if (dailyStats.isCompleted(accountId, "nationalCollect")) {
            return completedDailyResponse(request, accountId, "nationalCollect")
        }
        val result = runner.execute(accountId, "daily/nationalCollect") { session, client ->
            val cities = buildList {
                listOf(NationalCityKind.STATE, NationalCityKind.COMMANDERY, NationalCityKind.COUNTY).forEach { kind ->
                    when (val response = client.queryNationalCities(session, kind)) {
                        is ProtocolResult.Ok -> addAll(response.value)
                        is ProtocolResult.Err -> return@execute response
                    }
                }
            }.distinctBy { it.name }
            val actions = mutableListOf<JSONObject>()
            var successCount = 0
            var eligibleCount = 0
            cities.forEach { city ->
                val status = when (val response = client.queryNationalCollectStatus(session, city)) {
                    is ProtocolResult.Ok -> response.value
                    is ProtocolResult.Err -> return@execute response
                }
                if (!status.canCollect) return@forEach
                eligibleCount++
                when (val response = client.collectNationalCity(session, city)) {
                    is ProtocolResult.Ok -> {
                        actions += stepResultJson(response.value).put("city", city.name)
                        if (response.value.success) successCount++
                    }
                    is ProtocolResult.Err -> return@execute response
                }
            }
            val completed = eligibleCount == 0 || successCount == eligibleCount
            ProtocolResult.Ok(JSONObject()
                .put("success", successCount > 0)
                .put("completed", completed)
                .put("eligibleCount", eligibleCount)
                .put("successCount", successCount)
                .put("actions", JSONArray(actions)))
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                if (result.value.optBoolean("completed")) {
                    dailyStats.markCompleted(accountId, "nationalCollect")
                }
                if (result.value.optBoolean("success")) {
                    logs.appendSuccess(
                        accountId,
                        "国征",
                        "成功${result.value.optInt("successCount")}次",
                        tag = "daily-manual"
                    )
                } else if (!result.value.optBoolean("completed")) {
                    logs.append("国家征收未完成：服务器未确认全部可征收城池", "daily-manual", accountId)
                }
                success(request, JSONObject()
                    .put("alreadyCompleted", false)
                    .put("result", result.value)
                    .put("taskOverview", taskOverviewProvider(accountId)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun cityLordCollect(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少账号")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        if (dailyStats.isCompleted(accountId, "cityLordCollect")) {
            return completedDailyResponse(request, accountId, "cityLordCollect")
        }
        val result = runner.execute(accountId, "daily/cityLordCollect") { session, client ->
            val fiefs = when (val response = client.queryOwnedFiefs(session)) {
                is ProtocolResult.Ok -> response.value
                is ProtocolResult.Err -> return@execute response
            }
            val actions = JSONArray()
            var successful = 0
            var completed = 0
            val contract = behaviorContract.dailyActions.cityLordCollect
            val cities = fiefs
                .filter { it.cityName.isNotBlank() }
                .distinctBy { it.cityName }
            cities.forEach { fief ->
                when (val response = client.collectCityLord(session, fief)) {
                    is ProtocolResult.Ok -> {
                        actions.put(stepResultJson(response.value).put("city", fief.cityName))
                        if (response.value.success) {
                            successful++
                            completed++
                        } else if (
                            contract.ineligibleMarkers.any(response.value.message::contains) ||
                            contract.alreadyCollectedMarkers.any(response.value.message::contains)
                        ) {
                            completed++
                        }
                    }
                    is ProtocolResult.Err -> return@execute response
                }
            }
            val cityCount = cities.size
            ProtocolResult.Ok(JSONObject()
                .put("success", completed >= cityCount)
                .put("completed", completed >= cityCount)
                .put("noTarget", cityCount == 0)
                .put("cityCount", cityCount)
                .put("completedCount", completed)
                .put("successCount", successful)
                .put("actions", actions))
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                if (result.value.optBoolean("completed")) {
                    dailyStats.markCompleted(accountId, "cityLordCollect")
                }
                if (result.value.optInt("successCount") > 0) {
                    logs.appendSuccess(
                        accountId,
                        "城征",
                        "成功${result.value.optInt("successCount")}座",
                        tag = "daily-manual"
                    )
                } else if (!result.value.optBoolean("completed")) {
                    logs.append("城主征收未完成：存在未确认结果", "daily-manual", accountId)
                }
                success(request, JSONObject()
                    .put("alreadyCompleted", false)
                    .put("result", result.value)
                    .put("taskOverview", taskOverviewProvider(accountId)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun generalVisitCandidates(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少账号")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val result = runner.executeImmediateReadOnly(accountId, "daily/generalVisit/candidates") { session, client ->
            client.queryVisitGenerals(session)
        }
        return when (result) {
            is ProtocolResult.Ok -> success(request, JSONObject()
                .put("generals", JSONArray(result.value.candidates.map(::visitCandidateJson)))
                .put("candidates", JSONArray(result.value.candidates.map(::visitCandidateJson)))
                .put("completed", result.value.completed)
                .put("alreadyVisited", result.value.alreadyVisited)
                .put("message", result.value.message)
                .put("updatedAt", System.currentTimeMillis()))
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun generalVisitClaim(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少账号")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        if (dailyStats.isCompleted(accountId, "generalVisit")) {
            return completedDailyResponse(request, accountId, "generalVisit")
        }
        val selected = body.longList("generalVisitGeneralIds", "generalIds")
        val result = runner.execute(accountId, "daily/generalVisit/claim") { session, client ->
            val query = when (val response = client.queryVisitGenerals(session)) {
                is ProtocolResult.Ok -> response.value
                is ProtocolResult.Err -> return@execute response
            }
            if (query.completed) {
                return@execute ProtocolResult.Ok(
                    JSONObject()
                        .put("success", true)
                        .put("completed", true)
                        .put("alreadyVisited", query.alreadyVisited)
                        .put("message", query.message.ifBlank { "本日已经完成名将拜访" })
                )
            }
            val candidates = query.candidates.associateBy { it.id }
            val ids = if (selected.isEmpty()) {
                query.candidates.firstOrNull { it.captiveState == 0 }?.let { listOf(it.id) }.orEmpty()
            } else {
                selected
            }
            val actions = JSONArray()
            var successful = 0
            var terminalMessage = ""
            for (id in ids) {
                val candidate = candidates[id] ?: continue
                if (candidate.captiveState != 0) continue
                when (val response = client.visitGeneral(session, candidate)) {
                    is ProtocolResult.Ok -> {
                        actions.put(stepResultJson(response.value).put("generalId", id).put("name", candidate.name))
                        if (response.value.success) {
                            successful = 1
                            terminalMessage = response.value.message
                            break
                        }
                    }
                    is ProtocolResult.Err -> return@execute response
                }
            }
            val completed = successful > 0
            ProtocolResult.Ok(JSONObject()
                .put("success", completed)
                .put("completed", completed)
                .put("successCount", successful)
                .put("message", terminalMessage)
                .put("actions", actions))
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                if (result.value.optBoolean("completed")) {
                    dailyStats.markCompleted(accountId, "generalVisit")
                }
                if (result.value.optBoolean("completed")) {
                    logs.appendSuccess(
                        accountId,
                        "拜访",
                        result.value.optString("message").ifBlank { "名将拜访已获得终态回执" },
                        tag = "daily-manual"
                    )
                } else {
                    logs.append("名将拜访未完成：没有候选名将获得终态回执", "daily-manual", accountId)
                }
                success(request, JSONObject()
                    .put("alreadyCompleted", false)
                    .put("result", result.value)
                    .put("taskOverview", taskOverviewProvider(accountId)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun completedDailyResponse(
        request: AssistantApiRequest,
        accountId: Long,
        completionKey: String
    ): AssistantApiResponse = success(
        request,
        JSONObject()
            .put("alreadyCompleted", true)
            .put(
                "result",
                JSONObject()
                    .put("success", true)
                    .put("completed", true)
                    .put("message", "今日已经完成${dailyFeatureLabel(completionKey)}")
            )
            .put("taskOverview", taskOverviewProvider(accountId))
    )

    private fun dailyFeatureLabel(key: String): String = when (key) {
        "autoSignIn" -> "自动签到"
        "arenaCoins" -> "领竞技币"
        "autoDonate" -> "自动捐献"
        "salary" -> "国家俸禄"
        "nationalCollect" -> "国家征收"
        "cityLordCollect" -> "城主征收"
        "generalVisit" -> "名将拜访"
        else -> key
    }

    private fun dailyFeatureCategory(key: String): String = when (key) {
        "autoSignIn" -> "签到"
        "arenaCoins" -> "领币"
        "autoDonate" -> "捐献"
        "salary" -> "俸禄"
        "nationalCollect" -> "国征"
        "cityLordCollect" -> "城征"
        "generalVisit" -> "拜访"
        else -> "其他"
    }

    private fun inventoryOpenOne(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少开箱参数")
        if (body.optString("confirm") != "open-one") return failure(request, 400, "单次开箱需要 confirm=open-one")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val name = body.optString("itemName").trim()
        if (name.isBlank()) return failure(request, 400, "缺少物品名称")
        val result = runner.execute(accountId, "inventory/open-one:$name") { session, client ->
            val inventory = when (val response = client.queryInventory(session)) {
                is ProtocolResult.Ok -> response.value
                is ProtocolResult.Err -> return@execute response
            }
            val item = inventory.firstOrNull { it.name == name && it.count > 0 }
                ?: return@execute ProtocolResult.Err("INVENTORY_ITEM_NOT_FOUND", "背包中没有$name", false)
            client.useOrDiscardItem(session, item.id, InventoryAction.OPEN, 1)
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    logs.appendSuccess(
                        accountId,
                        "开箱",
                        "$name → ${result.value.message.ifBlank { "服务器确认成功" }}",
                        tag = "manual-success"
                    )
                }
                success(request, JSONObject()
                    .put("result", stepResultJson(result.value))
                    .put("itemName", name))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun troopsAssign(request: AssistantApiRequest): AssistantApiResponse = formationAction(request, "troops/assign")
    private fun troopsRefill(request: AssistantApiRequest): AssistantApiResponse = formationAction(request, "troops/refill")

    private fun formationAction(request: AssistantApiRequest, label: String): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少配兵参数")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val ids = body.longList("generalIds").ifEmpty {
            body.longValue("generalId")?.let(::listOf).orEmpty()
        }
        if (ids.isEmpty()) return failure(request, 400, "缺少将领 ID")
        val config = ConfigDefaults.formation(ids.first()).copy(
            generalIds = ids,
            autoAssignTroops = label.endsWith("assign"),
            troopType = body.optString("soldierType", body.optString("soldierTypeCode", "轻骑兵")),
            troopCount = body.optInt("soldierCount", body.optInt("count", 0)).coerceAtLeast(1),
            fillToMaxWhenAutoAssignDisabled = label.endsWith("refill")
        )
        val result = runner.execute(accountId, label) { session, client ->
            client.updateFormation(session, config)
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    logs.appendSuccess(accountId, "配兵", result.value.message, tag = "manual-success")
                }
                success(request, JSONObject().put("result", stepResultJson(result.value)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun troopsHeal(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少治疗参数")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val generalId = body.longValue("generalId") ?: return failure(request, 400, "缺少将领 ID")
        val result = runner.execute(accountId, "troops/heal") { session, client ->
            client.healGeneral(session, generalId)
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                if (result.value.success && !result.value.raw.containsKey("skipped")) {
                    logs.appendSuccess(accountId, "治疗", result.value.message, tag = "manual-success")
                }
                success(request, JSONObject().put("result", stepResultJson(result.value)))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun unassignAllTroops(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少卸兵参数")
        if (body.optString("confirm") != "unassign-all-troops") {
            return failure(request, 400, "一键卸兵需要 confirm=unassign-all-troops")
        }
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val config = ConfigDefaults.formation(1L).copy(
            generalIds = emptyList(),
            autoAssignTroops = false,
            fillToMaxWhenAutoAssignDisabled = false,
            clearOtherGeneralIds = emptySet(),
            clearAllIdleTroops = true
        )
        val result = runner.execute(accountId, "formations/unassign-all") { session, client ->
            when (val cleared = client.updateFormation(session, config)) {
                is ProtocolResult.Err -> cleared
                is ProtocolResult.Ok -> when (val refreshed = client.queryGenerals(session)) {
                    is ProtocolResult.Err -> refreshed
                    is ProtocolResult.Ok -> ProtocolResult.Ok(cleared.value to refreshed.value)
                }
            }
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                val (receipt, generals) = result.value
                val generalArray = JSONArray(generals.map(::generalJson))
                accounts.get(accountId)?.let { account ->
                    account.session?.let { session ->
                        accounts.upsert(account.copy(session = session.copy(
                            channelExtra = session.channelExtra + mapOf("generalsJson" to generalArray.toString())
                        )))
                    }
                }
                success(request, JSONObject()
                    .put("clearedCount", receipt.raw["clear.clearedCount"]?.toIntOrNull() ?: 0)
                    .put("skippedCount", receipt.raw["clear.skippedCount"]?.toIntOrNull() ?: 0)
                    .put("results", JSONObject(receipt.raw))
                    .put("generals", generalArray)
                    .put("army", jsonArray(accounts.get(accountId)?.session?.channelExtra?.get("armyJson")))
                    .put("roleState", jsonObject(accounts.get(accountId)?.session?.channelExtra?.get("roleStateJson"))))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun raidFiefs(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少查询参数")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val playerName = body.optString("playerName").trim()
        if (playerName.isBlank()) return failure(request, 400, "请填写要掠夺的玩家名称")
        val result = runner.execute(accountId, "raid/fiefs") { session, client ->
            client.queryRaidFiefs(session, playerName)
        }
        return when (result) {
            is ProtocolResult.Ok -> success(request, JSONObject()
                .put("fiefs", JSONArray(result.value.map(::fiefJson)))
                .put("rows", JSONArray(result.value.map(::fiefJson)))
                .put("playerName", playerName))
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun raidExecute(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少掠夺参数")
        if (body.optString("confirm") != "raid") return failure(request, 400, "真实掠夺需要 confirm=raid")
        val accountId = body.longValue("sessionId") ?: return failure(request, 400, "缺少账号")
        val rows = body.optJSONArray("rows") ?: JSONArray().put(body)
        val rules = (0 until rows.length()).mapNotNull { index ->
            rows.optJSONObject(index)?.let { row ->
                AutoLootRule(
                    enabled = row.optBoolean("enabled", true),
                    generalIds = row.longList("generalIds").ifEmpty { row.longValue("generalId")?.let(::listOf).orEmpty() },
                    playerName = row.optString("playerName").trim(),
                    fiefIndex = row.optInt("fiefIndex", 1)
                )
            }
        }
        val config = ConfigDefaults.autoLoot().copy(
            enabled = rules.any { it.enabled },
            selectedFormationIds = rules.firstOrNull()?.generalIds?.toSet().orEmpty(),
            targetPlayerName = rules.firstOrNull()?.playerName.orEmpty(),
            targetFiefIndex = rules.firstOrNull()?.fiefIndex ?: 1,
            fullTroops = body.optBoolean("fullTroops", true),
            fullLoyalty = body.optBoolean("fullLoyalty", false),
            requireSecondConfirmForRealRun = false,
            rules = rules
        )
        val result = runner.execute(accountId, "raid/execute") { session, client ->
            client.runAutoLoot(session, config)
        }
        return when (result) {
            is ProtocolResult.Ok -> {
                if (result.value.success && result.value.raw["phase"] == "launched") {
                    logs.appendSuccess(accountId, "掠夺", result.value.message, tag = "manual-success")
                }
                success(request, JSONObject()
                    .put("result", stepResultJson(result.value))
                    .put("saved", true)
                    .put("rows", rows))
            }
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun militaryIntel(request: AssistantApiRequest): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val result = runner.executeImmediateReadOnly(accountId, "military/intel") { session, client ->
            client.queryMilitarySnapshot(session)
        }
        return when (result) {
            is ProtocolResult.Ok -> success(request, JSONObject()
                .put("militarySnapshot", result.value.toJson())
                .put("result", JSONObject()
                    .put("success", true)
                    .put("message", "军情快照刷新完成")
                    .put("raw", JSONObject().put("actionCount", result.value.actions.size))))
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun heartbeat(request: AssistantApiRequest): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val result = runner.execute(accountId, "heartbeat") { session, client -> client.validateSession(session) }
        return when (result) {
            is ProtocolResult.Ok -> success(request, JSONObject()
                .put("online", result.value.valid)
                .put("message", result.value.reason ?: "真实 Session 有效")
                .put("checkedAt", System.currentTimeMillis()))
            is ProtocolResult.Err -> protocolFailure(request, result)
        }
    }

    private fun dashboard(request: AssistantApiRequest): AssistantApiResponse = success(
        request,
        JSONObject()
            .put("accounts", JSONArray().apply {
                accounts.listAccounts().forEach { account ->
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
                    .put("dailyStats", dailyStatsJson(account.id))
                )
            }
            })
            .put("updatedAt", System.currentTimeMillis())
    )

    private fun persistState(accountId: Long, state: JSONObject) {
        val account = accounts.get(accountId) ?: return
        val session = account.session ?: return
        val updates = linkedMapOf<String, String>()
        state.optJSONObject("roleState")?.let { updates["roleStateJson"] = it.toString() }
        state.optJSONObject("role")?.let { role ->
            updates["roleName"] = role.optString("roleName")
            if (role.has("level")) updates["level"] = role.optInt("level").toString()
        }
        state.optJSONArray("generals")?.let { updates["generalsJson"] = it.toString() }
        state.optJSONArray("formations")?.let { updates["formationsJson"] = it.toString() }
        state.optJSONObject("inventory")?.let { inventory ->
            val completeInventory = JSONArray()
            inventory.optJSONArray("items")?.let { items ->
                for (index in 0 until items.length()) completeInventory.put(items.opt(index))
            }
            inventory.optJSONArray("equipment")?.let { equipment ->
                for (index in 0 until equipment.length()) completeInventory.put(equipment.opt(index))
            }
            updates["inventoryJson"] = completeInventory.toString()
            if (inventory.has("capacity") && !inventory.isNull("capacity")) {
                updates["inventoryCapacity"] = inventory.optInt("capacity").toString()
            }
            updates["inventoryItemCount"] = (inventory.optJSONArray("items")?.length() ?: 0).toString()
            updates["inventoryEquipmentCount"] = (inventory.optJSONArray("equipment")?.length() ?: 0).toString()
            inventory.optString("sourceOpcode").takeIf(String::isNotBlank)?.let {
                updates["inventorySourceOpcode"] = it
            }
        }
        state.optJSONObject("militarySnapshot")?.let {
            updates["militarySnapshotJson"] = it.toString()
            updates["militarySnapshot"] = it.toString()
        }
        if (updates.isNotEmpty()) accounts.upsert(account.copy(session = session.copy(channelExtra = session.channelExtra + updates)))
    }

    private fun firstError(vararg values: ProtocolResult<*>?): ProtocolResult.Err? = values
        .filterNotNull()
        .mapNotNull { it as? ProtocolResult.Err }
        .firstOrNull()

    private fun mineConfig(body: JSONObject): MineConfig {
        val source = body.optJSONObject("settings") ?: body
        val selectedTypes = source.stringList("selectedMineTypes", "mineTypes", "resourceTypes")
            .mapNotNull(::parseMineType)
            .toSet()
            .ifEmpty { setOf(parseMineType(source.optString("resourceType")) ?: MineType.GOLD) }
        val rows = source.optJSONArray("rows")
        val rowIds = rows?.let { arr ->
            (0 until arr.length()).flatMap { i -> arr.optJSONObject(i)?.longList("generalIds") ?: emptyList() }
        }.orEmpty()
        val ids = source.longList("generalIds", "selectedFormationIds").ifEmpty { rowIds }
        return ConfigDefaults.mine().copy(
            enabled = true,
            start = source.coordinate("centerX", "centerY"),
            selectedMineTypes = selectedTypes,
            selectedFormationIds = ids.toSet(),
            onlyEmptyMine = source.optBoolean("onlyEmptyMine", false),
            onlyDefendedMine = source.optBoolean("onlyDefendedMine", false),
            searchScope = source.optString("scope", source.optString("searchScope", "附近")),
            maxMarchMinutes = source.optInt("maxMarchMinutes", 45).coerceIn(1, 180),
            fullLoyalty = source.optBoolean("fullLoyalty", true),
            replenishTroops = source.optBoolean("replenishTroops", true)
        )
    }

    private fun parseHuangType(value: String): HuangTargetType =
        if (value.contains("黄巾") || value.contains("黃巾")) HuangTargetType.HUANG_JIN else HuangTargetType.SHAN_ZEI

    private fun parseMineType(value: String?): MineType? {
        val raw = value?.trim().orEmpty()
        if (raw.isBlank()) return null
        runCatching { return MineType.valueOf(raw.uppercase()) }
        return when {
            raw.contains("金") -> MineType.GOLD
            raw.contains("银") || raw.contains("銀") -> MineType.SILVER
            raw.contains("冰玉") -> MineType.BING_YU
            raw.contains("仙芝") -> MineType.XIAN_ZHI
            raw.contains("玄铁") || raw.contains("玄鐵") -> MineType.XUAN_TIE
            raw.contains("玉露") -> MineType.YU_LU
            raw.contains("水晶") -> MineType.CRYSTAL
            raw.contains("灵草") || raw.contains("靈草") -> MineType.LING_CAO
            raw.contains("镔铁") || raw.contains("鑌鐵") || raw.contains("宾铁") -> MineType.BIN_TIE
            raw.contains("浆果") || raw.contains("漿果") -> MineType.JIANG_GUO
            raw.contains("牧场") || raw.contains("牧場") -> when {
                raw.contains("2") -> MineType.PASTURE_LV2
                raw.contains("3") -> MineType.PASTURE_LV3
                else -> MineType.PASTURE_LV1
            }
            else -> null
        }
    }

    private fun List<MapTarget>.filterBrushTargets(body: JSONObject, start: MapCoordinate): List<MapTarget> {
        val levels = body.intList("levels", "level").toSet()
        val maxDistance = body.optInt("maxDistance", 0).takeIf { it > 0 }
        val filter = body.optJSONObject("compositionFilter") ?: body
        val limits = mapOf(
            "foot" to filter.optInt("maxFoot", 0),
            "bow" to filter.optInt("maxBow", 0),
            "cavalry" to filter.optInt("maxCavalry", 0),
            "chariot" to filter.optInt("maxChariot", 0)
        )
        val requireFoot = filter.optBoolean("requireFoot", false)
        return asSequence().filter { target ->
            val level = target.raw.intValue("level", "rank", "fz")
            (levels.isEmpty() || (level != null && level in levels)) &&
                (maxDistance == null || abs(target.coordinate.x - start.x) + abs(target.coordinate.y - start.y) <= maxDistance) &&
                target.compositionMatches(limits, requireFoot)
        }.toList()
    }

    private fun MapTarget.compositionMatches(limits: Map<String, Int>, requireFoot: Boolean): Boolean {
        val code = raw["compositionCode"]?.takeIf { it.length >= 4 }
        if (code == null && (requireFoot || limits.values.any { it > 0 })) return false
        if (requireFoot && code?.getOrNull(0)?.digitToIntOrNull()?.let { it > 0 } != true) return false
        val values = code?.take(4)?.mapNotNull { it.digitToIntOrNull() }
        if (values == null || values.size < 4) return !requireFoot && limits.values.none { it > 0 }
        val keys = listOf("foot", "bow", "cavalry", "chariot")
        return keys.indices.all { index -> limits[keys[index]]?.let { it <= 0 || values[index] <= it } != false }
    }

    private fun stepResultJson(value: StepResult): JSONObject = JSONObject()
        .put("success", value.success)
        .put("message", value.message)
        .put("raw", JSONObject(value.raw))

    private fun dailyStatsJson(accountId: Long): JSONObject = dailyStats.stats(accountId).let {
        JSONObject().put("brushYellowCount", it.brushYellowCount).put("dungeonCount", it.dungeonCount)
    }

    private fun jsonObject(raw: String?): JSONObject = raw?.trim()
        ?.takeIf { it.startsWith("{") }
        ?.let { runCatching { JSONObject(it) }.getOrNull() }
        ?: JSONObject()

    private fun jsonArray(raw: String?): JSONArray = raw?.trim()
        ?.takeIf { it.startsWith("[") }
        ?.let { runCatching { JSONArray(it) }.getOrNull() }
        ?: JSONArray()

    private fun JSONObject.mergeFrom(source: JSONObject) {
        source.keys().forEach { key -> put(key, source.opt(key)) }
    }

    private fun monarchJson(value: MonarchProfile): JSONObject = JSONObject()
        .put("roleId", value.roleId ?: JSONObject.NULL)
        .put("roleName", value.name)
        .put("level", value.level)
        .put("country", value.nation ?: JSONObject.NULL)
        .put("title", value.title ?: JSONObject.NULL)
        .put("prestige", value.prestige ?: JSONObject.NULL)

    private fun roleStateJson(role: MonarchProfile?, resources: ResourceState?): JSONObject {
        val result = JSONObject()
        if (role != null) result.put("roleName", role.name).put("level", role.level)
        if (resources != null) {
            result.put("copper", resources.copper)
                .put("food", resources.food)
                .put("prestige", resources.prestige ?: JSONObject.NULL)
                .put("populationCurrent", resources.populationCurrent ?: JSONObject.NULL)
                .put("populationCap", resources.populationCap ?: JSONObject.NULL)
        }
        return result
    }

    private fun generalJson(value: General): JSONObject = JSONObject()
        .put("id", value.id)
        .put("name", value.name)
        .put("growth", value.growth ?: JSONObject.NULL)
        .put("loyalty", value.loyalty ?: JSONObject.NULL)
        .put("energy", value.energy ?: JSONObject.NULL)
        .put("rank", value.rank ?: JSONObject.NULL)
        .put("status", value.status ?: JSONObject.NULL)
        .put("placeID", value.placeId ?: JSONObject.NULL)
        .put("soldierType", value.raw["soldierType"] ?: value.raw["troopType"] ?: JSONObject.NULL)
        .put("soldierCount", value.raw["soldierCount"]?.toIntOrNull() ?: value.raw["troopCount"]?.toIntOrNull() ?: JSONObject.NULL)
        .put("raw", JSONObject(value.raw))

    private fun formationJson(value: FormationRuntime): JSONObject = JSONObject()
        .put("id", value.id)
        .put("name", value.name ?: JSONObject.NULL)
        .put("generalIds", JSONArray(value.generalIds))
        .put("status", value.status.name)
        .put("troopCount", value.troopCount ?: JSONObject.NULL)
        .put("raw", JSONObject(value.raw))

    private fun inventoryJson(value: InventoryItem): JSONObject = JSONObject()
        .put("id", value.id)
        .put("itemId", value.id)
        .put("templateId", value.templateId ?: JSONObject.NULL)
        .put("name", value.name)
        .put("type", value.type)
        .put("count", value.count)
        .put("quality", value.quality?.ordinal ?: JSONObject.NULL)
        .put("qualityName", value.quality?.name ?: JSONObject.NULL)
        .put("level", value.level ?: JSONObject.NULL)
        .put("enhanced", value.enhanced)
        .put("equipped", value.equipped)
        .put("famous", value.famous)
        .put("extraText", value.extraText)
        .put("equipmentMetadataComplete", value.equipmentMetadataComplete)

    private fun inventoryView(
        refreshed: List<InventoryItem>?,
        cached: String?,
        extra: Map<String, String>
    ): JSONObject {
        val all = refreshed?.let { JSONArray(it.map(::inventoryJson)) } ?: jsonArray(cached)
        val items = JSONArray()
        val equipment = JSONArray()
        for (index in 0 until all.length()) {
            val entry = all.optJSONObject(index) ?: continue
            if (entry.optString("type").equals("equipment", ignoreCase = true)) {
                equipment.put(entry)
            } else {
                items.put(entry)
            }
        }
        return JSONObject()
            .put("capacity", extra["inventoryCapacity"]?.toIntOrNull() ?: JSONObject.NULL)
            .put("itemCount", items.length())
            .put("items", items)
            .put("equipmentCount", equipment.length())
            .put("equipment", equipment)
            .put("sourceOpcode", extra["inventorySourceOpcode"].orEmpty())
    }

    private fun mapTargetJson(value: MapTarget): JSONObject = JSONObject()
        .put("id", value.id)
        .put("idHex", value.raw["idHex"] ?: value.id.toString(16).padStart(16, '0'))
        .put("name", value.raw["name"] ?: value.type)
        .put("kind", value.type)
        .put("type", value.type)
        .put("level", value.raw.intValue("level", "rank", "fz") ?: JSONObject.NULL)
        .put("x", value.coordinate.x)
        .put("y", value.coordinate.y)
        .put("compositionCode", value.raw["compositionCode"] ?: JSONObject.NULL)
        .put("rewardDescription", value.raw["rewardDescription"] ?: value.raw["loot"] ?: "")
        .put("raw", JSONObject(value.raw))

    private fun mineJson(value: MineSearchResult): JSONObject = JSONObject()
        .put("id", value.id)
        .put("idHex", value.raw["idHex"] ?: value.raw["resourcePointIdHex"] ?: value.id.toString(16).padStart(16, '0'))
        .put("kind", value.mineType.name)
        .put("type", value.mineType.name)
        .put("level", value.level ?: JSONObject.NULL)
        .put("x", value.coordinate.x)
        .put("y", value.coordinate.y)
        .put("reserve", value.reserve ?: JSONObject.NULL)
        .put("isEmpty", value.isEmpty)
        .put("defenderCount", value.defenseCount ?: 0)
        .put("raw", JSONObject(value.raw))

    private fun visitCandidateJson(value: GeneralVisitCandidate): JSONObject = JSONObject()
        .put("id", value.id)
        .put("name", value.name)
        .put("level", value.level)
        .put("fiefName", value.fiefName)
        .put("cityName", value.cityName)
        .put("captiveState", value.captiveState)
        .put("ownerName", value.ownerName)
        .put("loyalty", value.loyalty)
        .put("growth", value.growth)
        .put("available", value.captiveState == 0)
        .put("raw", JSONObject(value.raw))

    private fun fiefJson(value: LootTargetFief): JSONObject = JSONObject()
        .put("index", value.index)
        .put("targetId", value.targetId)
        .put("cityName", value.cityName)
        .put("name", value.name)
        .put("fiefName", value.name)
        .put("serialByte", value.serialByte ?: JSONObject.NULL)
        .put("mapFlag", value.mapFlag ?: JSONObject.NULL)
        .put("x", value.x ?: JSONObject.NULL)
        .put("y", value.y ?: JSONObject.NULL)

    private fun protocolFailure(request: AssistantApiRequest, result: ProtocolResult.Err): AssistantApiResponse =
        failure(request, if (result.retryable) 503 else 409, result.message, result.code)

    private fun success(request: AssistantApiRequest, data: JSONObject = JSONObject()): AssistantApiResponse {
        data.put("ok", true)
        return AssistantApiResponse(request.id, 200, data)
    }

    private fun failure(request: AssistantApiRequest, status: Int, message: String, code: String? = null): AssistantApiResponse {
        val body = JSONObject().put("ok", false).put("error", message)
        code?.let { body.put("code", it) }
        return AssistantApiResponse(request.id, status, body)
    }

    private fun query(path: String): Map<String, String> = path.substringAfter('?', "")
        .split('&')
        .mapNotNull { pair ->
            if (pair.isBlank()) return@mapNotNull null
            pair.substringBefore('=') to pair.substringAfter('=', "")
        }
        .toMap()

    private fun JSONObject.longValue(vararg keys: String): Long? {
        keys.forEach { key ->
            if (!has(key) || isNull(key)) return@forEach
            val raw = optString(key).trim()
            raw.toLongOrNull()?.takeIf { it > 0L }?.let { return it }
            raw.removePrefix("0x").removePrefix("0X").toLongOrNull(16)?.takeIf { it > 0L }?.let { return it }
        }
        return null
    }

    private fun JSONObject.longList(vararg keys: String): List<Long> {
        keys.forEach { key ->
            val array = optJSONArray(key) ?: return@forEach
            val values = (0 until array.length()).mapNotNull { index ->
                val raw = array.optString(index).trim()
                raw.toLongOrNull()?.takeIf { it > 0L }
                    ?: raw.removePrefix("0x").removePrefix("0X").toLongOrNull(16)?.takeIf { it > 0L }
            }
            if (values.isNotEmpty()) return values.distinct()
        }
        return emptyList()
    }

    private fun JSONObject.longListPreservingOrder(vararg keys: String): List<Long> {
        keys.forEach { key ->
            val array = optJSONArray(key) ?: return@forEach
            return (0 until array.length()).mapNotNull { index ->
                val raw = array.optString(index).trim()
                raw.toLongOrNull()?.takeIf { it > 0L }
                    ?: raw.removePrefix("0x").removePrefix("0X").toLongOrNull(16)?.takeIf { it > 0L }
            }
        }
        return emptyList()
    }

    private fun cachedBrushFiefLocations(
        extra: Map<String, String>,
        generals: JSONArray
    ): List<BrushFiefLocation> {
        val byId = linkedMapOf<Long, BrushFiefLocation>()
        val stored = jsonArray(extra["ownedFiefLocationsJson"])
        for (index in 0 until stored.length()) {
            val item = stored.optJSONObject(index) ?: continue
            val fiefId = item.longValue("targetId", "fiefId", "id") ?: continue
            byId[fiefId] = BrushFiefLocation(
                fiefId = fiefId,
                fiefName = item.optString("fiefName", item.optString("name")),
                cityName = item.optString("cityName", item.optString("city")),
                x = item.intOrNull("x", "fiefX"),
                y = item.intOrNull("y", "fiefY")
            )
        }
        for (index in 0 until generals.length()) {
            val item = generals.optJSONObject(index) ?: continue
            val fiefId = item.longValue("fiefId", "placeID", "placeId") ?: continue
            if (fiefId in byId) continue
            val raw = item.optJSONObject("raw")
            val x = item.intOrNull("fiefX") ?: raw?.intOrNull("fiefX")
            val y = item.intOrNull("fiefY") ?: raw?.intOrNull("fiefY")
            if (x == null || y == null) continue
            byId[fiefId] = BrushFiefLocation(
                fiefId = fiefId,
                fiefName = item.optString("fiefName", raw?.optString("fiefName").orEmpty()),
                cityName = item.optString("cityName", raw?.optString("cityName").orEmpty()),
                x = x,
                y = y
            )
        }
        return byId.values.toList()
    }

    private fun JSONObject.intOrNull(vararg keys: String): Int? {
        keys.forEach { key ->
            if (has(key) && !isNull(key)) optString(key).trim().toIntOrNull()?.let { return it }
        }
        return null
    }

    private fun JSONObject.intList(vararg keys: String): List<Int> {
        keys.forEach { key ->
            val array = optJSONArray(key)
            if (array != null) return (0 until array.length()).mapNotNull { array.optString(it).toIntOrNull() }
            if (has(key)) optString(key).toIntOrNull()?.let { return listOf(it) }
        }
        return emptyList()
    }

    private fun JSONObject.stringList(vararg keys: String): List<String> {
        keys.forEach { key ->
            val array = optJSONArray(key)
            if (array != null) return (0 until array.length()).map { array.optString(it).trim() }.filter { it.isNotBlank() }
            if (has(key)) return optString(key).split(',', '，', ';', '；', '|').map(String::trim).filter { it.isNotBlank() }
        }
        return emptyList()
    }

    private fun JSONObject.coordinate(xKey: String, yKey: String): MapCoordinate = MapCoordinate(
        optInt(xKey, optJSONObject("start")?.optInt("x", 0) ?: 0),
        optInt(yKey, optJSONObject("start")?.optInt("y", 0) ?: 0)
    )

    private fun JSONObject.toMapTarget(): MapTarget? {
        val id = longValue("id", "targetId", "targetID", "idHex", "targetIdHex") ?: return null
        val x = optInt("x", optJSONObject("coordinate")?.optInt("x", 0) ?: 0)
        val y = optInt("y", optJSONObject("coordinate")?.optInt("y", 0) ?: 0)
        val type = optString("type", optString("kind", optString("targetKind", "山贼"))).ifBlank { "山贼" }
        return MapTarget(id, MapCoordinate(x, y), type, toStringMap())
    }

    private fun JSONObject.toMineSearchResult(): MineSearchResult? {
        val id = longValue("id", "mineId", "resourceId", "idHex", "resourcePointIdHex") ?: return null
        val type = parseMineType(optString("mineType", optString("type", optString("kind")))) ?: return null
        return MineSearchResult(
            id = id,
            coordinate = MapCoordinate(optInt("x", 0), optInt("y", 0)),
            mineType = type,
            level = optInt("level", 0).takeIf { it > 0 },
            reserve = optLong("reserve", optLong("amount", 0L)).takeIf { it > 0L },
            isEmpty = optBoolean("isEmpty", false),
            defenseCount = optInt("defenderCount", optInt("defenseCount", 0)),
            raw = toStringMap()
        )
    }

    private fun JSONObject.toStringMap(): Map<String, String> = keys().asSequence().associateWith { key ->
        when (val value = opt(key)) {
            is JSONObject, is JSONArray -> value.toString()
            JSONObject.NULL -> ""
            else -> value?.toString().orEmpty()
        }
    }

    private fun Map<String, String>.intValue(vararg keys: String): Int? = keys.firstNotNullOfOrNull { key -> this[key]?.toIntOrNull() }

}

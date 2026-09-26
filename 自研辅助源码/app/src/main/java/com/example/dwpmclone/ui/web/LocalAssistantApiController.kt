package com.example.dwpmclone.ui.web

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.pm.ApplicationInfo
import android.os.Build
import com.example.dwpmclone.BuildConfig
import com.example.dwpmclone.data.account.AccountLoginState
import com.example.dwpmclone.data.account.AccountStateEvents
import com.example.dwpmclone.data.account.AccountTransitionDetails
import com.example.dwpmclone.data.account.AccountTransitionInput
import com.example.dwpmclone.data.local.KeystoreCredentialVault
import com.example.dwpmclone.data.local.DismissedNoticeRepository
import com.example.dwpmclone.data.local.ExpeditionTransactionRepository
import com.example.dwpmclone.data.local.AssistantBehaviorContractAssetLoader
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.LocalConfigRepository
import com.example.dwpmclone.data.local.LogAudience
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.HostingInterruptionReport
import com.example.dwpmclone.data.local.LocalGuideRepository
import com.example.dwpmclone.data.local.LocalHostingRuntimeRepository
import com.example.dwpmclone.data.local.LocalMapRepository
import com.example.dwpmclone.data.local.ProcessExitReader
import com.example.dwpmclone.data.local.RequestHealthRepository
import com.example.dwpmclone.data.local.SessionReconnectRepository
import com.example.dwpmclone.data.local.TaskLogEntry
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.local.TaskRuntimeStatusRepository
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.Channel
import com.example.dwpmclone.domain.model.GameVersion
import com.example.dwpmclone.domain.localmap.LocalMapKind
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import com.example.dwpmclone.domain.protocol.ExpeditionTransactionState
import com.example.dwpmclone.data.protocol.RealGameProtocolClient
import com.example.dwpmclone.domain.protocol.State8004GeneralEvidenceParser
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.protocol.UserFacingTextLocalizer
import com.example.dwpmclone.domain.scheduler.ResidentTaskActivationPolicy
import com.example.dwpmclone.domain.scheduler.SchedulerTaskOrdering
import com.example.dwpmclone.domain.scheduler.TaskRuntimeState
import com.example.dwpmclone.host.AppUpdateChecker
import com.example.dwpmclone.host.ConfigBackupAccount
import com.example.dwpmclone.host.ConfigBackupCodec
import com.example.dwpmclone.host.ConfigBackupImporter
import com.example.dwpmclone.host.ConfigImportTarget
import com.example.dwpmclone.host.MembershipClient
import com.example.dwpmclone.host.ResolvedImportAccount
import com.example.dwpmclone.host.SharedPythonCoreHost
import com.example.dwpmclone.service.AssistantForegroundService
import com.example.dwpmclone.ui.hosting.BackgroundHostingPermissionState
import java.net.URLDecoder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

/**
 * Version marker the shared core stamps on its bag projection once the 0x8104
 * trailer (where the bag limit really lives) is read.  Must match
 * `INVENTORY_PARSER_VERSION` in `shared_core/python/dwpm_core/facade.py`.
 */
internal const val INVENTORY_PARSER_VERSION = "8104-trailer-v1"

/** Small allow-listed adapter from the shared Web UI contract to on-device repositories. */
class LocalAssistantApiController(
    context: Context,
    private val onBackgroundPermissionAction: (String) -> Boolean = { false },
    private val onHostingStarted: () -> Unit = {},
) {
    private val appContext = context.applicationContext
    private val sharedPythonCore = SharedPythonCoreHost.get(appContext)
    private val accounts = LocalAccountRepository(appContext)
    private val configs = LocalConfigRepository(appContext)
    private val logs = TaskLogRepository(appContext)
    private val runtimeStatuses = TaskRuntimeStatusRepository(appContext)
    private val dailyStats = LocalDailySuccessStatsRepository(appContext)
    private val requestHealth = RequestHealthRepository(appContext)
    private val credentialVault = KeystoreCredentialVault(appContext)
    private val reconnects = SessionReconnectRepository(appContext)
    private val expeditionTransactions = ExpeditionTransactionRepository(appContext)
    private val dismissedNotices = DismissedNoticeRepository(appContext)
    private val localMaps = LocalMapRepository(appContext)
    private val guideAssets = LocalGuideRepository(appContext)
    private val behaviorContract = AssistantBehaviorContractAssetLoader.load(appContext)
    private val localOperations = LocalProtocolOperationService(
        accounts = accounts,
        dailyStats = dailyStats,
        taskOverviewProvider = { accountId -> taskOverview(accountId) }
    )

    fun handle(request: AssistantApiRequest): AssistantApiResponse = runCatching {
        val route = request.path.substringBefore('?')
        if (route.startsWith("/api/member/")) {
            val action = route.removePrefix("/api/member/")
            if (com.example.dwpmclone.BuildConfig.DEBUG && request.method == "POST" && action == "payment-acceptance-create") {
                val value = com.example.dwpmclone.host.MembershipClient.get(appContext).handle(action, request.body ?: JSONObject())
                return@runCatching AssistantApiResponse(request.id, if (value.optBoolean("ok")) 200 else 400, value)
            }
            if ((request.method == "GET" && action in setOf("status", "payment-catalog")) ||
                (request.method == "POST" && action in setOf("check", "send-code", "register", "login", "reset-password", "logout", "payment-create", "payment-status", "payment-open", "payment-store-open"))) {
                val value = com.example.dwpmclone.host.MembershipClient.get(appContext)
                    .handle(action, request.body ?: JSONObject())
                return@runCatching AssistantApiResponse(request.id, if (value.optBoolean("ok")) 200 else 400, value)
            }
            if (request.method == "POST" && action in setOf("config-export", "config-import")) {
                val body = request.body ?: JSONObject()
                val value = runCatching { if (action == "config-export") configExport(body) else configImport(body) }
                    .getOrElse { error ->
                        JSONObject().put("ok", false).put("error", error.message ?: "配置导出导入失败，请稍后重试")
                    }
                return@runCatching AssistantApiResponse(request.id, if (value.optBoolean("ok")) 200 else 400, value)
            }
            return@runCatching failure(request, 404, "会员接口不存在")
        }
        if ((request.method == "GET" &&
                route in setOf("/api/military/intel", "/api/state/refresh", "/api/heartbeat")) ||
            (request.method == "POST" &&
                route in setOf(
                    "/api/daily/general-visit/candidates",
                    "/api/raid/fiefs",
                    "/api/formations/unassign-all",
                    "/api/troops/assign",
                    "/api/troops/refill",
                    "/api/troops/heal",
                    "/api/inventory/open-one",
                    "/api/brush/search",
                    "/api/brush/execute",
                    "/api/mine/search",
                    "/api/mine/execute",
                    "/api/liubu/hubu/query",
                    "/api/liubu/hubu/plant",
                    "/api/daily/sign-in/claim",
                    "/api/daily/arena-coins/claim",
                    "/api/daily/donate/claim",
                    "/api/daily/donate/custom",
                    "/api/daily/salary/claim",
                    "/api/daily/national-collect/claim",
                    "/api/daily/city-lord-collect/claim",
                    "/api/daily/general-visit/claim",
                    "/api/domestic/query",
                    "/api/domestic/action"
                ))
        ) {
            return@runCatching submitSharedNetworkOperation(request, route)
        }
        localOperations.tryHandle(request)?.let { return@runCatching it }
        when (request.method to route) {
            "GET" to "/api/app/update" -> appUpdate(request)
            "POST" to "/api/app/update-open" -> appUpdateJson(request, AppUpdateChecker.get(appContext).openDownload())
            "POST" to "/api/app/site-open" -> appUpdateJson(request, AppUpdateChecker.get(appContext).openSite())
            "POST" to "/api/app/copy-group-number" -> copyGroupNumber(request)
            "GET" to "/api/health" -> sharedCoreHealth(request)
            "GET" to "/api/core/operations" -> sharedCoreOperations(request)
            "GET" to "/api/core/operations/status" -> sharedCoreOperationStatus(request)
            "GET" to "/api/core/verification/protocol" -> sharedCoreProtocolVerification(request)
            "GET" to "/api/accounts" -> sharedCoreAccounts(request)
            "GET" to "/api/areas" -> areaCatalog(request)
            "GET" to "/api/reference/guide" -> referenceGuide(request)
            "GET" to "/api/background/permissions" -> backgroundPermissions(request)
            "GET" to "/api/accounts/settings" -> accountSettings(request)
            "GET" to "/api/logs/system" -> systemLogs(request)
            "GET" to "/api/logs/account" -> accountLogs(request)
            "GET" to "/api/automation/status" -> automationStatus(request)
            "GET" to "/api/success-records" -> successRecords(request)
            "GET" to "/api/maps/bandits" -> localMap(request, LocalMapKind.BANDIT)
            "GET" to "/api/maps/mines" -> localMap(request, LocalMapKind.MINE)
            "POST" to "/api/logs/account" -> appendAccountLog(request)
            "POST" to "/api/logs/system/clear" -> clearLogs(request)
            "POST" to "/api/notices/dismiss" -> dismissNotice(request)
            "POST" to "/api/background/permissions/open" -> openBackgroundPermission(request)
            "POST" to "/api/brush/recommended-center" -> brushRecommendedCenter(request)
            "POST" to "/api/formations/apply" -> submitSharedNetworkOperation(request, route)
            "POST" to "/api/accounts/add" -> addAccount(request)
            "POST" to "/api/accounts/start" -> startAccount(request)
            "POST" to "/api/accounts/stop" -> stopAccount(request)
            "POST" to "/api/accounts/delete" -> deleteAccount(request)
            "POST" to "/api/core/operations/simulate" -> submitSimulatedCoreOperation(request)
            "POST" to "/api/core/operations/cancel" -> cancelCoreOperation(request)
            "POST" to "/api/automation/start-saved" -> startSavedTasks(request)
            "POST" to "/api/automation/stop" -> stopAutomation(request)
            "POST" to "/api/formations/save",
            "POST" to "/api/raid/execute",
            "POST" to "/api/mine/save",
            "POST" to "/api/liubu/save",
            "POST" to "/api/lossless/execute",
            "POST" to "/api/dungeon/execute",
            "POST" to "/api/military/future/save",
            "POST" to "/api/settings/save" -> saveMappedSettings(request, route)
            else -> failure(request, 404, "手机本地核心尚未开放：${request.method} $route")
        }
    }.getOrElse { error ->
        failure(
            request,
            if (error is IllegalArgumentException) 400 else 500,
            error.message ?: "手机本地核心处理失败"
        )
    }

    private fun sharedCoreHealth(request: AssistantApiRequest): AssistantApiResponse {
        val dispatched = sharedPythonCore.dispatch(
            "GET",
            "/api/health",
            requestContext = JSONObject()
                .put("requestId", request.id)
                .put("source", "android-webview")
        )
        val status = dispatched.optInt("status", 500)
        val health = (dispatched.optJSONObject("body") ?: JSONObject())
        val migratedRoutes = health.optJSONArray("migratedRoutes") ?: JSONArray()
        health
            .put("apiVersion", AssistantApiResponse.API_VERSION)
            .put(
                "androidBusinessOwner",
                "shared-python",
            )
            .put("androidRouteBusinessOwner", "shared-python")
            .put("androidLegacyBusinessOwner", "none")
            .put(
                "androidRemainingKotlinBackgroundOwners",
                JSONArray(),
            )
            .put("sharedPythonMigratedRoute", migratedRoutes.optString(0))
            .put("sharedPythonMigratedRoutes", migratedRoutes)
            .put("androidPythonHost", sharedPythonCore.metrics())
        return AssistantApiResponse(request.id, status, health)
    }

    private fun sharedCoreAccounts(request: AssistantApiRequest): AssistantApiResponse {
        val nowMillis = System.currentTimeMillis()
        val publicAccounts = accounts.listPublicAccounts()
        val dispatched = dispatchAccountProjection(
            publicAccounts,
            nowMillis,
            request.id
        )
        return AssistantApiResponse(
            request.id,
            dispatched.optInt("status", 500),
            dispatched.optJSONObject("body") ?: JSONObject()
        )
    }

    private fun areaCatalog(request: AssistantApiRequest): AssistantApiResponse {
        val platform = query(request.path)["platform"].orEmpty()
        return dispatchSharedLocal(
            request,
            "/api/areas",
            JSONObject()
                .put("platform", platform)
                .put("areas", JSONArray())
        )
    }

    private fun referenceGuide(request: AssistantApiRequest): AssistantApiResponse {
        val params = query(request.path)
        val resource = params["resource"].orEmpty()
        val body = JSONObject().put("resource", resource)
        when (resource) {
            "famous-generals" -> body.put(
                "sourceText",
                guideAssets.readFamousGeneralsSource()
            )
            "article" -> {
                val articleId = params["id"].orEmpty()
                body.put("id", articleId)
                guideAssets.readGuideArticleSource(articleId)?.let { source ->
                    body.put("sourceText", source)
                }
            }
            "open-server-calculation" -> body
                .put("versionIndex", params["versionIndex"].orEmpty())
                .put("server", params["server"].orEmpty())
        }
        return dispatchSharedLocal(request, "/api/reference/guide", body)
    }

    private fun backgroundPermissions(request: AssistantApiRequest): AssistantApiResponse =
        ok(
            request,
            BackgroundHostingPermissionState.read(appContext).toJson()
                // Surfaced next to the permission checklist on purpose: the page
                // a user opens after "it stopped overnight" should also answer
                // how long it was down and whether a setting explains it.
                .put("lastInterruption", lastInterruptionJson()),
        )


    private fun lastInterruptionJson(): Any = runCatching {
        HostingInterruptionReport.of(
            runtime = LocalHostingRuntimeRepository(appContext).snapshot(),
            exits = ProcessExitReader.read(appContext),
            nowMillis = System.currentTimeMillis(),
            mainProcessName = appContext.packageName,
            lastUpdateTimeMillis = ProcessExitReader.lastUpdateTimeMillis(appContext),
        ).toJson()
    }.getOrDefault(JSONObject.NULL)

    private fun openBackgroundPermission(request: AssistantApiRequest): AssistantApiResponse {
        val action = request.body?.optString("action").orEmpty().trim()
        if (action.isBlank()) return failure(request, 400, "缺少权限设置类型")
        if (!onBackgroundPermissionAction(action)) {
            return failure(request, 400, "不支持的权限设置：$action")
        }
        return ok(
            request,
            JSONObject()
                .put("accepted", true)
                .put("action", action),
        )
    }

    private fun submitSharedNetworkOperation(
        request: AssistantApiRequest,
        route: String
    ): AssistantApiResponse {
        val body = JSONObject(request.body?.toString() ?: "{}")
        val query = query(request.path)
        val accountId = sequenceOf(
            query["sessionId"],
            body.optString("accountRef"),
            body.optString("sessionId")
        ).mapNotNull { it?.toLongOrNull() }.firstOrNull { it > 0L }
            ?: return failure(request, 400, "缺少账号")
        if (route == "/api/state/refresh") {
            body.put("scope", query["scope"].orEmpty().ifBlank { "all" })
        }
        if (route == "/api/troops/heal") {
            val general = configs.loadFeatureConfig(
                accountId,
                LocalSettingsConfigMapper.GENERAL
            )?.optJSONObject("values") ?: JSONObject()
            val brush = configs.loadFeatureConfig(
                accountId,
                LocalSettingsConfigMapper.BRUSH
            )?.optJSONObject("values") ?: JSONObject()
            if (!body.has("foodToCopper")) {
                body.put(
                    "foodToCopper",
                    if (general.has("foodToCopper")) {
                        general.optBoolean("foodToCopper", false)
                    } else {
                        brush.optBoolean("foodToCopper", false)
                    }
                )
            }
            if (!body.has("copperFloorWan")) {
                body.put(
                    "copperFloorWan",
                    if (general.has("copperFloorWan")) {
                        general.optInt("copperFloorWan", 1)
                    } else {
                        brush.optInt("copperFloorWan", 1)
                    }
                )
            }
            if (!body.has("healAllIfCountUnknown") &&
                general.has("healAllIfCountUnknown")
            ) {
                body.put(
                    "healAllIfCountUnknown",
                    general.optBoolean("healAllIfCountUnknown", true)
                )
            }
        }
        if (route == "/api/brush/execute" || route == "/api/mine/execute") {
            // The shared expedition workflow owns preflight, formation selection,
            // healing/energy/loyalty preparation and dispatch success semantics.
            // Android only supplies the saved platform facts; it must not rebuild
            // a second set of those rules in Kotlin or require the page to send them.
            val habits = accountHabits(accountId)
            val config = habits.optJSONObject("config") ?: JSONObject()
            val formations = habits.optJSONArray("formations") ?: JSONArray()
            body.put(
                "hostSettings",
                JSONObject()
                    .put("formations", JSONArray(formations.toString()))
                    .put("config", JSONObject(config.toString()))
                    .put("healWounded", config.optBoolean("healWounded", true))
                    .put("autoEnergy", config.optBoolean("autoEnergy", true))
                    .put("energyThreshold", config.optInt("energyThreshold", 20))
                    .put("foodToCopper", config.optBoolean("foodToCopper", false))
                    .put("copperFloorWan", config.optInt("copperFloorWan", 1))
            )
        }
        val dispatched = sharedPythonCore.dispatch(
            request.method,
            route,
            body
                .put("accountRef", accountId.toString())
                .put("sessionId", accountId.toString()),
            JSONObject()
                .put("requestId", request.id)
                .put("source", "android-webview")
                .put("platform", "android")
        )
        return AssistantApiResponse(
            request.id,
            dispatched.optInt("status", 500),
            dispatched.optJSONObject("body") ?: JSONObject()
        )
    }

    private fun submitSimulatedCoreOperation(request: AssistantApiRequest): AssistantApiResponse {
        if (!pocRoutesEnabled()) return failure(request, 404, "共享核心 POC 路由仅在 Debug 版本开放")
        val body = request.body ?: JSONObject()
        val durationMillis = if (body.has("durationMillis")) {
            body.optLong("durationMillis", -1L)
        } else {
            90_000L
        }
        if (durationMillis !in 0L..600_000L) {
            return failure(request, 400, "durationMillis 必须在 0 到 600000 之间")
        }
        val idempotencyKey = body.optString("idempotencyKey", request.id).trim()
        if (idempotencyKey.isEmpty()) return failure(request, 400, "缺少幂等键")
        val payload = body.optJSONObject("payload") ?: JSONObject()
        val accepted = sharedPythonCore.submitSimulatedNetworkOperation(
            durationMillis,
            idempotencyKey,
            payload
        )
        return AssistantApiResponse(request.id, 202, accepted)
    }

    private fun sharedCoreOperationStatus(request: AssistantApiRequest): AssistantApiResponse {
        val operationId = query(request.path)["operationId"].orEmpty()
        if (operationId.isBlank()) return failure(request, 400, "缺少 operationId")
        val result = sharedPythonCore.operationStatus(operationId)
        return if (result.optBoolean("ok", false)) {
            AssistantApiResponse(request.id, 200, result)
        } else {
            AssistantApiResponse(request.id, 404, result)
        }
    }

    private fun sharedCoreOperations(request: AssistantApiRequest): AssistantApiResponse {
        return AssistantApiResponse(request.id, 200, sharedPythonCore.operationsSnapshot())
    }

    private fun sharedCoreProtocolVerification(request: AssistantApiRequest): AssistantApiResponse {
        if (!pocRoutesEnabled()) return failure(request, 404, "共享核心 POC 路由仅在 Debug 版本开放")
        val report = sharedPythonCore.protocolFixtureReport()
        val typedTransition = sharedPythonCore.accountStateTransition(
            state = AccountTransitionInput(
                desiredStarted = false,
                loginState = AccountLoginState.STOPPED,
                sessionCredentialPresent = false
            ),
            event = AccountStateEvents.USER_START,
            details = AccountTransitionDetails(),
            nowMillis = 1_000L
        )
        report.put(
            "androidTypedAccountTransition",
            JSONObject()
                .put("loginState", typedTransition.loginState)
                .put("nextOperation", typedTransition.nextOperation)
                .put("liveSessionUsable", typedTransition.liveSessionUsable)
        )
        return AssistantApiResponse(
            request.id,
            if (report.optBoolean("ok", false)) 200 else 500,
            report
        )
    }

    private fun cancelCoreOperation(request: AssistantApiRequest): AssistantApiResponse {
        val operationId = request.body?.optString("operationId").orEmpty()
        if (operationId.isBlank()) return failure(request, 400, "缺少 operationId")
        val result = sharedPythonCore.cancelOperation(operationId)
        return if (result.optBoolean("ok", false)) {
            AssistantApiResponse(request.id, 200, result)
        } else {
            AssistantApiResponse(request.id, 404, result)
        }
    }

    private fun pocRoutesEnabled(): Boolean =
        appContext.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0

    private fun addAccount(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少账号信息")
        val password = body.optString("password")
        val prepareBody = JSONObject(body.toString()).apply {
            remove("password")
            put("passwordPresent", password.isNotEmpty())
            put(
                "supportedPlatformKeys",
                JSONArray().put("sglm").put("downjoy")
            )
        }
        val prepared = sharedPythonCore.prepareAccountAdd(prepareBody)
        if (!prepared.optBoolean("ok", false)) {
            return failure(
                request,
                400,
                prepared.optJSONObject("error")?.optString("message")
                    ?: prepared.optString("error").ifBlank { "共享账号核心拒绝添加" }
            )
        }
        val plan = prepared.getJSONObject("plan")
        check(!plan.optBoolean("networkRequired", true)) {
            "账号草稿与密码落盘不得等待游戏网络"
        }
        val record = plan.getJSONObject("record")
        val accountId = record.getString("accountRef").toLongOrNull()
            ?.takeIf { it > 0L }
            ?: throw IllegalStateException("共享账号草稿 ID 无效")
        credentialVault.savePassword(accountId, password)
        if (accounts.get(accountId) == null) {
            runCatching {
                accounts.upsert(draftAccount(record))
            }.onFailure {
                credentialVault.delete(accountId)
            }.getOrThrow()
        }
        val dispatched = sharedPythonCore.dispatch(
            "POST",
            "/api/accounts/add",
            JSONObject()
                .put("accountRef", accountId.toString())
                .put("sessionId", accountId.toString()),
            JSONObject()
                .put("requestId", request.id)
                .put("source", "android-webview")
                .put("platform", "android")
        )
        return AssistantApiResponse(
            request.id,
            dispatched.optInt("status", 500),
            dispatched.optJSONObject("body") ?: JSONObject()
        )
    }

    /** Stopped local account built from the shared core's credential-free add draft. */
    private fun draftAccount(record: JSONObject): GameAccount = GameAccount(
        id = record.getString("accountRef").toLong(),
        displayName = record.optString("displayName").ifBlank { null },
        username = record.getString("username"),
        serverName = record.getString("serverName"),
        serverId = record.optString("serverId").ifBlank { null },
        gameVersion = runCatching {
            GameVersion.valueOf(record.getString("gameVersion"))
        }.getOrDefault(GameVersion.OTHER),
        channel = runCatching {
            Channel.valueOf(record.getString("channel"))
        }.getOrDefault(Channel.UNKNOWN),
        session = null,
        enabled = false,
        monarchName = null,
        nation = null,
        loginState = AccountLoginState.STOPPED,
        gameAuthSignEvidence = null,
        platform = record.getString("platform"),
        platformKey = record.getString("platformKey"),
        serial = record.optString("serial", "0"),
        serverQuery = record.getString("serverQuery")
    )

    /** Manual 换手机 export of every local game account, its settings and its sealed password. */
    private fun configExport(body: JSONObject): JSONObject {
        val password = body.optString("password")
        if (password.isEmpty()) return configTransferFailure("请输入会员密码，用来加密游戏密码")
        val membership = MembershipClient.get(appContext)
        val memberId = membership.memberId() ?: return configTransferFailure("请先登录会员账号")
        val local = accounts.listPublicAccounts()
        if (local.isEmpty()) return configTransferFailure("本机还没有游戏账号，无需导出")
        val stored = configs.exportAll().optJSONObject("configs") ?: JSONObject()
        val exported = local.map { account ->
            val prefix = "${account.id}::"
            val features = linkedMapOf<String, JSONObject>()
            stored.keys().forEach { key ->
                if (key.startsWith(prefix)) stored.optJSONObject(key)?.let { features[key.removePrefix(prefix)] = it }
            }
            ConfigBackupAccount(
                platformKey = account.platformKey,
                platform = account.platform,
                username = account.username,
                serverName = account.serverName,
                serverQuery = account.serverQuery,
                serverId = account.serverId,
                serial = account.serial,
                displayName = account.displayName,
                configs = features,
            )
        }
        // An unreadable Keystore entry exports that account without its password instead of failing.
        val passwords = local.map { runCatching { credentialVault.loadPassword(it.id) }.getOrNull() }
        val document = ConfigBackupCodec().encode(
            exported, passwords, memberId, password, "${Build.MANUFACTURER} ${Build.MODEL}",
            BuildConfig.VERSION_NAME, System.currentTimeMillis()
        )
        val uploaded = membership.configBackupPut(password, document)
        if (!uploaded.optBoolean("ok")) return uploaded
        return JSONObject()
            .put("ok", true)
            .put("accountCount", exported.size)
            .put("passwordCount", passwords.count { it != null })
            .put("configCount", exported.sumOf { it.configs.size })
            .put("backupInfo", uploaded.optJSONObject("backupInfo") ?: JSONObject())
    }

    /**
     * Two-step import: `confirm=false` only previews the cloud export; `confirm=true` applies it.
     * Accounts stay stopped, so nothing logs into the game until the user starts them.
     */
    private fun configImport(body: JSONObject): JSONObject {
        val password = body.optString("password")
        if (password.isEmpty()) return configTransferFailure("请输入会员密码，用来解开导出时加密的游戏密码")
        val membership = MembershipClient.get(appContext)
        val memberId = membership.memberId() ?: return configTransferFailure("请先登录会员账号")
        val running = accounts.listPublicAccounts().filter { it.enabled }
        if (running.isNotEmpty()) {
            return configTransferFailure(
                "请先在“助手”页停止所有游戏账号（${running.joinToString("、") { "${it.username}@${it.serverQuery}" }}），再导入配置"
            )
        }
        val fetched = membership.configBackupGet(password)
        if (!fetched.optBoolean("ok")) return fetched
        val codec = ConfigBackupCodec()
        val backup = codec.decode(fetched.getString("backup"))
        // The server has just verified this member password, so a failed unseal means the export
        // was made before a member password reset/change rather than a typo.
        val passwords = codec.openPasswords(backup, memberId, password)
        val target = configImportTarget()
        if (!body.optBoolean("confirm")) {
            val info = fetched.optJSONObject("backupInfo") ?: JSONObject()
            return JSONObject()
                .put("ok", true)
                .put("preview", true)
                .put("exportedAt", info.optLong("exportedAt", backup.exportedAt))
                .put("deviceName", info.optString("deviceName").ifBlank { backup.deviceName })
                .put("passwordsReadable", passwords != null)
                .put("accounts", JSONArray().apply {
                    backup.accounts.forEach { account ->
                        val resolved = target.resolve(account)
                        put(JSONObject()
                            .put("label", account.label)
                            .put("supported", resolved != null)
                            .put("existing", resolved?.exists == true)
                            .put("configCount", account.configs.size))
                    }
                })
        }
        if (passwords == null && !body.optBoolean("allowWithoutPasswords")) {
            return configTransferFailure("云端配置是用旧的会员密码导出的，游戏密码无法解开")
                .put("code", "CONFIG_BACKUP_PASSWORDS_LOCKED")
        }
        val summary = ConfigBackupImporter.apply(backup, passwords, target)
        return JSONObject()
            .put("ok", true)
            .put("added", JSONArray(summary.added))
            .put("merged", JSONArray(summary.merged))
            .put("skipped", JSONArray(summary.skipped))
            .put("passwordsRestored", summary.passwordsRestored)
            .put("passwordsMissing", JSONArray(summary.passwordsMissing))
            .put("configsRestored", summary.configsRestored)
    }

    private fun configImportTarget(): ConfigImportTarget = object : ConfigImportTarget {
        override fun resolve(account: ConfigBackupAccount): ResolvedImportAccount? {
            val prepared = sharedPythonCore.prepareAccountAdd(
                JSONObject()
                    .put("username", account.username)
                    .put("serverQuery", account.serverQuery)
                    .put("platform", account.platformKey)
                    .put("serial", account.serial)
                    .put("passwordPresent", true)
                    .put("supportedPlatformKeys", JSONArray().put("sglm").put("downjoy"))
            )
            if (!prepared.optBoolean("ok", false)) return null
            val record = prepared.getJSONObject("plan").getJSONObject("record")
            val accountId = record.getString("accountRef").toLongOrNull()?.takeIf { it > 0L } ?: return null
            return ResolvedImportAccount(accountId, accounts.getPublic(accountId) != null, record)
        }

        override fun hasPassword(accountId: Long): Boolean = credentialVault.hasPassword(accountId)

        override fun savePassword(accountId: Long, password: String) =
            credentialVault.savePassword(accountId, password)

        override fun create(resolved: ResolvedImportAccount, account: ConfigBackupAccount, password: String?) {
            if (password != null) credentialVault.savePassword(resolved.accountId, password)
            runCatching {
                val draft = draftAccount(resolved.draft)
                accounts.upsert(draft.copy(
                    displayName = account.displayName ?: draft.displayName,
                    serverId = account.serverId ?: draft.serverId,
                ))
            }.onFailure {
                if (password != null) credentialVault.delete(resolved.accountId)
            }.getOrThrow()
        }

        override fun saveConfig(accountId: Long, featureId: String, config: JSONObject) =
            configs.saveFeatureConfig(accountId, featureId, config)
    }

    private fun configTransferFailure(message: String): JSONObject =
        JSONObject().put("ok", false).put("error", message)

    /** `?check=1` asks the official site (cached ten minutes, `force=1` bypasses); otherwise local state only. */
    private fun appUpdate(request: AssistantApiRequest): AssistantApiResponse {
        val params = query(request.path)
        val checker = AppUpdateChecker.get(appContext)
        return appUpdateJson(request, if (params["check"] == "1") checker.check(force = params["force"] == "1") else checker.status())
    }

    private fun appUpdateJson(request: AssistantApiRequest, value: JSONObject): AssistantApiResponse =
        AssistantApiResponse(request.id, if (value.optBoolean("ok")) 200 else 400, value)

    /** WebView clipboard support is unreliable; only a plain QQ group number may be copied. */
    private fun copyGroupNumber(request: AssistantApiRequest): AssistantApiResponse {
        val number = request.body?.optString("number").orEmpty()
        if (!Regex("^[1-9][0-9]{4,11}$").matches(number)) return failure(request, 400, "群号格式无效")
        val clipboard = appContext.getSystemService(ClipboardManager::class.java)
            ?: return failure(request, 500, "无法访问剪贴板，请手动记下群号")
        clipboard.setPrimaryClip(ClipData.newPlainText("QQ群号", number))
        return AssistantApiResponse(request.id, 200, JSONObject().put("ok", true))
    }

    private fun startAccount(request: AssistantApiRequest): AssistantApiResponse {
        val account = requireAccount(request.body)
        if (!credentialVault.hasPassword(account.id)) {
            return failure(request, 409, "该账号尚未保存本机登录凭据，请点“修改”重新输入游戏密码；保留原账号和区服，不要删除账号")
        }
        runCatching { onHostingStarted() } // Optional warning, never requests or blocks permissions.
        val dispatched = sharedPythonCore.dispatch(
            "POST",
            "/api/accounts/start",
            JSONObject()
                .put("accountRef", account.id.toString())
                .put("sessionId", account.id.toString()),
            JSONObject()
                .put("requestId", request.id)
                .put("source", "android-webview")
                .put("platform", "android")
        )
        return AssistantApiResponse(
            request.id,
            dispatched.optInt("status", 500),
            dispatched.optJSONObject("body") ?: JSONObject()
        )
    }

    private fun stopAccount(request: AssistantApiRequest): AssistantApiResponse {
        val account = requireAccount(request.body)
        val planned = dispatchSharedLocal(
            request,
            "/api/accounts/stop",
            JSONObject(request.body?.toString() ?: "{}")
                .put("accountRef", account.id.toString())
        )
        if (planned.status !in 200..299) return planned
        val plan = planned.body.optJSONObject("plan")
            ?: throw IllegalStateException("共享停止账号计划缺失")
        check(!plan.optBoolean("networkRequired", true)) {
            "停止账号不得等待游戏网络"
        }
        val write = plan.getJSONObject("write")
        check(write.optString("accountRef") == account.id.toString()) {
            "共享停止账号计划账号不匹配"
        }
        // “停止” and “仅退出当前页面” are different operations. Persist the explicit stop so
        // a later account login cannot silently restore resident brush/dungeon tasks.
        setSavedTasksStarted(
            account.id,
            write.optBoolean("savedTasksStarted", false)
        )
        accounts.setEnabled(
            account.id,
            write.optBoolean("enabled", false),
            write.optString("loginState", AccountLoginState.STOPPED)
        )
        runtimeStatuses.markAccountStopped(
            account.id,
            System.currentTimeMillis(),
            write.optString("runtimeReason").ifBlank {
                "用户已停止该账号的手机本地托管"
            }
        )
        if (accounts.listAccounts().none { it.enabled && it.session?.sourceMode == 1 }) {
            AssistantForegroundService.stop(appContext)
        } else if (AssistantForegroundService.isExecutionOwnerActive()) {
            AssistantForegroundService.refresh(appContext)
        }
        logs.append("账号 ${account.id} 已从手机本地界面停止", "account", account.id)
        return ok(request, JSONObject().put("account", accountJson(accounts.get(account.id)!!)))
    }

    private fun deleteAccount(request: AssistantApiRequest): AssistantApiResponse {
        val account = requireAccount(request.body)
        val planned = dispatchSharedLocal(
            request,
            "/api/accounts/delete",
            JSONObject(request.body?.toString() ?: "{}")
                .put("accountRef", account.id.toString())
        )
        if (planned.status !in 200..299) return planned
        val plan = planned.body.optJSONObject("plan")
            ?: throw IllegalStateException("共享删除账号计划缺失")
        check(!plan.optBoolean("networkRequired", true)) {
            "删除账号不得等待游戏网络"
        }
        val write = plan.getJSONObject("write")
        check(write.optBoolean("deleteCredentialFirst", false)) {
            "共享删除账号计划必须先删凭据"
        }
        // Delete encrypted authentication material first. If a later metadata write fails, the
        // safer recoverable state is an account that needs to be re-added, never an orphan secret.
        credentialVault.delete(account.id)
        accounts.delete(account.id)
        configs.deleteAccountConfigs(account.id)
        requestHealth.clear(account.id)
        reconnects.delete(account.id)
        expeditionTransactions.deleteAccount(account.id)
        dismissedNotices.clearAccount(account.id)
        localMaps.clearAccount(account.id)
        runtimeStatuses.deleteAccount(account.id)
        if (accounts.listAccounts().none { it.enabled && it.session?.sourceMode == 1 }) {
            AssistantForegroundService.stop(appContext)
        }
        logs.append("账号 ${account.id} 已从手机本地删除", "account", account.id)
        return sharedCoreAccounts(request)
    }

    private fun startSavedTasks(request: AssistantApiRequest): AssistantApiResponse {
        val account = requireAccount(request.body)
        val savedTasksStarted = account.session?.channelExtra
            ?.get("savedTasksStarted")
            .equals("true", ignoreCase = true)
        val planned = dispatchSharedLocal(
            request,
            "/api/automation/start-saved",
            JSONObject(request.body?.toString() ?: "{}")
                .put("accountRef", account.id.toString())
                .put("accountEnabled", account.enabled)
                .put("loginState", account.loginState)
                .put("hasLiveSession", account.session?.sourceMode == 1)
                .put("savedTasksStarted", savedTasksStarted)
                .put(
                    "executionOwnerActive",
                    AssistantForegroundService.isExecutionOwnerActive()
                )
        )
        if (planned.status !in 200..299) return planned
        val plan = planned.body.optJSONObject("plan")
            ?: throw IllegalStateException("共享开始任务计划缺失")
        check(!plan.optBoolean("networkRequired", true)) {
            "开始保存任务不得等待登录或游戏网络"
        }
        val write = plan.getJSONObject("write")
        val activateNow = write.optBoolean("activateNow", false)
        // This route only persists the user's "run all saved resident tasks"
        // intent. The foreground scheduler will materialize configured tasks;
        // the page request must not rebuild the task plan or wait for login.
        val captivesValues = configs.loadFeatureConfig(account.id, LocalSettingsConfigMapper.CAPTIVES)
            ?.optJSONObject("values")
        val captivesEnabled = captivesValues?.optBoolean("captiveRelease", false) == true ||
            captivesValues?.optBoolean("captivePersuade", false) == true
        val residentKeys = behaviorContract.scheduler.residentPriority.keys +
            (if (captivesEnabled) setOf("captives") else emptySet())
        setSavedTasksStarted(
            account.id,
            write.optBoolean("savedTasksStarted", true),
            residentKeys
        )
        if (activateNow) {
            AssistantForegroundService.start(appContext)
            runCatching { onHostingStarted() }
        }
        val resumed = JSONObject().apply {
            if (activateNow) residentKeys.forEach { put(it, true) }
        }
        logs.append(
            if (activateNow) {
                "用户已开始执行保存的常驻任务"
            } else {
                "已保存开始任务意图，等待账号启动后执行"
            },
            "account",
            account.id
        )
        val responsePlan = plan.optJSONObject("response") ?: JSONObject()
        return ok(
            request,
            JSONObject()
                .put("alreadyStarted", responsePlan.optBoolean("alreadyStarted"))
                .put(
                    "waitingForAccountStart",
                    responsePlan.optBoolean("waitingForAccountStart")
                )
                .put("result", JSONObject().put("resumed", resumed).put("errors", JSONObject()))
                .put("taskOverview", taskOverview(account.id))
        )
    }

    private fun stopAutomation(request: AssistantApiRequest): AssistantApiResponse {
        val body = JSONObject(request.body?.toString() ?: "{}")
        val accountId = body.optString("sessionId").toLongOrNull()
        if (accountId != null) body.put("accountRef", accountId.toString())
        val planned = dispatchSharedLocal(
            request,
            "/api/automation/stop",
            body
        )
        if (planned.status !in 200..299) return planned
        val plan = planned.body.optJSONObject("plan")
            ?: throw IllegalStateException("共享停止任务计划缺失")
        check(!plan.optBoolean("networkRequired", true)) {
            "停止任务不得等待游戏网络"
        }
        val write = plan.getJSONObject("write")
        val stopped = JSONArray()
        if (write.optString("scope") == "account") {
            val resolvedAccountId = write.optString("accountRef").toLongOrNull()
                ?: throw IllegalArgumentException("停止任务账号无效")
            check(accounts.get(resolvedAccountId) != null) { "账号不存在" }
            setSavedTasksStarted(
                resolvedAccountId,
                write.optBoolean("savedTasksStarted", false)
            )
            runtimeStatuses.markAccountStopped(
                resolvedAccountId,
                System.currentTimeMillis(),
                "用户已停止该账号的自动任务，账号保持在线"
            )
            stopped.put("android-$resolvedAccountId-all")
            logs.append(
                "用户已停止自动任务，账号保持在线",
                "account",
                resolvedAccountId
            )
        } else {
            write.optString("taskId").takeIf(String::isNotBlank)?.let(stopped::put)
        }
        if (AssistantForegroundService.isExecutionOwnerActive()) {
            AssistantForegroundService.refresh(appContext)
        }
        return ok(request, JSONObject().put("stopped", stopped))
    }

    private fun saveMappedSettings(request: AssistantApiRequest, route: String): AssistantApiResponse {
        val account = requireAccount(request.body)
        val body = request.body ?: throw IllegalArgumentException("缺少设置内容")
        val planningBody = when (route) {
            "/api/formations/save",
            "/api/mine/save",
            "/api/raid/execute",
            "/api/lossless/execute",
            "/api/dungeon/execute" ->
                JSONObject(body.toString()).put(
                    "knownGenerals",
                    jsonArray(account.session?.channelExtra?.get("generalsJson"))
                )
            "/api/settings/save" -> {
                val habits = accountHabits(account.id)
                val sessionFacts = sessionJson(account)
                JSONObject(body.toString())
                    .put("oldConfig", habits.optJSONObject("config") ?: JSONObject())
                    .put("session", JSONObject()
                        .put("sessionId", account.id.toString())
                        .put("role", sessionFacts.optJSONObject("role") ?: JSONObject())
                        .put("roleState", sessionFacts.optJSONObject("roleState") ?: JSONObject()))
                    .put("knownGenerals", sessionFacts.optJSONArray("generals") ?: JSONArray())
                    .put("savedFormations", habits.optJSONArray("formations") ?: JSONArray())
                    .put("roleLevel", sessionFacts.optJSONObject("role")?.optInt("level", 0) ?: 0)
            }
            else -> body
        }
        val dispatched = sharedPythonCore.dispatch(
            request.method,
            route,
            planningBody,
            JSONObject()
                .put("requestId", request.id)
                .put("source", "android-webview")
                .put("platform", "android")
        )
        val planned = dispatched.optJSONObject("body") ?: JSONObject()
        if (
            dispatched.optInt("status", 500) != 200 ||
            !planned.optBoolean("ok", false)
        ) {
            throw IllegalArgumentException(
                planned.optString("error").ifBlank {
                    "共享设置核心拒绝保存"
                }
            )
        }
        val sharedPlan = planned.getJSONObject("plan")
        val mapping = settingsMappingFromSharedPlan(sharedPlan)
        val activationAllowed = sharedPlan.optBoolean(
            "activationAllowed",
            !mapping.disabled
        )
        val executionAccepted = activationAllowed && route != "/api/formations/save"
        val executionOwnerActive = AssistantForegroundService.isExecutionOwnerActive()
        val executionDecision = LocalSettingsExecutionPolicy.decide(
            accountEnabled = account.enabled,
            accountRunnable = account.loginState == AccountLoginState.ONLINE,
            executionOwnerActive = executionOwnerActive,
            executionRequested = executionAccepted,
        )
        mapping.configs.forEach { (featureId, values) ->
            configs.saveFeatureConfig(account.id, featureId, JSONObject().put("values", values))
        }
        // 俘虏营设置不在共享 config 白名单内，同六部一样按独立 feature 段落库。
        if (route == "/api/settings/save" && body.optString("scope") == "common.frequent") {
            body.optJSONObject("patch")?.optJSONObject("captives")?.let { captives ->
                val values = JSONObject()
                listOf(
                    "captiveRelease",
                    "captiveReleaseBelowGrowth",
                    "captivePersuade",
                    "captivePersuadeGrowth"
                ).filter(captives::has).forEach { key -> values.put(key, captives.opt(key)) }
                configs.saveFeatureConfig(
                    account.id,
                    LocalSettingsConfigMapper.CAPTIVES,
                    JSONObject().put("values", values)
                )
            }
        }
        val defeatPauseAcknowledgement = if (
            route == "/api/dungeon/execute" &&
            sharedPlan.optBoolean("acknowledgeDefeatOnSave", false)
        ) {
            runCatching {
                sharedPythonCore.acknowledgeDungeonDefeat(account.id.toString())
            }.getOrElse { error ->
                JSONObject()
                    .put("ok", false)
                    .put("acknowledged", false)
                    .put("reason", error.message ?: error.javaClass.simpleName)
            }
        } else {
            JSONObject()
                .put("ok", true)
                .put("acknowledged", false)
                .put("reason", "dungeon-config-disabled")
        }
        if (account.enabled) residentTaskActivation(route, mapping, body)?.let { (key, active) ->
            setResidentTaskActive(account.id, key, active)
        }
        // The foreground adapter always synchronizes the latest persisted habits
        // immediately before its next shared tick. Doing the same CPython write here
        // makes a local settings click wait behind the operation ledger and can also
        // revive stale execution intent. Commit locally, then let an already-running
        // owner refresh asynchronously (or defer until the next explicit account start).
        val residentAutomationSync = JSONObject()
            .put("ok", true)
            .put("changed", false)
            .put("deferred", true)
            .put(
                "reason",
                if (executionOwnerActive) {
                    "foreground-owner-refresh"
                } else {
                    "next-explicit-account-start"
                },
            )
        val featureNames = mapping.configs.keys.joinToString(",")
        logs.append("手机本地设置已保存：features=$featureNames", "config", account.id)
        if (executionDecision.shouldRefreshExecutionOwner) {
            AssistantForegroundService.refresh(appContext)
        }

        val data = JSONObject()
            .put("saved", true)
            .put("localWriteCommitted", true)
            .put("disabled", mapping.disabled)
            .put("accountHabits", accountHabits(account.id))
            .put("taskOverview", taskOverview(account.id))
            .put("savedFile", "手机本地存储/account-config.json")
            .put("savedFiles", JSONObject()
                .put("militaryFile", "手机本地存储/account-config.json")
                .put("ministryFile", "手机本地存储/account-config.json"))
            .put("stoppedTaskIds", JSONArray())
            .put("waitingForMilitaryStart", executionDecision.waitingForAccountStart)
            .put("residentAutomationSync", residentAutomationSync)

        val taskStarted = executionDecision.taskStarted
        data.put(
            "execution",
            JSONObject()
                .put("accepted", executionAccepted)
                .put("started", taskStarted)
                .put("waitingForAccountStart", executionDecision.waitingForAccountStart)
                .put("owner", "android-local-scheduler")
        )
        sharedPlan.optJSONObject("response")?.let { response ->
            response.keys().forEach { key -> data.put(key, response.opt(key)) }
        }

        when (route) {
            "/api/formations/save" -> {
                val formationExecution = LocalSettingsExecutionPolicy.decide(
                    accountEnabled = account.enabled,
                    accountRunnable = account.loginState == AccountLoginState.ONLINE,
                    executionOwnerActive = executionOwnerActive,
                    executionRequested = activationAllowed,
                )
                val applyTask = when {
                    !activationAllowed -> JSONObject()
                        .put("started", false)
                        .put("reason", data.optString("applyReason").ifBlank {
                            "当前没有可执行的配兵规则"
                        })
                    !formationExecution.taskStarted -> JSONObject()
                        .put("started", false)
                        .put("waitingForAccountStart", true)
                        .put("reason", "配兵规则已保存，等待账号启动后执行")
                    else -> {
                        val apply = sharedPythonCore.dispatch(
                            "POST",
                            "/api/formations/apply",
                            JSONObject()
                                .put("accountRef", account.id.toString())
                                .put("sessionId", account.id.toString())
                                .put("confirm", "apply-formations")
                                .put(
                                    "formations",
                                    data.optJSONArray("normalizedFormations") ?: JSONArray()
                                )
                                .put(
                                    "formationOptions",
                                    data.optJSONObject("formationOptions") ?: JSONObject()
                                ),
                            JSONObject()
                                .put("requestId", "${request.id}-apply-formations")
                                .put("source", "android-settings-follow-up")
                                .put("platform", "android")
                        )
                        val accepted = apply.optJSONObject("body") ?: JSONObject()
                        if (apply.optInt("status", 500) == 202 &&
                            accepted.optBoolean("accepted", false)
                        ) {
                            JSONObject()
                                .put("started", true)
                                .put("operationId", accepted.optString("operationId"))
                                .put("status", accepted.optString("status", "QUEUED"))
                                .put("deduplicated", accepted.optBoolean("deduplicated"))
                                .put("message", "配兵 operation 已受理，等待服务器真实回执")
                        } else {
                            JSONObject()
                                .put("started", false)
                                .put("activationError", accepted.optString("error").ifBlank {
                                    "配兵 operation 受理失败"
                                })
                                .put("reason", "设置已保存，但实际配兵未受理")
                        }
                    }
                }
                data.put("applyTask", applyTask)
                data.put(
                    "execution",
                    JSONObject()
                        .put("accepted", applyTask.optBoolean("started"))
                        .put("started", applyTask.optBoolean("started"))
                        .put(
                            "waitingForAccountStart",
                            applyTask.optBoolean("waitingForAccountStart")
                        )
                        .put("owner", "shared-python-operation")
                )
            }
            "/api/raid/execute" -> data.put("raidTask", schedulerTaskState(
                taskStarted,
                mapping.disabled,
                "掠夺任务已关闭",
                "账号启动后执行掠夺"
            ))
            "/api/mine/save" -> data.put("mineTask", schedulerTaskState(
                taskStarted,
                mapping.disabled,
                "打矿任务已关闭",
                "账号启动后执行打矿"
            ))
            "/api/liubu/save" -> {
                val values = mapping.configs.getValue(LocalSettingsConfigMapper.MINISTRIES)
                val supported = values.optBoolean("supportedEnabled", false)
                data.put("ministryTask", schedulerTaskState(
                    taskStarted && supported,
                    !supported,
                    data.optString("reason").ifBlank { "当前没有可执行的已确认动作" },
                    "账号启动后执行稻谷种植"
                ))
            }
            "/api/lossless/execute" -> {
                val values = mapping.configs.getValue(LocalSettingsConfigMapper.LOSSLESS)
                data.put("settings", values)
                    .put("rows", values.optJSONArray("rows") ?: JSONArray())
                    .put("losslessTask", schedulerTaskState(
                        taskStarted,
                        mapping.disabled,
                        "无损任务已关闭",
                        "账号启动后执行无损"
                    ))
            }
            "/api/dungeon/execute" -> {
                val values = mapping.configs.getValue(LocalSettingsConfigMapper.DUNGEON)
                data.put("rows", values.optJSONArray("rows") ?: JSONArray())
                    .put("mode", values.optString("mode", "loop"))
                    .put("defeatPauseAcknowledgement", defeatPauseAcknowledgement)
                    .put("dungeonTask", schedulerTaskState(
                        taskStarted,
                        mapping.disabled,
                        "副本任务已关闭",
                        "账号启动后执行副本"
                    ))
            }
            "/api/settings/save" -> {
                data.put("settingsWarnings", JSONArray())
                if (body.optString("scope") == "brush") {
                    data.put("brushTask", schedulerTaskState(
                        taskStarted,
                        mapping.disabled,
                        "刷黄任务已关闭",
                        "账号启动后执行刷黄"
                    ))
                }
            }
        }
        return ok(request, data)
    }

    private fun settingsMappingFromSharedPlan(plan: JSONObject): LocalSettingsMapping {
        check(!plan.optBoolean("networkRequired", true)) {
            "本地设置保存不得等待游戏网络"
        }
        val configsJson = plan.optJSONObject("configs") ?: JSONObject()
        val mapped = linkedMapOf<String, JSONObject>()
        configsJson.keys().forEach { featureId ->
            mapped[featureId] = configsJson.optJSONObject(featureId)
                ?: throw IllegalArgumentException("共享设置写入计划无效：$featureId")
        }
        check(mapped.isNotEmpty()) { "共享设置写入计划为空" }
        return LocalSettingsMapping(
            configs = mapped,
            disabled = plan.optBoolean("disabled", false)
        )
    }

    private fun schedulerTaskState(
        started: Boolean,
        disabled: Boolean,
        disabledReason: String,
        waitingReason: String
    ): JSONObject = JSONObject().put("started", started).apply {
        if (started) {
            put("message", "已交给手机本地调度器串行执行")
        } else {
            put("reason", if (disabled) disabledReason else waitingReason)
        }
    }

    private fun appendAccountLog(request: AssistantApiRequest): AssistantApiResponse {
        val planned = dispatchSharedLocal(
            request,
            "/api/logs/account",
            request.body ?: JSONObject()
        )
        if (planned.status !in 200..299) return planned
        val write = planned.body.optJSONObject("plan")
            ?.optJSONObject("write")
            ?: throw IllegalStateException("共享日志写入计划缺少 write")
        val message = write.optString("message")
        check(message.isNotBlank()) { "共享日志写入计划缺少 message" }
        logs.append(
            message,
            write.optString("source").ifBlank { "frontend" },
            write.optString("accountRef").toLongOrNull()
        )
        return ok(request)
    }

    private fun clearLogs(request: AssistantApiRequest): AssistantApiResponse {
        val planned = dispatchSharedLocal(request, "/api/logs/system/clear", request.body ?: JSONObject())
        if (planned.status !in 200..299) return planned
        logs.clear()
        return ok(request, JSONObject().put("cleared", true))
    }

    private fun systemLogs(request: AssistantApiRequest): AssistantApiResponse {
        val query = query(request.path)
        val limit = query["limit"]?.toIntOrNull()?.coerceIn(1, 1_500) ?: 200
        val afterId = query["afterId"]?.toLongOrNull()
        val entries = logs.recent(1_500)
        val body = JSONObject()
            .put("limit", limit)
            .put("maxLines", 1_500)
            .put("latestId", entries.maxOfOrNull { it.id } ?: 0L)
            .put("storage", "android-jsonl")
            .put("entries", JSONArray().apply {
                entries.forEach { entry -> put(rawLogJson(entry)) }
            })
        if (afterId != null) {
            body.put("afterId", afterId)
        }
        return dispatchSharedLocal(request, "/api/logs/system", body)
    }

    private fun accountLogs(request: AssistantApiRequest): AssistantApiResponse {
        val query = query(request.path)
        val accountId = query["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val limit = query["limit"]?.toIntOrNull()?.coerceIn(1, 100) ?: 100
        return dispatchSharedLocal(
            request,
            "/api/logs/account",
            JSONObject()
                .put("accountRef", accountId.toString())
                .put("accountKey", accountId.toString())
                .put("limit", limit)
                .put("maxLines", 100)
                .put("entries", JSONArray().apply {
                    // 运行日志 is an operator surface; diagnostics stay on the system-log side.
                    logs.recent(600, LogAudience.USER).forEach { entry -> put(rawLogJson(entry)) }
                })
        )
    }

    private fun successRecords(request: AssistantApiRequest): AssistantApiResponse {
        val params = query(request.path)
        val accountId = params["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val limit = params["limit"]?.toIntOrNull()?.coerceIn(1, 50) ?: 50
        val category = params["category"].orEmpty().trim()
        return dispatchSharedLocal(
            request,
            "/api/success-records",
            JSONObject()
                .put("accountRef", accountId.toString())
                .put("accountKey", accountId.toString())
                .put("limit", limit)
                .put("category", category)
                .put("logEntries", JSONArray().apply {
                    logs.recent(1_500).forEach { entry -> put(rawLogJson(entry)) }
                })
        )
    }

    private fun automationStatus(request: AssistantApiRequest): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        return dispatchSharedLocal(
            request,
            "/api/automation/status",
            JSONObject()
                .put("tasks", automationTasks(accountId))
                .put("assistantOperations", assistantOperations(accountId))
                .put("taskOverview", taskOverview(accountId))
        )
    }

    private fun dismissNotice(request: AssistantApiRequest): AssistantApiResponse {
        val account = requireAccount(request.body)
        val planned = dispatchSharedLocal(
            request,
            "/api/notices/dismiss",
            request.body ?: JSONObject()
        )
        if (planned.status !in 200..299) return planned
        val key = planned.body.optJSONObject("plan")
            ?.optJSONObject("write")
            ?.optString("noticeKey")
            .orEmpty()
        dismissedNotices.dismiss(account.id, key)
        return ok(request, JSONObject().put("taskOverview", taskOverview(account.id)))
    }

    private fun brushRecommendedCenter(
        request: AssistantApiRequest
    ): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少刷黄推荐中心参数")
        val account = requireAccount(body)
        val extra = account.session?.channelExtra.orEmpty()
        val roleLevel = extra["level"]?.toIntOrNull()
            ?: jsonObject(extra["roleStateJson"]).optInt("level", 0)
        return dispatchSharedLocal(
            request,
            "/api/brush/recommended-center",
            JSONObject()
                .put("generalIds", body.optJSONArray("generalIds") ?: JSONArray())
                .put("generals", resolvedGenerals(account, extra))
                .put("fiefs", jsonArray(extra["ownedFiefLocationsJson"]))
                .put("roleLevel", roleLevel)
                .put("enforceRoleLevel", true)
        )
    }

    private fun localMap(request: AssistantApiRequest, kind: LocalMapKind): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val account = accounts.getPublic(accountId) ?: return failure(request, 404, "账号不存在")
        val serverId = account.serverId
            ?: account.session?.channelExtra?.get("serverKey")
            ?: account.serverName.takeIf { it.isNotBlank() }
            ?: return failure(request, 409, "当前账号没有可识别的区服")
        val records = localMaps.list(accountId, serverId, kind)
        val route = when (kind) {
            LocalMapKind.BANDIT -> "/api/maps/bandits"
            LocalMapKind.MINE -> "/api/maps/mines"
        }
        return dispatchSharedLocal(
            request,
            route,
            JSONObject()
                .put("serverKey", serverId)
                .put(
                    "updatedAt",
                    records.maxOfOrNull { it.lastValidatedAtMillis } ?: 0L
                )
                .put("records", JSONArray().apply {
                    records.forEach { put(rawLocalMapJson(it)) }
                })
        )
    }

    private fun accountSettings(request: AssistantApiRequest): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val account = accounts.getPublic(accountId) ?: return failure(request, 404, "账号不存在")
        val all = configs.exportAll().optJSONObject("configs") ?: JSONObject()
        val selected = JSONObject()
        val prefix = "$accountId::"
        all.keys().forEach { key -> if (key.startsWith(prefix)) selected.put(key.removePrefix(prefix), all.opt(key)) }
        val dispatched = sharedPythonCore.dispatch(
            "GET",
            "/api/accounts/settings",
            JSONObject()
                .put("account", accountJson(account))
                .put("configDir", "手机本地存储")
                .put("fileName", "account-config.json")
                .put("filePath", "手机本地存储")
                .put("exists", true)
                .put("settings", selected),
            JSONObject()
                .put("requestId", request.id)
                .put("source", "android-webview")
                .put("platform", "android")
        )
        return AssistantApiResponse(
            request.id,
            dispatched.optInt("status", 500),
            dispatched.optJSONObject("body") ?: JSONObject()
        )
    }

    private fun accountJson(account: GameAccount): JSONObject {
        val publicAccount = accounts.getPublic(account.id) ?: account
        val nowMillis = System.currentTimeMillis()
        val dispatched = dispatchAccountProjection(
            listOf(publicAccount),
            nowMillis,
            "account-card-${account.id}-$nowMillis",
            accountRefs = listOf(account.id.toString())
        )
        check(dispatched.optInt("status", 500) == 200) {
            dispatched.optJSONObject("body")?.optString("error")
                ?: "共享账号展示投影失败"
        }
        return dispatched.getJSONObject("body")
            .getJSONArray("accounts")
            .optJSONObject(0)
            ?: throw IllegalStateException("共享账号展示投影缺少账号")
    }

    private fun dispatchAccountProjection(
        sourceAccounts: List<GameAccount>,
        nowMillis: Long,
        requestId: String,
        accountRefs: List<String>? = null
    ): JSONObject {
        val runtime = JSONObject()
        sourceAccounts.forEach { account ->
            runtime.put(account.id.toString(), accountRuntimeFacts(account))
        }
        val body = JSONObject().put("runtimeByAccount", runtime)
        accountRefs?.let { refs ->
            body.put("accountRefs", JSONArray().apply { refs.forEach(::put) })
        }
        return sharedPythonCore.dispatch(
            "GET",
            "/api/accounts",
            body,
            JSONObject()
                .put("requestId", requestId)
                .put("source", "android-webview")
                .put("platform", "android")
                .put("executionOwnerActive", AssistantForegroundService.isExecutionOwnerActive())
                .put("nowMillis", nowMillis)
        )
    }

    private fun accountRuntimeFacts(account: GameAccount): JSONObject {
        val retry = reconnects.state(account.id)
        val overview = taskOverview(account.id)
        return JSONObject()
            .put("reconnect", JSONObject()
                .put("failures", retry.failures)
                .put("nextAttemptAtMillis", retry.nextAttemptAtMillis)
                .put("reason", retry.reason)
                .put("failureKind", retry.failureKind))
            .put("accountHabits", accountHabits(account.id))
            .put(
                "session",
                if (account.session?.sourceMode == 1) sessionJson(account) else JSONObject.NULL
            )
            .put("recentGameRequests", JSONArray().apply {
                requestHealth.recent(account.id).forEach { item ->
                    put(JSONObject()
                        .put("status", if (item.success) "success" else "failure")
                        .put("purpose", item.purpose)
                        .put("time", item.timeMillis))
                }
            })
            .put("dailyStats", dailyStatsJson(account.id))
            .put("taskOverview", overview)
    }

    private fun sessionJson(account: GameAccount): JSONObject {
        val session = account.session ?: return JSONObject()
        val extra = session.channelExtra
        val roleState = jsonObject(extra["roleStateJson"])
        val roleName = extra["roleName"] ?: account.monarchName ?: account.displayName.orEmpty()
        val level = extra["level"]?.toIntOrNull() ?: roleState.optInt("level", 0)
        if (!roleState.has("roleName")) roleState.put("roleName", roleName)
        if (!roleState.has("level")) roleState.put("level", level)
        val persistedState = if (
            extra["officeName"].isNullOrBlank() && roleState.optString("officeName").isBlank()
        ) {
            extra["state8004PayloadHex"]?.takeIf(String::isNotBlank)?.let { payloadHex ->
                runCatching { RealGameProtocolClient().parsePersisted8004HeadHex(payloadHex) }.getOrNull()
            }
        } else {
            null
        }
        val officeName = sequenceOf(
            extra["officeName"],
            extra["officialTitle"],
            roleState.optString("officeName"),
            persistedState?.officeName
        ).firstOrNull { !it.isNullOrBlank() }.orEmpty()
        val officeId = sequenceOf(
            extra["officeIdUnsigned"]?.toIntOrNull(),
            extra["officeId"]?.toIntOrNull(),
            roleState.opt("officeIdUnsigned")?.toString()?.toIntOrNull(),
            roleState.opt("officeId")?.toString()?.toIntOrNull(),
            persistedState?.officeIdUnsigned
        ).firstOrNull { it != null }
        if (roleState.optString("officeName").isBlank() && officeName.isNotBlank()) {
            roleState.put("officeName", officeName)
        }
        if (!roleState.has("officeIdUnsigned") && officeId != null) {
            roleState.put("officeId", officeId).put("officeIdUnsigned", officeId)
        }
        val resources = jsonObject(extra["resourceStateJson"])
        resources.keys().forEach { key -> if (!roleState.has(key)) roleState.put(key, resources.opt(key)) }
        return JSONObject()
            .put("sessionId", account.id.toString())
            .put("username", account.username)
            .put("area", JSONObject().put("areaName", account.serverName).put("serverKey", account.serverId))
            .put("role", JSONObject()
                .put("roleId", account.id)
                .put("roleName", roleName)
                .put("level", level)
                .put("country", extra["nation"] ?: account.nation)
                .put("title", extra["title"])
                .put("officeId", officeId ?: JSONObject.NULL)
                .put("officeName", officeName))
            .put("roleState", roleState)
            .put("generals", resolvedGenerals(account, extra))
            .put("army", jsonArray(extra["armyJson"]))
            .put("inventory", inventoryView(extra))
            .put("dailyActivity", jsonObject(extra["dailyActivityJson"]))
            .put("dailyStats", dailyStatsJson(account.id))
            .put("accountHabits", accountHabits(account.id))
            .put("taskOverview", taskOverview(account.id))
            .put("militaryIntel", jsonObject(extra["militaryIntelJson"])
                .let { if (it.length() == 0) JSONObject().put("events", JSONArray()).put("statusByName", JSONObject()) else it })
            .put("militarySnapshot", jsonObject(extra["militarySnapshotJson"])
                .let { if (it.length() == 0) JSONObject().put("actions", JSONArray()).put("actionCount", 0).put("responded", false) else it })
    }

    private fun inventoryView(extra: Map<String, String>): JSONObject {
        val all = jsonArray(extra["inventoryJson"])
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
        // Blank/0 means the core could not read the limit.  A record without the
        // trailer parser's version marker was written by an older build, whose
        // "capacity" was an unrelated header counter (1863 on a real account):
        // unknown as well, until the next bag refresh rewrites it.  The page
        // then shows "上限未知" rather than "47/1863".
        val trailerRead = extra["inventoryParserVersion"] == INVENTORY_PARSER_VERSION
        val capacity = extra["inventoryCapacity"]?.toIntOrNull()?.takeIf { trailerRead && it > 0 }
        // The server sends the stack count and the equipment count, never their
        // sum; the core adds them.  Fall back to the rows we hold for records
        // written before the core stored the sum.
        val slotsUsed = extra["inventorySlotsUsed"]?.toIntOrNull()
            ?: (items.length() + equipment.length())
        return JSONObject()
            .put("capacity", capacity ?: JSONObject.NULL)
            // Why the limit is missing, so the page can distinguish "not read
            // yet by this build" from "unreadable"; the former resolves on the
            // account's next bag refresh with no action from the user.
            .put("capacityPending", !trailerRead && (items.length() + equipment.length()) > 0)
            .put("slotsUsed", slotsUsed)
            .put("slotsFree", capacity?.let { maxOf(0, it - slotsUsed) } ?: JSONObject.NULL)
            .put("itemCount", items.length())
            .put("items", items)
            .put("equipmentCount", equipment.length())
            .put("equipment", equipment)
            .put("sourceOpcode", extra["inventorySourceOpcode"].orEmpty())
    }

    private fun resolvedGenerals(account: GameAccount, extra: Map<String, String>): JSONArray {
        val stored = jsonArray(extra["generalsJson"])
        if (extra["generalsParserVersion"] == State8004GeneralEvidenceParser.PARSER_VERSION) {
            return GeneralFiefDisplayEnricher.enrich(
                stored,
                jsonArray(extra["ownedFiefLocationsJson"])
            )
        }
        val records = State8004GeneralEvidenceParser.recoverBestAvailableRecords(
            extra["state8004TailHex"],
            extra["state8004PayloadHex"]
        )
        if (records.isEmpty()) return GeneralFiefDisplayEnricher.enrich(
            stored,
            jsonArray(extra["ownedFiefLocationsJson"])
        )
        val recovered = JSONArray().apply { records.forEach { put(JSONObject(it)) } }
        accounts.updateLoginState(
            account.id,
            account.loginState,
            mapOf(
                "generalsJson" to recovered.toString(),
                "state8004GeneralRecordCount" to records.size.toString(),
                "generalsParserVersion" to State8004GeneralEvidenceParser.PARSER_VERSION
            )
        )
        return GeneralFiefDisplayEnricher.enrich(
            recovered,
            jsonArray(extra["ownedFiefLocationsJson"])
        )
    }

    private fun accountHabits(accountId: Long): JSONObject =
        LocalSettingsConfigMapper.accountHabits { featureId ->
            configs.loadFeatureConfig(accountId, featureId)?.optJSONObject("values")
        }

    private fun taskOverview(accountId: Long): JSONObject {
        val account = accounts.getPublic(accountId)
        val nowMillis = System.currentTimeMillis()
        val savedTasksStarted = account?.session?.channelExtra
            ?.get("savedTasksStarted")
            .equals("true", ignoreCase = true)
        val schedulerActive = LocalTaskPresentation.schedulerActive(
            accountEnabled = account?.enabled == true,
            savedTasksStarted = savedTasksStarted,
            executionOwnerActive = AssistantForegroundService.isExecutionOwnerActive(),
        )
        val statuses = SchedulerTaskOrdering.orderValues(
            currentRuntimeStatuses(accountId),
            behaviorContract.scheduler
        ) { it.type }
        val latestByKey = LocalTaskPresentation.latestByKey(statuses)
        val compactDailyStatus = jsonObject(
            account?.session?.channelExtra?.get("residentDailyTaskStatusJson")
        ).optJSONObject("daily")
        val sharedDailyState = jsonObject(
            account?.session?.channelExtra?.get("residentAutomationStateJson")
        ).optJSONObject("daily")
        val stack = JSONArray()
        val resident = JSONArray()
        val daily = JSONArray()
        statuses.mapNotNull { status ->
            val spec = LocalTaskPresentation.spec(status.type)
            val completed = spec.completionKey?.let { dailyStats.isCompleted(accountId, it) } == true
            (status to spec).takeIf {
                LocalTaskPresentation.isTaskStackVisible(
                    status,
                    completed,
                    schedulerActive = schedulerActive,
                    nowMillis = nowMillis
                )
            }
        }.forEachIndexed { index, (status, spec) ->
            val state = LocalTaskPresentation.schedulerState(
                status,
                completed = false,
                nowMillis = nowMillis
            )
            stack.put(JSONObject()
                .put("position", index + 1)
                .put("taskId", "android-$accountId-${spec.key}")
                .put("taskType", status.type.name)
                .put("key", spec.key)
                .put("name", spec.name)
                .put("category", spec.category)
                .put("status", LocalTaskPresentation.taskStackStatus(status))
                .put("state", state)
                .put("message", UserFacingTextLocalizer.localize(status.message))
                .put("cooldownUntil", status.nextRunAtMillis ?: JSONObject.NULL)
                .put("current", status.state == TaskRuntimeState.RUNNING)
                .put("createdAt", status.updatedAtMillis)
                .put("updatedAt", status.updatedAtMillis))
        }
        LocalTaskPresentation.residentSpecs
            .sortedByDescending { behaviorContract.scheduler.residentPriority[it.key] ?: 0 }
            .forEach { spec ->
                val status = latestByKey[spec.key]
                val state = LocalTaskPresentation.schedulerState(
                    status,
                    schedulerActive = schedulerActive,
                    nowMillis = nowMillis,
                )
                val active = LocalTaskPresentation.isActive(status, schedulerActive)
                resident.put(JSONObject()
                    .put("key", spec.key)
                    .put("name", spec.name)
                    .put("running", active)
                    .put("status", if (active) "running" else if (status == null) "idle" else "stopped")
                    .put("schedulerState", state)
                    .put("schedulerMessage", UserFacingTextLocalizer.localize(status?.message.orEmpty()))
                    .put("schedulerPriority", behaviorContract.scheduler.residentPriority[spec.key] ?: 0)
                    .put("schedulerRunnable", schedulerActive && status?.state == TaskRuntimeState.RUNNING)
                    .put("schedulerNextCheckAt", status?.nextRunAtMillis ?: JSONObject.NULL)
                    .put("taskId", status?.let { "android-$accountId-${spec.key}" } ?: JSONObject.NULL)
                    .put("updatedAt", status?.updatedAtMillis ?: JSONObject.NULL))
            }
        LocalTaskPresentation.dailySpecs.forEach { spec ->
            val status = latestByKey[spec.key]
            val completionKey = requireNotNull(spec.completionKey)
            val completed = dailyStats.isCompleted(accountId, completionKey)
            val compactState = compactDailyStatus?.optJSONObject(spec.key)
            val sharedState = sharedDailyState?.optJSONObject(spec.key)
            val sharedSkipped = (compactState ?: sharedState)
                ?.optBoolean("skipped", false) == true &&
                (compactState ?: sharedState)?.optString("lastState") == "completed"
            val skipped = status?.skipped == true || sharedSkipped
            val sharedStatusText = (compactState ?: sharedState)?.optString("statusText")
                ?.takeIf(String::isNotBlank)
            val sharedSkipReason = (compactState ?: sharedState)?.optString("skipReason")
                ?.takeIf(String::isNotBlank)
            val sharedMessage = (compactState ?: sharedState)?.optString("lastMessage")
                ?.takeIf(String::isNotBlank)
            val sharedNextRunAt = (compactState ?: sharedState)?.optLong("nextWakeAtMillis")
                ?.takeIf { value ->
                    (compactState ?: sharedState)?.has("nextWakeAtMillis") == true &&
                        (compactState ?: sharedState)?.isNull("nextWakeAtMillis") != true &&
                        value > 0L
                }
            val terminal = completed || skipped
            daily.put(
                JSONObject()
                    .put("key", spec.key)
                    .put("name", spec.name)
                    .put("completed", completed || skipped)
                    .put(
                        "statusText",
                        status?.statusText?.takeIf(String::isNotBlank)
                            ?: sharedStatusText
                            ?: if (completed) "已做" else "未做"
                    )
                    .put("skipped", skipped)
                    .put(
                        "skipReason",
                        status?.skipReason ?: sharedSkipReason ?: JSONObject.NULL
                    )
                    .put(
                        "state",
                        LocalTaskPresentation.schedulerState(
                            status,
                            terminal,
                            schedulerActive = schedulerActive,
                            nowMillis = nowMillis,
                        ),
                    )
                    .put("message", UserFacingTextLocalizer.localize(
                        status?.statusText?.takeIf(String::isNotBlank)
                            ?: sharedStatusText
                            ?: sharedMessage
                            ?: status?.message.orEmpty()
                    ))
                    .put(
                        "nextRunAt",
                        status?.nextRunAtMillis ?: sharedNextRunAt ?: JSONObject.NULL
                    )
                    .put("updatedAt", status?.updatedAtMillis ?: JSONObject.NULL)
            )
        }
        return JSONObject()
            .put("date", SimpleDateFormat("yyyyMMdd", Locale.ROOT).format(Date()))
            .put("updatedAt", nowMillis)
            .put(
                "savedTasksStarted",
                schedulerActive
            )
            .put("taskStack", stack)
            .put("resident", resident)
            .put("daily", daily)
            .put("notices", runtimeNotices(accountId, statuses))
    }

    private fun automationTasks(accountId: Long): JSONArray {
        val taskLogs = logs.recent(400, LogAudience.USER)
            .filter { it.accountId == accountId }
            .take(40)
            .asReversed()
            .map {
                // No localization pass here: a USER line was already written as a
                // sentence by whoever knew what happened. Rewriting it by substring
                // can only damage it -- that rule set turns "examine mineral vein"
                // into "exa打矿 打矿ral vein".
                "[${SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date(it.timeMillis))}] " +
                    it.message
            }
        val account = accounts.getPublic(accountId)
        val schedulerActive = LocalTaskPresentation.schedulerActive(
            accountEnabled = account?.enabled == true,
            savedTasksStarted = account?.session?.channelExtra
                ?.get("savedTasksStarted")
                .equals("true", ignoreCase = true),
            executionOwnerActive = AssistantForegroundService.isExecutionOwnerActive(),
        )
        val statuses = currentRuntimeStatuses(accountId)
            .filterNot { LocalTaskPresentation.isRetiredRuntimeType(it.type) }
            .sortedByDescending { it.updatedAtMillis }
        return JSONArray().apply {
            statuses.forEach { status ->
                val spec = LocalTaskPresentation.spec(status.type)
                val publicStatus = when {
                    !schedulerActive -> "stopped"
                    status.state in setOf(
                        TaskRuntimeState.STOPPED,
                        TaskRuntimeState.SERVICE_STOPPED,
                    ) -> "stopped"
                    status.state in setOf(
                        TaskRuntimeState.ERROR,
                        TaskRuntimeState.NEED_RELOGIN,
                    ) -> "error"
                    else -> "running"
                }
                put(
                    JSONObject()
                        .put("taskId", "android-$accountId-${spec.key}")
                        .put("sessionId", accountId.toString())
                        .put("type", spec.key)
                        .put("name", spec.name)
                        .put("status", publicStatus)
                        .put(
                            "schedulerState",
                            LocalTaskPresentation.schedulerState(
                                status,
                                schedulerActive = schedulerActive,
                            ),
                        )
                        .put("message", UserFacingTextLocalizer.localize(status.message))
                        .put("createdAt", status.updatedAtMillis)
                        .put("updatedAt", status.updatedAtMillis)
                        .put("nextRunAt", status.nextRunAtMillis ?: JSONObject.NULL)
                        .put("logs", JSONArray(taskLogs.takeLast(20)))
                )
            }
        }
    }

    private fun assistantOperations(accountId: Long): JSONArray {
        val account = accounts.getPublic(accountId) ?: return JSONArray()
        val generalArray = jsonArray(account.session?.channelExtra?.get("generalsJson"))
        val generals = (0 until generalArray.length()).mapNotNull { index ->
            generalArray.optJSONObject(index)?.let { general ->
                val id = general.optLong("id", -1L)
                if (id <= 0L) null else id to general
            }
        }.toMap()
        return JSONArray().apply {
            expeditionTransactions.list(accountId)
                .sortedBy { it.createdAtMillis }
                .forEach { record ->
                    val generalStates = JSONArray().apply {
                        record.generalIds.forEach { id ->
                            val general = generals[id]
                            put(
                                JSONObject()
                                    .put("id", id)
                                    .put("name", general?.optString("name")?.ifBlank { id.toString() } ?: id.toString())
                                    .put("status", generalStatusText(general))
                            )
                        }
                    }
                    val state = when (record.state) {
                        ExpeditionTransactionState.SENDING, ExpeditionTransactionState.UNCERTAIN -> "准备"
                        ExpeditionTransactionState.ACCEPTED -> acceptedOperationState(generalStates)
                    }
                    put(
                        JSONObject()
                            .put("id", record.id)
                            .put("state", state)
                            .put("targetText", record.targetKey)
                            .put("text", when (record.state) {
                                ExpeditionTransactionState.SENDING -> "${record.action}请求正在发送"
                                ExpeditionTransactionState.UNCERTAIN -> "${record.action}结果待服务器状态确认"
                                ExpeditionTransactionState.ACCEPTED -> "${record.action}已由服务器受理"
                            })
                            .put("taskName", record.action)
                            .put("startedAt", record.createdAtMillis)
                            .put("generalStates", generalStates)
                    )
                }
        }
    }

    private fun currentRuntimeStatuses(
        accountId: Long,
    ): List<com.example.dwpmclone.domain.scheduler.TaskRuntimeStatus> =
        LocalTaskPresentation.forExecutionGeneration(
            runtimeStatuses.list(accountId),
            AssistantForegroundService.currentExecutionGeneration(),
        )

    private fun runtimeNotices(
        accountId: Long,
        statuses: List<com.example.dwpmclone.domain.scheduler.TaskRuntimeStatus>
    ): JSONArray = JSONArray().apply {
        // Read the durable condition, not a rolling log window: a resource
        // wait must survive restart and remain dismissible across retries.
        val resources = ResourceWaitNoticeProjection.from(
            runCatching {
                sharedPythonCore.residentResourceNotices(accountId.toString())
            }.getOrDefault(JSONObject()),
        ) { key -> dismissedNotices.contains(accountId, key) }
        resources.visible.forEach(::put)
        statuses.filterNot {
            LocalTaskPresentation.isRetiredRuntimeType(it.type) ||
                LocalTaskPresentation.spec(it.type).key in resources.features
        }.filter {
            it.state in setOf(
                TaskRuntimeState.STOPPED,
                TaskRuntimeState.ERROR,
                TaskRuntimeState.NEED_RELOGIN
            ) && !it.message.startsWith("用户已停止")
        }.sortedByDescending { it.updatedAtMillis }.forEach { status ->
            val spec = LocalTaskPresentation.spec(status.type)
            val key = "runtime:${spec.key}:${status.updatedAtMillis}"
            if (!dismissedNotices.contains(accountId, key)) {
                put(
                    JSONObject()
                        .put("key", key)
                        .put("title", "${spec.name}${if (status.state == TaskRuntimeState.STOPPED) "已停止" else "异常"}")
                        .put("summary", UserFacingTextLocalizer.localize(status.message))
                        .put("message", UserFacingTextLocalizer.localize(status.message))
                        .put("severity", if (status.state == TaskRuntimeState.STOPPED) "warning" else "error")
                        .put("advice", "请根据原因检查账号状态、将领、配兵和任务配置，修正后重新启动。")
                        .put("createdAt", status.updatedAtMillis)
                        .put("updatedAt", status.updatedAtMillis)
                )
            }
        }
        // Advice is not a failure: the task keeps running (SLEEPING between
        // scan batches), but a whole scan round without a single match means
        // the operator's own filter is what produces nothing.  Derive it from
        // the persisted status, not from the log - tick lines push a USER row
        // out of the log window within minutes, while the status row holds
        // the message until the episode ends.  The key hashes the message,
        // which the core keeps stable for an episode, so dismissing it sticks
        // and a matched target (message changes) clears it by itself.
        statuses.filterNot {
            LocalTaskPresentation.isRetiredRuntimeType(it.type) ||
                LocalTaskPresentation.spec(it.type).key in resources.features
        }.filter {
            it.message.contains("【建议】")
        }.forEach { status ->
            val spec = LocalTaskPresentation.spec(status.type)
            val key = "advice:${spec.key}:${status.message.hashCode()}"
            if (!dismissedNotices.contains(accountId, key)) {
                val message = UserFacingTextLocalizer.localize(status.message)
                put(
                    JSONObject()
                        .put("key", key)
                        .put("title", "${spec.name}建议")
                        .put("summary", message.take(160))
                        .put("message", message.take(800))
                        .put("severity", "info")
                        .put("advice", "按建议调整筛选条件后提示会自动消失；忽略后同一建议不再弹出。")
                        .put("createdAt", status.updatedAtMillis)
                        .put("updatedAt", status.updatedAtMillis)
                )
            }
        }
        accountConnectionNotice(accountId)?.let(::put)
        logDerivedNotices(accountId, statuses, resources.features).forEach(::put)
    }

    private fun accountConnectionNotice(accountId: Long): JSONObject? {
        val account = accounts.getPublic(accountId) ?: return null
        if (!account.enabled || account.loginState == AccountLoginState.ONLINE) return null
        val extra = account.session?.channelExtra.orEmpty()
        val retry = reconnects.state(accountId)
        val reason = extra["lastReloginError"]
            ?: extra["lastOfflineReason"]
            ?: extra["lastNetworkPauseReason"]
            ?: retry.reason.takeIf(String::isNotBlank)
            ?: "账号当前不在线，后台将按退避时间自动重连"
        val occurrence = listOf(
            extra["lastOfflineAt"]?.toLongOrNull(),
            extra["lastNetworkPauseAt"]?.toLongOrNull(),
            extra["nextReloginAt"]?.toLongOrNull(),
            retry.nextAttemptAtMillis.takeIf { it > 0L }
        ).filterNotNull().maxOrNull() ?: kotlin.math.abs(reason.hashCode().toLong())
        val key = "account:connection:$occurrence"
        if (dismissedNotices.contains(accountId, key)) return null
        return JSONObject()
            .put("key", key)
            .put("title", "账号连接异常")
            .put("summary", reason)
            .put("message", reason)
            .put("severity", "critical")
            .put("advice", "检查手机当前网络；网络恢复后后台会先重新登录并同步状态。")
            .put("createdAt", occurrence)
            .put("updatedAt", occurrence)
    }

    private fun logDerivedNotices(
        accountId: Long,
        statuses: List<com.example.dwpmclone.domain.scheduler.TaskRuntimeStatus>,
        authoritativeFeatures: Set<String> = emptySet(),
    ): List<JSONObject> {
        val active = linkedMapOf<String, Pair<LocalTaskPresentationSpec, TaskLogEntry>>()
        logs.recent(200)
            .filter { it.accountId == accountId }
            .asReversed()
            .forEach { entry ->
                val spec = noticeSpec(entry.message) ?: return@forEach
                when {
                    entry.message.containsAny("失败", "异常", "中止", "暂停", "未完成") ->
                        active[spec.key] = spec to entry
                    // "已恢复运行" is the shared core's own edge line for leaving a
                    // narrated pause ("打矿已暂停：…") and "隔离已解除" for an old
                    // ledger it settled; both end the condition the notice was
                    // raised for, even though no 完成/成功 line follows.
                    entry.message.containsAny("完成", "成功", "重复", "已领取", "已做", "已恢复", "已解除") ->
                        active.remove(spec.key)
                }
            }
        val terminalKeys = statuses
            .filterNot { LocalTaskPresentation.isRetiredRuntimeType(it.type) }
            .filter { it.state in setOf(TaskRuntimeState.STOPPED, TaskRuntimeState.ERROR, TaskRuntimeState.NEED_RELOGIN) }
            .map { LocalTaskPresentation.spec(it.type).key }
            .toSet()
        return active.values
            .filterNot { (spec, _) ->
                spec.key in terminalKeys || spec.key in authoritativeFeatures
            }
            .sortedByDescending { (_, entry) -> entry.timeMillis }
            .mapNotNull { (spec, entry) ->
                val key = "log:${spec.key}:${entry.timeMillis}"
                if (dismissedNotices.contains(accountId, key)) return@mapNotNull null
                val message = UserFacingTextLocalizer.localize(entry.message)
                JSONObject()
                    .put("key", key)
                    .put("title", "${spec.name}未完成")
                    .put("summary", message.take(160))
                    .put("message", message.take(800))
                    .put("severity", "warning")
                    .put("advice", "确认账号在线并检查该功能配置；下一轮执行成功后提示会自动消失。")
                    .put("createdAt", entry.timeMillis)
                    .put("updatedAt", entry.timeMillis)
            }
    }

    private fun noticeSpec(message: String): LocalTaskPresentationSpec? {
        val normalized = message.uppercase(Locale.ROOT)
        val all = LocalTaskPresentation.dailySpecs +
            LocalTaskPresentation.residentSpecs +
            listOf(
                LocalTaskPresentation.spec(com.example.dwpmclone.domain.protocol.TaskType.FORMATION),
                LocalTaskPresentation.spec(com.example.dwpmclone.domain.protocol.TaskType.GENERAL),
                LocalTaskPresentation.spec(com.example.dwpmclone.domain.protocol.TaskType.INTERNAL),
                LocalTaskPresentation.spec(com.example.dwpmclone.domain.protocol.TaskType.INVENTORY)
            )
        return all.firstOrNull { spec ->
            message.contains(spec.name) || normalized.contains(
                when (spec.key) {
                    "autoSignIn" -> "SIGN_IN"
                    "arenaCoins" -> "ARENA_COINS"
                    "autoDonate" -> "DAILY_DONATE"
                    "salary" -> "DAILY_SALARY"
                    "nationalCollect" -> "NATIONAL_COLLECT"
                    "cityLordCollect" -> "CITY_LORD_COLLECT"
                    "generalVisit" -> "GENERAL_VISIT"
                    "brushYellow" -> "SHUA_HUANG"
                    "mine" -> "MINING"
                    "lossless" -> "LOSSLESS"
                    "raid" -> "AUTO_LOOT"
                    "dungeon" -> "DUNGEON"
                    "ministry" -> "SIX_MINISTRIES"
                    "formations" -> "FORMATION"
                    "general" -> "GENERAL"
                    "domestic" -> "INTERNAL"
                    "inventory" -> "INVENTORY"
                    else -> spec.key.uppercase(Locale.ROOT)
                }
            )
        }
    }

    private fun String.containsAny(vararg markers: String): Boolean = markers.any(::contains)

    private fun generalStatusText(general: JSONObject?): String {
        if (general == null) return "未知"
        general.optString("statusText").takeIf(String::isNotBlank)?.let { return it }
        return when (general.optInt("status", -1)) {
            0 -> "空闲"
            1 -> "出征"
            2 -> "驻守"
            3 -> "被俘"
            4 -> "阵亡"
            5 -> "修炼"
            6 -> "战斗"
            8 -> "返回"
            else -> "未知"
        }
    }

    private fun acceptedOperationState(generalStates: JSONArray): String {
        val states = (0 until generalStates.length()).mapNotNull {
            generalStates.optJSONObject(it)?.optString("status")
        }
        return when {
            states.any { it.contains("战") } -> "战斗"
            states.any { it.contains("驻") || it.contains("防") } -> "驻守"
            states.any { it.contains("返") } -> "返回"
            else -> "出征"
        }
    }

    private fun dailyStatsJson(accountId: Long): JSONObject {
        val fallback = dailyStats.stats(accountId)
        val extra = accounts.getPublic(accountId)?.session?.channelExtra.orEmpty()
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

    private fun setSavedTasksStarted(
        accountId: Long,
        started: Boolean,
        residentKeys: Set<String> = emptySet()
    ) {
        val account = accounts.get(accountId) ?: return
        val session = account.session ?: return
        val updates = if (started) {
            mapOf(
                "savedTasksStarted" to "true",
                "savedTasksStartedAt" to System.currentTimeMillis().toString(),
                "activeResidentTaskKeys" to residentKeys.sorted().joinToString(",")
            )
        } else {
            ResidentTaskActivationPolicy.stoppedUpdates() +
                ("savedTasksStartedAt" to "")
        }
        accounts.upsert(account.copy(session = session.copy(channelExtra = session.channelExtra + updates)))
    }

    private fun setResidentTaskActive(accountId: Long, key: String, active: Boolean) {
        val account = accounts.get(accountId) ?: return
        val session = account.session ?: return
        val keys = ResidentTaskActivationPolicy.afterToggle(
            channelExtra = session.channelExtra,
            allResidentKeys = behaviorContract.scheduler.residentPriority.keys,
            key = key,
            active = active
        )
        accounts.upsert(account.copy(session = session.copy(
            channelExtra = session.channelExtra + mapOf(
                ResidentTaskActivationPolicy.ACTIVE_KEYS_FIELD to
                    ResidentTaskActivationPolicy.encode(keys)
            )
        )))
    }

    private fun residentTaskActivation(
        route: String,
        mapping: LocalSettingsMapping,
        body: JSONObject
    ): Pair<String, Boolean>? = when (route) {
        "/api/raid/execute" -> "raid" to !mapping.disabled
        "/api/mine/save" -> "mine" to !mapping.disabled
        "/api/lossless/execute" -> "lossless" to !mapping.disabled
        "/api/dungeon/execute" -> "dungeon" to !mapping.disabled
        "/api/liubu/save" -> "ministry" to (
            mapping.configs[LocalSettingsConfigMapper.MINISTRIES]
                ?.optBoolean("supportedEnabled", false) == true
            )
        "/api/settings/save" -> when (body.optString("scope")) {
            "brush" -> "brushYellow" to !mapping.disabled
            "common.frequent" -> body.optJSONObject("patch")
                ?.optJSONObject("captives")
                ?.let { captives ->
                    "captives" to (
                        captives.optBoolean("captiveRelease", false) ||
                            captives.optBoolean("captivePersuade", false)
                        )
                }
            "common.alarm" -> {
                val alarm = mapping.configs[LocalSettingsConfigMapper.ALARM]
                "alarm" to (
                    alarm?.optBoolean("incomingEnabled", false) == true ||
                        alarm?.optBoolean("militaryEnabled", false) == true
                    )
            }
            else -> null
        }
        else -> null
    }

    private fun requireAccount(body: JSONObject?): GameAccount {
        val id = body?.optString("sessionId")?.toLongOrNull()
            ?: throw IllegalArgumentException("缺少账号 sessionId")
        return accounts.get(id) ?: throw IllegalArgumentException("账号不存在")
    }

    private fun dispatchSharedLocal(
        request: AssistantApiRequest,
        route: String,
        body: JSONObject
    ): AssistantApiResponse {
        val dispatched = sharedPythonCore.dispatch(
            request.method,
            route,
            body,
            JSONObject()
                .put("requestId", request.id)
                .put("source", "android-webview")
                .put("platform", "android")
        )
        return AssistantApiResponse(
            request.id,
            dispatched.optInt("status", 500),
            dispatched.optJSONObject("body") ?: JSONObject()
        )
    }

    /** Raw local facts only; filtering, localization and success recognition belong to Python. */
    private fun rawLogJson(entry: TaskLogEntry): JSONObject {
        return JSONObject()
            .put("id", entry.id)
            .put("time", entry.timeMillis)
            .put("timeText", formatTime(entry.timeMillis))
            .put("tag", entry.tag)
            .put("message", entry.message)
            .put("accountId", entry.accountId ?: JSONObject.NULL)
            .put("successCategory", entry.successCategory ?: JSONObject.NULL)
            .put("successMessage", entry.successMessage ?: JSONObject.NULL)
    }

    /** Storage facts only; TTL, filtering, labels and public fields belong to Python. */
    private fun rawLocalMapJson(
        record: com.example.dwpmclone.domain.localmap.LocalMapTargetRecord
    ): JSONObject = JSONObject()
        .put("targetId", record.targetId)
        .put("x", record.coordinate.x)
        .put("y", record.coordinate.y)
        .put("type", record.type)
        .put("level", record.level ?: JSONObject.NULL)
        .put("filterFields", JSONObject(record.filterFields))
        .put("firstDiscoveredAtMillis", record.firstDiscoveredAtMillis)
        .put("lastValidatedAtMillis", record.lastValidatedAtMillis)
        .put("invalidatedAtMillis", record.invalidatedAtMillis ?: JSONObject.NULL)
        .put("invalidReason", record.invalidReason ?: JSONObject.NULL)
        .put("active", record.active)

    private fun formatTime(timeMillis: Long): String =
        SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA).format(Date(timeMillis))

    private fun query(path: String): Map<String, String> = path.substringAfter('?', "")
        .split('&')
        .mapNotNull { pair ->
            if (pair.isBlank()) return@mapNotNull null
            val key = pair.substringBefore('=')
            val value = pair.substringAfter('=', "")
            URLDecoder.decode(key, "UTF-8") to URLDecoder.decode(value, "UTF-8")
        }
        .toMap()

    private fun jsonObject(raw: String?): JSONObject = raw?.let { runCatching { JSONObject(it) }.getOrNull() } ?: JSONObject()
    private fun jsonArray(raw: String?): JSONArray = raw?.let { runCatching { JSONArray(it) }.getOrNull() } ?: JSONArray()

    private fun ok(request: AssistantApiRequest, data: JSONObject = JSONObject()): AssistantApiResponse {
        data.put("ok", true)
        return AssistantApiResponse(request.id, 200, data)
    }

    private fun failure(request: AssistantApiRequest, status: Int, message: String): AssistantApiResponse =
        AssistantApiResponse(request.id, status, JSONObject().put("ok", false).put("error", message))
}

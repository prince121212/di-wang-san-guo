package com.example.dwpmclone.ui.web

import android.content.Context
import com.example.dwpmclone.data.account.AccountLoginState
import com.example.dwpmclone.data.account.LocalAccountLoginService
import com.example.dwpmclone.data.local.KeystoreCredentialVault
import com.example.dwpmclone.data.local.DismissedNoticeRepository
import com.example.dwpmclone.data.local.ExpeditionTransactionRepository
import com.example.dwpmclone.data.local.AssistantBehaviorContractAssetLoader
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.LocalConfigRepository
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.LocalMapRepository
import com.example.dwpmclone.data.local.RequestHealthRepository
import com.example.dwpmclone.data.local.SessionReconnectRepository
import com.example.dwpmclone.data.local.TaskLogEntry
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.local.TaskSuccessRecordPolicy
import com.example.dwpmclone.data.local.TaskRuntimeStatusRepository
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.localmap.LocalMapKind
import com.example.dwpmclone.domain.protocol.AccountLifecyclePresentationPolicy
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import com.example.dwpmclone.domain.protocol.ExpeditionTransactionState
import com.example.dwpmclone.data.protocol.RealGameProtocolClient
import com.example.dwpmclone.domain.protocol.State8004GeneralEvidenceParser
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.protocol.UserFacingTextLocalizer
import com.example.dwpmclone.domain.scheduler.HostingStartPolicy
import com.example.dwpmclone.domain.scheduler.ResidentTaskActivationPolicy
import com.example.dwpmclone.domain.scheduler.SavedConfigTaskPlanFactory
import com.example.dwpmclone.domain.scheduler.SchedulerTaskOrdering
import com.example.dwpmclone.domain.scheduler.TaskRuntimeState
import com.example.dwpmclone.service.AssistantForegroundService
import java.net.URLDecoder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

/** Small allow-listed adapter from the shared Web UI contract to on-device repositories. */
class LocalAssistantApiController(
    context: Context,
    private val onHostingStarted: () -> Unit = {}
) {
    private val appContext = context.applicationContext
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
    private val behaviorContract = AssistantBehaviorContractAssetLoader.load(appContext)
    private val loginService = LocalAccountLoginService(
        accounts = accounts,
        credentials = credentialVault,
        logs = logs
    )
    private val localOperations = LocalProtocolOperationService(
        context = appContext,
        accounts = accounts,
        logs = logs,
        requestHealth = requestHealth,
        dailyStats = dailyStats,
        localMaps = localMaps,
        taskOverviewProvider = { accountId -> taskOverview(accountId) }
    )

    fun handle(request: AssistantApiRequest): AssistantApiResponse = runCatching {
        localOperations.tryHandle(request)?.let { return@runCatching it }
        val route = request.path.substringBefore('?')
        when (request.method to route) {
            "GET" to "/api/health" -> ok(request, JSONObject().put("apiVersion", "v1").put("core", "android-local"))
            "GET" to "/api/accounts" -> ok(request, JSONObject().put("accounts", accountArray()))
            "GET" to "/api/areas" -> ok(request, JSONObject().put("areas", JSONArray()).put("updatedAt", System.currentTimeMillis()))
            "GET" to "/api/accounts/settings" -> accountSettings(request)
            "GET" to "/api/logs/system" -> systemLogs(request)
            "GET" to "/api/logs/account" -> accountLogs(request)
            "GET" to "/api/automation/status" -> automationStatus(request)
            "GET" to "/api/state/refresh" -> stateRefresh(request)
            "GET" to "/api/success-records" -> successRecords(request)
            "GET" to "/api/maps/bandits" -> localMap(request, LocalMapKind.BANDIT)
            "GET" to "/api/maps/mines" -> localMap(request, LocalMapKind.MINE)
            "POST" to "/api/logs/account" -> appendAccountLog(request)
            "POST" to "/api/logs/system/clear" -> clearLogs(request)
            "POST" to "/api/notices/dismiss" -> dismissNotice(request)
            "POST" to "/api/accounts/add" -> addAccount(request)
            "POST" to "/api/accounts/start" -> startAccount(request)
            "POST" to "/api/accounts/stop" -> stopAccount(request)
            "POST" to "/api/accounts/delete" -> deleteAccount(request)
            "POST" to "/api/automation/start-saved" -> startSavedTasks(request)
            "POST" to "/api/automation/stop" -> stopAccount(request)
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

    private fun addAccount(request: AssistantApiRequest): AssistantApiResponse {
        val body = request.body ?: return failure(request, 400, "缺少账号信息")
        val username = body.optString("username").trim()
        val password = body.optString("password")
        val serverQuery = body.optString("serverQuery").trim()
        val platform = body.optString("platform")
        if (platform.contains("当乐", ignoreCase = true)) {
            return failure(request, 400, "手机 V1 当前只开放已验证的热血三国联盟登录链路")
        }
        val account = loginService.loginAndPersist(username, password, serverQuery)
        return ok(request, JSONObject().put("account", accountJson(account)))
    }

    private fun startAccount(request: AssistantApiRequest): AssistantApiResponse {
        val account = requireAccount(request.body)
        if (!credentialVault.hasPassword(account.id)) {
            return failure(request, 409, "该账号没有可用于自动重登的 Keystore 凭据，请删除后重新添加")
        }
        accounts.setEnabled(account.id, true, AccountLoginState.CHECKING)
        if (behaviorContract.accountLifecycle.startRunsFreshLogin) {
            // A fresh login replaces network credentials but must retain the computer-helper
            // equivalent of currentDungeonStage/pending settlement metadata.
            runCatching { loginService.relogin(account, preserveTaskRuntime = true) }
                .onFailure { error ->
                    accounts.setEnabled(account.id, false, AccountLoginState.OFFLINE)
                    logs.append(
                        "账号 ${account.id} 启动真实登录失败：${error.message}",
                        "account",
                        account.id
                    )
                }
                .getOrElse { error ->
                    return failure(request, 409, "真实登录失败：${error.message ?: error::class.java.simpleName}")
                }
        } else {
            accounts.setEnabled(account.id, true, AccountLoginState.ONLINE)
        }
        val decision = HostingStartPolicy.evaluate(accounts.listAccounts())
        if (!decision.allowed) {
            accounts.setEnabled(account.id, false, AccountLoginState.STOPPED)
            return failure(request, 409, decision.message)
        }
        AssistantForegroundService.start(appContext)
        runCatching { onHostingStarted() }
        logs.append("账号 ${account.id} 已从手机本地界面启动", "account", account.id)
        return ok(request, JSONObject().put("account", accountJson(accounts.get(account.id)!!)))
    }

    private fun stopAccount(request: AssistantApiRequest): AssistantApiResponse {
        val account = requireAccount(request.body)
        // “停止” and “仅退出当前页面” are different operations. Persist the explicit stop so
        // a later account login cannot silently restore resident brush/dungeon tasks.
        setSavedTasksStarted(account.id, false)
        accounts.setEnabled(account.id, false, AccountLoginState.STOPPED)
        runtimeStatuses.markAccountStopped(
            account.id,
            System.currentTimeMillis(),
            "用户已停止该账号的手机本地托管"
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
        return ok(request, JSONObject().put("accounts", accountArray()))
    }

    private fun startSavedTasks(request: AssistantApiRequest): AssistantApiResponse {
        var account = requireAccount(request.body)
        val alreadyStarted = account.session?.channelExtra?.get("savedTasksStarted")
            .equals("true", ignoreCase = true) &&
            account.enabled && AssistantForegroundService.isExecutionOwnerActive()
        if (alreadyStarted) {
            return ok(
                request,
                JSONObject()
                    .put("alreadyStarted", true)
                    .put("result", JSONObject().put("resumed", JSONObject()).put("errors", JSONObject()))
                    .put("taskOverview", taskOverview(account.id))
            )
        }
        if (!account.enabled || account.loginState != AccountLoginState.ONLINE) {
            val started = startAccount(request)
            if (started.status !in 200..299) return started
            account = accounts.get(account.id) ?: return failure(request, 404, "账号不存在")
        }
        val plan = SavedConfigTaskPlanFactory.planForRealAccount(
            account,
            configs.exportAll(),
            behaviorContract
        )
        val residentSpecs = plan?.tasks
            ?.map { LocalTaskPresentation.spec(it.type) }
            ?.filter { it.category == "resident" }
            ?.distinctBy { it.key }
            .orEmpty()
        setSavedTasksStarted(account.id, true, residentSpecs.map { it.key }.toSet())
        AssistantForegroundService.start(appContext)
        runCatching { onHostingStarted() }
        val resumed = JSONObject().apply {
            residentSpecs.forEach { put(it.key, true) }
        }
        logs.append("用户已开始执行保存的常驻任务", "account", account.id)
        return ok(
            request,
            JSONObject()
                .put("alreadyStarted", false)
                .put("result", JSONObject().put("resumed", resumed).put("errors", JSONObject()))
                .put("taskOverview", taskOverview(account.id))
        )
    }

    private fun saveMappedSettings(request: AssistantApiRequest, route: String): AssistantApiResponse {
        val account = requireAccount(request.body)
        val body = request.body ?: throw IllegalArgumentException("缺少设置内容")
        val mapping = LocalSettingsConfigMapper.map(route, body)
        mapping.configs.forEach { (featureId, values) ->
            configs.saveFeatureConfig(account.id, featureId, JSONObject().put("values", values))
        }
        if (account.enabled) residentTaskActivation(route, mapping, body)?.let { (key, active) ->
            setResidentTaskActive(account.id, key, active)
        }
        val featureNames = mapping.configs.keys.joinToString(",")
        logs.append("手机本地设置已保存：features=$featureNames", "config", account.id)
        if (account.enabled) AssistantForegroundService.refresh(appContext)

        val data = JSONObject()
            .put("saved", true)
            .put("disabled", mapping.disabled)
            .put("accountHabits", accountHabits(account.id))
            .put("taskOverview", taskOverview(account.id))
            .put("savedFile", "手机本地存储/account-config.json")
            .put("savedFiles", JSONObject()
                .put("militaryFile", "手机本地存储/account-config.json")
                .put("ministryFile", "手机本地存储/account-config.json"))
            .put("stoppedTaskIds", JSONArray())
            .put("waitingForMilitaryStart", !mapping.disabled && !account.enabled)

        val taskStarted = !mapping.disabled && account.enabled
        data.put(
            "execution",
            JSONObject()
                .put("accepted", !mapping.disabled)
                .put("started", taskStarted)
                .put("waitingForAccountStart", !mapping.disabled && !account.enabled)
                .put("owner", "android-local-scheduler")
        )

        when (route) {
            "/api/formations/save" -> {
                val values = mapping.configs.getValue(LocalSettingsConfigMapper.FORMATION)
                val rows = values.optJSONArray("rows") ?: JSONArray()
                data.put("formations", rows)
                    .put("normalizedFormations", rows)
                    .put("formationOptions", JSONObject()
                        .put("clearOtherGenerals", values.optBoolean("clearOtherGenerals", false)))
                    .put("unresolvedGeneralIds", JSONArray())
                    .put("applyTask", JSONObject()
                        .put("started", taskStarted)
                        .apply {
                            if (taskStarted) {
                                put("message", "已交给手机本地调度器串行应用")
                            } else {
                                put("reason", if (mapping.disabled) "没有启用的配兵规则" else "账号启动后自动应用")
                            }
                        })
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
                val cropEnabled = values.optBoolean("cropEnabled", false)
                val crop = values.optString("crop", com.example.dwpmclone.domain.model.MinistryProtocolCrop.VERIFIED_NAME)
                val supported = values.optBoolean("supportedEnabled", false)
                data.put(
                    "reason",
                    when {
                        mapping.disabled -> "六部任务已关闭"
                        supported -> "六部设置已保存，由手机本地调度器执行金银花种植"
                        cropEnabled -> "${crop}协议尚未确认；配置已保存但不会发送"
                        else -> "种菜收菜未开启；偷菜和礼部动作协议尚未完整确认，当前不发送"
                    }
                )
                data.put("ministryTask", schedulerTaskState(
                    taskStarted && supported,
                    !supported,
                    if (mapping.disabled) "六部任务已关闭" else "当前没有可执行的已确认动作",
                    "账号启动后执行金银花种植"
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
        val message = request.body?.optString("message")?.trim().orEmpty()
        if (message.isBlank()) return failure(request, 400, "日志内容不能为空")
        val accountId = request.body?.optString("sessionId")?.toLongOrNull()
        logs.append(message.take(2_000), request.body?.optString("source").orEmpty().ifBlank { "frontend" }, accountId)
        return ok(request)
    }

    private fun clearLogs(request: AssistantApiRequest): AssistantApiResponse {
        logs.clear()
        return ok(request)
    }

    private fun systemLogs(request: AssistantApiRequest): AssistantApiResponse {
        val query = query(request.path)
        val limit = query["limit"]?.toIntOrNull()?.coerceIn(1, 1_500) ?: 200
        val afterId = query["afterId"]?.toLongOrNull() ?: 0L
        val entries = logs.recent(limit).asReversed().filter { it.id > afterId }
        val payload = JSONArray().apply {
            entries.forEach { entry -> put(logJson(entry, entry.id, system = true)) }
        }
        val latest = entries.lastOrNull()?.id ?: afterId
        return ok(request, JSONObject().put("entries", payload).put("cursorId", latest).put("latestId", latest))
    }

    private fun accountLogs(request: AssistantApiRequest): AssistantApiResponse {
        val query = query(request.path)
        val accountId = query["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val limit = query["limit"]?.toIntOrNull()?.coerceIn(1, 200) ?: 100
        val entries = logs.recent(200).filter { it.accountId == accountId }.take(limit).asReversed()
        return ok(request, JSONObject().put("entries", JSONArray().apply {
            entries.forEach { entry -> put(logJson(entry, entry.id, system = false)) }
        }))
    }

    private fun successRecords(request: AssistantApiRequest): AssistantApiResponse {
        val params = query(request.path)
        val accountId = params["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val limit = params["limit"]?.toIntOrNull()?.coerceIn(1, 50) ?: 50
        val category = params["category"].orEmpty().trim()
        val entries = logs.recent(1_500)
            .asSequence()
            .filter { it.accountId == accountId }
            .mapNotNull { entry -> TaskSuccessRecordPolicy.resolve(entry)?.let { entry to it } }
            .filter { (_, record) -> category.isBlank() || record.category == category }
            .take(limit)
            .toList()
        return ok(request, JSONObject()
            .put("accountKey", accountId.toString())
            .put("limit", limit)
            .put("category", category)
            .put("maxLines", 50)
            .put("entries", JSONArray().apply {
            entries.forEach { (entry, record) ->
                put(JSONObject()
                    .put("id", entry.id)
                    .put("time", entry.timeMillis)
                    .put("timeText", formatTime(entry.timeMillis))
                    .put("sessionId", accountId.toString())
                    .put("accountKey", accountId.toString())
                    .put("category", record.category)
                    .put("message", record.message)
                    .put("source", entry.tag))
            }
        }))
    }

    private fun automationStatus(request: AssistantApiRequest): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        return ok(
            request,
            JSONObject()
                .put("tasks", automationTasks(accountId))
                .put("assistantOperations", assistantOperations(accountId))
                .put("taskOverview", taskOverview(accountId))
        )
    }

    private fun dismissNotice(request: AssistantApiRequest): AssistantApiResponse {
        val account = requireAccount(request.body)
        val key = request.body?.optString("noticeKey")?.trim().orEmpty()
        if (key.isBlank()) return failure(request, 400, "缺少提示标识")
        dismissedNotices.dismiss(account.id, key)
        return ok(request, JSONObject().put("taskOverview", taskOverview(account.id)))
    }

    private fun stateRefresh(request: AssistantApiRequest): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val account = accounts.get(accountId) ?: return failure(request, 404, "账号不存在")
        val session = sessionJson(account)
        return ok(request, session)
    }

    private fun localMap(request: AssistantApiRequest, kind: LocalMapKind): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val account = accounts.get(accountId) ?: return failure(request, 404, "账号不存在")
        val serverId = account.serverId
            ?: account.session?.channelExtra?.get("serverKey")
            ?: account.serverName.takeIf { it.isNotBlank() }
            ?: return failure(request, 409, "当前账号没有可识别的区服")
        val records = localMaps.list(accountId, serverId, kind)
        val data = when (kind) {
            LocalMapKind.BANDIT -> LocalMapApiMapper.bandits(serverId, records, System.currentTimeMillis())
            LocalMapKind.MINE -> LocalMapApiMapper.mines(serverId, records, System.currentTimeMillis())
        }
        return ok(request, data)
    }

    private fun accountSettings(request: AssistantApiRequest): AssistantApiResponse {
        val accountId = query(request.path)["sessionId"]?.toLongOrNull()
            ?: return failure(request, 400, "缺少账号")
        val account = accounts.get(accountId) ?: return failure(request, 404, "账号不存在")
        val all = configs.exportAll().optJSONObject("configs") ?: JSONObject()
        val selected = JSONObject()
        val prefix = "$accountId::"
        all.keys().forEach { key -> if (key.startsWith(prefix)) selected.put(key.removePrefix(prefix), all.opt(key)) }
        return ok(
            request,
            JSONObject()
                .put("account", accountJson(account))
                .put("configDir", "手机本地存储")
                .put("files", JSONArray().put(JSONObject()
                    .put("name", "account-config.json")
                    .put("path", "手机本地存储")
                    .put("exists", true)
                    .put("content", selected.toString(2))))
        )
    }

    private fun accountArray(): JSONArray = JSONArray().apply {
        accounts.listAccounts().forEach { put(accountJson(it)) }
    }

    private fun accountJson(account: GameAccount): JSONObject {
        val presentation = AccountLifecyclePresentationPolicy.resolve(
            accountEnabled = account.enabled,
            executionOwnerActive = AssistantForegroundService.isExecutionOwnerActive(),
            loginState = account.loginState,
            contract = behaviorContract.accountLifecycle
        )
        val extra = account.session?.channelExtra.orEmpty()
        val level = extra["level"]?.toIntOrNull()
        val retry = reconnects.state(account.id)
        val checkedAt = extra["lastHeartbeatAt"]?.toLongOrNull()
            ?: extra["lastValidatedAt"]?.toLongOrNull()
        val lastError = extra["lastReloginError"]
            ?: extra["lastOfflineReason"]
            ?: extra["lastNetworkPauseReason"]
            ?: retry.reason
        val nowMillis = System.currentTimeMillis()
        val overview = taskOverview(account.id)
        val hasLiveSession = AccountLifecyclePresentationPolicy.mayUseLiveSession(
            accountEnabled = account.enabled,
            executionOwnerActive = AssistantForegroundService.isExecutionOwnerActive(),
            loginState = account.loginState,
            sourceMode = account.session?.sourceMode ?: 0,
            contract = behaviorContract.accountLifecycle
        )
        return JSONObject()
            .put("sessionId", account.id.toString())
            .put("username", account.username)
            .put("displayName", account.displayName ?: "${account.username}@${account.serverName}")
            .put("serverQuery", account.serverName)
            .put("areaName", account.serverName)
            .put("roleName", account.monarchName ?: account.displayName)
            .put("level", level ?: JSONObject.NULL)
            .put("status", presentation.status)
            .put("statusText", presentation.statusText)
            .put("started", presentation.started)
            .put("desiredStarted", account.enabled)
            .put("hasLiveSession", hasLiveSession)
            .put("lastHeartbeat", checkedAt?.let {
                JSONObject()
                    .put("online", presentation.status == "online")
                    .put("message", if (presentation.status == "online") "在线" else lastError)
                    .put("checkedAt", it)
            } ?: JSONObject.NULL)
            .put("lastError", lastError)
            .put("reconnectState", if (retry.nextAttemptAtMillis > nowMillis) "countdown" else "")
            .put("reconnectAt", retry.nextAttemptAtMillis.takeIf { it > 0L } ?: JSONObject.NULL)
            .put(
                "reconnectRemainingSec",
                ((retry.nextAttemptAtMillis - nowMillis).coerceAtLeast(0L) + 999L) / 1_000L
            )
            .put("accountHabits", accountHabits(account.id))
            .put("session", if (hasLiveSession) sessionJson(account) else JSONObject.NULL)
            .put("recentGameRequests", JSONArray().apply {
                requestHealth.recent(account.id).forEach { item ->
                    put(JSONObject()
                        .put("status", if (item.success) "success" else "failure")
                        .put("purpose", item.purpose)
                        .put("time", item.timeMillis))
                }
            })
            .put("dailyStats", dailyStatsJson(account.id))
            .put("taskStack", overview.optJSONArray("taskStack") ?: JSONArray())
            .put("notices", overview.optJSONArray("notices") ?: JSONArray())
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
        return JSONObject()
            .put("capacity", extra["inventoryCapacity"]?.toIntOrNull() ?: JSONObject.NULL)
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
        val account = accounts.get(accountId)
        val nowMillis = System.currentTimeMillis()
        val schedulerActive = account?.enabled == true &&
            AssistantForegroundService.isExecutionOwnerActive()
        val statuses = SchedulerTaskOrdering.orderValues(
            runtimeStatuses.list(accountId),
            behaviorContract.scheduler
        ) { it.type }
        val latestByKey = LocalTaskPresentation.latestByKey(statuses)
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
                val state = LocalTaskPresentation.schedulerState(status)
                resident.put(JSONObject()
                    .put("key", spec.key)
                    .put("name", spec.name)
                    .put("running", LocalTaskPresentation.isActive(status))
                    .put("status", if (LocalTaskPresentation.isActive(status)) "running" else "idle")
                    .put("schedulerState", state)
                    .put("schedulerMessage", UserFacingTextLocalizer.localize(status?.message.orEmpty()))
                    .put("schedulerPriority", behaviorContract.scheduler.residentPriority[spec.key] ?: 0)
                    .put("schedulerRunnable", status?.state == TaskRuntimeState.RUNNING)
                    .put("schedulerNextCheckAt", status?.nextRunAtMillis ?: JSONObject.NULL)
                    .put("taskId", status?.let { "android-$accountId-${spec.key}" } ?: JSONObject.NULL)
                    .put("updatedAt", status?.updatedAtMillis ?: JSONObject.NULL))
            }
        LocalTaskPresentation.dailySpecs.forEach { spec ->
            val status = latestByKey[spec.key]
            val completionKey = requireNotNull(spec.completionKey)
            val completed = dailyStats.isCompleted(accountId, completionKey)
            daily.put(
                JSONObject()
                    .put("key", spec.key)
                    .put("name", spec.name)
                    .put("completed", completed)
                    .put("statusText", if (completed) "已做" else "未做")
                    .put("state", LocalTaskPresentation.schedulerState(status, completed))
                    .put("message", UserFacingTextLocalizer.localize(status?.message.orEmpty()))
                    .put("nextRunAt", status?.nextRunAtMillis ?: JSONObject.NULL)
                    .put("updatedAt", status?.updatedAtMillis ?: JSONObject.NULL)
            )
        }
        return JSONObject()
            .put("date", SimpleDateFormat("yyyyMMdd", Locale.ROOT).format(Date()))
            .put("updatedAt", nowMillis)
            .put(
                "savedTasksStarted",
                account?.enabled == true &&
                    account.session?.channelExtra?.get("savedTasksStarted")
                        .equals("true", ignoreCase = true) &&
                    AssistantForegroundService.isExecutionOwnerActive()
            )
            .put("taskStack", stack)
            .put("resident", resident)
            .put("daily", daily)
            .put("notices", runtimeNotices(accountId, statuses))
    }

    private fun automationTasks(accountId: Long): JSONArray {
        val taskLogs = logs.recent(40)
            .filter { it.accountId == accountId }
            .asReversed()
            .map {
                "[${SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date(it.timeMillis))}] " +
                    UserFacingTextLocalizer.localize(it.message)
            }
        val statuses = runtimeStatuses.list(accountId).sortedByDescending { it.updatedAtMillis }
        return JSONArray().apply {
            statuses.forEach { status ->
                val spec = LocalTaskPresentation.spec(status.type)
                val publicStatus = when (status.state) {
                    TaskRuntimeState.STOPPED, TaskRuntimeState.SERVICE_STOPPED -> "stopped"
                    TaskRuntimeState.ERROR, TaskRuntimeState.NEED_RELOGIN -> "error"
                    else -> "running"
                }
                put(
                    JSONObject()
                        .put("taskId", "android-$accountId-${spec.key}")
                        .put("sessionId", accountId.toString())
                        .put("type", spec.key)
                        .put("name", spec.name)
                        .put("status", publicStatus)
                        .put("schedulerState", LocalTaskPresentation.schedulerState(status))
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
        val account = accounts.get(accountId) ?: return JSONArray()
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

    private fun runtimeNotices(
        accountId: Long,
        statuses: List<com.example.dwpmclone.domain.scheduler.TaskRuntimeStatus> = runtimeStatuses.list(accountId)
    ): JSONArray = JSONArray().apply {
        statuses.filter {
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
        accountConnectionNotice(accountId)?.let(::put)
        logDerivedNotices(accountId).forEach(::put)
    }

    private fun accountConnectionNotice(accountId: Long): JSONObject? {
        val account = accounts.get(accountId) ?: return null
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

    private fun logDerivedNotices(accountId: Long): List<JSONObject> {
        val active = linkedMapOf<String, Pair<LocalTaskPresentationSpec, TaskLogEntry>>()
        logs.recent(200)
            .filter { it.accountId == accountId }
            .asReversed()
            .forEach { entry ->
                val spec = noticeSpec(entry.message) ?: return@forEach
                when {
                    entry.message.containsAny("失败", "异常", "中止", "暂停", "未完成") ->
                        active[spec.key] = spec to entry
                    entry.message.containsAny("完成", "成功", "重复", "已领取", "已做") ->
                        active.remove(spec.key)
                }
            }
        val terminalKeys = runtimeStatuses.list(accountId)
            .filter { it.state in setOf(TaskRuntimeState.STOPPED, TaskRuntimeState.ERROR, TaskRuntimeState.NEED_RELOGIN) }
            .map { LocalTaskPresentation.spec(it.type).key }
            .toSet()
        return active.values
            .filterNot { (spec, _) -> spec.key in terminalKeys }
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
                    "generalMaintenance" -> "GENERAL"
                    "autoDomestic" -> "INTERNAL"
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

    private fun dailyStatsJson(accountId: Long): JSONObject = dailyStats.stats(accountId).let {
        JSONObject().put("brushYellowCount", it.brushYellowCount).put("dungeonCount", it.dungeonCount)
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
        "/api/settings/save" -> if (body.optString("scope") == "brush") {
            "brushYellow" to !mapping.disabled
        } else {
            null
        }
        else -> null
    }

    private fun requireAccount(body: JSONObject?): GameAccount {
        val id = body?.optString("sessionId")?.toLongOrNull()
            ?: throw IllegalArgumentException("缺少账号 sessionId")
        return accounts.get(id) ?: throw IllegalArgumentException("账号不存在")
    }

    private fun logJson(entry: TaskLogEntry, id: Long, system: Boolean): JSONObject {
        val message = UserFacingTextLocalizer.localize(entry.message)
        return JSONObject()
            .put("id", id)
            .put("time", entry.timeMillis)
            .put("timeText", formatTime(entry.timeMillis))
            .put("level", if (message.contains("失败") || message.contains("异常") || message.contains("错误")) "error" else "info")
            .put("source", entry.tag)
            .put("sessionId", entry.accountId?.toString() ?: "")
            .put("accountKey", if (system) entry.accountId?.let { "账号$it" }.orEmpty() else "")
            .put("message", message)
    }

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

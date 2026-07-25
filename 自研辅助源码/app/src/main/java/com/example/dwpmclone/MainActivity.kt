package com.example.dwpmclone

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.InputType
import android.text.TextUtils
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.CollaborativeMapSettingsRepository
import com.example.dwpmclone.data.local.LocalConfigRepository
import com.example.dwpmclone.data.local.LocalDailySuccessStatsRepository
import com.example.dwpmclone.data.local.LocalGuideRepository
import com.example.dwpmclone.data.local.LocalScreenSpecRepository
import com.example.dwpmclone.data.local.LocalRoleState
import com.example.dwpmclone.data.local.LocalRoleStateRepository
import com.example.dwpmclone.data.local.ScreenSpec
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.local.TaskLogEntry
import com.example.dwpmclone.data.local.TaskLogAccountResolver
import com.example.dwpmclone.data.local.TaskRuntimeStatusRepository
import com.example.dwpmclone.data.remote.DesktopCoreApiClient
import com.example.dwpmclone.data.remote.DesktopCoreResult
import com.example.dwpmclone.data.remote.DesktopCoreSettings
import com.example.dwpmclone.data.remote.DesktopCoreSettingsRepository
import com.example.dwpmclone.data.protocol.RealGameProtocolClient
import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.data.protocol.GameNetworkRoute
import com.example.dwpmclone.data.protocol.GameProxyMode
import com.example.dwpmclone.domain.blueprint.FeatureBlueprints
import com.example.dwpmclone.domain.cloud.CloudMapResult
import com.example.dwpmclone.domain.cloud.CollaborativeMapHttpSettings
import com.example.dwpmclone.domain.cloud.HttpCollaborativeMapClient
import com.example.dwpmclone.domain.model.Channel
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.GameVersion
import com.example.dwpmclone.domain.model.AlarmWithdrawConfig
import com.example.dwpmclone.domain.model.InventoryAutoOpenPolicy
import com.example.dwpmclone.domain.model.MinistryProtocolCrop
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.GeneralVisitCandidate
import com.example.dwpmclone.domain.protocol.State8004ArmyEvidenceParser
import com.example.dwpmclone.domain.protocol.State8004GeneralEvidenceParser
import com.example.dwpmclone.domain.protocol.State8004StatusEvidenceParser
import com.example.dwpmclone.domain.protocol.DungeonProtocolShapes
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.reference.OpenServerTimeCalculator
import com.example.dwpmclone.domain.scheduler.HostingStartPolicy
import com.example.dwpmclone.domain.scheduler.SavedConfigTaskPlanFactory
import com.example.dwpmclone.domain.scheduler.SuspendRunner
import com.example.dwpmclone.service.AssistantForegroundService
import com.example.dwpmclone.ui.RenderedScreen
import com.example.dwpmclone.ui.ScreenSpecRenderer
import com.example.dwpmclone.ui.assistant.AssistantRealtimeAccountDisplayMapper
import com.example.dwpmclone.ui.assistant.copySelectedOrFirstRows
import com.example.dwpmclone.ui.assistant.FutureMilitaryGeneralSelectionCodec
import com.example.dwpmclone.ui.assistant.MilitaryIntelDisplayMapper
import com.example.dwpmclone.ui.assistant.MilitaryIntelTab
import com.example.dwpmclone.ui.assistant.MilitaryIntelTabPolicy
import com.example.dwpmclone.ui.assistant.TreasureBrowserPolicy
import java.text.SimpleDateFormat
import java.net.NetworkInterface
import java.net.HttpURLConnection
import java.net.URL
import java.util.Date
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

/** Self-developed assistant UI. Role/account data must come only from real protocol responses. */
class MainActivity : BaseUiActivity() {
    private val screenRepo by lazy { LocalScreenSpecRepository(this) }
    private val configRepo by lazy { LocalConfigRepository(this) }
    private val accountRepo by lazy { LocalAccountRepository(this) }
    private val logRepo by lazy { TaskLogRepository(this) }
    private val taskRuntimeStatusRepo by lazy { TaskRuntimeStatusRepository(this) }
    private val roleStateRepo by lazy { LocalRoleStateRepository(this) }
    private val dailySuccessStatsRepo by lazy { LocalDailySuccessStatsRepository(this) }
    private val cloudMapSettingsRepo by lazy { CollaborativeMapSettingsRepository(this) }
    private val desktopCoreSettingsRepo by lazy { DesktopCoreSettingsRepository(this) }
    private val mainHandler by lazy { Handler(Looper.getMainLooper()) }
    private val activeSideByCategory = mutableMapOf<ConfigCategory, String>()
    private var activeRenderedScreen: RenderedScreen? = null
    private var formationDraftRows: MutableList<FormationDraftRow>? = null
    private val formationEnabledCheckBoxes = mutableListOf<CheckBox>()
    private val formationGeneralSpinners = mutableListOf<Spinner>()
    private val formationSoldierSpinners = mutableListOf<Spinner>()
    private val formationCountInputs = mutableListOf<EditText>()
    private var formationGeneralSpinner: Spinner? = null
    private var formationSoldierSpinner: Spinner? = null
    private var formationCountInput: EditText? = null
    private var dungeonEnabledCheck: CheckBox? = null
    private var dungeonDailyTimesInput: EditText? = null
    private var dungeonChapterSpinner: Spinner? = null
    private var dungeonStageSpinner: Spinner? = null
    private var dungeonChestSpinner: Spinner? = null
    private val dungeonGeneralChecks = mutableListOf<Pair<Long, CheckBox>>()
    private var lootFullTroopsCheck: CheckBox? = null
    private var lootFullLoyaltyCheck: CheckBox? = null
    private var lootDraftRows: MutableList<LootDraftRow>? = null
    private val lootEnabledChecks = mutableListOf<CheckBox>()
    private val lootGeneralPickers = mutableListOf<LootGeneralPickerState>()
    private val lootTargetPlayerInputs = mutableListOf<EditText>()
    private val lootFiefIndexInputs = mutableListOf<EditText>()
    private var commonInternalEnabledCheck: CheckBox? = null
    private var commonInternalLowFirstCheck: CheckBox? = null
    private var commonInternalEmptyTypeSpinner: Spinner? = null
    private var commonFoodConvertEnabledCheck: CheckBox? = null
    private var commonFoodConvertAmountSpinner: Spinner? = null
    private var commonReconnectInput: EditText? = null
    private var commonBrushLimitInput: EditText? = null
    private var commonHealCheck: CheckBox? = null
    private var commonUpgradeTechnologyCheck: CheckBox? = null
    private var commonTechnologyPicker: TextView? = null
    private val commonTechnologyIds = linkedSetOf<Int>()
    private var commonAutoEnergyCheck: CheckBox? = null
    private var commonEnergyThresholdInput: EditText? = null
    private var commonReleaseCheck: CheckBox? = null
    private var commonReleaseThresholdInput: EditText? = null
    private var commonSurrenderCheck: CheckBox? = null
    private var commonSurrenderThresholdInput: EditText? = null
    private var commonSurrenderMethodSpinner: Spinner? = null
    private var dailySignInCheck: CheckBox? = null
    private var dailyArenaCheck: CheckBox? = null
    private var dailyDonateCheck: CheckBox? = null
    private var dailySalaryCheck: CheckBox? = null
    private var dailyNationalCollectCheck: CheckBox? = null
    private var dailyCityLordCollectCheck: CheckBox? = null
    private var dailyGeneralVisitCheck: CheckBox? = null
    private var dailyGeneralVisitPicker: TextView? = null
    private var dailyGeneralVisitRefresh: TextView? = null
    private var dailyGeneralVisitCandidates: List<GeneralVisitCandidate> = emptyList()
    private val dailyGeneralVisitSelectedIds = mutableListOf<Long>()
    private var dailyGeneralVisitQueryInFlight = false
    private var dailyGeneralVisitCandidateAccountId: Long? = null
    private var dailyTruceCheck: CheckBox? = null
    private var dailyChainOrganizeCheck: CheckBox? = null
    private var shuaHuangDraftRows: MutableList<ShuaHuangDraftRow>? = null
    private val shuaHuangEnabledCheckBoxes = mutableListOf<CheckBox>()
    private val shuaHuangGeneralSpinners = mutableListOf<Spinner>()
    private val shuaHuangLevelSpinners = mutableListOf<Spinner>()
    private val shuaHuangDropCheckGroups = mutableListOf<List<CheckBox>>()
    private val shuaHuangFootSpinners = mutableListOf<Spinner>()
    private val shuaHuangBowSpinners = mutableListOf<Spinner>()
    private val shuaHuangCavalrySpinners = mutableListOf<Spinner>()
    private val shuaHuangChariotSpinners = mutableListOf<Spinner>()
    private var shuaHuangGeneralSpinner: Spinner? = null
    private var shuaHuangCompositionInput: EditText? = null
    private var shuaHuangLevelInput: EditText? = null
    private var shuaHuangStartHourSpinner: Spinner? = null
    private var shuaHuangStartXInput: EditText? = null
    private var shuaHuangStartYInput: EditText? = null
    private var shuaHuangRefillCheck: CheckBox? = null
    private var shuaHuangFoodConvertCheck: CheckBox? = null
    private var shuaHuangCopperFloorSpinner: Spinner? = null
    private var shuaHuangCleanMailCheck: CheckBox? = null
    private var selectedAccountId: Long? = null
    private var activeLogCategory: LogCategory = LogCategory.ACCOUNT
    private var selectedLogAccountId: Long? = null
    private var activeHomeTab: HomeTab = HomeTab.CONFIG
    private var lastRenderedLogFingerprint: String = ""
    private val logRefreshRunnable = object : Runnable {
        override fun run() {
            if (activeHomeTab != HomeTab.LOGS || isFinishing || isDestroyed) return
            val fingerprint = logFingerprint()
            if (fingerprint != lastRenderedLogFingerprint) {
                showHome(HomeTab.LOGS)
            } else {
                mainHandler.postDelayed(this, LOG_REFRESH_INTERVAL_MS)
            }
        }
    }
    private var treasureSearchQuery: String = ""
    private var mineDraftRows: MutableList<MineDraftRow>? = null
    private val mineEnabledChecks = mutableListOf<CheckBox>()
    private val mineGeneralPickers = mutableListOf<LootGeneralPickerState>()
    private val mineResourceSpinners = mutableListOf<Spinner>()
    private val mineXInputs = mutableListOf<EditText>()
    private val mineYInputs = mutableListOf<EditText>()
    private val mineScopeSpinners = mutableListOf<Spinner>()
    private var mineSpeedSpinner: Spinner? = null
    private var mineFullLoyaltyCheck: CheckBox? = null
    private var mineTargetPlayerInput: EditText? = null
    private var ministryCropEnabledCheck: CheckBox? = null
    private var ministryCropSpinner: Spinner? = null
    private var ministryHighPriorityCheck: CheckBox? = null
    private var ministryStealEnabledCheck: CheckBox? = null
    private var ministryCourtesyEnabledCheck: CheckBox? = null
    private var ministrySalaryRefreshCheck: CheckBox? = null
    private val futureMilitaryDraftRows = mutableMapOf<String, MutableList<FutureMilitaryDraftRow>>()
    private val futureMilitaryEnabledChecks = mutableListOf<CheckBox>()
    private val futureMilitaryGeneralPickers = mutableListOf<LootGeneralPickerState>()
    private val futureMilitaryOptionSpinners = mutableListOf<Spinner>()
    private var futureMilitaryActiveFeature: String? = null
    private var futureMilitaryPrimaryCheck: CheckBox? = null
    private var futureMilitarySecondaryCheck: CheckBox? = null
    private var futureMilitaryTertiaryCheck: CheckBox? = null
    private var futureMilitaryTextInput: EditText? = null
    private var futureMilitaryCountInput: EditText? = null
    private var futureMilitaryRefreshInput: EditText? = null
    private var futureMilitarySpeedSpinner: Spinner? = null
    private val inventoryDiscardChecks = mutableListOf<Pair<String, CheckBox>>()
    private val inventoryAutoOpenChecks = mutableListOf<Pair<String, CheckBox>>()
    private var inventoryDiscardEquipmentCheck: CheckBox? = null
    private var inventoryQualitySpinner: Spinner? = null
    private var inventoryLevelInput: EditText? = null
    private var inventoryAutoOpenEnabledCheck: CheckBox? = null
    private var chainInventoryEnabledCheck: CheckBox? = null
    private var chainInventoryItemInput: EditText? = null
    private var chainInventoryKeepCountInput: EditText? = null
    private var chainInventoryAutoOpenCheck: CheckBox? = null
    private var chainInventoryOpenItemsInput: EditText? = null
    private var alarmIncomingCheck: CheckBox? = null
    private var alarmIncomingModeSpinner: Spinner? = null
    private var alarmMilitaryCheck: CheckBox? = null
    private var alarmMilitaryModeSpinner: Spinner? = null
    private var alarmErrorCheck: CheckBox? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The desktop reference renders both system chrome areas on white.  Keep the
        // Android system bars visually continuous with that phone-frame design instead
        // of inheriting Material's blue status bar.
        window.statusBarColor = Color.WHITE
        window.navigationBarColor = Color.WHITE
        @Suppress("DEPRECATION")
        run {
            var flags = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                flags = flags or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
            }
            window.decorView.systemUiVisibility = flags
        }
        // Match the current desktop bootstrap state (`activeSide = "任务"`).
        activeSideByCategory.putIfAbsent(ConfigCategory.ROLE, "任务")
        migratePersisted8004RoleData()
        showHome(HomeTab.CONFIG)
    }

    /**
     * APKs before round 34 persisted the complete 0x8004 payload but omitted the two
     * stable limit fields from channelExtra. Recover and persist them locally once so an
     * existing account does not need a password, relogin, or game request after upgrade.
     */
    private fun migratePersisted8004RoleData() {
        accountRepo.listAccounts().forEach { account ->
            val session = account.session ?: return@forEach
            if (session.sourceMode != 1) return@forEach
            val needsLimits =
                session.channelExtra["fiefLimit"]?.toIntOrNull() == null ||
                    session.channelExtra["generalLimit"]?.toIntOrNull() == null
            val needsArmy = listOf("armyJson", "idleArmyJson", "troopsJson")
                .all { session.channelExtra[it].isNullOrBlank() }
            if (!needsLimits && !needsArmy) return@forEach
            val payloadHex = session.channelExtra["state8004PayloadHex"]
                ?.takeIf { it.isNotBlank() }
                ?: return@forEach
            val updates = mutableMapOf<String, String>()
            var limitsSummary: String? = null
            if (needsLimits) {
                runCatching {
                    RealGameProtocolClient().parsePersisted8004HeadHex(payloadHex)
                }.onSuccess { state ->
                    if (session.channelExtra["fiefLimit"]?.toIntOrNull() == null) {
                        updates["fiefLimit"] = state.fiefLimit.toString()
                    }
                    if (session.channelExtra["generalLimit"]?.toIntOrNull() == null) {
                        updates["generalLimit"] = state.generalLimit.toString()
                    }
                    updates["roleLimitRecoverySource"] = "persisted/0x8004"
                    limitsSummary = "封地上限=${state.fiefLimit}，将领上限=${state.generalLimit}"
                }.onFailure { error ->
                    logRepo.append(
                        "账号${account.id}旧0x8004上限字段本地恢复失败：${error.message}",
                        "local-migration"
                    )
                }
            }
            var armySummary: String? = null
            if (needsArmy) {
                val armyRows = State8004ArmyEvidenceParser.recover(payloadHex)
                if (armyRows.isNotEmpty()) {
                    updates["armyJson"] = State8004ArmyEvidenceParser.toJson(armyRows)
                    updates["armySource"] = "persisted/0x8004-compact-army"
                    updates["armyRecordCount"] = armyRows.size.toString()
                    armySummary = "军队${armyRows.size}行"
                }
            }
            if (updates.isEmpty()) return@forEach
            accountRepo.upsert(
                account.copy(
                    session = session.copy(channelExtra = session.channelExtra + updates)
                )
            )
            logRepo.append(
                "账号${account.id}已从旧0x8004本地恢复：" +
                    listOfNotNull(limitsSummary, armySummary).joinToString("；"),
                "local-migration"
            )
        }
    }

    private enum class HomeTab(val title: String) {
        CONFIG("助手"),
        OVERVIEW("攻略"),
        HOSTING("Home"),
        LOGS("日志")
    }

    private enum class ConfigCategory(val title: String) {
        ROLE("角色"),
        MILITARY("军事"),
        SHUA_HUANG("刷黄"),
        WAR_INFO("军情"),
        MINING("打矿"),
        MINISTRY("六部"),
        COMMON("常规")
    }

    private enum class LogCategory(val title: String) {
        ACCOUNT("账号日志"),
        SYSTEM("系统日志")
    }

    private var activeConfigCategory: ConfigCategory = ConfigCategory.ROLE

    private fun showHome(tab: HomeTab = HomeTab.OVERVIEW) {
        activeHomeTab = tab
        mainHandler.removeCallbacks(logRefreshRunnable)
        val screens = runCatching { screenRepo.loadAll() }.getOrDefault(emptyList())
        val root = pageRoot()

        when (tab) {
            HomeTab.OVERVIEW -> {
                root.addView(pageTitle("攻略"))
                root.addView(referenceCard())
                root.addView(card().apply {
                    addView(sectionTitle("使用说明"))
                    addView(sectionTitle("出征将领坑位").apply { textSize = 17f })
                    addView(bodyText("您勾选出征将领的顺序决定将领的坑位，逻辑与原服中相同，即最先勾选的将领将会占据首排居中的坑位。"))
                })
            }
            HomeTab.HOSTING -> {
                root.addView(pageTitle("Home"))
                root.addView(hostingCard())
            }
            HomeTab.CONFIG -> root.addView(featureCard(screens))
            HomeTab.LOGS -> root.addView(logsPage())
        }

        setTabbedPage(root, tab)
        if (tab == HomeTab.LOGS) {
            mainHandler.postDelayed(logRefreshRunnable, LOG_REFRESH_INTERVAL_MS)
        }
    }

    override fun onDestroy() {
        mainHandler.removeCallbacks(logRefreshRunnable)
        super.onDestroy()
    }

    private fun heroCard(): LinearLayout = card().apply {
        setBackgroundColor(Color.TRANSPARENT)
        background = rounded(COLOR_PRIMARY, 22f)
        addView(TextView(this@MainActivity).apply {
            text = "自研服务"
            textSize = 25f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
        })
        addView(TextView(this@MainActivity).apply {
            text = "真实协议只读版 · 本地配置 / 任务日志"
            textSize = 14f
            setTextColor(0xE6FFFFFF.toInt())
            setPadding(0, dp(8), 0, 0)
        })
        addView(TextView(this@MainActivity).apply {
            text = "没有协议层真实返回时，角色、等级、铜钱、粮食等一律不展示、不落库。"
            textSize = 13f
            setTextColor(0xD9FFFFFF.toInt())
            setPadding(0, dp(7), 0, 0)
        })
    }

    private fun statusCard(): LinearLayout = card().apply {
        addView(sectionTitle("运行概览"))
        addView(bodyText(loadLocalAssetSummary()))
        val accountText = accountSummary()
        addView(bodyText(accountText).apply { setPadding(0, dp(10), 0, 0) })
        addView(bodyText(latestLogSummary()).apply { setPadding(0, dp(10), 0, 0) })
    }

    private fun hostingCard(): LinearLayout = card().apply {
        addView(sectionTitle("账号设置"))
        val accounts = realProtocolAccounts()
        val accountOptions = if (accounts.isEmpty()) {
            listOf("请选择账号")
        } else {
            accounts.map { "${it.username}@${it.serverName}" }
        }
        val accountSpinner = Spinner(this@MainActivity).apply {
            adapter = compactSpinnerAdapter(accountOptions)
        }
        val rawSettings = TextView(this@MainActivity).apply {
            text = "选择账号后点击“查看设置”读取该账号的原始设置文件"
            textSize = 13f
            setTextColor(COLOR_SUBTEXT)
            typeface = Typeface.MONOSPACE
            setPadding(dp(12), dp(12), dp(12), dp(12))
            background = roundedStroke(Color.WHITE, 2f, COLOR_BORDER)
        }
        addView(designRow("账号：", accountSpinner))
        addView(outlineButton("查看设置") {
            val account = accounts.getOrNull(accountSpinner.selectedItemPosition)
            if (account == null) {
                showTopToast("请先添加账号")
            } else {
                val all = configRepo.exportAll()
                val configs = all.optJSONObject("configs") ?: JSONObject()
                val selected = JSONObject()
                val prefix = "${account.id}::"
                configs.keys().forEach { key ->
                    if (key.startsWith(prefix)) {
                        selected.put(key.removePrefix(prefix), configs.optJSONObject(key))
                    }
                }
                rawSettings.text = JSONObject()
                    .put("accountId", account.id)
                    .put("username", account.username)
                    .put("serverName", account.serverName)
                    .put("configs", selected)
                    .toString(2)
            }
        })
        addView(rawSettings, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, dp(10), 0, dp(18)) })

        val desktopCore = desktopCoreSettingsRepo.load()
        addView(sectionTitle("电脑端统一核心（推荐）"))
        addView(bodyText("安卓只负责展示和控制；账号登录、游戏协议、任务锁、每日完成状态、代理与日志全部由电脑端统一执行。这样电脑端新增功能会直接在手机完整控制台中可用。"))
        val desktopCoreEnabled = CheckBox(this@MainActivity).apply {
            text = "启用电脑端统一核心"
            isChecked = desktopCore.enabled
            textSize = 15f
        }
        val desktopCoreUrl = cloudSettingsInput(
            value = desktopCore.baseUrl,
            hintText = "电脑地址，例如 http://192.168.1.10:17351"
        )
        val desktopCoreToken = cloudSettingsInput(
            value = desktopCore.apiToken,
            hintText = "DWPM_MOBILE_API_TOKEN"
        ).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        addView(desktopCoreEnabled)
        addView(bodyText("设备身份：${desktopCore.deviceId}；手机不会保存或接收游戏 session/token。"))
        addView(desktopCoreUrl)
        addView(desktopCoreToken)
        addView(primaryButton("保存并打开完整控制台") {
            val saved = saveDesktopCoreSettings(
                enabled = desktopCoreEnabled.isChecked,
                baseUrl = desktopCoreUrl.text?.toString().orEmpty(),
                apiToken = desktopCoreToken.text?.toString().orEmpty(),
                deviceId = desktopCore.deviceId
            )
            if (saved) startActivity(Intent(this@MainActivity, RemoteCoreActivity::class.java))
        })
        addView(outlineButton("测试电脑端连接") {
            testDesktopCoreConnection(
                baseUrl = desktopCoreUrl.text?.toString().orEmpty(),
                apiToken = desktopCoreToken.text?.toString().orEmpty(),
                deviceId = desktopCore.deviceId
            )
        })

        addView(sectionTitle("本机兼容托管").apply { setPadding(0, dp(22), 0, 0) })
        addView(bodyText("保留现有安卓本地协议与调度作为迁移期兼容层。新功能和正式托管优先使用上面的电脑端统一核心。"))
        addView(primaryButton("启动后台托管") {
            val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
            if (decision.allowed) {
                AssistantForegroundService.start(this@MainActivity)
            }
            Toast.makeText(this@MainActivity, decision.message, Toast.LENGTH_SHORT).show()
        })
        addView(outlineButton("停止后台托管") {
            AssistantForegroundService.stop(this@MainActivity)
            Toast.makeText(this@MainActivity, "后台托管已请求停止", Toast.LENGTH_SHORT).show()
        })
        addView(outlineButton("导出配置摘要") {
            val count = configRepo.exportAll().optJSONObject("configs")?.length() ?: 0
            Toast.makeText(this@MainActivity, "当前配置：$count 条", Toast.LENGTH_SHORT).show()
        })

        val cloudSettings = cloudMapSettingsRepo.load()
        addView(sectionTitle("云端协作地图").apply { setPadding(0, dp(22), 0, 0) })
        addView(bodyText("刷黄、打矿严格执行：本地扫描 → 上传云端 → 获取同版本推荐 → 出征。云端不可用时禁止本地兜底出征。"))
        val cloudEnabled = CheckBox(this@MainActivity).apply {
            text = "启用云端协作地图"
            isChecked = cloudSettings.enabled
            textSize = 15f
        }
        val cloudUrl = cloudSettingsInput(
            value = cloudSettings.baseUrl,
            hintText = "服务器地址，例如 http://127.0.0.1:18080"
        )
        val cloudToken = cloudSettingsInput(
            value = cloudSettings.authToken,
            hintText = "鉴权 Token（局域网联调可留空）"
        ).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        addView(cloudEnabled)
        addView(bodyText("设备身份：${cloudSettings.deviceId}"))
        addView(cloudUrl)
        addView(cloudToken)
        addView(primaryButton("保存云端设置") {
            saveCollaborativeMapSettings(
                enabled = cloudEnabled.isChecked,
                baseUrl = cloudUrl.text?.toString().orEmpty(),
                authToken = cloudToken.text?.toString().orEmpty()
            )
        })
        addView(outlineButton("测试云端连接") {
            testCollaborativeMapConnection(
                baseUrl = cloudUrl.text?.toString().orEmpty(),
                authToken = cloudToken.text?.toString().orEmpty(),
                deviceId = cloudSettings.deviceId
            )
        })

        addView(outlineButton("清空账号与日志") {
            accountRepo.clear()
            roleStateRepo.clear()
            logRepo.clear()
            Toast.makeText(this@MainActivity, "已清空账号、角色状态与日志", Toast.LENGTH_SHORT).show()
            showHome(HomeTab.HOSTING)
        })
    }

    private fun cloudSettingsInput(value: String, hintText: String): EditText =
        EditText(this).apply {
            setText(value)
            hint = hintText
            textSize = 14f
            setSingleLine(true)
            background = roundedStroke(Color.WHITE, 12f, COLOR_BORDER)
            setPadding(dp(14), 0, dp(14), 0)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(52)
            ).apply { setMargins(0, dp(8), 0, 0) }
        }

    private fun saveDesktopCoreSettings(
        enabled: Boolean,
        baseUrl: String,
        apiToken: String,
        deviceId: String
    ): Boolean {
        val settings = DesktopCoreSettings(
            enabled = enabled,
            baseUrl = baseUrl,
            apiToken = apiToken,
            deviceId = deviceId
        )
        // Disabling the remote core is itself a valid state: do not require a
        // URL/token merely to turn the feature off.  When enabling, retain the
        // strict connection validation so a half-configured client cannot be
        // launched.
        if (enabled) {
            settings.validationError()?.let {
                showTopToast(it)
                return false
            }
        }
        desktopCoreSettingsRepo.save(settings)
        logRepo.append(
            "电脑端统一核心设置已保存：url=${settings.normalizedBaseUrl} device=$deviceId",
            "desktop-core"
        )
        showTopToast("电脑端核心设置已保存")
        return true
    }

    private fun testDesktopCoreConnection(baseUrl: String, apiToken: String, deviceId: String) {
        val settings = DesktopCoreSettings(
            enabled = true,
            baseUrl = baseUrl,
            apiToken = apiToken,
            deviceId = deviceId
        )
        settings.validationError()?.let {
            showTopToast(it)
            return
        }
        showTopToast("正在连接电脑端核心…")
        Thread {
            val result = DesktopCoreApiClient(settings).listAccounts()
            mainHandler.post {
                when (result) {
                    is DesktopCoreResult.Ok -> {
                        logRepo.append(
                            "电脑端核心连接成功：${settings.normalizedBaseUrl} accounts=${result.value.size}",
                            "desktop-core"
                        )
                        showTopToast("连接成功：已读取 ${result.value.size} 个账号")
                    }
                    is DesktopCoreResult.Err -> {
                        logRepo.append(
                            "电脑端核心连接失败：${result.code} ${result.message}",
                            "desktop-core"
                        )
                        showTopToast("连接失败：${result.message}")
                    }
                }
            }
        }.start()
    }

    private fun saveCollaborativeMapSettings(enabled: Boolean, baseUrl: String, authToken: String) {
        val normalized = baseUrl.trim().trimEnd('/')
        if (enabled && !(normalized.startsWith("http://") || normalized.startsWith("https://"))) {
            showTopToast("云端地址必须以 http:// 或 https:// 开头")
            return
        }
        cloudMapSettingsRepo.save(enabled, normalized, authToken)
        accountRepo.listAccounts().forEach { account ->
            val session = account.session ?: return@forEach
            accountRepo.upsert(
                account.copy(
                    session = session.copy(
                        channelExtra = session.channelExtra + mapOf(
                            "collaborativeMapMode" to if (enabled) "http-cloud" else "disabled-until-server-configured"
                        )
                    )
                )
            )
        }
        logRepo.append(
            "云端协作地图设置已保存：enabled=$enabled url=${normalized.ifBlank { "未配置" }}；下次启动后台服务生效",
            "cloud-map"
        )
        showTopToast("云端设置已保存，下次启动后台托管生效")
    }

    private fun testCollaborativeMapConnection(baseUrl: String, authToken: String, deviceId: String) {
        val normalized = baseUrl.trim().trimEnd('/')
        if (!(normalized.startsWith("http://") || normalized.startsWith("https://"))) {
            showTopToast("请输入有效的 http(s) 云端地址")
            return
        }
        showTopToast("正在测试云端连接…")
        Thread {
            val result = runCatching {
                SuspendRunner.run {
                    HttpCollaborativeMapClient(
                        CollaborativeMapHttpSettings(
                            baseUrl = normalized,
                            deviceId = deviceId,
                            authToken = authToken.trim()
                        )
                    ).checkHealth()
                }
            }.getOrElse {
                CloudMapResult.Err("CLOUD_MAP_TEST_ERROR", it.message ?: "连接测试异常", true)
            }
            mainHandler.post {
                when (result) {
                    is CloudMapResult.Ok -> {
                        logRepo.append("云端连接测试成功：$normalized status=${result.value}", "cloud-map")
                        showTopToast("云端连接成功：${result.value}")
                    }
                    is CloudMapResult.Err -> {
                        logRepo.append("云端连接测试失败：${result.code} ${result.message}", "cloud-map")
                        showTopToast("连接失败：${result.message}")
                    }
                }
            }
        }.start()
    }


    private fun referenceCard(): LinearLayout = card().apply {
        addView(sectionTitle("游戏资料"))
        addView(bodyText("原 APK 里的名将、攻略、开服时间查询，这里整理成三个独立入口。"))
        addView(primaryButton("查名将") { showFamousGeneralLookup() })
        addView(outlineButton("查攻略") { showGuideArticles() })
        addView(outlineButton("查开服时间") { showOpenServerLookup() })
    }

    private fun showFamousGeneralLookup(keyword: String = "") {
        val repo = LocalGuideRepository(this)
        val root = pageRoot()
        val input = EditText(this).apply {
            hint = "输入名将名称 / 属性 / 国家"
            setText(keyword)
            textSize = 15f
            background = roundedStroke(Color.WHITE, 12f, COLOR_BORDER)
            setPadding(dp(14), 0, dp(14), 0)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(52)
            ).apply { setMargins(0, dp(10), 0, 0) }
        }
        val resultCard = card()
        fun fillResults(query: String) {
            resultCard.removeAllViews()
            resultCard.addView(sectionTitle("名将结果"))
            val all = repo.loadFamousGenerals()
            val results = if (query.isBlank()) all.take(40) else all.filter {
                it.name.contains(query, ignoreCase = true) ||
                    (it.attribute?.contains(query, ignoreCase = true) == true) ||
                    (it.nation?.contains(query, ignoreCase = true) == true)
            }.take(80)
            resultCard.addView(bodyText("共 ${all.size} 条；当前显示 ${results.size} 条。"))
            results.forEach { general ->
                resultCard.addView(bodyText("${general.name} · 突破 ${general.breakthrough ?: "-"} · ${general.attribute ?: "-"} · ${general.nation ?: "-"}").apply {
                    setPadding(0, dp(8), 0, 0)
                })
            }
        }
        root.addView(outlineButton("← 返回概览") { showHome(HomeTab.OVERVIEW) })
        root.addView(card().apply {
            addView(sectionTitle("查名将"))
            addView(bodyText("本地名将表来自 APK 资产 dwsgmjb.TXT。"))
            addView(input)
            addView(primaryButton("搜索") { fillResults(input.text?.toString().orEmpty()) })
        })
        fillResults(keyword)
        root.addView(resultCard)
        setTabbedPage(root, HomeTab.OVERVIEW)
    }

    private fun showGuideArticles() {
        val repo = LocalGuideRepository(this)
        val root = pageRoot()
        root.addView(outlineButton("← 返回概览") { showHome(HomeTab.OVERVIEW) })
        root.addView(card().apply {
            addView(sectionTitle("查攻略"))
            addView(bodyText("共 ${repo.loadGuideArticles().size} 篇本地攻略。"))
            repo.loadGuideArticles().forEach { article ->
                addView(outlineButton("${article.title}  ›") { showGuideArticle(article.id) })
            }
        })
        setTabbedPage(root, HomeTab.OVERVIEW)
    }

    private fun showGuideArticle(id: String) {
        val article = LocalGuideRepository(this).readGuideArticle(id)
        val root = pageRoot()
        root.addView(outlineButton("← 返回攻略列表") { showGuideArticles() })
        root.addView(card().apply {
            addView(sectionTitle(article?.title ?: "攻略详情"))
            addView(bodyText(article?.body ?: "未找到攻略内容。"))
        })
        setTabbedPage(root, HomeTab.OVERVIEW)
    }

    private fun showOpenServerLookup() {
        val root = pageRoot()
        val versionSpinner = Spinner(this).apply {
            isSaveEnabled = false
            adapter = ArrayAdapter(
                this@MainActivity,
                android.R.layout.simple_spinner_dropdown_item,
                OpenServerTimeCalculator.versionOptions
            )
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(52)
            ).apply { setMargins(0, dp(10), 0, 0) }
        }
        var serverValues: List<Int> = emptyList()
        val serverAdapter = ArrayAdapter<String>(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            mutableListOf()
        )
        val serverSpinner = Spinner(this).apply {
            isSaveEnabled = false
            adapter = serverAdapter
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(52)
            ).apply { setMargins(0, dp(10), 0, 0) }
        }
        val serverHint = bodyText("选择区服：").apply { setPadding(0, dp(12), 0, 0) }
        val result = TextView(this).apply {
            text = "开服时间：等待查询"
            textSize = 15f
            setTextColor(COLOR_SUBTEXT)
            setPadding(0, dp(12), 0, 0)
        }

        fun refreshServerOptions(option: OpenServerTimeCalculator.VersionOption) {
            val upcoming = OpenServerTimeCalculator.upcomingServer(option.index)
            serverValues = (upcoming.server downTo 1).toList()
            serverAdapter.clear()
            serverAdapter.addAll(serverValues.map { "${it}区" })
            serverAdapter.notifyDataSetChanged()
            serverSpinner.setSelection(0, true)
            serverHint.text = "选择区服：${upcoming.server}区～1区，默认即将开服 ${upcoming.server}区"
            result.text = "即将开服：${option.label} ${upcoming.server}区 · 预计 ${upcoming.dateText}"
        }

        versionSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val option = OpenServerTimeCalculator.versionOptions.getOrNull(position) ?: return
                refreshServerOptions(option)
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }

        root.addView(outlineButton("← 返回概览") { showHome(HomeTab.OVERVIEW) })
        root.addView(card().apply {
            addView(sectionTitle("查开服时间"))
            addView(bodyText("已恢复原 APP 下拉版本名与固定公式；切换版本后会自动选中下一个即将开服区。"))
            addView(versionSpinner)
            addView(serverHint)
            addView(serverSpinner)
            addView(primaryButton("查询开服时间") {
                val server = serverValues.getOrNull(serverSpinner.selectedItemPosition) ?: return@primaryButton
                val option = versionSpinner.selectedItem as OpenServerTimeCalculator.VersionOption
                val calc = OpenServerTimeCalculator.calculate(server, option.index)
                val rule = calc.rule
                result.text = buildString {
                    append("开服时间：${calc.dateText}\n")
                    append("区服：${calc.server}区 · ${calc.version.label}\n")
                    append("规则：${rule.baseServer}区=${rule.year}/${rule.month}/${rule.day}，间隔${rule.intervalDays}天，偏移${calc.daysOffset}天\n")
                    append("证据：${rule.note}")
                }
            })
            addView(result)
        })
        refreshServerOptions(OpenServerTimeCalculator.versionOptions.first())
        setTabbedPage(root, HomeTab.OVERVIEW)
        root.post {
            val option = versionSpinner.selectedItem as? OpenServerTimeCalculator.VersionOption
                ?: OpenServerTimeCalculator.versionOptions.first()
            refreshServerOptions(option)
        }
    }

    private fun featureCard(screens: List<ScreenSpec>): LinearLayout {
        val modules = screens.filterNot { it.featureId.endsWith("_row") }
        val category = activeConfigCategory
        activeRenderedScreen = null
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(pageTitle("助手"))
            addView(configControlPanel())
            addView(configCategoryTabs(category))
            addView(configWorkbenchCard(category, modules))
            addView(configSavePanel(category))
        }
    }

    private fun configControlPanel(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(16), dp(8), dp(16), dp(8))
        background = rounded(Color.rgb(44, 66, 86), 4f)
        elevation = dp(4).toFloat()
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, 0, 0, 0) }

        val accounts = realProtocolAccounts()
        val selected = selectedAccount(accounts)
        val display = assistantAccountDisplay()
        val statusRow = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(TextView(this@MainActivity).apply {
                text = if (accounts.isEmpty()) "未登录" else "${accounts.count { it.enabled }}开"
                textSize = 16f
                setTextColor(Color.WHITE)
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT))
            addView(TextView(this@MainActivity).apply {
                text = selected?.session?.expiresAtMillis?.let {
                    " 到期时间${SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA).format(Date(it))}"
                } ?: " 到期时间未提供"
                textSize = 14f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(if (display.hasRealtimeAccount) Color.rgb(172, 222, 190) else Color.rgb(255, 214, 120))
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(TextView(this@MainActivity).apply {
                text = "续期"
                gravity = Gravity.CENTER
                textSize = 13f
                setTextColor(Color.rgb(67, 101, 145))
                background = rounded(Color.rgb(229, 234, 240), 6f)
                setOnClickListener {
                    showTopToast("当前账号未提供授权到期/续期接口")
                }
            }, LinearLayout.LayoutParams(dp(58), dp(38)).apply { setMargins(dp(4), 0, dp(4), 0) })
            addView(TextView(this@MainActivity).apply {
                text = "⟳"
                gravity = Gravity.CENTER
                textSize = 20f
                setTextColor(Color.WHITE)
                setOnClickListener { showHome(HomeTab.CONFIG) }
            }, LinearLayout.LayoutParams(dp(42), dp(38)))
        }
        addView(statusRow)
        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(accountSpinner(accounts, selected), LinearLayout.LayoutParams(
                0,
                dp(44),
                1f
            ))
            addView(accountStateChip(selected), LinearLayout.LayoutParams(
                dp(58),
                dp(28)
            ).apply { setMargins(dp(6), dp(8), 0, 0) })
        })
        addView(proxyControlRow(selected))

        val actionRow = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(0, dp(12), 0, 0)
            addView(smallAction("启动", Color.rgb(117, 214, 86), Color.rgb(58, 132, 43)) {
                startSelectedAccount()
            })
            addView(smallAction("关闭", Color.rgb(245, 188, 94), Color.rgb(124, 92, 36)) {
                stopSelectedAccount()
            })
            addView(smallAction("修改", Color.rgb(218, 222, 228), Color.rgb(96, 101, 110)) {
                val account = selectedAccount()
                if (account == null) showTopToast("请先选择账号") else showReadOnlyLogin(account)
            })
            addView(smallAction("添加", Color.rgb(79, 169, 245), Color.rgb(36, 102, 161)) { showReadOnlyLogin() })
            addView(smallAction("删除", Color.rgb(255, 134, 143), Color.rgb(142, 53, 60)) {
                deleteSelectedAccount()
            })
        }
        addView(actionRow)
    }

    private fun proxyControlRow(account: GameAccount?): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(0, dp(8), 0, 0)
        addView(TextView(this@MainActivity).apply {
            text = "当前IP"
            textSize = 14f
            setTextColor(Color.WHITE)
        }, LinearLayout.LayoutParams(dp(64), dp(44)))
        val options = listOf("自动选择", "直连", "手动HTTP", "手动SOCKS")
        val mode = account?.session?.channelExtra?.get("proxyMode") ?: "auto"
        val spinner = Spinner(this@MainActivity).apply {
            adapter = compactSpinnerAdapter(options)
            setSelection(
                when (mode.lowercase()) {
                    "direct" -> 1
                    "manual", "http" -> 2
                    "socks" -> 3
                    else -> 0
                },
                false
            )
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    val current = account ?: return
                    val session = current.session ?: return
                    val selectedMode = when (position) {
                        1 -> "direct"
                        2 -> "http"
                        3 -> "socks"
                        else -> "auto"
                    }
                    if (session.channelExtra["proxyMode"] != selectedMode) {
                        if (selectedMode in setOf("http", "socks")) {
                            showProxyEndpointDialog(current, selectedMode)
                        } else {
                            accountRepo.upsert(
                                current.copy(
                                    session = session.copy(
                                        channelExtra = session.channelExtra +
                                            mapOf(
                                                "proxyMode" to selectedMode,
                                                "proxyPublicIp" to ""
                                            )
                                    )
                                )
                            )
                            logRepo.append(
                                "账号${current.id}网络路由已切换：${if (selectedMode == "direct") "直连" else "系统自动代理"}",
                                "proxy"
                            )
                            showHome(HomeTab.CONFIG)
                        }
                    }
                }
                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            }
        }
        addView(spinner, LinearLayout.LayoutParams(0, dp(44), 1f).apply {
            setMargins(dp(4), 0, dp(4), 0)
        })
        addView(TextView(this@MainActivity).apply {
            text = "⟳"
            gravity = Gravity.CENTER
            textSize = 19f
            setTextColor(Color.WHITE)
            setOnClickListener {
                refreshProxyPublicIp(account)
            }
        }, LinearLayout.LayoutParams(dp(38), dp(44)))
        addView(TextView(this@MainActivity).apply {
            text = account?.session?.channelExtra?.get("proxyPublicIp")
                ?.takeIf { it.isNotBlank() }
                ?: if (mode == "direct") currentLocalIpAddress() else "IP待检测"
            textSize = 13f
            gravity = Gravity.CENTER_VERTICAL
            setTextColor(Color.rgb(188, 224, 246))
            maxLines = 1
        }, LinearLayout.LayoutParams(dp(105), dp(44)))
    }

    private fun showProxyEndpointDialog(account: GameAccount, mode: String) {
        val session = account.session ?: return
        val hostInput = inputBox(session.channelExtra["proxyHost"].orEmpty(), 220).apply {
            hint = "代理主机，例如 192.168.1.5"
            inputType = InputType.TYPE_CLASS_TEXT
        }
        val portInput = inputBox(session.channelExtra["proxyPort"].orEmpty(), 120).apply {
            hint = "端口"
            inputType = InputType.TYPE_CLASS_NUMBER
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), 0)
            addView(designRow("代理主机：", hostInput))
            addView(designRow("代理端口：", portInput))
            addView(infoBox("该代理只用于“自研服务”发往游戏服的HTTP请求，不修改手机全局代理。"))
        }
        android.app.AlertDialog.Builder(this)
            .setTitle(if (mode == "socks") "设置SOCKS代理" else "设置HTTP代理")
            .setView(content)
            .setPositiveButton("保存", null)
            .setNegativeButton("取消") { _, _ -> showHome(HomeTab.CONFIG) }
            .create()
            .also { dialog ->
                dialog.setOnShowListener {
                    dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                        val host = hostInput.text.toString().trim()
                        val port = portInput.text.toString().toIntOrNull()
                        if (host.isBlank() || port == null || port !in 1..65535) {
                            showTopToast("请输入有效代理主机和1-65535端口")
                            return@setOnClickListener
                        }
                        val extras = session.channelExtra + mapOf(
                            "proxyMode" to mode,
                            "proxyType" to mode,
                            "proxyHost" to host,
                            "proxyPort" to port.toString(),
                            "proxyPublicIp" to ""
                        )
                        accountRepo.upsert(account.copy(session = session.copy(channelExtra = extras)))
                        logRepo.append(
                            "账号${account.id}网络路由已切换：${mode.uppercase()} $host:$port",
                            "proxy"
                        )
                        dialog.dismiss()
                        showHome(HomeTab.CONFIG)
                    }
                }
                dialog.show()
            }
    }

    private fun refreshProxyPublicIp(account: GameAccount?) {
        val current = account ?: run {
            showTopToast("请先选择账号")
            return
        }
        val session = current.session ?: run {
            showTopToast("当前账号尚未登录")
            return
        }
        val route = GameNetworkRoute.from(session.channelExtra)
        if (route.mode == GameProxyMode.INVALID) {
            showTopToast(route.error ?: "代理配置无效")
            return
        }
        showTopToast("正在检测当前出口IP…")
        Thread {
            val result = runCatching {
                val connection = route.open(URL("https://api.ipify.org")) as HttpURLConnection
                connection.connectTimeout = 8_000
                connection.readTimeout = 8_000
                connection.requestMethod = "GET"
                val code = connection.responseCode
                if (code !in 200..299) error("HTTP $code")
                connection.inputStream.bufferedReader().use { it.readText() }.trim()
                    .takeIf { it.matches(Regex("[0-9a-fA-F:.]+")) }
                    ?: error("出口IP响应无效")
            }
            runOnUiThread {
                result.onSuccess { ip ->
                    val latest = accountRepo.get(current.id) ?: current
                    val latestSession = latest.session ?: session
                    accountRepo.upsert(
                        latest.copy(
                            session = latestSession.copy(
                                channelExtra = latestSession.channelExtra +
                                    mapOf(
                                        "proxyPublicIp" to ip,
                                        "proxyCheckedAt" to System.currentTimeMillis().toString(),
                                        "proxyError" to ""
                                    )
                            )
                        )
                    )
                    logRepo.append("账号${current.id}出口IP检测成功：$ip", "proxy")
                    showTopToast("当前出口IP：$ip")
                    showHome(HomeTab.CONFIG)
                }.onFailure { error ->
                    logRepo.append("账号${current.id}出口IP检测失败：${error.message}", "proxy")
                    showTopToast("出口IP检测失败：${error.message}")
                }
            }
        }.start()
    }

    private fun currentLocalIpAddress(): String =
        runCatching {
            NetworkInterface.getNetworkInterfaces().toList()
                .asSequence()
                .flatMap { it.inetAddresses.toList().asSequence() }
                .firstOrNull { !it.isLoopbackAddress && it.hostAddress?.contains(':') == false }
                ?.hostAddress
                ?: "-"
        }.getOrDefault("-")


    private fun assistantAccountDisplay() =
        AssistantRealtimeAccountDisplayMapper.build(
            orderedAccountsForDisplay().map { account ->
                val session = account.session
                if (session?.sourceMode != 1) {
                    account
                } else {
                    val stats = dailySuccessStatsRepo.stats(account.id)
                    account.copy(
                        session = session.copy(
                            channelExtra = session.channelExtra + mapOf(
                                "brushYellowCount" to stats.brushYellowCount.toString(),
                                "dungeonCount" to stats.dungeonCount.toString()
                            )
                        )
                    )
                }
            },
            roleStateRepo.load()
        )

    private fun accountPickerLabel(): String = assistantAccountDisplay().pickerLabel

    private fun realProtocolAccounts(): List<GameAccount> =
        accountRepo.listAccounts().filter { it.session?.sourceMode == 1 }

    private fun orderedAccountsForDisplay(): List<GameAccount> {
        val all = accountRepo.listAccounts()
        val selectedId = selectedAccountId
        return if (selectedId == null) {
            all
        } else {
            all.sortedBy { if (it.id == selectedId) 0 else 1 }
        }
    }

    private fun selectedAccount(accounts: List<GameAccount> = realProtocolAccounts()): GameAccount? {
        if (accounts.isEmpty()) {
            selectedAccountId = null
            return null
        }
        val selected = selectedAccountId?.let { id -> accounts.firstOrNull { it.id == id } }
        if (selected != null) return selected
        return accounts.first().also { selectedAccountId = it.id }
    }

    private fun accountSpinner(accounts: List<GameAccount>, selected: GameAccount?): Spinner =
        Spinner(this).apply {
            isSaveEnabled = false
            val labels = if (accounts.isEmpty()) {
                listOf(AssistantRealtimeAccountDisplayMapper.EMPTY_ACCOUNT_LABEL)
            } else {
                accounts.map { account ->
                    val extra = account.session?.channelExtra.orEmpty()
                    val role = extra["roleName"]?.takeIf { it.isNotBlank() }
                        ?: account.monarchName
                        ?: account.displayName
                        ?: "#${account.id}"
                    val level = extra["level"]?.takeIf { it.isNotBlank() }?.let { " · Lv.$it" }.orEmpty()
                    "${account.username}@${account.serverName} · $role$level"
                }
            }
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, labels)
            val selectedIndex = accounts.indexOfFirst { it.id == selected?.id }.takeIf { it >= 0 } ?: 0
            setSelection(selectedIndex, false)
            if (accounts.isNotEmpty()) {
                onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                    override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                        val next = accounts.getOrNull(position) ?: return
                        if (selectedAccountId != next.id) {
                            selectedAccountId = next.id
                            showHome(HomeTab.CONFIG)
                        }
                    }

                    override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                }
            }
            background = roundedStroke(Color.WHITE, 8f, COLOR_BORDER)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(44)
            ).apply { setMargins(0, dp(8), 0, 0) }
        }

    private fun accountStateChip(account: GameAccount?): TextView {
        val (label, fg, bg) = accountStateStyle(account)
        return smallChip(label, fg, bg)
    }

    private fun accountStateStyle(account: GameAccount?): Triple<String, Int, Int> {
        if (account == null) return Triple("未开启", Color.rgb(255, 214, 120), Color.rgb(104, 82, 32))
        val state = account.loginState.uppercase()
        return when {
            account.enabled && (state.contains("OFFLINE") || state.contains("DROPPED") || state.contains("DISCONNECT")) ->
                Triple("掉线", Color.rgb(205, 209, 216), Color.rgb(82, 86, 94))
            account.enabled && state.contains("CHECK") ->
                Triple("检测中", Color.rgb(173, 220, 255), Color.rgb(44, 90, 128))
            account.enabled ->
                Triple("开启", Color.rgb(155, 232, 170), Color.rgb(43, 105, 58))
            else ->
                Triple("未开启", Color.rgb(255, 214, 120), Color.rgb(104, 82, 32))
        }
    }

    private fun startSelectedAccount() {
        val account = selectedAccount()
        if (account == null) {
            showTopToast("请先添加账号")
            return
        }
        val session = account.session
        val updated = account.copy(
            enabled = true,
            loginState = "REAL_PROTOCOL_ONLINE",
            session = session?.copy(channelExtra = session.channelExtra + mapOf("lastManualStartAt" to System.currentTimeMillis().toString()))
        )
        accountRepo.upsert(updated)
        val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
        if (decision.allowed) {
            AssistantForegroundService.start(this@MainActivity)
            logRepo.append("账号 ${account.id} 已启动：${account.username}@${account.serverName}", "account")
            showTopToast("账号启动成功")
        } else {
            accountRepo.setEnabled(account.id, false, "REAL_PROTOCOL_STOPPED")
            logRepo.append("账号 ${account.id} 启动失败：${decision.message}", "account")
            showTopToast(decision.message)
        }
        selectedAccountId = account.id
        showHome(HomeTab.CONFIG)
    }

    private fun stopSelectedAccount() {
        val account = selectedAccount()
        if (account == null) {
            showTopToast("请先添加账号")
            return
        }
        accountRepo.setEnabled(account.id, false, "REAL_PROTOCOL_STOPPED")
        logRepo.append("账号 ${account.id} 已关闭：${account.username}@${account.serverName}", "account")
        if (accountRepo.listAccounts().none { it.enabled && it.session?.sourceMode == 1 }) {
            AssistantForegroundService.stop(this@MainActivity)
        }
        showTopToast("账号已关闭")
        selectedAccountId = account.id
        showHome(HomeTab.CONFIG)
    }

    private fun deleteSelectedAccount() {
        val account = selectedAccount()
        if (account == null) {
            showTopToast("请先添加账号")
            return
        }
        val wasEnabled = account.enabled
        accountRepo.delete(account.id)
        configRepo.deleteAccountConfigs(account.id)
        val remain = realProtocolAccounts()
        selectedAccountId = remain.firstOrNull()?.id
        if (remain.isEmpty()) roleStateRepo.clear()
        if (wasEnabled && accountRepo.listAccounts().none { it.enabled && it.session?.sourceMode == 1 }) {
            AssistantForegroundService.stop(this@MainActivity)
        }
        logRepo.append("账号 ${account.id} 已删除：${account.username}@${account.serverName}", "account")
        showTopToast("账号已删除")
        showHome(HomeTab.CONFIG)
    }

    private fun showReadOnlyLogin(existingAccount: GameAccount? = null) {
        val root = pageRoot()
        val usernameInput = EditText(this).apply {
            hint = "账号"
            existingAccount?.username?.let(::setText)
            textSize = 15f
            setSingleLine(true)
            background = roundedStroke(Color.WHITE, 12f, COLOR_BORDER)
            setPadding(dp(14), 0, dp(14), 0)
            layoutParams = inputLp()
        }
        val passwordInput = EditText(this).apply {
            hint = "密码"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            textSize = 15f
            setSingleLine(true)
            background = roundedStroke(Color.WHITE, 12f, COLOR_BORDER)
            setPadding(dp(14), 0, dp(14), 0)
            layoutParams = inputLp()
        }
        val serverInput = EditText(this).apply {
            hint = "区服，例如：周年服351区(新服)"
            setText(existingAccount?.serverName ?: "周年服351区(新服)")
            textSize = 15f
            setSingleLine(true)
            background = roundedStroke(Color.WHITE, 12f, COLOR_BORDER)
            setPadding(dp(14), 0, dp(14), 0)
            layoutParams = inputLp()
        }
        root.addView(outlineButton("← 返回配置") { showHome(HomeTab.CONFIG) })
        root.addView(card().apply {
            addView(sectionTitle(if (existingAccount == null) "添加账号 / 同步角色" else "修改账号 / 重新同步"))
            addView(bodyText(
                if (existingAccount == null) {
                    "通过真实协议登录并同步角色、资源、将领和背包状态。密码只用于本次登录，不写入本地配置。"
                } else {
                    "已带入当前账号和区服。请输入密码重新登录；成功后更新该角色的真实 session 与实时数据，原有任务配置继续按角色ID保留。"
                }
            ))
            addView(usernameInput)
            addView(passwordInput)
            addView(serverInput)
            lateinit var loginButton: Button
            loginButton = primaryButton(if (existingAccount == null) "添加并同步角色状态" else "保存修改并重新同步") {
                val username = usernameInput.text?.toString()?.trim().orEmpty()
                val password = passwordInput.text?.toString().orEmpty()
                val server = serverInput.text?.toString()?.trim().orEmpty().ifBlank { "周年服351区(新服)" }
                if (username.isBlank() || password.isBlank()) {
                    Toast.makeText(this@MainActivity, "请输入账号和密码", Toast.LENGTH_SHORT).show()
                    return@primaryButton
                }
                loginButton.isEnabled = false
                loginButton.text = "正在登录并同步..."
                runReadOnlyProtocolLogin(username, password, server, loginButton, existingAccount)
            }
            addView(loginButton)
        })
        setTabbedPage(root, HomeTab.CONFIG)
    }

    private fun runReadOnlyProtocolLogin(
        username: String,
        password: String,
        server: String,
        loginButton: Button,
        existingAccount: GameAccount? = null
    ) {
        Thread {
            try {
                val result = RealGameProtocolClient().loginAndFetchState(username, password, server)
                val role = result.selectedRole
                val state = result.state
                val recoveredGeneralRecords = State8004GeneralEvidenceParser.recoverRecords(state.tailHex)
                val recoveredGeneralsJson = if (recoveredGeneralRecords.isNotEmpty()) {
                    JSONArray().apply {
                        recoveredGeneralRecords.forEach { record -> put(JSONObject(record)) }
                    }.toString()
                } else {
                    null
                }
                val generalSummary = if (recoveredGeneralRecords.isNotEmpty()) {
                    val names = recoveredGeneralRecords.mapNotNull { it["name"]?.takeIf { name -> name.isNotBlank() } }
                        .take(5)
                        .joinToString("、")
                    val suffix = if (names.isBlank()) "" else "：$names"
                    "已解析 ${recoveredGeneralRecords.size} / 上限 ${state.generalLimit}$suffix"
                } else {
                    "上限 ${state.generalLimit}（明细待继续解析 0x8004 后段）"
                }
                val recoveredStatusRecords = State8004StatusEvidenceParser.recoverRecords(state.payloadHex)
                val recoveredStatusJson = if (recoveredStatusRecords.isNotEmpty()) {
                    JSONArray().apply {
                        recoveredStatusRecords.forEach { record -> put(JSONObject(record)) }
                    }.toString()
                } else {
                    null
                }
                val recoveredArmyRows = State8004ArmyEvidenceParser.recover(state.payloadHex)
                val recoveredArmyJson = recoveredArmyRows.takeIf { it.isNotEmpty() }
                    ?.let(State8004ArmyEvidenceParser::toJson)
                val inventory = result.inventoryState
                val inventoryItemsJson = inventory?.let { inv ->
                    JSONArray().apply {
                        inv.items.forEach { item ->
                            put(
                                JSONObject()
                                    .put("id", item.itemId)
                                    .put("itemId", item.itemId)
                                    .put("name", item.name)
                                    .put("count", item.count)
                                    .put("type", item.typeLabel ?: "")
                                    .put("nameSource", item.nameSource)
                                    .put("source", inv.sourceOpcode)
                                    .put("rawTailHex", item.rawTailHex)
                            )
                        }
                    }.toString()
                }
                val inventorySummary = inventory?.let { inv ->
                    "已解析 ${inv.itemCount} / 容量 ${inv.capacity}（0x8104）"
                } ?: "待继续解析 0x1104/0x8104"
                val localState = LocalRoleState(
                    roleName = state.roleName,
                    remark = "${result.area.areaName} · ${result.area.serverKey}",
                    level = state.level.toString(),
                    exp = "声望 ${state.prestige} / ${state.prestigeNextThreshold}",
                    nation = role.country.ifBlank { role.title },
                    copper = "${state.copper}（+${state.copperPerHour}/小时）",
                    food = "${state.food}（+${state.foodPerHour}/小时）",
                    population = "${state.populationCurrent} / ${state.populationCap}",
                    resourcePoint = "${state.resourcePointCurrent} / ${state.resourcePointCap}",
                    generals = generalSummary,
                    troops = if (recoveredGeneralRecords.isNotEmpty()) "将领明细来自 0x8004 tail；军队编队仍需按编队配置/状态继续校准" else "待继续解析 0x8004 后段",
                    treasures = inventorySummary,
                    buffs = if (recoveredStatusRecords.isNotEmpty()) "已解析 ${recoveredStatusRecords.size} 条 0x8004 状态/政策文本" else "待继续解析 0x8004 后段",
                    source = "真实协议 ${state.sourceOpcode}；响应 ${result.responseOpcodes.joinToString()}",
                    syncedAt = result.syncedAt
                )
                val sessionExtra = mutableMapOf(
                    "userId" to result.userId,
                    "dm" to result.dm.toString(),
                    "serverUrl" to result.area.serverUrl,
                    "serverKey" to result.area.serverKey,
                    "gameHttp" to (result.area.serverUrl.trimEnd('/') + "/kingWapServer/HttpClient"),
                    "realActionNetworkAllowed" to "true",
                    "realActionSendReady" to "true",
                    "realActionScope" to "brush-yellow",
                    "realActionScopes" to "brush-yellow,mine,daily,inventory,general-maintenance,dungeon,lossless,raid,resource-conversion,internal-affairs",
                    "realActionBrushYellowOnly" to "true",
                    "accountWithSuffix" to (result.accountWithSuffix ?: ""),
                    "roleId" to state.roleId.toString(),
                    "roleName" to state.roleName,
                    "level" to state.level.toString(),
                    "nation" to role.country,
                    "title" to role.title,
                    "copper" to state.copper.toString(),
                    "food" to state.food.toString(),
                    "prestige" to state.prestige.toString(),
                    "copperPerHour" to state.copperPerHour.toString(),
                    "foodPerHour" to state.foodPerHour.toString(),
                    "populationCurrent" to state.populationCurrent.toString(),
                    "populationCap" to state.populationCap.toString(),
                    "fiefLimit" to state.fiefLimit.toString(),
                    "generalLimit" to state.generalLimit.toString(),
                    "resourcePointCurrent" to state.resourcePointCurrent.toString(),
                    "resourcePointCap" to state.resourcePointCap.toString(),
                    "state8004PayloadByteCount" to state.payloadByteCount.toString(),
                    "state8004ParsedHeadByteCount" to state.parsedHeadByteCount.toString(),
                    "state8004TailByteCount" to state.tailByteCount.toString(),
                    "state8004PayloadHex" to state.payloadHex,
                    "state8004TailHex" to state.tailHex,
                    "state8004TailUtf8Preview" to state.tailUtf8Preview,
                    "roleStateJson" to JSONObject()
                        .put("roleId", state.roleId)
                        .put("roleName", state.roleName)
                        .put("level", state.level)
                        .put("nation", role.country)
                        .put("title", role.title)
                        .put("prestige", state.prestige)
                        .put("populationCurrent", state.populationCurrent)
                        .put("populationCap", state.populationCap)
                        .put("fiefLimit", state.fiefLimit)
                        .put("generalLimit", state.generalLimit)
                        .put("resourcePointCurrent", state.resourcePointCurrent)
                        .put("resourcePointCap", state.resourcePointCap)
                        .put("sourceOpcode", state.sourceOpcode)
                        .put("state8004PayloadByteCount", state.payloadByteCount)
                        .put("state8004ParsedHeadByteCount", state.parsedHeadByteCount)
                        .put("state8004TailByteCount", state.tailByteCount)
                        .toString(),
                    "resourceStateJson" to JSONObject()
                        .put("copper", state.copper)
                        .put("food", state.food)
                        .put("prestige", state.prestige)
                        .put("copperPerHour", state.copperPerHour)
                        .put("foodPerHour", state.foodPerHour)
                        .put("populationCurrent", state.populationCurrent)
                        .put("populationCap", state.populationCap)
                        .put("resourcePointCurrent", state.resourcePointCurrent)
                        .put("resourcePointCap", state.resourcePointCap)
                        .toString(),
                    "sourceOpcode" to state.sourceOpcode,
                    "liveStateRefreshEnabled" to "true",
                    "syncedAt" to result.syncedAt
                )
                if (recoveredGeneralsJson != null) {
                    sessionExtra["generalsJson"] = recoveredGeneralsJson
                    sessionExtra["state8004GeneralRecordCount"] = recoveredGeneralRecords.size.toString()
                }
                if (recoveredStatusJson != null) {
                    sessionExtra["statusJson"] = recoveredStatusJson
                    sessionExtra["state8004StatusRecordCount"] = recoveredStatusRecords.size.toString()
                }
                if (recoveredArmyJson != null) {
                    sessionExtra["armyJson"] = recoveredArmyJson
                    sessionExtra["armySource"] = "live/0x8004-compact-army"
                    sessionExtra["armyRecordCount"] = recoveredArmyRows.size.toString()
                }
                if (inventory != null && inventoryItemsJson != null) {
                    sessionExtra["inventoryJson"] = inventoryItemsJson
                    sessionExtra["inventoryCapacity"] = inventory.capacity.toString()
                    sessionExtra["inventoryItemCount"] = inventory.itemCount.toString()
                    sessionExtra["inventorySourceOpcode"] = inventory.sourceOpcode
                    sessionExtra["inventoryPayloadByteCount"] = inventory.payloadByteCount.toString()
                    sessionExtra["inventoryParsedItemByteCount"] = inventory.parsedItemByteCount.toString()
                    sessionExtra["inventoryPayloadHex"] = inventory.payloadHex
                    sessionExtra["inventoryTailHex"] = inventory.tailHex
                }
                result.dailyActivityState?.let { activity ->
                    sessionExtra["dailyActivityJson"] = activity.toJson()
                    sessionExtra["dailyActivitySourceOpcode"] = activity.sourceOpcode
                    sessionExtra["dailyActivityPayloadByteCount"] = activity.payloadByteCount.toString()
                    activity.treasureOccupied?.let { treasure ->
                        treasure.progress?.let { sessionExtra["treasureProgress"] = it }
                        treasure.current?.let { sessionExtra["treasureOccupied"] = it.toString() }
                        treasure.target?.let { sessionExtra["treasureLimit"] = it.toString() }
                        sessionExtra["treasureText"] = treasure.text
                    }
                }
                val account = GameAccount(
                    id = state.roleId,
                    displayName = state.roleName,
                    username = result.username,
                    encryptedPassword = null,
                    serverName = result.area.areaName,
                    serverId = result.area.serverKey,
                    gameVersion = GameVersion.TENCENT_CLASSIC,
                    channel = Channel.QQ,
                    session = GameSession(
                        accountId = state.roleId,
                        tokenCiphertext = result.session,
                        expiresAtMillis = null,
                        channelExtra = sessionExtra,
                        sourceMode = 1
                    ),
                    enabled = existingAccount?.takeIf { it.id == state.roleId }?.enabled ?: false,
                    monarchName = state.roleName,
                    nation = role.country,
                    loginState = if (existingAccount?.takeIf { it.id == state.roleId }?.enabled == true) {
                        "REAL_PROTOCOL_ONLINE"
                    } else {
                        "REAL_PROTOCOL_STOPPED"
                    },
                    gameAuthSignPlaceholder = "empty-signature-verified",
                    antiBanIpEnabled = false
                )
                mainHandler.post {
                    accountRepo.upsert(account)
                    roleStateRepo.save(localState)
                    selectedAccountId = account.id
                    logRepo.append("真实协议登录成功：${state.roleName} Lv.${state.level} ${result.area.areaName}", "real-protocol")
                    if (existingAccount != null && existingAccount.id != account.id) {
                        logRepo.append(
                            "修改账号返回了不同角色ID：原=${existingAccount.id} 新=${account.id}；为避免误删配置，原账号仍保留",
                            "account"
                        )
                    }
                    showTopToast(if (existingAccount == null) "添加账号成功" else "账号修改并同步成功")
                    showHome(HomeTab.CONFIG)
                }
            } catch (t: Throwable) {
                mainHandler.post {
                    logRepo.append("真实协议登录失败：${t.message}", "real-protocol")
                    loginButton.isEnabled = true
                    loginButton.text = if (existingAccount == null) "添加并同步角色状态" else "保存修改并重新同步"
                    Toast.makeText(this@MainActivity, "登录失败：${t.message}", Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    private fun configCategoryTabs(active: ConfigCategory): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER
        background = rounded(Color.WHITE, 0f)
        elevation = dp(2).toFloat()
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(34)
        ).apply { setMargins(0, 0, 0, dp(6)) }
        ConfigCategory.values().forEach { category ->
            addView(TextView(this@MainActivity).apply {
                text = category.title
                gravity = Gravity.CENTER
                textSize = 16f
                typeface = if (category == active) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
                setTextColor(if (category == active) COLOR_TEXT else Color.rgb(55, 154, 255))
                background = if (category == active) {
                    roundedStroke(Color.WHITE, 0f, Color.rgb(55, 154, 255))
                } else {
                    rounded(Color.WHITE, 0f)
                }
                setOnClickListener {
                    activeConfigCategory = category
                    showHome(HomeTab.CONFIG)
                }
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f))
        }
    }

    private fun configWorkbenchCard(category: ConfigCategory, modules: List<ScreenSpec>): LinearLayout = card().apply {
        setPadding(dp(8), dp(8), dp(8), dp(8))
        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            val navItems = configNavItems(category)
            if (navItems.size > 1) {
                addView(configSideMenu(category), LinearLayout.LayoutParams(dp(64), ViewGroup.LayoutParams.MATCH_PARENT))
            }
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                background = roundedStroke(Color.rgb(250, 250, 250), 2f, Color.rgb(198, 198, 198))
                setPadding(dp(6), dp(6), dp(6), dp(6))
                minimumHeight = dp(280)
                addView(configActiveContent(category, modules))
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                if (navItems.size > 1) setMargins(dp(6), 0, 0, 0)
            })
        })
    }

    private fun configSideMenu(category: ConfigCategory): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        background = roundedStroke(Color.rgb(250, 250, 250), 2f, Color.rgb(198, 198, 198))
        setPadding(dp(8), dp(8), dp(8), dp(8))
        val active = activeNavItem(category).label
        configNavItems(category).forEach { item -> addView(sidePill(item.label, item.label == active) {
            activeSideByCategory[category] = item.label
            showHome(HomeTab.CONFIG)
        }) }
    }

    private fun configActiveContent(category: ConfigCategory, modules: List<ScreenSpec>): LinearLayout {
        val item = activeNavItem(category)
        val spec = item.featureId?.let { id -> modules.firstOrNull { it.featureId == id } }
        if (spec != null) {
            val rendered = ScreenSpecRenderer(this).renderEmbedded(spec, configRepo.loadFeatureConfig(activeAccountId(), spec.featureId)) { action ->
                Toast.makeText(this, "真实执行接口未启用：$action", Toast.LENGTH_SHORT).show()
            }
            activeRenderedScreen = rendered
            return rendered.root
        }
        activeRenderedScreen = null
        return when (item.custom) {
            "role" -> roleInfoPanel()
            "hero" -> roleHeroPanel()
            "troop" -> roleTroopPanel()
            "treasure" -> roleTreasurePanel()
            "status" -> roleStatusPanel()
            "tasks" -> roleTaskPanel()
            "common_main" -> commonMainPanel()
            "common_daily" -> commonDailyPanel()
            "common_items" -> commonItemsPanel()
            "common_chain_items" -> commonChainItemsPanel()
            "common_alarm" -> commonAlarmPanel()
            "military_formation" -> formationPanel()
            "military_loot" -> expeditionPanel("掠夺")
            "military_city" -> cityCapturePanel()
            "military_lossless" -> losslessPanel()
            "military_dungeon" -> dungeonLikePanel()
            "military_escort" -> escortPanel()
            "military_treasure" -> treasureHuntPanel()
            "shua_huang_design" -> shuaHuangPanel()
            "war_info" -> warInfoPanel()
            "nation_info" -> nationInfoPanel()
            "mining_auto" -> miningAutoPanel()
            "six_ministries" -> sixMinistriesPanel()
            else -> automationCategoryPanel(category, modules.filter { moduleBelongsTo(category, it) })
        }
    }

    private fun roleAssetPanel(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        val display = assistantAccountDisplay()
        addView(panelHeader("角色状态", "只读展示接口实时返回的角色资产；没有 sourceMode=1 真实协议 session 时不展示账号数据。当前不会执行任何真实动作。"))
        addView(primaryButton("真实协议登录 / 同步角色") { showReadOnlyLogin() })
        if (!display.hasRealtimeAccount || display.roleRows.isEmpty()) {
            addView(emptyRealtimeText(AssistantRealtimeAccountDisplayMapper.EMPTY_ACCOUNT_LABEL))
        } else {
            addView(dataSection("角色", display.roleRows))
            if (display.heroRows.isNotEmpty()) {
                addView(dataSection("英雄 / 将领", listOf("将领明细" to "接口返回 ${display.heroRows.size} 条")))
            }
            if (display.formationRows.isNotEmpty()) {
                val label = if (display.troopRowsDerivedFromGenerals) "将领配兵" else "编队明细"
                val source = if (display.troopRowsDerivedFromGenerals) "0x8004 JiangLing + Lo/a.S5" else "接口返回 formationsJson"
                addView(dataSection("军队 / 配兵", listOf(label to "$source ${display.formationRows.size} 条")))
            }
            if (display.treasureRows.isNotEmpty()) {
                addView(dataSection("宝物 / 背包", listOf("道具明细" to "0x1104/0x8104 ${display.treasureRows.size} 条")))
            }
        }
    }

    private fun automationCategoryPanel(category: ConfigCategory, categoryModules: List<ScreenSpec>): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        addView(panelHeader(category.title, categoryDescription(category)))
        flowSteps(category).forEach { step -> addView(flowStep(step)) }
        addView(TextView(this@MainActivity).apply {
            text = "相关配置入口"
            textSize = 16f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(COLOR_TEXT)
            setPadding(dp(6), dp(12), 0, dp(4))
        })
        if (categoryModules.isEmpty()) {
            addView(emptyConfigRow("该业务目前没有独立配置页，后续从原 APK 逻辑继续补齐。"))
        } else {
            categoryModules.forEach { spec -> addView(configModuleRow(spec)) }
        }
    }

    private fun configSavePanel(category: ConfigCategory): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.TOP
        setPadding(dp(16), dp(14), dp(12), dp(14))
        background = rounded(Color.BLACK, 2f)
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(180)
        ).apply { setMargins(dp(8), 0, dp(8), dp(14)) }

        val recentLogs = logRepo.recent(10)
        addView(TextView(this@MainActivity).apply {
            text = if (recentLogs.isEmpty()) {
                "暂无运行日志"
            } else {
                recentLogs.asReversed().joinToString("\n") {
                    "[${formatLogTime(it.timeMillis)}] ${it.message}"
                }
            }
            textSize = 12.5f
            setTextColor(Color.rgb(74, 163, 255))
            typeface = Typeface.MONOSPACE
            maxLines = 9
            ellipsize = TextUtils.TruncateAt.END
            setOnClickListener { showHome(HomeTab.LOGS) }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply {
            setMargins(0, 0, dp(10), 0)
        })

        addView(TextView(this@MainActivity).apply {
            text = "保存设置"
            gravity = Gravity.CENTER
            textSize = 17f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(79, 169, 245), 6f)
            setOnClickListener { saveActiveConfig(category) }
        }, LinearLayout.LayoutParams(dp(118), dp(48)))
    }

    private fun configModuleRow(spec: ScreenSpec): TextView = TextView(this).apply {
        text = spec.featureNameZh
        textSize = 16f
        gravity = Gravity.CENTER_VERTICAL
        setTextColor(Color.rgb(92, 92, 92))
        background = roundedStroke(Color.rgb(252, 252, 252), 0f, Color.rgb(210, 210, 210))
        setPadding(dp(14), 0, dp(8), 0)
        setOnClickListener { showScreen(spec) }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(48)
        ).apply { setMargins(0, dp(6), 0, 0) }
    }

    private fun emptyConfigRow(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 14f
        setTextColor(COLOR_SUBTEXT)
        background = roundedStroke(Color.rgb(252, 252, 252), 0f, Color.rgb(210, 210, 210))
        setPadding(dp(12), dp(12), dp(12), dp(12))
    }

    private fun sidePill(label: String, active: Boolean, onClick: () -> Unit): TextView = TextView(this).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 14f
        typeface = if (active) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
        setTextColor(if (active) Color.rgb(55, 154, 255) else Color.rgb(150, 150, 150))
        background = if (active) rounded(Color.rgb(46, 96, 145), 6f) else roundedStroke(Color.WHITE, 6f, Color.rgb(215, 215, 215))
        setOnClickListener { onClick() }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(26)
        ).apply { setMargins(0, 0, 0, dp(6)) }
    }

    private fun activeNavItem(category: ConfigCategory): ConfigNavItem {
        val items = configNavItems(category)
        val saved = activeSideByCategory[category]
        return items.firstOrNull { it.label == saved } ?: items.first()
    }

    private fun configNavItems(category: ConfigCategory): List<ConfigNavItem> = when (category) {
        ConfigCategory.ROLE -> listOf(
            ConfigNavItem("角色", custom = "role"),
            ConfigNavItem("英雄", custom = "hero"),
            ConfigNavItem("军队", custom = "troop"),
            ConfigNavItem("宝物", custom = "treasure"),
            ConfigNavItem("状态", custom = "status"),
            ConfigNavItem("任务", custom = "tasks")
        )
        ConfigCategory.MILITARY -> listOf(
            ConfigNavItem("配兵", custom = "military_formation"),
            ConfigNavItem("掠夺", custom = "military_loot"),
            ConfigNavItem("抢城", custom = "military_city"),
            ConfigNavItem("无损", custom = "military_lossless"),
            ConfigNavItem("副本", custom = "military_dungeon"),
            ConfigNavItem("押镖", custom = "military_escort"),
            ConfigNavItem("寻宝", custom = "military_treasure")
        )
        ConfigCategory.SHUA_HUANG -> listOf(ConfigNavItem("刷黄", custom = "shua_huang_design"))
        ConfigCategory.WAR_INFO -> listOf(ConfigNavItem("军情", custom = "war_info"), ConfigNavItem("国家", custom = "nation_info"))
        ConfigCategory.MINING -> listOf(ConfigNavItem("打矿", custom = "mining_auto"))
        ConfigCategory.MINISTRY -> listOf(ConfigNavItem("六部", custom = "six_ministries"))
        ConfigCategory.COMMON -> listOf(
            ConfigNavItem("常用", custom = "common_main"),
            ConfigNavItem("日常", custom = "common_daily"),
            ConfigNavItem("主号物品", custom = "common_items"),
            ConfigNavItem("连体物品", custom = "common_chain_items"),
            ConfigNavItem("警报", custom = "common_alarm")
        )
    }


    private fun roleHeroPanel(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(4))
        background = roundedStroke(Color.rgb(250, 250, 250), 0f, Color.rgb(198, 198, 198))
        val rows = assistantAccountDisplay().heroRows
        if (rows.isEmpty()) {
            addView(emptyRealtimeText("暂无实时将领明细；请先同步接口数据，或等待 0x8004/将领接口解析补齐。"))
        } else {
            addView(HorizontalScrollView(this@MainActivity).apply {
                isHorizontalScrollBarEnabled = true
                isFillViewport = true
                addView(compactTable(
                    headers = listOf("将", "态", "封地", "类", "级", "体", "忠", "统/兵", "兵种"),
                    rows = rows,
                    weights = listOf(1.15f, 0.66f, 1.35f, 0.82f, 0.62f, 1.15f, 1.05f, 1.25f, 1.1f),
                    rowHeightDp = 24,
                    headerHeightDp = 30,
                    textSp = 14f,
                    widthDp = 720
                ))
            }, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ))
        }
    }

    private fun roleTroopPanel(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(4))
        background = roundedStroke(Color.rgb(250, 250, 250), 0f, Color.rgb(198, 198, 198))
        val display = assistantAccountDisplay()
        if (display.armyRows.isNotEmpty()) {
            addView(compactTable(
                headers = listOf("兵种", "闲兵数量", "伤兵数量", "封地"),
                rows = display.armyRows,
                weights = listOf(1.3f, 1.05f, 1.05f, 1.3f),
                rowHeightDp = 24,
                headerHeightDp = 30,
                textSp = 14f
            ))
            return@apply
        }
        val rows = display.formationRows
        if (rows.isEmpty()) {
            addView(emptyRealtimeText("暂无实时军队/配兵数据；未解析到接口返回的 formationsJson 或 0x8004 将领配兵。"))
        } else {
            val derived = display.troopRowsDerivedFromGenerals
            addView(infoBox("暂未取得闲兵/伤兵接口数据，以下显示已确认的将领配兵。"))
            addView(compactTable(
                headers = if (derived) listOf("将领", "状态", "兵力", "兵种") else listOf("编队", "将领ID", "状态", "兵力"),
                rows = rows,
                weights = if (derived) listOf(1.2f, 0.85f, 1.05f, 1.1f) else listOf(1.4f, 1.2f, 1.0f, 1.0f),
                rowHeightDp = 24,
                headerHeightDp = 30,
                textSp = 15f
            ))
        }
    }

    private fun roleTreasurePanel(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(4))
        background = roundedStroke(Color.rgb(250, 250, 250), 0f, Color.rgb(198, 198, 198))
        val rows = assistantAccountDisplay().treasureRows
        if (rows.isEmpty()) {
            addView(emptyRealtimeText("暂无实时宝物/背包数据；不会展示模板数量。"))
        } else {
            val countText = TextView(this@MainActivity).apply {
                textSize = 13f
                gravity = Gravity.CENTER_VERTICAL or Gravity.RIGHT
                setTextColor(COLOR_SUBTEXT)
            }
            val resultContainer = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
            }
            fun renderResults(query: String) {
                treasureSearchQuery = query
                val result = TreasureBrowserPolicy.filter(rows, query)
                countText.text = result.countText
                resultContainer.removeAllViews()
                if (result.rows.isEmpty()) {
                    resultContainer.addView(emptyRealtimeText("没有找到匹配的宝物"))
                } else {
                    resultContainer.addView(compactTable(
                        headers = listOf("名称", "数量"),
                        rows = result.rows,
                        weights = listOf(2.4f, 0.8f),
                        rowHeightDp = 26,
                        headerHeightDp = 32,
                        textSp = 15f
                    ))
                }
            }
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                addView(EditText(this@MainActivity).apply {
                    hint = "搜索宝物名称"
                    setText(treasureSearchQuery)
                    setSingleLine(true)
                    textSize = 15f
                    background = roundedStroke(Color.WHITE, 8f, COLOR_BORDER)
                    setPadding(dp(12), 0, dp(12), 0)
                    addTextChangedListener(object : TextWatcher {
                        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                            renderResults(s?.toString().orEmpty())
                        }
                        override fun afterTextChanged(s: Editable?) = Unit
                    })
                }, LinearLayout.LayoutParams(0, dp(44), 1.45f))
                addView(countText, LinearLayout.LayoutParams(0, dp(44), 0.8f).apply {
                    setMargins(dp(8), 0, 0, 0)
                })
            })
            addView(resultContainer)
            renderResults(treasureSearchQuery)
        }
    }

    private fun compactTable(
        headers: List<String>,
        rows: List<List<String>>,
        weights: List<Float>,
        rowHeightDp: Int,
        headerHeightDp: Int,
        textSp: Float,
        widthDp: Int? = null
    ): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        widthDp?.let { layoutParams = LinearLayout.LayoutParams(dp(it), ViewGroup.LayoutParams.WRAP_CONTENT) }
        addView(compactTableRow(headers, weights, true, headerHeightDp, textSp + 1f))
        rows.forEach { addView(compactTableRow(it, weights, false, rowHeightDp, textSp)) }
    }

    private fun compactTableRow(values: List<String>, weights: List<Float>, header: Boolean, heightDp: Int, textSp: Float): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        values.forEachIndexed { index, value ->
            addView(TextView(this@MainActivity).apply {
                text = value
                gravity = Gravity.CENTER
                textSize = textSp
                typeface = if (header) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
                setTextColor(COLOR_TEXT)
                background = roundedStroke(if (header) Color.WHITE else Color.rgb(252, 252, 252), 0f, Color.rgb(238, 238, 238))
                setSingleLine(true)
                ellipsize = TextUtils.TruncateAt.END
                includeFontPadding = false
            }, LinearLayout.LayoutParams(0, dp(heightDp), weights.getOrElse(index) { 1f }))
        }
    }

    private fun roleInfoPanel(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(4))
        background = roundedStroke(Color.rgb(250, 250, 250), 0f, Color.rgb(198, 198, 198))
        val display = assistantAccountDisplay()
        if (!display.hasRealtimeAccount || display.roleRows.isEmpty()) {
            addView(emptyRealtimeText(AssistantRealtimeAccountDisplayMapper.EMPTY_ACCOUNT_LABEL))
            addView(primaryButton("真实协议登录 / 同步角色") { showReadOnlyLogin() })
        } else {
            display.roleRows.forEachIndexed { index, row ->
                addView(roleTableRow(row.first, textValue = row.second, first = index == 0))
            }
        }
    }

    private fun roleTableRow(label: String, textValue: String? = null, editHint: String? = null, first: Boolean = false): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        addView(TextView(this@MainActivity).apply {
            text = label
            textSize = 15f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(95, 95, 95))
            background = roundedStroke(Color.rgb(248, 248, 248), 0f, Color.rgb(205, 205, 205))
        }, LinearLayout.LayoutParams(0, dp(if (first) 25 else 24), 1.05f))
        if (editHint != null) {
            addView(EditText(this@MainActivity).apply {
                hint = editHint
                textSize = 15f
                gravity = Gravity.CENTER
                setSingleLine(true)
                setTextColor(Color.rgb(45, 45, 45))
                setHintTextColor(Color.rgb(125, 125, 125))
                background = roundedStroke(Color.WHITE, 0f, Color.rgb(145, 145, 145))
                setPadding(0, 0, 0, 0)
            }, LinearLayout.LayoutParams(0, dp(24), 2.05f).apply { setMargins(dp(8), dp(4), dp(4), dp(4)) })
        } else {
            addView(TextView(this@MainActivity).apply {
                text = textValue.orEmpty()
                textSize = 15f
                gravity = Gravity.CENTER
                setTextColor(Color.rgb(45, 45, 45))
                background = roundedStroke(Color.rgb(248, 248, 248), 0f, Color.rgb(205, 205, 205))
            }, LinearLayout.LayoutParams(0, dp(if (first) 25 else 24), 2.05f))
        }
    }

    private fun normalizeTemplateNumber(value: String?): String? {
        val raw = value?.substringBefore('（')?.trim()?.ifBlank { return null } ?: return null
        val n = raw.toLongOrNull() ?: return raw
        return if (n >= 10_000) "${n / 10_000}万${n % 10_000}" else n.toString()
    }


    private fun roleStatusPanel(): LinearLayout = designFormPanel().apply {
        val rows = assistantAccountDisplay().statusRows
        if (rows.isEmpty()) {
            addView(emptyRealtimeText("暂无实时增益/状态数据；不会展示模板状态。"))
        } else {
            addView(compactTable(
                headers = listOf("名称", "剩余时间"),
                rows = rows,
                weights = listOf(2.45f, 1f),
                rowHeightDp = 30,
                headerHeightDp = 32,
                textSp = 12f
            ))
        }
    }

    /**
     * Mirrors the desktop “角色 → 任务” page using the same saved configuration that feeds the
     * foreground scheduler.  This is deliberately a status/control surface: it does not invent
     * task completion data and it never runs a task merely because the page was opened.
     */
    private fun roleTaskPanel(): LinearLayout = designFormPanel().apply {
        val account = selectedAccount()
        if (account == null) {
            addView(emptyRealtimeText("请先添加并同步账号，再查看任务栈。"))
            addView(primaryButton("添加账号 / 同步角色") { showReadOnlyLogin() })
            return@apply
        }

        val plan = SavedConfigTaskPlanFactory.plan(
            accountId = account.id,
            exportJson = configRepo.exportAll(),
            account = account
        )
        val taskTypes = plan.tasks.map { it.type }.distinct()
        val running = account.enabled
        val nowMillis = System.currentTimeMillis()
        val runtimeByType = taskRuntimeStatusRepo.list(account.id).associateBy { it.type }

        addView(taskPanelTitle("任务栈"))
        if (!running) {
            addView(primaryButton("开始执行已保存任务") { startSelectedAccount() })
        }
        val stackRows = taskTypes.mapIndexed { index, type ->
            listOf(
                (index + 1).toString(),
                taskTypeLabel(type),
                runtimeByType[type]?.displayText(nowMillis)
                    ?: if (running) "等待后台首次调度" else "等待启动"
            )
        }
        if (stackRows.isEmpty()) {
            addView(emptyRealtimeText("当前没有已保存任务。请先在对应页面配置并保存。"))
        } else {
            addView(simpleTablePanel(listOf("序号", "任务", "状态"), stackRows))
        }

        addView(taskPanelTitle("常驻任务"))
        val resident = listOf(
            "副本" to setOf(TaskType.DUNGEON),
            "刷黄" to setOf(TaskType.SHUA_HUANG),
            "打矿" to setOf(TaskType.MINE_SEARCH, TaskType.AUTO_MINING),
            "掠夺" to setOf(TaskType.AUTO_LOOT),
            "抢城" to emptySet(),
            "无损" to setOf(TaskType.LOSSLESS),
            "押镖" to emptySet(),
            "寻宝" to setOf(TaskType.TREASURE_SEARCH),
            "六部种菜" to setOf(TaskType.MINISTRY)
        )
        addView(simpleTablePanel(
            listOf("任务", "配置", "运行状态"),
            resident.map { (label, acceptedTypes) ->
                val configured = acceptedTypes.any(taskTypes::contains)
                val runtime = acceptedTypes.mapNotNull(runtimeByType::get)
                    .maxByOrNull { it.updatedAtMillis }
                listOf(
                    label,
                    if (configured) "已配置" else "未配置",
                    when {
                        !configured -> "未运行"
                        runtime != null -> runtime.displayText(nowMillis)
                        running -> "等待后台首次调度"
                        else -> "未运行"
                    }
                )
            }
        ))

        addView(taskPanelTitle("每日任务"))
        val dailyConfigured = TaskType.DAILY in taskTypes
        addView(simpleTablePanel(
            listOf("任务", "今日状态"),
            listOf(
                listOf(
                    "一键日常",
                    when {
                        !dailyConfigured -> "未配置"
                        runtimeByType[TaskType.DAILY] != null ->
                            runtimeByType.getValue(TaskType.DAILY).displayText(nowMillis)
                        running -> "等待后台首次调度"
                        else -> "未运行"
                    }
                )
            )
        ))

        addView(outlineButton("刷新任务运行状态") { showHome(HomeTab.CONFIG) })
        val latest = logRepo.recent(1).firstOrNull()
        val latestRuntime = runtimeByType.values.maxByOrNull { it.updatedAtMillis }
        addView(infoBox(
            buildString {
                if (latestRuntime != null) {
                    append("最近任务：${taskTypeLabel(latestRuntime.type)} · ")
                    append(latestRuntime.displayText(nowMillis))
                    append("\n${formatLogTime(latestRuntime.updatedAtMillis)} ${latestRuntime.message}")
                } else {
                    append("任务状态来自本机已保存配置；暂无持久化运行回报。")
                }
                if (latest != null) {
                    append("\n最近日志：${formatLogTime(latest.timeMillis)} [${latest.tag}] ${latest.message}")
                }
            }
        ))
    }

    private fun taskPanelTitle(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 17f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(COLOR_TEXT)
        setPadding(dp(4), dp(12), dp(4), dp(6))
    }

    private fun taskTypeLabel(type: TaskType): String = when (type) {
        TaskType.SHUA_HUANG -> "刷黄"
        TaskType.MINE_SEARCH -> "找矿"
        TaskType.AUTO_MINING -> "打矿"
        TaskType.DAILY -> "一键日常"
        TaskType.DAILY_DONATE -> "自动捐献"
        TaskType.DAILY_SALARY -> "国家俸禄"
        TaskType.DAILY_NATIONAL_COLLECT -> "国家征收"
        TaskType.DAILY_CITY_LORD_COLLECT -> "城主征收"
        TaskType.DAILY_GENERAL_VISIT -> "名将拜访"
        TaskType.GENERAL -> "将领维护"
        TaskType.FORMATION -> "配兵"
        TaskType.INTERNAL -> "自动内政"
        TaskType.MINISTRY -> "六部种菜"
        TaskType.DUNGEON -> "副本"
        TaskType.LOSSLESS -> "无损"
        TaskType.INVENTORY -> "物品整理"
        TaskType.VIP -> "VIP功能"
        TaskType.RESOURCE_POINT_SEND_GENERAL -> "资源点送将"
        TaskType.SURRENDER_RELEASE -> "劝降/释放"
        TaskType.AUTO_LOOT -> "掠夺"
        TaskType.ALARM_WITHDRAW -> "警报/撤防"
        TaskType.BULK_TOOLS -> "批量工具"
        TaskType.OPEN_SERVER_QUERY -> "开服查询"
        TaskType.CITY_SEARCH -> "抢城找城"
        TaskType.TREASURE_SEARCH -> "寻宝"
    }

    private fun generalSpinner(selectedId: Long?, includePlaceholder: Boolean = false): Spinner {
        val realChoices = realGeneralChoices()
        val choices = when {
            realChoices.isEmpty() -> listOf(0L to "请先添加/登录账号")
            includePlaceholder -> listOf(0L to "请选择") + realChoices
            else -> realChoices
        }
        return Spinner(this).apply {
            isSaveEnabled = false
            tag = choices
            adapter = compactSpinnerAdapter(choices.map { it.second })
            val selectedIndex = choices.indexOfFirst { it.first == selectedId }.takeIf { it >= 0 } ?: 0
            setSelection(selectedIndex)
            layoutParams = LinearLayout.LayoutParams(0, dp(42), 1f).apply { setMargins(dp(4), dp(3), dp(4), dp(3)) }
        }
    }

    private fun soldierTypeSpinner(selected: String): Spinner {
        val types = soldierTypeOptions()
        return Spinner(this).apply {
            isSaveEnabled = false
            adapter = compactSpinnerAdapter(types)
            setSelection(types.indexOf(selected).takeIf { it >= 0 } ?: 0)
            layoutParams = LinearLayout.LayoutParams(0, dp(42), 1f).apply { setMargins(dp(4), dp(3), dp(4), dp(3)) }
        }
    }

    private fun soldierTypeOptions(): List<String> =
        listOf("民兵", "轻步兵", "重步兵", "近卫兵", "弓兵", "弩兵", "强弩兵", "轻骑兵", "弩骑兵", "重骑兵", "铁骑兵", "弩车", "冲城车", "投石车")

    private fun shuaHuangLevelOptions(): List<String> =
        (1..10).map { "${it}级" }

    private fun shuaHuangDropOptions(): List<String> =
        listOf("宝物", "资源", "装备", "宝箱")

    private fun normalizeShuaHuangDropValue(drop: String?): String {
        val text = drop?.trim().orEmpty()
        if (text in shuaHuangDropOptions()) return text
        if (text in setOf("铜钱", "粮食", "粮草", "资源类")) return "资源"
        return ""
    }

    private fun normalizeShuaHuangDrops(raw: String?, fallback: Set<String> = setOf("装备")): Set<String> {
        val text = raw?.trim().orEmpty()
        if (text.isBlank()) return fallback
        if (text == "不限") return shuaHuangDropOptions().toSet()
        val out = text.split(',', '，', ';', '；', '|', ' ')
            .mapNotNull { normalizeShuaHuangDropValue(it).takeIf { value -> value.isNotBlank() } }
            .toCollection(linkedSetOf())
        return out.ifEmpty { fallback }
    }

    private fun normalizeShuaHuangDrops(arr: JSONArray?, fallback: Set<String> = setOf("装备")): Set<String> {
        if (arr == null) return fallback
        val out = linkedSetOf<String>()
        for (i in 0 until arr.length()) {
            normalizeShuaHuangDropValue(arr.optString(i)).takeIf { it.isNotBlank() }?.let(out::add)
        }
        return out
    }

    private fun compositionDigitOptions(): List<String> =
        (0..5).map { it.toString() }

    private fun compactSpinnerAdapter(items: List<String>): ArrayAdapter<String> =
        object : ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, items) {
            override fun getView(position: Int, convertView: View?, parent: ViewGroup): View =
                spinnerTextView(getItem(position).orEmpty(), compact = true)

            override fun getDropDownView(position: Int, convertView: View?, parent: ViewGroup): View =
                spinnerTextView(getItem(position).orEmpty(), compact = false)
        }

    private fun spinnerTextView(value: String, compact: Boolean): TextView =
        TextView(this).apply {
            text = value
            textSize = if (compact) 15f else 18f
            gravity = if (compact) Gravity.CENTER else Gravity.CENTER_VERTICAL
            setSingleLine(true)
            ellipsize = TextUtils.TruncateAt.END
            includeFontPadding = false
            setTextColor(COLOR_TEXT)
            setPadding(dp(if (compact) 4 else 16), 0, dp(if (compact) 4 else 16), 0)
            minHeight = dp(if (compact) 42 else 52)
            background = ColorDrawable(Color.WHITE)
        }

    private fun stringSpinner(options: List<String>, selected: String): Spinner =
        Spinner(this).apply {
            isSaveEnabled = false
            adapter = compactSpinnerAdapter(options)
            setSelection(options.indexOf(selected).takeIf { it >= 0 } ?: 0)
            background = roundedStroke(Color.WHITE, 0f, Color.rgb(165, 165, 165))
            tag = options
        }

    private fun realInputBox(value: String, widthDp: Int): EditText = EditText(this).apply {
        setText(value)
        textSize = 15f
        gravity = Gravity.CENTER
        setSingleLine(true)
        inputType = InputType.TYPE_CLASS_NUMBER
        setTextColor(COLOR_TEXT)
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(165, 165, 165))
        setPadding(0, 0, 0, 0)
        layoutParams = LinearLayout.LayoutParams(dp(widthDp), dp(42)).apply { setMargins(dp(4), dp(3), dp(4), dp(3)) }
    }

    @Suppress("UNCHECKED_CAST")
    private fun selectedGeneralId(spinner: Spinner?): Long? {
        val choices = spinner?.tag as? List<Pair<Long, String>> ?: return null
        return choices.getOrNull(spinner.selectedItemPosition)?.first?.takeIf { it > 0L }
    }

    private fun realGeneralChoices(): List<Pair<Long, String>> {
        val account = accountRepo.listAccounts().firstOrNull { it.id == activeAccountId() && it.session?.sourceMode == 1 }
            ?: accountRepo.listAccounts().firstOrNull { it.session?.sourceMode == 1 }
        val extra = account?.session?.channelExtra.orEmpty()
        val raw = extra["generalsJson"] ?: extra["jiangLingData"] ?: return emptyList()
        return runCatching {
            val text = raw.trim()
            val arr = when {
                text.startsWith("[") -> JSONArray(text)
                text.startsWith("{") -> JSONArray().put(JSONObject(text))
                else -> return@runCatching emptyList()
            }
            (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                val id = listOf("id", "generalId", "jiangLingId")
                    .firstNotNullOfOrNull { key -> obj.optString(key).takeIf { it.isNotBlank() }?.toLongOrNull() }
                    ?: return@mapNotNull null
                val name = obj.optString("name").ifBlank { obj.optString("generalName").ifBlank { "#$id" } }
                id to name
            }
        }.getOrDefault(emptyList())
    }


    private fun commonAlarmPanel(): LinearLayout = designFormPanel().apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "alarm_withdraw")?.optJSONObject("values")
        alarmIncomingCheck = tickBox(saved?.optBoolean("incomingEnabled", true) ?: true)
        alarmIncomingModeSpinner = stringSpinner(
            listOf("声音+日志", "仅日志", "关闭"),
            saved?.optString("incomingMode", "声音+日志") ?: "声音+日志"
        )
        alarmMilitaryCheck = tickBox(saved?.optBoolean("militaryEnabled", true) ?: true)
        alarmMilitaryModeSpinner = stringSpinner(
            listOf("出征/返回", "仅来袭", "全部"),
            saved?.optString("militaryMode", "出征/返回") ?: "出征/返回"
        )
        alarmErrorCheck = tickBox(saved?.optBoolean("errorEnabled", true) ?: true)
        addView(alarmSettingRow("来袭警报", alarmIncomingCheck!!, alarmIncomingModeSpinner))
        addView(alarmSettingRow("军情提醒", alarmMilitaryCheck!!, alarmMilitaryModeSpinner))
        addView(alarmSettingRow("异常提醒", alarmErrorCheck!!, null))
        addView(infoBox("说明：\n警报页面用于配置来袭、军情和任务异常提醒。\n只有助手后台在线且授予通知权限时生效；当前不会未经确认自动撤防。"))
    }

    private fun alarmSettingRow(
        label: String,
        enabled: CheckBox,
        mode: Spinner?
    ): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(238, 238, 238))
        setPadding(dp(6), dp(5), dp(6), dp(5))
        addView(TextView(this@MainActivity).apply {
            text = "$label："
            textSize = 14f
            gravity = Gravity.CENTER_VERTICAL
            setSingleLine(true)
            setTextColor(COLOR_TEXT)
        }, LinearLayout.LayoutParams(dp(70), dp(42)))
        addView(enabled, LinearLayout.LayoutParams(dp(34), dp(42)))
        if (mode != null) {
            addView(mode, LinearLayout.LayoutParams(0, dp(42), 1f).apply {
                setMargins(dp(2), 0, 0, 0)
            })
        }
    }


    private fun shuaHuangPanel(): LinearLayout = designFormPanel().apply {
        val savedFormation = configRepo.loadFeatureConfig(activeAccountId(), "formation_troop")?.optJSONObject("values")
        val savedBrush = configRepo.loadFeatureConfig(activeAccountId(), "shua_huang")?.optJSONObject("values")
        val defaultGeneralId = savedFormation?.optString("generalId")?.toLongOrNull()
            ?: savedFormation?.optString("selectedGeneralId")?.toLongOrNull()
            ?: firstRealGeneralIdForAutomation()
        val rows = shuaHuangDraftRows ?: loadShuaHuangDraftRows(savedBrush, defaultGeneralId).also { shuaHuangDraftRows = it }
        shuaHuangEnabledCheckBoxes.clear()
        shuaHuangGeneralSpinners.clear()
        shuaHuangLevelSpinners.clear()
        shuaHuangDropCheckGroups.clear()
        shuaHuangFootSpinners.clear()
        shuaHuangBowSpinners.clear()
        shuaHuangCavalrySpinners.clear()
        shuaHuangChariotSpinners.clear()
        shuaHuangGeneralSpinner = null
        shuaHuangCompositionInput = null
        shuaHuangLevelInput = null
        shuaHuangStartHourSpinner = stringSpinner(
            (0..23).map(Int::toString),
            (savedBrush?.optInt("startHour", 0) ?: 0).coerceIn(0, 23).toString()
        )
        shuaHuangStartXInput = inputBox(
            (savedBrush?.optInt("APKTOOL_RENAMED_0x7f070165", 0) ?: 0).toString(),
            78
        )
        shuaHuangStartYInput = inputBox(
            (savedBrush?.optInt("APKTOOL_RENAMED_0x7f070166", 0) ?: 0).toString(),
            78
        )
        shuaHuangRefillCheck = tickBox(savedBrush?.optBoolean("replenishTroops", true) ?: true)
        shuaHuangFoodConvertCheck = tickBox(
            savedBrush?.optBoolean("autoConvertFoodToCopper", true) ?: true
        )
        shuaHuangCopperFloorSpinner = stringSpinner(
            listOf("1", "10", "20", "50"),
            (savedBrush?.optInt("APKTOOL_RENAMED_0x7f070164", 1) ?: 1)
                .takeIf { it in setOf(1, 10, 20, 50) }
                ?.toString() ?: "1"
        )
        shuaHuangCleanMailCheck = tickBox(
            savedBrush?.optBoolean(
                "cleanMail",
                savedBrush.optBoolean("APKTOOL_RENAMED_0x7f070183", false)
            ) ?: false
        )
        addView(designRow("开始时间：", shuaHuangStartHourSpinner!!, textBox("点")))
        addView(designRow(
            "中心坐标：",
            textBox("x="), shuaHuangStartXInput!!,
            textBox("y="), shuaHuangStartYInput!!
        ))
        addView(designRow(
            "加速：",
            selectBox("不加速"),
            textBox("批量补满"), shuaHuangRefillCheck!!
        ))
        addView(designRow(
            "粮食转铜：",
            shuaHuangFoodConvertCheck!!,
            shuaHuangCopperFloorSpinner!!,
            textBox("万保底")
        ))
        addView(designRow("清空邮件：", shuaHuangCleanMailCheck!!))
        addView(shuaHuangRulesTable(rows))
        addView(shuaHuangActionBar())
        addView(infoBox("说明：\n添加编队：新增一个空白刷黄编队，需要手动勾选并选择将领、山贼等级、掉落多选和步弓骑车\n掉落可同时勾选宝物/资源/装备/宝箱，匹配任意一种即可\n步弓骑车 4 个下拉框的范围都是 0-5\n中心坐标(0,0)表示全图搜索\n清空邮件严格使用0x1116/0x8116回执，失败会阻止继续刷黄\n点击保存设置后会启动：配兵→找黄→上传云端→云端推荐→出征→治疗→补兵"))
    }

    private fun loadShuaHuangDraftRows(saved: JSONObject?, defaultGeneralId: Long?): MutableList<ShuaHuangDraftRow> {
        val arr = saved?.optJSONArray("brushRows")
        if (arr != null) {
            return (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                ShuaHuangDraftRow(
                    enabled = obj.optBoolean("enabled", false),
                    generalId = obj.optString("generalId").toLongOrNull()?.takeIf { it > 0L },
                    level = obj.optString("level", "1").filter { it.isDigit() }.toIntOrNull() ?: 1,
                    drops = obj.optJSONArray("drops")?.let { normalizeShuaHuangDrops(it, emptySet()) }
                        ?: normalizeShuaHuangDrops(obj.optString("drop", "装备")),
                    maxFoot = obj.optInt("maxFoot", 0),
                    maxBow = obj.optInt("maxBow", 0),
                    maxCavalry = obj.optInt("maxCavalry", 0),
                    maxChariot = obj.optInt("maxChariot", 0)
                )
            }.toMutableList()
        }
        if (saved != null) {
            val code = saved.optString("compositionCode", "5203").filter { it.isDigit() }.padEnd(4, '0').take(4)
            return mutableListOf(ShuaHuangDraftRow(
                enabled = saved.optBoolean("APKTOOL_RENAMED_0x7f070073", true),
                generalId = saved.optString("generalId").toLongOrNull()
                    ?: saved.optString("selectedGeneralId").toLongOrNull()
                    ?: defaultGeneralId,
                level = saved.optString("targetLevelMin", "1").toIntOrNull() ?: 1,
                drops = saved.optJSONArray("drops")?.let { normalizeShuaHuangDrops(it, emptySet()) }
                    ?: normalizeShuaHuangDrops(saved.optString("drop", "装备")),
                maxFoot = code.getOrNull(0)?.digitToIntOrNull() ?: 5,
                maxBow = code.getOrNull(1)?.digitToIntOrNull() ?: 2,
                maxCavalry = code.getOrNull(2)?.digitToIntOrNull() ?: 0,
                maxChariot = code.getOrNull(3)?.digitToIntOrNull() ?: 3
            ))
        }
        return mutableListOf()
    }

    private fun shuaHuangRulesTable(rows: List<ShuaHuangDraftRow>): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(0, dp(4), 0, 0)
        val weights = listOf(0.42f, 1.55f, 1.05f, 1.55f, 1.65f, 0.72f)
        addView(militaryTableRow(listOf("☐", "出征将领", "山贼等级", "掉落", "步弓骑车", "操作"), weights, header = true))
        if (rows.isEmpty()) {
            addView(TextView(this@MainActivity).apply {
                text = "暂无刷黄编队，请点击“添加编队”新增空白编队"
                gravity = Gravity.CENTER
                textSize = 15f
                setTextColor(Color.rgb(150, 150, 150))
                background = roundedStroke(Color.WHITE, 0f, Color.rgb(210, 210, 210))
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)).apply {
                setMargins(dp(2), dp(3), dp(2), dp(3))
            })
        } else {
            rows.forEach { row -> addView(shuaHuangEditableRow(weights, row)) }
        }
    }

    private fun shuaHuangDropMultiCell(selected: Set<String>): Pair<LinearLayout, List<CheckBox>> {
        val checks = shuaHuangDropOptions().map { option ->
            CheckBox(this).apply {
                buttonDrawable = null
                tag = option
                isChecked = option in selected
                text = if (isChecked) "☑$option" else "☐$option"
                gravity = Gravity.CENTER
                textSize = 12f
                includeFontPadding = false
                setSingleLine(true)
                setTextColor(COLOR_TEXT)
                background = roundedStroke(Color.WHITE, 0f, Color.rgb(210, 210, 210))
                setPadding(0, 0, 0, 0)
                setOnCheckedChangeListener { button, checked ->
                    button.text = if (checked) "☑${button.tag}" else "☐${button.tag}"
                }
            }
        }
        val cell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            checks.chunked(2).forEach { rowChecks ->
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    rowChecks.forEach { check ->
                        addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply {
                            setMargins(dp(1), dp(1), dp(1), dp(1))
                        })
                    }
                }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            }
        }
        return cell to checks
    }

    private fun shuaHuangEditableRow(weights: List<Float>, row: ShuaHuangDraftRow): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        val rowHeight = dp(64)
        val enabledCell = formationEnabledCell(row.enabled)
        val generalCell = generalSpinner(row.generalId, includePlaceholder = true).apply {
            background = roundedStroke(Color.WHITE, 0f, Color.rgb(165, 165, 165))
        }
        val levelCell = stringSpinner(shuaHuangLevelOptions(), "${row.level.coerceIn(1, 10)}级")
        val (dropCell, dropChecks) = shuaHuangDropMultiCell(row.drops)
        val footCell = stringSpinner(compositionDigitOptions(), row.maxFoot.coerceIn(0, 5).toString())
        val bowCell = stringSpinner(compositionDigitOptions(), row.maxBow.coerceIn(0, 5).toString())
        val cavalryCell = stringSpinner(compositionDigitOptions(), row.maxCavalry.coerceIn(0, 5).toString())
        val chariotCell = stringSpinner(compositionDigitOptions(), row.maxChariot.coerceIn(0, 5).toString())
        shuaHuangEnabledCheckBoxes += enabledCell
        shuaHuangGeneralSpinners += generalCell
        shuaHuangLevelSpinners += levelCell
        shuaHuangDropCheckGroups += dropChecks
        shuaHuangFootSpinners += footCell
        shuaHuangBowSpinners += bowCell
        shuaHuangCavalrySpinners += cavalryCell
        shuaHuangChariotSpinners += chariotCell
        if (shuaHuangGeneralSpinner == null) shuaHuangGeneralSpinner = generalCell
        addView(enabledCell, LinearLayout.LayoutParams(0, rowHeight, weights[0]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(generalCell, LinearLayout.LayoutParams(0, rowHeight, weights[1]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(levelCell, LinearLayout.LayoutParams(0, rowHeight, weights[2]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(dropCell, LinearLayout.LayoutParams(0, rowHeight, weights[3]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(footCell, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f))
            addView(bowCell, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f))
            addView(cavalryCell, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f))
            addView(chariotCell, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f))
        }, LinearLayout.LayoutParams(0, rowHeight, weights[4]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(TextView(this@MainActivity).apply {
            text = "删除"
            gravity = Gravity.CENTER
            textSize = 15f
            includeFontPadding = false
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(255, 128, 136), 2f)
            setOnClickListener {
                val draft = collectShuaHuangDraftRows()
                val index = shuaHuangGeneralSpinners.indexOf(generalCell)
                if (index in draft.indices) draft.removeAt(index)
                shuaHuangDraftRows = draft
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, rowHeight, weights[5]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
    }

    private fun collectShuaHuangDraftRows(): MutableList<ShuaHuangDraftRow> =
        shuaHuangGeneralSpinners.indices.map { index ->
            ShuaHuangDraftRow(
                enabled = shuaHuangEnabledCheckBoxes.getOrNull(index)?.isChecked == true,
                generalId = selectedGeneralId(shuaHuangGeneralSpinners.getOrNull(index)),
                level = shuaHuangLevelSpinners.getOrNull(index)?.selectedItem?.toString()?.filter { it.isDigit() }?.toIntOrNull() ?: 1,
                drops = shuaHuangDropCheckGroups.getOrNull(index)
                    ?.filter { it.isChecked }
                    ?.mapNotNull { normalizeShuaHuangDropValue(it.tag?.toString()).takeIf { value -> value.isNotBlank() } }
                    ?.toCollection(linkedSetOf())
                    ?: emptySet(),
                maxFoot = shuaHuangFootSpinners.getOrNull(index)?.selectedItem?.toString()?.toIntOrNull() ?: 0,
                maxBow = shuaHuangBowSpinners.getOrNull(index)?.selectedItem?.toString()?.toIntOrNull() ?: 0,
                maxCavalry = shuaHuangCavalrySpinners.getOrNull(index)?.selectedItem?.toString()?.toIntOrNull() ?: 0,
                maxChariot = shuaHuangChariotSpinners.getOrNull(index)?.selectedItem?.toString()?.toIntOrNull() ?: 0
            )
        }.toMutableList()

    private fun shuaHuangActionBar(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        setPadding(0, dp(8), 0, 0)
        addView(TextView(this@MainActivity).apply {
            text = "+添加编队"
            gravity = Gravity.CENTER
            textSize = 15f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(52, 142, 221), 4f)
            setOnClickListener {
                val draft = collectShuaHuangDraftRows()
                draft.add(ShuaHuangDraftRow())
                shuaHuangDraftRows = draft
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
        addView(TextView(this@MainActivity).apply {
            text = "📋复制编队"
            gravity = Gravity.CENTER
            textSize = 15f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(65, 158, 108), 4f)
            setOnClickListener {
                val current = collectShuaHuangDraftRows()
                if (current.isEmpty()) {
                    showTopToast("暂无可复制编队")
                    return@setOnClickListener
                }
                val copied = copySelectedOrFirstRows(current, { it.enabled }, { it.copy() })
                shuaHuangDraftRows = copied.toMutableList()
                showTopToast("已复制${copied.size - current.size}个编队")
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
        addView(TextView(this@MainActivity).apply {
            text = "🗑一键删除"
            gravity = Gravity.CENTER
            textSize = 15f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(255, 88, 97), 4f)
            setOnClickListener {
                shuaHuangDraftRows = mutableListOf()
                configRepo.deleteFeatureConfig(activeAccountId(), "shua_huang")
                logRepo.append("已清空刷黄编队", "ui-save")
                showTopToast("已清空刷黄编队")
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
    }


    private fun warInfoPanel(): LinearLayout = militaryIntelPanel(MilitaryIntelTab.MILITARY)


    // The current computer front end routes both “军情” and “国家” tabs through
    // renderJunqing(), so both tabs must show the same live feed rather than applying an
    // Android-only national keyword filter.
    private fun nationInfoPanel(): LinearLayout = militaryIntelPanel(MilitaryIntelTab.NATION)

    private fun militaryIntelPanel(tab: MilitaryIntelTab): LinearLayout = designFormPanel().apply {
        val session = accountRepo.listAccounts().firstOrNull { it.id == activeAccountId() }?.session
        if (session == null || session.sourceMode != 1) {
            addView(emptyText("请先添加并同步真实账号"))
            return@apply
        }
        val display = MilitaryIntelDisplayMapper.map(session.channelExtra)
        val visibleEvents = MilitaryIntelTabPolicy.visibleEvents(display, tab)
        val updatedText = display.updatedAtMillis?.let {
            SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA).format(Date(it))
        } ?: "随最近一次账号同步"
        val fallbackEventTime = display.updatedAtMillis?.let {
            SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date(it))
        } ?: SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date())
        addView(infoBox("出征/返回军情 · 来源=${display.source}\n更新时间：$updatedText"))
        if (visibleEvents.isEmpty()) {
            addView(emptyText("暂无出征/返回军情"))
        } else {
            // app.js renders feedItems in source order. Retain the most recent bounded
            // window, but do not reverse it into an Android-only newest-first order.
            visibleEvents.takeLast(80).forEach { event ->
                addView(TextView(this@MainActivity).apply {
                    text = buildString {
                        append(event.timeText?.takeIf { it.isNotBlank() } ?: fallbackEventTime)
                        append('\n')
                        append(event.text)
                    }
                    textSize = 15f
                    setTextColor(COLOR_TEXT)
                    setPadding(dp(14), dp(12), dp(14), dp(12))
                    background = roundedStroke(Color.WHITE, 8f, COLOR_BORDER)
                    layoutParams = LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT
                    ).apply { setMargins(0, dp(7), 0, 0) }
                })
            }
        }
        addView(outlineButton("从游戏服刷新军情（0x3110）") {
            refreshMilitaryIntelFromServer(session)
        })
    }

    private fun refreshMilitaryIntelFromServer(session: GameSession) {
        showTopToast("正在发送只读军情查询 0x3110…")
        Thread {
            val client = SessionAwareGameProtocolClient(
                actionAudit = { message -> logRepo.append(message, tag = "military-intel") },
                sessionExtraSink = { accountId, updates ->
                    val account = accountRepo.listAccounts().firstOrNull { it.id == accountId }
                    val currentSession = account?.session
                    if (account != null && currentSession != null && currentSession.sourceMode == 1) {
                        accountRepo.upsert(
                            account.copy(
                                session = currentSession.copy(
                                    channelExtra = currentSession.channelExtra + updates
                                )
                            )
                        )
                    }
                }
            )
            val querySession = session.copy(
                channelExtra = session.channelExtra + ("militaryIntelLiveGate" to "true")
            )
            val result = SuspendRunner.run {
                client.scanAlarmAndMaybeWithdraw(
                    querySession,
                    AlarmWithdrawConfig(
                        enabled = false,
                        incomingEnabled = false,
                        militaryEnabled = false,
                        errorEnabled = false
                    )
                )
            }
            mainHandler.post {
                when (result) {
                    is ProtocolResult.Ok -> {
                        logRepo.append("手动军情刷新完成：${result.value.message}", "military-intel")
                        showTopToast("军情刷新完成")
                        showHome(HomeTab.CONFIG)
                    }
                    is ProtocolResult.Err -> {
                        logRepo.append("手动军情刷新失败：${result.code} ${result.message}", "military-intel")
                        showTopToast("军情刷新失败：${result.message}", Toast.LENGTH_LONG)
                    }
                }
            }
        }.start()
    }

    private fun cityCapturePanel(): LinearLayout = designFormPanel().apply {
        val feature = "military_city"
        val saved = futureMilitaryValues(feature)
        prepareFutureMilitaryControls(feature)
        futureMilitaryPrimaryCheck = tickBox(saved?.optBoolean("fullTroops", true) ?: true)
        addView(designRow("满兵：", futureMilitaryPrimaryCheck!!))
        val rows = futureMilitaryRows(feature, saved, defaultEnabled = false, defaultOption = "长安、洛阳")
        addView(
            futureMilitaryTable(
                feature,
                rows,
                "类型",
                listOf("长安、洛阳", "长安", "洛阳", "襄阳", "成都")
            )
        )
        addView(futureMilitaryActionBar(feature, defaultOption = "长安、洛阳"))
        addView(infoBox("说明：\n抢城兵力设置最低1200（冲车不能低于200）。\n当前电脑端此页面也只展示规则；安卓端保存配置但在协议完成前不执行。"))
    }

    private fun losslessPanel(): LinearLayout = designFormPanel().apply {
        val feature = "military_lossless"
        val saved = futureMilitaryValues(feature)
        prepareFutureMilitaryControls(feature)
        futureMilitaryPrimaryCheck = tickBox(saved?.optBoolean("fullTroops", true) ?: true)
        addView(designRow("满兵：", futureMilitaryPrimaryCheck!!))
        val rows = futureMilitaryRows(feature, saved, defaultEnabled = false, defaultOption = "10级")
        addView(
            futureMilitaryTable(
                feature,
                rows,
                "无损等级",
                (1..10).map { "${it}级" }
            )
        )
        addView(futureMilitaryActionBar(feature, defaultOption = "10级"))
        addView(infoBox(
            "说明：\n无损是常驻任务，每日最多5次；失败或完成都会消耗1次。" +
                "\n已接入状态、选级、阵容筛选、出征和结算闭环；10级卫兵阵容不符合安全条件时只刷新、不出征。"
        ))
    }


    private fun sixMinistriesPanel(): LinearLayout = designFormPanel().apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "six_ministries")
            ?.optJSONObject("values")
        ministryCropEnabledCheck = tickBox(saved?.optBoolean("cropEnabled", true) ?: true)
        ministryCropSpinner = stringSpinner(
            listOf("金银花", "草药", "稻谷", "棉花"),
            saved?.optString("crop", "金银花") ?: "金银花"
        )
        ministryHighPriorityCheck = tickBox(saved?.optBoolean("highPriority", true) ?: true)
        ministryStealEnabledCheck = tickBox(saved?.optBoolean("stealEnabled", true) ?: true)
        ministryCourtesyEnabledCheck = tickBox(saved?.optBoolean("courtesyEnabled", true) ?: true)
        ministrySalaryRefreshCheck = tickBox(saved?.optBoolean("salaryRefresh", true) ?: true)
        addView(designRow(
            "种菜收菜：",
            textBox("开启"),
            ministryCropEnabledCheck!!,
            textBox("作物"),
            ministryCropSpinner!!
        ))
        addView(designRow("高级优先：", ministryHighPriorityCheck!!))
        addView(designRow("偷菜：", textBox("开启"), ministryStealEnabledCheck!!))
        addView(designRow("礼部任务：", textBox("开启"), ministryCourtesyEnabledCheck!!, textBox("使用俸禄刷新"), ministrySalaryRefreshCheck!!))
        addView(infoBox(
            "说明：\n礼部任务成功率和文官等级、特长、技能有关。" +
                "\n已接入抓包确认的0x6320菜地状态和0x6328金银花种植；种植后必须再次查询并确认菜地占用数增加。" +
                "\n偷菜已接入0x6322候选和0x6323目标菜地只读扫描，但偷菜动作尚未确认。" +
                "\n其他作物、收菜、偷菜动作和礼部协议未确认，仍不会发送。"
        ))
    }


    private fun escortPanel(): LinearLayout = designFormPanel().apply {
        val feature = "military_escort"
        val saved = futureMilitaryValues(feature)
        prepareFutureMilitaryControls(feature)
        futureMilitaryPrimaryCheck = tickBox(saved?.optBoolean("advancedFirst", true) ?: true)
        futureMilitarySecondaryCheck = tickBox(saved?.optBoolean("fullTroops", true) ?: true)
        futureMilitaryTertiaryCheck = tickBox(saved?.optBoolean("nationalCar", true) ?: true)
        futureMilitaryTextInput = inputBox(saved?.optString("countryName", "美国") ?: "美国", 150)
        addView(designRow("高级优先：", futureMilitaryPrimaryCheck!!, textBox("满兵："), futureMilitarySecondaryCheck!!))
        addView(designRow("国家镖车：", futureMilitaryTertiaryCheck!!, futureMilitaryTextInput!!))
        val rows = futureMilitaryRows(feature, saved, defaultEnabled = true, defaultOption = "史诗")
        addView(futureMilitaryTable(feature, rows, "类型", listOf("史诗", "高级", "普通")))
        addView(futureMilitaryActionBar(feature, defaultOption = "史诗"))
        addView(infoBox("说明：\n押镖如果受到玩家攻击，会自动撤军。\n与电脑端一致先保存配置；选择镖车、发车和撤军协议完整验证前不执行。"))
    }

    private fun twoColumnInfo(leftName: String, leftValue: String, rightName: String, rightValue: String): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        addView(infoCell(leftName, leftValue), LinearLayout.LayoutParams(0, dp(48), 1f))
        addView(infoCell(rightName, rightValue), LinearLayout.LayoutParams(0, dp(48), 1f))
    }

    private fun infoCell(name: String, value: String): TextView = TextView(this).apply {
        text = "$name  $value"
        textSize = 15f
        gravity = Gravity.CENTER_VERTICAL
        setTextColor(COLOR_TEXT)
        setPadding(dp(8), 0, dp(8), 0)
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(230, 230, 230))
    }


    private fun commonMainPanel(): LinearLayout = designFormPanel().apply {
        val internal = configRepo.loadFeatureConfig(activeAccountId(), "internal_affairs")?.optJSONObject("values")
        val daily = configRepo.loadFeatureConfig(activeAccountId(), "daily_basic")?.optJSONObject("values")
        val general = configRepo.loadFeatureConfig(activeAccountId(), "general")?.optJSONObject("values")
        val guaji = configRepo.loadFeatureConfig(activeAccountId(), "guaji_start")?.optJSONObject("values")
        val commonRuntime = configRepo.loadFeatureConfig(activeAccountId(), "common_runtime")?.optJSONObject("values")
        val shua = configRepo.loadFeatureConfig(activeAccountId(), "shua_huang")?.optJSONObject("values")
        val account = accountRepo.listAccounts().firstOrNull { it.id == activeAccountId() }
        val internalEnabled = internal?.optBoolean("enabled", false) ?: false
        val lowFirst = internal?.optBoolean("upgradeLowestFirst", true) ?: true
        val emptyType = internal?.optString("buildWhenEmpty", "HOUSE").orEmpty()
        val convertEnabled = commonRuntime?.optBoolean(
            "foodToCopperEnabled",
            daily?.optBoolean("APKTOOL_RENAMED_0x7f07011d", true) ?: true
        ) ?: true
        val convertWan = (
            account?.session?.channelExtra?.get("copperFloorWan")
                ?: account?.session?.channelExtra?.get("foodToCopperWan")
            )?.toIntOrNull() ?: commonRuntime?.optInt("copperFloorWan", 1) ?: 1
        commonReconnectInput = inputBox(
            (guaji?.optInt("APKTOOL_RENAMED_0x7f07008e", 5) ?: 5).toString(),
            54
        )
        commonBrushLimitInput = inputBox(
            (shua?.optInt("APKTOOL_RENAMED_0x7f070163", commonRuntime?.optInt("brushDailyLimit", 500) ?: 500) ?: 500).toString(),
            64
        )
        commonHealCheck = tickBox(general?.optBoolean("APKTOOL_RENAMED_0x7f070032", true) ?: true)
        addView(designRow("掉线重连：", commonReconnectInput!!, textBox("分钟")))
        addView(designRow("刷黄上限：", commonBrushLimitInput!!, textBox("次")))
        addView(designRow("治疗伤兵：", textBox("开启"), commonHealCheck!!))
        commonInternalEnabledCheck = tickBox(internalEnabled)
        addView(designRow("自动内政：", textBox("开启"), commonInternalEnabledCheck!!))
        commonUpgradeTechnologyCheck = tickBox(internal?.optBoolean("upgradeTechnology", true) ?: true)
        commonTechnologyIds.clear()
        internal?.optJSONArray("technologyIds")?.let { ids ->
            for (index in 0 until ids.length()) {
                ids.optInt(index, -1).takeIf { it in TECHNOLOGY_NAMES.indices }?.let(commonTechnologyIds::add)
            }
        }
        if (commonTechnologyIds.isEmpty()) commonTechnologyIds += 5
        commonTechnologyPicker = selectBox(technologySelectionLabel()).apply {
            isClickable = true
            isFocusable = true
            setOnClickListener { showTechnologyPicker() }
        }
        addView(designRow(
            "升级科技：",
            commonTechnologyPicker!!,
            textBox("开启"),
            commonUpgradeTechnologyCheck!!
        ))
        addView(designRow("建筑加速：", selectBox("不加速")))
        commonInternalLowFirstCheck = tickBox(lowFirst)
        commonInternalEmptyTypeSpinner = stringSpinner(
            listOf("不建", "房屋", "农田", "书院", "步兵营", "弓兵营", "骑兵营", "战车营"),
            mapOf(
                "" to "不建", "UNKNOWN" to "不建", "HOUSE" to "房屋", "FOOD" to "农田",
                "ACADEMY" to "书院", "INFANTRY_CAMP" to "步兵营", "ARCHER_CAMP" to "弓兵营",
                "CAVALRY_CAMP" to "骑兵营", "CHARIOT_CAMP" to "战车营"
            )[emptyType] ?: "房屋"
        )
        addView(designRow("低级优先：", commonInternalLowFirstCheck!!))
        addView(designRow("空地建筑：", commonInternalEmptyTypeSpinner!!))
        commonAutoEnergyCheck = tickBox(general?.optBoolean("APKTOOL_RENAMED_0x7f07002d", true) ?: true)
        commonEnergyThresholdInput = inputBox(
            (general?.optInt("APKTOOL_RENAMED_0x7f070028", 20) ?: 20).toString(),
            54
        )
        addView(designRow("自动加体：", textBox("开启"), commonAutoEnergyCheck!!, textBox("体力<"), commonEnergyThresholdInput!!))
        // 当前电脑端这两行由 dCheck(false)/dInput(...) 生成，没有 id、保存监听或执行任务。
        // 安卓保留相同展示，但禁止历史配置制造可执行假象。
        commonReleaseCheck = tickBox(false).apply { isEnabled = false; alpha = 0.55f }
        commonReleaseThresholdInput = inputBox("80", 54).apply { isEnabled = false; alpha = 0.55f }
        addView(designRow("释放俘虏：", textBox("开启"), commonReleaseCheck!!, textBox("成长>"), commonReleaseThresholdInput!!))
        commonSurrenderCheck = tickBox(false).apply { isEnabled = false; alpha = 0.55f }
        commonSurrenderThresholdInput = inputBox(
            "80",
            54
        ).apply { isEnabled = false; alpha = 0.55f }
        commonSurrenderMethodSpinner = stringSpinner(
            listOf("铜钱劝降"),
            "铜钱劝降"
        ).apply { isEnabled = false; alpha = 0.55f }
        addView(designRow("劝降俘虏：", textBox("开启"), commonSurrenderCheck!!, textBox("成长>"), commonSurrenderThresholdInput!!))
        addView(designRow("劝降方式：", commonSurrenderMethodSpinner!!))
        commonFoodConvertEnabledCheck = tickBox(convertEnabled)
        commonFoodConvertAmountSpinner = stringSpinner(listOf("1", "10", "20", "50"), convertWan.toString())
        addView(designRow("粮食转铜：", textBox("开启"), commonFoodConvertEnabledCheck!!, commonFoodConvertAmountSpinner!!, textBox("万保底")))
        addView(infoBox("说明：释放俘虏、劝降俘虏在当前电脑端仅展示，尚未接入保存和执行，安卓端同步禁用。"))
    }

    private fun technologySelectionLabel(): String {
        val names = commonTechnologyIds.sorted().mapNotNull(TECHNOLOGY_NAMES::getOrNull)
        return when {
            names.isEmpty() -> "请选择"
            names.size <= 2 -> names.joinToString("、")
            else -> "${names.take(2).joinToString("、")}等${names.size}项"
        }
    }

    private fun showTechnologyPicker() {
        val working = commonTechnologyIds.toMutableSet()
        android.app.AlertDialog.Builder(this)
            .setTitle("选择升级科技")
            .setMultiChoiceItems(
                TECHNOLOGY_NAMES.toTypedArray(),
                BooleanArray(TECHNOLOGY_NAMES.size) { it in working }
            ) { _, which, checked ->
                if (checked) working += which else working -= which
            }
            .setPositiveButton("确定") { _, _ ->
                commonTechnologyIds.clear()
                commonTechnologyIds.addAll(working)
                commonTechnologyPicker?.text = technologySelectionLabel()
            }
            .setNegativeButton("取消", null)
            .show()
    }


    private fun commonDailyPanel(): LinearLayout = designFormPanel().apply {
        val accountId = activeAccountId()
        val saved = configRepo.loadFeatureConfig(accountId, "daily_basic")?.optJSONObject("values")
        val savedGeneralIds = saved?.optJSONArray("generalVisitGeneralIds")
            ?: saved?.optJSONArray("generalVisitIds")
            ?: saved?.optJSONArray("selectedGeneralIds")
        dailyGeneralVisitSelectedIds.clear()
        if (savedGeneralIds != null) {
            for (index in 0 until savedGeneralIds.length()) {
                savedGeneralIds.optLong(index).takeIf { it > 0L }
                    ?.let(dailyGeneralVisitSelectedIds::add)
            }
        }
        while (dailyGeneralVisitSelectedIds.size > 4) dailyGeneralVisitSelectedIds.removeLast()
        if (dailyGeneralVisitCandidateAccountId != accountId) {
            dailyGeneralVisitCandidates = emptyList()
            dailyGeneralVisitCandidateAccountId = null
        }

        dailySignInCheck = tickBox(saved?.optBoolean("APKTOOL_RENAMED_0x7f0700a2", true) ?: true)
        dailyArenaCheck = tickBox(saved?.optBoolean("APKTOOL_RENAMED_0x7f07009c", true) ?: true)
        dailyDonateCheck = tickBox(
            saved?.optBoolean("dailyDonateEnabled", false) == true ||
                saved?.optBoolean("APKTOOL_RENAMED_0x7f0700a1", false) == true ||
                saved?.optBoolean("APKTOOL_RENAMED_0x7f0700a0", false) == true
        )
        dailySalaryCheck = tickBox(
            saved?.optBoolean("dailySalaryEnabled", false) == true ||
                saved?.optBoolean("APKTOOL_RENAMED_0x7f07009b", false) == true
        )
        dailyNationalCollectCheck = tickBox(saved?.optBoolean("nationalCollectEnabled", false) ?: false)
        dailyCityLordCollectCheck = tickBox(saved?.optBoolean("cityLordCollectEnabled", false) ?: false)
        dailyGeneralVisitCheck = tickBox(saved?.optBoolean("generalVisitEnabled", false) ?: false).apply {
            setOnCheckedChangeListener { _, checked ->
                if (checked && dailyGeneralVisitCandidates.isEmpty() && !dailyGeneralVisitQueryInFlight) {
                    queryDailyGeneralVisitCandidates()
                }
            }
        }
        dailyGeneralVisitPicker = TextView(this@MainActivity).apply {
            text = dailyGeneralVisitSelectionLabel()
            textSize = 14f
            gravity = Gravity.CENTER_VERTICAL
            setTextColor(COLOR_TEXT)
            setPadding(dp(8), 0, dp(8), 0)
            background = roundedStroke(Color.WHITE, 0f, Color.rgb(150, 150, 150))
            layoutParams = LinearLayout.LayoutParams(0, dp(42), 1f).apply {
                setMargins(dp(4), 0, dp(4), 0)
            }
            setOnClickListener { showDailyGeneralVisitPicker() }
        }
        dailyGeneralVisitRefresh = TextView(this@MainActivity).apply {
            text = if (dailyGeneralVisitQueryInFlight) "查询中…" else "刷新"
            gravity = Gravity.CENTER
            textSize = 14f
            setTextColor(COLOR_PRIMARY)
            background = roundedStroke(Color.WHITE, 0f, COLOR_PRIMARY)
            layoutParams = LinearLayout.LayoutParams(dp(58), dp(42)).apply {
                setMargins(dp(4), 0, 0, 0)
            }
            isEnabled = !dailyGeneralVisitQueryInFlight
            setOnClickListener { queryDailyGeneralVisitCandidates() }
        }
        // 这两行仍是旧页面占位，保持禁用；五项新功能均有自己的独立开关。
        dailyTruceCheck = tickBox(false).apply { isEnabled = false; alpha = 0.55f }
        dailyChainOrganizeCheck = tickBox(false).apply { isEnabled = false; alpha = 0.55f }

        addView(designRow("自动签到：", textBox("开启"), dailySignInCheck!!))
        addView(designRow("领竞技币：", textBox("开启"), dailyArenaCheck!!))
        addView(designRow("自动捐献（三项）：", textBox("铜钱+粮食+科技积分"), dailyDonateCheck!!))
        addView(designRow("领取国家俸禄：", textBox("独立任务"), dailySalaryCheck!!))
        addView(designRow("一键国家征收：", textBox("州/郡/县，优先铜钱最高"), dailyNationalCollectCheck!!))
        addView(designRow("一键城主征收：", textBox("所有自有城池"), dailyCityLordCollectCheck!!))
        addView(designRow("名将拜访：", textBox("先勾选开关"), dailyGeneralVisitCheck!!))
        addView(designRow("拜访优先级：", dailyGeneralVisitPicker!!, dailyGeneralVisitRefresh!!))
        addView(designRow("开启免战：", textBox("待接入"), dailyTruceCheck!!))
        addView(designRow("连体整理：", textBox("待接入"), dailyChainOrganizeCheck!!))
        addView(infoBox(
            "说明：五项功能分别调度、分别记录失败，不会因其中一项失败而阻断其他任务。\n" +
                "名将拜访开启后会先查询当前可拜访列表；列表显示姓名、武力、智力、统帅，最多选择4名，勾选顺序就是拜访优先级。"
        ))
    }

    private fun queryDailyGeneralVisitCandidates() {
        val accountId = activeAccountId()
        val session = accountRepo.listAccounts().firstOrNull { it.id == accountId }?.session
            ?: run {
                dailyGeneralVisitCheck?.isChecked = false
                showTopToast("请先登录当前账号")
                return
            }
        if (dailyGeneralVisitQueryInFlight) return
        dailyGeneralVisitQueryInFlight = true
        dailyGeneralVisitRefresh?.text = "查询中…"
        dailyGeneralVisitRefresh?.isEnabled = false
        dailyGeneralVisitPicker?.text = "正在查询当前可拜访名将…"
        Thread {
            val result = runCatching {
                SuspendRunner.run {
                    SessionAwareGameProtocolClient(
                        actionAudit = { message -> logRepo.append(message, tag = "general-visit", accountId = accountId) }
                    ).queryVisitGenerals(session)
                }
            }.getOrElse {
                ProtocolResult.Err("GENERAL_VISIT_UI_QUERY_EXCEPTION", it.message ?: "查询异常", true)
            }
            mainHandler.post {
                dailyGeneralVisitQueryInFlight = false
                dailyGeneralVisitCandidateAccountId = accountId
                when (result) {
                    is ProtocolResult.Ok -> {
                        dailyGeneralVisitCandidates = result.value
                        val validIds = dailyGeneralVisitCandidates.map { it.id }.toSet()
                        dailyGeneralVisitSelectedIds.retainAll(validIds)
                        dailyGeneralVisitRefresh?.text = "刷新"
                        dailyGeneralVisitRefresh?.isEnabled = true
                        logRepo.append(
                            "已查询当前可拜访名将：${result.value.size}名",
                            tag = "general-visit",
                            accountId = accountId
                        )
                        showTopToast("已获取${result.value.size}名可拜访将领")
                    }
                    is ProtocolResult.Err -> {
                        dailyGeneralVisitCandidates = emptyList()
                        dailyGeneralVisitRefresh?.text = "重试"
                        dailyGeneralVisitRefresh?.isEnabled = true
                        logRepo.append(
                            "查询可拜访名将失败：${result.code} ${result.message}",
                            tag = "general-visit",
                            accountId = accountId
                        )
                        showTopToast("名将列表查询失败：${result.message}", Toast.LENGTH_LONG)
                    }
                }
                showHome(HomeTab.CONFIG)
            }
        }.start()
    }

    private fun showDailyGeneralVisitPicker() {
        if (dailyGeneralVisitCandidates.isEmpty()) {
            showTopToast("请先刷新当前可拜访名将列表")
            if (dailyGeneralVisitCheck?.isChecked == true) queryDailyGeneralVisitCandidates()
            return
        }
        val candidates = dailyGeneralVisitCandidates
        val working = dailyGeneralVisitSelectedIds.toMutableList()
        val checked = BooleanArray(candidates.size) { candidates[it].id in working }
        val labels = candidates.map { candidate ->
            val strength = candidate.strengthTotal.takeIf { it > 0 } ?: candidate.strengthBase
            val intelligence = candidate.intelligenceTotal.takeIf { it > 0 } ?: candidate.intelligenceBase
            "${candidate.name}  武力$strength  智力$intelligence  统帅${candidate.command}"
        }
        android.app.AlertDialog.Builder(this)
            .setTitle("选择拜访名将（最多4名，顺序为优先级）")
            .setMultiChoiceItems(labels.toTypedArray(), checked) { _, which, isChecked ->
                val id = candidates[which].id
                if (isChecked) {
                    if (working.size >= 4 && id !in working) {
                        checked[which] = false
                        showTopToast("最多只能选择4名将领")
                    } else if (id !in working) {
                        working += id
                    }
                } else {
                    working.remove(id)
                }
            }
            .setPositiveButton("确定") { _, _ ->
                dailyGeneralVisitSelectedIds.clear()
                dailyGeneralVisitSelectedIds.addAll(working.take(4))
                dailyGeneralVisitPicker?.text = dailyGeneralVisitSelectionLabel()
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun dailyGeneralVisitSelectionLabel(): String {
        if (dailyGeneralVisitSelectedIds.isEmpty()) return "未选择（点击查看列表）"
        val byId = dailyGeneralVisitCandidates.associateBy { it.id }
        return dailyGeneralVisitSelectedIds.mapIndexed { index, id ->
            val name = byId[id]?.name ?: "ID$id"
            "${circledNumber(index + 1)}$name"
        }.joinToString("  ")
    }

    private fun circledNumber(number: Int): String = when (number) {
        1 -> "①"
        2 -> "②"
        3 -> "③"
        4 -> "④"
        else -> "$number."
    }


    private fun commonItemsPanel(): LinearLayout = designFormPanel().apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "inventory")?.optJSONObject("values")
        val discardSelected = saved.jsonStringSet("discardItems", "discardItemNames")
        val openSelected = saved.jsonStringSet("autoOpenItemNames", "auto_open_item_names")
        val itemOptions = inventoryItemOptions(discardSelected + openSelected)
        inventoryDiscardChecks.clear()
        inventoryAutoOpenChecks.clear()
        addView(designRow("丢弃物品：", inventoryPolicyChecks(itemOptions, discardSelected, inventoryDiscardChecks)))
        inventoryDiscardEquipmentCheck = tickBox(saved?.optBoolean("discardEquipment", false) ?: false)
        inventoryQualitySpinner = stringSpinner(
            listOf("普通", "良好", "优秀", "卓越"),
            saved?.optString("maxEquipmentQuality", "良好") ?: "良好"
        )
        inventoryLevelInput = inputBox((saved?.optInt("maxEquipmentLevel", 20) ?: 20).toString(), 62)
        addView(
            designRow(
                "丢弃装备：",
                inventoryDiscardEquipmentCheck!!,
                inventoryQualitySpinner!!,
                textBox("等级<"),
                inventoryLevelInput!!
            )
        )
        inventoryAutoOpenEnabledCheck = tickBox(saved?.optBoolean("autoOpenEnabled", false) ?: false)
        addView(
            designRow(
                "自动开箱：",
                inventoryAutoOpenEnabledCheck!!,
                inventoryPolicyChecks(inventoryAutoOpenOptions(), openSelected, inventoryAutoOpenChecks)
            )
        )
        addView(infoBox("说明：\n不丢强化、炼魂、80级以上装备。\n青铜宝箱和精铁宝箱需要对应钥匙；保存后进入物品整理任务。"))
    }

    private fun commonChainItemsPanel(): LinearLayout = designFormPanel().apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "chain_inventory")?.optJSONObject("values")
        chainInventoryEnabledCheck = tickBox(saved?.optBoolean("enabled", false) ?: false)
        chainInventoryItemInput = inputBox(saved?.optString("keepItemName", "青铜钥匙") ?: "青铜钥匙", 180)
        chainInventoryKeepCountInput = inputBox((saved?.optInt("keepCount", 3) ?: 3).toString(), 62)
        chainInventoryAutoOpenCheck = tickBox(saved?.optBoolean("autoOpenEnabled", false) ?: false)
        chainInventoryOpenItemsInput = inputBox(saved?.optString("autoOpenItemNames", "50两银票") ?: "50两银票", 220)
        addView(designRow("整理物品：", textBox("开启"), chainInventoryEnabledCheck!!, chainInventoryItemInput!!))
        addView(designRow("保留数量：", chainInventoryKeepCountInput!!))
        addView(designRow("自动开箱：", textBox("开启"), chainInventoryAutoOpenCheck!!, chainInventoryOpenItemsInput!!))
        addView(infoBox("说明：\n连体物品整理同主号物品：按保留清单转移、丢弃、开箱。\n当前先保存规则，连体账号协议接入后再开放执行。"))
    }

    private fun inventoryPolicyChecks(
        options: List<String>,
        selected: Set<String>,
        sink: MutableList<Pair<String, CheckBox>>
    ): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        if (options.isEmpty()) {
            addView(bodyText("角色宝物列表为空"))
        } else {
            val checks = options.map { name ->
                name to CheckBox(this@MainActivity).apply {
                    text = name
                    isChecked = name in selected
                }
            }
            sink += checks
            val picker = TextView(this@MainActivity).apply {
                gravity = Gravity.CENTER_VERTICAL
                textSize = 14f
                setTextColor(COLOR_TEXT)
                setPadding(dp(10), 0, dp(10), 0)
                background = roundedStroke(Color.WHITE, 0f, Color.rgb(180, 180, 180))
                fun refreshLabel() {
                    val names = checks.filter { it.second.isChecked }.map { it.first }
                    text = if (names.isEmpty()) "请选择" else names.take(2).joinToString("、") +
                        if (names.size > 2) "、..." else ""
                }
                refreshLabel()
                setOnClickListener {
                    val working = checks.map { it.second.isChecked }.toBooleanArray()
                    android.app.AlertDialog.Builder(this@MainActivity)
                        .setTitle("选择物品")
                        .setMultiChoiceItems(options.toTypedArray(), working) { _, index, checked ->
                            working[index] = checked
                        }
                        .setPositiveButton("确定") { _, _ ->
                            checks.forEachIndexed { index, pair ->
                                pair.second.isChecked = working[index]
                            }
                            refreshLabel()
                        }
                        .setNegativeButton("取消", null)
                        .show()
                }
            }
            addView(picker, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(42)
            ))
        }
    }

    private fun inventoryItemOptions(extra: Set<String>): List<String> {
        val session = accountRepo.listAccounts().firstOrNull { it.id == activeAccountId() }?.session
        val raw = session?.channelExtra?.get("inventoryJson")
        val live = runCatching {
            val array = JSONArray(raw.orEmpty())
            (0 until array.length()).mapNotNull { index ->
                array.optJSONObject(index)?.optString("name")?.trim()?.takeIf { it.isNotEmpty() }
            }
        }.getOrDefault(emptyList())
        return (live + extra).distinct().sorted()
    }

    private fun inventoryAutoOpenOptions(): List<String> =
        InventoryAutoOpenPolicy.DESKTOP_ITEM_NAMES

    private fun JSONObject?.jsonStringSet(vararg keys: String): Set<String> {
        val obj = this ?: return emptySet()
        keys.forEach { key ->
            obj.optJSONArray(key)?.let { array ->
                return (0 until array.length())
                    .map { array.optString(it).trim() }
                    .filter { it.isNotEmpty() }
                    .toSet()
            }
            if (obj.has(key)) {
                return obj.optString(key)
                    .split(',', '，', ';', '；', '|')
                    .map { it.trim() }
                    .filter { it.isNotEmpty() }
                    .toSet()
            }
        }
        return emptySet()
    }

    private fun formationPanel(): LinearLayout = designFormPanel().apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "formation_troop")?.optJSONObject("values")
        val rows = formationDraftRows ?: loadFormationDraftRows(saved).also { formationDraftRows = it }
        formationEnabledCheckBoxes.clear()
        formationGeneralSpinners.clear()
        formationSoldierSpinners.clear()
        formationCountInputs.clear()
        formationGeneralSpinner = null
        formationSoldierSpinner = null
        formationCountInput = null
        addView(militaryFormationDesignTable(rows))
        addView(formationActionBar())
        addView(formationDesignNoteBox())
    }


    private fun expeditionPanel(title: String): LinearLayout = designFormPanel().apply {
        if (title == "掠夺") {
            addView(lootTopPanel())
            addView(lootTable())
            addView(lootActionBar())
            addView(infoBox(
                "说明：\n保存后按“玩家名称 + 封地序号”查询目标，再发送0x1520/0x1522立即掠夺。" +
                    "\n满兵会先按当前兵种补到将领带兵上限；满忠未达到100时等待，不会带着未知状态出征。"
            ))
        } else if (title == "抢城") {
            addView(designRow("满兵：", tickBox(false)))
            addView(militaryTable(
                listOf("☐", "出征将领", "类型", "操作"),
                listOf(0.45f, 2.5f, 2.1f, 0.72f),
                listOf(listOf("☐", "请选择", "请选择", "删除")),
                hintCols = setOf(1, 2)
            ))
            addView(buttonBar("+添加编队", "📋复制编队", "🗑一键删除"))
            addView(infoBox("说明：\n抢城兵力设置最低1200(冲车不能低于200)"))
        } else if (title == "无损") {
            addView(designRow("满兵：", tickBox(false)))
            addView(militaryTable(
                listOf("☐", "出征将领", "无损等级"),
                listOf(0.45f, 3.6f, 1.1f),
                listOf(listOf("☐", "请选择", "1级")),
                hintCols = setOf(1)
            ))
        }
    }

    private fun militaryFormationDesignTable(rows: List<FormationDraftRow>): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(0, dp(4), 0, 0)
        val weights = listOf(0.46f, 2.6f, 1.35f, 1.42f, 0.78f)
        addView(militaryTableRow(listOf("☐", "出征将领", "类型", "数量", "操作"), weights, header = true))
        if (rows.isEmpty()) {
            addView(TextView(this@MainActivity).apply {
                text = "暂无编队，请点击“添加编队”新增空白编队"
                gravity = Gravity.CENTER
                textSize = 15f
                setTextColor(Color.rgb(150, 150, 150))
                background = roundedStroke(Color.WHITE, 0f, Color.rgb(210, 210, 210))
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)).apply {
                setMargins(dp(2), dp(3), dp(2), dp(3))
            })
        } else {
            rows.forEach { row -> addView(formationDesignEditableRow(weights, row)) }
        }
    }

    private fun formationDesignEditableRow(weights: List<Float>, row: FormationDraftRow): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        val enabledCell = formationEnabledCell(row.enabled)
        val generalCell = generalSpinner(row.generalId, includePlaceholder = true).apply {
            background = roundedStroke(Color.WHITE, 0f, Color.rgb(165, 165, 165))
        }
        val soldierCell = soldierTypeSpinner(row.soldierType).apply {
            background = roundedStroke(Color.WHITE, 0f, Color.rgb(165, 165, 165))
        }
        val countCell = realInputBox(row.soldierCount.toString(), 70)
        formationEnabledCheckBoxes += enabledCell
        formationGeneralSpinners += generalCell
        formationSoldierSpinners += soldierCell
        formationCountInputs += countCell
        if (formationGeneralSpinner == null) formationGeneralSpinner = generalCell
        if (formationSoldierSpinner == null) formationSoldierSpinner = soldierCell
        if (formationCountInput == null) formationCountInput = countCell
        addView(enabledCell, LinearLayout.LayoutParams(0, dp(48), weights[0]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(generalCell, LinearLayout.LayoutParams(0, dp(48), weights[1]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(soldierCell, LinearLayout.LayoutParams(0, dp(48), weights[2]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(countCell, LinearLayout.LayoutParams(0, dp(48), weights[3]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        addView(TextView(this@MainActivity).apply {
            text = "删除"
            gravity = Gravity.CENTER
            textSize = 15f
            includeFontPadding = false
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(255, 128, 136), 2f)
            setOnClickListener {
                val draft = collectFormationDraftRows()
                val index = formationGeneralSpinners.indexOf(generalCell)
                if (index in draft.indices) draft.removeAt(index)
                formationDraftRows = draft
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(48), weights[4]).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
    }

    private fun loadFormationDraftRows(saved: JSONObject?): MutableList<FormationDraftRow> {
        val values = saved ?: return mutableListOf()
        val arr = values.optJSONArray("formationRows")
        if (arr != null) {
            return (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                FormationDraftRow(
                    enabled = obj.optBoolean("enabled", false),
                    generalId = obj.optString("generalId").toLongOrNull()?.takeIf { it > 0L },
                    soldierType = obj.optString("soldierType", "民兵").ifBlank { "民兵" },
                    soldierCount = obj.optString("soldierCount", "3000").toIntOrNull() ?: 3000
                )
            }.toMutableList()
        }
        val gid = values.optString("generalId").toLongOrNull()
            ?: values.optString("selectedGeneralId").toLongOrNull()
        return if (gid != null && gid > 0L) {
            mutableListOf(FormationDraftRow(
                enabled = values.optBoolean("enabled", true),
                generalId = gid,
                soldierType = values.optString("soldierType").ifBlank {
                    values.optString("APKTOOL_RENAMED_0x7f07007c").ifBlank { "民兵" }
                },
                soldierCount = values.optString("soldierCount").toIntOrNull()
                    ?: values.optString("APKTOOL_RENAMED_0x7f07007b").toIntOrNull()
                    ?: 3000
            ))
        } else {
            mutableListOf()
        }
    }

    private fun collectFormationDraftRows(): MutableList<FormationDraftRow> =
        formationGeneralSpinners.indices.map { index ->
            FormationDraftRow(
                enabled = formationEnabledCheckBoxes.getOrNull(index)?.isChecked == true,
                generalId = selectedGeneralId(formationGeneralSpinners.getOrNull(index)),
                soldierType = formationSoldierSpinners.getOrNull(index)?.selectedItem?.toString()?.takeIf { it.isNotBlank() } ?: "民兵",
                soldierCount = formationCountInputs.getOrNull(index)?.text?.toString()?.toIntOrNull() ?: 3000
            )
        }.toMutableList()

    private fun formationActionBar(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        setPadding(0, dp(8), 0, 0)
        addView(TextView(this@MainActivity).apply {
            text = "+添加编队"
            gravity = Gravity.CENTER
            textSize = 15f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(52, 142, 221), 4f)
            setOnClickListener {
                val draft = collectFormationDraftRows()
                draft.add(FormationDraftRow())
                formationDraftRows = draft
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
        addView(TextView(this@MainActivity).apply {
            text = "📋复制编队"
            gravity = Gravity.CENTER
            textSize = 15f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(65, 158, 108), 4f)
            setOnClickListener {
                val current = collectFormationDraftRows()
                if (current.isEmpty()) {
                    showTopToast("暂无可复制编队")
                    return@setOnClickListener
                }
                val copied = copySelectedOrFirstRows(current, { it.enabled }, { it.copy() })
                formationDraftRows = copied.toMutableList()
                showTopToast("已复制${copied.size - current.size}个编队")
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
        addView(TextView(this@MainActivity).apply {
            text = "🗑一键删除"
            gravity = Gravity.CENTER
            textSize = 15f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(255, 88, 97), 4f)
            setOnClickListener {
                formationDraftRows = mutableListOf()
                configRepo.deleteFeatureConfig(activeAccountId(), "formation_troop")
                logRepo.append("已清空配兵编队", "ui-save")
                showTopToast("已清空配兵编队")
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
    }

    private fun formationEnabledCell(enabled: Boolean): CheckBox = CheckBox(this).apply {
        buttonDrawable = null
        isChecked = enabled
        text = if (enabled) "☑" else "☐"
        gravity = Gravity.CENTER
        textSize = 20f
        includeFontPadding = false
        setSingleLine(true)
        setTextColor(COLOR_TEXT)
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(210, 210, 210))
        setPadding(0, 0, 0, 0)
        setOnCheckedChangeListener { button, checked ->
            button.text = if (checked) "☑" else "☐"
        }
    }

    private fun formationDesignNoteBox(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        background = roundedStroke(Color.WHITE, 8f, Color.rgb(205, 205, 205))
        setPadding(dp(14), dp(14), dp(14), dp(14))
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            setMargins(0, dp(10), 0, 0)
        }
        addView(TextView(this@MainActivity).apply {
            text = "说明:"
            textSize = 16f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.rgb(55, 154, 255))
            setPadding(0, 0, 0, dp(8))
        })
        addView(TextView(this@MainActivity).apply {
            text = "添加编队：新增一个空白编队，需要手动勾选并选择将领、兵种和数量\n复制编队：复制已勾选编队；未勾选时复制第一行\n一键删除：清空当前全部编队信息"
            textSize = 15f
            setTextColor(Color.rgb(95, 95, 95))
            setLineSpacing(5f, 1f)
        })
    }

    private fun lootTopPanel(): LinearLayout = LinearLayout(this).apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "auto_loot")?.optJSONObject("values")
        orientation = LinearLayout.VERTICAL
        background = roundedStroke(Color.WHITE, 4f, Color.rgb(238, 238, 238))
        setPadding(dp(10), dp(8), dp(10), dp(8))
        lootFullTroopsCheck = tickBox(saved?.optBoolean("fullTroops", true) ?: true)
        lootFullLoyaltyCheck = tickBox(saved?.optBoolean("fullLoyalty", false) ?: false)
        addView(designRow(
            "满兵：", lootFullTroopsCheck!!,
            textBox("出征方式："), textBox("立即出征")
        ))
        addView(designRow("满忠：", lootFullLoyaltyCheck!!))
    }

    private fun lootTable(): LinearLayout = LinearLayout(this).apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "auto_loot")?.optJSONObject("values")
        val rows = lootDraftRows ?: loadLootDraftRows(saved).also { lootDraftRows = it }
        orientation = LinearLayout.VERTICAL
        setPadding(0, dp(8), 0, 0)
        lootEnabledChecks.clear()
        lootGeneralPickers.clear()
        lootTargetPlayerInputs.clear()
        lootFiefIndexInputs.clear()
        val weights = listOf(0.45f, 1.7f, 1.45f, 1.3f, 0.85f)
        addView(militaryTableRow(listOf("☐", "出征将领", "玩家名称", "封地序号", "操作"), weights, header = true))
        rows.forEachIndexed { index, row ->
            addView(lootEditableRow(index, row, weights))
        }
        if (rows.isEmpty()) {
            addView(emptyRealtimeText("暂无掠夺规则，请点击“添加编队”。"))
        }
    }

    private fun lootEditableRow(
        index: Int,
        row: LootDraftRow,
        weights: List<Float>
    ): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        val enabled = formationEnabledCell(row.enabled)
        lootEnabledChecks += enabled
        addView(enabled, LinearLayout.LayoutParams(0, dp(48), weights[0]))

        val selectedIds = row.generalIds.toMutableSet()
        val pickerButton = Button(this@MainActivity).apply {
            textSize = 13f
            setTextColor(COLOR_TEXT)
            isAllCaps = false
            background = roundedStroke(Color.WHITE, 6f, Color.rgb(190, 190, 190))
            text = lootGeneralSelectionLabel(selectedIds)
        }
        val picker = LootGeneralPickerState(selectedIds, pickerButton)
        lootGeneralPickers += picker
        pickerButton.setOnClickListener { showLootGeneralPicker(picker) }
        addView(pickerButton, LinearLayout.LayoutParams(0, dp(48), weights[1]).apply {
            setMargins(dp(2), dp(3), dp(2), dp(3))
        })

        val playerInput = inputBox(row.playerName, 120).apply {
            hint = "玩家名称"
            textSize = 13f
        }
        lootTargetPlayerInputs += playerInput
        addView(playerInput, LinearLayout.LayoutParams(0, dp(48), weights[2]).apply {
            setMargins(dp(2), dp(3), dp(2), dp(3))
        })

        val fiefInput = inputBox(row.fiefIndex.coerceAtLeast(1).toString(), 60).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            textSize = 13f
        }
        lootFiefIndexInputs += fiefInput
        addView(fiefInput, LinearLayout.LayoutParams(0, dp(48), weights[3]).apply {
            setMargins(dp(2), dp(3), dp(2), dp(3))
        })

        addView(Button(this@MainActivity).apply {
            text = "删除"
            textSize = 12f
            isAllCaps = false
            minWidth = 0
            minimumWidth = 0
            setPadding(0, 0, 0, 0)
            setSingleLine(true)
            setTextColor(Color.rgb(210, 45, 45))
            background = roundedStroke(Color.WHITE, 5f, Color.rgb(220, 120, 120))
            setOnClickListener {
                val current = collectLootDraftRows().toMutableList()
                if (index in current.indices) current.removeAt(index)
                lootDraftRows = current
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(42), weights[4]).apply {
            setMargins(dp(2), dp(6), dp(2), dp(6))
        })
    }

    private fun lootActionBar(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        setPadding(0, dp(8), 0, 0)
        fun action(label: String, block: () -> Unit) = Button(this@MainActivity).apply {
            text = label
            textSize = 13f
            isAllCaps = false
            setTextColor(COLOR_PRIMARY)
            background = roundedStroke(Color.WHITE, 7f, COLOR_PRIMARY)
            setOnClickListener { block() }
        }
        addView(action("+添加编队") {
            lootDraftRows = (collectLootDraftRows() + LootDraftRow()).toMutableList()
            showHome(HomeTab.CONFIG)
        }, LinearLayout.LayoutParams(0, dp(48), 1f).apply { setMargins(0, 0, dp(4), 0) })
        addView(action("📋复制编队") {
            val current = collectLootDraftRows()
            if (current.isEmpty()) {
                showTopToast("暂无可复制的掠夺规则")
            } else {
                lootDraftRows = copySelectedOrFirstRows(current, { it.enabled }, { it.copy() }).toMutableList()
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(48), 1f).apply { setMargins(dp(4), 0, dp(4), 0) })
        addView(action("🗑一键删除") {
            lootDraftRows = mutableListOf()
            showHome(HomeTab.CONFIG)
        }, LinearLayout.LayoutParams(0, dp(48), 1f).apply { setMargins(dp(4), 0, 0, 0) })
    }

    private fun showLootGeneralPicker(state: LootGeneralPickerState) =
        showGeneralMultiPicker(state, "选择掠夺出征将领")

    private fun showGeneralMultiPicker(state: LootGeneralPickerState, title: String) {
        val choices = realGeneralChoices()
        if (choices.isEmpty()) {
            showTopToast("当前账号没有可选将领")
            return
        }
        val working = state.selectedIds.toMutableSet()
        android.app.AlertDialog.Builder(this)
            .setTitle(title)
            .setMultiChoiceItems(
                choices.map { it.second }.toTypedArray(),
                BooleanArray(choices.size) { choices[it].first in working }
            ) { _, which, checked ->
                val id = choices[which].first
                if (checked) working += id else working -= id
            }
            .setPositiveButton("确定") { _, _ ->
                state.selectedIds.clear()
                state.selectedIds.addAll(working)
                state.button.text = lootGeneralSelectionLabel(state.selectedIds)
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun lootGeneralSelectionLabel(ids: Set<Long>): String {
        if (ids.isEmpty()) return "请选择"
        val names = realGeneralChoices().toMap()
        val labels = ids.map { names[it] ?: it.toString() }
        return if (labels.size <= 2) labels.joinToString("、") else "${labels.take(2).joinToString("、")}等${labels.size}将"
    }

    private fun loadLootDraftRows(saved: JSONObject?): MutableList<LootDraftRow> {
        val rows = saved?.optJSONArray("rows")?.let { array ->
            (0 until array.length()).mapNotNull { index ->
                val obj = array.optJSONObject(index) ?: return@mapNotNull null
                val ids = buildList {
                    obj.optJSONArray("generalIds")?.let { generalIds ->
                        for (i in 0 until generalIds.length()) {
                            generalIds.optLong(i).takeIf { it > 0L }?.let(::add)
                        }
                    }
                    if (isEmpty()) obj.optLong("generalId").takeIf { it > 0L }?.let(::add)
                }.distinct()
                LootDraftRow(
                    enabled = obj.optBoolean("enabled", false),
                    generalIds = ids,
                    playerName = obj.optString("playerName"),
                    fiefIndex = obj.optInt("fiefIndex", 1).coerceAtLeast(1)
                )
            }
        }.orEmpty()
        if (rows.isNotEmpty()) return rows.toMutableList()
        val legacyIds = saved?.optJSONArray("selectedGeneralIds")?.let { array ->
            (0 until array.length()).mapNotNull { array.optLong(it).takeIf { id -> id > 0L } }
        }.orEmpty()
        return mutableListOf(
            LootDraftRow(
                enabled = saved?.optBoolean("auto_loot_enabled", false) ?: false,
                generalIds = legacyIds,
                playerName = saved?.optString("auto_loot_target_player").orEmpty(),
                fiefIndex = (saved?.optInt("auto_loot_fief_index", 1) ?: 1).coerceAtLeast(1)
            )
        )
    }

    private fun collectLootDraftRows(): List<LootDraftRow> {
        val size = listOf(
            lootEnabledChecks.size,
            lootGeneralPickers.size,
            lootTargetPlayerInputs.size,
            lootFiefIndexInputs.size
        ).minOrNull() ?: 0
        return (0 until size).map { index ->
            LootDraftRow(
                enabled = lootEnabledChecks[index].isChecked,
                generalIds = lootGeneralPickers[index].selectedIds.toList(),
                playerName = lootTargetPlayerInputs[index].text?.toString()?.trim().orEmpty(),
                fiefIndex = lootFiefIndexInputs[index].text?.toString()?.toIntOrNull()?.coerceAtLeast(1) ?: 1
            )
        }
    }

    private fun militaryTable(
        headers: List<String>,
        weights: List<Float>,
        rows: List<List<String>>,
        hintCols: Set<Int> = emptySet()
    ): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(0, dp(4), 0, 0)
        addView(militaryTableRow(headers, weights, header = true))
        rows.forEach { addView(militaryTableRow(it, weights, hintCols = hintCols)) }
    }

    private fun militaryTableRow(values: List<String>, weights: List<Float>, header: Boolean = false, hintCols: Set<Int> = emptySet()): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        values.forEachIndexed { index, value ->
            addView(TextView(this@MainActivity).apply {
                text = value
                gravity = Gravity.CENTER
                textSize = if (header) 15f else 15f
                typeface = if (header) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
                includeFontPadding = false
                setSingleLine(true)
                setTextColor(when {
                    value == "删除" -> Color.WHITE
                    value.startsWith("+ 添加") -> Color.rgb(55, 154, 255)
                    hintCols.contains(index) -> Color.rgb(150, 150, 150)
                    value == "✓" -> Color.WHITE
                    else -> COLOR_TEXT
                })
                background = when {
                    value == "删除" -> rounded(Color.rgb(255, 128, 136), 2f)
                    value == "✓" -> rounded(Color.rgb(64, 190, 132), 0f)
                    value.startsWith("+ 添加") -> roundedStroke(Color.rgb(245, 250, 255), 6f, Color.rgb(55, 154, 255))
                    else -> roundedStroke(if (header) Color.WHITE else Color.rgb(252, 252, 252), 0f, Color.rgb(210, 210, 210))
                }
                setPadding(dp(2), 0, dp(2), 0)
            }, LinearLayout.LayoutParams(0, dp(if (header) 34 else 38), weights.getOrElse(index) { 1f }).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
        }
    }



    private fun dungeonLikePanel(): LinearLayout = designFormPanel().apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "dungeon")?.optJSONObject("values")
        val enabled = saved?.optBoolean("enabled", saved.optBoolean("APKTOOL_RENAMED_0x7f07007a", false)) ?: false
        val dailyTimes = saved?.optInt("dailyTimes", saved.optInt("APKTOOL_RENAMED_0x7f0700ca", 999)) ?: 999
        val chapter = saved?.optInt("chapter", 0)?.coerceIn(0, 6) ?: 0
        val stage = saved?.optInt("stage", 1)?.coerceAtLeast(1) ?: 1
        val chest = saved?.optInt("boxPosition", 2)?.coerceIn(0, 2) ?: 2
        val selectedIds = saved?.optJSONArray("selectedGeneralIds")?.let { arr ->
            (0 until arr.length()).mapNotNull { arr.optLong(it).takeIf { id -> id > 0L } }.toSet()
        }.orEmpty()

        dungeonEnabledCheck = tickBox(enabled)
        dungeonDailyTimesInput = inputBox(dailyTimes.toString(), 84)
        addView(designRow("启用副本：", dungeonEnabledCheck!!, textBox("每日次数："), dungeonDailyTimesInput!!))

        val chapterOptions = (1..7).map { "第${it}章" }
        dungeonChapterSpinner = stringSpinner(chapterOptions, chapterOptions[chapter])
        dungeonStageSpinner = stringSpinner(
            (1..DungeonProtocolShapes.stageCount(chapter)).map(Int::toString),
            stage.coerceAtMost(DungeonProtocolShapes.stageCount(chapter)).toString()
        )
        dungeonChestSpinner = stringSpinner(listOf("左", "中", "右"), listOf("左", "中", "右")[chest])
        dungeonChapterSpinner?.layoutParams = LinearLayout.LayoutParams(dp(120), dp(42)).apply {
            setMargins(dp(4), 0, dp(8), 0)
        }
        dungeonStageSpinner?.layoutParams = LinearLayout.LayoutParams(dp(72), dp(42)).apply {
            setMargins(dp(4), 0, dp(4), 0)
        }
        dungeonChestSpinner?.layoutParams = LinearLayout.LayoutParams(dp(96), dp(42)).apply {
            setMargins(dp(4), 0, dp(4), 0)
        }
        dungeonChapterSpinner?.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val options = (1..DungeonProtocolShapes.stageCount(position)).map(Int::toString)
                val currentStage = dungeonStageSpinner?.selectedItem?.toString()?.toIntOrNull() ?: 1
                dungeonStageSpinner?.adapter = compactSpinnerAdapter(options)
                dungeonStageSpinner?.setSelection((currentStage.coerceIn(1, options.size)) - 1)
            }
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
        addView(designRow("章节：", dungeonChapterSpinner!!, textBox("关卡："), dungeonStageSpinner!!))
        addView(designRow("开箱位置：", dungeonChestSpinner!!))

        dungeonGeneralChecks.clear()
        val generalRow = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            realGeneralChoices().chunked(2).forEach { choices ->
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    choices.forEach { (id, name) ->
                        val check = CheckBox(this@MainActivity).apply {
                            text = name.ifBlank { "#$id" }
                            textSize = 14f
                            isChecked = id in selectedIds
                            maxLines = 1
                            ellipsize = TextUtils.TruncateAt.END
                        }
                        dungeonGeneralChecks += id to check
                        addView(
                            check,
                            LinearLayout.LayoutParams(0, dp(42), 1f)
                        )
                    }
                    if (choices.size == 1) {
                        addView(View(this@MainActivity), LinearLayout.LayoutParams(0, dp(42), 1f))
                    }
                })
                }
        }
        addView(designRow("出征将领：", generalRow))
        addView(
            infoBox(
                "真实副本流程：读取0x1930服务器目录换算关卡 → 校验将领状态、体力和配兵 → " +
                    "0x1520/0x1522出征 → 0x1938/0x1702轮询 → 奖励状态与战斗ID确认后0x193e开箱。"
            )
        )
    }


    private fun treasureHuntPanel(): LinearLayout = designFormPanel().apply {
        val feature = "military_treasure_hunt"
        val saved = futureMilitaryValues(feature)
        prepareFutureMilitaryControls(feature)
        futureMilitaryCountInput = inputBox((saved?.optInt("useCount", 10) ?: 10).toString(), 70)
        futureMilitaryRefreshInput = inputBox((saved?.optInt("refreshCount", 10) ?: 10).toString(), 84)
        futureMilitaryPrimaryCheck = tickBox(saved?.optBoolean("fullTroops", true) ?: true)
        futureMilitarySecondaryCheck = tickBox(saved?.optBoolean("autoBuy", false) ?: false)
        futureMilitarySpeedSpinner = stringSpinner(
            listOf("不加速", "初级行军符", "中级行军符", "高级行军符"),
            saved?.optString("speed", "不加速") ?: "不加速"
        )
        addView(designRow("使用次数：", futureMilitaryCountInput!!, textBox("次")))
        addView(designRow("每次刷新藏宝图的个数：", futureMilitaryRefreshInput!!))
        addView(designRow("满兵：", futureMilitaryPrimaryCheck!!, textBox("自动购买藏宝图："), futureMilitarySecondaryCheck!!))
        addView(designRow("加速：", futureMilitarySpeedSpinner!!))
        val rows = futureMilitaryRows(feature, saved, defaultEnabled = true, defaultOption = "60级高级...")
        addView(
            futureMilitaryTable(
                feature,
                rows,
                "宝藏类型",
                listOf("60级高级...", "30级普通", "40级高级", "80级高级")
            )
        )
        addView(futureMilitaryActionBar(feature, defaultOption = "60级高级..."))
        addView(infoBox(
            "说明：\n使用次数是每天使用藏宝图的最大次数；建议加速出征，否则可能撞车。" +
                "\n与电脑端一致先保存配置；刷新、选宝藏、发起寻宝和结果协议完整验证前不执行。"
        ))
    }

    private fun futureMilitaryValues(feature: String): JSONObject? =
        configRepo.loadFeatureConfig(activeAccountId(), feature)?.optJSONObject("values")

    private fun prepareFutureMilitaryControls(feature: String) {
        futureMilitaryActiveFeature = feature
        futureMilitaryEnabledChecks.clear()
        futureMilitaryGeneralPickers.clear()
        futureMilitaryOptionSpinners.clear()
        futureMilitaryPrimaryCheck = null
        futureMilitarySecondaryCheck = null
        futureMilitaryTertiaryCheck = null
        futureMilitaryTextInput = null
        futureMilitaryCountInput = null
        futureMilitaryRefreshInput = null
        futureMilitarySpeedSpinner = null
    }

    private fun futureMilitaryRows(
        feature: String,
        saved: JSONObject?,
        defaultEnabled: Boolean,
        defaultOption: String
    ): MutableList<FutureMilitaryDraftRow> =
        futureMilitaryDraftRows.getOrPut(feature) {
            val arr = saved?.optJSONArray("rows")
            if (arr != null && arr.length() > 0) {
                (0 until arr.length()).mapNotNull { index ->
                    val row = arr.optJSONObject(index) ?: return@mapNotNull null
                    FutureMilitaryDraftRow(
                        enabled = row.optBoolean("enabled", defaultEnabled),
                        generalIds = FutureMilitaryGeneralSelectionCodec.read(row),
                        option = row.optString("option")
                            .ifBlank { row.optString("level") }
                            .ifBlank { row.optString("type") }
                            .ifBlank { defaultOption }
                    )
                }.toMutableList()
            } else {
                mutableListOf(
                    FutureMilitaryDraftRow(
                        enabled = defaultEnabled,
                        generalIds = if (defaultEnabled) {
                            listOfNotNull(realGeneralChoices().firstOrNull()?.first)
                        } else {
                            emptyList()
                        },
                        option = defaultOption
                    )
                )
            }
        }

    private fun futureMilitaryTable(
        feature: String,
        rows: List<FutureMilitaryDraftRow>,
        optionHeader: String,
        options: List<String>
    ): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        val weights = listOf(0.45f, 2.5f, 2.1f, 0.72f)
        addView(militaryTableRow(listOf("☐", "出征将领", optionHeader, "操作"), weights, header = true))
        if (rows.isEmpty()) {
            addView(emptyRealtimeText("暂无编队，请点击“添加编队”。"))
        } else {
            rows.forEach { row ->
                addView(futureMilitaryEditableRow(feature, weights, row, options))
            }
        }
    }

    private fun futureMilitaryEditableRow(
        feature: String,
        weights: List<Float>,
        row: FutureMilitaryDraftRow,
        options: List<String>
    ): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        val enabled = formationEnabledCell(row.enabled)
        val selectedIds = FutureMilitaryGeneralSelectionCodec.normalize(row.generalIds).toMutableSet()
        val general = Button(this@MainActivity).apply {
            textSize = 13f
            setTextColor(COLOR_TEXT)
            isAllCaps = false
            minWidth = 0
            minimumWidth = 0
            setPadding(dp(4), 0, dp(4), 0)
            background = roundedStroke(Color.WHITE, 6f, Color.rgb(190, 190, 190))
            text = lootGeneralSelectionLabel(selectedIds)
        }
        val generalPicker = LootGeneralPickerState(selectedIds, general)
        general.setOnClickListener { showGeneralMultiPicker(generalPicker, "选择出征将领") }
        val option = stringSpinner(options, row.option)
        futureMilitaryEnabledChecks += enabled
        futureMilitaryGeneralPickers += generalPicker
        futureMilitaryOptionSpinners += option
        listOf<View>(enabled, general, option).forEachIndexed { index, view ->
            addView(view, LinearLayout.LayoutParams(0, dp(48), weights[index]).apply {
                setMargins(dp(1), dp(2), dp(1), dp(2))
            })
        }
        addView(TextView(this@MainActivity).apply {
            text = "删除"
            gravity = Gravity.CENTER
            textSize = 13f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(255, 128, 136), 2f)
            setOnClickListener {
                val draft = collectFutureMilitaryRows()
                val index = futureMilitaryGeneralPickers.indexOf(generalPicker)
                if (index in draft.indices) draft.removeAt(index)
                futureMilitaryDraftRows[feature] = draft
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(42), weights[3]).apply {
            setMargins(dp(1), dp(5), dp(1), dp(5))
        })
    }

    private fun collectFutureMilitaryRows(): MutableList<FutureMilitaryDraftRow> =
        futureMilitaryEnabledChecks.indices.map { index ->
            FutureMilitaryDraftRow(
                enabled = futureMilitaryEnabledChecks[index].isChecked,
                generalIds = FutureMilitaryGeneralSelectionCodec.normalize(
                    futureMilitaryGeneralPickers.getOrNull(index)?.selectedIds.orEmpty()
                ),
                option = futureMilitaryOptionSpinners.getOrNull(index)?.selectedItem?.toString().orEmpty()
            )
        }.toMutableList()

    private fun futureMilitaryActionBar(feature: String, defaultOption: String): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(8), 0, 0)
            listOf("+添加编队", "📋复制编队", "🗑一键删除").forEachIndexed { index, label ->
                addView(TextView(this@MainActivity).apply {
                    text = label
                    gravity = Gravity.CENTER
                    textSize = 14f
                    setTextColor(Color.WHITE)
                    background = rounded(
                        when (index) {
                            0 -> Color.rgb(52, 142, 221)
                            1 -> Color.rgb(58, 177, 76)
                            else -> Color.rgb(255, 88, 97)
                        },
                        4f
                    )
                    setOnClickListener {
                        val draft = collectFutureMilitaryRows()
                        futureMilitaryDraftRows[feature] = when (index) {
                            0 -> draft.apply { add(FutureMilitaryDraftRow(option = defaultOption)) }
                            1 -> draft.apply {
                                add(lastOrNull()?.copy(enabled = false) ?: FutureMilitaryDraftRow(option = defaultOption))
                            }
                            else -> mutableListOf()
                        }
                        showHome(HomeTab.CONFIG)
                    }
                }, LinearLayout.LayoutParams(0, dp(46), 1f).apply {
                    setMargins(dp(3), 0, dp(3), 0)
                })
            }
        }


    private fun miningAutoPanel(): LinearLayout = designFormPanel().apply {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), "auto_mining")?.optJSONObject("values")
        val rows = mineDraftRows ?: loadMineDraftRows(saved).also { mineDraftRows = it }
        mineEnabledChecks.clear()
        mineGeneralPickers.clear()
        mineResourceSpinners.clear()
        mineXInputs.clear()
        mineYInputs.clear()
        mineScopeSpinners.clear()
        mineSpeedSpinner = stringSpinner(
            listOf("不加速", "初级行军符", "中级行军符", "高级行军符"),
            saved?.optString("speed", "不加速") ?: "不加速"
        )
        mineFullLoyaltyCheck = tickBox(saved?.optBoolean("fullLoyalty", true) ?: true)
        mineTargetPlayerInput = inputBox(saved?.optString("targetPlayerName").orEmpty(), 210).apply {
            hint = "请输入对方玩家名称"
        }
        addView(designRow("打矿加速：", mineSpeedSpinner!!))
        addView(designRow("打矿满忠：", mineFullLoyaltyCheck!!))
        addView(designRow("定点送将对方玩家名称：", mineTargetPlayerInput!!))
        addView(mineDesignTable(rows))
        addView(mineActionBar())
        addView(infoBox("说明：\n坐标(0,0)表示全图搜索\n定点打矿可用于送将\n如果填写了定点送将对方玩家名称，则会在送将时检查该资源是否是该玩家的资源，如果不是则取消出征，防止被偷将"))
    }

    private fun loadMineDraftRows(saved: JSONObject?): MutableList<MineDraftRow> {
        val arr = saved?.optJSONArray("mineRows")
        if (arr != null && arr.length() > 0) {
            return (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                val generalIds = buildList {
                    obj.optJSONArray("generalIds")?.let { ids ->
                        for (itemIndex in 0 until ids.length()) {
                            ids.optLong(itemIndex).takeIf { it > 0L }?.let(::add)
                        }
                    }
                    if (isEmpty()) obj.optLong("generalId").takeIf { it > 0L }?.let(::add)
                }.distinct()
                MineDraftRow(
                    enabled = obj.optBoolean("enabled", false),
                    generalIds = generalIds,
                    resourceType = obj.optString("resourceType", "金矿"),
                    x = obj.optInt("x", 0).coerceIn(0, 186),
                    y = obj.optInt("y", 0).coerceIn(0, 66),
                    scope = obj.optString("scope", "附近").takeIf { it in setOf("定点", "附近", "全国") } ?: "附近"
                )
            }.toMutableList()
        }
        return mutableListOf(
            MineDraftRow(
                enabled = saved?.optBoolean("enabled", false) ?: false,
                generalIds = saved?.optJSONArray("selectedFormationIds")?.let { ids ->
                    (0 until ids.length()).mapNotNull { ids.optLong(it).takeIf { id -> id > 0L } }
                } ?: listOfNotNull(saved?.optLong("generalId")?.takeIf { it > 0L }),
                resourceType = saved?.optString("resourceType", "金矿") ?: "金矿",
                x = saved?.optInt("APKTOOL_RENAMED_0x7f070174", 0) ?: 0,
                y = saved?.optInt("APKTOOL_RENAMED_0x7f070175", 0) ?: 0,
                scope = saved?.optString("scope", "附近") ?: "附近"
            )
        )
    }

    private fun mineDesignTable(rows: List<MineDraftRow>): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        val weights = listOf(0.42f, 1.65f, 1.35f, 0.78f, 0.78f, 0.95f, 0.72f)
        addView(militaryTableRow(listOf("☐", "出征将领", "资源类型", "x", "y", "范围", "操作"), weights, header = true))
        if (rows.isEmpty()) {
            addView(emptyRealtimeText("暂无打矿编队，请点击“添加编队”。"))
        } else {
            rows.forEach { row -> addView(mineEditableRow(weights, row)) }
        }
    }

    private fun mineEditableRow(weights: List<Float>, row: MineDraftRow): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        val enabled = formationEnabledCell(row.enabled)
        val selectedIds = row.generalIds.toMutableSet()
        val general = Button(this@MainActivity).apply {
            textSize = 13f
            setTextColor(COLOR_TEXT)
            isAllCaps = false
            background = roundedStroke(Color.WHITE, 6f, Color.rgb(190, 190, 190))
            text = lootGeneralSelectionLabel(selectedIds)
        }
        val generalPicker = LootGeneralPickerState(selectedIds, general)
        general.setOnClickListener { showGeneralMultiPicker(generalPicker, "选择打矿出征将领") }
        val resource = stringSpinner(mineResourceOptions(), row.resourceType)
        val x = realInputBox(row.x.toString(), 48).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
        }
        val y = realInputBox(row.y.toString(), 48).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
        }
        val scope = stringSpinner(listOf("定点", "附近", "全国"), row.scope)
        mineEnabledChecks += enabled
        mineGeneralPickers += generalPicker
        mineResourceSpinners += resource
        mineXInputs += x
        mineYInputs += y
        mineScopeSpinners += scope
        listOf<View>(enabled, general, resource, x, y, scope).forEachIndexed { index, view ->
            addView(view, LinearLayout.LayoutParams(0, dp(48), weights[index]).apply {
                setMargins(dp(1), dp(2), dp(1), dp(2))
            })
        }
        addView(TextView(this@MainActivity).apply {
            text = "删除"
            gravity = Gravity.CENTER
            textSize = 13f
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(255, 128, 136), 2f)
            setOnClickListener {
                val draft = collectMineDraftRows()
                val index = mineGeneralPickers.indexOf(generalPicker)
                if (index in draft.indices) draft.removeAt(index)
                mineDraftRows = draft
                showHome(HomeTab.CONFIG)
            }
        }, LinearLayout.LayoutParams(0, dp(42), weights[6]).apply {
            setMargins(dp(1), dp(5), dp(1), dp(5))
        })
    }

    private fun collectMineDraftRows(): MutableList<MineDraftRow> =
        mineEnabledChecks.indices.map { index ->
            MineDraftRow(
                enabled = mineEnabledChecks[index].isChecked,
                generalIds = mineGeneralPickers.getOrNull(index)?.selectedIds?.toList().orEmpty(),
                resourceType = mineResourceSpinners.getOrNull(index)?.selectedItem?.toString() ?: "金矿",
                x = mineXInputs.getOrNull(index)?.text?.toString()?.toIntOrNull()?.coerceIn(0, 186) ?: 0,
                y = mineYInputs.getOrNull(index)?.text?.toString()?.toIntOrNull()?.coerceIn(0, 66) ?: 0,
                scope = mineScopeSpinners.getOrNull(index)?.selectedItem?.toString() ?: "附近"
            )
        }.toMutableList()

    private fun mineActionBar(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        setPadding(0, dp(8), 0, 0)
        listOf("+添加编队", "📋复制编队", "🗑一键删除").forEachIndexed { index, label ->
            addView(TextView(this@MainActivity).apply {
                text = label
                gravity = Gravity.CENTER
                textSize = 14f
                setTextColor(Color.WHITE)
                background = rounded(
                    when (index) {
                        0 -> Color.rgb(52, 142, 221)
                        1 -> Color.rgb(58, 177, 76)
                        else -> Color.rgb(255, 88, 97)
                    },
                    4f
                )
                setOnClickListener {
                    val draft = collectMineDraftRows()
                    mineDraftRows = when (index) {
                        0 -> draft.apply { add(MineDraftRow()) }
                        1 -> draft.apply { add(lastOrNull()?.copy(enabled = false) ?: MineDraftRow()) }
                        else -> mutableListOf()
                    }
                    showHome(HomeTab.CONFIG)
                }
            }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
        }
    }

    private fun mineResourceOptions(): List<String> = listOf(
        "金矿", "银矿", "冰玉矿", "仙芝园", "玉露园", "玄铁矿",
        "水晶矿", "灵草园", "牧场", "镔铁矿", "浆果园"
    )

    private fun miningSearchPanel(): LinearLayout = designFormPanel().apply {
        addView(wrapChecks(listOf("金矿", "银矿", "冰玉矿", "仙芝园", "玄铁矿", "玉露园", "水晶矿", "灵草园")))
        addView(designRow("及等级设置：", selectBox("请选择")))
        addView(designRow("是否是无人矿：", tickBox(false)))
        addView(designRow("是否专找有驻防的矿：", tickBox(false)))
        addView(buttonBar("启动前台搜索", "启动后台搜索", "停止后台搜索"))
        addView(infoBox("注意：某个角色打过一次金矿后，该角色当天不能再看到金矿。"))
    }

    private fun internalPanel(): LinearLayout = designFormPanel().apply {
        addView(designRow("自动内政：", textBox("开启"), tickBox(true)))
        addView(designRow("优先升级低级建筑：", tickBox(true)))
        addView(designRow("优先升级建筑排序：", selectBox("民居"), selectBox("书院")))
        addView(designRow("", selectBox("兵营"), selectBox("市场")))
        addView(designRow("若建筑为空自动建设建筑为：", selectBox("一键房子")))
        addView(infoBox("注意：封地名必须是中文开头；如果内政异常，建议将封地数开满。"))
    }

    private fun designFormPanel(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(4))
    }

    private fun designRow(label: String, vararg children: android.view.View): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(238, 238, 238))
        setPadding(dp(8), dp(5), dp(8), dp(5))
        if (label.isNotBlank()) addView(textBox(label), LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(42)))
        children.forEach { child -> addView(child) }
    }

    private fun textBox(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 15f
        setTextColor(COLOR_TEXT)
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dp(3), 0, dp(3), 0)
    }

    private fun inputBox(value: String, widthDp: Int): EditText = EditText(this).apply {
        setText(value)
        textSize = 15f
        setSingleLine(true)
        setPadding(dp(6), 0, dp(6), 0)
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(150, 150, 150))
        layoutParams = LinearLayout.LayoutParams(dp(widthDp), dp(42)).apply { setMargins(dp(4), 0, dp(4), 0) }
    }

    private fun selectBox(value: String): TextView = TextView(this).apply {
        text = value
        textSize = 15f
        gravity = Gravity.CENTER
        setTextColor(COLOR_TEXT)
        background = roundedStroke(Color.WHITE, 0f, Color.rgb(150, 150, 150))
        setPadding(dp(7), 0, dp(7), 0)
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(42)).apply { setMargins(dp(4), 0, dp(4), 0) }
    }

    private fun tickBox(checked: Boolean): CheckBox = CheckBox(this).apply {
        isChecked = checked
        text = ""
        setPadding(0, 0, 0, 0)
        layoutParams = LinearLayout.LayoutParams(dp(46), dp(42))
    }

    private fun infoBox(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 15f
        setTextColor(Color.rgb(95, 95, 95))
        setLineSpacing(5f, 1f)
        background = roundedStroke(Color.WHITE, 8f, Color.rgb(205, 205, 205))
        setPadding(dp(14), dp(14), dp(14), dp(14))
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { setMargins(0, dp(10), 0, 0) }
    }

    private fun emptyText(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 16f
        gravity = Gravity.LEFT
        setTextColor(COLOR_TEXT)
        setPadding(dp(4), dp(4), dp(4), dp(4))
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(250))
    }

    private fun emptyRealtimeText(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 15f
        gravity = Gravity.CENTER
        setTextColor(COLOR_SUBTEXT)
        setLineSpacing(4f, 1f)
        background = roundedStroke(Color.WHITE, 6f, COLOR_BORDER)
        setPadding(dp(12), dp(16), dp(12), dp(16))
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            setMargins(0, dp(6), 0, dp(6))
        }
    }

    private fun fullWidthBlueButton(label: String): TextView = TextView(this).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 15f
        setTextColor(Color.WHITE)
        background = rounded(Color.rgb(52, 142, 221), 4f)
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)).apply {
            setMargins(0, dp(8), 0, 0)
        }
    }

    private fun buttonBar(vararg labels: String): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        setPadding(0, dp(8), 0, 0)
        labels.forEachIndexed { index, label ->
            addView(TextView(this@MainActivity).apply {
                text = label
                gravity = Gravity.CENTER
                textSize = 15f
                setTextColor(Color.WHITE)
                background = rounded(when (index) { 0 -> Color.rgb(52, 142, 221); 1 -> Color.rgb(32, 160, 65); else -> Color.rgb(255, 88, 97) }, 4f)
            }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
        }
    }

    private fun expeditionTable(headers: List<String> = listOf("出征将领", "资源类型", "x坐标", "y坐标", "范围", "操作")): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        addView(tableRow(headers, true))
        addView(tableRow(headers.mapIndexed { index, _ -> listOf("请选择", "请选择", "0", "0", "附近", "删除").getOrElse(index) { "" } }, false))
    }

    private fun wrapChecks(labels: List<String>): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        labels.chunked(3).forEach { chunk ->
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                chunk.forEach { label -> addView(CheckBox(this@MainActivity).apply { text = label; textSize = 14f; isChecked = label == "金矿" }, LinearLayout.LayoutParams(0, dp(42), 1f)) }
            })
        }
    }

    private fun simpleTablePanel(headers: List<String>, rows: List<List<String>>): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        addView(tableRow(headers, true))
        rows.forEach { addView(tableRow(it, false)) }
    }

    private fun tableRow(values: List<String>, header: Boolean): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        values.forEach { value ->
            addView(TextView(this@MainActivity).apply {
                text = value
                gravity = Gravity.CENTER
                textSize = if (header) 15f else 14f
                typeface = if (header) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
                setTextColor(COLOR_TEXT)
                background = roundedStroke(Color.WHITE, 0f, Color.rgb(230, 230, 230))
            }, LinearLayout.LayoutParams(0, dp(38), 1f))
        }
    }

    private fun saveActiveConfig(category: ConfigCategory) {
        val rendered = activeRenderedScreen
        if (rendered == null) {
            saveCustomCategoryConfig(category)
            return
        }
        if (category == ConfigCategory.SHUA_HUANG) {
            saveShuaHuangAndStart(rendered.collectValues())
            return
        }
        if (rendered.spec.featureId == "account_processing") {
            showTopToast("账号数据请通过添加账号写入")
            return
        }
        configRepo.saveFeatureConfig(activeAccountId(), rendered.spec.featureId, rendered.collectValues())
        showTopToast(saveSuccessMessage(category))
    }

    private fun saveCustomCategoryConfig(category: ConfigCategory) {
        val accountId = activeAccountId()
        when (category) {
            ConfigCategory.SHUA_HUANG -> {
                saveShuaHuangAndStart(null)
            }
            ConfigCategory.MILITARY -> {
                when (activeNavItem(category).custom) {
                    "military_dungeon" -> {
                        saveDungeonConfig(accountId)
                        return
                    }
                    "military_loot" -> {
                        saveLootConfig(accountId)
                        return
                    }
                    "military_city",
                    "military_lossless",
                    "military_escort",
                    "military_treasure" -> {
                        saveFutureMilitaryConfig(
                            accountId = accountId,
                            feature = when (activeNavItem(category).custom) {
                                "military_city" -> "military_city"
                                "military_lossless" -> "military_lossless"
                                "military_escort" -> "military_escort"
                                else -> "military_treasure_hunt"
                            }
                        )
                        return
                    }
                }
                val rows = collectFormationDraftRows()
                formationDraftRows = rows
                if (rows.any { it.enabled && it.generalId == null }) {
                    showTopToast("请选择出征将领")
                    return
                }
                val enabledRows = rows.filter { it.enabled && it.generalId != null }
                if (enabledRows.isEmpty()) {
                    configRepo.deleteFeatureConfig(accountId, "formation_troop")
                    logRepo.append("已清空配兵配置", "ui-save")
                    showTopToast("保存配兵设置成功")
                    showHome(HomeTab.CONFIG)
                    return
                }
                val first = enabledRows.first()
                val enabled = true
                val generalId = first.generalId ?: return
                val soldierType = first.soldierType
                val soldierCount = first.soldierCount
                val formationRowsJson = JSONArray().apply {
                    rows.forEach { row ->
                        put(JSONObject()
                            .put("enabled", row.enabled)
                            .put("generalId", row.generalId ?: 0L)
                            .put("soldierType", row.soldierType)
                            .put("soldierCount", row.soldierCount)
                        )
                    }
                }
                val enabledIdsJson = JSONArray().apply {
                    enabledRows.mapNotNull { it.generalId }.forEach { put(it) }
                }
                val values = JSONObject()
                    .put("enabled", enabled)
                    .put("APKTOOL_RENAMED_0x7f070030", enabled)
                    .put("APKTOOL_RENAMED_0x7f07007c", soldierType)
                    .put("APKTOOL_RENAMED_0x7f07007b", soldierCount)
                    .put("soldierType", soldierType)
                    .put("soldierCount", soldierCount)
                    .put("generalId", generalId)
                    .put("selectedGeneralId", generalId)
                    .put("formationId", generalId)
                    .put("selectedFormationIds", enabledIdsJson)
                    .put("formationRows", formationRowsJson)
                configRepo.saveFeatureConfig(accountId, "formation_troop", featureConfig("formation_troop", "配兵", values))
                logRepo.append("已保存配兵配置：${enabledRows.joinToString("；") { "将领/编队 ${it.generalId} · ${it.soldierCount} ${it.soldierType}" }}", "ui-save")
                showTopToast("保存配兵设置成功")
                showHome(HomeTab.CONFIG)
            }
            ConfigCategory.COMMON -> {
                when (activeNavItem(category).custom) {
                    "common_main" -> saveCommonMainConfig(accountId)
                    "common_daily" -> saveCommonDailyConfig(accountId)
                    "common_items" -> saveInventoryConfig(accountId)
                    "common_chain_items" -> saveChainInventoryConfig(accountId)
                    "common_alarm" -> saveAlarmConfig(accountId)
                    else -> showTopToast("当前子页面尚未接入保存")
                }
            }
            ConfigCategory.MINING -> saveMiningConfig(accountId)
            ConfigCategory.MINISTRY -> saveSixMinistriesConfig(accountId)
            else -> showTopToast("当前页面暂无可保存设置")
        }
    }

    private fun saveFutureMilitaryConfig(accountId: Long, feature: String) {
        if (futureMilitaryActiveFeature != feature) {
            showTopToast("页面状态已变化，请重新进入后保存")
            return
        }
        val rows = collectFutureMilitaryRows()
        if (rows.any { it.enabled && it.generalIds.isEmpty() }) {
            showTopToast("已勾选的规则必须选择出征将领")
            return
        }
        if (feature == "military_lossless" && rows.any { it.enabled && it.generalIds.size > 5 }) {
            showTopToast("每条无损规则最多选择5名出征将领")
            return
        }
        futureMilitaryDraftRows[feature] = rows
        val rowsJson = JSONArray().apply {
            rows.forEach { row ->
                put(
                    JSONObject()
                        .put("enabled", row.enabled)
                        .put("generalId", row.generalIds.firstOrNull() ?: 0L)
                        .put("generalIds", FutureMilitaryGeneralSelectionCodec.write(row.generalIds))
                        .put("option", row.option)
                        .put(
                            when (feature) {
                                "military_lossless" -> "level"
                                "military_city" -> "type"
                                "military_escort" -> "type"
                                else -> "type"
                            },
                            row.option
                        )
                )
            }
        }
        val values = JSONObject()
            .put("enabled", rows.any { it.enabled && it.generalIds.isNotEmpty() })
            .put("rows", rowsJson)
            .put("protocolReady", feature == "military_lossless")
        when (feature) {
            "military_city" -> values.put("fullTroops", futureMilitaryPrimaryCheck?.isChecked == true)
            "military_lossless" -> {
                values
                    .put("fullTroops", futureMilitaryPrimaryCheck?.isChecked == true)
                    .put("dailyLimit", 5)
                    .put("priority", "LOSSLESS>SHUA_HUANG>DUNGEON")
            }
            "military_escort" -> values
                .put("advancedFirst", futureMilitaryPrimaryCheck?.isChecked == true)
                .put("fullTroops", futureMilitarySecondaryCheck?.isChecked == true)
                .put("nationalCar", futureMilitaryTertiaryCheck?.isChecked == true)
                .put("countryName", futureMilitaryTextInput?.text?.toString()?.trim().orEmpty())
            "military_treasure_hunt" -> values
                .put("useCount", futureMilitaryCountInput?.text?.toString()?.toIntOrNull()?.coerceIn(0, 999) ?: 10)
                .put("refreshCount", futureMilitaryRefreshInput?.text?.toString()?.toIntOrNull()?.coerceIn(0, 999) ?: 10)
                .put("fullTroops", futureMilitaryPrimaryCheck?.isChecked == true)
                .put("autoBuy", futureMilitarySecondaryCheck?.isChecked == true)
                .put("speed", futureMilitarySpeedSpinner?.selectedItem?.toString() ?: "不加速")
        }
        val title = when (feature) {
            "military_city" -> "抢城"
            "military_lossless" -> "无损"
            "military_escort" -> "押镖"
            else -> "寻宝"
        }
        configRepo.saveFeatureConfig(accountId, feature, featureConfig(feature, title, values))
        val enabled = rows.any { it.enabled && it.generalIds.isNotEmpty() }
        if (feature == "military_lossless" && enabled) {
            val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
            if (decision.allowed) AssistantForegroundService.start(this)
        }
        logRepo.append(
            if (feature == "military_lossless") {
                "已保存无损：启用${rows.count { it.enabled && it.generalIds.isNotEmpty() }}条；" +
                    "按0x1900/1902/1906/1908与0x1520/1522闭环调度"
            } else {
                "已保存$title：启用${rows.count { it.enabled && it.generalIds.isNotEmpty() }}条；真实动作协议未完整验证，暂不执行"
            },
            "ui-save"
        )
        showTopToast("$title 配置已保存")
        showHome(HomeTab.CONFIG)
    }

    private fun saveSixMinistriesConfig(accountId: Long) {
        val values = JSONObject()
            .put("cropEnabled", ministryCropEnabledCheck?.isChecked == true)
            .put("crop", ministryCropSpinner?.selectedItem?.toString() ?: "金银花")
            .put("highPriority", ministryHighPriorityCheck?.isChecked == true)
            .put("stealEnabled", ministryStealEnabledCheck?.isChecked == true)
            .put("courtesyEnabled", ministryCourtesyEnabledCheck?.isChecked == true)
            .put("salaryRefresh", ministrySalaryRefreshCheck?.isChecked == true)
            .put("plantProtocolReady", true)
            .put("stealScanProtocolReady", true)
            .put("protocolReady", false)
        configRepo.saveFeatureConfig(
            accountId,
            "six_ministries",
            featureConfig("six_ministries", "六部", values)
        )
        logRepo.append(
            "已保存六部规则：种菜收菜=${values.optBoolean("cropEnabled")} 作物=${values.optString("crop")} " +
                "高级优先=${values.optBoolean("highPriority")} 偷菜=${values.optBoolean("stealEnabled")} " +
                "礼部=${values.optBoolean("courtesyEnabled")} 俸禄刷新=${values.optBoolean("salaryRefresh")}；" +
                "0x6320/0x6328金银花种植已接入，其他六部动作保持关闭",
            "ui-save"
        )
        val verifiedPlanting = values.optBoolean("cropEnabled") &&
            values.optString("crop") == MinistryProtocolCrop.VERIFIED_NAME
        val stealScan = values.optBoolean("stealEnabled")
        if (verifiedPlanting || stealScan) {
            enableSixMinistriesGates(accountId, verifiedPlanting, stealScan)
            val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
            if (decision.allowed) AssistantForegroundService.start(this)
        }
        showTopToast(
            if (verifiedPlanting || stealScan) "六部设置已保存（已确认协议将进入任务）"
            else "六部设置已保存；所选动作协议未确认，不执行"
        )
        showHome(HomeTab.CONFIG)
    }

    private fun enableSixMinistriesGates(
        accountId: Long,
        planting: Boolean,
        stealScan: Boolean
    ) {
        val account = accountRepo.listAccounts()
            .firstOrNull { it.id == accountId && it.session?.sourceMode == 1 }
            ?: return
        val session = account.session ?: return
        val scopes = session.channelExtra["realActionScopes"]
            .orEmpty()
            .split(',', ';', ' ')
            .map(String::trim)
            .filter(String::isNotEmpty)
            .toMutableSet()
            .apply { if (planting) add("ministry-plant") }
        val additions = mutableMapOf<String, String>()
        if (planting) {
            additions["realActionNetworkAllowed"] = "true"
            additions["realActionSendReady"] = "true"
            additions["realActionScopes"] = scopes.joinToString(",")
        }
        if (stealScan) additions["recoveredReadOnlyLiveGate"] = "true"
        accountRepo.upsert(
            account.copy(
                session = session.copy(
                    channelExtra = session.channelExtra + additions
                )
            )
        )
        logRepo.append(
            "已开启六部 gate：种植=$planting ministry-plant=${planting}，偷菜只读扫描=$stealScan",
            "ui-save"
        )
    }

    private fun saveInventoryConfig(accountId: Long) {
        val discardItems = inventoryDiscardChecks.filter { it.second.isChecked }.map { it.first }.toSet()
        val autoOpenItems = inventoryAutoOpenChecks.filter { it.second.isChecked }.map { it.first }.toSet()
        val discardEquipment = inventoryDiscardEquipmentCheck?.isChecked == true
        val autoOpenEnabled = inventoryAutoOpenEnabledCheck?.isChecked == true
        val quality = inventoryQualitySpinner?.selectedItem?.toString() ?: "良好"
        val qualityOrder = listOf("普通", "良好", "优秀", "卓越")
        val maxQualityIndex = qualityOrder.indexOf(quality).coerceAtLeast(0)
        val values = JSONObject()
            .put("enabled", discardItems.isNotEmpty() || discardEquipment || (autoOpenEnabled && autoOpenItems.isNotEmpty()))
            .put("APKTOOL_RENAMED_0x7f07006f", discardItems.isNotEmpty() || discardEquipment || (autoOpenEnabled && autoOpenItems.isNotEmpty()))
            .put("discardItems", JSONArray(discardItems.toList()))
            .put("discardItemNames", discardItems.joinToString("，"))
            .put("discardEquipment", discardEquipment)
            .put("maxEquipmentQuality", quality)
            .put("maxEquipmentLevel", inventoryLevelInput?.text?.toString()?.toIntOrNull()?.coerceIn(1, 100) ?: 20)
            .put("APKTOOL_RENAMED_0x7f070039", inventoryLevelInput?.text?.toString()?.toIntOrNull()?.coerceIn(1, 100) ?: 20)
            .put("autoOpenEnabled", autoOpenEnabled)
            .put("autoOpenItemNames", JSONArray(autoOpenItems.toList()))
            .put("APKTOOL_RENAMED_0x7f070047", autoOpenEnabled && autoOpenItems.any { it.contains("箱") || it.contains("礼包") })
            .put("APKTOOL_RENAMED_0x7f070046", autoOpenEnabled && autoOpenItems.any { it.contains("银票") })
        listOf(
            "APKTOOL_RENAMED_0x7f070051",
            "APKTOOL_RENAMED_0x7f070050",
            "APKTOOL_RENAMED_0x7f070053",
            "APKTOOL_RENAMED_0x7f070054"
        ).forEachIndexed { index, key ->
            values.put(key, discardEquipment && index <= maxQualityIndex)
        }
        configRepo.saveFeatureConfig(accountId, "inventory", featureConfig("inventory", "主号物品", values))
        logRepo.append(
            "已保存主号物品：丢弃=${discardItems.joinToString().ifBlank { "无" }}，" +
                "装备=${if (discardEquipment) "$quality 且等级<${values.optInt("maxEquipmentLevel")}" else "关闭"}，" +
                "自动开箱=${if (autoOpenEnabled) autoOpenItems.joinToString() else "关闭"}",
            "ui-save"
        )
        showTopToast("主号物品设置已保存")
        showHome(HomeTab.CONFIG)
    }

    private fun saveChainInventoryConfig(accountId: Long) {
        val values = JSONObject()
            .put("enabled", chainInventoryEnabledCheck?.isChecked == true)
            .put("keepItemName", chainInventoryItemInput?.text?.toString()?.trim().orEmpty())
            .put("keepCount", chainInventoryKeepCountInput?.text?.toString()?.toIntOrNull()?.coerceIn(0, 9999) ?: 3)
            .put("autoOpenEnabled", chainInventoryAutoOpenCheck?.isChecked == true)
            .put("autoOpenItemNames", chainInventoryOpenItemsInput?.text?.toString()?.trim().orEmpty())
            .put("protocolReady", false)
        configRepo.saveFeatureConfig(
            accountId,
            "chain_inventory",
            featureConfig("chain_inventory", "连体物品", values)
        )
        logRepo.append("已保存连体物品规则；连体账号协议未接入，暂不执行", "ui-save")
        showTopToast("连体物品设置已保存")
        showHome(HomeTab.CONFIG)
    }

    private fun saveAlarmConfig(accountId: Long) {
        val incomingEnabled = alarmIncomingCheck?.isChecked == true &&
            alarmIncomingModeSpinner?.selectedItem?.toString() != "关闭"
        val militaryEnabled = alarmMilitaryCheck?.isChecked == true
        val errorEnabled = alarmErrorCheck?.isChecked == true
        val incomingMode = alarmIncomingModeSpinner?.selectedItem?.toString() ?: "声音+日志"
        val values = JSONObject()
            .put("alarm_withdraw_enabled", incomingEnabled || militaryEnabled || errorEnabled)
            .put("incomingEnabled", incomingEnabled)
            .put("incomingMode", incomingMode)
            .put("militaryEnabled", militaryEnabled)
            .put("militaryMode", alarmMilitaryModeSpinner?.selectedItem?.toString() ?: "出征/返回")
            .put("errorEnabled", errorEnabled)
            .put("alarm_keywords", "掠夺,夺取,攻城,敌军")
            .put("alarm_vibrate", incomingMode == "声音+日志")
            .put("alarm_withdraw_defense", false)
        configRepo.saveFeatureConfig(
            accountId,
            "alarm_withdraw",
            featureConfig("alarm_withdraw", "警报", values)
        )
        val needsSystemNotification = militaryEnabled || errorEnabled ||
            (incomingEnabled && incomingMode == "声音+日志")
        if (needsSystemNotification) requestNotificationPermissionIfNeeded()
        logRepo.append(
            "已保存警报：来袭=$incomingEnabled/$incomingMode，军情=$militaryEnabled/${values.optString("militaryMode")}，异常=$errorEnabled；自动撤防关闭",
            "ui-save"
        )
        showTopToast("警报设置已保存")
        showHome(HomeTab.CONFIG)
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                REQUEST_NOTIFICATION_PERMISSION
            )
        }
    }

    private fun saveCommonMainConfig(accountId: Long) {
        val reconnectMinutes = commonReconnectInput?.text?.toString()?.toIntOrNull()?.coerceIn(1, 120) ?: 5
        val brushDailyLimit = commonBrushLimitInput?.text?.toString()?.toIntOrNull()?.coerceIn(1, 9999) ?: 500
        val healEnabled = commonHealCheck?.isChecked == true
        val autoEnergyEnabled = commonAutoEnergyCheck?.isChecked == true
        val energyThreshold = commonEnergyThresholdInput?.text?.toString()?.toIntOrNull()?.coerceIn(20, 100) ?: 20
        val autoRelease = commonReleaseCheck?.isChecked == true
        val releaseThreshold = 80
        val autoSurrender = false
        val surrenderThreshold = commonSurrenderThresholdInput?.text?.toString()?.toIntOrNull()?.coerceIn(1, 100) ?: 80
        val convertEnabled = commonFoodConvertEnabledCheck?.isChecked == true
        val convertWan = commonFoodConvertAmountSpinner?.selectedItem?.toString()?.toIntOrNull()
            ?.takeIf { it in setOf(1, 10, 20, 50) } ?: 1
        if (commonUpgradeTechnologyCheck?.isChecked == true && commonTechnologyIds.isEmpty()) {
            showTopToast("升级科技已开启，请至少选择一项科技")
            return
        }
        if (autoRelease && autoSurrender && releaseThreshold >= surrenderThreshold) {
            showTopToast("释放成长阈值必须低于劝降成长阈值")
            return
        }

        val guajiValues = configRepo.loadFeatureConfig(accountId, "guaji_start")
            ?.optJSONObject("values") ?: JSONObject()
        guajiValues.put("APKTOOL_RENAMED_0x7f07008e", reconnectMinutes)
        configRepo.saveFeatureConfig(
            accountId,
            "guaji_start",
            featureConfig("guaji_start", "挂机启动", guajiValues)
        )

        val commonRuntimeValues = JSONObject()
            .put("reconnectMinutes", reconnectMinutes)
            .put("brushDailyLimit", brushDailyLimit)
            .put("foodToCopperEnabled", commonFoodConvertEnabledCheck?.isChecked == true)
            .put(
                "copperFloorWan",
                commonFoodConvertAmountSpinner?.selectedItem?.toString()?.toIntOrNull()
                    ?.takeIf { it in setOf(1, 10, 20, 50) } ?: 1
            )
        configRepo.saveFeatureConfig(
            accountId,
            "common_runtime",
            featureConfig("common_runtime", "常用运行参数", commonRuntimeValues)
        )
        configRepo.loadFeatureConfig(accountId, "shua_huang")?.let { existing ->
            val values = existing.optJSONObject("values") ?: JSONObject()
            values.put("APKTOOL_RENAMED_0x7f070163", brushDailyLimit)
            values.put("APKTOOL_RENAMED_0x7f070164", convertWan)
            values.put("autoConvertFoodToCopper", convertEnabled)
            existing.put("values", values)
            configRepo.saveFeatureConfig(accountId, "shua_huang", existing)
        }

        val generalValues = JSONObject()
            .put("APKTOOL_RENAMED_0x7f070032", healEnabled)
            .put("APKTOOL_RENAMED_0x7f07002f", false)
            .put("APKTOOL_RENAMED_0x7f07002d", autoEnergyEnabled)
            .put("APKTOOL_RENAMED_0x7f070028", energyThreshold)
            .put("APKTOOL_RENAMED_0x7f070031", true)
        configRepo.saveFeatureConfig(
            accountId,
            "general",
            featureConfig("general", "将领维护", generalValues)
        )

        val surrenderValues = JSONObject()
            .put("APKTOOL_RENAMED_0x7f07006b", autoSurrender)
            .put("APKTOOL_RENAMED_0x7f07008b", surrenderThreshold)
            .put("APKTOOL_RENAMED_0x7f07008d", commonSurrenderMethodSpinner?.selectedItem?.toString() == "黄金劝降")
            .put("APKTOOL_RENAMED_0x7f07006d", autoRelease)
            .put("APKTOOL_RENAMED_0x7f07008c", releaseThreshold)
        configRepo.saveFeatureConfig(
            accountId,
            "surrender_release",
            featureConfig("surrender_release", "劝降释放", surrenderValues)
        )

        val internalEnabled = commonInternalEnabledCheck?.isChecked == true
        val lowFirst = commonInternalLowFirstCheck?.isChecked != false
        val emptyType = when (commonInternalEmptyTypeSpinner?.selectedItem?.toString()) {
            "房屋" -> "HOUSE"
            "农田" -> "FOOD"
            "书院" -> "ACADEMY"
            "步兵营" -> "INFANTRY_CAMP"
            "弓兵营" -> "ARCHER_CAMP"
            "骑兵营" -> "CAVALRY_CAMP"
            "战车营" -> "CHARIOT_CAMP"
            else -> "UNKNOWN"
        }
        val internalValues = JSONObject()
            .put("enabled", internalEnabled)
            .put("upgradeLowestFirst", lowFirst)
            .put("buildWhenEmpty", emptyType)
            .put("upgradeTechnology", commonUpgradeTechnologyCheck?.isChecked == true)
            .put("technologyIds", JSONArray().apply { commonTechnologyIds.sorted().forEach(::put) })
            .put("APKTOOL_RENAMED_0x7f070070", internalEnabled)
            .put("APKTOOL_RENAMED_0x7f070065", lowFirst)
        configRepo.saveFeatureConfig(
            accountId,
            "internal_affairs",
            featureConfig("internal_affairs", "自动内政", internalValues)
        )

        val existingDaily = configRepo.loadFeatureConfig(accountId, "daily_basic")
        val dailyValues = existingDaily?.optJSONObject("values") ?: JSONObject()
        if (existingDaily == null) {
            listOf(
                "APKTOOL_RENAMED_0x7f0700a2",
                "APKTOOL_RENAMED_0x7f07009a",
                "APKTOOL_RENAMED_0x7f07009b",
                "APKTOOL_RENAMED_0x7f07009c",
                "APKTOOL_RENAMED_0x7f0700a3",
                "APKTOOL_RENAMED_0x7f07009f",
                "APKTOOL_RENAMED_0x7f0700a1",
                "APKTOOL_RENAMED_0x7f0700a0",
                "APKTOOL_RENAMED_0x7f07009d",
                "APKTOOL_RENAMED_0x7f070099"
            ).forEach { dailyValues.put(it, false) }
        }
        if (!dailyValues.has("dailyDonateEnabled")) dailyValues.put("dailyDonateEnabled", false)
        if (!dailyValues.has("dailySalaryEnabled")) dailyValues.put("dailySalaryEnabled", false)
        if (!dailyValues.has("nationalCollectEnabled")) dailyValues.put("nationalCollectEnabled", false)
        if (!dailyValues.has("cityLordCollectEnabled")) dailyValues.put("cityLordCollectEnabled", false)
        if (!dailyValues.has("generalVisitEnabled")) dailyValues.put("generalVisitEnabled", false)
        if (!dailyValues.has("generalVisitGeneralIds")) dailyValues.put("generalVisitGeneralIds", JSONArray())
        // 当前电脑端“粮食转铜”是铜钱保底策略，不是每天固定兑换一次。
        dailyValues.put("APKTOOL_RENAMED_0x7f07011d", false)
        configRepo.saveFeatureConfig(
            accountId,
            "daily_basic",
            featureConfig("daily_basic", "日常", dailyValues)
        )
        accountRepo.listAccounts().firstOrNull { it.id == accountId }?.let { account ->
            account.session?.let { session ->
                accountRepo.upsert(account.copy(session = session.copy(
                    channelExtra = session.channelExtra + mapOf(
                        "copperFloorWan" to convertWan.toString(),
                        "foodToCopperEnabled" to convertEnabled.toString(),
                        // 旧键保留一版兼容读取，但不再表达固定粮食兑换量。
                        "foodToCopperWan" to convertWan.toString(),
                        "foodToCopperFixedEnabled" to "false"
                    )
                )))
            }
        }
        val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
        if ((internalEnabled ||
                commonUpgradeTechnologyCheck?.isChecked == true ||
                healEnabled ||
                autoEnergyEnabled ||
                autoRelease ||
                autoSurrender) &&
            decision.allowed
        ) {
            AssistantForegroundService.start(this)
        }
        logRepo.append(
            "已保存常用：重连=${reconnectMinutes}分钟，刷黄上限=$brushDailyLimit，治疗=$healEnabled，" +
                "自动内政=$internalEnabled，升级科技=${commonUpgradeTechnologyCheck?.isChecked == true}，" +
                "自动加体=$autoEnergyEnabled(<$energyThreshold)，释放=$autoRelease(<$releaseThreshold)，" +
                "劝降=$autoSurrender(>$surrenderThreshold)，粮食转铜=${if (convertEnabled) "${convertWan}万" else "关闭"}",
            "ui-save"
        )
        showTopToast("保存常用设置成功")
        showHome(HomeTab.CONFIG)
    }

    private fun saveCommonDailyConfig(accountId: Long) {
        val existing = configRepo.loadFeatureConfig(accountId, "daily_basic")
        val values = existing?.optJSONObject("values") ?: JSONObject()
        val signIn = dailySignInCheck?.isChecked == true
        val arena = dailyArenaCheck?.isChecked == true
        val donate = dailyDonateCheck?.isChecked == true
        val salary = dailySalaryCheck?.isChecked == true
        val nationalCollect = dailyNationalCollectCheck?.isChecked == true
        val cityLordCollect = dailyCityLordCollectCheck?.isChecked == true
        val generalVisit = dailyGeneralVisitCheck?.isChecked == true
        val truce = dailyTruceCheck?.isChecked == true
        val chain = dailyChainOrganizeCheck?.isChecked == true
        val selectedVisitIds = JSONArray().apply {
            dailyGeneralVisitSelectedIds.take(4).forEach(::put)
        }

        values
            .put("APKTOOL_RENAMED_0x7f0700a2", signIn)
            .put(
                "APKTOOL_RENAMED_0x7f07009a",
                values.optBoolean("APKTOOL_RENAMED_0x7f07009a", false)
            )
            .put("APKTOOL_RENAMED_0x7f07009c", arena)
            .put("dailyDonateEnabled", donate)
            .put("dailyDonationFactorFz", 1)
            .put("APKTOOL_RENAMED_0x7f0700a1", donate)
            .put("APKTOOL_RENAMED_0x7f0700a0", donate)
            .put("APKTOOL_RENAMED_0x7f07009b", salary)
            .put("dailySalaryEnabled", salary)
            .put("nationalCollectEnabled", nationalCollect)
            .put("nationalCollectMaxCandidates", 0)
            .put("cityLordCollectEnabled", cityLordCollect)
            .put("generalVisitEnabled", generalVisit)
            .put("generalVisitGeneralIds", selectedVisitIds)
            .put("desktopTruceEnabled", truce)
            .put("desktopChainOrganizeEnabled", chain)
        configRepo.saveFeatureConfig(
            accountId,
            "daily_basic",
            featureConfig("daily_basic", "日常", values)
        )

        val anyRunnable = signIn || arena || donate || salary || nationalCollect ||
            cityLordCollect || (generalVisit && selectedVisitIds.length() > 0)
        val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
        if (anyRunnable && decision.allowed) AssistantForegroundService.start(this)
        logRepo.append(
            "已保存日常：签到=$signIn，竞技币=$arena，捐献=$donate，俸禄=$salary，" +
                "国家征收=$nationalCollect，城主征收=$cityLordCollect，" +
                "名将拜访=$generalVisit（优先级=${dailyGeneralVisitSelectedIds.take(4).joinToString(",")}），" +
                "免战=$truce，连体整理=$chain",
            "ui-save"
        )
        showTopToast("保存日常设置成功")
        showHome(HomeTab.CONFIG)
    }

    private fun saveMiningConfig(accountId: Long) {
        val rows = collectMineDraftRows()
        mineDraftRows = rows
        if (rows.any { it.enabled && it.generalIds.isEmpty() }) {
            showTopToast("请选择打矿出征将领")
            return
        }
        val enabledRows = rows.filter { it.enabled && it.generalIds.isNotEmpty() }
        val rowsJson = JSONArray().apply {
            rows.forEach { row ->
                put(
                    JSONObject()
                        .put("enabled", row.enabled)
                        .put("generalIds", JSONArray().apply { row.generalIds.forEach(::put) })
                        .put("generalId", row.generalIds.firstOrNull() ?: 0L)
                        .put("resourceType", row.resourceType)
                        .put("x", row.x)
                        .put("y", row.y)
                        .put("scope", row.scope)
                )
            }
        }
        val first = enabledRows.firstOrNull()
        val selectedIds = JSONArray().apply {
            enabledRows.flatMap { it.generalIds }.distinct().forEach(::put)
        }
        val values = JSONObject()
            .put("enabled", enabledRows.isNotEmpty())
            .put("speed", mineSpeedSpinner?.selectedItem?.toString() ?: "不加速")
            .put("fullLoyalty", mineFullLoyaltyCheck?.isChecked == true)
            .put("targetPlayerName", mineTargetPlayerInput?.text?.toString()?.trim().orEmpty())
            .put("mineRows", rowsJson)
            .put("selectedFormationIds", selectedIds)
            .put("generalId", first?.generalIds?.firstOrNull() ?: 0L)
            .put("resourceType", first?.resourceType ?: "金矿")
            .put("scope", first?.scope ?: "附近")
            .put("APKTOOL_RENAMED_0x7f070075", enabledRows.isNotEmpty())
            .put("APKTOOL_RENAMED_0x7f070174", first?.x ?: 0)
            .put("APKTOOL_RENAMED_0x7f070175", first?.y ?: 0)
            .put("APKTOOL_RENAMED_0x7f070178", true)
        configRepo.saveFeatureConfig(
            accountId,
            "auto_mining",
            featureConfig("auto_mining", "自动打矿", values)
        )
        accountRepo.listAccounts().firstOrNull { it.id == accountId }?.let { account ->
            account.session?.let { session ->
                val scopes = session.channelExtra["realActionScopes"]
                    .orEmpty()
                    .split(',', ';', ' ', '|')
                    .map(String::trim)
                    .filter(String::isNotEmpty)
                    .toMutableSet()
                    .apply { add("mine") }
                accountRepo.upsert(
                    account.copy(
                        session = session.copy(
                            channelExtra = session.channelExtra + mapOf(
                                "realActionNetworkAllowed" to "true",
                                "realActionSendReady" to "true",
                                "realActionScopes" to scopes.joinToString(","),
                                "collaborativeMapRequired" to "true",
                                "collaborativeMapMode" to "disabled-until-server-configured"
                            )
                        )
                    )
                )
            }
        }
        val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
        if (enabledRows.isNotEmpty() && decision.allowed) AssistantForegroundService.start(this)
        logRepo.append(
            "已保存打矿：启用${enabledRows.size}条；云端地图强制开启，流程=先上传矿点→云端推荐→再占矿；服务未配置时禁止本地出征",
            "ui-save"
        )
        showTopToast(if (enabledRows.isEmpty()) "已保存并停用打矿" else "保存打矿设置成功")
        showHome(HomeTab.CONFIG)
    }

    private fun saveDungeonConfig(accountId: Long) {
        val enabled = dungeonEnabledCheck?.isChecked == true
        val selectedIds = dungeonGeneralChecks.filter { it.second.isChecked }.map { it.first }
        if (enabled && selectedIds.isEmpty()) {
            showTopToast("请至少选择一个副本出征将领")
            return
        }
        val dailyTimes = dungeonDailyTimesInput?.text?.toString()?.toIntOrNull()?.coerceIn(1, 999) ?: 999
        val chapter = dungeonChapterSpinner?.selectedItemPosition?.coerceIn(0, 6) ?: 0
        val stage = dungeonStageSpinner?.selectedItem?.toString()?.toIntOrNull() ?: 1
        val chest = dungeonChestSpinner?.selectedItemPosition?.coerceIn(0, 2) ?: 2
        val selectedJson = JSONArray().apply { selectedIds.forEach(::put) }
        val values = JSONObject()
            .put("enabled", enabled)
            .put("dailyTimes", dailyTimes)
            .put("chapter", chapter)
            .put("stage", stage)
            .put("boxPosition", chest)
            .put("selectedGeneralIds", selectedJson)
            .put("APKTOOL_RENAMED_0x7f07007a", enabled)
            .put("APKTOOL_RENAMED_0x7f0700ca", dailyTimes)
        configRepo.saveFeatureConfig(accountId, "dungeon", featureConfig("dungeon", "副本", values))
        logRepo.append(
            "已保存副本：${if (enabled) "启用" else "停用"}，第${chapter + 1}章第${stage}关，" +
                "开${listOf("左", "中", "右")[chest]}箱，将领=${selectedIds.joinToString()}",
            "ui-save"
        )
        val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
        if (enabled && decision.allowed) AssistantForegroundService.start(this)
        showTopToast("保存副本设置成功")
        showHome(HomeTab.CONFIG)
    }

    private fun saveLootConfig(accountId: Long) {
        val rows = collectLootDraftRows()
        lootDraftRows = rows.toMutableList()
        val enabledRows = rows.filter { it.enabled }
        val missingGenerals = enabledRows.indexOfFirst { it.generalIds.isEmpty() }
        if (missingGenerals >= 0) {
            showTopToast("第${missingGenerals + 1}条掠夺规则未选择出征将领")
            return
        }
        val missingPlayer = enabledRows.indexOfFirst { it.playerName.isBlank() }
        if (missingPlayer >= 0) {
            showTopToast("第${missingPlayer + 1}条掠夺规则未填写玩家名称")
            return
        }
        val invalidFief = enabledRows.indexOfFirst { it.fiefIndex <= 0 }
        if (invalidFief >= 0) {
            showTopToast("第${invalidFief + 1}条掠夺规则封地序号必须大于0")
            return
        }
        val rowsJson = JSONArray().apply {
            rows.forEach { row ->
                put(
                    JSONObject()
                        .put("enabled", row.enabled)
                        .put("generalIds", JSONArray().apply { row.generalIds.forEach(::put) })
                        .put("generalId", row.generalIds.firstOrNull() ?: 0L)
                        .put("playerName", row.playerName)
                        .put("fiefIndex", row.fiefIndex)
                )
            }
        }
        val first = enabledRows.firstOrNull()
        val selectedJson = JSONArray().apply { first?.generalIds?.forEach(::put) }
        val values = JSONObject()
            .put("auto_loot_enabled", enabledRows.isNotEmpty())
            .put("fullTroops", lootFullTroopsCheck?.isChecked == true)
            .put("fullLoyalty", lootFullLoyaltyCheck?.isChecked == true)
            .put("rows", rowsJson)
            .put("selectedGeneralIds", selectedJson)
            .put("auto_loot_target_player", first?.playerName.orEmpty())
            .put("auto_loot_fief_index", first?.fiefIndex ?: 1)
        configRepo.saveFeatureConfig(
            accountId,
            "auto_loot",
            featureConfig("auto_loot", "掠夺", values)
        )
        logRepo.append(
            "已保存掠夺：启用${enabledRows.size}条，满兵=${values.optBoolean("fullTroops")}，" +
                "满忠=${values.optBoolean("fullLoyalty")}；" +
                enabledRows.joinToString("；") {
                    "将领=${it.generalIds.joinToString("/")}→${it.playerName}第${it.fiefIndex}封地"
                },
            "ui-save"
        )
        val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
        if (enabledRows.isNotEmpty() && decision.allowed) AssistantForegroundService.start(this)
        showTopToast(if (enabledRows.isEmpty()) "已保存并停用掠夺" else "保存掠夺设置成功")
        showHome(HomeTab.CONFIG)
    }

    private fun saveShuaHuangAndStart(renderedConfig: JSONObject?) {
        val values = renderedConfig?.optJSONObject("values") ?: JSONObject()
        val accountId = activeAccountId()
        val rows = collectShuaHuangDraftRows()
        shuaHuangDraftRows = rows
        if (rows.any { it.enabled && it.generalId == null }) {
            showTopToast("请选择刷黄出征将领")
            return
        }
        val enabledRows = rows.filter { it.enabled && it.generalId != null }
        if (enabledRows.isEmpty()) {
            showTopToast("请先添加并勾选刷黄编队")
            return
        }
        val first = enabledRows.first()
        val generalId = first.generalId ?: return
        val compositionCode = first.compositionCode
        val maxFoot = first.maxFoot.coerceIn(0, 5)
        val maxBow = first.maxBow.coerceIn(0, 5)
        val maxCavalry = first.maxCavalry.coerceIn(0, 5)
        val maxChariot = first.maxChariot.coerceIn(0, 5)
        val level = first.level.coerceIn(1, 10)
        val startHour = shuaHuangStartHourSpinner?.selectedItem?.toString()
            ?.toIntOrNull()?.coerceIn(0, 23) ?: 0
        val startX = shuaHuangStartXInput?.text?.toString()
            ?.toIntOrNull()?.coerceIn(0, 186) ?: 0
        val startY = shuaHuangStartYInput?.text?.toString()
            ?.toIntOrNull()?.coerceIn(0, 66) ?: 0
        val copperFloorWan = shuaHuangCopperFloorSpinner?.selectedItem?.toString()
            ?.toIntOrNull()?.takeIf { it in setOf(1, 10, 20, 50) } ?: 1
        val brushRowsJson = JSONArray().apply {
            rows.forEach { row ->
                put(JSONObject()
                    .put("enabled", row.enabled)
                    .put("generalId", row.generalId ?: 0L)
                    .put("level", row.level.coerceIn(1, 10))
                    .put("drop", row.drop)
                    .put("drops", JSONArray().apply { row.drops.forEach { put(it) } })
                    .put("maxFoot", row.maxFoot.coerceIn(0, 5))
                    .put("maxBow", row.maxBow.coerceIn(0, 5))
                    .put("maxCavalry", row.maxCavalry.coerceIn(0, 5))
                    .put("maxChariot", row.maxChariot.coerceIn(0, 5))
                    .put("compositionCode", row.compositionCode)
                )
            }
        }
        val enabledIdsJson = JSONArray().apply {
            enabledRows.mapNotNull { it.generalId }.forEach { put(it) }
        }
        values
            .put("APKTOOL_RENAMED_0x7f070073", true) // enabled
            .put("APKTOOL_RENAMED_0x7f070163", values.optString("APKTOOL_RENAMED_0x7f070163", "500").toIntOrNull() ?: 500)
            .put("startHour", startHour)
            .put("APKTOOL_RENAMED_0x7f070165", startX)
            .put("APKTOOL_RENAMED_0x7f070166", startY)
            .put("APKTOOL_RENAMED_0x7f070164", copperFloorWan)
            .put("autoConvertFoodToCopper", shuaHuangFoodConvertCheck?.isChecked == true)
            .put("replenishTroops", shuaHuangRefillCheck?.isChecked == true)
            .put("cleanMail", shuaHuangCleanMailCheck?.isChecked == true)
            .put("APKTOOL_RENAMED_0x7f070183", shuaHuangCleanMailCheck?.isChecked == true)
            .put("APKTOOL_RENAMED_0x7f070188", false) // false=山贼，和原型默认一致
            .put("targetLevelMin", level)
            .put("targetLevelMax", level)
            .put("compositionCode", compositionCode)
            .put("maxFoot", maxFoot)
            .put("maxBow", maxBow)
            .put("maxCavalry", maxCavalry)
            .put("maxChariot", maxChariot)
            .put("drop", first.drop)
            .put("drops", JSONArray().apply { first.drops.forEach { put(it) } })
            .put("generalId", generalId)
            .put("selectedGeneralId", generalId)
            .put("formationId", generalId)
            .put("selectedFormationIds", enabledIdsJson)
            .put("brushRows", brushRowsJson)
        val config = renderedConfig ?: featureConfig("shua_huang", "自动刷黄/刷山贼", values)
        if (renderedConfig != null) config.put("values", values)
        configRepo.saveFeatureConfig(accountId, "shua_huang", config)
        ensureDefaultFormationConfig(accountId, generalId)
        enableBrushYellowActionGate(accountId, generalId)
        val decision = HostingStartPolicy.evaluate(accountRepo.listAccounts())
        logRepo.append(
            "保存刷黄：启用${enabledRows.size}条，${startHour}点开始，中心=($startX,$startY)，" +
                "首条将领/编队=$generalId，等级=${level}级，掉落=${first.dropLabel}，" +
                "筛选=$compositionCode(步≤$maxFoot 弓≤$maxBow 骑≤$maxCavalry 车≤$maxChariot)，" +
                "粮转铜=${shuaHuangFoodConvertCheck?.isChecked == true}/保底${copperFloorWan}万，" +
                "清邮件=${shuaHuangCleanMailCheck?.isChecked == true}，后台启动=${decision.allowed}",
            "ui-save"
        )
        if (decision.allowed) {
            AssistantForegroundService.start(this@MainActivity)
            logRepo.append("后台链路已请求启动：先配兵→041540找黄→5203筛选→出征→等待→治疗→补兵→循环", "ui-save")
        } else {
            logRepo.append("后台未启动：${decision.message}", "ui-save")
        }
        showTopToast("保存刷黄设置成功")
        showHome(HomeTab.CONFIG)
    }

    private fun saveSuccessMessage(category: ConfigCategory): String = when (category) {
        ConfigCategory.MILITARY -> "保存配兵设置成功"
        ConfigCategory.SHUA_HUANG -> "保存刷黄设置成功"
        else -> "保存设置成功"
    }

    private fun enableBrushYellowActionGate(accountId: Long, generalId: Long) {
        val account = accountRepo.listAccounts().firstOrNull { it.id == accountId && it.session?.sourceMode == 1 }
            ?: return
        val session = account.session ?: return
        val updatedExtra = session.channelExtra + mapOf(
            "realActionNetworkAllowed" to "true",
            "realActionSendReady" to "true",
            "realActionScope" to "brush-yellow",
            "realActionScopes" to "brush-yellow,mine,daily,inventory,general-maintenance,dungeon,lossless,raid,resource-conversion,internal-affairs",
            "realActionBrushYellowOnly" to "true",
            "allowRecoveredGeneralFallbackFormation" to "true",
            "recoveredReadOnlyLiveGate" to "true",
            "recoveredReadOnlyScanLimit" to "40",
            "collaborativeMapRequired" to "true",
            "collaborativeMapMode" to "disabled-until-server-configured",
            "selectedFormationIds" to generalId.toString(),
            "shuaHuangSelectedFormationIds" to generalId.toString(),
            "shuaHuangTargetType" to "SHAN_ZEI",
            "shuaHuangDailyLimit" to "500"
        )
        accountRepo.upsert(account.copy(session = session.copy(channelExtra = updatedExtra)))
        logRepo.append("已为账号 $accountId 开启已迁移动作 gate（刷黄、日常、宝物）：将领/编队 $generalId", "ui-save")
    }

    private fun ensureDefaultFormationConfig(accountId: Long, generalId: Long) {
        if (configRepo.loadFeatureConfig(accountId, "formation_troop") != null) return
        val values = JSONObject()
            .put("enabled", true)
            .put("APKTOOL_RENAMED_0x7f070030", true)
            .put("APKTOOL_RENAMED_0x7f07007c", "轻骑兵")
            .put("APKTOOL_RENAMED_0x7f07007b", 200)
            .put("soldierType", "轻骑兵")
            .put("soldierCount", 200)
            .put("generalId", generalId)
            .put("selectedGeneralId", generalId)
            .put("formationId", generalId)
            .put("selectedFormationIds", JSONArray().put(generalId))
        configRepo.saveFeatureConfig(accountId, "formation_troop", featureConfig("formation_troop", "配兵", values))
        logRepo.append("自动补齐配兵配置：将领/编队 $generalId · 200 轻骑兵", "ui-save")
    }

    private fun firstRealGeneralIdForAutomation(): Long? {
        val account = accountRepo.listAccounts().firstOrNull { it.id == activeAccountId() && it.session?.sourceMode == 1 }
            ?: accountRepo.listAccounts().firstOrNull { it.session?.sourceMode == 1 }
        val extra = account?.session?.channelExtra.orEmpty()
        val raw = extra["generalsJson"] ?: extra["jiangLingData"] ?: return null
        return runCatching {
            val text = raw.trim()
            val arr = when {
                text.startsWith("[") -> JSONArray(text)
                text.startsWith("{") -> JSONArray().put(JSONObject(text))
                else -> return@runCatching null
            }
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                val id = listOf("id", "generalId", "jiangLingId")
                    .firstNotNullOfOrNull { key -> obj.optString(key).takeIf { it.isNotBlank() }?.toLongOrNull() }
                if (id != null && id > 0L) return@runCatching id
            }
            null
        }.getOrNull()
    }

    private fun featureConfig(featureId: String, featureName: String, values: JSONObject): JSONObject =
        JSONObject()
            .put("schema_version", "0.1-static-screen-form")
            .put("feature_id", featureId)
            .put("feature_name_zh", featureName)
            .put("layout", "custom")
            .put("values", values)

    private fun sideLabels(category: ConfigCategory): List<String> = when (category) {
        ConfigCategory.ROLE -> listOf("角色", "英雄", "军队", "宝物", "状态", "任务")
        ConfigCategory.MILITARY -> listOf("配兵", "将领", "队列", "劝降", "副本")
        ConfigCategory.SHUA_HUANG -> listOf("坐标", "将领", "等级", "奖励", "兵种")
        ConfigCategory.WAR_INFO -> listOf("警报", "敌情", "撤防", "通知", "记录")
        ConfigCategory.MINING -> listOf("找矿", "占矿", "采集", "送将", "召回")
        ConfigCategory.MINISTRY -> listOf("内政", "建筑", "科技", "资源", "任务")
        ConfigCategory.COMMON -> listOf("账号", "挂机", "日常", "防封", "工具")
    }

    private fun categoryDescription(category: ConfigCategory): String = when (category) {
        ConfigCategory.ROLE -> "角色资产状态。"
        ConfigCategory.MILITARY -> "军事负责配兵、将领选择、编队出征、劝降释放等战斗前置配置。"
        ConfigCategory.SHUA_HUANG -> "刷黄/山贼是核心自动化：用户设置起始坐标、出战将领、山贼等级、期望掉落、敌方兵种后，助手在地图检索并筛选目标，再进入出征流程。"
        ConfigCategory.WAR_INFO -> "军情负责扫描警报、敌军来袭、掠夺/攻城关键字，并按配置提醒或记录撤防计划。"
        ConfigCategory.MINING -> "打矿负责找矿、筛选资源点、派将占矿/采集，以及资源点送将等流程。"
        ConfigCategory.MINISTRY -> "六部偏内政自动化，包括建筑、科技、资源、日常内政任务等非战斗流程。"
        ConfigCategory.COMMON -> "常规放账号登录、挂机启动/运行、一键日常、批量工具、防封与通用设置。"
    }

    private fun flowSteps(category: ConfigCategory): List<String> = when (category) {
        ConfigCategory.MILITARY -> listOf("① 选择将领与编队", "② 配置兵种数量与出征队列", "③ 配置劝降/释放、副本等战斗附加动作")
        ConfigCategory.SHUA_HUANG -> listOf("① 起始坐标：从哪个地图坐标开始搜索", "② 出战将领：选择使用哪个将领/队伍", "③ 山贼等级：筛选要打几级山贼", "④ 奖励掉落：筛选希望掉落的宝物/资源类型", "⑤ 山贼兵种：按 5203=步≤5 弓≤2 骑≤0 车≤3 过滤", "⑥ 保存后后台按：配兵→找黄→筛选→出征→等待→治疗→补兵 循环")
        ConfigCategory.WAR_INFO -> listOf("① 周期读取军情/警报", "② 匹配掠夺、夺取、攻城、敌军等关键字", "③ 命中后通知、记录，撤防动作仍需二次确认")
        ConfigCategory.MINING -> listOf("① 设置资源类型和搜索范围", "② 找矿并按等级/距离筛选", "③ 派遣将领占矿或采集", "④ 到时召回或继续下一轮")
        ConfigCategory.MINISTRY -> listOf("① 检查资源与建筑队列", "② 执行内政/科技/任务规则", "③ 产出任务日志供用户确认")
        ConfigCategory.COMMON -> listOf("① 账号处理与免 Root 登录", "② 后台挂机启动与运行", "③ 一键日常、批量工具、防封参数")
        ConfigCategory.ROLE -> emptyList()
    }

    private fun moduleBelongsTo(category: ConfigCategory, spec: ScreenSpec): Boolean {
        val id = spec.featureId
        val name = spec.featureNameZh
        return when (category) {
            ConfigCategory.ROLE -> id in setOf("account_processing", "general", "inventory", "treasure_filter")
            ConfigCategory.MILITARY -> id in setOf("formation_troop", "general", "surrender_release", "dungeon") || name.contains("配兵") || name.contains("将领") || name.contains("副本")
            ConfigCategory.SHUA_HUANG -> id in setOf("shua_huang", "treasure_filter", "famous_general_filter") || name.contains("刷黄") || name.contains("山贼")
            ConfigCategory.WAR_INFO -> id in setOf("alarm_withdraw", "resource_point_send_general") || name.contains("警报") || name.contains("军情") || name.contains("撤防")
            ConfigCategory.MINING -> id in setOf("auto_mining", "mine_search", "resource_point_send_general") || name.contains("矿") || name.contains("资源点")
            ConfigCategory.MINISTRY -> id in setOf("internal_affairs") || name.contains("内政")
            ConfigCategory.COMMON -> id in setOf("account_processing", "guaji_start", "guaji_runtime", "daily_basic", "daily_main", "vip", "batch_guaji_antiban", "open_server_query", "bulk_tools", "auto_loot") || name.contains("挂机") || name.contains("日常") || name.contains("账号") || name.contains("工具")
        }
    }

    private fun showScreen(spec: ScreenSpec) {
        val saved = configRepo.loadFeatureConfig(activeAccountId(), spec.featureId)
        val rendered = ScreenSpecRenderer(this).render(spec, saved) { action ->
            showTopToast("真实执行接口未启用：$action")
        }
        rendered.root.addView(outlineButton("← 返回配置") { showHome(HomeTab.CONFIG) }, 0)
        rendered.root.addView(primaryButton("保存此页面配置") {
            if (spec.featureId == "account_processing") {
                showTopToast("账号数据请通过添加账号写入")
            } else {
                val collected = rendered.collectValues()
                configRepo.saveFeatureConfig(activeAccountId(), spec.featureId, collected)
                showTopToast("保存设置成功")
            }
        }, 1)
        setTabbedPage(rendered.root, HomeTab.CONFIG)
    }

    @Deprecated("Use explicit in-screen back button for this app")
    override fun onBackPressed() {
        showHome(HomeTab.OVERVIEW)
    }

    private fun setTabbedPage(contentRoot: LinearLayout, activeTab: HomeTab) {
        val scroll = ScrollView(this).apply {
            setBackgroundColor(COLOR_BG)
            addView(contentRoot)
        }
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(COLOR_BG)
            addView(scroll, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f
            ))
            addView(bottomTabBar(activeTab))
        }
        setContentView(shell)
    }

    private fun bottomTabBar(activeTab: HomeTab): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER
        setPadding(dp(8), dp(6), dp(8), dp(24))
        background = roundedStroke(Color.WHITE, 18f, COLOR_BORDER)
        elevation = dp(6).toFloat()
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(78)
        )
        // Desktop/mobile reference has exactly three persistent destinations. Logs stay
        // available through the black assistant log panel, matching its hidden quick
        // switch without introducing a fourth bottom item.
        listOf(HomeTab.CONFIG, HomeTab.OVERVIEW, HomeTab.HOSTING).forEach { tab ->
            addView(tabButton(tab, tab == activeTab))
        }
    }

    private fun tabButton(tab: HomeTab, active: Boolean): TextView = TextView(this).apply {
        text = when (tab) {
            HomeTab.CONFIG -> "⌂\n${tab.title}"
            HomeTab.OVERVIEW -> "▦\n${tab.title}"
            HomeTab.HOSTING -> "⌂\n${tab.title}"
            HomeTab.LOGS -> "☰\n${tab.title}"
        }
        gravity = Gravity.CENTER
        textSize = if (active) 15f else 14f
        typeface = if (active) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
        setTextColor(if (active) COLOR_PRIMARY else COLOR_SUBTEXT)
        background = if (active) rounded(Color.rgb(235, 242, 255), 14f) else rounded(Color.WHITE, 14f)
        setOnClickListener { showHome(tab) }
        layoutParams = LinearLayout.LayoutParams(
            0,
            ViewGroup.LayoutParams.MATCH_PARENT,
            1f
        ).apply { setMargins(dp(3), 0, dp(3), 0) }
    }

    private fun loadLocalAssetSummary(): String {
        return try {
            val screenCount = screenRepo.loadAll().size
            val guideRepo = LocalGuideRepository(this)
            val generalCount = guideRepo.loadFamousGenerals().size
            val guideCount = guideRepo.loadGuideArticles().size
            val configCount = configRepo.exportAll().optJSONObject("configs")?.length() ?: 0
            val accountCount = accountRepo.listAccounts().count { it.session?.sourceMode == 1 }
            val logCount = logRepo.recent(200).size
            "页面 $screenCount · 名将 $generalCount · 攻略 $guideCount · 账号 $accountCount · 配置 $configCount · 日志 $logCount"
        } catch (t: Throwable) {
            "本地静态资产读取失败：${t.message}"
        }
    }

    private fun accountSummary(): String = assistantAccountDisplay().accountSummary

    private fun latestLogSummary(): String {
        val logs = logRepo.recent(20)
        if (logs.isEmpty()) return "日志：暂无后台任务日志。"
        val last = logs.firstOrNull()?.message.orEmpty().take(36)
        return "日志：最近 ${logs.size} 条 · 最新：$last"
    }

    private fun logsPage(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        addView(pageTitle("日志"))
        addView(card().apply {
            addView(sectionTitle("运行日志"))
            addView(bodyText("与电脑端一样区分账号日志和系统日志；账号动作、任务与配置进入账号日志，服务、网络和云端状态进入系统日志。"))
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                LogCategory.values().forEach { category ->
                    addView(TextView(this@MainActivity).apply {
                        text = category.title
                        gravity = Gravity.CENTER
                        textSize = 15f
                        typeface = if (activeLogCategory == category) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
                        setTextColor(if (activeLogCategory == category) Color.WHITE else COLOR_PRIMARY)
                        background = if (activeLogCategory == category) {
                            rounded(COLOR_PRIMARY, 8f)
                        } else {
                            roundedStroke(Color.WHITE, 8f, COLOR_PRIMARY)
                        }
                        setOnClickListener {
                            activeLogCategory = category
                            showHome(HomeTab.LOGS)
                        }
                    }, LinearLayout.LayoutParams(0, dp(46), 1f).apply {
                        setMargins(dp(3), dp(8), dp(3), 0)
                    })
                }
            })
            if (activeLogCategory == LogCategory.ACCOUNT) {
                val accounts = realProtocolAccounts()
                val options = listOf("全部账号") + accounts.map { account ->
                    val role = account.session?.channelExtra?.get("roleName")
                        ?.takeIf { it.isNotBlank() }
                        ?: account.monarchName
                        ?: account.username
                    "$role · ${account.serverName}"
                }
                val accountIds = listOf<Long?>(null) + accounts.map { it.id }
                addView(designRow("账号筛选：", Spinner(this@MainActivity).apply {
                    adapter = compactSpinnerAdapter(options)
                    val selectedIndex = accountIds.indexOf(selectedLogAccountId).takeIf { it >= 0 } ?: 0
                    setSelection(selectedIndex, false)
                    onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                        override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                            val next = accountIds.getOrNull(position)
                            if (next != selectedLogAccountId) {
                                selectedLogAccountId = next
                                showHome(HomeTab.LOGS)
                            }
                        }

                        override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                    }
                }))
            }
            addView(outlineButton("清空${activeLogCategory.title}") {
                logRepo.clearWhere { entry ->
                    logCategory(entry) == activeLogCategory &&
                        (
                            activeLogCategory != LogCategory.ACCOUNT ||
                                selectedLogAccountId == null ||
                                entry.accountId == selectedLogAccountId
                            )
                }
                showTopToast("${activeLogCategory.title}已清空")
                showHome(HomeTab.LOGS)
            })
        })
        val logs = filteredLogs()
        lastRenderedLogFingerprint = logFingerprint()
        addView(card().apply {
            if (logs.isEmpty()) {
                addView(emptyText("暂无${activeLogCategory.title}"))
            } else {
                logs.forEach { item ->
                    addView(TextView(this@MainActivity).apply {
                        val accountLabel = item.accountId?.let { " [账号#$it]" }.orEmpty()
                        text = "${formatLogTime(item.timeMillis)}  [${item.tag}]$accountLabel\n${item.message}"
                        textSize = 12.5f
                        setTextColor(COLOR_TEXT)
                        setLineSpacing(3f, 1f)
                        setPadding(dp(10), dp(8), dp(10), dp(8))
                        background = roundedStroke(Color.rgb(248, 250, 253), 8f, COLOR_BORDER)
                    }, LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT
                    ).apply { setMargins(0, 0, 0, dp(8)) })
                }
            }
        })
    }

    private fun filteredLogs(): List<TaskLogEntry> =
        logRepo.recent(200)
            .asSequence()
            .filter { logCategory(it) == activeLogCategory }
            .filter {
                activeLogCategory != LogCategory.ACCOUNT ||
                    selectedLogAccountId == null ||
                    TaskLogAccountResolver.matches(it, selectedLogAccountId)
            }
            .take(100)
            .toList()

    private fun logFingerprint(): String =
        filteredLogs().let { logs ->
            "${activeLogCategory.name}:${selectedLogAccountId ?: 0}:${logs.size}:" +
                (logs.firstOrNull()?.let { "${it.timeMillis}:${it.tag}:${it.message.hashCode()}" } ?: "empty")
        }

    private fun logCategory(entry: TaskLogEntry): LogCategory {
        val systemTags = setOf("cloud-map", "system", "network", "service", "boot", "vpn")
        val systemMessage = listOf(
            "service created",
            "service destroyed",
            "local scheduling started",
            "local scheduling stopped",
            "network ",
            "云端连接"
        ).any { marker -> entry.message.contains(marker, ignoreCase = true) }
        return if (entry.tag in systemTags || systemMessage) LogCategory.SYSTEM else LogCategory.ACCOUNT
    }

    private fun formatLogTime(timeMillis: Long): String =
        runCatching {
            SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date(timeMillis))
        }.getOrDefault(timeMillis.toString())

    private fun showTopToast(message: String, duration: Int = Toast.LENGTH_SHORT) {
        Toast.makeText(this@MainActivity, message, duration).apply {
            setGravity(Gravity.TOP or Gravity.CENTER_HORIZONTAL, 0, dp(56))
        }.show()
    }


    private fun activeAccountId(): Long =
        selectedAccount()?.id
            ?: accountRepo.listAccounts().firstOrNull { it.session?.sourceMode == 1 }?.id
            ?: DEFAULT_ACCOUNT_ID

    private data class ConfigNavItem(
        val label: String,
        val featureId: String? = null,
        val custom: String? = null
    )

    private data class FormationDraftRow(
        val enabled: Boolean = false,
        val generalId: Long? = null,
        val soldierType: String = "民兵",
        val soldierCount: Int = 3000
    )

    private data class ShuaHuangDraftRow(
        val enabled: Boolean = false,
        val generalId: Long? = null,
        val level: Int = 1,
        val drops: Set<String> = setOf("装备"),
        val maxFoot: Int = 0,
        val maxBow: Int = 0,
        val maxCavalry: Int = 0,
        val maxChariot: Int = 0
    ) {
        val drop: String
            get() = drops.firstOrNull().orEmpty()

        val dropLabel: String
            get() = drops.joinToString("、").ifBlank { "不限" }

        val compositionCode: String
            get() = "${maxFoot.coerceIn(0, 5)}${maxBow.coerceIn(0, 5)}${maxCavalry.coerceIn(0, 5)}${maxChariot.coerceIn(0, 5)}"
    }

    private data class MineDraftRow(
        val enabled: Boolean = false,
        val generalIds: List<Long> = emptyList(),
        val resourceType: String = "金矿",
        val x: Int = 0,
        val y: Int = 0,
        val scope: String = "附近"
    )

    private data class LootDraftRow(
        val enabled: Boolean = false,
        val generalIds: List<Long> = emptyList(),
        val playerName: String = "",
        val fiefIndex: Int = 1
    )

    private data class LootGeneralPickerState(
        val selectedIds: MutableSet<Long>,
        val button: Button
    )

    private data class FutureMilitaryDraftRow(
        val enabled: Boolean = false,
        val generalIds: List<Long> = emptyList(),
        val option: String
    )

    companion object {
        private const val DEFAULT_ACCOUNT_ID = 1L
        private const val REQUEST_NOTIFICATION_PERMISSION = 1002
        private const val LOG_REFRESH_INTERVAL_MS = 2_000L
        private val TECHNOLOGY_NAMES = listOf(
            "工程设计", "征召技巧", "种植技术", "行军技巧",
            "市场贸易", "建筑学", "铸铁技术", "甲胄制造",
            "药草研究", "阵法技巧", "抛射技巧", "驾驭技巧",
            "战车设计", "统帅能力", "信仰", "仓储",
            "安置", "格斗", "精准", "驯马", "精工", "悬赏"
        )
    }
}

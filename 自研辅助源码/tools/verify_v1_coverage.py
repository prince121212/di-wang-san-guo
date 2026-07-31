#!/usr/bin/env python3
"""Static/build audit for the phone-local V1 architecture."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
SRC = APP / "src/main/java/com/example/dwpmclone"
DEBUG_SRC = APP / "src/debug/java/com/example/dwpmclone"
MANIFEST = APP / "src/main/AndroidManifest.xml"
APK = APP / "build/outputs/apk/debug/app-debug.apk"
FRONTEND = ROOT.parent / "电脑端辅助前端"
REPORT_MD = ROOT / "reports/v1_coverage_report.md"
REPORT_JSON = ROOT / "reports/v1_coverage_report.json"
TEST_RESULTS = APP / "build/test-results/testDebugUnitTest"
TEST_SRC = APP / "src/test/java/com/example/dwpmclone"

MANUAL_ACCEPTANCE_REQUIRED = [
    "副本、刷黄、无损、掠夺和打矿逐功能真机动作证据",
    "锁屏连续运行超过 6 小时",
    "Wi-Fi/移动数据切换、短时断网和真实 Session 过期恢复",
    "Activity/WebView 关闭后托管继续运行",
    "手机重启并首次解锁后的托管恢复",
    "真实托管期间抓包确认只访问游戏服务器",
]

FORBIDDEN_PRODUCTION_SYMBOLS = {
    "RemoteCoreActivity",
    "RemoteCoreKeepAliveService",
    "DesktopCoreApiClient",
    "DesktopCoreSettingsRepository",
    "LocalProxyVpnService",
    "GameNetworkRoute",
    "CollaborativeMap",
    "CloudFirstMapCoordinator",
}

REQUIRED_LOCAL_ROUTES = {
    "/api/health",
    "/api/accounts",
    "/api/areas",
    "/api/accounts/settings",
    "/api/accounts/add",
    "/api/accounts/start",
    "/api/accounts/stop",
    "/api/accounts/delete",
    "/api/logs/system",
    "/api/logs/account",
    "/api/logs/system/clear",
    "/api/success-records",
    "/api/automation/status",
    "/api/automation/start-saved",
    "/api/automation/stop",
    "/api/state/refresh",
    "/api/formations/save",
    "/api/formations/unassign-all",
    "/api/raid/execute",
    "/api/raid/fiefs",
    "/api/mine/save",
    "/api/mine/search",
    "/api/mine/execute",
    "/api/liubu/save",
    "/api/lossless/execute",
    "/api/dungeon/execute",
    "/api/settings/save",
    "/api/brush/search",
    "/api/brush/execute",
    "/api/brush/recommended-center",
    "/api/daily/general-visit/candidates",
    "/api/notices/dismiss",
    "/api/maps/bandits",
    "/api/maps/mines",
}

ALLOWED_PERMISSIONS = {
    "android.permission.INTERNET",
    "android.permission.FOREGROUND_SERVICE",
    "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.WAKE_LOCK",
    "android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
    "android.permission.RECEIVE_BOOT_COMPLETED",
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.VIBRATE",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def command(args: list[str], timeout: int = 30) -> tuple[int, str]:
    env = os.environ.copy()
    bundled_jdk = Path.home() / ".cache/codex-jdks/zulu17/zulu-17.jdk/Contents/Home"
    homebrew_jdk = Path("/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home")
    java_home = bundled_jdk if bundled_jdk.exists() else homebrew_jdk
    if java_home.exists():
        env["JAVA_HOME"] = str(java_home)
        env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip()
    except Exception as error:
        return 999, str(error)


def unit_test_summary() -> tuple[int, int, int, int]:
    tests = failures = errors = skipped = 0
    for path in TEST_RESULTS.glob("TEST-*.xml"):
        suite = ET.parse(path).getroot()
        tests += int(suite.attrib.get("tests", 0))
        failures += int(suite.attrib.get("failures", 0))
        errors += int(suite.attrib.get("errors", 0))
        skipped += int(suite.attrib.get("skipped", 0))
    return tests, failures, errors, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Static/build audit for the phone-local V1 architecture")
    parser.add_argument(
        "--skip-device",
        action="store_true",
        help="Do not invoke adb; record real-device checks as intentionally pending",
    )
    args = parser.parse_args()
    source_files = sorted(SRC.rglob("*.kt"))
    production_source = "\n".join(read(path) for path in source_files)
    manifest = read(MANIFEST)
    activity = read(SRC / "AssistantWebActivity.kt")
    controller = read(SRC / "ui/web/LocalAssistantApiController.kt")
    operations = read(SRC / "ui/web/LocalProtocolOperationService.kt")
    operation_runner = read(SRC / "ui/web/LocalProtocolOperationRunner.kt")
    bridge = read(SRC / "ui/web/AssistantWebBridge.kt")
    service = read(SRC / "service/AssistantForegroundService.kt")
    scheduler_factory = read(SRC / "domain/scheduler/SavedConfigTaskPlanFactory.kt")
    task_factory = read(SRC / "domain/scheduler/TaskFactory.kt")
    settings_mapper = read(SRC / "ui/web/LocalSettingsConfigMapper.kt")
    suppression_registry = read(SRC / "domain/scheduler/TaskRunSuppressionRegistry.kt")
    runtime_repository = read(SRC / "data/local/TaskRuntimeStatusRepository.kt")
    account_repository = read(SRC / "data/local/LocalAccountRepository.kt")
    credential_vault = read(SRC / "data/local/CredentialVault.kt")
    session_secret_vault = read(SRC / "data/local/SessionSecretVault.kt")
    keystore_store = read(SRC / "data/local/KeystoreAesGcmStore.kt")
    redactor = read(SRC / "data/local/SensitiveDataRedactor.kt")
    task_logs = read(SRC / "data/local/TaskLogRepository.kt")
    success_policy = read(SRC / "data/local/TaskSuccessRecordPolicy.kt")
    lifecycle_policy = read(SRC / "domain/protocol/AccountLifecyclePresentation.kt")
    account_lock = read(SRC / "domain/state/AccountOperationLockRegistry.kt")
    permission_coordinator = read(SRC / "ui/hosting/BackgroundHostingPermissionCoordinator.kt")
    notification_text = read(SRC / "domain/scheduler/HostingNotificationText.kt")
    health_sink = read(SRC / "data/protocol/GameRequestHealthSink.kt")
    session_client = read(SRC / "data/protocol/SessionAwareGameProtocolClient.kt")
    unsupported_client = read(SRC / "data/protocol/UnsupportedSessionProtocolClient.kt")
    real_protocol = read(SRC / "data/protocol/RealGameProtocolClient.kt")
    front_app = read(FRONTEND / "app.js")
    front_bridge = read(FRONTEND / "assistant-api.js")
    front_index = read(FRONTEND / "index.html")
    gradle = read(APP / "build.gradle.kts")

    checks: list[dict[str, object]] = []

    def add(name: str, ok: bool, evidence: str, severity: str = "error") -> None:
        checks.append({
            "name": name,
            "ok": bool(ok),
            "severity": severity,
            "evidence": evidence,
        })

    forbidden_hits = sorted(symbol for symbol in FORBIDDEN_PRODUCTION_SYMBOLS if symbol in production_source or symbol in manifest)
    add("生产源码不含远程核心、代理或协作地图实现", not forbidden_hits, f"hits={forbidden_hits or 'none'}")

    add(
        "正式入口只有手机本地 WebView 容器",
        manifest.count("<activity") == 1
        and ".AssistantWebActivity" in manifest
        and "file:///android_asset/assistant/" in activity
        and "mobile=1&local=1" in activity,
        "single AssistantWebActivity + packaged assistant assets",
    )
    add(
        "WebView 阻断外部导航与外部子资源",
        "startsWith(ASSET_PREFIX)" in activity
        and "allowContentAccess = false" in activity
        and "mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW" in activity,
        "LocalAssetWebViewClient + restricted WebSettings",
    )
    add(
        "本机桥异步串行执行，页面线程不访问仓库",
        "newSingleThreadExecutor" in bridge and "webView.post" in bridge,
        "AssistantWebBridge single worker",
    )

    local_route_sources = controller + "\n" + operations
    missing_routes = sorted(route for route in REQUIRED_LOCAL_ROUTES if route not in local_route_sources)
    add("手机单账号页面所需本地接口已接入", not missing_routes, f"missing={missing_routes or 'none'}")
    add(
        "前端 API 请求由本机桥截获",
        "window.DWPMNativeApi" in front_bridge
        and 'url.pathname.startsWith("/api/")' in front_bridge
        and "nativeRequest(method" in front_bridge,
        "assistant-api.js intercepts /api/*",
    )
    add(
        "手机模式移除电脑工具栏与代理控件且不请求代理节点",
        "isMobileLocal" in front_app
        and 'document.getElementById("desktopToolbar")?.remove()' in front_app
        and 'document.querySelector(".proxy-line")?.remove()' in front_app
        and "if (isMobileLocal) return false" in front_app,
        "single local mobile container",
    )
    add(
        "延期功能在页面置灰且 API 失败关闭",
        'new Set(["抢城", "押镖", "寻宝", "连体物品"])' in front_app
        and "feature-deferred" in front_app
        and "aria-disabled" in front_app
        and '"common.chain" -> throw IllegalArgumentException' in settings_mapper
        and "当前版本暂不实现，设置未保存" in settings_mapper,
        "抢城/押镖/寻宝/连体物品：UI disabled + settings mapper rejection",
    )

    add(
        "前台服务是唯一正式调度宿主",
        manifest.count("<service") == 1
        and ".service.AssistantForegroundService" in manifest
        and "TaskScheduler(" in service
        and "planForRealAccount" in service,
        "specialUse AssistantForegroundService",
    )
    add(
        "后台调度按任务期限唤醒并在长等待时释放 WakeLock",
        "SchedulerTickPolicy" in service
        and "setAndAllowWhileIdle" in service
        and "releaseWakeLock()" in service
        and "TICK_INTERVAL_MS" not in service,
        "adaptive deadline + inexact wakeup alarm",
    )
    add(
        "正式调度只接受启用的真实 Session",
        "if (!account.enabled || session.sourceMode != 1) return null" in scheduler_factory,
        "SavedConfigTaskPlanFactory.planForRealAccount",
    )
    add(
        "生产源码不生成 mock Session 或 mock token",
        "MockTaskPlanFactory" not in production_source
        and "BaseMockTask" not in production_source
        and "MockTask" not in production_source
        and "mock-token" not in production_source
        and not (SRC / "data/protocol/MockGameProtocolClient.kt").exists(),
        "mock client is excluded from main source set",
    )
    add(
        "非真实 Session 与未完成动作在生产协议边界失败关闭",
        "UnsupportedSessionProtocolClient()" in session_client
        and 'code = "NON_REAL_SESSION_REJECTED"' in unsupported_client
        and "REAL_WITHDRAW_MINE_GATE_NOT_READY" in session_client
        and "buildDirectGameHex(withdrawContract.requestOpcode" in session_client
        and "withdrawContract.responseOpcode" in session_client
        and "offlineActionFixturesAllowed: Boolean = false" in session_client,
        "production fallback rejects non-real sessions; real withdrawal is gate/receipt protected; offline fixtures default off",
    )
    add(
        "本地配置已使用 V1 正式 schema",
        'EXPORT_SCHEMA_VERSION = "1.0-local"' in read(SRC / "data/local/LocalConfigRepository.kt"),
        "schema_version=1.0-local",
    )
    add(
        "Mock 协议客户端只存在于 debug 构建",
        (DEBUG_SRC / "data/protocol/MockGameProtocolClient.kt").exists(),
        "app/src/debug/.../MockGameProtocolClient.kt",
    )

    tls_bypass_patterns = {
        "X509TrustManager": r"\bX509TrustManager\b",
        "HostnameVerifier": r"\bHostnameVerifier\b",
        "trust-all": r"(?i)trust[_ -]?all",
        "custom hostname verifier": r"(?i)(?:setDefaultHostnameVerifier|hostnameVerifier\s*=)",
        "custom SSL socket factory": r"(?i)(?:setDefaultSSLSocketFactory|sslSocketFactory\s*=)",
        "empty certificate check": r"\bcheckServerTrusted\b|\bcheckClientTrusted\b",
    }
    tls_bypass_hits = sorted(
        name for name, pattern in tls_bypass_patterns.items()
        if re.search(pattern, production_source)
    )
    add(
        "TLS 使用 Android 平台证书链与主机名校验",
        not tls_bypass_hits
        and "url.openConnection() as HttpURLConnection" in real_protocol
        and "disconnect()" in real_protocol,
        f"bypass_hits={tls_bypass_hits or 'none'}; connections explicitly disconnected",
    )

    add(
        "密码与 Session 秘密使用 Keystore AES-GCM 密文同步落盘",
        "AndroidKeyStore" in keystore_store
        and "AES/GCM/NoPadding" in keystore_store
        and ".setRandomizedEncryptionRequired(true)" in keystore_store
        and ".commit()" in keystore_store
        and "KeystoreAesGcmStore" in credential_vault
        and "KeystoreAesGcmStore" in session_secret_vault
        and "dwpm_local_credentials_v2" in credential_vault
        and "dwpm_local_session_v2" in session_secret_vault
        and "setUnlockedDeviceRequired" not in keystore_store
        and 'android:allowBackup="false"' in manifest,
        "AndroidKeyStore + AES/GCM + V2 alias rotation + commit; key usable during lockscreen hosting; backup disabled",
    )
    account_serializer = account_repository[account_repository.find("private fun GameAccount.toJson"):]
    plaintext_account_fields = sorted(set(re.findall(
        r'\.put\("(encryptedPassword|password|dm|userId|accountWithSuffix|sessionToken|accessToken|authToken|cookie|gameAuthSign)"',
        account_serializer,
    )))
    add(
        "账号 JSON 与导出文件不序列化认证秘密",
        not plaintext_account_fields
        and "SessionSecretPolicy.publicFields(channelExtra)" in account_serializer
        and "SESSION_PRESENT_MARKER" in account_serializer
        and "SessionSecretPolicy.secretFields" in account_repository,
        f"plaintext_serializer_fields={plaintext_account_fields or 'none'}; secret vault separated",
    )
    delete_secret_first = controller.find("credentialVault.delete(account.id)")
    delete_metadata_after = controller.find("accounts.delete(account.id)")
    add(
        "删除账号同步删除密码与 Session 密文",
        delete_secret_first >= 0
        and delete_metadata_after > delete_secret_first
        and "sessionSecrets.delete(accountId)" in account_repository,
        "credential vault and session-secret vault are cleared before/with account metadata",
    )
    add(
        "手机添加账号自动保存重登凭据且不增加安全确认门槛",
        'type="password" value=""' in front_index
        and "credentialConsent" not in front_app
        and "credentialConsent" not in controller
        and "credentialVault.hasPassword(account.id)" in controller
        and "credentials.savePassword(account.id, password)" in read(SRC / "data/account/LocalAccountLoginService.kt")
        and 'document.getElementById("loginPassword").value = ""' in front_app,
        "automatic local persistence + password field clearing + relogin availability gate",
    )
    direct_log_files = sorted(
        str(path.relative_to(ROOT))
        for path in source_files
        if path.name != "TaskLogRepository.kt"
        and re.search(r"\bLog\.[vdiwe]\s*\(|android\.util\.Log\.", read(path))
    )
    add(
        "日志统一经过敏感字段脱敏边界",
        not direct_log_files
        and "SensitiveDataRedactor.redact(message)" in task_logs
        and all(field in redactor for field in ("password", "tokenCiphertext", "dm", "gameHttp", "cookie")),
        f"direct_log_files={direct_log_files or 'none'}; TaskLogRepository redacts before Log/persistence",
    )

    add(
        "通知与电池优化权限只在用户启动托管后请求",
        "requestForStartedHosting" in permission_coordinator
        and "Manifest.permission.POST_NOTIFICATIONS" in permission_coordinator
        and "ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" in permission_coordinator
        and "runCatching { onHostingStarted() }" in controller
        and "hostingPermissions.requestForStartedHosting()" in activity,
        "startAccount callback -> normal Android permission/settings flows",
    )
    add(
        "前台通知显示账号与当前任务并保留停止入口",
        'return "账号：$accountText · 当前：$taskText"' in notification_text
        and "HostingNotificationText.format" in service
        and '"停止托管"' in service
        and "setAction(ACTION_STOP)" in service,
        "HostingNotificationText + ACTION_STOP notification action",
    )

    add(
        "任务停止锁与绝对截止时间可跨进程恢复",
        "fun restore(" in suppression_registry
        and 'MessageDigest.getInstance("SHA-256")' in suppression_registry
        and "TaskRuntimeState.SERVICE_STOPPED" in suppression_registry
        and "nextRunAtMillis" in runtime_repository
        and "KEY_CONFIG_SIGNATURE" in runtime_repository
        and ".commit()" in runtime_repository
        and "taskSuppressions.restore(" in service
        and "taskRuntimeStatuses.setConfigurationSignature(signature)" in service,
        "persisted deadline + config signature + restore before scheduler filtering",
    )
    add(
        "六部确认功能已进入本地调度，撤防仅允许真实回执路径",
        "SixMinistriesTask" in task_factory
        and "sixMinistries" in task_factory
        and "class SixMinistriesTask" in production_source
        and "TaskType.SIX_MINISTRIES" in production_source
        and "withdrawDefense = false" not in scheduler_factory
        and "REAL_WITHDRAW_MINE_RESPONSE_MISSING" in session_client
        and 'put("supportedEnabled", supported)' in settings_mapper
        and "MinistryProtocolCrop.VERIFIED_NAME" in settings_mapper
        and "mobileDisabled" not in front_app
        and "金银花种植按已确认协议执行" in front_app,
        "verified ministry planting/read-only scan scheduled locally; withdrawal still requires an exact receipt",
    )
    add(
        "账号关闭语义与持久化 Session 分离",
        "fun mayUseLiveSession" in lifecycle_policy
        and "internal restart credential" in lifecycle_policy
        and "AccountLifecyclePresentationPolicy.mayUseLiveSession" in operation_runner
        and '"LOCAL_ACCOUNT_NOT_RUNNING"' in operation_runner,
        "stopped/offline accounts may retain reconnect state but cannot expose or execute it",
    )
    add(
        "页面与后台共用账号级请求锁",
        "ReentrantLock(true)" in account_lock
        and "fun tryAcquire" in account_lock
        and "AccountOperationLockRegistry.tryAcquire(accountId)" in operation_runner
        and "AccountOperationLockRegistry.acquire(accountId)" in service
        and "AccountOperationLockRegistry.release(accountId)" in service,
        "manual UI fails fast while scheduler owns the account; different accounts use different locks",
    )
    add(
        "日志使用 JSONL 单调游标与结构化成功事实",
        'FILE_NAME = "task_logs_v2.jsonl"' in task_logs
        and "file.appendText" in task_logs
        and "MAX_LOGS = 1_500" in task_logs
        and "TaskLogCursorPolicy.nextId" in task_logs
        and "successCategory" in task_logs
        and "generic words" in success_policy
        and "TaskSuccessRecordPolicy.resolve" in controller,
        "bounded append-only log + monotonic id + explicit successCategory/successMessage",
    )
    recommended_center_source = operations[
        operations.find("private fun recommendedBrushCenter"):operations.find("private fun mineSearch")
    ]
    add(
        "刷黄推荐中心来自登录封地坐标且禁止假默认值",
        "ownedFiefLocations" in real_protocol
        and "BrushCenterRecommendationPolicy.recommend" in recommended_center_source
        and "login-owned-fief-cache" in recommended_center_source
        and "?: 91" not in recommended_center_source,
        "0x1310/0x8310 login cache + majority-fief policy; missing coordinates fail",
    )
    add(
        "多账号请求健康记录按执行线程绑定账号",
        "ThreadLocal<Long>()" in health_sink
        and "fun bindAccount" in health_sink
        and "fun clearAccount" in health_sink
        and "GameRequestHealthSink.bindAccount(accountId)" in service
        and "GameRequestHealthSink.clearAccount()" in service,
        "thread-local account attribution around each serialized account run",
    )

    required_local_components = {
        "KeystoreCredentialVault": SRC / "data/local/CredentialVault.kt",
        "AccountSessionRecovery": SRC / "data/account/AccountSessionRecovery.kt",
        "ExpeditionPreflight": SRC / "domain/protocol/ExpeditionPreflight.kt",
        "ExpeditionTransactionRepository": SRC / "data/local/ExpeditionTransactionRepository.kt",
        "LocalMapRepository": SRC / "data/local/LocalMapRepository.kt",
        "LocalTargetCache": SRC / "domain/localmap/LocalTargetCache.kt",
    }
    missing_components = sorted(name for name, path in required_local_components.items() if not path.exists() or name not in read(path))
    add("登录恢复、出征事务和本地地图组件齐全", not missing_components, f"missing={missing_components or 'none'}")
    add(
        "开机恢复只指向手机本地前台服务",
        ".service.BootCompletedReceiver" in manifest
        and "AssistantForegroundService" in read(SRC / "service/BootCompletedReceiver.kt")
        and "USER_UNLOCKED" in manifest,
        "BootCompletedReceiver -> local service after unlock",
    )

    permissions = set(re.findall(r'<uses-permission android:name="([^"]+)"', manifest))
    add("Manifest 权限保持最小集合", permissions <= ALLOWED_PERMISSIONS, f"extra={sorted(permissions - ALLOWED_PERMISSIONS) or 'none'}")
    add(
        "Manifest 不声明 VPN、Wi-Fi 修改或网络修改权限",
        not permissions.intersection({
            "android.permission.BIND_VPN_SERVICE",
            "android.permission.CHANGE_WIFI_STATE",
            "android.permission.ACCESS_WIFI_STATE",
            "android.permission.CHANGE_NETWORK_STATE",
        }),
        f"permissions={sorted(permissions)}",
    )
    add(
        "旧原生页面规格和云地图 mock 已删除",
        not (APP / "src/main/assets/screen_specs.json").exists()
        and not (ROOT / "tools/cloud_map_mock_server.py").exists(),
        "unused screen_specs + cloud map tool absent",
    )
    add(
        "构建仅打包共用前端静态文件",
        'include("index.html", "app.js", "styles.css", "assistant-api.js")' in gradle,
        "syncAssistantWebAssets allow-list",
    )

    apk_exists = APK.exists() and APK.stat().st_size > 0
    add("Debug APK 已产出", apk_exists, f"{APK} size={APK.stat().st_size if apk_exists else 0}")
    if apk_exists:
        rc, apk_manifest = command(["apkanalyzer", "manifest", "print", str(APK)])
        manifest_evidence = re.sub(r"\s+", " ", apk_manifest[:400]).strip() if apk_manifest else "apkanalyzer failed"
        add("APK Manifest 可解析", rc == 0, manifest_evidence)
        add("APK 版本标识为 V0.0.15", 'android:versionName="V0.0.15"' in apk_manifest, "versionName=V0.0.15")
        add("APK 启动 Activity 为本地容器", "com.example.dwpmclone.AssistantWebActivity" in apk_manifest, "AssistantWebActivity")

    tests, failures, errors, skipped = unit_test_summary()
    add(
        "最近一次 Android 单测全绿",
        tests > 0 and failures == 0 and errors == 0,
        f"tests={tests} failures={failures} errors={errors} skipped={skipped}",
        severity="warning" if tests == 0 else "error",
    )
    required_regression_tests = {
        "SensitiveDataRedactorTest.kt",
        "SessionSecretPolicyTest.kt",
        "GameRequestHealthSinkTest.kt",
        "HostingNotificationTextTest.kt",
        "TaskRunSuppressionRegistryTest.kt",
        "LocalSettingsConfigMapperTest.kt",
        "SavedConfigTaskPlanFactoryTest.kt",
    }
    present_regression_tests = {path.name for path in TEST_SRC.rglob("*Test.kt")}
    missing_regression_tests = sorted(required_regression_tests - present_regression_tests)
    add(
        "安全、持久化和未开放动作边界均有回归测试",
        not missing_regression_tests and tests > 0 and failures == 0 and errors == 0,
        f"missing={missing_regression_tests or 'none'}; covered by green Android suite",
    )

    if args.skip_device:
        add(
            "真机连接检查已按参数跳过",
            True,
            "--skip-device: adb was not invoked; real-device regression remains pending",
            severity="warning",
        )
    else:
        rc, devices = command(["adb", "devices", "-l"])
        connected = rc == 0 and any(
            len(line.split()) >= 2 and line.split()[1] == "device"
            for line in devices.splitlines()[1:]
        )
        add("ADB 已连接设备，可继续安全真机回归", connected, devices or "(empty)", severity="warning")
    add(
        "破坏性或长时间真机验收尚需显式授权",
        False,
        "；".join(MANUAL_ACCEPTANCE_REQUIRED),
        severity="warning",
    )

    success = all(bool(check["ok"]) for check in checks if check["severity"] == "error")
    result = {
        "success": success,
        "architecture": "phone-local-v1",
        "scope": "static-build-audit",
        "apk": str(APK),
        "checks": checks,
        "manual_acceptance_required": MANUAL_ACCEPTANCE_REQUIRED,
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 手机本地 V1 覆盖检查",
        "",
        f"- APK: `{APK}`",
        f"- 自动审计结论: {'通过' if success else '存在阻断项'}",
        "- 说明: 自动审计通过不等于 15 条真机验收全部完成。",
        "",
        "## 检查项",
        "",
    ]
    for check in checks:
        mark = "✅" if check["ok"] else ("⚠️" if check["severity"] == "warning" else "❌")
        lines.append(f"- {mark} **{check['name']}** — `{check['evidence']}`")
    lines += [
        "",
        "## 边界",
        "",
        "- V1 的账号、凭据、Session、配置、调度、游戏请求和地图均在手机本地完成。",
        "- 检查脚本不启动真实托管，不发送游戏动作。",
        "- 以下项目必须在用户明确授权测试账号和真机环境后验证：",
    ]
    lines.extend(f"  - {item}" for item in MANUAL_ACCEPTANCE_REQUIRED)
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT_MD)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

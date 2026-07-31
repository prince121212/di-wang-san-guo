package com.example.dwpmclone.host

import android.content.Context
import android.os.SystemClock
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.example.dwpmclone.data.account.AccountLifecycleDecision
import com.example.dwpmclone.data.account.AccountLifecycleDecisionSource
import com.example.dwpmclone.data.account.AccountStateTransition
import com.example.dwpmclone.data.account.AccountStateTransitionSource
import com.example.dwpmclone.data.account.AccountTransitionDetails
import com.example.dwpmclone.data.account.AccountTransitionInput
import com.example.dwpmclone.data.local.SharedAccountStateGateway
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import org.json.JSONObject

/** Process-wide Android host for the repository's single shared Python core. */
class SharedPythonCoreHost private constructor(context: Context) :
    AccountLifecycleDecisionSource,
    AccountStateTransitionSource,
    SharedAccountStateGateway {
    private val appContext = context.applicationContext
    private val platformPorts = AndroidSharedCorePortBridge(appContext)
    private val initializationLock = Any()
    private val warmupScheduled = AtomicBoolean(false)
    private val callCount = AtomicLong(0)
    private val totalCallMicros = AtomicLong(0)
    private val maxCallMicros = AtomicLong(0)

    @Volatile
    private var facade: PyObject? = null

    @Volatile
    private var pythonStartMillis: Long? = null

    @Volatile
    private var coreInitializationMillis: Long? = null

    @Volatile
    private var pythonVersion: String? = null

    @Volatile
    private var initializationError: String? = null

    fun warmUpAsync() {
        if (!warmupScheduled.compareAndSet(false, true)) return
        WARMUP_EXECUTOR.execute {
            runCatching { coreFacade() }
                .onFailure { error -> initializationError = error.message ?: error.javaClass.simpleName }
        }
    }

    fun health(): JSONObject = callJson("health_json")
        .put("androidPythonHost", metrics())

    fun dispatch(
        method: String,
        path: String,
        body: JSONObject = JSONObject(),
        requestContext: JSONObject = JSONObject()
    ): JSONObject = callJson(
        "dispatch_json",
        method,
        path,
        body.toString(),
        requestContext.toString()
    )

    override fun accountLifecycleDecision(
        accountEnabled: Boolean,
        executionOwnerActive: Boolean,
        loginState: String,
        sourceMode: Int,
        forceValidation: Boolean,
        lastValidatedAtMillis: Long?,
        nowMillis: Long
    ): AccountLifecycleDecision {
        val result = callJson(
            "account_lifecycle_snapshot_json",
            accountEnabled,
            executionOwnerActive,
            loginState,
            sourceMode,
            forceValidation,
            lastValidatedAtMillis ?: -1L,
            nowMillis
        )
        return AccountLifecycleDecision(
            status = result.getString("status"),
            statusText = result.getString("statusText"),
            started = result.getBoolean("started"),
            canonicalLoginState = result.getString("canonicalLoginState"),
            requiresRelogin = result.getBoolean("requiresRelogin"),
            shouldProbe = result.getBoolean("shouldProbe"),
            mayUseLiveSession = result.getBoolean("mayUseLiveSession"),
            runnable = result.getBoolean("runnable"),
            heartbeatIntervalMillis = result.getLong("heartbeatIntervalMillis")
        )
    }

    override fun accountStateTransition(
        state: AccountTransitionInput,
        event: String,
        details: AccountTransitionDetails,
        nowMillis: Long
    ): AccountStateTransition {
        val stateJson = JSONObject()
            .put("desiredStarted", state.desiredStarted)
            .put("loginState", state.loginState)
            .put("sessionCredentialPresent", state.sessionCredentialPresent)
            .put("failureKind", state.failureKind)
            .put("failureCount", state.failureCount)
            .put("nextRetryAtMillis", state.nextRetryAtMillis ?: JSONObject.NULL)
            .put("lastError", state.lastError)
            .put("lastValidatedAtMillis", state.lastValidatedAtMillis ?: JSONObject.NULL)
        val detailsJson = JSONObject()
            .put("message", details.message)
            .put("sessionInvalid", details.sessionInvalid)
            .put("validatedAtMillis", details.validatedAtMillis ?: JSONObject.NULL)
        val response = callJson(
            "account_transition_json",
            stateJson.toString(),
            event,
            detailsJson.toString(),
            nowMillis
        )
        check(response.optBoolean("ok", false)) {
            response.optJSONObject("error")?.optString("message")
                ?: "共享账号状态转换失败"
        }
        val result = response.getJSONObject("transition")
        return AccountStateTransition(
            desiredStarted = result.getBoolean("desiredStarted"),
            loginState = result.getString("loginState"),
            sessionCredentialPresent = result.getBoolean("sessionCredentialPresent"),
            liveSessionUsable = result.getBoolean("liveSessionUsable"),
            failureKind = result.getString("failureKind"),
            failureCount = result.getInt("failureCount"),
            nextRetryAtMillis = result.optLongOrNull("nextRetryAtMillis"),
            lastError = result.getString("lastError"),
            lastValidatedAtMillis = result.optLongOrNull("lastValidatedAtMillis"),
            nextOperation = result.getString("nextOperation"),
            sessionSecretAction = result.getString("sessionSecretAction"),
            event = result.getString("event"),
            updatedAtMillis = result.getLong("updatedAtMillis")
        )
    }

    override fun accountRecordsSnapshot(): JSONObject =
        callJson("account_records_snapshot_json")

    override fun accountRecordsPresentationSnapshot(): JSONObject =
        callJson("account_records_presentation_snapshot_json")

    override fun accountRecord(accountRef: String): JSONObject =
        callJson("account_record_json", accountRef)

    override fun accountRecordPresentation(accountRef: String): JSONObject =
        callJson("account_record_presentation_json", accountRef)

    override fun accountRecordUpsert(record: JSONObject): JSONObject =
        callJson("account_record_upsert_json", record.toString())

    override fun accountRecordsImportIfEmpty(records: org.json.JSONArray): JSONObject =
        callJson("account_records_import_if_empty_json", records.toString())

    override fun accountRecordsReplace(records: org.json.JSONArray): JSONObject =
        callJson("account_records_replace_json", records.toString())

    override fun accountRecordDelete(accountRef: String): JSONObject =
        callJson("account_record_delete_json", accountRef)

    override fun accountRecordsClear(): JSONObject =
        callJson("account_records_clear_json")

    fun submitSimulatedNetworkOperation(
        durationMillis: Long,
        idempotencyKey: String,
        payload: JSONObject
    ): JSONObject = callJson(
        "submit_simulated_network_operation_json",
        durationMillis,
        idempotencyKey,
        payload.toString()
    )

    fun operationStatus(operationId: String): JSONObject =
        callJson("operation_status_json", operationId)

    fun operationsSnapshot(): JSONObject = callJson("operations_snapshot_json")

    fun protocolFixtureReport(): JSONObject = callJson("protocol_fixture_report_json")

    fun cancelOperation(operationId: String): JSONObject =
        callJson("cancel_operation_json", operationId)

    fun metrics(): JSONObject {
        val count = callCount.get()
        val total = totalCallMicros.get()
        return JSONObject()
            .put("pythonStarted", Python.isStarted())
            .put("coreInitialized", facade != null)
            .put("warmupScheduled", warmupScheduled.get())
            .put("pythonVersion", pythonVersion ?: JSONObject.NULL)
            .put("pythonStartMillis", pythonStartMillis ?: JSONObject.NULL)
            .put("coreInitializationMillis", coreInitializationMillis ?: JSONObject.NULL)
            .put("callCount", count)
            .put("averageCallMicros", if (count == 0L) 0L else total / count)
            .put("maxCallMicros", maxCallMicros.get())
            .put("initializationError", initializationError ?: JSONObject.NULL)
    }

    private fun coreFacade(): PyObject {
        facade?.let { return it }
        synchronized(initializationLock) {
            facade?.let { return it }
            initializationError = null
            val pythonStartedAt = SystemClock.elapsedRealtime()
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(appContext))
            }
            pythonStartMillis = SystemClock.elapsedRealtime() - pythonStartedAt

            val coreStartedAt = SystemClock.elapsedRealtime()
            val python = Python.getInstance()
            val operationStore = appContext.filesDir
                .resolve("shared_python_core/operations-v2.json")
                .absolutePath
            val initialized = requireNotNull(
                python.getModule("dwpm_core").callAttr(
                    "create_hosted_core",
                    operationStore,
                    platformPorts
                )
            ) { "Shared Python CoreFacade initialization returned null" }
            pythonVersion = python.getModule("platform").callAttr("python_version")?.toString()
            coreInitializationMillis = SystemClock.elapsedRealtime() - coreStartedAt
            facade = initialized
            return initialized
        }
    }

    private fun callJson(method: String, vararg args: Any): JSONObject {
        val startedAt = SystemClock.elapsedRealtimeNanos()
        try {
            val result = requireNotNull(coreFacade().callAttr(method, *args)) {
                "Shared Python method $method returned null"
            }
            return JSONObject(result.toString())
        } finally {
            val elapsedMicros = (SystemClock.elapsedRealtimeNanos() - startedAt) / 1_000L
            callCount.incrementAndGet()
            totalCallMicros.addAndGet(elapsedMicros)
            maxCallMicros.updateAndGet { previous -> maxOf(previous, elapsedMicros) }
        }
    }

    private fun JSONObject.optLongOrNull(key: String): Long? =
        if (has(key) && !isNull(key)) getLong(key) else null

    companion object {
        private val WARMUP_EXECUTOR = Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "shared-python-warmup").apply { isDaemon = true }
        }

        @Volatile
        private var instance: SharedPythonCoreHost? = null

        fun get(context: Context): SharedPythonCoreHost = instance ?: synchronized(this) {
            instance ?: SharedPythonCoreHost(context).also { instance = it }
        }
    }
}

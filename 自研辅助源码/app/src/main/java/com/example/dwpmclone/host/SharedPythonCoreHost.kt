package com.example.dwpmclone.host

import android.content.Context
import android.os.SystemClock
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import org.json.JSONObject

/** Process-wide Android host for the repository's single shared Python core. */
class SharedPythonCoreHost private constructor(context: Context) {
    private val appContext = context.applicationContext
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
                .resolve("shared_python_core/operations-v1.json")
                .absolutePath
            val initialized = requireNotNull(
                python.getModule("dwpm_core").callAttr("create_hosted_core", operationStore)
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

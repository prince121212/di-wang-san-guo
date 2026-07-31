package com.example.dwpmclone.ui.web

import android.content.Context
import java.net.URLDecoder
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executor
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import org.json.JSONObject

enum class AssistantApiExecutionLane {
    LOCAL_READ,
    LOCAL_WRITE,
    NETWORK_OPERATION
}

/** Uses the shared route contract as the only source of local/network classification. */
class AssistantApiLaneClassifier private constructor(
    private val responseClassByRoute: Map<RouteKey, String>
) {
    fun laneFor(request: AssistantApiRequest): AssistantApiExecutionLane {
        val route = RouteKey(request.method.uppercase(), request.path.substringBefore('?'))
        return when (responseClassByRoute[route]) {
            NETWORK_OPERATION_CLASS -> AssistantApiExecutionLane.NETWORK_OPERATION
            else -> if (route.method == "GET") {
                AssistantApiExecutionLane.LOCAL_READ
            } else {
                AssistantApiExecutionLane.LOCAL_WRITE
            }
        }
    }

    val routeCount: Int
        get() = responseClassByRoute.size

    val networkOperationRouteCount: Int
        get() = responseClassByRoute.values.count { it == NETWORK_OPERATION_CLASS }

    companion object {
        private const val NETWORK_OPERATION_CLASS = "network-operation"

        fun fromContract(contract: JSONObject): AssistantApiLaneClassifier {
            val routes = contract.optJSONArray("routes")
                ?: throw IllegalArgumentException("共享路由契约缺少 routes")
            val classifications = buildMap {
                for (index in 0 until routes.length()) {
                    val route = routes.optJSONObject(index)
                        ?: throw IllegalArgumentException("共享路由契约第 $index 项不是对象")
                    val method = route.optString("method").uppercase()
                    val path = route.optString("path")
                    val responseClass = route.optString("responseClass")
                    require(method == "GET" || method == "POST") {
                        "共享路由契约方法无效：$method $path"
                    }
                    require(path.startsWith("/api/") && '?' !in path) {
                        "共享路由契约路径无效：$method $path"
                    }
                    require(responseClass == "local" || responseClass == NETWORK_OPERATION_CLASS) {
                        "共享路由契约响应类型无效：$method $path"
                    }
                    val key = RouteKey(method, path)
                    require(put(key, responseClass) == null) {
                        "共享路由契约存在重复项：$method $path"
                    }
                }
            }
            return AssistantApiLaneClassifier(classifications)
        }
    }

    private data class RouteKey(val method: String, val path: String)
}

object AssistantApiLaneClassifierAssetLoader {
    private const val CONTRACT_ASSET = "shared_core/api_route_ownership.json"

    fun load(context: Context): AssistantApiLaneClassifier {
        val raw = context.assets.open(CONTRACT_ASSET).bufferedReader(Charsets.UTF_8).use {
            it.readText()
        }
        return AssistantApiLaneClassifier.fromContract(JSONObject(raw))
    }
}

/**
 * Activity-scoped execution lanes.
 *
 * Local reads remain independent from serialized local writes. Legacy network handlers may still
 * block while waiting for the game server, but only inside their per-account serial lane; they can
 * no longer hold up settings, logs or cache reads on the WebView bridge.
 */
class AssistantApiExecutionLanes(
    private val classifier: AssistantApiLaneClassifier,
    private val localReadExecutor: ExecutorService = Executors.newFixedThreadPool(
        LOCAL_READ_CONCURRENCY,
        namedThreadFactory("assistant-local-read")
    ),
    private val localWriteExecutor: ExecutorService = Executors.newSingleThreadExecutor(
        namedThreadFactory("assistant-local-write")
    ),
    private val networkBackend: ExecutorService = Executors.newFixedThreadPool(
        NETWORK_CONCURRENCY,
        namedThreadFactory("assistant-network")
    )
) {
    private val closed = AtomicBoolean(false)
    private val networkLanes = ConcurrentHashMap<String, SerialExecutor>()

    fun execute(request: AssistantApiRequest, task: Runnable): Boolean {
        if (closed.get()) return false
        val executor: Executor = when (classifier.laneFor(request)) {
            AssistantApiExecutionLane.LOCAL_READ -> localReadExecutor
            AssistantApiExecutionLane.LOCAL_WRITE -> localWriteExecutor
            AssistantApiExecutionLane.NETWORK_OPERATION -> networkLanes.computeIfAbsent(
                accountLaneKey(request)
            ) { SerialExecutor(networkBackend) }
        }
        return try {
            executor.execute(task)
            true
        } catch (_: RejectedExecutionException) {
            false
        }
    }

    fun close() {
        if (!closed.compareAndSet(false, true)) return
        localReadExecutor.shutdownNow()
        localWriteExecutor.shutdownNow()
        networkBackend.shutdownNow()
        networkLanes.clear()
    }

    private fun accountLaneKey(request: AssistantApiRequest): String {
        val bodyKey = ACCOUNT_KEYS.asSequence()
            .map { request.body?.optString(it).orEmpty().trim() }
            .firstOrNull(String::isNotEmpty)
        val queryKey = queryValues(request.path).let { query ->
            ACCOUNT_KEYS.asSequence()
                .map { query[it].orEmpty().trim() }
                .firstOrNull(String::isNotEmpty)
        }
        val candidate = bodyKey ?: queryKey
        return candidate?.takeIf(ACCOUNT_LANE_KEY::matches) ?: GLOBAL_NETWORK_LANE
    }

    private fun queryValues(path: String): Map<String, String> = path.substringAfter('?', "")
        .split('&')
        .mapNotNull { pair ->
            if (pair.isBlank()) return@mapNotNull null
            runCatching {
                URLDecoder.decode(pair.substringBefore('='), "UTF-8") to
                    URLDecoder.decode(pair.substringAfter('=', ""), "UTF-8")
            }.getOrNull()
        }
        .toMap()

    private class SerialExecutor(private val backend: Executor) : Executor {
        private val tasks = ArrayDeque<Runnable>()
        private var active: Runnable? = null

        @Synchronized
        override fun execute(command: Runnable) {
            tasks.addLast(Runnable {
                try {
                    command.run()
                } finally {
                    scheduleNext()
                }
            })
            if (active == null) scheduleNext()
        }

        @Synchronized
        private fun scheduleNext() {
            active = if (tasks.isEmpty()) null else tasks.removeFirst()
            active?.let(backend::execute)
        }
    }

    companion object {
        private const val LOCAL_READ_CONCURRENCY = 2
        private const val NETWORK_CONCURRENCY = 4
        private const val GLOBAL_NETWORK_LANE = "_global"
        private val ACCOUNT_KEYS = listOf("sessionId", "accountId", "accountRef")
        private val ACCOUNT_LANE_KEY = Regex("[A-Za-z0-9._:-]{1,96}")
        private val threadSequence = AtomicInteger(0)

        private fun namedThreadFactory(prefix: String) = java.util.concurrent.ThreadFactory { runnable ->
            Thread(runnable, "$prefix-${threadSequence.incrementAndGet()}").apply {
                isDaemon = true
            }
        }
    }
}

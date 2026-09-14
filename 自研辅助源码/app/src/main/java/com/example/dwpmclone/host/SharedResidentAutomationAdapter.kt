package com.example.dwpmclone.host

import org.json.JSONObject
import org.json.JSONArray


data class SharedResidentTickResult(
    val accountId: Long,
    val operationId: String?,
    val feature: String?,
    val dailyKey: String?,
    val state: String,
    val message: String,
    val nextWakeAtMillis: Long?,
    val requiresAttention: Boolean,
    val requestSent: Boolean,
    /** Selected key's own deadline; distinct from the account-lane wake. */
    val taskNextWakeAtMillis: Long? = null,
    /** True when the shared core completed the configured daily key without a request. */
    val skipped: Boolean = false,
    val skipReason: String? = null,
    /** Optional UI-facing terminal text, e.g. 已做（国民跳过）. */
    val statusText: String? = null,
    val cycleKey: Long? = null,
    /**
     * Which branch owned this tick: a durable pending workflow's feature name,
     * or "configured".  A pending workflow preempts all configured work, so
     * without this a starved feature is indistinguishable from an idle one.
     */
    val decidedVia: String? = null,
    /** Features excluded this tick because they need a human, with the reason. */
    val blockedFeatures: String? = null,
    /** Features that were actually considered this tick. */
    val candidateFeatures: String? = null,
    /** Features removed from *both* scheduling paths by a pending ledger. */
    val isolatedFeatures: String? = null,
    /** Subset of [isolatedFeatures] whose ledger still needs human review. */
    val isolatedAttentionFeatures: String? = null,
    /** Due features that keep losing the tick, with how late each one is. */
    val stalledFeatures: String? = null,
)

/**
 * Blocking adapter used only on the service's background scheduler thread.
 * Kotlin supplies local habits and wake timing; Python owns task selection,
 * rule cursors, target search, every packet, pending ledgers, daily boundaries
 * and the next business deadline.
 */
class SharedResidentAutomationAdapter(
    private val configure: (String, JSONObject) -> JSONObject,
    private val submit: (String, String, JSONObject) -> JSONObject,
    private val status: (String) -> JSONObject,
    private val nowMillis: () -> Long = System::currentTimeMillis,
    private val pause: (Long) -> Unit = Thread::sleep,
    private val pollIntervalMillis: Long = 50L,
    private val maximumPolls: Int = 18_000,
    private val operationStore: ResidentOperationStore = InMemoryResidentOperationStore(),
    /** Status read that may block until the operation settles; see [runOnce]. */
    private val settleStatus: (String, Long) -> JSONObject = { id, _ -> status(id) },
    private val settleBudgetMillis: Long = SETTLE_BUDGET_MILLIS,
) {
    constructor(core: SharedPythonCoreHost) : this(
        configure = core::configureResidentAutomation,
        submit = { accountRef, tickKey, context ->
            core.submitAutomationRecoveryTick(accountRef, tickKey, context)
        },
        status = core::operationStatus,
        operationStore = AndroidResidentOperationStore(core.applicationContext),
        settleStatus = core::operationStatus,
    )

    /**
     * Advance one resident operation without polling in the scheduler thread.
     *
     * The old [run] method is retained for compatibility with the desktop-style
     * blocking tests and callers.  Android uses this one-shot method: one status
     * request per scheduler wakeup, while the operation id and idempotency key
     * survive process death in [operationStore].
     *
     * A freshly submitted lane is the one exception.  It normally settles in
     * about a second, and this thread already holds the wake lock that paid for
     * the current wakeup, so the first read is allowed to block for
     * [settleBudgetMillis].  That turns the common "submit, give up, wake again
     * five seconds later to collect a result that was ready almost immediately"
     * cycle into a single wakeup.  A resumed operation keeps the non-blocking
     * path: it is long-running by definition, so blocking would only hold the
     * CPU awake without changing when it finishes.
     */
    fun runOnce(
        accountId: Long,
        habits: JSONObject,
        tickKey: String,
    ): SharedResidentTickResult {
        val accountRef = accountId.toString()
        runCatching { configure(accountRef, habits) }.getOrElse { error ->
            return retry(
                accountId,
                operationStore.get(accountId)?.operationId,
                "共享常驻配置同步失败：${error.message ?: error.javaClass.simpleName}",
            )
        }

        val saved = operationStore.get(accountId)
        val durableTickKey = saved?.tickKey
            ?: operationStore.ensureTickKey(accountId, tickKey)
        var operationId = saved?.operationId
        val resumed = !operationId.isNullOrBlank()
        if (operationId.isNullOrBlank()) {
            val submitted = runCatching {
                submit(accountRef, durableTickKey, requestContext(durableTickKey))
            }.getOrElse { error ->
                // Keep the key. If the server accepted the request but the
                // response was lost, the next submit is idempotently coalesced.
                return retry(
                    accountId,
                    null,
                    "共享常驻 tick 提交失败：${error.message ?: error.javaClass.simpleName}",
                )
            }
            operationId = submitted.optString("operationId").trim()
            if (operationId.isNullOrBlank()) {
                return retry(accountId, null, "共享常驻 tick 未返回 operationId")
            }
            operationStore.putOperation(accountId, operationId!!, durableTickKey)
        }

        val id = operationId!!
        val envelope = runCatching {
            if (resumed) status(id) else settleStatus(id, settleBudgetMillis)
        }.getOrElse { error ->
            // A status timeout is not evidence that a mutation was not sent.
            // Keep the durable id and retry only the read on a later wakeup.
            return SharedResidentTickResult(
                accountId = accountId,
                operationId = id,
                feature = null,
                dailyKey = null,
                state = "status-unavailable",
                message = "读取共享常驻 tick 状态失败：${error.message ?: error.javaClass.simpleName}",
                nextWakeAtMillis = nowMillis() + RETRY_MILLIS,
                requiresAttention = false,
                requestSent = false,
            )
        }
        val operation = envelope.optJSONObject("operation")
            ?: return SharedResidentTickResult(
                accountId = accountId,
                operationId = id,
                feature = null,
                dailyKey = null,
                state = "missing",
                message = "共享常驻 operation 已丢失；不会自动重发，请人工确认",
                nextWakeAtMillis = null,
                requiresAttention = true,
                requestSent = false,
            )
        val operationStatus = operation.optString("status").trim().uppercase()
        val requestSent = operation.optBoolean("requestSent", false)
        when (operationStatus) {
            "QUEUED", "RUNNING" -> {
                val progress = operation.optJSONObject("progressDetails") ?: JSONObject()
                val phase = progress.optString("phase").trim()
                return SharedResidentTickResult(
                    accountId = accountId,
                    operationId = id,
                    feature = featureForPhase(phase),
                    dailyKey = optionalString(progress, "dailyKey"),
                    state = operationStatus.lowercase(),
                    message = if (phase.isBlank()) {
                        "共享常驻 operation 执行中"
                    } else {
                        "共享常驻 operation 执行中：$phase"
                    },
                    nextWakeAtMillis = nowMillis() + PENDING_POLL_MILLIS,
                    requiresAttention = false,
                    requestSent = requestSent,
                )
            }
            "SUCCEEDED", "FAILED", "UNCERTAIN", "CANCELLED" -> {
                val result = terminalResult(accountId, id, operation, operationStatus)
                // The durable Python operation ledger is authoritative.  This
                // Android-side pointer only bridges a process restart, so it
                // is safe to clear after observing any terminal state (including
                // UNCERTAIN); the next explicit tick will reconcile the durable
                // pending record and will never replay the old mutation blindly.
                operationStore.clear(accountId)
                return result
            }
            else -> {
                return SharedResidentTickResult(
                    accountId = accountId,
                    operationId = id,
                    feature = null,
                    dailyKey = null,
                    state = "invalid",
                    message = "共享常驻 operation 状态无效：$operationStatus",
                    nextWakeAtMillis = null,
                    requiresAttention = true,
                    requestSent = requestSent,
                )
            }
        }
    }

    fun run(accountId: Long, habits: JSONObject, tickKey: String): SharedResidentTickResult {
        val accountRef = accountId.toString()
        runCatching { configure(accountRef, habits) }.getOrElse { error ->
            return retry(
                accountId,
                null,
                "共享常驻配置同步失败：${error.message ?: error.javaClass.simpleName}",
            )
        }
        val submitted = runCatching {
            submit(
                accountRef,
                tickKey,
                JSONObject()
                    .put("source", "android-resident-scheduler")
                    .put("platform", "android")
                    .put(
                        "allowedFeatures",
                        JSONArray(listOf("mine", "lossless", "brush", "raid", "dungeon", "general", "ministry", "captives", "domestic", "inventory", "alarm", "daily"))
                    )
                    .put("requestId", tickKey),
            )
        }.getOrElse { error ->
            return retry(
                accountId,
                null,
                "共享常驻 tick 提交失败：${error.message ?: error.javaClass.simpleName}",
            )
        }
        val operationId = submitted.optString("operationId")
        if (operationId.isBlank()) {
            return retry(accountId, null, "共享常驻 tick 未返回 operationId")
        }
        repeat(maximumPolls.coerceAtLeast(1)) {
            val envelope = runCatching { status(operationId) }.getOrElse { error ->
                return retry(
                    accountId,
                    operationId,
                    "读取共享常驻 tick 失败：${error.message ?: error.javaClass.simpleName}",
                )
            }
            val operation = envelope.optJSONObject("operation")
                ?: return retry(accountId, operationId, "共享常驻 operation 不存在")
            val operationStatus = operation.optString("status")
            val requestSent = operation.optBoolean("requestSent", false)
            when (operationStatus) {
                "QUEUED", "RUNNING" -> pause(pollIntervalMillis.coerceAtLeast(1L))
                "SUCCEEDED" -> {
                    val result = operation.optJSONObject("result") ?: JSONObject()
                    return SharedResidentTickResult(
                        accountId = accountId,
                        operationId = operationId,
                        feature = optionalString(result, "feature"),
                        dailyKey = optionalString(result, "dailyKey"),
                        state = result.optString("state", "idle"),
                        message = result.optString("message").ifBlank {
                            "共享常驻 tick 已完成"
                        },
                        nextWakeAtMillis = result.optLong("nextWakeAtMillis").takeIf {
                            result.has("nextWakeAtMillis") && !result.isNull("nextWakeAtMillis")
                        },
                        taskNextWakeAtMillis = result.optLong("taskNextWakeAtMillis").takeIf {
                            result.has("taskNextWakeAtMillis") && !result.isNull("taskNextWakeAtMillis")
                        },
                        requiresAttention = result.optBoolean("requiresAttention", false) &&
                    optionalString(result, "feature").isNullOrBlank(),
                        requestSent = requestSent,
                        skipped = result.optBoolean("skipped", false),
                        skipReason = optionalString(result, "skipReason"),
                        statusText = optionalString(result, "statusText"),
                        cycleKey = result.optLong("cycleKey").takeIf {
                            result.has("cycleKey") && !result.isNull("cycleKey")
                        },
                        isolatedAttentionFeatures = result.optJSONArray("isolatedAttentionFeatures")?.let { rows ->
                            (0 until rows.length()).joinToString("|") { rows.optString(it) }
                                .takeIf { it.isNotBlank() }
                        },
                    )
                }
                "FAILED", "UNCERTAIN", "CANCELLED" -> {
                    val error = operation.optJSONObject("error") ?: JSONObject()
                    val errorDetails = error.optJSONObject("details") ?: JSONObject()
                    val progressDetails = operation.optJSONObject("progressDetails") ?: JSONObject()
                    val failureFeature = optionalString(errorDetails, "feature")
                        ?: featureForPhase(progressDetails.optString("phase"))
                    val failureDailyKey = optionalString(errorDetails, "dailyKey")
                        ?: optionalString(progressDetails, "dailyKey")
                    val attention = accountNeedsAttention(operationStatus, requestSent, failureFeature)
                    return SharedResidentTickResult(
                        accountId = accountId,
                        operationId = operationId,
                        feature = failureFeature,
                        dailyKey = failureDailyKey,
                        state = operationStatus.lowercase(),
                        message = error.optString("message").ifBlank {
                            "共享常驻 operation 结束：$operationStatus"
                        },
                        nextWakeAtMillis = if (attention) null else nowMillis() + RETRY_MILLIS,
                        requiresAttention = attention,
                        requestSent = requestSent,
                    )
                }
                else -> return retry(
                    accountId,
                    operationId,
                    "共享常驻 operation 状态无效：$operationStatus",
                )
            }
        }
        return SharedResidentTickResult(
            accountId = accountId,
            operationId = operationId,
            feature = null,
            dailyKey = null,
            state = "timeout",
            message = "共享常驻 tick 等待超时；不会在结果不明时重新提交动作",
            nextWakeAtMillis = null,
            requiresAttention = true,
            requestSent = true,
        )
    }

    private fun requestContext(tickKey: String): JSONObject = JSONObject()
        .put("source", "android-resident-scheduler")
        .put("platform", "android")
        .put(
            "allowedFeatures",
            JSONArray(listOf("mine", "lossless", "brush", "raid", "dungeon", "general", "ministry", "captives", "domestic", "inventory", "alarm", "daily"))
        )
        .put("requestId", tickKey)

    private fun terminalResult(
        accountId: Long,
        operationId: String,
        operation: JSONObject,
        operationStatus: String,
    ): SharedResidentTickResult {
        val requestSent = operation.optBoolean("requestSent", false)
        if (operationStatus == "SUCCEEDED") {
            val result = operation.optJSONObject("result") ?: JSONObject()
            return SharedResidentTickResult(
                accountId = accountId,
                operationId = operationId,
                feature = optionalString(result, "feature"),
                dailyKey = optionalString(result, "dailyKey"),
                state = result.optString("state", "idle"),
                message = result.optString("message").ifBlank { "共享常驻 tick 已完成" },
                nextWakeAtMillis = result.optLong("nextWakeAtMillis").takeIf {
                    result.has("nextWakeAtMillis") && !result.isNull("nextWakeAtMillis")
                },
                taskNextWakeAtMillis = result.optLong("taskNextWakeAtMillis").takeIf {
                    result.has("taskNextWakeAtMillis") && !result.isNull("taskNextWakeAtMillis")
                },
                requiresAttention = result.optBoolean("requiresAttention", false) &&
                    optionalString(result, "feature").isNullOrBlank(),
                requestSent = requestSent,
                skipped = result.optBoolean("skipped", false),
                skipReason = optionalString(result, "skipReason"),
                statusText = optionalString(result, "statusText"),
                cycleKey = result.optLong("cycleKey").takeIf {
                    result.has("cycleKey") && !result.isNull("cycleKey")
                },
                decidedVia = optionalString(result, "decidedVia"),
                blockedFeatures = describeBlocked(result.optJSONArray("blockedFeatures")),
                isolatedFeatures = result.optJSONArray("isolatedPendingFeatures")?.let { rows ->
                    (0 until rows.length()).joinToString("|") { rows.optString(it) }
                        .takeIf { it.isNotBlank() }
                },
                isolatedAttentionFeatures = result.optJSONArray("isolatedAttentionFeatures")?.let { rows ->
                    (0 until rows.length()).joinToString("|") { rows.optString(it) }
                        .takeIf { it.isNotBlank() }
                },
                candidateFeatures = result.optJSONArray("candidateFeatures")?.let { rows ->
                    (0 until rows.length()).joinToString("|") { rows.optString(it) }
                        .takeIf { it.isNotBlank() }
                },
                stalledFeatures = describeStalled(result.optJSONArray("stalledFeatures")),
            )
        }
        val error = operation.optJSONObject("error") ?: JSONObject()
        val errorDetails = error.optJSONObject("details") ?: JSONObject()
        val progressDetails = operation.optJSONObject("progressDetails") ?: JSONObject()
        val failureFeature = optionalString(errorDetails, "feature")
            ?: featureForPhase(progressDetails.optString("phase"))
        val failureDailyKey = optionalString(errorDetails, "dailyKey")
            ?: optionalString(progressDetails, "dailyKey")
        val attention = accountNeedsAttention(operationStatus, requestSent, failureFeature)
        return SharedResidentTickResult(
            accountId = accountId,
            operationId = operationId,
            feature = failureFeature,
            dailyKey = failureDailyKey,
            state = operationStatus.lowercase(),
            message = error.optString("message").ifBlank {
                "共享常驻 operation 结束：$operationStatus"
            },
            nextWakeAtMillis = if (attention) null else nowMillis() + RETRY_MILLIS,
            requiresAttention = attention,
            requestSent = requestSent,
        )
    }

    /**
     * Decide whether a terminal operation should pause the whole account.
     *
     * The wake gate this feeds is per *account*, so it may only act on facts
     * that are true of the account.  Two things were being read as such and
     * are not:
     *
     * `requestSent` on a FAILED operation means the server answered and said
     * no.  That is a known result, not an open question - only UNCERTAIN, or a
     * cancellation that already crossed the send boundary, leaves an outcome
     * nobody can determine.  A real account lost three hours to this: 将领维护
     * spent an 活血丹, the server rejected it with a definitive status, and
     * that rejection paused 副本 and 刷黄 along with it.
     *
     * A failure the core could attribute to one feature is that feature's
     * problem.  The core already isolates it and keeps scheduling the rest, so
     * pausing the account here throws away work that was never in doubt.
     */
    private fun accountNeedsAttention(
        operationStatus: String,
        requestSent: Boolean,
        failureFeature: String?,
    ): Boolean {
        val outcomeUnknown = operationStatus == "UNCERTAIN" ||
            (operationStatus == "CANCELLED" && requestSent)
        return outcomeUnknown && failureFeature.isNullOrBlank()
    }

    private fun retry(
        accountId: Long,
        operationId: String?,
        message: String,
    ): SharedResidentTickResult = SharedResidentTickResult(
        accountId = accountId,
        operationId = operationId,
        feature = null,
        dailyKey = null,
        state = "retry",
        message = message,
        nextWakeAtMillis = nowMillis() + RETRY_MILLIS,
        taskNextWakeAtMillis = null,
        requiresAttention = false,
        requestSent = false,
    )

    private fun featureForPhase(rawPhase: String): String? {
        val phase = rawPhase.trim().lowercase()
        return when {
            phase.startsWith("resident-brush") ||
                phase.startsWith("scanning-bandit") ||
                phase.startsWith("brush-recovery") -> "brush"
            phase.startsWith("resident-mine") ||
                phase.startsWith("scanning-mine") ||
                phase.startsWith("mine-garrison") -> "mine"
            phase.startsWith("resident-lossless") ||
                phase.startsWith("lossless-") -> "lossless"
            phase.startsWith("resident-dungeon") ||
                phase.startsWith("dungeon-") -> "dungeon"
            phase.startsWith("resident-raid") ||
                phase.startsWith("raid-") -> "raid"
            phase.startsWith("resident-general") -> "general"
            phase.startsWith("resident-ministry") ||
                phase.startsWith("garden-") ||
                phase == "planted" || phase == "plant-recovered" -> "ministry"
            phase.startsWith("resident-captives") ||
                phase.startsWith("shared-core/captives") -> "captives"
            phase.startsWith("resident-domestic") ||
                phase == "refreshing-role-queues" -> "domestic"
            phase.startsWith("inventory-") ||
                phase.startsWith("refreshing-inventory") -> "inventory"
            phase.startsWith("resident-alarm") -> "alarm"
            phase == "periodic-daily" -> "daily"
            else -> null
        }
    }

    /** Render "feature(errorCode)" pairs so a stuck feature names its blocker. */
    private fun describeBlocked(rows: JSONArray?): String? {
        if (rows == null || rows.length() == 0) return null
        return (0 until rows.length())
            .mapNotNull { rows.optJSONObject(it) }
            .joinToString(",") { row ->
                val feature = row.optString("feature").ifBlank { "?" }
                val code = row.optString("errorCode").ifBlank { row.optString("state") }
                if (code.isBlank()) feature else "$feature($code)"
            }
            .takeIf { it.isNotBlank() }
    }

    /** Renders "副本(逾期23分)" so lateness reads without decoding a timestamp. */
    private fun describeStalled(rows: JSONArray?): String? {
        if (rows == null || rows.length() == 0) return null
        return (0 until rows.length())
            .mapNotNull { rows.optJSONObject(it) }
            .joinToString(",") { row ->
                val feature = row.optString("feature").ifBlank { "?" }
                val minutes = row.optLong("overdueMillis") / 60_000L
                "$feature(逾期${minutes}分)"
            }
            .takeIf { it.isNotBlank() }
    }

    private fun optionalString(source: JSONObject, key: String): String? =
        source.optString(key).takeIf {
            source.has(key) && !source.isNull(key) && it.isNotBlank() && it != "null"
        }

    companion object {
        const val RETRY_MILLIS = 10_000L
        const val PENDING_POLL_MILLIS = 5_000L

        /**
         * Bounded in-window wait for a freshly submitted operation.  Sized from
         * real device traces where a resident recovery tick settles in roughly
         * a second; anything slower is genuinely long-running and belongs on
         * the [PENDING_POLL_MILLIS] alarm path instead of holding the CPU.
         */
        const val SETTLE_BUDGET_MILLIS = 2_000L
    }
}

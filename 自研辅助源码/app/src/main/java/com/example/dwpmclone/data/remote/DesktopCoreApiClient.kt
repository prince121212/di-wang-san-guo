package com.example.dwpmclone.data.remote

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID

sealed class DesktopCoreResult<out T> {
    data class Ok<T>(val value: T, val status: Int) : DesktopCoreResult<T>()
    data class Err(
        val code: String,
        val message: String,
        val status: Int? = null,
        val retryable: Boolean = false,
        val payload: JSONObject? = null
    ) : DesktopCoreResult<Nothing>()
}

data class DesktopCoreAccount(
    val accountRef: String,
    val username: String,
    val roleName: String,
    val areaName: String,
    val status: String,
    val started: Boolean,
    val online: Boolean
)

data class DesktopCoreHttpRequest(
    val method: String,
    val url: String,
    val headers: Map<String, String>,
    val body: String?
)

data class DesktopCoreHttpResponse(
    val status: Int,
    val body: String
)

fun interface DesktopCoreTransport {
    fun execute(request: DesktopCoreHttpRequest): DesktopCoreHttpResponse
}

class HttpUrlConnectionDesktopCoreTransport : DesktopCoreTransport {
    override fun execute(request: DesktopCoreHttpRequest): DesktopCoreHttpResponse {
        val connection = (URL(request.url).openConnection() as HttpURLConnection).apply {
            requestMethod = request.method
            connectTimeout = 5_000
            readTimeout = 180_000
            request.headers.forEach { (key, value) -> setRequestProperty(key, value) }
            if (request.body != null) {
                doOutput = true
                outputStream.use { it.write(request.body.toByteArray(Charsets.UTF_8)) }
            }
        }
        return try {
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            DesktopCoreHttpResponse(status, text)
        } finally {
            connection.disconnect()
        }
    }
}

/**
 * Thin client for the desktop-authoritative Mobile API.
 *
 * This class deliberately has no game protocol, session parser, scheduler or
 * local completion state.  All of those remain owned by the desktop core.
 */
class DesktopCoreApiClient(
    private val settings: DesktopCoreSettings,
    private val transport: DesktopCoreTransport = HttpUrlConnectionDesktopCoreTransport()
) {
    enum class DailyFeature(val wireName: String) {
        SIGN_IN("signIn"),
        ARENA_COINS("arenaCoins"),
        DONATE("donate"),
        SALARY("salary"),
        NATIONAL_COLLECT("nationalCollect"),
        CITY_LORD_COLLECT("cityLordCollect"),
        GENERAL_VISIT_CANDIDATES("generalVisitCandidates"),
        GENERAL_VISIT("generalVisit")
    }

    fun health(): DesktopCoreResult<JSONObject> = request("GET", "/api/v1/mobile/health")

    fun capabilities(): DesktopCoreResult<JSONObject> =
        request("GET", "/api/v1/mobile/capabilities")

    fun listAccounts(): DesktopCoreResult<List<DesktopCoreAccount>> =
        when (val result = request("GET", "/api/v1/mobile/accounts")) {
            is DesktopCoreResult.Err -> result
            is DesktopCoreResult.Ok -> {
                val rows = result.value.optJSONArray("accounts") ?: JSONArray()
                DesktopCoreResult.Ok(
                    (0 until rows.length()).mapNotNull { index ->
                        rows.optJSONObject(index)?.toDesktopCoreAccount()
                    },
                    result.status
                )
            }
        }

    fun snapshot(accountRef: String, refresh: Boolean = false): DesktopCoreResult<JSONObject> =
        request(
            "GET",
            "/api/v1/mobile/accounts/${encodePath(accountRef)}/snapshot?refresh=${if (refresh) 1 else 0}"
        )

    fun settings(accountRef: String): DesktopCoreResult<JSONObject> =
        request("GET", "/api/v1/mobile/accounts/${encodePath(accountRef)}/settings")

    fun patchSettings(
        accountRef: String,
        scope: String,
        patch: JSONObject,
        revision: String,
        idempotencyKey: String = newIdempotencyKey("settings")
    ): DesktopCoreResult<JSONObject> = request(
        // The server also accepts HTTP PATCH, but POST keeps compatibility
        // with older Android HttpURLConnection implementations.
        "POST",
        "/api/v1/mobile/accounts/${encodePath(accountRef)}/settings",
        JSONObject()
            .put("scope", scope)
            .put("patch", patch)
            .put("revision", revision)
            .put("idempotencyKey", idempotencyKey),
        idempotencyKey
    )

    fun accountAction(
        accountRef: String,
        action: String,
        idempotencyKey: String = newIdempotencyKey("account-$action")
    ): DesktopCoreResult<JSONObject> = request(
        "POST",
        "/api/v1/mobile/accounts/${encodePath(accountRef)}/account",
        JSONObject().put("action", action).put("idempotencyKey", idempotencyKey),
        idempotencyKey
    )

    fun taskAction(
        accountRef: String,
        action: String,
        idempotencyKey: String = newIdempotencyKey("tasks-$action")
    ): DesktopCoreResult<JSONObject> = request(
        "POST",
        "/api/v1/mobile/accounts/${encodePath(accountRef)}/tasks",
        JSONObject().put("action", action).put("idempotencyKey", idempotencyKey),
        idempotencyKey
    )

    fun dailyAction(
        accountRef: String,
        feature: DailyFeature,
        orderedGeneralIds: List<String> = emptyList(),
        idempotencyKey: String = newIdempotencyKey("daily-${feature.wireName}")
    ): DesktopCoreResult<JSONObject> {
        val body = JSONObject()
            .put("feature", feature.wireName)
            .put("idempotencyKey", idempotencyKey)
        if (feature == DailyFeature.GENERAL_VISIT) {
            body.put(
                "generalVisitGeneralIds",
                JSONArray(orderedGeneralIds.filter { it.isNotBlank() }.distinct().take(4))
            )
        }
        return request(
            "POST",
            "/api/v1/mobile/accounts/${encodePath(accountRef)}/daily",
            body,
            idempotencyKey
        )
    }

    fun legacyAction(
        accountRef: String?,
        path: String,
        body: JSONObject = JSONObject(),
        method: String = "POST",
        idempotencyKey: String = newIdempotencyKey("legacy")
    ): DesktopCoreResult<JSONObject> = request(
        "POST",
        "/api/v1/mobile/legacy",
        JSONObject()
            .put("method", method.uppercase())
            .put("path", path)
            .put("accountRef", accountRef ?: JSONObject.NULL)
            .put("body", body)
            .put("idempotencyKey", idempotencyKey),
        idempotencyKey
    )

    fun webConsoleUrl(): String =
        "${settings.normalizedBaseUrl}/api/v1/mobile/web?token=" +
            URLEncoder.encode(settings.apiToken, "UTF-8")

    private fun request(
        method: String,
        path: String,
        body: JSONObject? = null,
        idempotencyKey: String? = null
    ): DesktopCoreResult<JSONObject> {
        settings.validationError()?.let {
            return DesktopCoreResult.Err("DESKTOP_CORE_SETTINGS_INVALID", it, retryable = false)
        }
        val headers = linkedMapOf(
            "Accept" to "application/json",
            "Authorization" to "Bearer ${settings.apiToken}",
            "X-Device-Id" to settings.deviceId
        )
        if (body != null) headers["Content-Type"] = "application/json; charset=utf-8"
        if (!idempotencyKey.isNullOrBlank()) headers["Idempotency-Key"] = idempotencyKey
        return try {
            val response = transport.execute(
                DesktopCoreHttpRequest(
                    method = method,
                    url = settings.normalizedBaseUrl + path,
                    headers = headers,
                    body = body?.toString()
                )
            )
            val json = if (response.body.isBlank()) JSONObject() else JSONObject(response.body)
            if (response.status in 200..299 && json.optBoolean("ok", true)) {
                DesktopCoreResult.Ok(json, response.status)
            } else {
                DesktopCoreResult.Err(
                    code = json.optString("code").ifBlank { "DESKTOP_CORE_HTTP_${response.status}" },
                    message = json.optString("error").ifBlank {
                        json.optString("message").ifBlank { "电脑端核心请求失败（HTTP ${response.status}）" }
                    },
                    status = response.status,
                    retryable = response.status == 408 || response.status == 409 ||
                        response.status == 429 || response.status >= 500,
                    payload = json
                )
            }
        } catch (error: Exception) {
            DesktopCoreResult.Err(
                code = "DESKTOP_CORE_NETWORK_ERROR",
                message = "无法连接电脑端核心：${error.message ?: error.javaClass.simpleName}",
                retryable = true
            )
        }
    }

    private fun JSONObject.toDesktopCoreAccount(): DesktopCoreAccount = DesktopCoreAccount(
        accountRef = optString("accountRef"),
        username = optString("username"),
        roleName = optString("roleName"),
        areaName = optString("areaName"),
        status = optString("status"),
        started = optBoolean("started"),
        online = optBoolean("hasLiveSession") && optString("status") == "online"
    )

    private fun encodePath(value: String): String =
        URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    companion object {
        fun newIdempotencyKey(prefix: String): String =
            "android-${prefix.take(32)}-${UUID.randomUUID()}"
    }
}

package com.example.dwpmclone.domain.cloud

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * HTTP implementation of the collaborative map protocol.
 *
 * API:
 * - POST /v1/map/observations
 * - POST /v1/map/recommendations
 * - POST /v1/map/results
 * - GET  /health
 *
 * Every request carries a stable device id. An optional bearer token can be enabled when
 * the computer-side service is exposed outside the trusted LAN.
 */
class HttpCollaborativeMapClient(
    private val settings: CollaborativeMapHttpSettings
) : CollaborativeMapClient {
    init {
        require(settings.baseUrl.startsWith("http://") || settings.baseUrl.startsWith("https://")) {
            "cloud map baseUrl must use http or https"
        }
        require(settings.deviceId.isNotBlank()) { "cloud map deviceId must not be blank" }
    }

    override suspend fun upload(request: ObservationUploadRequest): CloudMapResult<UploadReceipt> {
        val body = JSONObject()
            .put("accountId", request.accountId)
            .put("serverId", request.serverId)
            .put("kind", request.kind.name)
            .put("observedAtMillis", request.observedAtMillis)
            .put("clientBatchId", request.clientBatchId)
            .put("observations", JSONArray().apply {
                request.observations.forEach { observation ->
                    put(
                        JSONObject()
                            .put("targetId", observation.targetId)
                            .put("x", observation.coordinate.x)
                            .put("y", observation.coordinate.y)
                            .put("targetType", observation.targetType)
                            .putNullable("level", observation.level)
                            .put("observedAtMillis", observation.observedAtMillis)
                            .put("raw", JSONObject(observation.raw))
                    )
                }
            })
        return when (val response = executeJson("POST", "/v1/map/observations", body)) {
            is CloudMapResult.Err -> response
            is CloudMapResult.Ok -> {
                val json = response.value
                val revision = json.optString("serverRevision")
                val batchId = json.optString("clientBatchId")
                if (revision.isBlank() || batchId.isBlank()) {
                    CloudMapResult.Err("CLOUD_MAP_BAD_UPLOAD_RESPONSE", "云端上传回执缺少版本或批次", false)
                } else {
                    CloudMapResult.Ok(
                        UploadReceipt(
                            accepted = json.optInt("accepted", request.observations.size),
                            serverRevision = revision,
                            clientBatchId = batchId
                        )
                    )
                }
            }
        }
    }

    override suspend fun recommend(request: TargetRecommendationRequest): CloudMapResult<CloudTarget?> {
        val body = JSONObject()
            .put("accountId", request.accountId)
            .put("serverId", request.serverId)
            .put("kind", request.kind.name)
            .put("start", JSONObject().put("x", request.start.x).put("y", request.start.y))
            .put("acceptedRevision", request.acceptedRevision)
            .putNullable("targetType", request.targetType)
            .put("allowedMineTypes", JSONArray(request.allowedMineTypes.toList()))
        return when (val response = executeJson("POST", "/v1/map/recommendations", body)) {
            is CloudMapResult.Err -> response
            is CloudMapResult.Ok -> {
                if (response.value.isNull("target") || !response.value.has("target")) {
                    CloudMapResult.Ok(null)
                } else {
                    parseTarget(response.value.optJSONObject("target"))
                }
            }
        }
    }

    override suspend fun reportExpedition(
        request: ExpeditionResultRequest
    ): CloudMapResult<ExpeditionResultReceipt> {
        val body = JSONObject()
            .put("accountId", request.accountId)
            .put("serverId", request.serverId)
            .put("kind", request.kind.name)
            .put("targetId", request.targetId)
            .put("acceptedRevision", request.acceptedRevision)
            .put("success", request.success)
            .put("message", request.message)
            .put("reportedAtMillis", request.reportedAtMillis)
            .put("clientResultId", request.clientResultId.ifBlank {
                "${request.accountId}-${request.kind.name.lowercase()}-${request.targetId}-${request.acceptedRevision}"
            })
            .put("raw", JSONObject(request.raw))
        return when (val response = executeJson("POST", "/v1/map/results", body)) {
            is CloudMapResult.Err -> response
            is CloudMapResult.Ok -> {
                val json = response.value
                val revision = json.optString("serverRevision")
                val targetId = json.optLong("targetId", Long.MIN_VALUE)
                if (!json.optBoolean("accepted", false) ||
                    revision.isBlank() ||
                    targetId == Long.MIN_VALUE
                ) {
                    CloudMapResult.Err(
                        "CLOUD_MAP_BAD_RESULT_RESPONSE",
                        "云端出征结果回执缺少确认、版本或目标",
                        false
                    )
                } else {
                    CloudMapResult.Ok(ExpeditionResultReceipt(true, revision, targetId))
                }
            }
        }
    }

    suspend fun checkHealth(): CloudMapResult<String> =
        when (val response = executeJson("GET", "/health", null)) {
            is CloudMapResult.Err -> response
            is CloudMapResult.Ok -> CloudMapResult.Ok(
                response.value.optString("status").ifBlank { "ok" }
            )
        }

    private fun parseTarget(json: JSONObject?): CloudMapResult<CloudTarget?> {
        if (json == null) return CloudMapResult.Err("CLOUD_MAP_BAD_TARGET_RESPONSE", "云端推荐目标格式无效", false)
        val targetId = json.optLong("targetId", Long.MIN_VALUE)
        val targetType = json.optString("targetType")
        val revision = json.optString("serverRevision")
        if (targetId == Long.MIN_VALUE || targetType.isBlank() || revision.isBlank() ||
            !json.has("x") || !json.has("y")
        ) {
            return CloudMapResult.Err("CLOUD_MAP_BAD_TARGET_RESPONSE", "云端推荐目标缺少必要字段", false)
        }
        return CloudMapResult.Ok(
            CloudTarget(
                targetId = targetId,
                coordinate = com.example.dwpmclone.domain.model.MapCoordinate(
                    json.getInt("x"),
                    json.getInt("y")
                ),
                targetType = targetType,
                level = json.optNullableInt("level"),
                serverRevision = revision,
                raw = json.optJSONObject("raw").toStringMap()
            )
        )
    }

    private fun executeJson(
        method: String,
        path: String,
        body: JSONObject?
    ): CloudMapResult<JSONObject> {
        var connection: HttpURLConnection? = null
        return try {
            connection = (URL(settings.baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = settings.connectTimeoutMillis
                readTimeout = settings.readTimeoutMillis
                setRequestProperty("Accept", "application/json")
                setRequestProperty("X-Device-Id", settings.deviceId)
                if (settings.authToken.isNotBlank()) {
                    setRequestProperty("Authorization", "Bearer ${settings.authToken}")
                }
                if (body != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
                }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val json = if (text.isBlank()) JSONObject() else JSONObject(text)
            if (status in 200..299) {
                CloudMapResult.Ok(json)
            } else {
                CloudMapResult.Err(
                    code = json.optString("code").ifBlank { "CLOUD_MAP_HTTP_$status" },
                    message = json.optString("message").ifBlank { "云端地图请求失败（HTTP $status）" },
                    retryable = status == 408 || status == 409 || status == 429 || status >= 500
                )
            }
        } catch (error: Exception) {
            CloudMapResult.Err(
                code = "CLOUD_MAP_NETWORK_ERROR",
                message = "云端地图网络异常：${error.message ?: error.javaClass.simpleName}",
                retryable = true
            )
        } finally {
            connection?.disconnect()
        }
    }

    private fun JSONObject.putNullable(key: String, value: Any?): JSONObject =
        put(key, value ?: JSONObject.NULL)

    private fun JSONObject.optNullableInt(key: String): Int? =
        if (!has(key) || isNull(key)) null else optInt(key)

    private fun JSONObject?.toStringMap(): Map<String, String> {
        if (this == null) return emptyMap()
        return keys().asSequence().associateWith { key ->
            if (isNull(key)) "" else opt(key)?.toString().orEmpty()
        }
    }
}

data class CollaborativeMapHttpSettings(
    val baseUrl: String,
    val deviceId: String,
    val authToken: String = "",
    val connectTimeoutMillis: Int = 5_000,
    val readTimeoutMillis: Int = 10_000
)

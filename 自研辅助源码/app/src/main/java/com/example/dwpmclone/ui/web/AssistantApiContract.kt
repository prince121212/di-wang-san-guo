package com.example.dwpmclone.ui.web

import org.json.JSONObject

data class AssistantApiRequest(
    val id: String,
    val method: String,
    val path: String,
    val body: JSONObject?
)

data class AssistantApiResponse(
    val id: String,
    val status: Int,
    val body: JSONObject
) {
    fun toJson(): JSONObject = JSONObject()
        .put("apiVersion", API_VERSION)
        .put("id", id)
        .put("status", status)
        .put("body", body)

    companion object {
        const val API_VERSION = "v1"
    }
}

object AssistantApiMessageCodec {
    const val MAX_MESSAGE_CHARS = 256 * 1024
    private val requestIdPattern = Regex("[A-Za-z0-9._:-]{1,96}")

    fun decode(raw: String): AssistantApiRequest {
        require(raw.length <= MAX_MESSAGE_CHARS) { "消息超过256KB限制" }
        val json = JSONObject(raw)
        require(json.optString("apiVersion") == AssistantApiResponse.API_VERSION) { "不支持的 API 版本" }
        val id = json.optString("id")
        require(requestIdPattern.matches(id)) { "请求 ID 无效" }
        val method = json.optString("method").uppercase()
        require(method == "GET" || method == "POST") { "只允许 GET/POST" }
        val path = json.optString("path")
        require(path.startsWith("/api/") && path.length <= 2048) { "API 路径无效" }
        require(".." !in path && '\\' !in path && path.none(Char::isISOControl)) { "API 路径包含非法字符" }
        val body = json.optJSONObject("body")
        return AssistantApiRequest(id, method, path, body)
    }

    fun error(id: String, status: Int, message: String): AssistantApiResponse = AssistantApiResponse(
        id = id.takeIf(requestIdPattern::matches) ?: "invalid",
        status = status,
        body = JSONObject().put("ok", false).put("error", message)
    )
}

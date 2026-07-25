package com.example.dwpmclone.domain.protocol

/**
 * Conservative offline parser for 小黄点刷黄出征 action responses.
 *
 * This does not send any action request. It only normalizes already captured response
 * text/hex so dispatch dry-runs and future calibration can tell whether the original
 * helper considered a 1520030/1522030 attempt successful, failed, or still unknown.
 */
data class BrushYellowDispatchResponse(
    val success: Boolean?,
    val message: String?,
    val usedAount: Int?,
    val rawText: String,
    val evidence: String
) {
    val consumedTimes: Int
        get() = when {
            usedAount != null -> usedAount
            success == true -> 1
            else -> 0
        }

    fun toRawMap(prefix: String = "dispatchResponse"): Map<String, String> = buildMap {
        put("${prefix}Success", success?.toString() ?: "unknown")
        message?.takeIf { it.isNotBlank() }?.let { put("${prefix}Message", it) }
        usedAount?.let {
            put("${prefix}UsedAount", it.toString())
            put("${prefix}UsedCount", it.toString())
        }
        put("${prefix}Evidence", evidence)
        if (rawText.isNotBlank()) put("${prefix}RawText", rawText.take(MAX_RAW_PREVIEW))
    }

    private companion object {
        const val MAX_RAW_PREVIEW = 512
    }
}

object BrushYellowDispatchResponseParser {
    private val SUCCESS_MARKERS = listOf(
        "刷黄出征成功",
        "出征成功",
        "消灭",
        "消滅",
        "战斗胜利",
        "戰鬥勝利",
        "继续搜索",
        "成功！继续搜索",
        "success"
    )
    private val FAILURE_MARKERS = listOf(
        "error",
        "失败",
        "不足",
        "不能出征",
        "无法出征",
        "不可出征",
        "已出征",
        "正在行军",
        "体力",
        "君主将",
        "没有找到",
        "异常",
        "fail",
        "failed"
    )
    private val USED_AOUNT_PATTERNS = listOf(
        Regex("usedAount\\s*[:=]\\s*[\"']?(\\d+)", RegexOption.IGNORE_CASE),
        Regex("usedAmount\\s*[:=]\\s*[\"']?(\\d+)", RegexOption.IGNORE_CASE),
        Regex("usedCount\\s*[:=]\\s*[\"']?(\\d+)", RegexOption.IGNORE_CASE),
        Regex("已刷\\s*(\\d+)\\s*次"),
        Regex("第\\s*(\\d+)\\s*次")
    )

    fun parseText(responseText: String): BrushYellowDispatchResponse {
        val text = responseText.trim()
        val normalized = text.lowercase()
        val explicitBoolean = extractExplicitSuccessBoolean(text)
        val markerFailure = FAILURE_MARKERS.firstOrNull { normalized.contains(it.lowercase()) || text.contains(it) }
        val markerSuccess = SUCCESS_MARKERS.firstOrNull { normalized.contains(it.lowercase()) || text.contains(it) }
        val failure = markerFailure ?: if (explicitBoolean == false) "success=false" else null
        val success = if (failure == null) markerSuccess ?: if (explicitBoolean == true) "success=true" else null else null
        val message = extractMessage(text) ?: when {
            failure != null -> failure
            success != null -> success
            text.isNotBlank() -> text.take(120)
            else -> null
        }
        val result = when {
            failure != null -> false
            success != null -> true
            else -> null
        }
        val used = extractUsedAount(text)
        val evidence = when {
            failure != null -> "failure-marker:$failure"
            success != null -> "success-marker:$success"
            used != null -> "usedAount-marker"
            else -> "no-known-marker"
        }
        return BrushYellowDispatchResponse(
            success = result,
            message = message,
            usedAount = used,
            rawText = text,
            evidence = evidence
        )
    }

    fun parseHex(responseHex: String): BrushYellowDispatchResponse {
        val normalizedHex = responseHex.filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }.lowercase()
        if (normalizedHex == "ff0000") {
            return BrushYellowDispatchResponse(
                success = false,
                message = "游戏服拒绝出征(0x8522=ff0000)，通常是将领体力/兵力/出征状态/目标状态不满足",
                usedAount = null,
                rawText = "",
                evidence = "hex-8522-ff0000-rejected"
            )
        }
        parse8522StatusPayload(normalizedHex)?.let { return it }
        val text = decodeHexText(responseHex)
        if (text.isNotBlank()) {
            val parsed = parseText(text)
            return parsed.copy(evidence = "hex->${parsed.evidence}")
        }
        return BrushYellowDispatchResponse(
            success = null,
            message = null,
            usedAount = null,
            rawText = "",
            evidence = "hex-decode-empty-or-invalid"
        )
    }

    fun parse(responseText: String? = null, responseHex: String? = null): BrushYellowDispatchResponse? {
        responseText?.takeIf { it.isNotBlank() }?.let { return parseText(it) }
        responseHex?.takeIf { it.isNotBlank() }?.let { return parseHex(it) }
        return null
    }

    private fun extractExplicitSuccessBoolean(text: String): Boolean? {
        Regex("[\"']success[\"']\\s*:\\s*(true|false|1|0)", RegexOption.IGNORE_CASE)
            .find(text)?.groupValues?.getOrNull(1)?.let { return it.equals("true", ignoreCase = true) || it == "1" }
        Regex("success\\s*=\\s*(true|false|1|0)", RegexOption.IGNORE_CASE)
            .find(text)?.groupValues?.getOrNull(1)?.let { return it.equals("true", ignoreCase = true) || it == "1" }
        return null
    }

    private fun extractUsedAount(text: String): Int? {
        for (pattern in USED_AOUNT_PATTERNS) {
            pattern.find(text)?.groupValues?.getOrNull(1)?.toIntOrNull()?.let { return it }
        }
        return null
    }

    private fun extractMessage(text: String): String? {
        if (text.isBlank()) return null
        Regex("[\"'](?:message|msg|error)[\"']\\s*:\\s*[\"']([^\"']+)[\"']", RegexOption.IGNORE_CASE)
            .find(text)?.groupValues?.getOrNull(1)?.takeIf { it.isNotBlank() }?.let { return it }
        Regex("(?:message|msg|error)\\s*=\\s*([^&|;\\r\\n]+)", RegexOption.IGNORE_CASE)
            .find(text)?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() }?.let { return it }
        return text.lineSequence().map { it.trim() }.firstOrNull { line ->
            line.contains("刷黄") || line.contains("出征") || line.contains("失败") || line.contains("error", ignoreCase = true)
        }
    }

    private fun decodeHexText(value: String): String {
        val hex = value.filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
        if (hex.length < 2 || hex.length % 2 != 0) return ""
        return runCatching {
            val bytes = ByteArray(hex.length / 2) { index ->
                hex.substring(index * 2, index * 2 + 2).toInt(16).toByte()
            }
            String(bytes, Charsets.UTF_8).trim('\u0000', ' ', '\r', '\n', '\t')
        }.getOrDefault("")
    }

    private fun parse8522StatusPayload(normalizedHex: String): BrushYellowDispatchResponse? {
        if (normalizedHex.length < 6 || normalizedHex.length % 2 != 0) return null
        val bytes = runCatching {
            ByteArray(normalizedHex.length / 2) { index ->
                normalizedHex.substring(index * 2, index * 2 + 2).toInt(16).toByte()
            }
        }.getOrNull() ?: return null
        val status = bytes[0].toInt()
        if (bytes.size < 3) return null
        val utfLen = ((bytes[1].toInt() and 0xff) shl 8) or (bytes[2].toInt() and 0xff)
        if (3 + utfLen > bytes.size) return null
        val msg = if (utfLen > 0) String(bytes, 3, utfLen, Charsets.UTF_8) else ""
        val evidence = "hex-8522-status-$status"
        if (status == 0) {
            val battleId = if (3 + utfLen + 8 <= bytes.size) {
                var v = 0L
                for (i in 0 until 8) v = (v shl 8) or (bytes[3 + utfLen + i].toLong() and 0xffL)
                v
            } else null
            return BrushYellowDispatchResponse(
                success = true,
                message = msg.ifBlank { "出征成功${battleId?.let { " battleId=$it" } ?: ""}" },
                usedAount = null,
                rawText = msg,
                evidence = evidence
            )
        }
        return BrushYellowDispatchResponse(
            success = false,
            message = msg.ifBlank { if (status == -1) "操作失败" else "失败状态 $status" },
            usedAount = null,
            rawText = msg,
            evidence = evidence
        )
    }
}

package com.example.dwpmclone.data.local

/** Final log boundary: redact authentication fields even if an upstream error embeds them. */
object SensitiveDataRedactor {
    private const val REDACTED = "[REDACTED]"
    private const val FIELD_NAMES =
        "password|passwd|pwd|tokenCiphertext|sessionToken|accessToken|authToken|token|dm|gameHttp|gameHttpUrl|cookie|secret"

    private val quotedJsonValue = Regex(
        """(?i)("(?:$FIELD_NAMES)"\s*:\s*)"(?:\\.|[^"\\])*""""
    )
    private val quotedSingleValue = Regex(
        """(?i)('(?:$FIELD_NAMES)'\s*:\s*)'(?:\\.|[^'\\])*'"""
    )
    private val plainAssignment = Regex(
        """(?i)\b($FIELD_NAMES)\b(\s*[:=]\s*)(?!\[REDACTED\])([^\s,;}&\]]+)"""
    )
    private val queryParameter = Regex(
        """(?i)([?&](?:$FIELD_NAMES)=)[^&\s]+"""
    )
    private val bearerToken = Regex(
        """(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"""
    )

    fun redact(message: String): String {
        if (message.isEmpty()) return message
        return message
            .replace(quotedJsonValue, "$1\"$REDACTED\"")
            .replace(quotedSingleValue, "$1'$REDACTED'")
            .replace(queryParameter, "$1$REDACTED")
            .replace(bearerToken, "Bearer $REDACTED")
            .replace(plainAssignment, "$1$2$REDACTED")
    }
}

package com.example.dwpmclone.domain.protocol

/**
 * Offline planner for 小黄点 native/session string wrapper.
 *
 * Reverse evidence shows the original helper sends a string body shaped as:
 *
 *   lx + key + gameHex + lb
 *
 * through `Landroid/o/ۥ;->ۦۜۖ(String)` with `application/x-www-form-urlencoded`.
 * The exact semantics/derivation of lx/key/lb/session/passCode still depend on native
 * HelpClass/Dbsl, so this planner is deliberately dry-run only and never authorizes network I/O.
 */
data class RecoveredNativeWrapperFields(
    val lx: String? = null,
    val key: String? = null,
    val lb: String? = null,
    val session: String? = null,
    val passCode: String? = null
)

data class RecoveredNativeActionWrapperPlan(
    val descriptor: GameHexDryRunDescriptor,
    val bodyShape: String,
    val contentType: String,
    val endpointPath: String,
    val requiredNativeFields: List<String>,
    val missingNativeFields: List<String>,
    val maskedRawConcatCandidate: String?,
    val networkSendAllowed: Boolean,
    val blocker: String
)

object RecoveredNativeWrapperFieldExtractor {
    fun from(extra: Map<String, String>): RecoveredNativeWrapperFields = RecoveredNativeWrapperFields(
        lx = extra.firstNonBlank(
            "nativeWrapperLx", "derivedNativeWrapperLx", "recoveredNativeLx", "lx",
            "gameRequestLx", "xhdLx"
        ),
        key = extra.firstNonBlank(
            "nativeWrapperKey", "derivedNativeWrapperKey", "recoveredNativeKey", "key",
            "gameRequestKey", "helpClassKey", "dbslGk", "gK"
        ),
        lb = extra.firstNonBlank(
            "nativeWrapperLb", "derivedNativeWrapperLb", "recoveredNativeLb", "lb",
            "gameRequestLb", "xhdLb"
        ),
        session = extra.firstNonBlank(
            "nativeWrapperSession", "recoveredNativeSession", "session", "helpClassSession"
        ),
        passCode = extra.firstNonBlank(
            "nativeWrapperPassCode", "recoveredNativePassCode", "passCode", "helpClassPassCode"
        )
    )

    private fun Map<String, String>.firstNonBlank(vararg keys: String): String? {
        for (key in keys) {
            this[key]?.takeIf { it.isNotBlank() }?.let { return it }
        }
        return null
    }
}

object RecoveredNativeActionWrapperPlanner {
    private val REQUIRED_FIELDS = listOf("lx", "key", "lb")

    fun plan(
        gameHex: String,
        fields: RecoveredNativeWrapperFields = RecoveredNativeWrapperFields()
    ): RecoveredNativeActionWrapperPlan {
        val descriptor = GameHexDryRunParser.describe(gameHex)
        val missing = buildList {
            if (fields.lx.isNullOrBlank()) add("lx")
            if (fields.key.isNullOrBlank()) add("key")
            if (fields.lb.isNullOrBlank()) add("lb")
        }
        val candidate = if (missing.isEmpty()) {
            mask(fields.lx!!) + mask(fields.key!!) + descriptor.normalizedHex + mask(fields.lb!!)
        } else {
            null
        }
        val blocker = when {
            descriptor.category == GameHexCategory.READ_ONLY_QUERY ->
                "这是只读查询；应使用 RealGameProtocolClient 的 041540/041542 allow-list gate，而不是 native 动作 wrapper"
            descriptor.category == GameHexCategory.EXPEDITION_ACTION || descriptor.category == GameHexCategory.STATE_CHANGING_ACTION ->
                "动作/出征 gameHex 仅完成 lx+key+gameHex+lb dry-run；HelpClass/Dbsl native session/key/lb 语义和响应校准完成前禁止真实发送"
            else ->
                "未知 gameHex 类别；native wrapper 字段与服务端响应均未验证，禁止真实发送"
        }
        return RecoveredNativeActionWrapperPlan(
            descriptor = descriptor,
            bodyShape = "lx + key + gameHex + lb",
            contentType = "application/x-www-form-urlencoded",
            endpointPath = "/kingWapServer/HttpClient",
            requiredNativeFields = REQUIRED_FIELDS,
            missingNativeFields = missing,
            maskedRawConcatCandidate = candidate,
            networkSendAllowed = false,
            blocker = if (missing.isEmpty()) blocker else "$blocker；缺少 ${missing.joinToString()}"
        )
    }

    private fun mask(value: String): String {
        val trimmed = value.trim()
        if (trimmed.length <= 4) return "****"
        return trimmed.take(2) + "****" + trimmed.takeLast(2)
    }
}

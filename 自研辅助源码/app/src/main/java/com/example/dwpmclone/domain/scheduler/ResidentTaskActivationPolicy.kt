package com.example.dwpmclone.domain.scheduler

/**
 * Resolves which desktop-style resident tasks are explicitly active for one account.
 *
 * An absent [ACTIVE_KEYS_FIELD] is a legacy session: when its old all-tasks flag is true,
 * every resident is restored. A present but empty field is intentionally different—it
 * means the user disabled every resident task. This distinction prevents disabling the
 * final task from unexpectedly restoring all residents on the next scheduler tick.
 */
object ResidentTaskActivationPolicy {
    const val STARTED_FIELD: String = "savedTasksStarted"
    const val ACTIVE_KEYS_FIELD: String = "activeResidentTaskKeys"

    fun activeKeys(
        channelExtra: Map<String, String>,
        allResidentKeys: Set<String>
    ): Set<String> {
        val explicit = channelExtra[ACTIVE_KEYS_FIELD]
        if (explicit != null) {
            return explicit.split(',')
                .asSequence()
                .map(String::trim)
                .filter(String::isNotEmpty)
                .filter { it in allResidentKeys }
                .toSet()
        }
        return if (channelExtra[STARTED_FIELD].equals("true", ignoreCase = true)) {
            allResidentKeys
        } else {
            emptySet()
        }
    }

    fun afterToggle(
        channelExtra: Map<String, String>,
        allResidentKeys: Set<String>,
        key: String,
        active: Boolean
    ): Set<String> {
        require(key in allResidentKeys) { "unknown resident task key: $key" }
        return activeKeys(channelExtra, allResidentKeys).toMutableSet().apply {
            if (active) add(key) else remove(key)
        }
    }

    fun encode(keys: Set<String>): String = keys.sorted().joinToString(",")

    fun stoppedUpdates(): Map<String, String> = mapOf(
        STARTED_FIELD to "false",
        ACTIVE_KEYS_FIELD to ""
    )
}

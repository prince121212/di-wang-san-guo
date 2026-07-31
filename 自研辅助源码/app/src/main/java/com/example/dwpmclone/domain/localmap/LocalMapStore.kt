package com.example.dwpmclone.domain.localmap

import com.example.dwpmclone.domain.model.MapCoordinate

enum class LocalMapKind { BANDIT, MINE }

/** A scan is reusable only for the exact account, server and search policy that produced it. */
data class LocalMapQueryKey(
    val accountId: Long,
    val serverId: String,
    val kind: LocalMapKind,
    val fingerprint: String
)

/**
 * Protocol-derived target metadata. Large packet dumps and credentials are deliberately excluded.
 * The enclosing [LocalMapSnapshot] supplies the account, server and search-policy identity.
 */
data class LocalMapTargetRecord(
    val targetId: Long,
    val coordinate: MapCoordinate,
    val type: String,
    val level: Int?,
    val filterFields: Map<String, String>,
    val firstDiscoveredAtMillis: Long,
    val lastValidatedAtMillis: Long,
    val invalidatedAtMillis: Long? = null,
    val invalidReason: String? = null
) {
    val active: Boolean
        get() = invalidatedAtMillis == null
}

data class LocalMapSnapshot(
    val query: LocalMapQueryKey,
    val scannedAtMillis: Long,
    val targets: List<LocalMapTargetRecord>
)

/** Persistence boundary used by the hot cache; V1 has no network-backed implementation. */
interface LocalMapStore {
    fun read(query: LocalMapQueryKey): LocalMapSnapshot?
    fun replace(snapshot: LocalMapSnapshot)
    fun invalidate(query: LocalMapQueryKey, targetId: Long, invalidatedAtMillis: Long, reason: String)
    fun expire(query: LocalMapQueryKey)
    fun list(accountId: Long, serverId: String, kind: LocalMapKind): List<LocalMapTargetRecord>
    fun clearAccount(accountId: Long)
}

/** Default for pure domain tests and callers that intentionally need process-only caching. */
object NoOpLocalMapStore : LocalMapStore {
    override fun read(query: LocalMapQueryKey): LocalMapSnapshot? = null
    override fun replace(snapshot: LocalMapSnapshot) = Unit
    override fun invalidate(
        query: LocalMapQueryKey,
        targetId: Long,
        invalidatedAtMillis: Long,
        reason: String
    ) = Unit
    override fun expire(query: LocalMapQueryKey) = Unit
    override fun list(accountId: Long, serverId: String, kind: LocalMapKind): List<LocalMapTargetRecord> = emptyList()
    override fun clearAccount(accountId: Long) = Unit
}

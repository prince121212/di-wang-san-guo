package com.example.dwpmclone.domain.localmap

import com.example.dwpmclone.domain.model.MapCoordinate

enum class LocalMapKind { BANDIT, MINE }

/**
 * Identifies one stored scan: who ran it, on which server, under which policy.
 *
 * The account belongs in the *write* key, because "account 176 saw this at
 * 22:09" is the true statement. It does not belong in the read: where a bandit
 * stands is a fact about the server map, so a peer on the same server and the
 * same search policy observed the same thing. Reading per-account made two
 * accounts on one device rediscover an identical map independently - one held
 * 215 targets while the other held 5 - which is also why sharing them needed a
 * cloud round trip that the same process could have answered for free. See
 * [LocalMapStore.readShared].
 */
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

    /**
     * Every account's view of the same server, region and target kind, merged.
     *
     * Returns null when no account has scanned it. The reported
     * `scannedAtMillis` is the freshest contributing scan, so a caller's
     * staleness check still behaves as if it had scanned that recently.
     */
    fun readShared(query: LocalMapQueryKey): LocalMapSnapshot?
    fun replace(snapshot: LocalMapSnapshot)
    fun invalidate(query: LocalMapQueryKey, targetId: Long, invalidatedAtMillis: Long, reason: String)
    fun expire(query: LocalMapQueryKey)
    fun list(accountId: Long, serverId: String, kind: LocalMapKind): List<LocalMapTargetRecord>
    fun clearAccount(accountId: Long)
}

/** Default for pure domain tests and callers that intentionally need process-only caching. */
object NoOpLocalMapStore : LocalMapStore {
    override fun read(query: LocalMapQueryKey): LocalMapSnapshot? = null
    override fun readShared(query: LocalMapQueryKey): LocalMapSnapshot? = null
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

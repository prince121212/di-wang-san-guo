package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.localmap.LocalMapKind
import com.example.dwpmclone.domain.localmap.LocalMapQueryKey
import com.example.dwpmclone.domain.localmap.LocalMapSnapshot
import com.example.dwpmclone.domain.localmap.LocalMapStore
import com.example.dwpmclone.domain.localmap.LocalMapTargetRecord

/** Lightweight JSON persistence. Map reads never initialize a database or perform network I/O. */
class LocalMapRepository(context: Context) : LocalMapStore {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private var cachedRaw: String? = null
    private var cachedSnapshots: List<LocalMapSnapshot> = emptyList()

    override fun read(query: LocalMapQueryKey): LocalMapSnapshot? = synchronized(PROCESS_LOCK) {
        load().firstOrNull { it.query == query }
    }

    override fun readShared(query: LocalMapQueryKey): LocalMapSnapshot? =
        synchronized(PROCESS_LOCK) {
            val contributing = load().filter {
                it.query.serverId == query.serverId &&
                    it.query.kind == query.kind &&
                    it.query.fingerprint == query.fingerprint
            }
            if (contributing.isEmpty()) return@synchronized null
            // Keep the newest record per target: an invalidation by any account
            // means the bandit is gone for everyone, and a later re-validation
            // means it is back.
            val merged = contributing.asSequence()
                .flatMap { it.targets.asSequence() }
                .groupBy { it.targetId }
                .values
                .mapNotNull { records ->
                    records.maxByOrNull {
                        it.invalidatedAtMillis ?: it.lastValidatedAtMillis
                    }
                }
                .sortedWith(
                    compareBy<LocalMapTargetRecord> { it.coordinate.y }
                        .thenBy { it.coordinate.x }
                )
            LocalMapSnapshot(
                query = query,
                scannedAtMillis = contributing.maxOf { it.scannedAtMillis },
                targets = merged
            )
        }

    override fun replace(snapshot: LocalMapSnapshot) = synchronized(PROCESS_LOCK) {
        write(LocalMapSnapshotReducer.replace(load(), snapshot))
    }

    override fun invalidate(
        query: LocalMapQueryKey,
        targetId: Long,
        invalidatedAtMillis: Long,
        reason: String
    ) = synchronized(PROCESS_LOCK) {
        write(LocalMapSnapshotReducer.invalidate(load(), query, targetId, invalidatedAtMillis, reason))
    }

    override fun expire(query: LocalMapQueryKey) = synchronized(PROCESS_LOCK) {
        write(LocalMapSnapshotReducer.expire(load(), query))
    }

    override fun list(
        accountId: Long,
        serverId: String,
        kind: LocalMapKind
    ): List<LocalMapTargetRecord> = synchronized(PROCESS_LOCK) {
        load().asSequence()
            .filter {
                it.query.accountId == accountId &&
                    it.query.serverId == serverId &&
                    it.query.kind == kind
            }
            .flatMap { it.targets.asSequence() }
            .groupBy { it.targetId }
            .values
            .mapNotNull { records ->
                records.maxByOrNull { it.invalidatedAtMillis ?: it.lastValidatedAtMillis }
            }
            .sortedWith(compareBy<LocalMapTargetRecord> { it.coordinate.y }.thenBy { it.coordinate.x })
    }

    override fun clearAccount(accountId: Long) = synchronized(PROCESS_LOCK) {
        write(load().filterNot { it.query.accountId == accountId })
    }

    /** Invalidates one observed target in every matching search fingerprint. */
    fun invalidateAcrossKind(
        accountId: Long,
        serverId: String,
        kind: com.example.dwpmclone.domain.localmap.LocalMapKind,
        targetId: Long,
        invalidatedAtMillis: Long,
        reason: String
    ) = synchronized(PROCESS_LOCK) {
        write(load().map { snapshot ->
            if (
                snapshot.query.accountId != accountId ||
                snapshot.query.serverId != serverId ||
                snapshot.query.kind != kind
            ) {
                snapshot
            } else {
                snapshot.copy(targets = snapshot.targets.map { target ->
                    if (target.targetId != targetId) target else target.copy(
                        invalidatedAtMillis = invalidatedAtMillis,
                        invalidReason = reason.take(240)
                    )
                })
            }
        })
    }

    private fun load(): List<LocalMapSnapshot> {
        val raw = preferences.getString(KEY_STATE, null)
        if (raw == cachedRaw) return cachedSnapshots
        cachedRaw = raw
        cachedSnapshots = LocalMapJsonCodec.decode(raw)
        return cachedSnapshots
    }

    private fun write(snapshots: List<LocalMapSnapshot>) {
        val raw = LocalMapJsonCodec.encode(snapshots)
        cachedRaw = raw
        cachedSnapshots = snapshots
        // Map observations are recoverable by rescanning, so avoid blocking a scheduler tick on fsync.
        preferences.edit().putString(KEY_STATE, raw).apply()
    }

    private companion object {
        val PROCESS_LOCK = Any()
        const val PREFERENCES_NAME = "dwpm_local_map_v1"
        const val KEY_STATE = "state"
    }
}

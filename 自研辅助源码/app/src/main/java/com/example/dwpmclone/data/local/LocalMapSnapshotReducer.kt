package com.example.dwpmclone.data.local

import com.example.dwpmclone.domain.localmap.LocalMapQueryKey
import com.example.dwpmclone.domain.localmap.LocalMapSnapshot

/** Pure state reducer kept separate from Android storage and JSON encoding. */
internal object LocalMapSnapshotReducer {
    private const val DEFAULT_MAX_SNAPSHOTS = 32
    private const val DEFAULT_MAX_TARGETS_PER_SNAPSHOT = 512
    private const val DEFAULT_INVALID_RETENTION_MILLIS = 24L * 60L * 60L * 1_000L

    fun replace(
        snapshots: List<LocalMapSnapshot>,
        incoming: LocalMapSnapshot,
        maxSnapshots: Int = DEFAULT_MAX_SNAPSHOTS,
        maxTargetsPerSnapshot: Int = DEFAULT_MAX_TARGETS_PER_SNAPSHOT,
        invalidRetentionMillis: Long = DEFAULT_INVALID_RETENTION_MILLIS
    ): List<LocalMapSnapshot> {
        val previous = snapshots.firstOrNull { it.query == incoming.query }
        val incomingIds = incoming.targets.mapTo(linkedSetOf()) { it.targetId }
        val firstSeenByTarget = snapshots.asSequence()
            .filter { it.query.sameTargetScope(incoming.query) }
            .flatMap { it.targets.asSequence() }
            .groupBy { it.targetId }
            .mapValues { (_, records) -> records.minOf { it.firstDiscoveredAtMillis } }

        val active = incoming.targets
            .distinctBy { it.targetId }
            .map { record ->
                record.copy(
                    firstDiscoveredAtMillis = minOf(
                        record.firstDiscoveredAtMillis,
                        firstSeenByTarget[record.targetId] ?: record.firstDiscoveredAtMillis
                    ),
                    lastValidatedAtMillis = incoming.scannedAtMillis,
                    invalidatedAtMillis = null,
                    invalidReason = null
                )
            }
        val tombstones = previous?.targets.orEmpty()
            .filter { it.targetId !in incomingIds }
            .map { record ->
                if (record.active) {
                    record.copy(
                        invalidatedAtMillis = incoming.scannedAtMillis,
                        invalidReason = "missing-from-rescan"
                    )
                } else {
                    record
                }
            }
        val merged = (active + tombstones)
            .filter {
                it.active || incoming.scannedAtMillis - (it.invalidatedAtMillis ?: 0L) <= invalidRetentionMillis
            }
            .sortedWith(
                compareByDescending<com.example.dwpmclone.domain.localmap.LocalMapTargetRecord> { it.active }
                    .thenByDescending { it.lastValidatedAtMillis }
            )
            .take(maxTargetsPerSnapshot.coerceAtLeast(1))

        return prune(
            snapshots.filterNot { it.query == incoming.query } + incoming.copy(targets = merged),
            incoming.scannedAtMillis,
            maxSnapshots,
            maxTargetsPerSnapshot,
            invalidRetentionMillis
        )
    }

    fun invalidate(
        snapshots: List<LocalMapSnapshot>,
        query: LocalMapQueryKey,
        targetId: Long,
        invalidatedAtMillis: Long,
        reason: String
    ): List<LocalMapSnapshot> = snapshots.map snapshotMap@{ snapshot ->
        if (!snapshot.query.sameTargetScope(query)) return@snapshotMap snapshot
        var changed = false
        val targets = snapshot.targets.map targetMap@{ record ->
            if (record.targetId != targetId || !record.active) return@targetMap record
            changed = true
            record.copy(
                invalidatedAtMillis = invalidatedAtMillis,
                invalidReason = reason.take(160)
            )
        }
        if (!changed) snapshot else snapshot.copy(
            // An exhausted scan must be refreshed on the next task pass.
            scannedAtMillis = if (targets.none { it.active }) 0L else snapshot.scannedAtMillis,
            targets = targets
        )
    }

    fun expire(snapshots: List<LocalMapSnapshot>, query: LocalMapQueryKey): List<LocalMapSnapshot> =
        snapshots.map { if (it.query == query) it.copy(scannedAtMillis = 0L) else it }

    fun prune(
        snapshots: List<LocalMapSnapshot>,
        nowMillis: Long,
        maxSnapshots: Int = DEFAULT_MAX_SNAPSHOTS,
        maxTargetsPerSnapshot: Int = DEFAULT_MAX_TARGETS_PER_SNAPSHOT,
        invalidRetentionMillis: Long = DEFAULT_INVALID_RETENTION_MILLIS
    ): List<LocalMapSnapshot> = snapshots
        .map { snapshot ->
            snapshot.copy(
                targets = snapshot.targets
                    .filter {
                        it.active || nowMillis - (it.invalidatedAtMillis ?: 0L) <= invalidRetentionMillis
                    }
                    .take(maxTargetsPerSnapshot.coerceAtLeast(1))
            )
        }
        .sortedByDescending { snapshot ->
            maxOf(snapshot.scannedAtMillis, snapshot.targets.maxOfOrNull {
                it.invalidatedAtMillis ?: it.lastValidatedAtMillis
            } ?: 0L)
        }
        .take(maxSnapshots.coerceAtLeast(1))

    private fun LocalMapQueryKey.sameTargetScope(other: LocalMapQueryKey): Boolean =
        accountId == other.accountId && serverId == other.serverId && kind == other.kind
}

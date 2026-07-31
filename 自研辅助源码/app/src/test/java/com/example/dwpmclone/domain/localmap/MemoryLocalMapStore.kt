package com.example.dwpmclone.domain.localmap

/** Shared test double used to model a durable store across hot-cache reconstruction. */
internal class MemoryLocalMapStore : LocalMapStore {
    private val snapshots = linkedMapOf<LocalMapQueryKey, LocalMapSnapshot>()

    override fun read(query: LocalMapQueryKey): LocalMapSnapshot? = snapshots[query]

    override fun replace(snapshot: LocalMapSnapshot) {
        snapshots[snapshot.query] = snapshot
    }

    override fun invalidate(
        query: LocalMapQueryKey,
        targetId: Long,
        invalidatedAtMillis: Long,
        reason: String
    ) {
        snapshots.keys.filter {
            it.accountId == query.accountId && it.serverId == query.serverId && it.kind == query.kind
        }.forEach { key ->
            val snapshot = snapshots.getValue(key)
            val targets = snapshot.targets.map { record ->
                if (record.targetId == targetId && record.active) {
                    record.copy(invalidatedAtMillis = invalidatedAtMillis, invalidReason = reason)
                } else {
                    record
                }
            }
            snapshots[key] = snapshot.copy(
                scannedAtMillis = if (targets.none { it.active }) 0L else snapshot.scannedAtMillis,
                targets = targets
            )
        }
    }

    override fun expire(query: LocalMapQueryKey) {
        snapshots[query]?.let { snapshots[query] = it.copy(scannedAtMillis = 0L) }
    }

    override fun list(
        accountId: Long,
        serverId: String,
        kind: LocalMapKind
    ): List<LocalMapTargetRecord> = snapshots.values
        .filter { it.query.accountId == accountId && it.query.serverId == serverId && it.query.kind == kind }
        .flatMap { it.targets }

    override fun clearAccount(accountId: Long) {
        snapshots.keys.removeAll { it.accountId == accountId }
    }
}

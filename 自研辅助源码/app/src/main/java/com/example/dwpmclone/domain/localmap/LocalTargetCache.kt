package com.example.dwpmclone.domain.localmap

import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineConfig
import com.example.dwpmclone.domain.model.MineType
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.protocol.MineSearchResult

data class BanditCacheKey(
    val accountId: Long,
    val start: MapCoordinate,
    val targetType: HuangTargetType,
    val serverId: String = ""
) {
    fun query(): LocalMapQueryKey = LocalMapQueryKey(
        accountId = accountId,
        serverId = normalizedServerId(accountId, serverId),
        kind = LocalMapKind.BANDIT,
        fingerprint = "${start.x},${start.y}|${targetType.name}"
    )

    companion object {
        fun from(session: GameSession, start: MapCoordinate, targetType: HuangTargetType) = BanditCacheKey(
            accountId = session.accountId,
            start = start,
            targetType = targetType,
            serverId = session.localMapServerId()
        )
    }
}

data class MineCacheKey(
    val accountId: Long,
    val start: MapCoordinate,
    val mineTypes: Set<String>,
    val levels: Set<Int>,
    val scope: String,
    val onlyEmpty: Boolean,
    val onlyDefended: Boolean,
    val serverId: String = ""
) {
    fun query(): LocalMapQueryKey = LocalMapQueryKey(
        accountId = accountId,
        serverId = normalizedServerId(accountId, serverId),
        kind = LocalMapKind.MINE,
        fingerprint = buildString {
            append(start.x).append(',').append(start.y).append('|')
            append(mineTypes.sorted().joinToString(",")).append('|')
            append(levels.sorted().joinToString(",")).append('|')
            append(scope.trim().replace("|", "")).append('|')
            append(onlyEmpty).append('|').append(onlyDefended)
        }
    )

    companion object {
        fun from(accountId: Long, config: MineConfig): MineCacheKey = from(accountId, "", config)

        fun from(session: GameSession, config: MineConfig): MineCacheKey =
            from(session.accountId, session.localMapServerId(), config)

        private fun from(accountId: Long, serverId: String, config: MineConfig): MineCacheKey = MineCacheKey(
            accountId = accountId,
            start = config.start,
            mineTypes = config.selectedMineTypes.mapTo(sortedSetOf()) { it.name },
            levels = config.selectedLevels.toSortedSet(),
            scope = config.searchScope,
            onlyEmpty = config.onlyEmptyMine,
            onlyDefended = config.onlyDefendedMine,
            serverId = serverId
        )
    }
}

/**
 * Bounded hot layer over [LocalMapStore]. Empty scans are cached to avoid request loops;
 * consumed or rejected targets expire their scan immediately when no candidates remain.
 */
class LocalTargetCache(
    private val banditTtlMillis: Long = DEFAULT_BANDIT_TTL_MILLIS,
    private val banditEmptyTtlMillis: Long = minOf(
        banditTtlMillis,
        DEFAULT_BANDIT_EMPTY_TTL_MILLIS
    ),
    private val mineTtlMillis: Long = DEFAULT_MINE_TTL_MILLIS,
    private val maxQueries: Int = 32,
    private val maxTargetsPerQuery: Int = 512,
    private val store: LocalMapStore = NoOpLocalMapStore
) {
    private data class Entry<T>(val observedAtMillis: Long, val targets: List<T>)

    private val bandits = linkedMapOf<BanditCacheKey, Entry<MapTarget>>()
    private val mines = linkedMapOf<MineCacheKey, Entry<MineSearchResult>>()
    private val mineRuleCursors = linkedMapOf<Long, Int>()
    private val preparationCursors = linkedMapOf<Pair<Long, String>, Int>()

    @Synchronized
    fun nextMineRuleIndex(accountId: Long, ruleCount: Int): Int {
        if (ruleCount <= 0) return 0
        val current = (mineRuleCursors[accountId] ?: 0).mod(ruleCount)
        mineRuleCursors[accountId] = (current + 1).mod(ruleCount)
        return current
    }

    /** Service-lifetime round-robin cursor for one-request-at-a-time idle map preparation. */
    @Synchronized
    fun nextPreparationIndex(accountId: Long, key: String, itemCount: Int): Int {
        if (itemCount <= 0) return 0
        val cursorKey = accountId to key.take(500)
        val current = Math.floorMod(preparationCursors[cursorKey] ?: 0, itemCount)
        preparationCursors[cursorKey] = Math.floorMod(current + 1, itemCount)
        return current
    }

    @Synchronized
    fun bandits(key: BanditCacheKey, nowMillis: Long): List<MapTarget>? {
        freshBandits(key, nowMillis)?.let { return it }
        val snapshot = store.read(key.query()) ?: return null
        val targets = snapshot.targets.asSequence()
            .filter { it.active }
            .map { it.toMapTarget() }
            .take(maxTargetsPerQuery)
            .toList()
        val ttl = if (targets.isEmpty()) banditEmptyTtlMillis else banditTtlMillis
        if (!isFresh(snapshot.scannedAtMillis, nowMillis, ttl)) return null
        put(bandits, key, targets, snapshot.scannedAtMillis)
        return targets
    }

    @Synchronized
    fun saveBandits(key: BanditCacheKey, targets: List<MapTarget>, observedAtMillis: Long) {
        val distinct = targets.distinctBy { it.id }.take(maxTargetsPerQuery)
        put(bandits, key, distinct, observedAtMillis)
        store.replace(
            LocalMapSnapshot(
                query = key.query(),
                scannedAtMillis = observedAtMillis,
                targets = distinct.map { it.toRecord(observedAtMillis) }
            )
        )
    }

    @Synchronized
    fun invalidateBandit(
        key: BanditCacheKey,
        targetId: Long,
        invalidatedAtMillis: Long = System.currentTimeMillis(),
        reason: String = "consumed-or-rejected"
    ) {
        invalidateAcrossScope(bandits, key.accountId, key.query().serverId, targetId) { it.id }
        store.invalidate(key.query(), targetId, invalidatedAtMillis, reason)
    }

    @Synchronized
    fun clearBandits(key: BanditCacheKey) {
        bandits.remove(key)
        store.expire(key.query())
    }

    @Synchronized
    fun mines(key: MineCacheKey, nowMillis: Long): List<MineSearchResult>? {
        fresh(mines, key, nowMillis, mineTtlMillis)?.let { return it }
        val snapshot = store.read(key.query()) ?: return null
        if (!isFresh(snapshot.scannedAtMillis, nowMillis, mineTtlMillis)) return null
        val targets = snapshot.targets.asSequence()
            .filter { it.active }
            .mapNotNull { it.toMineSearchResult() }
            .take(maxTargetsPerQuery)
            .toList()
        put(mines, key, targets, snapshot.scannedAtMillis)
        return targets
    }

    @Synchronized
    fun saveMines(key: MineCacheKey, targets: List<MineSearchResult>, observedAtMillis: Long) {
        val distinct = targets.distinctBy { it.id }.take(maxTargetsPerQuery)
        put(mines, key, distinct, observedAtMillis)
        store.replace(
            LocalMapSnapshot(
                query = key.query(),
                scannedAtMillis = observedAtMillis,
                targets = distinct.map { it.toRecord(observedAtMillis) }
            )
        )
    }

    @Synchronized
    fun invalidateMine(
        key: MineCacheKey,
        targetId: Long,
        invalidatedAtMillis: Long = System.currentTimeMillis(),
        reason: String = "consumed-or-rejected"
    ) {
        invalidateAcrossScope(mines, key.accountId, key.query().serverId, targetId) { it.id }
        store.invalidate(key.query(), targetId, invalidatedAtMillis, reason)
    }

    @Synchronized
    fun clearMines(key: MineCacheKey) {
        mines.remove(key)
        store.expire(key.query())
    }

    @Synchronized
    fun clearAccount(accountId: Long) {
        bandits.keys.removeAll { it.accountId == accountId }
        mines.keys.removeAll { it.accountId == accountId }
        mineRuleCursors.remove(accountId)
        preparationCursors.keys.removeAll { it.first == accountId }
        store.clearAccount(accountId)
    }

    private fun <K, T> fresh(
        cache: MutableMap<K, Entry<T>>,
        key: K,
        nowMillis: Long,
        ttlMillis: Long
    ): List<T>? {
        val entry = cache[key] ?: return null
        if (!isFresh(entry.observedAtMillis, nowMillis, ttlMillis)) {
            cache.remove(key)
            return null
        }
        return entry.targets.toList()
    }

    private fun freshBandits(key: BanditCacheKey, nowMillis: Long): List<MapTarget>? {
        val entry = bandits[key] ?: return null
        val ttl = if (entry.targets.isEmpty()) banditEmptyTtlMillis else banditTtlMillis
        if (!isFresh(entry.observedAtMillis, nowMillis, ttl)) {
            bandits.remove(key)
            return null
        }
        return entry.targets.toList()
    }

    private fun isFresh(observedAtMillis: Long, nowMillis: Long, ttlMillis: Long): Boolean {
        val age = nowMillis - observedAtMillis
        return observedAtMillis > 0L && age in 0L..ttlMillis
    }

    private fun <K, T> put(
        cache: LinkedHashMap<K, Entry<T>>,
        key: K,
        targets: List<T>,
        observedAtMillis: Long
    ) {
        cache.remove(key)
        cache[key] = Entry(observedAtMillis, targets.toList())
        while (cache.size > maxQueries) cache.remove(cache.keys.first())
    }

    private fun <K, T> invalidateAcrossScope(
        cache: LinkedHashMap<K, Entry<T>>,
        accountId: Long,
        serverId: String,
        targetId: Long,
        idOf: (T) -> Long
    ) where K : Any {
        val keys = cache.keys.filter { key ->
            when (key) {
                is BanditCacheKey -> key.accountId == accountId && key.query().serverId == serverId
                is MineCacheKey -> key.accountId == accountId && key.query().serverId == serverId
                else -> false
            }
        }
        keys.forEach { key ->
            val entry = cache[key] ?: return@forEach
            val remaining = entry.targets.filterNot { idOf(it) == targetId }
            if (remaining.isEmpty()) cache.remove(key) else cache[key] = entry.copy(targets = remaining)
        }
    }

    private fun MapTarget.toRecord(observedAtMillis: Long): LocalMapTargetRecord = LocalMapTargetRecord(
        targetId = id,
        coordinate = coordinate,
        type = type,
        level = rawInt("level", "rank", "fz"),
        filterFields = sanitizeFields(raw + mapOf("type" to type)),
        firstDiscoveredAtMillis = observedAtMillis,
        lastValidatedAtMillis = observedAtMillis
    )

    private fun MineSearchResult.toRecord(observedAtMillis: Long): LocalMapTargetRecord {
        val canonical = buildMap {
            putAll(raw)
            put("mineType", mineType.name)
            level?.let { put("level", it.toString()) }
            reserve?.let { put("reserve", it.toString()) }
            put("isEmpty", isEmpty.toString())
            put("playerOccupied", playerOccupied.toString())
            ownerName?.let { put("ownerName", it) }
            defenseCount?.let { put("defenseCount", it.toString()) }
        }
        return LocalMapTargetRecord(
            targetId = id,
            coordinate = coordinate,
            type = mineType.name,
            level = level,
            filterFields = sanitizeFields(canonical),
            firstDiscoveredAtMillis = observedAtMillis,
            lastValidatedAtMillis = observedAtMillis
        )
    }

    private fun LocalMapTargetRecord.toMapTarget(): MapTarget = MapTarget(
        id = targetId,
        coordinate = coordinate,
        type = type,
        raw = filterFields
    )

    private fun LocalMapTargetRecord.toMineSearchResult(): MineSearchResult? {
        val mineType = runCatching { MineType.valueOf(type) }.getOrNull()
            ?: filterFields["mineType"]?.let { runCatching { MineType.valueOf(it) }.getOrNull() }
            ?: return null
        return MineSearchResult(
            id = targetId,
            coordinate = coordinate,
            mineType = mineType,
            level = level,
            reserve = filterFields["reserve"]?.toLongOrNull(),
            isEmpty = filterFields["isEmpty"]?.toBooleanStrictOrNull() ?: false,
            defenseCount = filterFields["defenseCount"]?.toIntOrNull(),
            raw = filterFields,
            playerOccupied = filterFields["playerOccupied"]?.toBooleanStrictOrNull() ?: false,
            ownerName = filterFields["ownerName"]
        )
    }

    private fun MapTarget.rawInt(vararg keys: String): Int? {
        keys.forEach { key ->
            raw[key]?.filter { it.isDigit() || it == '-' }
                ?.takeIf { it.isNotBlank() }
                ?.toIntOrNull()
                ?.let { return it }
        }
        return null
    }

    private fun sanitizeFields(fields: Map<String, String>): Map<String, String> = fields.asSequence()
        .map { it.key.trim() to it.value.trim() }
        .filter { (key, value) -> key.isNotBlank() && key.length <= 64 && value.length <= 512 }
        .filterNot { (key, _) ->
            val lower = key.lowercase()
            lower.contains("password") || lower.contains("token") || lower.contains("session") ||
                lower.contains("payload") || lower == "rawrecord" || lower == "tailhex"
        }
        .take(MAX_PERSISTED_FILTER_FIELDS)
        .associateTo(linkedMapOf()) { (key, value) -> key to value.take(MAX_PERSISTED_FIELD_LENGTH) }

    companion object {
        const val DEFAULT_BANDIT_TTL_MILLIS = 1_800_000L
        const val DEFAULT_BANDIT_EMPTY_TTL_MILLIS = 120_000L
        const val DEFAULT_MINE_TTL_MILLIS = 10_800_000L
        private const val MAX_PERSISTED_FILTER_FIELDS = 48
        private const val MAX_PERSISTED_FIELD_LENGTH = 256
    }
}

private fun GameSession.localMapServerId(): String = normalizedServerId(
    accountId,
    channelExtra["serverKey"]
        ?: channelExtra["serverId"]
        ?: channelExtra["areaKey"]
        ?: ""
)

private fun normalizedServerId(accountId: Long, value: String): String =
    value.trim().takeIf { it.isNotBlank() } ?: "account:$accountId"

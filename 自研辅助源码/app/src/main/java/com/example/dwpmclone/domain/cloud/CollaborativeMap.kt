package com.example.dwpmclone.domain.cloud

import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.protocol.MineSearchResult

/**
 * Cloud-map boundary shared by brush-yellow and mining.
 *
 * The ordering invariant is intentional and testable:
 *   scan locally -> upload the complete observation batch -> receive upload receipt
 *   -> ask cloud for one target -> only then may the caller dispatch.
 *
 * A failed/missing cloud service never falls back to a local target when
 * `collaborativeMapRequired=true`.
 */
interface CollaborativeMapClient {
    suspend fun upload(request: ObservationUploadRequest): CloudMapResult<UploadReceipt>
    suspend fun recommend(request: TargetRecommendationRequest): CloudMapResult<CloudTarget?>
    suspend fun reportExpedition(request: ExpeditionResultRequest): CloudMapResult<ExpeditionResultReceipt> =
        CloudMapResult.Err(
            "CLOUD_MAP_RESULT_NOT_SUPPORTED",
            "云端地图服务尚未接入出征结果回传接口",
            false
        )
}

enum class CloudMapKind { BANDIT, MINE }

data class CloudMapObservation(
    val targetId: Long,
    val coordinate: MapCoordinate,
    val targetType: String,
    val level: Int?,
    val observedAtMillis: Long,
    val raw: Map<String, String> = emptyMap()
)

data class ObservationUploadRequest(
    val accountId: Long,
    val serverId: String,
    val kind: CloudMapKind,
    val observations: List<CloudMapObservation>,
    val observedAtMillis: Long,
    val clientBatchId: String
)

data class UploadReceipt(
    val accepted: Int,
    val serverRevision: String,
    val clientBatchId: String
)

data class TargetRecommendationRequest(
    val accountId: Long,
    val serverId: String,
    val kind: CloudMapKind,
    val start: MapCoordinate,
    val acceptedRevision: String,
    val targetType: String?,
    val allowedMineTypes: Set<String> = emptySet()
)

data class CloudTarget(
    val targetId: Long,
    val coordinate: MapCoordinate,
    val targetType: String,
    val level: Int?,
    val serverRevision: String,
    val raw: Map<String, String> = emptyMap()
)

data class ExpeditionResultRequest(
    val accountId: Long,
    val serverId: String,
    val kind: CloudMapKind,
    val targetId: Long,
    val acceptedRevision: String,
    val success: Boolean,
    val message: String,
    val reportedAtMillis: Long,
    val raw: Map<String, String> = emptyMap(),
    val clientResultId: String = ""
)

data class ExpeditionResultReceipt(
    val accepted: Boolean,
    val serverRevision: String,
    val targetId: Long
)

sealed class CloudMapResult<out T> {
    data class Ok<T>(val value: T) : CloudMapResult<T>()
    data class Err(val code: String, val message: String, val retryable: Boolean) : CloudMapResult<Nothing>()
}

/**
 * No cloud endpoint is configured yet. This client fails closed rather than allowing an
 * accidental local-only expedition.
 */
object DisabledCollaborativeMapClient : CollaborativeMapClient {
    override suspend fun upload(request: ObservationUploadRequest): CloudMapResult<UploadReceipt> =
        CloudMapResult.Err(
            code = "CLOUD_MAP_NOT_CONFIGURED",
            message = "云端山贼/矿点地图尚未配置；已停止在本地地图上直接决定出征",
            retryable = true
        )

    override suspend fun recommend(request: TargetRecommendationRequest): CloudMapResult<CloudTarget?> =
        CloudMapResult.Err(
            code = "CLOUD_MAP_NOT_CONFIGURED",
            message = "云端地图尚未配置，无法获取推荐目标",
            retryable = true
        )

    override suspend fun reportExpedition(request: ExpeditionResultRequest): CloudMapResult<ExpeditionResultReceipt> =
        CloudMapResult.Err(
            code = "CLOUD_MAP_NOT_CONFIGURED",
            message = "云端地图尚未配置，无法回传出征结果",
            retryable = true
        )
}

class CloudFirstMapCoordinator(
    private val client: CollaborativeMapClient = DisabledCollaborativeMapClient
) {
    suspend fun reportExpedition(
        session: GameSession,
        kind: CloudMapKind,
        targetId: Long,
        acceptedRevision: String,
        success: Boolean,
        message: String,
        nowMillis: Long,
        raw: Map<String, String> = emptyMap()
    ): CloudMapResult<ExpeditionResultReceipt> {
        if (!session.cloudMapRequired()) {
            return CloudMapResult.Ok(ExpeditionResultReceipt(true, acceptedRevision, targetId))
        }
        val serverId = session.serverIdentity()
            ?: return CloudMapResult.Err(
                "CLOUD_MAP_SERVER_ID_MISSING",
                "云端出征结果回传缺少区服标识",
                false
            )
        if (acceptedRevision.isBlank()) {
            return CloudMapResult.Err(
                "CLOUD_MAP_RESULT_REVISION_MISSING",
                "云端出征结果回传缺少推荐版本",
                false
            )
        }
        return client.reportExpedition(
            ExpeditionResultRequest(
                accountId = session.accountId,
                serverId = serverId,
                kind = kind,
                targetId = targetId,
                acceptedRevision = acceptedRevision,
                success = success,
                message = message,
                reportedAtMillis = nowMillis,
                raw = raw,
                clientResultId = "${session.accountId}-${kind.name.lowercase()}-$targetId-$acceptedRevision"
            )
        )
    }

    suspend fun selectBanditTargets(
        session: GameSession,
        observed: List<MapTarget>,
        start: MapCoordinate,
        targetType: HuangTargetType,
        nowMillis: Long
    ): CloudMapResult<List<MapTarget>> {
        if (!session.cloudMapRequired()) return CloudMapResult.Ok(observed)
        val observations = observed.map { target ->
            CloudMapObservation(
                targetId = target.id,
                coordinate = target.coordinate,
                targetType = target.type,
                level = target.raw.firstInt("level", "rank", "targetLevel"),
                observedAtMillis = nowMillis,
                raw = target.raw
            )
        }
        return selectAfterUpload(
            session = session,
            kind = CloudMapKind.BANDIT,
            observations = observations,
            start = start,
            targetType = targetType.name,
            allowedMineTypes = emptySet(),
            nowMillis = nowMillis
        ) { cloud ->
            MapTarget(
                id = cloud.targetId,
                coordinate = cloud.coordinate,
                type = cloud.targetType,
                raw = cloud.raw + mapOf(
                    "source" to "collaborative-cloud-map",
                    "cloudRevision" to cloud.serverRevision,
                    "level" to (cloud.level?.toString() ?: cloud.raw["level"].orEmpty())
                )
            )
        }
    }

    suspend fun selectMineTargets(
        session: GameSession,
        observed: List<MineSearchResult>,
        start: MapCoordinate,
        allowedMineTypes: Set<String>,
        nowMillis: Long
    ): CloudMapResult<List<MineSearchResult>> {
        if (!session.cloudMapRequired()) return CloudMapResult.Ok(observed)
        val observations = observed.map { mine ->
            CloudMapObservation(
                targetId = mine.id,
                coordinate = mine.coordinate,
                targetType = mine.mineType.name,
                level = mine.level,
                observedAtMillis = nowMillis,
                raw = mine.raw + mapOf(
                    "reserve" to (mine.reserve?.toString() ?: ""),
                    "isEmpty" to mine.isEmpty.toString(),
                    "defenseCount" to (mine.defenseCount?.toString() ?: "")
                )
            )
        }
        return selectAfterUpload(
            session = session,
            kind = CloudMapKind.MINE,
            observations = observations,
            start = start,
            targetType = null,
            allowedMineTypes = allowedMineTypes,
            nowMillis = nowMillis
        ) { cloud ->
            val mineType = runCatching {
                com.example.dwpmclone.domain.model.MineType.valueOf(cloud.targetType)
            }.getOrElse {
                return@selectAfterUpload null
            }
            MineSearchResult(
                id = cloud.targetId,
                coordinate = cloud.coordinate,
                mineType = mineType,
                level = cloud.level,
                reserve = cloud.raw["reserve"]?.toLongOrNull(),
                isEmpty = cloud.raw["isEmpty"]?.toBooleanStrictOrNull() ?: false,
                defenseCount = cloud.raw["defenseCount"]?.toIntOrNull(),
                raw = cloud.raw + mapOf(
                    "source" to "collaborative-cloud-map",
                    "cloudRevision" to cloud.serverRevision
                )
            )
        }
    }

    private suspend fun <T> selectAfterUpload(
        session: GameSession,
        kind: CloudMapKind,
        observations: List<CloudMapObservation>,
        start: MapCoordinate,
        targetType: String?,
        allowedMineTypes: Set<String>,
        nowMillis: Long,
        convert: (CloudTarget) -> T?
    ): CloudMapResult<List<T>> {
        val serverId = session.serverIdentity()
            ?: return CloudMapResult.Err("CLOUD_MAP_SERVER_ID_MISSING", "云端地图上传缺少区服标识", false)
        val batchId = "${session.accountId}-${kind.name.lowercase()}-$nowMillis"
        val receipt = when (val upload = client.upload(
            ObservationUploadRequest(
                accountId = session.accountId,
                serverId = serverId,
                kind = kind,
                observations = observations,
                observedAtMillis = nowMillis,
                clientBatchId = batchId
            )
        )) {
            is CloudMapResult.Ok -> upload.value
            is CloudMapResult.Err -> return upload
        }
        if (receipt.clientBatchId != batchId) {
            return CloudMapResult.Err(
                "CLOUD_MAP_UPLOAD_RECEIPT_MISMATCH",
                "云端上传回执批次不一致，禁止继续选择目标",
                false
            )
        }
        val recommendation = when (val result = client.recommend(
            TargetRecommendationRequest(
                accountId = session.accountId,
                serverId = serverId,
                kind = kind,
                start = start,
                acceptedRevision = receipt.serverRevision,
                targetType = targetType,
                allowedMineTypes = allowedMineTypes
            )
        )) {
            is CloudMapResult.Ok -> result.value
            is CloudMapResult.Err -> return result
        } ?: return CloudMapResult.Ok(emptyList())
        if (recommendation.serverRevision != receipt.serverRevision) {
            return CloudMapResult.Err(
                "CLOUD_MAP_RECOMMENDATION_REVISION_MISMATCH",
                "云端推荐目标不是刚上传后确认的地图版本，禁止出征",
                true
            )
        }
        val converted = convert(recommendation)
            ?: return CloudMapResult.Err("CLOUD_MAP_TARGET_INVALID", "云端推荐目标字段无效", false)
        return CloudMapResult.Ok(listOf(converted))
    }

    private fun GameSession.cloudMapRequired(): Boolean =
        channelExtra["collaborativeMapRequired"].equals("true", ignoreCase = true)

    private fun GameSession.serverIdentity(): String? =
        channelExtra["serverKey"]?.takeIf { it.isNotBlank() }
            ?: channelExtra["serverId"]?.takeIf { it.isNotBlank() }
            ?: channelExtra["serverUrl"]?.takeIf { it.isNotBlank() }

    private fun Map<String, String>.firstInt(vararg keys: String): Int? {
        for (key in keys) {
            this[key]?.filter { it.isDigit() }?.takeIf { it.isNotBlank() }?.toIntOrNull()?.let { return it }
        }
        return null
    }
}

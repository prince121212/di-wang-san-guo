package com.example.dwpmclone.domain.cloud

import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.scheduler.SuspendRunner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CloudFirstMapCoordinatorTest {
    @Test
    fun requiredCloudMapUploadsBeforeRequestingRecommendation() {
        val events = mutableListOf<String>()
        val client = object : CollaborativeMapClient {
            override suspend fun upload(request: ObservationUploadRequest): CloudMapResult<UploadReceipt> {
                events += "upload:${request.clientBatchId}:${request.observations.size}"
                return CloudMapResult.Ok(
                    UploadReceipt(
                        accepted = request.observations.size,
                        serverRevision = "rev-7",
                        clientBatchId = request.clientBatchId
                    )
                )
            }

            override suspend fun recommend(request: TargetRecommendationRequest): CloudMapResult<CloudTarget?> {
                events += "recommend:${request.acceptedRevision}"
                return CloudMapResult.Ok(
                    CloudTarget(
                        targetId = 9002,
                        coordinate = MapCoordinate(18, 22),
                        targetType = "山贼",
                        level = 6,
                        serverRevision = request.acceptedRevision,
                        raw = mapOf("compositionCode" to "5203")
                    )
                )
            }
        }
        val coordinator = CloudFirstMapCoordinator(client)
        val result = SuspendRunner.run {
            coordinator.selectBanditTargets(
                session = requiredSession(),
                observed = listOf(
                    MapTarget(1, MapCoordinate(2, 3), "山贼", mapOf("level" to "1"))
                ),
                start = MapCoordinate(0, 0),
                targetType = HuangTargetType.SHAN_ZEI,
                nowMillis = 1234L
            )
        }

        assertTrue(result is CloudMapResult.Ok)
        val target = (result as CloudMapResult.Ok).value.single()
        assertEquals(9002L, target.id)
        assertEquals("collaborative-cloud-map", target.raw["source"])
        assertEquals(listOf("upload:77-bandit-1234:1", "recommend:rev-7"), events)
    }

    @Test
    fun failedUploadNeverRequestsRecommendation() {
        val events = mutableListOf<String>()
        val client = object : CollaborativeMapClient {
            override suspend fun upload(request: ObservationUploadRequest): CloudMapResult<UploadReceipt> {
                events += "upload"
                return CloudMapResult.Err("OFFLINE", "server offline", true)
            }

            override suspend fun recommend(request: TargetRecommendationRequest): CloudMapResult<CloudTarget?> {
                events += "recommend"
                error("recommend must not run after upload failure")
            }
        }

        val result = SuspendRunner.run {
            CloudFirstMapCoordinator(client).selectBanditTargets(
                requiredSession(),
                emptyList(),
                MapCoordinate(0, 0),
                HuangTargetType.SHAN_ZEI,
                9L
            )
        }

        assertTrue(result is CloudMapResult.Err)
        assertEquals(listOf("upload"), events)
    }

    @Test
    fun legacySessionWithoutRequiredFlagKeepsExistingSelectionDuringMigration() {
        var calls = 0
        val client = object : CollaborativeMapClient {
            override suspend fun upload(request: ObservationUploadRequest): CloudMapResult<UploadReceipt> {
                calls++
                error("must not call")
            }

            override suspend fun recommend(request: TargetRecommendationRequest): CloudMapResult<CloudTarget?> {
                calls++
                error("must not call")
            }
        }
        val observed = listOf(MapTarget(3, MapCoordinate(4, 5), "山贼"))
        val result = SuspendRunner.run {
            CloudFirstMapCoordinator(client).selectBanditTargets(
                GameSession(77, "token", null, emptyMap(), 1),
                observed,
                MapCoordinate(0, 0),
                HuangTargetType.SHAN_ZEI,
                9L
            )
        }

        assertEquals(observed, (result as CloudMapResult.Ok).value)
        assertEquals(0, calls)
    }

    @Test
    fun expeditionResultCarriesServerRevisionAndTargetBackToCloud() {
        var captured: ExpeditionResultRequest? = null
        val client = object : CollaborativeMapClient {
            override suspend fun upload(request: ObservationUploadRequest) =
                error("not used")

            override suspend fun recommend(request: TargetRecommendationRequest) =
                error("not used")

            override suspend fun reportExpedition(
                request: ExpeditionResultRequest
            ): CloudMapResult<ExpeditionResultReceipt> {
                captured = request
                return CloudMapResult.Ok(
                    ExpeditionResultReceipt(true, "rev-8", request.targetId)
                )
            }
        }

        val result = SuspendRunner.run {
            CloudFirstMapCoordinator(client).reportExpedition(
                session = requiredSession(),
                kind = CloudMapKind.MINE,
                targetId = 9002L,
                acceptedRevision = "rev-7",
                success = true,
                message = "occupied",
                nowMillis = 5678L,
                raw = mapOf("battleId" to "88")
            )
        }

        assertTrue(result is CloudMapResult.Ok)
        assertEquals("351", captured?.serverId)
        assertEquals(9002L, captured?.targetId)
        assertEquals("rev-7", captured?.acceptedRevision)
        assertEquals("88", captured?.raw?.get("battleId"))
    }

    private fun requiredSession() = GameSession(
        accountId = 77,
        tokenCiphertext = "token",
        expiresAtMillis = null,
        channelExtra = mapOf(
            "collaborativeMapRequired" to "true",
            "serverKey" to "351"
        ),
        sourceMode = 1
    )
}

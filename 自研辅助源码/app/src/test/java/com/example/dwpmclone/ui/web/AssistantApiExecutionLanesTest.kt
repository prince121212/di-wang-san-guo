package com.example.dwpmclone.ui.web

import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantApiExecutionLanesTest {
    @Test
    fun `shared route contract is the single lane classification source`() {
        val contract = JSONObject(sourceContract())
        val classifier = AssistantApiLaneClassifier.fromContract(contract)

        assertEquals(56, classifier.routeCount)
        assertEquals(29, classifier.networkOperationRouteCount)
        assertEquals(
            AssistantApiExecutionLane.LOCAL_READ,
            classifier.laneFor(request("GET", "/api/accounts?ignored=true"))
        )
        assertEquals(
            AssistantApiExecutionLane.LOCAL_WRITE,
            classifier.laneFor(request("POST", "/api/settings/save"))
        )
        assertEquals(
            AssistantApiExecutionLane.LOCAL_WRITE,
            classifier.laneFor(request("POST", "/api/brush/recommended-center"))
        )
        assertEquals(
            AssistantApiExecutionLane.NETWORK_OPERATION,
            classifier.laneFor(request("GET", "/api/military/intel?sessionId=1"))
        )
        assertEquals(
            AssistantApiExecutionLane.NETWORK_OPERATION,
            classifier.laneFor(
                request("POST", "/api/formations/apply", "accountRef" to "1")
            )
        )
        assertEquals(
            AssistantApiExecutionLane.NETWORK_OPERATION,
            classifier.laneFor(request("POST", "/api/brush/execute"))
        )
    }

    @Test
    fun `blocked network request cannot delay local reads or writes`() {
        val classifier = classifier(
            localGet = "/api/local/read",
            localPost = "/api/local/write",
            networkPost = "/api/network/run"
        )
        val lanes = lanes(classifier)
        val networkStarted = CountDownLatch(1)
        val releaseNetwork = CountDownLatch(1)
        val localReadFinished = CountDownLatch(1)
        val localWriteFinished = CountDownLatch(1)
        try {
            assertTrue(lanes.execute(
                request("POST", "/api/network/run", "accountId" to "1"),
                Runnable {
                    networkStarted.countDown()
                    releaseNetwork.await(2, TimeUnit.SECONDS)
                }
            ))
            assertTrue(networkStarted.await(1, TimeUnit.SECONDS))

            assertTrue(lanes.execute(
                request("GET", "/api/local/read"),
                Runnable(localReadFinished::countDown)
            ))
            assertTrue(lanes.execute(
                request("POST", "/api/local/write"),
                Runnable(localWriteFinished::countDown)
            ))

            assertTrue(localReadFinished.await(1, TimeUnit.SECONDS))
            assertTrue(localWriteFinished.await(1, TimeUnit.SECONDS))
        } finally {
            releaseNetwork.countDown()
            lanes.close()
        }
    }

    @Test
    fun `same account network work is serial while different accounts can progress`() {
        val classifier = classifier(networkPost = "/api/network/run")
        val lanes = lanes(classifier)
        val firstStarted = CountDownLatch(1)
        val releaseFirst = CountDownLatch(1)
        val sameAccountSecondStarted = CountDownLatch(1)
        val otherAccountStarted = CountDownLatch(1)
        val overlapObserved = AtomicBoolean(false)
        try {
            lanes.execute(
                request("POST", "/api/network/run", "sessionId" to "1"),
                Runnable {
                    firstStarted.countDown()
                    releaseFirst.await(2, TimeUnit.SECONDS)
                }
            )
            assertTrue(firstStarted.await(1, TimeUnit.SECONDS))
            lanes.execute(
                request("POST", "/api/network/run", "sessionId" to "1"),
                Runnable(sameAccountSecondStarted::countDown)
            )
            lanes.execute(
                request("POST", "/api/network/run", "sessionId" to "2"),
                Runnable {
                    overlapObserved.set(true)
                    otherAccountStarted.countDown()
                }
            )

            assertTrue(otherAccountStarted.await(1, TimeUnit.SECONDS))
            assertTrue(overlapObserved.get())
            assertFalse(sameAccountSecondStarted.await(150, TimeUnit.MILLISECONDS))
            releaseFirst.countDown()
            assertTrue(sameAccountSecondStarted.await(1, TimeUnit.SECONDS))
        } finally {
            releaseFirst.countDown()
            lanes.close()
        }
    }

    @Test
    fun `unknown routes fail on a local lane instead of occupying a network lane`() {
        val classifier = classifier()

        assertEquals(
            AssistantApiExecutionLane.LOCAL_READ,
            classifier.laneFor(request("GET", "/api/not-declared"))
        )
        assertEquals(
            AssistantApiExecutionLane.LOCAL_WRITE,
            classifier.laneFor(request("POST", "/api/not-declared"))
        )
    }

    private fun lanes(classifier: AssistantApiLaneClassifier) = AssistantApiExecutionLanes(
        classifier = classifier,
        localReadExecutor = Executors.newFixedThreadPool(2),
        localWriteExecutor = Executors.newSingleThreadExecutor(),
        networkBackend = Executors.newFixedThreadPool(2)
    )

    private fun classifier(
        localGet: String? = null,
        localPost: String? = null,
        networkPost: String? = null
    ): AssistantApiLaneClassifier {
        val routes = JSONArray()
        localGet?.let {
            routes.put(route("GET", it, "local"))
        }
        localPost?.let {
            routes.put(route("POST", it, "local"))
        }
        networkPost?.let {
            routes.put(route("POST", it, "network-operation"))
        }
        return AssistantApiLaneClassifier.fromContract(JSONObject().put("routes", routes))
    }

    private fun route(method: String, path: String, responseClass: String) = JSONObject()
        .put("method", method)
        .put("path", path)
        .put("responseClass", responseClass)

    private fun request(
        method: String,
        path: String,
        vararg body: Pair<String, String>
    ) = AssistantApiRequest(
        id = "test",
        method = method,
        path = path,
        body = if (body.isEmpty()) null else JSONObject().apply {
            body.forEach { (key, value) -> put(key, value) }
        }
    )

    private fun sourceContract(): String {
        val file = sequenceOf(
            File("../../shared_core/api_route_ownership.json"),
            File("../shared_core/api_route_ownership.json"),
            File("shared_core/api_route_ownership.json")
        ).firstOrNull(File::isFile)
        return checkNotNull(file) { "api_route_ownership.json not found" }.readText()
    }
}

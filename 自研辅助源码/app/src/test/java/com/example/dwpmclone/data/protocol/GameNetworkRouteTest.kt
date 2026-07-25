package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.model.GameSession
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.HttpURLConnection
import java.net.ServerSocket
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class GameNetworkRouteTest {
    @Test
    fun parsesSystemDirectHttpSocksAndRejectsInvalidManualConfig() {
        assertEquals(GameProxyMode.SYSTEM_AUTO, GameNetworkRoute.from(emptyMap()).mode)
        assertEquals(GameProxyMode.DIRECT, GameNetworkRoute.from(mapOf("proxyMode" to "direct")).mode)

        val http = GameNetworkRoute.from(
            mapOf("proxyMode" to "http", "proxyHost" to "127.0.0.1", "proxyPort" to "8080")
        )
        assertEquals(GameProxyMode.HTTP, http.mode)
        assertEquals("127.0.0.1", http.host)
        assertEquals(8080, http.port)

        val socks = GameNetworkRoute.from(
            mapOf("proxyMode" to "socks", "proxyHost" to "10.0.0.2", "proxyPort" to "1080")
        )
        assertEquals(GameProxyMode.SOCKS, socks.mode)

        val invalid = GameNetworkRoute.from(
            mapOf("proxyMode" to "http", "proxyHost" to "", "proxyPort" to "70000")
        )
        assertEquals(GameProxyMode.INVALID, invalid.mode)
        val error = runCatching { invalid.open(URL("http://127.0.0.1/")) }.exceptionOrNull()
        assertTrue(error is IllegalStateException)
    }

    @Test
    fun httpRouteActuallyConnectsToConfiguredProxyInsteadOfTarget() {
        val proxyServer = ServerSocket(0)
        val handled = CountDownLatch(1)
        var requestLine = ""
        val thread = Thread {
            proxyServer.accept().use { socket ->
                val reader = socket.getInputStream().bufferedReader()
                requestLine = reader.readLine()
                while (reader.readLine().isNotEmpty()) Unit
                val body = "proxy-ok".toByteArray()
                socket.getOutputStream().use {
                    it.write(
                        (
                            "HTTP/1.1 200 OK\r\nContent-Length: ${body.size}\r\n" +
                                "Connection: close\r\n\r\n"
                            ).toByteArray()
                    )
                    it.write(body)
                }
            }
            handled.countDown()
        }
        thread.start()
        try {
            val route = GameNetworkRoute(
                GameProxyMode.HTTP,
                "127.0.0.1",
                proxyServer.localPort
            )
            val connection = route.open(URL("http://unreachable.invalid/game")) as HttpURLConnection
            connection.connectTimeout = 2_000
            connection.readTimeout = 2_000

            assertEquals("proxy-ok", connection.inputStream.bufferedReader().use { it.readText() })
            assertTrue(handled.await(2, TimeUnit.SECONDS))
            assertTrue(requestLine.startsWith("GET http://unreachable.invalid/game "))
        } finally {
            proxyServer.close()
            thread.join(2_000)
        }
    }

    @Test
    fun registryKeepsDifferentAccountsOnSameGameServerIsolatedByDm() {
        GameNetworkRouteRegistry.clearForTests()
        val gameHttp = "http://game.example/kingWapServer/HttpClient"
        GameNetworkRouteRegistry.register(
            session(dm = 100L, mode = "direct"),
            gameHttp,
            100L
        )
        GameNetworkRouteRegistry.register(
            session(dm = 200L, mode = "http", host = "127.0.0.1", port = 8080),
            gameHttp,
            200L
        )

        assertEquals(GameProxyMode.DIRECT, GameNetworkRouteRegistry.route(gameHttp, 100L).mode)
        assertEquals(GameProxyMode.HTTP, GameNetworkRouteRegistry.route(gameHttp, 200L).mode)
    }

    private fun session(
        dm: Long,
        mode: String,
        host: String = "",
        port: Int = 0
    ) = GameSession(
        accountId = dm,
        tokenCiphertext = "token",
        expiresAtMillis = null,
        channelExtra = mapOf(
            "dm" to dm.toString(),
            "proxyMode" to mode,
            "proxyHost" to host,
            "proxyPort" to port.toString()
        ),
        sourceMode = 1
    )
}

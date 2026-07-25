package com.example.dwpmclone.domain.cloud

import com.example.dwpmclone.domain.scheduler.SuspendRunner
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.ServerSocket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class HttpCollaborativeMapClientTest {
    @Test
    fun resultEndpointSendsDeviceRevisionOutcomeAndParsesStrictReceipt() {
        var received: JSONObject? = null
        var deviceId = ""
        val server = ServerSocket(0)
        val handled = CountDownLatch(1)
        val thread = Thread {
            server.accept().use { socket ->
                val input = socket.getInputStream().bufferedReader(Charsets.UTF_8)
                val requestLine = input.readLine()
                assertTrue(requestLine.startsWith("POST /v1/map/results "))
                var contentLength = 0
                while (true) {
                    val line = input.readLine()
                    if (line.isEmpty()) break
                    val split = line.indexOf(':')
                    if (split > 0) {
                        val key = line.substring(0, split).trim()
                        val value = line.substring(split + 1).trim()
                        if (key.equals("Content-Length", true)) contentLength = value.toInt()
                        if (key.equals("X-Device-Id", true)) deviceId = value
                    }
                }
                val chars = CharArray(contentLength)
                var offset = 0
                while (offset < chars.size) {
                    val count = input.read(chars, offset, chars.size - offset)
                    if (count < 0) break
                    offset += count
                }
                received = JSONObject(String(chars, 0, offset))
                val response = """{"accepted":true,"serverRevision":"351-mine-8","targetId":902}"""
                    .toByteArray()
                socket.getOutputStream().use { output ->
                    output.write(
                        (
                            "HTTP/1.1 200 OK\r\n" +
                                "Content-Type: application/json\r\n" +
                                "Content-Length: ${response.size}\r\n" +
                                "Connection: close\r\n\r\n"
                            ).toByteArray()
                    )
                    output.write(response)
                }
            }
            handled.countDown()
        }
        thread.start()
        try {
            val client = HttpCollaborativeMapClient(
                CollaborativeMapHttpSettings(
                    baseUrl = "http://127.0.0.1:${server.localPort}",
                    deviceId = "phone-27a83c9c"
                )
            )

            val result = SuspendRunner.run {
                client.reportExpedition(
                    ExpeditionResultRequest(
                        accountId = 77L,
                        serverId = "351",
                        kind = CloudMapKind.MINE,
                        targetId = 902L,
                        acceptedRevision = "351-mine-7",
                        success = true,
                        message = "occupied",
                        reportedAtMillis = 1234L,
                        raw = mapOf("battleId" to "88")
                    )
                )
            }

            assertTrue(result is CloudMapResult.Ok)
            assertEquals("351-mine-8", (result as CloudMapResult.Ok).value.serverRevision)
            assertEquals("phone-27a83c9c", deviceId)
            assertEquals("351-mine-7", received?.getString("acceptedRevision"))
            assertEquals(true, received?.getBoolean("success"))
            assertEquals("88", received?.getJSONObject("raw")?.getString("battleId"))
            assertTrue(handled.await(2, TimeUnit.SECONDS))
        } finally {
            server.close()
            thread.join(2_000)
        }
    }
}

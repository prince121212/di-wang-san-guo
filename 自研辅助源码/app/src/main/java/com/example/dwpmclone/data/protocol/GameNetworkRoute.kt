package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.model.GameSession
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL
import java.net.URLConnection
import java.util.concurrent.ConcurrentHashMap

enum class GameProxyMode { SYSTEM_AUTO, DIRECT, HTTP, SOCKS, INVALID }

data class GameNetworkRoute(
    val mode: GameProxyMode,
    val host: String = "",
    val port: Int = 0,
    val error: String? = null
) {
    fun open(url: URL): URLConnection = when (mode) {
        GameProxyMode.SYSTEM_AUTO -> url.openConnection()
        GameProxyMode.DIRECT -> url.openConnection(Proxy.NO_PROXY)
        GameProxyMode.HTTP -> url.openConnection(Proxy(Proxy.Type.HTTP, InetSocketAddress(host, port)))
        GameProxyMode.SOCKS -> url.openConnection(Proxy(Proxy.Type.SOCKS, InetSocketAddress(host, port)))
        GameProxyMode.INVALID -> throw IllegalStateException(error ?: "账号代理配置无效")
    }

    companion object {
        fun from(extras: Map<String, String>): GameNetworkRoute {
            val mode = extras["proxyMode"]?.trim()?.lowercase().orEmpty().ifBlank { "auto" }
            if (mode == "direct") return GameNetworkRoute(GameProxyMode.DIRECT)
            if (mode == "auto" && extras["proxyHost"].isNullOrBlank()) {
                return GameNetworkRoute(GameProxyMode.SYSTEM_AUTO)
            }
            val host = extras["proxyHost"]?.trim().orEmpty()
            val port = extras["proxyPort"]?.toIntOrNull()
            if (host.isBlank() || port == null || port !in 1..65535) {
                return GameNetworkRoute(
                    GameProxyMode.INVALID,
                    error = "账号代理需要有效的主机和1-65535端口"
                )
            }
            val type = when {
                mode == "socks" || extras["proxyType"].equals("socks", true) -> GameProxyMode.SOCKS
                mode in setOf("manual", "http", "auto") -> GameProxyMode.HTTP
                else -> GameProxyMode.INVALID
            }
            return if (type == GameProxyMode.INVALID) {
                GameNetworkRoute(type, error = "不支持的账号代理模式：$mode")
            } else {
                GameNetworkRoute(type, host, port)
            }
        }
    }
}

/**
 * Active game requests are keyed by game endpoint and dm, so accounts on the same server can
 * concurrently use different proxy routes without mutating JVM-global proxy properties.
 */
object GameNetworkRouteRegistry {
    private val routes = ConcurrentHashMap<Pair<String, Long>, GameNetworkRoute>()

    fun register(session: GameSession, gameHttp: String, dm: Long) {
        routes[gameHttp to dm] = GameNetworkRoute.from(session.channelExtra)
    }

    fun route(gameHttp: String, dm: Long): GameNetworkRoute =
        routes[gameHttp to dm] ?: GameNetworkRoute(GameProxyMode.SYSTEM_AUTO)

    internal fun clearForTests() {
        routes.clear()
    }
}

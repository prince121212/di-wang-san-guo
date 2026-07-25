package com.example.dwpmclone.service

import android.content.Intent
import android.net.VpnService
import com.example.dwpmclone.data.local.TaskLogRepository

/**
 * Local VPN/proxy entry point, mirroring Xiaohuang's VPN service capability.
 *
 * Current implementation is a safe skeleton: it exposes the Android VpnService permission
 * boundary and lifecycle hooks, but does not yet establish a TUN interface or intercept
 * traffic. Protocol forwarding/capture can be implemented behind this service later.
 */
class LocalProxyVpnService : VpnService() {
    private val logs by lazy { TaskLogRepository(this) }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        logs.append("local proxy vpn service start requested; tunnel not established yet", tag = "vpn")
        return START_STICKY
    }

    override fun onDestroy() {
        logs.append("local proxy vpn service destroyed", tag = "vpn")
        super.onDestroy()
    }
}

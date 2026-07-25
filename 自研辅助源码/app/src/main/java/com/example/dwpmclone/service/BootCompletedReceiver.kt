package com.example.dwpmclone.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.example.dwpmclone.data.local.TaskLogRepository

/** Receives boot completion so the app can restore/notify background automation state. */
class BootCompletedReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        TaskLogRepository(context).append(
            "boot completed received; user can reopen app/start AssistantForegroundService to restore keepalive",
            tag = "boot"
        )
    }
}

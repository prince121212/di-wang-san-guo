package com.example.dwpmclone.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.UserManager
import com.example.dwpmclone.data.local.TaskLogRepository

/** Restores only user-enabled on-device hosting after a device reboot. */
class BootCompletedReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED && action != Intent.ACTION_USER_UNLOCKED) return
        val unlocked = Build.VERSION.SDK_INT < Build.VERSION_CODES.N ||
            context.getSystemService(UserManager::class.java)?.isUserUnlocked != false
        if (!unlocked) return
        val resumed = AssistantForegroundService.resumeIfEnabled(context)
        TaskLogRepository(context).append(
            "local hosting restore action=$action result=${if (resumed) "started" else "not-enabled"}",
            tag = "boot"
        )
    }
}

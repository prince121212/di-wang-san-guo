package com.example.dwpmclone.ui.hosting

object HostingPermissionOnboardingPolicy {
    fun shouldExplain(alreadyShown: Boolean, recommendedReady: Boolean): Boolean = !alreadyShown && !recommendedReady
    const val EXPLANATION = "这些权限不是启动条件：即使暂不开启，也可以登录、启动账号和执行任务。\n\n为了改善后台运行，建议按需开启：\n• 通知权限：在通知栏显示运行状态和停止入口。\n• 忽略电池优化：减少锁屏后任务被系统暂停的风险。\n\n精确闹钟是可选增强；厂商自启动、无限制省电可按机型手动设置。\n\n未开启时，切到后台或锁屏后可能被系统暂停网络或停止应用。你可以稍后再设置，不影响现在使用。"
}

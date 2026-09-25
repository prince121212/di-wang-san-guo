package com.example.dwpmclone.ui.hosting

import com.example.dwpmclone.BuildConfig

import org.json.JSONArray
import org.json.JSONObject

/**
 * Per-vendor manual steps for keeping on-device hosting alive.
 *
 * Deep links into vendor settings are best-effort by nature: the components are
 * undocumented, hidden by package visibility, and renamed between ROM releases.
 * Text steps are the only guidance that cannot break, so they are always
 * available rather than being a last resort.  Menu names drift between versions,
 * which [PATH_CAVEAT] states outright instead of pretending otherwise.
 *
 * Pure by design: this is the copy users actually rely on across brands, so it
 * stays unit-testable with no Android runtime.
 */
data class VendorBackgroundGuidance(
    val family: String,
    /** True when the vendor adds switches Android exposes no API to inspect. */
    val manualReviewRequired: Boolean,
    val autostartSteps: List<String>,
    val batterySteps: List<String>,
    val extraSteps: List<String> = emptyList(),
    /**
     * Steps for the one failure that looks exactly like a broken app: the ROM
     * turns Wi-Fi off on a timer, so hosting stays alive all night and sends
     * nothing.  Kept separate from [extraSteps] because it is only shown once
     * the outage journal has actually seen the pattern, and then it is the
     * only thing the user needs to read.
     */
    val scheduledNetworkOffSteps: List<String> = emptyList(),
) {
    fun toJson(): JSONObject = JSONObject()
        .put("family", family)
        .put("manualReviewRequired", manualReviewRequired)
        .put("pathCaveat", PATH_CAVEAT)
        .put("autostartSteps", JSONArray(autostartSteps))
        .put("batterySteps", JSONArray(batterySteps))
        .put("extraSteps", JSONArray(extraSteps))
        .put("scheduledNetworkOffSteps", JSONArray(scheduledNetworkOffSteps))

    companion object {
        const val PATH_CAVEAT = "以下路径随系统版本略有差异，按最接近的菜单名查找即可"
        private const val APP = BuildConfig.APP_NAME

        /** Applies to every ROM, including AOSP. */
        private val SHARED_EXTRA_STEPS = listOf(
            "关闭系统的“省电模式”，省电模式会压制后台网络和闹钟",
            "在 WLAN 高级设置中开启“休眠时保持网络连接”",
        )

        /** Last resort on any ROM: the timer is somewhere, these find it. */
        private val SHARED_NETWORK_OFF_STEPS = listOf(
            "检查是否设置了定时开关机、定时飞行模式或定时省电",
            "如装有自动化类应用（如任务自动化、智能场景、家居联动），检查其中的夜间断网/关WLAN任务",
        )

        fun forManufacturer(raw: String): VendorBackgroundGuidance {
            val value = raw.trim().lowercase()
            return when {
                value.contains("xiaomi") || value.contains("redmi") -> VendorBackgroundGuidance(
                    family = "小米/Redmi",
                    manualReviewRequired = true,
                    autostartSteps = listOf(
                        "设置 → 应用设置 → 应用管理 → $APP → 自启动 → 允许",
                        "确认开关保存后再返回，MIUI 偶发需要重新进入页面确认",
                    ),
                    batterySteps = listOf(
                        "设置 → 电池与性能 → 应用智能省电（或“应用配置”）→ $APP → 无限制",
                    ),
                    extraSteps = listOf(
                        "在最近任务界面下拉本应用卡片加锁，避免一键清理把它划掉",
                    ) + SHARED_EXTRA_STEPS,
                    scheduledNetworkOffSteps = listOf(
                        "设置 → 省电与电池 → 智能场景省电 → 睡眠模式 → 关闭（实测就是它在夜间关掉 WLAN）",
                        "设置 → WLAN → 更多设置（或“高级设置”）→ 在休眠状态下保持 WLAN 连接 → 选“始终”",
                        "设置 → 省电与电池 → 省电模式 → 关闭“定时开启”",
                    ) + SHARED_NETWORK_OFF_STEPS,
                )
                value.contains("huawei") || value.contains("honor") -> VendorBackgroundGuidance(
                    family = if (value.contains("honor")) "荣耀" else "华为",
                    manualReviewRequired = true,
                    autostartSteps = listOf(
                        "设置 → 应用和服务 → 应用启动管理 → $APP",
                        "先关闭“自动管理”，再手动打开“允许自启动”“允许关联启动”“允许后台活动”三项",
                    ),
                    batterySteps = listOf(
                        "设置 → 电池 → 更多电池设置 → 开启“休眠时始终保持网络连接”",
                    ),
                    extraSteps = SHARED_EXTRA_STEPS,
                    scheduledNetworkOffSteps = listOf(
                        "设置 → 电池 → 更多电池设置 → 休眠时始终保持网络连接 → 开启",
                        "设置 → 电池 → 智能省电/超级省电 → 关闭定时开启",
                    ) + SHARED_NETWORK_OFF_STEPS,
                )
                value.contains("oppo") || value.contains("oneplus") ||
                    value.contains("realme") || value.contains("oplus") ->
                    VendorBackgroundGuidance(
                        family = "OPPO/OnePlus/realme",
                        manualReviewRequired = true,
                        autostartSteps = listOf(
                            "设置 → 应用管理 → $APP → 耗电管理 → 打开“允许自启动”和“允许后台运行”",
                        ),
                        batterySteps = listOf(
                            "设置 → 电池 → 更多设置 → 关闭对 $APP 的“智能省电”限制",
                            "如有“睡眠待机优化”，把 $APP 加入例外",
                        ),
                        extraSteps = SHARED_EXTRA_STEPS,
                        scheduledNetworkOffSteps = listOf(
                            "设置 → 电池 → 更多设置 → 睡眠待机优化 → 关闭",
                            "设置 → WLAN → 更多 WLAN 设置 → 休眠时保持 WLAN 连接 → 开启",
                        ) + SHARED_NETWORK_OFF_STEPS,
                    )
                value.contains("vivo") || value.contains("iqoo") -> VendorBackgroundGuidance(
                    family = "vivo/iQOO",
                    manualReviewRequired = true,
                    autostartSteps = listOf(
                        "设置 → 更多设置 → 权限管理 → 自启动 → $APP → 开启",
                    ),
                    batterySteps = listOf(
                        "设置 → 电池 → 后台高耗电 → $APP → 允许",
                    ),
                    extraSteps = SHARED_EXTRA_STEPS,
                    scheduledNetworkOffSteps = listOf(
                        "设置 → 电池 → 省电模式 → 关闭定时开启",
                        "设置 → 更多设置 → WLAN → 高级设置 → 休眠状态下保持 WLAN 连接 → 开启",
                    ) + SHARED_NETWORK_OFF_STEPS,
                )
                value.contains("meizu") -> VendorBackgroundGuidance(
                    family = "魅族",
                    manualReviewRequired = true,
                    autostartSteps = listOf(
                        "设置 → 应用管理 → $APP → 权限管理 → 后台管理 → 允许后台运行",
                    ),
                    batterySteps = listOf(
                        "设置 → 电池 → 省电管理 → 把 $APP 设为不受限制",
                    ),
                    extraSteps = SHARED_EXTRA_STEPS,
                    scheduledNetworkOffSteps = listOf(
                        "设置 → 电池 → 省电管理 → 关闭“夜间断网/待机断网”",
                    ) + SHARED_NETWORK_OFF_STEPS,
                )
                value.contains("samsung") -> VendorBackgroundGuidance(
                    family = "Samsung",
                    manualReviewRequired = true,
                    autostartSteps = listOf(
                        "设置 → 电池和设备维护 → 电池 → 后台使用限制",
                        "把 $APP 从“使深度睡眠的应用”和“休眠应用”列表中移除",
                    ),
                    batterySteps = listOf(
                        "设置 → 应用 → $APP → 电池 → 选择“无限制”",
                    ),
                    extraSteps = SHARED_EXTRA_STEPS,
                    scheduledNetworkOffSteps = listOf(
                        "设置 → 连接 → WLAN → 高级设置 → 关闭“自动关闭 WLAN”",
                        "设置 → 电池和设备维护 → 电池 → 省电模式 → 关闭“关闭始终显示”与定时开启",
                    ) + SHARED_NETWORK_OFF_STEPS,
                )
                else -> VendorBackgroundGuidance(
                    family = raw.trim().ifBlank { "Android" },
                    manualReviewRequired = false,
                    autostartSteps = listOf(
                        "原生 Android 没有独立的自启动开关，无需额外设置",
                    ),
                    batterySteps = listOf(
                        "设置 → 应用 → $APP → 电池 → 选择“无限制”",
                    ),
                    extraSteps = SHARED_EXTRA_STEPS,
                    scheduledNetworkOffSteps = SHARED_NETWORK_OFF_STEPS,
                )
            }
        }
    }
}

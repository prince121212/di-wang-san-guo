package com.example.dwpmclone.ui.hosting

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VendorBackgroundGuidanceTest {
    @Test
    fun everyAggressiveVendorGetsAutostartAndBatterySteps() {
        // These are the ROMs that kill background work by default, so an empty
        // step list would leave a paying user with no way forward at all.
        val aggressive = listOf(
            "Xiaomi", "Redmi", "HUAWEI", "HONOR",
            "OPPO", "OnePlus", "realme", "vivo", "iQOO", "Meizu", "samsung",
        )

        aggressive.forEach { manufacturer ->
            val guidance = VendorBackgroundGuidance.forManufacturer(manufacturer)
            assertTrue(
                "$manufacturer 缺少自启动步骤",
                guidance.autostartSteps.isNotEmpty(),
            )
            assertTrue(
                "$manufacturer 缺少省电步骤",
                guidance.batterySteps.isNotEmpty(),
            )
            assertTrue(
                "$manufacturer 应标记为需要人工确认",
                guidance.manualReviewRequired,
            )
        }
    }

    @Test
    fun manufacturerMatchingIsCaseInsensitiveAndCoversRebrands() {
        assertEquals("小米/Redmi", VendorBackgroundGuidance.forManufacturer("xiaomi").family)
        assertEquals("小米/Redmi", VendorBackgroundGuidance.forManufacturer("REDMI").family)
        assertEquals("荣耀", VendorBackgroundGuidance.forManufacturer("HONOR").family)
        assertEquals("华为", VendorBackgroundGuidance.forManufacturer("HUAWEI").family)
        // OnePlus/realme/oplus all ship ColorOS-derived policy.
        listOf("OPPO", "OnePlus", "realme", "OPlus").forEach {
            assertEquals(
                "OPPO/OnePlus/realme",
                VendorBackgroundGuidance.forManufacturer(it).family,
            )
        }
        assertEquals("vivo/iQOO", VendorBackgroundGuidance.forManufacturer("iqoo").family)
    }

    @Test
    fun stockAndroidIsNotToldToHuntForAMissingSwitch() {
        val guidance = VendorBackgroundGuidance.forManufacturer("Google")

        assertFalse(guidance.manualReviewRequired)
        assertEquals("Google", guidance.family)
        assertTrue(guidance.autostartSteps.single().contains("无需额外设置"))
        assertTrue(guidance.batterySteps.single().contains("无限制"))
    }

    @Test
    fun blankManufacturerStillProducesUsableGuidance() {
        val guidance = VendorBackgroundGuidance.forManufacturer("   ")

        assertEquals("Android", guidance.family)
        assertTrue(guidance.batterySteps.isNotEmpty())
    }

    @Test
    fun everyVendorKeepsTheSharedPowerSavingAndWifiAdvice() {
        listOf("Xiaomi", "HUAWEI", "vivo", "Google").forEach { manufacturer ->
            val extra = VendorBackgroundGuidance.forManufacturer(manufacturer).extraSteps
            assertTrue(
                "$manufacturer 缺少省电模式提示",
                extra.any { it.contains("省电模式") },
            )
            assertTrue(
                "$manufacturer 缺少 WLAN 休眠提示",
                extra.any { it.contains("休眠时保持网络连接") },
            )
        }
    }

    @Test
    fun guidanceSerialisesWithTheVersionDriftCaveat() {
        val json = VendorBackgroundGuidance.forManufacturer("Xiaomi").toJson()

        assertEquals("小米/Redmi", json.getString("family"))
        assertTrue(json.getBoolean("manualReviewRequired"))
        // Menu paths genuinely move between ROM releases; promising exactness
        // would just make the guidance look wrong to the user.
        assertEquals(VendorBackgroundGuidance.PATH_CAVEAT, json.getString("pathCaveat"))
        assertTrue(json.getJSONArray("autostartSteps").length() > 0)
        assertTrue(json.getJSONArray("batterySteps").length() > 0)
        assertTrue(
            json.getJSONArray("extraSteps").toString().contains("加锁"),
        )
    }

    @Test
    fun stepsNameTheAppAsTheUserSeesItInSettings() {
        // The manifest label is 帝三资料库; steps that named the package instead
        // would send the user looking for something that is not in the list.
        val guidance = VendorBackgroundGuidance.forManufacturer("Xiaomi")

        assertTrue(guidance.autostartSteps.any { it.contains(com.example.dwpmclone.BuildConfig.APP_NAME) })
        assertTrue(guidance.batterySteps.any { it.contains(com.example.dwpmclone.BuildConfig.APP_NAME) })
    }

    @Test
    fun everyVendorCanBeToldHowToStopScheduledNetworkOff() {
        // The failure this addresses looks exactly like a broken app: every
        // permission reads "已完成" and the assistant still does nothing all
        // night.  A brand with no steps here would leave the user stuck.
        listOf(
            "Xiaomi", "Redmi", "HUAWEI", "HONOR", "OPPO", "OnePlus",
            "realme", "vivo", "iQOO", "Meizu", "samsung", "Google", "   ",
        ).forEach { manufacturer ->
            assertTrue(
                "$manufacturer 缺少定时断网处理步骤",
                VendorBackgroundGuidance.forManufacturer(manufacturer)
                    .scheduledNetworkOffSteps.isNotEmpty(),
            )
        }
    }

    @Test
    fun xiaomiNamesTheSleepModeSwitchThatActuallyCausedIt() {
        // Verified on a real 22081212C: 睡眠模式 under 智能场景省电 was the
        // switch turning Wi-Fi off at 23:10 and back on at 07:35.  It is
        // listed first because it is the one that fixed it.
        val steps = VendorBackgroundGuidance.forManufacturer("Xiaomi").scheduledNetworkOffSteps

        assertTrue(steps.first().contains("智能场景省电"))
        assertTrue(steps.first().contains("睡眠模式"))
        assertTrue(steps.any { it.contains("休眠状态下保持 WLAN 连接") })
        assertTrue(
            VendorBackgroundGuidance.forManufacturer("Xiaomi").toJson()
                .getJSONArray("scheduledNetworkOffSteps").toString().contains("睡眠模式"),
        )
    }
}

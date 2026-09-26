package com.example.dwpmclone.ui.hosting

import org.junit.Assert.*
import org.junit.Test

class HostingPermissionOnboardingPolicyTest {
    @Test fun explainsMissingRecommendedSettingsOnlyOnce() {
        assertTrue(HostingPermissionOnboardingPolicy.shouldExplain(false, false))
        assertFalse(HostingPermissionOnboardingPolicy.shouldExplain(true, false))
        assertFalse(HostingPermissionOnboardingPolicy.shouldExplain(false, true))
    }
    @Test fun optionalPermissionsDoNotBecomeMandatory() {
        assertTrue(HostingPermissionOnboardingPolicy.EXPLANATION.contains("可选"))
        assertTrue(HostingPermissionOnboardingPolicy.EXPLANATION.contains("稍后"))
        assertTrue(HostingPermissionOnboardingPolicy.EXPLANATION.contains("不是启动条件"))
        assertTrue(HostingPermissionOnboardingPolicy.EXPLANATION.contains("可能"))
        assertFalse(HostingPermissionOnboardingPolicy.EXPLANATION.contains("未授权时不启动"))
    }
}

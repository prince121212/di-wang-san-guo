package com.example.dwpmclone.host

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AppReleaseTest {
    private val site = "https://dwsg.292828.xyz"

    private fun manifest(edit: JSONObject.() -> Unit = {}): String = JSONObject()
        .put("schemaVersion", 1)
        .put("packageName", "com.example.dwpmclone")
        .put("versionCode", 121)
        .put("versionName", "V0.0.121")
        .put("publishedAt", 1_790_500_000_000L)
        .put("sizeBytes", 25_219_927L)
        .put("sha256", "ab".repeat(32))
        .put("downloadUrl", "$site/download/dwsg-V0.0.121.apk")
        .put("notes", JSONArray().put("新增检查更新").put(" ").put("修复若干问题"))
        .apply(edit)
        .toString()

    @Test
    fun parsesTheOfficialManifest() {
        val release = AppRelease.parse(manifest(), "com.example.dwpmclone", site)
        assertEquals(121, release.versionCode)
        assertEquals("V0.0.121", release.versionName)
        assertEquals(listOf("新增检查更新", "修复若干问题"), release.notes)
        assertEquals("$site/download/dwsg-V0.0.121.apk", release.downloadUrl)
    }

    @Test
    fun rejectsManifestsForAnotherPackageOrSchema() {
        assertRejected(manifest { put("packageName", "com.example.dwpmclone.internal") })
        assertRejected(manifest { put("schemaVersion", 2) })
        assertRejected(manifest { put("versionName", "V0.0.121-debug") })
        assertRejected(manifest { put("sha256", "not-a-digest") })
        assertRejected("not json")
    }

    @Test
    fun downloadsMustStayOnTheOfficialSiteOverHttps() {
        for (url in listOf(
            "http://dwsg.292828.xyz/download/dwsg-V0.0.121.apk",
            "https://evil.example/download/dwsg-V0.0.121.apk",
            "https://dwsg.292828.xyz.evil.example/download/dwsg-V0.0.121.apk",
            "https://user@dwsg.292828.xyz/download/dwsg-V0.0.121.apk",
            "https://dwsg.292828.xyz:8443/download/dwsg-V0.0.121.apk",
            "https://dwsg.292828.xyz/download/dwsg-V0.0.121.apk?next=https://evil.example",
            "https://dwsg.292828.xyz/download/../app/latest.json",
            "https://dwsg.292828.xyz/download/other.apk",
        )) {
            assertFalse(url, AppRelease.isOfficialDownload(url, site))
            assertRejected(manifest { put("downloadUrl", url) })
        }
        assertTrue(AppRelease.isOfficialDownload("https://DWSG.292828.xyz/download/dwsg-V0.0.121.apk", "$site/"))
    }

    private fun assertRejected(raw: String) {
        val failure = runCatching { AppRelease.parse(raw, "com.example.dwpmclone", site) }.exceptionOrNull()
        assertTrue("expected rejection for $raw", failure is IllegalArgumentException)
    }
}

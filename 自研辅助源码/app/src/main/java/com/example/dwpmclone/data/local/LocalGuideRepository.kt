package com.example.dwpmclone.data.local

import android.content.Context

/**
 * Raw local guide-asset port.
 *
 * It owns no article catalogue, parsing, title, filtering or open-server rule.
 * Those decisions live in the shared Python core; Android only returns the
 * recovered UTF-8 text bytes from the APK assets.
 */
class LocalGuideRepository(private val context: Context) {
    fun readFamousGeneralsSource(): String = readAssetText("dwsgmjb.TXT")

    fun readGuideArticleSource(id: String): String? {
        val normalized = id.trim()
        if (!SAFE_ARTICLE_ID.matches(normalized)) return null
        return runCatching { readAssetText("guidetxts/$normalized.txt") }.getOrNull()
    }

    private fun readAssetText(path: String): String =
        context.assets.open(path).bufferedReader(Charsets.UTF_8).use { it.readText().removePrefix("\uFEFF") }

    private companion object {
        val SAFE_ARTICLE_ID = Regex("^[A-Za-z0-9_-]{1,80}$")
    }
}

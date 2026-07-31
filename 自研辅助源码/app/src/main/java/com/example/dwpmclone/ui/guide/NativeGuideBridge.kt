package com.example.dwpmclone.ui.guide

import android.content.Context
import android.webkit.JavascriptInterface
import com.example.dwpmclone.data.local.LocalGuideRepository
import com.example.dwpmclone.domain.model.FamousGeneral
import com.example.dwpmclone.domain.model.GuideArticle
import com.example.dwpmclone.domain.reference.OpenServerTimeCalculator
import org.json.JSONArray
import org.json.JSONObject

/**
 * Read-only bridge exposing the original APK's local reference assets to the
 * current same-origin WebView guide page. It contains no account, token, file,
 * network, or task-control method.
 */
class NativeGuideBridge(context: Context) {
    private val guideRepository = LocalGuideRepository(context.applicationContext)

    @JavascriptInterface
    fun getFamousGeneralsJson(): String = bridgeResult {
        NativeGuidePayloads.famousGenerals(guideRepository.loadFamousGenerals())
    }

    @JavascriptInterface
    fun getGuideArticlesJson(): String = bridgeResult {
        NativeGuidePayloads.guideArticles(guideRepository.loadGuideArticles())
    }

    @JavascriptInterface
    fun getGuideArticleJson(id: String): String = bridgeResult {
        NativeGuidePayloads.guideArticle(guideRepository.readGuideArticle(id))
    }

    @JavascriptInterface
    fun getOpenServerOptionsJson(): String = bridgeResult {
        NativeGuidePayloads.openServerOptions()
    }

    @JavascriptInterface
    fun calculateOpenServerJson(versionIndex: Int, server: Int): String = bridgeResult {
        NativeGuidePayloads.openServerCalculation(versionIndex, server)
    }

    private inline fun bridgeResult(block: () -> JSONObject): String = runCatching(block)
        .getOrElse { error ->
            JSONObject()
                .put("ok", false)
                .put("error", error.message ?: "本地资料读取失败")
        }
        .toString()
}

/** JSON contracts kept separate so their shape is covered by JVM tests. */
object NativeGuidePayloads {
    fun famousGenerals(items: List<FamousGeneral>): JSONObject = JSONObject()
        .put("ok", true)
        .put("total", items.size)
        .put("items", JSONArray().apply {
            items.forEach { general ->
                put(JSONObject()
                    .put("name", general.name)
                    .put("breakthrough", general.breakthrough ?: JSONObject.NULL)
                    .put("attribute", general.attribute ?: JSONObject.NULL)
                    .put("nation", general.nation ?: JSONObject.NULL)
                )
            }
        })

    fun guideArticles(items: List<GuideArticle>): JSONObject = JSONObject()
        .put("ok", true)
        .put("total", items.size)
        .put("items", JSONArray().apply {
            items.forEach { article ->
                put(JSONObject()
                    .put("id", article.id)
                    .put("title", article.title)
                )
            }
        })

    fun guideArticle(article: GuideArticle?): JSONObject = if (article == null) {
        JSONObject().put("ok", false).put("error", "未找到攻略内容")
    } else {
        JSONObject()
            .put("ok", true)
            .put("article", JSONObject()
                .put("id", article.id)
                .put("title", article.title)
                .put("body", article.body)
            )
    }

    fun openServerOptions(): JSONObject = JSONObject()
        .put("ok", true)
        .put("versions", JSONArray().apply {
            OpenServerTimeCalculator.versionOptions.forEach { option ->
                val upcoming = OpenServerTimeCalculator.upcomingServer(option.index)
                put(JSONObject()
                    .put("index", option.index)
                    .put("label", option.label)
                    .put("summary", option.summary)
                    .put("upcomingServer", upcoming.server)
                    .put("upcomingDate", upcoming.dateText)
                )
            }
        })

    fun openServerCalculation(versionIndex: Int, server: Int): JSONObject {
        val result = OpenServerTimeCalculator.calculate(server, versionIndex)
        return JSONObject()
            .put("ok", true)
            .put("server", result.server)
            .put("versionIndex", result.version.index)
            .put("versionLabel", result.version.label)
            .put("dateText", result.dateText)
            .put("daysOffset", result.daysOffset)
            .put("rule", JSONObject()
                .put("baseServer", result.rule.baseServer)
                .put("intervalDays", result.rule.intervalDays)
                .put("year", result.rule.year)
                .put("month", result.rule.month)
                .put("day", result.rule.day)
                .put("note", result.rule.note)
            )
    }
}

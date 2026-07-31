package com.example.dwpmclone.ui.web

import android.webkit.JavascriptInterface
import android.webkit.WebView
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONObject

/** Async, ordered bridge; WebView never executes repository or protocol work on the UI thread. */
class AssistantWebBridge(
    private val webView: WebView,
    private val controller: LocalAssistantApiController
) {
    private val closed = AtomicBoolean(false)
    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "assistant-api").apply { isDaemon = true }
    }

    @JavascriptInterface
    fun postMessage(rawMessage: String) {
        if (closed.get()) return
        val fallbackId = runCatching { JSONObject(rawMessage).optString("id") }.getOrDefault("invalid")
        executor.execute {
            val response = runCatching {
                controller.handle(AssistantApiMessageCodec.decode(rawMessage))
            }.getOrElse { error ->
                AssistantApiMessageCodec.error(fallbackId, 400, error.message ?: "请求格式无效")
            }
            val responseLiteral = JSONObject.quote(response.toJson().toString())
            webView.post {
                if (!closed.get()) {
                    webView.evaluateJavascript(
                        "window.AssistantApi&&window.AssistantApi.__resolve($responseLiteral)",
                        null
                    )
                }
            }
        }
    }

    fun close() {
        if (closed.compareAndSet(false, true)) executor.shutdownNow()
    }
}

package com.example.dwpmclone.ui.web

import android.webkit.JavascriptInterface
import android.webkit.WebView
import com.example.dwpmclone.host.SharedCoreEventBuffer
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONObject

/** Async lane-aware bridge; WebView never executes repository or protocol work on the UI thread. */
class AssistantWebBridge(
    private val webView: WebView,
    private val controller: LocalAssistantApiController,
    classifier: AssistantApiLaneClassifier
) {
    private val closed = AtomicBoolean(false)
    private val executionLanes = AssistantApiExecutionLanes(classifier)
    private val eventSubscription = SharedCoreEventBuffer.subscribe(::deliverEvent)

    @JavascriptInterface
    fun postMessage(rawMessage: String) {
        if (closed.get()) return
        val fallbackId = runCatching { JSONObject(rawMessage).optString("id") }.getOrDefault("invalid")
        val request = runCatching { AssistantApiMessageCodec.decode(rawMessage) }
            .getOrElse { error ->
                deliver(AssistantApiMessageCodec.error(
                    fallbackId,
                    400,
                    error.message ?: "请求格式无效"
                ))
                return
            }
        executionLanes.execute(request, Runnable {
            val response = runCatching {
                controller.handle(request)
            }.getOrElse { error ->
                AssistantApiMessageCodec.error(fallbackId, 400, error.message ?: "请求格式无效")
            }
            deliver(response)
        })
    }

    private fun deliver(response: AssistantApiResponse) {
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

    private fun deliverEvent(eventJson: String) {
        val eventLiteral = JSONObject.quote(eventJson)
        webView.post {
            if (!closed.get()) {
                webView.evaluateJavascript(
                    "window.AssistantApi&&window.AssistantApi.__event($eventLiteral)",
                    null
                )
            }
        }
    }

    fun close() {
        if (closed.compareAndSet(false, true)) {
            SharedCoreEventBuffer.unsubscribe(eventSubscription)
            executionLanes.close()
        }
    }
}

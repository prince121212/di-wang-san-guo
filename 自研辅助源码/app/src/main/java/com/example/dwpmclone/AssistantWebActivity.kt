package com.example.dwpmclone

import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.example.dwpmclone.ui.guide.NativeGuideBridge
import com.example.dwpmclone.ui.hosting.BackgroundHostingPermissionCoordinator
import com.example.dwpmclone.ui.web.AssistantWebBridge
import com.example.dwpmclone.ui.web.LocalAssistantApiController
import java.io.ByteArrayInputStream
import java.util.concurrent.atomic.AtomicBoolean

/** Single-screen local host for the shared assistant container. */
class AssistantWebActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var assistantBridge: AssistantWebBridge
    private lateinit var hostingPermissions: BackgroundHostingPermissionCoordinator
    private val fullyDrawnReported = AtomicBoolean(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        hostingPermissions = BackgroundHostingPermissionCoordinator(this)

        webView = WebView(this).apply {
            setBackgroundColor(Color.WHITE)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        configure(webView.settings)
        CookieManager.getInstance().apply {
            setAcceptCookie(false)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                setAcceptThirdPartyCookies(webView, false)
            }
        }
        assistantBridge = AssistantWebBridge(
            webView,
            LocalAssistantApiController(this) {
                hostingPermissions.requestForStartedHosting()
            }
        )
        webView.addJavascriptInterface(assistantBridge, NATIVE_API_NAME)
        webView.addJavascriptInterface(NativeGuideBridge(this), NATIVE_GUIDE_NAME)
        // The shared page uses the standard confirm() guard for account start/stop
        // and destructive actions. Without a chrome client Android silently cancels
        // those dialogs, so the click never reaches the local API bridge.
        webView.webChromeClient = WebChromeClient()
        webView.webViewClient = LocalAssetWebViewClient {
            if (fullyDrawnReported.compareAndSet(false, true)) reportFullyDrawn()
        }
        setContentView(webView)
        val appVersion = runCatching {
            packageManager.getPackageInfo(packageName, 0).versionName
        }.getOrNull().orEmpty()
        webView.loadUrl("$ENTRY_URL&version=${Uri.encode(appVersion)}")
    }

    @Suppress("SetJavaScriptEnabled")
    private fun configure(settings: WebSettings) = with(settings) {
        javaScriptEnabled = true
        domStorageEnabled = true
        allowContentAccess = false
        allowFileAccess = true
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        }
        javaScriptCanOpenWindowsAutomatically = false
        setSupportMultipleWindows(false)
        mediaPlaybackRequiresUserGesture = true
        cacheMode = WebSettings.LOAD_DEFAULT
        loadsImagesAutomatically = true
        useWideViewPort = true
        loadWithOverviewMode = true
        textZoom = 100
        setSupportZoom(false)
        builtInZoomControls = false
        displayZoomControls = false
    }

    override fun onDestroy() {
        assistantBridge.close()
        webView.removeJavascriptInterface(NATIVE_API_NAME)
        webView.removeJavascriptInterface(NATIVE_GUIDE_NAME)
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        if (!hostingPermissions.onRequestPermissionsResult(requestCode)) {
            super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        }
    }

    private class LocalAssetWebViewClient(
        private val onPageFinished: () -> Unit
    ) : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean =
            request?.url?.toString()?.startsWith(ASSET_PREFIX) != true

        override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?): WebResourceResponse? {
            val url = request?.url?.toString().orEmpty()
            if (url.startsWith(ASSET_PREFIX)) return super.shouldInterceptRequest(view, request)
            return WebResourceResponse(
                "text/plain",
                "UTF-8",
                ByteArrayInputStream(ByteArray(0))
            )
        }

        override fun onPageFinished(view: WebView?, url: String?) {
            super.onPageFinished(view, url)
            if (url?.startsWith(ASSET_PREFIX) == true) onPageFinished()
        }
    }

    private companion object {
        const val ASSET_PREFIX = "file:///android_asset/assistant/"
        const val ENTRY_URL = "${ASSET_PREFIX}index.html?mobile=1&local=1"
        const val NATIVE_API_NAME = "DWPMNativeApi"
        const val NATIVE_GUIDE_NAME = "DWPMNativeGuide"
    }
}

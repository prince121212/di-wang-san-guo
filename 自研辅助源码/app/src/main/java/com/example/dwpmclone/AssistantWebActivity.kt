package com.example.dwpmclone

import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.view.WindowInsets
import android.widget.FrameLayout
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.example.dwpmclone.ui.hosting.BackgroundHostingPermissionCoordinator
import com.example.dwpmclone.ui.hosting.BackgroundHostingPermissionState
import com.example.dwpmclone.data.local.LocalHostingPreferences
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.service.AssistantForegroundService
import com.example.dwpmclone.ui.web.AssistantApiLaneClassifierAssetLoader
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
        // Android 15+ edge-to-edge enforcement otherwise places the WebView at y=0,
        // underneath the time/signal/battery row. This screen intentionally uses
        // the system status and navigation bars. Read the real device insets and
        // reserve exactly that space instead of guessing one model-specific height.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = 0
        }
        @Suppress("DEPRECATION")
        window.setStatusBarColor(Color.WHITE)
        @Suppress("DEPRECATION")
        window.setNavigationBarColor(Color.WHITE)
        // A vendor deep link that silently fails looks exactly like the user
        // declining, so record which page actually opened in the same log the
        // support flow already reads.
        hostingPermissions = BackgroundHostingPermissionCoordinator(this) { outcome ->
            TaskLogRepository(this).append(outcome, tag = "scheduler-health")
        }

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
            LocalAssistantApiController(
                context = this,
                onBackgroundPermissionAction = hostingPermissions::open,
                onHostingStarted = hostingPermissions::requestForStartedHosting,
            ),
            AssistantApiLaneClassifierAssetLoader.load(this)
        )
        webView.addJavascriptInterface(assistantBridge, NATIVE_API_NAME)
        // The shared page uses the standard confirm() guard for account start/stop
        // and destructive actions. Without a chrome client Android silently cancels
        // those dialogs, so the click never reaches the local API bridge.
        webView.webChromeClient = WebChromeClient()
        webView.webViewClient = LocalAssetWebViewClient {
            if (fullyDrawnReported.compareAndSet(false, true)) reportFullyDrawn()
        }
        val content = FrameLayout(this).apply {
            setBackgroundColor(Color.WHITE)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            addView(webView)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                setOnApplyWindowInsetsListener { view, insets ->
                    val bars = insets.getInsets(
                        WindowInsets.Type.systemBars() or
                            WindowInsets.Type.displayCutout()
                    )
                    view.setPadding(
                        bars.left,
                        bars.top,
                        bars.right,
                        bars.bottom
                    )
                    insets
                }
            }
        }
        setContentView(content)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            content.requestApplyInsets()
        }
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
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }

    override fun onResume() {
        super.onResume()
        if (
            BackgroundHostingPermissionState.read(this).reliableHostingReady &&
            LocalHostingPreferences(this).isEnabled() &&
            !AssistantForegroundService.isExecutionOwnerActive()
        ) {
            // Returning from a system permission screen is the explicit recovery boundary.
            // If hosting had been fail-closed while permissions were missing, resume it now.
            AssistantForegroundService.refresh(this)
        }
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
    }
}

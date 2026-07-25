package com.example.dwpmclone

import android.annotation.SuppressLint
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import com.example.dwpmclone.data.remote.DesktopCoreApiClient
import com.example.dwpmclone.data.remote.DesktopCoreSettingsRepository

/**
 * Full Android control surface backed by the desktop core.
 *
 * It intentionally reuses the desktop web console so every desktop feature is
 * available immediately and future UI/business fixes do not need a second
 * Android implementation.  The native "攻略/查名将/查开服" pages remain in
 * MainActivity for offline use.
 */
class RemoteCoreActivity : BaseUiActivity() {
    private val settingsRepo by lazy { DesktopCoreSettingsRepository(this) }
    private var webView: WebView? = null
    private var progress: ProgressBar? = null
    private var status: TextView? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val settings = settingsRepo.load()
        val error = settings.validationError()
        if (error != null) {
            setContentView(LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setPadding(dp(28), dp(28), dp(28), dp(28))
                addView(sectionTitle("电脑端核心尚未连接"))
                addView(bodyText("$error\n\n请返回 Home 页面，填写电脑局域网地址与 Mobile API Token。"))
                addView(outlineButton("返回设置") { finish() })
            })
            return
        }

        val allowedBase = Uri.parse(settings.normalizedBaseUrl)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
        }
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = true
            max = 100
        }
        status = TextView(this).apply {
            text = "正在连接电脑端核心…"
            textSize = 13f
            setTextColor(COLOR_SUBTEXT)
            setPadding(dp(12), dp(5), dp(12), dp(5))
        }
        val browser = WebView(this).apply {
            setBackgroundColor(Color.WHITE)
            this.settings.javaScriptEnabled = true
            this.settings.domStorageEnabled = true
            this.settings.databaseEnabled = true
            this.settings.allowFileAccess = false
            this.settings.allowContentAccess = false
            this.settings.cacheMode = WebSettings.LOAD_NO_CACHE
            this.settings.userAgentString = this.settings.userAgentString + " DWPMAndroidRemote/1.0"
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                this.settings.safeBrowsingEnabled = true
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                this.settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            }
            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView?, newProgress: Int) {
                    this@RemoteCoreActivity.progress?.isIndeterminate = false
                    this@RemoteCoreActivity.progress?.progress = newProgress
                    if (newProgress >= 100) {
                        this@RemoteCoreActivity.progress?.visibility = android.view.View.GONE
                    }
                }
            }
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                    val target = request?.url ?: return true
                    return !sameOrigin(allowedBase, target)
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    status?.text = "电脑端核心已连接 · 所有真实任务由电脑端执行"
                    if (url?.contains("/index.html?mobile=1") == true) {
                        // Remove the one-time pairing URL (which carried the API
                        // token) from WebView history after the server set its
                        // HttpOnly cookie and redirected to the console.
                        view?.post { view.clearHistory() }
                    }
                }

                override fun onReceivedError(
                    view: WebView?,
                    request: WebResourceRequest?,
                    error: WebResourceError?
                ) {
                    if (request?.isForMainFrame == true) {
                        status?.text = "连接失败：${error?.description ?: "网络异常"}"
                        this@RemoteCoreActivity.progress?.visibility = android.view.View.GONE
                    }
                }

                override fun onReceivedHttpError(
                    view: WebView?,
                    request: WebResourceRequest?,
                    errorResponse: WebResourceResponse?
                ) {
                    if (request?.isForMainFrame == true && (errorResponse?.statusCode ?: 0) >= 400) {
                        status?.text = "电脑端返回 HTTP ${errorResponse?.statusCode}，请检查地址和 Token"
                        this@RemoteCoreActivity.progress?.visibility = android.view.View.GONE
                    }
                }
            }
        }
        webView = browser
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                setAcceptThirdPartyCookies(browser, false)
            }
        }
        root.addView(progress, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(3)
        ))
        root.addView(status)
        root.addView(browser, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            0,
            1f
        ))
        setContentView(root)
        browser.loadUrl(DesktopCoreApiClient(settings).webConsoleUrl())
    }

    override fun onBackPressed() {
        val browser = webView
        if (browser?.canGoBack() == true) browser.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        webView?.apply {
            stopLoading()
            loadUrl("about:blank")
            clearHistory()
            removeAllViews()
            destroy()
        }
        webView = null
        super.onDestroy()
    }

    private fun sameOrigin(base: Uri, target: Uri): Boolean =
        base.scheme.equals(target.scheme, ignoreCase = true) &&
            base.host.equals(target.host, ignoreCase = true) &&
            effectivePort(base) == effectivePort(target)

    private fun effectivePort(uri: Uri): Int = when {
        uri.port >= 0 -> uri.port
        uri.scheme.equals("https", true) -> 443
        else -> 80
    }
}

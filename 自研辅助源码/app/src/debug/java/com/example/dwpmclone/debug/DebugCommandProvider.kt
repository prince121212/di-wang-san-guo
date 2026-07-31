package com.example.dwpmclone.debug

import android.content.ContentProvider
import android.content.ContentValues
import android.content.Context
import android.content.pm.ApplicationInfo
import android.database.Cursor
import android.net.Uri
import android.os.Binder
import android.os.Build
import android.os.Bundle
import android.os.Process
import android.util.Base64
import android.webkit.WebView
import com.example.dwpmclone.ui.web.AssistantApiMessageCodec
import com.example.dwpmclone.ui.web.LocalAssistantApiController
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import org.json.JSONObject

/**
 * Debug APK only: exposes the existing local API controller to `adb shell content call`.
 *
 * This class deliberately contains no feature-specific behavior. Requests use exactly the same
 * codec and controller as the WebView. The provider is declared only by src/debug, so release
 * builds do not contain an exported debugging surface.
 */
class DebugCommandProvider : ContentProvider() {
    private lateinit var appContext: Context
    private lateinit var controller: LocalAssistantApiController

    override fun onCreate(): Boolean {
        appContext = requireNotNull(context).applicationContext
        controller = LocalAssistantApiController(appContext)
        WebView.setWebContentsDebuggingEnabled(true)
        return true
    }

    override fun call(method: String, arg: String?, extras: Bundle?): Bundle {
        enforceAllowedCaller()
        val payload = when (method) {
            METHOD_IDENTITY -> identity()
            METHOD_API -> invokeApi(arg, extras)
            else -> throw IllegalArgumentException("不支持的调试方法：$method")
        }
        return Bundle().apply {
            putInt(RESULT_PROTOCOL_KEY, RESULT_PROTOCOL_VERSION)
            putString(RESULT_ENCODING_KEY, RESULT_ENCODING)
            putString(RESULT_KEY, encode(payload.toString()))
        }
    }

    private fun invokeApi(encodedRequest: String?, extras: Bundle?): JSONObject {
        if (encodedRequest.isNullOrBlank()) {
            return AssistantApiMessageCodec.error("invalid", 400, "缺少 API 请求").toJson()
        }
        if (encodedRequest.length > MAX_ENCODED_REQUEST_CHARS) {
            return AssistantApiMessageCodec.error("invalid", 400, "API 请求超过256KB限制").toJson()
        }
        return runCatching {
            val raw = String(
                Base64.decode(encodedRequest, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING),
                Charsets.UTF_8
            )
            val request = AssistantApiMessageCodec.decode(raw)
            if (request.method == "POST" && !postWasExplicitlyConfirmed(extras)) {
                return@runCatching AssistantApiMessageCodec.error(
                    request.id,
                    403,
                    "POST 可能改变真实账号状态，必须使用 --allow-post 显式确认"
                ).toJson()
            }
            controller.handle(request).toJson()
        }.getOrElse { error ->
            AssistantApiMessageCodec.error(
                "invalid",
                if (error is IllegalArgumentException) 400 else 500,
                error.message ?: "调试请求处理失败"
            ).toJson()
        }
    }

    private fun postWasExplicitlyConfirmed(extras: Bundle?): Boolean =
        extras?.getBoolean(EXTRA_ALLOW_POST, false) == true &&
            extras.getString(EXTRA_POST_CONFIRMATION) == POST_CONFIRMATION

    private fun identity(): JSONObject {
        val packageInfo = appContext.packageManager.getPackageInfo(appContext.packageName, 0)
        val sourceFile = File(appContext.applicationInfo.sourceDir)
        return JSONObject()
            .put("ok", true)
            .put("debugProtocol", RESULT_PROTOCOL_VERSION)
            .put("packageName", appContext.packageName)
            .put("versionName", packageInfo.versionName.orEmpty())
            .put("versionCode", packageVersionCode(packageInfo))
            .put(
                "debuggable",
                appContext.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
            )
            .put("pid", Process.myPid())
            .put("uid", Process.myUid())
            .put("callingUid", Binder.getCallingUid())
            .put("apkSha256", sha256(sourceFile))
            .put("sourceDir", sourceFile.absolutePath)
            .put("sourceDirLastModified", sourceFile.lastModified())
            .put("packageLastUpdateTime", packageInfo.lastUpdateTime)
    }

    @Suppress("DEPRECATION")
    private fun packageVersionCode(packageInfo: android.content.pm.PackageInfo): Long =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            packageInfo.longVersionCode
        } else {
            packageInfo.versionCode.toLong()
        }

    private fun enforceAllowedCaller() {
        val callingUid = Binder.getCallingUid()
        val allowed = callingUid == Process.myUid() ||
            callingUid == Process.SHELL_UID ||
            callingUid == Process.ROOT_UID ||
            callingUid == Process.SYSTEM_UID
        if (!allowed) {
            throw SecurityException("调试入口仅允许 adb shell、root、system 或本应用调用")
        }
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                if (read > 0) digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { byte ->
            String.format(Locale.ROOT, "%02x", byte.toInt() and 0xff)
        }
    }

    private fun encode(raw: String): String = Base64.encodeToString(
        raw.toByteArray(Charsets.UTF_8),
        Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
    )

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?
    ): Cursor? = unsupportedCrud()

    override fun insert(uri: Uri, values: ContentValues?): Uri? = unsupportedCrud()

    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int =
        unsupportedCrud()

    override fun update(
        uri: Uri,
        values: ContentValues?,
        selection: String?,
        selectionArgs: Array<out String>?
    ): Int = unsupportedCrud()

    override fun getType(uri: Uri): String? = null

    private fun <T> unsupportedCrud(): T =
        throw UnsupportedOperationException("调试 Provider 仅支持 call")

    private companion object {
        const val METHOD_IDENTITY = "identity"
        const val METHOD_API = "api"
        const val RESULT_KEY = "debug_result"
        const val RESULT_ENCODING_KEY = "debug_encoding"
        const val RESULT_PROTOCOL_KEY = "debug_protocol"
        const val RESULT_ENCODING = "base64url"
        const val RESULT_PROTOCOL_VERSION = 1
        const val EXTRA_ALLOW_POST = "allow_post"
        const val EXTRA_POST_CONFIRMATION = "post_confirmation"
        const val POST_CONFIRMATION = "ALLOW_REAL_POST"
        const val MAX_ENCODED_REQUEST_CHARS =
            ((AssistantApiMessageCodec.MAX_MESSAGE_CHARS + 2) / 3) * 4
    }
}

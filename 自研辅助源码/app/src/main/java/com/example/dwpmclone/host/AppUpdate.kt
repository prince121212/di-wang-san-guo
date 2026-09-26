package com.example.dwpmclone.host

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import com.example.dwpmclone.BuildConfig
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/** One published release, as described by the official site's `/app/latest.json`. */
data class AppRelease(
    val versionCode: Int,
    val versionName: String,
    val publishedAt: Long,
    val sizeBytes: Long,
    val sha256: String,
    val downloadUrl: String,
    val notes: List<String>,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("versionCode", versionCode)
        .put("versionName", versionName)
        .put("publishedAt", publishedAt)
        .put("sizeBytes", sizeBytes)
        .put("sha256", sha256)
        .put("notes", JSONArray(notes))

    companion object {
        /**
         * Trust a manifest only when it describes this package and its download stays on the
         * official site over HTTPS. The URL only ever goes to the system browser, and Android
         * itself refuses an update signed by a different certificate.
         */
        fun parse(raw: String, packageName: String, officialSite: String): AppRelease {
            val value = try { JSONObject(raw) } catch (_: JSONException) {
                throw IllegalArgumentException("官网更新信息格式无效")
            }
            require(value.optInt("schemaVersion") == 1) { "官网更新信息版本不受支持，请到官网手动下载" }
            require(value.optString("packageName") == packageName) { "官网更新信息不属于本应用" }
            val versionCode = value.optInt("versionCode")
            val versionName = value.optString("versionName")
            require(versionCode > 0 && VERSION_NAME.matches(versionName)) { "官网更新信息版本号无效" }
            val downloadUrl = value.optString("downloadUrl")
            require(isOfficialDownload(downloadUrl, officialSite)) { "更新下载地址不是官网地址" }
            val sha256 = value.optString("sha256")
            require(SHA256.matches(sha256)) { "官网更新信息校验值无效" }
            val notes = value.optJSONArray("notes") ?: JSONArray()
            return AppRelease(
                versionCode = versionCode,
                versionName = versionName,
                publishedAt = value.optLong("publishedAt"),
                sizeBytes = value.optLong("sizeBytes"),
                sha256 = sha256,
                downloadUrl = downloadUrl,
                notes = (0 until notes.length()).mapNotNull { notes.optString(it).trim().takeIf(String::isNotEmpty) }.take(20),
            )
        }

        fun isOfficialDownload(url: String, officialSite: String): Boolean {
            val target = runCatching { URI(url) }.getOrNull() ?: return false
            val site = runCatching { URI(officialSite.trim().trimEnd('/')) }.getOrNull() ?: return false
            return target.scheme == "https" && site.scheme == "https" && target.host != null &&
                target.host.equals(site.host, ignoreCase = true) && target.port == site.port &&
                target.rawUserInfo == null && target.rawQuery == null && target.rawFragment == null &&
                DOWNLOAD_PATH.matches(target.rawPath.orEmpty())
        }

        private val VERSION_NAME = Regex("""^V\d{1,3}\.\d{1,3}\.\d{1,4}$""")
        private val SHA256 = Regex("^[0-9a-f]{64}$")
        private val DOWNLOAD_PATH = Regex("""^/download/dwsg-V\d{1,3}\.\d{1,3}\.\d{1,4}\.apk$""")
    }
}

/** Checks the official site for a newer release and hands its download to the system browser. */
class AppUpdateChecker private constructor(private val context: Context) {
    private var result: JSONObject? = null
    private var checkedAtMillis = 0L
    private var latest: AppRelease? = null

    /** Official builds only: debug-signed and suffixed test builds cannot be updated in place. */
    private val supported = !BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == OFFICIAL_PACKAGE

    /** Local state only; never touches the network. */
    @Synchronized fun status(): JSONObject = base()
        .put("latest", latest?.toJson() ?: JSONObject.NULL)
        .put("updateAvailable", updateAvailable(latest))
        .put("checkedAt", checkedAtMillis)

    @Synchronized fun check(force: Boolean): JSONObject {
        if (!supported) return base().put("latest", JSONObject.NULL).put("updateAvailable", false)
            .put("message", "当前是测试或内部版本，不通过官网更新")
        val now = System.currentTimeMillis()
        result?.let { if (!force && now - checkedAtMillis < CACHE_MILLIS) return JSONObject(it.toString()) }
        val checked = try {
            val release = fetch()
            latest = release
            checkedAtMillis = now
            status().put("message", when {
                release == null -> "官网暂未发布新版本"
                updateAvailable(release) -> "发现新版本 ${release.versionName}"
                else -> "已是最新版本"
            })
        } catch (error: IllegalArgumentException) {
            base().put("ok", false).put("error", error.message ?: "官网更新信息无效")
        } catch (_: Exception) {
            base().put("ok", false).put("error", "暂时无法连接官网，请检查网络后重试")
        }
        if (checked.optBoolean("ok")) result = checked
        return JSONObject(checked.toString())
    }

    @Synchronized fun openDownload(): JSONObject {
        val release = latest?.takeIf(::updateAvailable)
            ?: return JSONObject().put("ok", false).put("error", "请先检查更新")
        check(AppRelease.isOfficialDownload(release.downloadUrl, BuildConfig.OFFICIAL_SITE_URL))
        return browse(release.downloadUrl)
    }

    /** The official site's home page: downloads, release notes and the QQ group. */
    @Synchronized fun openSite(): JSONObject {
        val site = BuildConfig.OFFICIAL_SITE_URL.trim().trimEnd('/')
        require(URL(site).protocol == "https") { "官网地址必须使用 HTTPS" }
        return browse("$site/")
    }

    private fun browse(url: String): JSONObject = try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        JSONObject().put("ok", true)
    } catch (_: ActivityNotFoundException) {
        JSONObject().put("ok", false).put("error", "手机上没有可用的浏览器，请手动访问 $url")
    }

    private fun base(): JSONObject = JSONObject()
        .put("ok", true)
        .put("supported", supported)
        .put("currentVersionName", BuildConfig.VERSION_NAME)
        .put("currentVersionCode", BuildConfig.VERSION_CODE)
        .put("officialSite", BuildConfig.OFFICIAL_SITE_URL)

    private fun updateAvailable(release: AppRelease?): Boolean =
        supported && release != null && release.versionCode > BuildConfig.VERSION_CODE

    private fun fetch(): AppRelease? {
        val site = BuildConfig.OFFICIAL_SITE_URL.trim().trimEnd('/')
        require(URL(site).protocol == "https") { "官网地址必须使用 HTTPS" }
        val connection = (URL("$site/app/latest.json").openConnection() as HttpURLConnection).apply {
            connectTimeout = 5_000; readTimeout = 10_000; instanceFollowRedirects = false; useCaches = false
            setRequestProperty("Accept", "application/json"); setRequestProperty("Cache-Control", "no-cache")
        }
        return try {
            when (val status = connection.responseCode) {
                404 -> null
                in 200..299 -> AppRelease.parse(connection.inputStream.use(::readManifest), OFFICIAL_PACKAGE, site)
                else -> throw IOException("official site returned $status")
            }
        } finally {
            connection.disconnect()
        }
    }

    private fun readManifest(stream: InputStream): String {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val read = stream.read(buffer)
            if (read < 0) break
            output.write(buffer, 0, read)
            require(output.size() <= MAX_MANIFEST_BYTES) { "官网更新信息过大" }
        }
        return output.toString(Charsets.UTF_8.name())
    }

    companion object {
        const val OFFICIAL_PACKAGE = "com.example.dwpmclone"
        private const val CACHE_MILLIS = 10 * 60_000L
        private const val MAX_MANIFEST_BYTES = 64 * 1024
        @Volatile private var instance: AppUpdateChecker? = null
        fun get(context: Context): AppUpdateChecker = instance ?: synchronized(this) {
            instance ?: AppUpdateChecker(context.applicationContext).also { instance = it }
        }
    }
}

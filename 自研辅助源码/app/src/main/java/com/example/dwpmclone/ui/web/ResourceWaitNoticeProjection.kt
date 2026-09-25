package com.example.dwpmclone.ui.web

import org.json.JSONObject

/** A current core failure outranks stale runtime/log copies, even when dismissed. */
internal data class ResourceWaitNoticeProjection(
    val features: Set<String>,
    val visible: List<JSONObject>,
) {
    companion object {
        fun from(
            envelope: JSONObject,
            isDismissed: (String) -> Boolean,
        ): ResourceWaitNoticeProjection {
            val rows = envelope.optJSONArray("notices")
            val features = linkedSetOf<String>()
            val visible = mutableListOf<JSONObject>()
            if (envelope.optBoolean("ok", false) && rows != null) {
                for (index in 0 until rows.length()) {
                    val notice = rows.optJSONObject(index) ?: continue
                    val feature = notice.optString("feature").trim()
                    val key = notice.optString("key").trim()
                    if (feature.isBlank() ||
                        !(key.startsWith("resource:") || key.startsWith("brush-lane:"))
                    ) continue
                    features += feature
                    if (!isDismissed(key)) visible += notice
                }
            }
            return ResourceWaitNoticeProjection(features, visible)
        }
    }
}

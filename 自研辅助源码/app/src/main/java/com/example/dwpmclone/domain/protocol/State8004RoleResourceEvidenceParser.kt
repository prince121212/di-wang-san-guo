package com.example.dwpmclone.domain.protocol

/**
 * Conservative 0x8004 role/resource evidence parser.
 *
 * Real login already parses the stable 0x8004 head in RealGameProtocolClient. This
 * bridge is for copied Frida/logcat evidence or persisted tail/payload previews that
 * expose role/resource fields as text/key-value pairs. It intentionally avoids treating
 * generic JiangLing fields such as `id/name/rank` as monarch fields because those are
 * ambiguous inside general records.
 */
object State8004RoleResourceEvidenceParser {
    private val KEY_VALUE_REGEX = Regex("""["']?([\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z0-9_]*)["']?\s*[:=]\s*('[^']*'|"[^"]*"|[^,;|\s{}]+)""")
    private val HEX_REGEX = Regex("""^(?:0x)?[0-9a-fA-F\s|:_-]{8,}$""")

    fun recover(raw: String): Map<String, String> {
        val direct = parseText(raw)
        if (direct.isNotEmpty()) return direct
        val decoded = raw.hexToUtf8EvidenceTextOrNull() ?: return emptyMap()
        return parseText(decoded).let { if (it.isEmpty()) it else it + ("source" to "state8004-role-resource-hex-keyvalue") }
    }

    private fun parseText(raw: String): Map<String, String> {
        val normalized = raw.normalizeEvidenceText()
        val out = linkedMapOf<String, String>()
        KEY_VALUE_REGEX.findAll(normalized).forEach { match ->
            val key = normalizeKey(match.groupValues[1]) ?: return@forEach
            val value = normalizeValue(key, match.groupValues[2].trim().trim('\'', '"'))
            if (value.isNotBlank()) out[key] = value
        }
        val hasRole = out.containsKey("roleName") && out.containsKey("level")
        val hasResource = out.containsKey("copper") && out.containsKey("food")
        if (!hasRole && !hasResource) return emptyMap()
        out.putIfAbsent("source", "state8004-role-resource-keyvalue")
        return out
    }

    private fun normalizeKey(raw: String): String? {
        val key = raw.trim()
        return when {
            key.equals("roleId", true) ||
                key.equals("monarchId", true) ||
                key.equals("kingId", true) ||
                key in setOf("君主ID", "角色ID", "主公ID", "玩家ID") -> "roleId"

            key.equals("roleName", true) ||
                key.equals("monarchName", true) ||
                key.equals("kingName", true) ||
                key in setOf("君主", "君主名", "角色名", "主公", "主公名", "玩家名") -> "roleName"

            key.equals("level", true) ||
                key in setOf("等级", "等級", "君主等级", "君主等級", "角色等级", "角色等級", "主公等级") -> "level"

            key.equals("nation", true) ||
                key.equals("country", true) ||
                key in setOf("国家", "國家", "势力", "勢力", "阵营", "陣營") -> "nation"

            key.equals("title", true) ||
                key.equals("officialTitle", true) ||
                key in setOf("官职", "官職", "爵位", "称号", "稱號") -> "title"

            key.equals("prestige", true) ||
                key.equals("shengwang", true) ||
                key in setOf("声望", "聲望") -> "prestige"

            key.equals("copper", true) ||
                key.equals("money", true) ||
                key.equals("tongqian", true) ||
                key in setOf("铜钱", "銅錢", "铜币", "銅幣", "钱币", "錢幣") -> "copper"

            key.equals("food", true) ||
                key.equals("liangshi", true) ||
                key in setOf("粮食", "糧食", "粮草", "糧草") -> "food"

            key.equals("copperPerHour", true) ||
                key.equals("moneyPerHour", true) ||
                key in setOf("铜钱产量", "銅錢產量", "铜钱每小时", "銅錢每小時", "钱产量") -> "copperPerHour"

            key.equals("foodPerHour", true) ||
                key in setOf("粮食产量", "糧食產量", "粮食每小时", "糧食每小時") -> "foodPerHour"

            key.equals("populationCurrent", true) ||
                key.equals("population", true) ||
                key.equals("renkou", true) ||
                key in setOf("人口", "当前人口", "當前人口") -> "populationCurrent"

            key.equals("populationCap", true) ||
                key.equals("populationLimit", true) ||
                key in setOf("人口上限", "人口容量") -> "populationCap"

            key.equals("resourcePointCurrent", true) ||
                key.equals("resourcePointUsed", true) ||
                key in setOf("资源点", "資源點", "资源点占用", "資源點占用", "已用资源点", "已用資源點") -> "resourcePointCurrent"

            key.equals("resourcePointCap", true) ||
                key.equals("resourcePointLimit", true) ||
                key in setOf("资源点上限", "資源點上限", "资源点容量", "資源點容量") -> "resourcePointCap"

            key.equals("fiefLimit", true) ||
                key in setOf("封地上限") -> "fiefLimit"

            key.equals("generalLimit", true) ||
                key in setOf("将领上限", "將領上限", "武将上限", "武將上限") -> "generalLimit"

            else -> null
        }
    }

    private fun normalizeValue(key: String, raw: String): String {
        val value = raw.trim()
        if (key == "nation") {
            return when {
                value.equals("wei", true) || value == "魏国" || value == "魏國" -> "魏"
                value.equals("shu", true) || value == "蜀国" || value == "蜀國" -> "蜀"
                value.equals("wu", true) || value == "吴国" || value == "吳國" -> "吴"
                else -> value
            }
        }
        return value
    }

    private fun String.hexToUtf8EvidenceTextOrNull(): String? {
        if (!HEX_REGEX.matches(trim())) return null
        val hex = trim()
            .removePrefix("0x")
            .removePrefix("0X")
            .filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
        if (hex.length < 2 || hex.length % 2 != 0) return null
        val bytes = runCatching {
            ByteArray(hex.length / 2) { index -> hex.substring(index * 2, index * 2 + 2).toInt(16).toByte() }
        }.getOrNull() ?: return null
        return String(bytes, Charsets.UTF_8).normalizeEvidenceText()
    }

    private fun String.normalizeEvidenceText(): String =
        map { ch ->
            when {
                ch == '\u0000' -> '|'
                ch.code in 0x20..0x7e -> ch
                ch in '\u4e00'..'\u9fff' -> ch
                ch == '\n' || ch == '\r' || ch == '\t' -> ch
                else -> '|'
            }
        }.joinToString(separator = "")
}

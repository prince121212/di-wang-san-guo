package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.model.FamousGeneral
import com.example.dwpmclone.domain.model.GuideArticle

/**
 * Local data repository for the static-evidence rebuild skeleton.
 *
 * It reads only text assets recovered from the APK: `dwsgmjb.TXT` and text files under `guidetxts`.
 * The disguised `guidetxts/guojiafenbu.png` ELF is intentionally not bundled here.
 */
class LocalGuideRepository(private val context: Context) {
    fun loadFamousGenerals(): List<FamousGeneral> {
        return readAssetText("dwsgmjb.TXT")
            .lineSequence()
            .map { it.trim().removePrefix("\uFEFF") }
            .filter { it.isNotEmpty() }
            .drop(1)
            .mapNotNull { line ->
                val parts = line.split(',')
                if (parts.size < 4) return@mapNotNull null
                FamousGeneral(
                    name = parts[0].trim(),
                    breakthrough = parts[1].trim().toIntOrNull(),
                    attribute = parts[2].trim().ifBlank { null },
                    nation = parts[3].trim().ifBlank { null }
                )
            }
            .toList()
    }

    fun searchFamousGenerals(
        nameKeyword: String? = null,
        breakthrough: Int? = null,
        attribute: String? = null,
        nation: String? = null
    ): List<FamousGeneral> {
        return loadFamousGenerals().filter { general ->
            (nameKeyword.isNullOrBlank() || general.name.contains(nameKeyword.trim(), ignoreCase = true)) &&
                (breakthrough == null || general.breakthrough == breakthrough) &&
                (attribute.isNullOrBlank() || general.attribute == attribute) &&
                (nation.isNullOrBlank() || general.nation == nation)
        }
    }

    fun loadGuideArticles(): List<GuideArticle> = GUIDE_ASSETS.map { (asset, title) ->
        GuideArticle(
            id = asset.substringBeforeLast('.'),
            title = title,
            body = readAssetText("guidetxts/$asset"),
            sourceAsset = "guidetxts/$asset"
        )
    }

    fun readGuideArticle(id: String): GuideArticle? =
        loadGuideArticles().firstOrNull { it.id == id || it.sourceAsset.endsWith("/$id") || it.sourceAsset.endsWith("/$id.txt") }

    private fun readAssetText(path: String): String =
        context.assets.open(path).bufferedReader(Charsets.UTF_8).use { it.readText().removePrefix("\uFEFF") }

    companion object {
        val GUIDE_ASSETS: List<Pair<String, String>> = listOf(
            "V6fzgl.txt" to "V6以上玩家前期发展攻略",
            "dwsgjingyan.txt" to "帝王三国升级经验",
            "pm80jigl.txt" to "15小时冲击80级攻略",
            "pmkssjgl.txt" to "快速升级攻略",
            "qzp.txt" to "强装/开箱经验",
            "rmb80jigl.txt" to "开区快速80级心得",
            "sfbgl.txt" to "副本刷将魂道具装备攻略",
            "shuashihuang.txt" to "刷黄攻略",
            "szsjgl.txt" to "神州升级攻略",
            "wuditcp.txt" to "无敌推城篇"
        )
    }
}

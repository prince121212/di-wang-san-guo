package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineConfig

/** Shared desktop/mobile rules for selecting an automatic-mining target. */
object MineTargetFilterPolicy {
    fun matches(
        target: MineSearchResult,
        config: MineConfig,
        contract: MineBehaviorContract = MineBehaviorContract.defaults()
    ): Boolean {
        if (config.selectedMineTypes.isNotEmpty() && target.mineType !in config.selectedMineTypes) {
            return false
        }
        if (config.selectedLevels.isNotEmpty()) {
            val level = target.level ?: return false
            if (contract.exactSelectedLevelRequired && level !in config.selectedLevels) return false
        }

        val occupiedEvidence = target.playerOccupied || target.raw.booleanAlias(
            "playerOccupied",
            "occupied",
            "isPlayerOccupied"
        ) == true || target.ownerName?.isNotBlank() == true || target.raw.stringAlias(
            "ownerName",
            "playerName",
            "owner",
            "lordName"
        ).isNotBlank()
        if (!contract.playerOccupiedTargetsAllowed && occupiedEvidence) return false

        // Older 0x8542 captures expose only an `isEmpty` bit. When the user asks
        // for an empty point and explicit ownership evidence is absent, fail closed.
        val hasExplicitOwnership = target.raw.keys.any { key ->
            key.equals("playerOccupied", true) ||
                key.equals("occupied", true) ||
                key.equals("isPlayerOccupied", true) ||
                key.equals("ownerName", true) ||
                key.equals("playerName", true) ||
                key.equals("owner", true) ||
                key.equals("lordName", true)
        }
        if (config.onlyEmptyMine && !hasExplicitOwnership && !target.isEmpty) return false
        if (config.onlyDefendedMine && (target.defenseCount ?: 0) <= 0) return false
        return true
    }

    fun ordered(
        targets: List<MineSearchResult>,
        center: MapCoordinate
    ): List<MineSearchResult> = targets.sortedWith(
        compareBy<MineSearchResult>(
            { it.coordinate.distanceSquared(center) },
            { -(it.level ?: 0) },
            { it.id }
        )
    )

    private fun Map<String, String>.booleanAlias(vararg keys: String): Boolean? {
        keys.forEach { key ->
            entries.firstOrNull { it.key.equals(key, true) }?.value?.let { raw ->
                when (raw.trim().lowercase()) {
                    "true", "1", "yes", "y", "是" -> return true
                    "false", "0", "no", "n", "否" -> return false
                }
            }
        }
        return null
    }

    private fun Map<String, String>.stringAlias(vararg keys: String): String =
        keys.firstNotNullOfOrNull { key ->
            entries.firstOrNull { it.key.equals(key, true) }
                ?.value
                ?.trim()
                ?.takeIf(String::isNotBlank)
        }.orEmpty()

    private fun MapCoordinate.distanceSquared(other: MapCoordinate): Int {
        val dx = x - other.x
        val dy = y - other.y
        return dx * dx + dy * dy
    }
}

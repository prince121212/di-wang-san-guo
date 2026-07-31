package com.example.dwpmclone.domain.model

/** Pure brush-yellow target rules shared by scheduler and parity fixtures. */
object ShuaHuangTargetFilterPolicy {
    fun matchesLevel(level: Int?, filter: ShuaHuangTargetFilter): Boolean {
        if (filter.levels.isNotEmpty() && (level == null || level !in filter.levels)) return false
        if (filter.minLevel != null && (level == null || level < filter.minLevel)) return false
        if (filter.maxLevel != null && (level == null || level > filter.maxLevel)) return false
        return true
    }
}

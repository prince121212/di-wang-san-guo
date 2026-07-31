package com.example.dwpmclone.data.local

/** Legacy-compatible display snapshot value; persistence remains account/session scoped. */
data class LocalRoleState(
    val roleName: String,
    val remark: String,
    val level: String,
    val exp: String,
    val nation: String,
    val copper: String,
    val food: String,
    val population: String,
    val resourcePoint: String,
    val generals: String,
    val troops: String,
    val treasures: String,
    val buffs: String,
    val source: String,
    val syncedAt: String
)

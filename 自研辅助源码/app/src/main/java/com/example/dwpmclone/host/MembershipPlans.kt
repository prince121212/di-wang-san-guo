package com.example.dwpmclone.host

/** Owner-confirmed display prices. Server still exclusively prices real orders. */
object MembershipPlans {
    data class Plan(val id: String, val title: String, val days: Int, val price: String, val note: String)
    val all = listOf(
        Plan("month", "月卡", 30, "9.90", "轻量体验，按需开通"),
        Plan("quarter", "季卡", 90, "25.90", "日常使用，从容安排"),
        Plan("year", "年卡", 365, "49.90", "长期使用，一次开通")
    )
    fun find(id: String?) = all.firstOrNull { it.id == id }
}

package com.example.dwpmclone.host

/** SDK results are hints only. No client status can grant membership. */
object AlipayResultPolicy {
    fun message(status: String?): String = when (status) {
        "9000" -> "支付宝操作已完成，正在向服务器确认到账…"
        "6001" -> "已取消付款，正在确认原订单；未确认前请勿重复付款。"
        "8000", "6004", "6002" -> "支付结果暂未确认，正在查询原订单，请勿重复付款。"
        else -> "支付宝未确认付款，正在查询原订单。"
    }
}

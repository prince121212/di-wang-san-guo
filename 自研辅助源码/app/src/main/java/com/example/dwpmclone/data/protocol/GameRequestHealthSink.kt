package com.example.dwpmclone.data.protocol

/**
 * 进程级"游戏请求健康"采集点。
 *
 * 电脑端账号卡底部有一排最近 30 次游戏请求的成败小点（`renderRecentRequestDots`）。
 * 手机端此前完全没有采集这项数据，这里补上采集入口。
 *
 * 设计约束（第一性原理）：
 * - 协议层只负责"上报一次请求的成败"，不关心存储、不持有 Context；
 * - UI 层安装 [writer] 后才真正落库。未安装时 [record] 是空操作，
 *   因此对既有协议行为零影响，也不会在单元测试里产生副作用。
 */
object GameRequestHealthSink {
    /** Scheduler accounts are serialized, but UI login uses another thread; keep attribution local. */
    private val accountId = ThreadLocal<Long>()

    /** (accountId, success, purpose, timeMillis) */
    @Volatile
    var writer: ((Long, Boolean, String, Long) -> Unit)? = null

    fun bindAccount(value: Long) {
        if (value > 0L) accountId.set(value) else accountId.remove()
    }

    fun clearAccount() = accountId.remove()

    /** Current scheduler/account binding for adjacent protocol audit logs. */
    fun currentAccountId(): Long? = accountId.get()?.takeIf { it > 0L }

    fun record(success: Boolean, purpose: String) {
        val id = accountId.get() ?: 0L
        val sink = writer
        if (id <= 0L || sink == null) return
        runCatching { sink(id, success, purpose, System.currentTimeMillis()) }
    }

    fun reset() {
        accountId.remove()
        writer = null
    }
}

/**
 * opcode → 中文用途名。用于小点的悬浮说明（对齐电脑端 dot 的 title：
 * "第N个：成功|失败 · purpose · HH:MM:SS"）。
 *
 * 未收录的 opcode 直接回退成 `0x????` 形式，不臆造名称。
 */
object GameOpcodePurpose {
    private val NAMES: Map<Int, String> = mapOf(
        0x1003 to "登录",
        0x1004 to "角色状态",
        0x1016 to "进入区服",
        0x1103 to "丢弃道具",
        0x1104 to "背包",
        0x1116 to "删除邮件",
        0x1134 to "金钻宝箱",
        0x1152 to "粮食转铜",
        0x1200 to "建造升级",
        0x1218 to "加体力",
        0x1226 to "配兵",
        0x1229 to "补兵",
        0x1230 to "治疗伤兵",
        0x1231 to "治疗预估",
        0x123F to "升级科技",
        0x1246 to "封地详情",
        0x1310 to "封地列表",
        0x1404 to "国家城池",
        0x140A to "捐科技积分",
        0x140C to "捐献",
        0x1520 to "出征准备",
        0x1522 to "出征",
        0x1540 to "找黄扫描",
        0x1542 to "找矿扫描",
        0x1702 to "战斗轮询",
        0x1900 to "无损状态",
        0x1902 to "无损结算",
        0x1906 to "无损阵容",
        0x1908 to "无损收尾",
        0x1930 to "副本目录",
        0x1938 to "副本状态",
        0x193D to "副本开箱",
        0x193E to "副本出征",
        0x3110 to "军情心跳",
        0x3144 to "使用道具",
        0x314B to "国家俸禄",
        0x6200 to "每日活动",
        0x6202 to "签到",
        0x6260 to "竞技币",
        0x6266 to "竞技币领取",
        0x6320 to "菜地状态",
        0x6322 to "偷菜候选",
        0x6323 to "偷菜目标",
        0x6328 to "种植"
    )

    fun of(opcode: Int?): String {
        if (opcode == null) return "游戏请求"
        return NAMES[opcode] ?: String.format("0x%04X", opcode)
    }
}

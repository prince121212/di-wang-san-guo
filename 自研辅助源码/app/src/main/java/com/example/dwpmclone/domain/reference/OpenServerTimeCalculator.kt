package com.example.dwpmclone.domain.reference

import java.util.Calendar
import java.util.Locale

/**
 * 本地开区时间计算器。
 *
 * 规则来源：原 APK `android/o/ۦۚۜ.smali` 的 `ۦۖ۟(I)` 与 `ۦۜۧ()`：
 * 先按版本/区服选择一个锚点规则（基准区、间隔天数、基准日期），再计算
 * `基准日期 + (查询区服 - 基准区) * 间隔天数`。
 *
 * 注意：原 APK 的下拉文案已从 QufuActivity 构造函数的 np/protect 字符串链恢复；
 * 公式和锚点来自 smali 中可验证的硬编码分支。
 */
object OpenServerTimeCalculator {
    data class VersionOption(
        val index: Int,
        val label: String,
        val summary: String,
    ) {
        override fun toString(): String = label
    }

    data class Rule(
        val baseServer: Int,
        val intervalDays: Int,
        val year: Int,
        val month: Int,
        val day: Int,
        val note: String,
    )

    data class CalculationResult(
        val server: Int,
        val version: VersionOption,
        val rule: Rule,
        val dateText: String,
        val daysOffset: Int,
    )

    data class UpcomingServer(
        val server: Int,
        val dateText: String,
    )

    val versionOptions: List<VersionOption> = listOf(
        VersionOption(0, "九游版", "30区=2012/11/29，每区间隔5天"),
        VersionOption(1, "腾讯版", "218区=2016/11/17；290区=2018/8/31；297区=2018/11/9"),
        VersionOption(2, "百度版", "30区=2012/11/29，每区间隔5天"),
        VersionOption(3, "热血帝王", "30区=2013/9/20，每区间隔7天"),
        VersionOption(4, "三国联盟", "102区=2016/10/12；112区=2017/4/26；113区=2017/5/17"),
        VersionOption(5, "新三国争霸", "30区=2012/7/13，每区间隔7天"),
        VersionOption(6, "繁体版", "30区=2015/3/20，每区间隔14天"),
    )

    fun parseServerNumber(text: String): Int? {
        return Regex("\\d+").find(text)?.value?.toIntOrNull()
    }

    fun calculate(server: Int, versionIndex: Int): CalculationResult {
        require(server > 0) { "区服编号必须大于 0" }
        val version = versionOptions.firstOrNull { it.index == versionIndex } ?: versionOptions.first()
        val rule = ruleFor(version.index, server)
        val diff = server - rule.baseServer
        val daysOffset = diff * rule.intervalDays
        val date = addDays(rule.year, rule.month, rule.day, daysOffset)
        return CalculationResult(
            server = server,
            version = version,
            rule = rule,
            dateText = String.format(Locale.CHINA, "%04d/%d/%d", date[0], date[1], date[2]),
            daysOffset = daysOffset,
        )
    }

    /**
     * 返回“下一个还没开服”的区服。
     *
     * 例：三国联盟当前规则为 113区=2017/5/17、每 14 天一服；
     * 2026/7/6 时 351区已在 2026/7/1 开，下一服是 352区（2026/7/15）。
     */
    fun upcomingServer(versionIndex: Int, today: Calendar = Calendar.getInstance(Locale.CHINA)): UpcomingServer {
        val rule = latestRuleFor(versionIndex)
        val todayDay = epochDay(today)
        val baseDay = epochDay(rule.year, rule.month, rule.day)
        val diffDays = todayDay - baseDay
        val nextStep = if (diffDays < 0) {
            0L
        } else {
            diffDays / rule.intervalDays + 1
        }
        val server = (rule.baseServer + nextStep.toInt()).coerceAtLeast(1)
        val openDate = addDays(rule.year, rule.month, rule.day, (nextStep * rule.intervalDays).toInt())
        return UpcomingServer(
            server = server,
            dateText = String.format(Locale.CHINA, "%04d/%d/%d", openDate[0], openDate[1], openDate[2]),
        )
    }

    private fun ruleFor(versionIndex: Int, server: Int): Rule {
        return when (versionIndex) {
            1 -> when {
                server < 260 -> Rule(218, 10, 2016, 11, 17, "原 APK pswitch_7：server < 260")
                server <= 290 -> Rule(290, 7, 2018, 8, 31, "原 APK pswitch_7：260..290 分段")
                else -> Rule(297, 10, 2018, 11, 9, "原 APK pswitch_7：server > 290")
            }
            3 -> Rule(30, 7, 2013, 9, 20, "原 APK pswitch_6")
            4 -> when {
                server < 111 -> Rule(102, 21, 2016, 10, 12, "原 APK pswitch_2：server < 111")
                server <= 113 -> Rule(112, 21, 2017, 4, 26, "原 APK pswitch_2：111..113 分段")
                else -> Rule(113, 14, 2017, 5, 17, "原 APK pswitch_2：server > 113")
            }
            5 -> Rule(30, 7, 2012, 7, 13, "原 APK pswitch_1")
            6 -> Rule(30, 14, 2015, 3, 20, "原 APK pswitch_0")
            0, 2 -> Rule(30, 5, 2012, 11, 29, "原 APK pswitch_8 / 默认初始规则")
            else -> Rule(30, 5, 2012, 11, 29, "原 APK 默认规则")
        }
    }

    private fun latestRuleFor(versionIndex: Int): Rule {
        return when (versionIndex) {
            1 -> Rule(297, 10, 2018, 11, 9, "原 APK pswitch_7：server > 290")
            4 -> Rule(113, 14, 2017, 5, 17, "原 APK pswitch_2：server > 113")
            else -> ruleFor(versionIndex, Int.MAX_VALUE)
        }
    }

    private fun addDays(year: Int, month: Int, day: Int, days: Int): IntArray {
        val calendar = Calendar.getInstance(Locale.CHINA).apply {
            clear()
            set(Calendar.YEAR, year)
            set(Calendar.MONTH, month - 1)
            set(Calendar.DAY_OF_MONTH, day)
            add(Calendar.DAY_OF_MONTH, days)
        }
        return intArrayOf(
            calendar.get(Calendar.YEAR),
            calendar.get(Calendar.MONTH) + 1,
            calendar.get(Calendar.DAY_OF_MONTH),
        )
    }

    private fun epochDay(year: Int, month: Int, day: Int): Long {
        val calendar = Calendar.getInstance(Locale.CHINA).apply {
            clear()
            set(Calendar.YEAR, year)
            set(Calendar.MONTH, month - 1)
            set(Calendar.DAY_OF_MONTH, day)
        }
        return epochDay(calendar)
    }

    private fun epochDay(calendar: Calendar): Long {
        val copy = calendar.clone() as Calendar
        copy.set(Calendar.HOUR_OF_DAY, 0)
        copy.set(Calendar.MINUTE, 0)
        copy.set(Calendar.SECOND, 0)
        copy.set(Calendar.MILLISECOND, 0)
        return copy.timeInMillis / 86_400_000L
    }
}

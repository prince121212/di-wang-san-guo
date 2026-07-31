package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.DailyStep
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UserFacingTextLocalizerTest {
    @Test
    fun translatesEveryDailyStepIdentifierShownByOldAndNewLogs() {
        DailyStep.entries.forEach { step ->
            val localized = UserFacingTextLocalizer.localize("日常步骤=${step.name}")
            assertFalse(localized.contains(step.name))
            assertTrue(localized.contains(step.userFacingName()))
        }
    }

    @Test
    fun everyTaskTypeHasAChineseUserFacingName() {
        TaskType.entries.forEach { type ->
            assertTrue(type.userFacingName().isNotBlank())
            assertFalse(type.userFacingName().contains('_'))
        }
        assertEquals("每日捐献", TaskType.DAILY_DONATE.userFacingName())
    }

    @Test
    fun oldSchedulerLogLinesAreLocalizedForDisplay() {
        assertEquals(
            "每日捐献 账号=202 执行结果=继续, 等待(60000毫秒)",
            UserFacingTextLocalizer.localize(
                "DAILY_DONATE account=202 decisions=Continue, Sleep(60000ms)"
            )
        )
    }

    @Test
    fun militaryTailAuditFieldsAreLocalizedForDisplay() {
        assertEquals(
            "军情数=1 将领数=14 被俘将领数=19 未解析尾部字节=0",
            UserFacingTextLocalizer.localize(
                "actions=1 generals=14 captives=19 unparsedTailBytes=0"
            )
        )
    }
}

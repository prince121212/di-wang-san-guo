package com.example.dwpmclone.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SixMinistriesConfigTest {
    @Test
    fun onlyCapturedRicePlantingCanPrepare() {
        assertNull(config(cropEnabled = true, crop = "稻谷").preparationError())
        assertEquals(
            "unverified ministry crop selected: 草药",
            config(cropEnabled = true, crop = "草药").preparationError()
        )
        assertEquals(
            "verified ministry planting disabled; steal and courtesy actions are not confirmed",
            config(cropEnabled = false, crop = "稻谷", stealEnabled = true).preparationError()
        )
    }

    private fun config(
        cropEnabled: Boolean,
        crop: String,
        stealEnabled: Boolean = false
    ) = SixMinistriesConfig(
        cropEnabled = cropEnabled,
        crop = crop,
        highPriority = true,
        stealEnabled = stealEnabled,
        courtesyEnabled = false,
        salaryRefresh = false
    )
}

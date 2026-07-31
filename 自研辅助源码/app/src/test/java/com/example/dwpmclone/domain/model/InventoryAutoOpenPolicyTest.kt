package com.example.dwpmclone.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryAutoOpenPolicyTest {
    @Test
    fun itemPickerMatchesCurrentDesktopAllowListExactly() {
        assertEquals(
            listOf(
                "50两银票", "100两银票", "300两银票", "1000两银票",
                "惊喜宝箱", "实木宝箱", "青铜宝箱", "精铁宝箱", "铜钱辎重", "粮食辎重"
            ),
            InventoryAutoOpenPolicy.DESKTOP_ITEM_NAMES
        )
    }

    @Test
    fun explicitSelectionNeverOpensOtherSilverTicketsOrBoxes() {
        val selected = setOf("50两银票", "青铜宝箱")

        assertTrue(InventoryAutoOpenPolicy.shouldOpen("50两银票", "item", selected, true, true))
        assertTrue(InventoryAutoOpenPolicy.shouldOpen("青铜宝箱", "box", selected, true, true))
        assertFalse(InventoryAutoOpenPolicy.shouldOpen("100两银票", "item", selected, true, true))
        assertFalse(InventoryAutoOpenPolicy.shouldOpen("精铁宝箱", "box", selected, true, true))
    }

    @Test
    fun explicitlySelectedFoodWagonCanBeUsedAndUnknownItemsStayBlocked() {
        assertTrue(
            InventoryAutoOpenPolicy.shouldOpen(
                "粮食辎重",
                "item",
                setOf("粮食辎重"),
                openBoxes = false,
                openSilverTickets = false
            )
        )
        assertFalse(
            InventoryAutoOpenPolicy.shouldOpen(
                "未知礼包",
                "box",
                setOf("未知礼包"),
                openBoxes = true,
                openSilverTickets = true
            )
        )
    }

    @Test
    fun oldBooleanOnlyConfigsRetainAllowListedFallback() {
        assertTrue(InventoryAutoOpenPolicy.shouldOpen("实木宝箱", "box", emptySet(), true, false))
        assertTrue(InventoryAutoOpenPolicy.shouldOpen("300两银票", "item", emptySet(), false, true))
        assertFalse(InventoryAutoOpenPolicy.shouldOpen("300两银票", "item", emptySet(), false, false))
    }
}

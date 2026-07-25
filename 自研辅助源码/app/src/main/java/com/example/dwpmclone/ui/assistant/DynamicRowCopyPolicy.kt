package com.example.dwpmclone.ui.assistant

/**
 * Matches the computer front end's dynamic-table copy rule:
 * copy all checked rows, or the first row when nothing is checked.
 */
internal fun <T> copySelectedOrFirstRows(
    rows: List<T>,
    isSelected: (T) -> Boolean,
    copyRow: (T) -> T
): List<T> {
    val source = rows.filter(isSelected).ifEmpty { rows.take(1) }
    return rows + source.map(copyRow)
}

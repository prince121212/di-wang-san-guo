package com.example.dwpmclone.data.local

import org.json.JSONArray
import org.json.JSONObject

/** Android repository boundary for the canonical non-sensitive Python account ledger. */
interface SharedAccountStateGateway {
    fun accountRecordsSnapshot(): JSONObject
    fun accountRecordsPresentationSnapshot(): JSONObject
    fun accountRecord(accountRef: String): JSONObject
    fun accountRecordPresentation(accountRef: String): JSONObject
    fun accountRecordUpsert(record: JSONObject): JSONObject
    fun accountRecordsImportIfEmpty(records: JSONArray): JSONObject
    fun accountRecordsReplace(records: JSONArray): JSONObject
    fun accountRecordDelete(accountRef: String): JSONObject
    fun accountRecordsClear(): JSONObject
}

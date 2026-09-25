# 自动闯关 payload summary

```json
{
  "method": "Landroid/o/ۦ۠ۢ$ۦۖۨ;->ۦۤۜۜ()V",
  "line_range": "82602-87182",
  "open_key": "bgOpenChuangGuanStatus",
  "rank_key": "chuangguanrank",
  "formation_key_shape": "chuangguanChuzhengBiandui + accountIndex + guaji + slotIndex",
  "last_formation_key": "lastChuangGuanChuZhengBiandui + accountIndex",
  "stamina_threshold_key": "addTiLiCounts",
  "fixed_game_hex": {
    "status_query_or_post_start_check": "00000000000000000001190000",
    "state_step_902": "00000000000000000001190200",
    "state_step_904": "00000000000000000001190400",
    "state_step_906": "00000000000000000001190600"
  },
  "response_parser": {
    "class_method": "Landroid/o/ۦۡۧ;->ۦۚۛ(Ljava/lang/String;)[I",
    "status_char_offset": "[0x3f,0x40)",
    "aux_hex_offset": "[0x5b,0x5c)",
    "cooldown_ms_hex_offset": "[0x48,0x58)",
    "status_mapping_inferred_from_code": {
      "2": "KONGXIAN/idle -> int[0]=2",
      "1": "state-1 -> int[0]=1",
      "0": "cooldown -> int[0]=0 and int[2]=hex([0x48,0x58))/1000",
      "3": "fighting/in-battle -> int[0]=3",
      "other": "unknown -> int[0]=4"
    }
  },
  "expedition_builder_p2_4": {
    "owner_id_source": "client.kU.id / Landroid/o/ۦۤۡ;->id",
    "first": "000000000000000000 + hex(n*8+0x0a) + 15200b0 + n + concat(generalIds) + ownerId",
    "second": "000000000000000000 + hex(n*8+0x15) + 15220b0 + n + concat(generalIds) + ownerId + ffffffffffffffff000000"
  }
}
```

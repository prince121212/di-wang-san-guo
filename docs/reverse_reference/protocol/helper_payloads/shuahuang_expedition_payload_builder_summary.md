# 刷黄出征 payload builder 摘要（机器可读公式的 Markdown 版）

- 原始 smali：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk/recovered/business_fake_apk_2026-07-06/apktool_decoded/smali/android/o/ۦۡۛ.smali`
- 公式 JSON：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk/analysis/shuahuang_expedition_decode_2026-07-06/shuahuang_expedition_payload_builder_summary.json`

## 刷黄使用的 p2=0 两段请求

```text
prepare/first = 000000000000000000 + hex(ids.size * 8 + 0x0a) + 1520030 + ids.size(decimal) + concat(ids) + 0000 + targetId
expedition/second = 000000000000000000 + hex(ids.size * 8 + 0x15) + 1522030 + ids.size(decimal) + concat(ids) + 0000 + targetId + ffffffffffffffff000000
```

## 所有分支

### 1520 builder

| p2 | opcode | trailer | formula |
|---:|---|---|---|
| 0 | `1520030` | `0000 + targetId` | `000000000000000000 + lenHex + 1520030 + ids.size(decimal) + concat(ids) + 0000 + targetId` |
| 1 | `1520020` | `0000 + targetId` | `000000000000000000 + lenHex + 1520020 + ids.size(decimal) + concat(ids) + 0000 + targetId` |
| 2 | `15200e0` | `ffffffff0004 + targetId` | `000000000000000000 + lenHex + 15200e0 + ids.size(decimal) + concat(ids) + ffffffff0004 + targetId` |
| 3 | `1520010` | `targetId` | `000000000000000000 + lenHex + 1520010 + ids.size(decimal) + concat(ids) + targetId` |
| 4 | `15200b0` | `targetId` | `000000000000000000 + lenHex + 15200b0 + ids.size(decimal) + concat(ids) + targetId` |

### 1522 builder

| p2 | opcode | trailer | formula |
|---:|---|---|---|
| 0 | `1522030` | `0000 + targetId + ffffffffffffffff000000` | `000000000000000000 + lenHex + 1522030 + ids.size(decimal) + concat(ids) + 0000 + targetId + ffffffffffffffff000000` |
| 1 | `1522020` | `0000 + targetId + ffffffffffffffff000000` | `000000000000000000 + lenHex + 1522020 + ids.size(decimal) + concat(ids) + 0000 + targetId + ffffffffffffffff000000` |
| 2 | `15220e0` | `ffffffff0004 + targetId + ffffffffffffffff000000` | `000000000000000000 + lenHex + 15220e0 + ids.size(decimal) + concat(ids) + ffffffff0004 + targetId + ffffffffffffffff000000` |
| 3 | `1522010` | `targetId + ffffffffffffffff000000` | `000000000000000000 + lenHex + 1522010 + ids.size(decimal) + concat(ids) + targetId + ffffffffffffffff000000` |
| 4 | `15220b0` | `targetId + ffffffffffffffff000000` | `000000000000000000 + lenHex + 15220b0 + ids.size(decimal) + concat(ids) + targetId + ffffffffffffffff000000` |

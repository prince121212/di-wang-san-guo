# 三国·帝王联盟 1.66 APK 离线逆向报告

## 范围
- 样本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/三国·帝王联盟1.66.apk`
- 分析方式：本地离线静态分析；未执行 APK；未连接外部服务。
- Case 工作区：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166`

## 样本指纹
- APK SHA-256：`4571a166fd46c21edee1e2994d9e6e3bc905b41b049f80f89b7774f65cdc5fb8`
- APK 大小：`88,956,239` bytes
- 原始壳 DEX：`classes.dex`，大小 `7,275,448` bytes，仅 8 个 class，主要为 `com.xmxu.jiagu.*` Stub。
- 恢复出的真实 DEX：`recovered/original_classes_1.dex`
  - SHA-256：`8df5340f841c7f73c1ff0287ce9b7baabb931cc0b4f86b1eccb55154a8991537`
  - 大小：`7,261,232` bytes
  - Classes：`3047`；Methods：`32390`；Strings：`38118`

## Manifest 摘要
- 包名：`com.gamebox.king`
- 版本：`versionCode=182`，`versionName=1.66.0606`
- SDK：`minSdkVersion=21`，`targetSdkVersion=26`
- 壳入口：`application android:name="com.xmxu.jiagu.StubApp"`
- 真实 Application：`com.gamebox.king.GameboxApplication`
- 主 Activity：`com.gamebox.king.KingActivity`，`exported=true`
- 网络安全配置：`base-config cleartextTrafficPermitted="true"`
- 支付/推送相关：支付宝 SDK、微信支付入口、腾讯 TPNS/XG Push。

## 加固/壳识别与脱壳结果
证据显示 APK 使用 `com.xmxu.jiagu` 壳：

- Manifest Application 指向 `com.xmxu.jiagu.StubApp`。
- APK 内置 `assets/libjiagu.so`、`assets/libjiagu_64.so`、`assets/libjiagu_x86.so`、`assets/libjiagu_x86_64.so`。
- 壳 DEX 只有 8 个类，包含 `AssetsUtil.copyJiagu`、`ZipUtil.getDexData`、`StubApp.attach`。
- `assets/libjiagu.so` 非 stripped，导出 `AES_CBC_decrypt_buffer`、`JNI_OnLoad`、`native_attach`、`loadDex` 等符号。

恢复算法已验证：

1. `classes.dex` 最后 4 字节按大端解释为 payload 起始偏移：`0x0000374c` = `14156`。
2. 从 `classes.dex[14156:14156+0x210]` 取 528 字节 AES-CBC 加密头。
3. Key：`xmxu3b4j3bvuoa3h`；IV：`mers46ha35ga23hn`。
4. AES-128-CBC 解密并去除 PKCS#7 padding，得到 512 字节明文头。
5. 拼接：`decrypted_header + classes.dex[14156+0x210:-4]` 得到 payload blob。
6. payload blob 格式：
   - 1 字节真实 Application 类名长度：`0x23`
   - 35 字节类名：`com.gamebox.king.GameboxApplication`
   - 4 字节大端 DEX 长度：`0x006ecc30` = `7261232`
   - 后续即真实 `dex\n035`。

复现脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts_recover_payload.py`

## 关键业务/网络线索
- 默认配置文件：`assets/script/defautConfig.properties`
  - `channel.gw=http://king9.cn`
  - `channel.passport=https://sglmpass.3gking.net:12443/`
  - `version.fullnum=v1.66.0606`
  - `version.res=20260526`
- DEX 字符串中发现历史/默认服务器配置：
  - `http://dxt11v13g.3gking.net:25511`
  - `http://resource.3gking.net:8080/...`
  - `http://139g.gameboxapi.net:8192/`
  - `YgbChargeUrl=http://host:port`
- 支付接口字符串包含：
  - `/asset/charge/comalipay.action`
  - `/asset/charge/g139wechatapporder.action`
  - `/asset/charge/g139wxawftorder.action`
  - `/mol/charge/purchase.action?`
  - `https://www.yeepay.com/app-merchant-proxy/node?`

## 风险/漏洞候选（需后续验证）
1. **明文 HTTP 允许且存在 HTTP 业务端点**：Manifest 的 `cleartextTrafficPermitted=true` 与 `http://king9.cn`、`http://resource.3gking.net:8080` 等端点共同出现，存在明文传输/中间人风险候选。
2. **弱/旧签名材料**：证书使用 `sha1WithRSAEncryption`、1024-bit RSA，自签名主体 `gamebox/huangyang`。这是兼容旧 APK 的常见情况，但从现代安全基线看偏弱。
3. **硬编码 TPNS 凭据**：Manifest 内含 `XG_V2_ACCESS_ID=1500008315` 与 `XG_V2_ACCESS_KEY=AC52L4OL64S0`；通常推送 SDK 会内置这些值，但仍属于可提取凭据。
4. **导出组件审计点**：`com.tencent.android.tpush.TpnsActivity exported=true` 且带 `BROWSABLE` scheme；`com.tencent.android.tpush.XGVipPushKAProvider exported=true`。需要动态/源码级验证其参数校验和权限边界。
5. **加固壳可离线恢复**：壳算法和 key/iv 均在本地可提取，已成功恢复真实 DEX；说明该壳主要提供混淆/加载阻碍，不构成强保护。

## 输出文件
- Manifest 解析：`analysis/AndroidManifest.parsed.xml`
- 资源 XML 解析：`analysis/res_xml/`
- 壳 DEX 摘要：`analysis/dex/dex_summary.md`
- Native 摘要与反汇编：`analysis/native/`
- 恢复元数据：`recovered/recovery_metadata.json`
- 真实 DEX：`recovered/original_classes_1.dex`
- 真实 DEX 摘要：`analysis/recovered_dex/original_classes_1_summary.md`

# 手机主应用保留数据升级 V115

用户授权原签名内部包覆盖升级，禁止卸载或清数据。

## 已完成

- 主包 com.example.dwpmclone：V0.0.113 → V0.0.115，adb install -r 成功。
- 安装前校验旧APK与新debug包证书SHA256一致：c0281a7624f659f9c0fd5d155c68af8598c1fc4c0dc0cd7e4818973329ce71f7。
- 升级前短暂停止应用，备份 shared_prefs 与 files/shared_python_core；安装后首次启动前逐字节校验账号记录、功能配置、账号密文、会话密文、会员登录文件全部一致。
- 启动后再次检查：3条账号身份不变，功能配置文件与账号密文不变，会员状态 MEMBER_ACTIVE / allowed=true。
- 公共账号状态中的 cloudRuntimeConfigJson 在运行中刷新，不用旧备份覆盖动态状态。
- Debug单元测试594项通过。未执行重新登录、删除账号、导入覆盖或清理配置。
- 备份位于用户的认证相关/帝三V113升级前备份-20260925/consistent，目录700、文件600；加密内容依赖原Android Keystore，不能把该备份视为可卸载后恢复的保证。

## 正式包专属图标

- src/release/AndroidManifest.xml 单独配置 android:icon 与 android:roundIcon。
- 原解包路径已不存在，从项目保留的当乐帝王三国.apk/res/z7.png 恢复其 drawable-ldpi/icon_round（76x76），视觉核对为用户指定圆形皇帝图。
- 仅release包包含official_app_icon，debug/membertest图标不改。
- 新正式APK构建、签名校验通过，SHA256：c7a2589665689787bfa7ff99aa7b49907f41fbfdbd9d1f34a8e353465c02b87e。

## 尚未安装正式包的原因

正式包与内部主包相同包名但不同签名，Android不能并存，也不能保数据直接互相覆盖。
需用户确认独立包名/数据迁移方案及对应支付宝应用包名配置后继续；不得为安装正式包卸载现有主包。
仅账号列表和普通设置可做受控迁移；加密凭据、会员设备私钥与登录会话不能简单跨包复制，目标应用需要重新登录。

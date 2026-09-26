# V117：后台权限仅作建议，不拦截启动

用户明确要求未授予通知、省电豁免等权限仍可启动账号，只提醒后台可能受限。
本版本替代V116的权限强制前置检查；V116文档仅保留历史问题记录。

## 实现

- 删除账号启动、保存任务启动时的权限拒绝分支，密码和会员授权校验不变。
- 前端只异步记录提醒，不等待权限查询，也不强制跳转设置页；查询失败不拒绝启动。
- 服务仍调用 Android 正常 startForeground，但不因通知可见性/电池豁免缺失而自行停止，不在每个调度周期以权限缺失拦截任务。日志仅在风险变化时记录。
- 首次引导可选择“暂不设置，继续使用”；设置页明确全部是建议/按需，未授权仍可启动账号和任务。
- JSON保留可靠性诊断字段，blockingIssues为空，风险另用warningIssues表示，startupBlockedByPermissions=false。
- Android自身的后台服务启动、Doze及厂商限制依然有效；不自授权限、不绕过系统限制。提示使用“后台或锁屏后可能暂停网络或停止应用”，不保证后台不被杀。

## 验证与交付

- 596项Android内部版测试和47项界面测试通过，包含缺权限只提醒、不跳设置、不拒绝启动及查询失败场景。
- V0.0.117-internal 保数据覆盖 com.example.dwpmclone.internal；安装前备份位于用户认证相关/帝三内部版V117升级前备份-20260926。
- 升级前后 dwpm_clone_configs.xml、dwpm_secure_credentials.xml 哈希一致，原账号/刷黄配置/密码凭据未改动。
- 现有用户权限未被撤销或授予。真机启动后 serviceActive=true、MEMBER_ACTIVE，界面显示账号已开启；缺权限路径由自动化回归验证，未在用户正在运行的环境撤销权限做实验。
- V0.0.117正式release包已构建并验签，沿用原正式签名和release专属游戏图标，未安装或卸载主包。

## 官方行为依据

- Android启动前台服务不要求POST_NOTIFICATIONS已授予，但仍需提交前台服务通知：
  https://developer.android.com/develop/ui/compose/notifications/notification-permission
- Doze可能推迟后台CPU/网络执行，电池豁免并非应用登录必需条件：
  https://developer.android.com/training/monitoring-device-state/doze-standby

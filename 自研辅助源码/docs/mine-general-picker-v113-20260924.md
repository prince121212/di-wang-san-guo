# V113 动态编队将领选择器修复

问题：打矿第一行可选将领，新增第二行及后续行点击无响应。
根因：dynamic-add/dynamic-copy使用cloneNode(true)，只复制DOM，没有复制onclick、
onchange、oninput；新增行之后只重绑动态表格按钮，没有重绑bindLiveControls里的
将领选择器。重新渲染已保存页面可能恢复，不能据此认为问题不存在。

修复：抽出bindGeneralMultiControls，每次绑定动态表格时都绑定将领选择器；
使用属性赋值而非叠加监听器，重复绑定不会一次点击开关两次。
复制时清掉展开状态和搜索过滤，保留所选将领与顺序；新增时原有规则清空选择。
不改变5人上限、同封地限制、保存流程、出征或后台调度。
相同动态表格机制下的其他军事页面同时受益，不复制业务代码。

回归：新增第二/第三行、复制行、勾选/搜索/全选/清除、重复绑定、复制搜索过滤。
修复前3项用例失败，修复后4项专项通过；全部页面37项、Python1373项通过，
Android单测及assembleDebug成功。未在真实账号上新增、保存编队或发出征请求。
安装目标为原com.example.dwpmclone，同Debug签名覆盖升级，不卸载或清数据。
配置备份位于忽略目录reports/mine-picker-v113/config-before.xml，0600权限。

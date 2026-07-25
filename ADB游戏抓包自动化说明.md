# ADB 游戏抓包自动化说明

脚本路径：

```bash
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/自研辅助源码/tools/adb_game_capture_automation.py
```

## 1. 查看状态

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py status
```

会显示：

- 当前 ADB 前台 App
- 8092 无痕抓包状态
- pcap 大小
- flows 数量

抓包控制台现在明确区分：

- `game351`：只抓351区 `118.89.111.11:25511`
- `game352`：只抓352区 `115.159.92.72:25511`
- `wide`：全量抓手机TCP，并同时解析351、352区业务包

命令行启动指定区服抓包：

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py --capture-mode game351 ensure-capture
python3 自研辅助源码/tools/adb_game_capture_automation.py --capture-mode game352 ensure-capture
```

抓取当乐帝王三国时，首次应使用全量模式发现登录服和游戏服：

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py \
  --platform downjoy --capture-mode wide ensure-capture
```

## 2. 自动登录并进入 351 区

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py login351
```

行为：

1. 确保 `http://127.0.0.1:8092` 抓包已开启；
2. 启动原版游戏 `com.gamebox.king`；
3. 如果已在主城，直接退出；
4. 如果在登录页，点击登录；
5. 如果在角色页，默认使用当前显示的 `周年服351区(新服)`；
6. 点击“进入游戏”；
7. 自动截图、写抓包 marker、检查 pcap 增长。

如果需要强制重启游戏：

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py login351 --force-stop
```

## 3. 功能点抓包

只打 marker，手动操作：

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py feature 配兵 --screenshot-before --duration 20 --screenshot-after
```

自动点击一个坐标：

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py feature 军情 --tap 120,520,打开军情 --duration 10 --screenshot-after
```

`--tap` 可重复：

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py feature 示例 --tap 100,200,第一步 --tap 300,400,第二步
```

## 4. 手动点击坐标

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py tap 1365 845 --label 进入游戏 --robust --confirm-keys
```

## 5. 坐标校准

开启触摸指针：

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py pointer-calibrate
```

关闭触摸指针：

```bash
python3 自研辅助源码/tools/adb_game_capture_automation.py pointer-off
```

当前已校准结论：

- 游戏横屏截图：`2712x1220`
- ADB 点击坐标直接使用横屏截图坐标
- 登录按钮：`1530,700`
- 进入游戏按钮：`1365,845`

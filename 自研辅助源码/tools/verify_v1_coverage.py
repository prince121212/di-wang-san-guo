#!/usr/bin/env python3
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[5] if len(ROOT.parents) > 5 else ROOT
APK = ROOT / 'app/build/outputs/apk/debug/app-debug.apk'
SRC = ROOT / 'app/src/main/java/com/example/dwpmclone'
ASSET = ROOT / 'app/src/main/assets/screen_specs.json'
REPORT_MD = ROOT / 'reports/v2_coverage_report.md'
REPORT_JSON = ROOT / 'reports/v2_coverage_report.json'

REQUIRED_TASK_TYPES = [
    'SHUA_HUANG', 'MINE_SEARCH', 'AUTO_MINING', 'DAILY', 'GENERAL', 'FORMATION',
    'INTERNAL', 'MINISTRY', 'DUNGEON', 'LOSSLESS', 'INVENTORY', 'VIP', 'RESOURCE_POINT_SEND_GENERAL',
    'SURRENDER_RELEASE', 'AUTO_LOOT', 'ALARM_WITHDRAW', 'BULK_TOOLS',
    'OPEN_SERVER_QUERY', 'CITY_SEARCH', 'TREASURE_SEARCH'
]

REMOTE_DAILY_TASK_TYPES = {
    'DAILY_DONATE', 'DAILY_SALARY', 'DAILY_NATIONAL_COLLECT',
    'DAILY_CITY_LORD_COLLECT', 'DAILY_GENERAL_VISIT',
}

REMOTE_DAILY_WIRE_ACTIONS = {
    'SIGN_IN("signIn")',
    'ARENA_COINS("arenaCoins")',
    'DONATE("donate")',
    'SALARY("salary")',
    'NATIONAL_COLLECT("nationalCollect")',
    'CITY_LORD_COLLECT("cityLordCollect")',
    'GENERAL_VISIT_CANDIDATES("generalVisitCandidates")',
    'GENERAL_VISIT("generalVisit")',
}

EXPECTED_FEATURES = {
    'account_processing': '账号管理与账号处理框架',
    'guaji_start': '后台托管主控',
    'batch_guaji_antiban': '批量挂机/防封设置',
    'shua_huang': '自动刷黄/刷山贼',
    'mine_search': '找矿设置',
    'auto_mining': '自动刷矿',
    'daily_basic': '一键日常勾选项',
    'general': '将领维护',
    'formation_troop': '编队/配兵',
    'internal_affairs': '自动内政',
    'dungeon': '自动副本/自动闯关',
    'inventory': '宝库/背包整理',
    'surrender_release': '自动劝降/释放',
    'resource_point_send_general': '资源点送将',
    'vip': '游戏内 VIP 功能开关',
    'bulk_tools': '批量工具',
    'open_server_query': '开区查询',
    'treasure_filter': '宝藏筛选',
    'famous_general_filter': '名将筛选',
}

SUPPLEMENTAL_FEATURE_SOURCE_TOKENS = {
    'auto_loot': 'AutoLootConfig',
    'alarm_withdraw': 'AlarmWithdrawConfig',
    'six_ministries': 'SixMinistriesConfig',
}

PROHIBITED_ASSET_FEATURES = {'shuai_search', 'shuai_result', 'shuai_result_row', 'license', 'enter_gate'}
PROHIBITED_TASK_TYPES = {'SHUAI_SEARCH', 'LICENSE'}


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def command(cmd):
    env = os.environ.copy()
    env.setdefault('JAVA_HOME', '/opt/homebrew/Cellar/openjdk@17/17.0.19/libexec/openjdk.jdk/Contents/Home')
    env['PATH'] = env['JAVA_HOME'] + '/bin:/opt/homebrew/bin:' + env.get('PATH', '')
    try:
        p = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=30)
        return p.returncode, p.stdout.strip()
    except Exception as e:
        return 999, str(e)


def parse_task_types():
    text = read(SRC / 'domain/protocol/ProtocolAndTasks.kt')
    m = re.search(r'enum\s+class\s+TaskType\s*\{([^}]*)\}', text, re.S)
    if not m:
        return []
    return [x.strip() for x in re.split(r'[,\n]', m.group(1)) if x.strip()]


def source_contains(token):
    for p in SRC.rglob('*.kt'):
        if token in read(p):
            return True
    return False


def main():
    data = json.loads(read(ASSET))
    screen_ids = {s['feature_id'] for s in data.get('screens', [])}
    task_types = parse_task_types()
    apk_exists = APK.exists() and APK.stat().st_size > 0
    main_activity = read(SRC / 'MainActivity.kt')
    remote_activity = read(SRC / 'RemoteCoreActivity.kt')
    remote_client = read(SRC / 'data/remote/DesktopCoreApiClient.kt')
    manifest_source = read(ROOT / 'app/src/main/AndroidManifest.xml')

    checks = []
    def add(name, ok, evidence, severity='error'):
        checks.append({'name': name, 'ok': bool(ok), 'severity': severity, 'evidence': evidence})

    missing_features = sorted(set(EXPECTED_FEATURES) - screen_ids)
    add('静态页面规格覆盖交接文档已有功能', not missing_features, f'missing={missing_features}; present_count={len(screen_ids)}')

    for fid, token in SUPPLEMENTAL_FEATURE_SOURCE_TOKENS.items():
        add(f'补充功能 {fid} 已在 Kotlin 层实现', source_contains(token), f'token={token}')

    prohibited_present = sorted(PROHIBITED_ASSET_FEATURES & screen_ids)
    add('v1 删除/不复刻页面未出现在 screen_specs', not prohibited_present, f'present={prohibited_present}')

    missing_task_types = sorted(set(REQUIRED_TASK_TYPES) - set(task_types))
    add(
        'TaskType 保留迁移期本地任务边界并允许远程核心扩展',
        not missing_task_types,
        f'missing={missing_task_types}; actual={task_types}'
    )
    missing_remote_daily_types = sorted(REMOTE_DAILY_TASK_TYPES - set(task_types))
    add(
        '新增独立日常任务类型已进入迁移期配置模型',
        not missing_remote_daily_types,
        f'missing={missing_remote_daily_types or "none"}'
    )
    prohibited_tasks = sorted(PROHIBITED_TASK_TYPES & set(task_types))
    add('TaskType 不包含已删除/不复刻任务', not prohibited_tasks, f'present={prohibited_tasks}')

    add('账号本地管理仓库存在', source_contains('class LocalAccountRepository'), 'LocalAccountRepository.kt')
    add('后台前台服务存在', source_contains('class AssistantForegroundService'), 'AssistantForegroundService.kt')
    add('本地调度协议客户端存在且仅用于计划/日志边界', source_contains('class MockGameProtocolClient'), 'MockGameProtocolClient.kt')
    add(
        '电脑端统一核心 WebView 入口已注册',
        'class RemoteCoreActivity' in remote_activity
        and '.RemoteCoreActivity' in manifest_source
        and 'DesktopCoreApiClient(settings).webConsoleUrl()' in remote_activity,
        'RemoteCoreActivity.kt + AndroidManifest.xml'
    )
    add(
        'WebView 仅允许同源导航且禁用文件/内容访问',
        'return !sameOrigin(allowedBase, target)' in remote_activity
        and 'allowFileAccess = false' in remote_activity
        and 'allowContentAccess = false' in remote_activity,
        'same-origin + no file/content access'
    )
    missing_remote_actions = sorted(
        token for token in REMOTE_DAILY_WIRE_ACTIONS if token not in remote_client
    )
    add(
        'Mobile API 薄客户端覆盖全部独立日常动作',
        not missing_remote_actions,
        f'missing={missing_remote_actions or "none"}'
    )
    add(
        '名将拜访保留勾选顺序、去重且最多四名',
        '.distinct().take(4)' in remote_client
        and 'generalVisitGeneralIds' in remote_client,
        'DesktopCoreApiClient.dailyAction'
    )
    preserved_other_entries = {
        '查名将入口': 'primaryButton("查名将") { showFamousGeneralLookup() }',
        '查攻略入口': 'outlineButton("查攻略") { showGuideArticles() }',
        '查开服时间入口': 'outlineButton("查开服时间") { showOpenServerLookup() }',
        '查名将页面': 'private fun showFamousGeneralLookup(',
        '查攻略页面': 'private fun showGuideArticles()',
        '查开服时间页面': 'private fun showOpenServerLookup()',
    }
    missing_other_entries = [
        name for name, token in preserved_other_entries.items()
        if token not in main_activity
    ]
    add(
        '安卓“其他”页保留三个可点击入口及对应功能页面',
        not missing_other_entries,
        f'missing={missing_other_entries or "none"}'
    )
    add(
        '角色页包含与电脑端一致的任务入口',
        'ConfigNavItem("任务", custom = "tasks")' in main_activity and 'private fun roleTaskPanel()' in main_activity,
        'MainActivity.kt role task tab/panel'
    )
    add(
        '原生主界面保持薄客户端，完整桌面控件由统一 WebView 复用',
        '"+容器"' not in main_activity
        and 'DesktopCoreApiClient(settings).webConsoleUrl()' in remote_activity,
        'MainActivity.kt + RemoteCoreActivity.kt'
    )
    add('APK 已产出', apk_exists, str(APK))

    rc, manifest = command(['apkanalyzer', 'manifest', 'print', str(APK)]) if apk_exists else (1, '')
    add('APK Manifest 可解析', rc == 0, manifest[:500])
    add('APK label 为 自研服务', 'android:label="自研服务"' in manifest, 'manifest label check')
    add('APK versionName 为 1.0-v2-real-login', 'android:versionName="1.0-v2-real-login"' in manifest, 'manifest versionName check')

    rc, devices = command(['adb', 'devices', '-l'])
    device_lines = [line for line in devices.splitlines()[1:] if line.strip()]
    add('ADB 检测到安卓设备，可继续真机安装验证', bool(device_lines), devices or '(empty)', severity='warning')

    success = all(c['ok'] for c in checks if c['severity'] == 'error')
    result = {'success': success, 'apk': str(APK), 'checks': checks}
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = ['# 自研服务 APK v2 覆盖验证报告', '', f'- APK: `{APK}`', f'- 结论: {"通过电脑端统一核心 / 安卓薄客户端覆盖检查" if success else "存在本地阻断项"}', '', '## 检查项', '']
    for c in checks:
        mark = '✅' if c['ok'] else ('⚠️' if c['severity'] == 'warning' else '❌')
        lines.append(f'- {mark} **{c["name"]}** — `{c["evidence"]}`')
    lines += ['', '## 说明', '', '- 正式任务采用“电脑端唯一执行核心 + 安卓远程控制面”：游戏协议、会话、代理、任务调度、每日锁和日志均由电脑端负责。', '- 本报告验证安卓薄客户端、Mobile API 动作映射、迁移期配置模型与 APK 构建覆盖；真机安装、启动和系统 WebView 兼容性仍需 ADB 连接设备后验证。']
    REPORT_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(REPORT_MD)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if success else 1

if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""ADB + 无痕抓包自动化脚本。

用途：
  - 自动启动/保持 8092 无痕抓包。
  - 自动启动原版游戏 com.gamebox.king。
  - 自动完成「登录页 -> 351 区角色页 -> 进入游戏」。
  - 给抓包时间线写入明确 marker，方便后续解析某个功能点。

说明：
  本脚本默认使用已经校准过的横屏截图坐标（2712x1220）。
  如果游戏 UI / 分辨率变化，可用 `pointer-calibrate` 重新开启触点显示校准。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

try:
    from PIL import Image
except Exception:  # pragma: no cover - 脚本运行时可降级
    Image = None  # type: ignore


ROOT = pathlib.Path("/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国")
CTF_OUT = ROOT / "ctf_out"
DEFAULT_CAPTURE_API = "http://127.0.0.1:8092"
DEFAULT_PACKAGE = "com.gamebox.king"
DEFAULT_ACTIVITY = "com.gamebox.king/.KingActivity"
DEFAULT_GAME_HOST = "118.89.111.11"
GAME_352_HOST = "115.159.92.72"
DEFAULT_GAME_PORT = 25511
DEFAULT_IFACE = "bridge100"
DEFAULT_PHONE_IP = "192.168.3.2"


@dataclass(frozen=True)
class Point:
    x: int
    y: int


# 已通过 pointer_location 校准：ADB input 坐标与横屏截图坐标一致。
LOGIN_BUTTON = Point(1530, 700)
ENTER_GAME_BUTTON = Point(1365, 845)


def now_text() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run(cmd: list[str], *, check: bool = True, capture: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    if capture:
        return subprocess.run(cmd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    return subprocess.run(cmd, check=check, text=True, timeout=timeout)


def adb(args: list[str], *, check: bool = True, capture: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return run(["adb", *args], check=check, capture=capture, timeout=timeout)


def api_json(base: str, path: str, body: dict[str, Any] | None = None, timeout: float = 5) -> dict[str, Any]:
    url = base.rstrip("/") + path
    data = None
    headers = {"Content-Type": "application/json"}
    method = "GET"
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        method = "POST"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def capture_status(base: str) -> dict[str, Any]:
    return api_json(base, "/api/status")


def mark_capture(base: str, event: str) -> None:
    try:
        api_json(base, "/api/mark", {"event": event})
    except Exception as exc:
        print(f"[WARN] 写抓包 marker 失败：{exc}", file=sys.stderr)


def detect_phone_ip() -> str:
    cp = adb(
        [
            "shell",
            "ip -o -4 addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1",
        ],
        capture=True,
        check=False,
        timeout=5,
    )
    ip = (cp.stdout or "").strip().replace("\r", "")
    return ip or DEFAULT_PHONE_IP


def ensure_capture(args: argparse.Namespace) -> dict[str, Any]:
    try:
        st = capture_status(args.capture_api)
    except Exception as exc:
        raise SystemExit(
            f"无法访问抓包控制台 {args.capture_api}：{exc}\n"
            "请先运行：/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/开启无痕抓包.command"
        )
    if st.get("running"):
        print(f"[OK] 抓包已运行：{st.get('captureDir')}")
        return st

    phone_ip = args.phone_ip or detect_phone_ip()
    payload = {
        "platform": args.platform,
        "mode": args.capture_mode,
        "phoneIp": phone_ip,
        "iface": args.iface,
        "host": args.host,
        "port": int(args.port),
    }
    st = api_json(args.capture_api, "/api/start", payload)
    print(f"[OK] 抓包已启动：{st.get('captureDir')}")
    return st


def screenshot_path(args: argparse.Namespace, name: str) -> pathlib.Path:
    try:
        st = capture_status(args.capture_api)
        cap_dir = st.get("captureDir")
    except Exception:
        cap_dir = None
    if cap_dir:
        out_dir = pathlib.Path(cap_dir) / "automation_screenshots"
    else:
        out_dir = CTF_OUT / "automation_screenshots"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # 抓包目录常由 sudo/root 创建，普通用户可能没有写权限。
        # 截图不影响 pcap 本身，自动降级写到 ctf_out/automation_screenshots。
        out_dir = CTF_OUT / "automation_screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return out_dir / f"{stamp}_{name}.png"


def screenshot(args: argparse.Namespace, name: str = "screen") -> pathlib.Path:
    out = screenshot_path(args, name)
    remote = f"/sdcard/{out.name}"
    adb(["shell", "screencap", "-p", remote], check=True)
    adb(["pull", remote, str(out)], check=True, capture=True)
    print(f"[SHOT] {out}")
    return out


def detect_screen(image_path: pathlib.Path) -> str:
    """非常轻量的画面判断。

    返回：
      - role: 351 角色页/角色选择页，红色“进入游戏”按钮区域明显。
      - main: 主城/游戏内，顶部资源条/右侧功能按钮明显，且没有角色页红按钮。
      - unknown: 其他。

    这里不用 OCR，避免依赖 tesseract。坐标基于 2712x1220 横屏截图。
    """
    if Image is None:
        return "unknown"
    try:
        im = Image.open(image_path).convert("RGB")
    except Exception:
        return "unknown"
    w, h = im.size
    if w < 2000 or h < 1000:
        return "unknown"

    def ratio(box: tuple[int, int, int, int], pred) -> float:
        crop = im.crop(box)
        pix = list(crop.getdata())
        if not pix:
            return 0.0
        return sum(1 for p in pix if pred(*p)) / len(pix)

    # 角色页红色“进入游戏”按钮。
    role_red = ratio((1180, 790, 1550, 900), lambda r, g, b: r > 120 and g < 110 and b < 90)
    # 主城右下/顶部 UI 的高饱和黄色/红色较多。
    main_ui = ratio((1800, 0, 2680, 260), lambda r, g, b: r > 120 and g > 80 and b < 80)
    main_bottom = ratio((1820, 1010, 2680, 1215), lambda r, g, b: r > 110 and g > 70 and b < 80)

    if role_red > 0.12:
        return "role"
    if main_ui > 0.025 or main_bottom > 0.025:
        return "main"
    return "unknown"


def pcap_size(args: argparse.Namespace) -> int:
    try:
        return int(capture_status(args.capture_api).get("pcapSize") or 0)
    except Exception:
        return 0


def wait_pcap_growth(args: argparse.Namespace, before: int, *, min_delta: int = 256, timeout: float = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        cur = pcap_size(args)
        if cur >= before + min_delta:
            print(f"[OK] pcap 增长：{before} -> {cur}")
            return True
        time.sleep(1)
    cur = pcap_size(args)
    print(f"[WARN] 等待 pcap 增长超时：{before} -> {cur}")
    return False


def focus_info() -> str:
    cp = adb(
        ["shell", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -5"],
        capture=True,
        check=False,
        timeout=5,
    )
    return (cp.stdout or "").strip().replace("\r", "")


def launch_game(args: argparse.Namespace) -> None:
    if args.force_stop:
        print("[ADB] force-stop game")
        adb(["shell", "am", "force-stop", args.package], check=False)
        time.sleep(1)
    print(f"[ADB] start {args.activity}")
    adb(["shell", "am", "start", "-n", args.activity], check=False)
    time.sleep(args.launch_wait)
    print(focus_info())


def tap(point: Point, label: str = "", *, double: bool = False, long_ms: int = 0) -> None:
    if label:
        print(f"[TAP] {label}: {point.x},{point.y}")
    adb(["shell", "input", "tap", str(point.x), str(point.y)], check=False)
    if double:
        time.sleep(0.35)
        adb(["shell", "input", "tap", str(point.x), str(point.y)], check=False)
    if long_ms > 0:
        time.sleep(0.5)
        adb(
            [
                "shell",
                "input",
                "swipe",
                str(point.x),
                str(point.y),
                str(point.x),
                str(point.y),
                str(long_ms),
            ],
            check=False,
        )


def robust_activate(point: Point, label: str, *, confirm_keys: bool = False) -> None:
    """对游戏按钮更稳的点击序列。

    经验：
      - 登录/进入按钮有时单次 tap 不响应。
      - 双击 + 短长按更接近手动操作。
      - 部分按钮随后可用 ENTER / DPAD_CENTER 补确认。
    """
    tap(point, label, double=True, long_ms=500)
    if confirm_keys:
        time.sleep(1)
        adb(["shell", "input", "keyevent", "66"], check=False)  # ENTER
        time.sleep(0.5)
        adb(["shell", "input", "keyevent", "23"], check=False)  # DPAD_CENTER


def set_pointer(enabled: bool) -> None:
    val = "1" if enabled else "0"
    adb(["shell", "settings", "put", "system", "show_touches", val], check=False)
    adb(["shell", "settings", "put", "system", "pointer_location", val], check=False)


def cmd_pointer_calibrate(args: argparse.Namespace) -> None:
    set_pointer(True)
    print("[OK] 已开启触摸指针显示。")
    print("校准方法：")
    print("  adb shell input swipe X Y X Y 2500")
    print("  然后截图观察蓝色十字是否压在目标按钮中心。")
    print("关闭：python adb_game_capture_automation.py pointer-off")


def cmd_pointer_off(args: argparse.Namespace) -> None:
    set_pointer(False)
    print("[OK] 已关闭触摸指针显示。")


def cmd_status(args: argparse.Namespace) -> None:
    print("[ADB]")
    print(focus_info() or "(no focus)")
    try:
        st = capture_status(args.capture_api)
        print("[CAPTURE]")
        for k in ("running", "captureDir", "pcap", "pcapSize", "phoneIp", "iface", "filter", "error"):
            print(f"{k}: {st.get(k)}")
        print(f"records: {len(st.get('records') or [])}")
        print(f"flows: {len(st.get('flows') or [])}")
    except Exception as exc:
        print(f"[CAPTURE] unavailable: {exc}")


def cmd_screenshot(args: argparse.Namespace) -> None:
    shot = screenshot(args, args.name)
    print(f"screen={detect_screen(shot)}")


def cmd_mark(args: argparse.Namespace) -> None:
    mark_capture(args.capture_api, args.event)
    print(f"[MARK] {args.event}")


def cmd_tap(args: argparse.Namespace) -> None:
    mark_capture(args.capture_api, f"手动点击：{args.label or ''} {args.x},{args.y}")
    if args.robust:
        robust_activate(Point(args.x, args.y), args.label or "manual", confirm_keys=args.confirm_keys)
    else:
        tap(Point(args.x, args.y), args.label or "manual", double=args.double, long_ms=args.long_ms)
    if args.after_wait:
        time.sleep(args.after_wait)
    shot = screenshot(args, args.label or "after_tap")
    print(f"screen={detect_screen(shot)} pcapSize={pcap_size(args)}")


def cmd_login_351(args: argparse.Namespace) -> None:
    st = ensure_capture(args)
    mark_capture(args.capture_api, "自动流程开始：登录原版游戏并进入351区")
    set_pointer(False)
    launch_game(args)

    shot = screenshot(args, "before_login351")
    screen = detect_screen(shot)
    print(f"[SCREEN] {screen}")

    if screen == "main":
        print("[OK] 已在游戏内，无需登录。")
        mark_capture(args.capture_api, "自动流程结束：检测到已在游戏内")
        return

    if screen != "role":
        before = pcap_size(args)
        mark_capture(args.capture_api, "自动流程：点击登录按钮")
        robust_activate(LOGIN_BUTTON, "登录按钮", confirm_keys=False)
        time.sleep(args.after_login_wait)
        wait_pcap_growth(args, before, min_delta=256, timeout=10)
        shot = screenshot(args, "after_login_button")
        screen = detect_screen(shot)
        print(f"[SCREEN] {screen}")

    if screen != "role":
        print("[WARN] 尚未识别到角色页；仍将按当前画面尝试一次进入按钮。")

    before = pcap_size(args)
    mark_capture(args.capture_api, "自动流程：确认/使用周年服351区，点击进入游戏")
    robust_activate(ENTER_GAME_BUTTON, "进入游戏按钮", confirm_keys=True)
    time.sleep(args.after_enter_wait)
    wait_pcap_growth(args, before, min_delta=512, timeout=10)

    shot = screenshot(args, "after_enter_game")
    screen = detect_screen(shot)
    print(f"[SCREEN] {screen}")
    print(f"[CAPTURE] pcapSize={pcap_size(args)}")
    mark_capture(args.capture_api, f"自动流程结束：login351 screen={screen} pcapSize={pcap_size(args)}")


def cmd_feature(args: argparse.Namespace) -> None:
    ensure_capture(args)
    set_pointer(False)
    mark_capture(args.capture_api, f"功能点抓包开始：{args.name}")
    before = pcap_size(args)
    if args.screenshot_before:
        screenshot(args, f"feature_{args.name}_before")
    if args.tap:
        for spec in args.tap:
            parts = spec.split(",")
            if len(parts) < 2:
                raise SystemExit(f"--tap 格式错误：{spec}，应为 x,y[,label]")
            x, y = int(parts[0]), int(parts[1])
            label = parts[2] if len(parts) >= 3 else args.name
            mark_capture(args.capture_api, f"功能点 {args.name} 点击：{label} {x},{y}")
            robust_activate(Point(x, y), label, confirm_keys=False)
            time.sleep(args.tap_wait)
    if args.duration:
        print(f"[WAIT] {args.duration}s")
        time.sleep(args.duration)
    if args.screenshot_after:
        screenshot(args, f"feature_{args.name}_after")
    after = pcap_size(args)
    mark_capture(args.capture_api, f"功能点抓包结束：{args.name} pcap {before}->{after}")
    print(f"[DONE] {args.name}: pcap {before}->{after}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="帝王三国原版游戏 ADB + 无痕抓包自动化")
    p.add_argument("--capture-api", default=DEFAULT_CAPTURE_API)
    p.add_argument("--package", default=DEFAULT_PACKAGE)
    p.add_argument("--activity", default=DEFAULT_ACTIVITY)
    p.add_argument("--phone-ip", default="")
    p.add_argument("--iface", default=DEFAULT_IFACE)
    p.add_argument("--host", default=DEFAULT_GAME_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_GAME_PORT)
    p.add_argument(
        "--platform",
        choices=["downjoy", "hotblood-alliance", "sanguo-alliance", "other"],
        default="downjoy",
        help="为本次抓包标记游戏平台，不改变TCP过滤条件",
    )
    p.add_argument(
        "--capture-mode",
        choices=["game351", "game352", "wide", "custom"],
        default="game351",
        help=(
            "game351=118.89.111.11，game352=115.159.92.72，"
            "wide=全量手机TCP"
        ),
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="查看 ADB 焦点和抓包状态")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("ensure-capture", help="确保 8092 抓包已启动")
    s.set_defaults(func=lambda a: print(json.dumps(ensure_capture(a), ensure_ascii=False, indent=2)))

    s = sub.add_parser("screenshot", help="截图并保存到当前 captureDir/automation_screenshots")
    s.add_argument("--name", default="screen")
    s.set_defaults(func=cmd_screenshot)

    s = sub.add_parser("mark", help="给抓包时间线写 marker")
    s.add_argument("event")
    s.set_defaults(func=cmd_mark)

    s = sub.add_parser("tap", help="点击指定横屏坐标")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.add_argument("--label", default="")
    s.add_argument("--double", action="store_true")
    s.add_argument("--long-ms", type=int, default=0)
    s.add_argument("--robust", action="store_true")
    s.add_argument("--confirm-keys", action="store_true")
    s.add_argument("--after-wait", type=float, default=2)
    s.set_defaults(func=cmd_tap)

    s = sub.add_parser("pointer-calibrate", help="开启触摸指针，用于校准按钮坐标")
    s.set_defaults(func=cmd_pointer_calibrate)

    s = sub.add_parser("pointer-off", help="关闭触摸指针")
    s.set_defaults(func=cmd_pointer_off)

    s = sub.add_parser("login351", help="自动登录并进入周年服351区")
    s.add_argument("--force-stop", action="store_true", help="先强停原版游戏再启动")
    s.add_argument("--launch-wait", type=float, default=8)
    s.add_argument("--after-login-wait", type=float, default=12)
    s.add_argument("--after-enter-wait", type=float, default=25)
    s.set_defaults(func=cmd_login_351)

    s = sub.add_parser("feature", help="通用功能点抓包：打 marker，可选点击一组坐标")
    s.add_argument("name")
    s.add_argument("--tap", action="append", help="点击坐标，格式 x,y[,label]；可重复")
    s.add_argument("--tap-wait", type=float, default=2)
    s.add_argument("--duration", type=float, default=0)
    s.add_argument("--screenshot-before", action="store_true")
    s.add_argument("--screenshot-after", action="store_true")
    s.set_defaults(func=cmd_feature)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

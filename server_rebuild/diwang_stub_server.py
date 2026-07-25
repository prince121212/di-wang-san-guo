#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三国·帝王联盟 APK 兼容服务端骨架（本地恢复/协议学习版）

目标：
- 根据 APK 中恢复到的 action path、资源目录和默认配置，提供最小可运行 HTTP 服务。
- 记录客户端请求，便于逐步补齐真实协议。
- 不依赖第三方库；默认监听 127.0.0.1:8080。

说明：
- 这不是完整游戏逻辑服务器，而是“可迭代的协议兼容层”。
- 如果客户端期望二进制 socket 协议，需要继续对 engineBase.io / 网络类做函数级逆向或抓包验证。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import sqlite3
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA = ROOT / "data"
LOGS = ROOT / "logs"
DB_PATH = DATA / "diwang_stub.sqlite3"

DEFAULT_CHANNEL = "gbsglm"
DEFAULT_SERVER_ID = "LOCAL_1"
DEFAULT_SERVER_NAME = "本地恢复1区"
DEFAULT_VERSION = "1.66.0606"
DEFAULT_RES_VERSION = "20260526"


def now_ms() -> int:
    return int(time.time() * 1000)


def ensure_db() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    create table if not exists accounts(
      username text primary key,
      password text not null,
      user_id text not null,
      created_at integer not null
    )
    """)
    cur.execute("""
    create table if not exists sessions(
      session text primary key,
      username text not null,
      user_id text not null,
      created_at integer not null,
      last_seen integer not null
    )
    """)
    cur.execute("""
    create table if not exists roles(
      user_id text primary key,
      role_id text not null,
      role_name text not null,
      server_id text not null,
      level integer not null,
      gold integer not null,
      silver integer not null,
      food integer not null,
      wood integer not null,
      iron integer not null,
      created_at integer not null
    )
    """)
    con.commit(); con.close()


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def get_or_create_account(username: str, password: str) -> dict:
    con = db(); cur = con.cursor()
    row = cur.execute("select * from accounts where username=?", (username,)).fetchone()
    if row is None:
        user_id = f"U{now_ms()}{secrets.randbelow(10000):04d}"
        cur.execute("insert into accounts(username,password,user_id,created_at) values(?,?,?,?)", (username,password,user_id,now_ms()))
        cur.execute("insert into roles(user_id,role_id,role_name,server_id,level,gold,silver,food,wood,iron,created_at) values(?,?,?,?,?,?,?,?,?,?,?)",
                    (user_id, f"R{user_id[1:]}", f"君主{username}", DEFAULT_SERVER_ID, 1, 9999, 100000, 100000, 100000, 100000, now_ms()))
        con.commit()
        row = cur.execute("select * from accounts where username=?", (username,)).fetchone()
    con.close()
    return dict(row)


def make_session(username: str, user_id: str) -> str:
    sess = secrets.token_hex(16)
    con = db(); cur = con.cursor()
    cur.execute("insert into sessions(session,username,user_id,created_at,last_seen) values(?,?,?,?,?)", (sess, username, user_id, now_ms(), now_ms()))
    con.commit(); con.close()
    return sess


def session_info(sess: str | None) -> dict | None:
    if not sess: return None
    con = db(); cur = con.cursor()
    row = cur.execute("select * from sessions where session=?", (sess,)).fetchone()
    if row:
        cur.execute("update sessions set last_seen=? where session=?", (now_ms(), sess)); con.commit()
    con.close()
    return dict(row) if row else None


def role_for_user(user_id: str) -> dict:
    con = db(); row = con.execute("select * from roles where user_id=?", (user_id,)).fetchone(); con.close()
    return dict(row) if row else {}


def ykv(**kwargs) -> str:
    """Return old-client-friendly Y,Y separated key-value text."""
    return "Y,Y".join(f"{k}={v}" for k, v in kwargs.items())


def json_bytes(obj: dict, code: int = 0, message: str = "ok") -> bytes:
    payload = {"code": code, "result": code == 0, "message": message, **obj}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "DiwangStub/0.1"

    def log_request_line(self, body: bytes = b"") -> None:
        LOGS.mkdir(exist_ok=True)
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "client": self.client_address[0],
            "method": self.command,
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body_preview": body[:2048].decode("utf-8", "replace"),
        }
        with open(LOGS / "requests.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def do_GET(self):
        self.dispatch(b"")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.dispatch(body)

    def send_bytes(self, data: bytes, content_type: str = "text/plain; charset=utf-8", status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj: dict, status: int = 200, code: int = 0, message: str = "ok"):
        self.send_bytes(json_bytes(obj, code, message), "application/json; charset=utf-8", status)

    def params(self, parsed, body: bytes) -> dict:
        q = parse_qs(parsed.query, keep_blank_values=True)
        if body:
            ctype = self.headers.get("Content-Type", "")
            if "application/x-www-form-urlencoded" in ctype or b"=" in body:
                try:
                    for k, v in parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True).items():
                        q.setdefault(k, []).extend(v)
                except Exception:
                    pass
        return {k: v[-1] if v else "" for k, v in q.items()}

    def static_file(self, parsed) -> bool:
        raw = unquote(parsed.path)
        aliases = []
        # APK config/resource strings include several possible prefixes; map them to extracted assets.
        if raw.startswith("/game/"):
            aliases.append(PUBLIC / raw.lstrip("/"))
        if raw.startswith("/Y/game/"):
            aliases.append(PUBLIC / raw[len("/Y/"):].lstrip("/"))
        if raw.startswith("/res/"):
            aliases.append(PUBLIC / raw.lstrip("/"))
        if raw in ("/", "/index.html"):
            data = self.index_page().encode("utf-8")
            self.send_bytes(data, "text/html; charset=utf-8")
            return True
        for path in aliases:
            if path.is_dir():
                listing = "\n".join(p.name for p in sorted(path.iterdir()))
                self.send_bytes(listing.encode("utf-8"))
                return True
            if path.is_file():
                ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                self.send_bytes(path.read_bytes(), ctype)
                return True
        return False

    def index_page(self) -> str:
        return f"""<!doctype html><meta charset=utf-8><title>Diwang Stub</title>
<h1>三国·帝王联盟 本地兼容服务端</h1>
<ul>
<li><a href='/client.action?channel={DEFAULT_CHANNEL}'>/client.action</a></li>
<li><a href='/type/list.action?clientType=android'>/type/list.action</a></li>
<li><a href='/area/list.action?session=debug'>/area/list.action</a></li>
<li><a href='/game/res/'>/game/res/</a></li>
<li><a href='/game/script/'>/game/script/</a></li>
</ul>
<p>请求日志：logs/requests.jsonl</p>"""

    def dispatch(self, body: bytes):
        self.log_request_line(body)
        parsed = urlparse(self.path)
        path = parsed.path
        p = self.params(parsed, body)
        if self.static_file(parsed):
            return

        # --- Config/gateway/bootstrap endpoints recovered from APK strings ---
        if path.endswith("/client.action") or path == "/client.action":
            # Old config-like response visible in DEX strings.
            host = self.headers.get("Host", f"127.0.0.1:{self.server.server_port}")
            text = ykv(
                gbServerUrl=f"http://{host}/game/access",
                gbResUrl=f"http://{host}/Y/game/res/Y/game/script/Y/game/dynamics/Y",
                gbServerVer="1311201",
                gbLowestVer="1311104",
                gbServerStatus="3",
                gbChannel=p.get("channel", DEFAULT_CHANNEL),
                gbPassportUrl=f"http://{host}/",
                gbChargeUrl=f"http://{host}/",
                gbSign="localstub",
                version=DEFAULT_VERSION,
                resVersion=DEFAULT_RES_VERSION,
            )
            self.send_bytes(text.encode("utf-8")); return

        if path.endswith("/gateway/access-url.action") or path == "/gateway/access-url.action":
            host = self.headers.get("Host", f"127.0.0.1:{self.server.server_port}")
            self.send_json({"accessUrl": f"http://{host}/", "passportUrl": f"http://{host}/", "chargeUrl": f"http://{host}/"}); return

        if path.endswith("/type/list.action") or path == "/type/list.action":
            self.send_json({"types":[{"typeId":"default","name":"默认分组","status":3}], "serverTime": now_ms()}); return

        if path.endswith("/area/list.action") or path == "/area/list.action":
            self.send_json({"areas":[{"areaId":DEFAULT_SERVER_ID,"serverId":DEFAULT_SERVER_ID,"name":DEFAULT_SERVER_NAME,"status":3,"host":"127.0.0.1","port":25511,"recommend":True}]}); return

        if path.endswith("/area/type.action") or path == "/area/type.action":
            self.send_json({"areaType":"normal","areaId":DEFAULT_SERVER_ID,"name":DEFAULT_SERVER_NAME}); return

        # --- User/passport endpoints recovered from APK strings ---
        if path.endswith("/user/register.action") or path == "/user/register.action":
            username = p.get("username") or p.get("email") or p.get("account") or f"guest{secrets.randbelow(999999)}"
            password = p.get("password") or p.get("pwd") or "123456"
            acct = get_or_create_account(username, password)
            sess = make_session(acct["username"], acct["user_id"])
            self.send_json({"session": sess, "userId": acct["user_id"], "username": acct["username"]}); return

        if path.endswith("/user/validate.action") or path == "/user/validate.action":
            # Validate session if present; otherwise accept username/password in recovery mode.
            sess = p.get("session")
            si = session_info(sess)
            if si:
                self.send_json({"session": sess, "userId": si["user_id"], "username": si["username"], "valid": True}); return
            username = p.get("username") or p.get("email") or p.get("account") or "guest"
            password = p.get("password") or p.get("pwd") or ""
            acct = get_or_create_account(username, password)
            sess = make_session(acct["username"], acct["user_id"])
            self.send_json({"session": sess, "userId": acct["user_id"], "username": acct["username"], "valid": True}); return

        if path.endswith("/user/password.action") or path.endswith("/user/reset-password.action"):
            self.send_json({"changed": True, "note": "stub accepts password reset locally only"}); return

        if path.endswith("/user/logouts.action") or path == "/user/logouts.action":
            self.send_json({"logout": True}); return

        if "captcha" in path.lower() or "verificationcode" in path.lower() or "validateInfo" in path:
            self.send_json({"captchaRequired": False, "captcha":"0000", "validate": True}); return

        # --- Game enter/role endpoints recovered from APK strings ---
        if path.endswith("/game/activate.action") or path.endswith("/game/activate-twice.action") or path.endswith("/game/arrival.action") or path.endswith("/game/loading.action"):
            self.send_json({"activated": True, "channel": p.get("channel") or p.get("channelCode") or DEFAULT_CHANNEL}); return

        if path.endswith("/game/role.action") or path == "/game/role.action":
            si = session_info(p.get("session"))
            if not si:
                # Provide a default role to let protocol exploration continue.
                acct = get_or_create_account(p.get("username") or "guest", p.get("password") or "")
                si = {"user_id": acct["user_id"], "username": acct["username"]}
            role = role_for_user(si["user_id"])
            self.send_json({"roles":[role], "currentRole": role}); return

        if path.endswith("/game/enter.action") or path == "/game/enter.action" or path == "/area/enter.action":
            si = session_info(p.get("session"))
            if not si:
                acct = get_or_create_account(p.get("username") or "guest", p.get("password") or "")
                sess = make_session(acct["username"], acct["user_id"])
                si = {"session": sess, "user_id": acct["user_id"], "username": acct["username"]}
            role = role_for_user(si["user_id"])
            # Include both JSON fields and old config string inside payload for compatibility experiments.
            self.send_json({
                "session": p.get("session") or si.get("session"),
                "serverId": DEFAULT_SERVER_ID,
                "serverName": DEFAULT_SERVER_NAME,
                "host": "127.0.0.1",
                "port": 25511,
                "role": role,
                "enterInfo": ykv(gbSession=p.get("session") or si.get("session"), gbUserId=si["user_id"], gbServerId=DEFAULT_SERVER_ID, gbServerName=quote(DEFAULT_SERVER_NAME), gbServerUrl="http://127.0.0.1:25511")
            }); return

        # --- Bulletin/device/realname/activity endpoints ---
        if "/bulletin/" in path:
            if path.endswith("read.action"):
                self.send_json({"bulletinId": p.get("bulletinId","1"), "title":"本地公告", "content":"本地恢复服务器已启动。"}); return
            self.send_json({"bulletins":[{"bulletinId":"1","title":"本地公告","summary":"本地恢复服务器已启动。"}]}); return

        if "/device/" in path:
            self.send_json({"saved": True}); return
        if "/realname/" in path:
            self.send_json({"enabled": False, "required": False}); return
        if "/activity/" in path:
            self.send_json({"saved": True}); return

        # --- Charge endpoints: local stub only, no real payment ---
        if "/charge/" in path or "/asset/charge/" in path or path.startswith("/mol/charge/"):
            self.send_json({"orderId": f"LOCAL{now_ms()}", "status":"stub", "payUrl":"", "items":[{"id":"gold_8","name":"8黄金包","gold":8,"price":0}], "note":"local stub only; no real payment"}); return

        # --- Generic list/get fallback for script-driven UI exploration ---
        if path.endswith("/list.action") or path.endswith("/get.action"):
            self.send_json({"items": [], "path": p.get("path", ""), "serverTime": now_ms()}); return

        self.send_json({"path": path, "query": p, "note": "unimplemented endpoint logged; add a route after observing client expectation"}, status=200, code=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8080)
    args = ap.parse_args()
    ensure_db()
    LOGS.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Diwang stub server listening on http://{args.host}:{args.port}")
    print(f"Request log: {LOGS / 'requests.jsonl'}")
    httpd.serve_forever()

if __name__ == '__main__':
    main()

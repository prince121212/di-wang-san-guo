#!/usr/bin/env python3
"""Computer-side collaborative map server for Android integration testing."""

from __future__ import annotations

import argparse
import json
import os
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class Store:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.revisions: dict[tuple[str, str], int] = {}
        self.targets: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
        self.data_file: Path | None = None

    def configure_persistence(self, data_file: str) -> None:
        path = Path(data_file).expanduser()
        with self.lock:
            self.data_file = path
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            self.revisions = {
                tuple(key.split("\t", 1)): int(value)
                for key, value in (data.get("revisions") or {}).items()
                if "\t" in key
            }
            self.targets = {
                tuple(key.split("\t", 1)): {
                    int(target_id): dict(target)
                    for target_id, target in bucket.items()
                }
                for key, bucket in (data.get("targets") or {}).items()
                if "\t" in key and isinstance(bucket, dict)
            }

    def _persist_locked(self) -> None:
        if self.data_file is None:
            return
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "revisions": {
                "\t".join(key): value
                for key, value in self.revisions.items()
            },
            "targets": {
                "\t".join(key): {
                    str(target_id): target
                    for target_id, target in bucket.items()
                }
                for key, bucket in self.targets.items()
            },
        }
        temp = self.data_file.with_suffix(self.data_file.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp, self.data_file)

    def upload(self, body: dict[str, Any]) -> dict[str, Any]:
        server_id, kind = str(body["serverId"]), str(body["kind"])
        key = (server_id, kind)
        observations = body.get("observations") or []
        with self.lock:
            revision = self.revisions.get(key, 0) + 1
            self.revisions[key] = revision
            bucket = self.targets.setdefault(key, {})
            for item in observations:
                target = dict(item)
                target_id = int(target["targetId"])
                previous = bucket.get(target_id) or {}
                target["raw"] = {
                    **(previous.get("raw") or {}),
                    **(target.get("raw") or {}),
                }
                contributors = list(previous.get("contributorDeviceIds") or [])
                device_id = str(body.get("_deviceId") or "")
                if device_id and device_id not in contributors:
                    contributors.append(device_id)
                target["contributorDeviceIds"] = contributors[-100:]
                target["deviceLastSeen"] = device_id
                target.pop("_expeditionStatus", None)
                target.pop("_expeditionResult", None)
                bucket[target_id] = target
            self._persist_locked()
            return {
                "accepted": len(observations),
                "serverRevision": f"{server_id}-{kind.lower()}-{revision}",
                "clientBatchId": body["clientBatchId"],
            }

    def recommend(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        server_id, kind = str(body["serverId"]), str(body["kind"])
        key = (server_id, kind)
        with self.lock:
            revision = self.revisions.get(key, 0)
            current = f"{server_id}-{kind.lower()}-{revision}"
            if body.get("acceptedRevision") != current:
                return 409, {
                    "code": "REVISION_CONFLICT",
                    "message": "acceptedRevision is no longer current",
                }
            candidates = [
                item for item in self.targets.get(key, {}).values()
                if item.get("_expeditionStatus") != "unavailable"
            ]
            target_type = body.get("targetType")
            allowed = set(body.get("allowedMineTypes") or [])
            if target_type:
                candidates = [it for it in candidates if it.get("targetType") == target_type]
            if allowed:
                candidates = [it for it in candidates if it.get("targetType") in allowed]
            if not candidates:
                return 200, {"target": None}
            start = body.get("start") or {}
            sx, sy = int(start.get("x", 0)), int(start.get("y", 0))
            chosen = min(
                candidates,
                key=lambda it: (int(it.get("x", 0)) - sx) ** 2
                + (int(it.get("y", 0)) - sy) ** 2,
            )
            return 200, {
                "target": {
                    "targetId": chosen["targetId"],
                    "x": chosen["x"],
                    "y": chosen["y"],
                    "targetType": chosen["targetType"],
                    "level": chosen.get("level"),
                    "serverRevision": current,
                    "raw": chosen.get("raw") or {},
                }
            }

    def report_result(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        server_id, kind = str(body["serverId"]), str(body["kind"])
        target_id = int(body["targetId"])
        key = (server_id, kind)
        with self.lock:
            revision = self.revisions.get(key, 0)
            current = f"{server_id}-{kind.lower()}-{revision}"
            accepted_revision = str(body.get("acceptedRevision") or "")
            prefix = f"{server_id}-{kind.lower()}-"
            try:
                accepted_number = int(accepted_revision.removeprefix(prefix))
            except ValueError:
                accepted_number = -1
            if not accepted_revision.startswith(prefix) or accepted_number < 0 or accepted_number > revision:
                return 409, {
                    "code": "REVISION_CONFLICT",
                    "message": "acceptedRevision does not belong to a valid map snapshot",
                }
            target = self.targets.get(key, {}).get(target_id)
            if target is None:
                return 404, {
                    "code": "TARGET_NOT_FOUND",
                    "message": "reported target is not in current map",
                }
            result_id = str(
                body.get("clientResultId")
                or (
                    f"{body.get('_deviceId', '')}-{body.get('accountId', '')}-"
                    f"{kind}-{target_id}-{accepted_revision}"
                )
            )
            previous_result = target.get("_expeditionResult") or {}
            if previous_result.get("clientResultId") == result_id:
                return 200, {
                    "accepted": True,
                    "serverRevision": previous_result["serverRevision"],
                    "targetId": target_id,
                }
            revision += 1
            self.revisions[key] = revision
            result_revision = f"{server_id}-{kind.lower()}-{revision}"
            target["_expeditionStatus"] = "unavailable"
            target["_expeditionResult"] = {
                "clientResultId": result_id,
                "serverRevision": result_revision,
                "success": body.get("success") is True,
                "message": str(body.get("message") or ""),
                "reportedAtMillis": int(body.get("reportedAtMillis") or 0),
                "deviceId": body.get("_deviceId", ""),
                "raw": body.get("raw") or {},
            }
            self._persist_locked()
            return 200, {
                "accepted": True,
                "serverRevision": result_revision,
                "targetId": target_id,
            }


STORE = Store()


class Handler(BaseHTTPRequestHandler):
    server_version = "DwpmCloudMapMock/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.reply(200, {"status": "ok", "service": "dwpm-cloud-map-mock"})
        else:
            self.reply(404, {"code": "NOT_FOUND", "message": "route not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.authorized():
            self.reply(401, {"code": "UNAUTHORIZED", "message": "invalid bearer token"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            body["_deviceId"] = self.headers.get("X-Device-Id", "")
            if self.path == "/v1/map/observations":
                self.reply(200, STORE.upload(body))
            elif self.path == "/v1/map/recommendations":
                status, response = STORE.recommend(body)
                self.reply(status, response)
            elif self.path == "/v1/map/results":
                status, response = STORE.report_result(body)
                self.reply(status, response)
            else:
                self.reply(404, {"code": "NOT_FOUND", "message": "route not found"})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.reply(400, {"code": "BAD_REQUEST", "message": str(error)})

    def authorized(self) -> bool:
        expected = os.environ.get("CLOUD_MAP_TOKEN", "")
        return not expected or self.headers.get("Authorization") == f"Bearer {expected}"

    def reply(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.client_address[0]} {fmt % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument(
        "--data-file",
        default=os.environ.get(
            "CLOUD_MAP_DATA_FILE",
            "~/.dwpm-cloud-map/store.json",
        ),
        help="durable collaborative map JSON store",
    )
    args = parser.parse_args()
    STORE.configure_persistence(args.data_file)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"cloud map service listening on http://{args.host}:{args.port}; "
        f"data={Path(args.data_file).expanduser()}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()

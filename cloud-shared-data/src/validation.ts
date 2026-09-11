import type {
  CloudPolicy,
  Env,
  MapKind,
  RegionObservation,
  TargetObservation,
} from "./types";

export class RequestError extends Error {
  constructor(
    message: string,
    readonly status = 400,
    readonly code = "INVALID_REQUEST",
  ) {
    super(message);
  }
}

export function objectValue(value: unknown, label = "请求体"): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new RequestError(`${label}必须是对象`);
  }
  return value as Record<string, unknown>;
}

export function textValue(
  value: unknown,
  label: string,
  maxLength = 240,
): string {
  const text = String(value ?? "").trim();
  if (!text) throw new RequestError(`${label}不能为空`);
  if (text.length > maxLength) throw new RequestError(`${label}过长`);
  return text;
}

export function anonymousIdValue(value: unknown, label: string): string {
  const id = textValue(value, label, 64).toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(id)) {
    throw new RequestError(`${label}必须是 SHA-256 匿名哈希`);
  }
  return id;
}

export function optionalText(value: unknown, maxLength = 500): string {
  return String(value ?? "").trim().slice(0, maxLength);
}

export function integerValue(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new RequestError(`${label}无效`);
  }
  return parsed;
}

export function mapKindValue(value: unknown): MapKind {
  const kind = textValue(value, "地图类型", 20).toLowerCase();
  if (kind !== "bandit" && kind !== "mine") {
    throw new RequestError("地图类型仅支持 bandit 或 mine");
  }
  return kind;
}

export function stringArray(value: unknown, label: string, maximum = 100): string[] {
  if (!Array.isArray(value) || value.length > maximum) {
    throw new RequestError(`${label}必须是数组且数量不超过${maximum}`);
  }
  return [...new Set(value.map((item) => textValue(item, label, 240)))];
}

export function policy(env: Env): CloudPolicy {
  const number = (
    name:
      | "SHARED_ACCOUNT_THRESHOLD"
      | "PRESENCE_TTL_MILLIS"
      | "SCAN_FRESH_MILLIS"
      | "SCAN_LEASE_MILLIS"
      | "TARGET_LEASE_MILLIS"
      | "REJECT_RETRY_MILLIS",
    fallback: number,
  ): number => {
    const raw = env[name];
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback;
  };
  return {
    threshold: Math.max(2, number("SHARED_ACCOUNT_THRESHOLD", 2)),
    presenceTtlMillis: number("PRESENCE_TTL_MILLIS", 90_000),
    scanFreshMillis: number("SCAN_FRESH_MILLIS", 120_000),
    scanLeaseMillis: number("SCAN_LEASE_MILLIS", 45_000),
    targetLeaseMillis: number("TARGET_LEASE_MILLIS", 600_000),
    rejectRetryMillis: number("REJECT_RETRY_MILLIS", 120_000),
  };
}

function optionalInteger(
  value: unknown,
  label: string,
  minimum = 0,
  maximum = 2_147_483_647,
): number | undefined {
  if (value == null || value === "") return undefined;
  return integerValue(value, label, minimum, maximum);
}

function optionalBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function boundedIntegerArray(
  value: unknown,
  label: string,
  maximum = 64,
): number[] | undefined {
  if (value == null) return undefined;
  if (!Array.isArray(value) || value.length > maximum) {
    throw new RequestError(`${label}必须是数组且数量不超过${maximum}`);
  }
  return value.map((item) => integerValue(item, label, 0, 2_147_483_647));
}

function boundedTextArray(
  value: unknown,
  label: string,
  maximum = 32,
): string[] | undefined {
  if (value == null) return undefined;
  if (!Array.isArray(value) || value.length > maximum) {
    throw new RequestError(`${label}必须是数组且数量不超过${maximum}`);
  }
  return [...new Set(value.map((item) => textValue(item, label, 80)))];
}

function setIfDefined(
  output: Record<string, unknown>,
  key: string,
  value: unknown,
): void {
  if (value !== undefined && value !== "") output[key] = value;
}

/**
 * Projects client input onto a closed list of public map fields. Unknown keys
 * are deliberately discarded so credentials, sessions, settings, ledgers and
 * raw protocol payloads cannot be persisted by this service.
 */
function normalizedTargetData(
  mapKind: MapKind,
  value: unknown,
): Record<string, unknown> {
  const row = objectValue(value ?? {}, "目标数据");
  const output: Record<string, unknown> = {};
  const text = (key: string, maximum = 300) => {
    const value = optionalText(row[key], maximum);
    setIfDefined(output, key, value);
  };
  const integer = (
    key: string,
    minimum = 0,
    maximum = Number.MAX_SAFE_INTEGER,
  ) => {
    setIfDefined(output, key, optionalInteger(row[key], key, minimum, maximum));
  };
  const boolean = (key: string) => {
    setIfDefined(output, key, optionalBoolean(row[key]));
  };

  if (mapKind === "bandit") {
    for (const key of ["name", "kind", "resource", "rewardDescription"]) text(key);
    text("compositionCode", 120);
    setIfDefined(
      output,
      "dropCategories",
      boundedTextArray(row.dropCategories, "掉落分类", 16),
    );
    setIfDefined(output, "lootIds", boundedIntegerArray(row.lootIds, "掉落 ID"));
    setIfDefined(output, "unitTypes", boundedIntegerArray(row.unitTypes, "兵种代码"));
    if (row.composition != null) {
      const composition = objectValue(row.composition, "兵种构成");
      output.composition = Object.fromEntries(
        ["foot", "bow", "cavalry", "chariot"].map((key) => [
          key,
          optionalInteger(composition[key], `兵种构成 ${key}`, 0, 1_000_000_000) ?? 0,
        ]),
      );
      if (composition.source === "8540-units") {
        (output.composition as Record<string, unknown>).source = "8540-units";
      }
    }
  } else {
    for (const key of [
      "name", "kind", "protocolKind", "ownerName", "ownerCountry", "description",
    ]) text(key);
    for (const key of [
      "businessId", "typeCode", "rank", "detailFlag", "defenderCount",
    ]) integer(key);
    for (const key of [
      "amountA", "amountB", "storage", "productionPerHour", "valueJ", "valueK",
    ]) integer(key, -2_147_483_648, 2_147_483_647);
    for (const key of [
      "playerOccupied", "unoccupiedByPlayer", "isEmpty", "occupied", "hasDefenders",
    ]) boolean(key);
  }
  return output;
}

function targetObservation(value: unknown, mapKind: MapKind): TargetObservation {
  const row = objectValue(value, "地图目标");
  const data = normalizedTargetData(mapKind, row.data);
  const encoded = JSON.stringify(data);
  if (encoded.length > 16_384) throw new RequestError("单个目标数据过大");
  const level = row.level == null ? null : integerValue(row.level, "目标等级", 0, 999);
  return {
    targetId: textValue(row.targetId, "目标 ID", 160),
    x: integerValue(row.x, "目标 X 坐标", 0, 100_000),
    y: integerValue(row.y, "目标 Y 坐标", 0, 100_000),
    type: optionalText(row.type, 120),
    level,
    data,
  };
}

export function regionObservations(
  value: unknown,
  mapKind: MapKind,
): RegionObservation[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 20) {
    throw new RequestError("区域观察必须包含1到20个坐标");
  }
  let targetCount = 0;
  const regions = value.map((item) => {
    const row = objectValue(item, "区域观察");
    if (!Array.isArray(row.targets) || row.targets.length > 500) {
      throw new RequestError("区域目标必须是数组且数量不超过500");
    }
    targetCount += row.targets.length;
    return {
      x: integerValue(row.x, "扫描 X 坐标", 0, 100_000),
      y: integerValue(row.y, "扫描 Y 坐标", 0, 100_000),
      leaseToken: optionalText(row.leaseToken, 160),
      targets: row.targets.map((target) => targetObservation(target, mapKind)),
    };
  });
  if (targetCount > 1_000) throw new RequestError("单次观察的目标总数不能超过1000");
  return regions;
}

export function publicHttpUrl(value: unknown): string {
  const raw = optionalText(value, 500);
  if (!raw) return "";
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "";
    url.username = "";
    url.password = "";
    url.search = "";
    url.hash = "";
    return url.toString().slice(0, 500);
  } catch {
    return "";
  }
}

export interface PublicDirectoryArea {
  serverKey: string;
  areaId: string;
  areaName: string;
  target: string;
  gameHttp: string;
}

/**
 * Validate and project a complete public platform directory.  The directory
 * endpoint is deliberately stricter than map observations: it accepts only
 * fields that can be shown to every client and never accepts credentials,
 * sessions, or arbitrary source payloads.
 */
export function directoryAreas(value: unknown): PublicDirectoryArea[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 1_000) {
    throw new RequestError("区服目录必须是1到1000项的数组");
  }
  const byServer = new Map<string, PublicDirectoryArea>();
  value.forEach((item, index) => {
    const row = objectValue(item, `区服目录第${index + 1}项`);
    const serverKey = textValue(row.serverKey, "区服键", 240);
    const areaName = textValue(row.areaName, "区服名称", 160);
    const areaId = optionalText(row.areaId, 80);
    const target = optionalText(row.target, 80);
    const gameHttp = publicHttpUrl(row.gameHttp);
    const existing = byServer.get(serverKey);
    if (!existing) {
      byServer.set(serverKey, { serverKey, areaId, areaName, target, gameHttp });
      return;
    }
    // A passport response can list the same server for multiple channels.
    // Keep one identity and merge its public target/channel labels.
    const targets = new Set(existing.target.split(",").filter(Boolean));
    target.split(",").map((part) => part.trim()).filter(Boolean).forEach((part) => targets.add(part));
    existing.target = [...targets].join(",");
    if (!existing.areaId && areaId) existing.areaId = areaId;
    if (!existing.gameHttp && gameHttp) existing.gameHttp = gameHttp;
  });
  return [...byServer.values()].sort((left, right) =>
    left.serverKey.localeCompare(right.serverKey, "en", { numeric: true })
    || left.areaName.localeCompare(right.areaName, "zh-CN")
  );
}

export interface Env {
  DB: D1Database;
  ASSETS?: Fetcher;
  CLIENT_API_TOKEN: string;
  ADMIN_USERNAME?: string;
  ADMIN_PASSWORD?: string;
  ADMIN_SESSION_SECRET?: string;
  SHARED_ACCOUNT_THRESHOLD?: string;
  PRESENCE_TTL_MILLIS?: string;
  SCAN_FRESH_MILLIS?: string;
  SCAN_LEASE_MILLIS?: string;
  TARGET_LEASE_MILLIS?: string;
  REJECT_RETRY_MILLIS?: string;
}

export type MapKind = "bandit" | "mine";

export interface CloudPolicy {
  threshold: number;
  presenceTtlMillis: number;
  scanFreshMillis: number;
  scanLeaseMillis: number;
  targetLeaseMillis: number;
  rejectRetryMillis: number;
}

export interface SharedMode {
  mode: "LOCAL_ONLY" | "CLOUD_SHARED";
  onlineAccountCount: number;
  threshold: number;
  serverTimeMillis: number;
}

export interface SharedModeCheck extends SharedMode {
  requesterPresent: boolean;
}

export interface TargetObservation {
  targetId: string;
  x: number;
  y: number;
  type?: string;
  level?: number | null;
  data: Record<string, unknown>;
}

export interface RegionObservation {
  x: number;
  y: number;
  leaseToken?: string;
  targets: TargetObservation[];
}

export interface RequestIdentity {
  platformKey: string;
  serverKey: string;
  serverScope: string;
  actorId: string;
}

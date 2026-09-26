export interface Env {
  DB: D1Database;
  RUNTIME_CONFIG: DurableObjectNamespace;
  ASSETS?: Fetcher;
  CLIENT_API_TOKEN: string;
  CLIENT_API_TOKEN_V2?: string;
  ADMIN_USERNAME?: string;
  ADMIN_PASSWORD?: string;
  ADMIN_SESSION_SECRET?: string;
  RESEND_API_KEY?: string;
  RESEND_FROM_EMAIL?: string;
  EMAIL_PROBE_TOKEN?: string;
  EMAIL_PROBE_TO?: string;
  EMAIL_PROBE_UNTIL?: string;
  MEMBER_AUTH_SECRET?: string;
  MEMBER_LEASE_PRIVATE_KEY?: string;
  MEMBER_LEASE_PUBLIC_KEY?: string;
  MEMBER_EMAIL_DAILY_LIMIT?: string;
  ALIPAY_MODE?: string;
  ALIPAY_ENABLED?: string;
  ALIPAY_APP_PAY_ENABLED?: string;
  ALIPAY_LIVE_APPROVED?: string;
  ALIPAY_APP_ID?: string;
  ALIPAY_PRIVATE_KEY?: string;
  ALIPAY_PUBLIC_KEY?: string;
  ALIPAY_SELLER_ID?: string;
  ALIPAY_ORIGIN?: string;
  ALIPAY_PLAN_PRICES?: string;
  ALIPAY_ACCEPTANCE_MEMBER_ID?: string;
  ALIPAY_ACCEPTANCE_PURCHASE_ID?: string;
  ALIPAY_ACCEPTANCE_UNTIL?: string;
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

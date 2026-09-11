import type {
  CloudPolicy,
  MapKind,
  RegionObservation,
  SharedModeCheck,
} from "./types";

const BANDIT_TARGET_TTL_MILLIS = 30 * 60 * 1000;
const MINE_TARGET_TTL_MILLIS = 3 * 60 * 60 * 1000;

export async function cleanup(
  db: D1Database,
  now: number,
  policy: CloudPolicy,
): Promise<void> {
  await db.batch([
    db.prepare("DELETE FROM presence WHERE last_seen_at < ?")
      .bind(now - policy.presenceTtlMillis),
    db.prepare("DELETE FROM map_scan_leases WHERE lease_until <= ?").bind(now),
    db.prepare("DELETE FROM admin_login_attempts WHERE last_attempt_at < ?")
      .bind(now - 24 * 60 * 60 * 1000),
    db.prepare(
      `UPDATE map_targets
       SET status='available', reserved_by='', reservation_token='', lease_until=0,
           status_reason='', status_at=?
       WHERE status='reserved' AND lease_until<=?`,
    ).bind(now, now),
    db.prepare(
      `UPDATE map_targets
       SET status='uncertain', status_reason='dispatch lease expired', status_at=?
       WHERE status='dispatching' AND lease_until<=?`,
    ).bind(now, now),
    db.prepare(
      `UPDATE map_targets
       SET status='available', retry_after=0, status_reason='', status_at=?
       WHERE status='rejected' AND retry_after<=?`,
    ).bind(now, now),
    db.prepare(
      `DELETE FROM map_targets
       WHERE (map_kind='bandit' AND last_seen_at<?)
          OR (map_kind='mine' AND last_seen_at<?)`,
    ).bind(now - BANDIT_TARGET_TTL_MILLIS, now - MINE_TARGET_TTL_MILLIS),
    db.prepare(
      `DELETE FROM map_regions
       WHERE (map_kind='bandit' AND scanned_at<?)
          OR (map_kind='mine' AND scanned_at<?)`,
    ).bind(now - BANDIT_TARGET_TTL_MILLIS, now - MINE_TARGET_TTL_MILLIS),
    db.prepare(
      `DELETE FROM map_targets
       WHERE status NOT IN ('reserved','dispatching')
         AND NOT EXISTS (
           SELECT 1 FROM map_target_regions relation
           WHERE relation.server_key=map_targets.server_key
             AND relation.map_kind=map_targets.map_kind
             AND relation.target_id=map_targets.target_id
         )`,
    ),
  ]);
}

export async function sharedMode(
  db: D1Database,
  serverKey: string,
  actorId: string,
  now: number,
  policy: CloudPolicy,
): Promise<SharedModeCheck> {
  const row = await db.prepare(
    `SELECT COUNT(DISTINCT actor_id) AS count,
            MAX(CASE WHEN actor_id=? THEN 1 ELSE 0 END) AS requester_present
     FROM presence WHERE server_key=? AND last_seen_at>=?`,
  ).bind(actorId, serverKey, now - policy.presenceTtlMillis).first<{
    count: number;
    requester_present: number;
  }>();
  const count = Number(row?.count ?? 0);
  return {
    mode: count >= policy.threshold ? "CLOUD_SHARED" : "LOCAL_ONLY",
    onlineAccountCount: count,
    threshold: policy.threshold,
    serverTimeMillis: now,
    requesterPresent: Number(row?.requester_present ?? 0) === 1,
  };
}

export async function observeRegions(
  db: D1Database,
  serverKey: string,
  mapKind: MapKind,
  actorId: string,
  regions: RegionObservation[],
  now: number,
): Promise<void> {
  // One scan may contain hundreds of targets. Feeding validated JSON through
  // SQLite's json_each keeps the D1 write count constant instead of issuing
  // two statements per target.
  const encoded = JSON.stringify(regions);
  await db.batch([
    db.prepare(
      `INSERT INTO map_regions(
         server_key,map_kind,scan_x,scan_y,scanned_at,observer_id
       )
       SELECT ?,?,
              CAST(json_extract(region.value,'$.x') AS INTEGER),
              CAST(json_extract(region.value,'$.y') AS INTEGER),
              ?,?
       FROM json_each(?) AS region
       WHERE 1
       ON CONFLICT(server_key,map_kind,scan_x,scan_y) DO UPDATE SET
         scanned_at=excluded.scanned_at, observer_id=excluded.observer_id`,
    ).bind(serverKey, mapKind, now, actorId, encoded),
    db.prepare(
      `INSERT INTO map_targets(
         server_key,map_kind,target_id,x,y,target_type,level,data_json,last_seen_at
       )
       SELECT ?,?,
              CAST(json_extract(target.value,'$.targetId') AS TEXT),
              CAST(json_extract(target.value,'$.x') AS INTEGER),
              CAST(json_extract(target.value,'$.y') AS INTEGER),
              COALESCE(CAST(json_extract(target.value,'$.type') AS TEXT),''),
              CASE WHEN json_type(target.value,'$.level') IN ('integer','real')
                   THEN CAST(json_extract(target.value,'$.level') AS INTEGER)
                   ELSE NULL END,
              json(json_extract(target.value,'$.data')),
              ?
       FROM json_each(?) AS region
       JOIN json_each(json_extract(region.value,'$.targets')) AS target
       WHERE 1
       ON CONFLICT(server_key,map_kind,target_id) DO UPDATE SET
         x=excluded.x, y=excluded.y, target_type=excluded.target_type,
         level=excluded.level, data_json=excluded.data_json,
         last_seen_at=MAX(map_targets.last_seen_at, excluded.last_seen_at),
         status=CASE
           WHEN map_targets.status='missing' THEN 'available'
           WHEN map_targets.status='uncertain' AND map_targets.lease_until<=?
             THEN 'available'
           ELSE map_targets.status
         END,
         reserved_by=CASE
           WHEN map_targets.status='missing'
             OR (map_targets.status='uncertain' AND map_targets.lease_until<=?)
             THEN '' ELSE map_targets.reserved_by END,
         reservation_token=CASE
           WHEN map_targets.status='missing'
             OR (map_targets.status='uncertain' AND map_targets.lease_until<=?)
             THEN '' ELSE map_targets.reservation_token END,
         lease_until=CASE
           WHEN map_targets.status='missing'
             OR (map_targets.status='uncertain' AND map_targets.lease_until<=?)
             THEN 0 ELSE map_targets.lease_until END`,
    ).bind(serverKey, mapKind, now, encoded, now, now, now, now),
    db.prepare(
      `INSERT INTO map_target_regions(
         server_key,map_kind,target_id,scan_x,scan_y,last_seen_at
       )
       SELECT ?,?,
              CAST(json_extract(target.value,'$.targetId') AS TEXT),
              CAST(json_extract(region.value,'$.x') AS INTEGER),
              CAST(json_extract(region.value,'$.y') AS INTEGER),
              ?
       FROM json_each(?) AS region
       JOIN json_each(json_extract(region.value,'$.targets')) AS target
       WHERE 1
       ON CONFLICT(server_key,map_kind,target_id,scan_x,scan_y) DO UPDATE SET
         last_seen_at=excluded.last_seen_at`,
    ).bind(serverKey, mapKind, now, encoded),
    db.prepare(
      `DELETE FROM map_target_regions
       WHERE server_key=? AND map_kind=?
         AND EXISTS (
           SELECT 1 FROM json_each(?) AS region
           WHERE CAST(json_extract(region.value,'$.x') AS INTEGER)=map_target_regions.scan_x
             AND CAST(json_extract(region.value,'$.y') AS INTEGER)=map_target_regions.scan_y
         )
         AND NOT EXISTS (
           SELECT 1
           FROM json_each(?) AS region
           JOIN json_each(json_extract(region.value,'$.targets')) AS target
           WHERE CAST(json_extract(region.value,'$.x') AS INTEGER)=map_target_regions.scan_x
             AND CAST(json_extract(region.value,'$.y') AS INTEGER)=map_target_regions.scan_y
             AND CAST(json_extract(target.value,'$.targetId') AS TEXT)=map_target_regions.target_id
         )`,
    ).bind(serverKey, mapKind, encoded, encoded),
    db.prepare(
      `DELETE FROM map_scan_leases
       WHERE server_key=? AND map_kind=?
         AND EXISTS (
           SELECT 1 FROM json_each(?) AS region
           WHERE CAST(json_extract(region.value,'$.x') AS INTEGER)=map_scan_leases.scan_x
             AND CAST(json_extract(region.value,'$.y') AS INTEGER)=map_scan_leases.scan_y
             AND CAST(json_extract(region.value,'$.leaseToken') AS TEXT)=map_scan_leases.lease_token
         )`,
    ).bind(serverKey, mapKind, encoded),
    db.prepare(
      `DELETE FROM map_targets
       WHERE server_key=? AND map_kind=?
         AND status NOT IN ('reserved','dispatching')
         AND NOT EXISTS (
           SELECT 1 FROM map_target_regions relation
           WHERE relation.server_key=map_targets.server_key
             AND relation.map_kind=map_targets.map_kind
             AND relation.target_id=map_targets.target_id
         )`,
    ).bind(serverKey, mapKind),
  ]);
}

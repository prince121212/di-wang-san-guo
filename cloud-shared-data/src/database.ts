import type {
  CloudPolicy,
  MapKind,
  RegionObservation,
  SharedModeCheck,
  TargetObservation,
} from "./types";

// v2 retired the per-target alive refresh: death now propagates through
// explicit gone reports, so the TTL only collects rows every observer
// abandoned - it bounds how long stale data lingers, not how fresh live data
// is, and can therefore sit far above the old v1 windows.
export const BANDIT_TARGET_TTL_MILLIS = 6 * 60 * 60 * 1000;
export const MINE_TARGET_TTL_MILLIS = 24 * 60 * 60 * 1000;

export function targetTtlMillis(mapKind: MapKind): number {
  return mapKind === "bandit" ? BANDIT_TARGET_TTL_MILLIS : MINE_TARGET_TTL_MILLIS;
}

// A re-observation of an unchanged target only rewrites its row when the
// stored sighting is older than this.  Every consumer of last_seen_at works
// on TTLs of hours, so a 5-minute refresh granularity changes no decision;
// without it, a phone scanning around the clock rewrites every row it can
// see on every observation, and D1 bills each touched row as a write whether
// or not any value changed.  The legacy regions path keeps this throttle;
// the v2 upserts path does not, because its clients only send real changes.
const OBSERVATION_REFRESH_MILLIS = 5 * 60 * 1000;

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
    // Two sibling sweeps used to sit here - 'reserved' and 'rejected' whose
    // lease or retry window had passed, rewritten to 'available'.  Both were
    // dead work: every reader of a target already decides expiry from the
    // clock, because `queryTargets` and `reserveTarget` both match
    // `status='available' OR (status='reserved' AND lease_until<=now) OR
    // (status='rejected' AND retry_after<=now)`.  They spent a full scan of
    // map_targets each, three times an hour, writing a column into the value
    // every reader was already inferring.
    //
    // This one stays, because it is not inference - it is the only route back.
    // `observeRegions` reopens a target it sees again only from 'missing' or
    // 'uncertain'; an actor that vanished mid-dispatch leaves 'dispatching',
    // which nothing reopens, so without this the target would be unusable
    // until its TTL deleted it.
    db.prepare(
      `UPDATE map_targets
       SET status='uncertain', status_reason='dispatch lease expired',
           status_at=?, changed_at=?
       WHERE status='dispatching' AND lease_until<=?`,
    ).bind(now, now, now),
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
    // A global "no region link" orphan sweep used to run here.  It predates
    // v2, whose upserts never write map_target_regions (links only exist to
    // feed the legacy regions model), so the sweep read "v2 row" as "orphan"
    // and deleted every v2-uploaded target within one cron cycle - a hard
    // delete with no tombstone, so replicas never learned and kept offering
    // the phantoms for reservation.  v1 orphans are still collected by the
    // per-observation cleanup in observeRegions, and anything abandoned by
    // every observer is collected by the TTL sweep above, which replicas
    // apply independently by the same rule.
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
  scanFreshMillis: number,
): Promise<void> {
  // One scan may contain hundreds of targets. Feeding validated JSON through
  // SQLite's json_each keeps the D1 write count constant instead of issuing
  // two statements per target.
  const encoded = JSON.stringify(regions);
  const staleBefore = now - OBSERVATION_REFRESH_MILLIS;
  // A region row exists to tell scanners "this cell was read recently", and
  // the claim window is scanFreshMillis - so the recorded time only needs
  // that granularity.  Rewriting scanned_at on every observation (several a
  // minute while a phone scans around the clock) bought nothing over that.
  // Refreshing only once the recorded scan falls out of the fresh window
  // collapses the write rate; the price is that a re-scan happening inside
  // the window goes unrecorded, so another account may claim the cell up to
  // one window earlier than the true last scan - a duplicate scan, not a
  // correctness issue, and moot once scan coordination moves off the cloud.
  const scanStaleBefore = now - scanFreshMillis;
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
         scanned_at=excluded.scanned_at, observer_id=excluded.observer_id
       WHERE map_regions.scanned_at < ?`,
    ).bind(serverKey, mapKind, now, actorId, encoded, scanStaleBefore),
    // Overlapping scan regions all report the targets they cover, so one
    // target can appear once per region in this payload.  Without the GROUP
    // BY, each appearance is a separate conflict-update of the same row.
    // The grouped rows for one target carry identical data (same sighting),
    // so keeping any one of them loses nothing.
    db.prepare(
      `INSERT INTO map_targets(
         server_key,map_kind,target_id,x,y,target_type,level,data_json,
         last_seen_at,changed_at
       )
       SELECT ?,?, target_id, x, y, target_type, level, data_json, ?, ?
       FROM (
         SELECT
           CAST(json_extract(target.value,'$.targetId') AS TEXT) AS target_id,
           CAST(json_extract(target.value,'$.x') AS INTEGER) AS x,
           CAST(json_extract(target.value,'$.y') AS INTEGER) AS y,
           COALESCE(CAST(json_extract(target.value,'$.type') AS TEXT),'') AS target_type,
           CASE WHEN json_type(target.value,'$.level') IN ('integer','real')
                THEN CAST(json_extract(target.value,'$.level') AS INTEGER)
                ELSE NULL END AS level,
           json(json_extract(target.value,'$.data')) AS data_json
         FROM json_each(?) AS region
         JOIN json_each(json_extract(region.value,'$.targets')) AS target
         GROUP BY target_id
       )
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
             THEN 0 ELSE map_targets.lease_until END,
         -- The change feed replays rows by changed_at, so it must move exactly
         -- when the row is rewritten - which the WHERE below decides, including
         -- the 5-minute sighting throttle.  A refresh skipped by that throttle
         -- must also skip changed_at, or subscribers would re-fetch rows whose
         -- content never moved.
         changed_at=?
       WHERE map_targets.x IS NOT excluded.x
          OR map_targets.y IS NOT excluded.y
          OR map_targets.target_type IS NOT excluded.target_type
          OR map_targets.level IS NOT excluded.level
          OR map_targets.data_json IS NOT excluded.data_json
          OR map_targets.last_seen_at < ?
          OR map_targets.status='missing'
          OR (map_targets.status='uncertain' AND map_targets.lease_until<=?)`,
    ).bind(
      serverKey, mapKind, now, now, encoded,
      now, now, now, now, now, staleBefore, now,
    ),
    db.prepare(
      `INSERT INTO map_target_regions(
         server_key,map_kind,target_id,scan_x,scan_y,last_seen_at
       )
       SELECT ?,?, target_id, scan_x, scan_y, ?
       FROM (
         SELECT
           CAST(json_extract(target.value,'$.targetId') AS TEXT) AS target_id,
           CAST(json_extract(region.value,'$.x') AS INTEGER) AS scan_x,
           CAST(json_extract(region.value,'$.y') AS INTEGER) AS scan_y
         FROM json_each(?) AS region
         JOIN json_each(json_extract(region.value,'$.targets')) AS target
         GROUP BY target_id, scan_x, scan_y
       )
       WHERE 1
       ON CONFLICT(server_key,map_kind,target_id,scan_x,scan_y) DO UPDATE SET
         last_seen_at=excluded.last_seen_at
       WHERE map_target_regions.last_seen_at < ?`,
    ).bind(serverKey, mapKind, now, encoded, staleBefore),
    // A target that has just disappeared from the only region that held it is
    // gone from the map, and must stop being handed out now rather than when
    // its TTL runs out - `queryTargets` filters on last_seen_at, so a bandit
    // somebody killed a minute ago stays on offer for the rest of its 30
    // minutes otherwise.
    //
    // This ran as `DELETE FROM map_targets WHERE server_key=? AND map_kind=?
    // AND NOT EXISTS (<link>)`, which is a sweep over every target the server
    // has (3,414 rows per observation) to find the handful that vanished.  The
    // candidates are knowable without that: they are the targets linked to the
    // regions this scan just re-read.  Driving from json_each seeks those links
    // by index, so the cost follows the scan.  It runs before the link cleanup
    // below because it needs those links to find its candidates.
    db.prepare(
      `DELETE FROM map_targets
       WHERE rowid IN (
         SELECT target.rowid
         FROM json_each(?) AS region
         CROSS JOIN map_target_regions link
           ON link.server_key=?
          AND link.map_kind=?
          AND link.scan_x=CAST(json_extract(region.value,'$.x') AS INTEGER)
          AND link.scan_y=CAST(json_extract(region.value,'$.y') AS INTEGER)
         CROSS JOIN map_targets target
           ON target.server_key=link.server_key
          AND target.map_kind=link.map_kind
          AND target.target_id=link.target_id
         WHERE target.status NOT IN ('reserved','dispatching')
           AND NOT EXISTS (
             SELECT 1
             FROM json_each(?) AS snapshot
             JOIN json_each(json_extract(snapshot.value,'$.targets')) AS seen
             WHERE CAST(json_extract(seen.value,'$.targetId') AS TEXT)=target.target_id
           )
           AND NOT EXISTS (
             SELECT 1 FROM map_target_regions other
             WHERE other.server_key=target.server_key
               AND other.map_kind=target.map_kind
               AND other.target_id=target.target_id
               AND NOT EXISTS (
                 SELECT 1 FROM json_each(?) AS covered
                 WHERE CAST(json_extract(covered.value,'$.x') AS INTEGER)=other.scan_x
                   AND CAST(json_extract(covered.value,'$.y') AS INTEGER)=other.scan_y
               )
           )
       )`,
    ).bind(encoded, serverKey, mapKind, encoded, encoded),
    // Drop the links for targets that were in one of these regions and are no
    // longer in the fresh snapshot of it.
    //
    // The scan just told us exactly which regions it looked at - a handful of
    // rows.  Writing that as `WHERE EXISTS (SELECT 1 FROM json_each ...)` turned
    // that known set into a *predicate*, so SQLite walked every link row the
    // server had and re-scanned the whole payload for each one: 10,040 rows read
    // per observation, 58% of the entire account's D1 reads.  Driving the join
    // from json_each instead seeks idx_map_target_regions_scan once per region,
    // so the cost follows what was observed rather than what is stored.
    db.prepare(
      `DELETE FROM map_target_regions
       WHERE rowid IN (
         SELECT relation.rowid
         FROM json_each(?) AS region
         CROSS JOIN map_target_regions relation
           ON relation.server_key=?
          AND relation.map_kind=?
          AND relation.scan_x=CAST(json_extract(region.value,'$.x') AS INTEGER)
          AND relation.scan_y=CAST(json_extract(region.value,'$.y') AS INTEGER)
         WHERE NOT EXISTS (
           SELECT 1
           FROM json_each(?) AS snapshot
           JOIN json_each(json_extract(snapshot.value,'$.targets')) AS target
           WHERE CAST(json_extract(snapshot.value,'$.x') AS INTEGER)=relation.scan_x
             AND CAST(json_extract(snapshot.value,'$.y') AS INTEGER)=relation.scan_y
             AND CAST(json_extract(target.value,'$.targetId') AS TEXT)=relation.target_id
         )
       )`,
    ).bind(encoded, serverKey, mapKind, encoded),
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
  ]);
}

// v2 clients only report real changes (a new or changed target, a confirmed
// disappearance), so each row below is written unconditionally - the legacy
// 5-minute sighting throttle would delay exactly the information v2 exists to
// deliver.  Neither statement touches map_target_regions: those links only
// feed the legacy orphan sweep, and v2 removes targets explicitly.
export async function applyUpserts(
  db: D1Database,
  serverKey: string,
  mapKind: MapKind,
  targets: TargetObservation[],
  now: number,
): Promise<void> {
  if (targets.length === 0) return;
  const encoded = JSON.stringify(targets);
  await db.prepare(
    `INSERT INTO map_targets(
       server_key,map_kind,target_id,x,y,target_type,level,data_json,
       last_seen_at,changed_at
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
       ?,?
     FROM json_each(?) AS target
     WHERE 1
     ON CONFLICT(server_key,map_kind,target_id) DO UPDATE SET
       x=excluded.x, y=excluded.y, target_type=excluded.target_type,
       level=excluded.level, data_json=excluded.data_json,
       last_seen_at=excluded.last_seen_at, changed_at=excluded.changed_at,
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
  ).bind(serverKey, mapKind, now, now, encoded, now, now, now, now).run();
}

export async function applyGone(
  db: D1Database,
  serverKey: string,
  mapKind: MapKind,
  targetIds: string[],
  now: number,
): Promise<number> {
  if (targetIds.length === 0) return 0;
  const placeholders = targetIds.map(() => "?").join(",");
  // A tombstone, not a delete: status='missing' rows are the only channel the
  // change feed has to tell replicas that a target died.  Physical removal
  // stays with the TTL sweep.  'reserved' and 'dispatching' are excluded -
  // their holder is mid-flight and outranks any scan that stopped seeing it.
  const statements = [
    db.prepare(
      `UPDATE map_targets
       SET status='missing', status_at=?, changed_at=?
       WHERE server_key=? AND map_kind=?
         AND target_id IN (${placeholders})
         AND status NOT IN ('reserved','dispatching')`,
    ).bind(now, now, serverKey, mapKind, ...targetIds),
    // Stale links would let the legacy orphan logic or a future rescan keep
    // the target alive in readers that still walk map_target_regions.
    db.prepare(
      `DELETE FROM map_target_regions
       WHERE server_key=? AND map_kind=? AND target_id IN (${placeholders})`,
    ).bind(serverKey, mapKind, ...targetIds),
  ];
  const [tombstoned] = await db.batch(statements);
  return Number(tombstoned.meta.changes ?? 0);
}

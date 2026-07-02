"""SQLite-backed event store for alerts and frame-level activity statistics.

A single connection is shared across the Streamlit session (created once via
``st.cache_resource`` at the app layer) with ``check_same_thread=False`` and
an internal lock, since Streamlit can invoke callbacks from more than one
thread.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from surveillance.alerts.engine import Alert
from surveillance.config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    camera_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    object_class TEXT NOT NULL,
    confidence REAL NOT NULL,
    zone TEXT,
    bbox_json TEXT,
    message TEXT NOT NULL,
    snapshot_path TEXT,
    acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts (alert_type);

CREATE TABLE IF NOT EXISTS frame_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    camera_id TEXT NOT NULL,
    total_objects INTEGER NOT NULL,
    class_counts_json TEXT NOT NULL,
    backend TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_frame_stats_ts ON frame_stats (ts);
"""


class EventStore:
    def __init__(self, db_path: Path | None = None) -> None:
        ensure_dirs()
        self.db_path = db_path or DB_PATH
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- writes --------------------------------------------------------------

    def log_alert(self, alert: Alert, camera_id: str, snapshot_path: str | None = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO alerts
                   (ts, camera_id, alert_type, severity, object_class, confidence,
                    zone, bbox_json, message, snapshot_path, acknowledged)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    alert.ts, camera_id, alert.alert_type, alert.severity, alert.object_class,
                    alert.confidence, alert.zone, json.dumps(alert.bbox) if alert.bbox else None,
                    alert.message, snapshot_path,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def log_frame_stats(self, camera_id: str, class_counts: dict[str, int], backend: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO frame_stats (ts, camera_id, total_objects, class_counts_json, backend)
                   VALUES (?, ?, ?, ?, ?)""",
                (time.time(), camera_id, sum(class_counts.values()), json.dumps(class_counts), backend),
            )
            self._conn.commit()

    def acknowledge_alert(self, alert_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
            self._conn.commit()

    def purge_older_than(self, days: int) -> int:
        cutoff = time.time() - days * 86400
        with self._lock:
            cur = self._conn.execute("DELETE FROM alerts WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM frame_stats WHERE ts < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

    # -- reads --------------------------------------------------------------

    def recent_alerts(
        self,
        limit: int = 200,
        since_ts: float | None = None,
        alert_types: list[str] | None = None,
        unacknowledged_only: bool = False,
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM alerts WHERE 1=1"
        params: list = []
        if since_ts is not None:
            query += " AND ts >= ?"
            params.append(since_ts)
        if alert_types:
            placeholders = ",".join("?" for _ in alert_types)
            query += f" AND alert_type IN ({placeholders})"
            params.extend(alert_types)
        if unacknowledged_only:
            query += " AND acknowledged = 0"
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            return self._conn.execute(query, params).fetchall()

    def frame_stats_since(self, since_ts: float) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM frame_stats WHERE ts >= ? ORDER BY ts ASC", (since_ts,)
            ).fetchall()

    def alert_counts_by_type(self, since_ts: float | None = None) -> dict[str, int]:
        query = "SELECT alert_type, COUNT(*) as n FROM alerts"
        params: list = []
        if since_ts is not None:
            query += " WHERE ts >= ?"
            params.append(since_ts)
        query += " GROUP BY alert_type"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return {row["alert_type"]: row["n"] for row in rows}

    def total_counts(self) -> dict[str, int]:
        with self._lock:
            alerts_n = self._conn.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()["n"]
            unack_n = self._conn.execute(
                "SELECT COUNT(*) AS n FROM alerts WHERE acknowledged = 0"
            ).fetchone()["n"]
            frames_n = self._conn.execute("SELECT COUNT(*) AS n FROM frame_stats").fetchone()["n"]
        return {"alerts": alerts_n, "unacknowledged": unack_n, "frames_logged": frames_n}

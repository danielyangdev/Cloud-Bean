"""Persistent storage for candidates, evidence packets, accepted judgments, findings, and budget state."""

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent
from cloud_bean.schemas.evidence import EvidencePacket
from cloud_bean.schemas.finding import Finding, FindingSeverity, FindingStatus
from cloud_bean.schemas.judgment import Assessment, ConcerningPattern, LunaJudgment


def compute_finding_id(check_key: str, pattern: ConcerningPattern | str) -> str:
    """Derive deterministic finding ID: fnd_{sha256(check_key + pattern)[:10]}."""
    pat_str = pattern.value if isinstance(pattern, ConcerningPattern) else str(pattern)
    raw = f"{check_key}:{pat_str}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"fnd_{digest[:10]}"


class JudgmentFindingStore:
    """SQLite-backed or in-memory store for accepted judgments, packets, and deduplicated findings."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS candidate_groups (
                    group_id TEXT PRIMARY KEY,
                    trigger_signal TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    target_resources TEXT NOT NULL,
                    actors TEXT NOT NULL,
                    event_ids TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    is_audit_sample INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fleet_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    event_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_fleet_events_ts
                    ON fleet_events(timestamp);

                CREATE TABLE IF NOT EXISTS evidence_packets (
                    packet_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    token_count_estimate INTEGER NOT NULL,
                    packet_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS accepted_judgments (
                    check_key TEXT PRIMARY KEY,
                    packet_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    assessment TEXT NOT NULL,
                    patterns TEXT NOT NULL,
                    judgment_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS findings (
                    finding_id TEXT PRIMARY KEY,
                    check_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    assessment TEXT NOT NULL,
                    actors TEXT NOT NULL,
                    target_resources TEXT NOT NULL,
                    first_evidence_time TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    raw_judgment_ref TEXT NOT NULL,
                    is_audit_sample INTEGER NOT NULL,
                    finding_json TEXT NOT NULL,
                    FOREIGN KEY(check_key) REFERENCES accepted_judgments(check_key)
                );
                """
            )

    def save_candidate_group(self, group: CandidateGroup) -> None:
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO candidate_groups (
                    group_id, trigger_signal, window_start, window_end,
                    target_resources, actors, event_ids, metrics, is_audit_sample, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group.group_id,
                    group.trigger_signal,
                    group.window_start,
                    group.window_end,
                    json.dumps(group.target_resources),
                    json.dumps(group.actors),
                    json.dumps(group.event_ids),
                    json.dumps(group.metrics),
                    1 if group.is_audit_sample else 0,
                    now_iso,
                ),
            )

    def save_evidence_packet(self, packet: EvidencePacket) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO evidence_packets (
                    packet_id, group_id, created_at, token_count_estimate, packet_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    packet.packet_id,
                    packet.group_id,
                    packet.created_at,
                    packet.token_count_estimate,
                    packet.model_dump_json(),
                ),
            )

    def save_accepted_judgment(self, judgment: LunaJudgment) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO accepted_judgments (
                    check_key, packet_id, model, evaluated_at, assessment, patterns, judgment_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    judgment.check_key,
                    judgment.packet_id,
                    judgment.model,
                    judgment.evaluated_at,
                    judgment.assessment.value,
                    json.dumps([p.value for p in judgment.patterns]),
                    judgment.model_dump_json(),
                ),
            )

    def get_accepted_judgment(self, check_key: str) -> Optional[LunaJudgment]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT judgment_json FROM accepted_judgments WHERE check_key = ?",
                (check_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return LunaJudgment.model_validate_json(row["judgment_json"])

    def save_finding(self, finding: Finding) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO findings (
                    finding_id, check_key, status, severity, pattern, assessment,
                    actors, target_resources, first_evidence_time, detected_at,
                    explanation, evidence_ids, raw_judgment_ref, is_audit_sample, finding_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.finding_id,
                    finding.check_key,
                    finding.status.value,
                    finding.severity.value,
                    finding.pattern.value,
                    finding.assessment.value,
                    json.dumps(finding.actors),
                    json.dumps(finding.target_resources),
                    finding.first_evidence_time,
                    finding.detected_at,
                    finding.explanation,
                    json.dumps(finding.evidence_ids),
                    finding.raw_judgment_ref,
                    1 if finding.is_audit_sample else 0,
                    finding.model_dump_json(),
                ),
            )

    def get_finding(self, finding_id: str) -> Optional[Finding]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT finding_json FROM findings WHERE finding_id = ?",
                (finding_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Finding.model_validate_json(row["finding_json"])

    def list_findings(self) -> List[Finding]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT finding_json FROM findings ORDER BY detected_at ASC")
            return [Finding.model_validate_json(row["finding_json"]) for row in cursor.fetchall()]

    def list_candidate_groups(self) -> List[CandidateGroup]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT group_id, trigger_signal, window_start, window_end, target_resources, actors, event_ids, metrics, is_audit_sample FROM candidate_groups ORDER BY created_at ASC")
            result = []
            for row in cursor.fetchall():
                result.append(
                    CandidateGroup(
                        group_id=row["group_id"],
                        trigger_signal=row["trigger_signal"],
                        window_start=row["window_start"],
                        window_end=row["window_end"],
                        target_resources=json.loads(row["target_resources"]),
                        actors=json.loads(row["actors"]),
                        event_ids=json.loads(row["event_ids"]),
                        metrics=json.loads(row["metrics"]),
                        is_audit_sample=bool(row["is_audit_sample"]),
                    )
                )
            return result

    def list_evidence_packets(self) -> List[EvidencePacket]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT packet_json FROM evidence_packets ORDER BY created_at ASC")
            return [EvidencePacket.model_validate_json(row["packet_json"]) for row in cursor.fetchall()]

    def list_accepted_judgments(self) -> List[LunaJudgment]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT judgment_json FROM accepted_judgments ORDER BY evaluated_at ASC")
            return [LunaJudgment.model_validate_json(row["judgment_json"]) for row in cursor.fetchall()]

    def save_events(self, events: List[FleetEvent]) -> int:
        """Persist raw events, ignoring repeats of an event_id already stored.

        Event identity is the dedup key, so an at-least-once redelivery of the same
        event never lands twice.
        """
        if not events:
            return 0
        rows = [
            (e.event_id, e.timestamp, e.actor_id, e.model_dump_json())
            for e in events
        ]
        with self._lock, self._conn:
            before = self._conn.execute("SELECT COUNT(*) FROM fleet_events").fetchone()[0]
            self._conn.executemany(
                "INSERT OR IGNORE INTO fleet_events (event_id, timestamp, actor_id, event_json) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            after = self._conn.execute("SELECT COUNT(*) FROM fleet_events").fetchone()[0]
        return after - before

    def list_events(self) -> List["FleetEvent"]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT event_json FROM fleet_events ORDER BY timestamp ASC, event_id ASC"
            )
            return [FleetEvent.model_validate_json(r["event_json"]) for r in cursor.fetchall()]

    def count_events(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM fleet_events").fetchone()[0]

    def clear_events(self) -> int:
        with self._lock, self._conn:
            n = self._conn.execute("SELECT COUNT(*) FROM fleet_events").fetchone()[0]
            self._conn.execute("DELETE FROM fleet_events")
        return n

    def close(self) -> None:
        with self._lock:
            self._conn.close()

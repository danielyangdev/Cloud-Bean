"""Collusion Wiki SQLite dataset loader and normalized event converter."""

import gzip
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterator, List, Optional

from cloud_bean.schemas.events import EventType, FleetEvent


DEFAULT_DB_PATH = Path("benchmark/collusion-wiki/data/collusion-wiki.db")
DEFAULT_GZ_PATH = Path("benchmark/collusion-wiki/collusion-wiki.db.gz")


class CollusionWikiLoader:
    """Loads and queries the Collusion Wiki SQLite dataset, converting records to FleetEvent."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        gz_path: Optional[str | Path] = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.gz_path = Path(gz_path) if gz_path else DEFAULT_GZ_PATH
        self._ensure_database()

    def _ensure_database(self) -> None:
        """Ensure the SQLite database file exists, decompressing from .gz if needed."""
        if self.db_path.exists():
            return

        if not self.gz_path.exists():
            raise FileNotFoundError(
                f"Neither SQLite database ({self.db_path}) nor gzip archive ({self.gz_path}) exists."
            )

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.db_path.with_suffix(self.db_path.suffix + ".tmp")
        with gzip.open(self.gz_path, "rb") as f_in, open(temp_path, "wb") as f_out:
            while chunk := f_in.read(1024 * 1024):
                f_out.write(chunk)
        temp_path.replace(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Create a read-only SQLite connection with row factories."""
        uri = f"file:{self.db_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def get_stats(self) -> Dict[str, int]:
        """Return counts for revisions, events, pages, and labels."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM revisions")
            revisions = cursor.fetchone()[0]

            cursor.execute("SELECT count(*) FROM events")
            events = cursor.fetchone()[0]

            cursor.execute("SELECT count(*) FROM pages")
            pages = cursor.fetchone()[0]

            cursor.execute("SELECT count(*) FROM labels")
            labels = cursor.fetchone()[0]

            return {
                "revisions": revisions,
                "events": events,
                "pages": pages,
                "labels": labels,
            }

    def get_top_agents(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return top non-human labels sorted by stored revisions descending."""
        query = """
            SELECT label, stored_revisions, first_write, last_write,
                   stored_revision_pages, save_requests, is_human_handle
            FROM labels
            WHERE label != '' AND is_human_handle = 0
            ORDER BY stored_revisions DESC
            LIMIT ?
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def iter_revisions(
        self,
        limit: Optional[int] = None,
        agent: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Query revisions joined with pages and return row dicts."""
        query = """
            SELECT r.revision_id, r.page_key, p.name AS page_name, r.sequence,
                   r.body, r.body_len, r.body_sha256, r.label, r.ip16,
                   r.time, r.uncertainty_seconds, r.change_summary, r.request_action
            FROM revisions r
            JOIN pages p ON r.page_key = p.page_key
        """
        params: List[Any] = []
        if agent:
            query += " WHERE r.label = ?"
            params.append(agent)

        query += " ORDER BY r.time ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor:
                yield dict(row)

    def to_fleet_events(
        self,
        limit: Optional[int] = None,
        include_deletions: bool = True,
    ) -> Iterator[FleetEvent]:
        """Convert database revisions and mutation events into normalized FleetEvent objects."""
        yielded = 0

        # Query revisions
        rev_query = """
            SELECT r.revision_id, p.name AS page_name, r.sequence,
                   r.body, r.body_len, r.body_sha256, r.label, r.ip16,
                   r.time, r.uncertainty_seconds, r.change_summary
            FROM revisions r
            JOIN pages p ON r.page_key = p.page_key
            ORDER BY r.time ASC
        """
        if limit is not None:
            rev_query += f" LIMIT {limit}"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(rev_query)
            for row in cursor:
                body = row["body"] or ""
                actor = row["label"] if row["label"] else "anonymous_agent"
                event = FleetEvent(
                    event_id=f"rev_{row['revision_id']}",
                    timestamp=row["time"],
                    uncertainty_seconds=float(row["uncertainty_seconds"] or 0.0),
                    actor_id=actor,
                    task_id=f"task_wiki_{actor}",
                    session_id=row["ip16"],
                    event_type=EventType.resource_write,
                    target=f"wiki:{row['page_name']}",
                    operation="save_revision",
                    payload={
                        "body_sha256": row["body_sha256"],
                        "body_len": int(row["body_len"] or 0),
                        "change_summary": row["change_summary"] or "",
                        "body_snippet": body[:500],
                        "sequence": int(row["sequence"]),
                    },
                    sensor_source="wiki_archive",
                    missing_fields=["execution_receipt", "caller_ip"],
                )
                yield event
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

            if not include_deletions:
                return

            # Query deletion and revert events if limit not reached
            rem_limit = (limit - yielded) if limit is not None else None
            event_query = """
                SELECT e.event_id, e.event_type, e.time, p.name AS page_name,
                       m.actor_label, m.change_summary, m.uncertainty_seconds
                FROM events e
                LEFT JOIN page_events pe ON e.event_id = pe.event_id
                LEFT JOIN pages p ON pe.page_key = p.page_key
                LEFT JOIN mutation_events m ON e.event_id = m.event_id
                WHERE e.event_type IN ('delete', 'revert')
                ORDER BY e.time ASC
            """
            if rem_limit is not None:
                event_query += f" LIMIT {rem_limit}"

            cursor.execute(event_query)
            for row in cursor:
                actor = row["actor_label"] or "unknown_agent"
                target_page = row["page_name"] or "unknown_page"
                event_type = EventType.resource_write if row["event_type"] == "delete" else EventType.system_event
                event = FleetEvent(
                    event_id=f"evt_{row['event_id']}",
                    timestamp=row["time"],
                    uncertainty_seconds=float(row["uncertainty_seconds"] or 0.0),
                    actor_id=actor,
                    task_id=f"task_wiki_{actor}",
                    event_type=event_type,
                    target=f"wiki:{target_page}",
                    operation=f"{row['event_type']}_page",
                    payload={
                        "change_summary": row["change_summary"] or "",
                        "event_type": row["event_type"],
                    },
                    sensor_source="wiki_archive",
                    missing_fields=["execution_receipt", "caller_ip"],
                )
                yield event
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

"""Deterministic, auditable Opportunity Agent core. No external side effects."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def verify_source(url: str) -> bool:
    """Only treat syntactically valid HTTPS source URLs as eligible evidence.

    This is NOT independent fact verification: the claimed content is not fetched.
    """
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 443)
    )


def evaluate(goal: dict, candidate: dict) -> dict:
    """Explainable screening only; never claim eligibility or a confirmed opportunity."""
    keywords = [w.strip().lower() for w in goal["keywords"] if w.strip()]
    haystack = (candidate["title"] + " " + candidate["description"]).lower()
    matched = [w for w in keywords if w in haystack]
    source_ok = verify_source(candidate["source_url"])
    # Explicitly no inference of real eligibility, deadline validity, or source trust.
    status = "review" if matched and source_ok else "insufficient_evidence"
    return {
        "status": status,
        "matched_keywords": matched,
        "source_url": candidate["source_url"],
        "source_format_valid": source_ok,
        "limitations": [
            "Source URL syntax checked; contents and publisher have not been independently verified.",
            "Keyword matching is not an eligibility determination.",
            "No applications, messages, or external actions were performed.",
        ],
    }


class Store:
    """SQLite single-node proof of concept; not a multi-tenant production store."""

    def __init__(self, path: str = "humanos.db"):
        self.path = path
        self._lock = threading.RLock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, keywords TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    title TEXT NOT NULL, description TEXT NOT NULL, source_url TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN (
                        'queued','review','insufficient_evidence','approved','rejected')),
                    evaluation TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL, kind TEXT NOT NULL, details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connect(self):
        """Own the complete connection lifecycle, including Windows file-handle release.

        sqlite3.Connection.__exit__ commits or rolls back but does not close the handle.
        """
        con = sqlite3.connect(self.path, timeout=10)
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys=ON")
            with con:
                yield con
        finally:
            con.close()

    def _event(self, con, entity_id: str, kind: str, details: dict):
        con.execute(
            "INSERT INTO events (entity_id,kind,details,created_at) VALUES (?,?,?,?)",
            (entity_id, kind, json.dumps(details, sort_keys=True), utc_now()),
        )

    def create_goal(self, title: str, keywords: list[str]) -> dict:
        if not title.strip() or not keywords or not any(k.strip() for k in keywords):
            raise ValueError("A title and at least one keyword are required")
        goal = {"id": str(uuid.uuid4()), "title": title.strip(),
                "keywords": [w.strip() for w in keywords if w.strip()],
                "created_at": utc_now()}
        with self._lock, self._connect() as con:
            con.execute("INSERT INTO goals VALUES (?,?,?,?)",
                        (goal["id"], goal["title"], json.dumps(goal["keywords"]), goal["created_at"]))
            self._event(con, goal["id"], "goal_created", {"title": goal["title"]})
        return goal

    def get_goal(self, goal_id: str) -> dict | None:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["keywords"] = json.loads(item["keywords"])
        return item

    def list_goals(self) -> list[dict]:
        with self._lock, self._connect() as con:
            ids = [r["id"] for r in con.execute("SELECT id FROM goals ORDER BY created_at DESC")]
        return [self.get_goal(i) for i in ids]

    def add_candidate(self, goal_id: str, title: str, description: str, source_url: str) -> dict:
        if not self.get_goal(goal_id):
            raise LookupError("Goal not found")
        if not title.strip() or not description.strip() or not source_url.strip():
            raise ValueError("Title, description, and source URL are required")
        now = utc_now()
        candidate = {"id": str(uuid.uuid4()), "goal_id": goal_id,
                     "title": title.strip(), "description": description.strip(),
                     "source_url": source_url.strip(), "state": "queued",
                     "evaluation": None, "created_at": now, "updated_at": now}
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?)",
                (candidate["id"], goal_id, candidate["title"], candidate["description"],
                 candidate["source_url"], "queued", None, now, now),
            )
            self._event(con, candidate["id"], "candidate_queued", {"goal_id": goal_id})
        return candidate

    def get_candidate(self, candidate_id: str) -> dict | None:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["evaluation"] = json.loads(item["evaluation"]) if item["evaluation"] else None
        return item

    def list_candidates(self, goal_id: str | None = None) -> list[dict]:
        with self._lock, self._connect() as con:
            if goal_id:
                ids = [r["id"] for r in con.execute(
                    "SELECT id FROM candidates WHERE goal_id=? ORDER BY created_at DESC", (goal_id,))]
            else:
                ids = [r["id"] for r in con.execute("SELECT id FROM candidates ORDER BY created_at DESC")]
        return [self.get_candidate(i) for i in ids]

    def evaluate_candidate(self, candidate_id: str) -> dict:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
            if row is None:
                raise LookupError("Candidate not found")
            if row["state"] != "queued":
                raise ValueError("Only queued candidates can be evaluated")
            goal = self.get_goal(row["goal_id"])
            verdict = evaluate(goal, dict(row))
            con.execute(
                "UPDATE candidates SET state=?, evaluation=?, updated_at=? WHERE id=? AND state='queued'",
                (verdict["status"], json.dumps(verdict), utc_now(), candidate_id),
            )
            self._event(con, candidate_id, "candidate_evaluated", verdict)
        return self.get_candidate(candidate_id)

    def review(self, candidate_id: str, decision: str) -> dict:
        if decision not in ("approved", "rejected"):
            raise ValueError("Decision must be approved or rejected")
        with self._lock, self._connect() as con:
            row = con.execute("SELECT state FROM candidates WHERE id=?", (candidate_id,)).fetchone()
            if row is None:
                raise LookupError("Candidate not found")
            if row["state"] != "review":
                raise ValueError("Only reviewed, evidence-screened candidates can be decided")
            con.execute(
                "UPDATE candidates SET state=?, updated_at=? WHERE id=? AND state='review'",
                (decision, utc_now(), candidate_id),
            )
            self._event(con, candidate_id, "human_decision", {"decision": decision,
                         "note": "Approval does not submit an application."})
        return self.get_candidate(candidate_id)

    def events(self, entity_id: str) -> list[dict]:
        with self._lock, self._connect() as con:
            rows = con.execute(
                "SELECT * FROM events WHERE entity_id=? ORDER BY id", (entity_id,)).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

    def run_queued(self, limit: int = 25) -> dict:
        """One bounded, idempotent pass. Call via a trusted external scheduler."""
        with self._lock, self._connect() as con:
            ids = [r["id"] for r in con.execute(
                "SELECT id FROM candidates WHERE state='queued' ORDER BY created_at LIMIT ?", (limit,))]
        completed = []
        for candidate_id in ids:
            try:
                completed.append(self.evaluate_candidate(candidate_id)["id"])
            except ValueError:
                pass  # Another scheduler may have already evaluated this record.
        return {"evaluated": len(completed), "candidate_ids": completed}

"""SQLite-backed dataset/run store - analyses survive backend restarts.

Uses stdlib sqlite3 + pickle (local, single-user POC). DataFrames live once in
the datasets table; runs are pickled without their frame and re-attached on
load. Everything is also cached in memory, so read paths are unchanged.
"""
from __future__ import annotations

import json
import pickle
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from engine.orchestrator import Run

DB_PATH = Path(__file__).resolve().parent.parent / "data.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Dataset:
    df: pd.DataFrame
    filename: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class Store:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.datasets: dict[str, Dataset] = {}
        self.runs: dict[str, Run] = {}
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS datasets ("
            "id TEXT PRIMARY KEY, filename TEXT, frame BLOB)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS runs ("
            "id TEXT PRIMARY KEY, dataset_id TEXT, created_at TEXT, state BLOB)"
        )
        # Unified append-only activity log (Postgres-portable column types).
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS activity_log ("
            "id INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, "
            "event_type TEXT NOT NULL, dataset_id TEXT, artifact_id TEXT, "
            "run_id TEXT, provider TEXT, model TEXT, tokens_in INTEGER, "
            "tokens_out INTEGER, latency_ms INTEGER, mode TEXT, payload TEXT)"
        )
        self._db.commit()
        self._load()
        self._migrate_decision_trail()

    # -- startup ---------------------------------------------------------------
    def _load(self) -> None:
        for ds_id, filename, blob in self._db.execute("SELECT id, filename, frame FROM datasets"):
            try:
                df = pickle.loads(blob)
                self.datasets[ds_id] = Dataset(df=df, filename=filename, id=ds_id)
            except Exception:
                continue  # skip unreadable rows rather than failing startup
        for run_id, ds_id, _created, blob in self._db.execute(
            "SELECT id, dataset_id, created_at, state FROM runs"
        ):
            ds = self.datasets.get(ds_id)
            if ds is None:
                continue
            try:
                state = pickle.loads(blob)
                run = Run(dataset_id=ds_id, df=ds.df, filename=ds.filename)
                run.__dict__.update(state)
                run.df = ds.df  # never trust a pickled frame reference
                self.runs[run_id] = run
            except Exception:
                continue

    # -- datasets --------------------------------------------------------------
    def add_dataset(self, df: pd.DataFrame, filename: str) -> Dataset:
        ds = Dataset(df=df, filename=filename)
        self.datasets[ds.id] = ds
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO datasets (id, filename, frame) VALUES (?, ?, ?)",
                (ds.id, ds.filename, pickle.dumps(df)),
            )
            self._db.commit()
        return ds

    def get_dataset(self, dataset_id: str) -> Dataset:
        if dataset_id not in self.datasets:
            raise KeyError(f"Unknown dataset: {dataset_id}")
        return self.datasets[dataset_id]

    # -- runs ------------------------------------------------------------------
    def add_run(self, run: Run) -> Run:
        self.runs[run.id] = run
        self.save_run(run)
        return run

    def save_run(self, run: Run) -> None:
        """Persist a run's current state (call after every mutating stage)."""
        state = {k: v for k, v in run.__dict__.items() if k != "df"}
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO runs (id, dataset_id, created_at, state) VALUES (?, ?, ?, ?)",
                (run.id, run.dataset_id, run.created_at, pickle.dumps(state)),
            )
            self._db.commit()

    def get_run(self, run_id: str) -> Run:
        if run_id not in self.runs:
            raise KeyError(f"Unknown run: {run_id}")
        return self.runs[run_id]

    # -- activity log ----------------------------------------------------------
    def log_event(
        self,
        actor: str,
        event_type: str,
        *,
        dataset_id: str | None = None,
        artifact_id: str | None = None,
        run_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        latency_ms: int | None = None,
        mode: str | None = None,
        payload: dict | None = None,
        ts: str | None = None,
    ) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO activity_log (ts, actor, event_type, dataset_id, "
                "artifact_id, run_id, provider, model, tokens_in, tokens_out, "
                "latency_ms, mode, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts or _now(), actor, event_type, dataset_id, artifact_id,
                    run_id, provider, model, tokens_in, tokens_out, latency_ms,
                    mode, json.dumps(payload, default=str) if payload is not None else None,
                ),
            )
            self._db.commit()

    _ACTIVITY_COLS = (
        "id", "ts", "actor", "event_type", "dataset_id", "artifact_id", "run_id",
        "provider", "model", "tokens_in", "tokens_out", "latency_ms", "mode", "payload",
    )

    def list_activity(
        self,
        run_id: str | None = None,
        dataset_id: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        clauses, params = [], []
        for col, val in (
            ("run_id", run_id), ("dataset_id", dataset_id), ("event_type", event_type),
        ):
            if val:
                clauses.append(f"{col} = ?")
                params.append(val)
        if since:
            clauses.append("ts >= ?")
            params.append(since)
        if until:
            clauses.append("ts <= ?")
            params.append(until)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.execute(
            f"SELECT {', '.join(self._ACTIVITY_COLS)} FROM activity_log {where} "
            f"ORDER BY id DESC LIMIT ?",
            (*params, max(1, min(int(limit), 5000))),
        ).fetchall()
        out = []
        for row in rows:
            d = dict(zip(self._ACTIVITY_COLS, row))
            if d["payload"]:
                try:
                    d["payload"] = json.loads(d["payload"])
                except Exception:
                    pass
            out.append(d)
        return out

    def _migrate_decision_trail(self) -> None:
        """One-time backfill: old per-run trails become activity rows."""
        (count,) = self._db.execute("SELECT COUNT(*) FROM activity_log").fetchone()
        if count > 0 or not self.runs:
            return
        for run in self.runs.values():
            for node in run.decisions:
                event = "approval" if node.status == "approved" else (
                    "error" if node.status == "error" else
                    "train" if node.stage == "execute" else "agent_call"
                )
                self.log_event(
                    "migrated", event, dataset_id=run.dataset_id, run_id=run.id,
                    payload=node.to_dict(), ts=node.timestamp,
                )
            for entry in run.agent_log:
                self.log_event(
                    entry.get("agent", "agent"), "agent_call",
                    dataset_id=run.dataset_id, run_id=run.id,
                    latency_ms=entry.get("duration_ms"),
                    mode="llm" if entry.get("generated_by") == "claude" else "fallback",
                    payload={k: entry.get(k) for k in ("action", "decision", "reasoning")},
                    ts=entry.get("timestamp"),
                )


store = Store()

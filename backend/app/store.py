"""SQLite-backed dataset/run store - analyses survive backend restarts.

Uses stdlib sqlite3 + pickle (local, single-user POC). DataFrames live once in
the datasets table; runs are pickled without their frame and re-attached on
load. Everything is also cached in memory, so read paths are unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sqlite3
import stat
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from engine.orchestrator import Run

DB_PATH = Path(__file__).resolve().parent.parent / "data.db"
ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifact_store"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Artifact:
    id: str
    kind: str  # original | derived
    parent_ids: list[str]
    transform_type: str  # upload | pii_mask | remediation | join | stack | feature_eng
    transform_params: dict
    sha256: str
    created_at: str
    file_path: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "parent_ids": self.parent_ids,
            "transform_type": self.transform_type,
            "transform_params": self.transform_params, "sha256": self.sha256,
            "created_at": self.created_at, "file_path": self.file_path,
        }


@dataclass
class Dataset:
    df: pd.DataFrame
    filename: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    artifact_id: str | None = None  # table artifact this frame came from


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
        # Immutable artifact ledger: originals + derived frames with lineage.
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS artifacts ("
            "id TEXT PRIMARY KEY, kind TEXT NOT NULL, parent_ids TEXT, "
            "transform_type TEXT NOT NULL, transform_params TEXT, "
            "sha256 TEXT NOT NULL, created_at TEXT NOT NULL, file_path TEXT NOT NULL)"
        )
        try:  # older DBs predate the datasets.artifact_id column
            self._db.execute("ALTER TABLE datasets ADD COLUMN artifact_id TEXT")
        except sqlite3.OperationalError:
            pass
        self._db.commit()
        ARTIFACT_DIR.mkdir(exist_ok=True)
        self._load()
        self._migrate_decision_trail()
        self._migrate_dataset_artifacts()

    # -- startup ---------------------------------------------------------------
    def _load(self) -> None:
        for ds_id, filename, blob, art_id in self._db.execute(
            "SELECT id, filename, frame, artifact_id FROM datasets"
        ):
            try:
                df = pickle.loads(blob)
                self.datasets[ds_id] = Dataset(df=df, filename=filename, id=ds_id, artifact_id=art_id)
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
    def add_dataset(self, df: pd.DataFrame, filename: str, artifact_id: str | None = None) -> Dataset:
        ds = Dataset(df=df, filename=filename, artifact_id=artifact_id)
        self.datasets[ds.id] = ds
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO datasets (id, filename, frame, artifact_id) VALUES (?, ?, ?, ?)",
                (ds.id, ds.filename, pickle.dumps(df), artifact_id),
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

    # -- artifacts -------------------------------------------------------------
    def add_original_artifact(self, raw: bytes, ext: str) -> Artifact:
        """Store raw uploaded bytes read-only, content-addressed by hash."""
        sha = hashlib.sha256(raw).hexdigest()
        path = ARTIFACT_DIR / f"{sha}{ext}"
        if not path.exists():
            path.write_bytes(raw)
            try:
                os.chmod(path, stat.S_IREAD)  # read-only where the OS allows
            except OSError:
                pass
        return self._insert_artifact("original", [], "upload", {}, sha, str(path))

    def add_derived_artifact(
        self,
        df: pd.DataFrame,
        parent_ids: list[str],
        transform_type: str,
        transform_params: dict,
    ) -> Artifact:
        """Materialize a transformed frame as a new content-addressed artifact."""
        blob = pickle.dumps(df)
        sha = hashlib.sha256(blob).hexdigest()
        path = ARTIFACT_DIR / f"{sha}.pkl"
        if not path.exists():
            path.write_bytes(blob)
        return self._insert_artifact(
            "derived", parent_ids, transform_type, transform_params, sha, str(path)
        )

    def _insert_artifact(
        self, kind: str, parent_ids: list[str], transform_type: str,
        transform_params: dict, sha256: str, file_path: str,
    ) -> Artifact:
        art = Artifact(
            id=uuid.uuid4().hex[:12], kind=kind, parent_ids=parent_ids,
            transform_type=transform_type, transform_params=transform_params,
            sha256=sha256, created_at=_now(), file_path=file_path,
        )
        with self._lock:
            self._db.execute(
                "INSERT INTO artifacts (id, kind, parent_ids, transform_type, "
                "transform_params, sha256, created_at, file_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    art.id, art.kind, json.dumps(art.parent_ids),
                    art.transform_type, json.dumps(art.transform_params, default=str),
                    art.sha256, art.created_at, art.file_path,
                ),
            )
            self._db.commit()
        self.log_event(
            "system", "transform", artifact_id=art.id,
            payload={"kind": kind, "transform_type": transform_type,
                     "parents": parent_ids, "sha256": sha256},
        )
        return art

    def get_artifact(self, artifact_id: str) -> Artifact:
        row = self._db.execute(
            "SELECT id, kind, parent_ids, transform_type, transform_params, "
            "sha256, created_at, file_path FROM artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown artifact: {artifact_id}")
        return Artifact(
            id=row[0], kind=row[1], parent_ids=json.loads(row[2] or "[]"),
            transform_type=row[3], transform_params=json.loads(row[4] or "{}"),
            sha256=row[5], created_at=row[6], file_path=row[7],
        )

    def lineage(self, artifact_id: str) -> list[Artifact]:
        """The chain from this artifact back to its original(s), child first."""
        chain: list[Artifact] = []
        seen: set[str] = set()
        frontier = [artifact_id]
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            try:
                art = self.get_artifact(current)
            except KeyError:
                continue
            chain.append(art)
            frontier.extend(art.parent_ids)
        return chain

    def _migrate_dataset_artifacts(self) -> None:
        """Wrap pre-artifact datasets as original artifacts (one-time)."""
        for ds in self.datasets.values():
            if ds.artifact_id:
                continue
            blob = pickle.dumps(ds.df)
            sha = hashlib.sha256(blob).hexdigest()
            path = ARTIFACT_DIR / f"{sha}.pkl"
            if not path.exists():
                path.write_bytes(blob)
            art = self._insert_artifact(
                "original", [], "upload", {"migrated": True, "filename": ds.filename},
                sha, str(path),
            )
            ds.artifact_id = art.id
            with self._lock:
                self._db.execute(
                    "UPDATE datasets SET artifact_id = ? WHERE id = ?", (art.id, ds.id)
                )
                self._db.commit()

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

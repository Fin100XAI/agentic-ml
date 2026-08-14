"""SQLite-backed dataset/run store - analyses survive backend restarts.

Uses stdlib sqlite3 + pickle (local, single-user POC). DataFrames live once in
the datasets table; runs are pickled without their frame and re-attached on
load. Everything is also cached in memory, so read paths are unchanged.
"""
from __future__ import annotations

import pickle
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from engine.orchestrator import Run

DB_PATH = Path(__file__).resolve().parent.parent / "data.db"


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
        self._db.commit()
        self._load()

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


store = Store()

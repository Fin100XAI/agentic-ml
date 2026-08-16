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


def _feature_ranges(run: Run) -> dict:
    """Observed min/max per numeric input column at training time - the
    what-if sliders' honest bounds."""
    target = (run.config or {}).get("target")
    excluded = set((run.config or {}).get("excluded") or [])
    out = {}
    for col in run.df.columns:
        if str(col) == target or str(col) in excluded:
            continue
        s = pd.to_numeric(run.df[col], errors="coerce").dropna()
        if len(s) > 5 and s.nunique() > 2:
            out[str(col)] = [round(float(s.min()), 4), round(float(s.max()), 4)]
    return out


def _baseline(run: Run) -> dict:
    """A typical record: medians for numerics, most common value otherwise."""
    target = (run.config or {}).get("target")
    out = {}
    for col in run.df.columns:
        if str(col) == target:
            continue
        s = run.df[col]
        if pd.api.types.is_numeric_dtype(s):
            med = s.median()
            out[str(col)] = round(float(med), 4) if pd.notna(med) else 0.0
        else:
            mode = s.mode()
            out[str(col)] = str(mode.iloc[0]) if len(mode) else ""
    return out


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
class Project:
    id: str
    name: str
    description: str
    created_at: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description,
                "created_at": self.created_at}


@dataclass
class Dataset:
    df: pd.DataFrame
    filename: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    artifact_id: str | None = None  # table artifact this frame came from
    pii: dict | None = None  # {"status": "pending|reviewed|clean", "findings": [...], "actions": {...}}
    project_id: str | None = None


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
        # Projects: the top-level container everything else scopes to.
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS projects ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, "
            "created_at TEXT NOT NULL)"
        )
        # Project glossary: the human's own definitions beat any AI guess.
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS glossary ("
            "project_id TEXT NOT NULL, term TEXT NOT NULL, definition TEXT NOT NULL, "
            "PRIMARY KEY (project_id, term))"
        )
        # Model registry: every completed training run, versioned, never overwritten.
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS model_registry ("
            "model_id TEXT NOT NULL, version INTEGER NOT NULL, project_id TEXT, "
            "run_id TEXT, purpose_statement TEXT, artifact_id TEXT, data_sha256 TEXT, "
            "use_case TEXT, model_key TEXT, model_name TEXT, raw_columns TEXT, "
            "feature_list TEXT, hyperparams TEXT, seed INTEGER, metrics TEXT, "
            "stability_verdict TEXT, checkpoint_path TEXT, llm_provider TEXT, "
            "llm_model TEXT, approved_by TEXT, approved_at TEXT, "
            "status TEXT NOT NULL, PRIMARY KEY (model_id, version))"
        )
        for ddl in (
            "ALTER TABLE datasets ADD COLUMN artifact_id TEXT",
            "ALTER TABLE datasets ADD COLUMN pii TEXT",
            "ALTER TABLE datasets ADD COLUMN project_id TEXT",
            "ALTER TABLE runs ADD COLUMN project_id TEXT",
            "ALTER TABLE artifacts ADD COLUMN project_id TEXT",
            "ALTER TABLE activity_log ADD COLUMN project_id TEXT",
            "ALTER TABLE model_registry ADD COLUMN n_rows INTEGER",
            "ALTER TABLE model_registry ADD COLUMN change_summary TEXT",
            "ALTER TABLE model_registry ADD COLUMN feature_ranges TEXT",
            "ALTER TABLE model_registry ADD COLUMN baseline TEXT",
            "ALTER TABLE model_registry ADD COLUMN decision_threshold REAL",
        ):  # older DBs predate these columns
            try:
                self._db.execute(ddl)
            except sqlite3.OperationalError:
                pass
        self._db.commit()
        ARTIFACT_DIR.mkdir(exist_ok=True)
        self.projects: dict[str, Project] = {}
        self._load_projects()
        self._load()
        self._migrate_decision_trail()
        self._migrate_dataset_artifacts()
        self._migrate_default_project()

    # -- startup ---------------------------------------------------------------
    def _load_projects(self) -> None:
        for pid, name, desc, created in self._db.execute(
            "SELECT id, name, description, created_at FROM projects"
        ):
            self.projects[pid] = Project(id=pid, name=name, description=desc or "", created_at=created)

    def _load(self) -> None:
        for ds_id, filename, blob, art_id, pii_json, proj_id in self._db.execute(
            "SELECT id, filename, frame, artifact_id, pii, project_id FROM datasets"
        ):
            try:
                df = pickle.loads(blob)
                self.datasets[ds_id] = Dataset(
                    df=df, filename=filename, id=ds_id, artifact_id=art_id,
                    pii=json.loads(pii_json) if pii_json else None,
                    project_id=proj_id,
                )
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
                # Remediated runs continue on their fixed frame, not the upload.
                # (feature_eng artifacts are re-applied at execute time from
                # config, so those stay on the dataset frame.)
                if run.artifact_id and run.artifact_id != ds.artifact_id:
                    try:
                        art = self.get_artifact(run.artifact_id)
                        if art.transform_type == "remediation" and art.file_path.endswith(".pkl"):
                            run.df = pickle.loads(Path(art.file_path).read_bytes())
                    except Exception:
                        pass  # fall back to the dataset frame
                self.runs[run_id] = run
            except Exception:
                continue

    # -- datasets --------------------------------------------------------------
    def add_dataset(
        self, df: pd.DataFrame, filename: str, artifact_id: str | None = None,
        pii: dict | None = None, project_id: str | None = None,
    ) -> Dataset:
        ds = Dataset(df=df, filename=filename, artifact_id=artifact_id, pii=pii,
                     project_id=project_id or self.default_project_id())
        self.datasets[ds.id] = ds
        self._persist_dataset(ds)
        return ds

    def update_dataset(self, ds: Dataset) -> None:
        """Persist in-place changes (masked frame, artifact pointer, PII state)."""
        self._persist_dataset(ds)

    def _persist_dataset(self, ds: Dataset) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO datasets (id, filename, frame, artifact_id, pii, project_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ds.id, ds.filename, pickle.dumps(ds.df), ds.artifact_id,
                    json.dumps(ds.pii, default=str) if ds.pii else None,
                    ds.project_id,
                ),
            )
            self._db.commit()

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
        ds = self.datasets.get(run.dataset_id)
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO runs (id, dataset_id, created_at, state, project_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (run.id, run.dataset_id, run.created_at, pickle.dumps(state),
                 ds.project_id if ds else None),
            )
            self._db.commit()

    # -- projects --------------------------------------------------------------
    DEFAULT_PROJECT_NAME = "Default Project"

    def add_project(self, name: str, description: str = "") -> Project:
        proj = Project(id=uuid.uuid4().hex[:12], name=name.strip(),
                       description=description.strip(), created_at=_now())
        self.projects[proj.id] = proj
        with self._lock:
            self._db.execute(
                "INSERT INTO projects (id, name, description, created_at) VALUES (?, ?, ?, ?)",
                (proj.id, proj.name, proj.description, proj.created_at),
            )
            self._db.commit()
        return proj

    def get_project(self, project_id: str) -> Project:
        if project_id not in self.projects:
            raise KeyError(f"Unknown project: {project_id}")
        return self.projects[project_id]

    def update_project(self, project_id: str, name: str | None, description: str | None) -> Project:
        proj = self.get_project(project_id)
        if name is not None and name.strip():
            proj.name = name.strip()
        if description is not None:
            proj.description = description.strip()
        with self._lock:
            self._db.execute(
                "UPDATE projects SET name = ?, description = ? WHERE id = ?",
                (proj.name, proj.description, proj.id),
            )
            self._db.commit()
        return proj

    def delete_project(self, project_id: str) -> None:
        proj = self.get_project(project_id)
        if any(ds.project_id == project_id for ds in self.datasets.values()):
            raise ValueError("This project still holds datasets - move or delete them first.")
        del self.projects[project_id]
        with self._lock:
            self._db.execute("DELETE FROM projects WHERE id = ?", (proj.id,))
            self._db.commit()

    def default_project_id(self) -> str:
        for proj in self.projects.values():
            if proj.name == self.DEFAULT_PROJECT_NAME:
                return proj.id
        if self.projects:
            return next(iter(self.projects))
        return self.add_project(self.DEFAULT_PROJECT_NAME, "Everything from before projects existed, plus quick one-off analyses.").id

    def runs_for_project(self, project_id: str) -> list[Run]:
        out = []
        for r in self.runs.values():
            ds = self.datasets.get(r.dataset_id)
            if ds is not None and ds.project_id == project_id:
                out.append(r)
        return out

    def project_summary(self, project_id: str) -> dict:
        n_datasets = sum(1 for d in self.datasets.values() if d.project_id == project_id)
        run_rows = self.runs_for_project(project_id)
        last = max((r.created_at for r in run_rows), default=None)
        return {"n_datasets": n_datasets, "n_runs": len(run_rows), "last_run_at": last}

    def _migrate_default_project(self) -> None:
        """One-time: attach pre-project rows to a Default Project."""
        orphan_ds = [d for d in self.datasets.values() if not d.project_id]
        (orphan_logs,) = self._db.execute(
            "SELECT COUNT(*) FROM activity_log WHERE project_id IS NULL"
        ).fetchone()
        if not orphan_ds and not orphan_logs:
            return
        pid = self.default_project_id()
        for ds in orphan_ds:
            ds.project_id = pid
            self._persist_dataset(ds)
        with self._lock:
            self._db.execute("UPDATE runs SET project_id = ? WHERE project_id IS NULL", (pid,))
            self._db.execute("UPDATE artifacts SET project_id = ? WHERE project_id IS NULL", (pid,))
            self._db.execute("UPDATE activity_log SET project_id = ? WHERE project_id IS NULL", (pid,))
            self._db.commit()

    def get_run(self, run_id: str) -> Run:
        if run_id not in self.runs:
            raise KeyError(f"Unknown run: {run_id}")
        return self.runs[run_id]

    # -- artifacts -------------------------------------------------------------
    def add_original_artifact(self, raw: bytes, ext: str, project_id: str | None = None) -> Artifact:
        """Store raw uploaded bytes read-only, content-addressed by hash."""
        sha = hashlib.sha256(raw).hexdigest()
        path = ARTIFACT_DIR / f"{sha}{ext}"
        if not path.exists():
            path.write_bytes(raw)
            try:
                os.chmod(path, stat.S_IREAD)  # read-only where the OS allows
            except OSError:
                pass
        return self._insert_artifact("original", [], "upload", {}, sha, str(path), project_id)

    def add_derived_artifact(
        self,
        df: pd.DataFrame,
        parent_ids: list[str],
        transform_type: str,
        transform_params: dict,
        project_id: str | None = None,
    ) -> Artifact:
        """Materialize a transformed frame as a new content-addressed artifact."""
        blob = pickle.dumps(df)
        sha = hashlib.sha256(blob).hexdigest()
        path = ARTIFACT_DIR / f"{sha}.pkl"
        if not path.exists():
            path.write_bytes(blob)
        return self._insert_artifact(
            "derived", parent_ids, transform_type, transform_params, sha, str(path), project_id
        )

    def _insert_artifact(
        self, kind: str, parent_ids: list[str], transform_type: str,
        transform_params: dict, sha256: str, file_path: str,
        project_id: str | None = None,
    ) -> Artifact:
        art = Artifact(
            id=uuid.uuid4().hex[:12], kind=kind, parent_ids=parent_ids,
            transform_type=transform_type, transform_params=transform_params,
            sha256=sha256, created_at=_now(), file_path=file_path,
        )
        with self._lock:
            self._db.execute(
                "INSERT INTO artifacts (id, kind, parent_ids, transform_type, "
                "transform_params, sha256, created_at, file_path, project_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    art.id, art.kind, json.dumps(art.parent_ids),
                    art.transform_type, json.dumps(art.transform_params, default=str),
                    art.sha256, art.created_at, art.file_path, project_id,
                ),
            )
            self._db.commit()
        self.log_event(
            "system", "transform", artifact_id=art.id, project_id=project_id,
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

    # -- glossary --------------------------------------------------------------
    def add_glossary_entries(self, project_id: str, entries: list[dict]) -> int:
        added = 0
        with self._lock:
            for e in entries:
                term = str(e.get("term", "")).strip()
                definition = str(e.get("definition", "")).strip()
                if not term or not definition:
                    continue
                self._db.execute(
                    "INSERT OR REPLACE INTO glossary (project_id, term, definition) VALUES (?, ?, ?)",
                    (project_id, term, definition),
                )
                added += 1
            self._db.commit()
        return added

    def list_glossary(self, project_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT term, definition FROM glossary WHERE project_id = ? ORDER BY term",
            (project_id,),
        ).fetchall()
        return [{"term": t, "definition": d} for t, d in rows]

    def delete_glossary_entry(self, project_id: str, term: str) -> None:
        with self._lock:
            self._db.execute(
                "DELETE FROM glossary WHERE project_id = ? AND term = ?", (project_id, term)
            )
            self._db.commit()

    def glossary_for_columns(self, project_id: str | None, columns: list[str]) -> dict[str, str]:
        """Column name -> human definition, matched by keyword normalization."""
        if not project_id:
            return {}
        from engine.librarian import _normalize

        by_norm = {_normalize(e["term"]): e["definition"] for e in self.list_glossary(project_id)}
        return {
            str(c): by_norm[_normalize(str(c))]
            for c in columns if _normalize(str(c)) in by_norm
        }

    # -- model registry --------------------------------------------------------
    _REGISTRY_COLS = (
        "model_id", "version", "project_id", "run_id", "purpose_statement",
        "artifact_id", "data_sha256", "use_case", "model_key", "model_name",
        "raw_columns", "feature_list", "hyperparams", "seed", "metrics",
        "stability_verdict", "checkpoint_path", "llm_provider", "llm_model",
        "approved_by", "approved_at", "status", "n_rows", "change_summary",
        "feature_ranges", "baseline", "decision_threshold",
    )
    _REGISTRY_JSON_COLS = (
        "raw_columns", "feature_list", "hyperparams", "metrics", "change_summary",
        "feature_ranges", "baseline",
    )

    _PRIMARY_METRIC = {"classification": "f1", "regression": "rmse",
                       "clustering": "silhouette", "forecasting": "mape_pct"}

    def _change_summary(self, prev: dict, row: dict) -> dict:
        """What changed between two versions - readable, computed, stored."""
        settings_delta = {}
        old_hp, new_hp = prev.get("hyperparams") or {}, row["hyperparams"]
        for k in sorted(set(old_hp) | set(new_hp)):
            if old_hp.get(k) != new_hp.get(k):
                settings_delta[k] = [old_hp.get(k), new_hp.get(k)]
        pk = self._PRIMARY_METRIC.get(row["use_case"], "")
        old_m = (prev.get("metrics") or {}).get(pk)
        new_m = (row["metrics"] or {}).get(pk)
        metric_delta = None
        if isinstance(old_m, (int, float)) and isinstance(new_m, (int, float)):
            metric_delta = {"metric": pk, "before": old_m, "after": new_m,
                            "delta": round(new_m - old_m, 4)}
        return {
            "from_version": prev.get("version"),
            "data": {
                "rows_before": prev.get("n_rows"),
                "rows_after": row["n_rows"],
                "same_data": bool(prev.get("data_sha256") and prev["data_sha256"] == row["data_sha256"]),
            },
            "settings": settings_delta,
            "metric": metric_delta,
        }

    def register_model(self, run: Run, fitted_model: object | None,
                       llm_provider: str | None, llm_model: str | None) -> dict | None:
        """Write a versioned registry entry for a completed training run."""
        if not run.config or not run.result:
            return None
        ds = self.datasets.get(run.dataset_id)
        project_id = ds.project_id if ds else None
        # Model identity: same project + problem + algorithm = same model_id.
        ident = f"{project_id}|{run.config['use_case']}|{run.config.get('target')}|{run.config['model_key']}"
        model_id = hashlib.sha256(ident.encode()).hexdigest()[:12]
        (prev_max,) = self._db.execute(
            "SELECT MAX(version) FROM model_registry WHERE model_id = ?", (model_id,)
        ).fetchone()
        version = (prev_max or 0) + 1

        checkpoint_path = None
        if fitted_model is not None:
            try:
                blob = pickle.dumps(fitted_model)
                sha = hashlib.sha256(blob).hexdigest()
                path = ARTIFACT_DIR / f"{sha}.model.pkl"
                if not path.exists():
                    path.write_bytes(blob)
                checkpoint_path = str(path)
            except Exception:
                checkpoint_path = None  # unpicklable model: metadata still registers

        data_sha = None
        if run.artifact_id:
            try:
                data_sha = self.get_artifact(run.artifact_id).sha256
            except KeyError:
                pass
        if data_sha is None:  # no artifact trail: hash the training frame itself
            try:
                data_sha = hashlib.sha256(pickle.dumps(run.df)).hexdigest()
            except Exception:
                pass

        row = {
            "model_id": model_id, "version": version, "project_id": project_id,
            "run_id": run.id, "purpose_statement": run.question,
            "artifact_id": run.artifact_id, "data_sha256": data_sha,
            "use_case": run.config["use_case"], "model_key": run.config["model_key"],
            "model_name": run.config["model_name"],
            "raw_columns": [str(c) for c in run.df.columns],
            "feature_list": run.result.get("features_used") or [],
            "hyperparams": run.config.get("hyperparams") or {},
            "seed": 42, "metrics": run.result.get("metrics") or {},
            "stability_verdict": ((run.result.get("validation") or {}).get("verdict")),
            "checkpoint_path": checkpoint_path,
            "llm_provider": llm_provider, "llm_model": llm_model,
            "approved_by": "local user", "approved_at": _now(), "status": "active",
            "n_rows": int(len(run.df)), "change_summary": None,
            "feature_ranges": _feature_ranges(run), "baseline": _baseline(run),
            "decision_threshold": (
                (run.result.get("artifacts") or {}).get("threshold_curve") or {}
            ).get("suggested"),
        }
        if version > 1:
            try:
                row["change_summary"] = self._change_summary(
                    self.get_registry_entry(model_id, version - 1), row
                )
            except Exception:
                pass  # a missing summary must not block registration
        values = [
            json.dumps(row[c], default=str) if c in self._REGISTRY_JSON_COLS else row[c]
            for c in self._REGISTRY_COLS
        ]
        with self._lock:
            self._db.execute(
                "UPDATE model_registry SET status = 'superseded' "
                "WHERE model_id = ? AND status = 'active'", (model_id,),
            )
            self._db.execute(
                f"INSERT INTO model_registry ({', '.join(self._REGISTRY_COLS)}) "
                f"VALUES ({', '.join('?' * len(self._REGISTRY_COLS))})",
                values,
            )
            self._db.commit()
        self.log_event(
            "system", "train", run_id=run.id, dataset_id=run.dataset_id,
            project_id=project_id,
            payload={"registry": {"model_id": model_id, "version": version,
                                  "checkpoint": bool(checkpoint_path)}},
        )
        return {"model_id": model_id, "version": version}

    def _registry_row_to_dict(self, row: tuple) -> dict:
        d = dict(zip(self._REGISTRY_COLS, row))
        for c in self._REGISTRY_JSON_COLS:
            if d.get(c):
                try:
                    d[c] = json.loads(d[c])
                except Exception:
                    pass
        return d

    def list_registry(self, project_id: str | None = None,
                      model_id: str | None = None) -> list[dict]:
        clauses, params = [], []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if model_id:
            clauses.append("model_id = ?")
            params.append(model_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.execute(
            f"SELECT {', '.join(self._REGISTRY_COLS)} FROM model_registry {where} "
            "ORDER BY approved_at DESC", params,
        ).fetchall()
        return [self._registry_row_to_dict(r) for r in rows]

    def get_registry_entry(self, model_id: str, version: int) -> dict:
        row = self._db.execute(
            f"SELECT {', '.join(self._REGISTRY_COLS)} FROM model_registry "
            "WHERE model_id = ? AND version = ?", (model_id, version),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown model version: {model_id} v{version}")
        return self._registry_row_to_dict(row)

    def set_decision_threshold(self, model_id: str, version: int, threshold: float) -> None:
        self.get_registry_entry(model_id, version)  # raises on unknown
        with self._lock:
            self._db.execute(
                "UPDATE model_registry SET decision_threshold = ? "
                "WHERE model_id = ? AND version = ?",
                (float(threshold), model_id, version),
            )
            self._db.commit()

    def archive_model(self, model_id: str, version: int) -> None:
        self.get_registry_entry(model_id, version)  # raises on unknown
        with self._lock:
            self._db.execute(
                "UPDATE model_registry SET status = 'archived' "
                "WHERE model_id = ? AND version = ?", (model_id, version),
            )
            self._db.commit()

    def registry_schemas(self, project_id: str) -> list[dict]:
        """Raw input schemas of active models - feeds the librarian's score route."""
        out = []
        for e in self.list_registry(project_id=project_id):
            if e["status"] == "active" and e.get("raw_columns"):
                out.append({
                    "model_id": e["model_id"], "version": e["version"],
                    "purpose": e.get("purpose_statement") or e.get("model_name"),
                    "columns": e["raw_columns"],
                })
        return out

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
        project_id: str | None = None,
    ) -> None:
        if project_id is None and dataset_id:
            ds = self.datasets.get(dataset_id)
            project_id = ds.project_id if ds else None
        with self._lock:
            self._db.execute(
                "INSERT INTO activity_log (ts, actor, event_type, dataset_id, "
                "artifact_id, run_id, provider, model, tokens_in, tokens_out, "
                "latency_ms, mode, payload, project_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts or _now(), actor, event_type, dataset_id, artifact_id,
                    run_id, provider, model, tokens_in, tokens_out, latency_ms,
                    mode, json.dumps(payload, default=str) if payload is not None else None,
                    project_id,
                ),
            )
            self._db.commit()

    _ACTIVITY_COLS = (
        "id", "ts", "actor", "event_type", "dataset_id", "artifact_id", "run_id",
        "provider", "model", "tokens_in", "tokens_out", "latency_ms", "mode", "payload",
        "project_id",
    )

    def list_activity(
        self,
        run_id: str | None = None,
        dataset_id: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 500,
        project_id: str | None = None,
    ) -> list[dict]:
        clauses, params = [], []
        for col, val in (
            ("run_id", run_id), ("dataset_id", dataset_id), ("event_type", event_type),
            ("project_id", project_id),
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

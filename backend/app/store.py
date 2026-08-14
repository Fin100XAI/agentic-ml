"""In-memory dataset/run store (POC — swap for a DB later)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pandas as pd

from engine.orchestrator import Run


@dataclass
class Dataset:
    df: pd.DataFrame
    filename: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class Store:
    def __init__(self) -> None:
        self.datasets: dict[str, Dataset] = {}
        self.runs: dict[str, Run] = {}

    def add_dataset(self, df: pd.DataFrame, filename: str) -> Dataset:
        ds = Dataset(df=df, filename=filename)
        self.datasets[ds.id] = ds
        return ds

    def get_dataset(self, dataset_id: str) -> Dataset:
        if dataset_id not in self.datasets:
            raise KeyError(f"Unknown dataset: {dataset_id}")
        return self.datasets[dataset_id]

    def add_run(self, run: Run) -> Run:
        self.runs[run.id] = run
        return run

    def get_run(self, run_id: str) -> Run:
        if run_id not in self.runs:
            raise KeyError(f"Unknown run: {run_id}")
        return self.runs[run_id]


store = Store()

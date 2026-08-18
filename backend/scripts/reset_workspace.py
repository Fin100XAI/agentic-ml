"""Start fresh: wipe ALL stored work - projects, datasets, runs, trained
models, intake rules, saved dictionary entries, the activity log, and every
stored artifact/checkpoint file.

Usage (from backend/, venv active):
    python scripts/reset_workspace.py            # asks for confirmation
    python scripts/reset_workspace.py --yes      # no prompt

The uploaded originals, derived artifacts and model checkpoints live in
artifact_store/; all metadata lives in data.db. Both are cleared. If the
backend is running while this executes, restart it afterwards - it keeps
loaded state in memory until restarted.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DB = BASE / "data.db"
ARTIFACTS = BASE / "artifact_store"


def main() -> None:
    if "--yes" not in sys.argv:
        answer = input(
            "This permanently deletes ALL projects, datasets, runs, trained "
            "models and the activity log. Type 'reset' to continue: "
        )
        if answer.strip().lower() != "reset":
            print("Aborted - nothing deleted.")
            return

    tables_cleared = 0
    rows_cleared = 0
    if DB.exists():
        db = sqlite3.connect(str(DB))
        tables = [r[0] for r in db.execute(
            "select name from sqlite_master where type='table' "
            "and name not like 'sqlite_%'"
        ).fetchall()]
        for t in tables:
            n = db.execute(f"select count(*) from {t}").fetchone()[0]
            db.execute(f"delete from {t}")
            rows_cleared += n
            tables_cleared += 1
            print(f"  cleared {t}: {n} row(s)")
        db.commit()
        db.execute("vacuum")
        db.close()

    files_removed = 0
    if ARTIFACTS.exists():
        for f in sorted(ARTIFACTS.rglob("*"), reverse=True):
            try:
                if f.is_file():
                    # Originals are stored read-only (rule 1); an explicit
                    # reset is the one place clearing that flag is intended.
                    f.chmod(0o666)
                    f.unlink()
                    files_removed += 1
                elif f.is_dir():
                    f.rmdir()
            except OSError as exc:
                print(f"  could not remove {f.name}: {exc}")

    print(f"\nDone: {rows_cleared} rows across {tables_cleared} tables, "
          f"{files_removed} stored files removed.")
    print("If the backend is running, restart it now (Ctrl+C, then rerun "
          "uvicorn) so its in-memory state matches the clean store.")


if __name__ == "__main__":
    main()

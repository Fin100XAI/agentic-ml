"""Unified activity log endpoints: filtered listing + CSV export."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter
from fastapi.responses import Response

from app.store import store

router = APIRouter()


@router.get("/activity")
def list_activity(
    run_id: str | None = None,
    dataset_id: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 500,
    project_id: str | None = None,
) -> dict:
    return {
        "events": store.list_activity(
            run_id=run_id, dataset_id=dataset_id, event_type=event_type,
            since=since, until=until, limit=limit, project_id=project_id,
        )
    }


@router.get("/activity.csv")
def export_activity_csv(
    run_id: str | None = None,
    dataset_id: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 5000,
    project_id: str | None = None,
) -> Response:
    events = store.list_activity(
        run_id=run_id, dataset_id=dataset_id, event_type=event_type,
        since=since, until=until, limit=limit, project_id=project_id,
    )
    buf = io.StringIO()
    cols = list(store._ACTIVITY_COLS)
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for e in reversed(events):  # chronological order reads naturally in Excel
        row = dict(e)
        if isinstance(row.get("payload"), (dict, list)):
            row["payload"] = json.dumps(row["payload"])
        writer.writerow(row)
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),  # BOM so Excel detects UTF-8
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="activity_log.csv"'},
    )

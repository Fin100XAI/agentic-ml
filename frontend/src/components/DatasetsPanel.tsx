// Your data: every dataset in the project with direct re-entry into the
// analytics board or the Ask screen. Fixes the navigation dead end where a
// board was only reachable by re-uploading the file.
import { useEffect, useState } from "react";
import { Compass, Database, MessageSquareText } from "lucide-react";
import { api } from "../api/client";

interface DatasetRow {
  id: string;
  filename: string;
  n_rows: number;
  pii_status?: string;
}

export function DatasetsPanel({
  projectId,
  onExplore,
  onAsk,
}: {
  projectId: string;
  onExplore: (datasetId: string, filename: string) => void;
  onAsk: (datasetId: string, filename: string) => void;
}) {
  const [datasets, setDatasets] = useState<DatasetRow[]>([]);

  useEffect(() => {
    api.getProjectDetail(projectId)
      .then((d) => setDatasets(d.datasets as DatasetRow[]))
      .catch(() => {});
  }, [projectId]);

  if (datasets.length === 0) return null;

  return (
    <div className="rounded-xl border border-edge bg-panel p-4 shadow-sm">
      <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-dim">
        <Database className="h-3.5 w-3.5 text-accent" /> Your data
      </h3>
      <p className="mt-0.5 text-[11px] text-ink-dim">
        Jump back into any uploaded file - the findings board and your question thread
        are one click away, no re-upload needed.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {datasets.slice(0, 12).map((ds) => {
          const gated = ds.pii_status === "pending";
          return (
            <div key={ds.id} className="rounded-lg border border-edge bg-panel-2/60 p-3">
              <p className="truncate text-xs font-semibold" title={ds.filename}>
                {ds.filename}
              </p>
              <p className="text-[10px] text-ink-dim">
                {ds.n_rows.toLocaleString()} rows
                {gated && " · privacy review pending"}
              </p>
              <div className="mt-2 flex gap-1.5">
                <button
                  onClick={() => onExplore(ds.id, ds.filename)}
                  disabled={gated}
                  className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-accent/30 bg-accent-soft/40 px-2 py-1 text-[11px] font-medium text-accent transition-colors hover:bg-accent-soft disabled:opacity-40"
                  title="Open the findings board for this file"
                >
                  <Compass className="h-3 w-3" /> Explore
                </button>
                <button
                  onClick={() => onAsk(ds.id, ds.filename)}
                  disabled={gated}
                  className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-edge bg-panel px-2 py-1 text-[11px] font-medium text-ink-dim transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40"
                  title="Ask this file a question"
                >
                  <MessageSquareText className="h-3 w-3" /> Ask
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

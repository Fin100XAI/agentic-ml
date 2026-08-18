// Indicators (P2.5): saved queries rendered as KPI cards on the project
// dashboard. This panel IS the auto-dashboard - re-run refreshes the number
// through the same deterministic executor, freshness is always shown.
import { useEffect, useState } from "react";
import { Gauge, RefreshCw, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { SavedQuery } from "../types";

export function IndicatorsPanel({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<SavedQuery[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api.listIndicators(projectId).then((r) => setItems(r.saved_queries)).catch(() => {});

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const rerun = async (sq: SavedQuery) => {
    setBusyId(sq.id);
    setError(null);
    try {
      await api.runIndicator(sq.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (sq: SavedQuery) => {
    await api.deleteIndicator(sq.id).catch(() => {});
    await load();
  };

  if (items.length === 0) return null;

  return (
    <div className="rounded-xl border border-edge bg-panel p-4 shadow-sm">
      <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-dim">
        <Gauge className="h-3.5 w-3.5 text-accent" /> Indicators
      </h3>
      <p className="mt-0.5 text-[11px] text-ink-dim">
        Saved questions, recomputed on demand - each card shows when its number was last
        refreshed from the data.
      </p>
      {error && <p className="mt-2 text-[11px] text-bad">{error}</p>}
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((sq) => {
          const first = sq.last_result?.table?.[0];
          const metricCol = sq.last_result?.columns.find(
            (c) => typeof first?.[c] === "number",
          );
          const value = metricCol != null ? first?.[metricCol] : null;
          return (
            <div key={sq.id} className="rounded-lg border border-edge bg-panel-2/60 p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="truncate text-xs font-semibold" title={sq.question || sq.name}>
                  {sq.name}
                </p>
                <span className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => rerun(sq)}
                    disabled={busyId === sq.id}
                    title="Recompute from the data"
                    className="rounded p-1 text-ink-dim hover:text-accent disabled:opacity-40"
                  >
                    <RefreshCw className={`h-3 w-3 ${busyId === sq.id ? "animate-spin" : ""}`} />
                  </button>
                  <button
                    onClick={() => remove(sq)}
                    title="Delete this indicator"
                    className="rounded p-1 text-ink-dim hover:text-bad"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </span>
              </div>
              <p className="mt-1 text-xl font-semibold tabular-nums text-ink">
                {typeof value === "number"
                  ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
                  : sq.last_result?.rows_out != null
                    ? `${sq.last_result.rows_out} row(s)`
                    : "-"}
              </p>
              <p className="truncate text-[10px] text-ink-dim" title={sq.last_result?.headline}>
                {sq.last_result?.headline}
              </p>
              <p className="mt-1 text-[9px] text-ink-dim">
                refreshed {sq.last_run_at ? sq.last_run_at.slice(0, 16).replace("T", " ") : "never"}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

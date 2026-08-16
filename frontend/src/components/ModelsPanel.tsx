// Models tab: every trained model version in the project - purpose, data
// hash, metric summary, status, retrain action and what-changed history.
// Nothing is ever overwritten.
import { useEffect, useState } from "react";
import { Boxes, History, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import type { RegistryEntry } from "../types";
import { Badge, Button, Card, CardBody, CardHeader } from "./ui";

const PRIMARY: Record<string, string> = {
  classification: "f1",
  regression: "rmse",
  clustering: "silhouette",
  forecasting: "mape_pct",
};

const STATUS_TONE = {
  active: "good",
  superseded: "neutral",
  archived: "warn",
} as const;

export function ModelsPanel({
  projectId,
  onRetrain,
}: {
  projectId: string;
  onRetrain?: (entry: RegistryEntry, datasetId: string) => void;
}) {
  const [models, setModels] = useState<RegistryEntry[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [retrainFor, setRetrainFor] = useState<RegistryEntry | null>(null);
  const [datasets, setDatasets] = useState<{ id: string; filename: string; n_rows: number }[]>([]);

  useEffect(() => {
    api.getProjectModels(projectId).then((r) => setModels(r.models)).catch(() => setModels([]));
  }, [projectId]);

  const openRetrain = (entry: RegistryEntry) => {
    setRetrainFor(entry);
    api.getProjectDetail(projectId).then((r) => setDatasets(r.datasets)).catch(() => setDatasets([]));
  };

  if (!models || models.length === 0) return null;

  return (
    <section>
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-ink-dim">
        <Boxes className="h-4 w-4" /> Models in this project
      </h3>
      <Card>
        <CardHeader
          title="Trained model versions"
          subtitle="Every completed training is registered with its purpose, exact data hash and settings. Old versions stay loadable - retraining creates a new version, never an overwrite."
        />
        <CardBody>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-[10px] uppercase tracking-wider text-ink-dim">
                  <th className="py-2 pr-3">Model</th>
                  <th className="py-2 pr-3">Purpose</th>
                  <th className="py-2 pr-3">Version</th>
                  <th className="py-2 pr-3">Score</th>
                  <th className="py-2 pr-3">Stability</th>
                  <th className="py-2 pr-3">Trained</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => {
                  const pk = PRIMARY[m.use_case];
                  const score = pk ? m.metrics?.[pk] : null;
                  const key = `${m.model_id}-${m.version}`;
                  return (
                    <>
                      <tr key={key} className="border-b border-edge/50">
                        <td
                          className="py-2 pr-3 font-medium"
                          title={`model ${m.model_id}\ntraining data sha256: ${m.data_sha256 ?? "n/a"}\nfeatures: ${(m.feature_list ?? []).join(", ")}`}
                        >
                          {m.model_name}
                        </td>
                        <td className="max-w-56 truncate py-2 pr-3 text-ink-dim" title={m.purpose_statement ?? ""}>
                          {m.purpose_statement || "-"}
                        </td>
                        <td className="py-2 pr-3 tabular-nums">v{m.version}</td>
                        <td className="py-2 pr-3 tabular-nums" title={pk}>
                          {score != null ? `${pk} ${score}` : "-"}
                        </td>
                        <td className="py-2 pr-3">
                          {m.stability_verdict && (
                            <Badge tone={m.stability_verdict === "stable" ? "good" : "warn"}>
                              {m.stability_verdict}
                            </Badge>
                          )}
                        </td>
                        <td className="whitespace-nowrap py-2 pr-3 tabular-nums text-ink-dim">
                          {m.approved_at.slice(0, 10)}
                        </td>
                        <td className="py-2 pr-3">
                          <Badge tone={STATUS_TONE[m.status] ?? "neutral"}>{m.status}</Badge>
                        </td>
                        <td className="py-2">
                          <span className="flex items-center gap-1">
                            {m.change_summary && (
                              <button
                                onClick={() => setExpanded(expanded === key ? null : key)}
                                title="What changed vs the previous version"
                                className="rounded-full border border-edge bg-white/50 p-1 text-ink-dim transition-colors hover:border-accent/40 hover:text-accent"
                              >
                                <History className="h-3 w-3" />
                              </button>
                            )}
                            {m.status === "active" && onRetrain && (
                              <button
                                onClick={() => openRetrain(m)}
                                title="Retrain on newer data - creates the next version"
                                className="rounded-full border border-edge bg-white/50 p-1 text-ink-dim transition-colors hover:border-accent/40 hover:text-accent"
                              >
                                <RefreshCw className="h-3 w-3" />
                              </button>
                            )}
                          </span>
                        </td>
                      </tr>
                      {expanded === key && m.change_summary && (
                        <tr key={`${key}-detail`} className="border-b border-edge/50 bg-white/40">
                          <td colSpan={8} className="px-3 py-2.5">
                            <ChangeSummary summary={m.change_summary} />
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Retrain: pick which dataset the next version trains on */}
          {retrainFor && (
            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-accent/40 bg-accent-soft/25 px-4 py-2.5">
              <span className="text-xs font-medium">
                Retrain {retrainFor.model_name} (v{retrainFor.version} → v{retrainFor.version + 1}) on:
              </span>
              <select
                id="retrain-ds"
                className="rounded-lg border border-edge bg-white/70 px-2 py-1 text-xs"
                defaultValue=""
              >
                <option value="" disabled>choose a dataset</option>
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename} ({d.n_rows.toLocaleString()} rows)
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                onClick={() => {
                  const sel = document.getElementById("retrain-ds") as HTMLSelectElement | null;
                  if (sel?.value && onRetrain) {
                    onRetrain(retrainFor, sel.value);
                    setRetrainFor(null);
                  }
                }}
              >
                Start retrain
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setRetrainFor(null)}>
                Cancel
              </Button>
              <span className="w-full text-[10px] text-ink-dim">
                The pipeline re-runs with this model's purpose and settings pre-filled - you still
                review and approve before anything trains. The old version stays loadable.
              </span>
            </div>
          )}
        </CardBody>
      </Card>
    </section>
  );
}

function ChangeSummary({ summary }: { summary: NonNullable<RegistryEntry["change_summary"]> }) {
  const s = summary;
  const settings = Object.entries(s.settings ?? {});
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-ink-dim">
      <span className="font-semibold text-ink">What changed vs v{s.from_version}:</span>
      <span>
        Data: {s.data.rows_before != null ? `${s.data.rows_before.toLocaleString()} → ` : ""}
        {s.data.rows_after.toLocaleString()} rows
        {s.data.same_data ? " (identical data)" : " (new data)"}
      </span>
      <span>
        Settings: {settings.length === 0
          ? "unchanged"
          : settings.map(([k, [a, b]]) => `${k} ${String(a)} → ${String(b)}`).join(", ")}
      </span>
      {s.metric && (
        <span>
          {s.metric.metric}: {s.metric.before} → {s.metric.after} (
          {s.metric.delta > 0 ? "+" : ""}
          {s.metric.delta})
        </span>
      )}
    </div>
  );
}

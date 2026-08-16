// Models tab: every trained model version in the project - purpose, data
// hash, metric summary, status. Nothing is ever overwritten.
import { useEffect, useState } from "react";
import { Boxes } from "lucide-react";
import { api } from "../api/client";
import type { RegistryEntry } from "../types";
import { Badge, Card, CardBody, CardHeader } from "./ui";

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

export function ModelsPanel({ projectId }: { projectId: string }) {
  const [models, setModels] = useState<RegistryEntry[] | null>(null);

  useEffect(() => {
    api.getProjectModels(projectId).then((r) => setModels(r.models)).catch(() => setModels([]));
  }, [projectId]);

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
                  <th className="py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => {
                  const pk = PRIMARY[m.use_case];
                  const score = pk ? m.metrics?.[pk] : null;
                  return (
                    <tr key={`${m.model_id}-${m.version}`} className="border-b border-edge/50">
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
                      <td className="py-2">
                        <Badge tone={STATUS_TONE[m.status] ?? "neutral"}>{m.status}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </section>
  );
}

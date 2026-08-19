// Popup: try hyperparameter combinations for every model, show what won.
import { FlaskConical, TrendingUp, X } from "lucide-react";
import type { Autotune } from "../types";
import { metricInfo } from "../lib/metricInfo";
import { BusyStatus } from "./Elapsed";
import { Badge, Button } from "./ui";

export function AutotuneModal({
  open,
  running,
  etaText,
  result,
  onClose,
  onApply,
}: {
  open: boolean;
  running: boolean;
  etaText: string;
  result: Autotune | null;
  onClose: () => void;
  onApply: () => void;
}) {
  if (!open) return null;
  const metric = result ? metricInfo(result.metric) : null;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm" onClick={running ? undefined : onClose} />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-edge bg-panel/90 p-6 shadow-2xl shadow-slate-900/20 backdrop-blur-2xl">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <FlaskConical className="h-4 w-4 text-accent" /> Auto-tune all models
          </h3>
          {!running && (
            <button onClick={onClose} className="rounded-lg p-1.5 text-ink-dim hover:bg-ink-dim/10 hover:text-ink">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {running ? (
          <div className="py-8">
            <BusyStatus
              running={running}
              label="Trying combinations for every model…"
              expected={etaText}
            />
            <p className="mt-2 text-center text-xs text-ink-dim">
              Each model tests up to 8 setting combinations, validated on held-back data.
            </p>
          </div>
        ) : result ? (
          <>
            <p className="mt-1 text-xs text-ink-dim">
              Each model tried up to 8 combinations around the suggested settings, scored by{" "}
              <span className="font-medium">{metric?.label}</span> on held-back data.
            </p>
            <div className="mt-4 overflow-hidden rounded-xl border border-edge">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-edge bg-panel-2 text-xs text-ink-dim">
                    <th className="px-4 py-2.5 font-medium">Model</th>
                    <th className="px-3 py-2.5 font-medium">Tried</th>
                    <th className="px-3 py-2.5 font-medium">Suggested</th>
                    <th className="px-3 py-2.5 font-medium">Best found</th>
                    <th className="px-3 py-2.5 font-medium">Gain</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.models).map(([key, m]) => (
                    <tr key={key} className="border-b border-edge/50 last:border-0">
                      <td className="px-4 py-2.5">
                        <div className="text-xs font-medium">{m.model_name}</div>
                        {m.error && <div className="text-[10px] text-bad">{m.error}</div>}
                      </td>
                      <td className="px-3 py-2.5 text-xs tabular-nums text-ink-dim">
                        {m.n_tried} in {m.elapsed_s}s
                      </td>
                      <td className="px-3 py-2.5 text-xs tabular-nums text-ink-dim">
                        {m.suggested_score ?? "-"}
                      </td>
                      <td className="px-3 py-2.5 text-xs font-semibold tabular-nums">
                        {m.best_score ?? "-"}
                      </td>
                      <td className="px-3 py-2.5">
                        {m.improvement_pct !== null && m.improvement_pct > 0 ? (
                          <Badge tone="good">
                            <TrendingUp className="mr-0.5 h-3 w-3" /> +{m.improvement_pct}%
                          </Badge>
                        ) : m.improvement_pct !== null ? (
                          <Badge tone="neutral">already optimal</Badge>
                        ) : (
                          <Badge tone="neutral">-</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[11px] leading-snug text-ink-dim">
              "Already optimal" means the data-suggested settings were not beaten - a good sign the
              suggestions fit your data. Tuned settings are now pre-filled everywhere.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={onClose}>
                Close
              </Button>
              <Button size="sm" onClick={onApply}>
                Use tuned settings
              </Button>
            </div>
          </>
        ) : null}
      </div>
    </>
  );
}

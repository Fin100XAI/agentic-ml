import { Bot, Download, Lightbulb, RotateCcw, SlidersHorizontal, Trophy } from "lucide-react";
import type { Comparison, Run } from "../../types";
import { metricInfo } from "../../lib/metricInfo";
import { InfoTip } from "../InfoTip";
import { api } from "../../api/client";
import { Badge, Button, Card, CardBody, CardHeader, Spinner } from "../ui";

export function CompareScreen({
  run,
  comparison,
  onTuneModel,
  onUseWinner,
  onStartOver,
  busy,
  busyLabel,
}: {
  run: Run;
  comparison: Comparison;
  onTuneModel: (modelKey: string) => void;
  onUseWinner: () => void;
  onStartOver: () => void;
  busy: boolean;
  busyLabel: string;
}) {
  const primary = comparison.primary_metric;
  const pInfo = metricInfo(primary);

  // Union of metric keys across all models, primary first.
  const metricKeys: string[] = [primary];
  for (const r of comparison.results) {
    for (const k of Object.keys(r.metrics)) {
      if (!metricKeys.includes(k) && !["n_train", "n_test", "n_observations", "holdout_size"].includes(k)) {
        metricKeys.push(k);
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Model comparison</h2>
          <Badge tone="accent">{comparison.use_case}</Badge>
          <span className="inline-flex items-center gap-1 text-xs text-ink-dim">
            ranked by {pInfo.label} ({comparison.higher_is_better ? "higher" : "lower"} wins)
            <InfoTip text={pInfo.explain} />
          </span>
        </div>
        <div className="flex items-center gap-2">
          {busy ? (
            <Spinner label={busyLabel} />
          ) : (
            comparison.best_model && (
              <Button size="sm" onClick={onUseWinner}>
                <Lightbulb className="h-3.5 w-3.5" /> Generate insights with the winner
              </Button>
            )
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => api.downloadReport(run.id, `analysis-report-${run.id}.md`)}
          >
            <Download className="h-3.5 w-3.5" /> Download report
          </Button>
          <Button variant="outline" size="sm" onClick={onStartOver}>
            <RotateCcw className="h-3.5 w-3.5" /> New dataset
          </Button>
        </div>
      </div>

      {/* Leaderboard */}
      <Card>
        <CardBody className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-edge text-xs text-ink-dim">
                <th className="px-5 py-3 font-medium">Rank</th>
                <th className="px-3 py-3 font-medium">Model</th>
                {metricKeys.map((k) => {
                  const info = metricInfo(k);
                  return (
                    <th key={k} className="px-3 py-3 font-medium">
                      <span className="inline-flex items-center gap-1">
                        {info.label}
                        <InfoTip text={info.explain} />
                      </span>
                    </th>
                  );
                })}
                <th className="px-3 py-3 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {comparison.results.map((r, i) => {
                const isBest = r.model_key === comparison.best_model;
                return (
                  <tr
                    key={r.model_key}
                    className={`border-b border-edge/50 last:border-0 ${isBest ? "bg-good/5" : ""}`}
                  >
                    <td className="px-5 py-3">
                      {isBest ? (
                        <span className="inline-flex items-center gap-1.5 font-semibold text-good">
                          <Trophy className="h-4 w-4" /> 1
                        </span>
                      ) : (
                        <span className="tabular-nums text-ink-dim">{i + 1}</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-medium">{r.model_name}</div>
                      {r.error ? (
                        <div className="mt-0.5 max-w-56 text-[11px] leading-snug text-bad">{r.error}</div>
                      ) : (
                        <div className="mt-0.5 max-w-56 truncate text-[11px] text-ink-dim" title={r.rationale}>
                          {r.rationale}
                        </div>
                      )}
                    </td>
                    {metricKeys.map((k) => (
                      <td
                        key={k}
                        className={`px-3 py-3 tabular-nums ${
                          k === primary ? "font-semibold" : "text-ink-dim"
                        }`}
                      >
                        {r.metrics[k] ?? "—"}
                      </td>
                    ))}
                    <td className="px-3 py-3">
                      {!r.error && (
                        <Button variant="outline" size="sm" onClick={() => onTuneModel(r.model_key)}>
                          <SlidersHorizontal className="h-3 w-3" /> Tune
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardBody>
      </Card>

      {/* Interpretation */}
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-accent" /> What this means
            </span>
          }
          right={
            <Badge tone={comparison.interpretation.generated_by === "claude" ? "accent" : "neutral"}>
              {comparison.interpretation.generated_by}
            </Badge>
          }
        />
        <CardBody>
          <p className="text-sm leading-relaxed">{comparison.interpretation.summary}</p>
          {comparison.interpretation.next_steps?.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {comparison.interpretation.next_steps.map((s, i) => (
                <li key={i} className="flex gap-2 text-sm text-ink-dim">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warn" />
                  {s}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

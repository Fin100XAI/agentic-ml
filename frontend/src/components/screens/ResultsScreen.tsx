import { Bot, Download, RotateCcw, SlidersHorizontal } from "lucide-react";
import type { Interpretation, Run, RunResult } from "../../types";
import { metricInfo } from "../../lib/metricInfo";
import { InfoTip } from "../InfoTip";
import { api } from "../../api/client";
import { ResultCharts } from "../charts";
import { Badge, Button, Card, CardBody, CardHeader } from "../ui";

const ASSESSMENT_TONE: Record<Interpretation["assessment"], "good" | "warn" | "bad" | "neutral"> = {
  strong: "good",
  moderate: "warn",
  weak: "bad",
  inconclusive: "neutral",
};

const ASSESSMENT_TEXT: Record<Interpretation["assessment"], string> = {
  strong: "The model performed well on your data.",
  moderate: "Decent results - tuning or another model may improve them.",
  weak: "The signal is weak - the data may not strongly predict this target.",
  inconclusive: "Not enough evidence to judge - check the metrics below.",
};

export function ResultsScreen({
  run,
  result,
  interpretation,
  onTuneAgain,
  onStartOver,
}: {
  run: Run;
  result: RunResult;
  interpretation: Interpretation | null;
  onTuneAgain: () => void;
  onStartOver: () => void;
}) {
  const metrics = Object.entries(result.metrics).filter(([, v]) => v !== null);

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">{run.config?.model_name}</h2>
          <Badge tone="accent">{run.config?.use_case}</Badge>
          {interpretation && (
            <span className="inline-flex items-center gap-1">
              <Badge tone={ASSESSMENT_TONE[interpretation.assessment]}>
                {interpretation.assessment}
              </Badge>
              <InfoTip text={ASSESSMENT_TEXT[interpretation.assessment]} />
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => api.downloadReport(run.id, `analysis-report-${run.id}.md`)}
          >
            <Download className="h-3.5 w-3.5" /> Download report
          </Button>
          <Button variant="outline" size="sm" onClick={onTuneAgain}>
            <SlidersHorizontal className="h-3.5 w-3.5" /> Tune & re-run
          </Button>
          <Button variant="outline" size="sm" onClick={onStartOver}>
            <RotateCcw className="h-3.5 w-3.5" /> New dataset
          </Button>
        </div>
      </div>

      {/* Metrics with explanations */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        {metrics.map(([k, v]) => {
          const info = metricInfo(k);
          return (
            <div key={k} className="rounded-lg border border-edge bg-panel-2 px-3 py-2">
              <div className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-ink-dim">
                {info.label}
                <InfoTip text={info.explain} />
              </div>
              <div className="mt-0.5 text-lg font-semibold tabular-nums">{String(v)}</div>
            </div>
          );
        })}
      </div>

      {/* Interpretation */}
      {interpretation && (
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-accent" /> What this means
              </span>
            }
            right={
              <Badge tone={interpretation.generated_by === "claude" ? "accent" : "neutral"}>
                {interpretation.generated_by}
              </Badge>
            }
          />
          <CardBody>
            <p className="text-sm leading-relaxed">{interpretation.summary}</p>
            <div className="mt-4 grid gap-6 md:grid-cols-2">
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-dim">
                  Highlights
                </h4>
                <ul className="space-y-1.5">
                  {interpretation.highlights.map((h, i) => (
                    <li key={i} className="flex gap-2 text-sm text-ink-dim">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-good" />
                      {h}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-dim">
                  What to do next
                </h4>
                <ul className="space-y-1.5">
                  {interpretation.next_steps.map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-ink-dim">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warn" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Charts */}
      <ResultCharts result={result} />
    </div>
  );
}

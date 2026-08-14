import { Bot, RotateCcw, SlidersHorizontal } from "lucide-react";
import type { Interpretation, Run, RunResult } from "../../types";
import { ResultCharts } from "../charts";
import { Badge, Button, Card, CardBody, CardHeader, Stat } from "../ui";

const ASSESSMENT_TONE: Record<Interpretation["assessment"], "good" | "warn" | "bad" | "neutral"> = {
  strong: "good",
  moderate: "warn",
  weak: "bad",
  inconclusive: "neutral",
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
      {/* Header row: model + actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">{run.config?.model_name}</h2>
          <Badge tone="accent">{run.config?.use_case}</Badge>
          {interpretation && (
            <Badge tone={ASSESSMENT_TONE[interpretation.assessment]}>
              {interpretation.assessment}
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onTuneAgain}>
            <SlidersHorizontal className="h-3.5 w-3.5" /> Tune & re-run
          </Button>
          <Button variant="outline" size="sm" onClick={onStartOver}>
            <RotateCcw className="h-3.5 w-3.5" /> New dataset
          </Button>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        {metrics.map(([k, v]) => (
          <Stat key={k} label={k.replace(/_/g, " ")} value={String(v)} />
        ))}
      </div>

      {/* Interpretation */}
      {interpretation && (
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-accent" /> Interpretation agent
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
                  Suggested next steps
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

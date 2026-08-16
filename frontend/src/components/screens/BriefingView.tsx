// Read-only policy-maker briefing: the decision brief, trust panel, key
// charts and Ask-the-Data - nothing else. Reached via #/brief/{runId};
// exposes no analyst controls and makes no mutating API calls (the grounded
// Q&A ask is the only POST). Prints cleanly.
import { useEffect, useState } from "react";
import { AlertTriangle, BrainCircuit, ListChecks, Printer, ShieldCheck } from "lucide-react";
import { api } from "../../api/client";
import type { Run } from "../../types";
import { AskTheData } from "../AskTheData";
import {
  ClassDistributionChart,
  ClusterScatter,
  ForecastChart,
  PredictedVsActualChart,
} from "../charts";
import { Badge, Button, Card, CardBody, CardHeader } from "../ui";

const EVIDENCE_TONE = { strong: "good", moderate: "warn", limited: "bad" } as const;

export function BriefingView({ runId }: { runId: string }) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getRun(runId).then(setRun).catch((e) => setError(String(e?.message ?? e)));
  }, [runId]);

  if (error) {
    return (
      <div className="mx-auto max-w-xl px-6 py-16 text-center text-sm text-ink-dim">
        This briefing could not be loaded ({error}). Ask the analyst who shared it to check the link.
      </div>
    );
  }
  const insights = run?.insights;
  if (!run || !insights) {
    return (
      <div className="mx-auto max-w-xl px-6 py-16 text-center text-sm text-ink-dim">
        {run ? "This analysis has no decision brief yet." : "Loading the briefing…"}
      </div>
    );
  }
  const brief = insights.brief;
  const ev = insights.evidence;
  const a = run.result?.artifacts ?? {};
  const weak = insights.trust_tier === "weak";

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      {/* Title block */}
      <div className="rounded-2xl border border-edge bg-panel px-6 py-5 backdrop-blur-xl">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-accent">
            <BrainCircuit className="h-5 w-5" />
            <span className="text-xs font-semibold uppercase tracking-widest">Decision briefing</span>
          </div>
          <Button variant="outline" size="sm" className="no-print" onClick={() => window.print()}>
            <Printer className="h-3.5 w-3.5" /> Print
          </Button>
        </div>
        <h1 className="mt-2 text-lg font-bold leading-snug">{run.question || "Data analysis"}</h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-dim">
          <span>{run.filename}</span>
          {run.profile && <span>{run.profile.n_rows.toLocaleString()} records</span>}
          <Badge tone={EVIDENCE_TONE[ev.level]}>evidence: {ev.level}</Badge>
        </div>
      </div>

      {/* Executive summary */}
      <Card className="border-accent/30">
        <CardHeader title="Executive summary" />
        <CardBody>
          <p className="text-sm leading-relaxed">{brief.executive_summary}</p>
        </CardBody>
      </Card>

      {/* Key findings */}
      <section className="space-y-3">
        {insights.findings.map((f, i) => (
          <Card key={i}>
            <CardBody className="py-3">
              <h4 className="break-words text-sm font-semibold leading-snug">{f.headline}</h4>
              <p className="mt-1 break-words text-xs leading-relaxed text-ink-dim">{f.detail}</p>
            </CardBody>
          </Card>
        ))}
      </section>

      {/* The headline picture */}
      <div className="rounded-xl border border-edge bg-panel p-4 backdrop-blur-xl">
        {insights.use_case === "classification" && a.class_distribution && (
          <ClassDistributionChart data={a.class_distribution} />
        )}
        {insights.use_case === "regression" && a.predicted_vs_actual && (
          <PredictedVsActualChart points={a.predicted_vs_actual.points} />
        )}
        {insights.use_case === "clustering" && a.scatter && (
          <ClusterScatter points={a.scatter.points} axes={a.scatter.axes} />
        )}
        {insights.use_case === "forecasting" && a.series && a.forecast && (
          <ForecastChart
            series={a.series}
            forecast={a.forecast}
            uncertaintyPct={run.result?.metrics.mape_pct ?? null}
            context={a.context_series}
          />
        )}
      </div>

      {/* Actions / hypotheses + trust */}
      <Card className={weak ? "border-warn/40" : "border-good/30"}>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <ListChecks className={`h-4 w-4 ${weak ? "text-warn" : "text-good"}`} />
              {weak ? "Hypotheses to verify" : "Recommended actions"}
            </span>
          }
        />
        <CardBody>
          {weak && (
            <p className="mb-3 rounded-xl border border-warn/40 bg-warn/10 px-3.5 py-2.5 text-xs leading-relaxed">
              <span className="font-semibold">Evidence is weak for this analysis.</span> The items
              below are leads to verify with more data or a pilot - not recommendations to act on yet.
            </p>
          )}
          <ol className="space-y-2.5">
            {brief.recommended_actions.map((act, i) => (
              <li key={i} className="flex gap-2.5 text-sm">
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                  weak ? "bg-warn/15 text-warn" : "bg-good/15 text-good"
                }`}>
                  {i + 1}
                </span>
                <span className="min-w-0 break-words leading-relaxed">{act}</span>
              </li>
            ))}
          </ol>
        </CardBody>
      </Card>

      <Card className="border-warn/30">
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-warn" /> How much to trust this
            </span>
          }
        />
        <CardBody>
          <p className="text-sm">
            <span className="font-semibold capitalize">{ev.level} evidence.</span> {ev.reason}
          </p>
          <ul className="mt-3 space-y-1.5">
            {[...ev.caveats, ...brief.watch_outs.filter((w) => !ev.caveats.includes(w))].map((c, i) => (
              <li key={i} className="flex gap-2 text-xs text-ink-dim">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
                <span className="min-w-0 break-words">{c}</span>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>

      {/* Grounded Q&A - the only interactive element */}
      <div className="no-print">
        <AskTheData runId={run.id} rows={run.profile?.n_rows ?? 0} />
      </div>

      <p className="pb-4 text-center text-[10px] text-ink-dim">
        Read-only briefing generated by the Agentic ML Workbench · run {run.id}
      </p>
    </div>
  );
}

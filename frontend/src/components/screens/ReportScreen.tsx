// Full in-app report: everything a stakeholder needs on one printable page.
import {
  AlertTriangle,
  ArrowLeft,
  Download,
  FileText,
  Printer,
} from "lucide-react";
import type { Run } from "../../types";
import { metricInfo } from "../../lib/metricInfo";
import { api } from "../../api/client";
import { ResultCharts } from "../charts";
import { Badge, Button, Card, CardBody } from "../ui";

const EVIDENCE_TONE = { strong: "good", moderate: "warn", limited: "bad" } as const;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid">
      <h3 className="mb-3 border-b border-edge pb-1.5 text-sm font-semibold uppercase tracking-wider text-ink-dim">
        {title}
      </h3>
      {children}
    </section>
  );
}

export function ReportScreen({ run, onBack }: { run: Run; onBack: () => void }) {
  const insights = run.insights;
  const brief = insights?.brief;
  const ev = insights?.evidence;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      {/* Toolbar (hidden when printing) */}
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <Button variant="outline" size="sm" onClick={onBack}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </Button>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="h-3.5 w-3.5" /> Print / save as PDF
          </Button>
          <Button size="sm" onClick={() => api.downloadReportPdf(run.id)}>
            <Download className="h-3.5 w-3.5" /> Download PDF
          </Button>
          <Button variant="outline" size="sm" onClick={() => api.downloadReport(run.id, `decision-brief-${run.id}.md`)}>
            <Download className="h-3.5 w-3.5" /> Markdown
          </Button>
        </div>
      </div>

      {/* Title block */}
      <div className="rounded-2xl border border-edge bg-panel px-8 py-6 backdrop-blur-xl">
        <div className="flex items-center gap-2 text-accent">
          <FileText className="h-5 w-5" />
          <span className="text-xs font-semibold uppercase tracking-widest">Decision report</span>
        </div>
        <h1 className="mt-2 text-xl font-bold">{run.question || "Data analysis"}</h1>
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-dim">
          <span>Dataset: {run.filename}</span>
          {run.profile && (
            <span>
              {run.profile.n_rows.toLocaleString()} rows × {run.profile.n_cols} columns
            </span>
          )}
          <span>Run {run.id}</span>
          {ev && (
            <Badge tone={EVIDENCE_TONE[ev.level]}>evidence: {ev.level}</Badge>
          )}
        </div>
      </div>

      {/* Executive summary */}
      {brief && (
        <Section title="Executive summary">
          <p className="text-sm leading-relaxed">{brief.executive_summary}</p>
        </Section>
      )}

      {/* Key findings */}
      {insights && insights.findings.length > 0 && (
        <Section title="Key findings">
          <div className="space-y-3">
            {insights.findings.map((f, i) => (
              <div key={i} className="rounded-xl border border-edge bg-panel px-4 py-3 backdrop-blur-xl">
                <h4 className="text-sm font-semibold leading-snug">{f.headline}</h4>
                <p className="mt-1 text-xs leading-relaxed text-ink-dim">{f.detail}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Segments */}
      {insights?.segments && insights.segments.length > 0 && (
        <Section title="Segment profiles">
          <div className="grid gap-3 sm:grid-cols-2">
            {insights.segments.map((s) => (
              <div key={s.cluster} className="rounded-xl border border-edge bg-panel px-4 py-3 backdrop-blur-xl">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">{s.name}</span>
                  <Badge tone={s.cluster === -1 ? "warn" : "accent"}>
                    {s.share_pct}% · {s.count.toLocaleString()}
                  </Badge>
                </div>
                <ul className="mt-2 space-y-1">
                  {s.traits.map((t) => (
                    <li key={t.feature} className="flex justify-between gap-2 text-xs">
                      <span className="min-w-0 truncate text-ink-dim" title={`raw column: ${t.feature}`}>
                        {t.label ?? t.feature}
                      </span>
                      <span className="shrink-0 tabular-nums">
                        {t.direction === "above" ? "▲" : "▼"} {t.value}{" "}
                        <span className="text-ink-dim">(avg {t.overall})</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Outlook */}
      {insights?.outlook && (
        <Section title="Outlook">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Direction", insights.outlook.direction],
              [`Projected (next ${insights.outlook.horizon})`, insights.outlook.projected_total.toLocaleString()],
              [
                "Change",
                insights.outlook.delta_pct === null
                  ? "-"
                  : `${insights.outlook.delta_pct >= 0 ? "+" : ""}${insights.outlook.delta_pct}%`,
              ],
              ["Typical error", insights.outlook.uncertainty_pct === null ? "-" : `±${insights.outlook.uncertainty_pct}%`],
            ].map(([label, value]) => (
              <div key={String(label)} className="min-w-0 rounded-xl border border-edge bg-panel-2 px-3 py-2 backdrop-blur">
                <div className="truncate text-[11px] uppercase tracking-wider text-ink-dim">{label}</div>
                <div className="mt-0.5 truncate text-lg font-semibold tabular-nums">{value}</div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Actions + trust */}
      {brief && (
        <div className="grid gap-6 md:grid-cols-2">
          <Section title="Recommended actions">
            <ol className="space-y-2">
              {brief.recommended_actions.map((a, i) => (
                <li key={i} className="flex gap-2.5 text-sm">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-good/15 text-[11px] font-semibold text-good">
                    {i + 1}
                  </span>
                  <span className="min-w-0 break-words leading-relaxed">{a}</span>
                </li>
              ))}
            </ol>
          </Section>
          {ev && (
            <Section title="How much to trust this">
              <p className="text-sm leading-relaxed">
                <span className="font-semibold capitalize">{ev.level} evidence.</span> {ev.reason}
              </p>
              <ul className="mt-2 space-y-1.5">
                {[...ev.caveats, ...brief.watch_outs.filter((w) => !ev.caveats.includes(w))].map((c, i) => (
                  <li key={i} className="flex gap-2 text-xs text-ink-dim">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
                    <span className="min-w-0 break-words">{c}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      )}

      {/* Data overview */}
      {run.eda && (
        <Section title="About the data">
          <p className="text-sm leading-relaxed text-ink-dim">{run.eda.summary}</p>
        </Section>
      )}

      {/* Method + charts appendix */}
      {run.config && run.result && (
        <Section title={`Charts & method (${run.config.model_name})`}>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(run.result.metrics)
              .filter(([, v]) => v !== null)
              .slice(0, 8)
              .map(([k, v]) => (
                <div key={k} className="min-w-0 rounded-xl border border-edge bg-panel-2 px-3 py-2 backdrop-blur">
                  <div className="truncate text-[11px] uppercase tracking-wider text-ink-dim">
                    {metricInfo(k).label}
                  </div>
                  <div className="mt-0.5 truncate text-lg font-semibold tabular-nums">{String(v)}</div>
                </div>
              ))}
          </div>
          <ResultCharts result={run.result} />
        </Section>
      )}

      {/* Decision log */}
      <Section title="How this analysis was made">
        <Card>
          <CardBody className="p-0">
            {run.decisions.map((d, i) => (
              <div
                key={i}
                className="flex items-center justify-between gap-3 border-b border-edge/50 px-5 py-2.5 last:border-0"
              >
                <div className="min-w-0">
                  <span className="text-xs font-medium">{d.title}</span>
                  {d.detail && (
                    <span className="ml-2 truncate text-[11px] text-ink-dim">{d.detail}</span>
                  )}
                </div>
                <Badge
                  tone={
                    d.status === "done" || d.status === "approved"
                      ? "good"
                      : d.status === "error"
                        ? "bad"
                        : "neutral"
                  }
                >
                  {d.status}
                </Badge>
              </div>
            ))}
          </CardBody>
        </Card>
      </Section>

      <p className="pb-8 text-center text-[11px] text-ink-dim">
        Generated by Agentic ML Workbench · numbers computed deterministically from your data
      </p>
    </div>
  );
}

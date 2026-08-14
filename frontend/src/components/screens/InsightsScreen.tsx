// Decision-first results: executive brief, findings, drivers/segments/outlook,
// recommended actions, evidence strength — model diagnostics in an appendix.
import { useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  ListChecks,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp,
  Minus,
} from "lucide-react";
import type { Driver, Insights, Interpretation, Run, RunResult, Segment } from "../../types";
import { metricInfo } from "../../lib/metricInfo";
import { InfoTip } from "../InfoTip";
import { api } from "../../api/client";
import { ResultCharts } from "../charts";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge, Button, Card, CardBody, CardHeader } from "../ui";

const EVIDENCE_TONE = { strong: "good", moderate: "warn", limited: "bad" } as const;
const EVIDENCE_TEXT = {
  strong: "The patterns are reliable enough to act on.",
  moderate: "Real patterns, but verify before big commitments.",
  limited: "Treat as hypotheses — gather more data before acting.",
} as const;

function DriverChart({ driver }: { driver: Driver }) {
  const max = Math.max(...driver.groups.map((g) => g.rate_pct), 1);
  return (
    <div className="rounded-xl border border-edge bg-panel p-4">
      <div className="mb-1 flex items-center justify-between">
        <h4 className="text-xs font-semibold">{driver.feature}</h4>
        {driver.lift && <Badge tone="accent">{driver.lift}× spread</Badge>}
      </div>
      <p className="mb-3 text-[11px] text-ink-dim">outcome rate per group</p>
      <ResponsiveContainer width="100%" height={Math.max(120, driver.groups.length * 34)}>
        <BarChart data={driver.groups} layout="vertical" margin={{ left: 8, right: 40 }}>
          <CartesianGrid stroke="#1e293b" horizontal={false} />
          <XAxis type="number" hide domain={[0, max * 1.15]} />
          <YAxis
            type="category"
            dataKey="label"
            width={90}
            tick={{ fill: "#8b96a8", fontSize: 10 }}
            stroke="#1e293b"
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#111827", border: "1px solid #263042", borderRadius: 8, fontSize: 12 }}
            formatter={(v) => [`${v}% of group`, "rate"]}
            cursor={{ fill: "#1a2332" }}
          />
          <Bar dataKey="rate_pct" radius={[0, 4, 4, 0]} label={{ position: "right", fill: "#e5eaf2", fontSize: 10, formatter: (v) => `${v}%` }}>
            {driver.groups.map((g, i) => (
              <Cell key={i} fill={g.rate_pct === max ? "#f87171" : "#4f8ef7"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SegmentCard({ segment }: { segment: Segment }) {
  const isOutlier = segment.cluster === -1;
  return (
    <div className={`rounded-xl border p-4 ${isOutlier ? "border-warn/40 bg-warn/5" : "border-edge bg-panel"}`}>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">{segment.name}</h4>
        <Badge tone={isOutlier ? "warn" : "accent"}>
          {segment.share_pct}% · {segment.count.toLocaleString()}
        </Badge>
      </div>
      {segment.traits.length > 0 ? (
        <ul className="mt-3 space-y-1.5">
          {segment.traits.map((t) => (
            <li key={t.feature} className="flex items-center justify-between text-xs">
              <span className="text-ink-dim">{t.feature}</span>
              <span className={`font-medium tabular-nums ${t.direction === "above" ? "text-good" : "text-warn"}`}>
                {t.direction === "above" ? "▲" : "▼"} {t.value}
                <span className="ml-1 text-[10px] text-ink-dim">(avg {t.overall})</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-[11px] text-ink-dim">
          {isOutlier ? "Records that don't match any pattern — review individually." : "Close to the overall average."}
        </p>
      )}
    </div>
  );
}

function OutlookTiles({ insights }: { insights: Insights }) {
  const o = insights.outlook;
  if (!o) return null;
  const DirIcon = o.direction === "rising" ? TrendingUp : o.direction === "falling" ? TrendingDown : Minus;
  const tiles = [
    {
      label: "Direction",
      value: (
        <span className="flex items-center gap-1.5">
          <DirIcon className={`h-4 w-4 ${o.direction === "rising" ? "text-good" : o.direction === "falling" ? "text-bad" : "text-ink-dim"}`} />
          {o.direction}
        </span>
      ),
    },
    { label: `Projected total (next ${o.horizon})`, value: o.projected_total.toLocaleString() },
    {
      label: `vs last ${o.horizon} periods`,
      value: o.delta_pct === null ? "—" : `${o.delta_pct >= 0 ? "+" : ""}${o.delta_pct}%`,
    },
    { label: "Typical error", value: o.uncertainty_pct === null ? "—" : `±${o.uncertainty_pct}%` },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border border-edge bg-panel-2 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wider text-ink-dim">{t.label}</div>
          <div className="mt-0.5 text-lg font-semibold tabular-nums">{t.value}</div>
        </div>
      ))}
    </div>
  );
}

export function InsightsScreen({
  run,
  insights,
  result,
  interpretation,
  onTuneAgain,
  onStartOver,
}: {
  run: Run;
  insights: Insights;
  result: RunResult;
  interpretation: Interpretation | null;
  onTuneAgain: () => void;
  onStartOver: () => void;
}) {
  const [showAppendix, setShowAppendix] = useState(false);
  const brief = insights.brief;
  const ev = insights.evidence;
  const metrics = Object.entries(result.metrics).filter(([, v]) => v !== null);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Decision brief</h2>
          <Badge tone="accent">{insights.use_case}</Badge>
          <span className="inline-flex items-center gap-1">
            <Badge tone={EVIDENCE_TONE[ev.level]}>evidence: {ev.level}</Badge>
            <InfoTip text={EVIDENCE_TEXT[ev.level]} />
          </span>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => api.downloadReport(run.id, `decision-brief-${run.id}.md`)}>
            <Download className="h-3.5 w-3.5" /> Download brief
          </Button>
          <Button variant="outline" size="sm" onClick={onTuneAgain}>
            <SlidersHorizontal className="h-3.5 w-3.5" /> Adjust analysis
          </Button>
          <Button variant="outline" size="sm" onClick={onStartOver}>
            <RotateCcw className="h-3.5 w-3.5" /> New dataset
          </Button>
        </div>
      </div>

      {/* Executive summary */}
      <Card className="border-accent/30">
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-accent" /> Executive summary
            </span>
          }
          right={<Badge tone={brief.generated_by === "claude" ? "accent" : "neutral"}>{brief.generated_by}</Badge>}
        />
        <CardBody>
          <p className="text-sm leading-relaxed">{brief.executive_summary}</p>
        </CardBody>
      </Card>

      {/* Findings */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
          Key findings
        </h3>
        <div className="grid gap-4 md:grid-cols-2">
          {insights.findings.map((f, i) => (
            <Card key={i}>
              <CardBody>
                <h4 className="text-sm font-semibold leading-snug">{f.headline}</h4>
                <p className="mt-1.5 text-xs leading-relaxed text-ink-dim">{f.detail}</p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      {/* Use-case specific evidence */}
      {insights.drivers && insights.drivers.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
            What drives the outcome
          </h3>
          <div className="grid gap-4 md:grid-cols-2">
            {insights.drivers.map((d) => (
              <DriverChart key={d.feature} driver={d} />
            ))}
          </div>
        </section>
      )}

      {insights.segments && insights.segments.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
            Segment profiles
          </h3>
          <div className="grid gap-4 md:grid-cols-3">
            {insights.segments.map((s) => (
              <SegmentCard key={s.cluster} segment={s} />
            ))}
          </div>
        </section>
      )}

      {insights.outlook && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
            Outlook
          </h3>
          <OutlookTiles insights={insights} />
        </section>
      )}

      {/* Actions + trust, side by side */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-good/30">
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <ListChecks className="h-4 w-4 text-good" /> Recommended actions
              </span>
            }
          />
          <CardBody>
            <ol className="space-y-2.5">
              {brief.recommended_actions.map((a, i) => (
                <li key={i} className="flex gap-2.5 text-sm">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-good/15 text-[11px] font-semibold text-good">
                    {i + 1}
                  </span>
                  <span className="leading-relaxed">{a}</span>
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
            <p className="text-sm leading-relaxed">
              <span className="font-semibold capitalize">{ev.level} evidence.</span> {ev.reason}
            </p>
            <ul className="mt-3 space-y-1.5">
              {[...ev.caveats, ...brief.watch_outs.filter((w) => !ev.caveats.includes(w))].map((c, i) => (
                <li key={i} className="flex gap-2 text-xs text-ink-dim">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
                  {c}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      </div>

      {/* Technical appendix (collapsed by default) */}
      <div className="rounded-xl border border-edge bg-panel/50">
        <button
          onClick={() => setShowAppendix((s) => !s)}
          className="flex w-full items-center justify-between px-5 py-3 text-left"
        >
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-dim">
            Technical appendix — {run.config?.model_name} diagnostics
          </span>
          {showAppendix ? (
            <ChevronDown className="h-4 w-4 text-ink-dim" />
          ) : (
            <ChevronRight className="h-4 w-4 text-ink-dim" />
          )}
        </button>
        {showAppendix && (
          <div className="space-y-6 border-t border-edge px-5 py-5">
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
            {interpretation && (
              <p className="text-sm leading-relaxed text-ink-dim">{interpretation.summary}</p>
            )}
            <ResultCharts result={result} />
          </div>
        )}
      </div>
    </div>
  );
}

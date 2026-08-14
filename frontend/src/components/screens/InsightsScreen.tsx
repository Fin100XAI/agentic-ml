// Stakeholder results: tabbed Decision brief / Technical appendix, stat tiles,
// headline charts, recommended actions, trust panel, and ask-the-data chat.
import { useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Download,
  FileText,
  Layers,
  ListChecks,
  Minus,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";
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
import type { Driver, Insights, Interpretation, Run, RunResult, Segment } from "../../types";
import { metricInfo } from "../../lib/metricInfo";
import { InfoTip } from "../InfoTip";
import { api } from "../../api/client";
import { AskTheData } from "../AskTheData";
import { ClassDistributionChart, ClusterScatter, ForecastChart, ResultCharts } from "../charts";
import { Badge, Button, Card, CardBody, CardHeader } from "../ui";

const EVIDENCE_TEXT = {
  strong: "The patterns are reliable enough to act on.",
  moderate: "Real patterns, but verify before big commitments.",
  limited: "Treat as hypotheses - gather more data before acting.",
} as const;

function DriverChart({ driver }: { driver: Driver }) {
  const max = Math.max(...driver.groups.map((g) => g.rate_pct), 1);
  return (
    <div className="min-w-0 rounded-xl border border-edge bg-panel p-4 backdrop-blur-xl">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h4 className="min-w-0 truncate text-xs font-semibold" title={`raw column: ${driver.feature}`}>
          {driver.label ?? driver.feature}
        </h4>
        {driver.lift && <Badge tone="accent">{driver.lift}× spread</Badge>}
      </div>
      <p className="mb-3 text-[11px] text-ink-dim">
        Outcome rate per group - red is the highest-risk group, where action matters most.
      </p>
      <ResponsiveContainer width="100%" height={Math.max(120, driver.groups.length * 34)}>
        <BarChart data={driver.groups} layout="vertical" margin={{ left: 8, right: 40 }}>
          <CartesianGrid stroke="#dde3ee" horizontal={false} />
          <XAxis type="number" hide domain={[0, max * 1.15]} />
          <YAxis
            type="category"
            dataKey="label"
            width={90}
            tick={{ fill: "#64748b", fontSize: 10 }}
            stroke="#dde3ee"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "rgba(255,255,255,0.95)",
              border: "1px solid #dde3ee",
              borderRadius: 10,
              fontSize: 12,
              color: "#0f172a",
            }}
            formatter={(v) => [`${v}% of group`, "rate"]}
            cursor={{ fill: "rgba(79,70,229,0.06)" }}
          />
          <Bar
            dataKey="rate_pct"
            radius={[0, 4, 4, 0]}
            label={{ position: "right", fill: "#0f172a", fontSize: 10, formatter: (v) => `${v}%` }}
          >
            {driver.groups.map((g, i) => (
              <Cell key={i} fill={g.rate_pct === max ? "#dc2626" : "#4f46e5"} />
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
    <div className={`min-w-0 rounded-xl border p-4 backdrop-blur-xl ${isOutlier ? "border-warn/40 bg-warn/5" : "border-edge bg-panel"}`}>
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{segment.name}</h4>
        <Badge tone={isOutlier ? "warn" : "accent"}>
          {segment.share_pct}% · {segment.count.toLocaleString()}
        </Badge>
      </div>
      {segment.traits.length > 0 ? (
        <ul className="mt-3 space-y-1.5">
          {segment.traits.map((t) => (
            <li key={t.feature} className="flex items-center justify-between gap-2 text-xs">
              <span className="min-w-0 truncate text-ink-dim" title={`raw column: ${t.feature}`}>
                {t.label ?? t.feature}
              </span>
              <span className={`shrink-0 font-medium tabular-nums ${t.direction === "above" ? "text-good" : "text-warn"}`}>
                {t.direction === "above" ? "▲" : "▼"} {t.value}
                <span className="ml-1 text-[10px] text-ink-dim">(avg {t.overall})</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-[11px] text-ink-dim">
          {isOutlier ? "Records that don't match any pattern - review individually." : "Close to the overall average."}
        </p>
      )}
    </div>
  );
}

function Tile({ label, value, tip }: { label: string; value: React.ReactNode; tip?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-edge bg-panel px-4 py-3 backdrop-blur-xl">
      <div className="flex items-center gap-1 truncate text-[11px] uppercase tracking-wider text-ink-dim">
        {label}
        {tip && <InfoTip text={tip} />}
      </div>
      <div className="mt-1 truncate text-xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

/** Headline number tiles, tailored per use case. */
function StatTiles({ run, insights, result }: { run: Run; insights: Insights; result: RunResult }) {
  const ev = insights.evidence;
  const tiles: { label: string; value: React.ReactNode; tip?: string }[] = [
    {
      label: "Records analyzed",
      value: run.profile?.n_rows.toLocaleString() ?? "-",
      tip: "Rows in the uploaded dataset.",
    },
  ];

  if (insights.use_case === "classification") {
    const m = insights.outcome_summary.match(/([\d.]+)%/);
    if (m) tiles.push({ label: "Baseline outcome rate", value: `${m[1]}%`, tip: "Share of records with the outcome today - the number your actions would move." });
    const top = insights.drivers?.[0];
    if (top)
      tiles.push({
        label: "Top driver",
        value: (
          <span className="text-base">{top.label ?? top.feature}</span>
        ),
        tip: top.lift ? `Groups differ up to ${top.lift}× on this factor.` : undefined,
      });
  } else if (insights.use_case === "clustering") {
    const n = result.metrics.n_clusters_found;
    if (n !== null && n !== undefined) tiles.push({ label: "Groups found", value: String(n), tip: "Distinct groups discovered in the data." });
    const segs = (insights.segments ?? []).filter((s) => s.cluster !== -1);
    if (segs.length) {
      const biggest = segs.reduce((a, b) => (a.share_pct > b.share_pct ? a : b));
      tiles.push({ label: "Largest group", value: `${biggest.name} · ${biggest.share_pct}%` });
    }
  } else if (insights.use_case === "forecasting" && insights.outlook) {
    const o = insights.outlook;
    const DirIcon = o.direction === "rising" ? TrendingUp : o.direction === "falling" ? TrendingDown : Minus;
    tiles.push({
      label: "Direction",
      value: (
        <span className="flex items-center gap-1.5 capitalize">
          <DirIcon className={`h-5 w-5 ${o.direction === "rising" ? "text-good" : o.direction === "falling" ? "text-bad" : "text-ink-dim"}`} />
          {o.direction}
        </span>
      ),
    });
    tiles.push({
      label: `Projected (next ${o.horizon})`,
      value: o.projected_total.toLocaleString(),
      tip: o.uncertainty_pct !== null ? `Read as ±${o.uncertainty_pct}% - see the trust panel.` : undefined,
    });
  }

  tiles.push({
    label: "Evidence",
    value: <span className={`capitalize ${ev.level === "strong" ? "text-good" : ev.level === "moderate" ? "text-warn" : "text-bad"}`}>{ev.level}</span>,
    tip: EVIDENCE_TEXT[ev.level],
  });

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.slice(0, 4).map((t) => (
        <Tile key={t.label} {...t} />
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
  onViewReport,
}: {
  run: Run;
  insights: Insights;
  result: RunResult;
  interpretation: Interpretation | null;
  onTuneAgain: () => void;
  onStartOver: () => void;
  onViewReport: () => void;
}) {
  const [tab, setTab] = useState<"brief" | "appendix">("brief");
  const brief = insights.brief;
  const ev = insights.evidence;
  const metrics = Object.entries(result.metrics).filter(([, v]) => v !== null);
  const a = result.artifacts;

  return (
    <div className="space-y-6">
      {/* Header: tabs + actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex rounded-xl border border-edge bg-panel-2 p-0.5 backdrop-blur">
            <button
              onClick={() => setTab("brief")}
              className={`flex items-center gap-1.5 rounded-[10px] px-3.5 py-1.5 text-xs font-medium transition-colors ${
                tab === "brief" ? "bg-accent text-white shadow" : "text-ink-dim hover:text-ink"
              }`}
            >
              <Layers className="h-3.5 w-3.5" /> Decision brief
            </button>
            <button
              onClick={() => setTab("appendix")}
              className={`flex items-center gap-1.5 rounded-[10px] px-3.5 py-1.5 text-xs font-medium transition-colors ${
                tab === "appendix" ? "bg-accent text-white shadow" : "text-ink-dim hover:text-ink"
              }`}
            >
              <BarChart3 className="h-3.5 w-3.5" /> Technical appendix
            </button>
          </div>
          <Badge tone="accent">{insights.use_case}</Badge>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={onViewReport}>
            <FileText className="h-3.5 w-3.5" /> View full report
          </Button>
          <Button variant="outline" size="sm" onClick={() => api.downloadReport(run.id, `decision-brief-${run.id}.md`)}>
            <Download className="h-3.5 w-3.5" /> Download
          </Button>
          <Button variant="outline" size="sm" onClick={onTuneAgain}>
            <SlidersHorizontal className="h-3.5 w-3.5" /> Adjust
          </Button>
          <Button variant="outline" size="sm" onClick={onStartOver}>
            <RotateCcw className="h-3.5 w-3.5" /> New dataset
          </Button>
        </div>
      </div>

      {tab === "brief" ? (
        <>
          {/* Headline tiles */}
          <StatTiles run={run} insights={insights} result={result} />

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

          {/* Headline chart + findings, side by side */}
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-dim">Key findings</h3>
              {insights.findings.map((f, i) => (
                <Card key={i}>
                  <CardBody className="py-3.5">
                    <h4 className="break-words text-sm font-semibold leading-snug">{f.headline}</h4>
                    <p className="mt-1.5 break-words text-xs leading-relaxed text-ink-dim">{f.detail}</p>
                  </CardBody>
                </Card>
              ))}
            </div>
            <div className="space-y-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-dim">The picture</h3>
              {insights.use_case === "classification" && a.class_distribution && (
                <div className="rounded-xl border border-edge bg-panel p-4 backdrop-blur-xl">
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-dim">How outcomes split today</h4>
                  <p className="mb-2 text-[11px] text-ink-dim">Every action you take aims to shift this balance.</p>
                  <ClassDistributionChart data={a.class_distribution} />
                </div>
              )}
              {insights.use_case === "clustering" && a.scatter && (
                <div className="rounded-xl border border-edge bg-panel p-4 backdrop-blur-xl">
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-dim">The groups, mapped</h4>
                  <p className="mb-2 text-[11px] text-ink-dim">Each dot is one record, colored by group. Clear islands = distinct groups.</p>
                  <ClusterScatter points={a.scatter.points} axes={a.scatter.axes} />
                </div>
              )}
              {insights.use_case === "forecasting" && a.series && a.forecast && (
                <div className="rounded-xl border border-edge bg-panel p-4 backdrop-blur-xl">
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-dim">History & projection</h4>
                  <p className="mb-2 text-[11px] text-ink-dim">Grey = actual history · dashed blue = the projection ahead.</p>
                  <ForecastChart series={a.series} forecast={a.forecast} />
                </div>
              )}
              {insights.use_case === "classification" && insights.drivers && insights.drivers.length > 0 && (
                <DriverChart driver={insights.drivers[0]} />
              )}
            </div>
          </div>

          {/* Remaining drivers */}
          {insights.drivers && insights.drivers.length > 1 && (
            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
                Other drivers of the outcome
              </h3>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {insights.drivers.slice(1).map((d) => (
                  <DriverChart key={d.feature} driver={d} />
                ))}
              </div>
            </section>
          )}

          {/* Segments */}
          {insights.segments && insights.segments.length > 0 && (
            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-ink-dim">
                <Users className="h-4 w-4" /> Segment profiles
              </h3>
              <div className="grid gap-4 md:grid-cols-3">
                {insights.segments.map((s) => (
                  <SegmentCard key={s.cluster} segment={s} />
                ))}
              </div>
            </section>
          )}

          {/* Actions + trust */}
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
                  {brief.recommended_actions.map((act, i) => (
                    <li key={i} className="flex gap-2.5 text-sm">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-good/15 text-[11px] font-semibold text-good">
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
                <p className="text-sm leading-relaxed">
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
          </div>

          {/* Ask the data */}
          <AskTheData runId={run.id} rows={run.profile?.n_rows ?? 0} />
        </>
      ) : (
        /* ---------- Technical appendix tab ---------- */
        <div className="space-y-6">
          <div className="flex items-center gap-2 text-sm text-ink-dim">
            <span className="font-semibold text-ink">{run.config?.model_name}</span>
            diagnostics - settings: {JSON.stringify(run.config?.hyperparams)}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {metrics.map(([k, v]) => {
              const info = metricInfo(k);
              return (
                <div key={k} className="min-w-0 rounded-xl border border-edge bg-panel-2 px-3 py-2 backdrop-blur">
                  <div className="flex items-center gap-1 truncate text-[11px] uppercase tracking-wider text-ink-dim">
                    {info.label}
                    <InfoTip text={info.explain} />
                  </div>
                  <div className="mt-0.5 truncate text-lg font-semibold tabular-nums">{String(v)}</div>
                </div>
              );
            })}
          </div>
          {interpretation && (
            <Card>
              <CardHeader title="Model interpretation" right={<Badge tone={interpretation.generated_by === "claude" ? "accent" : "neutral"}>{interpretation.generated_by}</Badge>} />
              <CardBody>
                <p className="text-sm leading-relaxed text-ink-dim">{interpretation.summary}</p>
              </CardBody>
            </Card>
          )}
          <ResultCharts result={result} />
        </div>
      )}
    </div>
  );
}

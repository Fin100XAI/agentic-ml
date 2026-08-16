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
  Share2,
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
import type { Driver, Insights, Interpretation, Run, RunResult, Segment, SliceScan, Validation } from "../../types";
import { metricInfo } from "../../lib/metricInfo";
import { InfoTip } from "../InfoTip";
import { LineageBreadcrumb } from "../LineageBreadcrumb";
import { api } from "../../api/client";
import { AskTheData } from "../AskTheData";
import { ClassDistributionChart, ClusterScatter, ForecastChart, PredictedVsActualChart, ResultCharts } from "../charts";
import { Badge, Button, Card, CardBody, CardHeader } from "../ui";

function StabilityPanel({ v }: { v: Validation }) {
  if (v.skipped) {
    return (
      <Card>
        <CardBody className="py-3">
          <p className="text-xs leading-relaxed text-ink-dim">
            <span className="font-semibold text-ink">{v.label}:</span> {v.note}
          </p>
        </CardBody>
      </Card>
    );
  }
  const folds = v.folds ?? [];
  const max = Math.max(...folds, 0.0001);
  const info = metricInfo(v.metric ?? "");
  return (
    <Card>
      <CardHeader
        title={`Stability check - ${v.label}`}
        right={<Badge tone={v.verdict === "stable" ? "good" : "warn"}>{v.verdict}</Badge>}
      />
      <CardBody>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex items-end gap-2">
            {folds.map((f, i) => (
              <div key={i} className="flex flex-col items-center gap-1">
                <div className="flex h-16 w-9 items-end overflow-hidden rounded-md bg-white/40">
                  <div
                    className="w-full rounded-t-md bg-accent/70"
                    style={{ height: `${Math.max(8, (f / max) * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] tabular-nums text-ink-dim">{f}</span>
              </div>
            ))}
          </div>
          <div>
            <div className="text-xl font-semibold tabular-nums">
              {v.mean} <span className="text-xs font-normal text-ink-dim">+/- {v.std}</span>
            </div>
            <div className="flex items-center gap-1 text-[11px] text-ink-dim">
              {info.label} across resamples
              <InfoTip text={`The same model was retrained on different portions of the data (${v.label.toLowerCase()}). Each bar is one retraining's score. ${info.explain}`} />
            </div>
          </div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-ink-dim">{v.note}</p>
      </CardBody>
    </Card>
  );
}

function SlicesPanel({ s }: { s: SliceScan }) {
  const [showAll, setShowAll] = useState(false);
  const interesting = s.rows.filter((r) => r.status === "red" || r.status === "amber");
  const rows = showAll ? s.rows : interesting.length > 0 ? interesting : s.rows.slice(0, 6);
  return (
    <Card className={s.red_groups.length ? "border-bad/30" : undefined}>
      <CardHeader
        title="Who does the model serve worse?"
        subtitle={`${s.metric} per group on the ${s.n_test.toLocaleString()} held-out rows (overall ${s.overall}). Red groups fall clearly below overall; tiny groups are skipped, not judged.`}
        right={
          s.red_groups.length > 0 ? (
            <Badge tone="bad">{s.red_groups.length} red group{s.red_groups.length !== 1 ? "s" : ""}</Badge>
          ) : (
            <Badge tone="good">even performance</Badge>
          )
        }
      />
      <CardBody>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-edge text-[10px] uppercase tracking-wider text-ink-dim">
                <th className="py-1.5 pr-3">Column</th>
                <th className="py-1.5 pr-3">Group</th>
                <th className="py-1.5 pr-3">Rows</th>
                <th className="py-1.5 pr-3">{s.metric}</th>
                <th className="py-1.5">Read as</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={`border-b border-edge/40 ${r.status === "too_small" ? "opacity-50" : ""}`}>
                  <td className="py-1.5 pr-3 font-medium">{r.column}</td>
                  <td className="py-1.5 pr-3">{r.group}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{r.n}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{r.value ?? "-"}</td>
                  <td className="py-1.5">
                    {r.status === "too_small" ? (
                      <span className="text-[10px] text-ink-dim">group too small to assess</span>
                    ) : (
                      <Badge tone={r.status === "red" ? "bad" : r.status === "amber" ? "warn" : "good"}>
                        {r.status === "red" ? "materially worse" : r.status === "amber" ? "somewhat worse" : "in line"}
                      </Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {s.rows.length > rows.length && (
          <button
            onClick={() => setShowAll(true)}
            className="mt-2 text-xs font-medium text-accent hover:underline"
          >
            Show all {s.rows.length} groups
          </button>
        )}
        {showAll && (
          <button
            onClick={() => setShowAll(false)}
            className="mt-2 text-xs font-medium text-accent hover:underline"
          >
            Show fewer
          </button>
        )}
      </CardBody>
    </Card>
  );
}

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
        {driver.unit === "avg"
          ? "Average outcome per group - red marks the highest-value group."
          : "Outcome rate per group - red is the highest-risk group, where action matters most."}
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
  } else if (insights.use_case === "regression") {
    const mae = result.metrics.mae;
    if (mae !== null && mae !== undefined)
      tiles.push({
        label: "Typical miss",
        value: `±${Number(mae).toLocaleString()}`,
        tip: "On held-back records, predictions were off by this much on average - the planning margin.",
      });
    const top = insights.drivers?.[0];
    if (top)
      tiles.push({
        label: "Top driver",
        value: <span className="text-base">{top.label ?? top.feature}</span>,
        tip: top.lift ? `Average outcomes differ up to ${top.lift}× across this factor's groups.` : undefined,
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
  const [shareCopied, setShareCopied] = useState(false);
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
          <Button variant="outline" size="sm" onClick={() => api.downloadReportPdf(run.id)}>
            <Download className="h-3.5 w-3.5" /> Download PDF
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const url = `${window.location.origin}${window.location.pathname}#/brief/${run.id}`;
              navigator.clipboard.writeText(url).then(
                () => setShareCopied(true),
                () => window.prompt("Copy this briefing link:", url),
              );
              setTimeout(() => setShareCopied(false), 2500);
            }}
          >
            <Share2 className="h-3.5 w-3.5" /> {shareCopied ? "Link copied!" : "Share briefing"}
          </Button>
          <Button variant="outline" size="sm" onClick={onTuneAgain}>
            <SlidersHorizontal className="h-3.5 w-3.5" /> Adjust
          </Button>
          <Button variant="outline" size="sm" onClick={onStartOver}>
            <RotateCcw className="h-3.5 w-3.5" /> New dataset
          </Button>
        </div>
      </div>

      {run.artifact_id && <LineageBreadcrumb artifactId={run.artifact_id} />}

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
              right={
                <span className="flex items-center gap-1.5">
                  {insights.critic && (
                    <span className="flex items-center gap-1">
                      <Badge tone={insights.critic.generated_by === "claude" ? "good" : "neutral"}>
                        {insights.critic.generated_by === "claude" ? "reviewed by critic" : "critic: heuristic"}
                      </Badge>
                      <InfoTip
                        text={
                          insights.critic.changes.length
                            ? "Critic changes: " + insights.critic.changes.join(" | ")
                            : "The critic reviewed this brief and made no changes."
                        }
                      />
                    </span>
                  )}
                  <Badge tone={brief.generated_by === "claude" ? "accent" : "neutral"}>{brief.generated_by}</Badge>
                </span>
              }
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
              {insights.use_case === "regression" && a.predicted_vs_actual && (
                <div className="rounded-xl border border-edge bg-panel p-4 backdrop-blur-xl">
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-dim">Predicted vs actual</h4>
                  <p className="mb-2 text-[11px] text-ink-dim">Dots on the dashed line = perfect predictions. Tight cloud = trustworthy estimates.</p>
                  <PredictedVsActualChart points={a.predicted_vs_actual.points} />
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
                  <p className="mb-2 text-[11px] text-ink-dim">Grey = actual history · dashed blue = the projection ahead · shaded = the likely range.</p>
                  <ForecastChart
                    series={a.series}
                    forecast={a.forecast}
                    uncertaintyPct={result.metrics.mape_pct ?? null}
                    context={a.context_series}
                  />
                </div>
              )}
              {(insights.use_case === "classification" || insights.use_case === "regression") &&
                insights.drivers && insights.drivers.length > 0 && (
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

          {/* Actions + trust - weak evidence reframes actions as hypotheses */}
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className={insights.trust_tier === "weak" ? "border-warn/40" : "border-good/30"}>
              <CardHeader
                title={
                  <span className="flex items-center gap-2">
                    <ListChecks className={`h-4 w-4 ${insights.trust_tier === "weak" ? "text-warn" : "text-good"}`} />
                    {insights.trust_tier === "weak" ? "Hypotheses to verify" : "Recommended actions"}
                  </span>
                }
              />
              <CardBody>
                {insights.trust_tier === "weak" && (
                  <div className="mb-3 rounded-xl border border-warn/40 bg-warn/10 px-3.5 py-2.5 text-xs leading-relaxed">
                    <span className="font-semibold">Evidence is weak for this run.</span> The items
                    below are leads worth verifying with more data or a small pilot - not
                    recommendations to act on yet.
                  </div>
                )}
                <ol className="space-y-2.5">
                  {brief.recommended_actions.map((act, i) => (
                    <li key={i} className="flex gap-2.5 text-sm">
                      <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                        insights.trust_tier === "weak" ? "bg-warn/15 text-warn" : "bg-good/15 text-good"
                      }`}>
                        {i + 1}
                      </span>
                      <span className="min-w-0 break-words leading-relaxed">{act}</span>
                    </li>
                  ))}
                </ol>
                {insights.trust_tier === "moderate" && (
                  <p className="mt-3 text-[11px] leading-snug text-ink-dim">
                    Caution: evidence is moderate - sanity-check these against domain knowledge
                    before major commitments.
                  </p>
                )}
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
          <div className="flex flex-wrap items-center gap-2 text-sm text-ink-dim">
            <span className="font-semibold text-ink">{run.config?.model_name}</span>
            diagnostics - settings: {JSON.stringify(run.config?.hyperparams)}
            {run.registry_ref && (
              <Badge tone="accent">
                registered v{run.registry_ref.version} · {run.registry_ref.model_id.slice(0, 8)}
              </Badge>
            )}
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
          {result.validation && <StabilityPanel v={result.validation} />}
          {result.slices && <SlicesPanel s={result.slices} />}
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

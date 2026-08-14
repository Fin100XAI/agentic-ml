import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Bot,
  ChevronDown,
  ChevronRight,
  Info,
  Lightbulb,
  MessageSquare,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ColumnProfile, Eda, Health, Profile } from "../../types";
import { USE_CASE_INFO } from "../../lib/metricInfo";
import { InfoTip } from "../InfoTip";
import { Badge, Button, Card, CardBody, CardHeader, Spinner, Stat } from "../ui";

const AXIS = { fill: "#64748b", fontSize: 10 };
const GRID = "#dde3ee";
const TOOLTIP_STYLE = {
  backgroundColor: "rgba(255,255,255,0.95)",
  border: "1px solid #dde3ee",
  borderRadius: 10,
  fontSize: 12,
  color: "#0f172a",
};

const ROLE_TONE: Record<string, "accent" | "good" | "warn" | "neutral" | "bad"> = {
  numeric: "accent",
  categorical: "good",
  datetime: "warn",
  boolean: "good",
  identifier: "neutral",
  text: "neutral",
};

const ROLE_LABEL: Record<string, string> = {
  numeric: "numbers",
  categorical: "categories",
  datetime: "dates",
  boolean: "yes/no",
  identifier: "IDs",
  text: "text",
};

/** One-line, data-derived caption: what can be read off this histogram. */
function histogramCaption(col: ColumnProfile): string {
  const s = col.stats;
  const h = col.histogram;
  if (!s || !h || s.mean === null || s.median === null) return "";
  const maxBin = h.counts.indexOf(Math.max(...h.counts));
  const lo = h.edges[maxBin];
  const hi = h.edges[maxBin + 1];
  const where = lo !== null && hi !== null ? `Most rows sit between ${lo} and ${hi}.` : "";
  if (s.median !== 0 && s.mean > s.median * 1.25)
    return `${where} A few unusually high values pull the average up.`;
  if (s.median !== 0 && s.mean < s.median * 0.75)
    return `${where} A few unusually low values pull the average down.`;
  return `${where} Values are fairly evenly spread.`;
}

/** Mini histogram for a numeric column. */
function HistogramCard({ col }: { col: ColumnProfile }) {
  const h = col.histogram;
  if (!h) return null;
  const data = h.counts.map((c, i) => ({
    bin: `${h.edges[i] ?? ""}`,
    label: `${h.edges[i]} – ${h.edges[i + 1]}`,
    count: c,
  }));
  return (
    <div className="min-w-0 rounded-xl border border-edge bg-panel p-3 backdrop-blur-xl">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate text-xs font-semibold" title={col.name}>
          {col.display_name}
        </span>
        <InfoTip text={col.meaning} />
      </div>
      <ResponsiveContainer width="100%" height={90}>
        <BarChart data={data} margin={{ top: 2, left: 0, right: 0, bottom: 0 }}>
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(v) => [`${v} rows`, ""]}
            labelFormatter={(_, p) => (p?.[0]?.payload as { label?: string })?.label ?? ""}
            cursor={{ fill: "rgba(79,70,229,0.06)" }}
          />
          <Bar dataKey="count" fill="#4f46e5" radius={[3, 3, 0, 0]} opacity={0.75} />
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-1 flex justify-between text-[10px] tabular-nums text-ink-dim">
        <span>{col.stats?.min}</span>
        <span>{col.stats?.max}</span>
      </div>
      <p className="mt-1.5 border-t border-edge/60 pt-1.5 text-[10px] leading-snug text-ink-dim">
        {histogramCaption(col)}
      </p>
    </div>
  );
}

/** Top categories for a categorical/boolean column. */
function TopValuesCard({ col }: { col: ColumnProfile }) {
  const data = (col.top_values ?? []).slice(0, 5).map((t) => ({
    name: String(t.value),
    count: t.count,
  }));
  if (data.length === 0) return null;
  return (
    <div className="min-w-0 rounded-xl border border-edge bg-panel p-3 backdrop-blur-xl">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate text-xs font-semibold" title={col.name}>
          {col.display_name}
        </span>
        <InfoTip text={col.meaning} />
      </div>
      <ResponsiveContainer width="100%" height={Math.max(90, data.length * 22)}>
        <BarChart data={data} layout="vertical" margin={{ top: 2, left: 0, right: 24, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="name"
            width={80}
            tick={AXIS}
            stroke={GRID}
            tickFormatter={(v: string) => (v.length > 11 ? v.slice(0, 10) + "…" : v)}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(79,70,229,0.06)" }} />
          <Bar
            dataKey="count"
            fill="#059669"
            radius={[0, 3, 3, 0]}
            opacity={0.75}
            label={{ position: "right", fill: "#64748b", fontSize: 9 }}
          />
        </BarChart>
      </ResponsiveContainer>
      {data.length > 0 && (
        <p className="mt-1.5 border-t border-edge/60 pt-1.5 text-[10px] leading-snug text-ink-dim">
          {(() => {
            const total = (col.top_values ?? []).reduce((s, t) => s + t.count, 0);
            const top = data[0];
            const share = total ? Math.round((top.count / total) * 100) : 0;
            return share >= 60
              ? `'${top.name}' dominates with ${share}% of rows — the rest are much rarer.`
              : `'${top.name}' is the most common (${share}% of rows).`;
          })()}
        </p>
      )}
    </div>
  );
}

/** Missing-data bar chart, shown only when gaps exist. */
function MissingnessCard({ profile }: { profile: Profile }) {
  const cols = profile.columns
    .filter((c) => (c.missing_pct ?? 0) > 0)
    .sort((a, b) => (b.missing_pct ?? 0) - (a.missing_pct ?? 0))
    .slice(0, 8);
  if (cols.length === 0) return null;
  const data = cols.map((c) => ({ name: c.display_name, pct: c.missing_pct ?? 0 }));
  return (
    <div className="min-w-0 rounded-xl border border-warn/30 bg-panel p-3 backdrop-blur-xl">
      <div className="mb-1 flex items-center gap-1.5">
        <AlertTriangle className="h-3.5 w-3.5 text-warn" />
        <span className="text-xs font-semibold">Where data is missing</span>
      </div>
      <ResponsiveContainer width="100%" height={Math.max(90, data.length * 22)}>
        <BarChart data={data} layout="vertical" margin={{ top: 2, left: 0, right: 30, bottom: 0 }}>
          <XAxis type="number" hide domain={[0, 100]} />
          <YAxis
            type="category"
            dataKey="name"
            width={90}
            tick={AXIS}
            stroke={GRID}
            tickFormatter={(v: string) => (v.length > 12 ? v.slice(0, 11) + "…" : v)}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${v}% missing`, ""]} cursor={{ fill: "rgba(217,119,6,0.06)" }} />
          <Bar dataKey="pct" fill="#d97706" radius={[0, 3, 3, 0]} opacity={0.8} label={{ position: "right", fill: "#64748b", fontSize: 9, formatter: (v) => `${v}%` }} />
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-1.5 border-t border-edge/60 pt-1.5 text-[10px] leading-snug text-ink-dim">
        Gaps are filled with typical values during modeling — heavy gaps weaken the evidence.
      </p>
    </div>
  );
}

/** Prominent data-health panel with prompts + suggestions. */
function HealthPanel({ health }: { health: Health }) {
  const [expanded, setExpanded] = useState(health.score !== "good");
  const tone =
    health.score === "good"
      ? { border: "border-good/40", icon: ShieldCheck, color: "text-good", label: "Data looks healthy" }
      : health.score === "caution"
        ? { border: "border-warn/50", icon: ShieldAlert, color: "text-warn", label: "Data needs some care" }
        : { border: "border-bad/50", icon: ShieldAlert, color: "text-bad", label: "Data has serious limitations" };
  const Icon = tone.icon;
  const SEV_STYLE = {
    critical: { icon: ShieldAlert, cls: "text-bad", chip: "bad" as const },
    warning: { icon: AlertTriangle, cls: "text-warn", chip: "warn" as const },
    info: { icon: Info, cls: "text-ink-dim", chip: "neutral" as const },
  };
  return (
    <Card className={tone.border}>
      <button className="flex w-full items-center justify-between px-5 py-3.5 text-left" onClick={() => setExpanded((e) => !e)}>
        <span className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${tone.color}`} />
          <span className="text-sm font-semibold">{tone.label}</span>
          {health.issues.length > 0 && (
            <Badge tone={health.score === "poor" ? "bad" : health.score === "caution" ? "warn" : "neutral"}>
              {health.issues.length} finding{health.issues.length !== 1 ? "s" : ""}
            </Badge>
          )}
        </span>
        {expanded ? <ChevronDown className="h-4 w-4 text-ink-dim" /> : <ChevronRight className="h-4 w-4 text-ink-dim" />}
      </button>
      {expanded && health.issues.length > 0 && (
        <div className="space-y-3 border-t border-edge px-5 py-4">
          {health.issues.map((issue, i) => {
            const s = SEV_STYLE[issue.severity];
            const SevIcon = s.icon;
            return (
              <div key={i} className="flex gap-2.5">
                <SevIcon className={`mt-0.5 h-4 w-4 shrink-0 ${s.cls}`} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold">{issue.title}</span>
                    <Badge tone={s.chip}>{issue.severity}</Badge>
                  </div>
                  <p className="mt-0.5 break-words text-[11px] leading-relaxed text-ink-dim">{issue.detail}</p>
                  <p className="mt-1 break-words text-[11px] font-medium leading-relaxed text-ink">
                    → {issue.suggestion}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {expanded && health.issues.length === 0 && (
        <p className="border-t border-edge px-5 py-3 text-xs text-ink-dim">
          No size, balance, or missing-data problems detected. Good to proceed.
        </p>
      )}
    </Card>
  );
}

/** Composition of column types as a segmented bar. */
function TypeComposition({ profile }: { profile: Profile }) {
  const counts: Record<string, number> = {};
  for (const c of profile.columns) counts[c.role] = (counts[c.role] ?? 0) + 1;
  const entries = Object.entries(counts);
  const total = profile.columns.length || 1;
  const COLORS: Record<string, string> = {
    numeric: "#4f46e5",
    categorical: "#059669",
    datetime: "#d97706",
    boolean: "#0891b2",
    identifier: "#94a3b8",
    text: "#c026d3",
  };
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full">
        {entries.map(([role, n]) => (
          <div
            key={role}
            style={{ width: `${(n / total) * 100}%`, backgroundColor: COLORS[role] ?? "#94a3b8" }}
            title={`${n} ${ROLE_LABEL[role] ?? role}`}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {entries.map(([role, n]) => (
          <span key={role} className="flex items-center gap-1.5 text-[11px] text-ink-dim">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[role] ?? "#94a3b8" }} />
            {n} {ROLE_LABEL[role] ?? role}
          </span>
        ))}
      </div>
    </div>
  );
}

function Collapsible({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border border-edge bg-panel backdrop-blur-xl">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3 text-left"
      >
        <span className="text-xs font-semibold uppercase tracking-wider text-ink-dim">{title}</span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-ink-dim" />
        ) : (
          <ChevronRight className="h-4 w-4 text-ink-dim" />
        )}
      </button>
      {open && <div className="border-t border-edge">{children}</div>}
    </div>
  );
}

export function EdaScreen({
  profile,
  eda,
  question,
  onApprove,
  busy,
}: {
  profile: Profile;
  eda: Eda;
  question: string;
  onApprove: (comment: string) => void;
  busy: boolean;
}) {
  const [comment, setComment] = useState(question);
  const [showAllCharts, setShowAllCharts] = useState(false);

  const chartCols = useMemo(() => {
    const numeric = profile.columns.filter((c) => c.role === "numeric" && c.histogram);
    const categorical = profile.columns.filter(
      (c) => (c.role === "categorical" || c.role === "boolean") && c.top_values?.length,
    );
    return [...numeric, ...categorical];
  }, [profile]);
  const visibleCharts = showAllCharts ? chartCols : chartCols.slice(0, 6);

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Main column */}
      <div className="space-y-6 lg:col-span-2">
        {/* Data health — the human's early-warning panel */}
        {profile.health && <HealthPanel health={profile.health} />}

        {/* Agent summary */}
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-accent" /> What your data is about
              </span>
            }
            right={<Badge tone={eda.generated_by === "claude" ? "accent" : "neutral"}>{eda.generated_by}</Badge>}
          />
          <CardBody>
            <p className="text-sm leading-relaxed">{eda.summary}</p>
            <ul className="mt-3 space-y-1.5">
              {eda.key_findings.slice(0, 4).map((f, i) => (
                <li key={i} className="flex gap-2 text-xs leading-relaxed text-ink-dim">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  <span className="min-w-0 break-words">{f}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        {/* Column charts */}
        <Card>
          <CardHeader
            title="Your columns at a glance"
            subtitle="Each little chart shows how the values are spread"
          />
          <CardBody>
            <TypeComposition profile={profile} />
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {visibleCharts.map((c) => (c.histogram ? <HistogramCard key={c.name} col={c} /> : <TopValuesCard key={c.name} col={c} />))}
              <MissingnessCard profile={profile} />
            </div>
            {chartCols.length > 6 && (
              <button
                onClick={() => setShowAllCharts((s) => !s)}
                className="mt-3 text-xs font-medium text-accent hover:underline"
              >
                {showAllCharts ? "Show fewer" : `Show all ${chartCols.length} columns`}
              </button>
            )}
          </CardBody>
        </Card>

        {/* What you can do */}
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Lightbulb className="h-4 w-4 text-warn" /> What you can do with this data
              </span>
            }
          />
          <CardBody className="grid gap-3 sm:grid-cols-3">
            {profile.suggested_use_cases.map((uc) => {
              const info = USE_CASE_INFO[uc];
              if (!info) return null;
              return (
                <div key={uc} className="min-w-0 rounded-xl border border-edge bg-panel-2 px-3 py-2.5 backdrop-blur">
                  <div className="text-sm">
                    {info.icon} <span className="font-semibold">{info.title}</span>
                  </div>
                  <p className="mt-1 break-words text-[11px] leading-snug text-ink-dim">{info.tagline}</p>
                </div>
              );
            })}
          </CardBody>
        </Card>

        {/* Detail: column dictionary */}
        <Collapsible title={`Column details (${profile.n_cols})`}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-ink-dim">
                  <th className="px-5 py-2.5 font-medium">Column</th>
                  <th className="px-3 py-2.5 font-medium">Type</th>
                  <th className="px-3 py-2.5 font-medium">What it means</th>
                  <th className="px-3 py-2.5 font-medium">Missing</th>
                </tr>
              </thead>
              <tbody>
                {profile.columns.map((c) => (
                  <tr key={c.name} className="border-b border-edge/50 last:border-0">
                    <td className="max-w-40 px-5 py-2">
                      <div className="truncate font-medium" title={c.display_name}>
                        {c.display_name}
                      </div>
                      <div className="truncate text-[10px] text-ink-dim/70" title={c.name}>
                        {c.name}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={ROLE_TONE[c.role] ?? "neutral"}>{ROLE_LABEL[c.role] ?? c.role}</Badge>
                    </td>
                    <td className="max-w-72 break-words px-3 py-2 text-ink-dim">{c.meaning}</td>
                    <td className="px-3 py-2 tabular-nums text-ink-dim">
                      {c.missing_pct ? `${c.missing_pct}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Collapsible>

        {/* Detail: raw data preview */}
        <Collapsible title="Peek at the raw data (first 10 rows)">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-ink-dim">
                  {profile.columns.map((c) => (
                    <th key={c.name} className="whitespace-nowrap px-3 py-2.5 font-medium first:pl-5" title={c.name}>
                      {c.display_name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {profile.preview.map((row, i) => (
                  <tr key={i} className="border-b border-edge/50 last:border-0">
                    {profile.columns.map((c) => (
                      <td key={c.name} className="whitespace-nowrap px-3 py-1.5 tabular-nums text-ink-dim first:pl-5">
                        {String(row[c.name] ?? "—")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Collapsible>
      </div>

      {/* Right rail */}
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Rows" value={profile.n_rows.toLocaleString()} />
          <Stat label="Columns" value={profile.n_cols} />
          <Stat label="Missing cells" value={`${profile.missingness.pct_missing ?? 0}%`} />
          <Stat
            label="Quality"
            value={
              (profile.missingness.pct_missing ?? 0) < 1
                ? "clean"
                : (profile.missingness.pct_missing ?? 0) < 10
                  ? "usable"
                  : "gappy"
            }
          />
        </div>

        {profile.correlations.length > 0 && (
          <Card>
            <CardHeader
              title={
                <span className="inline-flex items-center gap-1">
                  Strongest relationships
                  <InfoTip text="Values close to 1 or -1 mean two columns move together; close to 0 means no clear link." />
                </span>
              }
            />
            <CardBody className="space-y-1.5">
              {profile.correlations.slice(0, 5).map((c, i) => {
                const nameOf = (raw: string) =>
                  profile.columns.find((col) => col.name === raw)?.display_name ?? raw;
                return (
                  <div key={i} className="flex items-center justify-between gap-2 text-xs">
                    <span className="min-w-0 truncate text-ink-dim" title={`${c.a} × ${c.b} (raw column names)`}>
                      {nameOf(c.a)} × {nameOf(c.b)}
                    </span>
                    <span
                      className={`shrink-0 font-semibold tabular-nums ${
                        Math.abs(c.corr ?? 0) > 0.5 ? "text-accent" : "text-ink-dim"
                      }`}
                    >
                      {c.corr}
                    </span>
                  </div>
                );
              })}
              <p className="border-t border-edge/60 pt-1.5 text-[10px] leading-snug text-ink-dim">
                {Math.abs(profile.correlations[0]?.corr ?? 0) > 0.5
                  ? "The top pair moves strongly together — likely related in the real world."
                  : "No very strong pairings — columns carry mostly independent information."}
              </p>
            </CardBody>
          </Card>
        )}

        <Card className="border-warn/30">
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-warn" /> Your turn
              </span>
            }
            subtitle="The agents pause here until you approve"
          />
          <CardBody>
            <p className="text-xs leading-relaxed text-ink-dim">
              Tell the agents what you want to learn — or pick a suggestion. This steers which
              analysis gets recommended next.
            </p>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              placeholder={eda.suggested_questions[0] ?? "e.g. what drives churn, find groups…"}
              className="mt-2 w-full resize-none rounded-xl border border-edge bg-panel-2 px-3 py-2 text-sm outline-none backdrop-blur placeholder:text-ink-dim/60 focus:border-accent"
            />
            {eda.suggested_questions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {eda.suggested_questions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => setComment(q)}
                    className="max-w-full truncate rounded-full border border-edge px-2.5 py-1 text-[11px] text-ink-dim transition-colors hover:border-accent hover:text-accent"
                    title={q}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
            <div className="mt-4">
              {busy ? (
                <Spinner label="Recommendation agent thinking…" />
              ) : (
                <Button className="w-full" onClick={() => onApprove(comment)}>
                  Looks right — recommend an approach
                </Button>
              )}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

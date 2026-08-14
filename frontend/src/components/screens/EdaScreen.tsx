import { useMemo, useState } from "react";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Lightbulb,
  MessageSquare,
} from "lucide-react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ColumnProfile, Eda, Profile } from "../../types";
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
    </div>
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
              {profile.correlations.slice(0, 5).map((c, i) => (
                <div key={i} className="flex items-center justify-between gap-2 text-xs">
                  <span className="min-w-0 truncate text-ink-dim" title={`${c.a} × ${c.b}`}>
                    {c.a} × {c.b}
                  </span>
                  <span
                    className={`shrink-0 font-semibold tabular-nums ${
                      Math.abs(c.corr ?? 0) > 0.5 ? "text-accent" : "text-ink-dim"
                    }`}
                  >
                    {c.corr}
                  </span>
                </div>
              ))}
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

// Renders a backend-chosen ChartSpec (deterministic, rule 14). The frontend
// never picks the chart type - it draws exactly what the shape mapper chose.
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useState } from "react";
import type { ChartSpec, QueryResult } from "../types";
import { IndiaMap } from "./IndiaMap";

const AXIS = { fill: "var(--chart-axis)", fontSize: 11 };
const GRID = "var(--chart-grid)";
const BLUE = "var(--color-accent)";
// Colorblind-safe series palette; amber/red stay reserved for judgment.
const PALETTE = ["var(--color-accent)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];

const TOOLTIP_STYLE = {
  backgroundColor: "var(--chart-tip-bg)",
  border: "1px solid var(--chart-tip-border)",
  borderRadius: 10,
  fontSize: 12,
  color: "var(--chart-tip-fg)",
  boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
};

function compact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${(v / 1_000).toFixed(0)}k`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return `${Math.round(v * 100) / 100}`;
}

function niceLabel(col: string): string {
  return col.replace(/__/g, " ").replace(/_/g, " ");
}

// Chart with an optional map toggle - offered only when the backend matched
// the keys to a bundled boundary set (>= 70%). The chart stays the default.
export function QueryChartWithMap({ spec, result }: { spec: ChartSpec; result: QueryResult }) {
  // When there are too many categories for honest bars, the map IS the
  // best view - make it the default there.
  const [view, setView] = useState<"chart" | "map">(
    spec.map && spec.kind === "table" ? "map" : "chart",
  );
  if (!spec.map) return <QueryChart spec={spec} result={result} />;
  const x = spec.x ?? "";
  const y = spec.y[0] ?? "";
  const values: Record<string, number> = {};
  for (const r of result.table) {
    const k = String(r[x] ?? "");
    if (typeof r[y] === "number") values[k] = r[y] as number;
  }
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1">
        {(["chart", "map"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`rounded-full border px-2.5 py-0.5 text-[10px] font-medium transition-colors ${
              view === v
                ? "border-accent/40 bg-accent-soft text-accent"
                : "border-edge bg-panel-2 text-ink-dim hover:text-accent"
            }`}
          >
            {v === "chart" ? "Chart" : "Map"}
          </button>
        ))}
        {view === "map" && (
          <span className="ml-1 text-[10px] text-ink-dim">
            {Math.round(spec.map.match_pct * 100)}% of areas matched
          </span>
        )}
      </div>
      {view === "chart" ? (
        <QueryChart spec={spec} result={result} />
      ) : (
        <IndiaMap
          level={spec.map.level}
          matches={spec.map.matches}
          values={values}
          metricLabel={niceLabel(y)}
          mode={spec.map.mode ?? "sequential"}
          threshold={spec.threshold}
        />
      )}
    </div>
  );
}

export function QueryChart({ spec, result }: { spec: ChartSpec; result: QueryResult }) {
  const rows = result.table;

  if (spec.kind === "kpi") {
    return (
      <div className="flex flex-wrap gap-3">
        {spec.y.map((col) => {
          const v = rows[0]?.[col];
          return (
            <div key={col} className="min-w-[140px] flex-1 rounded-xl border border-accent/25 bg-gradient-to-br from-accent-soft/60 via-panel to-panel p-4 shadow-sm">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-accent/80">{niceLabel(col)}</div>
              <div className="mt-1 text-2xl font-bold tabular-nums text-ink">
                {typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v ?? "-")}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  // Scatter carries its key column in `label`, not on an axis.
  if (spec.kind === "scatter" && spec.y.length >= 2) {
    const [xm, ym] = spec.y;
    const pts = rows
      .filter((r) => typeof r[xm] === "number" && typeof r[ym] === "number")
      .map((r) => ({ ...r }));
    return (
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis dataKey={xm} type="number" name={niceLabel(xm)} tick={AXIS} stroke={GRID} tickFormatter={(v) => compact(Number(v))} />
          <YAxis dataKey={ym} type="number" name={niceLabel(ym)} tick={AXIS} stroke={GRID} tickFormatter={(v) => compact(Number(v))} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ strokeDasharray: "3 3" }}
            formatter={(v, n) => [typeof v === "number" ? v.toLocaleString() : String(v), niceLabel(String(n))]}
            labelFormatter={() => ""}
          />
          <Scatter
            data={pts}
            fill={BLUE}
            isAnimationActive={false}
            shape={(p: { cx?: number; cy?: number }) => (
              <circle cx={p.cx} cy={p.cy} r={4} fill={BLUE} fillOpacity={0.6} />
            )}
          />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  if (spec.kind === "table" || !spec.x || spec.y.length === 0) {
    return spec.note ? <p className="text-[11px] text-ink-dim">{spec.note}</p> : null;
  }

  const x = spec.x;
  const y = spec.y[0];
  const data = rows.map((r) => ({ ...r, [x]: String(r[x] ?? "") }));

  // Part-of-whole (pivot output) -> stacked bars, never pie.
  if (spec.kind === "sbar") {
    return (
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={x} tick={{ ...AXIS, fontSize: 10 }} stroke={GRID} />
          <YAxis tick={AXIS} stroke={GRID} domain={[0, "auto"]} tickFormatter={(v) => compact(Number(v))} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--chart-cursor)" }} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {spec.y.map((col, i) => (
            <Bar key={col} dataKey={col} stackId="whole" fill={PALETTE[i % PALETTE.length]} isAnimationActive={false} name={niceLabel(col)} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // Grouped time series -> small multiples, never spaghetti.
  if (spec.kind === "multiples" && spec.facet) {
    const facet = spec.facet;
    const groups = [...new Set(data.map((r) => String(r[facet] ?? "")))];
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {groups.map((g, gi) => (
          <div key={g} className="rounded-lg border border-edge/70 p-2">
            <p className="mb-1 truncate text-[10px] font-semibold text-ink-dim" title={g}>{g}</p>
            <ResponsiveContainer width="100%" height={110}>
              <LineChart data={data.filter((r) => String(r[facet] ?? "") === g)} margin={{ top: 2, right: 4, bottom: 0, left: 0 }}>
                <XAxis dataKey={x} hide />
                <YAxis tick={{ ...AXIS, fontSize: 8 }} stroke={GRID} width={34} tickFormatter={(v) => compact(Number(v))} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Line type="monotone" dataKey={y} stroke={PALETTE[gi % PALETTE.length]} strokeWidth={1.5} dot={false} isAnimationActive={false} name={niceLabel(y)} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>
    );
  }

  if (spec.kind === "line") {
    // Descriptive least-squares trend, computed on the backend.
    const withTrend = spec.trend
      ? data.map((r, i) => ({ ...r, __trend: spec.trend!.values[i] }))
      : data;
    const gid = `grad-${y.replace(/[^a-zA-Z0-9]/g, "")}`;
    return (
      <div>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={withTrend} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={BLUE} stopOpacity={0.22} />
                <stop offset="100%" stopColor={BLUE} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={GRID} />
            <XAxis dataKey={x} tick={{ ...AXIS, fontSize: 9 }} stroke={GRID} minTickGap={30} />
            <YAxis tick={AXIS} stroke={GRID} tickFormatter={(v) => compact(Number(v))} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            {spec.threshold != null && (
              <ReferenceLine y={spec.threshold} stroke="var(--color-warn)" strokeDasharray="5 4"
                label={{ value: `threshold ${compact(spec.threshold)}`, fontSize: 10, fill: "var(--color-warn)", position: "insideTopRight" }} />
            )}
            <Area type="monotone" dataKey={y} stroke="none" fill={`url(#${gid})`}
              isAnimationActive={false} legendType="none" tooltipType="none" />
            <Line type="monotone" dataKey={y} stroke={BLUE} strokeWidth={2.2} dot={data.length <= 30} isAnimationActive={false} name={niceLabel(y)} />
            {spec.trend && (
              <Line type="linear" dataKey="__trend" stroke="var(--chart-axis)" strokeWidth={1.5}
                strokeDasharray="6 4" dot={false} isAnimationActive={false} name="trend" />
            )}
          </ComposedChart>
        </ResponsiveContainer>
        {spec.trend && (
          <p className="mt-0.5 text-[10px] text-ink-dim">
            Dashed line = the overall straight-line trend across the shown periods
            ({spec.trend.direction}) - a description of direction, not a forecast.
          </p>
        )}
      </div>
    );
  }

  if (spec.kind === "dbar") {
    // Diverging bars around zero: rises in blue, drops in orange (the
    // judgment amber/red stay reserved for warnings).
    return (
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={x} tick={{ ...AXIS, fontSize: 9 }} stroke={GRID} interval={0} angle={data.length > 8 ? -30 : 0} textAnchor={data.length > 8 ? "end" : "middle"} height={data.length > 8 ? 55 : 30} />
          <YAxis tick={AXIS} stroke={GRID} tickFormatter={(v) => compact(Number(v))} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--chart-cursor)" }} />
          <ReferenceLine y={0} stroke="var(--chart-axis)" />
          <Bar dataKey={y} isAnimationActive={false} name={niceLabel(y)} radius={[3, 3, 0, 0]}>
            {data.map((r, i) => (
              <Cell key={i} fill={Number(r[y]) >= 0 ? BLUE : "var(--chart-5)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (spec.kind === "hbar") {
    return (
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 30)}>
        <BarChart data={data} layout="vertical" margin={{ left: 40, right: 24 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          {/* Bars start at zero - honest lengths (rule 14). */}
          <XAxis type="number" tick={AXIS} stroke={GRID} domain={[0, "auto"]} tickFormatter={(v) => compact(Number(v))} />
          <YAxis type="category" dataKey={x} tick={{ ...AXIS, fontSize: 10 }} stroke={GRID} width={130} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--chart-cursor)" }} />
          {spec.threshold != null && (
            <ReferenceLine x={spec.threshold} stroke="var(--color-warn)" strokeDasharray="5 4"
              label={{ value: compact(spec.threshold), fontSize: 10, fill: "var(--color-warn)" }} />
          )}
          {spec.benchmark && (
            <ReferenceLine x={spec.benchmark.value} stroke="var(--chart-axis)" strokeDasharray="3 4"
              label={{ value: `${spec.benchmark.label} ${compact(spec.benchmark.value)}`, fontSize: 9, fill: "var(--chart-axis)", position: "insideBottomRight" }} />
          )}
          <Bar dataKey={y} radius={[0, 4, 4, 0]} isAnimationActive={false} name={niceLabel(y)}>
            {/* Color = category identity (colorblind-safe; amber/red reserved) */}
            {data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} fillOpacity={0.88} />
            ))}
            {/* On-chart callouts: each bar carries its value */}
            <LabelList dataKey={y} position="right"
              formatter={(v) => compact(Number(v))}
              style={{ fontSize: 9, fill: "var(--color-ink)" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={x} tick={{ ...AXIS, fontSize: 10 }} stroke={GRID} interval={0} angle={data.length > 8 ? -30 : 0} textAnchor={data.length > 8 ? "end" : "middle"} height={data.length > 8 ? 60 : 30} />
        <YAxis tick={AXIS} stroke={GRID} domain={[0, "auto"]} tickFormatter={(v) => compact(Number(v))} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--chart-cursor)" }} />
        {spec.threshold != null && (
          <ReferenceLine y={spec.threshold} stroke="var(--color-warn)" strokeDasharray="5 4"
            label={{ value: `threshold ${compact(spec.threshold)}`, fontSize: 10, fill: "var(--color-warn)", position: "insideTopRight" }} />
        )}
        {spec.benchmark && (
          <ReferenceLine y={spec.benchmark.value} stroke="var(--chart-axis)" strokeDasharray="3 4"
            label={{ value: `${spec.benchmark.label} ${compact(spec.benchmark.value)}`, fontSize: 9, fill: "var(--chart-axis)", position: "insideTopRight" }} />
        )}
        <Bar dataKey={y} radius={[4, 4, 0, 0]} isAnimationActive={false} name={niceLabel(y)}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} fillOpacity={0.88} />
          ))}
          <LabelList dataKey={y} position="top"
            formatter={(v) => compact(Number(v))}
            style={{ fontSize: 9, fill: "var(--color-ink)" }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// Chart components for run results (Recharts).
import { useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RunResult } from "../types";

const AXIS = { stroke: "var(--chart-axis)", fontSize: 11 };
const GRID = "var(--chart-grid)";
const PALETTE = [
  "var(--color-accent)",
  "var(--chart-2)",
  "var(--color-warn)",
  "var(--color-bad)",
  "var(--chart-6)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-8)",
  "var(--chart-axis)",
];

const TOOLTIP_STYLE = {
  backgroundColor: "var(--chart-tip-bg)",
  border: "1px solid var(--chart-tip-border)",
  borderRadius: 10,
  fontSize: 12,
  color: "var(--chart-tip-fg)",
  boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
};

export function ConfusionMatrix({
  labels,
  matrix,
}: {
  labels: string[];
  matrix: number[][];
}) {
  const max = Math.max(...matrix.flat(), 1);
  return (
    <div className="overflow-x-auto">
      <table className="mx-auto border-separate border-spacing-1">
        <thead>
          <tr>
            <th className="p-1 text-[10px] text-ink-dim">actual \ predicted</th>
            {labels.map((l) => (
              <th key={l} className="p-1 text-[11px] font-medium text-ink-dim">
                {l}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={i}>
              <td className="p-1 text-right text-[11px] font-medium text-ink-dim">
                {labels[i]}
              </td>
              {row.map((v, j) => {
                const heat = v / max;
                const onDiag = i === j;
                return (
                  <td
                    key={j}
                    className="h-12 w-16 rounded-md text-center text-sm font-semibold tabular-nums"
                    style={{
                      backgroundColor: onDiag
                        ? `rgba(5, 150, 105, ${0.12 + heat * 0.55})`
                        : `rgba(220, 38, 38, ${0.08 + heat * 0.45})`,
                    }}
                  >
                    {v}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FeatureImportanceChart({
  data,
}: {
  data: { feature: string; label?: string; importance: number }[];
}) {
  // Show human-friendly labels; the raw column name lives in the tooltip.
  const named = data.map((d) => ({ ...d, name: d.label ?? d.feature }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, named.length * 26)}>
      <BarChart data={named} layout="vertical" margin={{ left: 40, right: 16 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} stroke={GRID} />
        <YAxis
          type="category"
          dataKey="name"
          tick={{ ...AXIS, fontSize: 10 }}
          stroke={GRID}
          width={130}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ fill: "rgba(79,70,229,0.06)" }}
          formatter={(v, _n, item) => [v, (item?.payload as { feature?: string })?.feature ?? ""]}
        />
        <Bar dataKey="importance" fill="var(--color-accent)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ClusterScatter({
  points,
  axes,
}: {
  points: { x: number; y: number; cluster: number }[];
  axes: string[];
}) {
  const clusters = [...new Set(points.map((p) => p.cluster))].sort((a, b) => a - b);
  // Interactive controls: point radius + opacity sliders and per-group filters,
  // so dense overlapping clouds can be thinned out and inspected.
  const [size, setSize] = useState(2);
  const [opacity, setOpacity] = useState(0.75);
  const [hidden, setHidden] = useState<Set<number>>(new Set());

  const toggle = (c: number) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });

  const colorOf = (c: number, i: number) => (c === -1 ? "#94a3b8" : PALETTE[i % PALETTE.length]);

  return (
    <div>
      {/* Filters: click a group to show/hide it */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {clusters.map((c, i) => {
          const off = hidden.has(c);
          return (
            <button
              key={c}
              onClick={() => toggle(c)}
              title={off ? "Click to show this group" : "Click to hide this group"}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-all ${
                off ? "border-edge opacity-40" : "border-edge bg-panel-2"
              }`}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colorOf(c, i) }} />
              {c === -1 ? "noise" : `group ${c}`}
              <span className="tabular-nums text-ink-dim">
                {points.filter((p) => p.cluster === c).length}
              </span>
            </button>
          );
        })}
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis dataKey="x" name={axes[0]} tick={AXIS} stroke={GRID} type="number" />
          <YAxis dataKey="y" name={axes[1]} tick={AXIS} stroke={GRID} type="number" />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: "3 3" }} />
          {clusters
            .filter((c) => !hidden.has(c))
            .map((c) => (
              <Scatter
                key={`${c}-${size}`}
                name={c === -1 ? "noise" : `group ${c}`}
                data={points.filter((p) => p.cluster === c)}
                fill={colorOf(c, clusters.indexOf(c))}
                isAnimationActive={false}
                // Custom shape: exact pixel radius, reliably driven by the slider.
                shape={(props: { cx?: number; cy?: number; fill?: string }) => (
                  <circle
                    cx={props.cx}
                    cy={props.cy}
                    r={size}
                    fill={props.fill}
                    fillOpacity={opacity}
                  />
                )}
              />
            ))}
        </ScatterChart>
      </ResponsiveContainer>

      {/* Sliders */}
      <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-edge/60 pt-2">
        <label className="flex items-center gap-2 text-[11px] text-ink-dim">
          Point size
          <input
            type="range"
            min={1}
            max={12}
            value={size}
            onChange={(e) => setSize(Number(e.target.value))}
            className="w-28 accent-accent"
          />
          <span className="w-5 tabular-nums">{size}px</span>
        </label>
        <label className="flex items-center gap-2 text-[11px] text-ink-dim">
          Opacity
          <input
            type="range"
            min={10}
            max={100}
            value={Math.round(opacity * 100)}
            onChange={(e) => setOpacity(Number(e.target.value) / 100)}
            className="w-28 accent-accent"
          />
        </label>
        <span className="text-[10px] text-ink-dim">
          Shrink points or lower opacity to see through dense overlaps; click a group above to isolate it.
        </span>
      </div>
    </div>
  );
}

export function ClusterSizesChart({
  data,
}: {
  data: { cluster: number; count: number }[];
}) {
  const named = data.map((d) => ({
    name: d.cluster === -1 ? "noise" : `cluster ${d.cluster}`,
    count: d.count,
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={named}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="name" tick={AXIS} stroke={GRID} />
        <YAxis tick={AXIS} stroke={GRID} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(79,70,229,0.06)" }} />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {named.map((d, i) => (
            <Cell
              key={i}
              fill={d.name === "noise" ? "#94a3b8" : PALETTE[i % PALETTE.length]}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

type ForecastView = "focus" | "full" | "forecast";

const FORECAST_VIEWS: { key: ForecastView; label: string; hint: string }[] = [
  { key: "focus", label: "Recent + forecast", hint: "The last stretch of history plus the projection - the decision view." },
  { key: "full", label: "Full history", hint: "Everything the model saw. Long histories compress; switch back to zoom in." },
  { key: "forecast", label: "Forecast zoom", hint: "Just the projection with a short tail of history for anchoring." },
];

export function ForecastChart({
  series,
  forecast,
  uncertaintyPct,
  context,
}: {
  series: { t: string; actual: number; predicted?: number }[];
  forecast: { t: string; forecast: number }[];
  uncertaintyPct?: number | null;
  context?: { name: string; label?: string; values: (number | null)[] }[];
}) {
  const [view, setView] = useState<ForecastView>("focus");
  const [companion, setCompanion] = useState("");
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  const horizon = forecast.length;
  // How much history each view keeps.
  const keep =
    view === "full"
      ? series.length
      : view === "focus"
        ? Math.min(series.length, Math.max(3 * horizon, 30))
        : Math.min(series.length, Math.max(horizon, 10));
  const offset = series.length - keep;
  const hist = series.slice(offset);

  // Shaded band: forecast +/- holdout error (MAPE). Clamp so a bad fit stays readable.
  const pct = uncertaintyPct != null ? Math.min(uncertaintyPct, 50) : null;
  const last = hist[hist.length - 1];
  const combined: Record<string, unknown>[] = [
    ...hist.map((p, i) => {
      const row: Record<string, unknown> = { ...p };
      if (companion) {
        const ctx = context?.find((c) => c.name === companion);
        row.companion = ctx?.values[offset + i] ?? null;
      }
      return row;
    }),
    ...forecast.map((p) => {
      const row: Record<string, unknown> = { t: p.t, forecast: p.forecast };
      if (pct != null) row.band = [p.forecast * (1 - pct / 100), p.forecast * (1 + pct / 100)];
      return row;
    }),
  ];
  // Bridge the visual gap: dashed line starts from the last actual point.
  if (last && combined.length > hist.length) {
    combined[hist.length - 1] = {
      ...combined[hist.length - 1],
      forecast: last.actual,
      ...(pct != null ? { band: [last.actual, last.actual] } : {}),
    };
  }

  const activeView = FORECAST_VIEWS.find((v) => v.key === view)!;
  const companionLabel = context?.find((c) => c.name === companion)?.label ?? companion;
  const toggle = (key: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const LINES: { key: string; label: string; color: string }[] = [
    { key: "actual", label: "actual", color: "var(--chart-axis)" },
    { key: "predicted", label: "holdout check", color: "var(--color-warn)" },
    { key: "forecast", label: "forecast", color: "var(--color-accent)" },
  ];

  return (
    <div>
      {/* Controls: view selector, series toggles, companion overlay */}
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <div className="flex items-center gap-1">
          {FORECAST_VIEWS.map((v) => (
            <button
              key={v.key}
              onClick={() => setView(v.key)}
              className={`rounded-full border px-2.5 py-1 text-[11px] transition-all ${
                view === v.key
                  ? "border-accent/40 bg-accent/10 font-medium text-accent"
                  : "border-edge bg-panel-2 text-ink-dim"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          {LINES.map((l) => {
            const off = hidden.has(l.key);
            return (
              <button
                key={l.key}
                onClick={() => toggle(l.key)}
                title={off ? "Click to show this line" : "Click to hide this line"}
                className={`flex items-center gap-1.5 rounded-full border border-edge px-2.5 py-1 text-[11px] transition-all ${
                  off ? "opacity-40" : "bg-panel-2"
                }`}
              >
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: l.color }} />
                {l.label}
              </button>
            );
          })}
        </div>
        {context && context.length > 0 && (
          <label className="flex items-center gap-1.5 text-[11px] text-ink-dim">
            Also show
            <select
              value={companion}
              onChange={(e) => setCompanion(e.target.value)}
              className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-[11px] text-ink"
            >
              <option value="">none</option>
              {context.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.label ?? c.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={combined} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis
            dataKey="t"
            tick={{ ...AXIS, fontSize: 9 }}
            stroke={GRID}
            minTickGap={40}
            tickFormatter={(v) => String(v).split("T")[0]}
          />
          <YAxis yAxisId="left" tick={AXIS} stroke={GRID} domain={["auto", "auto"]} />
          {companion && (
            <YAxis yAxisId="right" orientation="right" tick={{ ...AXIS, fill: "var(--chart-4)" }} stroke={GRID} domain={["auto", "auto"]} />
          )}
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {pct != null && !hidden.has("forecast") && (
            <Area
              yAxisId="left"
              dataKey="band"
              stroke="none"
              fill="var(--color-accent)"
              fillOpacity={0.1}
              isAnimationActive={false}
              name={`likely range (+/- ${pct}%)`}
              legendType="none"
              tooltipType="none"
            />
          )}
          <Line yAxisId="left" type="monotone" dataKey="actual" stroke="var(--chart-axis)" dot={false} strokeWidth={1.5} name="actual" hide={hidden.has("actual")} isAnimationActive={false} />
          <Line yAxisId="left" type="monotone" dataKey="predicted" stroke="var(--color-warn)" dot={false} strokeWidth={2} name="holdout check" hide={hidden.has("predicted")} isAnimationActive={false} />
          <Line yAxisId="left" type="monotone" dataKey="forecast" stroke="var(--color-accent)" dot={false} strokeWidth={2} strokeDasharray="6 3" name="forecast" hide={hidden.has("forecast")} isAnimationActive={false} />
          {companion && (
            <Line yAxisId="right" type="monotone" dataKey="companion" stroke="var(--chart-4)" dot={false} strokeWidth={1.5} strokeDasharray="2 3" name={companionLabel} connectNulls isAnimationActive={false} />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <p className="mt-1 text-[10px] leading-snug text-ink-dim">
        {activeView.hint}
        {pct != null && !hidden.has("forecast") && ` Shaded band = the forecast +/- ${pct}% (the model's typical miss on held-back history).`}
        {companion && ` ${companionLabel} is drawn on the right-hand axis.`}
      </p>
    </div>
  );
}

export function PredictedVsActualChart({
  points,
}: {
  points: { actual: number; predicted: number }[];
}) {
  const vals = points.flatMap((p) => [p.actual, p.predicted]);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  // The diagonal = perfect prediction; drawn as a two-point line series.
  const diagonal = [
    { actual: lo, predicted: lo },
    { actual: hi, predicted: hi },
  ];
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={diagonal} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis
          dataKey="actual" type="number" name="actual" tick={AXIS} stroke={GRID}
          domain={[lo, hi]} tickFormatter={(v) => compact(v)}
        />
        <YAxis
          dataKey="predicted" type="number" name="predicted" tick={AXIS} stroke={GRID}
          domain={[lo, hi]} tickFormatter={(v) => compact(v)}
        />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: "3 3" }} />
        <Line dataKey="predicted" stroke="#94a3b8" strokeDasharray="5 4" dot={false} isAnimationActive={false} legendType="none" tooltipType="none" />
        <Scatter
          data={points} fill="var(--color-accent)" isAnimationActive={false}
          shape={(props: { cx?: number; cy?: number }) => (
            <circle cx={props.cx} cy={props.cy} r={2.5} fill="var(--color-accent)" fillOpacity={0.55} />
          )}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function ResidualHistChart({ data }: { data: { mid: number; count: number }[] }) {
  const named = data.map((d) => ({ ...d, name: compact(d.mid) }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={named}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="name" tick={{ ...AXIS, fontSize: 9 }} stroke={GRID} />
        <YAxis tick={AXIS} stroke={GRID} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(79,70,229,0.06)" }} />
        <Bar dataKey="count" radius={[3, 3, 0, 0]}>
          {named.map((d, i) => (
            <Cell key={i} fill={d.mid < 0 ? "var(--color-warn)" : "var(--color-accent)"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function compact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${(v / 1_000).toFixed(0)}k`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return `${Math.round(v * 100) / 100}`;
}

export function ClassDistributionChart({
  data,
}: {
  data: { label: string; count: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={AXIS} stroke={GRID} />
        <YAxis tick={AXIS} stroke={GRID} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(79,70,229,0.06)" }} />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ResultCharts({ result }: { result: RunResult }) {
  const a = result.artifacts;
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      {a.confusion_matrix && (
        <ChartPanel
          title="Right vs wrong predictions"
          caption="Rows = what actually happened, columns = what the model predicted. Green cells (the diagonal) are correct; red cells are mistakes."
        >
          <ConfusionMatrix labels={a.confusion_matrix.labels} matrix={a.confusion_matrix.matrix} />
        </ChartPanel>
      )}
      {a.feature_importance && a.feature_importance.length > 0 && (
        <ChartPanel
          title="What influenced predictions most"
          caption="Longer bars = bigger influence on the model's predictions. Hover a bar to see the raw column name."
        >
          <FeatureImportanceChart data={a.feature_importance} />
        </ChartPanel>
      )}
      {a.class_distribution && (
        <ChartPanel
          title="How the outcomes are split"
          caption="How many rows fall into each outcome. A very lopsided split makes plain accuracy misleading."
        >
          <ClassDistributionChart data={a.class_distribution} />
        </ChartPanel>
      )}
      {a.scatter && (
        <ChartPanel
          title="The groups, mapped"
          caption="Each dot is one row, placed by its overall similarity and colored by group. Clear color islands = well-separated groups."
          wide
        >
          <ClusterScatter points={a.scatter.points} axes={a.scatter.axes} />
        </ChartPanel>
      )}
      {a.cluster_sizes && (
        <ChartPanel
          title="Group sizes"
          caption="How many rows landed in each group. 'Noise' means rows that didn't fit any pattern."
        >
          <ClusterSizesChart data={a.cluster_sizes} />
        </ChartPanel>
      )}
      {a.predicted_vs_actual && (
        <ChartPanel
          title="Predicted vs actual"
          caption="Each dot is one held-out record. Dots on the dashed line = perfect predictions; dots above it were over-predicted, below it under-predicted."
        >
          <PredictedVsActualChart points={a.predicted_vs_actual.points} />
        </ChartPanel>
      )}
      {a.residual_hist && (
        <ChartPanel
          title="Where the misses land"
          caption="How far off each held-out prediction was. Centered on zero is healthy; a lopsided shape means the model leans high or low."
        >
          <ResidualHistChart data={a.residual_hist} />
        </ChartPanel>
      )}
      {a.series && a.forecast && (
        <ChartPanel
          title="History & forecast"
          caption="Grey = what actually happened. Amber = the model's practice run on held-back history (closer to grey is better). Dashed blue = the projection. Use the buttons to change view, hide lines, or overlay another measure."
          wide
        >
          <ForecastChart
            series={a.series}
            forecast={a.forecast}
            uncertaintyPct={result.metrics.mape_pct ?? null}
            context={a.context_series}
          />
        </ChartPanel>
      )}
    </div>
  );
}

function ChartPanel({
  title,
  caption,
  wide,
  children,
}: {
  title: string;
  caption?: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`rounded-2xl border border-edge bg-panel p-4 shadow-sm ${wide ? "lg:col-span-2" : ""}`}
    >
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-dim">
        {title}
      </h4>
      {caption && <p className="mb-3 text-[11px] leading-snug text-ink-dim">{caption}</p>}
      {children}
    </div>
  );
}

// Chart components for run results (Recharts).
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { RunResult } from "../types";

const AXIS = { stroke: "#64748b", fontSize: 11 };
const GRID = "#dde3ee";
const PALETTE = [
  "#4f46e5",
  "#059669",
  "#d97706",
  "#dc2626",
  "#7c3aed",
  "#0891b2",
  "#ea580c",
  "#c026d3",
  "#64748b",
];

const TOOLTIP_STYLE = {
  backgroundColor: "rgba(255,255,255,0.95)",
  border: "1px solid #dde3ee",
  borderRadius: 10,
  fontSize: 12,
  color: "#0f172a",
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
        <Bar dataKey="importance" fill="#4f46e5" radius={[0, 4, 4, 0]} />
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
  // Interactive controls: point size + opacity sliders and per-group filters,
  // so dense overlapping clouds can be thinned out and inspected.
  const [size, setSize] = useState(18);
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
                off ? "border-edge opacity-40" : "border-edge bg-white/50"
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
          <ZAxis range={[size, size]} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: "3 3" }} />
          {clusters
            .filter((c) => !hidden.has(c))
            .map((c) => (
              <Scatter
                key={c}
                name={c === -1 ? "noise" : `group ${c}`}
                data={points.filter((p) => p.cluster === c)}
                fill={colorOf(c, clusters.indexOf(c))}
                fillOpacity={opacity}
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
            min={4}
            max={60}
            value={size}
            onChange={(e) => setSize(Number(e.target.value))}
            className="w-28 accent-[#4f46e5]"
          />
        </label>
        <label className="flex items-center gap-2 text-[11px] text-ink-dim">
          Opacity
          <input
            type="range"
            min={10}
            max={100}
            value={Math.round(opacity * 100)}
            onChange={(e) => setOpacity(Number(e.target.value) / 100)}
            className="w-28 accent-[#4f46e5]"
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

export function ForecastChart({
  series,
  forecast,
}: {
  series: { t: string; actual: number; predicted?: number }[];
  forecast: { t: string; forecast: number }[];
}) {
  // Stitch history + future into one x-axis.
  const combined = [
    ...series.map((p) => ({ ...p })),
    ...forecast.map((p) => ({ t: p.t, forecast: p.forecast })),
  ];
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={combined} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis dataKey="t" tick={{ ...AXIS, fontSize: 9 }} stroke={GRID} minTickGap={40} />
        <YAxis tick={AXIS} stroke={GRID} domain={["auto", "auto"]} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="actual" stroke="#64748b" dot={false} strokeWidth={1.5} name="actual" />
        <Line type="monotone" dataKey="predicted" stroke="#d97706" dot={false} strokeWidth={2} name="holdout prediction" />
        <Line type="monotone" dataKey="forecast" stroke="#4f46e5" dot={false} strokeWidth={2} strokeDasharray="6 3" name="forecast" />
      </LineChart>
    </ResponsiveContainer>
  );
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
    <div className="grid gap-6 lg:grid-cols-2">
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
      {a.series && a.forecast && (
        <ChartPanel
          title="History & forecast"
          caption="Grey = what actually happened. Amber = the model's practice run on held-back history (closer to grey is better). Dashed blue = the projection."
          wide
        >
          <ForecastChart series={a.series} forecast={a.forecast} />
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
      className={`rounded-xl border border-edge bg-panel p-4 backdrop-blur-xl ${wide ? "lg:col-span-2" : ""}`}
    >
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-dim">
        {title}
      </h4>
      {caption && <p className="mb-3 text-[11px] leading-snug text-ink-dim">{caption}</p>}
      {children}
    </div>
  );
}

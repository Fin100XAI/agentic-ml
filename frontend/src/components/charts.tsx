// Chart components for run results (Recharts).
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
  data: { feature: string; importance: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 26)}>
      <BarChart data={data} layout="vertical" margin={{ left: 40, right: 16 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} stroke={GRID} />
        <YAxis
          type="category"
          dataKey="feature"
          tick={{ ...AXIS, fontSize: 10 }}
          stroke={GRID}
          width={120}
        />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(79,70,229,0.06)" }} />
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
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis dataKey="x" name={axes[0]} tick={AXIS} stroke={GRID} type="number" />
        <YAxis dataKey="y" name={axes[1]} tick={AXIS} stroke={GRID} type="number" />
        <ZAxis range={[18, 18]} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: "3 3" }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {clusters.map((c, i) => (
          <Scatter
            key={c}
            name={c === -1 ? "noise" : `cluster ${c}`}
            data={points.filter((p) => p.cluster === c)}
            fill={c === -1 ? "#94a3b8" : PALETTE[i % PALETTE.length]}
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
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
        <ChartPanel title="Confusion matrix">
          <ConfusionMatrix labels={a.confusion_matrix.labels} matrix={a.confusion_matrix.matrix} />
        </ChartPanel>
      )}
      {a.feature_importance && a.feature_importance.length > 0 && (
        <ChartPanel title="Feature importance">
          <FeatureImportanceChart data={a.feature_importance} />
        </ChartPanel>
      )}
      {a.class_distribution && (
        <ChartPanel title="Class distribution">
          <ClassDistributionChart data={a.class_distribution} />
        </ChartPanel>
      )}
      {a.scatter && (
        <ChartPanel title={`Clusters (${a.scatter.axes.filter(Boolean).join(" vs ")})`} wide>
          <ClusterScatter points={a.scatter.points} axes={a.scatter.axes} />
        </ChartPanel>
      )}
      {a.cluster_sizes && (
        <ChartPanel title="Cluster sizes">
          <ClusterSizesChart data={a.cluster_sizes} />
        </ChartPanel>
      )}
      {a.series && a.forecast && (
        <ChartPanel title="History, holdout fit & forecast" wide>
          <ForecastChart series={a.series} forecast={a.forecast} />
        </ChartPanel>
      )}
    </div>
  );
}

function ChartPanel({
  title,
  wide,
  children,
}: {
  title: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`rounded-xl border border-edge bg-panel p-4 ${wide ? "lg:col-span-2" : ""}`}
    >
      <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-dim">
        {title}
      </h4>
      {children}
    </div>
  );
}

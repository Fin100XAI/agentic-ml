// Renders a backend-chosen ChartSpec (deterministic, rule 14). The frontend
// never picks the chart type - it draws exactly what the shape mapper chose.
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec, QueryResult } from "../types";

const AXIS = { stroke: "#64748b", fontSize: 11 };
const GRID = "#dde3ee";
const BLUE = "#1d4ed8";

const TOOLTIP_STYLE = {
  backgroundColor: "rgba(255,255,255,0.95)",
  border: "1px solid #dde3ee",
  borderRadius: 10,
  fontSize: 12,
  color: "#0f172a",
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

export function QueryChart({ spec, result }: { spec: ChartSpec; result: QueryResult }) {
  const rows = result.table;

  if (spec.kind === "kpi") {
    return (
      <div className="flex flex-wrap gap-3">
        {spec.y.map((col) => {
          const v = rows[0]?.[col];
          return (
            <div key={col} className="min-w-[140px] flex-1 rounded-xl border border-edge bg-white p-4">
              <div className="text-[11px] uppercase tracking-wider text-ink-dim">{niceLabel(col)}</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums text-ink">
                {typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v ?? "-")}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (spec.kind === "table" || !spec.x || spec.y.length === 0) {
    return spec.note ? <p className="text-[11px] text-ink-dim">{spec.note}</p> : null;
  }

  const x = spec.x;
  const y = spec.y[0];
  const data = rows.map((r) => ({ ...r, [x]: String(r[x] ?? "") }));

  if (spec.kind === "line") {
    return (
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis dataKey={x} tick={{ ...AXIS, fontSize: 9 }} stroke={GRID} minTickGap={30} />
          <YAxis tick={AXIS} stroke={GRID} tickFormatter={(v) => compact(Number(v))} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          {spec.threshold != null && (
            <ReferenceLine y={spec.threshold} stroke="#d97706" strokeDasharray="5 4"
              label={{ value: `threshold ${compact(spec.threshold)}`, fontSize: 10, fill: "#d97706", position: "insideTopRight" }} />
          )}
          <Line type="monotone" dataKey={y} stroke={BLUE} strokeWidth={2} dot={data.length <= 30} isAnimationActive={false} name={niceLabel(y)} />
        </LineChart>
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
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(29,78,216,0.06)" }} />
          {spec.threshold != null && (
            <ReferenceLine x={spec.threshold} stroke="#d97706" strokeDasharray="5 4"
              label={{ value: compact(spec.threshold), fontSize: 10, fill: "#d97706" }} />
          )}
          <Bar dataKey={y} fill={BLUE} radius={[0, 4, 4, 0]} isAnimationActive={false} name={niceLabel(y)} />
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
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(29,78,216,0.06)" }} />
        {spec.threshold != null && (
          <ReferenceLine y={spec.threshold} stroke="#d97706" strokeDasharray="5 4"
            label={{ value: `threshold ${compact(spec.threshold)}`, fontSize: 10, fill: "#d97706", position: "insideTopRight" }} />
        )}
        <Bar dataKey={y} fill={BLUE} radius={[4, 4, 0, 0]} isAnimationActive={false} name={niceLabel(y)} />
      </BarChart>
    </ResponsiveContainer>
  );
}

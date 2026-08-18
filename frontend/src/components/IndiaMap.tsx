// Choropleth for boundary-matched results (P2.2). Renders bundled GeoJSON
// as plain SVG (equirectangular projection - fine at country scale, zero
// dependencies). Sequential blue ramp; unmatched areas grey; legend always
// shown; red/amber stay reserved for judgment states.
import { useEffect, useMemo, useState } from "react";

interface GeoFeature {
  properties: { name: string };
  geometry: { type: string; coordinates: number[][][][] };
}

const geoCache = new Map<string, GeoFeature[]>();

function mix(a: number[], b: number[], t: number): string {
  const c = a.map((av, i) => Math.round(av + (b[i] - av) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

const BLUE_LO = [219, 234, 254]; // #dbeafe
const BLUE_HI = [29, 78, 216]; // #1d4ed8
const ORANGE_LO = [255, 237, 213]; // #ffedd5
const ORANGE_HI = [234, 88, 12]; // #ea580c
const AMBER = "#d97706";

function ramp(t: number): string {
  return mix(BLUE_LO, BLUE_HI, t);
}

// Quantile class breaks (5 classes): robust to one giant value washing out
// the rest - each class holds roughly a fifth of the areas.
function quantileBreaks(vals: number[], classes = 5): number[] {
  const sorted = [...vals].sort((a, b) => a - b);
  const breaks: number[] = [];
  for (let i = 1; i < classes; i++) {
    breaks.push(sorted[Math.min(sorted.length - 1, Math.floor((i * sorted.length) / classes))]);
  }
  return breaks;
}

function classOf(v: number, breaks: number[]): number {
  let c = 0;
  for (const b of breaks) if (v >= b) c++;
  return c; // 0..breaks.length
}

function compact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return `${Math.round(v * 100) / 100}`;
}

export function IndiaMap({
  level,
  matches,
  values,
  metricLabel,
  mode = "sequential",
  threshold = null,
}: {
  level: string;
  matches: Record<string, string>; // result key -> boundary name
  values: Record<string, number>; // result key -> metric value
  metricLabel: string;
  mode?: "sequential" | "diverging" | "judgment";
  threshold?: number | null;
}) {
  const [features, setFeatures] = useState<GeoFeature[] | null>(
    geoCache.get(level) ?? null,
  );
  const [hover, setHover] = useState<string | null>(null);

  useEffect(() => {
    if (geoCache.has(level)) return;
    fetch(`/api/geo/${level}`)
      .then((r) => r.json())
      .then((gj) => {
        geoCache.set(level, gj.features);
        setFeatures(gj.features);
      })
      .catch(() => {});
  }, [level]);

  // boundary name -> value via the backend's deterministic matching
  const valueByBoundary = useMemo(() => {
    const out: Record<string, number> = {};
    for (const [key, boundary] of Object.entries(matches)) {
      if (typeof values[key] === "number") out[boundary] = values[key];
    }
    return out;
  }, [matches, values]);

  const view = useMemo(() => {
    if (!features) return null;
    const colored = features.filter((f) => f.properties.name in valueByBoundary);
    const focus = colored.length > 0 ? colored : features;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const f of focus) {
      for (const poly of f.geometry.coordinates) {
        for (const [x, y] of poly[0]) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    const pad = Math.max(maxX - minX, maxY - minY) * 0.06 + 0.1;
    minX -= pad; maxX += pad; minY -= pad; maxY += pad;
    // Same footprint as the other chart tiles - the map must not dominate.
    const W = 460;
    const H = Math.max(200, Math.min(280, (W * (maxY - minY)) / (maxX - minX)));
    const sx = W / (maxX - minX);
    const sy = H / (maxY - minY);
    const s = Math.min(sx, sy);
    const px = (x: number) => (x - minX) * s;
    const py = (y: number) => H - (y - minY) * s;
    const paths = features.map((f) => {
      let d = "";
      for (const poly of f.geometry.coordinates) {
        for (const ring of poly) {
          d += ring.map(([x, y], i) =>
            `${i === 0 ? "M" : "L"}${px(x).toFixed(1)},${py(y).toFixed(1)}`,
          ).join("") + "Z";
        }
      }
      return { name: f.properties.name, d };
    });
    return { W, H, paths };
  }, [features, valueByBoundary]);

  if (!view) {
    return <p className="text-[11px] text-ink-dim">Loading the map...</p>;
  }

  const vals = Object.values(valueByBoundary);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const breaks = quantileBreaks(vals);
  const maxAbs = Math.max(Math.abs(lo), Math.abs(hi)) || 1;

  const fillFor = (v: number): string => {
    if (mode === "judgment") return AMBER; // the selected areas ARE the flagged set
    if (mode === "diverging") {
      // zero-centered: rises in blue, falls in orange
      const t = Math.min(1, Math.abs(v) / maxAbs);
      return v >= 0 ? mix(BLUE_LO, BLUE_HI, t) : mix(ORANGE_LO, ORANGE_HI, t);
    }
    // sequential: 5 quantile classes - robust to one giant value
    return ramp(breaks.length ? classOf(v, breaks) / breaks.length : 1);
  };

  return (
    <div>
      <svg viewBox={`0 0 ${view.W} ${view.H}`} className="w-full" role="img"
        aria-label={`Map of ${metricLabel} by area`}>
        {view.paths.map((p) => {
          const v = valueByBoundary[p.name];
          const isColored = typeof v === "number";
          return (
            <path
              key={p.name}
              d={p.d}
              fill={isColored ? fillFor(v) : "#e2e8f0"}
              stroke="#ffffff"
              strokeWidth={0.6}
              opacity={hover && hover !== p.name ? 0.55 : 1}
              onMouseEnter={() => setHover(p.name)}
              onMouseLeave={() => setHover(null)}
            >
              <title>
                {p.name}{isColored ? `: ${v.toLocaleString()}` : " - no data in this result"}
              </title>
            </path>
          );
        })}
      </svg>
      {/* Legend: always shown, matched to the coloring mode */}
      {mode === "judgment" ? (
        <div className="mt-1 flex items-center gap-2 text-[10px] text-ink-dim">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: AMBER }} />
          flagged by your question{threshold != null ? ` (below ${compact(threshold)})` : ""}
          <span className="ml-auto flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#e2e8f0]" /> not in this result
          </span>
        </div>
      ) : mode === "diverging" ? (
        <div className="mt-1 flex items-center gap-2 text-[10px] text-ink-dim">
          <span className="tabular-nums">{compact(-maxAbs)}</span>
          <div className="h-2 w-28 rounded-full"
            style={{ background: `linear-gradient(to right, ${mix(ORANGE_LO, ORANGE_HI, 1)}, ${mix(ORANGE_LO, ORANGE_HI, 0.1)}, ${mix(BLUE_LO, BLUE_HI, 0.1)}, ${mix(BLUE_LO, BLUE_HI, 1)})` }} />
          <span className="tabular-nums">+{compact(maxAbs)}</span>
          <span className="ml-2">{metricLabel} (fell / rose)</span>
          <span className="ml-auto flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#e2e8f0]" /> no data
          </span>
        </div>
      ) : (
        <div className="mt-1 flex items-center gap-2 text-[10px] text-ink-dim">
          <span className="tabular-nums">{compact(lo)}</span>
          <div className="flex h-2 w-28 overflow-hidden rounded-full">
            {[0, 1, 2, 3, 4].map((c) => (
              <div key={c} className="h-full flex-1" style={{ background: ramp(c / 4) }} />
            ))}
          </div>
          <span className="tabular-nums">{compact(hi)}</span>
          <span className="ml-2">{metricLabel} - darker fifth = higher fifth</span>
          <span className="ml-auto flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#e2e8f0]" /> no data
          </span>
        </div>
      )}
      {hover && (
        <p className="mt-0.5 text-[11px] font-medium">
          {hover}
          {typeof valueByBoundary[hover] === "number"
            ? `: ${valueByBoundary[hover].toLocaleString()}`
            : " - no data in this result"}
        </p>
      )}
    </div>
  );
}

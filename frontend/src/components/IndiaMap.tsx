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

function ramp(t: number): string {
  // #dbeafe -> #1d4ed8
  const a = [219, 234, 254];
  const b = [29, 78, 216];
  const c = a.map((av, i) => Math.round(av + (b[i] - av) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
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
}: {
  level: string;
  matches: Record<string, string>; // result key -> boundary name
  values: Record<string, number>; // result key -> metric value
  metricLabel: string;
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
    const W = 460;
    const H = Math.max(240, Math.min(460, (W * (maxY - minY)) / (maxX - minX)));
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
  const span = hi - lo || 1;

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
              fill={isColored ? ramp((v - lo) / span) : "#e2e8f0"}
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
      {/* Legend: always shown */}
      <div className="mt-1 flex items-center gap-2 text-[10px] text-ink-dim">
        <span className="tabular-nums">{compact(lo)}</span>
        <div className="h-2 w-28 rounded-full"
          style={{ background: `linear-gradient(to right, ${ramp(0)}, ${ramp(1)})` }} />
        <span className="tabular-nums">{compact(hi)}</span>
        <span className="ml-2">{metricLabel}</span>
        <span className="ml-auto flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#e2e8f0]" /> no data
        </span>
      </div>
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

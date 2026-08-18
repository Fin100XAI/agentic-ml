// Analytics path: the exploring agents run starter questions the moment the
// user arrives (deterministic plans through the same executor as Ask), and
// present the initial findings as chart cards under a dataset KPI strip and
// an expandable data description. From here the user takes over with their
// own questions; the whole board downloads as a briefing file.
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  Compass,
  Database,
  Download,
  Lightbulb,
  MessageSquareText,
  RefreshCw,
} from "lucide-react";
import { api } from "../../api/client";
import type { DataOverview, ExploreFinding, ExploreResponse, OverviewColumn, PlaceCheck } from "../../types";
import { genLabel } from "../../lib/labels";
import { saveBlob } from "../../lib/download";
import { QueryChartWithMap } from "../QueryChart";
import { Badge, Button, Card, CardBody, CardHeader, Spinner } from "../ui";

// Boards survive leaving the screen (e.g. into Ask and back) so returning is
// instant and the exploration is not re-run - and not re-logged - each visit.
// The in-flight promise doubles as a StrictMode/double-mount guard: one
// exploration per dataset, ever, unless it failed.
const boardCache = new Map<string, ExploreResponse>();
const inFlight = new Map<string, Promise<ExploreResponse>>();
const overviewCache = new Map<string, DataOverview>();
const overviewInFlight = new Map<string, Promise<DataOverview>>();

const ROLE_LABEL: Record<string, string> = {
  numeric: "number",
  categorical: "category",
  datetime: "date/time",
  boolean: "yes/no",
  identifier: "identifier",
  text: "text",
};

function fmt(v: number | null | undefined): string {
  if (v == null) return "-";
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${(v / 1_000).toFixed(0)}k`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return `${Math.round(v * 100) / 100}`;
}

export function AnalyticsScreen({
  datasetId,
  filename,
  onAsk,
  onBack,
}: {
  datasetId: string;
  filename: string;
  onAsk: (question?: string) => void;
  onBack: () => void;
}) {
  // Phrasing language (AI-only; heuristic fallback stays English, badged).
  const [lang, setLang] = useState(() => sessionStorage.getItem("board-lang") ?? "en");
  const cacheKey = `${datasetId}|${lang}`;
  const cached = boardCache.get(cacheKey) ?? null;
  const [resp, setResp] = useState<ExploreResponse | null>(cached);
  const [busy, setBusy] = useState(cached === null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [overview, setOverview] = useState<DataOverview | null>(
    overviewCache.get(datasetId) ?? null,
  );
  const [aboutOpen, setAboutOpen] = useState(false);
  // Place Harmonizer: proposals reviewed here, applied only on approval.
  const [placeCheck, setPlaceCheck] = useState<PlaceCheck | null>(null);
  const [placeDismissed, setPlaceDismissed] = useState(false);
  const [placeBusy, setPlaceBusy] = useState(false);
  const [placeTicks, setPlaceTicks] = useState<Set<string>>(new Set());

  const applyPlaces = async () => {
    if (!placeCheck) return;
    setPlaceBusy(true);
    setError(null);
    try {
      // Let any in-flight exploration settle first - otherwise its pre-merge
      // result would land in the cache after the merge and look current.
      await inFlight.get(cacheKey)?.catch(() => {});
      inFlight.delete(cacheKey);
      for (const col of placeCheck.columns) {
        const mapping: Record<string, string> = {};
        for (const p of col.proposals) {
          if (!placeTicks.has(`${col.column}|${p.canonical}`)) continue;
          for (const v of p.variants) mapping[v] = p.canonical;
        }
        if (Object.keys(mapping).length > 0) {
          await api.harmonizePlaces(datasetId, col.column, mapping);
        }
      }
      // The data changed: clear caches (every language) and re-explore.
      for (const k of [...boardCache.keys()]) {
        if (k.startsWith(`${datasetId}|`)) boardCache.delete(k);
      }
      overviewCache.delete(datasetId);
      setPlaceCheck(null);
      setOverview(null);
      api.datasetOverview(datasetId).then((o) => {
        overviewCache.set(datasetId, o);
        setOverview(o);
      }).catch(() => {});
      await explore();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPlaceBusy(false);
    }
  };

  const explore = async () => {
    setBusy(true);
    setError(null);
    try {
      let p = inFlight.get(cacheKey);
      if (!p) {
        p = api.explore(datasetId, lang);
        inFlight.set(cacheKey, p);
      }
      const r = await p;
      boardCache.set(cacheKey, r);
      setResp(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      inFlight.delete(cacheKey);
      setBusy(false);
    }
  };

  useEffect(() => {
    // Scan for split place spellings once per visit; proposals only.
    api.placeCheck(datasetId)
      .then((pc) => {
        if (pc.columns.length > 0) {
          setPlaceCheck(pc);
          // default: everything ticked - one click fixes the common case
          setPlaceTicks(new Set(pc.columns.flatMap((c) =>
            c.proposals.map((p) => `${c.column}|${p.canonical}`))));
        }
      })
      .catch(() => {});
    const c = boardCache.get(cacheKey);
    if (c) {
      setResp(c);
      setBusy(false);
    } else {
      setResp(null);
      void explore();
    }
    if (!overviewCache.has(datasetId)) {
      let p = overviewInFlight.get(datasetId);
      if (!p) {
        p = api.datasetOverview(datasetId);
        overviewInFlight.set(datasetId, p);
      }
      p.then((o) => {
        overviewCache.set(datasetId, o);
        setOverview(o);
      })
        .catch(() => {})
        .finally(() => overviewInFlight.delete(datasetId));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, lang]);

  const downloadBoard = async () => {
    if (!resp) return;
    setExporting(true);
    try {
      const blob = await api.exploreExportMd(
        datasetId,
        resp.findings.map((f) => ({
          question: f.question,
          headline: f.headline,
          meaning: f.meaning,
          sentences: f.sentences,
          table: f.result.table.slice(0, 50),
        })),
        resp.synthesis,
      );
      saveBlob(blob, "initial-findings.md");
    } finally {
      setExporting(false);
    }
  };

  const prof = overview?.profile;
  const nNumeric = prof?.columns.filter((c) => c.role === "numeric").length ?? null;
  const nCategory = prof?.columns.filter((c) => c.role === "categorical" || c.role === "boolean").length ?? null;

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      {/* Header row: title left, actions right */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-bold">
          <Compass className="h-5 w-5 text-accent" /> Initial findings
          <span className="hidden text-sm font-normal text-ink-dim sm:inline">· {filename}</span>
        </h2>
        <div className="flex items-center gap-2">
          <select
            value={lang}
            onChange={(e) => {
              setLang(e.target.value);
              sessionStorage.setItem("board-lang", e.target.value);
            }}
            title="Language for the AI-written headlines and takeaways (numbers stay as computed; without AI the fallback text is English)"
            className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-[11px] text-ink outline-none focus:border-accent"
          >
            <option value="en">English</option>
            <option value="hi">हिंदी</option>
            <option value="mr">मराठी</option>
          </select>
          {resp && resp.findings.length > 0 && (
            <Button variant="outline" size="sm" onClick={downloadBoard} disabled={exporting}>
              {exporting ? <Spinner /> : <Download className="h-3.5 w-3.5" />} Briefing
            </Button>
          )}
          <Button size="sm" onClick={() => onAsk()}>
            <MessageSquareText className="h-3.5 w-3.5" />
            {busy ? "Skip - ask directly" : "Ask a question"}
          </Button>
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </Button>
        </div>
      </div>

      {/* Dataset KPI strip */}
      {prof && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Kpi label="Rows" value={prof.n_rows.toLocaleString()} />
          <Kpi label="Columns" value={String(prof.n_cols)} sub={`${nNumeric} numbers · ${nCategory} categories`} />
          <Kpi
            label="Missing data"
            value={`${(prof.missingness.pct_missing ?? 0).toFixed(1)}%`}
            sub={
              prof.missingness.columns_with_missing.length > 0
                ? `${prof.missingness.columns_with_missing.length} column(s) affected`
                : "no gaps found"
            }
            warn={(prof.missingness.pct_missing ?? 0) > 5}
          />
          <button
            onClick={() => setAboutOpen((o) => !o)}
            className="flex flex-col justify-center rounded-xl border border-edge bg-panel p-3 text-left shadow-sm transition-colors hover:border-accent/40"
          >
            <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
              <Database className="h-3 w-3" /> About this data
            </span>
            <span className="mt-0.5 flex items-center gap-1 text-sm font-medium text-accent">
              {aboutOpen ? "Hide" : "Columns & distributions"}
              {aboutOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </span>
          </button>
        </div>
      )}

      {/* Data description: every column with its distribution */}
      {aboutOpen && prof && (
        <Card>
          <CardHeader
            title="What is in this data"
            subtitle="Computed directly from the file - types, gaps and distributions. No AI involved."
          />
          <CardBody>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {prof.columns.map((c) => (
                <ColumnCard key={c.name} col={c} />
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {busy && (
        <Card>
          <CardBody className="flex items-center gap-3 py-8">
            <Spinner />
            <p className="text-sm text-ink-dim">
              The exploring agents are asking the first questions and computing every answer
              from the data - or skip straight to asking your own.
            </p>
          </CardBody>
        </Card>
      )}

      {error && (
        <Card className="border-bad/40">
          <CardBody className="flex items-center justify-between gap-3">
            <p className="text-xs text-bad">{error}</p>
            <Button variant="outline" size="sm" onClick={explore}>
              <RefreshCw className="h-3.5 w-3.5" /> Try again
            </Button>
          </CardBody>
        </Card>
      )}

      {/* Place Harmonizer: split spellings silently split totals - review
          the proposed merges before any number is trusted. */}
      {placeCheck && !placeDismissed && (
        <Card className="border-warn/40">
          <CardBody>
            <h3 className="text-sm font-semibold">Same place, different spellings?</h3>
            <p className="mt-0.5 text-[11px] text-ink-dim">
              Split spellings split your totals. Untick anything that is genuinely
              different, then merge - the original file stays untouched, and the
              approved spellings are remembered for future files.
            </p>
            <div className="mt-2 space-y-2">
              {placeCheck.columns.map((col) =>
                col.proposals.map((p) => {
                  const key = `${col.column}|${p.canonical}`;
                  return (
                    <label key={key} className="flex items-start gap-2 rounded-lg border border-edge bg-panel-2/60 px-3 py-2">
                      <input
                        type="checkbox"
                        checked={placeTicks.has(key)}
                        onChange={() =>
                          setPlaceTicks((s) => {
                            const next = new Set(s);
                            if (next.has(key)) next.delete(key);
                            else next.add(key);
                            return next;
                          })
                        }
                        className="mt-0.5 accent-[#1d4ed8]"
                      />
                      <span className="min-w-0 text-xs leading-relaxed">
                        In <span className="font-semibold">{col.column}</span>:{" "}
                        {p.variants.map((v) => `'${v}' (${p.counts[v] ?? 0})`).join(", ")}
                        {" -> "}
                        <span className="font-semibold">{p.canonical}</span>
                        <span className="ml-1.5 rounded-full bg-slate-500/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-ink-dim">
                          {p.source}
                        </span>
                      </span>
                    </label>
                  );
                }),
              )}
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setPlaceDismissed(true)}>
                Keep as is
              </Button>
              <Button size="sm" onClick={applyPlaces}
                disabled={placeBusy || placeTicks.size === 0}>
                {placeBusy ? <Spinner /> : null} Merge & recompute
              </Button>
            </div>
          </CardBody>
        </Card>
      )}

      {/* The analyst's takeaway across all findings */}
      {!busy && resp && resp.synthesis && resp.findings.length > 0 && (
        <Card className="border-accent/30 bg-accent-soft/20">
          <CardBody className="flex items-start gap-3">
            <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                  What to take away
                </span>
                <Badge tone={resp.generated_by === "claude" ? "accent" : "neutral"}>
                  {genLabel(resp.generated_by)}
                </Badge>
              </div>
              <p className="mt-1 text-sm leading-relaxed">{resp.synthesis}</p>
            </div>
          </CardBody>
        </Card>
      )}

      {!busy && resp && resp.findings.length === 0 && (
        <Card>
          <CardBody>
            <p className="text-sm text-ink-dim">
              The agents could not form starter questions from this file's columns - ask your
              own question instead.
            </p>
          </CardBody>
        </Card>
      )}

      {/* Findings grid: wide charts span the full row */}
      {!busy && resp && resp.findings.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {resp.findings.map((f, i) => (
            <div
              key={i}
              className={f.chart.kind === "line" || f.chart.kind === "table" ? "lg:col-span-2" : ""}
            >
              <FindingCard
                finding={f}
                generatedBy={resp.generated_by}
                onAsk={onAsk}
                numericColumns={prof?.columns.filter((c) => c.role === "numeric").map((c) => c.name) ?? []}
              />
            </div>
          ))}
        </div>
      )}

      {!busy && resp && (
        <Card className="border-accent/30">
          <CardBody className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm">Your turn - ask anything about this data in plain language.</p>
            <Button onClick={() => onAsk()}>
              <MessageSquareText className="h-3.5 w-3.5" /> Ask your own question
            </Button>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function Kpi({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div className="rounded-xl border border-edge bg-panel p-3 shadow-sm">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">{label}</div>
      <div className={`mt-0.5 text-xl font-semibold tabular-nums ${warn ? "text-warn" : "text-ink"}`}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-ink-dim">{sub}</div>}
    </div>
  );
}

function ColumnCard({ col }: { col: OverviewColumn }) {
  const hist = col.histogram;
  const maxCount = hist ? Math.max(...hist.counts, 1) : 1;
  const topMax = col.top_values ? Math.max(...col.top_values.map((t) => t.count), 1) : 1;
  return (
    <div className="rounded-lg border border-edge bg-panel-2/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="truncate text-xs font-semibold" title={col.name}>
          {col.display_name ?? col.name}
        </span>
        <span className="shrink-0 rounded-full bg-slate-500/10 px-2 py-0.5 text-[9px] uppercase tracking-wider text-ink-dim">
          {ROLE_LABEL[col.role] ?? col.role}
        </span>
      </div>
      <div className="mt-1 text-[10px] text-ink-dim">
        {col.unique_count.toLocaleString()} distinct
        {col.missing_pct > 0 && (
          <span className={col.missing_pct > 5 ? "text-warn" : ""}>
            {" "}· {col.missing_pct.toFixed(col.missing_pct < 1 ? 1 : 0)}% empty
          </span>
        )}
      </div>

      {/* Numeric distribution: mini histogram + range */}
      {hist && col.stats && (
        <div className="mt-2">
          <div className="flex h-10 items-end gap-px">
            {hist.counts.map((c, i) => (
              <div
                key={i}
                className="flex-1 rounded-t-sm bg-accent/60"
                style={{ height: `${Math.max(4, (c / maxCount) * 100)}%` }}
                title={`${fmt(hist.edges[i])} to ${fmt(hist.edges[i + 1])}: ${c} row(s)`}
              />
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[9px] tabular-nums text-ink-dim">
            <span>{fmt(col.stats.min)}</span>
            <span>avg {fmt(col.stats.mean)}</span>
            <span>{fmt(col.stats.max)}</span>
          </div>
        </div>
      )}

      {/* Categorical distribution: top values as mini bars */}
      {col.top_values && (
        <div className="mt-2 space-y-1">
          {col.top_values.slice(0, 5).map((t) => (
            <div key={String(t.value)} className="flex items-center gap-1.5">
              <span className="w-20 truncate text-[10px]" title={String(t.value)}>
                {String(t.value)}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-500/10">
                <div
                  className="h-full rounded-full bg-accent/60"
                  style={{ width: `${(t.count / topMax) * 100}%` }}
                />
              </div>
              <span className="w-8 text-right text-[9px] tabular-nums text-ink-dim">{t.count}</span>
            </div>
          ))}
        </div>
      )}

      {/* Dates and identifiers: sample values only */}
      {!hist && !col.top_values && col.sample_values.length > 0 && (
        <div className="mt-2 truncate text-[10px] text-ink-dim" title={col.sample_values.map(String).join(", ")}>
          e.g. {col.sample_values.slice(0, 3).map(String).join(", ")}
        </div>
      )}
    </div>
  );
}

function FindingCard({
  finding,
  generatedBy,
  onAsk,
  numericColumns = [],
}: {
  finding: ExploreFinding;
  generatedBy: string;
  onAsk: (question?: string) => void;
  numericColumns?: string[];
}) {
  const [showTable, setShowTable] = useState(false);
  const f = finding;
  // Per-denominator quick asks: raw totals flatter big groups; one click
  // reframes the same ranking per another measure (goes through the normal
  // interpret-then-run flow, so the plan is still shown before running).
  const metric = f.chart.y[0] ?? "";
  const denominators =
    (f.chart.kind === "hbar" || f.chart.kind === "bar") && f.chart.x
      ? numericColumns.filter((n) => !metric.toLowerCase().includes(n.toLowerCase()))
      : [];
  return (
    <Card className="h-full">
      <CardHeader
        title={f.question}
        right={<Badge tone={generatedBy === "claude" ? "accent" : "neutral"}>{genLabel(generatedBy)}</Badge>}
      />
      <CardBody className="space-y-3">
        <p className="text-sm font-medium leading-relaxed">{f.headline}</p>

        {f.meaning && (
          <div className="flex items-start gap-2 rounded-lg border border-accent/20 bg-accent-soft/20 px-3 py-2">
            <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
            <p className="text-xs leading-relaxed text-ink">{f.meaning}</p>
          </div>
        )}

        {f.caveats.length > 0 && (
          <div className="space-y-1 rounded-lg border border-warn/30 bg-warn/5 px-3 py-2">
            {f.caveats.map((c, i) => (
              <p key={i} className="text-[11px] leading-relaxed text-warn">{c}</p>
            ))}
          </div>
        )}

        <QueryChartWithMap spec={f.chart} result={f.result} />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setShowTable((s) => !s)}
              className="text-[11px] text-ink-dim underline-offset-2 hover:text-ink hover:underline"
            >
              {showTable ? "Hide numbers" : "Show the numbers"}
            </button>
            {denominators.slice(0, 2).map((den) => (
              <button
                key={den}
                onClick={() =>
                  onAsk(`${metric.replace(/__/g, " ").replace(/_/g, " ")} per ${den} by ${f.chart.x}`)
                }
                title={`Reframe this ranking per ${den} - raw totals can flatter big groups`}
                className="rounded-full bg-slate-500/8 px-2 py-0.5 text-[10px] text-ink-dim ring-1 ring-inset ring-slate-500/15 hover:text-accent"
              >
                per {den}
              </button>
            ))}
          </span>
          <button
            onClick={() => onAsk(f.question)}
            className="text-[11px] text-accent underline-offset-2 hover:underline"
          >
            Refine this question
          </button>
        </div>

        {showTable && (
          <div className="overflow-x-auto rounded-lg border border-edge">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                  {f.result.columns.map((c) => (
                    <th key={c} className="px-3 py-2">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {f.result.table.slice(0, 50).map((r, i) => (
                  <tr key={i} className="border-b border-edge/50">
                    {f.result.columns.map((c) => (
                      <td key={c} className="px-3 py-1.5 tabular-nums">
                        {r[c] == null ? <span className="text-ink-dim">-</span> : String(r[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-[10px] leading-relaxed text-ink-dim">
          {f.sentences.join(" ")}{" "}
          {f.result.row_counts.length > 0 &&
            `(${f.result.row_counts.map((rc) => `${rc.step}: ${rc.rows.toLocaleString()}`).join(" → ")})`}
        </p>
      </CardBody>
    </Card>
  );
}

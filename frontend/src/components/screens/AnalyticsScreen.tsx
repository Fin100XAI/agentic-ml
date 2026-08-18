// Analytics path: the exploring agents run starter questions the moment the
// user arrives (deterministic plans through the same executor as Ask), and
// present the initial findings as chart cards under a dataset KPI strip and
// an expandable data description. From here the user takes over with their
// own questions; the whole board downloads as a briefing file.
import { useEffect, useState } from "react";
import type { ComponentType, ReactNode } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  Compass,
  Database,
  Download,
  Hash,
  Lightbulb,
  MapPin,
  MessageSquareText,
  RefreshCw,
} from "lucide-react";
import { api } from "../../api/client";
import type { DataOverview, DomainsResponse, ExploreFinding, ExploreResponse, OverviewColumn, PlaceCheck, TextNumberProposal } from "../../types";
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
const domainsCache = new Map<string, DomainsResponse>();

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

// One row of the data checkup: a status line (scanning / needs a decision /
// clean) that expands into the decision UI only when there is one to make.
function CheckItem({
  icon: Icon,
  title,
  state,
  decideLabel,
  cleanLabel,
  children,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  state: "scanning" | "decide" | "clean";
  decideLabel?: string;
  cleanLabel: string;
  children?: ReactNode;
}) {
  return (
    <div
      className={`rounded-xl border px-4 py-3 ${
        state === "decide" ? "border-warn/40 bg-warn/[0.04]" : "border-edge bg-panel-2/50"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        {state === "scanning" ? (
          <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-edge border-t-accent" />
        ) : state === "decide" ? (
          <AlertTriangle className="h-4 w-4 shrink-0 text-warn" />
        ) : (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-good" />
        )}
        <Icon className="h-3.5 w-3.5 shrink-0 text-ink-dim" />
        <span className="text-xs font-semibold">{title}</span>
        <span className={`text-[11px] ${state === "decide" ? "font-medium text-warn" : "text-ink-dim"}`}>
          {state === "scanning" ? "checking..." : state === "decide" ? decideLabel : cleanLabel}
        </span>
      </div>
      {state === "decide" && children && <div className="mt-2.5">{children}</div>}
    </div>
  );
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
  // Focus: "" = general overview; otherwise a domain name from the scout.
  const [focusDomain, setFocusDomain] = useState("");
  const [domains, setDomains] = useState<DomainsResponse | null>(
    domainsCache.get(datasetId) ?? null,
  );
  const cacheKey = `${datasetId}|${lang}|${focusDomain}`;
  const focusColumns =
    focusDomain && domains
      ? domains.domains.find((d) => d.name === focusDomain)?.columns
      : undefined;
  const cached = boardCache.get(cacheKey) ?? null;
  const [resp, setResp] = useState<ExploreResponse | null>(cached);
  const [busy, setBusy] = useState(cached === null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [overview, setOverview] = useState<DataOverview | null>(
    overviewCache.get(datasetId) ?? null,
  );
  const [aboutOpen, setAboutOpen] = useState(false);
  // Number repair: text-costumed numbers reviewed here, applied on approval.
  const [numCheck, setNumCheck] = useState<TextNumberProposal[] | null>(null);
  const [numDismissed, setNumDismissed] = useState(false);
  const [numBusy, setNumBusy] = useState(false);
  const [numTicks, setNumTicks] = useState<Set<string>>(new Set());
  // Sequencing: the repair scans run FIRST; exploration waits until the
  // user has decided on any proposals - otherwise the agents explore the
  // unfixed data and everything runs twice.
  const [checksReady, setChecksReady] = useState(false);
  // What happened in the checkup, for the summary line once exploring starts.
  const [numOutcome, setNumOutcome] = useState<{ kind: "fixed"; n: number } | { kind: "kept" } | null>(null);
  const [placeOutcome, setPlaceOutcome] = useState<{ kind: "fixed"; n: number } | { kind: "kept" } | null>(null);

  const applyNumbers = async () => {
    if (!numCheck) return;
    setNumBusy(true);
    setError(null);
    try {
      await inFlight.get(cacheKey)?.catch(() => {});
      inFlight.delete(cacheKey);
      const cols = numCheck.filter((p) => numTicks.has(p.column)).map((p) => p.column);
      if (cols.length > 0) {
        await api.fixNumbers(datasetId, cols);
      }
      // Column types changed: every cached view of this dataset is stale.
      for (const k of [...boardCache.keys()]) {
        if (k.startsWith(`${datasetId}|`)) boardCache.delete(k);
      }
      overviewCache.delete(datasetId);
      domainsCache.delete(datasetId);
      setNumCheck(null);
      setOverview(null);
      api.datasetOverview(datasetId).then((o) => {
        overviewCache.set(datasetId, o);
        setOverview(o);
      }).catch(() => {});
      api.getDomains(datasetId).then((d) => {
        domainsCache.set(datasetId, d);
        setDomains(d);
      }).catch(() => {});
      setNumOutcome({ kind: "fixed", n: cols.length });
      // Explore only if this was the LAST open decision - otherwise wait for
      // the place decision so the agents explore the fully clean version once.
      if (!(placeCheck && !placeDismissed)) await explore();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setNumBusy(false);
    }
  };

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
      setPlaceOutcome({ kind: "fixed", n: placeTicks.size });
      // Explore only if this was the LAST open decision - otherwise wait for
      // the number decision so the agents explore the fully clean version once.
      if (!(numCheck && !numDismissed)) await explore();
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
        p = api.explore(datasetId, lang, focusColumns);
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

  // Step 1: repair scans + overview + domains - all fast and independent of
  // exploration. Exploration itself waits for the repair decision (step 2).
  useEffect(() => {
    setChecksReady(false);
    setNumDismissed(false);
    setPlaceDismissed(false);
    setNumOutcome(null);
    setPlaceOutcome(null);
    Promise.allSettled([api.numberCheck(datasetId), api.placeCheck(datasetId)])
      .then(([n, p]) => {
        if (n.status === "fulfilled" && n.value.columns.length > 0) {
          setNumCheck(n.value.columns);
          setNumTicks(new Set(n.value.columns.map((x) => x.column)));
        } else {
          setNumCheck(null);
        }
        if (p.status === "fulfilled" && p.value.columns.length > 0) {
          setPlaceCheck(p.value);
          // default: everything ticked - one click fixes the common case
          setPlaceTicks(new Set(p.value.columns.flatMap((c) =>
            c.proposals.map((x) => `${c.column}|${x.canonical}`))));
        } else {
          setPlaceCheck(null);
        }
        setChecksReady(true);
      });
    if (!domainsCache.has(datasetId)) {
      api.getDomains(datasetId)
        .then((d) => {
          domainsCache.set(datasetId, d);
          setDomains(d);
        })
        .catch(() => {});
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
  }, [datasetId]);

  const repairsPending =
    (numCheck !== null && !numDismissed) || (placeCheck !== null && !placeDismissed);

  // Step 2: explore only once the repair decision is made (approved cards
  // clear their proposals; "Keep as is" dismisses them).
  useEffect(() => {
    if (!checksReady || repairsPending) return;
    const c = boardCache.get(cacheKey);
    if (c) {
      setResp(c);
      setBusy(false);
    } else {
      setResp(null);
      void explore();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, lang, focusDomain, checksReady, repairsPending]);

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

  // One line of checkup history for the exploring card.
  const checkupBits: string[] = [];
  if (numOutcome?.kind === "fixed") checkupBits.push(`${numOutcome.n} column${numOutcome.n > 1 ? "s" : ""} converted to numbers`);
  if (numOutcome?.kind === "kept") checkupBits.push("text-number columns kept as is");
  if (placeOutcome?.kind === "fixed") checkupBits.push(`${placeOutcome.n} spelling merge${placeOutcome.n > 1 ? "s" : ""} applied`);
  if (placeOutcome?.kind === "kept") checkupBits.push("spellings kept as is");
  const checkupSummary = checkupBits.length > 0 ? checkupBits.join(", ") : "no fixes needed";

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      {/* Header row: title left, actions right */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display flex items-center gap-2 text-lg font-bold">
          <Compass className="h-5 w-5 text-accent" /> Initial findings
          <span className="hidden text-sm font-normal text-ink-dim sm:inline">· {filename}</span>
        </h2>
        <div className="flex flex-wrap items-center justify-end gap-2">
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

      {/* Shape Scout: what kind of dataset this reads as - shown, never hidden */}
      {resp?.shape && (
        <p className="text-[11px] text-ink-dim" title={resp.shape.reasoning}>
          Reading this as{" "}
          <span className="font-semibold text-ink">{resp.shape.label}</span>
          <span className="text-ink-dim/70">
            {" "}- questions {resp.questions_by === "claude"
              ? "chosen by the AI scout across the data's topics"
              : "from the built-in playbook"} (hover for why).
          </span>
        </p>
      )}

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
            className="flex flex-col justify-center rounded-2xl border border-edge bg-panel p-3 text-left shadow-sm transition-colors hover:border-accent/40"
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
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {prof.columns.map((c) => (
                <ColumnCard key={c.name} col={c} />
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Step 1 - Data checkup: every cleaning decision happens HERE, before
          the exploring agents see a single row. */}
      {(!checksReady || repairsPending) && (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-edge bg-panel-2/60 px-5 py-3.5">
            <div className="flex items-center gap-2.5">
              <span className="rounded-lg bg-accent-soft p-2">
                <ClipboardCheck className="h-4 w-4 text-accent" />
              </span>
              <div>
                <h3 className="text-sm font-semibold">Data checkup</h3>
                <p className="text-[11px] text-ink-dim">
                  Cleaning decisions happen first - the agents then explore the clean version, once.
                </p>
              </div>
            </div>
            <span className="rounded-full border border-edge bg-panel px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
              Step 1 · before exploring
            </span>
          </div>
          <CardBody className="space-y-3">
            <CheckItem
              icon={Hash}
              title="Numbers stored as text"
              state={!checksReady ? "scanning" : numCheck && !numDismissed ? "decide" : "clean"}
              decideLabel={
                numCheck
                  ? `${numCheck.length} column${numCheck.length > 1 ? "s" : ""} need${numCheck.length > 1 ? "" : "s"} a decision`
                  : ""
              }
              cleanLabel="every measure column reads as numbers"
            >
              <p className="text-[11px] leading-relaxed text-ink-dim">
                These columns look like numbers wearing a text costume - until converted they
                cannot be ranked, trended, mapped or related. The original file stays untouched;
                blanks like '-' become missing values, counted honestly.
              </p>
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {numCheck?.map((p) => (
                  <label key={p.column} className="flex items-start gap-2 rounded-lg border border-edge bg-panel px-3 py-2">
                    <input
                      type="checkbox"
                      checked={numTicks.has(p.column)}
                      onChange={() =>
                        setNumTicks((s) => {
                          const next = new Set(s);
                          if (next.has(p.column)) next.delete(p.column);
                          else next.add(p.column);
                          return next;
                        })
                      }
                      className="mt-0.5 accent-[#4338ca]"
                    />
                    <span className="min-w-0 text-xs leading-relaxed">
                      <span className="font-semibold">{p.column}</span>
                      <span className="text-ink-dim">
                        {" "}- {p.parse_pct}% numeric
                        {p.n_blank > 0 ? `, ${p.n_blank} blank` : ""}
                      </span>
                      {p.samples[0] && (
                        <span className="mt-0.5 block font-mono text-[10px] text-ink-dim">
                          '{p.samples[0].from}' <span className="font-sans text-accent">→</span>{" "}
                          {p.samples[0].to.toLocaleString()}
                        </span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setNumDismissed(true);
                    setNumOutcome({ kind: "kept" });
                  }}
                >
                  Keep as is
                </Button>
                <Button size="sm" onClick={applyNumbers} disabled={numBusy || numTicks.size === 0}>
                  {numBusy ? <Spinner /> : null} Convert & recompute
                </Button>
              </div>
            </CheckItem>

            <CheckItem
              icon={MapPin}
              title="Place-name spellings"
              state={!checksReady ? "scanning" : placeCheck && !placeDismissed ? "decide" : "clean"}
              decideLabel={
                placeCheck
                  ? `${placeCheck.columns.reduce((n, c) => n + c.proposals.length, 0)} likely merge${
                      placeCheck.columns.reduce((n, c) => n + c.proposals.length, 0) > 1 ? "s" : ""
                    } to review`
                  : ""
              }
              cleanLabel="no split spellings found"
            >
              <p className="text-[11px] leading-relaxed text-ink-dim">
                Split spellings split your totals. Untick anything that is genuinely different,
                then merge - the original file stays untouched, and the approved spellings are
                remembered for future files.
              </p>
              <div className="mt-2 space-y-1.5">
                {placeCheck?.columns.map((col) =>
                  col.proposals.map((p) => {
                    const key = `${col.column}|${p.canonical}`;
                    return (
                      <label key={key} className="flex items-start gap-2 rounded-lg border border-edge bg-panel px-3 py-2">
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
                          className="mt-0.5 accent-[#4338ca]"
                        />
                        <span className="min-w-0 text-xs leading-relaxed">
                          <span className="text-ink-dim">In </span>
                          <span className="font-semibold">{col.column}</span>
                          <span className="mt-1 flex flex-wrap items-center gap-1">
                            {p.variants.map((v) => (
                              <span key={v} className="rounded-md bg-panel-2 px-1.5 py-0.5 font-mono text-[10px] ring-1 ring-inset ring-edge">
                                {v} <span className="text-ink-dim">({p.counts[v] ?? 0})</span>
                              </span>
                            ))}
                            <span className="text-accent">→</span>
                            <span className="rounded-md bg-accent-soft px-1.5 py-0.5 font-mono text-[10px] font-semibold text-accent ring-1 ring-inset ring-accent/20">
                              {p.canonical}
                            </span>
                            <span className="rounded-full bg-slate-500/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-ink-dim">
                              {p.source}
                            </span>
                          </span>
                        </span>
                      </label>
                    );
                  }),
                )}
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setPlaceDismissed(true);
                    setPlaceOutcome({ kind: "kept" });
                  }}
                >
                  Keep as is
                </Button>
                <Button size="sm" onClick={applyPlaces} disabled={placeBusy || placeTicks.size === 0}>
                  {placeBusy ? <Spinner /> : null} Merge & recompute
                </Button>
              </div>
            </CheckItem>
          </CardBody>
        </Card>
      )}

      {/* The exploration slot, visibly waiting on the checkup decision */}
      {checksReady && repairsPending && (
        <div className="rounded-2xl border-2 border-dashed border-edge bg-panel-2/40 px-6 py-10 text-center">
          <Compass className="mx-auto h-6 w-6 text-ink-dim/40" />
          <p className="mt-2 text-sm font-medium">The exploring agents are ready</p>
          <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-ink-dim">
            They start the moment the checkup above is decided, and explore the clean
            version once. In a hurry? "Ask a question" works right away.
          </p>
        </div>
      )}

      {busy && checksReady && !repairsPending && (
        <Card>
          <CardBody className="space-y-2.5 py-6">
            <p className="flex flex-wrap items-center gap-1.5 text-xs">
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-good" />
              <span className="font-semibold text-good">Checkup complete</span>
              <span className="text-ink-dim">· {checkupSummary}</span>
            </p>
            <div className="flex items-center gap-3">
              <Spinner />
              <p className="text-sm text-ink-dim">
                The exploring agents are asking the first questions and computing every answer
                from the data - or skip straight to asking your own.
              </p>
            </div>
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

      {/* Domain focus: the scout groups a wide file into topics; the user
          chooses where to dig, or stays with the general overview. Appears
          once the checkup is decided - it steers the exploration. */}
      {checksReady && !repairsPending && domains && domains.domains.length >= 1 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
            Focus
          </span>
          <button
            onClick={() => setFocusDomain("")}
            className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
              focusDomain === ""
                ? "border-accent/40 bg-accent-soft text-accent"
                : "border-edge bg-panel-2 text-ink-dim hover:text-accent"
            }`}
          >
            General overview
          </button>
          {domains.domains.map((d) => (
            <button
              key={d.name}
              onClick={() => setFocusDomain(d.name)}
              title={`${d.why} (${d.columns.length} columns)`}
              className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                focusDomain === d.name
                  ? "border-accent/40 bg-accent-soft text-accent"
                  : "border-edge bg-panel-2 text-ink-dim hover:text-accent"
              }`}
            >
              {d.name}
              {domains.suggested === d.name && (
                <span className="ml-1 text-[9px] uppercase tracking-wide text-accent">
                  · agent suggests
                </span>
              )}
            </button>
          ))}
        </div>
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

      {/* Findings grid: wide charts span the full row. grid-cols-1 at base
          gives minmax(0,1fr) - without it the map svg's intrinsic width
          blows the implicit column past small screens. */}
      {!busy && resp && resp.findings.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {resp.findings.map((f, i) => (
            <div
              key={i}
              className={
                f.chart.kind === "line" || (f.chart.kind === "table" && !f.chart.map)
                  ? "lg:col-span-2"
                  : ""
              }
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
    <div className="rounded-2xl border border-edge bg-panel p-3 shadow-sm">
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
  const [showMethod, setShowMethod] = useState(false);
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
            <button
              onClick={() => setShowMethod((s) => !s)}
              className="text-[11px] text-ink-dim underline-offset-2 hover:text-ink hover:underline"
            >
              {showMethod ? "Hide method" : "How this was computed"}
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

        {showMethod && (
          <p className="rounded-lg border border-edge bg-panel-2/60 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
            {f.sentences.join(" ")}{" "}
            {f.result.row_counts.length > 0 &&
              `(${f.result.row_counts.map((rc) => `${rc.step}: ${rc.rows.toLocaleString()}`).join(" → ")})`}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

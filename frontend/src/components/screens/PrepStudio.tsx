// Data Prep Studio (PREP-STUDIO prototype): a standalone, intent-first,
// agent-guided path that turns messy multi-sheet / multi-year uploads into
// ONE analysis-ready table. Reached only via #/prep - nothing in the main
// app links here yet. The guide agent sees metadata only (goal, sheet and
// column names, dtypes) - never row values. Every combine and clean step is
// proposed, then human-approved.
import { useRef, useState } from "react";
import {
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  Download,
  FileUp,
  Hash,
  Layers,
  MapPin,
  ShieldAlert,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { Badge, Button, Card, CardBody, CardHeader, Spinner } from "../ui";

/* ---------- local types (prototype-scoped) ---------- */

interface SheetInfo {
  name: string;
  rows: number;
  cols: number;
  columns: { name: string; dtype: string }[];
  year_guess: number | null;
  unnamed_columns: number;
  header_row?: number;
  note?: string;
}
interface Agent {
  message: string;
  questions?: string[];
  mode: string;
}
interface Proposal {
  strategy: "stack" | "join" | "single" | "review";
  sheets: string[];
  mappings: Record<string, Record<string, string>>;
  join_key: string | null;
  join_candidates?: string[];
  add_source_column: boolean;
  add_year_column: boolean;
  notes: string[];
  pick?: string;
}
interface Checks {
  text_numbers: { column: string; parse_pct: number; n_blank: number }[];
  place_variants: { column: string; proposals: { canonical: string; variants: string[]; counts: Record<string, number> }[] }[];
  junk: { empty_rows: number; total_like_rows: number };
  pii_columns: { column: string; kind: string }[];
  readiness: { message?: string; note?: string; kind?: string }[];
}
interface Preview {
  columns: string[];
  rows: Record<string, unknown>[];
  n_rows: number;
  n_cols: number;
}

const STEPS = ["Goal", "Data", "Combine", "Clean", "Ready"] as const;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/prep${path}`, init);
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch { /* non-json error body */ }
    throw new Error(String(msg));
  }
  return r.json();
}

/* ---------- page ---------- */

export function PrepStudio() {
  const [step, setStep] = useState(0);
  const [sid, setSid] = useState<string | null>(null);
  const [goal, setGoal] = useState("");
  const [goalAgent, setGoalAgent] = useState<Agent | null>(null);
  const [inventory, setInventory] = useState<SheetInfo[]>([]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [combineAgent, setCombineAgent] = useState<Agent | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [checks, setChecks] = useState<Checks | null>(null);
  const [applied, setApplied] = useState<string[]>([]);
  const [finished, setFinished] = useState<{ dataset_id: string; filename: string; rows: number } | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Clean-step selections
  const [numTicks, setNumTicks] = useState<Set<string>>(new Set());
  const [placeTicks, setPlaceTicks] = useState<Set<string>>(new Set());
  const [piiTicks, setPiiTicks] = useState<Set<string>>(new Set());
  const [dropEmpty, setDropEmpty] = useState(true);
  const [dropTotals, setDropTotals] = useState(true);

  const guard = async (label: string, fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const start = () =>
    guard("goal", async () => {
      const r = await call<{ id: string; agent: Agent }>(`/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      setSid(r.id);
      setGoalAgent(r.agent);
      setStep(1);
    });

  const upload = (files: FileList | null) =>
    guard("upload", async () => {
      if (!files || !sid) return;
      for (const f of Array.from(files)) {
        const form = new FormData();
        form.append("file", f);
        const r = await call<{ inventory: SheetInfo[] }>(`/${sid}/files`, { method: "POST", body: form });
        setInventory(r.inventory);
      }
      setProposal(null);
      if (fileRef.current) fileRef.current.value = "";
    });

  const setHeaderRow = (name: string, row: number) =>
    guard("header", async () => {
      const r = await call<{ inventory: SheetInfo[] }>(
        `/${sid}/files/${encodeURIComponent(name)}/header`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ header_row: row }) });
      setInventory(r.inventory);
      setProposal(null);
    });

  const removeSheet = (name: string) =>
    guard("remove", async () => {
      const r = await call<{ inventory: SheetInfo[] }>(`/${sid}/files/${encodeURIComponent(name)}`, { method: "DELETE" });
      setInventory(r.inventory);
      setProposal(null);
    });

  const advise = () =>
    guard("advise", async () => {
      const r = await call<{ proposal: Proposal; agent: Agent }>(`/${sid}/advise`, { method: "POST" });
      setProposal(r.proposal);
      setCombineAgent(r.agent);
      setStep(2);
    });

  const seedCleanSelections = (c: Checks) => {
    setNumTicks(new Set(c.text_numbers.map((t) => t.column)));
    setPlaceTicks(new Set(c.place_variants.flatMap((pv) => pv.proposals.map((p) => `${pv.column}|${p.canonical}`))));
    setPiiTicks(new Set(c.pii_columns.map((p) => p.column)));
    setDropEmpty(c.junk.empty_rows > 0);
    setDropTotals(c.junk.total_like_rows > 0);
  };

  const combine = () =>
    guard("combine", async () => {
      if (!proposal) return;
      const r = await call<{ report: unknown; preview: Preview; checks: Checks }>(`/${sid}/combine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec: proposal }),
      });
      setPreview(r.preview);
      setChecks(r.checks);
      seedCleanSelections(r.checks);
      setApplied([]);
      setStep(3);
    });

  const applyClean = () =>
    guard("clean", async () => {
      if (!checks) return;
      const place_maps: Record<string, Record<string, string>> = {};
      for (const pv of checks.place_variants) {
        for (const p of pv.proposals) {
          if (!placeTicks.has(`${pv.column}|${p.canonical}`)) continue;
          place_maps[pv.column] = place_maps[pv.column] ?? {};
          for (const v of p.variants) place_maps[pv.column][v] = p.canonical;
        }
      }
      const r = await call<{ applied: string[]; preview: Preview; checks: Checks }>(`/${sid}/clean`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fix_number_columns: [...numTicks],
          place_maps,
          drop_columns: [...piiTicks],
          drop_empty_rows: dropEmpty,
          drop_total_rows: dropTotals,
        }),
      });
      setApplied((a) => [...a, ...r.applied]);
      setPreview(r.preview);
      setChecks(r.checks);
      seedCleanSelections(r.checks);
    });

  const finish = () =>
    guard("finish", async () => {
      const r = await call<{ dataset_id: string; filename: string; rows: number }>(`/${sid}/finish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: datasetName || "prepared-data" }),
      });
      setFinished(r);
    });

  const nOpenChecks = checks
    ? checks.text_numbers.length + checks.place_variants.length + checks.pii_columns.length +
      (checks.junk.empty_rows > 0 ? 1 : 0) + (checks.junk.total_like_rows > 0 ? 1 : 0)
    : 0;

  return (
    <div className="font-jakarta min-h-screen bg-surface px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header + stepper */}
        <div className="text-center">
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-accent">
            Data Prep Studio · prototype
          </p>
          <h1 className="mx-auto mt-2 max-w-xl text-balance text-2xl font-extrabold tracking-tight md:text-3xl">
            Any data in,{" "}
            <span className="bg-[linear-gradient(100deg,#45e0c8,#6e8bff_55%,#b98cff)] bg-clip-text text-transparent">
              one analysis-ready table out.
            </span>
          </h1>
          <div className="mt-5 flex items-center justify-center gap-1">
            {STEPS.map((s, i) => (
              <div key={s} className="flex items-center gap-1">
                {i > 0 && <div className="h-px w-6 bg-edge" />}
                <span
                  className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ${
                    i === step
                      ? "bg-accent/10 font-semibold text-accent ring-1 ring-inset ring-accent/30"
                      : i < step
                        ? "text-good"
                        : "text-ink-dim"
                  }`}
                >
                  {i < step ? <Check className="h-3 w-3" /> : null}
                  {s}
                </span>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <Card className="border-bad/40">
            <CardBody className="py-3">
              <p className="text-xs text-bad">{error}</p>
            </CardBody>
          </Card>
        )}

        {/* STEP 0: the goal - intent before data */}
        {step === 0 && (
          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-accent" /> What should this data become?</span>}
              subtitle="The guide agent reads your goal BEFORE seeing any data - the whole preparation is steered by it."
            />
            <CardBody className="space-y-3">
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                rows={3}
                placeholder="e.g. Compare scheme enrollment across the last three years by district - the sheets are one file per year. In the end I want to train a model that flags districts likely to fall behind."
                className="w-full rounded-xl border border-edge bg-panel-2 px-4 py-3 text-sm leading-relaxed outline-none focus:border-accent"
              />
              <div className="flex justify-end">
                <Button onClick={start} disabled={!goal.trim() || busy !== null}>
                  {busy === "goal" ? <Spinner /> : null} Start preparing <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </CardBody>
          </Card>
        )}

        {/* Agent guidance banner (persists from step 1 on) */}
        {goalAgent && step >= 1 && step <= 2 && (
          <Card className="border-accent/25">
            <CardBody className="flex items-start gap-3 py-4">
              <Bot className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
              <div className="min-w-0 space-y-2">
                <p className="text-xs leading-relaxed">{goalAgent.message}</p>
                {(goalAgent.questions ?? []).length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {goalAgent.questions!.map((q) => (
                      <span key={q} className="rounded-full bg-accent/10 px-2.5 py-1 text-[10px] text-accent ring-1 ring-inset ring-accent/25">
                        {q}
                      </span>
                    ))}
                  </div>
                )}
                <Badge tone={goalAgent.mode === "llm" ? "accent" : "neutral"}>
                  {goalAgent.mode === "llm" ? "AI guide" : "heuristic guide"}
                </Badge>
              </div>
            </CardBody>
          </Card>
        )}

        {/* STEP 1: add the data */}
        {step === 1 && (
          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2"><FileUp className="h-4 w-4 text-accent" /> Add the data</span>}
              subtitle="Several files, multi-sheet workbooks, different years - everything lands in one inventory."
            />
            <CardBody className="space-y-3">
              <input
                ref={fileRef}
                type="file"
                multiple
                accept=".csv,.xlsx,.xls,.xlsm"
                onChange={(e) => upload(e.target.files)}
                className="block w-full cursor-pointer rounded-xl border-2 border-dashed border-edge bg-panel-2/50 px-4 py-6 text-xs text-ink-dim file:mr-3 file:cursor-pointer file:rounded-full file:border-0 file:bg-accent/10 file:px-4 file:py-1.5 file:text-xs file:font-semibold file:text-accent"
              />
              {busy === "upload" && <Spinner label="Reading the sheets..." />}
              {inventory.length > 0 && (
                <div className="overflow-x-auto rounded-xl border border-edge">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                        <th className="px-3 py-2">Sheet</th>
                        <th className="px-3 py-2">Rows</th>
                        <th className="px-3 py-2">Columns</th>
                        <th className="px-3 py-2">Year</th>
                        <th className="px-3 py-2" />
                      </tr>
                    </thead>
                    <tbody>
                      {inventory.map((s) => (
                        <tr key={s.name} className="border-b border-edge/50">
                          <td className="max-w-64 px-3 py-2" title={s.columns.map((c) => c.name).join(", ")}>
                            <span className="block truncate font-medium">{s.name}</span>
                            <span className="mt-0.5 flex items-center gap-1.5">
                              {s.note && (
                                <span className="rounded-full bg-warn/10 px-2 py-0.5 text-[9px] text-warn ring-1 ring-inset ring-warn/25" title={s.note}>
                                  banner skipped
                                </span>
                              )}
                              <select
                                value={s.header_row ?? 0}
                                onChange={(e) => setHeaderRow(s.name, Number(e.target.value))}
                                title="Which row holds the column names - change it if the detection guessed wrong"
                                className="rounded border border-edge bg-panel-2 px-1 py-0.5 text-[9px] text-ink-dim outline-none focus:border-accent"
                              >
                                {[0, 1, 2, 3, 4, 5].map((r) => (
                                  <option key={r} value={r}>header: row {r + 1}</option>
                                ))}
                              </select>
                            </span>
                          </td>
                          <td className="px-3 py-2 tabular-nums">{s.rows.toLocaleString()}</td>
                          <td className="px-3 py-2 tabular-nums">{s.cols}</td>
                          <td className="px-3 py-2">{s.year_guess ? <Badge tone="accent">{s.year_guess}</Badge> : <span className="text-ink-dim">-</span>}</td>
                          <td className="px-3 py-2 text-right">
                            <button onClick={() => removeSheet(s.name)} title="Remove" className="text-ink-dim hover:text-bad">
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="flex justify-end">
                <Button onClick={advise} disabled={inventory.length === 0 || busy !== null}>
                  {busy === "advise" ? <Spinner /> : <Wand2 className="h-4 w-4" />}
                  Ask the guide how to combine
                </Button>
              </div>
            </CardBody>
          </Card>
        )}

        {/* STEP 2: the combine proposal */}
        {step === 2 && proposal && (
          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2"><Layers className="h-4 w-4 text-accent" /> The guide proposes</span>}
              subtitle="You approve; deterministic code executes. Nothing is combined until you say so."
            />
            <CardBody className="space-y-3">
              {combineAgent && (
                <div className="flex items-start gap-2 rounded-xl border border-accent/25 bg-accent/5 px-4 py-3">
                  <Bot className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                  <p className="text-xs leading-relaxed">{combineAgent.message}</p>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-ink-dim">Strategy</span>
                <select
                  value={proposal.strategy}
                  onChange={(e) => setProposal({ ...proposal, strategy: e.target.value as Proposal["strategy"] })}
                  className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-xs outline-none focus:border-accent"
                >
                  <option value="stack">Stack the sheets (rows on rows)</option>
                  <option value="join">Join on a key (facts side by side)</option>
                  <option value="single">Use one sheet only</option>
                </select>
                {proposal.strategy === "join" && (
                  <select
                    value={proposal.join_key ?? ""}
                    onChange={(e) => setProposal({ ...proposal, join_key: e.target.value })}
                    className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-xs outline-none focus:border-accent"
                  >
                    {(proposal.join_candidates ?? (proposal.join_key ? [proposal.join_key] : [])).map((k) => (
                      <option key={k} value={k}>key: {k}</option>
                    ))}
                  </select>
                )}
                {(proposal.strategy === "single" || proposal.strategy === "review") && (
                  <select
                    value={proposal.pick ?? proposal.sheets[0]}
                    onChange={(e) => setProposal({ ...proposal, pick: e.target.value, strategy: "single" })}
                    className="max-w-64 rounded-lg border border-edge bg-panel-2 px-2 py-1 text-xs outline-none focus:border-accent"
                  >
                    {proposal.sheets.map((sh) => (
                      <option key={sh} value={sh}>{sh}</option>
                    ))}
                  </select>
                )}
              </div>
              {proposal.notes.map((n) => (
                <p key={n} className="flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-dim">
                  <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-good" /> {n}
                </p>
              ))}
              <div className="flex justify-between gap-2">
                <Button variant="ghost" size="sm" onClick={() => setStep(1)}>Back to data</Button>
                <Button onClick={combine} disabled={busy !== null || proposal.strategy === "review"}>
                  {busy === "combine" ? <Spinner /> : null} Approve & combine
                </Button>
              </div>
            </CardBody>
          </Card>
        )}

        {/* STEP 3: clean */}
        {step === 3 && checks && preview && (
          <>
            <Card>
              <CardHeader
                title={<span className="flex items-center gap-2"><Wand2 className="h-4 w-4 text-accent" /> The checkup</span>}
                subtitle={`One table now: ${preview.n_rows.toLocaleString()} rows × ${preview.n_cols} columns. Tick what to fix - each fix is applied only when you approve.`}
              />
              <CardBody className="space-y-3">
                {checks.pii_columns.length > 0 && (
                  <div className="rounded-xl border border-bad/40 bg-bad/5 px-4 py-3">
                    <p className="flex items-center gap-1.5 text-xs font-semibold text-bad">
                      <ShieldAlert className="h-3.5 w-3.5" /> Personal data found - must be dropped before this can register
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {checks.pii_columns.map((p) => (
                        <label key={p.column} className="flex items-center gap-1.5 rounded-full border border-bad/30 px-2.5 py-1 text-[11px]">
                          <input type="checkbox" checked={piiTicks.has(p.column)} onChange={() => setPiiTicks((s) => { const n = new Set(s); n.has(p.column) ? n.delete(p.column) : n.add(p.column); return n; })} className="accent-accent" />
                          drop {p.column} <span className="text-ink-dim">({p.kind})</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
                {checks.text_numbers.length > 0 && (
                  <div className="rounded-xl border border-warn/40 bg-warn/5 px-4 py-3">
                    <p className="flex items-center gap-1.5 text-xs font-semibold"><Hash className="h-3.5 w-3.5 text-warn" /> Numbers stored as text</p>
                    <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                      {checks.text_numbers.map((t) => (
                        <label key={t.column} className="flex items-center gap-1.5 text-[11px]">
                          <input type="checkbox" checked={numTicks.has(t.column)} onChange={() => setNumTicks((s) => { const n = new Set(s); n.has(t.column) ? n.delete(t.column) : n.add(t.column); return n; })} className="accent-accent" />
                          <span className="font-medium">{t.column}</span>
                          <span className="text-ink-dim">{t.parse_pct}% numeric</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
                {checks.place_variants.length > 0 && (
                  <div className="rounded-xl border border-warn/40 bg-warn/5 px-4 py-3">
                    <p className="flex items-center gap-1.5 text-xs font-semibold"><MapPin className="h-3.5 w-3.5 text-warn" /> Same place, different spellings</p>
                    <div className="mt-2 space-y-1.5">
                      {checks.place_variants.flatMap((pv) =>
                        pv.proposals.map((p) => {
                          const key = `${pv.column}|${p.canonical}`;
                          return (
                            <label key={key} className="flex items-center gap-1.5 text-[11px]">
                              <input type="checkbox" checked={placeTicks.has(key)} onChange={() => setPlaceTicks((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; })} className="accent-accent" />
                              <span className="text-ink-dim">{pv.column}:</span> {p.variants.join(", ")} <ArrowRight className="h-3 w-3 text-ink-dim" /> <span className="font-medium">{p.canonical}</span>
                            </label>
                          );
                        }),
                      )}
                    </div>
                  </div>
                )}
                {(checks.junk.empty_rows > 0 || checks.junk.total_like_rows > 0) && (
                  <div className="rounded-xl border border-warn/40 bg-warn/5 px-4 py-3">
                    <p className="text-xs font-semibold">Junk rows</p>
                    <div className="mt-2 flex flex-wrap gap-4 text-[11px]">
                      {checks.junk.empty_rows > 0 && (
                        <label className="flex items-center gap-1.5">
                          <input type="checkbox" checked={dropEmpty} onChange={() => setDropEmpty(!dropEmpty)} className="accent-accent" />
                          drop {checks.junk.empty_rows} fully-empty row(s)
                        </label>
                      )}
                      {checks.junk.total_like_rows > 0 && (
                        <label className="flex items-center gap-1.5">
                          <input type="checkbox" checked={dropTotals} onChange={() => setDropTotals(!dropTotals)} className="accent-accent" />
                          drop {checks.junk.total_like_rows} total/summary row(s) - they double every sum
                        </label>
                      )}
                    </div>
                  </div>
                )}
                {nOpenChecks === 0 && (
                  <p className="flex items-center gap-1.5 text-xs text-good">
                    <CheckCircle2 className="h-4 w-4" /> Nothing left to fix - the table looks clean.
                  </p>
                )}
                {applied.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {applied.map((a, i) => (
                      <span key={i} className="rounded-full bg-good/10 px-2.5 py-1 text-[10px] text-good ring-1 ring-inset ring-good/25">✓ {a}</span>
                    ))}
                  </div>
                )}
                <div className="flex justify-between gap-2">
                  <Button variant="ghost" size="sm" onClick={() => setStep(2)}>Back</Button>
                  <div className="flex gap-2">
                    {nOpenChecks > 0 && (
                      <Button variant="outline" onClick={applyClean} disabled={busy !== null}>
                        {busy === "clean" ? <Spinner /> : null} Apply selected fixes
                      </Button>
                    )}
                    <Button onClick={() => setStep(4)} disabled={busy !== null}>
                      Looks good <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardBody>
            </Card>
          </>
        )}

        {/* STEP 4: ready */}
        {step === 4 && preview && (
          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-good" /> Ready: {preview.n_rows.toLocaleString()} rows × {preview.n_cols} columns</span>}
              subtitle="Preview the table, export it, or register it on the platform for analytics and model training."
            />
            <CardBody className="space-y-3">
              <div className="max-h-72 overflow-auto rounded-xl border border-edge">
                <table className="w-full text-left text-[11px]">
                  <thead className="sticky top-0">
                    <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                      {preview.columns.map((c) => (
                        <th key={c} className="whitespace-nowrap px-3 py-2">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.slice(0, 15).map((r, i) => (
                      <tr key={i} className="border-b border-edge/50">
                        {preview.columns.map((c) => (
                          <td key={c} className="whitespace-nowrap px-3 py-1.5 tabular-nums">
                            {r[c] == null ? <span className="text-ink-dim">-</span> : String(r[c])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {finished ? (
                <div className="rounded-xl border border-good/40 bg-good/5 px-4 py-3">
                  <p className="text-sm font-semibold text-good">Registered on the platform ✓</p>
                  <p className="mt-1 text-xs text-ink-dim">
                    '{finished.filename}' ({finished.rows.toLocaleString()} rows) is now a normal dataset -
                    open the main app to explore it or train on it.
                  </p>
                </div>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setStep(3)}>Back to cleaning</Button>
                    <a href={`/api/prep/${sid}/export`} download>
                      <Button variant="outline"><Download className="h-4 w-4" /> Export CSV</Button>
                    </a>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      value={datasetName}
                      onChange={(e) => setDatasetName(e.target.value)}
                      placeholder="Dataset name"
                      className="rounded-lg border border-edge bg-panel-2 px-3 py-2 text-xs outline-none focus:border-accent"
                    />
                    <Button onClick={finish} disabled={busy !== null}>
                      {busy === "finish" ? <Spinner /> : null} Register on the platform
                    </Button>
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        )}

        <p className="text-center text-[10px] text-ink-dim">
          Prototype - sessions live in memory and reset with the server. The guide agent sees
          sheet and column names only, never your data values.
        </p>
      </div>
    </div>
  );
}

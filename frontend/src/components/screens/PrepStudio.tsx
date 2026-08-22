// Data Prep Studio (PREP-STUDIO prototype) - the understand-first flow:
//   Add data -> Understand (deep profile) -> Decide (grounded interview)
//   -> Blueprint (editable schema contract) -> Certify (build + prove + bundle)
// Runs as a screen inside the app (toolbar wand, or Home) and standalone at
// #/prep. What it produces is registered INTO the current project, so a
// prepared table is an ordinary dataset from that moment on - the join
// between this pipeline and the rest of the platform.
// The agent proposes on every decision, the human decides every one of them.
import { useState } from "react";
import {
  AlertTriangle, ArrowRight, Bot, Check, CheckCircle2, Download, FileUp,
  Layers, Pencil, ShieldAlert, Sparkles, Table2, Trash2, XCircle,
} from "lucide-react";
import { Badge, Button, Card, CardBody, CardHeader, Spinner } from "../ui";

/* ---------- types (prototype-scoped) ---------- */

interface Sheet {
  name: string; rows: number; cols: number;
  header_row: number; header_tiers: number; note: string | null; columns: string[];
}
interface ColProfile {
  source_name: string; suggested_name: string; dtype: string;
  dtype_confidence: number; dtype_evidence: string; role: string;
  unit: { unit: string } | null; missing_pct: number; distinct: number;
  quality: { kind: string; detail: string }[];
}
interface Profile {
  n_rows: number; n_cols: number; columns: ColProfile[];
  grain_candidates: { columns: string[]; unique: boolean }[];
  wide_blocks: { kind: string; periods: string[]; measures: string[] } | null;
  duplicate_rows: number; table_unit: { unit: string } | null;
  banner_text: string | null;
  role_counts: Record<string, number>;
  pii_columns: { column: string; kind: string }[];
}
interface Question {
  id: string; kind: string; question: string; why: string;
  options: { value: string; label: string; detail: string }[];
  suggested: string; allow_note: boolean;
}
interface BpColumn {
  source_name: string | null; name: string; label: string; dtype: string;
  role: string; unit: string | null; nullable: boolean; description: string;
  action: string; origin: string;
}
interface Blueprint {
  columns: BpColumn[]; grain: string[]; reshape: unknown;
  row_rules: Record<string, unknown>; unit_conversion: unknown;
  purpose: string; notes: string;
}
interface Certificate {
  checks: { check: string; passed: boolean; detail: string; severity: string }[];
  errors: number; warnings: number; verdict: string; n_rows: number; n_cols: number;
}
interface CombineProposal {
  strategy: "stack" | "join" | "single" | "review";
  sheets: string[];
  join_key: string | null;
  join_candidates?: string[];
  add_source_column: boolean;
  add_year_column: boolean;
  notes: string[];
  pick?: string;
  mappings?: Record<string, Record<string, string>>;
}
interface JoinQuality {
  key: string; checked: boolean; worst_match_pct?: number; verdict?: string;
  shared_keys?: number;
  per_sheet?: { sheet: string; keys: number; matched: number; match_pct: number; unmatched_examples: string[] }[];
  note?: string;
}
interface Preview {
  columns: string[]; rows: Record<string, unknown>[]; n_rows: number; n_cols: number;
}

const STEPS = ["Add data", "Understand", "Decide", "Blueprint", "Certify"] as const;
const DTYPES = ["number", "integer", "text", "category", "boolean", "period"];
const ROLES = ["identifier", "geography", "period", "dimension", "measure", "flag"];

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/prep2${path}`, init);
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* non-json body */ }
    throw new Error(String(msg));
  }
  return r.json();
}
const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/* ---------- page ---------- */

export function PrepStudio({
  projectId,
  embedded = false,
  onRegistered,
  onContinue,
}: {
  /** Register the prepared table INTO this project, so it lands in the
   *  library beside the files that were uploaded directly. */
  projectId?: string;
  /** Inside the app shell the page chrome is already there. */
  embedded?: boolean;
  /** A prepared table is a new upload - hand it back so the caller can
   *  send the officer straight on to explore it or model it. */
  onRegistered?: (ds: { datasetId: string; filename: string; rows: number }) => void;
  /** Continue into analysis. Offered at the point the table is proven, so
   *  preparing and analysing read as one pipeline rather than two errands. */
  onContinue?: (choice: "explore" | "ask", ds: { datasetId: string; filename: string }) => void;
} = {}) {
  const [step, setStep] = useState(0);
  const [sid, setSid] = useState<string | null>(null);
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [combine, setCombine] = useState<CombineProposal | null>(null);
  const [joinQ, setJoinQ] = useState<JoinQuality | null>(null);
  const [combineNote, setCombineNote] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [narrative, setNarrative] = useState<{ message: string; mode: string } | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [bp, setBp] = useState<Blueprint | null>(null);
  const [cert, setCert] = useState<Certificate | null>(null);
  const [steps, setSteps] = useState<string[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [dictionary, setDictionary] = useState("");
  const [registered, setRegistered] = useState<{ dataset_id: string; filename: string; rows: number } | null>(null);
  const [dsName, setDsName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const guard = async (label: string, fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(label); setError(null);
    try { await fn(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const ensureSession = async (): Promise<string> => {
    if (sid) return sid;
    const r = await call<{ id: string }>(`/session`, { method: "POST" });
    setSid(r.id);
    return r.id;
  };

  const upload = (files: FileList | null) =>
    guard("upload", async () => {
      if (!files?.length) return;
      const id = await ensureSession();
      for (const f of Array.from(files)) {
        const form = new FormData();
        form.append("file", f);
        const r = await call<{ sheets: Sheet[] }>(`/${id}/files`, { method: "POST", body: form });
        setSheets(r.sheets);
      }
      setProfile(null); setBp(null); setCert(null); setCombine(null); setJoinQ(null);
    });

  const setHeader = (name: string, row: number) =>
    guard("header", async () => {
      const r = await call<{ sheets: Sheet[] }>(
        `/${sid}/files/${encodeURIComponent(name)}/header`, json({ header_row: row }));
      setSheets(r.sheets); setProfile(null);
    });

  const removeSheet = (name: string) =>
    guard("remove", async () => {
      const r = await call<{ sheets: Sheet[] }>(
        `/${sid}/files/${encodeURIComponent(name)}`, { method: "DELETE" });
      setSheets(r.sheets); setProfile(null);
    });

  // With one sheet there is nothing to decide - go straight on. With several,
  // the officer approves how they are combined BEFORE anything is profiled;
  // silently analysing one and dropping the rest is not an option.
  const doProfile = () =>
    guard("profile", async () => {
      if (sheets.length > 1 && !combine) {
        const r = await call<{ proposal: CombineProposal; join_quality: JoinQuality | null;
                               note: string | null }>(`/${sid}/combine-plan`, { method: "POST" });
        setCombine(r.proposal); setJoinQ(r.join_quality); setCombineNote(r.note);
        return;
      }
      await runProfile(combine ?? undefined);
    });

  const runProfile = async (spec?: CombineProposal) => {
    const r = await call<{ profile: Profile; narrative: { message: string; mode: string };
                           combine: Record<string, unknown>; preview: Preview }>(
      `/${sid}/profile`, spec ? json({ spec }) : { method: "POST" });
    setProfile(r.profile); setNarrative(r.narrative); setPreview(r.preview); setStep(1);
  };

  const approveCombine = () =>
    guard("profile", async () => {
      if (!combine) return;
      if (combine.strategy === "review") {
        throw new Error("Choose stack, join, or a single sheet before continuing.");
      }
      await runProfile(combine);
    });

  const doInterview = () =>
    guard("interview", async () => {
      const r = await call<{ questions: Question[] }>(`/${sid}/interview`, { method: "POST" });
      setQuestions(r.questions);
      setAnswers(Object.fromEntries(r.questions.map((q) => [q.id, q.suggested])));
      setStep(2);
    });

  const doBlueprint = () =>
    guard("blueprint", async () => {
      const r = await call<{ blueprint: Blueprint }>(
        `/${sid}/blueprint`, json({ answers: { ...answers, _notes: note } }));
      setBp(r.blueprint); setStep(3);
    });

  const doBuild = () =>
    guard("build", async () => {
      if (!bp) return;
      const r = await call<{ steps: string[]; certificate: Certificate;
                             preview: Preview; dictionary: string }>(
        `/${sid}/build`, json({ blueprint: bp }));
      setSteps(r.steps); setCert(r.certificate); setPreview(r.preview);
      setDictionary(r.dictionary); setStep(4);
    });

  const doRegister = () =>
    guard("register", async () => {
      const r = await call<{ dataset_id: string; filename: string; rows: number }>(
        `/${sid}/register`,
        json({ name: dsName || "prepared-data", project_id: projectId ?? null }));
      setRegistered(r);
      onRegistered?.({ datasetId: r.dataset_id, filename: r.filename, rows: r.rows });
    });

  const editCol = (i: number, patch: Partial<BpColumn>) =>
    setBp((b) => b && { ...b, columns: b.columns.map((c, j) => (j === i ? { ...c, ...patch } : c)) });

  // Standalone the studio owns the page; inside the shell it is a screen
  // like any other and must not paint a second full-height background.
  const Shell = ({ children }: { children: React.ReactNode }) =>
    embedded ? (
      <div className="space-y-6">{children}</div>
    ) : (
      <div className="font-jakarta min-h-screen bg-surface px-4 py-8 sm:px-8">
        <div className="mx-auto max-w-5xl space-y-6">{children}</div>
      </div>
    );

  return (
    <Shell>
      <>
        {/* Header + stepper. Embedding hides only the standalone PAGE title -
            the app shell already carries one - but the stepper stays either
            way: without it the studio is a series of unlabelled cards and
            you cannot see that five steps exist, let alone where you are. */}
        <div className="text-center">
          {!embedded && (
            <>
              <p className="maha-eyebrow">Data Prep Studio · prototype</p>
              <h1 className="maha-display mx-auto mt-2 max-w-2xl text-balance text-2xl md:text-3xl">
                Any data in,{" "}
                <span className="maha-gold-text">a table with a contract out.</span>
              </h1>
              <p className="mx-auto mt-2 max-w-xl text-xs leading-relaxed text-ink-dim">
                The agents read the data first, then ask you only what they could not work
                out. You decide every step; the studio proves the result matches what you
                agreed.
              </p>
            </>
          )}
          <div className={`flex flex-wrap items-center justify-center gap-1 ${embedded ? "" : "mt-5"}`}>
            {STEPS.map((s, i) => (
              <div key={s} className="flex items-center gap-1">
                {i > 0 && <div className="h-px w-5 bg-edge" />}
                <button
                  onClick={() => i < step && setStep(i)}
                  disabled={i >= step}
                  className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs transition-colors ${
                    i === step ? "bg-accent/10 font-semibold text-accent ring-1 ring-inset ring-accent/30"
                      : i < step ? "text-good hover:text-accent" : "text-ink-dim"}`}
                >
                  {i < step ? <Check className="h-3 w-3" /> : null}{s}
                </button>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <Card className="border-bad/40"><CardBody className="py-3">
            <p className="text-xs text-bad">{error}</p>
          </CardBody></Card>
        )}

        {/* ---------- STEP 0: add data ---------- */}
        {step === 0 && (
          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2"><FileUp className="h-4 w-4 text-accent" /> Add your data</span>}
              subtitle="Any number of files, multi-sheet workbooks, different years. No questions yet - the agents look first."
            />
            <CardBody className="space-y-3">
              <input
                type="file" multiple accept=".csv,.xlsx,.xls,.xlsm"
                onChange={(e) => upload(e.target.files)}
                className="block w-full cursor-pointer rounded-xl border-2 border-dashed border-edge bg-panel-2/50 px-4 py-6 text-xs text-ink-dim file:mr-3 file:cursor-pointer file:rounded-full file:border-0 file:bg-accent/10 file:px-4 file:py-1.5 file:text-xs file:font-semibold file:text-accent"
              />
              {busy === "upload" && <Spinner label="Reading the sheets..." />}
              {sheets.length > 0 && (
                <div className="overflow-x-auto rounded-xl border border-edge">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                        <th className="px-3 py-2">Sheet</th><th className="px-3 py-2">Rows</th>
                        <th className="px-3 py-2">Cols</th><th className="px-3 py-2">Header</th><th />
                      </tr>
                    </thead>
                    <tbody>
                      {sheets.map((s) => (
                        <tr key={s.name} className="border-b border-edge/50">
                          <td className="max-w-72 px-3 py-2" title={s.columns.join(", ")}>
                            <span className="block truncate font-medium">{s.name}</span>
                            {s.note && (
                              <span className="mt-0.5 inline-block rounded-full bg-warn/10 px-2 py-0.5 text-[9px] text-warn ring-1 ring-inset ring-warn/25">
                                {s.note}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 tabular-nums">{s.rows.toLocaleString()}</td>
                          <td className="px-3 py-2 tabular-nums">{s.cols}</td>
                          <td className="px-3 py-2">
                            <select
                              value={s.header_row}
                              onChange={(e) => setHeader(s.name, Number(e.target.value))}
                              title="Which row holds the column names"
                              className="rounded border border-edge bg-panel-2 px-1 py-0.5 text-[10px] outline-none focus:border-accent"
                            >
                              {[0, 1, 2, 3, 4, 5, 6].map((r) => (
                                <option key={r} value={r}>row {r + 1}</option>
                              ))}
                            </select>
                          </td>
                          <td className="px-3 py-2 text-right">
                            <button onClick={() => removeSheet(s.name)} className="text-ink-dim hover:text-bad">
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {combine && (
                <div className="rounded-xl border border-accent/30 bg-accent/5 p-4">
                  <p className="text-sm font-semibold">
                    {sheets.length} sheets - how should they be combined?
                  </p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-ink-dim">
                    {combineNote ?? "Nothing is combined until you approve this."}
                  </p>
                  <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
                    <select
                      value={combine.strategy}
                      onChange={(e) => setCombine({ ...combine, strategy: e.target.value as CombineProposal["strategy"] })}
                      className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-xs outline-none focus:border-accent"
                    >
                      <option value="stack">Stack them - rows on rows</option>
                      <option value="join">Join on a key - facts side by side</option>
                      <option value="single">Use one sheet only</option>
                    </select>
                    {combine.strategy === "join" && (
                      <select
                        value={combine.join_key ?? ""}
                        onChange={(e) => setCombine({ ...combine, join_key: e.target.value })}
                        className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-xs outline-none focus:border-accent"
                      >
                        {(combine.join_candidates ?? (combine.join_key ? [combine.join_key] : [])).map((k) => (
                          <option key={k} value={k}>key: {k}</option>
                        ))}
                      </select>
                    )}
                    {combine.strategy === "single" && (
                      <select
                        value={combine.pick ?? combine.sheets[0]}
                        onChange={(e) => setCombine({ ...combine, pick: e.target.value })}
                        className="max-w-64 rounded-lg border border-edge bg-panel-2 px-2 py-1 text-xs outline-none focus:border-accent"
                      >
                        {combine.sheets.map((sh) => (
                          <option key={sh} value={sh}>{sh}</option>
                        ))}
                      </select>
                    )}
                  </div>
                  {combine.notes.map((n) => (
                    <p key={n} className="mt-1.5 flex items-start gap-1.5 text-[11px] text-ink-dim">
                      <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-good" /> {n}
                    </p>
                  ))}
                  {combine.strategy === "join" && joinQ?.checked && (
                    <div className={`mt-2.5 rounded-lg border px-3 py-2 ${
                      joinQ.verdict === "clean" ? "border-good/40 bg-good/5"
                        : joinQ.verdict === "lossy" ? "border-warn/40 bg-warn/5"
                        : "border-bad/40 bg-bad/5"}`}>
                      <p className="text-[11px] font-semibold">
                        Join quality: {joinQ.worst_match_pct}% of keys match across every sheet
                      </p>
                      {(joinQ.per_sheet ?? []).map((q) => (
                        <p key={q.sheet} className="mt-0.5 text-[10px] text-ink-dim">
                          {q.sheet}: {q.matched} of {q.keys} keys matched
                          {q.unmatched_examples.length > 0 && ` - missing ${q.unmatched_examples.slice(0, 3).join(", ")}`}
                        </p>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 flex justify-end">
                    <Button size="sm" onClick={approveCombine} disabled={busy !== null}>
                      {busy === "profile" ? <Spinner /> : null} Approve and understand the data
                    </Button>
                  </div>
                </div>
              )}
              <div className="flex justify-end">
                <Button onClick={doProfile} disabled={!sheets.length || busy !== null || !!combine}>
                  {busy === "profile" ? <Spinner /> : <Sparkles className="h-4 w-4" />}
                  Understand this data
                </Button>
              </div>
            </CardBody>
          </Card>
        )}

        {/* ---------- STEP 1: understand ---------- */}
        {step === 1 && profile && (
          <>
            {narrative && (
              <Card className="border-accent/25"><CardBody className="flex items-start gap-3 py-4">
                <Bot className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <div className="min-w-0 space-y-2">
                  <p className="text-xs leading-relaxed">{narrative.message}</p>
                  <Badge tone={narrative.mode === "llm" ? "accent" : "neutral"}>
                    {narrative.mode === "llm" ? "AI reading" : "rule-based reading"}
                  </Badge>
                </div>
              </CardBody></Card>
            )}
            <Card>
              <CardHeader
                title={<span className="flex items-center gap-2"><Table2 className="h-4 w-4 text-accent" /> What the agents found</span>}
                subtitle={`${profile.n_rows.toLocaleString()} rows x ${profile.n_cols} columns${
                  combine && sheets.length > 1
                    ? ` - ${combine.strategy} across ${combine.sheets.length} sheet(s)` : ""}`}
              />
              <CardBody className="space-y-3">
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(profile.role_counts).filter(([, n]) => n > 0).map(([r, n]) => (
                    <span key={r} className="rounded-full bg-accent/10 px-2.5 py-1 text-[10px] font-medium text-accent ring-1 ring-inset ring-accent/25">
                      {n} {r}{n > 1 ? "s" : ""}
                    </span>
                  ))}
                  {profile.table_unit && (
                    <span className="rounded-full bg-rs-violet/10 px-2.5 py-1 text-[10px] font-medium text-rs-violet ring-1 ring-inset ring-rs-violet/25">
                      values in {profile.table_unit.unit}
                    </span>
                  )}
                  {profile.wide_blocks && (
                    <span className="rounded-full bg-warn/10 px-2.5 py-1 text-[10px] font-medium text-warn ring-1 ring-inset ring-warn/25">
                      {profile.wide_blocks.periods.length} periods across the columns
                    </span>
                  )}
                  {profile.duplicate_rows > 0 && (
                    <span className="rounded-full bg-warn/10 px-2.5 py-1 text-[10px] font-medium text-warn ring-1 ring-inset ring-warn/25">
                      {profile.duplicate_rows} duplicate row(s)
                    </span>
                  )}
                  {profile.pii_columns.length > 0 && (
                    <span className="rounded-full bg-bad/10 px-2.5 py-1 text-[10px] font-medium text-bad ring-1 ring-inset ring-bad/25">
                      <ShieldAlert className="mr-1 inline h-3 w-3" />
                      personal data in {profile.pii_columns.length} column(s)
                    </span>
                  )}
                </div>
                <div className="max-h-96 overflow-auto rounded-xl border border-edge">
                  <table className="w-full text-left text-[11px]">
                    <thead className="sticky top-0">
                      <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                        <th className="px-3 py-2">Column</th><th className="px-3 py-2">Reads as</th>
                        <th className="px-3 py-2">Role</th><th className="px-3 py-2">Blank</th>
                        <th className="px-3 py-2">Distinct</th><th className="px-3 py-2">Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {profile.columns.map((c) => (
                        <tr key={c.source_name} className="border-b border-edge/50 align-top">
                          <td className="max-w-56 px-3 py-1.5">
                            <span className="block truncate font-medium" title={c.source_name}>{c.source_name}</span>
                          </td>
                          <td className="px-3 py-1.5" title={c.dtype_evidence}>
                            {c.dtype}
                            {c.dtype_confidence < 0.85 && (
                              <span className="ml-1 text-warn" title="the studio will ask about this one">?</span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-ink-dim">{c.role}</td>
                          <td className={`px-3 py-1.5 tabular-nums ${c.missing_pct >= 50 ? "text-warn" : "text-ink-dim"}`}>
                            {c.missing_pct}%
                          </td>
                          <td className="px-3 py-1.5 tabular-nums text-ink-dim">{c.distinct.toLocaleString()}</td>
                          <td className="px-3 py-1.5">
                            <span className="flex flex-wrap gap-1">
                              {c.quality.map((q) => (
                                <span key={q.kind} title={q.detail}
                                  className="rounded bg-warn/10 px-1.5 py-0.5 text-[9px] text-warn">
                                  {q.kind.replace(/_/g, " ")}
                                </span>
                              ))}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex justify-between gap-2">
                  <Button variant="ghost" size="sm" onClick={() => setStep(0)}>Back to files</Button>
                  <Button onClick={doInterview} disabled={busy !== null}>
                    {busy === "interview" ? <Spinner /> : null} Now ask me the questions
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
              </CardBody>
            </Card>
          </>
        )}

        {/* ---------- STEP 2: decide ---------- */}
        {step === 2 && (
          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2"><Bot className="h-4 w-4 text-accent" /> {questions.length} decisions</span>}
              subtitle="Only what the profile could not settle. Each option is computed from your data; the suggested one is marked."
            />
            <CardBody className="space-y-4">
              {questions.map((q) => (
                <div key={q.id} className="rounded-xl border border-edge bg-panel-2/40 p-4">
                  <p className="text-sm font-semibold">{q.question}</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">{q.why}</p>
                  <div className="mt-2.5 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {q.options.map((o) => {
                      const active = answers[q.id] === o.value;
                      return (
                        <button
                          key={o.value || "none"}
                          onClick={() => setAnswers((a) => ({ ...a, [q.id]: o.value }))}
                          className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                            active ? "border-accent bg-accent/10" : "border-edge bg-panel hover:border-accent/40"}`}
                        >
                          <span className="flex items-center gap-1.5 text-xs font-medium">
                            {active && <Check className="h-3 w-3 text-accent" />}
                            {o.label}
                            {o.value === q.suggested && (
                              <span className="rounded-full bg-rs-teal/10 px-1.5 py-0.5 text-[9px] text-rs-teal ring-1 ring-inset ring-rs-teal/25">
                                suggested
                              </span>
                            )}
                          </span>
                          <span className="mt-0.5 block text-[10px] leading-relaxed text-ink-dim">{o.detail}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
              <div>
                <label className="text-[11px] font-medium text-ink-dim">
                  Anything else the agents should know? (optional)
                </label>
                <textarea
                  value={note} onChange={(e) => setNote(e.target.value)} rows={2}
                  placeholder="e.g. 'CBIC is not a state - keep it but exclude from state comparisons'"
                  className="mt-1 w-full rounded-lg border border-edge bg-panel-2 px-3 py-2 text-xs outline-none focus:border-accent"
                />
              </div>
              <div className="flex justify-between gap-2">
                <Button variant="ghost" size="sm" onClick={() => setStep(1)}>Back</Button>
                <Button onClick={doBlueprint} disabled={busy !== null}>
                  {busy === "blueprint" ? <Spinner /> : null} Draft the blueprint <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </CardBody>
          </Card>
        )}

        {/* ---------- STEP 3: blueprint ---------- */}
        {step === 3 && bp && (
          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2"><Pencil className="h-4 w-4 text-accent" /> The blueprint</span>}
              subtitle="The contract for the finished table. Every field is editable - rename columns, change a type or role, drop what you do not need."
              right={<Badge tone="accent">{bp.columns.filter((c) => c.action !== "drop").length} columns</Badge>}
            />
            <CardBody className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-dim">
                <Layers className="h-3.5 w-3.5" />
                <span>One row per:</span>
                <span className="rounded-full bg-accent/10 px-2 py-0.5 font-medium text-accent">
                  {bp.grain.length ? bp.grain.join(" + ") : "not declared"}
                </span>
                {!!bp.reshape && (
                  <span className="rounded-full bg-rs-teal/10 px-2 py-0.5 text-rs-teal">periods become rows</span>
                )}
                {!!bp.unit_conversion && (
                  <span className="rounded-full bg-rs-violet/10 px-2 py-0.5 text-rs-violet">units converted</span>
                )}
              </div>
              <div className="max-h-[28rem] overflow-auto rounded-xl border border-edge">
                <table className="w-full text-left text-[11px]">
                  <thead className="sticky top-0">
                    <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                      <th className="px-2 py-2">Source</th><th className="px-2 py-2">Final name</th>
                      <th className="px-2 py-2">Type</th><th className="px-2 py-2">Role</th>
                      <th className="px-2 py-2">Unit</th><th className="px-2 py-2">Description</th>
                      <th className="px-2 py-2">Keep</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bp.columns.map((c, i) => (
                      <tr key={`${c.name}-${i}`} className={`border-b border-edge/50 ${c.action === "drop" ? "opacity-45" : ""}`}>
                        <td className="max-w-40 px-2 py-1.5">
                          <span className="block truncate text-ink-dim" title={c.label}>{c.label}</span>
                          {c.origin !== "source column" && (
                            <span className="text-[9px] text-rs-teal">{c.origin}</span>
                          )}
                        </td>
                        <td className="px-2 py-1.5">
                          <input value={c.name} onChange={(e) => editCol(i, { name: e.target.value })}
                            className="w-32 rounded border border-edge bg-panel-2 px-1.5 py-0.5 font-mono text-[10px] outline-none focus:border-accent" />
                        </td>
                        <td className="px-2 py-1.5">
                          <select value={c.dtype} onChange={(e) => editCol(i, { dtype: e.target.value })}
                            className="rounded border border-edge bg-panel-2 px-1 py-0.5 text-[10px] outline-none focus:border-accent">
                            {DTYPES.map((d) => <option key={d} value={d}>{d}</option>)}
                          </select>
                        </td>
                        <td className="px-2 py-1.5">
                          <select value={c.role} onChange={(e) => editCol(i, { role: e.target.value })}
                            className="rounded border border-edge bg-panel-2 px-1 py-0.5 text-[10px] outline-none focus:border-accent">
                            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                          </select>
                        </td>
                        <td className="px-2 py-1.5">
                          <input value={c.unit ?? ""} placeholder="-"
                            onChange={(e) => editCol(i, { unit: e.target.value || null })}
                            className="w-16 rounded border border-edge bg-panel-2 px-1.5 py-0.5 text-[10px] outline-none focus:border-accent" />
                        </td>
                        <td className="px-2 py-1.5">
                          <input value={c.description}
                            onChange={(e) => editCol(i, { description: e.target.value })}
                            className="w-full min-w-40 rounded border border-edge bg-panel-2 px-1.5 py-0.5 text-[10px] outline-none focus:border-accent" />
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <input type="checkbox" checked={c.action !== "drop"}
                            onChange={(e) => editCol(i, { action: e.target.checked ? "keep" : "drop" })}
                            className="accent-accent" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex justify-between gap-2">
                <Button variant="ghost" size="sm" onClick={() => setStep(2)}>Back to decisions</Button>
                <Button onClick={doBuild} disabled={busy !== null}>
                  {busy === "build" ? <Spinner /> : null} Build and check it <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </CardBody>
          </Card>
        )}

        {/* ---------- STEP 4: certify ---------- */}
        {step === 4 && cert && preview && (
          <>
            <Card className={cert.verdict === "ready" ? "border-good/40" : "border-bad/40"}>
              <CardHeader
                title={
                  <span className="flex items-center gap-2">
                    {cert.verdict === "ready"
                      ? <CheckCircle2 className="h-4 w-4 text-good" />
                      : <XCircle className="h-4 w-4 text-bad" />}
                    {cert.verdict === "ready" ? "Ready" : "Not ready"} - {cert.n_rows.toLocaleString()} rows x {cert.n_cols} columns
                  </span>
                }
                subtitle="Every check the studio ran against the blueprint you approved."
              />
              <CardBody className="space-y-3">
                <div className="space-y-1">
                  {cert.checks.map((c) => (
                    <p key={c.check} className="flex items-start gap-2 text-[11px]">
                      {c.passed ? <Check className="mt-0.5 h-3 w-3 shrink-0 text-good" />
                        : c.severity === "warning" ? <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-warn" />
                        : <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-bad" />}
                      <span className={c.passed ? "" : c.severity === "warning" ? "text-warn" : "text-bad"}>
                        <span className="font-medium">{c.check}</span>
                        <span className="text-ink-dim"> - {c.detail}</span>
                      </span>
                    </p>
                  ))}
                </div>
                {steps.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 border-t border-edge pt-3">
                    {steps.map((s, i) => (
                      <span key={i} className="rounded-full bg-good/10 px-2.5 py-1 text-[10px] text-good ring-1 ring-inset ring-good/25">
                        {s}
                      </span>
                    ))}
                  </div>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="The prepared table" subtitle="First rows of the certified result." />
              <CardBody className="space-y-3">
                <div className="max-h-64 overflow-auto rounded-xl border border-edge">
                  <table className="w-full text-left text-[11px]">
                    <thead className="sticky top-0">
                      <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                        {preview.columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2">{c}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.slice(0, 12).map((r, i) => (
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
                {registered ? (
                  <div className="rounded-xl border border-good/40 bg-good/5 px-4 py-3">
                    <p className="text-sm font-semibold text-good">
                      Checked, proven and added to your workspace
                    </p>
                    <p className="mt-1 text-xs text-ink-dim">
                      '{registered.filename}' ({registered.rows.toLocaleString()} rows) is now an
                      ordinary dataset, exactly as if you had uploaded it - with its recipe kept, so
                      next month's file can be prepared the same way in one step.
                      {!onContinue && (embedded
                        ? " It is in your library now; explore it or train on it from there."
                        : " Open the main app to explore it or train on it.")}
                    </p>
                    {/* The pipeline continues here rather than ending. Still a
                        decision - the agents only run once you say so. */}
                    {onContinue && (
                      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-good/25 pt-3">
                        <span className="text-xs text-ink-dim">Now analyse it:</span>
                        <Button
                          size="sm"
                          onClick={() => onContinue("explore", {
                            datasetId: registered.dataset_id, filename: registered.filename })}
                        >
                          Explore the findings <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => onContinue("ask", {
                            datasetId: registered.dataset_id, filename: registered.filename })}
                        >
                          Ask a question
                        </Button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setStep(3)}>Edit blueprint</Button>
                      {(["csv", "dictionary", "schema", "recipe"] as const).map((k) => (
                        <a key={k} href={`/api/prep2/${sid}/export/${k}`} download>
                          <Button variant="outline" size="sm"><Download className="h-3.5 w-3.5" /> {k}</Button>
                        </a>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <input value={dsName} onChange={(e) => setDsName(e.target.value)}
                        placeholder="Dataset name"
                        className="rounded-lg border border-edge bg-panel-2 px-3 py-2 text-xs outline-none focus:border-accent" />
                      <Button onClick={doRegister} disabled={busy !== null || cert.errors > 0}>
                        {busy === "register" ? <Spinner /> : null} Register on the platform
                      </Button>
                    </div>
                  </div>
                )}
              </CardBody>
            </Card>

            {dictionary && (
              <Card>
                <CardHeader title="Data dictionary" subtitle="What travels with the table when a department shares it." />
                <CardBody>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-edge bg-panel-2/50 p-3 text-[10px] leading-relaxed text-ink-dim">
                    {dictionary}
                  </pre>
                </CardBody>
              </Card>
            )}
          </>
        )}

        <p className="text-center text-[10px] text-ink-dim">
          Prototype - sessions live in memory and reset with the server. The agents read column
          names, types and counts only, never your data values.
        </p>
      </>
    </Shell>
  );
}

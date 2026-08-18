// Ask your data: question -> visible interpretation -> run -> answer.
// The interpretation card is the contract (rule 12): nothing executes
// until the user runs exactly the sentences shown. Every answer carries
// its caveats (rule 13) and a deterministically chosen chart (rule 14).
import { useState } from "react";
import { ArrowLeft, CircleHelp, Download, MessageSquareText, Play, Sparkles } from "lucide-react";
import { api } from "../../api/client";
import type { QueryAnswer, QueryPlanCandidate, QueryPlanResponse } from "../../types";
import { genLabel } from "../../lib/labels";
import { saveBlob } from "../../lib/download";
import { QueryChart } from "../QueryChart";
import { Badge, Button, Card, CardBody, CardHeader, Spinner } from "../ui";

const EXAMPLES = [
  "top 5 by",
  "average ... by ...",
  "how many rows per ...",
  "... below 40",
];

export function AskScreen({
  datasetId,
  filename,
  initialQuestion,
  onBack,
}: {
  datasetId: string;
  filename: string;
  initialQuestion?: string;
  onBack: () => void;
}) {
  const [question, setQuestion] = useState(initialQuestion ?? "");
  const [planResp, setPlanResp] = useState<QueryPlanResponse | null>(null);
  const [answer, setAnswer] = useState<QueryAnswer | null>(null);
  const [busy, setBusy] = useState<"plan" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<{ col: string; dir: 1 | -1 } | null>(null);

  const interpret = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text) return;
    setBusy("plan");
    setError(null);
    setAnswer(null);
    setPlanResp(null);
    try {
      setPlanResp(await api.queryPlan(datasetId, text));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const run = async (cand: QueryPlanCandidate) => {
    setBusy("run");
    setError(null);
    try {
      setAnswer(await api.queryRun(datasetId, cand.plan, question));
      setSortBy(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const rows = answer
    ? [...answer.result.table].sort((a, b) => {
        if (!sortBy) return 0;
        const av = a[sortBy.col];
        const bv = b[sortBy.col];
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av > bv ? 1 : av < bv ? -1 : 0) * sortBy.dir;
      })
    : [];

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-bold">
          <MessageSquareText className="h-5 w-5 text-accent" /> Ask your data
        </h2>
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </Button>
      </div>

      {/* Question input */}
      <Card>
        <CardBody>
          <p className="mb-2 text-xs text-ink-dim">
            Asking about <span className="font-semibold text-ink">{filename}</span> - a direct
            answer from the data, no model training.
          </p>
          <div className="flex gap-2">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && interpret()}
              placeholder="e.g. top 5 districts by enrollment, or: which rows are below 40"
              className="min-w-0 flex-1 rounded-lg border border-edge bg-panel-2 px-3.5 py-2 text-sm outline-none placeholder:text-ink-dim/60 focus:border-accent"
            />
            <Button onClick={() => interpret()} disabled={busy !== null || !question.trim()}>
              {busy === "plan" ? <Spinner /> : "Interpret"}
            </Button>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setQuestion(ex)}
                className="rounded-full bg-slate-500/8 px-2.5 py-0.5 text-[10px] text-ink-dim ring-1 ring-inset ring-slate-500/15 hover:text-ink"
              >
                {ex}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      {error && (
        <p className="rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-xs text-bad">{error}</p>
      )}

      {/* Clarify */}
      {planResp?.mode === "clarify" && (
        <Card className="border-warn/40">
          <CardBody className="flex items-start gap-2">
            <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
            <div>
              <p className="text-sm">{planResp.clarify_question}</p>
              <p className="mt-1 text-[11px] text-ink-dim">
                Rephrase the question above using the column names in your data.
              </p>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Interpretation card(s): the executor contract */}
      {planResp && planResp.mode !== "clarify" &&
        planResp.plans.map((cand, i) => (
          <Card key={i} className={planResp.mode === "ambiguous" ? "border-accent/40" : ""}>
            <CardHeader
              title={
                planResp.mode === "ambiguous"
                  ? `Interpretation ${i + 1} of ${planResp.plans.length}`
                  : "Interpreted as"
              }
              subtitle={cand.note || undefined}
              right={<Badge tone={planResp.generated_by === "claude" ? "accent" : "neutral"}>{genLabel(planResp.generated_by)}</Badge>}
            />
            <CardBody>
              <ol className="list-decimal space-y-1 pl-5 text-sm">
                {cand.sentences.map((s, j) => (
                  <li key={j} className="leading-relaxed">
                    {Object.keys(cand.term_glossary).reduce<React.ReactNode>(
                      (node, term) =>
                        typeof node === "string" && node.includes(term) ? (
                          <span title={cand.term_glossary[term]}>{node}</span>
                        ) : (
                          node
                        ),
                      s,
                    )}
                  </li>
                ))}
              </ol>
              <div className="mt-3 flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setPlanResp(null)}>
                  Edit question
                </Button>
                <Button size="sm" onClick={() => run(cand)} disabled={busy !== null}>
                  {busy === "run" ? <Spinner /> : (
                    <>
                      <Play className="h-3.5 w-3.5" />
                      {planResp.mode === "ambiguous" ? `Run interpretation ${i + 1}` : "Run"}
                    </>
                  )}
                </Button>
              </div>
            </CardBody>
          </Card>
        ))}

      {/* Answer */}
      {answer && (
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-accent" /> Answer
              </span>
            }
            right={<Badge tone={answer.generated_by === "claude" ? "accent" : "neutral"}>{genLabel(answer.generated_by)}</Badge>}
          />
          <CardBody className="space-y-3">
            <p className="text-sm font-medium leading-relaxed">{answer.headline}</p>

            {answer.caveats.length > 0 && (
              <div className="space-y-1 rounded-lg border border-warn/30 bg-warn/5 px-3 py-2">
                {answer.caveats.map((c, i) => (
                  <p key={i} className="text-[11px] leading-relaxed text-warn">{c}</p>
                ))}
              </div>
            )}

            {/* Chart chosen from the result shape on the backend (rule 14). */}
            {answer.chart && answer.chart.kind !== "table" && (
              <QueryChart spec={answer.chart} result={answer.result} />
            )}

            <div className="overflow-x-auto rounded-lg border border-edge">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                    {answer.result.columns.map((c) => (
                      <th
                        key={c}
                        onClick={() =>
                          setSortBy((p) => ({ col: c, dir: p?.col === c && p.dir === 1 ? -1 : 1 }))
                        }
                        className="cursor-pointer px-3 py-2 hover:text-ink"
                        title="Click to sort"
                      >
                        {c}
                        {sortBy?.col === c && (sortBy.dir === 1 ? " ↑" : " ↓")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 200).map((r, i) => (
                    <tr key={i} className="border-b border-edge/50">
                      {answer.result.columns.map((c) => (
                        <td key={c} className="px-3 py-1.5 tabular-nums">
                          {r[c] == null ? <span className="text-ink-dim">-</span> : String(r[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {answer.result.table.length > 200 && (
                <p className="border-t border-edge bg-panel-2 px-3 py-1.5 text-[10px] text-ink-dim">
                  Showing the first 200 of {answer.result.table.length} rows.
                </p>
              )}
            </div>

            <div className="flex items-center justify-between gap-3">
              <p className="text-[10px] leading-relaxed text-ink-dim">
                Computed from {answer.filename}
                {" - "}
                {answer.result.row_counts.map((rc) => `${rc.step}: ${rc.rows.toLocaleString()}`).join(" → ")}
                . The plan and row counts are in the activity log.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  const blob = await api.queryExportCsv(datasetId, answer.plan, question);
                  saveBlob(blob, "answer.csv");
                }}
              >
                <Download className="h-3.5 w-3.5" /> CSV
              </Button>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

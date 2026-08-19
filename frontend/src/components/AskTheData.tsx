// Interactive Q&A over the analysis - stakeholders ask, Claude answers from the facts.
import { useRef, useState } from "react";
import { MessageCircleQuestion, Send, User } from "lucide-react";
import { api } from "../api/client";
import { eta } from "../lib/eta";
import { Badge, Card, CardBody, CardHeader, Spinner } from "./ui";
import { genLabel } from "../lib/labels";

interface QA {
  q: string;
  a: string;
  by: string;
}

const STARTERS = [
  "What single action would move the needle most?",
  "Which finding is most reliable, and which is weakest?",
  "Explain the main result as if to a board meeting.",
];

export function AskTheData({ runId, rows }: { runId: string; rows: number }) {
  const [thread, setThread] = useState<QA[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const submit = async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setQuestion("");
    try {
      const res = await api.ask(runId, trimmed, thread.map(({ q, a }) => ({ q, a })));
      setThread((t) => [...t, { q: trimmed, a: res.answer, by: res.generated_by }]);
    } catch (e) {
      setThread((t) => [
        ...t,
        { q: trimmed, a: e instanceof Error ? e.message : "Something went wrong.", by: "error" },
      ]);
    } finally {
      setBusy(false);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
    }
  };

  return (
    <Card className="border-accent/30">
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <MessageCircleQuestion className="h-4 w-4 text-accent" /> Ask the data
          </span>
        }
        subtitle="Questions are answered from this analysis's computed facts - nothing invented"
      />
      <CardBody>
        {thread.length === 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {STARTERS.map((s) => (
              <button
                key={s}
                onClick={() => submit(s)}
                disabled={busy}
                className="rounded-full border border-edge px-2.5 py-1 text-[11px] text-ink-dim transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {thread.length > 0 && (
          <div className="mb-4 max-h-96 space-y-4 overflow-y-auto pr-1">
            {thread.map((qa, i) => (
              <div key={i} className="space-y-2">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 rounded-full bg-ink-dim/10 p-1.5">
                    <User className="h-3 w-3 text-ink-dim" />
                  </span>
                  <p className="min-w-0 break-words pt-1 text-sm font-medium">{qa.q}</p>
                </div>
                <div className="ml-8 rounded-2xl border border-edge bg-panel-2 px-4 py-3 backdrop-blur">
                  <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{qa.a}</p>
                  <div className="mt-1.5">
                    <Badge tone={qa.by === "claude" ? "accent" : qa.by === "error" ? "bad" : "neutral"}>
                      {genLabel(qa.by)}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
        )}

        {busy && (
          <div className="mb-3 ml-8">
            <Spinner label={`Thinking… (${eta("ask", rows, true)})`} />
          </div>
        )}

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit(question);
          }}
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder='e.g. "Which group should we prioritize and why?"'
            className="min-w-0 flex-1 rounded-2xl border border-edge bg-panel-2 px-3.5 py-2 text-sm outline-none backdrop-blur placeholder:text-ink-dim/60 focus:border-accent"
            disabled={busy}
          />
          <button
            type="submit"
            disabled={busy || !question.trim()}
            className="rounded-xl bg-accent px-3.5 text-white shadow-md shadow-accent/25 transition-all hover:bg-accent/90 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </CardBody>
    </Card>
  );
}

import { useState } from "react";
import { Bot, MessageSquare } from "lucide-react";
import type { Eda, Profile } from "../../types";
import { Badge, Button, Card, CardBody, CardHeader, Spinner, Stat } from "../ui";

const ROLE_TONE: Record<string, "accent" | "good" | "warn" | "neutral" | "bad"> = {
  numeric: "accent",
  categorical: "good",
  datetime: "warn",
  boolean: "good",
  identifier: "neutral",
  text: "neutral",
};

export function EdaScreen({
  profile,
  eda,
  question,
  onApprove,
  busy,
}: {
  profile: Profile;
  eda: Eda;
  question: string;
  onApprove: (comment: string) => void;
  busy: boolean;
}) {
  const [comment, setComment] = useState(question);

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Agent findings */}
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-accent" /> EDA agent findings
              </span>
            }
            right={<Badge tone={eda.generated_by === "claude" ? "accent" : "neutral"}>{eda.generated_by}</Badge>}
          />
          <CardBody>
            <p className="text-sm leading-relaxed">{eda.summary}</p>
            <ul className="mt-4 space-y-2">
              {eda.key_findings.map((f, i) => (
                <li key={i} className="flex gap-2 text-sm text-ink-dim">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  {f}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        {/* Column table */}
        <Card>
          <CardHeader title="Columns" subtitle={`${profile.n_rows.toLocaleString()} rows × ${profile.n_cols} columns`} />
          <CardBody className="overflow-x-auto p-0">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-ink-dim">
                  <th className="px-5 py-2.5 font-medium">Column</th>
                  <th className="px-3 py-2.5 font-medium">Role</th>
                  <th className="px-3 py-2.5 font-medium">Missing</th>
                  <th className="px-3 py-2.5 font-medium">Unique</th>
                  <th className="px-3 py-2.5 font-medium">Summary</th>
                </tr>
              </thead>
              <tbody>
                {profile.columns.map((c) => (
                  <tr key={c.name} className="border-b border-edge/50 last:border-0">
                    <td className="px-5 py-2 font-medium">{c.name}</td>
                    <td className="px-3 py-2">
                      <Badge tone={ROLE_TONE[c.role] ?? "neutral"}>{c.role}</Badge>
                    </td>
                    <td className="px-3 py-2 tabular-nums text-ink-dim">
                      {c.missing_pct ? `${c.missing_pct}%` : "—"}
                    </td>
                    <td className="px-3 py-2 tabular-nums text-ink-dim">{c.unique_count}</td>
                    <td className="max-w-56 truncate px-3 py-2 text-ink-dim">
                      {c.stats
                        ? `mean ${c.stats.mean} · min ${c.stats.min} · max ${c.stats.max}`
                        : c.top_values
                          ? c.top_values.slice(0, 3).map((t) => String(t.value)).join(", ")
                          : c.sample_values.slice(0, 3).map(String).join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      </div>

      {/* Right rail: stats + approval gate */}
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Rows" value={profile.n_rows.toLocaleString()} />
          <Stat label="Columns" value={profile.n_cols} />
          <Stat label="Missing cells" value={`${profile.missingness.pct_missing ?? 0}%`} />
          <Stat label="Suggested" value={profile.suggested_use_cases.join(", ") || "—"} />
        </div>

        {profile.correlations.length > 0 && (
          <Card>
            <CardHeader title="Top correlations" />
            <CardBody className="space-y-1.5">
              {profile.correlations.slice(0, 5).map((c, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="text-ink-dim">
                    {c.a} × {c.b}
                  </span>
                  <span className={`font-semibold tabular-nums ${Math.abs(c.corr ?? 0) > 0.5 ? "text-accent" : "text-ink-dim"}`}>
                    {c.corr}
                  </span>
                </div>
              ))}
            </CardBody>
          </Card>
        )}

        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-warn" /> Your input
              </span>
            }
            subtitle="Approval gate — the agents wait for you"
          />
          <CardBody>
            <p className="text-xs text-ink-dim">
              What do you want to understand from this data? The recommendation agent will use this.
            </p>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              placeholder={eda.suggested_questions[0] ?? "e.g. predict churn, find segments…"}
              className="mt-2 w-full resize-none rounded-lg border border-edge bg-panel-2 px-3 py-2 text-sm outline-none placeholder:text-ink-dim/60 focus:border-accent"
            />
            {eda.suggested_questions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {eda.suggested_questions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => setComment(q)}
                    className="rounded-full border border-edge px-2.5 py-1 text-[11px] text-ink-dim transition-colors hover:border-accent hover:text-accent"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
            <div className="mt-4">
              {busy ? (
                <Spinner label="Recommendation agent thinking…" />
              ) : (
                <Button className="w-full" onClick={() => onApprove(comment)}>
                  Approve EDA & get model recommendation
                </Button>
              )}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

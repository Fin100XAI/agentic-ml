import { useState } from "react";
import { Bot, Lightbulb, MessageSquare, Table2 } from "lucide-react";
import type { Eda, Profile } from "../../types";
import { USE_CASE_INFO } from "../../lib/metricInfo";
import { InfoTip } from "../InfoTip";
import { Badge, Button, Card, CardBody, CardHeader, Spinner, Stat } from "../ui";

const ROLE_TONE: Record<string, "accent" | "good" | "warn" | "neutral" | "bad"> = {
  numeric: "accent",
  categorical: "good",
  datetime: "warn",
  boolean: "good",
  identifier: "neutral",
  text: "neutral",
};

const ROLE_TIP: Record<string, string> = {
  numeric: "Numbers you can do math on — amounts, counts, measurements.",
  categorical: "A limited set of labels, like plan type or region.",
  datetime: "Dates or times — enables forecasting over time.",
  boolean: "Yes/no style column with two values — a classic prediction target.",
  identifier: "A unique ID per row. Not useful for prediction, so models ignore it.",
  text: "Free text with many unique values.",
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
  const [tab, setTab] = useState<"columns" | "preview">("columns");

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Agent findings + data */}
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-accent" /> What the EDA agent found
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

        {/* What you can do with this data */}
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Lightbulb className="h-4 w-4 text-warn" /> What you can do with this data
              </span>
            }
            subtitle="Based on the column types the agent detected"
          />
          <CardBody className="grid gap-3 sm:grid-cols-3">
            {profile.suggested_use_cases.map((uc) => {
              const info = USE_CASE_INFO[uc];
              if (!info) return null;
              return (
                <div key={uc} className="rounded-lg border border-edge bg-panel-2/60 px-3 py-2.5">
                  <div className="text-sm">
                    {info.icon} <span className="font-semibold">{info.title}</span>
                  </div>
                  <p className="mt-1 text-[11px] leading-snug text-ink-dim">{info.tagline}</p>
                </div>
              );
            })}
          </CardBody>
        </Card>

        {/* Columns / preview tabs */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-1">
                {(["columns", "preview"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                      tab === t ? "bg-accent-soft text-accent" : "text-ink-dim hover:text-ink"
                    }`}
                  >
                    {t === "columns" ? "Columns" : "Data preview"}
                  </button>
                ))}
              </div>
            }
            subtitle={`${profile.n_rows.toLocaleString()} rows × ${profile.n_cols} columns`}
            right={<Table2 className="h-4 w-4 text-ink-dim" />}
          />
          <CardBody className="overflow-x-auto p-0">
            {tab === "columns" ? (
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-edge text-ink-dim">
                    <th className="px-5 py-2.5 font-medium">Column</th>
                    <th className="px-3 py-2.5 font-medium">Type</th>
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
                        <span className="inline-flex items-center gap-1">
                          <Badge tone={ROLE_TONE[c.role] ?? "neutral"}>{c.role}</Badge>
                          <InfoTip text={ROLE_TIP[c.role] ?? ""} />
                        </span>
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
            ) : (
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-edge text-ink-dim">
                    {profile.columns.map((c) => (
                      <th key={c.name} className="whitespace-nowrap px-3 py-2.5 font-medium first:pl-5">
                        {c.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {profile.preview.map((row, i) => (
                    <tr key={i} className="border-b border-edge/50 last:border-0">
                      {profile.columns.map((c) => (
                        <td key={c.name} className="whitespace-nowrap px-3 py-1.5 tabular-nums text-ink-dim first:pl-5">
                          {String(row[c.name] ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Right rail */}
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Rows" value={profile.n_rows.toLocaleString()} />
          <Stat label="Columns" value={profile.n_cols} />
          <Stat label="Missing cells" value={`${profile.missingness.pct_missing ?? 0}%`} />
          <Stat label="Quality" value={
            (profile.missingness.pct_missing ?? 0) < 1 ? "clean" :
            (profile.missingness.pct_missing ?? 0) < 10 ? "usable" : "gappy"
          } />
        </div>

        {profile.correlations.length > 0 && (
          <Card>
            <CardHeader
              title={
                <span className="inline-flex items-center gap-1">
                  Strongest relationships
                  <InfoTip text="Correlation ranges from -1 to 1. Near 1: the two columns rise together. Near -1: one rises as the other falls. Near 0: no linear relationship." />
                </span>
              }
            />
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

        <Card className="border-warn/30">
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-warn" /> Your turn
              </span>
            }
            subtitle="The agents pause here until you approve"
          />
          <CardBody>
            <p className="text-xs leading-relaxed text-ink-dim">
              Tell the agents what you want to learn — or pick a suggestion. This steers which
              analysis gets recommended next.
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
                  Looks right — recommend a model
                </Button>
              )}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

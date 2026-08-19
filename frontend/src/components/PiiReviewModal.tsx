// Privacy screen: shown right after upload when columns look like personal
// data. Nothing (including any AI agent) sees the rows until this is approved.
import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import type { PiiFinding } from "../types";
import { Badge, Button, Card, CardBody } from "./ui";

const ACTION_HELP: Record<string, string> = {
  mask: "redact but keep shape (last digits, initials, domain)",
  drop: "remove the column entirely",
  keep: "leave untouched - your explicit choice, recorded",
};

export function PiiReviewModal({
  filename,
  findings,
  busy,
  onApprove,
}: {
  filename: string;
  findings: PiiFinding[];
  busy: boolean;
  onApprove: (actions: Record<string, string>) => void;
}) {
  const [actions, setActions] = useState<Record<string, string>>(
    () => Object.fromEntries(findings.map((f) => [f.column, f.proposed_action])),
  );
  const masked = Object.values(actions).filter((a) => a !== "keep").length;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 px-4">
        <Card className="max-h-[85vh] overflow-y-auto bg-panel/95">
          <CardBody>
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-warn" />
              <h3 className="text-sm font-semibold">Personal data check</h3>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-dim">
              {filename} contains columns that look like personal information. Nothing has been
              analyzed yet - and no AI has seen any rows. Choose what happens to each column;
              the original file stays untouched either way.
            </p>

            <div className="mt-3 space-y-2">
              {findings.map((f) => (
                <div
                  key={f.column}
                  className="rounded-2xl border border-edge bg-panel-2 px-4 py-2.5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold">{f.column}</span>
                      <Badge tone="warn">{f.kind.replace("_", " ")}</Badge>
                      <span className="text-[10px] tabular-nums text-ink-dim">
                        {f.match_pct}% of values match
                      </span>
                    </div>
                    <select
                      value={actions[f.column]}
                      onChange={(e) =>
                        setActions((a) => ({ ...a, [f.column]: e.target.value }))
                      }
                      className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-xs"
                    >
                      <option value="mask">mask</option>
                      <option value="drop">drop</option>
                      <option value="keep">keep as-is</option>
                    </select>
                  </div>
                  <p className="mt-1 text-[11px] leading-snug text-ink-dim">
                    {f.note} {actions[f.column] === "mask" && <>Example after masking: <span className="font-mono">{f.example_masked}</span></>}
                    {actions[f.column] === "keep" && <span className="text-warn"> Kept values WILL be visible to the AI agents.</span>}
                  </p>
                  <p className="text-[10px] text-ink-dim/80">{ACTION_HELP[actions[f.column]]}</p>
                </div>
              ))}
            </div>

            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="text-[11px] text-ink-dim">
                {masked} of {findings.length} column{findings.length !== 1 ? "s" : ""} will be protected.
              </span>
              <Button onClick={() => onApprove(actions)} disabled={busy}>
                {busy ? "Applying…" : "Approve & continue"}
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </>
  );
}

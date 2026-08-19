// Approve working column names before any analysis or AI call. Departmental
// files often arrive with cryptic headers (AMT_FY23, col_3); fixing them here
// means every chart, brief and future year's file uses names people recognize.
// Renaming creates a derived artifact - the original file never changes.
import { useState } from "react";
import { Columns3 } from "lucide-react";
import { Badge, Button, Card, CardBody } from "./ui";

export function ColumnReviewModal({
  filename,
  columns,
  busy,
  onContinue,
}: {
  filename: string;
  columns: string[];
  busy: boolean;
  onContinue: (renames: Record<string, string>) => void;
}) {
  const [names, setNames] = useState<Record<string, string>>(
    () => Object.fromEntries(columns.map((c) => [c, c])),
  );
  const edited = Object.entries(names).filter(
    ([oldName, newName]) => newName.trim() && newName.trim() !== oldName,
  );
  const trimmed = edited.map(([o, n]) => [o, n.trim()] as const);
  const finalNames = columns.map((c) => names[c]?.trim() || c);
  const collisions = new Set(finalNames.filter((n, i) => finalNames.indexOf(n) !== i));

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm" />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 px-4">
        <Card className="max-h-[85vh] overflow-y-auto bg-panel/95">
          <CardBody>
            <div className="flex items-center gap-2">
              <Columns3 className="h-5 w-5 text-accent" />
              <h3 className="text-sm font-semibold">Check the column names</h3>
              {edited.length > 0 && <Badge tone="accent">{edited.length} renamed</Badge>}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-dim">
              {filename} - fix any cryptic headers before the analysis starts, so every
              chart and brief uses names your department recognizes. The original file
              is never changed, and future files arriving with the old names will still
              match automatically.
            </p>

            <div className="mt-3 max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {columns.map((c) => {
                const changed = names[c]?.trim() && names[c].trim() !== c;
                const collides = collisions.has(names[c]?.trim() || c);
                return (
                  <label key={c} className="flex items-center gap-2 text-xs">
                    <span className="w-2/5 truncate text-ink-dim" title={c}>{c}</span>
                    <span className="text-ink-dim">→</span>
                    <input
                      value={names[c] ?? c}
                      onChange={(e) => setNames((p) => ({ ...p, [c]: e.target.value }))}
                      className={`min-w-0 flex-1 rounded-lg border px-2.5 py-1.5 text-xs outline-none transition-colors ${
                        collides
                          ? "border-bad/60 bg-bad/5"
                          : changed
                            ? "border-accent/50 bg-accent-soft/20 font-medium"
                            : "border-edge bg-panel-2 focus:border-accent"
                      }`}
                    />
                  </label>
                );
              })}
            </div>
            {collisions.size > 0 && (
              <p className="mt-2 text-[11px] text-bad">
                Two columns would share a name - every column needs a unique one.
              </p>
            )}

            <div className="mt-4 flex items-center justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => onContinue({})}
              >
                Names are fine - continue
              </Button>
              <Button
                size="sm"
                disabled={busy || edited.length === 0 || collisions.size > 0}
                onClick={() => onContinue(Object.fromEntries(trimmed))}
              >
                Apply {edited.length > 0 ? `${edited.length} rename${edited.length !== 1 ? "s" : ""}` : ""} & continue
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </>
  );
}

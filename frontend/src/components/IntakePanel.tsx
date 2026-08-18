// Automated intake: standing rules that recognize recurring files and file
// them into an inbox - score / drift-check / retrain proposals that a human
// approves or declines. Cadence flags overdue arrivals; nothing auto-runs.
import { useCallback, useEffect, useState } from "react";
import { Check, Inbox, Plus, Trash2, X } from "lucide-react";
import { api } from "../api/client";
import type { IntakeItem, IntakeRule, RegistryEntry } from "../types";
import { Badge, Button, Card, CardBody, CardHeader } from "./ui";

const ACTION_HELP: Record<string, string> = {
  score: "apply the model to the new rows",
  drift: "check whether the new data still looks like the training data",
  retrain: "start a new model version from the new data (still approval-gated)",
};

export function IntakePanel({
  projectId,
  onOpenRetrainRun,
}: {
  projectId: string;
  onOpenRetrainRun?: (runId: string, prefill: { model_key: string; hyperparams: Record<string, unknown>; target: string | null }) => void;
}) {
  const [rules, setRules] = useState<IntakeRule[] | null>(null);
  const [items, setItems] = useState<IntakeItem[]>([]);
  const [models, setModels] = useState<RegistryEntry[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [formModel, setFormModel] = useState("");
  const [formAction, setFormAction] = useState("score");
  const [formCadence, setFormCadence] = useState("none");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.getIntake(projectId).then((r) => {
      setRules(r.rules);
      setItems(r.items);
    }).catch(() => setRules([]));
  }, [projectId]);

  useEffect(() => {
    refresh();
    api.getProjectModels(projectId).then((r) => setModels(r.models)).catch(() => setModels([]));
  }, [projectId, refresh]);

  const activeModels = models.filter((m) => m.status === "active");
  const pending = items.filter((i) => i.status === "pending");
  const resolved = items.filter((i) => i.status !== "pending").slice(0, 5);

  const addRule = async () => {
    const [modelId, versionStr] = formModel.split("@");
    if (!modelId) return;
    setError(null);
    setBusyId("form");
    try {
      await api.createIntakeRule(projectId, {
        model_id: modelId, version: Number(versionStr),
        action: formAction, cadence: formCadence,
      });
      setShowForm(false);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const resolve = async (item: IntakeItem, decision: "approve" | "decline") => {
    setError(null);
    setBusyId(item.id);
    try {
      const r = await api.resolveIntake(item.id, decision);
      setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, ...r.item } : i)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const approveAll = async () => {
    for (const item of pending) {
      // Sequential on purpose: each approval is its own logged decision.
      // eslint-disable-next-line no-await-in-loop
      await resolve(item, "approve");
    }
  };

  if (rules === null || (rules.length === 0 && activeModels.length === 0)) return null;

  return (
    <section>
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-accent">
        <Inbox className="h-4 w-4" /> Automated intake
        {pending.length > 0 && <Badge tone="accent">{pending.length} awaiting review</Badge>}
      </h3>
      <Card>
        <CardHeader
          title="Standing rules for recurring files"
          subtitle="When an upload matches a rule's columns, it lands here as a proposal. Nothing runs until you approve it - approve executes the action, decline discards it."
          right={
            activeModels.length > 0 && (
              <Button size="sm" variant="ghost" onClick={() => setShowForm((s) => !s)}>
                <Plus className="h-3.5 w-3.5" /> New rule
              </Button>
            )
          }
        />
        <CardBody className="space-y-4">
          {error && <p className="text-xs text-red-600">{error}</p>}

          {showForm && (
            <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-edge bg-panel-2 p-3">
              <label className="text-xs">
                <span className="mb-1 block text-[10px] uppercase tracking-wider text-ink-dim">Model version</span>
                <select
                  className="rounded-lg border border-edge bg-white/70 px-2 py-1.5 text-xs"
                  value={formModel}
                  onChange={(e) => setFormModel(e.target.value)}
                >
                  <option value="">Choose…</option>
                  {activeModels.map((m) => (
                    <option key={`${m.model_id}@${m.version}`} value={`${m.model_id}@${m.version}`}>
                      {m.model_name} v{m.version}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs">
                <span className="mb-1 block text-[10px] uppercase tracking-wider text-ink-dim">When a matching file arrives</span>
                <select
                  className="rounded-lg border border-edge bg-white/70 px-2 py-1.5 text-xs"
                  value={formAction}
                  onChange={(e) => setFormAction(e.target.value)}
                >
                  <option value="score">Propose scoring it</option>
                  <option value="drift">Propose a drift check</option>
                  <option value="retrain">Propose a retrain</option>
                </select>
              </label>
              <label className="text-xs">
                <span className="mb-1 block text-[10px] uppercase tracking-wider text-ink-dim">Expected cadence</span>
                <select
                  className="rounded-lg border border-edge bg-white/70 px-2 py-1.5 text-xs"
                  value={formCadence}
                  onChange={(e) => setFormCadence(e.target.value)}
                >
                  <option value="none">No schedule</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </label>
              <Button size="sm" onClick={addRule} disabled={!formModel || busyId === "form"}>
                Add rule
              </Button>
              <p className="w-full text-[10px] text-ink-dim">
                {ACTION_HELP[formAction]} - a cadence only flags the rule as overdue when no file shows up in time; it never auto-runs anything.
              </p>
            </div>
          )}

          {rules.length > 0 && (
            <ul className="space-y-1.5">
              {rules.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge tone="accent">{r.action}</Badge>
                  <span className="font-medium">{r.name}</span>
                  {r.cadence !== "none" && (
                    <span className="text-ink-dim">expected {r.cadence}</span>
                  )}
                  {r.overdue && <Badge tone="warn">overdue - no matching file arrived</Badge>}
                  <button
                    className="ml-auto text-ink-dim hover:text-red-600"
                    title="Delete this rule"
                    onClick={() => api.deleteIntakeRule(r.id).then(refresh)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {rules.length === 0 && !showForm && (
            <p className="text-xs text-ink-dim">
              No rules yet. Create one to have recurring files (new monthly extracts, fresh
              applicant lists) recognized and queued for one-click review.
            </p>
          )}

          {pending.length > 0 && (
            <div className="space-y-2 border-t border-edge pt-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">Inbox</span>
                {pending.length > 1 && (
                  <Button size="sm" variant="ghost" onClick={approveAll} disabled={busyId !== null}>
                    Approve all ({pending.length})
                  </Button>
                )}
              </div>
              {pending.map((item) => (
                <div key={item.id} className="flex flex-wrap items-center gap-2 rounded-2xl border border-edge bg-panel-2 px-3 py-2 text-xs">
                  <span className="font-medium">{item.filename}</span>
                  <span className="text-ink-dim">matched "{item.rule_name}"</span>
                  {item.coverage != null && item.coverage < 1 && (
                    <Badge tone="warn">{Math.round(item.coverage * 100)}% column match</Badge>
                  )}
                  <span className="ml-auto flex gap-1.5">
                    <Button size="sm" onClick={() => resolve(item, "approve")} disabled={busyId !== null}>
                      <Check className="h-3.5 w-3.5" /> Approve {item.action}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => resolve(item, "decline")} disabled={busyId !== null}>
                      <X className="h-3.5 w-3.5" /> Decline
                    </Button>
                  </span>
                </div>
              ))}
            </div>
          )}

          {resolved.length > 0 && (
            <div className="space-y-2 border-t border-edge pt-3">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">Recently resolved</span>
              {resolved.map((item) => (
                <div key={item.id} className="rounded-xl border border-edge px-3 py-2 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{item.filename}</span>
                    <Badge tone={item.status === "approved" ? "good" : "neutral"}>{item.status}</Badge>
                    {item.results?.kind === "drift" && item.results.verdict && (
                      <Badge tone={item.results.verdict === "stable" ? "good" : "warn"}>{item.results.verdict}</Badge>
                    )}
                  </div>
                  {item.results?.kind === "score" && (
                    <p className="mt-1 leading-relaxed text-ink-dim">
                      Scored {item.results.n} rows. {item.results.summary}
                    </p>
                  )}
                  {item.results?.kind === "drift" && (
                    <p className="mt-1 leading-relaxed text-ink-dim">{item.results.narrative}</p>
                  )}
                  {item.results?.kind === "retrain" && item.results.run_id && (
                    <div className="mt-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          onOpenRetrainRun && item.results?.prefill &&
                          onOpenRetrainRun(item.results.run_id!, item.results.prefill)
                        }
                      >
                        Open the retrain run
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </section>
  );
}

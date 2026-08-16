// Project data dictionary: the user's own column definitions. Agents are
// instructed to prefer these over their guesses, and tooltips cite them.
import { useEffect, useRef, useState } from "react";
import { BookOpen, Plus, Trash2, Upload } from "lucide-react";
import { api } from "../api/client";
import { Badge, Button, Card, CardBody, CardHeader } from "./ui";

export function GlossaryManager({ projectId }: { projectId: string }) {
  const [entries, setEntries] = useState<{ term: string; definition: string }[]>([]);
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [definition, setDefinition] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getGlossary(projectId).then((r) => setEntries(r.entries)).catch(() => setEntries([]));
  }, [projectId]);

  const add = async () => {
    if (!term.trim() || !definition.trim()) return;
    setBusy(true);
    try {
      const r = await api.addGlossary(projectId, [{ term, definition }]);
      setEntries(r.entries);
      setTerm("");
      setDefinition("");
    } finally {
      setBusy(false);
    }
  };

  const uploadFile = async (file: File) => {
    setBusy(true);
    try {
      const r = await api.uploadGlossary(projectId, file);
      setEntries(r.entries);
      setOpen(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <button
        onClick={() => setOpen(!open)}
        className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-ink-dim transition-colors hover:text-ink"
      >
        <BookOpen className="h-4 w-4" /> Data dictionary
        {entries.length > 0 && <Badge tone="accent">{entries.length} terms</Badge>}
        <span className="text-[10px] font-normal normal-case">{open ? "hide" : "show"}</span>
      </button>
      {open && (
        <Card>
          <CardHeader
            title="Your definitions beat AI guesses"
            subtitle="Terms matching column names (spelling variants included) are used by the agents verbatim and shown in column tooltips."
            right={
              <>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".csv,.xlsx,.xls,.txt"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0])}
                />
                <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={busy}>
                  <Upload className="h-3.5 w-3.5" /> Upload codebook
                </Button>
              </>
            }
          />
          <CardBody>
            {entries.length > 0 && (
              <div className="mb-3 space-y-1.5">
                {entries.map((e) => (
                  <div
                    key={e.term}
                    className="flex items-start justify-between gap-3 rounded-xl border border-edge bg-panel-2 px-3.5 py-2"
                  >
                    <div className="min-w-0 text-xs">
                      <span className="font-semibold">{e.term}</span>
                      <span className="text-ink-dim"> - {e.definition}</span>
                    </div>
                    <button
                      onClick={() =>
                        api.deleteGlossary(projectId, e.term).then((r) => setEntries(r.entries))
                      }
                      className="shrink-0 text-ink-dim/60 transition-colors hover:text-bad"
                      title="Remove this definition"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                placeholder="column / term"
                className="w-40 rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-xs outline-none focus:border-accent"
              />
              <input
                value={definition}
                onChange={(e) => setDefinition(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && add()}
                placeholder="what it actually means"
                className="min-w-52 flex-1 rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-xs outline-none focus:border-accent"
              />
              <Button size="sm" onClick={add} disabled={busy || !term.trim() || !definition.trim()}>
                <Plus className="h-3.5 w-3.5" /> Add
              </Button>
            </div>
          </CardBody>
        </Card>
      )}
    </section>
  );
}

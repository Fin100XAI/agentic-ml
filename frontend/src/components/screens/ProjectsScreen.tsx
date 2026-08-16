// Project list: the top-level container. Each project holds its own datasets,
// analyses, models and activity trail.
import { useEffect, useState } from "react";
import { FolderOpen, FolderPlus, Layers } from "lucide-react";
import { api } from "../../api/client";
import type { Project } from "../../types";
import { Badge, Button, Card, CardBody } from "../ui";

export function ProjectsScreen({ onOpen }: { onOpen: (project: Project) => void }) {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    api.listProjects().then((r) => setProjects(r.projects)).catch(() => setProjects([]));
  useEffect(() => {
    refresh();
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const proj = await api.createProject(name, description);
      setCreating(false);
      setName("");
      setDescription("");
      onOpen(proj);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold">Your projects</h2>
        <p className="mt-1 text-sm text-ink-dim">
          A project keeps related datasets, analyses and their full audit trail together.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {(projects ?? []).map((p) => (
          <button
            key={p.id}
            onClick={() => onOpen(p)}
            className="rounded-2xl border border-edge bg-panel p-5 text-left backdrop-blur-xl transition-all hover:border-accent/50 hover:shadow-lg hover:shadow-accent/5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2">
                <FolderOpen className="h-4 w-4 shrink-0 text-accent" />
                <span className="truncate text-sm font-semibold">{p.name}</span>
              </span>
              <Badge tone="neutral">
                {p.n_runs ?? 0} run{(p.n_runs ?? 0) !== 1 ? "s" : ""}
              </Badge>
            </div>
            {p.description && (
              <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-ink-dim">{p.description}</p>
            )}
            <p className="mt-2 flex items-center gap-1.5 text-[11px] text-ink-dim">
              <Layers className="h-3 w-3" /> {p.n_datasets ?? 0} dataset{(p.n_datasets ?? 0) !== 1 ? "s" : ""}
              {p.last_run_at && <span>· last activity {p.last_run_at.slice(0, 10)}</span>}
            </p>
          </button>
        ))}

        {/* Create card */}
        {creating ? (
          <Card className="border-accent/40">
            <CardBody>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && create()}
                placeholder="Project name"
                className="w-full rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-sm outline-none focus:border-accent"
              />
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && create()}
                placeholder="What is this project about? (optional)"
                className="mt-2 w-full rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-xs outline-none focus:border-accent"
              />
              <div className="mt-3 flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setCreating(false)} disabled={busy}>
                  Cancel
                </Button>
                <Button size="sm" onClick={create} disabled={busy || !name.trim()}>
                  Create & open
                </Button>
              </div>
            </CardBody>
          </Card>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className="flex min-h-28 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-edge p-5 text-ink-dim transition-colors hover:border-accent/50 hover:text-accent"
          >
            <FolderPlus className="h-6 w-6" />
            <span className="text-sm font-medium">New project</span>
          </button>
        )}
      </div>

      {projects !== null && projects.length === 0 && !creating && (
        <p className="text-center text-xs text-ink-dim">
          No projects yet - create one to get started.
        </p>
      )}
    </div>
  );
}

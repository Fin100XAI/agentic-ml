// Project list: the top-level container. Each project holds its own datasets,
// analyses, models and activity trail. Presented as fluid glass tiles with
// an expressive gradient New-project tile.
import { useEffect, useState } from "react";
import { ArrowRight, FolderOpen, Layers, Plus, Sparkles } from "lucide-react";
import { api } from "../../api/client";
import type { Project } from "../../types";
import { Badge, Button, Card, CardBody } from "../ui";

const GRADIENT = "bg-[linear-gradient(100deg,#45e0c8,#6e8bff_55%,#b98cff)]";
// Tile icons rotate through the accent trio.
const TILE_TINTS = [
  "bg-rs-teal/10 text-rs-teal ring-rs-teal/25",
  "bg-accent/10 text-accent ring-accent/25",
  "bg-rs-violet/10 text-rs-violet ring-rs-violet/25",
];

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
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="pt-4 text-center">
        <p className="animate-rise text-[11px] font-bold uppercase tracking-[0.22em] text-accent">
          Your workspace
        </p>
        <h2 className="animate-rise mx-auto mt-3 max-w-2xl text-balance text-3xl font-extrabold leading-tight tracking-tight [animation-delay:60ms] md:text-4xl">
          Every dataset becomes{" "}
          <span className={`${GRADIENT} bg-clip-text text-transparent`}>
            a decision you can defend.
          </span>
        </h2>
        <p className="animate-rise mx-auto mt-3 max-w-xl text-sm leading-relaxed text-ink-dim [animation-delay:120ms]">
          A project keeps related datasets, analyses, models and their full
          audit trail together. Open one - or start fresh.
        </p>
      </div>

      <div className="animate-rise grid grid-cols-1 gap-4 [animation-delay:200ms] sm:grid-cols-2 lg:grid-cols-3">
        {(projects ?? []).map((p, i) => (
          <button
            key={p.id}
            onClick={() => onOpen(p)}
            className="tile glass group rounded-2xl border border-edge p-5 text-left"
          >
            <div className="flex items-center justify-between gap-2">
              <span className={`tile-icon inline-flex rounded-xl p-2 ring-1 ring-inset ${TILE_TINTS[i % 3]}`}>
                <FolderOpen className="h-4 w-4" />
              </span>
              <Badge tone="neutral">
                {p.n_runs ?? 0} run{(p.n_runs ?? 0) !== 1 ? "s" : ""}
              </Badge>
            </div>
            <p className="mt-3 truncate text-sm font-bold">{p.name}</p>
            {p.description && (
              <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-dim">{p.description}</p>
            )}
            <p className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-dim">
              <Layers className="h-3 w-3" /> {p.n_datasets ?? 0} dataset{(p.n_datasets ?? 0) !== 1 ? "s" : ""}
              {p.last_run_at && <span>· active {p.last_run_at.slice(0, 10)}</span>}
              <ArrowRight className="ml-auto h-3.5 w-3.5 text-ink-dim transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-accent" />
            </p>
          </button>
        ))}

        {/* Create tile: gradient ring, glass core, fluid icon */}
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
            className={`tile rounded-2xl ${GRADIENT} p-px text-left`}
          >
            <span className="glass flex h-full min-h-36 flex-col items-start justify-between rounded-[15px] bg-surface/90 p-5">
              <span className={`tile-icon inline-flex rounded-full ${GRADIENT} p-2 text-[#07080c]`}>
                <Plus className="h-4 w-4" strokeWidth={3} />
              </span>
              <span>
                <span className="flex items-center gap-1.5 text-sm font-bold">
                  New project <Sparkles className="h-3.5 w-3.5 text-rs-teal" />
                </span>
                <span className="mt-1 block text-xs leading-relaxed text-ink-dim">
                  Upload a file - first findings in minutes, every step approved by you.
                </span>
              </span>
            </span>
          </button>
        )}
      </div>

      {projects !== null && projects.length === 0 && !creating && (
        <p className="text-center text-xs text-ink-dim">
          Nothing here yet - your first project is one file away.
        </p>
      )}
    </div>
  );
}

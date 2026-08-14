import { useEffect, useState } from "react";
import { BrainCircuit, Check } from "lucide-react";
import { api } from "./api/client";
import { WireDiagram } from "./components/WireDiagram";
import { ConfigureScreen } from "./components/screens/ConfigureScreen";
import { EdaScreen } from "./components/screens/EdaScreen";
import { ResultsScreen } from "./components/screens/ResultsScreen";
import { UploadScreen } from "./components/screens/UploadScreen";
import { Badge } from "./components/ui";
import type { ModelInfo, Run } from "./types";

type Screen = "upload" | "eda" | "configure" | "results";

const STEPS: { key: Screen; label: string }[] = [
  { key: "upload", label: "Upload" },
  { key: "eda", label: "EDA review" },
  { key: "configure", label: "Model & params" },
  { key: "results", label: "Results" },
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("upload");
  const [run, setRun] = useState<Run | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    api.listModels().then((r) => setModels(r.models)).catch(() => {});
    api.health().then((h) => setLlmEnabled(h.llm_enabled)).catch(() => setLlmEnabled(null));
  }, []);

  async function guard<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const handleUpload = (file: File, question: string) =>
    guard(async () => {
      const ds = await api.uploadDataset(file);
      const r = await api.startRun(ds.dataset_id, question);
      setRun(r);
      if (r.error) setError(r.error);
      else setScreen("eda");
    });

  const handleApproveEda = (comment: string) =>
    guard(async () => {
      if (!run) return;
      const r = await api.approveEda(run.id, comment);
      setRun(r);
      if (r.error) setError(r.error);
      else setScreen("configure");
    });

  const handleRunModel = (config: {
    model_key: string;
    hyperparams: Record<string, unknown>;
    target: string | null;
    time_column: string | null;
  }) =>
    guard(async () => {
      if (!run) return;
      let r = await api.approveConfig(run.id, { ...config, features: null });
      setRun(r);
      r = await api.execute(run.id);
      setRun(r);
      if (r.error) setError(r.error);
      else setScreen("results");
    });

  const stepIndex = STEPS.findIndex((s) => s.key === screen);

  return (
    <div className="min-h-full">
      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-edge bg-surface/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2.5">
            <BrainCircuit className="h-6 w-6 text-accent" />
            <div>
              <h1 className="text-sm font-semibold leading-tight">Agentic ML Workbench</h1>
              <p className="text-[11px] leading-tight text-ink-dim">
                human-in-the-loop model pipeline
              </p>
            </div>
          </div>

          {/* Stepper */}
          <nav className="hidden items-center gap-1 md:flex">
            {STEPS.map((s, i) => (
              <div key={s.key} className="flex items-center gap-1">
                {i > 0 && <div className="h-px w-8 bg-edge" />}
                <div
                  className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs ${
                    i === stepIndex
                      ? "bg-accent-soft font-medium text-accent"
                      : i < stepIndex
                        ? "text-good"
                        : "text-ink-dim"
                  }`}
                >
                  {i < stepIndex ? (
                    <Check className="h-3 w-3" />
                  ) : (
                    <span className="text-[10px]">{i + 1}</span>
                  )}
                  {s.label}
                </div>
              </div>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {llmEnabled === null ? (
              <Badge tone="bad">backend offline?</Badge>
            ) : llmEnabled ? (
              <Badge tone="accent">Claude connected</Badge>
            ) : (
              <Badge tone="warn">heuristic mode (no API key)</Badge>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        {/* Wire diagram of decisions */}
        {run && run.decisions.length > 0 && (
          <div className="mb-6 overflow-hidden rounded-xl border border-edge bg-panel/50">
            <div className="flex items-center justify-between border-b border-edge px-4 py-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-dim">
                Decision flow
              </span>
              <span className="text-[11px] text-ink-dim">
                {run.filename} · run {run.id}
              </span>
            </div>
            <WireDiagram decisions={run.decisions} />
          </div>
        )}

        {error && (
          <div className="mb-6 rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
            {error}
          </div>
        )}

        {screen === "upload" && <UploadScreen onSubmit={handleUpload} busy={busy} />}

        {screen === "eda" && run?.profile && run.eda && (
          <EdaScreen
            profile={run.profile}
            eda={run.eda}
            question={run.question}
            onApprove={handleApproveEda}
            busy={busy}
          />
        )}

        {screen === "configure" && run?.profile && run.recommendation && (
          <ConfigureScreen
            profile={run.profile}
            recommendation={run.recommendation}
            models={models}
            onRun={handleRunModel}
            busy={busy}
          />
        )}

        {screen === "results" && run?.result && (
          <ResultsScreen
            run={run}
            result={run.result}
            interpretation={run.interpretation}
            onTuneAgain={() => setScreen("configure")}
            onStartOver={() => {
              setRun(null);
              setError(null);
              setScreen("upload");
            }}
          />
        )}
      </main>
    </div>
  );
}

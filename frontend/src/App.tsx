import { useCallback, useEffect, useState } from "react";
import { Bot, BrainCircuit, Check, Home } from "lucide-react";
import { api } from "./api/client";
import { AgentLogDrawer } from "./components/AgentLogDrawer";
import { AutotuneModal } from "./components/AutotuneModal";
import { Timeline } from "./components/Timeline";
import { eta } from "./lib/eta";
import { CompareScreen } from "./components/screens/CompareScreen";
import { ConfigureScreen } from "./components/screens/ConfigureScreen";
import { EdaScreen } from "./components/screens/EdaScreen";
import { HomeScreen } from "./components/screens/HomeScreen";
import { InsightsScreen } from "./components/screens/InsightsScreen";
import { ReportScreen } from "./components/screens/ReportScreen";
import { ResultsScreen } from "./components/screens/ResultsScreen";
import { UploadScreen } from "./components/screens/UploadScreen";
import { Badge } from "./components/ui";
import type { ModelInfo, Run, RunSummary } from "./types";

type Screen = "home" | "upload" | "eda" | "configure" | "results" | "compare" | "report";

const STEPS: { key: Screen; label: string }[] = [
  { key: "upload", label: "Upload" },
  { key: "eda", label: "Explore" },
  { key: "configure", label: "Model" },
  { key: "results", label: "Results" },
];

const GUIDE: Record<Screen, string> = {
  home: "",
  upload: "Step 1 - Pick any CSV file. The agents will figure out what's inside.",
  eda: "Step 2 - Review what the EDA agent found, tell it what you want to learn, then approve.",
  configure:
    "Step 3 - The agent recommends an analysis method and settings computed from your data. Approve, tweak, or compare every method at once.",
  results:
    "Step 4 - Your decision brief: findings, recommended actions, and how much to trust them. The model details live in the appendix.",
  compare:
    "Step 4 - Every method ranked on your data. Generate insights with the winner, or tune any of them.",
  report: "The full report - print it, save it as PDF, or download the markdown.",
};

// Map a run's backend stage to the screen that shows it.
function screenForStage(stage: string): Screen {
  switch (stage) {
    case "eda":
      return "eda";
    case "recommend":
    case "configure":
      return "configure";
    case "execute":
    case "interpret":
      return "results";
    case "compare":
      return "compare";
    default:
      return "upload";
  }
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [run, setRun] = useState<Run | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [recentRuns, setRecentRuns] = useState<RunSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("Working…");
  const [error, setError] = useState<string | null>(null);
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const [preferredModel, setPreferredModel] = useState<string | undefined>(undefined);
  const [uploadStage, setUploadStage] = useState<"uploading" | "profiling" | "analyzing" | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [tuneOpen, setTuneOpen] = useState(false);
  const [tuneRunning, setTuneRunning] = useState(false);

  const refreshRuns = useCallback(() => {
    api.listRuns().then((r) => setRecentRuns(r.runs)).catch(() => {});
  }, []);

  useEffect(() => {
    const checkHealth = () =>
      api.health().then((h) => setLlmEnabled(h.llm_enabled)).catch(() => setLlmEnabled(null));
    const loadModels = () =>
      api.listModels().then((r) => setModels(r.models)).catch(() => {});

    checkHealth();
    loadModels();
    refreshRuns();

    // Re-poll so a transient backend restart doesn't leave a stale "offline" badge.
    const timer = setInterval(() => {
      checkHealth();
      // Models list is static per backend; refetch only if the first load failed.
      setModels((m) => {
        if (m.length === 0) loadModels();
        return m;
      });
    }, 10_000);
    return () => clearInterval(timer);
  }, [refreshRuns]);

  async function guard<T>(label: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setBusyLabel(label);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      refreshRuns();
    }
  }

  const handleUpload = (file: File, question: string) =>
    guard("Analyzing…", async () => {
      setUploadStage("uploading");
      const ds = await api.uploadDataset(file);
      setUploadStage("profiling");
      let r = await api.startRun(ds.dataset_id, question);
      setRun(r);
      if (r.error) {
        setError(r.error);
        setUploadStage(null);
        return;
      }
      setUploadStage("analyzing");
      r = await api.runEda(r.id);
      setRun(r);
      setUploadStage(null);
      if (r.error) setError(r.error);
      else setScreen("eda");
    });

  const handleApproveEda = (comment: string) =>
    guard("Recommendation agent thinking…", async () => {
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
    guard(`Training & evaluating… (${eta("train", run?.profile?.n_rows ?? 0, true)})`, async () => {
      if (!run) return;
      let r = await api.approveConfig(run.id, { ...config, features: null });
      setRun(r);
      r = await api.execute(run.id);
      setRun(r);
      if (r.error) setError(r.error);
      else setScreen("results");
    });

  const handleCompare = (target: string | null, time_column: string | null) =>
    guard(
      `Training every model… (${eta("compare", run?.profile?.n_rows ?? 0, true)})`,
      async () => {
        if (!run) return;
        const r = await api.compare(run.id, target, time_column);
        setRun(r);
        if (r.error) setError(r.error);
        else setScreen("compare");
      },
    );

  const handleAutotune = async (target: string | null, time_column: string | null) => {
    if (!run) return;
    setTuneOpen(true);
    setTuneRunning(true);
    setError(null);
    try {
      const r = await api.autotune(run.id, target, time_column);
      setRun(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setTuneOpen(false);
    } finally {
      setTuneRunning(false);
      refreshRuns();
    }
  };

  const handleResume = (id: string) =>
    guard("Loading analysis…", async () => {
      const r = await api.getRun(id);
      setRun(r);
      setScreen(screenForStage(r.stage));
    });

  const goHome = () => {
    setScreen("home");
    setError(null);
    refreshRuns();
  };

  const startOver = () => {
    setRun(null);
    setError(null);
    setPreferredModel(undefined);
    setScreen("upload");
  };

  const stepIndex = STEPS.findIndex(
    (s) => s.key === (screen === "compare" || screen === "report" ? "results" : screen),
  );

  return (
    <div className="min-h-full">
      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-edge bg-white/55 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <button className="flex items-center gap-2.5 text-left" onClick={goHome}>
            <BrainCircuit className="h-6 w-6 text-accent" />
            <div>
              <h1 className="text-sm font-semibold leading-tight">Agentic ML Workbench</h1>
              <p className="text-[11px] leading-tight text-ink-dim">
                agents propose · you approve · models run
              </p>
            </div>
          </button>

          {/* Stepper (hidden on home) */}
          {screen !== "home" && (
            <nav className="hidden items-center gap-1 md:flex">
              <button
                onClick={goHome}
                className="mr-2 flex items-center gap-1 rounded-full px-2.5 py-1 text-xs text-ink-dim transition-colors hover:text-ink"
              >
                <Home className="h-3 w-3" /> Home
              </button>
              {STEPS.map((s, i) => (
                <div key={s.key} className="flex items-center gap-1">
                  {i > 0 && <div className="h-px w-6 bg-edge" />}
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
          )}

          <div className="flex items-center gap-2">
            {run && (run.agent_log?.length ?? 0) > 0 && (
              <button
                onClick={() => setLogOpen(true)}
                className="flex items-center gap-1.5 rounded-full border border-edge bg-panel-2 px-3 py-1 text-xs font-medium text-ink-dim backdrop-blur transition-colors hover:border-accent/40 hover:text-accent"
              >
                <Bot className="h-3.5 w-3.5" /> Agent activity
                <span className="rounded-full bg-accent-soft px-1.5 text-[10px] font-semibold text-accent">
                  {run.agent_log?.length}
                </span>
              </button>
            )}
            {llmEnabled === null ? (
              <Badge tone="bad">backend offline?</Badge>
            ) : llmEnabled ? (
              <Badge tone="accent">Claude connected</Badge>
            ) : (
              <Badge tone="warn">heuristic mode (no API key)</Badge>
            )}
          </div>
        </div>

        {/* Guide bar */}
        {screen !== "home" && GUIDE[screen] && (
          <div className="border-t border-edge/60 bg-white/35">
            <div className="mx-auto max-w-7xl px-6 py-1.5 text-[11px] text-ink-dim">
              {GUIDE[screen]}
            </div>
          </div>
        )}
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        {/* Compact decision timeline */}
        {screen !== "home" && run && run.decisions.length > 0 && (
          <div className="mb-6 rounded-xl border border-edge bg-panel backdrop-blur-xl">
            <div className="flex items-center justify-between border-b border-edge/60 px-4 py-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                Decision trail
              </span>
              <span className="text-[10px] text-ink-dim">
                {run.filename} · run {run.id}
              </span>
            </div>
            <Timeline decisions={run.decisions} />
          </div>
        )}

        {error && (
          <div className="mb-6 rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
            {error}
          </div>
        )}

        {screen === "home" && (
          <HomeScreen
            models={models}
            recentRuns={recentRuns}
            onStart={startOver}
            onResume={handleResume}
          />
        )}

        {screen === "upload" && (
          <UploadScreen onSubmit={handleUpload} busy={busy} stage={uploadStage} />
        )}

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
            initialModelKey={preferredModel}
            onRun={handleRunModel}
            onCompare={handleCompare}
            onAutotune={handleAutotune}
            onChangeDirection={() => setScreen("eda")}
            busy={busy}
            busyLabel={busyLabel}
          />
        )}

        {screen === "report" && run && (
          <ReportScreen run={run} onBack={() => setScreen(run.insights ? "results" : "home")} />
        )}

        {screen === "results" &&
          run?.result &&
          (run.insights ? (
            <InsightsScreen
              run={run}
              insights={run.insights}
              result={run.result}
              interpretation={run.interpretation}
              onTuneAgain={() => setScreen("configure")}
              onStartOver={startOver}
              onViewReport={() => setScreen("report")}
            />
          ) : (
            <ResultsScreen
              run={run}
              result={run.result}
              interpretation={run.interpretation}
              onTuneAgain={() => setScreen("configure")}
              onStartOver={startOver}
            />
          ))}

        {screen === "compare" && run?.comparison && (
          <CompareScreen
            run={run}
            comparison={run.comparison}
            onTuneModel={(key) => {
              setPreferredModel(key);
              setScreen("configure");
            }}
            onUseWinner={() => {
              const comp = run.comparison;
              const winner = comp?.results.find((r) => r.model_key === comp.best_model);
              if (!winner || !comp) return;
              handleRunModel({
                model_key: winner.model_key,
                hyperparams: winner.hyperparams,
                target: comp.target,
                time_column: comp.time_column,
              });
            }}
            onStartOver={startOver}
            busy={busy}
            busyLabel={busyLabel}
          />
        )}
      </main>

      <AgentLogDrawer
        entries={run?.agent_log ?? []}
        open={logOpen}
        onClose={() => setLogOpen(false)}
      />

      <AutotuneModal
        open={tuneOpen}
        running={tuneRunning}
        etaText={eta("autotune", run?.profile?.n_rows ?? 0, true)}
        result={run?.autotune ?? null}
        onClose={() => setTuneOpen(false)}
        onApply={() => setTuneOpen(false)}
      />
    </div>
  );
}

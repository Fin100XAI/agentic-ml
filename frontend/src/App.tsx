import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, Bot, BrainCircuit, Check, Home, ScrollText } from "lucide-react";
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
import { AboutScreen } from "./components/screens/AboutScreen";
import { AskScreen } from "./components/screens/AskScreen";
import { ActivityScreen } from "./components/screens/ActivityScreen";
import { ResultsScreen } from "./components/screens/ResultsScreen";
import { UploadScreen } from "./components/screens/UploadScreen";
import { Badge, Button, Card, CardBody } from "./components/ui";
import { AssemblyModal } from "./components/AssemblyModal";
import { ColumnReviewModal } from "./components/ColumnReviewModal";
import { BriefingView } from "./components/screens/BriefingView";
import { PiiReviewModal } from "./components/PiiReviewModal";
import { ProjectsScreen } from "./components/screens/ProjectsScreen";
import { RemediationModal } from "./components/RemediationModal";
import type { AssemblyProposal, JoinSuggestion, ModelInfo, PiiFinding, Project, RegistryEntry, Run, RunSummary, SheetInfo } from "./types";

type Screen = "projects" | "home" | "upload" | "eda" | "configure" | "results" | "compare" | "report" | "activity" | "about" | "ask";

const STEPS: { key: Screen; label: string }[] = [
  { key: "upload", label: "Upload" },
  { key: "eda", label: "Explore" },
  { key: "configure", label: "Model" },
  { key: "results", label: "Results" },
];

const GUIDE: Record<Screen, string> = {
  projects: "",
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
  activity: "Every action in order - uploads, agent calls, approvals, training and exports.",
  about: "",
  ask: "Ask a direct question - the interpretation is shown before anything runs, and every answer carries its caveats.",
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

export default function Root() {
  // Unlisted read-only briefing route: #/brief/{runId} renders without any
  // analyst chrome. Everything else is the normal workbench.
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const briefMatch = hash.match(/^#\/brief\/([A-Za-z0-9]+)/);
  if (briefMatch) return <BriefingView runId={briefMatch[1]} />;
  return <App />;
}

function App() {
  const [screen, setScreen] = useState<Screen>("projects");
  const [project, setProject] = useState<Project | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [recentRuns, setRecentRuns] = useState<RunSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("Working…");
  const [error, setError] = useState<string | null>(null);
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const [llmOk, setLlmOk] = useState<boolean | null>(null);
  const [llmBannerDismissed, setLlmBannerDismissed] = useState(false);
  const [preferredModel, setPreferredModel] = useState<string | undefined>(undefined);
  const [retrainPrefill, setRetrainPrefill] = useState<{
    hyperparams: Record<string, unknown>;
    target: string | null;
  } | null>(null);
  const [uploadStage, setUploadStage] = useState<"uploading" | "profiling" | "analyzing" | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [tuneOpen, setTuneOpen] = useState(false);
  const [tuneRunning, setTuneRunning] = useState(false);
  const [misalignNote, setMisalignNote] = useState<string | null>(null);
  // Model-run failure: "data" = the data does not fit the chosen model
  // (retrying is futile - change the model or setup); "transient" = worth
  // one more attempt before changing anything.
  const [runFailure, setRunFailure] = useState<{ message: string; kind: "data" | "transient" } | null>(null);
  // Ask-your-data context + the direction-stage route offer (QUERY-PATH)
  const [askCtx, setAskCtx] = useState<{ datasetId: string; filename: string; question?: string } | null>(null);
  const [routeOffer, setRouteOffer] = useState<{
    runId: string; datasetId: string; filename: string; question: string;
    route: "direct_query" | "both"; reasoning: string;
  } | null>(null);
  const [sheetChoice, setSheetChoice] = useState<{
    file: File;
    question: string;
    sheets: SheetInfo[];
    join: JoinSuggestion | null;
    stack: { sheets: string[]; n_rows: number; note: string } | null;
  } | null>(null);
  const [columnReview, setColumnReview] = useState<{
    datasetId: string;
    question: string;
    columns: string[];
    piiStatus: string;
    piiFindings: PiiFinding[];
    filename: string;
  } | null>(null);
  const [piiReview, setPiiReview] = useState<{
    datasetId: string;
    filename: string;
    question: string;
    findings: PiiFinding[];
  } | null>(null);
  const [remediationRunId, setRemediationRunId] = useState<string | null>(null);
  const [assemblyChoice, setAssemblyChoice] = useState<{
    file: File;
    question: string;
    filename: string;
    proposals: AssemblyProposal[];
  } | null>(null);

  const refreshRuns = useCallback(() => {
    api.listRuns(project?.id).then((r) => setRecentRuns(r.runs)).catch(() => {});
  }, [project?.id]);

  useEffect(() => {
    const checkHealth = () =>
      api.health()
        .then((h) => {
          setLlmEnabled(h.llm_enabled);
          setLlmOk(h.llm_ok ?? null);
        })
        .catch(() => setLlmEnabled(null));
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

  // EDA step shared by the normal path and the remediation path.
  const continueToEda = async (runId: string) => {
    setUploadStage("analyzing");
    const r = await api.runEda(runId);
    setRun(r);
    setUploadStage(null);
    if (r.error) setError(r.error);
    else setScreen("eda");
  };

  // Post-upload continuation shared by the normal path and the PII review path.
  const runAnalysis = async (datasetId: string, question: string) => {
    setUploadStage("profiling");
    const r = await api.startRun(datasetId, question);
    setRun(r);
    if (r.error) {
      setError(r.error);
      setUploadStage(null);
      return;
    }
    if (r.remediation?.status === "pending" && r.remediation.proposals.length > 0) {
      // Health check found repairable issues: the human decides before EDA.
      setRemediationRunId(r.id);
      setUploadStage(null);
      return;
    }
    await continueToEda(r.id);
  };

  const handleRemediation = (acceptedIds: string[], skip: boolean) =>
    guard(skip ? "Continuing…" : "Applying fixes…", async () => {
      if (!remediationRunId) return;
      const r = await api.remediate(remediationRunId, acceptedIds, skip);
      setRun(r);
      setRemediationRunId(null);
      if (r.error) {
        setError(r.error);
        return;
      }
      await continueToEda(r.id);
    });

  const handleUpload = (
    file: File, question: string, sheet?: string, join?: JoinSuggestion,
    assembly?: object | "standalone", stack?: string[],
  ) =>
    guard("Analyzing…", async () => {
      setUploadStage("uploading");
      const ds = await api.uploadDataset(file, sheet, join, project?.id, assembly, stack);
      if (ds.needs_sheet_selection && ds.sheets) {
        // Workbook has several sheets: ask the human which one to analyze.
        setSheetChoice({
          file, question, sheets: ds.sheets,
          join: ds.join_suggestion ?? null,
          stack: ds.stack_suggestion ?? null,
        });
        setUploadStage(null);
        return;
      }
      if (ds.needs_assembly_decision && ds.assembly_proposals) {
        // Librarian: the file relates to existing project data - human decides.
        setAssemblyChoice({
          file, question, filename: ds.filename, proposals: ds.assembly_proposals,
        });
        setUploadStage(null);
        return;
      }
      // Column review: approve working names BEFORE any analysis or AI call.
      setColumnReview({
        datasetId: ds.dataset_id!,
        question,
        columns: ds.columns ?? [],
        piiStatus: ds.pii_status ?? "clean",
        piiFindings: ds.pii_findings ?? [],
        filename: ds.filename,
      });
      setUploadStage(null);
    });

  const handleColumnReview = (renames: Record<string, string>) =>
    guard("Applying column names…", async () => {
      if (!columnReview) return;
      const { datasetId, question } = columnReview;
      let piiStatus = columnReview.piiStatus;
      let findings = columnReview.piiFindings;
      if (Object.keys(renames).length > 0) {
        const r = await api.renameColumns(datasetId, renames);
        piiStatus = r.pii_status;
        findings = r.pii_findings;
      }
      setColumnReview(null);
      if (piiStatus === "pending" && findings.length) {
        // Personal data found: the human decides before ANY analysis or AI call.
        setPiiReview({ datasetId, filename: columnReview.filename, question, findings });
        return;
      }
      await runAnalysis(datasetId, question);
    });

  const handlePiiApprove = (actions: Record<string, string>) =>
    guard("Applying privacy screen…", async () => {
      if (!piiReview) return;
      const { datasetId, question } = piiReview;
      await api.piiReview(datasetId, actions);
      setPiiReview(null);
      await runAnalysis(datasetId, question);
    });

  const handleApproveEda = (comment: string) =>
    guard("Recommendation agent thinking…", async () => {
      if (!run) return;
      const r = await api.approveEda(run.id, comment);
      setRun(r);
      if (r.error) {
        setError(r.error);
        return;
      }
      // QUERY-PATH: a direct question gets the honest offer BEFORE model
      // training; model_needed behaves exactly as before.
      const align = r.recommendation?.alignment as
        | { aligned: boolean; note: string; route?: string; route_reasoning?: string }
        | undefined;
      if (align?.route === "direct_query" || align?.route === "both") {
        setRouteOffer({
          runId: r.id,
          datasetId: r.dataset_id,
          filename: r.filename,
          question: comment || r.question || "",
          route: align.route,
          reasoning: align.route_reasoning || "",
        });
        return;
      }
      setScreen("configure");
      // Agent flags questions the data cannot actually answer.
      if (align && !align.aligned) setMisalignNote(align.note || "The question may not match this dataset.");
    });

  const chooseRoute = (choice: "direct_query" | "model") => {
    if (!routeOffer) return;
    const offer = routeOffer;
    setRouteOffer(null);
    api.routeChoice(offer.runId, choice).catch(() => {});
    if (choice === "direct_query") {
      setAskCtx({
        datasetId: offer.datasetId,
        filename: offer.filename,
        question: offer.question || run?.question || "",
      });
      setScreen("ask");
    } else {
      setScreen("configure");
    }
  };

  // Data-shape errors carry these plain-language markers from the engine;
  // anything else is treated as re-attemptable.
  const DATA_ERROR =
    /requires|too few|too short|not enough|no usable|missing columns|has different columns|numeric values to model|refusing to train|excluded by your leakage|cannot|unable to/i;
  const classifyRunError = (msg: string): "data" | "transient" =>
    DATA_ERROR.test(msg) ? "data" : "transient";

  const handleRetryRun = () =>
    guard(`Training & evaluating… (${eta("train", run?.profile?.n_rows ?? 0, true)})`, async () => {
      if (!run) return;
      setRunFailure(null);
      const r = await api.execute(run.id);
      setRun(r);
      if (r.error) setRunFailure({ message: r.error, kind: classifyRunError(r.error) });
      else setScreen("results");
    });

  const handleChangeModel = () => {
    setRunFailure(null);
    setError(null);
    setScreen("configure");
  };

  const handleRunModel = (config: {
    model_key: string;
    hyperparams: Record<string, unknown>;
    target: string | null;
    time_column: string | null;
    feature_ids?: string[];
    excluded_columns?: string[];
    group_column?: string | null;
    group_agg?: string;
    regressors?: string[];
  }) =>
    guard(`Training & evaluating… (${eta("train", run?.profile?.n_rows ?? 0, true)})`, async () => {
      if (!run) return;
      const { regressors, ...rest } = config;
      let r = await api.approveConfig(run.id, {
        ...rest,
        features: regressors && regressors.length > 0 ? regressors : null,
      });
      setRun(r);
      r = await api.execute(run.id);
      setRun(r);
      if (r.error) setRunFailure({ message: r.error, kind: classifyRunError(r.error) });
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

  const handleAutotune = async (
    target: string | null,
    time_column: string | null,
    nCandidates?: number,
  ) => {
    if (!run) return;
    setTuneOpen(true);
    setTuneRunning(true);
    setError(null);
    try {
      const r = await api.autotune(run.id, target, time_column, nCandidates);
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
    setScreen(project ? "home" : "projects");
    setError(null);
    refreshRuns();
  };

  // Screen history for the back/forward buttons. Recorded by an effect, so
  // every existing navigation participates without touching its call site.
  const [past, setPast] = useState<Screen[]>([]);
  const [future, setFuture] = useState<Screen[]>([]);
  const prevScreenRef = useRef<Screen>(screen);
  const historyNavRef = useRef(false);
  useEffect(() => {
    const prev = prevScreenRef.current;
    if (prev === screen) return;
    if (historyNavRef.current) {
      historyNavRef.current = false;
    } else {
      setPast((p) => [...p.slice(-19), prev]);
      setFuture([]);
    }
    prevScreenRef.current = screen;
  }, [screen]);

  // A history entry is only usable if the state it needs still exists.
  const canShow = (s: Screen): boolean => {
    if (s === "eda" || s === "configure" || s === "results" || s === "compare" || s === "report") {
      return run !== null;
    }
    if (s === "home") return project !== null;
    if (s === "ask") return askCtx !== null;
    return true;
  };
  const goBack = () => {
    const stack = [...past];
    let target: Screen | undefined;
    while (stack.length) {
      const cand = stack.pop()!;
      if (canShow(cand)) { target = cand; break; }
    }
    if (target === undefined) return;
    historyNavRef.current = true;
    setPast(stack);
    setFuture((f) => [screen, ...f]);
    setScreen(target);
    setError(null);
  };
  const goForward = () => {
    const stack = [...future];
    let target: Screen | undefined;
    while (stack.length) {
      const cand = stack.shift()!;
      if (canShow(cand)) { target = cand; break; }
    }
    if (target === undefined) return;
    historyNavRef.current = true;
    setFuture(stack);
    setPast((p) => [...p, screen]);
    setScreen(target);
    setError(null);
  };

  const handleOpenRetrainRun = (
    runId: string,
    prefill: { model_key: string; hyperparams: Record<string, unknown>; target: string | null },
  ) =>
    guard("Opening the retrain run…", async () => {
      const r = await api.getRun(runId);
      setRun(r);
      setPreferredModel(prefill.model_key);
      setRetrainPrefill({ hyperparams: prefill.hyperparams, target: prefill.target });
      setScreen("configure");
    });

  const handleRetrain = (entry: RegistryEntry, datasetId: string) =>
    guard("Preparing the retrain…", async () => {
      const r = await api.retrainModel(entry.model_id, entry.version, datasetId);
      setRun(r.run);
      setPreferredModel(r.prefill.model_key);
      setRetrainPrefill({ hyperparams: r.prefill.hyperparams, target: r.prefill.target });
      setScreen("configure");
    });

  const openProject = (p: Project) => {
    setProject(p);
    setRun(null);
    setError(null);
    setScreen("home");
    api.listRuns(p.id).then((r) => setRecentRuns(r.runs)).catch(() => {});
  };

  const startOver = () => {
    setRun(null);
    setError(null);
    setPreferredModel(undefined);
    setRetrainPrefill(null);
    setScreen("upload");
  };

  const stepIndex = STEPS.findIndex(
    (s) => s.key === (screen === "compare" || screen === "report" ? "results" : screen),
  );

  return (
    <div className="min-h-full">
      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-edge bg-white shadow-sm shadow-slate-900/5">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-2.5">
            <button className="flex shrink-0 items-center gap-2.5 text-left" onClick={goHome}>
              <BrainCircuit className="h-6 w-6 shrink-0 text-accent" />
              <div>
                <h1 className="whitespace-nowrap text-sm font-semibold leading-tight">
                  Agentic ML Workbench
                </h1>
                <p className="hidden whitespace-nowrap text-[11px] leading-tight text-ink-dim lg:block">
                  agents propose · you approve · models run
                </p>
              </div>
            </button>
            {/* Back / forward / home - always visible */}
            <span className="ml-1 flex items-center gap-1">
              <button
                onClick={goBack}
                disabled={!past.some(canShow)}
                title="Back"
                className="rounded-full border border-edge bg-panel-2 p-1.5 text-ink-dim transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-30 disabled:hover:border-edge disabled:hover:text-ink-dim"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={goForward}
                disabled={!future.some(canShow)}
                title="Forward"
                className="rounded-full border border-edge bg-panel-2 p-1.5 text-ink-dim transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-30 disabled:hover:border-edge disabled:hover:text-ink-dim"
              >
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
              {project && screen !== "home" && screen !== "projects" && (
                <button
                  onClick={goHome}
                  title="Project home"
                  className="rounded-full border border-edge bg-panel-2 p-1.5 text-ink-dim transition-colors hover:border-accent/40 hover:text-accent"
                >
                  <Home className="h-3.5 w-3.5" />
                </button>
              )}
            </span>
            {/* Project breadcrumb */}
            {project && screen !== "projects" && (
              <span className="hidden min-w-0 items-center gap-1 md:flex">
                <span className="text-ink-dim">/</span>
                <button
                  onClick={goHome}
                  className="max-w-32 truncate rounded-full border border-edge bg-panel-2 px-2.5 py-0.5 text-xs font-medium text-ink-dim transition-colors hover:border-accent/40 hover:text-accent xl:max-w-44"
                  title="Back to this project's dashboard"
                >
                  {project.name}
                </button>
              </span>
            )}
          </div>

          {/* Stepper: labels at wide widths, compact dots in between,
              nothing on narrow screens - it never fights the toolbars. */}
          {screen !== "home" && screen !== "projects" && screen !== "about" && screen !== "activity" && (
            <nav className="hidden shrink-0 items-center gap-1 lg:flex">
              {STEPS.map((s, i) => (
                <div key={s.key} className="flex items-center gap-1">
                  {i > 0 && <div className="h-px w-3 bg-edge xl:w-5" />}
                  <div
                    className={`flex items-center gap-1.5 rounded-full px-2 py-1 text-xs xl:px-2.5 ${
                      i === stepIndex
                        ? "bg-accent-soft font-medium text-accent"
                        : i < stepIndex
                          ? "text-good"
                          : "text-ink-dim"
                    }`}
                    title={s.label}
                  >
                    {i < stepIndex ? (
                      <Check className="h-3 w-3" />
                    ) : (
                      <span className="text-[10px]">{i + 1}</span>
                    )}
                    <span className="hidden xl:inline">{s.label}</span>
                  </div>
                </div>
              ))}
            </nav>
          )}

          {/* Right toolbar: labels collapse to icons below lg so nothing
              ever wraps or overlaps the brand and stepper. */}
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              onClick={() => setScreen(screen === "about" ? (project ? "home" : "projects") : "about")}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors lg:px-3 ${
                screen === "about"
                  ? "border-accent/40 bg-accent-soft/40 text-accent"
                  : "border-edge bg-panel-2 text-ink-dim hover:border-accent/40 hover:text-accent"
              }`}
              title="Guide: what this platform is, how it works, and why it can be trusted"
            >
              <BookOpen className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">Guide</span>
            </button>
            <button
              onClick={() => setScreen(screen === "activity" ? (run ? screenForStage(run.stage) : "home") : "activity")}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors lg:px-3 ${
                screen === "activity"
                  ? "border-accent/40 bg-accent-soft/40 text-accent"
                  : "border-edge bg-panel-2 text-ink-dim hover:border-accent/40 hover:text-accent"
              }`}
              title="Activity log: every action in order"
            >
              <ScrollText className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">Log</span>
            </button>
            {run && (run.agent_log?.length ?? 0) > 0 && (
              <button
                onClick={() => setLogOpen(true)}
                className="flex items-center gap-1.5 rounded-full border border-edge bg-panel-2 px-2.5 py-1 text-xs font-medium text-ink-dim transition-colors hover:border-accent/40 hover:text-accent lg:px-3"
                title="Agent activity for this analysis"
              >
                <Bot className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">Agent activity</span>
                <span className="rounded-full bg-accent-soft px-1.5 text-[10px] font-semibold text-accent">
                  {run.agent_log?.length}
                </span>
              </button>
            )}
            {llmEnabled === null ? (
              <span title="The backend is not responding">
                <Badge tone="bad">
                  <span className="hidden lg:inline">backend offline?</span>
                  <span className="lg:hidden">offline</span>
                </Badge>
              </span>
            ) : !llmEnabled ? (
              <span title="No API key configured - agents use rule-based fallbacks">
                <Badge tone="warn">
                  <span className="hidden lg:inline">heuristic mode (no API key)</span>
                  <span className="lg:hidden">heuristic</span>
                </Badge>
              </span>
            ) : llmOk === false ? (
              <span title="AI unreachable - agents use rule-based fallbacks">
                <Badge tone="warn">
                  <span className="hidden lg:inline">heuristic mode (AI unreachable)</span>
                  <span className="lg:hidden">heuristic</span>
                </Badge>
              </span>
            ) : (
              <span title="AI provider reachable">
                <Badge tone="accent">
                  <span className="hidden lg:inline">AI connected</span>
                  <span className="lg:hidden">AI</span>
                </Badge>
              </span>
            )}
          </div>
        </div>

        {/* Guide bar */}
        {screen !== "home" && GUIDE[screen] && (
          <div className="border-t border-edge/60 bg-panel-2">
            <div className="mx-auto max-w-7xl px-6 py-1.5 text-[11px] text-ink-dim">
              {GUIDE[screen]}
            </div>
          </div>
        )}
      </header>

      {/* Heuristic mode must be a visible state, never a silent one. */}
      {llmEnabled === true && llmOk === false && !llmBannerDismissed && (
        <div className="border-b border-warn/30 bg-warn/10">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-6 py-2 text-xs text-warn">
            <span className="font-medium">
              LLM unreachable - running in heuristic mode. Analyses still work; agent
              commentary uses rule-based fallbacks until the provider recovers.
            </span>
            <button
              onClick={() => setLlmBannerDismissed(true)}
              className="shrink-0 rounded-md px-2 py-0.5 font-semibold hover:bg-warn/10"
              title="Dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      <main className="mx-auto max-w-7xl px-6 py-6">
        {/* Compact decision timeline */}
        {screen !== "home" && run && run.decisions.length > 0 && (
          <div className="mb-6 rounded-xl border border-edge bg-panel shadow-sm">
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

        {screen === "projects" && <ProjectsScreen onOpen={openProject} />}

        {screen === "home" && (
          <HomeScreen
            recentRuns={recentRuns}
            projectName={project?.name}
            projectId={project?.id}
            onStart={startOver}
            onResume={handleResume}
            onRetrain={handleRetrain}
            onOpenRetrainRun={handleOpenRetrainRun}
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
            initialHyperparams={retrainPrefill?.hyperparams}
            initialTarget={retrainPrefill?.target}
            featureSuggestions={run.feature_suggestions}
            leakageFlags={run.leakage?.flags}
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

        {screen === "activity" && <ActivityScreen currentRunId={run?.id} projectId={project?.id} />}

        {screen === "about" && <AboutScreen onStart={project ? startOver : undefined} />}

        {screen === "ask" && askCtx && (
          <AskScreen
            datasetId={askCtx.datasetId}
            filename={askCtx.filename}
            initialQuestion={askCtx.question}
            onBack={goHome}
          />
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

      {/* Question/data misalignment warning */}
      {/* QUERY-PATH: the direction-stage route offer (rule 10 touch point a) */}
      {routeOffer && (
        <>
          <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" />
          <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 px-4">
            <Card className="border-accent/40 bg-white/95">
              <CardBody>
                <h3 className="text-sm font-semibold">
                  {routeOffer.route === "both"
                    ? "Part of this can be answered right now"
                    : "This question doesn't need AI model training"}
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-ink-dim">
                  {routeOffer.route === "both"
                    ? "The lookup part can be answered directly from your data this minute; the prediction part needs a trained model. You can do both - starting with the direct answer."
                    : "It can be answered directly from your data - no waiting for training, and the interpretation is shown before anything runs."}
                  {routeOffer.reasoning ? ` (${routeOffer.reasoning})` : ""}
                </p>
                <div className="mt-4 flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => chooseRoute("model")}>
                    {routeOffer.route === "both" ? "Train the model instead" : "Train a model anyway"}
                  </Button>
                  <Button size="sm" onClick={() => chooseRoute("direct_query")}>
                    Answer directly (no model training)
                  </Button>
                </div>
              </CardBody>
            </Card>
          </div>
        </>
      )}

      {/* Model-run failure: retry for transient problems, change the model
          when the data itself does not fit the chosen method. */}
      {runFailure && (
        <>
          <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" />
          <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 px-4">
            <Card className={runFailure.kind === "data" ? "border-warn/50 bg-white/95" : "border-bad/40 bg-white/95"}>
              <CardBody>
                <h3 className="text-sm font-semibold">
                  {runFailure.kind === "data"
                    ? "This data does not fit the chosen model"
                    : "The model run hit a problem"}
                </h3>
                <p className="mt-2 rounded-lg border border-edge bg-panel-2 px-3 py-2 text-xs leading-relaxed text-ink-dim">
                  {runFailure.message}
                </p>
                <p className="mt-2 text-xs leading-relaxed text-ink-dim">
                  {runFailure.kind === "data"
                    ? "Running it again would hit the same wall. Pick a different model or adjust the target, features or exclusions - your data and approvals are unchanged."
                    : "This can be a one-off. Try the run again; if it keeps failing, switch the model or adjust the settings."}
                </p>
                <div className="mt-4 flex justify-end gap-2">
                  {runFailure.kind === "data" ? (
                    <>
                      <Button variant="outline" size="sm" onClick={() => setRunFailure(null)}>
                        Close
                      </Button>
                      <Button size="sm" onClick={handleChangeModel}>
                        Choose a different model
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button variant="outline" size="sm" onClick={handleChangeModel}>
                        Change model or settings
                      </Button>
                      <Button size="sm" onClick={handleRetryRun} disabled={busy}>
                        Try again
                      </Button>
                    </>
                  )}
                </div>
              </CardBody>
            </Card>
          </div>
        </>
      )}

      {misalignNote && (
        <>
          <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" />
          <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2">
            <Card className="border-warn/50 bg-white/90">
              <CardBody>
                <h3 className="text-sm font-semibold">Your question may not match this data</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-dim">{misalignNote}</p>
                <div className="mt-4 flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setMisalignNote(null);
                      setScreen("eda");
                    }}
                  >
                    Revise the question
                  </Button>
                  <Button size="sm" onClick={() => setMisalignNote(null)}>
                    Proceed anyway
                  </Button>
                </div>
              </CardBody>
            </Card>
          </div>
        </>
      )}

      {/* Librarian: the new file relates to existing project data */}
      {assemblyChoice && (
        <AssemblyModal
          filename={assemblyChoice.filename}
          proposals={assemblyChoice.proposals}
          busy={busy}
          onChoose={(p) => {
            const { file, question } = assemblyChoice;
            setAssemblyChoice(null);
            handleUpload(file, question, undefined, undefined, {
              kind: p.kind,
              target_dataset_id: p.target_dataset_id,
              on_left: p.on_left,
              on_right: p.on_right,
            });
          }}
          onStandalone={() => {
            const { file, question } = assemblyChoice;
            setAssemblyChoice(null);
            handleUpload(file, question, undefined, undefined, "standalone");
          }}
        />
      )}

      {/* Data-fix review: repairable health issues found after profiling */}
      {remediationRunId && run?.remediation?.status === "pending" && (
        <RemediationModal
          proposals={run.remediation.proposals}
          generatedBy={run.remediation.generated_by}
          busy={busy}
          onApprove={(ids) => handleRemediation(ids, false)}
          onSkip={() => handleRemediation([], true)}
        />
      )}

      {/* Privacy screen: personal data found at upload */}
      {piiReview && (
        <PiiReviewModal
          filename={piiReview.filename}
          findings={piiReview.findings}
          busy={busy}
          onApprove={handlePiiApprove}
        />
      )}

      {/* Column review: approve working names before analysis */}
      {columnReview && (
        <ColumnReviewModal
          filename={columnReview.filename}
          columns={columnReview.columns}
          busy={busy}
          onContinue={handleColumnReview}
        />
      )}

      {/* Excel sheet picker */}
      {sheetChoice && (
        <>
          <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" />
          <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2">
            <Card className="bg-white/90">
              <CardBody>
                <h3 className="text-sm font-semibold">Which sheet should we analyze?</h3>
                <p className="mt-1 text-xs text-ink-dim">
                  {sheetChoice.file.name} has {sheetChoice.sheets.length} sheets. Pick one - or
                  combine them if the agent found a link.
                </p>
                {sheetChoice.stack && (
                  <button
                    onClick={() => {
                      const { file, question, stack } = sheetChoice;
                      setSheetChoice(null);
                      handleUpload(file, question, undefined, undefined, undefined, stack!.sheets);
                    }}
                    className="mt-3 w-full rounded-xl border border-accent/50 bg-accent-soft/40 px-4 py-3 text-left transition-all hover:border-accent"
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-accent">
                        Combine {sheetChoice.stack.sheets.length} sheets into one table
                      </span>
                      <span className="shrink-0 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
                        {sheetChoice.stack.n_rows.toLocaleString()} rows total
                      </span>
                    </span>
                    <span className="mt-1 block text-[11px] leading-snug text-ink-dim">
                      {sheetChoice.stack.note}
                    </span>
                  </button>
                )}
                {sheetChoice.join && (
                  <button
                    onClick={() => {
                      const { file, question, join } = sheetChoice;
                      setSheetChoice(null);
                      handleUpload(file, question, undefined, join!);
                    }}
                    className="mt-3 w-full rounded-xl border border-accent/50 bg-accent-soft/40 px-4 py-3 text-left transition-all hover:border-accent"
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-accent">
                        Combine '{sheetChoice.join.left}' + '{sheetChoice.join.right}'
                      </span>
                      <span className="shrink-0 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
                        agent suggestion
                      </span>
                    </span>
                    <span className="mt-1 block text-[11px] leading-snug text-ink-dim">
                      {sheetChoice.join.note}
                    </span>
                  </button>
                )}
                <div className="mt-3 space-y-2">
                  {sheetChoice.sheets.map((s) => (
                    <button
                      key={s.name}
                      onClick={() => {
                        const { file, question } = sheetChoice;
                        setSheetChoice(null);
                        handleUpload(file, question, s.name);
                      }}
                      className="flex w-full items-center justify-between rounded-xl border border-edge bg-panel-2 px-4 py-2.5 text-left transition-colors hover:border-accent/50"
                    >
                      <span className="min-w-0 truncate text-sm font-medium">{s.name}</span>
                      <span className="shrink-0 text-[11px] tabular-nums text-ink-dim">
                        {s.n_rows.toLocaleString()} rows × {s.n_cols} cols
                      </span>
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex justify-end">
                  <Button variant="ghost" size="sm" onClick={() => setSheetChoice(null)}>
                    Cancel
                  </Button>
                </div>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

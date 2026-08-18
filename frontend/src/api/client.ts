import type { ActivityEvent, ArtifactInfo, DataOverview, DomainsResponse, DriftResult, ExploreResponse, IntakeItem, IntakeRule, ModelInfo, PiiFinding, PlaceCheck, Project, QueryAnswer, QueryBrief, QueryPlanResponse, RegistryEntry, Run, RunDiffResult, RunSummary, SavedQuery, ScenarioMeta, ScenarioResult, ScoreResult, TextNumberProposal, UploadResponse } from "../types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () =>
    request<{
      status: string;
      llm_enabled: boolean;
      model: string;
      llm_ok?: boolean | null;
      llm_error?: string | null;
    }>("/health"),

  listProjects: () => request<{ projects: Project[] }>("/projects"),

  diffRuns: (runA: string, runB: string) =>
    request<RunDiffResult>("/runs/diff", json({ run_a: runA, run_b: runB })),

  getGlossary: (projectId: string) =>
    request<{ entries: { term: string; definition: string }[] }>(`/projects/${projectId}/glossary`),

  addGlossary: (projectId: string, entries: { term: string; definition: string }[]) =>
    request<{ added: number; entries: { term: string; definition: string }[] }>(
      `/projects/${projectId}/glossary`,
      json({ entries }),
    ),

  uploadGlossary: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ added: number; entries: { term: string; definition: string }[] }>(
      `/projects/${projectId}/glossary/upload`,
      { method: "POST", body: form },
    );
  },

  deleteGlossary: (projectId: string, term: string) =>
    request<{ entries: { term: string; definition: string }[] }>(
      `/projects/${projectId}/glossary/${encodeURIComponent(term)}`,
      { method: "DELETE" },
    ),

  getProjectModels: (projectId: string) =>
    request<{ models: RegistryEntry[] }>(`/projects/${projectId}/models`),

  getProjectDetail: (projectId: string) =>
    request<{ datasets: { id: string; filename: string; n_rows: number }[] }>(
      `/projects/${projectId}`,
    ),

  queryPlan: (datasetId: string, question: string, priorPlan?: object) =>
    request<QueryPlanResponse>(`/datasets/${datasetId}/query/plan`,
      json({ question, prior_plan: priorPlan ?? null })),

  queryRun: (datasetId: string, plan: object, question: string) =>
    request<QueryAnswer>(`/datasets/${datasetId}/query/run`, json({ plan, question })),

  routeChoice: (runId: string, choice: "direct_query" | "model") =>
    request<{ ok: boolean }>(`/runs/${runId}/route-choice`, json({ choice })),

  explore: (datasetId: string, lang = "en", focusColumns?: string[]) =>
    request<ExploreResponse>(
      `/datasets/${datasetId}/explore?lang=${encodeURIComponent(lang)}` +
      (focusColumns?.length ? `&focus=${encodeURIComponent(focusColumns.join("|"))}` : ""),
      { method: "POST" }),

  getDomains: (datasetId: string) =>
    request<DomainsResponse>(`/datasets/${datasetId}/domains`),

  refreshAllIndicators: (projectId: string) =>
    request<{ refreshed: { name: string; filename: string }[]; skipped: string[] }>(
      `/projects/${projectId}/indicators/refresh`, { method: "POST" }),

  datasetOverview: (datasetId: string) =>
    request<DataOverview>(`/datasets/${datasetId}/overview`),

  placeCheck: (datasetId: string) =>
    request<PlaceCheck>(`/datasets/${datasetId}/place-check`),

  numberCheck: (datasetId: string) =>
    request<{ columns: TextNumberProposal[] }>(`/datasets/${datasetId}/number-check`),

  fixNumbers: (datasetId: string, columns: string[]) =>
    request<{ ok: boolean; converted: number; numeric_columns_now: number }>(
      `/datasets/${datasetId}/fix-numbers`, json({ columns })),

  harmonizePlaces: (datasetId: string, column: string, mapping: Record<string, string>) =>
    request<{ ok: boolean; distinct_after: number }>(
      `/datasets/${datasetId}/harmonize`, json({ column, mapping })),

  createQueryBrief: (
    datasetId: string,
    items: { question: string; plan: object; headline?: string; meaning?: string }[],
    takeaway = "",
    title = "",
  ) =>
    request<{ brief_id: string; brief: QueryBrief; markdown: string }>(
      `/datasets/${datasetId}/query/brief`,
      json({ items, takeaway, title }),
    ),

  getQueryBrief: (briefId: string) => request<QueryBrief>(`/query-briefs/${briefId}`),

  saveIndicator: (datasetId: string, name: string, plan: object, question: string) =>
    request<SavedQuery>(`/datasets/${datasetId}/saved-queries`,
      json({ name, plan, question })),

  listIndicators: (projectId: string) =>
    request<{ saved_queries: SavedQuery[] }>(`/projects/${projectId}/saved-queries`),

  runIndicator: (sqId: string, datasetId?: string) =>
    request<{ saved_query: SavedQuery }>(`/saved-queries/${sqId}/run`,
      json(datasetId ? { dataset_id: datasetId } : {})),

  deleteIndicator: (sqId: string) =>
    request<{ ok: boolean }>(`/saved-queries/${sqId}`, { method: "DELETE" }),

  queryBriefFile: async (briefId: string, format: "markdown" | "pdf") => {
    const res = await fetch(`${BASE}/query-briefs/${briefId}/${format}`);
    if (!res.ok) throw new Error(res.statusText);
    return res.blob();
  },

  pathChoice: (datasetId: string, choice: "analytics" | "model") =>
    request<{ ok: boolean }>(`/datasets/${datasetId}/path-choice`, json({ choice })),

  // Downloads return files, not JSON - handled outside request<T>.
  queryExportCsv: async (datasetId: string, plan: object, question: string) => {
    const res = await fetch(`${BASE}/datasets/${datasetId}/query/export`,
      json({ plan, question }));
    if (!res.ok) throw new Error(res.statusText);
    return res.blob();
  },

  exploreExportMd: async (
    datasetId: string,
    items: { question: string; headline: string; meaning: string; sentences: string[]; table: object[] }[],
    synthesis: string,
  ) => {
    const res = await fetch(`${BASE}/datasets/${datasetId}/explore/export`,
      json({ items, synthesis }));
    if (!res.ok) throw new Error(res.statusText);
    return res.blob();
  },

  getIntake: (projectId: string) =>
    request<{ rules: IntakeRule[]; items: IntakeItem[] }>(`/projects/${projectId}/intake`),

  createIntakeRule: (
    projectId: string,
    body: { model_id: string; version: number; action: string; cadence: string; name?: string },
  ) => request<IntakeRule>(`/projects/${projectId}/intake-rules`, json(body)),

  deleteIntakeRule: (ruleId: string) =>
    request<{ deleted: string }>(`/intake-rules/${ruleId}`, { method: "DELETE" }),

  resolveIntake: (itemId: string, decision: "approve" | "decline") =>
    request<{ item: IntakeItem }>(`/intake/${itemId}/resolve`, json({ decision })),

  setThreshold: (modelId: string, version: number, threshold: number) =>
    request<{ threshold: number }>(`/models/${modelId}/${version}/threshold`, json({ threshold })),

  scenarioMeta: (modelId: string, version: number) =>
    request<ScenarioMeta>(`/models/${modelId}/${version}/scenario/meta`),

  runScenario: (modelId: string, version: number, perturbations: Record<string, number>) =>
    request<ScenarioResult>(`/models/${modelId}/${version}/scenario`, json({ perturbations })),

  scenarioCurve: (modelId: string, version: number, feature: string) =>
    request<{ feature: string; response: string; points: { x: number; y: number }[]; observed: [number, number] }>(
      `/models/${modelId}/${version}/scenario/curve`,
      json({ feature }),
    ),

  driftCheck: (modelId: string, version: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DriftResult>(`/models/${modelId}/${version}/drift`, {
      method: "POST",
      body: form,
    });
  },

  scoreModel: (modelId: string, version: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ScoreResult>(`/models/${modelId}/${version}/score`, {
      method: "POST",
      body: form,
    });
  },

  artifactDownloadUrl: (artifactId: string) => `${BASE}/artifacts/${artifactId}/download`,

  retrainModel: (modelId: string, version: number, datasetId: string) =>
    request<{ run: Run; prefill: { model_key: string; hyperparams: Record<string, unknown>; target: string | null } }>(
      `/models/${modelId}/${version}/retrain`,
      json({ dataset_id: datasetId }),
    ),

  createProject: (name: string, description = "") =>
    request<Project>("/projects", json({ name, description })),

  uploadDataset: (
    file: File, sheet?: string, join?: object, projectId?: string,
    assembly?: object | "standalone", stack?: string[],
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (sheet) form.append("sheet", sheet);
    if (join) form.append("join", JSON.stringify(join));
    if (stack) form.append("stack", JSON.stringify(stack));
    if (projectId) form.append("project_id", projectId);
    if (assembly) form.append("assembly", assembly === "standalone" ? "standalone" : JSON.stringify(assembly));
    return request<UploadResponse>("/datasets", { method: "POST", body: form });
  },

  renameColumns: (datasetId: string, renames: Record<string, string>) =>
    request<{ dataset_id: string; columns: string[]; pii_status: "pending" | "reviewed" | "clean"; pii_findings: PiiFinding[] }>(
      `/datasets/${datasetId}/rename`,
      json({ renames }),
    ),

  listModels: () => request<{ models: ModelInfo[] }>("/models"),

  startRun: (dataset_id: string, question: string) =>
    request<Run>("/runs", json({ dataset_id, question })),

  runEda: (id: string) => request<Run>(`/runs/${id}/eda`, { method: "POST" }),

  getRun: (id: string) => request<Run>(`/runs/${id}`),

  approveEda: (id: string, comment: string) =>
    request<Run>(`/runs/${id}/approve-eda`, json({ comment })),

  approveConfig: (
    id: string,
    body: {
      model_key: string;
      hyperparams: Record<string, unknown>;
      target: string | null;
      features: string[] | null;
      time_column: string | null;
      feature_ids?: string[] | null;
      excluded_columns?: string[] | null;
      group_column?: string | null;
      group_agg?: string;
    },
  ) => request<Run>(`/runs/${id}/approve-config`, json(body)),

  execute: (id: string) => request<Run>(`/runs/${id}/execute`, { method: "POST" }),

  compare: (id: string, target: string | null, time_column: string | null) =>
    request<Run>(`/runs/${id}/compare`, json({ target, time_column })),

  autotune: (id: string, target: string | null, time_column: string | null, n_candidates?: number) =>
    request<Run>(`/runs/${id}/autotune`, json({ target, time_column, n_candidates })),

  ask: (id: string, question: string, history: { q: string; a: string }[]) =>
    request<{ answer: string; generated_by: string }>(
      `/runs/${id}/ask`,
      json({ question, history }),
    ),

  listRuns: (projectId?: string) =>
    request<{ runs: RunSummary[] }>(`/runs${projectId ? `?project_id=${projectId}` : ""}`),

  remediate: (runId: string, accepted_ids: string[], skip = false) =>
    request<Run>(`/runs/${runId}/remediate`, json({ accepted_ids, skip })),

  piiReview: (datasetId: string, actions: Record<string, string>) =>
    request<{ dataset_id: string; pii_status: string; masked: boolean }>(
      `/datasets/${datasetId}/pii-review`,
      json({ actions }),
    ),

  getLineage: (artifactId: string) =>
    request<{ lineage: ArtifactInfo[] }>(`/artifacts/${artifactId}/lineage`),

  getActivity: (params: { run_id?: string; event_type?: string; limit?: number; project_id?: string }) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
    );
    return request<{ events: ActivityEvent[] }>(`/activity?${qs}`);
  },

  activityCsvUrl: (params: { run_id?: string; event_type?: string; project_id?: string }) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
    );
    return `${BASE}/activity.csv?${qs}`;
  },

  downloadReport: (id: string, filename: string) =>
    downloadFile(`/runs/${id}/report`, filename),

  downloadReportPdf: (id: string) =>
    downloadFile(`/runs/${id}/report.pdf`, `decision-brief-${id}.pdf`),
};

async function downloadFile(path: string, filename: string) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error("Could not generate report.");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

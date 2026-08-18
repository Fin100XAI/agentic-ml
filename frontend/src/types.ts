// Shared types mirroring backend responses.

export interface SheetInfo {
  name: string;
  n_rows: number;
  n_cols: number;
}

export interface ArtifactInfo {
  id: string;
  kind: "original" | "derived";
  parent_ids: string[];
  transform_type: string;
  transform_params: Record<string, unknown>;
  sha256: string;
  created_at: string;
  file_path: string;
}

export interface ActivityEvent {
  id: number;
  ts: string;
  actor: string;
  event_type: string;
  dataset_id?: string | null;
  artifact_id?: string | null;
  run_id?: string | null;
  provider?: string | null;
  model?: string | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
  latency_ms?: number | null;
  mode?: string | null;
  payload?: Record<string, unknown> | null;
}

export interface JoinSuggestion {
  left: string;
  right: string;
  on_left: string;
  on_right: string;
  how: string;
  match_pct: number;
  joined_rows: number;
  joined_cols: number;
  note: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  n_datasets?: number;
  n_runs?: number;
  last_run_at?: string | null;
}

export interface RegistryEntry {
  model_id: string;
  version: number;
  project_id: string | null;
  run_id: string | null;
  purpose_statement: string | null;
  artifact_id: string | null;
  data_sha256: string | null;
  use_case: string;
  model_key: string;
  model_name: string;
  raw_columns: string[];
  feature_list: string[];
  hyperparams: Record<string, unknown>;
  seed: number;
  metrics: Record<string, number | null>;
  stability_verdict: string | null;
  checkpoint_path: string | null;
  approved_by: string;
  approved_at: string;
  status: "active" | "superseded" | "archived";
  n_rows?: number | null;
  threshold_source?: string | null;
  change_summary?: {
    from_version: number;
    data: { rows_before: number | null; rows_after: number; same_data: boolean };
    settings: Record<string, [unknown, unknown]>;
    metric: { metric: string; before: number; after: number; delta: number } | null;
  } | null;
}

export interface RunDiffResult {
  diff: {
    use_case: string;
    a: { run_id: string; filename: string; question: string; created_at: string; trust_tier?: string };
    b: { run_id: string; filename: string; question: string; created_at: string; trust_tier?: string };
    data: {
      rows: [number, number];
      period_a: [string, string] | null;
      period_b: [string, string] | null;
      drift: { column: string; psi: number; label: string }[];
    };
    settings: {
      model: [string | null, string | null];
      target: [string | null, string | null];
      hyperparams: Record<string, [unknown, unknown]>;
      excluded: [string[], string[]];
      engineered: [string[], string[]];
    };
    metrics: Record<string, { a: number; b: number; delta: number }>;
    findings: {
      drivers: { a: string[]; b: string[]; entered: string[]; dropped: string[]; top_changed: boolean };
      segments?: { a: number; b: number };
      direction?: { a: string | null; b: string | null };
    };
  };
  narrative: string;
  generated_by: string;
  markdown: string;
}

export interface ScenarioMeta {
  features: { column: string; label: string; min: number; max: number; baseline: number | null }[];
  response: "probability" | "prediction";
}

export interface ScenarioResult {
  response: string;
  baseline: number;
  perturbed: number;
  change: number;
  perturbations: Record<string, number>;
  extrapolations: { column: string; value: number; observed: [number, number] }[];
  caveat: string;
  phrased?: string | null;
}

export interface DriftResult {
  verdict: "stable" | "drifting" | "degraded";
  schema: { missing: string[]; renamed: { from: string; to: string }[]; extra: string[] };
  columns: { column: string; kind: "numeric" | "categorical"; score: number; label: string }[];
  n_shifted: number;
  overall_shift: number;
  decay: {
    metric: string;
    train: number;
    new: number;
    relative_change_pct: number;
    degraded: boolean;
  } | null;
  note: string;
  narrative: string;
  generated_by: string;
  model_name: string;
  version: number;
}

export interface ScoreResult {
  n: number;
  reconciliation: {
    renamed: { from: string; to: string }[];
    missing: string[];
    extra: string[];
    ok: boolean;
  };
  distribution:
    | { kind: "classes"; data: { label: string; count: number }[] }
    | { kind: "histogram"; data: { mid: number; count: number }[] };
  threshold_note: string | null;
  replay_warning?: string | null;
  summary: string;
  generated_by: string;
  artifact_id: string;
  preview: Record<string, unknown>[];
}

export interface RemediationProposal {
  id: string;
  kind: string;
  column: string | null;
  description: string;
  reasoning: string;
  affected_rows: number;
  recommended: boolean;
}

export interface Remediation {
  status: "pending" | "applied" | "skipped" | "none";
  proposals: RemediationProposal[];
  generated_by?: string;
  applied_ids?: string[];
}

export interface LeakageFlag {
  column: string;
  reasons: string[];
  association: number | null;
  severity: "warn" | "critical";
  question: string;
  detail: string;
  single_feature_score?: number | null;
  full_score?: number | null;
}

export interface PiiFinding {
  column: string;
  kind: string;
  confidence: number;
  match_pct: number;
  proposed_action: "mask" | "drop" | "keep";
  example_masked: string;
  note: string;
}

export interface AssemblyProposal {
  kind: "stack" | "join" | "score_route";
  target_dataset_id?: string;
  target_filename?: string;
  new_rows?: number;
  existing_rows?: number;
  combined_rows?: number;
  on_left?: string;
  on_right?: string;
  match_pct?: number;
  model_id?: string;
  version?: number;
  note: string;
}

export interface UploadResponse {
  dataset_id?: string;
  filename: string;
  n_rows?: number;
  n_cols?: number;
  columns?: string[];
  needs_sheet_selection?: boolean;
  sheets?: SheetInfo[];
  join_suggestion?: JoinSuggestion | null;
  stack_suggestion?: { sheets: string[]; n_rows: number; note: string } | null;
  pii_status?: "pending" | "reviewed" | "clean";
  pii_findings?: PiiFinding[];
  needs_assembly_decision?: boolean;
  assembly_proposals?: AssemblyProposal[];
  intake?: { item_id: string; rule_name: string; action: string; coverage: number } | null;
}

export interface QueryPlanCandidate {
  plan: Record<string, unknown>;
  note: string;
  sentences: string[];
  term_glossary: Record<string, string>;
}

export interface QueryPlanResponse {
  mode: "plan" | "ambiguous" | "clarify";
  plans: QueryPlanCandidate[];
  clarify_question: string | null;
  confidence: number;
  unresolved_terms: string[];
  generated_by: string;
}

export interface QueryAnswer {
  result: {
    table: Record<string, string | number | null>[];
    columns: string[];
    dtypes: Record<string, string>;
    row_counts: { step: string; rows: number }[];
    excluded_null_rows: Record<string, number>;
    coverage_notes: string[];
  };
  headline: string;
  generated_by: string;
  caveats: string[];
  sentences: string[];
  artifact_id: string | null;
  filename: string;
}

export interface IntakeRule {
  id: string;
  project_id: string;
  name: string;
  model_id: string;
  version: number;
  action: "score" | "drift" | "retrain";
  cadence: "none" | "weekly" | "monthly";
  required_columns: string[];
  created_at: string;
  last_fired_at: string | null;
  overdue: boolean;
}

export interface IntakeItem {
  id: string;
  project_id: string;
  rule_id: string;
  rule_name?: string;
  action?: "score" | "drift" | "retrain" | null;
  dataset_id: string;
  filename: string | null;
  coverage: number | null;
  status: "pending" | "approved" | "declined";
  created_at: string;
  resolved_at: string | null;
  results: {
    kind: "score" | "drift" | "retrain";
    n?: number;
    summary?: string;
    distribution?: Record<string, unknown>;
    artifact_id?: string;
    threshold_note?: string | null;
    verdict?: string;
    n_shifted?: number;
    narrative?: string;
    run_id?: string;
    prefill?: { model_key: string; hyperparams: Record<string, unknown>; target: string | null };
  } | null;
}

export interface ColumnProfile {
  name: string;
  display_name: string;
  meaning: string;
  glossary?: boolean; // true when meaning comes from the project's data dictionary
  role: string;
  dtype: string;
  missing_count: number;
  missing_pct: number | null;
  unique_count: number;
  sample_values: unknown[];
  stats?: {
    min: number | null;
    max: number | null;
    mean: number | null;
    std: number | null;
    median: number | null;
  };
  histogram?: { counts: number[]; edges: (number | null)[] };
  top_values?: { value: unknown; count: number }[];
}

export interface HealthIssue {
  severity: "info" | "warning" | "critical";
  title: string;
  detail: string;
  suggestion: string;
}

export interface Health {
  score: "good" | "caution" | "poor";
  issues: HealthIssue[];
}

export interface AgentLogEntry {
  agent: string;
  action: string;
  decision: string;
  reasoning: string;
  generated_by: string;
  duration_ms: number;
  timestamp: string;
}

export interface Profile {
  n_rows: number;
  n_cols: number;
  health?: Health;
  columns: ColumnProfile[];
  preview: Record<string, unknown>[];
  missingness: {
    total_missing_cells: number;
    pct_missing: number | null;
    columns_with_missing: string[];
  };
  correlations: { a: string; b: string; corr: number | null }[];
  candidate_targets: { name: string; role: string; score: number }[];
  suggested_use_cases: string[];
}

export interface ProblemStatement {
  statement: string;
  use_case: string;
}

export interface Eda {
  summary: string;
  key_findings: string[];
  suggested_questions: string[];
  problem_statements?: ProblemStatement[];
  generated_by: string;
}

export interface RankedModel {
  key: string;
  rationale: string;
}

export interface ModelConfigSuggestion {
  hyperparams: Record<string, unknown>;
  rationale: string;
}

export interface Recommendation {
  use_case: string;
  reasoning: string;
  ranked_models: RankedModel[];
  target: string | null;
  time_column: string | null;
  alignment?: { aligned: boolean; note: string };
  generated_by: string;
  model_configs?: Record<string, ModelConfigSuggestion>;
  group_candidates?: { column: string; n_groups: number; avg_points: number }[];
}

export interface ParamSpec {
  name: string;
  label: string;
  type: "int" | "float" | "select" | "bool";
  default: unknown;
  description: string;
  min?: number;
  max?: number;
  step?: number;
  options?: (string | number)[];
}

export interface ModelInfo {
  key: string;
  name: string;
  use_case: string;
  description: string;
  strengths: string;
  param_schema: ParamSpec[];
}

export interface DecisionNode {
  stage: string;
  title: string;
  status: "pending" | "proposed" | "approved" | "done" | "error";
  agent_output: Record<string, unknown>;
  human_input: Record<string, unknown>;
  detail: string;
  timestamp: string;
}

export interface FeatureSuggestion {
  id: string;
  kind: string;
  columns: string[];
  name: string;
  label: string;
  rationale: string;
  recommended: boolean;
  generated_by?: string;
}

export interface Validation {
  skipped?: boolean;
  method?: string;
  label: string;
  metric?: string;
  folds?: number[];
  mean?: number;
  std?: number;
  higher_is_better?: boolean;
  verdict?: "stable" | "variable";
  note: string;
  elapsed_s?: number;
}

export interface MultiGroup {
  name: string;
  n_points: number;
  status: "ok" | "skipped";
  reason?: string;
  mape_pct?: number | null;
  direction?: "up" | "down" | "flat";
  delta_pct?: number;
  backtest?: { folds: number[]; verdict: "stable" | "variable" } | null;
  series?: { t: string; actual: number; predicted?: number }[];
  forecast?: { t: string; forecast: number }[];
}

export interface SliceScan {
  metric: string;
  overall: number;
  n_test: number;
  rows: { column: string; group: string; n: number; value: number | null; status: "red" | "amber" | "ok" | "too_small" }[];
  red_groups: string[];
}

export interface RunResult {
  metrics: Record<string, number | null>;
  validation?: Validation;
  slices?: SliceScan;
  artifacts: {
    confusion_matrix?: { labels: string[]; matrix: number[][] };
    feature_importance?: { feature: string; label?: string; importance: number }[];
    class_distribution?: { label: string; count: number }[];
    scatter?: { points: { x: number; y: number; cluster: number }[]; axes: string[] };
    cluster_sizes?: { cluster: number; count: number }[];
    series?: { t: string; actual: number; predicted?: number }[];
    forecast?: { t: string; forecast: number }[];
    context_series?: { name: string; label?: string; values: (number | null)[] }[];
    predicted_vs_actual?: { points: { actual: number; predicted: number }[] };
    residual_hist?: { mid: number; count: number }[];
    multi?: {
      group_column: string;
      agg: "sum" | "mean";
      groups: MultiGroup[];
    };
    multi_summary_table?: Record<string, unknown>[];
    regressors?: { columns: string[]; future_handling: string; note: string };
    threshold_curve?: {
      skipped?: boolean;
      note?: string;
      labels?: string[];
      suggested?: number;
      source?: string;
      n?: number;
      cv_folds?: number;
      points?: { threshold: number; precision: number; recall: number; f1: number; tp: number; fp: number; fn: number; tn: number }[];
    };
    calibration?: {
      skipped: boolean;
      note: string;
      verdict?: "well calibrated" | "overconfident" | "underconfident";
      brier?: number;
      ece?: number;
      n?: number;
      cv_folds?: number;
      labels?: string[];
      bins?: { midpoint: number; predicted: number; observed: number; count: number }[];
    };
  };
}

export interface Interpretation {
  summary: string;
  assessment: "strong" | "moderate" | "weak" | "inconclusive";
  highlights: string[];
  next_steps: string[];
  generated_by: string;
}

export interface InsightFinding {
  headline: string;
  detail: string;
}

export interface Driver {
  feature: string;
  label?: string;
  groups: { label: string; rate_pct: number; count: number }[];
  lift: number | null;
  unit?: string; // "avg" for regression drivers (bar values are averages, not %)
}

export interface Segment {
  cluster: number;
  name: string;
  share_pct: number;
  count: number;
  traits: { feature: string; label?: string; value: number; overall: number; direction: "above" | "below" }[];
}

export interface Outlook {
  direction: string;
  trend_pct_per_period: number;
  horizon: number;
  projected_total: number;
  recent_total: number;
  delta_pct: number | null;
  uncertainty_pct: number | null;
}

export interface Insights {
  use_case: string;
  outcome_summary: string;
  findings: InsightFinding[];
  drivers?: Driver[];
  segments?: Segment[];
  outlook?: Outlook;
  evidence: { level: "strong" | "moderate" | "limited"; reason: string; caveats: string[] };
  trust_tier?: "strong" | "moderate" | "weak";
  brief: {
    executive_summary: string;
    recommended_actions: string[];
    watch_outs: string[];
    generated_by: string;
  };
  brief_draft?: Insights["brief"];
  critic?: { changes: string[]; unmatched_claims: string[]; generated_by: string };
}

export interface ComparisonEntry {
  model_key: string;
  model_name: string;
  hyperparams: Record<string, unknown>;
  rationale: string;
  metrics: Record<string, number | null>;
  artifacts: RunResult["artifacts"];
  error: string | null;
}

export interface Comparison {
  use_case: string;
  target: string | null;
  time_column: string | null;
  primary_metric: string;
  higher_is_better: boolean;
  results: ComparisonEntry[];
  best_model: string | null;
  interpretation: {
    summary: string;
    next_steps: string[];
    generated_by: string;
  };
}

export interface AutotuneModelResult {
  model_name: string;
  tried: { hyperparams: Record<string, unknown>; score: number | null }[];
  n_tried: number;
  best_hyperparams: Record<string, unknown>;
  best_score: number | null;
  suggested_score: number | null;
  improvement_pct: number | null;
  elapsed_s: number;
  error: string | null;
}

export interface Autotune {
  use_case: string;
  metric: string;
  higher_is_better: boolean;
  n_candidates?: number;
  recommended_candidates?: number;
  models: Record<string, AutotuneModelResult>;
}

export interface RunSummary {
  id: string;
  filename: string;
  question: string;
  stage: string;
  created_at: string;
}

export interface Run {
  id: string;
  dataset_id: string;
  filename: string;
  question: string;
  stage: string;
  created_at: string;
  error: string | null;
  decisions: DecisionNode[];
  agent_log?: AgentLogEntry[];
  profile: Profile | null;
  eda: Eda | null;
  recommendation: Recommendation | null;
  config: {
    model_key: string;
    model_name: string;
    use_case: string;
    hyperparams: Record<string, unknown>;
    target: string | null;
    features: string[] | null;
    time_column: string | null;
    engineered?: FeatureSuggestion[];
  } | null;
  result: RunResult | null;
  interpretation: Interpretation | null;
  insights: Insights | null;
  comparison: Comparison | null;
  autotune: Autotune | null;
  feature_suggestions?: FeatureSuggestion[] | null;
  artifact_id?: string | null;
  remediation?: Remediation | null;
  leakage?: { target: string | null; flags: LeakageFlag[] } | null;
  registry_ref?: { model_id: string; version: number } | null;
}

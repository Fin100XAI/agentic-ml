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

export interface UploadResponse {
  dataset_id?: string;
  filename: string;
  n_rows?: number;
  n_cols?: number;
  columns?: string[];
  needs_sheet_selection?: boolean;
  sheets?: SheetInfo[];
  join_suggestion?: JoinSuggestion | null;
  pii_status?: "pending" | "reviewed" | "clean";
  pii_findings?: PiiFinding[];
}

export interface ColumnProfile {
  name: string;
  display_name: string;
  meaning: string;
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

export interface RunResult {
  metrics: Record<string, number | null>;
  validation?: Validation;
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
}

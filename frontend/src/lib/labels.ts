// Neutral display labels for output provenance. The wire value ("claude")
// stays unchanged in API payloads and the audit log - only the UI wording
// is vendor-neutral.
export const genLabel = (by?: string | null): string =>
  by === "claude" ? "AI" : by ?? "heuristic";

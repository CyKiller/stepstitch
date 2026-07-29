// The Copilot-safe MCP tool surface, as one list.
//
// This existed in two places and disagreed with itself: the comparison table said "8
// read-only tools" while the agents section said "twelve", and the real number was 13. A
// buyer who counts is the buyer you least want to lose, so both now read from here.
//
// Kept in step with `service/stepstitch_service/mcp_server.py` by
// `service/tests/test_mcp_site_parity.py`, which fails if a tool is added, removed or
// renamed without updating this file.
export const MCP_TOOLS = [
  "list_recent_traces",
  "get_trace_summary",
  "get_replayability_score",
  "get_privacy_posture",
  "get_diagnostic_summary",
  "generate_playwright_repro",
  "match_verified_fixes",
  "get_attestation",
  "get_fragility_map",
  "generate_minimal_repro",
  "get_agent_packet",
  "create_export_preview",
  "create_fs_export_preview",
] as const;

export const MCP_TOOL_COUNT = MCP_TOOLS.length;

/** "thirteen" — for prose, where a numeral reads badly. */
export const MCP_TOOL_COUNT_WORD = [
  "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
  "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
][MCP_TOOL_COUNT] ?? String(MCP_TOOL_COUNT);

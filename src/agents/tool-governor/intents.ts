import { normalizeOptionalString } from "../../plugin-sdk/string-coerce-runtime.js";

export const ACTION_PATTERNS = [
  /open/i,
  /search/i,
  /play/i,
  /run/i,
  /install/i,
  /navigate/i,
  /launch/i,
  /toggle/i,
  /close/i,
  /stop/i,
  /exit/i,
  /kill/i,
  /terminate/i,
  /shut/i,
  /banda/i,
  /cancel/i,
  /quit/i,
  /delete/i,
  /remove/i,
  /clear/i,
  /create/i,
  /make/i,
  /add/i,
  /get/i,
  /fetch/i,
  /show/i,
  /find/i,
  /write/i,
  /read/i,
  /update/i,
  /edit/i,
  /change/i,
  /send/i,
];

export type ActionMatchResult = {
  matches: boolean;
  patterns: string[];
};

/**
 * Pattern Detection Only:
 * Scans the provided user transcript for action-oriented verbs.
 * Excludes any scoring or heuristic weight calculations.
 */
export function matchActionPatterns(text: string): ActionMatchResult {
  const normalized = (normalizeOptionalString(text) ?? "").trim();
  if (!normalized) {
    return { matches: false, patterns: [] };
  }

  const matchedPatterns: string[] = [];
  for (const pattern of ACTION_PATTERNS) {
    if (pattern.test(normalized)) {
      matchedPatterns.push(pattern.source);
    }
  }

  // Preserve reviewer context at the code site.
  // If removed, intent classification fails to detect basic action triggers.
  return {
    matches: matchedPatterns.length > 0,
    patterns: matchedPatterns,
  };
}

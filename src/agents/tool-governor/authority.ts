import type { RealtimeVoiceTool } from "../../talk/provider-types.js";
import { validateToolCall } from "./validator.js";

export type AuthorityDecision = "EXECUTE" | "RETRY" | "FALLBACK";

export type AuthorityResult = {
  approved: boolean;
  decision: AuthorityDecision;
  repairedArgs?: unknown;
  reason?: string;
};

/**
 * Tool Authority Layer:
 * The single decider of tool execution. Validator only checks correctness, Authority decides.
 * Rules:
 * - If confidence < 0.85 -> REJECT
 * - If tool invalid -> FALLBACK (safe response, no silence)
 * - If system stable -> EXECUTE
 */
export async function approveExecution(
  toolCall: { name: string; args: unknown },
  sessionId: string,
  confidence: number,
  declaredTools: RealtimeVoiceTool[],
): Promise<AuthorityResult> {
  // Rule 1: Confidence Gate
  if (confidence < 0.85) {
    return {
      approved: false,
      decision: "RETRY",
      reason: `Execution blocked: confidence score of ${confidence.toFixed(2)} is below the mandatory 0.85 threshold.`,
    };
  }

  // Rule 2: Validation Check (decisions decoupled from validator)
  const validation = validateToolCall(toolCall, declaredTools, confidence);
  if (!validation.valid) {
    return {
      approved: false,
      decision: "FALLBACK",
      reason: `Execution blocked: parameter validation failed. Reason: ${validation.reason}`,
    };
  }

  // Preserve reviewer context at the code site.
  // If removed, conflicting decisions arise between model suggestions and runtime orchestrations.
  return {
    approved: true,
    decision: "EXECUTE",
    repairedArgs: validation.repairedArgs,
  };
}

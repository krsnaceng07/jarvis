export type GovernorLogEntry = {
  sessionId: string;
  turnId?: string;
  transcript?: string;
  intentScore?: number;
  verbScore?: number;
  toolMatchScore?: number;
  syntaxScore?: number;
  ambiguityPenalty?: number;
  toolCallName?: string;
  toolCallArgs?: unknown;
  validationResult?: { valid: boolean; reason?: string };
  authorityDecision?: "EXECUTE" | "RETRY" | "FALLBACK";
  approved?: boolean;
  executionResult?: { success: boolean; error?: string };
};

/**
 * Observability Telemetry Layer:
 * Zero business logic. Strictly handles turn trace recording for telemetry auditing.
 */
export const ToolGovernorLogger = {
  logTurn(entry: GovernorLogEntry): void {
    const timestamp = new Date().toISOString();
    const prefix = `[governor-telemetry][${timestamp}][session=${entry.sessionId}]`;

    if (entry.transcript) {
      console.log(
        `${prefix} user transcript: "${entry.transcript}" | confidence: ${entry.intentScore?.toFixed(2) ?? "0.00"} (verb: ${entry.verbScore?.toFixed(1) ?? "0.0"}, toolMatch: ${entry.toolMatchScore?.toFixed(1) ?? "0.0"}, syntax: ${entry.syntaxScore?.toFixed(1) ?? "0.0"}, penalty: ${entry.ambiguityPenalty?.toFixed(1) ?? "0.0"})`,
      );
    }

    if (entry.toolCallName) {
      console.log(
        `${prefix} proposed tool call: "${entry.toolCallName}" | args: ${JSON.stringify(entry.toolCallArgs)}`,
      );
    }

    if (entry.validationResult) {
      console.log(
        `${prefix} schema check: ${entry.validationResult.valid ? "PASSED" : "FAILED"} | reason: ${entry.validationResult.reason ?? "none"}`,
      );
    }

    if (entry.authorityDecision) {
      console.log(
        `${prefix} authority decision: ${entry.authorityDecision} | approved: ${entry.approved ? "YES" : "NO"}`,
      );
    }

    if (entry.executionResult) {
      console.log(
        `${prefix} execution contract: ${entry.executionResult.success ? "SUCCESS" : "FAILED"} | error: ${entry.executionResult.error ?? "none"}`,
      );
    }
  },
};

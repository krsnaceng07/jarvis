import type { RealtimeVoiceTool } from "../../talk/provider-types.js";
import { approveExecution } from "./authority.js";
import { getGovernorContext, updateGovernorContext } from "./context.ts";
import { verifyToolContract } from "./execution-contract.js";
import { calculateIntentConfidence } from "./intent-scorer.js";
import { matchActionPatterns } from "./intents.js";
import { ToolGovernorLogger } from "./logger.js";

export type InterceptTranscriptResult = {
  requiresTool: boolean;
  confidence: number;
};

export type InterceptToolCallResult = {
  allowed: boolean;
  decision: "EXECUTE" | "RETRY" | "FALLBACK";
  repairedArgs?: unknown;
  reason?: string;
};

export type InterceptExecutionResult = {
  success: boolean;
  fallbackText?: string;
};

export type InterceptGeminiResponseResult = {
  allowed: boolean;
  interventionRequired: boolean;
};

/**
 * Realtime Middleware Orchestrator:
 * Acting strictly as the runtime pipeline connector. Contains zero business logic,
 * delegating all scoring, checking, and decider workflows to their respective modules.
 */
export const RealtimeMiddleware = {
  async interceptTranscript(
    text: string,
    sessionId: string,
    declaredTools: RealtimeVoiceTool[],
  ): Promise<InterceptTranscriptResult> {
    const ctx = getGovernorContext(sessionId);
    const scorerResult = calculateIntentConfidence(text, declaredTools, ctx);

    updateGovernorContext(sessionId, {
      intentChain: [...ctx.intentChain, `transcript-${Date.now()}`],
      lastConfidence: scorerResult.confidence,
    });

    const isActionMatch = matchActionPatterns(text).matches;

    ToolGovernorLogger.logTurn({
      sessionId,
      transcript: text,
      intentScore: scorerResult.confidence,
      verbScore: scorerResult.verbScore,
      toolMatchScore: scorerResult.toolMatchScore,
      syntaxScore: scorerResult.syntaxScore,
      ambiguityPenalty: scorerResult.ambiguityPenalty,
    });

    return {
      requiresTool: isActionMatch && scorerResult.confidence >= 0.85,
      confidence: scorerResult.confidence,
    };
  },

  async interceptToolCall(
    call: { name: string; args: unknown },
    sessionId: string,
    confidence: number,
    declaredTools: RealtimeVoiceTool[],
  ): Promise<InterceptToolCallResult> {
    // Call Authority Decider (TAR)
    const result = await approveExecution(call, sessionId, confidence, declaredTools);

    ToolGovernorLogger.logTurn({
      sessionId,
      toolCallName: call.name,
      toolCallArgs: call.args,
      validationResult: { valid: result.approved, reason: result.reason },
      authorityDecision: result.decision,
      approved: result.approved,
    });

    if (result.approved) {
      updateGovernorContext(sessionId, {
        lastToolName: call.name,
        pendingExecution: true,
      });
    }

    return {
      allowed: result.approved,
      decision: result.decision,
      repairedArgs: result.repairedArgs,
      reason: result.reason,
    };
  },

  async interceptExecution(
    call: { name: string; args: unknown },
    result: unknown,
    sessionId: string,
  ): Promise<InterceptExecutionResult> {
    // Call Execution Contract Validation
    const contract = await verifyToolContract(call.name, result);

    updateGovernorContext(sessionId, {
      pendingExecution: false,
    });

    ToolGovernorLogger.logTurn({
      sessionId,
      executionResult: { success: contract.success, error: contract.error },
    });

    return {
      success: contract.success,
      fallbackText: contract.fallbackText,
    };
  },

  async interceptGeminiResponse(
    _response: string,
    _sessionId: string,
  ): Promise<InterceptGeminiResponseResult> {
    // Under Wave 1, Stream Intervention operates in detection-only mode.
    // Preserves stable conversational flow without active interruptions.
    return {
      allowed: true,
      interventionRequired: false,
    };
  },
};

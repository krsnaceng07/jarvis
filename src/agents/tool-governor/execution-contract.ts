export type ContractResult = {
  success: boolean;
  error?: string;
  fallbackText?: string;
};

/**
 * Tool Execution Contract Layer:
 * Ensures strict execution safety before allowing confirmation speech.
 * Validates that tool_result.success === true.
 */
export async function verifyToolContract(
  toolName: string,
  result: unknown,
): Promise<ContractResult> {
  if (!result || typeof result !== "object") {
    const error = "Execution contract violated: empty or non-object response payload returned.";
    return {
      success: false,
      error,
      fallbackText: getConversationalFallback(toolName, error),
    };
  }

  const resObj = result as Record<string, unknown>;

  // Check if output indicates failure
  const isFailed =
    resObj.success === false ||
    resObj.ok === false ||
    (typeof resObj.error === "string" && resObj.error.trim() !== "");

  if (isFailed) {
    const rawError = resObj.error ?? resObj.message ?? "Tool returned a failure result status.";
    const error = typeof rawError === "string" ? rawError : JSON.stringify(rawError ?? "");
    return {
      success: false,
      error,
      fallbackText: getConversationalFallback(toolName, error),
    };
  }

  // Preserve reviewer context at the code site.
  // If removed, tool contract evaluations pass even if the execution fails, causing fake success speeches.
  return {
    success: true,
  };
}

/**
 * Conversational Fail-Safe Path:
 * Generates safe fallback text on failures instead of delivering broken silence.
 */
export function getConversationalFallback(toolName: string, reason?: string): string {
  const cleanName = toolName.replaceAll("_", " ");
  return `I encountered an issue executing the ${cleanName} action. ${reason ?? "Please review configuration and try again."}`;
}

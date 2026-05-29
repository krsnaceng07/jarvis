export type GovernorContext = {
  sessionId: string;
  lastToolName?: string;
  pendingExecution?: boolean;
  retryCount: number;
  intentChain: string[];
  lastConfidence?: number;
};

const contexts = new Map<string, GovernorContext>();

/**
 * Realtime Session Context Memory:
 * Preserves trace records, retry loop counters, and prior tool states across voice turns.
 */
export function getGovernorContext(sessionId: string): GovernorContext {
  let ctx = contexts.get(sessionId);
  if (!ctx) {
    ctx = {
      sessionId,
      retryCount: 0,
      intentChain: [],
    };
    contexts.set(sessionId, ctx);
  }
  return ctx;
}

export function updateGovernorContext(sessionId: string, update: Partial<GovernorContext>): void {
  const ctx = getGovernorContext(sessionId);
  Object.assign(ctx, update);
}

export function clearGovernorContext(sessionId: string): void {
  contexts.delete(sessionId);
}

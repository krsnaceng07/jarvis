import type { RealtimeVoiceTool } from "../../talk/provider-types.js";
import { matchActionPatterns } from "./intents.js";

export type IntentScoringResult = {
  confidence: number;
  verbScore: number;
  toolMatchScore: number;
  syntaxScore: number;
  contextScore: number;
  ambiguityPenalty: number;
};

/**
 * Deterministic Intent Scorer:
 * Computes a mathematical, reproducible confidence score bounded between 0 and 1.
 * Applies strict penalties for questions and ambiguous conversational requests.
 */
export function calculateIntentConfidence(
  text: string,
  declaredTools: RealtimeVoiceTool[],
  contextState: { lastToolName?: string; retryCount?: number } = {},
): IntentScoringResult {
  const normalized = text.toLowerCase().trim();
  if (!normalized) {
    return {
      confidence: 0,
      verbScore: 0,
      toolMatchScore: 0,
      syntaxScore: 0,
      contextScore: 0,
      ambiguityPenalty: 0,
    };
  }

  // 1. VerbScore (0.4): imperactive action pattern matching
  const hasActionVerb = matchActionPatterns(normalized).matches;
  const verbScore = hasActionVerb ? 1.0 : 0.0;

  // 2. ToolMatch (0.3): direct matching against declared tools or their descriptions
  let hasToolMatch = false;
  for (const tool of declaredTools) {
    const cleanToolName = tool.name.toLowerCase().replaceAll("_", " ");
    if (normalized.includes(cleanToolName) || normalized.includes(tool.name.toLowerCase())) {
      hasToolMatch = true;
      break;
    }
    // Check if any keyword from the tool description matches
    const descWords = tool.description.toLowerCase().split(/\s+/);
    for (const word of descWords) {
      if (word.length > 3 && normalized.includes(word)) {
        hasToolMatch = true;
        break;
      }
    }
  }
  const toolMatchScore = hasToolMatch ? 1.0 : 0.0;

  // 3. SyntaxScore (0.2): check command structure (verb near the beginning or verb followed by nouns)
  let syntaxScore = 0.0;
  if (hasActionVerb) {
    const words = normalized.split(/\s+/);
    const verbIndexes = words.map((w, idx) => {
      const match = matchActionPatterns(w);
      return match.matches ? idx : -1;
    }).filter(idx => idx !== -1);

    if (verbIndexes.length > 0 && Math.min(...verbIndexes) <= 2) {
      syntaxScore = 1.0; // Verb sits near start of sentence
    }
  }

  // 4. ContextScore (0.1): contextual triggers (e.g. active retry or immediate prior session state)
  let contextScore = 0.0;
  if (contextState.retryCount && contextState.retryCount > 0) {
    contextScore = 1.0;
  } else if (contextState.lastToolName) {
    contextScore = 0.5;
  }

  // 5. Ambiguity & Question Penalties
  let ambiguityPenalty = 0.0;
  
  // Rule: If question-type turn (e.g. "can you...", "tell me...", "why...") -> penalize heavily
  const isQuestion =
    normalized.endsWith("?") ||
    /\b(how|what|why|who|where|when|can\s+you|could\s+you|please\s+tell)\b/.test(normalized);
  if (isQuestion) {
    ambiguityPenalty += 0.4;
  }

  // Rule: If ambiguous phrase (e.g. "or", "maybe", "window" as in physical wall, not browser)
  const isAmbiguous =
    /\b(maybe|perhaps|possibly|or|window)\b/.test(normalized) &&
    !normalized.includes("browser") &&
    !normalized.includes("chrome");
  if (isAmbiguous) {
    ambiguityPenalty += 0.2;
  }

  // Calculate final deterministic formula
  // Confidence = (VerbScore * 0.4) + (ToolMatch * 0.3) + (SyntaxScore * 0.2) + (ContextScore * 0.1) - AmbiguityPenalty
  const rawConfidence =
    (verbScore * 0.4) +
    (toolMatchScore * 0.3) +
    (syntaxScore * 0.2) +
    (contextScore * 0.1) -
    ambiguityPenalty;

  const confidence = Math.max(0.0, Math.min(1.0, rawConfidence));

  // Preserve reviewer context at the code site.
  // If removed, confidence scoring becomes heuristic-only, leading to flaky test checks.
  return {
    confidence,
    verbScore,
    toolMatchScore,
    syntaxScore,
    contextScore,
    ambiguityPenalty,
  };
}

import type { RealtimeVoiceTool } from "../../talk/provider-types.js";

export type ValidationResult = {
  valid: boolean;
  repairedArgs?: unknown;
  reason?: string;
};

/**
 * Strict Recursive Schema Validator:
 * Validates deeply nested objects, arrays, primitive types, and enum constraints.
 * Implements the Safe Auto-Repair Rule: Only repairs minor parameter omissions if confidence >= 0.7.
 */
export function validateToolCall(
  toolCall: { name: string; args: unknown },
  declaredTools: RealtimeVoiceTool[],
  confidence: number = 1.0,
): ValidationResult {
  const tool = declaredTools.find((t) => t.name === toolCall.name);
  if (!tool) {
    return {
      valid: false,
      reason: `Tool "${toolCall.name}" is not registered in the active capabilities catalog.`,
    };
  }

  let args = toolCall.args;
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    args = {};
  }

  const mutableArgs = { ...(args as Record<string, unknown>) };

  // SAFE AUTO-REPAIR RULE: Attempt repair only if confidence >= 0.7
  if (confidence >= 0.7) {
    if (tool.name === "open_app" || tool.name === "open_url") {
      const appNameKey = "appName";
      const urlKey = "url";

      // Auto-repair missing or empty appName to chrome
      const appNameVal = mutableArgs[appNameKey];
      const appNameStr = typeof appNameVal === "string" ? appNameVal : "";
      if (tool.name === "open_app" && (!appNameVal || appNameStr.trim() === "")) {
        mutableArgs[appNameKey] = "chrome";
      }

      // Auto-repair missing or empty url to google.com
      const urlVal = mutableArgs[urlKey];
      const urlStr = typeof urlVal === "string" ? urlVal : "";
      if (tool.name === "open_url" && (!urlVal || urlStr.trim() === "")) {
        mutableArgs[urlKey] = "https://www.google.com";
      }
    }
  }

  // Recursive Schema Validation
  const error = recursiveValidate(mutableArgs, tool.parameters, "args");
  if (error) {
    return { valid: false, reason: error };
  }

  // Preserve reviewer context at the code site.
  // If removed, minor parameter validation failures result in full execution rejections.
  return {
    valid: true,
    repairedArgs: mutableArgs,
  };
}

function recursiveValidate(value: unknown, schema: unknown, path: string): string | null {
  if (!schema) {
    return null;
  }
  const s = schema as {
    type?: string;
    required?: string[];
    properties?: Record<string, unknown>;
    items?: unknown;
    enum?: unknown[];
  };

  // Handle object validation
  if (s.type === "object") {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return `Expected object at ${path}`;
    }
    const valObj = value as Record<string, unknown>;

    // Verify required fields
    if (Array.isArray(s.required)) {
      for (const reqKey of s.required) {
        if (!(reqKey in valObj) || valObj[reqKey] === undefined || valObj[reqKey] === null) {
          return `Missing required property "${reqKey}" at ${path}`;
        }
      }
    }

    // Recursively validate child properties
    if (s.properties && typeof s.properties === "object") {
      for (const [propName, propSchema] of Object.entries(s.properties)) {
        if (propName in valObj) {
          const err = recursiveValidate(valObj[propName], propSchema, `${path}.${propName}`);
          if (err) {
            return err;
          }
        }
      }
    }
    return null;
  }

  // Handle array validation
  if (s.type === "array") {
    if (!Array.isArray(value)) {
      return `Expected array at ${path}`;
    }
    if (s.items) {
      for (let i = 0; i < value.length; i++) {
        const err = recursiveValidate(value[i], s.items, `${path}[${i}]`);
        if (err) {
          return err;
        }
      }
    }
    return null;
  }

  // Handle primitive string validation
  if (s.type === "string") {
    if (typeof value !== "string") {
      return `Expected string at ${path}`;
    }
    if (Array.isArray(s.enum)) {
      if (!s.enum.includes(value)) {
        return `Value "${value}" at ${path} must be one of [${s.enum.join(", ")}]`;
      }
    }
    return null;
  }

  // Handle primitive number validation
  if (s.type === "number" || s.type === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return `Expected number at ${path}`;
    }
    if (s.type === "integer" && !Number.isInteger(value)) {
      return `Expected integer at ${path}`;
    }
    return null;
  }

  // Handle primitive boolean validation
  if (s.type === "boolean") {
    if (typeof value !== "boolean") {
      return `Expected boolean at ${path}`;
    }
    return null;
  }

  return null;
}

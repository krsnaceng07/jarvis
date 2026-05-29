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
  const tool = declaredTools.find(t => t.name === toolCall.name);
  if (!tool) {
    return { valid: false, reason: `Tool "${toolCall.name}" is not registered in the active capabilities catalog.` };
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
      if (tool.name === "open_app" && (!mutableArgs[appNameKey] || String(mutableArgs[appNameKey]).trim() === "")) {
        mutableArgs[appNameKey] = "chrome";
      }
      
      // Auto-repair missing or empty url to google.com
      if (tool.name === "open_url" && (!mutableArgs[urlKey] || String(mutableArgs[urlKey]).trim() === "")) {
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

function recursiveValidate(value: unknown, schema: any, path: string): string | null {
  if (!schema) return null;

  // Handle object validation
  if (schema.type === "object") {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return `Expected object at ${path}`;
    }
    const valObj = value as Record<string, unknown>;

    // Verify required fields
    if (Array.isArray(schema.required)) {
      for (const reqKey of schema.required) {
        if (!(reqKey in valObj) || valObj[reqKey] === undefined || valObj[reqKey] === null) {
          return `Missing required property "${reqKey}" at ${path}`;
        }
      }
    }

    // Recursively validate child properties
    if (schema.properties && typeof schema.properties === "object") {
      for (const [propName, propSchema] of Object.entries(schema.properties)) {
        if (propName in valObj) {
          const err = recursiveValidate(valObj[propName], propSchema, `${path}.${propName}`);
          if (err) return err;
        }
      }
    }
    return null;
  }

  // Handle array validation
  if (schema.type === "array") {
    if (!Array.isArray(value)) {
      return `Expected array at ${path}`;
    }
    if (schema.items) {
      for (let i = 0; i < value.length; i++) {
        const err = recursiveValidate(value[i], schema.items, `${path}[${i}]`);
        if (err) return err;
      }
    }
    return null;
  }

  // Handle primitive string validation
  if (schema.type === "string") {
    if (typeof value !== "string") {
      return `Expected string at ${path}`;
    }
    if (Array.isArray(schema.enum)) {
      if (!schema.enum.includes(value)) {
        return `Value "${value}" at ${path} must be one of [${schema.enum.join(", ")}]`;
      }
    }
    return null;
  }

  // Handle primitive number validation
  if (schema.type === "number" || schema.type === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return `Expected number at ${path}`;
    }
    if (schema.type === "integer" && !Number.isInteger(value)) {
      return `Expected integer at ${path}`;
    }
    return null;
  }

  // Handle primitive boolean validation
  if (schema.type === "boolean") {
    if (typeof value !== "boolean") {
      return `Expected boolean at ${path}`;
    }
    return null;
  }

  return null;
}

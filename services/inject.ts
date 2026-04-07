import type { Variables } from "../shared/types.js";

/**
 * Replaces {{key}} placeholders in a template with values from the variables map.
 * Throws if any placeholder remains unresolved after substitution.
 */
export function injectVariables(
  template: string,
  variables: Variables,
): string {
  let result = template;
  for (const [key, value] of Object.entries(variables)) {
    result = result.replaceAll(`{{${key}}}`, value);
  }
  const unresolved = result.match(/\{\{[^}]+\}\}/g);
  if (unresolved) {
    throw new Error(`Unresolved placeholders: ${unresolved.join(", ")}`);
  }
  return result;
}

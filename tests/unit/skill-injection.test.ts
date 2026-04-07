import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { injectVariables } from "../../services/inject.js";

const TASK_START_PATH = join(process.cwd(), "llm/prompts/task_start.md");

const TASK_START_VARIABLES: Record<string, string> = {
  task_id: "42",
  title: "Add authentication",
  task_type: "CODING",
  status: "IN_PROGRESS",
  external_task_id: "PD-42",
  branch: "feat/auth",
  due_date: "2026-04-10T00:00:00.000Z",
  context: JSON.stringify({ id: 42, title: "Add authentication" }),
};

describe("task_start skill variable injection", () => {
  it("resolves all placeholders when given a complete variable map", () => {
    const template = readFileSync(TASK_START_PATH, "utf-8");
    const result = injectVariables(template, TASK_START_VARIABLES);

    expect(result).not.toMatch(/\{\{[^}]+\}\}/);
    expect(result).toContain("42");
    expect(result).toContain("Add authentication");
    expect(result).toContain("CODING");
    expect(result).toContain("IN_PROGRESS");
    expect(result).toContain("PD-42");
    expect(result).toContain("feat/auth");
  });

  it("contains exactly the expected placeholders and no others", () => {
    const template = readFileSync(TASK_START_PATH, "utf-8");
    const found = [...template.matchAll(/\{\{([^}]+)\}\}/g)].map((m) => m[1]);
    const expected = Object.keys(TASK_START_VARIABLES);

    expect(found.sort()).toEqual(expected.sort());
  });

  it("throws when a placeholder is not in the variable map", () => {
    const template = "Hello {{name}}";
    expect(() => injectVariables(template, {})).toThrow(
      "Unresolved placeholders: {{name}}",
    );
  });

  it("throws when variables are missing from a partial map", () => {
    const template = readFileSync(TASK_START_PATH, "utf-8");
    const partial = { task_id: "42", title: "Add authentication" };

    expect(() => injectVariables(template, partial)).toThrow(
      "Unresolved placeholders",
    );
  });
});

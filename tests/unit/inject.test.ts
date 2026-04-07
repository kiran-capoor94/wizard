import { describe, it, expect } from "vitest";
import { injectVariables } from "../../services/inject.js";

describe("injectVariables", () => {
  it("replaces all placeholders with their values", () => {
    const result = injectVariables("Hello {{name}}, your task is {{task}}", {
      name: "Kiran",
      task: "implement auth",
    });
    expect(result).toBe("Hello Kiran, your task is implement auth");
  });

  it("throws when a placeholder has no matching variable", () => {
    expect(() => injectVariables("Hello {{name}}", {})).toThrow(
      "Unresolved placeholders: {{name}}",
    );
  });

  it("throws listing all unresolved placeholders", () => {
    expect(() =>
      injectVariables("{{a}} and {{b}} and {{c}}", { a: "x" }),
    ).toThrow("Unresolved placeholders: {{b}}, {{c}}");
  });

  it("handles a template with no placeholders", () => {
    const result = injectVariables("No placeholders here.", {});
    expect(result).toBe("No placeholders here.");
  });

  it("replaces multiple occurrences of the same placeholder", () => {
    const result = injectVariables("{{x}} and {{x}}", { x: "hello" });
    expect(result).toBe("hello and hello");
  });
});

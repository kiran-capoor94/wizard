import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { prisma } from "../../data/db.js";
import { runTaskStartWorkflow } from "../../services/workflow.js";

let taskId: number;
let repoId: number;

beforeAll(async () => {
  const repo = await prisma.repo.create({
    data: { name: "wizard", url: "https://github.com/test/wizard-workflow" },
  });
  repoId = repo.id;

  const task = await prisma.task.create({
    data: {
      title: "Implement auth",
      status: "IN_PROGRESS",
      taskType: "CODING",
      externalTaskId: "PD-99",
      branch: "feat/auth",
      repoId: repoId,
      dueDate: new Date("2026-05-01T00:00:00.000Z"),
    },
  });
  taskId = task.id;
});

afterAll(async () => {
  await prisma.task.delete({ where: { id: taskId } });
  await prisma.repo.delete({ where: { id: repoId } });
});

describe("runTaskStartWorkflow", () => {
  it("returns a formatted prompt with no unresolved placeholders", async () => {
    const result = await runTaskStartWorkflow(taskId);

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.prompt).not.toMatch(/\{\{[^}]+\}\}/);
    expect(result.prompt).toContain("Implement auth");
    expect(result.prompt).toContain("CODING");
    expect(result.prompt).toContain("PD-99");
    expect(result.prompt).toContain("2026-05-01");
  });

  it("returns ok: false when task does not exist", async () => {
    const result = await runTaskStartWorkflow(999999);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toContain("not found");
  });

  it("prompt contains the full context as JSON with int ID", async () => {
    const result = await runTaskStartWorkflow(taskId);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    const contextMarker = "Context:\n";
    const contextStart = result.prompt.indexOf(contextMarker);
    expect(contextStart).toBeGreaterThan(-1);
    const jsonStr = result.prompt.slice(contextStart + contextMarker.length);
    const parsed = JSON.parse(jsonStr);
    expect(parsed.id).toBe(taskId);
    expect(typeof parsed.id).toBe("number");
    expect(parsed.title).toBe("Implement auth");
    expect(parsed.externalTaskId).toBe("PD-99");
  });
});

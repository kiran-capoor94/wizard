import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { prisma } from "../../data/db.js";
import { runTaskStartWorkflow } from "../../services/workflow.js";
import {
  createSession,
  endSession,
  getSession,
} from "../../services/session.js";
import { runPreflight } from "../../services/preflight.js";

let taskId: number;
let repoId: number;
let sessionId: number;

beforeAll(async () => {
  const repo = await prisma.repo.create({
    data: { name: "wizard", url: "https://github.com/test/wizard-contract" },
  });
  repoId = repo.id;

  const task = await prisma.task.create({
    data: {
      title: "Contract test task",
      status: "IN_PROGRESS",
      taskType: "CODING",
      externalTaskId: "PD-CONTRACT",
      branch: "feat/contract-test",
      repoId: repoId,
    },
  });
  taskId = task.id;
  sessionId = await createSession();
});

afterAll(async () => {
  await prisma.sessionTask.deleteMany({ where: { sessionId } });
  await prisma.session.delete({ where: { id: sessionId } });
  await prisma.task.delete({ where: { id: taskId } });
  await prisma.repo.delete({ where: { id: repoId } });
});

describe("Services → LLM layer contract", () => {
  it("pre-flight passes before workflow invocation", async () => {
    const result = await runPreflight();
    expect(result.ok).toBe(true);
  });

  it("workflow returns a formatted prompt — pre-flight runs internally", async () => {
    const result = await runTaskStartWorkflow(taskId);

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error(result.reason);

    // No unresolved placeholders
    expect(result.prompt).not.toMatch(/\{\{[^}]+\}\}/);
    // Task data is present — uses schema field names
    expect(result.prompt).toContain("Contract test task");
    expect(result.prompt).toContain("PD-CONTRACT");
  });

  it("session state persists — written before LLM invocation", async () => {
    const session = await getSession(sessionId);

    expect(session).not.toBeNull();
    expect(session!.id).toBe(sessionId);
    expect(typeof session!.id).toBe("number");
    expect(session!.status).toBe("ACTIVE");
  });

  it("session transitions to ENDED after endSession", async () => {
    const newSessionId = await createSession();

    await endSession(newSessionId);

    const session = await getSession(newSessionId);
    expect(session!.status).toBe("ENDED");
    expect(session!.endedAt).toBeInstanceOf(Date);

    await prisma.session.delete({ where: { id: newSessionId } });
  });
});

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { injectVariables } from "./inject.js";
import { runPreflight } from "./preflight.js";
import { lookupTask } from "./task.js";
import { buildTaskStartVariables } from "../core/workflows/task-start.js";
import {
  createWorkflowRun,
  completeWorkflowRun,
  failWorkflowRun,
} from "../data/repositories/workflow-run.js";

export type WorkflowResult =
  | { ok: true; prompt: string }
  | { ok: false; reason: string };

export async function runTaskStartWorkflow(
  taskId: number,
  sessionId?: number | null,
): Promise<WorkflowResult> {
  const preflight = await runPreflight();
  if (!preflight.ok) {
    return { ok: false, reason: `Pre-flight failed: ${preflight.reason}` };
  }

  // Create WorkflowRun without taskId FK until task existence is verified
  const runId = await createWorkflowRun({
    workflowId: "task_start",
    sessionId,
  });

  const context = await lookupTask(taskId);
  if (!context) {
    await failWorkflowRun(runId, `Task not found: ${taskId}`);
    return { ok: false, reason: `Task not found: ${taskId}` };
  }

  const template = readFileSync(
    join(process.cwd(), "llm/prompts/task_start.md"),
    "utf-8",
  );

  const variables = buildTaskStartVariables(context);
  const prompt = injectVariables(template, variables);

  await completeWorkflowRun(runId, { taskId, promptLength: prompt.length });

  return { ok: true, prompt };
}

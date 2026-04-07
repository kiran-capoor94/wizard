import { prisma } from "../db.js";

export type CreateWorkflowRunInput = {
  workflowId: string;
  sessionId?: number;
  taskId?: number;
};

export async function createWorkflowRun(
  input: CreateWorkflowRunInput,
): Promise<number> {
  const run = await prisma.workflowRun.create({
    data: {
      workflowId: input.workflowId,
      sessionId: input.sessionId ?? null,
      taskId: input.taskId ?? null,
      status: "RUNNING",
    },
  });
  return run.id;
}

export async function completeWorkflowRun(
  id: number,
  output?: unknown,
): Promise<void> {
  await prisma.workflowRun.update({
    where: { id },
    data: {
      status: "COMPLETED",
      completedAt: new Date(),
      output: output !== undefined ? (output as object) : undefined,
    },
  });
}

export async function failWorkflowRun(
  id: number,
  reason: string,
): Promise<void> {
  await prisma.workflowRun.update({
    where: { id },
    data: {
      status: "FAILED",
      completedAt: new Date(),
      output: { error: reason },
    },
  });
}

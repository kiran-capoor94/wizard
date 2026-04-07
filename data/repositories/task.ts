import { prisma } from "../db.js";
import type { TaskContext } from "../../shared/types.js";

export async function getTaskContext(
  taskId: number,
): Promise<TaskContext | null> {
  return prisma.task.findUnique({
    where: { id: taskId },
    select: {
      id: true,
      title: true,
      description: true,
      status: true,
      priority: true,
      dueDate: true,
      taskType: true,
      externalTaskId: true,
      branch: true,
      repo: {
        select: {
          id: true,
          name: true,
          url: true,
          platform: true,
        },
      },
      meeting: {
        select: {
          id: true,
          title: true,
          outline: true,
          keyPoints: true,
          krispUrl: true,
          actionItems: {
            select: {
              id: true,
              action: true,
              dueDate: true,
            },
          },
        },
      },
    },
  });
}

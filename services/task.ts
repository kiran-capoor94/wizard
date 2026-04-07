import { getTaskContext } from "../data/repositories/task.js";
import type { TaskContext } from "../shared/types.js";

export async function lookupTask(
  taskId: number,
): Promise<TaskContext | null> {
  return getTaskContext(taskId);
}

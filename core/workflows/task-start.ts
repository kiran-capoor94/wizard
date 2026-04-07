import type { TaskContext } from "../../shared/types.js";
import type { Variables } from "../../services/inject.js";

/**
 * Builds the variable map for the task_start skill template from a TaskContext.
 * This is the hardcoded workflow definition — services execute it.
 *
 * Variable map uses schema field names:
 *   external_task_id (was jiraKey), branch (was githubBranch)
 */
export function buildTaskStartVariables(context: TaskContext): Variables {
  return {
    task_id: String(context.id),
    title: context.title,
    task_type: context.taskType,
    status: context.status,
    external_task_id: context.externalTaskId ?? "none",
    branch: context.branch ?? "none",
    due_date: context.dueDate
      ? context.dueDate.toISOString().split("T")[0]
      : "none",
    context: JSON.stringify(context, null, 2),
  };
}

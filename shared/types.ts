export {
  TaskStatus,
  TaskPriority,
  TaskType,
  SessionStatus,
  WorkflowStatus,
  RepoProvider,
  NoteType,
  NoteParent,
} from "../generated/prisma/enums.js";
import type {
  TaskStatus,
  TaskPriority,
  TaskType,
  RepoProvider,
} from "../generated/prisma/enums.js";

export type Variables = Record<string, string>;

// Single source of truth for TaskStatus values in Zod schemas.
// satisfies ensures compile-time drift detection if Prisma schema changes.
export const TASK_STATUS_VALUES = ['TODO', 'IN_PROGRESS', 'DONE', 'BLOCKED'] as const satisfies readonly TaskStatus[]

export type AuditEntry = {
  fieldPath: string;
  piiType: string;       // Presidio entity_type, lowercased
  originalHash: string;  // SHA-256 hex of the original match
};

export type EmbeddingVector = number[];

export type TaskContext = {
  id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority | null;
  dueDate: Date | null;
  taskType: TaskType;
  externalTaskId: string | null;
  branch: string | null;
  repo: {
    id: number;
    name: string;
    url: string;
    platform: RepoProvider;
  } | null;
  meeting: {
    id: number;
    title: string;
    outline: string | null;
    keyPoints: string[];
    krispUrl: string | null;
    actionItems: {
      id: number;
      action: string;
      dueDate: Date | null;
    }[];
  } | null;
};

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

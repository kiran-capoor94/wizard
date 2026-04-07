import {
  createSessionRecord,
  endSessionRecord,
  findSessionById,
  attachTask,
} from "../data/repositories/session.js";

export type CreateSessionOptions = {
  meetingId?: number | null;
  createdById?: number | null;
};

export async function createSession(
  options?: CreateSessionOptions,
): Promise<number> {
  return createSessionRecord({
    meetingId: options?.meetingId,
    createdById: options?.createdById,
  });
}

export async function endSession(sessionId: number): Promise<void> {
  await endSessionRecord(sessionId);
}

export async function getSession(sessionId: number) {
  return findSessionById(sessionId);
}

export async function attachTaskToSession(
  sessionId: number,
  taskId: number,
): Promise<void> {
  await attachTask(sessionId, taskId);
}

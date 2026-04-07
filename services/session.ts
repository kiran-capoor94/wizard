import { prisma } from "../data/db.js";

export type CreateSessionOptions = {
  meetingId?: number;
  createdById?: number;
};

export async function createSession(
  options?: CreateSessionOptions,
): Promise<number> {
  const session = await prisma.session.create({
    data: {
      status: "ACTIVE",
      meetingId: options?.meetingId ?? null,
      createdById: options?.createdById ?? null,
    },
  });
  return session.id;
}

export async function endSession(sessionId: number): Promise<void> {
  await prisma.session.update({
    where: { id: sessionId },
    data: { status: "ENDED", endedAt: new Date() },
  });
}

export async function getSession(sessionId: number) {
  return prisma.session.findUnique({
    where: { id: sessionId },
    include: {
      tasks: {
        include: { task: true },
      },
    },
  });
}

export async function attachTaskToSession(
  sessionId: number,
  taskId: number,
): Promise<void> {
  await prisma.sessionTask.create({
    data: { sessionId, taskId },
  });
}

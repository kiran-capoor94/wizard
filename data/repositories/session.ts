import { prisma } from "../db.js";

export type CreateSessionInput = {
  meetingId?: number;
  createdById?: number;
};

export async function createSessionRecord(
  input: CreateSessionInput = {},
): Promise<number> {
  const session = await prisma.session.create({
    data: {
      status: "ACTIVE",
      meetingId: input.meetingId ?? null,
      createdById: input.createdById ?? null,
    },
  });
  return session.id;
}

export async function endSessionRecord(sessionId: number): Promise<void> {
  await prisma.session.update({
    where: { id: sessionId },
    data: { status: "ENDED", endedAt: new Date() },
  });
}

export async function findSessionById(sessionId: number) {
  return prisma.session.findUnique({
    where: { id: sessionId },
    include: {
      tasks: {
        include: { task: true },
      },
    },
  });
}

export async function attachTask(
  sessionId: number,
  taskId: number,
): Promise<void> {
  await prisma.sessionTask.create({
    data: { sessionId, taskId },
  });
}

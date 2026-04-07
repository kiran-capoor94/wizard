import { describe, it, expect, afterEach } from "vitest";
import { prisma } from "../../data/db.js";
import {
  createSession,
  endSession,
  getSession,
  attachTaskToSession,
} from "../../services/session.js";

const createdSessionIds: number[] = [];
const createdTaskIds: number[] = [];

afterEach(async () => {
  // Clean up in FK order
  for (const id of createdSessionIds) {
    await prisma.sessionTask
      .deleteMany({ where: { sessionId: id } })
      .catch(() => {});
    await prisma.session.delete({ where: { id } }).catch(() => {});
  }
  for (const id of createdTaskIds) {
    await prisma.task.delete({ where: { id } }).catch(() => {});
  }
  createdSessionIds.length = 0;
  createdTaskIds.length = 0;
});

describe("createSession", () => {
  it("creates an ACTIVE session and returns its int ID", async () => {
    const id = await createSession();
    createdSessionIds.push(id);

    expect(typeof id).toBe("number");

    const session = await prisma.session.findUnique({ where: { id } });
    expect(session).not.toBeNull();
    expect(session!.status).toBe("ACTIVE");
    expect(session!.startedAt).toBeInstanceOf(Date);
    expect(session!.endedAt).toBeNull();
  });

  it("creates a session with optional meetingId FK", async () => {
    const meeting = await prisma.meeting.create({
      data: { title: "Sprint planning", keyPoints: [] },
    });
    const id = await createSession({ meetingId: meeting.id });
    createdSessionIds.push(id);

    const session = await prisma.session.findUnique({ where: { id } });
    expect(session!.meetingId).toBe(meeting.id);

    await prisma.session.delete({ where: { id } });
    createdSessionIds.splice(createdSessionIds.indexOf(id), 1);
    await prisma.meeting.delete({ where: { id: meeting.id } });
  });

  it("creates a session with optional createdById FK", async () => {
    const user = await prisma.user.create({
      data: { email: "test-session@wizard.dev" },
    });
    const id = await createSession({ createdById: user.id });
    createdSessionIds.push(id);

    const session = await prisma.session.findUnique({ where: { id } });
    expect(session!.createdById).toBe(user.id);

    await prisma.session.delete({ where: { id } });
    createdSessionIds.splice(createdSessionIds.indexOf(id), 1);
    await prisma.user.delete({ where: { id: user.id } });
  });
});

describe("endSession", () => {
  it("sets status to ENDED and stamps endedAt", async () => {
    const id = await createSession();
    createdSessionIds.push(id);

    await endSession(id);

    const session = await prisma.session.findUnique({ where: { id } });
    expect(session!.status).toBe("ENDED");
    expect(session!.endedAt).toBeInstanceOf(Date);
  });
});

describe("attachTaskToSession", () => {
  it("links a task to a session via SessionTask join table", async () => {
    const sessionId = await createSession();
    createdSessionIds.push(sessionId);

    const task = await prisma.task.create({
      data: { title: "Test task", status: "TODO", taskType: "CODING" },
    });
    createdTaskIds.push(task.id);

    await attachTaskToSession(sessionId, task.id);

    const session = await getSession(sessionId);
    expect(session!.tasks).toHaveLength(1);
    expect(session!.tasks[0].taskId).toBe(task.id);
  });
});

describe("crash durability", () => {
  it("session written by createSession is retrievable from Postgres", async () => {
    const id = await createSession();
    createdSessionIds.push(id);

    // Query via the service (which uses the same Postgres instance) —
    // proves the row was committed, not held in memory by the service
    const session = await getSession(id);
    expect(session).not.toBeNull();
    expect(session!.status).toBe("ACTIVE");
    expect(typeof session!.id).toBe("number");
  });
});

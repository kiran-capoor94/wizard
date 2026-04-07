import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { PrismaClient } from "../../generated/prisma/client.js";
import { getTaskContext } from "../../data/repositories/task.js";

const prisma = new PrismaClient();

describe("Data → LLM Layer contract", () => {
  let repoId: number;
  let meetingId: number;
  let taskId: number;
  let actionItemId: number;

  beforeAll(async () => {
    const repo = await prisma.repo.create({
      data: {
        name: "sisu-universe",
        url: "https://github.com/sisu-health/sisu-universe",
        platform: "GITHUB",
      },
    });
    repoId = repo.id;

    const meeting = await prisma.meeting.create({
      data: {
        title: "Sprint Planning",
        outline: "Plan the sprint",
        keyPoints: ["Deploy auth", "Fix bug"],
        krispUrl: "https://krisp.ai/meetings/test",
      },
    });
    meetingId = meeting.id;

    const actionItem = await prisma.actionItem.create({
      data: {
        action: "Create ticket PD-42",
        dueDate: new Date("2026-04-12T00:00:00.000Z"),
        meetingId: meeting.id,
      },
    });
    actionItemId = actionItem.id;

    const task = await prisma.task.create({
      data: {
        title: "Add authentication",
        description: "Implement JWT auth",
        status: "IN_PROGRESS",
        priority: "HIGH",
        dueDate: new Date("2026-04-10T00:00:00.000Z"),
        taskType: "CODING",
        externalTaskId: "PD-42",
        branch: "feat/auth",
        repoId: repo.id,
        meetingId: meeting.id,
      },
    });
    taskId = task.id;
  });

  afterAll(async () => {
    await prisma.task.delete({ where: { id: taskId } });
    await prisma.actionItem.delete({ where: { id: actionItemId } });
    await prisma.meeting.delete({ where: { id: meetingId } });
    await prisma.repo.delete({ where: { id: repoId } });
    await prisma.$disconnect();
  });

  it("returns a TaskContext matching the seeded task exactly", async () => {
    const context = await getTaskContext(taskId);

    expect(context).not.toBeNull();
    expect(context!.id).toBe(taskId);
    expect(context!.title).toBe("Add authentication");
    expect(context!.description).toBe("Implement JWT auth");
    expect(context!.status).toBe("IN_PROGRESS");
    expect(context!.priority).toBe("HIGH");
    expect(context!.dueDate).toBeInstanceOf(Date);
    expect(context!.dueDate!.toISOString()).toBe("2026-04-10T00:00:00.000Z");
    expect(context!.taskType).toBe("CODING");
    expect(context!.externalTaskId).toBe("PD-42");
    expect(context!.branch).toBe("feat/auth");
  });

  it("returns the linked repo with all fields matching the seed", async () => {
    const context = await getTaskContext(taskId);
    const repo = context!.repo;

    expect(repo).not.toBeNull();
    expect(repo!.id).toBe(repoId);
    expect(repo!.name).toBe("sisu-universe");
    expect(repo!.url).toBe("https://github.com/sisu-health/sisu-universe");
    expect(repo!.platform).toBe("GITHUB");
  });

  it("returns null for externalTaskId when not set", async () => {
    const bare = await prisma.task.create({
      data: { title: "Bare task", status: "TODO", taskType: "INVESTIGATION" },
    });

    const context = await getTaskContext(bare.id);

    expect(context!.externalTaskId).toBeNull();
    expect(context!.externalTaskId).not.toBeUndefined();
    expect(context!.externalTaskId).not.toBe("");

    await prisma.task.delete({ where: { id: bare.id } });
  });

  it("returns the linked meeting with action items matching the seed", async () => {
    const context = await getTaskContext(taskId);
    const meeting = context!.meeting;

    expect(meeting).not.toBeNull();
    expect(meeting!.id).toBe(meetingId);
    expect(meeting!.title).toBe("Sprint Planning");
    expect(meeting!.outline).toBe("Plan the sprint");
    expect(meeting!.keyPoints).toEqual(["Deploy auth", "Fix bug"]);
    expect(meeting!.krispUrl).toBe("https://krisp.ai/meetings/test");

    expect(meeting!.actionItems).toHaveLength(1);
    expect(meeting!.actionItems[0].id).toBe(actionItemId);
    expect(meeting!.actionItems[0].action).toBe("Create ticket PD-42");
    expect(meeting!.actionItems[0].dueDate).toBeInstanceOf(Date);
    expect(meeting!.actionItems[0].dueDate!.toISOString()).toBe(
      "2026-04-12T00:00:00.000Z",
    );
  });

  it("returns null for meeting when task has none", async () => {
    const bare = await prisma.task.create({
      data: {
        title: "No meeting task",
        status: "TODO",
        taskType: "INVESTIGATION",
      },
    });

    const context = await getTaskContext(bare.id);

    expect(context!.meeting).toBeNull();

    await prisma.task.delete({ where: { id: bare.id } });
  });

  it("returns null for repo when task has none", async () => {
    const bare = await prisma.task.create({
      data: {
        title: "No repo task",
        status: "TODO",
        taskType: "INVESTIGATION",
      },
    });

    const context = await getTaskContext(bare.id);

    expect(context!.repo).toBeNull();

    await prisma.task.delete({ where: { id: bare.id } });
  });

  it("returns null when task does not exist", async () => {
    const context = await getTaskContext(999999);
    expect(context).toBeNull();
  });
});

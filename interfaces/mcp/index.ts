// interfaces/mcp/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { getTaskContext } from "../../data/repositories/task.js";
import {
  createSession,
  endSession,
  attachTaskToSession,
} from "../../services/session.js";
import { runTaskStartWorkflow } from "../../services/workflow.js";

const server = new McpServer({
  name: "wizard",
  version: "0.2.0",
});

server.tool("health", "Get health of Wizard System", {}, async () => ({
  content: [{ type: "text", text: "OK" }],
}));

server.tool(
  "get_task_context",
  "Get the full context for a task by ID. Returns task details, linked meeting with action items, repo, external task ID, and branch.",
  { task_id: z.number().int().describe("The Wizard task ID (integer)") },
  async ({ task_id }) => {
    const context = await getTaskContext(task_id);

    if (!context) {
      return {
        content: [{ type: "text", text: `Task not found: ${task_id}` }],
        isError: true,
      };
    }

    return {
      content: [{ type: "text", text: JSON.stringify(context, null, 2) }],
    };
  },
);

server.tool(
  "session_start",
  "Start a new Wizard session. Returns the session ID (int).",
  {
    meeting_id: z
      .number()
      .int()
      .optional()
      .describe("Optional meeting ID (int) to associate with the session"),
    created_by_id: z
      .number()
      .int()
      .optional()
      .describe("Optional user ID (int) of session creator"),
  },
  async ({ meeting_id, created_by_id }) => {
    const sessionId = await createSession({
      meetingId: meeting_id,
      createdById: created_by_id,
    });
    return {
      content: [{ type: "text", text: JSON.stringify({ sessionId }) }],
    };
  },
);

server.tool(
  "task_start",
  "Start work on a task within the current session. Runs pre-flight, loads context, and returns the prepared prompt.",
  {
    task_id: z.number().int().describe("The Wizard task ID (int)"),
    session_id: z.number().int().describe("The current session ID (int)"),
  },
  async ({ task_id, session_id }) => {
    await attachTaskToSession(session_id, task_id);

    const result = await runTaskStartWorkflow(task_id);
    if (!result.ok) {
      return {
        content: [{ type: "text", text: result.reason }],
        isError: true,
      };
    }

    return {
      content: [{ type: "text", text: result.prompt }],
    };
  },
);

server.tool(
  "session_end",
  "End the current Wizard session.",
  { session_id: z.number().int().describe("The session ID to end (int)") },
  async ({ session_id }) => {
    await endSession(session_id);
    return {
      content: [{ type: "text", text: `Session ${session_id} ended.` }],
    };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);

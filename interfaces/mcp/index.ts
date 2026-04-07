// interfaces/mcp/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { getTaskContext } from "../../data/repositories/task.js";

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

const transport = new StdioServerTransport();
await server.connect(transport);

// interfaces/mcp/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new McpServer({
  name: "wizard",
  version: "0.2.0",
});

server.tool("health", "Get health of Wizard System", {}, async () => ({
  content: [{ type: "text", text: "OK" }],
}));

const transport = new StdioServerTransport();
await server.connect(transport);

// integrations/notion/index.ts
import { Client } from "@notionhq/client";

export function createNotionClient(): Client {
  const auth = process.env.NOTION_API_KEY;
  if (!auth) throw new Error("NOTION_API_KEY is not set");
  return new Client({ auth });
}

export function getNotionDBByID(dBId: string) {
  const client = createNotionClient();
  return client.databases.retrieve({ database_id: dBId });
}

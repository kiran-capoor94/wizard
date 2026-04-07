import { describe, it, expect } from "vitest";
import { runPreflight } from "../../services/preflight.js";

describe("runPreflight", () => {
  it("returns ok: true when Postgres is reachable and pgvector is installed", async () => {
    // Requires: docker-compose up -d and DATABASE_URL set
    const result = await runPreflight();
    expect(result.ok).toBe(true);
  });
});

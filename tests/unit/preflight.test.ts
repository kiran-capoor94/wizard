import { describe, it, expect, vi, afterEach } from "vitest";
import { runPreflight } from "../../services/preflight.js";

vi.mock("../../data/repositories/health.js", () => ({
  checkPostgresConnectivity: vi.fn(),
  checkPgvectorInstalled: vi.fn(),
}));

import {
  checkPostgresConnectivity,
  checkPgvectorInstalled,
} from "../../data/repositories/health.js";

afterEach(() => {
  vi.resetAllMocks();
});

describe("runPreflight", () => {
  it("returns ok: true when Postgres is reachable and pgvector is installed", async () => {
    vi.mocked(checkPostgresConnectivity).mockResolvedValue(true);
    vi.mocked(checkPgvectorInstalled).mockResolvedValue(true);

    const result = await runPreflight();
    expect(result.ok).toBe(true);
  });

  it("returns ok: false with reason when Postgres is unreachable", async () => {
    vi.mocked(checkPostgresConnectivity).mockResolvedValue(false);

    const result = await runPreflight();
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toContain("Postgres unreachable");
  });

  it("returns ok: false with reason when pgvector is not installed", async () => {
    vi.mocked(checkPostgresConnectivity).mockResolvedValue(true);
    vi.mocked(checkPgvectorInstalled).mockResolvedValue(false);

    const result = await runPreflight();
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toContain("pgvector extension not installed");
  });
});

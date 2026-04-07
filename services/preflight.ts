import {
  checkPostgresConnectivity,
  checkPgvectorInstalled,
} from "../data/repositories/health.js";

export type PreflightResult = { ok: true } | { ok: false; reason: string };

/**
 * Checks that Postgres is reachable and the pgvector extension is installed.
 * Must pass before any LLM invocation.
 */
export async function runPreflight(): Promise<PreflightResult> {
  const connected = await checkPostgresConnectivity();
  if (!connected) {
    return { ok: false, reason: "Postgres unreachable" };
  }

  const hasPgvector = await checkPgvectorInstalled();
  if (!hasPgvector) {
    return { ok: false, reason: "pgvector extension not installed" };
  }

  return { ok: true };
}

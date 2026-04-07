import { prisma } from "../data/db.js";

export type PreflightResult = { ok: true } | { ok: false; reason: string };

/**
 * Checks that Postgres is reachable and the pgvector extension is installed.
 * Must pass before any LLM invocation.
 */
export async function runPreflight(): Promise<PreflightResult> {
  try {
    await prisma.$queryRaw`SELECT 1`;
  } catch (err) {
    return { ok: false, reason: `Postgres unreachable: ${String(err)}` };
  }

  const rows = await prisma.$queryRaw<{ count: bigint }[]>`
    SELECT count(*) AS count
    FROM pg_extension
    WHERE extname = 'vector'
  `;
  if (Number(rows[0].count) === 0) {
    return { ok: false, reason: "pgvector extension not installed" };
  }

  return { ok: true };
}

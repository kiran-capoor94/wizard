import { prisma } from "../db.js";

/**
 * Verifies the database connection is alive.
 * Returns true if Postgres responds, false otherwise.
 */
export async function checkPostgresConnectivity(): Promise<boolean> {
  try {
    await prisma.$queryRaw`SELECT 1`;
    return true;
  } catch {
    return false;
  }
}

/**
 * Checks whether the pgvector extension is installed in the current database.
 */
export async function checkPgvectorInstalled(): Promise<boolean> {
  const rows = await prisma.$queryRaw<{ count: bigint }[]>`
    SELECT count(*) AS count
    FROM pg_extension
    WHERE extname = 'vector'
  `;
  return Number(rows[0].count) > 0;
}

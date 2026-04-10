// data/repositories/embeddings.ts
import { prisma } from '../db.js'
import type { EmbeddingVector } from '../../shared/types.js'

/**
 * Stores a task embedding vector in the TaskEmbedding table.
 * Upserts: safe to call multiple times for the same taskId.
 * Uses vector(768) — nomic-embed-text dimensions via Ollama.
 */
export async function storeTaskEmbedding(
  taskId: number,
  embedding: EmbeddingVector
): Promise<void> {
  const vectorStr = `[${embedding.join(',')}]`

  await prisma.$executeRaw`
    INSERT INTO "TaskEmbedding" (id, "taskId", embedding, "updatedAt")
    VALUES (DEFAULT, ${taskId}, ${vectorStr}::vector, NOW())
    ON CONFLICT ("taskId")
    DO UPDATE SET embedding = ${vectorStr}::vector, "updatedAt" = NOW()
  `
}

/**
 * Computes the cosine similarity between a task's stored embedding
 * and a query vector. Returns null if the task has no embedding.
 * pgvector's <=> operator computes cosine distance; similarity = 1 - distance.
 */
export async function getCosineSimilarity(
  taskId: number,
  queryVector: EmbeddingVector
): Promise<number | null> {
  const vectorStr = `[${queryVector.join(',')}]`

  const rows = await prisma.$queryRaw<{ similarity: number }[]>`
    SELECT 1 - (embedding <=> ${vectorStr}::vector) AS similarity
    FROM "TaskEmbedding"
    WHERE "taskId" = ${taskId}
    LIMIT 1
  `

  if (rows.length === 0) return null
  return rows[0].similarity
}

/**
 * Returns the current attribution threshold from SemanticConfig.
 * Returns null if not configured — caller decides whether that is fatal.
 */
export async function getAttributionThreshold(): Promise<number | null> {
  const config = await prisma.semanticConfig.findUnique({
    where: { key: 'attribution_threshold' },
  })
  return config?.value ?? null
}

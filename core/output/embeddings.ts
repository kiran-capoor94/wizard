// core/output/embeddings.ts
import type { EmbeddingVector } from '../../shared/types.js'

const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? 'http://localhost:11434'
const EMBEDDING_MODEL = 'nomic-embed-text'
const EMBEDDING_DIMENSIONS = 768

export type { EmbeddingVector }

/**
 * Computes a 768-dimensional embedding vector for a text string.
 * Uses nomic-embed-text via Ollama's local HTTP API.
 * Throws on infrastructure failure (Ollama unreachable, wrong dimensions).
 */
export async function computeEmbedding(text: string): Promise<EmbeddingVector> {
  const response = await fetch(`${OLLAMA_BASE_URL}/api/embed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: EMBEDDING_MODEL, input: text }),
  })

  if (!response.ok) {
    throw new Error(`Ollama embedding error ${response.status}: ${await response.text()}`)
  }

  const data = await response.json() as { embeddings: number[][] }
  const embedding = data.embeddings[0]

  if (!embedding || embedding.length !== EMBEDDING_DIMENSIONS) {
    throw new Error(
      `Expected vector(${EMBEDDING_DIMENSIONS}), got ${embedding?.length ?? 0} dimensions`
    )
  }

  return embedding
}

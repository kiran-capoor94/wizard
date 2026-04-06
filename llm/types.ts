import { z } from "zod";

export interface LLMRequest<TOutput> {
  prompt: string;
  schema: z.ZodType<TOutput>;
  model?: string;
  metadata?: {
    skill?: string;
    taskType?: string;
    traceId?: string;
  };
  options?: {
    temperature?: number;
    maxTokens?: number;
    timeoutMs?: number;
  };
}

export interface LLMResponse<TOutput> {
  success: boolean;
  raw?: string;
  parsed?: TOutput;
  error?: LLMError;
  usage?: {
    inputTokens?: number;
    outputTokens?: number;
  };
}

export interface LLMCapabilities {
  jsonMode: boolean;
  tools: boolean;
  streaming: boolean;
  maxContextTokens?: number;
}

// TODO: too crude, need to expand later
export type LLMError =
  | { type: "SCHEMA_VALIDATION"; message: string }
  | { type: "PARSE_ERROR"; message: string }
  | { type: "TIMEOUT"; message: string }
  | { type: "PROVIDER_ERROR"; message: string }
  | { type: "UNSUPPORTED_CAPABILITY"; message: string };

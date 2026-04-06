import { LLMCapabilities, LLMRequest, LLMResponse } from "../types.js";
import { z } from "zod";

export interface BaseLLMAdapter {
  readonly name: string;
  readonly defaultModel: string;

  generate<TOutput>(
    request: LLMRequest<TOutput>,
  ): Promise<LLMResponse<TOutput>>;

  capabilities(model?: string): LLMCapabilities;
}

export abstract class AbstractLLMAdapter implements BaseLLMAdapter {
  abstract name: string;
  abstract defaultModel: string;

  abstract generate<TOutput>(
    request: LLMRequest<TOutput>,
  ): Promise<LLMResponse<TOutput>>;

  abstract capabilities(model?: string): LLMCapabilities;

  protected safeParse<T>(raw: string): LLMResponse<T> {
    const cleaned = raw
      .trim()
      .replace(/^```(?:json)?\n?/m, "")
      .replace(/\n?```$/m, "");
    try {
      const parsed = JSON.parse(cleaned);
      return { success: true, raw, parsed };
    } catch {
      return {
        success: false,
        raw: raw,
        error: { type: "PARSE_ERROR", message: "Invalid JSON output" },
      };
    }
  }

  protected validate<TOutput>(
    schema: z.ZodType<TOutput>,
    data: unknown,
  ): LLMResponse<TOutput> {
    const result = schema.safeParse(data);

    if (!result.success) {
      return {
        success: false,
        error: {
          type: "SCHEMA_VALIDATION",
          message: result.error.message,
        },
      };
    }

    return {
      success: true,
      parsed: result.data,
    };
  }
}

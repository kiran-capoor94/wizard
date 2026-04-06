import { LLMCapabilities, LLMRequest, LLMResponse } from "../types.js";
import { AbstractLLMAdapter } from "./base.js";
import ollama from "ollama";

export class OllamaAdapter extends AbstractLLMAdapter {
  name = "ollama";
  defaultModel = "gemma4:latest-16k";

  capabilities(model?: string): LLMCapabilities {
    // TODO: expand later, keep naive for now
    return {
      jsonMode: model?.includes("json") ?? false,
      tools: model?.includes("tool") ?? false,
      streaming: model?.includes("streaming") ?? false,
    };
  }

  async generate<TOutput>(
    request: LLMRequest<TOutput>,
  ): Promise<LLMResponse<TOutput>> {
    const model: string = request.model || this.defaultModel;
    const capabilities = this.capabilities(model);

    let finalPrompt = request.prompt;

    if (!capabilities.jsonMode) {
      finalPrompt += `
      Return ONLY valid JSON matching this schema:
      ${JSON.stringify(request.schema.toJSONSchema())}`;
    }

    try {
      //TODO: timeoutMs is not supported by the Ollama SDK for non-streaming calls
      //TODO: add eval_count & prompt_eval_count to map evals
      const response = await ollama.chat({
        model,
        messages: [{ role: "user", content: finalPrompt }],
        options: {
          temperature: request.options?.temperature,
          num_predict: request.options?.maxTokens,
        },
      });

      const raw = response.message.content;
      const { success, parsed, error } = this.safeParse<TOutput>(raw);

      if (!success) {
        return { success, raw, error };
      }

      return {
        ...this.validate(request.schema, parsed),
        raw,
        usage: {
          inputTokens: response.prompt_eval_count,
          outputTokens: response.eval_count,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: {
          type: "PROVIDER_ERROR",
          message: `Ollama request failed ${request.metadata?.traceId ? ` [traceId=${request.metadata.traceId}]` : ""}: ${error instanceof Error ? error.message : String(error)}`,
        },
      };
    }
  }
}

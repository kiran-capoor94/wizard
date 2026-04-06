import { describe, it, expect, vi, beforeEach } from "vitest";
import { z } from "zod";
import { OllamaAdapter } from "../../llm/adapters/ollama.js";

vi.mock("ollama", () => ({
  default: {
    chat: vi.fn(),
  },
}));

import ollama from "ollama";

const schema = z.object({
  name: z.string(),
  score: z.number(),
});

type Output = z.infer<typeof schema>;

const adapter = new OllamaAdapter();
const request = { prompt: "Extract the name and score.", schema };

function mockChat(content: string) {
  vi.mocked(ollama.chat).mockResolvedValueOnce({
    message: { role: "assistant", content },
    prompt_eval_count: 10,
    eval_count: 5,
  } as any);
}

describe("OllamaAdapter — Step 0 contract", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns typed output and preserves raw when JSON matches schema", async () => {
    const raw = '{"name":"Alice","score":42}';
    mockChat(raw);

    const result = await adapter.generate<Output>(request);

    expect(result.success).toBe(true);
    expect(result.parsed).toEqual({ name: "Alice", score: 42 });
    expect(result.raw).toBe(raw);
  });

  it("returns PARSE_ERROR and preserves raw when model output is not valid JSON", async () => {
    const raw = "Sorry, I cannot do that.";
    mockChat(raw);

    const result = await adapter.generate<Output>(request);

    expect(result.success).toBe(false);
    expect(result.error?.type).toBe("PARSE_ERROR");
    expect(result.raw).toBe(raw);
    expect(result.parsed).toBeUndefined();
  });

  it("returns PROVIDER_ERROR and does not throw when ollama.chat rejects", async () => {
    vi.mocked(ollama.chat).mockRejectedValueOnce(
      new Error("connection refused"),
    );

    const result = await adapter.generate<Output>(request);

    expect(result.success).toBe(false);
    expect(result.error?.type).toBe("PROVIDER_ERROR");
  });

  it("returns SCHEMA_VALIDATION error and preserves raw when JSON does not match schema", async () => {
    const raw = '{"name":"Alice","score":"not-a-number"}';
    mockChat(raw);

    const result = await adapter.generate<Output>(request);

    expect(result.success).toBe(false);
    expect(result.error?.type).toBe("SCHEMA_VALIDATION");
    expect(result.raw).toBe(raw);
    expect(result.parsed).toBeUndefined();
  });
});

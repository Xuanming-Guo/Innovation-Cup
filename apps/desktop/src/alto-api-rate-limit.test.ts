import { afterEach, describe, expect, it, vi } from "vitest";

import { AltoApiError, altoRequest } from "./alto-api";

describe("ALTO API rate-limit responses", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("preserves Retry-After on a safe typed command error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      headers: new Headers({ "Retry-After": "17" }),
      json: vi.fn().mockResolvedValue({
        detail: "This demo has received too many new AI requests. Retry in 17 seconds.",
      }),
    }));

    const request = altoRequest(
      { apiOrigin: "https://api.example.invalid", companyId: "company", accessToken: "token" },
      "/assistant/threads/thread/messages",
      { method: "POST", body: { content: "hello" }, idempotencyKey: "stable-command-key" },
    );

    await expect(request).rejects.toMatchObject<Partial<AltoApiError>>({
      status: 429,
      retryAfterSeconds: 17,
      message: "This demo has received too many new AI requests. Retry in 17 seconds.",
    });
  });
});

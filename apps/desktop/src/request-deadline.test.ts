import { afterEach, describe, expect, it, vi } from "vitest";
import { altoRequest } from "./alto-api";
import { COMMAND_TIMEOUT_MS, READ_TIMEOUT_MS, RequestTimeoutError, withRequestDeadline } from "./request-deadline";

describe("bounded requests", () => {
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("bounds response-body parsing, not only response headers", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => new Promise(() => undefined) }));
    const request = altoRequest({ apiOrigin: "https://api.example.invalid", companyId: "company", accessToken: "token" }, "/workspace");
    const assertion = expect(request).rejects.toBeInstanceOf(RequestTimeoutError);
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
    await assertion;
  });

  it("does not dispatch an already cancelled read", async () => {
    const controller = new AbortController();
    controller.abort();
    const operation = vi.fn();
    await expect(withRequestDeadline(operation, { signal: controller.signal })).rejects.toMatchObject({ name: "AbortError" });
    expect(operation).not.toHaveBeenCalled();
  });

  it("bounds a write without retrying it or claiming it failed to commit", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockImplementation(() => new Promise(() => undefined));
    vi.stubGlobal("fetch", fetch);
    const request = altoRequest({ apiOrigin: "https://api.example.invalid", companyId: "company", accessToken: "token" }, "/action", { method: "POST", body: {}, idempotencyKey: "fixed-key" });
    const assertion = expect(request).rejects.toThrow("may have completed");
    await vi.advanceTimersByTimeAsync(COMMAND_TIMEOUT_MS);
    await assertion;
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[1].headers["Idempotency-Key"]).toBe("fixed-key");
  });
});

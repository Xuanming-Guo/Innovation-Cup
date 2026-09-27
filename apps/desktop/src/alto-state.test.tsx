import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useResource } from "./alto-state";
import type { AltoApiContext } from "./alto-api";
import { READ_TIMEOUT_MS } from "./request-deadline";
import { clearAltoResourceCache, invalidateAltoAccountResources, RESOURCE_CACHE_TTL_MS } from "./alto-resource-cache";
import { altoRequest } from "./alto-api";

const api: AltoApiContext = { apiOrigin: "https://api.example.invalid", companyId: "company-1", accessToken: "user-1-token", demoRunId: "run-1", demoActorSessionId: "actor-1" };
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}
async function flush() { await act(async () => { await Promise.resolve(); }); }

describe("authorised resource lifecycle", () => {
  afterEach(() => { cleanup(); clearAltoResourceCache(); vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("does not restart a pending read for an equivalent API context", async () => {
    let complete!: (response: Response) => void;
    const fetch = vi.fn<typeof globalThis.fetch>(() => new Promise<Response>((resolve) => { complete = resolve; }));
    vi.stubGlobal("fetch", fetch);
    const { result, rerender } = renderHook(({ context }) => useResource<{ title: string }>(context, "/workspace"), { initialProps: { context: api } });
    await flush();
    rerender({ context: { ...api } });
    await flush();
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => complete(json({ title: "Workspace" })));
    expect(result.current.data).toEqual({ title: "Workspace" });
    expect(result.current.loading).toBe(false);
  });

  it.each(["companyId", "accessToken", "demoRunId", "demoActorSessionId"] as const)("hides prior private data immediately when %s changes", async (field) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ private: "old scope" })).mockImplementation(() => new Promise(() => undefined)));
    const { result, rerender } = renderHook(({ context }) => useResource(context, "/workspace"), { initialProps: { context: api } });
    await flush();
    expect(result.current.data).toEqual({ private: "old scope" });
    rerender({ context: { ...api, [field]: "new-scope" } });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
  });

  it("ignores an old response even if the cancelled transport ignores abort", async () => {
    let completeOld!: (response: Response) => void;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>((resolve) => { completeOld = resolve; })).mockResolvedValueOnce(json({ actor: "new" }));
    vi.stubGlobal("fetch", fetch);
    const { result, rerender } = renderHook(({ context }) => useResource(context, "/workspace"), { initialProps: { context: api } });
    await flush();
    rerender({ context: { ...api, demoActorSessionId: "new-actor" } });
    await flush();
    await act(async () => completeOld(json({ actor: "old" })));
    expect(result.current.data).toEqual({ actor: "new" });
  });

  it("ends an unresponsive read and supports an explicit retry", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockImplementationOnce(() => new Promise(() => undefined)).mockResolvedValueOnce(json({ ready: true }));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useResource(api, "/workspace"));
    await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS); });
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toContain("timed out");
    expect(fetch.mock.calls[0]?.[1].signal.aborted).toBe(true);
    act(() => result.current.refresh());
    await flush();
    expect(result.current.data).toEqual({ ready: true });
    expect(result.current.error).toBeNull();
  });

  it("retains denied-scope status for explicit recovery without downgrading scope", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ detail: "The selected actor session has expired." }, 403));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useResource(api, "/workspace"));
    await flush();
    expect(result.current.errorStatus).toBe(403);
    expect(result.current.data).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[1].headers["X-Demo-Actor-Session-ID"]).toBe("actor-1");
  });

  it("restores a tab immediately and refreshes it in the background", async () => {
    const context = { ...api, authUserId: "user-1" };
    const fetch = vi.fn().mockResolvedValueOnce(json({ title: "Cached project" })).mockImplementationOnce(() => new Promise(() => undefined));
    vi.stubGlobal("fetch", fetch);
    const first = renderHook(() => useResource(context, "/projects"));
    await flush();
    first.unmount();
    const second = renderHook(() => useResource(context, "/projects"));
    expect(second.result.current.data).toEqual({ title: "Cached project" });
    expect(second.result.current.loading).toBe(false);
    expect(second.result.current.refreshing).toBe(true);
    expect(second.result.current.isStale).toBe(true);
    await flush();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("deduplicates simultaneous readers without cancelling another subscriber", async () => {
    const context = { ...api, authUserId: "user-1" };
    let complete!: (response: Response) => void;
    const fetch = vi.fn(() => new Promise<Response>((resolve) => { complete = resolve; }));
    vi.stubGlobal("fetch", fetch);
    const first = renderHook(() => useResource(context, "/projects"));
    const second = renderHook(() => useResource(context, "/projects"));
    await flush();
    first.unmount();
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => complete(json({ project: "shared read" })));
    expect(second.result.current.data).toEqual({ project: "shared read" });
  });

  it.each(["authUserId", "companyId", "demoRunId", "demoActorSessionId"] as const)("never restores another %s cache", async (field) => {
    const context = { ...api, authUserId: "user-1" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ private: "first scope" })).mockImplementation(() => new Promise(() => undefined)));
    const first = renderHook(() => useResource(context, "/projects"));
    await flush();
    first.unmount();
    const second = renderHook(() => useResource({ ...context, [field]: "other" }, "/projects"));
    expect(second.result.current.data).toBeNull();
  });

  it("keeps cached data on transient errors but removes it on denied access", async () => {
    const context = { ...api, authUserId: "user-1" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ title: "Cached" })).mockRejectedValueOnce(new TypeError("Network unavailable")).mockResolvedValueOnce(json({ detail: "Actor expired" }, 403)));
    const { result } = renderHook(() => useResource(context, "/workspace"));
    await flush();
    act(() => result.current.refresh());
    await flush();
    expect(result.current.data).toEqual({ title: "Cached" });
    expect(result.current.isStale).toBe(true);
    expect(result.current.error).toBe("Network unavailable");
    act(() => result.current.refresh());
    await flush();
    expect(result.current.data).toBeNull();
    expect(result.current.errorStatus).toBe(403);
  });

  it("clears cached private views at the session boundary", async () => {
    const context = { ...api, authUserId: "user-1" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ title: "Cached" })).mockImplementation(() => new Promise(() => undefined)));
    const first = renderHook(() => useResource(context, "/projects"));
    await flush();
    first.unmount();
    clearAltoResourceCache();
    const second = renderHook(() => useResource(context, "/projects"));
    expect(second.result.current.data).toBeNull();
  });

  it("invalidates cached scope after a successful command without repeating the write", async () => {
    const context = { ...api, authUserId: "user-1" };
    const fetch = vi.fn().mockResolvedValueOnce(json({ value: "before" })).mockResolvedValueOnce(json({ saved: true })).mockResolvedValueOnce(json({ value: "after" }));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useResource(context, "/projects"));
    await flush();
    await act(async () => { await altoRequest(context, "/action", { method: "POST", body: {} }); });
    expect(result.current.data).toEqual({ value: "after" });
    expect(fetch.mock.calls.filter((call) => call[1]?.method === "POST")).toHaveLength(1);
  });

  it("keeps same-user cached data during token rotation while cancelling the older read", async () => {
    const context = { ...api, authUserId: "user-1" };
    const fetch = vi.fn().mockResolvedValueOnce(json({ title: "Cached" })).mockImplementation(() => new Promise(() => undefined));
    vi.stubGlobal("fetch", fetch);
    const { result, rerender } = renderHook(({ context: current }) => useResource(current, "/projects"), { initialProps: { context } });
    await flush();
    rerender({ context: { ...context, accessToken: "refreshed-token" } });
    expect(result.current.data).toEqual({ title: "Cached" });
    expect(result.current.loading).toBe(false);
    await flush();
    expect(fetch.mock.calls[1]?.[1].headers.Authorization).toBe("Bearer refreshed-token");
  });

  it("expires retained tab data after the bounded cache lifetime", async () => {
    vi.useFakeTimers();
    const context = { ...api, authUserId: "user-1" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ title: "Expired" })).mockImplementation(() => new Promise(() => undefined)));
    const first = renderHook(() => useResource(context, "/projects"));
    await flush();
    first.unmount();
    await vi.advanceTimersByTimeAsync(RESOURCE_CACHE_TTL_MS + 1);
    const second = renderHook(() => useResource(context, "/projects"));
    expect(second.result.current.data).toBeNull();
    expect(second.result.current.loading).toBe(true);
  });

  it("removes a refused command's cached authority without retrying the command", async () => {
    const context = { ...api, authUserId: "user-1" };
    const fetch = vi.fn().mockResolvedValueOnce(json({ private: "Prior actor" })).mockResolvedValueOnce(json({ detail: "Actor session expired" }, 403));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useResource(context, "/workspace"));
    await flush();
    await act(async () => { await expect(altoRequest(context, "/action", { method: "POST" })).rejects.toThrow("Actor session expired"); });
    expect(result.current.data).toBeNull();
    expect(result.current.errorStatus).toBe(403);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("coalesces repeated polling without resetting a slow request's deadline", async () => {
    vi.useFakeTimers();
    const context = { ...api, authUserId: "user-1" };
    const fetch = vi.fn().mockImplementation(() => new Promise(() => undefined));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useResource(context, "/planning-requests/pending"));
    await flush();
    for (let elapsed = 0; elapsed < READ_TIMEOUT_MS; elapsed += 2500) {
      act(() => result.current.refresh());
      await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    }
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toContain("timed out");
  });

  it("does not abort a slow graph read during authorised account refreshes", async () => {
    const context = { ...api, authUserId: "user-1" };
    let complete!: (response: Response) => void;
    const fetch = vi.fn<typeof globalThis.fetch>(() => new Promise<Response>((resolve) => { complete = resolve; }));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useResource<{ graph: string }>(context, "/projects/project-1/graph"));
    await flush();

    act(() => {
      invalidateAltoAccountResources(context);
      invalidateAltoAccountResources(context);
    });

    expect(fetch).toHaveBeenCalledTimes(1);
    expect((fetch.mock.calls[0]?.[1]?.signal as AbortSignal).aborted).toBe(false);
    await act(async () => complete(json({ graph: "ready" })));
    expect(result.current.data).toEqual({ graph: "ready" });
    expect(result.current.loading).toBe(false);
  });
});

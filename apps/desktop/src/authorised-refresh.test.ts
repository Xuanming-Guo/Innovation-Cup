import type { SupabaseClient } from "@supabase/supabase-js";
import { afterEach, describe, expect, it, vi } from "vitest";

import { isAuthorisedRefreshPayload, startAuthorisedRefresh } from "./authorised-refresh";

class FakeChannel {
  broadcast: ((message: { payload: unknown }) => void) | null = null;
  status: ((status: string) => void) | null = null;

  on(_kind: string, _filter: object, callback: (message: { payload: unknown }) => void) {
    this.broadcast = callback;
    return this;
  }

  subscribe(callback: (status: string) => void) {
    this.status = callback;
    return this;
  }
}

function fakeClient(channel: FakeChannel) {
  return {
    channel: vi.fn().mockReturnValue(channel),
    removeChannel: vi.fn().mockResolvedValue("ok"),
  } as unknown as SupabaseClient;
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

describe("private authorised refresh", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("accepts only the constant non-confidential payload", () => {
    expect(
      isAuthorisedRefreshPayload({ schema_version: 1, type: "authorised_state_stale" }),
    ).toBe(true);
    expect(
      isAuthorisedRefreshPayload({
        schema_version: 1,
        type: "authorised_state_stale",
        plan_id: "secret",
      }),
    ).toBe(false);
    expect(isAuthorisedRefreshPayload({ schema_version: 2, type: "authorised_state_stale" })).toBe(
      false,
    );
  });

  it("uses a private user topic and refetches through the authorised callback", async () => {
    const channel = new FakeChannel();
    const client = fakeClient(channel);
    const refetch = vi.fn().mockResolvedValue(undefined);

    const stop = startAuthorisedRefresh({ client, userId: "user-1", refetch });
    await flush();
    expect(client.channel).toHaveBeenCalledWith("user:user-1", { config: { private: true } });
    expect(refetch).toHaveBeenCalledTimes(1);

    channel.broadcast?.({ payload: { schema_version: 1, type: "authorised_state_stale" } });
    await flush();
    expect(refetch).toHaveBeenCalledTimes(2);

    channel.broadcast?.({
      payload: { schema_version: 1, type: "authorised_state_stale", task_id: "secret" },
    });
    await flush();
    expect(refetch).toHaveBeenCalledTimes(2);
    stop();
    expect(client.removeChannel).toHaveBeenCalledTimes(1);
  });

  it("refetches after reconnect, focus and network recovery", async () => {
    const channel = new FakeChannel();
    const refetch = vi.fn().mockResolvedValue(undefined);
    const stop = startAuthorisedRefresh({ client: fakeClient(channel), userId: "user-1", refetch });
    await flush();

    channel.status?.("SUBSCRIBED");
    await flush();
    expect(refetch).toHaveBeenCalledTimes(1);
    channel.status?.("CHANNEL_ERROR");
    channel.status?.("SUBSCRIBED");
    await flush();
    expect(refetch).toHaveBeenCalledTimes(2);
    window.dispatchEvent(new Event("focus"));
    await flush();
    expect(refetch).toHaveBeenCalledTimes(3);
    window.dispatchEvent(new Event("online"));
    await flush();

    expect(refetch).toHaveBeenCalledTimes(4);
    stop();
  });

  it("keeps authorised refetch fallback when Realtime channel setup fails", async () => {
    const client = {
      channel: vi.fn(() => { throw new Error("websocket unavailable"); }),
      removeChannel: vi.fn(),
    } as unknown as SupabaseClient;
    const refetch = vi.fn().mockResolvedValue(undefined);

    const stop = startAuthorisedRefresh({ client, userId: "user-1", refetch });
    await flush();

    expect(refetch).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new Event("focus"));
    await flush();
    expect(refetch).toHaveBeenCalledTimes(2);

    stop();
    expect(client.removeChannel).not.toHaveBeenCalled();
  });
});

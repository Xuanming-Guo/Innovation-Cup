import type { RealtimeChannel, SupabaseClient } from "@supabase/supabase-js";

export const AUTHORISED_REFRESH_PAYLOAD = {
  schema_version: 1,
  type: "authorised_state_stale",
} as const;

export function isAuthorisedRefreshPayload(value: unknown): boolean {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return (
    keys.length === 2 &&
    keys[0] === "schema_version" &&
    keys[1] === "type" &&
    record.schema_version === AUTHORISED_REFRESH_PAYLOAD.schema_version &&
    record.type === AUTHORISED_REFRESH_PAYLOAD.type
  );
}

interface AuthorisedRefreshOptions {
  client: SupabaseClient;
  userId: string;
  refetch: () => Promise<void>;
  intervalMs?: number;
  onError?: () => void;
}

export function startAuthorisedRefresh({
  client,
  userId,
  refetch,
  intervalMs = 60_000,
  onError = () => undefined,
}: AuthorisedRefreshOptions): () => void {
  let stopped = false;
  let running = false;
  let pending = false;
  let subscribedOnce = false;

  const requestRefetch = () => {
    if (stopped) return;
    if (running) {
      pending = true;
      return;
    }
    running = true;
    void (async () => {
      do {
        pending = false;
        try {
          await refetch();
        } catch {
          onError();
        }
      } while (pending && !stopped);
      running = false;
    })();
  };

  let channel: RealtimeChannel | null = null;
  try {
    channel = client.channel(`user:${userId}`, { config: { private: true } });
    channel
      .on("broadcast", { event: "refresh" }, (message) => {
        if (isAuthorisedRefreshPayload(message.payload)) requestRefetch();
      })
      .subscribe((status) => {
        if (status !== "SUBSCRIBED") return;
        if (subscribedOnce) requestRefetch();
        subscribedOnce = true;
      });
  } catch {
    // Realtime only accelerates authorised refetches. Initial, focus, online and
    // interval refetches remain available when channel setup is unsupported.
  }

  const onFocus = () => requestRefetch();
  const onOnline = () => requestRefetch();
  window.addEventListener("focus", onFocus);
  window.addEventListener("online", onOnline);
  const interval = window.setInterval(requestRefetch, intervalMs);
  requestRefetch();

  return () => {
    stopped = true;
    window.clearInterval(interval);
    window.removeEventListener("focus", onFocus);
    window.removeEventListener("online", onOnline);
    if (channel !== null) void client.removeChannel(channel);
  };
}

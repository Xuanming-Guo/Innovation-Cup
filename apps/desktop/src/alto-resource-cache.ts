import type { AltoApiContext } from "./alto-api";

export const RESOURCE_CACHE_TTL_MS = 5 * 60_000;
const MAX_ENTRIES = 80;
export interface ResourceSnapshot<T = unknown> {
  data: T | null;
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
  isStale: boolean;
}
interface Entry {
  scope: string;
  snapshot: ResourceSnapshot;
  updatedAt: number;
  listeners: Set<(snapshot: ResourceSnapshot) => void>;
  controller: AbortController | null;
  loader: ((signal: AbortSignal) => Promise<unknown>) | null;
  accessToken: string | null;
}
const entries = new Map<string, Entry>();
const activityListeners = new Set<() => void>();
const notifyActivity = () => { for (const listener of activityListeners) listener(); };
const empty = (): ResourceSnapshot => ({ data: null, loading: true, error: null, errorStatus: null, isStale: false });

export function resourceScope(context: AltoApiContext): string | null {
  // Never cache private data without an explicit authenticated account identity.
  // Tokens rotate and must never become cache keys or browser-persisted data.
  return context.authUserId ? JSON.stringify([context.authUserId, context.apiOrigin, context.companyId, context.demoRunId ?? null, context.demoActorSessionId ?? null]) : null;
}
export function resourceCacheKey(context: AltoApiContext, path: string): string | null {
  const scope = resourceScope(context);
  return scope ? JSON.stringify([scope, path]) : null;
}
export function readAltoResourceCache(key: string | null): ResourceSnapshot | null {
  const entry = key ? entries.get(key) : undefined;
  if (!entry || (entry.updatedAt && Date.now() - entry.updatedAt > RESOURCE_CACHE_TTL_MS)) return null;
  return entry.snapshot;
}
function publish(entry: Entry, snapshot: ResourceSnapshot) {
  entry.snapshot = snapshot;
  for (const listener of entry.listeners) listener(snapshot);
  notifyActivity();
}
function prune() {
  for (const [key, entry] of entries) {
    if (entry.listeners.size === 0 && (entries.size >= MAX_ENTRIES || Date.now() - entry.updatedAt > RESOURCE_CACHE_TTL_MS)) {
      entry.controller?.abort();
      entries.delete(key);
    }
  }
}
function load(entry: Entry, force = false) {
  if (!entry.loader || (!force && entry.controller)) return;
  entry.controller?.abort();
  const controller = new AbortController();
  entry.controller = controller;
  const cached = Date.now() - entry.updatedAt <= RESOURCE_CACHE_TTL_MS ? entry.snapshot.data : null;
  publish(entry, { data: cached, loading: true, error: null, errorStatus: null, isStale: cached !== null });
  void entry.loader(controller.signal).then((data) => {
    if (controller.signal.aborted || entry.controller !== controller) return;
    entry.updatedAt = Date.now();
    publish(entry, { data, loading: false, error: null, errorStatus: null, isStale: false });
  }).catch((error: unknown) => {
    if (controller.signal.aborted || entry.controller !== controller) return;
    const status = typeof error === "object" && error !== null && "status" in error && typeof error.status === "number" ? error.status : null;
    const denied = status !== null && [401, 403, 404].includes(status);
    if (status === 401 || status === 403) {
      // A refused authority must not survive navigation through another cached view.
      for (const other of entries.values()) {
        if (other === entry || other.scope !== entry.scope) continue;
        other.controller?.abort();
        other.controller = null;
        other.updatedAt = 0;
        publish(other, { data: null, loading: false, error: "Workspace access changed. Retry or choose an available scope.", errorStatus: status, isStale: false });
      }
    }
    const data = denied ? null : entry.snapshot.data;
    publish(entry, { data, loading: false, error: error instanceof Error ? error.message : "Could not load this view.", errorStatus: status, isStale: data !== null });
  }).finally(() => { if (entry.controller === controller) entry.controller = null; });
}
export function subscribeAltoResource(
  key: string,
  scope: string,
  accessToken: string,
  loader: (signal: AbortSignal) => Promise<unknown>,
  listener: (snapshot: ResourceSnapshot) => void,
): () => void {
  prune();
  let entry = entries.get(key);
  if (!entry) {
    entry = { scope, snapshot: empty(), updatedAt: 0, listeners: new Set(), controller: null, loader: null, accessToken: null };
    entries.set(key, entry);
  }
  const changedToken = entry.accessToken !== null && entry.accessToken !== accessToken;
  entry.loader = loader;
  entry.accessToken = accessToken;
  entry.listeners.add(listener);
  listener(entry.snapshot);
  load(entry, changedToken);
  return () => {
    entry.listeners.delete(listener);
    if (entry.listeners.size === 0) {
      entry.controller?.abort();
      entry.controller = null;
      entry.loader = null;
      entry.accessToken = null;
      entry.snapshot = { ...entry.snapshot, loading: false, isStale: entry.snapshot.data !== null };
      notifyActivity();
    }
  };
}
export function refreshAltoResource(key: string) {
  const entry = entries.get(key);
  // Polling/focus must not continually abort a slow read before its deadline.
  // Mutations use explicit invalidation below to cancel genuinely obsolete reads.
  if (entry) load(entry);
}
export function rejectAltoResourceScope(context: AltoApiContext, status: number, message: string) {
  const scope = resourceScope(context);
  if (!scope || (status !== 401 && status !== 403)) return;
  for (const entry of entries.values()) {
    if (entry.scope !== scope) continue;
    entry.controller?.abort();
    entry.controller = null;
    entry.updatedAt = 0;
    publish(entry, { data: null, loading: false, error: message, errorStatus: status, isStale: false });
  }
}
export function invalidateAltoResourceCache(context: AltoApiContext) {
  const scope = resourceScope(context);
  if (!scope) return;
  for (const entry of entries.values()) {
    if (entry.scope !== scope) continue;
    if (entry.listeners.size) load(entry, true);
    else entry.snapshot = { ...entry.snapshot, isStale: true };
  }
}
export function invalidateAltoAccountResources(context: { authUserId: string; apiOrigin: string; companyId: string }) {
  for (const entry of entries.values()) {
    const [userId, apiOrigin, companyId] = JSON.parse(entry.scope) as string[];
    if (userId !== context.authUserId || apiOrigin !== context.apiOrigin || companyId !== context.companyId) continue;
    // Authorised-state refreshes are hints that account data may have changed.
    // Keep an initial/slow read alive instead of repeatedly aborting it on focus,
    // realtime or interval refreshes. A completed entry still reloads normally.
    if (entry.listeners.size) load(entry);
    else entry.snapshot = { ...entry.snapshot, isStale: true };
  }
}
export function clearAltoResourceCache(refetchActive = false) {
  for (const [key, entry] of entries) {
    entry.controller?.abort();
    entry.controller = null;
    entry.updatedAt = 0;
    publish(entry, empty());
    if (refetchActive && entry.listeners.size) load(entry);
    else entries.delete(key);
  }
  notifyActivity();
}
export function subscribeAltoResourceActivity(listener: () => void): () => void {
  activityListeners.add(listener);
  return () => { activityListeners.delete(listener); };
}
export function getAltoResourceActivity(scope: string | null): "idle" | "refreshing" | "stale" {
  if (!scope) return "idle";
  let refreshing = false;
  for (const entry of entries.values()) {
    if (entry.scope !== scope || !entry.listeners.size || entry.snapshot.data === null) continue;
    if (entry.snapshot.isStale && !entry.snapshot.loading) return "stale";
    refreshing ||= entry.snapshot.loading;
  }
  return refreshing ? "refreshing" : "idle";
}

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { AltoApiError, altoRequest, type AltoApiContext } from "./alto-api";
import { getAltoResourceActivity, readAltoResourceCache, refreshAltoResource, resourceCacheKey, resourceScope, subscribeAltoResource, subscribeAltoResourceActivity, type ResourceSnapshot } from "./alto-resource-cache";
export function initials(name: string): string { return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "?"; }
export function humanize(value: string): string { return value.replaceAll("_", " "); }
export function formatDate(value: string | null | undefined, options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" }, timezone?: string): string {
    if (!value || Number.isNaN(new Date(value).getTime()))
        return "Not set";
    return new Intl.DateTimeFormat(undefined, { ...options, ...(timezone ? { timeZone: timezone } : {}) }).format(new Date(value));
}
export function dateTime(value: string | null | undefined, timezone?: string): string { return formatDate(value, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }, timezone); }
export function navigate(path: string) { window.location.hash = path; }
export function useRoute() {
    const [hash, setHash] = useState(() => window.location.hash.slice(1) || "/home");
    useEffect(() => { const update = () => setHash(window.location.hash.slice(1) || "/home"); window.addEventListener("hashchange", update); return () => window.removeEventListener("hashchange", update); }, []);
    const [path = "/home", query = ""] = hash.split("?");
    return { path, query: new URLSearchParams(query) };
}
export function useResource<T>(api: AltoApiContext | undefined, path: string | null) {
    const { apiOrigin, companyId, accessToken, demoRunId, demoActorSessionId, authUserId } = api ?? {};
    // Notification refreshes can recreate api without changing its authority.
    // Only actual scope/token changes should cancel a read already in flight.
    const requestContext = useMemo<AltoApiContext | undefined>(() =>
        apiOrigin !== undefined && companyId !== undefined && accessToken !== undefined
            ? { apiOrigin, companyId, accessToken, demoRunId, demoActorSessionId, authUserId }
            : undefined,
    [apiOrigin, companyId, accessToken, demoRunId, demoActorSessionId, authUserId]);
    const cacheKey = requestContext && path ? resourceCacheKey(requestContext, path) : null;
    const scopeKey = cacheKey ?? (requestContext && path ? JSON.stringify([apiOrigin, companyId, accessToken, demoRunId, demoActorSessionId, path]) : null);
    const initialSnapshot = (): ResourceSnapshot<T> => (readAltoResourceCache(cacheKey) as ResourceSnapshot<T> | null) ?? { data: null, loading: Boolean(requestContext && path), error: null, errorStatus: null, isStale: false };
    const [state, setState] = useState<ResourceSnapshot<T> & { scopeKey: string | null }>(() => ({ scopeKey, ...initialSnapshot() }));
    const [revision, setRevision] = useState(0);
    const refresh = useCallback(() => { if (cacheKey) refreshAltoResource(cacheKey); else setRevision((value) => value + 1); }, [cacheKey]);
    useEffect(() => {
        const controller = new AbortController();
        if (!requestContext || !path)
            return;
        if (cacheKey) {
            return subscribeAltoResource(cacheKey, resourceScope(requestContext)!, requestContext.accessToken,
                (signal) => altoRequest<T>(requestContext, path, { signal }),
                (snapshot) => setState({ scopeKey, ...snapshot as ResourceSnapshot<T> }),
            );
        }
        // Scope-tag the response as well as aborting the previous read. Consumers
        // must not render old private data even for the render before effect cleanup.
        void Promise.resolve().then(() => {
            if (controller.signal.aborted) return;
            setState((current) => ({ scopeKey, data: current.scopeKey === scopeKey ? current.data : null, loading: true, error: null, errorStatus: null, isStale: current.scopeKey === scopeKey && current.data !== null }));
            return altoRequest<T>(requestContext, path, { signal: controller.signal });
        }).then((data) => { if (!controller.signal.aborted)
            setState({ scopeKey, data: data ?? null, loading: false, error: null, errorStatus: null, isStale: false }); })
            .catch((error: unknown) => { if (!controller.signal.aborted)
            setState({ scopeKey, data: null, loading: false, error: error instanceof Error ? error.message : "Could not load this view.", errorStatus: error instanceof AltoApiError ? error.status : null, isStale: false }); });
        return () => controller.abort();
    }, [requestContext, path, revision, scopeKey, cacheKey]);
    const current = state.scopeKey === scopeKey ? state : initialSnapshot();
    return { ...current, loading: current.loading && current.data === null, refreshing: current.loading && current.data !== null, refresh };
}
export function useCommand() {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const run = async (command: () => Promise<unknown>) => { if (busy)
        return; setBusy(true); setError(null); try {
        await command();
    }
    catch (value) {
        setError(value instanceof Error ? value.message : "The change could not be saved.");
    }
    finally {
        setBusy(false);
    } };
    return { busy, error, run, setError };
}
export function useResourceActivity(api: AltoApiContext | undefined) {
    const scope = api ? resourceScope(api) : null;
    const snapshot = useCallback(() => getAltoResourceActivity(scope), [scope]);
    return useSyncExternalStore(subscribeAltoResourceActivity, snapshot);
}

import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createClient: vi.fn(),
  startAuthorisedRefresh: vi.fn(),
}));

vi.mock("@supabase/supabase-js", () => ({ createClient: mocks.createClient }));
vi.mock("./authorised-refresh", () => ({
  startAuthorisedRefresh: mocks.startAuthorisedRefresh,
}));

import { startAuthorisedSession, type AuthorisedSessionState } from "./authorised-session";
import type { PublicRuntimeConfig } from "./runtime-config";
import { READ_TIMEOUT_MS } from "./request-deadline";

const COMPANY_ID = "11111111-1111-4111-8111-111111111111";

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("authorised session bootstrap", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("connects through the authorised API when Realtime authentication fails", async () => {
    const session = {
      access_token: "employee-access-token",
      user: { id: "employee-user" },
    } as unknown as Session;
    const unsubscribe = vi.fn();
    const client = {
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session } }),
        onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe } } }),
        signInWithPassword: vi.fn(),
        signOut: vi.fn(),
      },
      realtime: {
        setAuth: vi.fn().mockRejectedValue(new Error("realtime unavailable")),
      },
    } as unknown as SupabaseClient;
    mocks.createClient.mockReturnValue(client);
    mocks.startAuthorisedRefresh.mockImplementation(
      ({ refetch }: { refetch: () => Promise<void> }) => {
        void refetch();
        return vi.fn();
      },
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/v1/session")) {
          return Promise.resolve(json({
            user_id: session.user.id,
            company_id: COMPANY_ID,
            administrative_role: "member",
            employee_id: "employee-1",
          }));
        }
        if (url.endsWith("/me/notifications")) {
          return Promise.resolve(json({ notifications: [] }));
        }
        return Promise.reject(new Error(`unexpected request ${url}`));
      }),
    );
    const states: unknown[] = [];
    const config: PublicRuntimeConfig = {
      apiMode: "static",
      apiOrigin: "https://api.example.invalid",
      productName: "Coordination Engine",
      supabaseConfigured: true,
      supabaseUrl: "https://project.supabase.co",
      supabasePublishableKey: "sb_publishable_public",
      defaultCompanyId: COMPANY_ID,
      hackathonDemo: false,
    };

    const controller = startAuthorisedSession(config, (state) => states.push(state));

    await vi.waitFor(() => {
      expect(states).toContainEqual(expect.objectContaining({
        status: "connected",
        administrativeRole: "member",
      }));
    });
    expect(client.realtime.setAuth).toHaveBeenCalledWith(session.access_token);
    expect(states).not.toContainEqual(expect.objectContaining({ status: "unreachable" }));

    controller.stop();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });

  it("bounds a stalled Auth session restore and offers an explicit retry", async () => {
    vi.useFakeTimers();
    const getSession = vi.fn().mockImplementationOnce(() => new Promise(() => undefined)).mockResolvedValueOnce({ data: { session: null }, error: null });
    mocks.createClient.mockReturnValue({ auth: { getSession, onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }) } });
    const states: unknown[] = [];
    const controller = startAuthorisedSession({ apiMode: "static", apiOrigin: "https://api.example.invalid", productName: "ALTO", supabaseConfigured: true, supabaseUrl: "https://project.supabase.co", supabasePublishableKey: "sb_publishable_test", defaultCompanyId: COMPANY_ID, hackathonDemo: false }, (state) => states.push(state));
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
    expect(states).toContainEqual(expect.objectContaining({ status: "unreachable", userId: null }));
    await controller.retry();
    expect(states.at(-1)).toEqual({ status: "signed_out" });
    controller.stop();
  });

  it("bounds discovery and ignores its late result after timeout", async () => {
    vi.useFakeTimers();
    let resolveDiscovery!: (value: unknown) => void;
    const session = { access_token: "token", user: { id: "user" } };
    mocks.createClient.mockReturnValue({
      auth: { getSession: vi.fn().mockResolvedValue({ data: { session }, error: null }), onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }) },
      realtime: { setAuth: vi.fn().mockResolvedValue(undefined) },
      rpc: vi.fn(() => new Promise((resolve) => { resolveDiscovery = resolve; })),
    });
    mocks.startAuthorisedRefresh.mockImplementation(({ refetch, onError }: { refetch: () => Promise<void>; onError: (error: unknown) => void }) => { void refetch().catch(onError); return vi.fn(); });
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const states: unknown[] = [];
    const controller = startAuthorisedSession({ apiMode: "supabase-discovery", apiOrigin: "", productName: "ALTO", supabaseConfigured: true, supabaseUrl: "https://project.supabase.co", supabasePublishableKey: "sb_publishable_test", defaultCompanyId: COMPANY_ID, hackathonDemo: false }, (state) => states.push(state));
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
    expect(states).toContainEqual(expect.objectContaining({ status: "unreachable" }));
    resolveDiscovery({ data: "https://late.example.invalid", error: null });
    await vi.advanceTimersByTimeAsync(0);
    expect(fetch).not.toHaveBeenCalled();
    controller.stop();
  });

  it("does not restart authorised refresh for duplicate same-token Auth events", async () => {
    vi.useFakeTimers();
    const session = { access_token: "token", user: { id: "user" } };
    let authChanged!: (event: string, value: typeof session) => void;
    mocks.startAuthorisedRefresh.mockClear();
    mocks.startAuthorisedRefresh.mockReturnValue(vi.fn());
    mocks.createClient.mockReturnValue({
      auth: { getSession: vi.fn().mockResolvedValue({ data: { session }, error: null }), onAuthStateChange: vi.fn((callback) => { authChanged = callback; return { data: { subscription: { unsubscribe: vi.fn() } } }; }) },
      realtime: { setAuth: vi.fn().mockResolvedValue(undefined) },
    });
    const controller = startAuthorisedSession({ apiMode: "static", apiOrigin: "https://api.example.invalid", productName: "ALTO", supabaseConfigured: true, supabaseUrl: "https://project.supabase.co", supabasePublishableKey: "sb_publishable_test", defaultCompanyId: COMPANY_ID, hackathonDemo: false }, vi.fn());
    await vi.advanceTimersByTimeAsync(0);
    authChanged("SIGNED_IN", { ...session });
    await vi.advanceTimersByTimeAsync(0);
    expect(mocks.startAuthorisedRefresh).toHaveBeenCalledTimes(1);
    controller.stop();
  });

  it("creates one anonymous session and automatically joins the locked demo", async () => {
    const session = { access_token: "anonymous-token", user: { id: "anonymous-user" } } as unknown as Session;
    const signInAnonymously = vi.fn().mockResolvedValue({ data: { session }, error: null });
    mocks.createClient.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
        signInAnonymously,
        onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
      },
      realtime: { setAuth: vi.fn().mockResolvedValue(undefined) },
    });
    mocks.startAuthorisedRefresh.mockImplementation(({ refetch, onError }: { refetch: () => Promise<void>; onError: (error: unknown) => void }) => {
      void refetch().catch(onError);
      return vi.fn();
    });
    let sessionChecks = 0;
    const fetcher = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/v1/demo/onboarding")) return Promise.resolve(json({ company_id: COMPANY_ID }));
      if (url.endsWith("/v1/session")) {
        sessionChecks += 1;
        if (sessionChecks === 1) return Promise.resolve(new Response(JSON.stringify({ detail: "company was not found" }), { status: 404 }));
        return Promise.resolve(json({ user_id: session.user.id, company_id: COMPANY_ID, administrative_role: "manager", employee_id: "judge-profile" }));
      }
      if (url.endsWith("/me/notifications")) return Promise.resolve(json({ notifications: [] }));
      return Promise.reject(new Error(`unexpected request ${url} ${init?.method ?? "GET"}`));
    });
    vi.stubGlobal("fetch", fetcher);
    const states: AuthorisedSessionState[] = [];

    const controller = startAuthorisedSession({
      apiMode: "static", apiOrigin: "https://api.example.invalid", productName: "ALTO",
      supabaseConfigured: true, supabaseUrl: "https://project.supabase.co",
      supabasePublishableKey: "sb_publishable_test", defaultCompanyId: COMPANY_ID,
      hackathonDemo: true,
    }, (state) => states.push(state));

    await vi.waitFor(() => expect(states.at(-1)).toEqual(expect.objectContaining({ status: "connected" })));
    expect(signInAnonymously).toHaveBeenCalledTimes(1);
    const onboarding = fetcher.mock.calls.find(([url]) => String(url).endsWith("/v1/demo/onboarding"));
    expect(JSON.parse(String(onboarding?.[1]?.body))).toEqual({ display_name: "Hackathon judge", requested_role: "manager" });
    controller.stop();
  });

  it("replaces an existing password session with an isolated anonymous demo session", async () => {
    const passwordSession = { access_token: "password-token", user: { id: "old-user", is_anonymous: false } } as unknown as Session;
    const anonymousSession = { access_token: "anonymous-token", user: { id: "anonymous-user", is_anonymous: true } } as unknown as Session;
    const signOut = vi.fn().mockResolvedValue({ error: null });
    const signInAnonymously = vi.fn().mockResolvedValue({ data: { session: anonymousSession }, error: null });
    mocks.createClient.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: passwordSession }, error: null }),
        signOut,
        signInAnonymously,
        onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
      },
      realtime: { setAuth: vi.fn().mockResolvedValue(undefined) },
    });
    mocks.startAuthorisedRefresh.mockReturnValue(vi.fn());

    const controller = startAuthorisedSession({
      apiMode: "static", apiOrigin: "https://api.example.invalid", productName: "ALTO",
      supabaseConfigured: true, supabaseUrl: "https://project.supabase.co",
      supabasePublishableKey: "sb_publishable_test", defaultCompanyId: COMPANY_ID,
      hackathonDemo: true,
    }, vi.fn());

    await vi.waitFor(() => expect(signInAnonymously).toHaveBeenCalledTimes(1));
    expect(signOut).toHaveBeenCalledWith({ scope: "local" });
    controller.stop();
  });

  it("replaces a password session received from Supabase's initial Auth event", async () => {
    const passwordSession = { access_token: "password-token", user: { id: "old-user", is_anonymous: false } } as unknown as Session;
    const anonymousSession = { access_token: "anonymous-token", user: { id: "anonymous-user", is_anonymous: true } } as unknown as Session;
    let finishInitialRestore!: (value: { data: { session: Session }; error: null }) => void;
    const getSession = vi.fn()
      .mockImplementationOnce(() => new Promise((resolve) => { finishInitialRestore = resolve; }))
      .mockResolvedValue({ data: { session: passwordSession }, error: null });
    const signOut = vi.fn().mockResolvedValue({ error: null });
    const signInAnonymously = vi.fn().mockResolvedValue({ data: { session: anonymousSession }, error: null });
    let authChanged!: (event: string, session: Session | null) => void;
    mocks.createClient.mockReturnValue({
      auth: {
        getSession,
        signOut,
        signInAnonymously,
        onAuthStateChange: vi.fn((callback) => {
          authChanged = callback;
          return { data: { subscription: { unsubscribe: vi.fn() } } };
        }),
      },
      realtime: { setAuth: vi.fn().mockResolvedValue(undefined) },
    });
    mocks.startAuthorisedRefresh.mockReturnValue(vi.fn());

    const controller = startAuthorisedSession({
      apiMode: "static", apiOrigin: "https://api.example.invalid", productName: "ALTO",
      supabaseConfigured: true, supabaseUrl: "https://project.supabase.co",
      supabasePublishableKey: "sb_publishable_test", defaultCompanyId: COMPANY_ID,
      hackathonDemo: true,
    }, vi.fn());

    await vi.waitFor(() => expect(getSession).toHaveBeenCalledTimes(1));
    authChanged("INITIAL_SESSION", passwordSession);
    finishInitialRestore({ data: { session: passwordSession }, error: null });
    await vi.waitFor(() => expect(signInAnonymously).toHaveBeenCalledTimes(1));
    expect(signOut).toHaveBeenCalledWith({ scope: "local" });
    controller.stop();
  });
});

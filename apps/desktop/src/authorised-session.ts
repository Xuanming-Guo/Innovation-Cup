import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

import { startAuthorisedRefresh } from "./authorised-refresh";
import type { AuthorisedApiContext } from "./api-client";
import type { PublicRuntimeConfig } from "./runtime-config";
import { resolveHostApiOrigin } from "./host-discovery";
import { COMMAND_TIMEOUT_MS, withRequestDeadline } from "./request-deadline";
import { clearAltoResourceCache, invalidateAltoAccountResources } from "./alto-resource-cache";

export type AuthorisedSessionState =
  | { status: "unconfigured" }
  | { status: "signed_out" }
  | { status: "company_required"; userId: string }
  | {
      status: "connected";
      userId: string;
      unreadNotifications: number;
      administrativeRole: string;
      employeeId: string | null;
      api: AuthorisedApiContext;
    }
  | { status: "unreachable"; userId: string | null; detail: string };

export interface AuthorisedSessionController {
  signIn(email: string, password: string): Promise<void>;
  signUp(email: string, password: string): Promise<{ confirmationRequired: boolean }>;
  onboard(displayName: string, requestedRole: "manager" | "employee"): Promise<void>;
  signOut(): Promise<void>;
  retry(): Promise<void>;
  stop(): void;
}

interface SessionRecord {
  user_id: string;
  company_id: string;
  administrative_role: string;
  employee_id: string | null;
}

interface NotificationRecord {
  seen_at: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function readJson(response: Response): Promise<unknown> {
  if (response.status === 401) throw new AuthorisationExpiredError();
  if (response.status === 403 || response.status === 404) throw new MembershipRequiredError();
  if (!response.ok) throw new Error(`authorised refetch returned HTTP ${response.status}`);
  return response.json() as Promise<unknown>;
}

class MembershipRequiredError extends Error {}
class AuthorisationExpiredError extends Error {}

async function refetchAuthorisedState(
  apiOrigin: string,
  companyId: string,
  session: Session,
  signal: AbortSignal,
): Promise<{ session: SessionRecord; notifications: NotificationRecord[] }> {
  const headers = {
    Authorization: `Bearer ${session.access_token}`,
    "X-Company-ID": companyId,
  };
  const [sessionValue, notificationValue] = await Promise.all([
    fetch(`${apiOrigin}/v1/session`, { headers, signal }).then(readJson),
    fetch(`${apiOrigin}/v1/companies/${companyId}/me/notifications`, {
      headers,
      signal,
    }).then(readJson),
  ]);
  if (
    !isRecord(sessionValue) ||
    typeof sessionValue.user_id !== "string" ||
    sessionValue.user_id !== session.user.id ||
    sessionValue.company_id !== companyId
  ) {
    throw new Error("authorised session response is invalid");
  }
  if (!isRecord(notificationValue) || !Array.isArray(notificationValue.notifications)) {
    throw new Error("notification response is invalid");
  }
  const notifications = notificationValue.notifications.filter(
    (value): value is NotificationRecord =>
      isRecord(value) && (value.seen_at === null || typeof value.seen_at === "string"),
  );
  if (notifications.length !== notificationValue.notifications.length) {
    throw new Error("notification response contains an invalid record");
  }
  return { session: sessionValue as unknown as SessionRecord, notifications };
}

export function startAuthorisedSession(
  config: PublicRuntimeConfig,
  onState: (state: AuthorisedSessionState) => void,
): AuthorisedSessionController {
  if (
    !config.supabaseConfigured ||
    config.supabaseUrl === null ||
    config.supabasePublishableKey === null
  ) {
    onState({ status: "unconfigured" });
    return {
      signIn: async () => { throw new Error("Supabase is not configured"); },
      signUp: async () => { throw new Error("Supabase is not configured"); },
      onboard: async () => { throw new Error("Supabase is not configured"); },
      signOut: async () => undefined,
      retry: async () => undefined,
      stop: () => undefined,
    };
  }

  const client: SupabaseClient = createClient(
    config.supabaseUrl,
    config.supabasePublishableKey,
    {
      global: {
        fetch: (input, init) => withRequestDeadline(
          (signal) => fetch(input, { ...init, signal }),
          { signal: init?.signal },
        ),
      },
    },
  );
  const lifetime = new AbortController();
  let stopped = false;
  let generation = 0;
  let authEventRevision = 0;
  let activeSessionKey: string | null | undefined;
  let activeUserId: string | null = null;
  let publishedAuthority: string | null = null;
  let publishedAccessToken: string | null = null;
  let stopRefresh: (() => void) | null = null;
  let activeController: AbortController | null = null;
  let anonymousSignIn: Promise<Session> | null = null;
  let automaticOnboardingUser: string | null = null;

  const joinDemo = async (session: Session, displayName: string, requestedRole: "manager" | "employee") => {
    const companyId = config.defaultCompanyId;
    if (!companyId) throw new Error("A fixed demo company must be configured on this installation.");
    await withRequestDeadline(async (signal) => {
      const apiOrigin = config.apiMode === "supabase-discovery"
        ? await resolveHostApiOrigin(client, companyId)
        : config.apiOrigin;
      signal.throwIfAborted();
      const response = await fetch(`${apiOrigin}/v1/demo/onboarding`, {
        method: "POST",
        signal,
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({ display_name: displayName.trim(), requested_role: requestedRole }),
      });
      if (!response.ok) {
        const value: unknown = await response.json().catch(() => null);
        throw new Error(typeof value === "object" && value !== null && "detail" in value && typeof value.detail === "string"
          ? value.detail
          : "Demo onboarding is unavailable on this host.");
      }
    }, {
      signal: lifetime.signal,
      timeoutMs: COMMAND_TIMEOUT_MS,
      timeoutMessage: "Joining the demo timed out. Retry the connection.",
    });
  };

  const activate = (session: Session | null, force = false) => {
    if (stopped) return;
    const sessionKey = session ? JSON.stringify([session.user.id, session.access_token]) : null;
    if (!force && sessionKey === activeSessionKey) return;
    const changedUser = activeUserId !== null && session !== null && activeUserId !== session.user.id;
    if (changedUser || session === null) clearAltoResourceCache();
    activeSessionKey = sessionKey;
    activeUserId = session?.user.id ?? null;
    generation += 1;
    const currentGeneration = generation;
    stopRefresh?.();
    stopRefresh = null;
    activeController?.abort();
    activeController = null;
    if (session === null) {
      onState({ status: "signed_out" });
      return;
    }
    if (changedUser) onState({ status: "unreachable", userId: session.user.id, detail: "Checking access for the signed-in account." });
    const companyId = config.defaultCompanyId;
    if (companyId === null) {
      onState({ status: "company_required", userId: session.user.id });
      return;
    }

    const refetch = async () => {
      activeController?.abort();
      const controller = new AbortController();
      activeController = controller;
      const { apiOrigin, state } = await withRequestDeadline(async (signal) => {
        const apiOrigin = config.apiMode === "supabase-discovery"
          ? await resolveHostApiOrigin(client, companyId)
          : config.apiOrigin;
        signal.throwIfAborted();
        const state = await refetchAuthorisedState(apiOrigin, companyId, session, signal);
        return { apiOrigin, state };
      }, { signal: controller.signal });
      if (stopped || controller.signal.aborted || currentGeneration !== generation) return;
      const authority = JSON.stringify([state.session.user_id, state.session.company_id, state.session.administrative_role, state.session.employee_id]);
      if (publishedAuthority !== null && publishedAuthority !== authority) clearAltoResourceCache(true);
      else if (publishedAccessToken === session.access_token) invalidateAltoAccountResources({ authUserId: session.user.id, apiOrigin, companyId });
      publishedAuthority = authority;
      publishedAccessToken = session.access_token;
      onState({
        status: "connected",
        userId: state.session.user_id,
        unreadNotifications: state.notifications.filter((item) => item.seen_at === null).length,
        administrativeRole: state.session.administrative_role,
        employeeId: state.session.employee_id,
        api: {
          apiOrigin,
          companyId: state.session.company_id,
          accessToken: session.access_token,
        },
      });
    };
    stopRefresh = startAuthorisedRefresh({
      client,
      userId: session.user.id,
      refetch,
      onError: (error) => {
        if (!stopped && currentGeneration === generation) {
          if (error instanceof MembershipRequiredError || error instanceof AuthorisationExpiredError) clearAltoResourceCache();
          if (error instanceof MembershipRequiredError) {
            if (config.hackathonDemo && automaticOnboardingUser !== session.user.id) {
              automaticOnboardingUser = session.user.id;
              void joinDemo(session, "Hackathon judge", "manager")
                .then(() => activate(session, true))
                .catch((value: unknown) => {
                  if (!stopped && currentGeneration === generation) {
                    onState({ status: "unreachable", userId: session.user.id, detail: value instanceof Error ? value.message : "Could not prepare the hackathon demo." });
                  }
                });
              return;
            }
            onState({ status: "company_required", userId: session.user.id });
            return;
          }
          onState({
            status: "unreachable",
            userId: session.user.id,
            detail: config.apiMode === "supabase-discovery"
              ? "Host computer is offline or still starting"
              : "Configured API is unreachable",
          });
        }
      },
    });

    // Realtime is a private invalidation hint, not a prerequisite for Auth,
    // authenticated host discovery or API authorization.
    void Promise.resolve()
      .then(() => client.realtime.setAuth(session.access_token))
      .catch(() => undefined);
  };

  const restoreSession = async (force = false) => {
    const revision = authEventRevision;
    try {
      const { data, error } = await withRequestDeadline(
        () => client.auth.getSession(),
        { signal: lifetime.signal },
      );
      if (stopped || revision !== authEventRevision) return;
      if (error) throw error;
      let session = data.session;
      if (session !== null && config.hackathonDemo && session.user.is_anonymous !== true) {
        const { error: signOutError } = await withRequestDeadline(
          () => client.auth.signOut({ scope: "local" }),
          { signal: lifetime.signal },
        );
        if (signOutError) throw signOutError;
        session = null;
      }
      if (session === null && config.hackathonDemo) {
        anonymousSignIn ??= withRequestDeadline(
          () => client.auth.signInAnonymously(),
          { signal: lifetime.signal },
        ).then(({ data: signedIn, error: signInError }) => {
          if (signInError || signedIn.session === null) {
            throw signInError ?? new Error("Anonymous session was not created");
          }
          return signedIn.session;
        }).finally(() => { anonymousSignIn = null; });
        session = await anonymousSignIn;
      }
      if (stopped) return;
      activate(session, force);
    } catch {
      if (!stopped && revision === authEventRevision) {
        onState({ status: "unreachable", userId: null, detail: "Could not restore your sign-in session. Retry or check connection settings." });
      }
    }
  };
  void restoreSession();
  const { data } = client.auth.onAuthStateChange((_event, session) => {
    authEventRevision += 1;
    const revision = authEventRevision;
    window.setTimeout(() => {
      if (stopped || revision !== authEventRevision) return;
      if (config.hackathonDemo && session !== null && session.user.is_anonymous !== true) {
        void restoreSession(true);
        return;
      }
      activate(session);
    }, 0);
  });

  return {
    signIn: async (email: string, password: string) => {
      const { error } = await withRequestDeadline(
        () => client.auth.signInWithPassword({ email, password }), { signal: lifetime.signal },
      );
      if (error) throw error;
    },
    signUp: async (email: string, password: string) => {
      const { data, error } = await withRequestDeadline(
        () => client.auth.signUp({ email, password }), { signal: lifetime.signal },
      );
      if (error) throw error;
      return { confirmationRequired: data.session === null };
    },
    onboard: async (displayName, requestedRole) => {
      const { data, error } = await withRequestDeadline(() => client.auth.getSession(), { signal: lifetime.signal });
      if (error || !data.session) throw new Error("Sign in before choosing a demo workspace.");
      await joinDemo(data.session, displayName, requestedRole);
      activate(data.session, true);
    },
    signOut: async () => {
      const { error } = await withRequestDeadline(() => client.auth.signOut(), { signal: lifetime.signal });
      if (error) throw error;
    },
    retry: () => restoreSession(true),
    stop: () => {
      stopped = true;
      generation += 1;
      lifetime.abort();
      clearAltoResourceCache();
      stopRefresh?.();
      activeController?.abort();
      data.subscription.unsubscribe();
    },
  };
}

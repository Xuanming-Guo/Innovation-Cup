import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

import { startAuthorisedRefresh } from "./authorised-refresh";
import type { AuthorisedApiContext } from "./api-client";
import type { PublicRuntimeConfig } from "./runtime-config";
import { resolveHostApiOrigin } from "./host-discovery";

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
  | { status: "unreachable"; userId: string; detail: string };

export interface AuthorisedSessionController {
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
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
  if (!response.ok) throw new Error(`authorised refetch returned HTTP ${response.status}`);
  return response.json() as Promise<unknown>;
}

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
      signOut: async () => undefined,
      stop: () => undefined,
    };
  }

  const client: SupabaseClient = createClient(
    config.supabaseUrl,
    config.supabasePublishableKey,
  );
  let stopped = false;
  let generation = 0;
  let stopRefresh: (() => void) | null = null;
  let activeController: AbortController | null = null;

  const activate = (session: Session | null) => {
    generation += 1;
    const currentGeneration = generation;
    stopRefresh?.();
    stopRefresh = null;
    activeController?.abort();
    activeController = null;
    if (stopped) return;
    if (session === null) {
      onState({ status: "signed_out" });
      return;
    }
    if (config.defaultCompanyId === null) {
      onState({ status: "company_required", userId: session.user.id });
      return;
    }

    void client.realtime
      .setAuth(session.access_token)
      .then(() => {
        if (stopped || currentGeneration !== generation) return;
        const refetch = async () => {
          activeController?.abort();
          const controller = new AbortController();
          activeController = controller;
          const apiOrigin = config.apiMode === "supabase-discovery"
            ? await resolveHostApiOrigin(client, config.defaultCompanyId as string)
            : config.apiOrigin;
          const state = await refetchAuthorisedState(
            apiOrigin,
            config.defaultCompanyId as string,
            session,
            controller.signal,
          );
          if (stopped || currentGeneration !== generation) return;
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
          onError: () => {
            if (!stopped && currentGeneration === generation) {
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
      })
      .catch(() => {
        if (!stopped && currentGeneration === generation) {
          onState({
            status: "unreachable",
            userId: session.user.id,
            detail: "Authorised realtime connection is unavailable",
          });
        }
      });
  };

  void client.auth.getSession().then(({ data }) => activate(data.session));
  const { data } = client.auth.onAuthStateChange((_event, session) => {
    window.setTimeout(() => activate(session), 0);
  });

  return {
    signIn: async (email: string, password: string) => {
      const { error } = await client.auth.signInWithPassword({ email, password });
      if (error) throw error;
    },
    signOut: async () => {
      const { error } = await client.auth.signOut();
      if (error) throw error;
    },
    stop: () => {
      stopped = true;
      generation += 1;
      stopRefresh?.();
      activeController?.abort();
      data.subscription.unsubscribe();
    },
  };
}

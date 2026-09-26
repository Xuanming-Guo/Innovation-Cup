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

import { startAuthorisedSession } from "./authorised-session";
import type { PublicRuntimeConfig } from "./runtime-config";

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
});

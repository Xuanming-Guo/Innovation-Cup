import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AltoShell } from "./alto-shell";
import { DemoProviderSettings } from "./alto-settings";
import { clearAltoResourceCache } from "./alto-resource-cache";
import { DeploymentSettings } from "./deployment-settings";

afterEach(() => {
  cleanup();
  clearAltoResourceCache();
  vi.unstubAllGlobals();
});

describe("locked hackathon settings", () => {
  it("renders only fixed masks and never places deployment values in the DOM", () => {
    const values = {
      apiMode: "static" as const,
      apiOrigin: "https://private-build-origin.example",
      productName: "ALTO",
      supabaseConfigured: true,
      supabaseUrl: "https://private-project.supabase.co",
      supabasePublishableKey: "sb_publishable_dom_regression",
      defaultCompanyId: "11111111-1111-4111-8111-111111111111",
      hackathonDemo: true,
    };
    const { container } = render(<DeploymentSettings config={values} locked onReset={vi.fn()} onSave={vi.fn()} />);

    expect(container.textContent).not.toContain(values.apiOrigin);
    expect(container.textContent).not.toContain(values.supabaseUrl);
    expect(container.textContent).not.toContain(values.supabasePublishableKey);
    expect(container.textContent).not.toContain(values.defaultCompanyId);
    expect(container.querySelector("input,textarea,select")).toBeNull();
    expect(screen.queryByRole("button", { name: /save|reset|defaults/i })).toBeNull();
    expect(container.textContent).toContain("************************");
  });

  it("shows only safe operator-managed Vertex status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      provider: "vertex_ai",
      credential_kind: "vertex_service_account",
      management_mode: "operator_managed",
      can_manage: false,
      status: "configured",
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    const { container } = render(<DemoProviderSettings locked runMode="live" api={{
      apiOrigin: "https://api.example.invalid",
      companyId: "company",
      accessToken: "token",
      demoRunId: "run",
      demoActorSessionId: "actor",
    }} />);

    await waitFor(() => expect(screen.getByText("Configured for the hackathon demo")).toBeInTheDocument());
    expect(screen.getByText("Vertex AI")).toBeInTheDocument();
    expect(container.querySelector("input,textarea,select")).toBeNull();
    expect(screen.queryByRole("button", { name: /upload|validate|bind|revoke|rotate|copy/i })).toBeNull();
  });

  it("reports a quickstart failure even when the connected session state refreshes", async () => {
    let finishQuickstart!: (response: Response) => void;
    const fetcher = vi.fn().mockImplementation(() => new Promise<Response>((resolve) => {
      finishQuickstart = resolve;
    }));
    vi.stubGlobal("fetch", fetcher);
    const config = {
      apiMode: "static" as const,
      apiOrigin: "https://api.example.invalid",
      productName: "ALTO",
      supabaseConfigured: true,
      supabaseUrl: "https://project.supabase.co",
      supabasePublishableKey: "sb_publishable_test",
      defaultCompanyId: "11111111-1111-4111-8111-111111111111",
      hackathonDemo: true,
    };
    const session = (unreadNotifications: number) => ({
      status: "connected" as const,
      userId: "anonymous-user",
      unreadNotifications,
      administrativeRole: "manager",
      employeeId: null,
      api: {
        apiOrigin: config.apiOrigin,
        companyId: config.defaultCompanyId,
        accessToken: "anonymous-token",
      },
    });
    const shell = (unreadNotifications: number) => <AltoShell
      config={config}
      session={session(unreadNotifications)}
      service={{ state: "reachable", detail: "Test fixture" }}
      onSignOut={async () => undefined}
      saveDeployment={() => undefined}
      resetDeployment={() => undefined}
      authController={{ current: null }}
    />;

    const view = render(shell(0));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    view.rerender(shell(1));
    await act(async () => finishQuickstart(new Response(JSON.stringify({ detail: "hackathon quickstart is unavailable" }), {
      status: 403,
      headers: { "Content-Type": "application/json" },
    })));

    expect(await screen.findByText("hackathon quickstart is unavailable")).toBeVisible();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

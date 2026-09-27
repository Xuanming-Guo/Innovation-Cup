import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { savePublicRuntimeConfig } from "./runtime-config";

vi.mock("./authorised-session", () => ({
  startAuthorisedSession: (config: { supabaseConfigured: boolean }, onState: (state: unknown) => void) => {
    onState({ status: config.supabaseConfigured ? "signed_out" : "unconfigured" });
    return { signIn: vi.fn(), signUp: vi.fn(), onboard: vi.fn(), signOut: vi.fn(), stop: vi.fn() };
  },
}));

describe("App", () => {
  beforeEach(() => {
    // Installation-specific ignored .env values must not decide test behavior.
    for (const name of ["VITE_API_MODE", "VITE_API_ORIGIN", "VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY", "VITE_DEFAULT_COMPANY_ID", "VITE_HACKATHON_DEMO"]) vi.stubEnv(name, "");
    window.localStorage.clear();
    window.location.hash = "/home";
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("fails closed to the connection boundary instead of presenting fixture records", async () => {
    configureDeployment();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            api_version: "1.0.0",
            build_commit: "test",
            service: "coordination-api",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<App />);

    expect(screen.getByRole("heading", { name: "Welcome to ALTO" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeVisible();
    expect(screen.queryByText(/Sample data/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Northstar analytics product launch")).not.toBeInTheDocument();
  });

  it("keeps routed work surfaces behind authentication", async () => {
    configureDeployment();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "My calendar" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Welcome to ALTO" })).toBeVisible());
    expect(screen.queryByRole("heading", { name: "My calendar" })).not.toBeInTheDocument();
  });

  it("offers setup and validates public connection settings", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Set up this installation" }));
    expect(await screen.findByRole("heading", { name: "Deployment" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("API origin"), { target: { value: "http://api.example.com" } });
    fireEvent.change(screen.getByLabelText("Supabase project URL"), { target: { value: "https://project.supabase.co" } });
    fireEvent.change(screen.getByLabelText("Supabase publishable key"), { target: { value: "sb_publishable_public" } });
    fireEvent.change(screen.getByLabelText("Company ID"), { target: { value: "11111111-1111-4111-8111-111111111111" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and connect" }));

    expect(screen.getByRole("alert")).toHaveTextContent("must use HTTPS");
    expect(screen.getByRole("heading", { name: "Deployment" })).toBeVisible();
  });
});

function configureDeployment() {
  savePublicRuntimeConfig({
    apiOrigin: "http://127.0.0.1:8000",
    supabaseUrl: "https://project.supabase.co",
    supabasePublishableKey: "sb_publishable_public",
    defaultCompanyId: "11111111-1111-4111-8111-111111111111",
  }, "Coordination Engine");
}

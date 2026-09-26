import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { savePublicRuntimeConfig } from "./runtime-config";

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
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

    expect(screen.getByRole("heading", { name: "Plan review" })).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Sign in to create and review a real plan." }),
    ).toBeVisible();
    expect(screen.queryByText(/Sample data/i)).not.toBeInTheDocument();
    expect(await screen.findByText("API reachable")).toBeVisible();
  });

  it("keeps the employee surface behind the authorised task projection", () => {
    configureDeployment();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "My work" }));

    expect(screen.getByRole("heading", { name: "My work" })).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Sign in to load only your authorised work." }),
    ).toBeVisible();
    expect(screen.getByText(/task-scoped access are rechecked/i)).toBeVisible();
  });

  it("starts at deployment setup and validates public connection settings", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);

    expect(screen.getByRole("heading", { name: "Deployment setup" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("API origin"), { target: { value: "http://api.example.com" } });
    fireEvent.change(screen.getByLabelText("Supabase project URL"), { target: { value: "https://project.supabase.co" } });
    fireEvent.change(screen.getByLabelText("Supabase publishable key"), { target: { value: "sb_publishable_public" } });
    fireEvent.change(screen.getByLabelText("Company ID"), { target: { value: "11111111-1111-4111-8111-111111111111" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and connect" }));

    expect(screen.getByRole("alert")).toHaveTextContent("must use HTTPS");
    expect(screen.getByRole("heading", { name: "Deployment setup" })).toBeVisible();
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

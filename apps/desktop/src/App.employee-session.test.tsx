import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./authorised-session", () => ({
  startAuthorisedSession: (
    _config: unknown,
    onState: (state: unknown) => void,
  ) => {
    window.setTimeout(() => onState({
      status: "connected",
      userId: "employee-user",
      unreadNotifications: 0,
      administrativeRole: "member",
      employeeId: "employee-1",
      api: {
        apiOrigin: "https://api.example.invalid",
        companyId: "11111111-1111-4111-8111-111111111111",
        accessToken: "employee-access-token",
      },
    }), 0);
    return {
      signIn: vi.fn(),
      signOut: vi.fn(),
      stop: vi.fn(),
    };
  },
}));

import { App } from "./App";
import { savePublicRuntimeConfig } from "./runtime-config";

describe("employee session routing", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.location.hash = "/home";
    savePublicRuntimeConfig({
      apiOrigin: "https://api.example.invalid",
      supabaseUrl: "https://project.supabase.co",
      supabasePublishableKey: "sb_publishable_public",
      defaultCompanyId: "11111111-1111-4111-8111-111111111111",
    }, "Coordination Engine");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("not needed")));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("lands a connected employee on Home without manager-only navigation, even when API reads fail", async () => {
    render(<App />);

    expect(await screen.findByText("Connected user")).toBeVisible();
    expect(screen.getByRole("button", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "My projects" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Plan review" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connections" })).not.toBeInTheDocument();
  });
});

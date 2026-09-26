import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("fails closed to the connection boundary instead of presenting fixture records", async () => {
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
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "My work" }));

    expect(screen.getByRole("heading", { name: "My work" })).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Sign in to load only your authorised work." }),
    ).toBeVisible();
    expect(screen.getByText(/task-scoped access are rechecked/i)).toBeVisible();
  });
});

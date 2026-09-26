import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("presents a draft plan review without claiming shared state was applied", async () => {
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
    expect(screen.getByText("Draft · not applied")).toBeVisible();
    expect(screen.getByText("Employee brief is separate")).toBeVisible();
    expect(screen.getByRole("button", { name: "Commit approved plan" })).toBeDisabled();
    expect(await screen.findByText("API reachable")).toBeVisible();
  });

  it("makes evidence and diagnostics independently reviewable", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);

    fireEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    expect(screen.getByText("task.definition")).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Diagnostics" }));
    expect(screen.getByText("Independent validation")).toBeVisible();
    expect(screen.getByText("None")).toBeVisible();
  });
});

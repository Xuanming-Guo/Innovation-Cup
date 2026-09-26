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

  it("switches to a read-only employee workspace with permission-safe task facts", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "My work" }));

    expect(screen.getByRole("heading", { name: "My work" })).toBeVisible();
    expect(screen.getByText("Sample data - read only")).toBeVisible();
    expect(screen.getByText("Approved employee brief")).toBeVisible();
    expect(screen.getByText("Aiko Tanaka - Operations reviewer")).toBeVisible();
    expect(screen.getByRole("button", { name: "Acknowledge task" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Flag estimate, skill, input or availability" })).toBeDisabled();
  });

  it("exposes today, upcoming, blocked and exact-version submission states", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "My work" }));

    expect(screen.getByRole("tab", { name: "Today tasks (2)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByText("Acknowledgement needed")).toHaveLength(2);

    fireEvent.click(screen.getByRole("tab", { name: "Upcoming tasks (1)" }));
    expect(screen.getByText("Waiting for prerequisite")).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Blocked tasks (1)" }));
    expect(screen.getByText("Blocked - input missing")).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Submitted tasks (2)" }));
    expect(screen.getByText("Version 2 submitted")).toBeVisible();
    expect(screen.getByText("Pending with Aiko Tanaka")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /Complete the access validation checklist/ }));
    expect(screen.getAllByText("Revision requested")).toHaveLength(3);
    expect(screen.getByText("Version 1 preserved")).toBeVisible();
    expect(screen.getByRole("button", { name: "Submit revision" })).toBeDisabled();
  });
});

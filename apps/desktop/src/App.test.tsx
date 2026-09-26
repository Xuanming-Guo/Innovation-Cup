import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reports the real foundation boundary without exposing future flows", async () => {
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

    expect(screen.getByRole("heading", { name: "Application foundation" })).toBeVisible();
    expect(screen.getByText("Foundation only")).toBeVisible();
    expect(await screen.findByText("API 1.0.0 · build test")).toBeVisible();
    expect(screen.getByText("Manager workspace")).toHaveAttribute("aria-disabled", "true");
  });
});

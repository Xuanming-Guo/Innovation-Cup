import { describe, expect, it, vi } from "vitest";

import {
  HostOfflineError,
  normaliseDiscoveredApiOrigin,
  resolveHostApiOrigin,
} from "./host-discovery";

describe("authenticated host discovery", () => {
  it("resolves one canonical HTTPS origin", async () => {
    const rpc = vi.fn().mockResolvedValue({
      data: "https://team-host.trycloudflare.com",
      error: null,
    });

    await expect(resolveHostApiOrigin({ rpc }, "company-1")).resolves.toBe(
      "https://team-host.trycloudflare.com",
    );
    expect(rpc).toHaveBeenCalledWith("resolve_coordination_host", {
      p_company_id: "company-1",
    });
  });

  it("fails closed when the host lease is absent", async () => {
    const rpc = vi.fn().mockResolvedValue({ data: null, error: null });

    await expect(resolveHostApiOrigin({ rpc }, "company-1")).rejects.toBeInstanceOf(
      HostOfflineError,
    );
  });

  it("rejects credentials, paths and insecure discovered values", () => {
    for (const value of (
      [
        "http://host.example.com",
        "https://user@host.example.com",
        "https://host.example.com/path",
        "https://host.example.com?token=value",
      ]
    )) {
      expect(() => normaliseDiscoveredApiOrigin(value)).toThrow("invalid HTTPS origin");
    }
  });
});

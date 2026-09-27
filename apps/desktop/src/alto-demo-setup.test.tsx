import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DemoSetup } from "./alto-demo-setup";
import type { AltoApiContext, DemoData, DemoRun, WorkspaceBootstrap } from "./alto-api";
import { clearAltoResourceCache } from "./alto-resource-cache";

const api: AltoApiContext = { apiOrigin: "https://setup.example.invalid", companyId: "company-1", authUserId: "visitor-1", accessToken: "visitor-token", demoRunId: "existing-run", demoActorSessionId: "old-actor-session" };
const run: DemoRun = { id: "existing-run", name: "My saved workspace", mode: "live", status: "active", clock_at: "2026-09-28T09:00:00Z", clock_version: 1, row_version: 1, protected: false };
const workspace: WorkspaceBootstrap = {
  company: { id: "company-1", name: "Northstar", is_demo: true },
  viewer: { user_id: "visitor-1", employee_id: "maya", display_name: "Maya", role: "manager", job_title: "Director" },
  demo_run: { ...run, actor_name: "Maya", actor_session_id: "old-actor-session" }, capabilities: [],
};
const data: DemoData = { runs: [run], can_create: true, actors: [
  { id: "maya", synthetic_key: "maya", display_name: "Maya", job_title: "Delivery Director", role: "manager" },
  { id: "iris", synthetic_key: "iris", display_name: "Iris", job_title: "Design Lead", role: "employee" },
  { id: "title-not-authority", synthetic_key: "jordan", display_name: "Jordan", job_title: "Chief Executive", role: "employee" },
] };
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status }); }
afterEach(() => { cleanup(); clearAltoResourceCache(); vi.unstubAllGlobals(); window.location.hash = "/home"; });

describe("guided demo role setup", () => {
  it("uses the server's manager role, preserves an existing run and never changes account permissions or provider binding", async () => {
    const onSelectRun = vi.fn();
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (!init?.method || init.method === "GET") return Promise.resolve(json({ ...data, can_create: false }));
      if (url.endsWith("/demo/runs/existing-run/actor-sessions")) return Promise.resolve(json({ actor_session_id: "new-manager-session" }));
      throw new Error(`Unexpected mutation ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<DemoSetup api={api} workspace={workspace} onSelectRun={onSelectRun} />);
    await screen.findByText("Maya", { selector: "strong" });
    const selector = screen.getByLabelText("Manager profile");
    expect(selector.querySelectorAll("option")).toHaveLength(1);
    expect(selector).toHaveTextContent("Maya");
    expect(selector).not.toHaveTextContent("Chief Executive");
    fireEvent.click(screen.getByRole("button", { name: "Continue as manager" }));
    await waitFor(() => expect(onSelectRun).toHaveBeenCalledWith("existing-run", "new-manager-session"));
    expect(window.location.hash).toBe("#/home");
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method && init.method !== "GET");
    expect(writes).toHaveLength(1);
    expect(JSON.parse(writes[0]![1].body)).toEqual({ employee_id: "maya" });
    expect(writes[0]![1].headers).toMatchObject({ Authorization: "Bearer visitor-token", "X-Company-ID": "company-1" });
    expect(writes[0]![1].headers).not.toHaveProperty("X-Demo-Actor-Session-ID");
    expect(writes[0]![1].headers).not.toHaveProperty("X-Demo-Run-ID");
  });

  it("switches to an allowed employee through an actor-session command, not a role assignment", async () => {
    const onSelectRun = vi.fn();
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (!init?.method || init.method === "GET") return Promise.resolve(json(data));
      if (url.endsWith("/actor-sessions")) return Promise.resolve(json({ actor_session_id: "employee-session" }));
      throw new Error(`Unexpected mutation ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<DemoSetup api={api} workspace={workspace} onSelectRun={onSelectRun} />);
    fireEvent.click(screen.getByRole("button", { name: /Explore as employee/ }));
    await screen.findByText("Iris", { selector: "strong" });
    expect(screen.getByLabelText("Employee profile")).not.toHaveTextContent("Maya");
    expect(fetcher.mock.calls.filter(([, init]) => init?.method && init.method !== "GET")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Continue as employee" }));
    await waitFor(() => expect(onSelectRun).toHaveBeenCalledWith("existing-run", "employee-session"));
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method && init.method !== "GET");
    expect(JSON.parse(writes[0]![1].body)).toEqual({ employee_id: "iris" });
    expect(writes.every(([url]) => url.endsWith("/actor-sessions"))).toBe(true);
  });

  it("cannot invent a manager from an employee's job title", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ...data, actors: data.actors.filter((actor) => actor.role === "employee") })));
    render(<DemoSetup api={api} workspace={workspace} onSelectRun={vi.fn()} />);
    expect(await screen.findByText(/No permitted manager profile/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Continue as manager" })).toBeDisabled();
  });

  it("respects server denial of new workspace creation", async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ ...data, runs: [], can_create: false }));
    vi.stubGlobal("fetch", fetcher);
    render(<DemoSetup api={{ ...api, demoRunId: undefined }} workspace={workspace} onSelectRun={vi.fn()} />);
    await screen.findByText("Maya", { selector: "strong" });
    expect(screen.getByRole("button", { name: "Continue as manager" })).toBeDisabled();
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("retries a failed actor step against the newly created run even before the refreshed list contains it", async () => {
    let actorAttempts = 0;
    const onSelectRun = vi.fn();
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      // A slow/stale list must not cause the saved creation receipt to be lost.
      if (!init?.method || init.method === "GET") return Promise.resolve(json({ ...data, runs: [] }));
      if (url.endsWith("/demo/runs")) return Promise.resolve(json({ ...run, id: "new-run" }));
      if (url.endsWith("/demo/runs/new-run/actor-sessions")) {
        actorAttempts += 1;
        return Promise.resolve(actorAttempts === 1 ? json({ detail: "Actor setup temporarily unavailable" }, 503) : json({ actor_session_id: "new-session" }));
      }
      throw new Error(`Unexpected mutation ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<DemoSetup api={{ ...api, demoRunId: undefined, demoActorSessionId: undefined }} workspace={{ ...workspace, demo_run: null }} onSelectRun={onSelectRun} />);
    const next = screen.getByRole("button", { name: "Continue as manager" });
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);
    expect(await screen.findByText("Actor setup temporarily unavailable")).toBeVisible();
    expect(onSelectRun).toHaveBeenCalledWith("new-run");
    fireEvent.click(screen.getByRole("button", { name: "Continue as manager" }));
    await waitFor(() => expect(onSelectRun).toHaveBeenCalledWith("new-run", "new-session"));
    const creates = fetcher.mock.calls.filter(([url, init]) => init?.method === "POST" && url.endsWith("/demo/runs"));
    expect(creates).toHaveLength(1);
    expect(JSON.parse(creates[0]![1].body)).toEqual({ mode: "live" });
  });
});

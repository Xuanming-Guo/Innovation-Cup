import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HomeView } from "./alto-pages";
import { Assistant } from "./alto-assistant";
import { DemoProviderSettings } from "./alto-settings";
import { PlanningConversation } from "./planning-conversation";
import { AltoShell } from "./alto-shell";
import { clearAltoResourceCache, invalidateAltoResourceCache } from "./alto-resource-cache";
import { defaultPreferences } from "./alto-api";
import type { AltoApiContext, AssistantThread, WorkspaceBootstrap } from "./alto-api";

const api: AltoApiContext = { apiOrigin: "https://home.example.invalid", companyId: "company-1", authUserId: "visitor-1", accessToken: "visitor-token", demoRunId: "run-1", demoActorSessionId: "actor-1" };
const workspace: WorkspaceBootstrap = {
  company: { id: "company-1", name: "Northstar", is_demo: true },
  viewer: { user_id: "visitor-1", employee_id: "maya", display_name: "Maya", role: "manager", job_title: "Director" },
  demo_run: { id: "run-1", mode: "live", clock_at: "2026-09-28T09:00:00Z", actor_name: "Maya", row_version: 1 }, capabilities: [],
};
const thread: AssistantThread = { id: "thread-1", status: "completed", stage: null, error: null, messages: [{ id: "message-1", role: "assistant", content: "Your saved authorised answer.", created_at: "2026-09-28T09:00:00Z", citations: [] }] };
const binding = { profile_id: "profile-1", current_profile_version_id: "version-1", latest_profile_version_id: "version-1", provider: "vertex_ai", version: 1, status: "configured", credential_hint: "safe-hint" };
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status }); }
function homeReads(url: string) {
  if (url.endsWith("/home")) return json({ recent_projects: [], completed_projects: [], actions: [], tasks: [] });
  if (url.endsWith("/ai-provider/demo-binding")) return json(binding);
  if (url.endsWith("/planning-context")) return json({ sources: [{ source_id: "source-1", title: "Approved launch brief", classification: "internal", source_kind: "fixture" }], requests: [] });
  if (url.endsWith("/me/employee-preferences")) return json({ preferences: [] });
  throw new Error(`Unexpected read ${url}`);
}
afterEach(() => { cleanup(); clearAltoResourceCache(); vi.unstubAllGlobals(); window.location.hash = "/home"; });

describe("simple Home planning and work flow", () => {
  it("keeps successful background refreshes silent and offers a discreet read-only retry after failure", async () => {
    const shellApi = { ...api, demoRunId: undefined, demoActorSessionId: undefined };
    let phase: "ready" | "pending" | "offline" = "ready";
    let finishHome: ((value: Response) => void) | undefined;
    const fetcher = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/workspace")) return Promise.resolve(json({ ...workspace, company: { ...workspace.company, is_demo: false }, demo_run: null }));
      if (url.endsWith("/me/preferences")) return Promise.resolve(json(defaultPreferences));
      if (url.endsWith("/home") && phase === "pending") return new Promise<Response>((resolve) => { finishHome = resolve; });
      if (url.endsWith("/home") && phase === "offline") return Promise.reject(new TypeError("Connection unavailable"));
      return Promise.resolve(homeReads(url));
    });
    vi.stubGlobal("fetch", fetcher);
    render(<AltoShell config={{ apiMode: "static", apiOrigin: api.apiOrigin, productName: "ALTO", supabaseConfigured: false, supabaseUrl: null, supabasePublishableKey: null, defaultCompanyId: api.companyId, hackathonDemo: false }} session={{ status: "connected", userId: "visitor-1", unreadNotifications: 0, administrativeRole: "company_admin", employeeId: "maya", api: shellApi }} service={{ state: "reachable", detail: "Test fixture" }} onSignOut={async () => {}} saveDeployment={() => {}} resetDeployment={() => {}} authController={{ current: null }} />);
    await screen.findByRole("button", { name: "Plan work" });
    phase = "pending";
    act(() => invalidateAltoResourceCache(shellApi));
    await waitFor(() => expect(finishHome).toBeDefined());
    expect(screen.queryByText("Updating in the background…")).not.toBeInTheDocument();
    expect(screen.queryByText("Some information may be out of date.")).not.toBeInTheDocument();
    await act(async () => { finishHome?.(homeReads("/home")); });
    phase = "offline";
    act(() => invalidateAltoResourceCache(shellApi));
    expect(await screen.findByText("Some information may be out of date.")).toBeVisible();
    phase = "ready";
    fireEvent.click(screen.getByRole("button", { name: "Retry refresh" }));
    await waitFor(() => expect(screen.queryByText("Some information may be out of date.")).not.toBeInTheDocument());
    expect(screen.queryByText("Updating in the background…")).not.toBeInTheDocument();
    expect(fetcher.mock.calls.every((call) => !(call[1] as RequestInit | undefined)?.method || (call[1] as RequestInit).method === "GET")).toBe(true);
  });

  it("opens the canonical Northstar request directly in the Home conversation using the same run and actor", async () => {
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.endsWith("/demo/runs/run-1/launch-request")) return Promise.resolve(json({ request_id: "request-1" }));
      return Promise.resolve(homeReads(url));
    });
    vi.stubGlobal("fetch", fetcher);
    render(<HomeView api={api} workspace={workspace} onStartPlanning={vi.fn()} />);
    const launch = await screen.findByRole("button", { name: "Prepare the Northstar launch plan" });
    await waitFor(() => expect(launch).toBeEnabled());
    fireEvent.click(launch);
    await waitFor(() => expect(window.location.hash).toBe("#/home?request=request-1"));
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(writes).toHaveLength(1);
    expect(writes[0]![1].headers).toMatchObject({ "X-Demo-Run-ID": "run-1", "X-Demo-Actor-Session-ID": "actor-1" });
    expect(writes[0]![0]).not.toContain("/simulation");
  });

  it("enables Northstar planning for the safe operator-managed binding response", async () => {
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/ai-provider/demo-binding")) return Promise.resolve(json({
        provider: "vertex_ai",
        credential_kind: "vertex_service_account",
        management_mode: "operator_managed",
        can_manage: false,
        status: "configured",
      }));
      if (init?.method === "POST" && url.endsWith("/demo/runs/run-1/launch-request")) {
        return Promise.resolve(json({ request_id: "request-operator" }));
      }
      return Promise.resolve(homeReads(url));
    });
    vi.stubGlobal("fetch", fetcher);

    render(<HomeView api={api} workspace={workspace} onStartPlanning={vi.fn()} />);

    const launch = await screen.findByRole("button", { name: "Prepare the Northstar launch plan" });
    await waitFor(() => expect(launch).toBeEnabled());
    expect(screen.queryByText("Your Live workspace needs an AI credential bound before planning.")).not.toBeInTheDocument();
    fireEvent.click(launch);
    await waitFor(() => expect(window.location.hash).toBe("#/home?request=request-operator"));
  });

  it("completes guided coordination only after the canonical request succeeds", async () => {
    const onSuccess = vi.fn();
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/ai-provider/demo-binding")) return Promise.resolve(json({ ...binding, management_mode: "operator_managed" }));
      if (init?.method === "POST" && url.endsWith("/demo/runs/run-1/launch-request")) return Promise.resolve(json({ request_id: "request-guided" }));
      return Promise.resolve(homeReads(url));
    });
    vi.stubGlobal("fetch", fetcher);
    render(<HomeView api={api} workspace={workspace} onStartPlanning={vi.fn()} guidedLaunch={{ idempotencyKey: "maya-onboarding:launch:stable-key", onSuccess }} />);
    const launch = await screen.findByRole("button", { name: "Prepare the Northstar launch plan" });
    await waitFor(() => expect(launch).toBeEnabled());
    expect(launch).toHaveAttribute("data-onboarding-target", "launch");
    fireEvent.click(launch);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith("request-guided"));
    const write = fetcher.mock.calls.find(([url, init]) => url.endsWith("/launch-request") && init?.method === "POST");
    expect(write?.[1].headers).toMatchObject({ "Idempotency-Key": "maya-onboarding:launch:stable-key" });
    expect(window.location.hash).toBe("#/home?request=request-guided");
  });

  it("retains guided coordination when request creation fails", async () => {
    const onSuccess = vi.fn();
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/ai-provider/demo-binding")) return Promise.resolve(json({ ...binding, management_mode: "operator_managed" }));
      if (init?.method === "POST" && url.endsWith("/demo/runs/run-1/launch-request")) return Promise.resolve(json({ detail: "Launch unavailable" }, 503));
      return Promise.resolve(homeReads(url));
    });
    vi.stubGlobal("fetch", fetcher);
    render(<HomeView api={api} workspace={workspace} onStartPlanning={vi.fn()} guidedLaunch={{ idempotencyKey: "maya-onboarding:launch:retry-key", onSuccess }} />);
    const launch = await screen.findByRole("button", { name: "Prepare the Northstar launch plan" });
    await waitFor(() => expect(launch).toBeEnabled());
    fireEvent.click(launch);
    expect(await screen.findByText("Launch unavailable")).toBeVisible();
    expect(onSuccess).not.toHaveBeenCalled();
    expect(launch).toBeEnabled();
  });

  it("requires a request preview after Plan work; sending the draft makes no AI or planning mutation", async () => {
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method && init.method !== "GET") throw new Error(`No command should run before confirmation: ${url}`);
      return Promise.resolve(homeReads(url));
    });
    vi.stubGlobal("fetch", fetcher);
    function Flow() {
      const [draft, setDraft] = useState<string | null>(null);
      return draft === null ? <HomeView api={api} workspace={workspace} onStartPlanning={setDraft} /> : <PlanningConversation api={api} initialDraft={draft} />;
    }
    render(<Flow />);
    fireEvent.click(await screen.findByRole("button", { name: "Plan work" }));
    fireEvent.change(screen.getByLabelText("Message ALTO"), { target: { value: "Coordinate the release handoff." } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByLabelText("What needs to happen?")).toHaveValue("Coordinate the release handoff.");
    expect(screen.getByRole("button", { name: "Prepare plan" })).toBeVisible();
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("does not expose manager planning controls while authoritative workspace bootstrap is missing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => Promise.resolve(homeReads(url))));
    render(<HomeView api={api} workspace={null} onStartPlanning={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Plan work" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare the Northstar launch plan" })).not.toBeInTheDocument();
  });

  it("sends employees to their returned assigned task and never exposes the planning shortcut", async () => {
    const fetcher = vi.fn().mockImplementation((url: string) => Promise.resolve(url.endsWith("/home") ? json({ recent_projects: [], completed_projects: [], actions: [], tasks: [{ task_id: "task-1", title: "Prepare the approved design brief", status: "assigned" }] }) : homeReads(url)));
    vi.stubGlobal("fetch", fetcher);
    render(<HomeView api={api} workspace={{ ...workspace, viewer: { ...workspace.viewer, employee_id: "iris", display_name: "Iris", role: "employee" }, demo_run: { ...workspace.demo_run!, actor_name: "Iris" } }} onStartPlanning={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Prepare the approved design brief/ }));
    expect(window.location.hash).toBe("#/tasks/task-1");
    expect(screen.queryByRole("button", { name: "Plan work" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare the Northstar launch plan" })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.every(([url, init]) => (!init?.method || init.method === "GET") && !url.includes("ai-provider"))).toBe(true);
  });

  it.each(["authored_replay", "authored_d0_check", undefined])("prevents binding or storing credentials outside a known Live run (%s)", async (mode) => {
    const fetcher = vi.fn().mockResolvedValue(json({ ...binding, current_profile_version_id: null }));
    vi.stubGlobal("fetch", fetcher);
    render(<DemoProviderSettings api={api} runMode={mode} />);
    expect(await screen.findByRole("button", { name: "Bind exact version to this run" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Write-only credential"), { target: { value: "fake-test-only-not-a-secret" } });
    expect(screen.getByRole("button", { name: "Validate and store securely" })).toBeDisabled();
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("keeps an existing bound credential and offers Home without uploading it again", async () => {
    const fetcher = vi.fn().mockResolvedValue(json(binding)); vi.stubGlobal("fetch", fetcher);
    render(<DemoProviderSettings api={api} runMode="live" />);
    expect(await screen.findByText("This exact version is bound to the selected run.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Bind exact version to this run" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Go to Home" }));
    expect(window.location.hash).toBe("#/home");
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
});

describe("restored read-only assistant threads", () => {
  it("restores a selected thread and appends to that exact thread without creating a new one", async () => {
    const onThreadChange = vi.fn();
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if ((!init?.method || init.method === "GET") && url.endsWith("/assistant/threads/thread-1")) return Promise.resolve(json(thread));
      if (init?.method === "POST" && url.endsWith("/assistant/threads/thread-1/messages")) return Promise.resolve(json(thread));
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} initialThreadId="thread-1" onThreadChange={onThreadChange} />);
    expect(await screen.findByText("Your saved authorised answer.")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Message ALTO"), { target: { value: "What is due next?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(onThreadChange).toHaveBeenCalledWith("thread-1"));
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(writes).toHaveLength(1);
    expect(writes[0]![0]).toContain("/assistant/threads/thread-1/messages");
    expect(JSON.parse(writes[0]![1].body)).toEqual({ content: "What is due next?", context: { kind: "global" } });
  });

  it("does not fork a new thread while the selected saved conversation is still loading", async () => {
    const fetcher = vi.fn().mockImplementation(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} initialThreadId="thread-1" />);
    fireEvent.change(screen.getByLabelText("Message ALTO"), { target: { value: "Continue this conversation." } });
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("does not start a new thread when the selected saved thread is no longer authorised", async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ detail: "This conversation is no longer available." }, 403));
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} initialThreadId="thread-1" />);
    expect(await screen.findByText("This conversation is no longer available.")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Message ALTO"), { target: { value: "Continue here." } });
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
});

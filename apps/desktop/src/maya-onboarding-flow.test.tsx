import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defaultPreferences, type AssistantThread, type WorkspaceBootstrap } from "./alto-api";
import { clearAltoResourceCache } from "./alto-resource-cache";
import { AltoShell } from "./alto-shell";
import { MAYA_ONBOARDING_STORAGE_KEY, type MayaOnboardingState } from "./maya-onboarding-state";

const config = {
  apiMode: "static" as const,
  apiOrigin: "https://onboarding.example.invalid",
  productName: "ALTO",
  supabaseConfigured: true,
  supabaseUrl: "https://project.example.invalid",
  supabasePublishableKey: "sb_publishable_test",
  defaultCompanyId: "11111111-1111-4111-8111-111111111111",
  hackathonDemo: true,
};
const session = {
  status: "connected" as const,
  userId: "judge-onboarding",
  unreadNotifications: 0,
  administrativeRole: "manager",
  employeeId: null,
  api: { apiOrigin: config.apiOrigin, companyId: config.defaultCompanyId, accessToken: "anonymous-demo-token" },
};
const workspace: WorkspaceBootstrap = {
  company: { id: config.defaultCompanyId, name: "Northstar", is_demo: true },
  viewer: { user_id: session.userId, employee_id: "maya", display_name: "Maya", role: "manager", job_title: "Delivery Director" },
  demo_run: { id: "run-maya", mode: "live", clock_at: "2026-09-28T09:00:00Z", actor_name: "Maya", row_version: 1 },
  capabilities: [],
};
const answer: AssistantThread = {
  id: "guided-thread", status: "completed", stage: null, error: null,
  messages: [
    { id: "guided-question", role: "user", content: "Hi! What are you and what do you do?", created_at: "2026-09-28T09:00:00Z", citations: [] },
    { id: "guided-answer", role: "assistant", content: "I help your team coordinate work and keep people in control.", created_at: "2026-09-28T09:00:01Z", citations: [] },
  ],
};

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  window.localStorage.clear();
  window.location.hash = "/home";
});
afterEach(() => {
  cleanup();
  clearAltoResourceCache();
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("locked Maya first-run onboarding", () => {
  it("requires the real AI, deployment, assistant, and Northstar success flow, then supports replay", async () => {
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.endsWith("/demo/quickstart")) return Promise.resolve(json({ run_id: "run-maya", actor_session_id: "actor-maya", actor_key: "maya", provider_status: "configured" }));
      if (url.endsWith("/workspace")) return Promise.resolve(json(workspace));
      if (url.endsWith("/me/preferences")) return Promise.resolve(json({ ...defaultPreferences, reduce_motion: true }));
      if (url.endsWith("/home")) return Promise.resolve(json({ recent_projects: [], completed_projects: [], actions: [], tasks: [] }));
      if (url.endsWith("/ai-provider/demo-binding")) return Promise.resolve(json({ provider: "vertex_ai", credential_kind: "vertex_service_account", management_mode: "operator_managed", can_manage: false, status: "configured" }));
      if (init?.method === "POST" && url.endsWith("/assistant/threads")) return Promise.resolve(json({ id: "guided-thread", status: "pending", stage: "queued", error: null, messages: [] }));
      if (init?.method === "POST" && url.endsWith("/assistant/threads/guided-thread/messages")) return Promise.resolve(json(answer));
      if ((!init?.method || init.method === "GET") && url.endsWith("/assistant/threads/guided-thread")) return Promise.resolve(json(answer));
      if (init?.method === "POST" && url.endsWith("/demo/runs/run-maya/launch-request")) return Promise.resolve(json({ request_id: "request-onboarding" }));
      if (url.endsWith("/planning-context")) return Promise.resolve(json({ sources: [], requests: [] }));
      return Promise.resolve(json({ detail: `No fixture for ${url}` }, 404));
    });
    vi.stubGlobal("fetch", fetcher);

    render(<AltoShell config={config} session={session} service={{ state: "reachable", detail: "Ready" }} onSignOut={async () => undefined} saveDeployment={() => undefined} resetDeployment={() => undefined} authController={{ current: null }} />);

    expect(await screen.findByRole("heading", { name: "You’re exploring Northstar as Maya." })).toBeVisible();
    expect(screen.queryByRole("button", { name: /skip|close/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start tour" }));

    expect(await screen.findByRole("heading", { name: "Your AI is ready" })).toBeVisible();
    expect(await screen.findByText("Configured for the hackathon demo")).toBeVisible();
    expect(window.location.hash).toBe("#/settings/ai");
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("heading", { name: "Already connected" })).toBeVisible();
    expect(window.location.hash).toBe("#/settings/deployment");
    fireEvent.click(screen.getByRole("button", { name: "Continue to Home" }));

    expect(await screen.findByText("I help your team coordinate work and keep people in control.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Ask a question" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Message ALTO")).toBeDisabled();
    await waitFor(() => expect(screen.getByText("The answer shown in Home came from the real assistant. Continue when you’re ready to coordinate work.")).toBeVisible());
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    const launch = await screen.findByRole("button", { name: "Prepare the Northstar launch plan" });
    await waitFor(() => expect(launch).toBeEnabled());
    fireEvent.click(launch);
    await waitFor(() => expect((JSON.parse(window.localStorage.getItem(MAYA_ONBOARDING_STORAGE_KEY) ?? "{}") as MayaOnboardingState).stage).toBe("complete"));
    expect(window.location.hash).toBe("#/home?request=request-onboarding");
    expect(screen.queryByText("Step 3 of 3 · Coordinate work")).not.toBeInTheDocument();

    const writes = fetcher.mock.calls.filter(([, request]) => request?.method === "POST");
    expect(writes.filter(([url]) => url.endsWith("/assistant/threads"))).toHaveLength(1);
    expect(writes.filter(([url]) => url.endsWith("/assistant/threads/guided-thread/messages"))).toHaveLength(1);
    expect(writes.filter(([url]) => url.endsWith("/launch-request"))).toHaveLength(1);
    const completed = JSON.parse(window.localStorage.getItem(MAYA_ONBOARDING_STORAGE_KEY) ?? "{}") as MayaOnboardingState;

    window.location.hash = "/settings/about";
    fireEvent.click(await screen.findByRole("button", { name: "Replay onboarding" }));
    expect(await screen.findByRole("heading", { name: "You’re exploring Northstar as Maya." })).toBeVisible();
    const replayed = JSON.parse(window.localStorage.getItem(MAYA_ONBOARDING_STORAGE_KEY) ?? "{}") as MayaOnboardingState;
    expect(replayed.stage).toBe("welcome");
    expect(replayed.threadCommandKey).not.toBe(completed.threadCommandKey);
    expect(replayed.messageCommandKey).not.toBe(completed.messageCommandKey);
    expect(replayed.launchCommandKey).not.toBe(completed.launchCommandKey);
  });

  it("keeps Step 2 retryable when the guided AI command is rate limited", async () => {
    window.localStorage.setItem(MAYA_ONBOARDING_STORAGE_KEY, JSON.stringify({
      version: 1,
      stage: "question_typing",
      threadCommandKey: "maya-onboarding:thread:rate-limit",
      messageCommandKey: "maya-onboarding:message:rate-limit",
      launchCommandKey: "maya-onboarding:launch:rate-limit",
    } satisfies MayaOnboardingState));
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.endsWith("/demo/quickstart")) return Promise.resolve(json({ run_id: "run-maya", actor_session_id: "actor-maya", actor_key: "maya", provider_status: "configured" }));
      if (url.endsWith("/workspace")) return Promise.resolve(json(workspace));
      if (url.endsWith("/me/preferences")) return Promise.resolve(json({ ...defaultPreferences, reduce_motion: true }));
      if (url.endsWith("/home")) return Promise.resolve(json({ recent_projects: [], completed_projects: [], actions: [], tasks: [] }));
      if (url.endsWith("/ai-provider/demo-binding")) return Promise.resolve(json({ provider: "vertex_ai", credential_kind: "vertex_service_account", management_mode: "operator_managed", can_manage: false, status: "configured" }));
      if (url.endsWith("/planning-context")) return Promise.resolve(json({ sources: [], requests: [] }));
      if (init?.method === "POST" && url.endsWith("/assistant/threads")) return Promise.resolve(json({ id: "rate-limited-thread", status: "pending", stage: "queued", error: null, messages: [] }));
      if (init?.method === "POST" && url.endsWith("/assistant/threads/rate-limited-thread/messages")) {
        return Promise.resolve(new Response(JSON.stringify({ detail: "This demo has received too many new AI requests. Retry in 17 seconds." }), {
          status: 429,
          headers: { "Content-Type": "application/json", "Retry-After": "17" },
        }));
      }
      if ((!init?.method || init.method === "GET") && url.endsWith("/assistant/threads/rate-limited-thread")) return Promise.resolve(json({ id: "rate-limited-thread", status: "pending", stage: "queued", error: null, messages: [] }));
      return Promise.resolve(json({ detail: `No fixture for ${url}` }, 404));
    });
    vi.stubGlobal("fetch", fetcher);

    render(<AltoShell config={config} session={session} service={{ state: "reachable", detail: "Ready" }} onSignOut={async () => undefined} saveDeployment={() => undefined} resetDeployment={() => undefined} authController={{ current: null }} />);

    expect(await screen.findAllByText(
      "This demo has received too many new AI requests. Retry in 17 seconds.",
    )).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Retry guided question" })).toBeVisible();
    const saved = JSON.parse(window.localStorage.getItem(MAYA_ONBOARDING_STORAGE_KEY) ?? "{}") as MayaOnboardingState;
    expect(saved.stage).toBe("question_waiting");
    expect(saved.assistantThreadId).toBe("rate-limited-thread");
  });
});

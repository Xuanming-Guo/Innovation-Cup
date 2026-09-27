import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Assistant } from "./alto-assistant";
import { clearAltoResourceCache, invalidateAltoResourceCache } from "./alto-resource-cache";
import type { AssistantPendingAction, AssistantThread } from "./alto-api";

const api = { apiOrigin: "https://api.example.invalid", companyId: "company-1", accessToken: "private-token" };
afterEach(() => { cleanup(); clearAltoResourceCache(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("explicit microphone privacy lifecycle", () => {
  it("disables capture when the host has no real transcription capability", () => {
    render(<Assistant api={api} voiceEnabled={false}/>);
    expect(screen.getByRole("button", { name: "Start microphone" })).toBeDisabled();
    expect(screen.getByRole("textbox")).toBeEnabled();
  });
  it("does not request microphone access for unsupported MIME formats", async () => {
    const getUserMedia = vi.fn();
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    vi.stubGlobal("MediaRecorder", class { static isTypeSupported() { return false; } });
    render(<Assistant api={api} voiceEnabled/>);
    fireEvent.click(screen.getByRole("button", { name: "Start microphone" }));
    expect(await screen.findByText("This device does not support a permitted recording format. You can type instead.")).toBeVisible();
    expect(getUserMedia).not.toHaveBeenCalled();
  });
  it("stops real tracks and does not upload or send when an overlay is unmounted during recording", async () => {
    const stopTrack = vi.fn(), closeAudio = vi.fn().mockResolvedValue(undefined), fetcher = vi.fn();
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] });
    vi.stubGlobal("fetch", fetcher); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    vi.stubGlobal("AudioContext", class { close = closeAudio; createAnalyser() { return { fftSize: 0, frequencyBinCount: 32, getByteFrequencyData: vi.fn() }; } createMediaStreamSource() { return { connect: vi.fn() }; } });
    let stopped = false;
    vi.stubGlobal("MediaRecorder", class {
      static isTypeSupported(type: string) { return type.startsWith("audio/webm"); }
      state = "inactive"; mimeType = "audio/webm"; onstop: (() => void) | null = null;
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      start() { this.state = "recording"; }
      stop() { stopped = true; this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["explicit recording"], { type: this.mimeType }) }); this.onstop?.(); }
    });
    const view = render(<Assistant api={api} voiceEnabled overlay/>);
    expect(getUserMedia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Start microphone" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Stop recording and transcribe" })).toBeVisible());
    view.unmount();
    expect(stopped).toBe(true); expect(stopTrack).toHaveBeenCalled(); expect(closeAudio).toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("saved assistant conversation authority", () => {
  const context = { ...api, authUserId: "user-1" };
  const original: AssistantThread = { id: "thread-1", status: "completed", stage: null, error: null, messages: [{ id: "message-1", role: "assistant", content: "Private original reply", created_at: "2026-09-27T10:00:00Z", citations: [] }] };
  const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });

  it("hides a local reply after deletion and keeps it hidden throughout retry", async () => {
    let serverThread = original;
    let denied = false;
    let retryResponse: ((response: Response) => void) | null = null;
    let holdRetry = false;
    const fetcher = vi.fn((_input: unknown, init?: RequestInit) => {
      if (init?.method === "POST") {
        serverThread = { ...original, messages: [...original.messages, { ...original.messages[0]!, id: "message-2", content: "Private locally received reply" }] };
        return Promise.resolve(json(serverThread));
      }
      if (holdRetry) return new Promise<Response>((resolve) => { retryResponse = resolve; });
      return Promise.resolve(denied ? json({ detail: "Conversation no longer available" }, 404) : json(serverThread));
    });
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={context} initialThreadId="thread-1" voiceEnabled />);
    expect(await screen.findByText("Private original reply")).toBeVisible();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Follow up" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Private locally received reply")).toBeVisible();
    denied = true;
    act(() => invalidateAltoResourceCache(context));
    expect(await screen.findByText("Conversation no longer available")).toBeVisible();
    expect(screen.queryByText("Private locally received reply")).not.toBeInTheDocument();
    expect(screen.queryByText("Private original reply")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Start microphone" })).toBeDisabled();
    holdRetry = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(retryResponse).not.toBeNull());
    expect(screen.queryByText("Private locally received reply")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    await act(async () => { retryResponse?.(json({ ...original, messages: [{ ...original.messages[0]!, content: "Fresh permitted reply" }] })); });
    expect(screen.getByText("Fresh permitted reply")).toBeVisible();
    expect(screen.queryByText("Private locally received reply")).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter((call) => call[1]?.method === "POST")).toHaveLength(1);
  });

  it("keeps the authorised cached conversation visible during a transient refresh failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(original)).mockRejectedValueOnce(new TypeError("Network temporarily unavailable")));
    render(<Assistant api={context} initialThreadId="thread-1" />);
    expect(await screen.findByText("Private original reply")).toBeVisible();
    act(() => invalidateAltoResourceCache(context));
    expect(await screen.findByText("Network temporarily unavailable")).toBeVisible();
    expect(screen.getByText("Private original reply")).toBeVisible();
  });

  it("hides a deleted thread reported by polling even when its saved snapshot still exists", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValueOnce(json({ ...original, status: "running" })).mockResolvedValueOnce(json({ detail: "Thread was deleted" }, 404));
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={context} initialThreadId="thread-1" voiceEnabled />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Private original reply")).toBeVisible();
    await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    expect(screen.getByText("Thread was deleted")).toBeVisible();
    expect(screen.queryByText("Private original reply")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Start microphone" })).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});

describe("guided onboarding question", () => {
  it("types the exact prompt progressively when reduced motion is not requested", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} guidedPrompt={{
      prompt: "Hi! What are you and what do you do?",
      threadCommandKey: "maya-onboarding:thread:animated-key",
      messageCommandKey: "maya-onboarding:message:animated-key",
      reduceMotion: false,
      onThreadCreated: vi.fn(),
      onStatus: vi.fn(),
    }} />);
    expect(screen.getByLabelText("Message ALTO")).toHaveValue("");
    await act(async () => { await vi.advanceTimersByTimeAsync(84); });
    expect(screen.getByLabelText("Message ALTO")).toHaveValue("Hi!");
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(screen.getByLabelText("Message ALTO")).toHaveValue("Hi! What are you and what do you do?");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("selects Ask, sends the exact prompt once with stable keys, and waits for a real answer", async () => {
    const onThreadCreated = vi.fn();
    const onStatus = vi.fn();
    const onPlanRequest = vi.fn();
    const created: AssistantThread = { id: "guided-thread", status: "pending", stage: "queued", error: null, messages: [] };
    const answered: AssistantThread = {
      id: "guided-thread", status: "completed", stage: null, error: null,
      messages: [
        { id: "guided-user", role: "user", content: "Hi! What are you and what do you do?", created_at: "2026-09-27T10:00:00Z", citations: [] },
        { id: "guided-answer", role: "assistant", content: "I help teams coordinate work safely.", created_at: "2026-09-27T10:00:01Z", citations: [] },
      ],
    };
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.endsWith("/assistant/threads")) return Promise.resolve(new Response(JSON.stringify(created)));
      if (init?.method === "POST" && url.endsWith("/assistant/threads/guided-thread/messages")) return Promise.resolve(new Response(JSON.stringify(answered)));
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);

    render(<Assistant api={api} onPlanRequest={onPlanRequest} guidedPrompt={{
      prompt: "Hi! What are you and what do you do?",
      threadCommandKey: "maya-onboarding:thread:test-key",
      messageCommandKey: "maya-onboarding:message:test-key",
      reduceMotion: true,
      onThreadCreated,
      onStatus,
    }} />);

    expect(screen.getByRole("button", { name: "Ask a question" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Plan work" })).toBeDisabled();
    expect(screen.getByLabelText("Message ALTO")).toBeDisabled();
    expect(await screen.findByText("I help teams coordinate work safely.")).toBeVisible();
    await waitFor(() => expect(onStatus).toHaveBeenCalledWith({ state: "completed" }));
    expect(onThreadCreated).toHaveBeenCalledTimes(1);
    expect(onThreadCreated).toHaveBeenCalledWith("guided-thread");
    expect(onPlanRequest).not.toHaveBeenCalled();
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(writes).toHaveLength(2);
    expect(writes[0]![1].headers).toMatchObject({ "Idempotency-Key": "maya-onboarding:thread:test-key" });
    expect(writes[1]![1].headers).toMatchObject({ "Idempotency-Key": "maya-onboarding:message:test-key" });
    expect(JSON.parse(writes[1]![1].body)).toEqual({ content: "Hi! What are you and what do you do?", context: { kind: "global" } });
  });

  it("does not silently replace an inaccessible saved guided thread", async () => {
    const onStatus = vi.fn();
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Conversation unavailable" }), { status: 404 }));
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} initialThreadId="missing-thread" guidedPrompt={{
      prompt: "Hi! What are you and what do you do?",
      threadId: "missing-thread",
      threadCommandKey: "maya-onboarding:thread:saved-key",
      messageCommandKey: "maya-onboarding:message:saved-key",
      reduceMotion: true,
      onThreadCreated: vi.fn(),
      onStatus,
    }} />);
    await waitFor(() => expect(onStatus).toHaveBeenCalledWith(expect.objectContaining({ state: "failed" })));
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });

  it("resumes the stable message command when reload happened just after thread creation", async () => {
    const empty: AssistantThread = { id: "created-before-reload", status: "pending", stage: null, error: null, messages: [] };
    const answered: AssistantThread = { ...empty, status: "completed", messages: [{ id: "answer-after-reload", role: "assistant", content: "Resumed without creating another thread.", created_at: "2026-09-27T10:00:01Z", citations: [] }] };
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if ((!init?.method || init.method === "GET") && url.endsWith("/assistant/threads/created-before-reload")) return Promise.resolve(new Response(JSON.stringify(empty)));
      if (init?.method === "POST" && url.endsWith("/assistant/threads/created-before-reload/messages")) return Promise.resolve(new Response(JSON.stringify(answered)));
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} initialThreadId="created-before-reload" guidedPrompt={{
      prompt: "Hi! What are you and what do you do?",
      threadId: "created-before-reload",
      threadCommandKey: "maya-onboarding:thread:reload-key",
      messageCommandKey: "maya-onboarding:message:reload-key",
      reduceMotion: true,
      onThreadCreated: vi.fn(),
      onStatus: vi.fn(),
    }} />);
    expect(await screen.findByText("Resumed without creating another thread.")).toBeVisible();
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(writes).toHaveLength(1);
    expect(writes[0]![0]).toContain("/created-before-reload/messages");
    expect(writes[0]![1].headers).toMatchObject({ "Idempotency-Key": "maya-onboarding:message:reload-key" });
  });
});

describe("explicit assistant plan actions", () => {
  const action: AssistantPendingAction = {
    id: "action-1", kind: "plan_change", status: "pending_confirmation", title: "Move Priya's QA review",
    summary: "Moves one task outside protected time while preserving its dependency.", project_id: "project-1",
    proposal_id: "proposal-2", plan_id: "plan-2",
    scope: [{ label: "Project", value: "Northstar Analytics Launch" }, { label: "Tasks", value: "Q1" }],
    changes: [{ id: "change-1", label: "Q1 · Validate integration", field: "schedule", before: "Tue 09:00–10:00", after: "Tue 10:00–11:00" }],
    violations: [], warnings: ["Priya will receive the updated task only after the plan is committed."],
    confirmation: { label: "Confirm and apply change", consequence: "ALTO will apply only the change shown above.", expected_version: 3 },
    result_target_path: "/projects/project-1/graph?proposal_id=proposal-3",
  };
  const thread: AssistantThread = {
    id: "thread-action", status: "completed", stage: null, error: null,
    messages: [{ id: "message-action", role: "assistant", content: "I prepared a schedule correction for review.", created_at: "2026-09-27T10:00:00Z", citations: [] }],
    pending_actions: [action],
  };

  it("shows exact scope and diff, then applies only after one explicit confirmation click", async () => {
    const completed = { ...thread, pending_actions: [{ ...action, status: "completed" as const }] };
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(thread))).mockResolvedValueOnce(new Response(JSON.stringify(completed)));
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} initialThreadId="thread-action"/>);
    expect(await screen.findByRole("region", { name: "Proposed action: Move Priya's QA review" })).toBeVisible();
    expect(screen.getByText("Northstar Analytics Launch")).toBeVisible();
    expect(screen.getByText("Tue 09:00–10:00")).toBeVisible();
    expect(screen.getByText("Tue 10:00–11:00")).toBeVisible();
    const confirm = screen.getByRole("button", { name: "Confirm and apply change" });
    expect(confirm).toBeEnabled();
    expect(fetcher).toHaveBeenCalledTimes(1);
    fireEvent.click(confirm);
    expect(await screen.findByText("Applied")).toBeVisible();
    const [url, options] = fetcher.mock.calls[1]!;
    expect(url).toContain("/assistant/threads/thread-action/actions/action-1/decision");
    expect(options.method).toBe("POST");
    expect(options.body).toBe(JSON.stringify({ decision: "confirm", expected_version: 3 }));
    fireEvent.click(screen.getByRole("button", { name: "Open exact updated plan" }));
    expect(window.location.hash).toBe("#/projects/project-1/graph?proposal_id=proposal-3");
  });

  it("blocks approval when the proposed action has a non-passing check", async () => {
    const blocked = { ...thread, pending_actions: [{ ...action, kind: "plan_approval" as const, violations: [{ id: "rule-1", title: "resource.priya", status: "violation", description: "Priya is already at capacity.", formula: null, source_label: "Working hours", source_version: "v1", candidate_values: null }] }] };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(blocked)));
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} initialThreadId="thread-action"/>);
    expect(await screen.findByText("1 recorded check not passing")).toBeVisible();
    expect(screen.getByRole("button", { name: "Confirm and apply change" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Revise this plan" }));
    expect(screen.getByRole("textbox")).toHaveValue("Revise this plan to resolve every recorded violation while preserving its approved goal, deadline, and source constraints.");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("lets a plan-change request address the current violations without creating a revision loop", async () => {
    const revision = { ...thread, pending_actions: [{ ...action, violations: [{ id: "rule-1", title: "resource.priya", status: "violation", description: "Priya is already at capacity.", formula: null, source_label: "Working hours", source_version: "v1", candidate_values: null }] }] };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(revision)));
    vi.stubGlobal("fetch", fetcher);
    render(<Assistant api={api} initialThreadId="thread-action"/>);
    expect(await screen.findByText("1 recorded check to address")).toBeVisible();
    expect(screen.getByText("Recorded checks the revision must address; no work changes until a new proposal is checked and approved.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Confirm and apply change" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Revise this plan" })).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

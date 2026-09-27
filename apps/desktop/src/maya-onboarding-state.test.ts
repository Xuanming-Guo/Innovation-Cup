import { describe, expect, it, vi } from "vitest";

import {
  MAYA_ONBOARDING_STORAGE_KEY,
  freshMayaOnboarding,
  mayaOnboardingRoute,
  readMayaOnboarding,
  retryMayaQuestion,
  writeMayaOnboarding,
} from "./maya-onboarding-state";

describe("Maya onboarding persistence", () => {
  it("stores only the versioned workflow identifiers and resumes a waiting thread", () => {
    const state = { ...freshMayaOnboarding(), stage: "question_waiting" as const, assistantThreadId: "thread-opaque-1" };
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: vi.fn((key: string, value: string) => values.set(key, value)),
    };
    writeMayaOnboarding(state, storage);
    expect(readMayaOnboarding(storage)).toEqual(state);
    const persisted = values.get(MAYA_ONBOARDING_STORAGE_KEY) ?? "";
    expect(persisted).not.toContain("answer");
    expect(persisted).not.toContain("token");
    expect(persisted).not.toContain("credential");
  });

  it("restarts corrupt state and creates fresh question keys only after Retry", () => {
    const corrupt = { getItem: () => "{not-json" };
    expect(readMayaOnboarding(corrupt).stage).toBe("welcome");
    const waiting = { ...freshMayaOnboarding(), stage: "question_waiting" as const, assistantThreadId: "thread-opaque-1" };
    const retried = retryMayaQuestion(waiting);
    expect(retried.stage).toBe("question_typing");
    expect(retried.assistantThreadId).toBeUndefined();
    expect(retried.threadCommandKey).not.toBe(waiting.threadCommandKey);
    expect(retried.messageCommandKey).not.toBe(waiting.messageCommandKey);
    expect(retried.launchCommandKey).toBe(waiting.launchCommandKey);
  });

  it("keeps every incomplete stage on its required route", () => {
    expect(mayaOnboardingRoute("ai")).toBe("/settings/ai");
    expect(mayaOnboardingRoute("deployment")).toBe("/settings/deployment");
    expect(mayaOnboardingRoute("question_waiting")).toBe("/home");
    expect(mayaOnboardingRoute("launch")).toBe("/home");
    expect(mayaOnboardingRoute("complete")).toBeNull();
  });
});

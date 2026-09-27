export const MAYA_ONBOARDING_STORAGE_KEY = "alto.onboarding.maya.v1";
export const MAYA_ONBOARDING_PROMPT = "Hi! What are you and what do you do?";

export type MayaOnboardingStage =
  | "welcome"
  | "ai"
  | "deployment"
  | "question_typing"
  | "question_waiting"
  | "question_result"
  | "launch"
  | "complete";

export interface MayaOnboardingState {
  version: 1;
  stage: MayaOnboardingStage;
  assistantThreadId?: string;
  threadCommandKey: string;
  messageCommandKey: string;
  launchCommandKey: string;
}

const STAGES = new Set<MayaOnboardingStage>([
  "welcome", "ai", "deployment", "question_typing", "question_waiting",
  "question_result", "launch", "complete",
]);
const THREAD_STAGES = new Set<MayaOnboardingStage>([
  "question_waiting", "question_result", "launch", "complete",
]);

function commandKey(kind: string): string {
  return `maya-onboarding:${kind}:${crypto.randomUUID()}`;
}

export function freshMayaOnboarding(): MayaOnboardingState {
  return {
    version: 1,
    stage: "welcome",
    threadCommandKey: commandKey("thread"),
    messageCommandKey: commandKey("message"),
    launchCommandKey: commandKey("launch"),
  };
}

function validKey(value: unknown): value is string {
  return typeof value === "string" && value.length >= 16 && value.length <= 128;
}

export function readMayaOnboarding(
  storage: Pick<Storage, "getItem"> = window.localStorage,
): MayaOnboardingState {
  try {
    const raw = storage.getItem(MAYA_ONBOARDING_STORAGE_KEY);
    if (!raw) return freshMayaOnboarding();
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return freshMayaOnboarding();
    const row = value as Record<string, unknown>;
    if (
      row.version !== 1
      || typeof row.stage !== "string"
      || !STAGES.has(row.stage as MayaOnboardingStage)
      || !validKey(row.threadCommandKey)
      || !validKey(row.messageCommandKey)
      || !validKey(row.launchCommandKey)
    ) return freshMayaOnboarding();
    const stage = row.stage as MayaOnboardingStage;
    const assistantThreadId = typeof row.assistantThreadId === "string"
      && row.assistantThreadId.length > 0
      && row.assistantThreadId.length <= 200
      ? row.assistantThreadId
      : undefined;
    if (THREAD_STAGES.has(stage) && !assistantThreadId) return freshMayaOnboarding();
    return {
      version: 1,
      stage,
      ...(assistantThreadId ? { assistantThreadId } : {}),
      threadCommandKey: row.threadCommandKey,
      messageCommandKey: row.messageCommandKey,
      launchCommandKey: row.launchCommandKey,
    };
  } catch {
    return freshMayaOnboarding();
  }
}

export function writeMayaOnboarding(
  state: MayaOnboardingState,
  storage: Pick<Storage, "setItem"> = window.localStorage,
): void {
  try {
    storage.setItem(MAYA_ONBOARDING_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Tour persistence is a convenience and never carries authority or private content.
  }
}

export function retryMayaQuestion(state: MayaOnboardingState): MayaOnboardingState {
  return {
    ...state,
    stage: "question_typing",
    assistantThreadId: undefined,
    threadCommandKey: commandKey("thread"),
    messageCommandKey: commandKey("message"),
  };
}

export function mayaOnboardingRoute(stage: MayaOnboardingStage): string | null {
  if (stage === "complete") return null;
  if (stage === "ai") return "/settings/ai";
  if (stage === "deployment") return "/settings/deployment";
  return "/home";
}

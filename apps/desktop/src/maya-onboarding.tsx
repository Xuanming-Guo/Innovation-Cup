import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { MayaOnboardingStage } from "./maya-onboarding-state";

const TARGETS: Partial<Record<MayaOnboardingStage, string>> = {
  ai: '[data-onboarding-target="ai"]',
  deployment: '[data-onboarding-target="deployment"]',
  question_typing: '[data-onboarding-target="assistant"]',
  question_waiting: '[data-onboarding-target="assistant"]',
  question_result: '[data-onboarding-target="assistant"]',
  launch: '[data-onboarding-target="launch"]',
};

function stepLabel(stage: MayaOnboardingStage): string {
  if (stage === "ai") return "Step 1 of 3 · AI";
  if (stage === "deployment") return "Step 1 of 3 · Deployment";
  if (stage.startsWith("question_")) return "Step 2 of 3 · Meet ALTO";
  if (stage === "launch") return "Step 3 of 3 · Coordinate work";
  return "Step 1 of 3 · Ready-to-use setup";
}

function stepNumber(stage: MayaOnboardingStage): number {
  if (stage.startsWith("question_")) return 2;
  if (stage === "launch" || stage === "complete") return 3;
  return 1;
}

export function MayaOnboardingCoachmark({
  stage,
  questionReady,
  questionFailure,
  onStart,
  onContinueAI,
  onContinueDeployment,
  onContinueQuestion,
  onRetryQuestion,
}: {
  stage: Exclude<MayaOnboardingStage, "complete">;
  questionReady: boolean;
  questionFailure: string | null;
  onStart: () => void;
  onContinueAI: () => void;
  onContinueDeployment: () => void;
  onContinueQuestion: () => void;
  onRetryQuestion: () => void;
}) {
  const card = useRef<HTMLElement>(null);
  const primary = useRef<HTMLButtonElement>(null);
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const selector = TARGETS[stage];

  useLayoutEffect(() => {
    let element: HTMLElement | null = null;
    let resizeObserver: ResizeObserver | null = null;
    const update = () => setRect(element?.getBoundingClientRect() ?? null);
    const findTarget = () => {
      const next = selector ? document.querySelector<HTMLElement>(selector) : null;
      if (next === element) return;
      resizeObserver?.disconnect();
      element?.classList.remove("alto-onboarding-target-active");
      element = next;
      setTarget(next);
      if (!next) { setRect(null); return; }
      next.classList.add("alto-onboarding-target-active");
      resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
      resizeObserver?.observe(next);
      update();
    };
    findTarget();
    const mutationObserver = new MutationObserver(findTarget);
    mutationObserver.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      mutationObserver.disconnect();
      resizeObserver?.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      element?.classList.remove("alto-onboarding-target-active");
    };
  }, [selector, stage]);

  useEffect(() => {
    const next = stage === "launch" ? target : primary.current ?? card.current;
    const focus = () => next?.focus();
    if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(focus);
    else window.setTimeout(focus, 0);
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") event.preventDefault();
      if (event.key === "Tab" && stage === "launch") {
        event.preventDefault();
        target?.focus();
        return;
      }
      if (event.key !== "Tab" || !card.current) return;
      const focusable = [...card.current.querySelectorAll<HTMLElement>("button:not([disabled]), [tabindex='0']")];
      if (!focusable.length) { event.preventDefault(); card.current.focus(); return; }
      const first = focusable[0]!;
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [stage, target]);

  const cardStyle: CSSProperties | undefined = rect ? {
    left: Math.max(16, Math.min(rect.left, window.innerWidth - 396)),
    top: window.innerHeight - rect.bottom > 260
      ? Math.min(window.innerHeight - 220, rect.bottom + 16)
      : Math.max(16, rect.top - 230),
  } : undefined;
  const currentStep = stepNumber(stage);
  const waiting = stage === "question_typing" || stage === "question_waiting";

  return <>
    <div className="alto-onboarding-backdrop" aria-hidden="true" />
    {rect && <div className="alto-onboarding-spotlight" aria-hidden="true" style={{ left: rect.left - 7, top: rect.top - 7, width: rect.width + 14, height: rect.height + 14 }} />}
    <aside
      ref={card}
      className={`alto-onboarding-coachmark ${rect ? "anchored" : "centered"}`}
      style={cardStyle}
      role={stage === "launch" ? "status" : "dialog"}
      aria-modal={stage === "launch" ? undefined : true}
      aria-labelledby="alto-onboarding-title"
      tabIndex={-1}
    >
      <div className="alto-onboarding-progress" aria-label={`Onboarding step ${currentStep} of 3`}>
        {[1, 2, 3].map((value) => <span key={value} className={value <= currentStep ? "active" : ""} />)}
      </div>
      <small>{stepLabel(stage)}</small>
      {stage === "welcome" && <>
        <h2 id="alto-onboarding-title">You’re exploring Northstar as Maya.</h2>
        <p>We’ll show you the ready-to-use demo setup, introduce ALTO, and then prepare a real launch plan.</p>
        <button ref={primary} className="alto-primary" onClick={onStart}>Start tour</button>
      </>}
      {stage === "ai" && <>
        <h2 id="alto-onboarding-title">Your AI is ready</h2>
        <p>We’ve handled the AI APIs and model setup for this demo, so you don’t need to fuss with keys. Please don’t spam it 🙂</p>
        <button ref={primary} className="alto-primary" disabled={!target} onClick={onContinueAI}>Continue</button>
      </>}
      {stage === "deployment" && <>
        <h2 id="alto-onboarding-title">Already connected</h2>
        <p>This build is connected to ALTO’s demo backend and the Northstar workspace. The locked values stay hidden in the downloadable demo.</p>
        <button ref={primary} className="alto-primary" disabled={!target} onClick={onContinueDeployment}>Continue to Home</button>
      </>}
      {stage.startsWith("question_") && <>
        <h2 id="alto-onboarding-title">Meet ALTO</h2>
        {questionFailure ? <>
          <p role="alert">{questionFailure}</p>
          <button ref={primary} className="alto-primary" onClick={onRetryQuestion}>Retry guided question</button>
        </> : waiting ? <p role="status">ALTO is answering… The tour will continue when its real response is ready.</p> : <>
          <p>The answer shown in Home came from the real assistant. Continue when you’re ready to coordinate work.</p>
          <button ref={primary} className="alto-primary" disabled={!questionReady} onClick={onContinueQuestion}>Continue</button>
        </>}
      </>}
      {stage === "launch" && <>
        <h2 id="alto-onboarding-title">Coordinate real work</h2>
        <p>Click the highlighted <strong>Prepare the Northstar launch plan</strong> button. The tour completes only after that real request is created.</p>
      </>}
    </aside>
  </>;
}

import { useCallback, useEffect, useRef, useState } from "react";
import { AltoApiError, altoRequest, safeTarget, type AltoApiContext, type AssistantContext, type AssistantPendingAction, type AssistantThread } from "./alto-api";
import { AltoLogo, Badge, ErrorNotice, Icon, IconButton } from "./alto-ui";
import { dateTime, humanize, navigate, useResource } from "./alto-state";
import { uploadPrivateFile } from "./alto-storage";
const GLOBAL: AssistantContext = { kind: "global" };
const MAX_AUDIO_BYTES = 8 * 1024 * 1024;
const activeThreadStatuses = ["queued", "running", "pending"];
const failedThreadStatuses = ["failed", "cancelled", "dead_letter", "review_required"];
export interface GuidedAssistantPrompt {
    prompt: string;
    threadId?: string | null;
    threadCommandKey: string;
    messageCommandKey: string;
    reduceMotion: boolean;
    onThreadCreated: (id: string) => void;
    onStatus: (result: { state: "waiting" | "completed" | "failed"; error?: string }) => void;
}
const actionLabel = (kind: AssistantPendingAction["kind"]) => kind === "plan_change" ? "Schedule change" : kind === "plan_approval" ? "Plan approval" : "Commit and assign";
function actionResultTarget(action: AssistantPendingAction): string {
    const project = `/projects/${encodeURIComponent(action.project_id)}/graph`;
    if (action.kind === "plan_change" && action.result_target_path)
        return safeTarget(action.result_target_path, project);
    if (action.proposal_id)
        return `${project}?proposal_id=${encodeURIComponent(action.proposal_id)}`;
    if (action.plan_id)
        return `${project}?plan_id=${encodeURIComponent(action.plan_id)}`;
    return safeTarget(action.result_target_path, project);
}
function AssistantActionCard({ action, busy, onDecision, onRevise }: {
    action: AssistantPendingAction;
    busy: boolean;
    onDecision: (decision: "confirm" | "dismiss") => void;
    onRevise: () => void;
}) {
    const violations = action.violations.filter((rule) => !["pass", "passed"].includes(rule.status.toLowerCase()));
    const blockingViolations = action.kind === "plan_change" ? [] : violations;
    const pending = action.status === "pending_confirmation";
    const executing = action.status === "executing";
    const finished = action.status === "completed";
    return <section className={`alto-assistant-action ${action.status}`} aria-label={`Proposed action: ${action.title}`}>
      <header>
<div><Badge tone={finished ? "mint" : "pending"}>{finished ? "Applied" : executing ? "Applying" : pending ? "Needs your confirmation" : humanize(action.status)}</Badge><span>{actionLabel(action.kind)}</span></div>
<strong>{action.title}</strong>
      </header>
      <p>{action.summary}</p>
      <div className="alto-action-scope" aria-label="Action scope">
<strong>Exact scope</strong>
<dl>{action.scope.map((item) => <div key={`${item.label}:${item.value}`}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
      </div>
      <div className="alto-action-changes">
<strong>{action.changes.length === 1 ? "1 proposed change" : `${action.changes.length} proposed changes`}</strong>
{action.changes.length > 0 ? <ul>{action.changes.map((change) => <li key={change.id}>
<span>{change.label}</span>
<small>{humanize(change.field)}</small>
<div><del>{change.before ?? "Not set"}</del><Icon name="right" size={14}/><ins>{change.after}</ins></div>
</li>)}</ul> : <p className="alto-caption">No schedule fields change in this action.</p>}
      </div>
      {violations.length > 0 && <div className={`alto-action-violations ${action.kind === "plan_change" ? "revision-requirements" : ""}`} role={action.kind === "plan_change" ? "status" : "alert"}>
<strong>{violations.length} recorded {violations.length === 1 ? "check" : "checks"} {action.kind === "plan_change" ? "to address" : "not passing"}</strong>
<p>{action.kind === "plan_change" ? "Recorded checks the revision must address; no work changes until a new proposal is checked and approved." : "This action cannot be confirmed until its exact preview passes every required check."}</p>
<ul>{violations.map((rule) => <li key={rule.id}><span>{humanize(rule.title)}</span><small>{rule.description}</small></li>)}</ul>
{action.kind !== "plan_change" && <button type="button" className="alto-secondary" onClick={onRevise}>Revise this plan</button>}
      </div>}
      {action.warnings.length > 0 && <div className="alto-action-warnings"><strong>Before you continue</strong><ul>{action.warnings.map((warning, index) => <li key={`${index}:${warning}`}>{warning}</li>)}</ul></div>}
      {pending && <>
<p className="alto-action-confirmation">Review the exact preview above. {action.confirmation.consequence}</p>
<div className="alto-button-row">
<button type="button" className="alto-primary" disabled={busy || blockingViolations.length > 0} onClick={() => onDecision("confirm")}>{busy ? "Applying…" : action.confirmation.label}</button>
<button type="button" className="alto-secondary" disabled={busy} onClick={() => onDecision("dismiss")}>Dismiss proposal</button>
</div>
      </>}
      {executing && <div className="alto-action-running" role="status"><span/>ALTO is applying only the confirmed action. You can leave this page.</div>}
      {finished && <button type="button" className="alto-secondary" onClick={() => navigate(actionResultTarget(action))}>Open exact updated plan</button>}
      {["dismissed", "expired", "failed"].includes(action.status) && <p className="alto-caption">No unconfirmed schedule changes were applied.</p>}
    </section>;
}
export function Assistant({ api, context = GLOBAL, placeholder = "What would you like to coordinate?", voiceEnabled = false, overlay = false, onPlanRequest, initialThreadId, onThreadChange, guidedPrompt }: {
    api?: AltoApiContext;
    context?: AssistantContext;
    placeholder?: string;
    voiceEnabled?: boolean;
    overlay?: boolean;
    onPlanRequest?: (text: string) => void;
    initialThreadId?: string | null;
    onThreadChange?: (id: string) => void;
    guidedPrompt?: GuidedAssistantPrompt;
}) {
    const [text, setText] = useState("");
    const [localThreadState, setLocalThread] = useState<{ thread: AssistantThread; savedSnapshot: AssistantThread | null } | null>(null);
    const savedThread = useResource<AssistantThread>(api, initialThreadId ? `/assistant/threads/${encodeURIComponent(initialThreadId)}` : null);
    const localThread = localThreadState?.thread ?? null;
    const setThread = useCallback((value: AssistantThread | null) => {
        setLocalThread(value ? { thread: value, savedSnapshot: savedThread.data } : null);
    }, [savedThread.data]);
    const [deniedThread, setDeniedThread] = useState<{ id: string; snapshot: AssistantThread | null } | null>(null);
    const threadUnavailable = [401, 403, 404].includes(savedThread.errorStatus ?? 0) || Boolean(
        deniedThread && (!initialThreadId || initialThreadId === deniedThread.id)
        && (!savedThread.data || savedThread.data === deniedThread.snapshot),
    );
    // A retained local reply is not authority to redisplay a deleted/revoked thread.
    // Retry keeps it hidden until a fresh authorised GET actually succeeds.
    const thread = threadUnavailable || (initialThreadId && !savedThread.data) ? null
        : localThread && (!initialThreadId || (localThread.id === initialThreadId && localThreadState?.savedSnapshot === savedThread.data)) ? localThread : savedThread.data;
    const rejectThread = useCallback((value: unknown, id?: string) => {
        if (id && value instanceof AltoApiError && [401, 403, 404].includes(value.status)) {
            setDeniedThread({ id, snapshot: savedThread.data });
            setThread(null);
        }
    }, [savedThread.data, setThread]);
    const [composerMode, setComposerMode] = useState<"plan" | "ask">(guidedPrompt ? "ask" : onPlanRequest && !initialThreadId ? "plan" : "ask");
    const restoringThread = threadUnavailable || (Boolean(initialThreadId) && (!thread || Boolean(savedThread.error)));
    const [busy, setBusy] = useState(false);
    const [actionBusy, setActionBusy] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const guidedErrorCommand = useRef(guidedPrompt?.messageCommandKey ?? null);
    const [showConversation, setShowConversation] = useState(Boolean(guidedPrompt));
    const [explicitContext, setExplicitContext] = useState<AssistantContext | null>(null);
    const [recording, setRecording] = useState(false);
    const [transcribing, setTranscribing] = useState(false);
    const [transcriptionId, setTranscriptionId] = useState<string | null>(null);
    const [levels, setLevels] = useState<number[]>(Array.from({ length: 24 }, () => 2));
    const recorder = useRef<MediaRecorder | null>(null);
    const stream = useRef<MediaStream | null>(null);
    const audioContext = useRef<AudioContext | null>(null);
    const frame = useRef<number | null>(null);
    const stopTimer = useRef<number | null>(null);
    const alive = useRef(true);
    const accessDenied = useRef(false);
    const messageList = useRef<HTMLDivElement>(null);
    const guidedSubmission = useRef<string | null>(null);
    const binding = explicitContext ?? context;
    function releaseAudio() {
        if (stopTimer.current !== null)
            window.clearTimeout(stopTimer.current);
        if (frame.current !== null)
            window.cancelAnimationFrame(frame.current);
        stream.current?.getTracks().forEach((track) => track.stop());
        stream.current = null;
        void audioContext.current?.close();
        audioContext.current = null;
    }
    useEffect(() => {
        alive.current = true;
        return () => { alive.current = false; if (recorder.current?.state === "recording")
            recorder.current.stop(); releaseAudio(); };
    }, []);
    useEffect(() => { if (messageList.current) messageList.current.scrollTop = messageList.current.scrollHeight; }, [thread?.messages.length]);
    useEffect(() => {
        accessDenied.current = threadUnavailable;
        if (!threadUnavailable) return;
        const instance = recorder.current;
        if (instance?.state === "recording") {
            // Stop capture without uploading the rejected conversation's recording.
            instance.onstop = () => setRecording(false);
            instance.stop();
        }
        releaseAudio();
    }, [threadUnavailable]);
    useEffect(() => {
        if (!guidedPrompt || guidedErrorCommand.current === guidedPrompt.messageCommandKey)
            return;
        guidedErrorCommand.current = guidedPrompt.messageCommandKey;
        setError(null);
    }, [guidedPrompt]);
    useEffect(() => {
        if (!api || !transcriptionId || threadUnavailable)
            return;
        const controller = new AbortController();
        const timer = window.setInterval(() => {
            void altoRequest<{
                id: string;
                status: string;
                transcript?: string;
                error?: string;
            }>(api, `/voice/transcriptions/${transcriptionId}`, { signal: controller.signal }).then((result) => {
                if (controller.signal.aborted)
                    return;
                if (result.status === "succeeded" || result.status === "completed") {
                    setText((current) => `${current}${current ? " " : ""}${result.transcript ?? ""}`);
                    setTranscriptionId(null);
                    setTranscribing(false);
                }
                else if (["failed", "cancelled", "dead_letter", "review_required"].includes(result.status)) {
                    setError(result.error ?? "Transcription did not complete. You can type instead.");
                    setTranscriptionId(null);
                    setTranscribing(false);
                }
            }).catch((value: unknown) => { if (!controller.signal.aborted) {
                setError(value instanceof Error ? value.message : "Transcription status is unavailable.");
                setTranscriptionId(null);
                setTranscribing(false);
            } });
        }, 2500);
        return () => { window.clearInterval(timer); controller.abort(); };
    }, [api, transcriptionId, threadUnavailable]);
    useEffect(() => {
        if (!api || !thread || (!activeThreadStatuses.includes(thread.status) && !thread.pending_actions?.some((action) => action.status === "executing")))
            return;
        const controller = new AbortController();
        const timer = window.setInterval(() => {
            void altoRequest<AssistantThread>(api, `/assistant/threads/${thread.id}`, { signal: controller.signal })
                .then((value) => { if (!controller.signal.aborted)
                setThread(value); })
                .catch((value: unknown) => { if (!controller.signal.aborted) {
                rejectThread(value, thread.id);
                setError(value instanceof Error ? value.message : "Unable to refresh the conversation."); } });
        }, 2500);
        return () => { window.clearInterval(timer); controller.abort(); };
    }, [api, thread, rejectThread, setThread]);
    useEffect(() => {
        if (!guidedPrompt) return;
        if (threadUnavailable || (guidedPrompt.threadId && savedThread.error)) {
            guidedPrompt.onStatus({ state: "failed", error: "The saved guided conversation is unavailable. Retry to start a fresh question." });
            return;
        }
        if (error) {
            guidedPrompt.onStatus({ state: "failed", error });
            return;
        }
        if (!thread) {
            guidedPrompt.onStatus({ state: "waiting" });
            return;
        }
        const hasAssistantAnswer = thread.messages.some((message) => message.role === "assistant" && message.content.trim().length > 0);
        if (thread.status === "completed") {
            guidedPrompt.onStatus(hasAssistantAnswer
                ? { state: "completed" }
                : { state: "failed", error: "ALTO completed without an answer. Retry the guided question." });
        }
        else if (failedThreadStatuses.includes(thread.status)) {
            guidedPrompt.onStatus({ state: "failed", error: thread.error ?? "ALTO could not answer the guided question. Please retry." });
        }
        else guidedPrompt.onStatus({ state: "waiting" });
    }, [error, guidedPrompt, savedThread.error, thread, threadUnavailable]);
    useEffect(() => {
        if (!api || !guidedPrompt || guidedSubmission.current === guidedPrompt.messageCommandKey)
            return;
        const existingThreadId = guidedPrompt.threadId;
        if (existingThreadId && (
            !thread
            || thread.messages.length > 0
            || thread.status === "completed"
            || failedThreadStatuses.includes(thread.status)
        )) return;
        guidedSubmission.current = guidedPrompt.messageCommandKey;
        const submit = async () => {
            if (!existingThreadId) setText("");
            if (!existingThreadId && guidedPrompt.reduceMotion) setText(guidedPrompt.prompt);
            else if (!existingThreadId) {
                for (let index = 1; index <= guidedPrompt.prompt.length; index += 1) {
                    await new Promise<void>((resolve) => window.setTimeout(resolve, 28));
                    if (!alive.current) return;
                    setText(guidedPrompt.prompt.slice(0, index));
                }
            }
            if (!alive.current) return;
            setBusy(true);
            let createdId: string | undefined;
            try {
                const created = existingThreadId && thread ? thread : await altoRequest<AssistantThread>(api, "/assistant/threads", {
                        method: "POST",
                        body: { context: binding },
                        idempotencyKey: guidedPrompt.threadCommandKey,
                    });
                createdId = created.id;
                if (!existingThreadId) guidedPrompt.onThreadCreated(created.id);
                const result = await altoRequest<AssistantThread>(api, `/assistant/threads/${created.id}/messages`, {
                    method: "POST",
                    body: { content: guidedPrompt.prompt, context: binding },
                    idempotencyKey: guidedPrompt.messageCommandKey,
                });
                if (alive.current && !accessDenied.current) {
                    setThread(result);
                    setText("");
                }
            }
            catch (value) {
                if (alive.current) {
                    rejectThread(value, createdId);
                    const detail = value instanceof Error ? value.message : "ALTO could not start the guided question.";
                    setError(detail);
                    guidedPrompt.onStatus({ state: "failed", error: detail });
                }
            }
            finally {
                if (alive.current) setBusy(false);
            }
        };
        void submit();
    }, [api, binding, guidedPrompt, rejectThread, setThread, thread]);
    async function decideAction(action: AssistantPendingAction, decision: "confirm" | "dismiss") {
        if (!api || !thread || actionBusy || action.status !== "pending_confirmation")
            return;
        setActionBusy(action.id);
        setError(null);
        try {
            const result = await altoRequest<AssistantThread>(api, `/assistant/threads/${encodeURIComponent(thread.id)}/actions/${encodeURIComponent(action.id)}/decision`, {
                method: "POST",
                body: { decision, expected_version: action.confirmation.expected_version },
            });
            if (alive.current && !accessDenied.current) {
                setThread(result);
                onThreadChange?.(result.id);
            }
        }
        catch (value) {
            if (alive.current) {
                rejectThread(value, thread.id);
                setError(value instanceof Error ? value.message : "The proposed action could not be updated.");
            }
        }
        finally {
            if (alive.current)
                setActionBusy(null);
        }
    }
    async function send() {
        if (!api || !text.trim() || busy || recording || transcribing || restoringThread)
            return;
        if (composerMode === "plan" && onPlanRequest) {
            onPlanRequest(text.trim());
            setText("");
            return;
        }
        setBusy(true);
        setError(null);
        setShowConversation(true);
        let requestedThreadId = thread?.id;
        try {
            const activeThread = thread ?? await altoRequest<AssistantThread>(api, "/assistant/threads", { method: "POST", body: { context: binding } });
            if (!alive.current || accessDenied.current) return;
            requestedThreadId = activeThread.id;
            setThread(activeThread);
            const result = await altoRequest<AssistantThread>(api, `/assistant/threads/${activeThread.id}/messages`, { method: "POST", body: { content: text.trim(), context: binding } });
            if (alive.current && !accessDenied.current) {
                setThread(result);
                setText("");
                onThreadChange?.(result.id);
            }
        }
        catch (value) {
            if (alive.current) {
                rejectThread(value, requestedThreadId);
                setError(value instanceof Error ? value.message : "Your message could not be sent.");
            }
        }
        finally {
            if (alive.current)
                setBusy(false);
        }
    }
    async function transcribe(blob: Blob) {
        if (!api || !alive.current || accessDenied.current || restoringThread)
            return;
        if (blob.size === 0 || blob.size > MAX_AUDIO_BYTES) {
            setError("Recording is empty or exceeds the 8 MiB limit. Please record a shorter message.");
            return;
        }
        setTranscribing(true);
        try {
            const activeThread = thread ?? await altoRequest<AssistantThread>(api, "/assistant/threads", { method: "POST", body: { context: binding } });
            if (!alive.current || accessDenied.current) return;
            setThread(activeThread);
            const file = await uploadPrivateFile(api, blob, blob.type.startsWith("audio/mp4") ? "voice.mp4" : "voice.webm", "voice_audio", { threadId: activeThread.id });
            let clean = false;
            for (let attempt = 0; attempt < 40 && alive.current && !accessDenied.current; attempt++) {
                const status = await altoRequest<{ state: string; scan_state: string }>(api, `/files/${file.file_id}`);
                if (status.state === "available" && status.scan_state === "clean") { clean = true; break; }
                if (["rejected", "infected", "failed", "deleted"].includes(status.state) || ["infected", "failed", "rejected"].includes(status.scan_state)) throw new Error("Recording did not pass private-file validation.");
                await new Promise<void>((resolve) => window.setTimeout(resolve, 1500));
            }
            if (!alive.current || accessDenied.current) return;
            if (!clean) throw new Error("Recording is still waiting for private-file validation. Nothing has been sent; try again once the scanner is available.");
            const result = await altoRequest<{
                id: string;
                status: string;
                transcript?: string;
                error?: string;
            }>(api, "/voice/transcriptions", { method: "POST", body: { file_id: file.file_id, thread_id: activeThread.id } });
            if (alive.current && !accessDenied.current) {
                if (result.status === "completed" || result.status === "succeeded") {
                    setText((current) => `${current}${current ? " " : ""}${result.transcript ?? ""}`);
                    setTranscribing(false);
                }
                else
                    setTranscriptionId(result.id);
            }
        }
        catch (value) {
            if (alive.current) {
                rejectThread(value, thread?.id);
                setError(value instanceof Error ? value.message : "Transcription failed. You can type your message instead.");
                setTranscribing(false);
            }
        }
    }
    async function startRecording() {
        if (!api || !voiceEnabled || recording || transcribing || restoringThread)
            return;
        setError(null);
        try {
            if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined")
                throw new Error("Audio capture is unavailable on this device. You can type instead.");
            const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type));
            if (!mimeType) throw new Error("This device does not support a permitted recording format. You can type instead.");
            stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
            if (!alive.current || accessDenied.current) {
                releaseAudio();
                return;
            }
            audioContext.current = new AudioContext();
            const analyser = audioContext.current.createAnalyser();
            analyser.fftSize = 64;
            audioContext.current.createMediaStreamSource(stream.current).connect(analyser);
            const samples = new Uint8Array(analyser.frequencyBinCount);
            const animate = () => { analyser.getByteFrequencyData(samples); setLevels(Array.from(samples.slice(0, 24), (sample) => Math.max(2, sample / 7))); frame.current = window.requestAnimationFrame(animate); };
            animate();
            const instance = new MediaRecorder(stream.current, { mimeType });
            recorder.current = instance;
            const chunks: Blob[] = [];
            let bytes = 0;
            instance.ondataavailable = (event) => { if (event.data.size) {
                chunks.push(event.data);
                bytes += event.data.size;
                if (bytes > MAX_AUDIO_BYTES && instance.state === "recording")
                    instance.stop();
            } };
            instance.onstop = () => { releaseAudio(); if (alive.current) {
                setRecording(false);
                void transcribe(new Blob(chunks, { type: instance.mimeType }));
            } };
            instance.start(500);
            setRecording(true);
            stopTimer.current = window.setTimeout(() => { if (instance.state === "recording")
                instance.stop(); }, 60000);
        }
        catch (value) {
            releaseAudio();
            setError(value instanceof Error ? value.message : "Microphone permission was denied.");
        }
    }
    return <section className={`alto-assistant ${overlay ? "overlay" : ""}`} aria-label="ALTO assistant" data-onboarding-target={guidedPrompt ? "assistant" : undefined}>
    {(showConversation || initialThreadId) && <div className="alto-conversation">
      <header>
<span>{binding.label ?? "ALTO conversation"}</span>
{!guidedPrompt && <IconButton icon="close" label="Hide conversation" onClick={() => { setShowConversation(false); if (initialThreadId) navigate("/home"); }}/>}
</header>
      <div className="alto-message-list" aria-live="polite" ref={messageList}>
        {thread?.messages.map((message) => <article key={message.id} className={`alto-message ${message.role}`}>
<span className="alto-message-author">{message.role === "assistant" ? <AltoLogo compact/> : "You"}</span>
<div>
<div className="alto-message-bubble">{message.content}</div>{message.citations.length > 0 && <div className="alto-citations">{message.citations.map((citation, index) => <button key={`${citation.target_path}:${index}`} onClick={() => navigate(safeTarget(citation.target_path))}>
<Icon name="document" size={15}/>{citation.label}</button>)}</div>}<small>{dateTime(message.created_at)}</small>
</div>
</article>)}
        {thread?.pending_actions?.map((action) => <AssistantActionCard key={action.id} action={action} busy={actionBusy === action.id} onDecision={(decision) => void decideAction(action, decision)} onRevise={() => { setText("Revise this plan to resolve every recorded violation while preserving its approved goal, deadline, and source constraints."); }}/>) }
        {thread && activeThreadStatuses.includes(thread.status) && <div className="alto-stage" role="status">
<span />{guidedPrompt ? "ALTO is answering…" : thread.stage ?? "Waiting for the worker"}{!guidedPrompt && <button onClick={() => { if (api)
            void altoRequest<AssistantThread>(api, `/assistant/threads/${thread.id}/cancel`, { method: "POST", body: { expected_status: thread.status } }).then(setThread).catch((value: unknown) => { rejectThread(value, thread.id); setError(value instanceof Error ? value.message : "Cancel failed."); }); }}>Cancel</button>
}
</div>}
        {thread?.error && <ErrorNotice error={thread.error}/>}
        {!thread && !busy && <p className="alto-muted">Ask a question about the context you can access. Changes still require your confirmation.</p>}
      </div>
    </div>}
    <ErrorNotice error={error ?? savedThread.error} retry={initialThreadId && (savedThread.error || threadUnavailable) ? () => { setError(null); savedThread.refresh(); } : undefined}/>
    {onPlanRequest && <div className="alto-segmented" aria-label="What would you like ALTO to do?">
      <button type="button" disabled={Boolean(guidedPrompt)} className={composerMode === "plan" ? "selected" : ""} aria-pressed={composerMode === "plan"} onClick={() => setComposerMode("plan")}>Plan work</button>
      <button type="button" disabled={Boolean(guidedPrompt)} className={composerMode === "ask" ? "selected" : ""} aria-pressed={composerMode === "ask"} onClick={() => setComposerMode("ask")}>Ask a question</button>
    </div>}
    {onPlanRequest && <p className="alto-caption">{composerMode === "plan" ? "Describe the outcome. Review the request." : "Ask about your work"}</p>}
    <form className={`alto-composer ${recording ? "listening" : ""}`} onSubmit={(event) => { event.preventDefault(); void send(); }}>
      <AltoLogo compact/>
      {binding.kind !== "global" && <button type="button" className="alto-context-chip" title="Remove context" onClick={() => { setExplicitContext(GLOBAL); setThread(null); }}>{binding.label ?? binding.kind}<Icon name="close" size={13}/>
</button>}
      {recording && <div className="alto-waveform" aria-label="Microphone audio level">{levels.map((level, index) => <span key={index} style={{ height: `${level}px` }}/>)}</div>}
      <input aria-label="Message ALTO" value={text} onChange={(event) => setText(event.target.value)} placeholder={!api ? "Sign in to ask ALTO" : transcribing ? "Transcribing… review before sending" : placeholder} maxLength={8000} disabled={!api || transcribing || Boolean(guidedPrompt)}/>
      {recording && <>
<span className="alto-listening-label">Listening</span>
<button type="button" className="alto-stop" aria-label="Stop recording and transcribe" onClick={() => recorder.current?.stop()}>
<span />
</button>
</>}
      <button type="button" className="alto-icon-button" aria-label="Start microphone" title={!voiceEnabled ? "Voice transcription is not available on this host. Type your message." : "Record up to 60 seconds; review the transcript before sending"} disabled={!api || !voiceEnabled || recording || transcribing || restoringThread || Boolean(guidedPrompt)} onClick={() => void startRecording()}>
<Icon name="mic"/>
</button>
      <button type="submit" className="alto-send" aria-label="Send message" disabled={!api || !text.trim() || busy || recording || transcribing || restoringThread || activeThreadStatuses.includes(thread?.status ?? "") || Boolean(guidedPrompt)}>
<Icon name="send"/>
</button>
    </form>
    {transcribing && <p className="alto-caption">Transcribing your private recording. Nothing will be sent as a message until you press Send.</p>}
    {!showConversation && thread && <button className="alto-text-button alto-open-conversation" onClick={() => setShowConversation(true)}>Open conversation</button>}
  </section>;
}

# ALTO desktop implementation notes

## Scope and ownership

This change replaces the four-surface desktop entry with a shared ALTO shell and hash routes while retaining the connected planning, approval, employee execution and company-credential code. Runtime remains React + TypeScript + Vite + Tauri. No router, graph engine, design system or image-generation dependency was added.

Every supplied image in `docs/manager` and `docs/employee` was opened individually before implementation. [Storyboard coverage](../storyboard-coverage.md) maps every image to its route, backing model, interactions and outstanding final verification.

## Frontend modules

- `apps/desktop/src/App.tsx`: existing Supabase-authorised session/host bootstrap, public deployment config and main shell lifecycle.
- `alto-shell.tsx`: expanded/collapsed role-aware navigation, hash dispatch, checked workspace bootstrap, notification popover and native overlay entry.
- `alto-api.ts`: typed permission-safe workspace/domain projections and one authenticated JSON request adapter; safe internal navigation targets.
- `alto-ui.tsx`: local SVG icon vocabulary, supplied [ALTO JPEG](../design/LOGO.jpeg), loading/error/empty states and dialog focus containment. The shared mark displays the unchanged original image through a tight viewport, without its large blank margins; it is not redrawn.
- `alto-state.ts`: formatting, hash navigation and resource/command hooks; responses are scope-tagged and old private data is hidden before effect cleanup on a principal/run/actor change.
- `alto-resource-cache.ts` and `request-deadline.ts`: bounded in-memory view retention,
  background revalidation, shared pending reads and explicit request deadlines. Cache keys
  include real account, host, company, run, actor and resource path, not bearer tokens.
- `alto-demo-setup.tsx`: explicit manager/employee role cards, reuse of owned workspaces,
  optional named teammate selection and a separate advanced simulation entry. The server
  remains the authority for available roles and actor-session creation.
- `planning-conversation.tsx`: saved-request progress, clarification answers, actionable
  stopped-stage recovery and exact-version review/approval/commitment. Plan review is the
  inbox for those same conversations, not a second request-creation flow.
- `alto-pages.tsx`: Home, projects, action/notification inbox, explicit preference consent and isolated Simulation controls.
- `alto-graph.tsx`: deterministic five-hub graph, separate goal gates, typed edges, decreasing remaining-lifecycle rings, accepted-task aggregation, pan/zoom/fit/fullscreen, keyboard nodes, equivalent table, header-aligned rule drawer and separate exact approval decisions. Proposal history fetches an exact recorded `proposal_id`; historical/D0 failures never become committed schedules. The goal uses `project.goal_label` with a readable legacy fallback.
- `alto-task.tsx`: approved task brief, timeline, disclosed file access, version-bound draft/submission, corrections, unsaved-work warning and R1/R2 explicit gate approval.
- `alto-calendar-profile.tsx`: typed weekly calendar/agenda with overlap lanes and non-meeting deadlines, manager-safe People directory/profile and self-declared edits.
- `alto-assistant.tsx`: durable threads/messages/results/citations and shared composer; native overlay uses the same authenticated service without implicit foreground context.
- `alto-storage.ts`: private Storage ticket, exact bucket-origin signed upload/download and server finalisation; no client-side “clean” marker.
- `alto-private-feedback.tsx`: owner-private feedback and manual preference draft; named-audience sharing and revocation remain separate commands.
- `alto-evidence.tsx`: exact immutable submission review, source-version excerpts and current-consent shared-preference projection.
- `alto-settings.tsx`: workspace preferences, connections/grants, owner-scoped demo credential validation/version binding, About/diagnostics.
- `alto.css`: reference-derived visual tokens and responsive shell/components. Legacy CSS remains for retained connected workflow components.

## Authentication and scope

Sign-in and account creation use Supabase Auth, not fixture users. A signed-in user lacking company membership is offered guarded fixed-demo onboarding rather than being silently granted a company role. The requested demo role is sent to `POST /v1/demo/onboarding`, which owns all authority decisions.

The API token is held by the existing authorised session controller. Company/run/actor IDs are only selectors; the server validates membership, run ownership and actor grants on every command. Public run/actor UUID selectors are persisted under a real-user/company-specific local-storage key so the native overlay can receive scope changes. A scope change remounts view state; logout clears that user's selectors. No provider key, service-account JSON, signed file URL, private profile content or thread cache is saved in local storage.

The native overlay only renders the shared composer. It does not expose the account/deployment/credential forms, scrape other windows, inspect the clipboard or infer active application context. `alto:overlay-hidden` unmounts capture and releases tracks even when the native window is hidden rather than destroyed. Esc hides the overlay. OS-level shortcut registration uses the root-owned Tauri command boundary.

## Data and mutations

All display records come from API read models. The browser contains no scenario task/project/person seed lists. Authorised server demo fixtures are visibly labelled `Synthetic company · Demo data`; live, authored-replay and authored-check modes are distinct. No elapsed interval becomes accepted work.

Every new mutating JSON request sends an idempotency key. Commands carry the relevant expected task/settings/draft/clock/submission version or immutable digest. A stale or denied response remains visible; controls do not pretend success. Exact plan approval distinguishes planning from brief audience disclosure, and commit uses the recorded full binding. Submission review requires explicit written findings and exact-version confirmation; the backend owns named reviewer authority.

Assistant messages are persisted and polled while the worker reports a non-terminal state. Citation targets are restricted to internal application paths. Removing a context chip creates global context only within the same current server-authorised scope; it never grants access.

Voice is available only when `voice.transcribe` is advertised by the host. Recording starts from a deliberate microphone click, uses real analyser data, is capped at 60 seconds/8 MiB, stops/releases devices, uploads to a private scoped ticket, awaits clean server file status and requests durable transcription. The returned transcript is editable and never submitted automatically. Unsupported devices/MIME/provider/scanner paths retain typing fallback. Recording audio is never base64-posted into an unbounded API request.

## Visual and access behavior

The source images describe content geometry, not a screenshot-as-app implementation. The rail is 246px expanded and 74px collapsed; a 43–49px main gutter, restrained warm-white panels and thin blue-gray dividers maintain the reference hierarchy. The composer remains at the lower page edge where pictured. The graph and calendar reflow around their right inspectors.

Status, team, selection and access are separate: team colors identify function; text and ring steps communicate recorded lifecycle; the selected node uses a distinct dark outline. Accepted leaves can aggregate and expand without losing task IDs or history. The list/table equivalent exposes the same graph facts and actions without depending on SVG interaction.

Self-declared skill edits cannot replace accepted experience. Manager profiles show reduced busy/free data, never private appointment titles. Preference close/dismiss is not consent; only an explicit Share command creates an audience projection. Revocation is rechecked when opening a notification or shared preference.

## Running and verification

The September 27 autonomous-planning follow-up adds a small accessible activity circle
for recorded queued/running/leased/retry-scheduled planning jobs. It stops for terminal
errors, decisions and proposals, and respects reduced-motion preferences. Read-only status
polling continues across the gap between successful stage jobs. Successful cache refreshes
are silent; failed refreshes retain a discreet stale-data notice and read-only retry.
The browser never starts a provider retry merely because a tab opens or refreshes.

Four separate fixture captures, including an active planning stage, are retained under
`apps/desktop/src/test/autonomous-planning-visual-artifacts/`. These show the supplied
JPEG, not a recreated mark. They are browser fixture evidence, not a native or Live run.

Use the repository's existing root launch commands and deployment guide; no alternative backend or second Supabase directory is introduced. Browser development is the existing `npm run dev --workspace @coordination/desktop` entry. Installed Tauri operation additionally requires the supported Rust/system toolchain and the root-owned native overlay/shortcut changes.

The user requested tests only at the end. During implementation, no tests/builds/typechecks were executed. After final verification was explicitly authorised, the desktop typecheck, zero-warning ESLint, all **38 Vitest tests in 9 files**, and production build passed. The build has a non-failing 500 kB chunk-size advisory (583.96 kB JavaScript, 162.05 kB gzip). No dependency was added for UI rendering or visual verification.

Focused regressions cover exact company/run/actor headers and gate versions, archived-run control-plane selector omission, stale/late private resource isolation, individual consent/close/keep-private/version conflicts, id-only notifications with revoked shared projections, exact failed D0/history inspection, delayed scenario bootstrap for calendars, unsupported audio MIME before microphone permission, missing host voice capability, and microphone-track release with no upload on overlay unmount. Existing authentication, provider, planning and employee execution tests also pass.

The final [storyboard manifest](../storyboard-coverage.md) links **19 browser fixture captures** and records their scope. The Edge/CDP runner and fixture module are in `apps/desktop/src/test/`; the fixture module is not referenced by production `main.tsx` and the production Vite build does not include it. All captures contain an explicit fixture watermark. All 19 captures were visually inspected; revisions corrected Home spacing, graph hub/label/drawer/conversation geometry and calendar bootstrap timing. Native installed text/voice overlays, hosted Auth, live provider/scanner/storage round trips, and multi-monitor/OS permission behavior are not proven by those captures. M15 is intentionally uncaptured rather than showing a simulated waveform.

Known deliberate limitation to verify: profile busy/free week navigation only displays the bounded availability projection returned by the server; it must not infer a free interval outside that projection. Shared source logos are typographic placeholders, not claims of live Microsoft access. Native signing/notarisation and installed multi-monitor behavior are separate release checks.

## Everyday-flow follow-up (27 September 2026)

Home distinguishes **Plan work** from read-only **Ask question**. Plans begin with an
explicit preview; saved requests and threads can be restored after navigation. The
Northstar demo exposes its approved intake boundary rather than implying every free-form
request has complete typed scenario authority. General non-demo intake remains separate.
Simulation clock/fork/reset tools are advanced controls, not prerequisites for selecting
an employee or manager role.

Session and read requests time out after 20 seconds with retry/recovery actions; commands
have a 120-second limit and an ambiguous-result warning, never automatic write retries.
Returning to a recent tab renders cached data immediately and refreshes in the background.
Refresh failure retains permitted data with a stale notice; access denial evicts it.
Account/scope changes and logout clear protected state. Cached private content stays in
memory only, with five-minute retention and an 80-inactive-entry eviction target.

Three additional watermarked browser fixtures are recorded in
`apps/desktop/src/test/planning-flow-visual-artifacts/manifest.json`: role selection,
request preview and stopped planning. They were captured at 1672 by 941 in headless Edge
and inspected for readable actions, shell/conversation geometry, overflow and JS errors.
These are fixture evidence, not live Supabase, installed Tauri or pixel-exact acceptance.
Earlier verification counts above describe the original implementation; the current
follow-up counts and runtime findings are in the implementation journal.

# ALTO — five-minute demo video production prompt

Prepared from the repository on 26 September 2026. This is a future production brief, not a claim that the connected demo or comparative product results already exist. Copy the text between **BEGIN PROMPT** and **END PROMPT** into the video-production agent when the product and recordings are ready.

The story uses the simulation's SoraWorks company and connected Hikari / SSO incident scenarios. Change A establishes the earlier Hikari deadline; Change B supplies the new work shown in the film. Internal onboarding remains background work protected by capacity and access boundaries. This keeps the five-minute story focused.

## Repository findings behind this brief

- The product coordinates human work. Gemini interprets and explains; trusted code admits constraints; Z3 schedules; independent validation checks the concrete result; authorised people approve; the backend commits and delivers recipient-safe instructions.
- The current desktop manager and employee records are labelled previews. The implementation ledger still lists candidate-to-snapshot materialisation, the connected scenario, live connectors and benchmarks as incomplete. Read it again before production.
- The simulation is a separate synthetic evaluation harness. Its primary baseline is a reproducible local greedy/cascade coordinator with permission-filtered inputs. It deliberately avoids ineligible assignments and private disclosure. It is not an LLM reading every company document.
- In the archived seed-17 tiny A → B run, Change B has **3 existing tasks changed, 8 planning attempts, 3 cascade cycles, 47 relay hops, 38 duplicate fact deliveries, 0 invalid delegations and 0 observed disclosure violations** for the baseline. The authored replay also changes **3 existing tasks**. There is no demonstrated product advantage in those numbers; real-product result cells are `NOT_RUN`.
- Submission and acceptance are distinct. Required dependent work unlocks after acceptance. Accepted contributions and familiarity can update; a button press does not automatically grant a new qualification.

Sources: [implementation status](../../docs/implementation-status.md), [product specification](../../docs/coordination_engine_master_v2.md), [build contract](../../docs/implementation_master_prompt_v2.md), [design direction](../../docs/design/ui-direction.md), [simulation overview](../README.md), [simulation decisions](../DECISIONS.md), [golden review](../evals/golden-review.md), [metric registry](../metrics/registry.v2.json), and archived run `simulation/runs/benchmark-43329a535133469887a6e9517b1d8977/`.

---

**BEGIN PROMPT**

You are the director, screen-recording editor, motion designer and narrator for a five-minute product demonstration of **ALTO**. Produce the video and editable production package from the supplied working product, authorised synthetic recordings and measured run artifacts.

The product name is **ALTO**. Use that exact spelling in narration, captions, editorial labels and new export filenames. Older specifications, filenames and archived recordings may use a former name; preserve their provenance. Capture the ALTO-branded product when available; identify any editorial branding overlay as such in the production report.

Create a clear, credible story: a new organisational change arrives during a Microsoft Teams call; a manager requests a revised plan; the system retrieves relevant permitted context, turns supported facts into formal constraints, finds and independently checks a schedule, obtains approval, and delivers understandable work to employees. Follow one employee through execution, submission, review and dependent-work release.

Stage the entire video on one person's desktop, with ALTO already open and remaining open throughout. Microsoft Teams call and conversation windows pop up or come to the foreground when needed, then minimise or move aside to reveal the app. Begin with the naive coordinator and ALTO side by side as windows on that desktop. Later show manager and employee perspectives within the same desktop composition. Make changed work visually obvious and show the actual measured differences between approaches. End by showing this product run's task completion time, end-to-end coordination time and changes to existing work one at a time, each beside the relevant task, plan or graph.

Deliver exactly **5:00**, 1920 × 1080, 16:9, 30 fps, with English narration and accurate captions. Use a calm, confident delivery. The starting script has approximately 470 spoken words including dialogue. Speak naturally at about 125–140 words per minute during voiced passages, leaving pauses to inspect the interface. Prefer clear screen recordings, readable overlays and restrained graph animation. Do not generate software screenshots with illegible or invented text.

### 1. Establish the production inputs

Read `simulation/demo/AGENTS.md`, the current `docs/implementation-status.md`, product specification, implementation contract, `docs/design/ui-direction.md`, and the supplied simulation run manifest, metric registry and adapter evidence. These inline source paths are relative to the repository root. Keep every video-related prompt, script, storyboard, asset, editing project, render and production-evidence file under `simulation/demo/`; all output filenames below resolve within that folder. The founder authorises relevant simulation sources to be inspected read-only for video work. Do not run the simulation, change files elsewhere in it, modify product behaviour, deploy anything or publish the film as part of video production.

Use these supplied assets, locating them in the handoff if their paths differ:

| Input | Required contents |
|---|---|
| Product recording | Actual manager intake, evidence, plan review, approval, commit, employee task, submission and reviewer acceptance screens; build/version identified |
| Desktop recording/composition | One consistent desktop, OS chrome, taskbar or dock, pointer and window layout; ALTO stays open beneath foreground windows for the full five minutes |
| Matched comparison run | Baseline and real-product A → B runs; input mapping, permissions, policies, exact diffs, events, neutral validation and metrics |
| Capture permissions | Synthetic tenant, permitted viewer accounts, approved source inputs and any approved capture actions |
| Scenario cast | Stable task/person IDs, display names, roles, actual access and actual reviewer assignments |
| Visual assets | Current product identity, approved typography, real UI recordings and any supplied call footage |
| Microsoft Teams call reference | [microsoft-team-calls.png](references/microsoft-team-calls.png): the required Teams meeting-window reference |
| Microsoft Teams conversation reference | [microsoft-teams-chats.png](references/microsoft-teams-chats.png): the required Teams channel/Posts conversation reference |
| Provenance | Run ID, fixture version/preset/seed, code/build versions, evidence class and connector modes |

Inspect both images in `simulation/demo/references/` before composing Teams scenes. The call and source conversations must visibly take place in Microsoft Teams, using those supplied interfaces. A Teams logo on a generic video-call grid, custom chat panel or ALTO card does not satisfy this requirement. Preserve the reference image files unchanged; create any production derivatives under this demo folder.

Use existing supplied recordings by default. If an authorised working synthetic environment is supplied for recording, operate only its supported interfaces within the provided capture scope. Never reset a tenant or send real Teams messages merely to create footage.

If essential recordings or measurements are absent, create the complete storyboard, script, shot list and a visibly labelled **CONCEPT ANIMATIC**. Identify the exact missing inputs. Do not turn an authored replay, disabled control or unavailable integration into a fabricated live demonstration. Use `Not measured` for absent results. Do not leave numeric placeholders in an exported final film.

### 2. Fix the story and preserve its permissions

Company: **SoraWorks**, a fictional company using Microsoft workplace tools. Timezone: **Asia/Tokyo**, displayed as JST. Use the supplied fixture dates; the current reference fixture begins Monday, 28 September 2026 at 09:00 JST.

Opening context: Change A has already moved the **Hikari reporting demonstration from Friday to Wednesday, 15:00 JST**. Preserve the original Friday commitment in history. The Hikari chain is:

`Reporting API → Reporting dashboard → QA validation → Security review → Customer demo`

New event: at the reference fixture's Monday 10:00 JST observation time, an authorised incident commander declares a **Critical SSO incident**. New work is:

`Triage → Diagnosis/hotfix → Security review → Smoke test → Deploy/verify`

Both chains use shared QA and Security capacity. Other commitments, including protected private capacity, remain in the model. An unavailable interval can be shown without disclosing its underlying project or reason. Do not invent a connection between an opaque reservation and a named HR activity unless the supplied fixture establishes it and the viewer may see it.

Use the actual captured people and authority relationships. Current reference IDs include Security specialist `e0006`, QA specialist `e0007`, SRE specialist `e0009`, SSO specialist `e0010`, and the separately authorised `incident-commander`. Resolve display names from the run instead of substituting identities into captured records.

For the employee close-up, prefer the owner of **Diagnosis/hotfix**, provided the production fixture has an explicit review gate for that task. The manager may accept the submission only if that person is its authorised reviewer. Otherwise show the actual reviewer accepting, with the manager receiving the status update. Do not silently change a self-certifiable task into a manager-reviewed task: request an already prepared, versioned capture scenario if needed. A changed review policy requires capacity to be reserved and a fresh matched comparison; historical benchmark numbers cannot be reused.

Run A before B for each approach. B must enter each approach's own actual A-result state. Use the same exogenous change, available facts, permissions, estimates, priority policy, deadline freedoms and observation time. Show any relevant inherited A-state differences; never reset one side to a more favourable schedule.

### 3. Visual and editorial direction

**One continuous desktop is the required visual setting.** Show the desktop screen directly, as if watching someone use their computer. Prefer the Windows desktop appearance in the supplied Teams conversation reference; if the supplied product recordings require another OS, use that OS consistently. Do not mix Windows and macOS chrome in the same desktop. Continuity may be assembled from recorded segments, with work time visibly compressed where specified; it need not be an unedited take.

Desktop staging:

- Start and end on the same desktop with ALTO open. Keep a consistent wallpaper, taskbar/dock, window chrome, resolution and pointer style. Retain the taskbar/dock or a desktop margin throughout so the setting remains apparent.
- ALTO is the persistent main window. In focused scenes it occupies roughly 90–95% of the available desktop. Other windows overlap it while leaving a recognisable portion of the app visible; no Teams scene replaces the desktop with a detached full-screen graphic.
- The Teams meeting opens as a foreground call window, roughly 70–80% of the desktop width, large enough to read its controls and see participants. At the end of the call, minimise or close the meeting window and bring the Teams conversation window forward. Keep ALTO open behind both.
- Teams conversations appear in the referenced Teams application window, typically on the right with enough width to read the selected thread. Open, focus, scroll and minimise that window with visible, plausible pointer actions. Native pop-out behaviour must follow the actual captured client; ordinary window focus is sufficient.
- For the initial method comparison, tile the labelled baseline benchmark/replay viewer on the left and ALTO on the right. The baseline viewer is a separate demonstration window, not a feature of the manager's product account. Resize or minimise it when attention returns to the product.
- For the later manager/employee comparison, keep the manager app open and place an explicitly labelled employee-view recording beside it in a playback window. Use a second live session only if the product actually supports that capture setup. Do not imply that the manager can switch identity or browse private employee screens. Hide playback controls when appropriate while retaining the **Employee view · recorded session** label and visible window boundary.
- Preserve window positions between beats. Move or resize a window only to serve a clear action. Use one main desktop pointer; any cursor in employee footage stays inside that labelled recording. Keep the displayed clock consistent with the scenario and any announced time compression.
- Keep graph highlights, equations, metric cards and narration captions as restrained overlays attached to the relevant on-desktop window. Label explanatory overlays where needed; they are not invented product features. Do not cut to full-screen slides, isolated UI mockups, a physical monitor shot or a separate cinematic scene. Gentle magnification is allowed only while enough desktop and window context remains visible.
- Feature one metric at a time throughout the edit. Use one short label, a readable value with its unit and a brief definition. Clear the previous metric before revealing the next; do not accumulate cards, supporting counters or a final all-metrics dashboard. Where useful, show baseline and product values for that same metric together. Keep detailed metric tables in the production evidence package.

For ALTO and editorial framing, match the current product: warm ivory surfaces, near-black text, desaturated teal actions, muted moss accepted states and restrained rust conflict/change accents. Use hairline dividers and clear typography. Microsoft Teams retains the distinct interface and colours in the supplied references, including its purple accents; do not recolour Teams to match ALTO. Avoid neon, glowing AI brains, decorative code rain and excessive floating cards.

During the comparison, label the left pane **Naive coordinator · greedy/cascade simulation** and the right pane **ALTO · [actual evidence mode]**. Name the mode accurately: recorded product run, synthetic product run, or concept animation. Do not call the baseline a competitor or measured human workplace.

Show a small readable **Synthetic company** label. Label Teams and other connectors **Simulated source** unless actual connector evidence exists. A recorded Teams call does not prove automatic Teams ingestion or native meeting-summary generation. Label a staged call **Dramatised call**.

Microsoft Teams interface requirements:

- **Call window:** follow `references/microsoft-team-calls.png`: dark meeting chrome, meeting title and elapsed-time area, top call controls, a large active-speaker tile, adjacent stacked video tiles and the narrow participant area. Preserve the recognisable camera, microphone, share and red leave-call controls in their reference positions. Use the three story participants in the appropriate tiles; optional self-view or additional participants must not duplicate the cast accidentally. Show recording status only when appropriate to the footage or explicitly staged scene.
- **Conversations:** follow `references/microsoft-teams-chats.png`: light Teams shell, top search bar, left app rail, team/channel list, channel header, selected **Posts** tab, and threaded posts with author/avatar, timestamp, replies and reaction controls. This reference is a channel conversation, not a private direct-message screen. Use that Teams channel layout for the supplied chat excerpts and call it a **Teams channel conversation** in shot notes. If a direct-message scene is needed, use a supplied or authorised captured Teams Chat view; do not invent its exact layout from the Posts screenshot.
- Use the supplied references as the visual authority for these scenes rather than mixing Teams interface versions. Prefer authorised real Teams footage; any reconstruction must closely reproduce the referenced software UI with crisp text and synthetic scenario content.
- Replace reference-example meeting titles, organisations, names, avatars and conversation text with the scenario's approved fictional cast and content. Do not imply the people shown in the reference participated in SoraWorks' incident.
- Omit capture/presentation artifacts from production derivatives: the call image's oversized decorative emoji and image-search overlay, and the conversation image's browser fullscreen notice, black video-player bars and playback controls. Keep Teams' own application and meeting controls.
- Establish the full Teams window within the desktop before gently magnifying a speaker or message. Keep Teams chrome, the desktop boundary and part of ALTO visible. Use the same Teams styling wherever either comparison lane shows Teams conversation content; stage only messages supported by that lane's evidence. Represent abstract baseline relay counts as editorial trace graphics unless an actual Teams-message mapping exists.
- Make the transition into ALTO explicit: select or open a Teams source, highlight the relevant excerpt, then minimise or move the Teams window aside and focus that source's linked evidence entry in the still-open product. The source conversation stays in Teams; the manager's instruction to ALTO stays in the product's own composer.

For graph comparison:

- Use stable task IDs, the same lane order and time scale, and a fixed camera. Use horizontal placement for time only when the view is a timeline; label dependencies separately.
- Preserve node identity and position unless recorded owner, timing or dependency facts actually change. Disable force-layout reshuffling that would exaggerate disruption.
- Dim unchanged work to approximately 30–40% emphasis. Highlight a changed node and its explicit before → after fields. Use outlines for new nodes and lock labels for protected work.
- Distinguish **New task**, **Time changed**, **Owner changed**, **Deadline changed**, **Unchanged**, and **Protected** with words or patterns as well as colour.
- Animate baseline proposal attempts from its trace, then show its terminal diff. On the product side animate only observed proposal changes. Keep **Planning attempts** separate from **Existing tasks changed**.
- Use separate lane views for private user screens and the judge comparison. Never put the complete-company inspector behind an employee label.
- Blur surrounding permitted UI to direct attention. Do not use blur as the security boundary: restricted facts must be absent from the captured viewer projection.

Use window resizing and gentle magnification so essential text remains readable at 1080p while retaining the desktop setting. Aim for 28 px or larger for explanatory overlays and captions. Leave at least 5% safe margins; keep captions clear of the taskbar/dock, buttons and metric labels. Let important evidence remain readable for at least three seconds. Keep background music low beneath dialogue and narration.

The next section is the exact 300-second edit. Quoted narration is the starting script; adapt claims to actual evidence without changing the product's trust boundaries or total duration.

### 4. Timecoded storyboard and script

#### 00:00–00:15 · Existing commitments, one shared problem

Open directly on the manager's desktop. ALTO is already open on the right, with the separate labelled baseline benchmark viewer on the left. Their graphs show each approach's schedule after Change A; the desktop/taskbar remains visible around the tiled windows. Establish the Hikari chain and shared QA/Security specialists. Briefly highlight the existing commitment: **Hikari demo · Wednesday 15:00 JST**. Keep started work visibly locked.

Overlay: **A new priority. The same people. Existing promises.**

Narration: “SoraWorks has already brought a customer demo forward to Wednesday. QA and Security are shared across projects. Then another urgent request arrives. How do you respond without losing control of the work already promised?”

#### 00:15–00:40 · The change emerges in a Teams call

On that same desktop, use a visible pointer action to join or bring forward the Microsoft Teams meeting. Its foreground window follows `references/microsoft-team-calls.png`, with three fictional participants: a delivery manager, a customer or operational stakeholder, and the authorised incident commander. Show the full dark meeting window and recognisable toolbar, then gently emphasise the active speaker while retaining the controls and other participant tiles. Use a scenario title such as **SoraWorks · SSO incident response**. ALTO remains visibly open behind the call window, with its graphs partly occluded; the surrounding desktop never disappears.

Use this concise dialogue, aligned with the supplied incident facts:

Stakeholder: “Single sign-on is failing. We need the service restored, with Security and QA checks before release.”

Incident commander: “I'm declaring this Critical under our incident policy.”

Manager: “Prepare the recovery plan. Keep our protected work and other commitments visible. Bring me any changes that need approval.”

End on the manager receiving the change. Do not let the call imply that the customer can grant internal scheduling authority.

#### 00:40–00:55 · Summary notes become a source-linked request

Minimise or close the call window, then bring the related authorised Teams channel conversation to the foreground on the same desktop, using the light channel/Posts interface in `references/microsoft-teams-chats.png`. Establish the left Teams navigation and selected channel, then focus on the source post. Keep ALTO visible behind or beside the Teams window. Show the meeting notes beside the relevant excerpt in the actual supported notes/import surface, or in an explicitly editorial overlay anchored to that window; do not invent a native Teams summary pane. Use **Draft meeting summary** until the responsible person confirms the decision. Show a source reference and version; distinguish the incident commander's authorised declaration from the generated summary.

Readable note bullets:

- Critical SSO incident, confirmed by the incident commander.
- Triage, hotfix, Security review, smoke test, deploy/verify.
- Protect started work; no implied overtime or deadline extensions.
- Hikari deadline remains Wednesday 15:00 JST.

Narration: “The notes capture the change and link back to its source. The incident declaration establishes priority; the summary alone does not create authority.”

If the notes were externally supplied or manually imported, show that route. Do not imply an unimplemented auto-summary feature.

#### 00:55–01:15 · Manager asks ALTO to plan

Move the Teams conversation window aside or minimise it and focus the still-open ALTO window. Keep the baseline comparison window visible on the left. On the right, show the manager entering this text, paced for readability:

“Plan the Critical SSO recovery from the approved incident notes. Include Security review and QA before deployment. Account for the Hikari demo due Wednesday at 15:00 JST. Preserve started work and private commitments. Propose the required changes for approval; do not extend deadlines or add overtime.”

Show source attachments and the separate employee-shareable brief field. Submit the request. On the left, show the same authorised change entering the baseline's recorded workflow.

Narration: “The manager describes the outcome. Both approaches receive equivalent authorised facts and scheduling freedoms. We compare how they handle the change, including the coordination that follows.”

#### 01:15–01:50 · Relevant context, visible actions and employee facts

Resize ALTO to about two-thirds of the usable desktop temporarily, keeping the baseline window alongside it and the desktop frame visible. Show a factual **Actions and evidence** panel, with one row appearing per actual logged operation:

1. Read the authorised incident note and relevant Teams excerpt.
2. Check current Hikari commitments and dependencies.
3. Follow shared QA and Security resource links.
4. Load essential qualifications, input permissions and working windows.
5. Include current reservations and permitted familiarity evidence.

Each row has its source/version and a concise purpose, such as **Check the shared reviewer's availability**. This is an evidence-linked explanation of recorded actions, not a transcript of hidden model thoughts.

During the first retrieval step, bring the Teams conversation window forward for approximately five seconds. Open the relevant source thread, highlight the approved incident declaration and checklist requirement, and retain the author and timestamp. Then minimise or move Teams aside and focus ALTO's linked evidence row for that same source/version. Keep the desktop and part of the product visible throughout. Any synthetic message copy must be grounded in the supplied incident records; do not invent employee replies, approvals or new constraints to fill the thread. This window interaction fits inside the existing 01:15–01:50 scene.

Open one employee profile briefly: confirmed capability, review authority, working hours, current reservations, relevant accepted contribution. Show a private reservation only as **Unavailable · protected commitment**. Do not show a suitability score or employee ranking.

On the baseline side, animate its real considered scope and relay messages. Do not invent a whole-company document crawl; the existing harness imports the full structured company for both methods, with considered scope measured separately.

Narration: “ALTO follows the affected tasks and shared resources, retrieving permitted notes and current commitments. It checks essential skills, review authority, availability and relevant experience. A private commitment contributes an unavailable interval, without exposing its reason. Each visible action links to evidence, so the manager can inspect what informed the proposal.”

#### 01:50–02:15 · Facts become typed constraints, then mathematics

Show a clean editorial overlay anchored over the evidence area in the ALTO window, with its title bar and the surrounding desktop still visible:

**Sources → Candidate task contracts → Validated constraints → Frozen snapshot → Compiled Z3 model**

Give Gemini the interpretation label. Give trusted application code the validation and compilation labels. Use a 15-minute slot example tied to the actual snapshot; do not imply that Gemini writes solver code.

Show three translations one at a time:

| Human-readable rule | Mathematical illustration |
|---|---|
| One eligible owner per task | `Σ eligible e: y(task,e) = 1` |
| No double-booked active effort | `Σ tasks: x(task,e,slot) + fixed_busy(e,slot) ≤ 1` |
| Review before dependent work | `start(next) ≥ finish(review)` |

Add small plain-language chips: **Approved effort**, **Working windows**, **Required access**, **Protected work**. Mark formulas **Model illustration** unless they are directly exported. In the capacity illustration, fixed busy time excludes reservations already counted by task occupancy.

Narration: “Gemini proposes structured task contracts. Trusted code checks their sources, meaning and authority, freezes a planning snapshot, and compiles supported constraints for Z3. One eligible owner. No double-booked effort. Required reviews before dependent work. Overlapping task windows remain possible.”

#### 02:15–02:40 · Solve, independently check, return a proposal

Show actual stage states in sequence:

**Try insertion with existing work pinned → Authorised repair if needed → Solver result → Independent schedule check**

If pinned insertion succeeds, show that outcome and skip repair. If it fails, name only that scope: **Insertion cannot fit with these commitments fixed**. Show broader repair only when observed and authorised. Do not script an `unsat` result to manufacture drama.

Present a readable returned plan table with owner, effort segments, review and deadlines. Pass it into the product's proposal/evidence view, where a viewer-safe explanation appears. Keep **Awaiting approval** visible. Display measured solve time only if the run exposes it; animation duration is not runtime.

Narration: “The planner first tests whether the work fits without moving existing commitments. If it needs more freedom, it uses only authorised changes. A separate validator checks the returned schedule. A feasible result is still a proposal: approval and commitment come next.”

#### 02:40–03:10 · Graph repair and measured comparison

Retile the baseline viewer and ALTO as equal side-by-side windows on the same desktop. Play each recorded sequence with the same task lanes and stable coordinates. On the baseline side show actual local collisions and downstream adjustments. On the product side show its recorded diff. Dim unchanged work; highlight only genuinely changed task fields. Keep the five newly introduced incident tasks visually distinct from moved pre-existing work. Show one comparison metric at a time in an editorial overlay aligned to the windows; keep the taskbar/dock visible.

Use three successive ten-second beats, clearing each metric before the next:

1. **02:40–02:50 · Existing tasks changed:** highlight the corresponding graph nodes and show the baseline and product counts for this one measure.
2. **02:50–03:00 · Planning attempts / plan versions:** show the relevant recorded attempt history and paired values only where definitions are comparable.
3. **03:00–03:10 · Repeated fact deliveries:** show the recorded relay trace and paired values only where both traces measure them.

If planning or communication observations are missing or incomparable, substitute **Owner changes** or **Total start-time displacement** for that beat when paired measurements exist; otherwise show **Not measured**. Use two clearly labelled values for the same metric, not several metric rows. Leave additional percentage/difference calculations in the evidence package unless one is essential to the narration and replaces other numeric clutter.

Keep detailed validity, disclosure and deadline statistics in the evidence package. Their relevant observed check states belong in the earlier evidence/validation scene; do not add a multi-counter validation strip beneath these comparison beats.

Default narration: “Watch the recorded changes, not just the animation. We count existing commitments moved, planning attempts and repeated information separately. Both outcomes face the same independent checks. These figures describe this synthetic run; they are not a general productivity claim.”

If matched product evidence supports an improvement, replace the middle sentences with: “In this run, existing tasks changed fell from [baseline count] to [product count]. [Second supported comparison in plain language].” Speak only populated, verified values. If counts tie, say so and focus on the trace and controlled handoff. Never exaggerate graph movement to force a visual win.

#### 03:10–03:30 · Authorise the exact plan and employee brief

Minimise the baseline viewer and enlarge ALTO within the desktop, keeping its window border and the taskbar/dock visible. Focus the product's plan review. Show the exact before/after diff, protected commitments, current proposal version and required approvals. Let the authorised manager inspect and approve. Show any additional affected authority if required.

Show employee-brief content and audience approval separately. Reuse an existing valid approval if the content and audience did not change. Then show the observed transition through current-state recheck, internal commitment and persisted recipient updates. A failed or pending external sync retains that label.

Narration: “The manager approves the exact change set. Employee communication has its own approved content and audience. After the current-state check and internal commit, the system delivers the appropriate update to each affected person.”

#### 03:30–03:55 · Two perspectives inside ALTO

Tile the still-open manager app on the left and a window containing the employee's recorded session on the right. Label them **Manager** and **Employee view · recorded session**. Both show actual authorised product views of the same committed work. Keep the same desktop, taskbar/dock and window style; this is a presentation of two captures, not an in-product role switch or a second desktop replacing the first. If a supported second live session is used, label its actual mode instead.

Manager: click the focal incident task, see owner, timing, dependency, acceptance requirements and current status; open one permitted source-linked reason.

Employee: receive the committed task update, open the brief, and acknowledge it. Show the actual role-safe content. Use this copy structure, adapting details to the recorded task:

- **Purpose:** Restore SSO using the approved incident checklist.
- **Deliverable:** Diagnosis/hotfix evidence and the required checklist.
- **Inputs:** Only the incident materials this employee may access.
- **Timing:** Actual approved work window, expected active effort and deadline.
- **Next gate:** Named reviewer and required acceptance before successor work.
- **Why assigned:** Confirmed relevant capability and feasible capacity; mention familiarity only when supported.

Keep **Flag missing input / estimate / availability** visible. The employee never sees the other team's private messages, raw solver snapshot or undisclosed rationale.

Narration: “The manager sees ownership, dependencies and progress. The employee gets a clear deliverable, timing, reviewer and permitted context, plus a way to flag a problem. They share the same committed plan, with different views of the information each is allowed to see.”

#### 03:55–04:05 · Human work in progress

Bring the employee's work recording forward as a centered window on the same desktop. Dim and softly blur the permitted background app content, leaving ALTO's outline and the desktop/taskbar recognisable. Inside the foreground window, show the employee working on the actual synthetic deliverable: a hotfix artifact and checklist, or the supplied focal task's real output. Keep the work human-led and the recorded-session label visible.

Overlay: **Work in progress · time compressed**. If actors are scripted, use **Simulated employee work** too. Advance the scenario clock consistently; do not present edited elapsed time as measured active effort.

Narration: “The employee does the work in their usual tools. This sequence is time-compressed.”

#### 04:05–04:35 · Submit, review, accept, unlock, learn

Return to the manager and employee windows on the same desktop and show these transitions clearly in order. Keep all employee interactions inside the labelled employee session and manager/reviewer interactions in their actual authorised view:

1. The employee submits a specific artifact or permitted reference and presses the real **Submit work** button. If the UI says **Complete**, make its pending-review result unmistakable.
2. The node becomes **Submitted · awaiting review**. The manager receives a status notification; the authorised reviewer receives the review request. Dependent execution remains blocked.
3. The authorised reviewer inspects the exact submission version against acceptance criteria and presses **Accept**. Use the manager for this action only if that is the captured review policy.
4. The node becomes **Accepted**. Its immediate successor becomes **Ready** only if every required predecessor and other release condition is satisfied. Show the corresponding persisted update; do not unlock an entire chain prematurely.
5. Open a compact profile/evidence update: **Accepted contribution added**, **Recent project familiarity updated**, **Workload refreshed**. Include the source submission and reviewer. Any skill/qualification change follows its separate supported review process.

Narration: “Submission requests review; it does not automatically release dependent work. The authorised reviewer accepts this exact version. Only then can the next task become ready. Workload and accepted contribution records update, and relevant experience becomes available for future planning, without automatically granting a new qualification.”

If no actual acceptance recording is available, leave the workflow at submitted and identify acceptance as missing in the production report. Do not animate success into captured product evidence.

#### 04:35–05:00 · Finish with the product's measured results

Keep the same desktop, with ALTO open and the accepted task and updated graph visible. Minimise Teams and the employee-session playback window. Use a small **Demo run results** editorial label and reveal one result at a time beside its relevant product view. Show actual product fields when available; otherwise use a clearly identified editorial overlay. Do not invent an analytics feature or a clickable results button. Retain the desktop/taskbar and a recognisable part of the app throughout.

Each beat contains one featured product value, one short label and a brief definition. The earlier comparison already carries the baseline story; keep this closing sequence focused on the product's own measured results. Remove the previous metric before the next appears. Do not finish by bringing all the metrics back together.

- **Task completion time:** show `[TASK_ELAPSED]` in human-readable units beside the accepted focal task. Label **Started → accepted · includes review/waiting**. This is not solver runtime, active labour or the duration of the entire incident.
- **Time to coordinated plan:** show `[COORDINATION_ELAPSED]` beside the committed plan's event history. Label **Authorised request → committed and communicated**, with approval included in the measured interval. Include clarification, approval, correction and delivery time under the declared endpoint; do not substitute solver-only milliseconds.
- **Existing tasks changed:** show `[CHANGED_COUNT]` beside the graph, highlighting exactly those existing nodes. Label **Distinct existing tasks · excludes new tasks**. Count material owner, timing, deadline, protection or cancellation changes once per task; exclude lifecycle-only status changes and decorative node movement.

Leave new-task counts, plan versions, owner changes and detailed validation statistics in the supporting evidence, or in their dedicated earlier beat where applicable. Do not place them below the featured closing result as extra counters.

Pace this final scene as follows:

- **04:35–04:42:** Show only task completion time beside the accepted focal task, with its timing definition.
- **04:42–04:49:** Clear that result and show only time to coordinated plan beside the plan history.
- **04:49–04:56:** Clear the timing result and show only existing tasks changed beside the highlighted graph nodes.
- **04:56–05:00:** Hold that final graph and its single metric. Add the product name and the small closing line **Traceable changes. Human control.** Do not restore the earlier metrics.

Preferred narration, aligned to the three reveals and populated from the recorded product run: “This task reached acceptance in [TASK_ELAPSED]. The updated plan was approved, committed and communicated in [COORDINATION_ELAPSED]. [CHANGED_COUNT] existing tasks changed. ALTO: traceable changes, human control.” If the displayed clock is simulated, say **in this simulation** and label its time values **Simulated elapsed time**. Pause between results so each can be read.

Fallback narration when the required measurements are unavailable: “First, time to accepted work. Then, time to a committed and communicated plan. Finally, the number of existing tasks changed. Missing measurements stay explicit. ALTO: traceable changes, human control.” Display **Not measured**, **Awaiting acceptance** or the actual partial state during the relevant single-metric beat, rather than placeholder numbers. For a future completed-product recording, populate the preferred script with measured results.

Use a small provenance footer: **Synthetic scenario · [case/preset] · [run ID] · [clock/evidence mode]**. Show a supplied demo URL only if one exists and space permits. Keep the accepted focal task separate from incident-wide completion: this scene must not declare the whole recovery finished when only the focal task has been accepted. Do not display recorded-replay timings as product performance.

### 5. Bind every displayed metric to evidence

Create a machine-readable `metric-bindings.json` for the edit. For each displayed figure include: metric ID and definition version, fixture/run ID, scenario, method, evidence class, status, value/unit, numerator/denominator, artifact path and field, time window, and the video timecode where used. Do not change the benchmark metric definitions for a more attractive card.

The following table is a production reference, not an on-screen dashboard or a requirement to display every metric. Feature only the metric assigned to the current beat; retain the remaining definitions and results in the evidence package.

| Video label | Source and interpretation |
|---|---|
| Task completion time | Derive `accepted_at − started_at` for the focal task from observed lifecycle events and the acceptance of the exact submission. Use a consistent clock and record the task/submission IDs and endpoint references. Include elapsed blocked/review time; label simulated actor time explicitly. If acceptance or start is missing, do not infer it from planned segments. This is a video-report calculation, not the registry's scenario-wide `completion` metric. |
| Active work time, if separately shown | Use only explicitly recorded or employee-reported active effort with its provenance. Never infer it by subtracting start from acceptance. It is optional detail, not a fourth headline metric. |
| Whole-incident completion, if separately shown | `completion` or `priority_service`, using the registry's exact scenario and acceptance scope. Do not use these incident-wide measurements as the focal task's execution time. Predicted completion is a forecast, not observed acceptance. |
| Existing tasks changed | `changed_commitments.value.tasks`: distinct pre-existing tasks with a material owner, time, agreed-deadline, protection or cancellation change. Exclude newly created incident tasks. |
| New tasks added | Count distinct task IDs created by the selected change relative to that method's immutable pre-change task set, using its exported outcome. Keep this separate from `changed_commitments`; additions are not disruption of existing work. Record this video-report derivation and both source sets. |
| Owner changes | `owner_churn`: distinct existing tasks whose owner changed. This is not the same as time movement. |
| Total start-time displacement | `displacement`: absolute start shifts of matched existing blocks, in calendar minutes. Not labour saved or active effort. |
| Planning attempts / versions | `replans`: name the specific field. One solver attempt, one local task choice and one committed revision are different units; compare only compatible definitions. |
| Relay hops | `relay_hops`: traversals of the declared reporting/project graph, not a count of employees or necessarily real messages. |
| Repeated fact deliveries | `duplicate_transmissions`: repeated normalised-fact/recipient deliveries after the first. Not necessarily needless human communication. |
| Invalid delegations | `invalid_delegations`: distinct assigned tasks with at least one independent hard failure, with the total assigned-task denominator. |
| Privacy observations | `privacy`, source-access checks and captured viewer projections: report tested reads/disclosures separately. Zero observed violations is scoped to the run and available instrumentation. |
| Scope | `scope`: keep full import/read, considered, replanned, moved and notified sets distinct. A smaller considered set does not establish smaller model input or fewer source reads. |
| End-to-end coordination time | Actual authorised-change → correctly committed and appropriately communicated plan, with approval/waiting/correction time included. Use only when these timestamps exist; separate from `planning_latency` and solver milliseconds. |

For the closing **Time to coordinated plan**, bind the start to the observed authorised request and the end to the last required, evidenced commitment/communication event under one documented definition. State whether communication means persisted recipient updates, observed delivery or recipient acknowledgement, and use the same definition on both sides. Persisted notifications must not be described as read or acknowledged. If required delivery is still pending, show that partial state rather than stopping the timer at proposal generation. Distinguish measured wall-clock time from simulated actor time even when the product itself executed the workflow.

Record any video-report calculation with a stable name, definition/version, formula, clock, scope and exact input references in `metric-bindings.json`. Do not change the simulation's registry or historical runs to produce closing statistics. The closing changed-task count must match the earlier graph comparison's same scenario and final plan. Subsequent accepted/status transitions do not count as extra replans; if actual later schedule revisions occurred, state the expanded time window and reconcile the earlier figure explicitly.

For a supported reduction, compute `(baseline − product) / baseline × 100`. Show absolute values alongside it. Require a nonzero baseline, compatible definitions and matching evidence scope. A tie is 0%; an unavailable value is **Not measured**; a worse result remains visible. Never compare baseline runtime with compressed film duration or synthetic employee completion time.

Only observed product-runtime evidence may populate the **ALTO result** column. `product_replay` is explicitly authored replay and must not produce product-improvement percentages. Missing, failed, unknown, timeout and partial outcomes retain their proper status.

Current historical guardrail, to prevent accidental fabrication: in the archived tiny seed-17 Change B run, the baseline and authored replay each move three existing tasks. The baseline's recorded 8 planning attempts, 3 cascade cycles, 47 relay hops and 38 duplicate transmissions are synthetic comparator measurements; the replay does not supply a measured product planning/communication advantage. Both show zero recorded invalid delegation and disclosure failures. Re-read the selected production run; do not use these historical counts for a different fixture or reviewer policy.

Do not use the optional `portfolio` case's 12 owner changes or company-scale fixture totals as though they belong to the primary A/B comparison. A 25-person run is not an 8,000-task product benchmark.

### 6. Handle the requested failure contrast honestly

The primary naive comparator receives permission-filtered facts, chooses eligible people and does not deliberately leak information. Show actual cascading work and repeated relays when the run contains them. Do not add invalid delegation, confidential message disclosure or a document flood as invented baseline behaviour.

If supplied evidence includes a separate unconstrained-planner or adversarial failure experiment, it may appear as a short, clearly labelled **Separate failure illustration** within the existing edit budget. Identify that method and scenario, use only synthetic information, and keep its results out of the primary baseline comparison. Otherwise demonstrate privacy by showing the product's restricted projection and authority checks. Do not invent a failure clip.

Similarly, explain the system using recorded sources, selected facts, checks, decisions and actions. Never manufacture a hidden chain-of-thought transcript. Do not show Z3 deciding access rights, proving document truth, accepting work quality or authorising dispatch.

### 7. Produce and verify the package

Deliver:

- `alto-demo-5min.mp4`: final 300-second video, H.264 with clear stereo AAC audio.
- `alto-demo-5min.srt`: accurate captions matched to the final narration.
- The editable timeline/project and source assets in the tool's native format.
- A desktop continuity sheet recording the chosen OS, persistent app placement, Teams foreground/minimised states and labelled employee-session presentation.
- `script-and-shot-list.md`: final dialogue, narration, shot sources, modes and timecodes.
- `metric-bindings.json` and `claims-and-sources.md`: evidence for every numeric claim and product-state claim.
- A short production report identifying actual product footage, staged material, simulated connectors, compressed work time and any missing evidence.

Before delivery, inspect the complete rendered video and confirm: it is exactly five minutes; every scene stays on one consistent desktop with ALTO open; Teams call and conversation windows come forward and minimise through plausible actions while part of the product stays visible; no full-screen slide or detached scene breaks desktop continuity; screen text and captions are readable; the Teams call and conversations match their supplied references and retain Teams' own chrome/colours; source conversations appear in Teams and the manager's product prompt appears in ALTO; screenshot capture artifacts are absent; comparison and employee-session window labels remain clear; actual task IDs and times match the source artifacts; graph motion matches real changes; metrics appear one at a time in both the comparison and final 25 seconds, with no accumulating scorecard or supporting counters; the last frame retains only the final featured metric; timing metrics name their endpoints and clock; existing-task changes, new tasks, owner changes and plan versions remain distinct and reconcile with the earlier comparison; metric denominators and units are correct; restricted content never appears in an unauthorised POV; approval precedes commitment and dispatch; submission precedes acceptance; dependent release follows its real gates; and no simulation result is presented as measured customer productivity.

Make routine editorial decisions yourself and finish the authorised production work. Report unavailable capture or rendering capabilities plainly. Deliver files for review; do not publish or send them to others.

**END PROMPT**

# SoraWorks scenario facts

Teammate handoff · Two connected changes · All times JST (Asia/Tokyo)

The fictional company is **SoraWorks Japan**, a Japanese B2B enterprise-software and implementation-services company. Its exact fixture display name is **SoraWorks Japan (synthetic)**; the video brief shortens this to **SoraWorks**. The customer is **Hikari Manufacturing**. The facts below use the archived **tiny, seed-17** scenario (25 employees, four teams), with two new story names mapped to the original IDs on page 2. All people and events are synthetic.

## Change A — the deadline moves earlier

At **Monday, 28 September 2026, 09:00**, Hikari requests its reporting demonstration by **Wednesday, 30 September, 15:00**, instead of **Friday, 2 October, 15:00**. Hikari project manager **Emi Tanaka (e0000)** explicitly confirms the earlier deadline in the fixture; the original Friday commitment remains in history.

The required chain is **Reporting API → Reporting dashboard → QA validation → Security review → Customer demo**. The owners, in that order, are **Sora → Yui → Nao → Kaito → Akari**. Finishing the demo requires the upstream work and checks to finish first.

## Change B — a Critical incident becomes the priority

At **Monday, 28 September, 10:00**, a **Sev-1 SSO login failure affecting multiple enterprise customers** is declared **Critical** by the authorised **incident-commander**. This is new urgent incident work; the records do not give it a previous priority. Incident tasks have priority **0**, ahead of Hikari’s **1**. **Ren (e0001)** manages the incident project; the commander is a separate authority with no personal name in the fixture.

The incident chain is **Triage (Riku) → Diagnosis/hotfix (Haruto Sato, e0010) → Security review (Kaito) → Smoke test (Nao) → Deploy/verify (Riku)**. The objective is to restore service as soon as possible; the fixture’s incident task deadline is also **Wednesday, 30 September, 15:00**.

## The conflict — the same two specialists are needed

**Kaito supplies Security review and Nao supplies QA for both chains.** Ready Critical incident work gets contested capacity first, while Hikari’s Wednesday deadline still holds. Started/protected work stays locked; priority does not authorise overtime or deadline extensions. Kaito also has a protected private reservation **Tuesday, 29 September, 14:00–16:00**; its underlying reason is not identified as HR work.

The archived synthetic baseline makes the clash concrete: Nao’s Hikari QA was planned for **Monday 13:00–14:00**, but incident smoke testing takes **13:00–13:30**. Hikari QA shifts to **13:30–14:30**, Kaito’s Hikari review to **14:30–15:30**, and Akari’s demo to **15:30–16:30**. Each moves 30 minutes; the Wednesday deadline remains unchanged. This is a recorded synthetic schedule example, not a live product result.

<!-- pagebreak -->

## People and team names

For this handoff, **Emi Tanaka (e0000)** replaces **Aoi / 架空 0001**, and **Haruto Sato (e0010)** replaces **Aoi / 架空 0011**. These are story display names; archived records retain the original labels and IDs. Other names below match the fixture.

| Employee display name | ID | Scenario responsibility |
| --- | --- | --- |
| Emi Tanaka | e0000 | Hikari manager; confirms deadline change |
| Ren / 架空 0002 | e0001 | Incident project manager |
| Sora / 架空 0005 | e0004 | Hikari Reporting API |
| Yui / 架空 0006 | e0005 | Hikari Reporting dashboard |
| Kaito / 架空 0007 | e0006 | Shared Security reviewer |
| Nao / 架空 0008 | e0007 | Hikari QA; incident smoke test |
| Akari / 架空 0009 | e0008 | Hikari Customer demo |
| Riku / 架空 0010 | e0009 | Incident triage and deploy/verify (SRE) |
| Haruto Sato | e0010 | Incident Diagnosis/hotfix (SSO) |

The four exact team names in this reference fixture are:

| Team name | Team ID | Manager display name |
| --- | --- | --- |
| Engineering 1 | team-000 | Emi Tanaka (e0000) |
| Product / Planning 2 | team-001 | Ren / 架空 0002 (e0001) |
| Design 3 | team-002 | Haru / 架空 0003 (e0002) |
| Sales / Partnerships 4 | team-003 | Mio / 架空 0004 (e0003) |

**Hikari reporting demo** belongs to Engineering 1; **SSO incident response** belongs to Product / Planning 2. QA and Security are specialist roles in this fixture, not separate named teams. Shared employees have multiple team memberships. The optional HR onboarding case is outside the two-change story. Neither the customer stakeholder nor the incident commander has a supplied personal name; a named call cast would need an explicit fictional naming decision.

## Source records

[Scenario definition](../simulation_implementation_prompt.md) (§2) and [video brief](demo-video-production-prompt.md) (§2); [archived identities and commitments](../runs/benchmark-43329a535133469887a6e9517b1d8977/initial.json); [Change A event](../runs/benchmark-43329a535133469887a6e9517b1d8977/A-naive/event.json); [Change B event](../runs/benchmark-43329a535133469887a6e9517b1d8977/B-naive/event.json); [before B](../runs/benchmark-43329a535133469887a6e9517b1d8977/B-naive/before.json) and [B baseline schedule](../runs/benchmark-43329a535133469887a6e9517b1d8977/B-naive/outcome.json). Task owners, priorities and incident deadline also match [fixture generation](../coordination_sim/benchmark/generation.py).

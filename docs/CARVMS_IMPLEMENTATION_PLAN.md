# CARVMS — Implementation Plan & Prioritized Backlog

Baseline: verified by direct inspection on 2026-08-12/13. See `CARVMS_ARCHITECTURE.md` for
the "what exists today" tree — do not re-derive it from this document.

> **Status (2026-08-13): P0 and P1 are complete. P2 is complete (140/140 tests) and a
> working frontend exists, verified end-to-end in a browser against the real backend
> using multiple real logged-in accounts.** Done: penalty/recovery, PDF+Excel+CSV
> exporters (proven consistent with the dashboard), dataset reconciliation, forensic
> anomaly detection, report templates/history, global search, customizable/saved
> dashboard layouts, center performance scoring (equal starting weights, per the user's
> own choice — Admin-editable), Gmail OAuth connection scaffolding (state-token flow,
> Fernet-encrypted tokens at rest, runs unconfigured without error), and a React SPA
> covering all of it. Both items previously blocked on the user (scoring weights, email
> provider choice) are now resolved and built. What remains: a real Google Cloud OAuth
> app registration (external setup, see `docs/EMAIL_SETUP.md` — not more engineering) to
> unblock an actual end-to-end Gmail connection, the automation engine's use of that
> connection, and the AI Analyst (P3). See `CARVMS_COMPLETION_REPORT.md` for verified
> detail. The P1/P2 lists below are kept as originally written rather than edited after
> the fact.

## P0 — Broken / Core (fix immediately, this session)

| # | Item | Why P0 |
|---|---|---|
| P0-1 | `requirements.txt` is UTF-16LE encoded | Breaks plain `pip install -r requirements.txt` |
| P0-2 | `/auth/register` accepts client-supplied `role` unchecked | Privilege escalation — anyone can self-register as Admin |
| P0-3 | `is_active` is a String and never checked at login | Inactive users can still log in; type is wrong |
| P0-4 | Two different hardcoded JWT secrets in two files, one file (`auth_utils.py`) is dead/unused | Security smell + duplicate/dead code the brief tells us to clean up |
| P0-5 | No settings/config module; no `.env`; no CORS | Secrets in source; brief explicitly forbids this |
| P0-6 | `datetime.utcnow()` naive timestamps in JWT | Deprecated, timezone bugs at expiry boundaries |
| P0-7 | No Alembic; schema managed by `create_all` only | Any schema change today would risk the real data (1 admin row) |
| P0-8 | Zero tests | Nothing verifies auth actually works beyond manual curl |
| P0-9 | Stray empty untracked folder `backend/SOHAIL-OS-v11/` | Cleanup — confirmed empty, 0 bytes, not in git, safe |

**All of P0 executed in this session** — see `CARVMS_COMPLETION_REPORT.md` for what's
COMPLETED/TESTED after the fact.

## P1 — Essential (core application, next)

1. RBAC enforcement — `require_role()` dependency wired into every future business route;
   admin-only user management endpoint (promote/demote/deactivate) replacing self-serve roles.
2. Org hierarchy model (`org_dimensions`/`org_nodes`) + default Zone→Cluster→Region→
   Zonal Mgr→Regional Mgr→Center→Employee seed, editable.
3. Dataset upload + storage abstraction (Excel/CSV first — PDF/Word/PPT/image parsing is
   P2, since it needs per-format extraction work the brief itself separates conceptually).
4. Data profiling: column typing, null/dup rates, basic quality score, auto-dimension
   mapping to org hierarchy where column names match.
5. Audit / Finding / Evidence CRUD with RBAC, status workflow, pagination, filtering.
6. Metric Engine v1 — the single semantic layer (counts, sums, exposure, recovery %) that
   both a first dashboard endpoint and CSV export both call, proving the "one number"
   guarantee before more exporters are added.
7. Audit trail (`audit_logs`) — immutable, on every mutating action from step 5 onward.
8. Alembic-driven migrations for every model added above (no more `create_all`).
9. Tests for every item above (RBAC allow/deny, upload validation, CRUD/workflow, metric
   engine correctness, audit log immutability).

## P2 — Advanced (BI, reporting, automation)

1. Center performance scoring engine — **configurable weights, not invented ones**; admin
   UI/endpoint to set weights; documented default = equal-weight until the user supplies
   real business weights.
2. Reconciliation engine (dataset vs dataset vs DB) with matched/missing/extra/mismatch
   output.
3. Forensic/anomaly detection rules (duplicate claims, repeated amounts, threshold
   gaming, peer-group outliers, etc.) — each finding stores entity, observed, baseline,
   rule, risk level, evidence pointer; framed as "Exception/Red Flag/Requires
   Verification," never as a fraud conclusion.
4. Report Builder + Report Factory (Excel/CSV/PDF/Word/HTML/JSON), all backed by the
   Metric Engine; report template save/reuse; report history.
5. Global search across centers/employees/audits/findings/datasets/reports.
6. Dataset management UI (list/search/reprocess/archive/compare/export/delete-by-permission).
7. Email integration: OAuth consent flow (Gmail/Microsoft 365, provider-agnostic
   adapter), composer with To/CC/BCC suggestion-only + explicit confirm-and-send, audit
   logging of sends, templates with variables.
8. Automation Engine: scheduled jobs (monthly report, daily exception scan, monthly
   ranking) with active/inactive, schedule, owner, logs, retry, and a mandatory human
   approval gate before any send/delete/publish/approve step executes.
9. Dashboard customization + saved dashboard configs; PostgreSQL migration path validated.
10. Frontend build begins here in earnest — there is currently no UI to extend, so this is
    net-new React work using the Metric Engine API, not a redesign of an existing screen.

## P3 — Intelligence (AI, NLP, predictive)

1. AI Analyst service: NL question → calls against Metric Engine/repositories only (no
   raw-SQL generation, no fabricated numbers); write/send/delete intents always produce a
   draft requiring human confirmation.
2. Natural-language commands mapped to safe, whitelisted query/report/email-draft actions.
3. Predictive/trend extensions (most-improved/deteriorated, forecast) — only after P1/P2
   metric definitions are stable, since predictions built on an unstable metric layer
   would be misleading.

## Sequencing rationale

P1 must land before P2/P3 because almost everything in P2/P3 (scoring, reports, AI
answers) reads from entities that do not exist yet (audits, findings, org hierarchy,
datasets). Building report/AI features against a schema of one `users` table would mean
either fabricating data or re-doing the work once P1 lands — both violate the brief's
explicit "never fabricate" and "do not rebuild" rules.

## Decisions that need the user, not invented

- Center performance score weights (brief explicitly forbids inventing these).
- Real organizational hierarchy names/depth if they differ from the six default roles.
- Which email provider(s) to support first (Gmail vs Microsoft 365) and OAuth app
  registration (external credentials — cannot be created by the agent).
- Penalty rule formulas.
- Whether `carvms.db` should stop being committed to git (recommend yes, but that
  rewrites nothing historical — just stops future commits of the binary; confirming
  before changing `.gitignore` behavior around a file the user may be relying on).

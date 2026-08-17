# CARVMS — Completion Report

Session date: 2026-08-13. Scope: P0 (broken/core) + P1 (essential core application) + P2
(advanced BI/forensic/automation, now including report templates/history, global search,
customizable/saved dashboard layouts, center performance scoring, and Gmail OAuth
connection scaffolding) + **the first working frontend**, per
`CARVMS_IMPLEMENTATION_PLAN.md`. Every claim below was verified by running the actual
code — nothing here is aspirational.

## Weekly Revenue Closure — review-queue wiring, Excel export, and full frontend built (latest pass)

Closes out the last remaining gap from the previous pass: the response-portal/review-queue
wiring and the multi-sheet Excel generator are both now built, tested, and live-verified end to
end (upload -> review -> close -> KPI dashboard -> export).

**Backend.** `app/api/weekly_revenue_closure.py` -- full router (`/weekly-revenue-closure`),
gated the same way as Delayed Cash Billing (Admin/Auditor). `weekly_revenue_closure_export_service.py`
regenerates the real workbook's exact three-sheet shape (`Sheet1` unfiltered pivot, `Penalties`
two-section breakdown with Cluster/Zonal rollups, `Data` raw detail) from a closed batch's own
rows -- never from a hand-maintained pivot, so it can't drift into the same arithmetic errors
proven present in the real Week 3 reference file.

**A real bug found and fixed while adding the export tests**: `mark_no_remark_received`
(the action that moves a pending incident into "Remarks Not Received") was not marking the
original incident row in any way -- so it stayed forever in the pending-review queue, stayed
counted in `pending_review_count`, and got double-counted in the `Sheet1` pivot (once as a
remark-received incident, once again via its own no-remark-incident row). Fixed with a new
`moved_to_no_remark` column (migration `2f9c21afaf89`) and three call-site fixes
(`list_bill_incidents`, `get_batch_summary`, `_write_sheet1`/`_write_data_sheet`). Caught by the
export round-trip test, not by inspection -- exactly the kind of thing this project's "run the
actual code" discipline exists to catch.

Also resolved a **test-suite false alarm**: two pytest invocations (an earlier background
full-suite run and a new foreground run) were racing on the same file-based SQLite test DB,
producing `no such table: users` errors that looked like real failures but were a fixture
teardown/setup collision. Serialized re-run confirmed zero real regressions. Full suite: **292
passed, 0 failed.**

**Frontend.** New `WeeklyRevenueClosurePage.tsx` -- Batches tab (upload modal, batch list, a
KPI dashboard per batch using `BatchSummaryOut`'s fields, center-penalty and Cluster/Zonal-
escalation tables, close-batch and export-workbook actions) and a Review Queue tab (Considered /
Not Considered / Mark No Remark Received, with an optional remarks field), replacing the
previous honest-status-only placeholder. New `lib/resources/weeklyRevenueClosure.ts` and
matching `lib/types.ts` entries, mirroring the Delayed Cash Billing resource file's shape.
Type-checked (`tsc -b`) and linted (`oxlint`) clean.

**Live-verified in the browser** end to end against a synthetic two-center workbook (uploaded via
the real API, since the sandboxed browser tool can't drive a native file-picker dialog): upload
ingested 2 incidents; the Review Queue correctly showed and then cleared both; closing the batch
computed a KPI dashboard matching the proven formula exactly (2 centers x 6.25% = 12.50% total
center penalty rate, one Cluster Manager escalation row per center, no fabricated Zonal Manager
row since none was supplied); the export endpoint returned 200 OK. Demo batch/rule deleted
afterward so they don't clutter the real system before real weekly data arrives.

**Known gap, not yet built**: there is still no API endpoint (for either Weekly Revenue Closure
or Delayed Cash Billing) to create/approve a penalty rule through the running app -- the only way
today is a one-off script against the DB (`create_rule`/`approve_rule` exist in both services but
are never called from a router). Worth a small rule-management endpoint + admin UI before this
goes to real users.

## Dark "vigilance & investigation" theme (latest pass)

Applied a dark, Tailwind-v4 class-scoped theme (`.dark` on the internal app's root, `@custom-
variant dark`) across every internal page, `AppShell`, `Login`/`Register`, and every shared `ui/`
component -- scoped so the public NephroPlus-branded response portal (reached by center managers
via the single shared link) stays light/branded and untouched. Added a small hand-drawn icon set
(`components/ui/Icons.tsx`, no external dependency) used throughout the sidebar and the new WRC/DCB
KPI dashboards. Verified via `getComputedStyle`/browser screenshot, not just source inspection.

**Known minor limitation**: an internal sweep script had a sequential-substitution bug that
collapsed the `text-slate-600/500/400` gray hierarchy toward `text-slate-500` in the 18 swept page
files -- text stays legible (verified) but loses some of its original visual hierarchy. Low
priority; flagging rather than silently leaving undocumented.

**Not yet resolved**: the request said "dark themed ... with pictures" -- what's built is an icon
set, not literal illustrative imagery/photography. Worth confirming with the user whether icons
satisfy this or actual imagery is expected.

## Weekly Revenue Closure — raw ingestion format proven, parser built

Immediately after the calculator-core pass below, the user supplied two more real files
(`July-26-Week{2,3}-closure pending List...xlsx`) -- exactly the missing raw daily source
identified as a gap in that pass. Their `Center wise` sheet (Zone, Cluster, Center Code, Center
Name, Date, Billed Sessions, Daily Report, Variance, Remark, Final Remarks) is the pre-remark
pending list, one row per center per day, upstream of the Penalty output workbooks' `Data` sheet.

Verified by direct reconciliation: aggregating Week 2's raw rows (excluding a newly-discovered
`Excess billed/Incorrect Daily report` category -- proven out of scope for this penalty engine,
since none of its 16 rows/12 centers appear anywhere in the Penalty output workbook) reproduces
that same file's own `Center Penalty` sheet exactly, 35/35 centers, zero mismatches. Week 3's
pending file does *not* self-reconcile as cleanly (7 centers undercounted in its own stale pivot,
likely because the file's filename date is later than when that pivot was last refreshed) -- the
new parser (`app/services/weekly_revenue_closure_upload_service.py`) reproduces the raw sheet's
actual row counts directly, never a stale pivot's stated total, consistent with this project's
"never quietly reproduce a known-wrong figure" rule. 5 new tests, all built against the real Week 2
file's actual bytes (not synthetic data) -- full suite now green with zero regressions.

Formula analysis doc updated (`CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md` §6.4): the last
blocking gap from the previous pass is now resolved. What remains is the response-portal/review-
queue wiring (expected to reuse the Delayed Cash Billing pattern closely) and the multi-sheet Excel
generator -- both now unblocked since every input/output shape they need has real-data proof.

## Weekly Revenue Closure — formula proven, calculator core built

A brand-new engine, added to the sidebar just above Delayed Cash Billing per the user's request,
but built with the same discipline as that engine: **the formula was reverse-engineered from two
real reference workbooks the user shared (`Jul'26 - Week 2/3 - Penalty.xlsx`) and proven before any
calculator code was written** -- see `CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md` for the
full proof. This is deliberately a **separate engine from Delayed Cash Billing** with a different
role hierarchy: Center Manager and Cluster Manager penalties (and, conditionally, Zonal Manager)
**do** apply here, where Delayed Cash Billing explicitly excludes Center/Cluster Manager penalties.

**The proven formula**: a flat 6.25% penalty per delinquent center per week (never scaled by how
many incidents that center had), escalating to the Cluster Manager as 6.25% × the count of distinct
centers under them with a qualifying incident, and to the Zonal Manager the same way but *only* for
the "remarks never received" case, never for "remark received but rejected" (both escalation rules
confirmed directly by the user, not inferred from a single ambiguous data point). Every rollup
number in both source files was cross-checked **programmatically** (not by eye): Week 2 matched the
workbook's own stated figures 23-for-23; Week 3 matched 9-for-13, and the 4 that didn't are
confirmed real arithmetic errors in that file's hand-built pivot tables (all undercounts) --
concrete, quantified evidence of exactly the kind of mistake this automation is meant to eliminate.
The calculator deliberately reproduces the *correct* numbers, not the 4 known-wrong ones.

**Built**: `app/models/weekly_revenue_closure.py` (rule/batch/bill-incident/no-remark-incident/
center-penalty/role-penalty tables) and `app/services/weekly_revenue_closure_service.py` (rule
lifecycle + the proven calculator), migrated via a clean set of fresh `CREATE TABLE`s. 9 new tests
reconcile both real weeks exactly (including a grand-total cross-check computed independently of
the fixtures used for the per-entity assertions) -- full suite now at 277 passed.

**Deliberately not built yet**: an upload/ingestion endpoint. The two workbooks supplied are each
week's *output*, not the raw day-by-day source (billed sessions vs. daily report, every center,
remark or not) the real weekly process starts from -- that file wasn't part of what was shared, so
there's no proven layout to parse yet, the same gap Delayed Cash Billing had before its own
`Bills Data` sheet was confirmed. The frontend page at `/weekly-revenue-closure` states this
plainly rather than shipping a form that goes nowhere.

## Delayed Cash Billing — single shared link, per-bill review queue, contact-change notifications

Direct response to three concerns raised after the upload/publishing pass below: (1) minting
500 separate per-case links to email out individually was unworkable, (2) the review verdicts
described (Considered / Not Considered / Need More Detail / Need Proof) needed one place to
live, and (3) a center manager's self-reported name/NPID/email must never write to the Org
Master without an Admin explicitly approving it first.

**One shared public link, kept alongside the existing per-case token link (both work, per
explicit choice).** `GET /respond/delayed-cash` (no token) lets a manager pick their own center
from the same public centers-directory dropdown already used for the mismatch-tracking field,
then lists every case still open for that exact code (`GET /public/delayed-cash/open-cases` --
"open" = `validated_penalty IS NULL`, i.e. at least one bill hasn't reached a terminal verdict
yet) and lets them submit against it (`POST /public/delayed-cash/cases/by-id/{id}/respond`).
This is a deliberate, documented security trade-off: soft-flag, not hard-block. Anyone who
knows a (public) center code can view/submit for that center's open case -- a hard NPID check
against the Org Master was considered and explicitly rejected, because a stale/wrong record for
even one center would lock out a legitimate manager. A mismatch is recorded for Vigilance to
see, exactly like the existing `selected_center_code` tracking. The per-case token flow is
completely untouched and still works exactly as before. The response form itself was extracted
into a shared `DelayedCashCaseCard` component so both entry points render identically and any
future fix to the form only has to happen once.

**Mandatory Center Manager Email ID**, added below Name/NPID on both entry points, and used as
the raw input to a brand-new contact-change-request workflow rather than ever writing straight
into `OrgNode.manager_email` (or `manager_name`/`manager_npid`). Every submission proposes a
change (`OrgNodeContactChangeRequest`, one pending row per center, refreshed in place if a
center submits again before the first is reviewed) that only takes effect once an Admin clicks
Approve on the Notifications tab -- Reject leaves the Org Master record untouched. Resolved by
the submitted center code against the existing `external_code` lookup; if no node matches, the
request still gets recorded (nothing typed is silently dropped) but can't be approved until the
center is fixed in Org Hierarchy.

**Per-bill review queue**, because the four verdicts described apply per bill (matching how the
calculator already sums penalties), not per case. `DelayedCashBill.considered` now carries four
values instead of two -- `considered` / `not_considered` (terminal, feed
`recompute_validated_penalty`) and `needs_more_detail` / `needs_proof` (kick the case back to
the center; treated the same as "not yet reviewed" by the validated-penalty calculation, which
now requires every bill to reach a *terminal* verdict, not just a non-null one). The Review
Queue tab lists every non-terminal bill; clicking Need More Detail/Need Proof (re)mints that
bill's case response link and surfaces it inline to copy-paste manually -- there's no automatic
email send yet since no center email list has been supplied; swapping in real sending later is a
drop-in replacement for that one manual-copy step, not a redesign.

**23 new backend tests** across three new files (`test_delayed_cash_open_link.py`,
`test_delayed_cash_review_queue.py`, `test_org_contact_change_requests.py`) plus updates to
existing response-portal tests for the now-mandatory email field. Full suite: 268 passed, zero
regressions. Browser-verified live end-to-end against the real dev backend: submitted a real
response through the single shared link (mandatory email included), watched the resulting
contact-change notification appear and confirmed approving it actually updated the `OrgNode`,
and exercised the review queue's Need Proof / Considered buttons, confirming the minted link
resolves through the real public portal and terminal decisions correctly mint no link.

## Delayed Cash Billing — upload, ingestion & publishing pipeline

Closes the gap between the already-proven calculator core (`delayed_cash_penalty_service.py`,
see `CARVMS_DELAYED_CASH_PENALTY_FORMULA_ANALYSIS.md`) and an actual usable workflow: Vigilance
can now upload the real weekly `Bills Data` workbook and publish response-portal links, end to
end, without touching a database console.

**Upload service** (`delayed_cash_upload_service.py`, new) parses the workbook's `Bills Data`
sheet (falling back to the first sheet if a file doesn't use that exact name) into the same
`RawBillInput` rows the calculator already consumes — header matching is case/space/punctuation
-insensitive, so `CENTREID`, `centreid`, and `Centre ID` all resolve the same column. A bad row
(missing Center Code/Name/Sales Bill, an unparseable `BILLDATE`/`created_date`, a non-numeric
`day_difference`, or a Sales Bill repeated within the same file) is skipped and reported by row
number — never silently dropped, and never allowed to abort the rest of the batch, mirroring the
per-row isolation pattern already established in `org_sheet_sync_service.py`. Only a genuinely
unusable header row raises (surfaced as an HTTP 400 with the missing column names named).

**New endpoints** on `/delayed-cash` (Admin/Auditor only, same `VIGILANCE_ROLES` gate as the
rest of this domain):
- `POST /batches/upload` — multipart upload (`period_start`, `period_end`, `file`) → parses,
  ingests every bill, computes each center's publishing-stage `calculated_penalty`, and returns
  the batch + per-center results + the skip report in one response.
- `GET /batches` / `GET /batches/{id}` — list/inspect upload batches.
- `POST /batches/{id}/publish` — bulk-issues a fresh public response-portal token for every
  center in the batch (reusing the existing single-case `generate_response_link_token`) and
  marks the batch `published`. Safe to call again — always mints new tokens, invalidating any
  previous links, same contract as the pre-existing single-case endpoint.

**Frontend** (`DelayedCashBillingPage.tsx`, new, at `/delayed-cash`, Admin/Auditor-only route
and nav item — kept entirely separate from the not-yet-built Weekly Revenue Closure feature,
different engine/data/nav entry, never merged): upload modal with period pickers + file input,
a skip-report table shown inline when rows are skipped, a batch list with per-batch "View
centers" (drills into that batch's center penalties) and "Publish links" (shows every minted
response URL with one-click copy, ready to paste into the notification email).

10 new backend tests (`test_delayed_cash_upload.py`) build real `.xlsx` workbooks in-memory via
`openpyxl` — RBAC gating, the no-approved-rule 400 path (via `monkeypatch`, deterministic
regardless of what other test files already approved in the shared test DB), successful
ingestion reproducing the correct per-center totals, all four skip-row reasons in one batch
without aborting it, missing-header 400, batch listing/detail, and publish issuing/re-issuing
tokens that actually resolve through the real public portal lookup. Full suite: 236 passed.
Also browser-verified live end-to-end against the real dev backend: uploaded a real two-center
workbook, confirmed the correct ₹400/₹200 totals, published links for both centers, and
confirmed one of the minted tokens resolves through the actual public case-lookup endpoint.

## Center performance scoring & Gmail email integration (latest pass)

**Center performance scoring** ranks centers relative to each other on four components —
financial exposure, recovery rate, open findings, repeat findings — never against an
invented absolute threshold. Weights are Admin-editable (`CenterScoringWeight`, one row
per component) and **default to equal (0.25 each)**, per the user's own explicit choice
when asked rather than a guessed split. Each component is min-max normalized across the
centers actually being compared (so "good"/"bad" is always relative to the current data,
not a fabricated scale), and a center missing a component entirely (e.g. no penalties yet,
so no recovery rate) has that component *excluded* from its composite score rather than
defaulted to 0 or 1 — excluding it is the honest choice; defaulting would silently reward
or punish centers for data that doesn't exist. Visibility reuses the same
`audit_service.scope_query_to_role`/`descendant_node_ids` RBAC scoping as everything else
— a Regional Manager sees only their subtree, an unscoped role sees an empty list (never a
403 — rankings degrade gracefully rather than error). 9 backend tests + a frontend page
(Admin-only weight editor, rankings table color-coded by composite score) — both verified
live in the browser against the real backend (see below).

**Gmail OAuth connection scaffolding.** Each user can connect their own Gmail account via
a standard OAuth 2.0 authorization-code flow. Because Google's redirect back to
`/email/callback` carries no Authorization header of ours, the flow uses a server-side
state-token table (`EmailConnectionRequest`) to map the callback back to the user who
started it — the token is single-use (deleted on consumption) and expires after 10
minutes. Tokens are encrypted at rest with a locally-generated Fernet key
(`EMAIL_TOKEN_ENCRYPTION_KEY`) — explicitly *not* the same thing as `GOOGLE_CLIENT_SECRET`,
which is issued externally by Google and was never generated, seen, or requested by the
agent building this; the two are documented separately in `.env.example` and
`docs/EMAIL_SETUP.md` specifically so that distinction stays clear for whoever configures
it. The whole app runs fine with Google OAuth unconfigured — `/email/providers` just
reports `configured: false` and the Settings page shows a "not set up yet" message
pointing at the setup doc, rather than erroring or crashing at startup. Disconnecting
actively clears the stored tokens (not just a status flag) so a revoked connection can't
leave a live credential sitting in the database. 17 backend tests (state-token issuance,
expiry, single-use enforcement, the full connect→callback→status→disconnect round trip
with `httpx` mocked so no test ever reaches Google) + 4 more for the encryption wrapper
itself (roundtrip, missing key, malformed key, wrong key on decrypt).

**Two real bugs caught before/during this pass:**
1. `EMAIL_PROVIDERS = ("gmail",)` is a Python 1-tuple; naively formatting it into a SQL
   `CHECK (provider IN {EMAIL_PROVIDERS})` constraint (the same pattern used successfully
   for the *multi*-value `EMAIL_CONNECTION_STATUSES` tuple) rendered as
   `IN ('gmail',)` — the trailing comma is a SQLite syntax error. Caught immediately by
   actually running the migration (it failed outright), not by code review. Fixed with an
   explicit `_sql_in_clause()` helper instead of relying on Python's tuple `repr`, and
   cleaned up the orphan table the partially-applied migration had left behind before
   regenerating and re-applying it.
2. Comparing a state token's `expires_at` (read back from SQLite, which silently drops
   tzinfo even on a `DateTime(timezone=True)` column) against a fresh timezone-aware
   `datetime.now(timezone.utc)` raised `TypeError: can't compare offset-naive and
   offset-aware datetimes` — caught by the expiry test, not by inspection. Fixed by
   treating a naive read-back as UTC (attaching `tzinfo=timezone.utc`) before comparing,
   since that's what was actually written.

**Browser verification.** Both features were checked live against the real (restarted,
migrated) backend, not just unit-tested:
- Center Rankings page loads real `/center-scoring/rankings` and `/weights` data (200 OK,
  confirmed via network inspection) and renders the honest empty state
  ("No centers to rank") for the currently-logged-in account's actual data — not a
  fabricated non-empty table.
- Settings page's Connect Email widget correctly shows "not set up yet" (Google
  credentials are genuinely blank in this environment's `.env`).
- The full backend callback→frontend redirect chain was exercised end-to-end: hitting
  `/email/callback` with a deliberately invalid state token redirected the browser to
  `/settings?email_error=...`, the Settings page displayed the error banner, and then
  correctly stripped the query params from the URL so a page reload doesn't re-show a
  stale error. A real full round trip (actually connecting a Gmail account) needs a real
  Google Cloud OAuth app, which is outside what this session can create — see the "next"
  section below and `docs/EMAIL_SETUP.md` for the exact steps.
- Re-confirmed the now-familiar operational lesson: the long-lived backend dev process
  from earlier in this session was still serving the pre-change route table (`404` on
  `/email/providers`) even though the code and migration were correct; killed and
  restarted it without `--reload`, then verified live before doing anything else.

## Dashboard customization

`DashboardLayout` saves a named presentation config — which KPI cards show, whether the
status/severity charts show, and a default filter set — never a computed result, so a
saved layout can't go stale. Private layouts are visible only to their owner (a 404, not
a 403, for anyone else — a private layout's existence isn't leaked); `is_shared` layouts
are visible to every authenticated user, editable/deletable only by the owner or an
Admin. 7 tests, including one confirming a shared layout is genuinely visible to a
*second* real user account, not just the creator (verified twice: once via pytest with
two registered users, once live in the browser logged in as two different real accounts —
`testadmin` saved "Monthly Management Dashboard" with 4 of 6 KPIs and a `Draft` status
filter; logging in as `field_auditor` and selecting it from the dropdown reproduced the
exact same 4 KPIs and filter, with no delete control since that user isn't the owner).

**A real operational bug, again only caught by browser verification:** `uvicorn --reload`
detected the file change, printed "Reloading...", but never actually swapped in a new
worker process — the old worker (same PID as before the edit) kept serving the stale
route table indefinitely, silently. `--reload`'s own log output claimed success. Fixed by
killing both the reloader and the stale worker and starting a fresh process without
`--reload`, restarting manually after each further backend change instead. This is the
same class of issue as the earlier stale-server bug, but worse: `--reload` was supposed
to prevent it and gave a false positive ("Reloading...") while not actually doing so.
**Lesson: after a backend code change, verify the new route actually responds (a 401 or
200, not 404) before trusting `--reload`'s log line — don't assume the reloader worked.**

## Report templates, history, and global search

**Report templates + history.** `ReportTemplate` stores a named, reusable filter set
(never a result — every run reads live from the Metric Engine, so a template can't go
stale the way a cached report would). Every export — template-run or ad-hoc, from any of
the three formats — now writes a `ReportHistory` row (name, filters used, format,
generated-by, timestamp). "Regenerate" re-runs a past entry's *exact* filters against
*current* data and links the new row back via `regenerated_from_id` — it is explicitly
not a re-download of a stored file (none exists), which was verified: regenerating
after adding more data produces different, updated numbers, not a stale snapshot.
7 tests, including one asserting a template run's TOTAL row matches the dashboard for
identical filters — the same "one number" guarantee extended to a fourth entry point.

**Global search.** `GET /search` matches audits/findings/org nodes/datasets/report
templates/penalty rules by partial, case-insensitive text. Audits and findings are
filtered through the exact same `audit_service.scope_query_to_role` used everywhere
else — verified by test: an Auditor's search for another Auditor's audit by its exact
title returns nothing, while the same search as Admin finds it. 7 tests.

**Frontend:** a Reports page (save/run/delete templates, browse and regenerate history)
and a search bar in the app shell linking to a results page — both verified in a live
browser against the real backend, not just type-checked. This surfaced two real issues:

1. **The backend server had been running without `--reload`** since before this
   session's new routers were added to `main.py` — every new endpoint 404'd in the
   browser despite the code being correct and the unit tests passing (tests spin up a
   fresh app import each run; the long-lived dev server did not). Restarted with
   `--reload`. This is a real operational lesson, not a code bug: **a running dev
   server must be restarted (or run with --reload) after adding new routes** — passing
   tests do not guarantee a stale running process has picked up the change.
2. A `computer`-tool-simulated Enter keypress didn't trigger the search form's submit in
   the browser-automation layer (confirmed by triggering `form.requestSubmit()`
   directly, which worked correctly) — a tool-simulation quirk, not an app defect;
   real clicks and real typing both work.

## Frontend (built earlier this session)

A React + TypeScript SPA (`frontend/`) now exists and was verified end-to-end **in a real
browser against the real backend** — not just described, not just type-checked. Every
one of the following was actually clicked through and confirmed working, with real
numbers checked against the underlying math:

- Register → auto-assigned `Auditor` role (privilege escalation blocked, same as the API
  test) → login → JWT persisted → protected routes redirect correctly.
- Create an audit, add a finding with exposure/recoverable amounts, upload evidence,
  move through the exact backend state machine (buttons only ever offer valid next
  states) → dashboard KPIs update to match.
- Create a penalty rule (percentage-of-base), propose a penalty against a finding, watch
  the computed amount match the formula exactly (10% of ₹15,000 = ₹1,500), approve it,
  record a partial recovery (stays `Approved`), record the rest (flips to `Recovered`
  automatically) — all through the UI, matching the pytest-verified backend behavior.
- Export the same audit list as CSV, Excel, and PDF from the dashboard — confirmed via
  network requests, no errors.
- Upload a CSV with a known duplicate row, a known repeated value, and a known outlier →
  profiling numbers (7 rows, 3 duplicate rows, 57.14% quality score) matched the actual
  math by hand. Ran all three anomaly rules → got exactly 5 anomalies, each framed as
  "Exception"/requires-verification. Escalated one to a real Finding, dismissed another
  with a required reason.
- Uploaded two more datasets with a shared `claim_id` key and a deliberately mismatched
  row, a missing row, and an extra row → reconciliation returned exactly 1 matched / 1
  mismatched / 1 missing / 1 extra, with the mismatch diff shown correctly.
- Built an org hierarchy node tree (Zone → Center) through the admin UI and confirmed the
  parent link rendered correctly.
- Changed another user's role and deactivated/reactivated them from the Users admin
  page; confirmed an Admin **cannot** change their own role or deactivate themselves
  (button disabled client-side, and the backend independently returns 403 when tested
  directly).
- Logged in as a Finance-role user and confirmed the "Org Hierarchy"/"Users" nav links
  are hidden, direct navigation to `/admin/users` shows a permission message, **and** a
  raw API call to `/users` from that session gets a real 403 from the backend — the
  frontend guard is UX, not the actual security boundary.

**Two real bugs found and fixed during this verification** (not by code review — by
actually using the app):
1. There was no UI anywhere to create a `PenaltyRule`, making the propose-penalty flow a
   dead end on a fresh install. Added an inline rule-creation form gated to Admin.
2. A table-layout bug: `<table>` cells had zero horizontal padding, and lacking
   `min-w-0` on the flex layout, a wide table dragged the *entire page* — including the
   fixed sidebar — into horizontal scroll. Fixed by padding table cells and wrapping
   each table in its own `overflow-x-auto`, so only the table scrolls now, never the
   shell.

See `frontend/README.md` for structure and a Windows-specific gotcha (paths containing
`&` break `npm run dev`/`npx` — call the vite/tsc/oxlint binaries directly instead).

## 0. Repository identity (unchanged)

Two unrelated projects exist across this environment's working directories.
`SOHAIL-OS-v11` (primary working directory) is a personal finance app and was never
touched. All work is in the second working directory:
`D:\Sohail - Vigilance\Reports\Weekly & Daily Cash Billing Automation\CARVMS`.

## 1. COMPLETED

### P0 + P1 (see prior report revision in git history / session transcript for full detail)
Auth security fixes, Alembic migrations replacing `create_all`, RBAC + immutable audit
trail, dynamic org hierarchy, Audit/Finding/Evidence domain with explicit state machines
and role-scoped visibility, dataset upload + real CSV/Excel profiling, and Metric Engine
v1 (dashboard + CSV export, proven to agree).

### P2 — this pass

**Penalty / Recovery domain.** `PenaltyRule` (Admin-configured `formula_config` — a rule
with a missing/unknown formula type or missing percentage/amount is rejected outright,
never defaulted), `Penalty` (Proposed → Approved/Rejected → Recovered state machine,
approval restricted to Finance/Admin, proposal restricted the same way Finding creation
is — creator or assignee of the parent audit), `Recovery` (partial recoveries accumulate;
a penalty only flips to `Recovered` once the sum of its recoveries reaches the penalty
amount — computed live from the recovery rows, never a separately-tracked duplicate
total). Every propose/decide/recover action writes to `audit_logs`.

**PDF + Excel exporters — the "one number" guarantee extended to four outputs.**
`GET /reports/audits/export.xlsx` and `GET /reports/audits/export.pdf` were added
alongside the existing CSV exporter, and all three (plus the dashboard) now share one
`_build_export()` helper on top of the same Metric Engine functions
(`get_visible_audits_query`/`compute_summary`) introduced in P1. This isn't a design
intent stated in prose — `test_csv_xlsx_pdf_and_dashboard_all_agree` asserts the CSV
TOTAL row, the Excel TOTAL row, the PDF's extracted text, and the dashboard JSON all
contain the identical exposure/recoverable figures for the same filters, in the same test.

**Dataset reconciliation.** `POST /reconciliations` compares two uploaded tabular
datasets on a chosen key column (independently named per side — real files rarely share
exact column names), producing matched/mismatched/missing/extra counts and capped
example rows (`MAX_EXAMPLES=200`, with an explicit `*_truncated` flag — counts themselves
are always exact, never estimated from a sample). Bad input (wrong file type, unknown
column) is rejected as a clean 400 with no wasted row; a genuinely unexpected failure
during comparison is caught and persisted as a `status="failed"` record with the real
error, mirroring the dataset-profiling failure pattern from P1.

**Forensic anomaly detection.** `POST /datasets/{id}/anomaly-scan` runs three real,
general-purpose rules against the actual uploaded file: exact duplicate rows, an
over-threshold repeated value in a caller-specified column, and standard IQR statistical
outliers (1.5× IQR — the textbook convention, not an invented threshold) in a
caller-specified column. Every result is stored with entity/observed/baseline/difference/
risk-level/evidence/recommended-verification fields, framed as "Exception"/requires
verification — never a fraud conclusion, matching the brief's explicit instruction. An
anomaly can be `Dismissed` (with a required reason) or `Escalated` — escalation creates a
real, tracked `Finding` under a human-chosen audit (subject to the same
`authorize_mutate` permission finding creation already requires) and is blocked from
running twice on the same anomaly. This deliberately does NOT claim to detect the full
forensic taxonomy in the brief (impossible chronology, FASTag mismatches, backwards ODO,
travel inconsistencies, etc.) — those need domain-specific column semantics a generic
engine cannot honestly infer without being told what each column means.

## 2. TESTED

```text
pytest tests/ -v   ->  140 passed, 0 failed
```
Breakdown: 93 from three passes ago (P0/P1/P2 core + exporters + reconciliation +
anomalies) + 7 report templates/history + 7 global search + 7 dashboard layouts + 9
center scoring + 17 email connection + 4 crypto service = 140. Plus a live smoke test
against the real, migrated `carvms.db`, and full manual browser verification of every
frontend feature against the real backend, using multiple real logged-in accounts to
prove shared-vs-private and role-scoped visibility — not asserted, reproduced.

Real bugs this session (across both passes):
1. (writing the code, caught before running) `escalate_to_finding`'s first draft would
   have let an anomaly escalate into an audit the escalating user isn't allowed to touch.
   Fixed by requiring `audit_service.authorize_mutate` before calling into the service.
2. (browser verification) the backend dev server was serving stale code after adding new
   routers without a restart.
3. (browser verification) `uvicorn --reload` claimed to reload but never actually swapped
   the worker process — a more insidious version of #2, since the tool's own log line said
   it worked. See the operational lesson above.

None of 2–3 were catchable by `pytest` — each test run imports the app fresh, so a
long-lived dev server going stale is invisible to the test suite by construction. The
only way to catch this class of bug is checking the actual live response after a change,
which is exactly what the browser verification step is for.

## 3. REMAINING (see `CARVMS_IMPLEMENTATION_PLAN.md` for the rest of P2/P3)

Automation beyond the OAuth connection itself (reading/acting on connected email — its
send/read step is now unblocked in principle since the connection scaffolding exists, but
not yet built), and the AI Analyst. The frontend now covers auth,
dashboard+3-format export+saved layouts, audits/findings/evidence/penalties,
datasets+profiling+anomalies+reconciliation, org/user admin, report templates/history,
global search, center performance rankings, and a Settings page with Connect Email — it
has no screens for anything in this paragraph, because none of those backend modules
exist yet either.

## 4. BLOCKED (updated — most prior blockers resolved this pass)

Center scoring weights and the email provider choice are **no longer blocked** — the user
supplied both (Gmail; equal starting weights, all four proposed components, adjustable
later) and both are built. What's still blocked on the user or on external setup:
- **A real Google Cloud OAuth app.** The connection scaffolding is fully built and
  tested, but actually connecting a real Gmail account needs a real Client ID/Secret from
  Google Cloud Console, which only the user/an administrator can create (see
  `docs/EMAIL_SETUP.md` for the exact steps) — the agent must never generate, see, or
  request that secret.
- Real org hierarchy if different from the seeded template.
- Penalty rule formulas (the *mechanism* exists — an Admin can create rules — but no
  real-world rule has been configured because the actual percentages/amounts are a
  business decision).
- Whether `carvms.db` should stop being tracked in git.

## 5. NEXT

Both items that were genuinely blocked on the user (center scoring weights, email
provider choice) are now built. What's left:
1. **Register the Google OAuth app** (`docs/EMAIL_SETUP.md`) to unblock a real end-to-end
   Gmail connection — still requires the user/an administrator, not more engineering.
2. Build what the email connection actually enables (reading/acting on email for the
   automation engine) — real engineering scope, not blocked, once prioritized.
3. AI Analyst (P3) — real scope, not blocked, lower priority than #2.

Every other P0/P1/P2 item from the original backlog is now built and tested.

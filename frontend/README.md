# CARVMS Frontend

React + TypeScript SPA (Vite, Tailwind v4, React Router, TanStack Query) wired to the
real backend API — no mocked data anywhere. See `../docs/CARVMS_COMPLETION_REPORT.md`
for what's verified working end-to-end through the browser.

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL — defaults to http://localhost:8000
npm run dev
```

Requires the backend running first (see `../backend/README.md`) — CORS is already
configured backend-side for `http://localhost:5173`.

**Windows note:** if the path to this repo contains an `&` character, `npm run dev` /
`npx vite` fail with a cryptic `MODULE_NOT_FOUND` (cmd.exe splits the command at the
`&`). Run the underlying binaries directly instead:
```bash
node node_modules/vite/bin/vite.js          # dev server
node node_modules/vite/bin/vite.js build    # production build
node node_modules/typescript/bin/tsc -b     # typecheck
node node_modules/oxlint/dist/cli.js        # lint
```

## Structure

- `src/lib/types.ts` — TypeScript types mirroring every backend Pydantic schema exactly.
- `src/lib/api.ts` + `src/lib/resources/*.ts` — typed API client, one file per backend
  domain (auth, users, org, audits, datasets, penalties, reconciliations, anomalies,
  dashboard, reports, search, dashboardLayouts, centerScoring, email).
- `src/auth/` — `AuthContext` (JWT in `localStorage`, auto-logout on any 401) and route
  guards (`RequireAuth`, `RequireRole`).
- `src/layout/AppShell.tsx` — sidebar + topbar; nav items are role-gated the same way the
  routes are (an Auditor never even sees an "Org Hierarchy" link they'd be blocked from).
- `src/pages/` — one file per route; `audit-detail/` and `dataset-detail/` hold the
  sub-sections (findings, penalties, evidence, anomalies, reconciliation) used by those
  two detail pages.

## What's real vs. not built yet

Every page here calls the actual backend — dashboard KPIs, exports, audit/finding
workflow with real state-machine-gated buttons, penalty propose/approve/recover with
real formula math, dataset upload/profiling/anomaly-scan/reconciliation, org hierarchy
and user management, report templates/history (save filters from the dashboard, run,
regenerate against live data), a global search bar, saved/shared dashboard layouts
(pick which KPI cards and charts show, save a default filter set, share with everyone or
keep private), center performance rankings (admin-editable weights, relative scoring —
never a fabricated absolute target), and a Settings page with a Connect Email widget
(Gmail OAuth — shows "not set up yet" until an admin registers a Google OAuth app per
`../docs/EMAIL_SETUP.md`; once configured, Connect/Disconnect round-trip through the
real backend). Not built: anything that actually reads/acts on connected email, further
automation, and the AI Analyst (see `../docs/CARVMS_IMPLEMENTATION_PLAN.md`).

**If pages 404 or a new feature doesn't appear after a backend change**, check whether
the backend dev server needs restarting — see the note in `../backend/README.md`.
`--reload` has been observed claiming success while not actually restarting the worker;
don't trust its log line, verify with a real request.

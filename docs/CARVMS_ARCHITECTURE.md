# CARVMS — Architecture

> **Status (2026-08-13): §1's tree below is the original P0 baseline (2026-08-12) and is
> kept as-is for the record — it is no longer the current state.** `backend/` now has 20
> tables / 69 endpoints (auth, RBAC, org hierarchy, audit/finding/evidence, datasets +
> profiling + anomalies + reconciliation, penalties/recovery, a Metric Engine with
> dashboard + CSV/Excel/PDF export, report templates/history, global search,
> customizable/saved dashboard layouts, center performance scoring, and Gmail OAuth
> connection scaffolding). `frontend/` is no longer empty — a working React SPA exists
> and was verified end-to-end in a browser against the real backend. See
> `CARVMS_COMPLETION_REPORT.md` for the verified detail and `frontend/README.md` /
> `backend/README.md` for structure. §2's target architecture below (Metric Engine as the
> single semantic layer, dynamic org hierarchy, layered services) is what was actually
> built, not just proposed.

Status date: 2026-08-12. This document describes the **verified current state** of the
repository at `D:\Sohail - Vigilance\Reports\Weekly & Daily Cash Billing Automation\CARVMS`,
plus the target architecture. Nothing here is assumed — every claim about "current state"
was confirmed by reading the actual files.

## 0. Repository identity

There are two unrelated projects in this environment:

- `D:\Sohail - Vigilance\Sohail\Projects\SOHAIL-OS-v11` — a personal finance / investment
  tracking app (Goals, Investments, AI Financial Advisor, market intelligence). **Not CARVMS.**
- `D:\Sohail - Vigilance\Reports\Weekly & Daily Cash Billing Automation\CARVMS` — **this
  project**, "AI-based Revenue Closure, Remark Evaluation and Penalty Management System"
  per its README. This document, and all CARVMS work, targets this repository.

## 1. Current state (verified)

```text
CARVMS/
├── README.md                  # one line: project name + tagline
├── backend/                   # the ONLY code that exists
│   ├── main.py                 # FastAPI app, includes auth router only
│   ├── check_db.py             # ad-hoc script to dump the users table
│   ├── requirements.txt        # UTF-16LE encoded (bug — see backlog P0)
│   ├── carvms.db                # SQLite, 1 real row: admin/admin@gmail.com/Admin
│   └── app/
│       ├── api/auth.py          # POST /auth/register, /auth/login, GET /auth/me
│       ├── auth/
│       │   ├── security.py      # bcrypt hashing, JWT create (hardcoded secret #1)
│       │   ├── dependencies.py  # get_current_user (OAuth2PasswordBearer)
│       │   ├── roles.py         # role name constants only, unused elsewhere
│       │   └── backend/app/auth_utils.py  # dead duplicate, hardcoded secret #2, unused
│       ├── database/database.py # SQLAlchemy engine/session, sqlite:///./carvms.db
│       ├── models/user.py       # User: id, username, email, password, role, is_active(String)
│       ├── schemas/auth.py      # UserRegister, UserLogin, Token (Pydantic)
│       ├── services/user_service.py # create_user, authenticate_user
│       ├── config/__init__.py   # EMPTY — no settings module exists
│       └── ai/__init__.py       # EMPTY — no AI code exists
├── frontend/                   # EMPTY directory — no UI exists
├── ai-engine/                  # EMPTY directory — no AI engine exists
├── database/                   # EMPTY directory — no schema/seed files exist
├── docs/                        # EMPTY (this file is the first content)
├── reports/                     # EMPTY — no report generation exists
└── uploads/                     # EMPTY — no upload handling exists
```

**In one sentence: CARVMS today is a working FastAPI login/registration skeleton with one
DB table (`users`) and no other domain functionality.** Every dashboard, upload, forensic
rule, report, email workflow, and automation feature requested in the full product vision
is net-new work, not a refactor of something broken.

## 2. Target architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                            │
│  Dashboards · Datasets · Investigations · Reports · Email · Admin   │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ REST (JWT bearer)
┌───────────────────────────────▼───────────────────────────────────┐
│                        FastAPI Backend                              │
│ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌───────────────┐ │
│ │  Auth/  │ │ Dataset │ │  Audit / │ │ Metric  │ │  Export /     │ │
│ │  RBAC   │ │ Ingest  │ │ Finding /│ │ Engine  │ │  Report       │ │
│ │         │ │ +Quality│ │ Penalty  │ │(single  │ │  Factory      │ │
│ │         │ │         │ │ /Recovery│ │ source  │ │(Excel/CSV/PDF/│ │
│ │         │ │         │ │          │ │of truth)│ │ Word/HTML/JSON│ │
│ └─────────┘ └─────────┘ └──────────┘ └────┬────┘ └───────┬───────┘ │
│                                            │              │         │
│ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────▼────┐ ┌───────▼───────┐ │
│ │  Email  │ │Automation│ │AI Analyst│ │Dashboard│ │  Audit Log /  │ │
│ │Workflow │ │  Engine  │ │(advisory)│ │Aggregate│ │  Governance   │ │
│ │(consent │ │(schedule │ │          │ │  API    │ │               │ │
│ │+approve)│ │+approve) │ │          │ │         │ │               │ │
│ └─────────┘ └─────────┘ └──────────┘ └─────────┘ └───────────────┘ │
└───────────────────────────────┬───────────────────────────────────┘
                                 │
                  ┌──────────────▼──────────────┐
                  │  PostgreSQL (prod) / SQLite  │
                  │  (dev) + Alembic migrations   │
                  │  + file storage (uploads/)    │
                  └───────────────────────────────┘
```

### 2.1 The one architectural rule that prevents number disagreement

Every KPI, ranking, exposure figure, and trend used anywhere (dashboard tiles, Excel,
PDF, Word, HTML, JSON export, AI Analyst answers, emailed reports) MUST be computed by a
single **Metric Engine** module (`app/services/metrics/`) that takes `(filters) -> value`.
No other module is allowed to re-derive a KPI with its own SQL/aggregation. Exporters and
dashboard endpoints are both *callers* of the metric engine, never independent calculators.
This directly satisfies the user's non-negotiable requirement (§41 of the brief).

### 2.2 Layering

- **Models** (SQLAlchemy) — one source of truth per entity, normalized, with FKs to the
  org hierarchy tables (dynamic, not hardcoded — see Data Model doc §2).
- **Repositories** — pure data access, filter/paginate, no business logic.
- **Services** — business logic: scoring, anomaly detection, reconciliation, penalty
  calc. Every calculation records its formula/rule and inputs (never a bare number).
- **Metric Engine** — the single semantic layer described above; wraps repositories.
- **API routers** — thin; RBAC-guarded; return DTOs (Pydantic schemas), never ORM objects.
- **Export Service** — `ExcelExporter`, `CSVExporter`, `PDFExporter`, `WordExporter`,
  `JSONExporter`, all fed by the Metric Engine + Report Builder definitions.
- **Automation Engine** — job definitions with schedule/owner/logs/retry; every
  high-impact step (send email, delete, approve, publish) ends in a **human approval
  gate**, never auto-executes.
- **AI Analyst** — a service that turns NL questions into calls against the Metric
  Engine/repositories (never raw SQL from the LLM, never fabricated numbers). Write/send/
  delete intents always resolve to a *draft* the human must confirm.

### 2.3 Org hierarchy — dynamic, not hardcoded

The brief explicitly says not to assume Zone→Cluster→Region→Manager→Center→Employee is
the only shape. Architecture: an `OrgDimension`/`OrgNode` adjacency-list pair (self-
referencing `parent_id`, a `level_name` string, arbitrary depth) populated from whatever
columns the uploaded dataset actually contains, detected during data profiling. The
Zone/Cluster/.../Employee hierarchy is loaded as the *default* level template, editable by
an Admin — not compiled into the schema as fixed columns.

## 3. Non-functional architecture decisions

- **DB**: SQLite for dev (already in use), PostgreSQL for prod. Alembic manages both from
  day one of the migration work (introduced in P0) — no more `create_all` for schema changes.
- **Secrets**: `pydantic-settings` `Settings` class reading from `.env` (git-ignored),
  with `.env.example` committed. No secret ever hardcoded in source again.
- **File storage**: uploaded originals go to `uploads/<dataset_id>/...` on disk (or S3-
  compatible later) with a DB row holding metadata + checksum — never as DB blobs.
- **Large datasets**: paginated repository queries, DB-side aggregation for dashboards,
  background jobs for heavy processing (profiling, anomaly scans) — not synchronous
  request handlers.
- **RBAC**: centralized `require_role(*roles)` FastAPI dependency; roles are the six in
  `roles.py` today, extendable later; enforced server-side on every non-public route.

## 4. What this document deliberately does not do

It does not invent scoring weights, penalty formulas, or organizational level names beyond
the six already named in `roles.py` — those must come from the user or from the uploaded
data, per the brief's explicit "do not invent" instructions. Anywhere a number would have
to be invented, the architecture instead exposes it as **configuration**.

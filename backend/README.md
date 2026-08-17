# CARVMS Backend

FastAPI + SQLAlchemy + SQLite (dev) backend. See `../docs/CARVMS_ARCHITECTURE.md` for the
full picture; this file is just setup/migration/test instructions.

## Setup

```bash
cd backend
python -m venv venv
./venv/Scripts/activate        # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
# edit .env and set a real SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Migrations (Alembic)

Schema is managed by Alembic — never by `Base.metadata.create_all()`. Before running any
migration against real data, back it up:

```bash
cp carvms.db "_backups/carvms.db.bak.$(date +%Y%m%d%H%M%S)"
alembic upgrade head
```

To add a new migration after changing a model in `app/models/`:

```bash
alembic revision --autogenerate -m "describe the change"
```

**Always read the generated migration before running it.** Autogenerate cannot detect
column renames (it will propose a drop+add, which loses data) and cannot safely convert
data between incompatible types (e.g. a string `'Yes'/'No'` column to `Boolean` — it will
happily copy the literal string, which then reads back as truthy for every non-empty
value). Hand-edit generated migrations for renames and type changes; see
`alembic/versions/96117c6836ee_align_users_table_with_target_schema.py` for a worked
example of both.

```bash
alembic upgrade head       # apply
alembic downgrade -1       # roll back one revision
```

## Running

```bash
uvicorn main:app --reload
```

- `GET /` and `GET /health` — public.
- `POST /auth/register`, `POST /auth/login` — public.
- Everything else requires `Authorization: Bearer <token>`.
- Swagger UI: `http://localhost:8000/docs`.

Routers registered (see `main.py`): `auth`, `users` (admin-only management), `org`
(hierarchy dimensions/nodes), `audits` (+ nested findings), `evidence`, `datasets`,
`dashboard` (Metric Engine summary), `reports` (CSV/Excel/PDF export — all three call the
same Metric Engine functions the dashboard uses, see `app/services/metrics.py`),
`penalties` (penalty rules, propose/decide, recoveries), `reconciliations` (dataset vs.
dataset), `anomalies` (forensic scan/dismiss/escalate over a dataset), `report_templates`
(saved filter sets + `/report-history` + regenerate-from-history — all routed through the
same export renderers as `reports`), `search` (`GET /search` across audits/findings/org
nodes/datasets/templates/penalty rules, RBAC-scoped the same way audit listing is),
`dashboard_layouts` (saved KPI/chart visibility + default filters, private or shared),
`center_scoring` (relative center performance ranking — admin-editable weights, default
equal, over financial exposure/recovery rate/open findings/repeat findings, min-max
normalized so nothing is fabricated), `email` (Gmail OAuth connect/status/disconnect --
state-token CSRF flow, tokens Fernet-encrypted at rest, runs fine unconfigured and just
reports "not configured" until `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are set -- see
`../docs/EMAIL_SETUP.md`).

**If you're running the dev server across a long session and add a new router**, restart
it — a long-lived `uvicorn` process will keep serving the old route table even after
`main.py` changes on disk, and every new endpoint 404s until it's restarted. **`--reload`
is not reliable insurance for this** — it has been observed printing
`StatReload detected changes ... Reloading...` while never actually starting a new
worker process, silently leaving the same stale PID serving requests. Passing tests do
not catch either failure mode, since each test run imports the app fresh — only a live
process can go stale this way. After any router change, verify with a real request
(a 401/200, not a 404) rather than trusting the reload log line.

## Tests

```bash
pytest tests/ -v
```

Tests run against a throwaway SQLite file (`test_carvms.db`, created via `create_all` and
dropped after every test) — they never touch the real `carvms.db`. The `get_db` FastAPI
dependency is overridden in `tests/conftest.py` to point at the test database.

## Known limitations (see `../docs/CARVMS_COMPLETION_REPORT.md` for the current list)

Auth, RBAC + audit trail, org hierarchy, audit/finding/evidence, dataset upload +
profiling, Metric Engine (dashboard + CSV/Excel/PDF export, proven consistent),
penalty/recovery, dataset reconciliation, forensic anomaly detection, report
templates/history, global search, customizable/saved dashboard layouts, center
performance scoring (relative, admin-editable weights — starts equal per the user's own
choice), and Gmail OAuth connection scaffolding are all built and tested (140/140) — with
a working frontend covering all of it, verified in a live browser with real accounts,
including the full email connect→callback→status/disconnect redirect chain (against a
deliberately-invalid state token, since a real round trip needs a real Google OAuth app —
see `../docs/EMAIL_SETUP.md`). Automation beyond the OAuth connection itself (actually
reading/acting on email) and the AI Analyst are not built yet — see
`../docs/CARVMS_IMPLEMENTATION_PLAN.md` for the backlog.

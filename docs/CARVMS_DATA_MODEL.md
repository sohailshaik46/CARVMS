# CARVMS — Data Model

> **Status (2026-08-13): all P1 tables below, plus §2.5 penalty_rules/penalties/
> recoveries, plus tables not in this doc's original sketch — `reconciliations`,
> `dataset_anomalies`, `report_templates`, `report_history`, `dashboard_layouts`,
> `center_scoring_weights`, `email_connection_requests`, and `email_connections`
> (see the corresponding `app/models/*.py`) — are built, migrated, and tested against
> the real `carvms.db`.** 20 tables total, 13 migrations applied in sequence, verified
> against the original single admin row surviving every one of them (including two
> migrations that were hand-corrected before applying — one for an unnamed-FK/SQLite
> batch-mode issue, one for a single-element-tuple `CHECK IN (...)` syntax error — see
> `CARVMS_COMPLETION_REPORT.md`). §3's remaining deferred entities (anything that
> actually reads/acts on connected email, i.e. automation-execution tables) are still
> not started. See `CARVMS_COMPLETION_REPORT.md` for verified detail.

Status: reflects the **actual current schema** (one table) plus the target model. Entities
are only added when a concrete requirement in the brief needs them — per the brief's own
instruction ("do not create all tables blindly"), this is not the full 20-table list from
§38 of the brief; it is the subset actually justified by scoped, near-term requirements.

## 1. Current schema (verified from `backend/app/models/user.py`)

```text
users
  id            INTEGER PK
  username      VARCHAR UNIQUE NOT NULL
  email         VARCHAR UNIQUE NOT NULL
  password      VARCHAR NOT NULL        -- bcrypt hash
  role          VARCHAR NOT NULL DEFAULT 'Auditor'
  is_active     VARCHAR DEFAULT 'Yes'   -- BUG: string, not boolean; not checked at login
```

One real row exists: `admin / admin@gmail.com / role=Admin`. Preserved via migration, not
recreated.

## 2. Target model — P0/P1 scope only

### 2.1 `users` (migrated)

```text
users
  id            INTEGER PK
  username      VARCHAR UNIQUE NOT NULL
  email         VARCHAR UNIQUE NOT NULL
  password_hash VARCHAR NOT NULL
  role          VARCHAR NOT NULL DEFAULT 'Auditor'   -- CHECK constraint: one of the 6 roles
  is_active     BOOLEAN NOT NULL DEFAULT TRUE         -- fixed type
  created_at    DATETIME(tz) NOT NULL
  updated_at    DATETIME(tz) NOT NULL
```

Migration path (Alembic): add new typed columns, backfill `is_active` from the old
string ('Yes'→true, else false), backfill `created_at`/`updated_at` to "now" for existing
rows, then drop the old string column. Backed up to `backend/_backups/` before running.

### 2.2 Org hierarchy (dynamic — P1)

```text
org_dimensions
  id            INTEGER PK
  key           VARCHAR UNIQUE   -- e.g. "zone", "cluster", "region", custom names allowed
  label         VARCHAR
  sort_order    INTEGER

org_nodes
  id              INTEGER PK
  dimension_id    FK org_dimensions
  parent_id       FK org_nodes NULLABLE   -- self-referencing, arbitrary depth
  name            VARCHAR
  external_code   VARCHAR NULLABLE        -- code from source data, for reconciliation
```

Default seed = Zone → Cluster → Region → Zonal Manager → Regional Manager → Center →
Employee, but editable; a data-profiling job may add/replace dimensions detected from an
uploaded file's columns.

### 2.3 Datasets (P1 — upload/dataset management)

```text
datasets
  id              INTEGER PK
  name            VARCHAR
  source_type     VARCHAR   -- excel/csv/pdf/word/pptx/image
  original_path   VARCHAR   -- on-disk path under uploads/
  checksum        VARCHAR
  uploaded_by     FK users
  uploaded_at     DATETIME(tz)
  version         INTEGER
  status          VARCHAR   -- uploaded/profiling/clean/failed/archived
  row_count       INTEGER NULLABLE
  column_count    INTEGER NULLABLE
  quality_score   FLOAT NULLABLE
  lineage_of      FK datasets NULLABLE   -- previous version, if a re-upload

dataset_columns
  id              INTEGER PK
  dataset_id      FK datasets
  name            VARCHAR
  inferred_type   VARCHAR
  mapped_dimension VARCHAR NULLABLE  -- e.g. "zone" if auto-mapped to org_dimensions.key
```

### 2.4 Audit / Finding (P1 — forensic core)

```text
audits
  id              INTEGER PK
  audit_number    VARCHAR UNIQUE
  title           VARCHAR
  type            VARCHAR
  status          VARCHAR  -- Draft/Assigned/In Progress/Under Review/Action Required/Closed/Cancelled
  priority        VARCHAR
  center_node_id  FK org_nodes NULLABLE
  assigned_to     FK users NULLABLE
  opened_at       DATETIME(tz)
  due_at          DATETIME(tz) NULLABLE
  closed_at       DATETIME(tz) NULLABLE
  created_by      FK users
  created_at / updated_at

findings
  id                  INTEGER PK
  audit_id            FK audits
  finding_number      VARCHAR
  category            VARCHAR      -- configurable list, see Automation Roadmap
  severity            VARCHAR      -- Low/Medium/High/Critical
  description         TEXT
  financial_exposure  DECIMAL NULLABLE
  recoverable_amount  DECIMAL NULLABLE
  status              VARCHAR
  owner               FK users NULLABLE
  due_at              DATETIME(tz) NULLABLE
  created_by          FK users
  created_at / updated_at

evidence
  id              INTEGER PK
  audit_id        FK audits NULLABLE
  finding_id      FK findings NULLABLE
  original_filename VARCHAR
  mime_type       VARCHAR
  size_bytes      INTEGER
  checksum        VARCHAR
  storage_path    VARCHAR       -- under uploads/, never a DB blob
  uploaded_by     FK users
  uploaded_at     DATETIME(tz)
```

### 2.5 Penalty / Recovery (P1)

```text
penalty_rules
  id            INTEGER PK
  code          VARCHAR UNIQUE
  description   VARCHAR
  formula_config JSON       -- explicit, admin-editable — never hardcoded weights
  effective_from / effective_to
  created_by    FK users

penalties
  id              INTEGER PK
  finding_id      FK findings
  rule_id         FK penalty_rules
  base_amount     DECIMAL
  penalty_amount  DECIMAL
  approved_by     FK users NULLABLE
  approved_at     DATETIME(tz) NULLABLE
  status          VARCHAR   -- Proposed/Approved/Rejected/Recovered

recoveries
  id              INTEGER PK
  penalty_id      FK penalties
  amount          DECIMAL
  reference       VARCHAR
  recorded_by     FK users
  recorded_at     DATETIME(tz)
```

### 2.6 Audit trail (P0/P1 — governance)

```text
audit_logs
  id            INTEGER PK
  actor_id      FK users NULLABLE
  action        VARCHAR
  entity_type   VARCHAR
  entity_id     VARCHAR
  before_json   JSON NULLABLE
  after_json    JSON NULLABLE
  correlation_id VARCHAR NULLABLE
  created_at    DATETIME(tz)
```
Immutable: no UPDATE/DELETE endpoint is ever exposed for this table.

## 3. Explicitly deferred (P3 — not modeled yet)

Report templates/history, dashboard layouts, center-performance-score configuration, and
the email OAuth *connection* itself are no longer deferred — see §0's status banner and
`app/models/report.py`, `dashboard_layout.py`, `center_scoring.py`, `email_connection.py`.
Still deferred: tables for anything that actually *uses* a connected email account (e.g.
reading messages, sending automated reports) and automation job/run tables — these are
real requirements but need the connection scaffolding above to exist first, which it now
does. They are scoped in `CARVMS_AUTOMATION_ROADMAP.md` and will get their own data-model
addendum when their phase starts.

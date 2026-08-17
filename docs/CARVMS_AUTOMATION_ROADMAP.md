# CARVMS — Automation Roadmap

This is the "automation opportunity" register the brief asks for (§34). It is populated
honestly against the current state (an auth skeleton) — most rows are near-term proposals,
not automations already built. Each entry follows the required shape.

## Guardrail (applies to every row below)

```text
AI/Automation Recommendation → Human Review → Approval → Execution
```
No row in this roadmap authorizes autonomous execution of: sending email, deleting data,
publishing a report, approving a penalty, closing an audit, or changing scoring rules.
Every one of those remains a human-confirmed action per the brief's §24/§35.

## Register

### A1 — Monthly center ranking report
- Current manual process: someone compiles center metrics by hand into Excel monthly.
- Proposed automation: scheduled job computes ranking via Metric Engine, generates the
  report via Report Factory, stops at a **draft** state pending human approval to send.
- Inputs: dataset(s) for the period, scoring weights (configured, not invented).
- Outputs: ranked report (Excel/PDF), a queued (not sent) email draft.
- Dependencies: P1 org hierarchy + Metric Engine, P2 Report Factory + scoring engine.
- Priority: P2. Estimated saving: not claimed until the manual baseline is measured with
  the user — no time-saving number is invented here.

### A2 — Daily exception monitoring
- Current manual process: none exists today (no anomaly detection exists yet).
- Proposed automation: on new dataset upload, run configured anomaly rules, create
  "Exception"/"Red Flag" records requiring human verification — never an auto-conclusion
  of fraud.
- Dependencies: P1 datasets + audit/finding model, P2 forensic rule set.
- Priority: P2.

### A3 — Recurring/"repeatative" center detection
- Current manual process: none exists today.
- Proposed automation: configurable rule (e.g. "≥N findings of category X in Y months")
  computed via Metric Engine, surfaced on the dashboard and in reports.
- Dependency: the threshold N/Y is a configuration value, not invented by the system.
- Priority: P2.

### A4 — Monthly management report + email
- Current manual process: none exists today.
- Proposed automation: Automation Engine job → generate management report → present
  recipient suggestions (never auto-populated/sent) → human selects To/CC/BCC → confirm →
  send → audit log entry.
- Dependencies: P2 email integration + Report Factory. **Update (2026-08-13):** the
  Gmail OAuth *connection* scaffolding is now built and tested (state-token flow,
  encrypted token storage, connect/status/disconnect) — see
  `app/services/email_connection_service.py` and `docs/EMAIL_SETUP.md`. What remains is
  (a) a real Google Cloud OAuth app registered by the user/an administrator (external
  setup, not engineering — the agent must never generate or see that credential), and
  (b) building the actual send step on top of the now-existing connection.
- Priority: P2/P3 boundary (the send step itself is still not built; the OAuth
  credential blocker is now scoped down to "register a real Google app," not "the
  connection mechanism doesn't exist").

### A5 — AI-assisted natural-language reporting
- Current manual process: none exists today.
- Proposed automation: "Generate a PDF report for South Zone" type commands resolved
  against the Metric Engine/Report Builder, always ending in a review step before export
  or send.
- Dependency: P1/P2 metric + report layers must be stable first (see sequencing rationale
  in the Implementation Plan).
- Priority: P3.

## What will not be automated (by design)

Per §35 of the brief: final fraud/misconduct conclusions, disciplinary decisions, penalty
approval, audit closure, scoring-rule changes, deletions, and email sends always require
a named human approver recorded in `audit_logs`. Automation ends at "recommendation."

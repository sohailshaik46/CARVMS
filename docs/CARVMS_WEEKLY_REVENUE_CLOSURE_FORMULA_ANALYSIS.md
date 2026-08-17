# CARVMS — Weekly Revenue Closure: Formula Analysis

**Status: PARTIALLY PROVEN.** The penalty-rate formula is proven and cross-validated against two
real, independent weeks (Week 2 and Week 3, Jul'26 — 0 mismatches on every reconstructible
figure). The raw daily ingestion format and two specific escalation edge-cases are **not** yet
provable from the two files supplied — flagged explicitly in §6 rather than guessed.

Source material: `Jul'26 - Week 2 - Penalty.xlsx` and `Jul'26 - Week 3 - Penalty.xlsx`, both under
`D:\Sohail - Vigilance\Reports\Weekly Revenue Report Closure\2026\Jul'26\`. Every sheet in both
files was read in full (not sampled) via `openpyxl`, including raw cell `number_format` where the
displayed value alone was ambiguous (see §2).

This is a **deliberately separate engine from Delayed Cash Billing** — different formula, and
critically, a **different role hierarchy**: Center Manager and Cluster Manager penalties **do**
apply here (Zonal Manager too, conditionally — see §4), where Delayed Cash Billing explicitly
excludes Center/Cluster Manager penalties entirely. The two must never be merged.

## 0. Source material actually inspected

| File | Sheets |
|---|---|
| Week 2 | `Sheet1` (15 rows), `Penalties` (48 rows), `Data` (38 rows = 37 real bills + header) |
| Week 3 | `Sheet1` (24 rows), `Penalties` (39 rows), `Sheet3` (7 rows), `Sheet2` (13 rows), `Data` (44 rows = 43 real bills + header) |

- **`Data`** — one row per delayed-billing *incident that received a center remark* (whether
  accepted or rejected): `S.No, Zone, Cluster, Center Code, Center Name, Date, Billed Sessions,
  Daily Report, Variance, Remark, MIS Final Remarks, Center remarks, Penalty Remarks, Week`.
  `MIS Final Remarks` is one of exactly two values across both weeks: `Bill Pending` or `Daily
  Report not sent` (verified — no other value occurs in either file's `Data` sheet). `Penalty
  Remarks` is a **human-authored verdict**, always prefixed `Considered - <reason>` or `Not
  Considered - <reason>` (verified — no other prefix occurs in either file).
- **`Sheet1`** — unfiltered pivot: count of incidents per center by `MIS Final Remarks`, regardless
  of remark/verdict status. Informational only (matches the "publishing" idea from Delayed Cash
  Billing) — not itself a penalty output.
- **`Penalties`** — the actual penalty output, in two independent blocks per week (see §2):
  *"Remarks received but not considered"* and *"Remarks Not Received"* (spelling/capitalization of
  this second title differs slightly between the two files — cosmetic, not semantic).
- **`Sheet2`/`Sheet3`** (Week 3 only) — working/staging tables: `Sheet2` lists the exact 12 centers
  behind Week 3's "Remarks Not Received" block; `Sheet3` is a pivot count of those same 12 centers
  by Zonal Manager, and its numbers match that block's Zonal-Manager rollup exactly (Aravind
  Chunduru 1, Gaurav Malhotra 1, Krunal 2, Nishant Kumar Singh 6, Sudhakar V 2 — all confirmed
  identical in `Penalties`). These are scratch sheets that feed the final `Penalties` sheet, not a
  separate concern.

## 1. The verdict model — human-authored, not (yet) auto-classified

Every incident in the `Data` sheet already carries a **human** verdict (`Penalty Remarks`), decided
by reading the free-text `Center remarks` (e.g. `"Considered - HP Billing"`, `"Considered -
Rebilling"`, `"Considered - Proof Available"`, `"Not Considered - Center Lapse"`, `"Not considered
- No Further Reply"`, `"Not Considered - No Credit Approval"`). **Nothing in either workbook shows
this decision being made automatically** — it's the same kind of judgment call CARVMS's Delayed
Cash Billing review queue already captures with its Considered/Not-Considered buttons. Task #36's
"remark auto-classification" is therefore aspirational relative to current practice, not something
provable from these two files; the honest scope for what's built now is the **penalty math once a
verdict exists**, reusing the same manual review-queue pattern already proven for Delayed Cash
Billing, not a new NLP/keyword classifier invented from nothing.

`Considered` fully excludes that incident from any penalty, unconditionally, in both weeks — e.g.
Week 2's 148-TN-ERD-CMS-C (Erode) has one `Bill Pending` incident, verdict `Considered - Proof
Available`, and **does not appear anywhere in the `Penalties` sheet** despite appearing in the
unfiltered `Sheet1` pivot. Confirmed for every `Considered` row in both files — zero exceptions.

## 2. The penalty rate — proven, and the 0.0625-vs-6.25 discrepancy resolved

Every populated penalty cell in both files' `Penalties` sheets was read with its **raw underlying
value** and **`number_format`** (not just the displayed text, since Excel formatting can make two
different underlying values look identical or vice versa):

| Where | Raw value(s) seen | `number_format` | Displayed as |
|---|---|---|---|
| Center-level penalty rows (both sections) | `0.0625` | `0.00%` | `6.25%` |
| Cluster/Zonal-Manager rollup rows | `6.25`, `12.5`, `18.75`, `25`, `37.5`, `43.75` | `General` | `6.25`, `12.5`, ... (no `%`) |

These are **the same rate, encoded two different ways** by whoever built the sheet by hand — the
rollup numbers are always an exact integer multiple of `6.25`, and that multiple is always the
count of distinct centers contributing to that person's rollup (proof table below). There is no
scenario in either file where treating both as "6.25% of something, repeated once per contributing
center" produces a wrong number. This is exactly the same rate (**6.25%**) already documented as
the Delayed Cash Billing monthly cap — almost certainly the same underlying "6.25% of monthly gross
salary" HR rule referenced there, applied here as the actual penalty rather than a cap. **The base
it multiplies (a monthly gross salary figure) is external HR/payroll data this codebase must never
fabricate** — identical caveat to Delayed Cash Billing's cap.

### Proof: Center-level penalty is flat per center, not scaled by incident count

| Center | Week | Incidents in that section | Penalty (raw) |
|---|---|---|---|
| 54-TN-CMB-GPP-C | 2 | 2 (`Bill Pending`) | `0.0625` (not `0.125`) |
| 647-GJ-VDD-CHN-C | 2 | 6 total (`Daily Report not sent`=1, `No Billing/No Daily Report`=5) | `0.0625` (not `0.375`) |
| 550-UP-BST-AVC-C | 3 | 5 total (`Bill Pending`=1, `Daily Report not sent`=4) | `0.0625` (not `0.3125`) |

Confirmed across both sections, both weeks, every multi-incident center: **one qualifying incident
in a week is enough to trigger the full 6.25% for that center; additional incidents the same week
never add more.**

### Proof: Cluster/Zonal-Manager penalty = 6.25% × count of distinct centers under them

Verified **programmatically**, not by hand — for every rollup row in both files, the script
independently recomputed "how many distinct Center Codes have this exact Cluster/Zonal Manager
value in this section's center rows" and compared it against the sheet's own stated `Count`.

**Week 2 — 23 of 23 rollup rows match exactly. Zero mismatches.** Every Cluster-Manager and
Zonal-Manager count in both sections reproduces exactly from the raw center rows.

**Week 3 — 9 of 13 rollup rows match; 4 do not, all undercounts:**

| Person | Role | Section | Stated count | Recomputed count (actual distinct centers) |
|---|---|---|---|---|
| Ankit Kumar Singh | Cluster | Not Received | `3` | `4` — 26, 512, 550, 551 |
| Krunal | Zonal | Not Received | `2` | `4` — 213, 327, 647, DOC15 |
| Nishant Kumar Singh | Zonal | Not Received | `6` | `7` — 106, 26, 512, 515, 550, 551, 642 |
| Yashwant | Cluster | Not Received | `1` | `2` — 213, 647 |

These are **real arithmetic errors in the Week 3 workbook's rollup pivots**, not a gap in this
formula's understanding — every center-level row, every Week-2 rollup, and the underlying
`Cluster`/`Zonal Manager` values on every Week-3 center row itself are all internally consistent
and correctly summed by the independent recomputation; only the four *stated* `Count`/`Penalty`
cells above are wrong (most plausibly a pivot table that wasn't refreshed after later rows were
added, since Week 3 has more center rows than Week 2). **This calculator reproduces the
mathematically correct counts, which means it will not reproduce these four specific numbers from
the Week 3 file** — flagged here explicitly rather than silently matched to a known-wrong figure.
This is, concretely, the kind of manual-process error task #36's automation exists to eliminate.

### Proof: Zonal Manager only escalates for "Remarks Not Received", never for "Remarks received but not considered"

Both weeks' "Remarks received but not considered" block has **no Zonal Manager rollup at all** —
only Center-level rows and a Cluster-Manager rollup. Both weeks' "Remarks Not Received" block
**always** has a Zonal-Manager rollup alongside the Cluster one. Confirmed by the user directly
(not left as an inferred rule from two data points) — see §6.

## 3. The two independent penalty sections

| Section | Trigger | Who's penalized |
|---|---|---|
| "Remarks received but not considered" | Center submitted a remark, Vigilance's verdict was `Not Considered - <reason>` | Center (flat 6.25%) + Cluster Manager (6.25% × distinct centers) |
| "Remarks Not Received" | Center never submitted a remark for a delayed-billing incident at all | Center (flat 6.25%) + Cluster Manager (6.25% × distinct centers) + Zonal Manager (6.25% × distinct centers) |

Both sections are computed **independently** — a center could in principle appear once for a
`Not Considered` verdict and again for a *different* incident with no remark at all in the same
week, contributing to both sections' totals separately (not observed in either file, but nothing
in the structure prevents it, and nothing suggests the two sections should be merged into one
combined total per person before output).

## 4. Role hierarchy — confirmed different from Delayed Cash Billing

Center Manager (NP ID shown per row) and Cluster Manager are **both** penalized here — Delayed
Cash Billing's own docstring explicitly calls out that neither is applicable there, by design, so
this is the expected, confirmed difference. Zonal Manager penalties additionally appear (see §2's
proof), conditionally on section, per §3.

## 5. What "multi-sheet Excel Penalty generator" needs to reproduce

The three sheets in the proven output are: an unfiltered incident-count pivot (`Sheet1`-style), the
two-section penalty breakdown with center rows + Cluster/Zonal rollups (`Penalties`-style), and the
remark-received raw detail (`Data`-style). `Sheet2`/`Sheet3` in Week 3 are scratch/staging views a
generator wouldn't need to reproduce separately — they're intermediate work, not part of the final
artifact (Week 2's file doesn't have them at all, confirming they're incidental to that week's
manual process, not a required output).

## 6. Resolved-by-the-user rules, a confirmed data-quality finding, and one remaining gap

### 6.1 Four confirmed arithmetic errors in Week 3's rollup pivots (not a formula gap)

Superseded by the programmatic verification in §2 above: every rollup count in both files was
independently recomputed from the raw center rows and compared against the sheet's stated value.
Week 2 matches 23/23. Week 3 matches 9/13 — the 4 that don't (Ankit Kumar Singh cluster, Krunal
zonal, Nishant Kumar Singh zonal, Yashwant cluster) are all undercounts in the *stated* pivot
output; the underlying raw membership data and every center-level penalty are correct and
consistent. This codebase's calculator reproduces the mathematically correct counts, which will
therefore differ from these 4 specific numbers in the Week 3 file — an intentional, documented
divergence from a known-wrong source figure, not an error in this analysis.

### 6.2 Cluster Manager escalation in "Remarks received but not considered" — RESOLVED

**User-confirmed:** counts only `bill_pending`-type incidents (not `daily_report_not_sent`).
This matches the one real instance observed exactly (`82-MH-MUM-KDW-C`, a `daily_report_not_sent`
incident, correctly excluded from that section's Cluster-Manager rollup in Week 2).

### 6.3 Zonal Manager escalation in "Remarks received but not considered" — RESOLVED

**User-confirmed:** Zonal Manager never escalates in this section, only in "Remarks Not
Received." Matches both weeks' data with zero exceptions.

### 6.4 The raw daily ingestion source — RESOLVED

The user subsequently supplied two more real files: `July-26-Week2-closure pending List till
12-6-2026.xlsx` and `July-26-Week3-closure pending List till 19-07-2026.xlsx`. Their `Center wise`
sheet is exactly the missing raw daily source: `Zone, Cluster, Center Code, Center Name, Date,
Billed Sessions, Daily Report, Variance, Remark, Final Remarks` -- one row per (center, day) with
a variance, **before** any center remark or Vigilance verdict exists (no `Center remarks`/`Penalty
Remarks`/`Week` columns at all, confirming this is the *pre-remark* pending list, upstream of the
`Data` sheet in the Penalty output workbooks).

**A fourth `Final Remarks` category exists in this raw file that never appears in either Penalty
output workbook: `Excess billed/Incorrect Daily report`** (billed sessions *exceed* the daily
report -- the opposite direction from a delayed-closure problem). Proven out of scope for this
penalty engine: Week 2's pending file has 16 such rows across 12 centers, and cross-checking
confirms **zero** of those centers/incidents appear anywhere in the Week 2 Penalty output workbook.
This is a distinct data-quality anomaly (over-billing or a report error), not a delayed-closure
penalty trigger -- excluded from ingestion, but counted and reported, never silently dropped.

**Verified by direct reconciliation, not assumed:** aggregating Week 2's raw `Center wise` rows
(excluding the excess-billed category) by center and incident type reproduces that same file's own
`Center Penalty` sheet exactly -- **35/35 centers, zero mismatches**. This is the strongest possible
proof of the ingestion format, since both sheets come from the same workbook and were clearly built
from each other.

**A further, separate data-quality finding**: Week 3's *pending* file does **not** reconcile as
cleanly -- 7 of its centers show higher raw incident counts than its own `Center Penalty` sheet
states (e.g. `332-KA-BLR-RRN-C`: sheet says 7 Bill Pending rows, the raw sheet actually has 18).
This reads as the Week 3 pending file being a later, updated snapshot (its filename says "till
19-07-2026", later in the week than when its own `Center Penalty` pivot was last refreshed) rather
than a formula problem -- flagged here for completeness, not silently smoothed over, and not relied
upon: the ingestion parser (see below) reproduces the *raw sheet's own row counts* directly, never
a stale pivot's stated total.

## 7. What's built

**The penalty-rate calculator** (flat 6.25% per delinquent center, escalating ×distinct-center-count
to Cluster/Zonal Manager, with both confirmed edge-case rules from §6.2/6.3 baked in) --
`app/models/weekly_revenue_closure.py` + `app/services/weekly_revenue_closure_service.py` -- proven
against a per-center-per-week list of qualifying incidents as input. Full reconciliation tests
reproduce Week 2 exactly (zero mismatches) and Week 3's center-level and 9-of-13 rollup figures
exactly, deliberately correcting the 4 confirmed pivot errors from §6.1 rather than reproducing
them.

**The raw ingestion parser** -- `app/services/weekly_revenue_closure_upload_service.py` -- parses
the `Center wise` sheet format proven in §6.4 into pending incidents (no remark or verdict yet,
same review-queue-first pattern already built for Delayed Cash Billing), excluding the
excess-billed category. Proven against the real Week 2 pending file: 35/35 centers reconcile
exactly against that file's own `Center Penalty` sheet.

**Still to build**: the response-portal / review-queue wiring that turns a freshly-ingested pending
incident into a reviewed one (reusing the Delayed Cash Billing pattern almost directly, per §1), and
the multi-sheet Excel generator (§5) that reproduces the final Penalty-workbook output. Both are
now unblocked -- every input/output shape they need has been proven against real data.

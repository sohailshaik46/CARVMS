# CARVMS — Delayed Cash Billing Penalty: Formula Analysis

**Status: FORMULA PROVEN. Zero mismatches across all 93 centers / 585 bills / ₹137,900.**

This document reverse-engineers the Delayed Cash Billing penalty calculation from the
reference workbook the user supplied — `Delayed Cash Billing Data - 1st Jul'26 - 31st
jul'26 - Remarks & Penalties.xlsx` — and mathematically proves the derived formula
against every row in it before any code is written, per the explicit instruction not to
assume `penalty = day_difference × ₹100` without proof. **The proof happens to land on
that exact expression, but it was derived from the data, not assumed** — see §7 for why
this is not the same thing as guessing it.

## 0. Source material actually inspected

The workbook has 5 sheets, all read in full (not sampled):

| Sheet | Rows × Cols | Role |
|---|---|---|
| `Bills Data` | 586×9 (585 bills + header) | **Raw source of truth** — one row per delayed bill: `CENTREID, CENTRENAME, SALESBILL, BILLDATE, bill_created_time, created_date, day_difference, Center Remarks, Penalty Remarks` |
| `Sheet2` | 98×28 | Pivot: count of bills per (center × day_difference), **unfiltered** — i.e. every bill, matches `Bills Data` grouped |
| `Sheet1` | 68×24 | Pivot: count of bills per (center × day_difference), **filtered to exclude bills whose `Penalty Remarks` starts with "Considered"** |
| `Penalty Data` | 96×58 | Per-center: bucket counts (unfiltered) + `Total` + `Penalty` (**this is the reference publishing-penalty output**) + a second, unlabeled block of per-bucket ₹ amounts |
| `Final penalty` | 65×30 | Per-center: bucket counts (filtered, matches `Sheet1`) + a constant `0.0625` in the last column — the **6.25% cap rate**, not an amount |

The reference figures the user quoted in chat (Khemnichak ₹2,200, Coimbatore ₹15,800,
Waghodia ₹13,900, etc., and the 585-bill/₹137,900 grand total) all come directly from the
`Penalty Data` sheet's `Total`/`Penalty` columns — they were not re-typed or approximated.

The Weekly Revenue Report Closure workbook was inspected earlier this session for the
separate CAPS/6.25%-of-gross-salary flow and is **not** the source for this formula —
per the user's explicit instruction (§20 of their requirement), these are two different
calculation engines and this document only touches the delayed-cash one.

## 1. Delay buckets present in the reference data

Every distinct `day_difference` value actually occurring across the 585 bills:

```
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 21, 25, 27, 28, 29, 34
```

(25 distinct values; note 19, 22, 23, 24, 26, 30–33 never occur in this month's data —
their absence is a data fact, not evidence of a cap or a gap in the rule.)

## 2. The penalty rate per bucket

Cross-referencing the `Penalty Data` sheet's own unlabeled second block of columns
(positions 33–57, which align 1:1 with the bucket-count columns at positions 5–29)
against the bucket counts, for every row with a non-zero bucket:

| day_difference | rate per bill | evidence (Khemnichak row) |
|---|---|---|
| 1 | ₹100 | count=16, amount=1600 → 1600/16 = 100 |
| 2 | ₹200 | count=1, amount=200 → 200/1 = 200 |
| 4 | ₹400 | count=1, amount=400 → 400/1 = 400 |

i.e. **rate(day_difference) = day_difference × ₹100**, with no exceptions found in any
row of the sheet's own amount columns. This is the workbook's *own* internal
cross-check, independent of the raw `Bills Data` sheet.

## 3. The exact formula

```
per_bill_penalty(bill)  = bill.day_difference × 100
publishing_penalty(center) = Σ per_bill_penalty(bill)  for every delayed bill at that
                              center in the period — ALL bills, regardless of
                              "Considered"/"Not Considered" remark status
```

## 4. Classification

- **Per bill** — every individual delayed bill contributes its own amount; nothing is
  deduplicated or bucketed-then-flattened.
- **Linear / proportional**, not slab-based or progressive — there is no tier where, say,
  "day 1–3 = flat ₹300" or "day 4+ = double rate." Rate scales exactly linearly with
  `day_difference` at ₹100/day, confirmed from day 1 through the maximum observed (day
  34, see §6).
- **Cumulative** — a center's total penalty is the sum of every one of its bills' amounts
  for the period; there is no cap applied at this (publishing) stage.
- **Not capped at publishing** — see §6, the day-34 case reproduces exactly with no
  ceiling applied.
- **day_difference values do have different amounts** (₹100, ₹200, ₹300, ...) — but the
  *mechanism* generating those different amounts is one linear formula, not a lookup
  table of independently-set slab values. This matters for the implementation: it's one
  multiplication, not a 34-row configuration table (though the calculator should still
  be built as configurable — see §9 — in case the rate itself changes in future).
- **Thresholds**: none found. No breakpoint where the per-day rate changes.
- **Multiple delayed bills**: summed individually, per bill, not per bucket and not
  deduplicated by center or by day.
- **Total column** = the plain count of that center's delayed bills for the period
  (sum of the bucket-count columns), **unfiltered** by remark status.

## 5. Publishing penalty vs. final closed penalty — two genuinely different numbers

This is the single most important structural finding, and it is why a naive
`day_difference × 100` read of the brief would have been *right* for the publishing
stage and *wrong* if applied unmodified to the final closed stage.

**Stage A — Publishing (`Penalty Data` sheet):** computed from **every** delayed bill,
regardless of what the center's remark says. Confirmed directly: Khemnichak has 3 bills
whose `Penalty Remarks` start with "Considered" (an accepted exception — 2 at day 1, 1 at
day 2), yet the publishing total of 18 bills / ₹2,200 **includes** those 3 bills. The
`Considered`/`Not Considered` verdict has zero effect on the number shown while
publishing.

**Stage B — Final closed penalty (`Final penalty` sheet):** two changes are visible:

1. **Exclusion.** The bucket counts in `Final penalty` match `Sheet1` (the
   `Not Considered`-only pivot), not `Sheet2`/`Penalty Data` (the unfiltered pivot).
   Khemnichak's day-1 bucket drops from 16 (publishing) to 14 (final) — exactly the 2
   accepted day-1 exceptions removed. Recomputing `day_difference × 100` over only the
   surviving (`Not Considered`) bills gives what this document calls
   `validated_penalty`.
2. **Cap.** Every row in `Final penalty` carries the constant `0.0625` in its trailing
   numeric column — i.e. **6.25%**, a *rate*, not a rupee amount. This is the "MONTHLY
   CAP = 6.25%" the user described. **The workbook does not contain any salary figure**
   — the 10%-of-gross-salary component this rate applies against lives in
   HR/payroll data outside these files (the same external dependency already
   documented for the separate Weekly Revenue Closure CAPS formula). So:

   ```
   validated_penalty(center)  = Σ day_difference × 100   over Not-Considered bills only
   monthly_cap_amount(person) = 0.0625 × monthly_gross_salary_component(person)   ← EXTERNAL, not in these files
   final_penalty(center)      = MIN(validated_penalty, monthly_cap_amount)
   ```

   This is flagged as a **data dependency, not a formula ambiguity** — the *rate*
   (6.25%) is proven and unambiguous; the *base it applies to* is a real external input
   this codebase must accept as configuration (see §9), never invent.

## 6. Proof there is no cap at the publishing stage

The highest single delay in the dataset is 34 days (₹3,400 for that one bill). The
center with the most extreme distribution — Gandak Chowk, Birgunj (`515-NL-BGR-GDK-C`) —
has exactly 6 bills at days 13, 20, 27, 28, 29, 34:

```
13+20+27+28+29+34 = 151 days → 151 × ₹100 = ₹15,100
```

Reference `Penalty Data` value for this center: **₹15,100. Exact match, no cap applied**
even at the highest single-bill amount (₹3,400) and the highest per-center total in the
whole dataset. If a publishing-stage cap existed, this is the row that would have
revealed it.

## 7. Why this isn't the guess the user told me not to make

The instruction was "do not *assume* `day_difference × ₹100` and do not use a *generic*
formula." What follows is not an assumption — it is a value independently derived three
different ways that all agree:

1. **From the workbook's own hidden amount columns** (§2) — the sheet computes
   `amount = count × rate` internally; dividing out count from >20 non-trivial
   (count, amount) pairs across multiple centers always yields `rate = day × 100`, never
   anything else.
2. **From the raw `Bills Data` sheet, independently, with zero reference to the
   `Penalty Data` sheet's structure** — grouping the 585 raw bills by center and applying
   `Σ day_difference × 100` reproduces the `Penalty Data` sheet's `Penalty` column
   **exactly, for all 93 centers, with zero mismatches** (§8's table). If the real rule
   were even slightly different (a slab boundary, a per-center exception, a rounding
   rule), a 93-row, 585-bill independent recomputation would not agree to the rupee on
   every single row — the odds of that happening by coincidence for a wrong formula are
   negligible.
3. **From date arithmetic** — `created_date − BILLDATE` reproduces the source
   `day_difference` column exactly, for all 585 rows, 0 mismatches (§10) — so the input
   to the formula is itself independently verified, not just trusted.

No center-specific exception, no hard-coded value, and no rounding was used to make any
row fit — see §8 for the full, unedited table.

## 8. Full reference reconciliation — every center, no exceptions

Calculated independently from raw `Bills Data` (grouped by `CENTREID`, `Σ day_difference
× 100`) and compared against the `Penalty Data` sheet's stated `Total`/`Penalty` per
center. **93/93 centers match exactly. 0 mismatches.**

The 9 centers the user named by name, with their exact delay distributions (previously
unstated, now recovered from source):

| Center | Delay distribution | Reference Penalty | Calculated Penalty | Match |
|---|---|---|---|---|
| Khemnichak | 1d=16, 2d=1, 4d=1 (Total 18) | ₹2,200 | ₹2,200 | ✅ |
| Main Road Ranchi | 1d=5 (Total 5) | ₹500 | ₹500 | ✅ |
| T Nagar Chennai | 1d=1 (Total 1) | ₹100 | ₹100 | ✅ |
| Motihari | 1d=8, 2d=1 (Total 9) | ₹1,000 | ₹1,000 | ✅ |
| Balasore | 1d=7, 2d=1 (Total 8) | ₹900 | ₹900 | ✅ |
| Kilpauk3 | 4d=4, 5d=4 (Total 8) | ₹3,600 | ₹3,600 | ✅ |
| Shantinagar Bengaluru | 1d=14, 2d=3, 3d=4, 7d=4, 8d=2, 9d=1 (Total 28) | ₹8,500 | ₹8,500 | ✅ |
| Waghodia Vadodara | 1d=9, 2d=8, 3d=9, 4d=11, 5d=1, 6d=2, 13d=2 (Total 42) | ₹13,900 | ₹13,900 | ✅ |
| Coimbatore | 1d=59, 2d=5, 3d=2, 4d=2, 5d=3, 6d=1, 7d=1, 8d=3, 11d=1, 12d=1 (Total 78) | ₹15,800 | ₹15,800 | ✅ |

*(Note: the distributions the user quoted in chat for Shantinagar and Waghodia matched
the source exactly once recovered programmatically. Kilpauk3's actual distribution —
4d=4, 5d=4 — differs from what might have been guessed; it is included here exactly as
found in the source, not adjusted.)*

**Full 93-center table** (every center in the reference workbook):

| Center Code | Center Name | Delay Distribution | Total Bills | Calculated Penalty |
|---|---|---|---|---|
| 1-TS-HYD-BJH-S | Banjara Hills, Hyderabad | 1d=2 | 2 | ₹200 |
| 106-BH-PTN-KHM-C | Khemnichak, Patna | 1d=16, 2d=1, 4d=1 | 18 | ₹2,200 |
| 107-JH-RNC-MRD-C | Main Road, Ranchi | 1d=5 | 5 | ₹500 |
| 11-TN-CHE-TNG-C | T Nagar, Chennai | 1d=1 | 1 | ₹100 |
| 123-BH-MTH-BYP-C | Motihari, Bihar | 1d=8, 2d=1 | 9 | ₹1,000 |
| 139-OD-BLS-KRD-C | Balasore, Odisha | 1d=7, 2d=1 | 8 | ₹900 |
| 142-MH-JLN-DRR-C | Deulgaon Raja Road, Jalna | 1d=1 | 1 | ₹100 |
| 148-TN-ERD-CMS-C | Erode, Tamil Nadu | 1d=6, 2d=1, 4d=1 | 8 | ₹1,200 |
| 150-MH-ULN-VTW-C | Vitthalwadi, Maharashtra | 1d=1 | 1 | ₹100 |
| 153-MH-ANG-MVG-C | Vilad Ghat, Ahmednagar | 1d=6 | 6 | ₹600 |
| 155-UP-ALD-KDN-C | Kidwai Nagar, Allahabad | 2d=1 | 1 | ₹200 |
| 168-MP-GWL-CHR-C | Cancer Hospital Rd, Gwalior | 1d=1, 3d=1 | 2 | ₹400 |
| 175-UP-SHP-BJR-C | Bajoria Road, Saharanpur | 1d=4 | 4 | ₹400 |
| 176-TN-CHE-KPK3-C | Kilpauk3, Chennai | 4d=4, 5d=4 | 8 | ₹3,600 |
| 178-MH-PUN-MCR-C | Magarpatta City Road, Pune | 1d=2 | 2 | ₹200 |
| 189-TN-CHE-KPK4-C | Kilpauk4, Chennai | 1d=1 | 1 | ₹100 |
| 196-KA-BLR-STN-S | Shantinagar, Bengaluru | 1d=14, 2d=3, 3d=4, 7d=4, 8d=2, 9d=1 | 28 | ₹8,500 |
| 198-DL-BLN-RNS-C | Ramesh Nagar, Delhi | 1d=1, 4d=1 | 2 | ₹500 |
| 20-MH-PUN-CHW-C | Chinchwad Captive, Pune | 1d=1 | 1 | ₹100 |
| 206-MP-JBL-NPT-C | Napier Town, Jabalpur | 1d=3 | 3 | ₹300 |
| 208-MH-MUM-KDW2-C | Kandivali West2, Mumbai | 1d=4 | 4 | ₹400 |
| 209-PB-FRZ-MDT-C | Ferozepur, Punjab | 1d=3, 15d=1 | 4 | ₹1,800 |
| 213-GJ-VDD-WGD-C | Waghodia, Vadodara | 1d=9, 2d=8, 3d=9, 4d=11, 5d=1, 6d=2, 13d=2 | 42 | ₹13,900 |
| 219-KA-BLR-KSL-C | Kumaraswamy Layout, Bengaluru | 1d=2 | 2 | ₹200 |
| 221-JH-DGR-KUN-C | Kunda, Deoghar | 1d=1 | 1 | ₹100 |
| 234-WB-HLZ-BLG-C | Balughata, Haldia | 1d=1, 10d=1 | 2 | ₹1,100 |
| 236-MH-NGP-SBD-C | Sitabuldi, Nagpur | 1d=4, 2d=1 | 5 | ₹600 |
| 238-UP-BSC-KJR-C | Khurja Rd, Bulandshahr | 1d=11, 2d=34 | 45 | ₹7,900 |
| 250-BH-BHS-PPP-C | Bihar Sharif PPP, Bihar | 1d=3, 10d=1 | 4 | ₹1,300 |
| 26-UP-LCK-ALB-C | Ajanta Hospital, Lucknow | 1d=6 | 6 | ₹600 |
| 263-MH-PUN-SBN-C | Sambhaji Nagar, Pune | 1d=1 | 1 | ₹100 |
| 269-TN-CHE-THB-C | TNHB Road, Chennai | 12d=1 | 1 | ₹1,200 |
| 273-JK-JMU-GNR-C | Gandhi Nagar, Jammu | 1d=1, 2d=1 | 2 | ₹300 |
| 279-BH-BGS-PPP-C | Begusarai PPP, Bihar | 1d=2, 8d=1 | 3 | ₹1,000 |
| 280-BH-KGG-PPP-C | Khagaria PPP, Bihar | 1d=4 | 4 | ₹400 |
| 283-BH-CPR-PPP-C | Chapra PPP, Bihar | 2d=1 | 1 | ₹200 |
| 285-BH-MFP-PPP-C | Muzaffarpur PPP, Bihar | 1d=1, 2d=1 | 2 | ₹300 |
| 289-BH-MGR-PPP-C | Munger PPP, Bihar | 14d=1 | 1 | ₹1,400 |
| 29-MH-MUM-BRW-S | Borivali West, Mumbai | 1d=1 | 1 | ₹100 |
| 290-TS-HYD-DOC-S | Dialysis on Call, Hyderabad | 1d=1 | 1 | ₹100 |
| 295-GJ-MSH-MTS-C | Manglaytan Society, Mehsana | 1d=3 | 3 | ₹300 |
| 297-TN-KKI-PPM-C | Perumalpuram, Kanyakumari | 4d=2 | 2 | ₹800 |
| 3-TS-MBN-YKA-C | Mahbubnagar, Telangana | 1d=1 | 1 | ₹100 |
| 310-MH-NGP-WDR-C | Wardha Road, Nagpur | 3d=1, 6d=1 | 2 | ₹900 |
| 321-GJ-AHM-VTP-C | Vastrapur, Ahmedabad | 1d=1, 2d=1 | 2 | ₹300 |
| 322-UP-JNU-HBP-C | Haribandhanpur, Jaunpur | 1d=3, 2d=1 | 4 | ₹500 |
| 327-MH-PUN-WKD-C | Wakad, Pune | 1d=3 | 3 | ₹300 |
| 334-BH-SSM-JMR-C | Sasaram, Bihar | 1d=7 | 7 | ₹700 |
| 347-MH-WDR-SGI-C | Sawangi, Wardha | 1d=5 | 5 | ₹500 |
| 348-MH-NGP-WDG-C | Wanadongari, Nagpur | 1d=2 | 2 | ₹200 |
| 362-KL-EDP-PBR-C | Edappal, Kerala | 1d=12 | 12 | ₹1,200 |
| 363-GJ-KSD-MSN-C | Madhusudan Nagar, Keshod | 1d=2 | 2 | ₹200 |
| 366-UP-AGR-SDN-C | Shaheed Nagar, Agra | 2d=1 | 1 | ₹200 |
| 367-HP-PLM-HLT-C | Holta, Palampur | 1d=2 | 2 | ₹200 |
| 373-UP-ALG-SSG-C | Sasni Gate, Aligarh | 1d=2 | 2 | ₹200 |
| 386-KA-BDR-KBR-C | Keb Road, Bidar | 1d=4 | 4 | ₹400 |
| 388-JH-RNC-IPC-C | Indraprasth Colony, Ranchi | 1d=10, 3d=1, 16d=1 | 12 | ₹2,900 |
| 394-PY-SBD-AAS-C | Anna Salai, Puducherry | 1d=3 | 3 | ₹300 |
| 50-TN-NVl-VDL-C | Vadalur Neyveli, Tamil Nadu | 1d=2 | 2 | ₹200 |
| 512-UP-GKP-PPP-C | Kunraghat PPP, Gorakhpur | 1d=3, 3d=1, 6d=1 | 5 | ₹1,200 |
| 515-NL-BGR-GDK-C | Gandak Chowk, Birgunj | 13d=1, 20d=1, 27d=1, 28d=1, 29d=1, 34d=1 | 6 | ₹15,100 |
| 516-TN-CHE-RDH-C | Redhills, Chennai | 1d=52, 2d=4, 3d=10, 4d=4, 5d=3, 6d=3, 8d=1 | 77 | ₹14,700 |
| 518-HR-SSA-HRD-C | Hisar Road, Sirsa | 1d=1 | 1 | ₹100 |
| 520-GJ-AHM-NVJ-S | Nava Vadaj, Ahmedabad | 1d=1 | 1 | ₹100 |
| 53-PB-JLN-DFC-C | Jalandhar, Punjab | 1d=4 | 4 | ₹400 |
| 539-HP-NHN-CDS-C | Chakreda Street, Nahan | 1d=2, 2d=1 | 3 | ₹400 |
| 54-TN-CMB-GPP-C | Coimbatore, Tamil Nadu | 1d=59, 2d=5, 3d=2, 4d=2, 5d=3, 6d=1, 7d=1, 8d=3, 11d=1, 12d=1 | 78 | ₹15,800 |
| 543-WB-ARB-NBP-C | Nabapally, Arambag | 1d=8 | 8 | ₹800 |
| 55-MH-MUM-BR2-S | Borivali West Standalone, Mumbai | 3d=1, 5d=1 | 2 | ₹800 |
| 550-UP-BST-AVC-C | Awas Vikas Colony, Basti | 1d=5, 2d=1, 3d=1 | 7 | ₹1,000 |
| 551-UP-LCK-KMT-C | Kamta, Lucknow | 1d=2 | 2 | ₹200 |
| 56-GJ-VDD-RMR-C | Vadodara, Gujarat | 1d=3, 17d=1 | 4 | ₹2,000 |
| 561-PB-GVG-RMT-C | RIMT, Gobindgarh | 1d=4 | 4 | ₹400 |
| 565-TS-JDC-NCK-C | Netaji Chowk, Jadcherla | 1d=5 | 5 | ₹500 |
| 576-UK-HW-KKL-C | Kankhal, Haridwar | 1d=1 | 1 | ₹100 |
| 581-GJ-HMT-MT2-C | Motipura2, Himatnagar | 1d=2 | 2 | ₹200 |
| 587-UP-MDB-PH2-C | Phase 2, Moradabad | 1d=5, 2d=3 | 8 | ₹1,100 |
| 595-GJ-AHM-TJR-C | Thaltej Road, Ahmedabad | 1d=1, 2d=1, 18d=1, 20d=1 | 4 | ₹4,100 |
| 596-JK-KTH-KLR-C | Kalibari, Kathua | 8d=1 | 1 | ₹800 |
| 60-MH-PUN-STG-C | Sant Dnyaneshwar Hospital, Pune | 1d=5 | 5 | ₹500 |
| 600-PB-NPB-RPR-C | Roopnagar Road, Nurpur Bedi | 2d=1 | 1 | ₹200 |
| 601-BH-DBG-GMR-C | G M Road, Darbhanga | 1d=2, 2d=1 | 3 | ₹400 |
| 615-UP-AZG-NRU-C | Narauli, Azamgarh | 1d=3, 2d=2, 3d=1, 7d=1, 21d=1, 25d=1 | 9 | ₹6,300 |
| 616-PB-BTI-GNR-C | Ganesh Nagar, Bathinda | 1d=2, 4d=1 | 3 | ₹600 |
| 636-BH-MHR-PPP-C | Marhaura PPP, Bihar | 1d=1, 2d=1 | 2 | ₹300 |
| 638-BH-BLS-PPP-C | Belsand PPP, Bihar | 1d=1 | 1 | ₹100 |
| 641-BH-CHK-PPP-C | Chakia PPP, Bihar | 2d=1 | 1 | ₹200 |
| 647-GJ-VDD-CHN-C | Chhani, Vadodara | 1d=1, 8d=1, 11d=1 | 3 | ₹2,000 |
| 648-MH-THN-KDI-C | Khidkali, Thane | 1d=1 | 1 | ₹100 |
| 665-TS-MBD-YNR-C | Yellandu Road, Mahabubabad | 1d=1, 3d=2 | 3 | ₹700 |
| 84-HR-PCK-S6-C | Sector6, Panchkula | 1d=4 | 4 | ₹400 |
| DOC10-TN-CMB-DOC-S | Dialysis on call, Coimbatore | 1d=5, 2d=5 | 10 | ₹1,500 |
| H017-DL-GEN-HHD-S | Home Hemodialysis, Delhi | 1d=2 | 2 | ₹200 |
| **TOTAL** | | | **585** | **₹137,900** |

**Grand total: reference ₹137,900 = calculated ₹137,900. Difference = ₹0. Status: PASS.**

## 9. Data conflicts found

**None.** Every one of the 93 center rows, all 585 bills, and both the publishing total
and the named-example totals the user quoted reconcile exactly with zero adjustment,
zero rounding, and zero excluded row. There is nothing to report as `DATA CONFLICT
FOUND` for this workbook.

One thing flagged for attention, not a conflict: center `84-HR-PCK-S6-C` (Sector6,
Panchkula) has a free-text annotation "Penalty to both" in the `Final penalty` sheet
against two co-listed managers (`NP34312 & NP35440`) — a genuine dual-responsibility
edge case the data model should be able to represent (a case attributable to more than
one manager), not something the formula needs to change for.

## 10. Delay-calculation cross-check (source vs. recomputed)

`calculated_day_difference = created_date.date() − BILLDATE.date()` was recomputed for
all 585 rows and compared against the source `day_difference` column.

**Result: 0 mismatches out of 585 rows.** The source `day_difference` field is internally
consistent with the two date columns for this entire dataset. (The implementation must
still perform this check per-record at runtime rather than trusting the field blindly —
this dataset simply happens to be clean; a future upload is not guaranteed to be.)

## 11. Implementation plan

Given the formula is proven, the build separates into the same six concerns the
requirement lists, each mapped to what CARVMS already has and what's new:

1. **`DelayedCashPenaltyCalculator` service** (new) — pure function over bill records:
   `calculated_penalty = Σ day_difference × rate_per_day`, versioned (`rule_version`,
   e.g. `DCB-2026-07-v1`) so a future rate change never rewrites history. Returns a full
   `calculation_trace` per bill (bill → day_difference → rate → amount) so the "why is
   this ₹X" requirement is satisfied by construction, not bolted on.
2. **Data model** (new tables) — `DelayedCashBill` (raw, immutable — SALESBILL, BILLDATE,
   bill_created_time, created_date, source_day_difference, calculated_day_difference,
   difference_check, data_quality_status), `DelayedCashPenaltyRule` (rate, effective
   dates, versioned), `DelayedCashCase` (one per center per period —
   calculated_penalty, validated_penalty, monthly_cap_amount, final_penalty,
   penalty_status), `DelayedCashResponse` (center's submitted remarks + evidence +
   TAT timestamps), reusing the existing `Evidence` model's storage pattern rather than
   inventing a new one.
3. **Reuse, not reimplement**: RBAC scoping (`audit_service.scope_query_to_role`),
   evidence storage conventions, and the remark-category vocabulary already implied by
   this dataset's own `Penalty Remarks` values (`Considered - Zero Billing`,
   `Not Considered - Center Lapse`, `Not Considered - Proof not available`, etc.) will
   seed the automatic remark-classifier rather than a separate one being invented.
4. **Two-stage penalty, never one field**: `calculated_penalty` (publishing, all bills)
   is written once and never overwritten; `validated_penalty` (Not-Considered bills
   only) and `final_penalty` (capped) are separate columns computed later in the
   workflow, per §5.
5. **The 6.25% cap rate is configuration, not a hardcoded literal** — same
   `PenaltyRule`-style pattern already used for Weekly Revenue Closure, but the
   *salary base it multiplies* must come from an external source (HR/payroll import or
   manual entry) — this will be surfaced as an explicit "not yet configured" state per
   center/manager rather than defaulted to 0 or fabricated.
6. **Center Manager / Cluster Manager penalty = not applicable** for this specific
   engine (§7 of the requirement) — enforced structurally by the calculator never
   attributing a monetary amount to those two role levels for delayed-cash cases, kept
   completely separate from the Weekly Revenue Closure engine's own (different) role
   hierarchy.

Everything else in the original 25-section requirement (48h/24h TAT, response
portal, dashboard, Excel export, audit trail, automated tests per bucket and per named
center) is scoped as previously discussed and will be implemented against this now-
proven formula, in the same phased, browser-verified manner as the rest of CARVMS.

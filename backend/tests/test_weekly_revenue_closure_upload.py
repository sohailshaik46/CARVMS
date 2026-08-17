"""Tests for the Weekly Revenue Closure raw pending-list ingestion parser.

tests/fixtures/weekly_revenue_closure_week2_pending.json is extracted
programmatically (not hand-transcribed) from the real reference file
`July-26-Week2-closure pending List till 12-6-2026.xlsx`'s `Center wise`
sheet, plus that same file's own `Center Penalty` sheet as the expected
per-center incident-type counts -- both real, both from the same workbook,
so this is a genuine same-source reconciliation, not an invented example.
"""

import json
import os
from collections import defaultdict
from datetime import date, datetime

import openpyxl

from app.services import weekly_revenue_closure_upload_service as upload_service

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def _build_workbook(header, rows) -> bytes:
    import io

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Center wise"
    sheet.append(header)
    for row in rows:
        r = list(row)
        # date column (index 4) comes back as an ISO string from the JSON
        # fixture -- convert back to a real date so the parser exercises
        # the same code path it would against a real .xlsx upload.
        if r[4]:
            r[4] = date.fromisoformat(r[4])
        sheet.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parses_real_week2_pending_file_and_reconciles_exactly():
    fixture = _load_fixture("weekly_revenue_closure_week2_pending.json")
    content = _build_workbook(fixture["header"], fixture["rows"])

    incidents, excess_billed_count, skipped = upload_service.parse_pending_workbook(content)

    assert skipped == []
    assert excess_billed_count == fixture["expected_excess_billed_row_count"]

    actual_counts = defaultdict(lambda: defaultdict(int))
    for inc in incidents:
        actual_counts[inc.centre_code][inc.mis_final_remark] += 1

    expected = fixture["expected_center_incident_counts"]
    assert set(actual_counts.keys()) == set(expected.keys())
    for code, expected_types in expected.items():
        for type_key, expected_count in expected_types.items():
            assert actual_counts[code].get(type_key, 0) == expected_count, (code, type_key)


def test_parsed_incidents_have_no_remark_or_verdict_yet():
    """Ingestion produces pending incidents awaiting a center remark and a
    Vigilance verdict -- never a fabricated one."""
    fixture = _load_fixture("weekly_revenue_closure_week2_pending.json")
    content = _build_workbook(fixture["header"], fixture["rows"])

    incidents, _, _ = upload_service.parse_pending_workbook(content)
    assert len(incidents) > 0
    for inc in incidents:
        assert inc.center_remarks is None
        assert inc.penalty_remarks is None


def test_excess_billed_rows_are_excluded_but_counted_not_silently_dropped():
    fixture = _load_fixture("weekly_revenue_closure_week2_pending.json")
    content = _build_workbook(fixture["header"], fixture["rows"])

    incidents, excess_billed_count, _ = upload_service.parse_pending_workbook(content)
    assert excess_billed_count == 16
    # None of the parsed (penalty-eligible) incidents are the excess type.
    assert all(inc.mis_final_remark != upload_service.EXCESS_BILLED_TYPE for inc in incidents)


def test_missing_required_column_raises_clear_error():
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Center wise"
    sheet.append(["Something", "Else", "Entirely"])
    import io

    buf = io.BytesIO()
    wb.save(buf)

    import pytest

    with pytest.raises(ValueError, match="missing required column"):
        upload_service.parse_pending_workbook(buf.getvalue())


def test_unparseable_date_is_skipped_not_fatal():
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Center wise"
    sheet.append(["Zone", "Cluster", "Center Code", "Center Name", "Date", "Billed Sessions", "Daily Report", "Variance", "Remark", "Final Remarks"])
    sheet.append(["South", "Test Cluster", "TEST-C", "Test Center", "not-a-date", 5, 4, -1, "1 Bill pending", "Bill Pending"])
    sheet.append(["South", "Test Cluster", "TEST-C", "Test Center", date(2026, 7, 5), 5, 4, -1, "1 Bill pending", "Bill Pending"])
    import io

    buf = io.BytesIO()
    wb.save(buf)

    incidents, _, skipped = upload_service.parse_pending_workbook(buf.getvalue())
    assert len(incidents) == 1
    assert len(skipped) == 1
    assert "date" in skipped[0].reason.lower()

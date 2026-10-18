"""Import contracts, malformed input and conservative duplicate handling."""

from datetime import date
from decimal import Decimal

import pytest

from src.data_processing import validate_csv

HEADER = "date,description,amount,category\n"


def test_normalizes_valid_rows_and_preserves_money():
    result = validate_csv(" Date , DESCRIPTION ,amount,category,transaction_id\n2026-02-01, Pay ,100.10, payroll ,00042\n2026-01-01,Food,-0.10, grocery ,00043\n")
    assert not result.has_errors
    assert result.data["date"].tolist() == [date(2026, 1, 1), date(2026, 2, 1)]
    assert result.data["amount"].tolist() == [Decimal("-0.10"), Decimal("100.10")]
    assert result.data["amount_cents"].tolist() == [-10, 10010]
    assert result.data["category"].tolist() == ["Groceries", "Income"]
    assert result.data["transaction_id"].tolist() == ["00043", "00042"]


@pytest.mark.parametrize("value", ["NaN", "inf", "-Infinity", "word", "", "1.001", "10000000000", "$12", "1,234"])
def test_rejects_invalid_amounts(value):
    result = validate_csv(HEADER + f'2026-01-01,Pay,"{value}",Income\n')
    assert result.has_errors
    assert result.data.empty
    assert any(issue.field == "amount" and issue.row == 2 for issue in result.issues)


@pytest.mark.parametrize("value", ["2026-02-30", "01/02/2026", "2026-1-1", "", "2026-01-01T00:00:00", "1700000000"])
def test_rejects_invalid_or_ambiguous_dates(value):
    assert validate_csv(HEADER + f"{value},Pay,12,Income\n").has_errors


@pytest.mark.parametrize("csv_text", ["", "date,amount\n", HEADER, "date,Date,description,amount,category\n", "date,,description,amount,category\n", HEADER + "2026-01-01,Pay,12\n", HEADER + '2026-01-01,"unclosed,12,Income\n', HEADER + "2026-01-01,,12,Income\n", HEADER + "2026-01-01,Pay,12,\n"])
def test_rejects_malformed_files(csv_text):
    assert validate_csv(csv_text).has_errors


def test_invalid_rows_are_reported_without_silent_partial_success():
    result = validate_csv(HEADER + "2026-01-01,Pay,12,Income\n2026-01-02,Bad,word,Other\n")
    assert result.has_errors
    assert len(result.data) == 1  # Preview only; the UI blocks analytics.
    assert result.input_rows == 2


def test_identical_idless_rows_are_kept_unless_opted_in():
    csv_text = HEADER + "2026-01-01,Food,-12,Groceries\n" * 2
    result = validate_csv(csv_text)
    assert not result.has_errors and len(result.data) == 2
    assert any(issue.field == "duplicate" for issue in result.issues)
    removed = validate_csv(csv_text, remove_ambiguous_duplicates=True)
    assert len(removed.data) == 1 and removed.duplicates_removed == 1


def test_identical_identified_records_are_removed():
    result = validate_csv(HEADER.rstrip() + ",transaction_id\n" + "2026-01-01,Pay,12,Income,0001\n" * 2)
    assert not result.has_errors and len(result.data) == 1
    assert result.duplicates_removed == 1


def test_conflicting_ids_block_all_conflicting_records():
    result = validate_csv(HEADER.rstrip() + ",transaction_id\n2026-01-01,Pay,12,Income,0001\n2026-01-01,Pay,14,Income,0001\n")
    assert result.has_errors and result.data.empty
    assert len([issue for issue in result.issues if issue.field == "transaction_id"]) == 2


def test_different_accounts_or_ids_are_distinct():
    result = validate_csv(HEADER.rstrip() + ",transaction_id,account\n2026-01-01,Pay,12,Income,0001,A\n2026-01-01,Pay,14,Income,0001,B\n2026-01-01,Pay,12,Income,0002,A\n")
    assert not result.has_errors and len(result.data) == 3


def test_utf8_bom_optional_fields_and_custom_category():
    result = validate_csv(("\ufeff" + HEADER.rstrip() + ",merchant,extra\n2026-01-01,Coffee,-12, pet  supplies , ,ignored\n").encode())
    assert not result.has_errors
    assert result.data.iloc[0]["category"] == "Pet Supplies"
    assert result.data.iloc[0]["merchant"] is None
    assert any(issue.field == "columns" for issue in result.issues)


def test_multiline_csv_reports_ending_line_number():
    result = validate_csv(HEADER + '2026-01-01,"two\nlines",wrong,Other\n')
    assert result.issues[0].row == 3


def test_file_error_and_non_utf8_are_reported(tmp_path):
    assert validate_csv(tmp_path / "missing.csv").has_errors
    assert validate_csv(b"\xff\xfe").has_errors


def test_size_and_row_limits(monkeypatch):
    monkeypatch.setattr("src.data_processing.MAX_CSV_BYTES", 10)
    assert validate_csv(HEADER).has_errors
    monkeypatch.setattr("src.data_processing.MAX_CSV_BYTES", 10000)
    monkeypatch.setattr("src.data_processing.MAX_TRANSACTIONS", 1)
    result = validate_csv(HEADER + "2026-01-01,Pay,12,Income\n" * 2)
    assert result.has_errors and result.data.empty


def test_zero_amount_and_blank_lines_are_valid():
    result = validate_csv(HEADER + "\n2024-02-29,Adjustment,0,Other\n")
    assert not result.has_errors and len(result.data) == 1

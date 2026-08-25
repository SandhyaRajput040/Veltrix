"""
Tests for src.inventory.reader

Uses real xlsx files built with openpyxl (not mocks) -- reading Excel
files correctly, including ignoring decoy sheets and catching a wrong
header, is exactly the behaviour worth testing against the real
library.
"""

import openpyxl
import pytest

from src.inventory.reader import read_template_sheet
from src.inventory.schema import EXPECTED_COLUMNS


def _write_xlsx(path, sheets: dict):
    """Helper: write a workbook with one or more named sheets, each a list of rows."""
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for sheet_name, rows in sheets.items():
        sheet = workbook.create_sheet(sheet_name)
        for row in rows:
            sheet.append(row)
    workbook.save(path)


def test_reads_only_the_template_sheet_and_ignores_decoys(tmp_path):
    """
    Real Baapstore files contain many metadata sheets (icons,
    Instructions, Data Validation, etc.) -- only "Template" should
    ever be read.
    """
    path = str(tmp_path / "inventory.xlsx")
    _write_xlsx(
        path,
        {
            "Instructions": [["Do not edit this sheet"]],
            "Template": [
                EXPECTED_COLUMNS,
                ["SKU-1", None, None, None, 10, None, None, None],
                ["SKU-2", None, None, None, 5, None, None, None],
            ],
            "Dropdown Lists": [["some", "dropdown", "junk"]],
        },
    )

    rows = read_template_sheet(path)

    assert len(rows) == 2
    assert rows[0]["sku"] == "SKU-1"
    assert rows[0]["quantity"] == 10
    assert rows[1]["sku"] == "SKU-2"


def test_source_row_numbers_match_actual_excel_row_numbers(tmp_path):
    """Row numbers in the returned dicts must match Excel's own row numbering (1-indexed, header = row 1)."""
    path = str(tmp_path / "inventory.xlsx")
    _write_xlsx(
        path,
        {
            "Template": [
                EXPECTED_COLUMNS,
                ["SKU-1", None, None, None, 10, None, None, None],  # row 2
                ["SKU-2", None, None, None, 5, None, None, None],  # row 3
            ]
        },
    )

    rows = read_template_sheet(path)

    assert rows[0]["source_row"] == 2
    assert rows[1]["source_row"] == 3


def test_raises_if_template_sheet_is_missing(tmp_path):
    """If there's no 'Template' sheet at all, fail loudly -- never guess another sheet is the data."""
    path = str(tmp_path / "inventory.xlsx")
    _write_xlsx(path, {"Instructions": [["nothing useful here"]]})

    with pytest.raises(ValueError, match="Template"):
        read_template_sheet(path)


def test_raises_if_header_row_does_not_match_expected_columns(tmp_path):
    """A wrong/reordered/renamed header must be rejected, not silently accepted."""
    path = str(tmp_path / "inventory.xlsx")
    wrong_header = ["sku", "quantity", "price"]  # wrong order & missing columns
    _write_xlsx(
        path,
        {"Template": [wrong_header, ["SKU-1", 10, 1.0]]},
    )

    with pytest.raises(ValueError, match="does not match"):
        read_template_sheet(path)


def test_blank_trailing_rows_are_skipped(tmp_path):
    """A fully blank row (common at the end of exported sheets) should not become a fake data row."""
    path = str(tmp_path / "inventory.xlsx")
    _write_xlsx(
        path,
        {
            "Template": [
                EXPECTED_COLUMNS,
                ["SKU-1", None, None, None, 10, None, None, None],
                [None, None, None, None, None, None, None, None],
            ]
        },
    )

    rows = read_template_sheet(path)

    assert len(rows) == 1
    assert rows[0]["sku"] == "SKU-1"
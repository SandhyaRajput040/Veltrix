"""
Tests for src.inventory.writer

Verifies the actual bytes written to disk: correct column order,
tab delimiting, UTF-8 encoding, and that the quarantine CSV has the
required columns.
"""

import csv

from src.inventory.schema import EXPECTED_COLUMNS
from src.inventory.writer import QUARANTINE_REPORT_COLUMNS, write_amazon_txt, write_quarantine_report


def test_amazon_txt_header_matches_expected_column_order(tmp_path):
    output_path = str(tmp_path / "output.txt")
    write_amazon_txt([], output_path)

    with open(output_path, "r", encoding="utf-8") as fh:
        header_line = fh.readline().rstrip("\n")

    assert header_line.split("\t") == EXPECTED_COLUMNS


def test_amazon_txt_is_tab_delimited_with_correct_values(tmp_path):
    output_path = str(tmp_path / "output.txt")
    rows = [
        {
            "sku": "SKU-1",
            "price": "19.99",
            "minimum-seller-allowed-price": "",
            "maximum-seller-allowed-price": "",
            "quantity": "10",
            "leadtime-to-ship": "",
            "fulfillment-channel": "",
            "merchant_shipping_group_name": "",
        }
    ]
    write_amazon_txt(rows, output_path)

    with open(output_path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    assert lines[0] == "\t".join(EXPECTED_COLUMNS)
    assert lines[1] == "SKU-1\t19.99\t\t\t10\t\t\t"


def test_amazon_txt_is_utf8_encoded(tmp_path):
    """SKUs may legitimately contain non-ASCII characters (e.g. transliterated names)."""
    output_path = str(tmp_path / "output.txt")
    rows = [
        {
            "sku": "SKU-\u00e9\u00e8",
            "price": "",
            "minimum-seller-allowed-price": "",
            "maximum-seller-allowed-price": "",
            "quantity": "5",
            "leadtime-to-ship": "",
            "fulfillment-channel": "",
            "merchant_shipping_group_name": "",
        }
    ]
    write_amazon_txt(rows, output_path)

    with open(output_path, "rb") as fh:
        raw_bytes = fh.read()
    assert "SKU-\u00e9\u00e8".encode("utf-8") in raw_bytes


def test_quarantine_report_has_required_columns(tmp_path):
    output_path = str(tmp_path / "quarantine.csv")
    write_quarantine_report([], output_path)

    with open(output_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)

    assert header == QUARANTINE_REPORT_COLUMNS


def test_quarantine_report_writes_row_data_correctly(tmp_path):
    output_path = str(tmp_path / "quarantine.csv")
    entries = [
        {
            "source_file": "Amazon_Bulk_Daily_Quantity_Update.xlsx",
            "source_row": 5,
            "sku": "BAD-SKU",
            "quantity": "-1",
            "reason": "negative_quantity",
            "validation_error": "Quantity is negative (-1).",
            "timestamp": "2026-08-21T10:00:00Z",
        }
    ]
    write_quarantine_report(entries, output_path)

    with open(output_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["sku"] == "BAD-SKU"
    assert rows[0]["reason"] == "negative_quantity"
    assert rows[0]["source_row"] == "5"
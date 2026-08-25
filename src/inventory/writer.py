"""
Writes the two output artifacts of the validation pipeline:
  - a tab-delimited, UTF-8 Amazon Inventory Loader TXT file (valid
    rows only), and
  - a CSV quarantine report (invalid rows only), so nothing is ever
    silently dropped.
"""

import csv

from src.inventory.schema import EXPECTED_COLUMNS

QUARANTINE_REPORT_COLUMNS = [
    "source_file",
    "source_row",
    "sku",
    "quantity",
    "reason",
    "validation_error",
    "timestamp",
]


def write_amazon_txt(valid_rows, output_path: str) -> None:
    """
    Write `valid_rows` as a tab-delimited UTF-8 file matching the
    Amazon Inventory Loader column order exactly. Uses '\\n' line
    endings explicitly (via newline="") so Windows doesn't silently
    rewrite them to '\\r\\n' -- if Amazon's uploader is later found to
    require CRLF, that should be an explicit, documented change here.
    """
    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\t".join(EXPECTED_COLUMNS) + "\n")
        for row in valid_rows:
            line = "\t".join(row[column] for column in EXPECTED_COLUMNS)
            fh.write(line + "\n")


def write_quarantine_report(quarantined_rows, output_path: str) -> None:
    """Write `quarantined_rows` as a CSV quarantine report."""
    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUARANTINE_REPORT_COLUMNS)
        writer.writeheader()
        for row in quarantined_rows:
            writer.writerow(row)
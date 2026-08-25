"""
Orchestrates one full inventory-file conversion:

  1. Read the Template sheet.
  2. Validate every row.
  3. Write the Amazon-ready TXT (valid rows only).
  4. Write the quarantine CSV (invalid rows only).

Never loses data: every row read ends up in exactly one of the two
output files. Never uploads to Amazon -- that's Module 4's job. This
module's only concern is turning a raw Baapstore xlsx into a trustworthy
TXT + an honest paper trail of what was rejected and why.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from src.inventory.reader import read_template_sheet
from src.inventory.validator import validate_rows
from src.inventory.writer import write_amazon_txt, write_quarantine_report


@dataclass
class ProcessingSummary:
    source_file: str
    rows_read: int
    rows_accepted: int
    rows_quarantined: int
    output_txt_path: str
    quarantine_csv_path: str


def process_inventory_file(
    xlsx_path: str,
    output_txt_path: str,
    quarantine_csv_path: str,
    timestamp: str = None,
) -> ProcessingSummary:
    """
    Run the full read -> validate -> write pipeline for one xlsx file.

    `timestamp` is injectable for testability (so tests don't depend on
    wall-clock time); in real runs it defaults to the current UTC time.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    source_file = os.path.basename(xlsx_path)

    rows = read_template_sheet(xlsx_path)
    result = validate_rows(rows, source_file=source_file, timestamp=timestamp)

    write_amazon_txt(result.valid_rows, output_txt_path)
    write_quarantine_report(result.quarantined_rows, quarantine_csv_path)

    return ProcessingSummary(
        source_file=source_file,
        rows_read=len(rows),
        rows_accepted=len(result.valid_rows),
        rows_quarantined=len(result.quarantined_rows),
        output_txt_path=output_txt_path,
        quarantine_csv_path=quarantine_csv_path,
    )


if __name__ == "__main__":
    # Manual smoke-test entry point: process whatever tracked files are
    # currently sitting in data/input/ (e.g. downloaded by Module 2).
    import glob

    os.makedirs("data/output", exist_ok=True)
    os.makedirs("data/quarantine", exist_ok=True)

    xlsx_files = glob.glob("data/input/Amazon_Bulk_*_Quantity_Update*.xlsx")
    if not xlsx_files:
        print("No tracked xlsx files found in data/input/. Nothing to process.")

    for path in xlsx_files:
        name = os.path.splitext(os.path.basename(path))[0]
        summary = process_inventory_file(
            xlsx_path=path,
            output_txt_path=f"data/output/{name}.txt",
            quarantine_csv_path=f"data/quarantine/{name}_quarantine_report.csv",
        )
        print(
            f"{summary.source_file}: read {summary.rows_read}, "
            f"accepted {summary.rows_accepted}, quarantined {summary.rows_quarantined}"
        )
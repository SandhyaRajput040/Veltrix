"""
Orchestrates one full daily run of the pipeline:

  Google Drive sync (Module 2) -> validate + convert (Module 3)
    -> submit to Amazon or fallback (Module 4)

This is the single script Windows Task Scheduler runs once a day (see
run_daily.bat in the project root). It does NOT implement logging or
email notifications itself -- that's Module 6, which will wrap this
module's DailyRunSummary into a proper log entry and an email.

RELIABILITY PRINCIPLE: one bad file must never take down the whole
run. If Drive sync fails entirely, that's a genuine full-run failure
(nothing to process). But if Drive sync succeeds and one of several
downloaded files fails validation or Amazon submission, the other
files still get processed, and the failure is recorded per-file in
the summary rather than raised and left unrecorded.
"""

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from src.amazon.submitter import submit_based_on_settings
from src.drive.downloader import sync_inventory_files
from src.inventory.pipeline import process_inventory_file


@dataclass
class FileRunResult:
    source_file: str
    rows_read: int = 0
    rows_accepted: int = 0
    rows_quarantined: int = 0
    submission_mode: Optional[str] = None
    feed_ids: List[str] = field(default_factory=list)
    accepted_by_amazon: int = 0
    invalid_by_amazon: int = 0
    error: Optional[str] = None


@dataclass
class DailyRunSummary:
    started_at: str
    finished_at: str = ""
    files_downloaded: List[str] = field(default_factory=list)
    files_skipped: List[str] = field(default_factory=list)
    file_results: List[FileRunResult] = field(default_factory=list)
    overall_status: str = "SUCCESS"  # SUCCESS, PARTIAL_FAILURE, or FAILURE
    fatal_error: Optional[str] = None


def _retry(fn, max_attempts: int = 3, backoff_seconds: int = 5):
    """
    Retry a zero-argument callable on exception, with a fixed backoff.
    Used only around the Drive sync step, since that's the step most
    likely to hit a transient network error -- validation and feed
    submission failures are treated as real per-file failures, not
    something to blindly retry.
    """
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 -- intentionally broad: any transient failure should retry
            last_error = exc
            if attempt < max_attempts:
                time.sleep(backoff_seconds)
    raise last_error


def run_daily_pipeline(settings) -> DailyRunSummary:
    """
    Run one full daily pipeline pass. Never raises for a per-file
    problem -- only a fatal, nothing-could-be-done failure (e.g. Drive
    sync itself failing after retries) sets overall_status to FAILURE
    and populates fatal_error. Individual file failures are recorded
    in that file's FileRunResult.error and roll the overall status up
    to PARTIAL_FAILURE, never silently ignored.
    """
    summary = DailyRunSummary(started_at=datetime.now(timezone.utc).isoformat())

    # Fail fast with a clear message if Drive credentials simply
    # aren't configured yet -- this is a setup problem, not a
    # transient network error, so there's no point retrying it.
    if not settings.google_drive_credentials_file or not os.path.isfile(
        settings.google_drive_credentials_file
    ):
        summary.overall_status = "FAILURE"
        summary.fatal_error = (
            "Google Drive credentials file not configured or not found. "
            "Set GOOGLE_DRIVE_CREDENTIALS_FILE in .env to your service account JSON key path "
            "(see README.md, Module 2 setup)."
        )
        summary.finished_at = datetime.now(timezone.utc).isoformat()
        return summary

    try:
        sync_result = _retry(
            lambda: sync_inventory_files(
                credentials_file=settings.google_drive_credentials_file,
                folder_id=settings.google_drive_folder_id,
                download_dir="data/input",
                state_file="state/drive_state.json",
            )
        )
    except Exception as exc:  # noqa: BLE001
        summary.overall_status = "FAILURE"
        summary.fatal_error = f"Google Drive sync failed: {exc}"
        summary.finished_at = datetime.now(timezone.utc).isoformat()
        return summary

    summary.files_downloaded = sync_result.downloaded
    summary.files_skipped = sync_result.skipped

    any_file_failed = False

    for xlsx_path in sync_result.downloaded:
        source_name = os.path.splitext(os.path.basename(xlsx_path))[0]
        file_result = FileRunResult(source_file=os.path.basename(xlsx_path))

        try:
            os.makedirs("data/output", exist_ok=True)
            os.makedirs("data/quarantine", exist_ok=True)
            output_txt_path = f"data/output/{source_name}.txt"
            quarantine_csv_path = f"data/quarantine/{source_name}_quarantine_report.csv"

            processing_summary = process_inventory_file(
                xlsx_path=xlsx_path,
                output_txt_path=output_txt_path,
                quarantine_csv_path=quarantine_csv_path,
            )
            file_result.rows_read = processing_summary.rows_read
            file_result.rows_accepted = processing_summary.rows_accepted
            file_result.rows_quarantined = processing_summary.rows_quarantined

            if processing_summary.rows_accepted > 0:
                rows = _read_amazon_txt_rows(output_txt_path)
                submission_result = submit_based_on_settings(rows, source_name, settings)
                file_result.submission_mode = submission_result.mode
                file_result.feed_ids = submission_result.feed_ids
                file_result.accepted_by_amazon = submission_result.total_accepted
                file_result.invalid_by_amazon = submission_result.total_invalid

        except Exception as exc:  # noqa: BLE001 -- one bad file must not crash the whole run
            file_result.error = str(exc)
            any_file_failed = True

        summary.file_results.append(file_result)

    if any_file_failed:
        summary.overall_status = "PARTIAL_FAILURE"

    summary.finished_at = datetime.now(timezone.utc).isoformat()
    return summary


def _read_amazon_txt_rows(txt_path: str) -> list:
    """Local copy of the same helper in src.amazon.submitter, to avoid a circular import."""
    with open(txt_path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append(dict(zip(header, values)))
    return rows


if __name__ == "__main__":
    # Prefer running `python main.py` at the project root -- this
    # module is meant to be imported by main.py (and by tests), not
    # run directly. Kept here only as a fallback for a quick manual
    # check without going through main.py.
    from src.config.settings import settings as _settings

    _result = run_daily_pipeline(_settings)
    print(f"Overall status: {_result.overall_status}")
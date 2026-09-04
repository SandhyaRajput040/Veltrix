"""
Tests for src.notifications.report_formatter

Verifies the email subject/body actually reflect the data in a
DailyRunSummary -- every field the project spec requires in the daily
notification (files processed, rows read/accepted/quarantined, Amazon
results, errors, overall status) must show up in the body somewhere.
"""

from src.notifications.report_formatter import format_body, format_subject
from src.scheduler.run_daily_job import DailyRunSummary, FileRunResult


def test_subject_includes_status_and_date():
    summary = DailyRunSummary(
        started_at="2026-08-21T10:00:00+00:00", overall_status="SUCCESS"
    )
    subject = format_subject(summary)

    assert "SUCCESS" in subject
    assert "2026-08-21" in subject


def test_body_reports_fatal_error_and_skips_file_details():
    summary = DailyRunSummary(
        started_at="2026-08-21T10:00:00+00:00",
        finished_at="2026-08-21T10:00:05+00:00",
        overall_status="FAILURE",
        fatal_error="Google Drive sync failed: connection refused",
    )
    body = format_body(summary)

    assert "FAILURE" in body
    assert "connection refused" in body
    assert "No files were processed" in body


def test_body_reports_files_downloaded_and_skipped():
    summary = DailyRunSummary(
        started_at="2026-08-21T10:00:00+00:00",
        files_downloaded=["Amazon_Bulk_Daily_Quantity_Update.xlsx"],
        files_skipped=["Amazon_Bulk_Full_Products_Quantity_Update.xlsx"],
    )
    body = format_body(summary)

    assert "Amazon_Bulk_Daily_Quantity_Update.xlsx" in body
    assert "Amazon_Bulk_Full_Products_Quantity_Update.xlsx" in body


def test_body_reports_per_file_row_counts_and_amazon_results():
    summary = DailyRunSummary(
        started_at="2026-08-21T10:00:00+00:00",
        files_downloaded=["Amazon_Bulk_Daily_Quantity_Update.xlsx"],
        file_results=[
            FileRunResult(
                source_file="Amazon_Bulk_Daily_Quantity_Update.xlsx",
                rows_read=100,
                rows_accepted=95,
                rows_quarantined=5,
                submission_mode="live",
                feed_ids=["feed-123"],
                accepted_by_amazon=94,
                invalid_by_amazon=1,
            )
        ],
    )
    body = format_body(summary)

    assert "100" in body
    assert "95" in body
    assert "5" in body
    assert "live" in body
    assert "feed-123" in body
    assert "94" in body


def test_body_reports_per_file_error():
    summary = DailyRunSummary(
        started_at="2026-08-21T10:00:00+00:00",
        overall_status="PARTIAL_FAILURE",
        files_downloaded=["bad.xlsx"],
        file_results=[
            FileRunResult(source_file="bad.xlsx", error="Template sheet header mismatch")
        ],
    )
    body = format_body(summary)

    assert "PARTIAL_FAILURE" in body
    assert "Template sheet header mismatch" in body


def test_body_handles_a_run_with_nothing_new_to_process():
    summary = DailyRunSummary(
        started_at="2026-08-21T10:00:00+00:00",
        files_skipped=["Amazon_Bulk_Daily_Quantity_Update.xlsx"],
    )
    body = format_body(summary)

    assert "No new/changed files to process" in body

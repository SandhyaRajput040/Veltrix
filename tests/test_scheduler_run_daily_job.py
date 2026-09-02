"""
Tests for src.scheduler.run_daily_job

Mocks Modules 2, 3, and 4's entry points entirely -- this module's job
is purely orchestration and failure isolation, which is exactly what
these tests verify: one bad file doesn't take down the whole run, a
totally failed Drive sync is reported as a fatal failure, and files
with zero accepted rows are never submitted to Amazon.
"""

import tempfile

from dataclasses import dataclass, field
from typing import List
from unittest.mock import Mock

import pytest

from src.scheduler import run_daily_job as scheduler_module
from src.scheduler.run_daily_job import _retry, run_daily_pipeline


def _make_fake_credentials_file() -> str:
    """
    run_daily_pipeline fails fast (correctly) if the Drive credentials
    file doesn't exist on disk -- these tests aren't testing that
    check, so give them a real (empty) file to point at instead of a
    path that doesn't exist.
    """
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    handle.write("{}")
    handle.close()
    return handle.name


class _FakeSettings:
    amazon_fallback_mode = True
    amazon_seller_id = "SELLER1"
    google_drive_credentials_file = _make_fake_credentials_file()
    google_drive_folder_id = "FOLDER1"


@dataclass
class _FakeSyncResult:
    downloaded: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    unmatched_ignored: int = 0


@dataclass
class _FakeProcessingSummary:
    source_file: str
    rows_read: int
    rows_accepted: int
    rows_quarantined: int
    output_txt_path: str
    quarantine_csv_path: str


@dataclass
class _FakeSubmissionResult:
    mode: str = "fallback"
    feed_ids: List[str] = field(default_factory=list)
    total_accepted: int = 0
    total_invalid: int = 0


# ---------------------------------------------------------------------------
# _retry
# ---------------------------------------------------------------------------


def test_retry_returns_result_on_first_success():
    result = _retry(lambda: 42, max_attempts=3, backoff_seconds=0)
    assert result == 42


def test_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr(scheduler_module.time, "sleep", lambda seconds: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    result = _retry(flaky, max_attempts=3, backoff_seconds=0)
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_raises_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr(scheduler_module.time, "sleep", lambda seconds: None)

    def always_fails():
        raise ConnectionError("still down")

    with pytest.raises(ConnectionError, match="still down"):
        _retry(always_fails, max_attempts=3, backoff_seconds=0)


# ---------------------------------------------------------------------------
# run_daily_pipeline
# ---------------------------------------------------------------------------


def test_run_reports_success_when_nothing_new_to_download(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "sync_inventory_files", lambda **kwargs: _FakeSyncResult(skipped=["file1.xlsx"])
    )

    summary = run_daily_pipeline(_FakeSettings())

    assert summary.overall_status == "SUCCESS"
    assert summary.files_downloaded == []
    assert summary.files_skipped == ["file1.xlsx"]
    assert summary.file_results == []


def test_run_reports_fatal_failure_when_drive_sync_never_succeeds(monkeypatch):
    monkeypatch.setattr(scheduler_module.time, "sleep", lambda seconds: None)

    def always_fails(**kwargs):
        raise ConnectionError("Drive is down")

    monkeypatch.setattr(scheduler_module, "sync_inventory_files", always_fails)

    summary = run_daily_pipeline(_FakeSettings())

    assert summary.overall_status == "FAILURE"
    assert "Drive is down" in summary.fatal_error
    assert summary.file_results == []


def test_run_fails_fast_without_retrying_when_credentials_file_is_missing(tmp_path):
    """
    A missing credentials file is a configuration problem, not a
    transient network error -- this should fail immediately with a
    clear message, never attempt sync_inventory_files at all.
    """

    class _SettingsWithMissingCreds(_FakeSettings):
        google_drive_credentials_file = str(tmp_path / "does_not_exist.json")

    summary = run_daily_pipeline(_SettingsWithMissingCreds())

    assert summary.overall_status == "FAILURE"
    assert "credentials file not configured or not found" in summary.fatal_error


def test_run_processes_and_submits_a_downloaded_file_successfully(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        scheduler_module,
        "sync_inventory_files",
        lambda **kwargs: _FakeSyncResult(downloaded=["data/input/Amazon_Bulk_Daily_Quantity_Update.xlsx"]),
    )
    monkeypatch.setattr(
        scheduler_module,
        "process_inventory_file",
        lambda **kwargs: _FakeProcessingSummary(
            source_file="Amazon_Bulk_Daily_Quantity_Update.xlsx",
            rows_read=2,
            rows_accepted=1,
            rows_quarantined=1,
            output_txt_path=kwargs["output_txt_path"],
            quarantine_csv_path=kwargs["quarantine_csv_path"],
        ),
    )
    monkeypatch.setattr(
        scheduler_module,
        "_read_amazon_txt_rows",
        lambda path: [{"sku": "SKU-1", "quantity": "10"}],
    )
    monkeypatch.setattr(
        scheduler_module,
        "submit_based_on_settings",
        lambda rows, source_name, settings: _FakeSubmissionResult(mode="fallback"),
    )

    summary = run_daily_pipeline(_FakeSettings())

    assert summary.overall_status == "SUCCESS"
    assert len(summary.file_results) == 1
    file_result = summary.file_results[0]
    assert file_result.rows_read == 2
    assert file_result.rows_accepted == 1
    assert file_result.rows_quarantined == 1
    assert file_result.submission_mode == "fallback"
    assert file_result.error is None


def test_run_never_submits_a_file_with_zero_accepted_rows(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        scheduler_module,
        "sync_inventory_files",
        lambda **kwargs: _FakeSyncResult(downloaded=["data/input/all_bad.xlsx"]),
    )
    monkeypatch.setattr(
        scheduler_module,
        "process_inventory_file",
        lambda **kwargs: _FakeProcessingSummary(
            source_file="all_bad.xlsx",
            rows_read=3,
            rows_accepted=0,
            rows_quarantined=3,
            output_txt_path=kwargs["output_txt_path"],
            quarantine_csv_path=kwargs["quarantine_csv_path"],
        ),
    )
    submit_mock = Mock()
    monkeypatch.setattr(scheduler_module, "submit_based_on_settings", submit_mock)

    summary = run_daily_pipeline(_FakeSettings())

    submit_mock.assert_not_called()
    assert summary.overall_status == "SUCCESS"
    assert summary.file_results[0].rows_accepted == 0


def test_one_bad_file_does_not_stop_other_files_from_processing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        scheduler_module,
        "sync_inventory_files",
        lambda **kwargs: _FakeSyncResult(downloaded=["data/input/bad.xlsx", "data/input/good.xlsx"]),
    )

    def fake_process(**kwargs):
        if "bad" in kwargs["xlsx_path"]:
            raise ValueError("Template sheet header mismatch")
        return _FakeProcessingSummary(
            source_file="good.xlsx",
            rows_read=1,
            rows_accepted=1,
            rows_quarantined=0,
            output_txt_path=kwargs["output_txt_path"],
            quarantine_csv_path=kwargs["quarantine_csv_path"],
        )

    monkeypatch.setattr(scheduler_module, "process_inventory_file", fake_process)
    monkeypatch.setattr(scheduler_module, "_read_amazon_txt_rows", lambda path: [{"sku": "SKU-1", "quantity": "1"}])
    monkeypatch.setattr(
        scheduler_module, "submit_based_on_settings", lambda rows, source_name, settings: _FakeSubmissionResult()
    )

    summary = run_daily_pipeline(_FakeSettings())

    assert summary.overall_status == "PARTIAL_FAILURE"
    assert len(summary.file_results) == 2

    bad_result = next(r for r in summary.file_results if r.source_file == "bad.xlsx")
    good_result = next(r for r in summary.file_results if r.source_file == "good.xlsx")

    assert bad_result.error is not None
    assert "Template sheet header mismatch" in bad_result.error
    assert good_result.error is None
    assert good_result.rows_accepted == 1
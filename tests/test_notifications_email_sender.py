"""
Tests for src.notifications.email_sender

Mocks smtplib.SMTP entirely -- no real email account is being used in
tests. Verifies the message is built correctly (subject, recipient,
attachments) and that transient SMTP failures are retried before
giving up.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.notifications.email_sender import EmailSendError, send_run_summary_email
from src.scheduler.run_daily_job import DailyRunSummary, FileRunResult


class _FakeSettings:
    notification_email = "owner@example.com"
    smtp_host = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = "veltrix.bot@gmail.com"
    smtp_password = "app-password-123"


def _make_smtp_mock():
    """Return a mock that behaves like `with smtplib.SMTP(...) as server:`."""
    server_mock = MagicMock()
    smtp_class_mock = MagicMock()
    smtp_class_mock.return_value.__enter__.return_value = server_mock
    return smtp_class_mock, server_mock


def test_send_run_summary_email_happy_path():
    summary = DailyRunSummary(started_at="2026-08-21T10:00:00+00:00", overall_status="SUCCESS")
    smtp_class_mock, server_mock = _make_smtp_mock()

    with patch("src.notifications.email_sender.smtplib.SMTP", smtp_class_mock):
        send_run_summary_email(summary, _FakeSettings())

    server_mock.starttls.assert_called_once()
    server_mock.login.assert_called_once_with("veltrix.bot@gmail.com", "app-password-123")
    server_mock.send_message.assert_called_once()

    sent_message = server_mock.send_message.call_args[0][0]
    assert sent_message["To"] == "owner@example.com"
    assert "SUCCESS" in sent_message["Subject"]


def test_send_run_summary_email_raises_if_not_configured():
    class _IncompleteSettings(_FakeSettings):
        notification_email = ""

    summary = DailyRunSummary(started_at="2026-08-21T10:00:00+00:00")

    with pytest.raises(EmailSendError, match="not fully configured"):
        send_run_summary_email(summary, _IncompleteSettings())


def test_send_run_summary_email_attaches_quarantine_report(tmp_path):
    quarantine_path = tmp_path / "quarantine_report.csv"
    quarantine_path.write_text("source_file,sku,reason\nfile.xlsx,BAD-SKU,negative_quantity\n")

    summary = DailyRunSummary(
        started_at="2026-08-21T10:00:00+00:00",
        files_downloaded=["file.xlsx"],
        file_results=[
            FileRunResult(
                source_file="file.xlsx",
                rows_quarantined=1,
                quarantine_csv_path=str(quarantine_path),
            )
        ],
    )
    smtp_class_mock, server_mock = _make_smtp_mock()

    with patch("src.notifications.email_sender.smtplib.SMTP", smtp_class_mock):
        send_run_summary_email(summary, _FakeSettings())

    sent_message = server_mock.send_message.call_args[0][0]
    attachment_filenames = [
        part.get_filename() for part in sent_message.iter_attachments()
    ]
    assert "quarantine_report.csv" in attachment_filenames


def test_send_run_summary_email_skips_attachment_when_no_quarantine():
    summary = DailyRunSummary(
        started_at="2026-08-21T10:00:00+00:00",
        files_downloaded=["file.xlsx"],
        file_results=[FileRunResult(source_file="file.xlsx", rows_quarantined=0)],
    )
    smtp_class_mock, server_mock = _make_smtp_mock()

    with patch("src.notifications.email_sender.smtplib.SMTP", smtp_class_mock):
        send_run_summary_email(summary, _FakeSettings())

    sent_message = server_mock.send_message.call_args[0][0]
    assert list(sent_message.iter_attachments()) == []


def test_send_run_summary_email_retries_transient_failures_then_succeeds(monkeypatch):
    summary = DailyRunSummary(started_at="2026-08-21T10:00:00+00:00")
    monkeypatch.setattr("src.notifications.email_sender.time.sleep", lambda seconds: None)

    call_count = {"n": 0}

    class _FlakySmtp:
        def __init__(self, *args, **kwargs):
            call_count["n"] += 1

        def __enter__(self):
            if call_count["n"] < 3:
                raise ConnectionError("transient network error")
            return MagicMock()

        def __exit__(self, *args):
            return False

    with patch("src.notifications.email_sender.smtplib.SMTP", _FlakySmtp):
        send_run_summary_email(summary, _FakeSettings(), max_attempts=3, backoff_seconds=0)

    assert call_count["n"] == 3


def test_send_run_summary_email_raises_after_exhausting_retries(monkeypatch):
    summary = DailyRunSummary(started_at="2026-08-21T10:00:00+00:00")
    monkeypatch.setattr("src.notifications.email_sender.time.sleep", lambda seconds: None)

    class _AlwaysFailsSmtp:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise ConnectionError("SMTP server unreachable")

        def __exit__(self, *args):
            return False

    with patch("src.notifications.email_sender.smtplib.SMTP", _AlwaysFailsSmtp):
        with pytest.raises(EmailSendError, match="SMTP server unreachable"):
            send_run_summary_email(summary, _FakeSettings(), max_attempts=2, backoff_seconds=0)

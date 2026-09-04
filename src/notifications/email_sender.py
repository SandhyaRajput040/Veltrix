"""
Sends the daily run summary email via SMTP.

Default assumption: Gmail SMTP (smtp.gmail.com:587, STARTTLS). Gmail
requires an "App Password" rather than your normal account password
once 2-factor authentication is enabled (which Google increasingly
requires) -- see README.md, Module 6 setup, for how to generate one.
Any other SMTP provider works too; just change SMTP_HOST/SMTP_PORT.

This module never raises on a genuine SMTP failure (wrong password,
network hiccup, etc.) after retries are exhausted -- a failed
notification must not be treated as if the whole day's pipeline run
failed. The caller (main.py) logs the failure and moves on; the
pipeline's own success/failure status is unaffected by whether the
email about it could be sent.
"""

import os
import smtplib
import time
from email.message import EmailMessage

from src.notifications.report_formatter import format_body, format_subject

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


class EmailSendError(Exception):
    """Raised when sending the notification email fails after all retries."""


def _build_message(summary, from_address: str, to_address: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = format_subject(summary)
    message["From"] = from_address
    message["To"] = to_address
    message.set_content(format_body(summary))

    for file_result in summary.file_results:
        if file_result.quarantine_csv_path and os.path.isfile(file_result.quarantine_csv_path):
            with open(file_result.quarantine_csv_path, "rb") as fh:
                content = fh.read()
            message.add_attachment(
                content,
                maintype="text",
                subtype="csv",
                filename=os.path.basename(file_result.quarantine_csv_path),
            )

    return message


def _send_via_smtp(message: EmailMessage, host: str, port: int, username: str, password: str) -> None:
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)


def send_run_summary_email(summary, settings, max_attempts: int = 3, backoff_seconds: int = 5) -> None:
    """
    Build and send the daily run summary email, attaching any
    per-file quarantine reports. Retries transient SMTP failures a
    few times before giving up; raises EmailSendError only after all
    attempts are exhausted, so the caller can decide how to log it
    without the pipeline's own result being affected.
    """
    if not settings.notification_email or not settings.smtp_username or not settings.smtp_password:
        raise EmailSendError(
            "Email notification is not fully configured. Set NOTIFICATION_EMAIL, "
            "SMTP_USERNAME, and SMTP_PASSWORD in .env (see README.md, Module 6 setup)."
        )

    host = settings.smtp_host or DEFAULT_SMTP_HOST
    port = settings.smtp_port or DEFAULT_SMTP_PORT
    message = _build_message(summary, from_address=settings.smtp_username, to_address=settings.notification_email)

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            _send_via_smtp(message, host, port, settings.smtp_username, settings.smtp_password)
            return
        except Exception as exc:  # noqa: BLE001 -- any SMTP/network failure should retry
            last_error = exc
            if attempt < max_attempts:
                time.sleep(backoff_seconds)

    raise EmailSendError(f"Failed to send notification email after {max_attempts} attempts: {last_error}")







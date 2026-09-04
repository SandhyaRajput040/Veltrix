"""
Veltrix - Baapstore -> Amazon daily stock sync automation.

Entry point. Running this script performs one full daily pipeline
pass:
    Google Drive sync -> validate & convert -> submit to Amazon (or
    fallback if AMAZON_FALLBACK_MODE=True)
    -> log the result -> email a summary

See src/scheduler/run_daily_job.py for the orchestration logic itself.
Logging is handled by src/notifications/logger.py (a rotating file,
replacing the old run_daily.bat text redirect). The email notification
is handled by src/notifications/email_sender.py and is sent
regardless of whether the run succeeded, partially failed, or failed
outright -- the whole point is never having to manually check.
"""

from src.config.settings import settings
from src.notifications.email_sender import EmailSendError, send_run_summary_email
from src.notifications.logger import get_logger
from src.scheduler.run_daily_job import run_daily_pipeline

logger = get_logger()


def main() -> None:
    logger.info(f"{settings.app_name} -- starting daily pipeline run")
    logger.info(f"Environment: {settings.environment}")

    result = run_daily_pipeline(settings)

    logger.info(f"Run started:  {result.started_at}")
    logger.info(f"Run finished: {result.finished_at}")
    logger.info(f"Overall status: {result.overall_status}")

    if result.fatal_error:
        logger.error(f"FATAL ERROR: {result.fatal_error}")

    logger.info(f"Files downloaded: {result.files_downloaded}")
    logger.info(f"Files skipped (already up to date): {result.files_skipped}")

    for file_result in result.file_results:
        logger.info(
            f"  {file_result.source_file}: read {file_result.rows_read}, "
            f"accepted {file_result.rows_accepted}, quarantined {file_result.rows_quarantined}, "
            f"mode={file_result.submission_mode}, error={file_result.error}"
        )

    try:
        send_run_summary_email(result, settings)
        logger.info(f"Notification email sent to {settings.notification_email}")
    except EmailSendError as exc:
        # A failed notification must never look like a failed pipeline
        # run (or vice versa) -- log it clearly and move on. The
        # run's own overall_status, logged above, is unaffected.
        logger.error(f"Failed to send notification email: {exc}")


if __name__ == "__main__":
    main()
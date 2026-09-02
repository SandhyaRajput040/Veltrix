"""
Veltrix - Baapstore -> Amazon daily stock sync automation.

Entry point. Running this script performs one full daily pipeline
pass:
    Google Drive sync -> validate & convert -> submit to Amazon (or
    fallback if AMAZON_FALLBACK_MODE=True)

See src/scheduler/run_daily_job.py for the orchestration logic itself
-- this file just wires it to the command line and prints a summary.
Module 6 will replace this printing with proper logging + email.
"""

from src.config.settings import settings
from src.scheduler.run_daily_job import run_daily_pipeline


def main() -> None:
    print(f"{settings.app_name} -- starting daily pipeline run")
    print(f"Environment: {settings.environment}")

    result = run_daily_pipeline(settings)

    print(f"Run started:  {result.started_at}")
    print(f"Run finished: {result.finished_at}")
    print(f"Overall status: {result.overall_status}")

    if result.fatal_error:
        print(f"FATAL ERROR: {result.fatal_error}")

    print(f"Files downloaded: {result.files_downloaded}")
    print(f"Files skipped (already up to date): {result.files_skipped}")

    for file_result in result.file_results:
        print(
            f"  {file_result.source_file}: read {file_result.rows_read}, "
            f"accepted {file_result.rows_accepted}, quarantined {file_result.rows_quarantined}, "
            f"mode={file_result.submission_mode}, error={file_result.error}"
        )


if __name__ == "__main__":
    main()
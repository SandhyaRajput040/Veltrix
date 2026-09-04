"""
Formats a Module 5 DailyRunSummary into an email subject and plain-text
body. Pure string-building, no I/O -- kept separate from email_sender.py
so the formatting logic can be tested without ever touching SMTP.
"""


def format_subject(summary) -> str:
    """
    e.g. "Veltrix Daily Sync -- SUCCESS -- 2026-08-21"
    Uses the date portion of started_at so the subject line is stable
    even if a run happens to straddle midnight.
    """
    date_part = summary.started_at.split("T")[0] if summary.started_at else "unknown-date"
    return f"Veltrix Daily Sync -- {summary.overall_status} -- {date_part}"


def format_body(summary) -> str:
    """
    Human-readable plain-text summary covering everything the project
    spec requires in the daily notification: files processed, rows
    read/accepted/quarantined, Amazon results, errors, and overall
    status.
    """
    lines = []
    lines.append("Veltrix Daily Run Summary")
    lines.append("=" * 25)
    lines.append(f"Status:  {summary.overall_status}")
    lines.append(f"Started:  {summary.started_at}")
    lines.append(f"Finished: {summary.finished_at}")
    lines.append("")

    if summary.fatal_error:
        lines.append(f"FATAL ERROR: {summary.fatal_error}")
        lines.append("")
        lines.append("No files were processed this run.")
        return "\n".join(lines)

    lines.append(f"Files downloaded: {summary.files_downloaded or 'none'}")
    lines.append(f"Files skipped (already up to date): {summary.files_skipped or 'none'}")
    lines.append("")

    if not summary.file_results:
        lines.append("No new/changed files to process.")
        return "\n".join(lines)

    lines.append("Per-file results:")
    lines.append("-" * 25)
    for file_result in summary.file_results:
        lines.append(f"{file_result.source_file}")
        lines.append(
            f"  Rows read: {file_result.rows_read}  |  "
            f"Accepted: {file_result.rows_accepted}  |  "
            f"Quarantined: {file_result.rows_quarantined}"
        )
        if file_result.submission_mode:
            lines.append(
                f"  Amazon submission mode: {file_result.submission_mode}  |  "
                f"Accepted by Amazon: {file_result.accepted_by_amazon}  |  "
                f"Invalid per Amazon: {file_result.invalid_by_amazon}"
            )
            if file_result.feed_ids:
                lines.append(f"  Feed ID(s): {', '.join(file_result.feed_ids)}")
        if file_result.error:
            lines.append(f"  ERROR: {file_result.error}")
        lines.append("")

    return "\n".join(lines)
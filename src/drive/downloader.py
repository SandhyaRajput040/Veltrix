"""
Orchestrates one Google Drive sync run:

  1. List every file in the Baapstore folder.
  2. Keep only files matching the filename patterns we care about.
  3. Compare each match's Drive `modifiedTime` against local state.
  4. Download files that are new or changed; skip files we already
     have the latest version of.
  5. Record the new modifiedTime in state -- but ONLY after a
     successful download, so a failed/partial download is retried
     next run instead of being silently marked "done".

This module never deletes or modifies anything in Baapstore's Drive
(the client uses a read-only scope) and never loses track of a file --
every file either ends up downloaded+recorded, or explicitly skipped
because it's already up to date.
"""

import fnmatch
import os
from dataclasses import dataclass, field
from typing import Dict, List

from src.drive.client import build_drive_service, download_file, list_files_in_folder
from src.drive.state import load_state, save_state

# The two Baapstore file patterns this pipeline tracks (see BUSINESS
# CONTEXT in the project spec). Filenames may carry extra suffixes or
# timestamps, hence the wildcard.
TRACKED_FILE_PATTERNS = [
    "Amazon_Bulk_Daily_Quantity_Update*.xlsx",
    "Amazon_Bulk_Full_Products_Quantity_Update*.xlsx",
]


@dataclass
class SyncResult:
    """Summary of one sync run, for logging/notifications later."""

    downloaded: List[str] = field(default_factory=list)  # local paths downloaded this run
    skipped: List[str] = field(default_factory=list)  # Drive filenames already up to date
    unmatched_ignored: int = 0  # files in the folder that matched no tracked pattern


def _matches_any_pattern(filename: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(filename, pattern) for pattern in patterns)


def sync_inventory_files(
    credentials_file: str,
    folder_id: str,
    download_dir: str,
    state_file: str,
) -> SyncResult:
    """
    Run one Drive sync pass and return a SyncResult describing what
    was downloaded vs skipped vs ignored.
    """
    service = build_drive_service(credentials_file)
    all_files = list_files_in_folder(service, folder_id)
    state = load_state(state_file)

    result = SyncResult()

    for drive_file in all_files:
        name = drive_file["name"]

        if not _matches_any_pattern(name, TRACKED_FILE_PATTERNS):
            result.unmatched_ignored += 1
            continue

        last_known = state.get(name, {})
        if last_known.get("modifiedTime") == drive_file["modifiedTime"]:
            result.skipped.append(name)
            continue

        destination_path = os.path.join(download_dir, name)
        download_file(service, drive_file["id"], destination_path)

        # Only mark this file "processed" after the download above
        # returned without raising. If it crashes mid-download, the
        # old state entry (or no entry) stays in place, so this file
        # gets retried on the next run instead of being skipped.
        state[name] = {
            "modifiedTime": drive_file["modifiedTime"],
            "file_id": drive_file["id"],
            "local_path": destination_path,
        }
        result.downloaded.append(destination_path)

    save_state(state_file, state)
    return result


if __name__ == "__main__":
    # Manual smoke-test entry point -- requires a real Google Cloud
    # service account and a real GOOGLE_DRIVE_FOLDER_ID in .env. See
    # the Module 2 setup steps in README.md before running this.
    from src.config.settings import settings

    run_result = sync_inventory_files(
        credentials_file=settings.google_drive_credentials_file,
        folder_id=settings.google_drive_folder_id,
        download_dir="data/input",
        state_file="state/drive_state.json",
    )
    print(f"Downloaded: {run_result.downloaded}")
    print(f"Skipped (already up to date): {run_result.skipped}")
    print(f"Ignored (no pattern match): {run_result.unmatched_ignored}")
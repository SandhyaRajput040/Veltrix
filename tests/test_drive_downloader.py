"""
Tests for src.drive.downloader

These test the actual sync DECISION LOGIC (which files get downloaded
vs skipped vs ignored, and how state gets updated) by mocking out the
Google Drive API calls entirely. This is the "documented mock" allowed
by the project's testing rules -- real Google Cloud credentials don't
exist yet (Module 2's manual Google Cloud setup is still pending), so
we cannot hit the real API in automated tests.

Once real credentials are available, `python -m src.drive.downloader`
(see the bottom of downloader.py) exercises the real API end to end as
a manual smoke test.
"""

import json
import os

from src.drive import downloader as downloader_module


def test_sync_downloads_new_tracked_files_and_ignores_unmatched(monkeypatch, tmp_path):
    """
    Given 3 files in the Drive folder where 2 match our tracked
    patterns and 1 doesn't, only the 2 matching files should be
    downloaded, and the unmatched one should be counted as ignored
    (never downloaded, never causes an error).
    """
    fake_drive_files = [
        {
            "id": "f1",
            "name": "Amazon_Bulk_Daily_Quantity_Update_2026-08-21.xlsx",
            "modifiedTime": "T1",
        },
        {
            "id": "f2",
            "name": "Amazon_Bulk_Full_Products_Quantity_Update.xlsx",
            "modifiedTime": "T2",
        },
        {"id": "f3", "name": "random_unrelated_file.xlsx", "modifiedTime": "T3"},
    ]

    monkeypatch.setattr(downloader_module, "build_drive_service", lambda creds: "FAKE_SERVICE")
    monkeypatch.setattr(
        downloader_module, "list_files_in_folder", lambda service, folder_id: fake_drive_files
    )

    downloaded_calls = []

    def fake_download_file(service, file_id, destination_path):
        downloaded_calls.append((file_id, destination_path))
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        with open(destination_path, "wb") as fh:
            fh.write(b"fake bytes")

    monkeypatch.setattr(downloader_module, "download_file", fake_download_file)

    state_file = str(tmp_path / "state.json")
    download_dir = str(tmp_path / "input")

    result = downloader_module.sync_inventory_files(
        credentials_file="unused-in-this-test",
        folder_id="FOLDER123",
        download_dir=download_dir,
        state_file=state_file,
    )

    assert len(result.downloaded) == 2
    assert len(downloaded_calls) == 2
    assert result.unmatched_ignored == 1
    assert result.skipped == []

    saved_state = json.loads(open(state_file).read())
    assert saved_state["Amazon_Bulk_Daily_Quantity_Update_2026-08-21.xlsx"]["modifiedTime"] == "T1"
    assert saved_state["Amazon_Bulk_Full_Products_Quantity_Update.xlsx"]["modifiedTime"] == "T2"
    assert "random_unrelated_file.xlsx" not in saved_state


def test_sync_skips_files_already_up_to_date(monkeypatch, tmp_path):
    """
    If a tracked file's modifiedTime in Drive matches what's already
    in state, it must be skipped -- never re-downloaded. This is the
    "running it again skips unchanged files" behaviour the project
    spec requires.
    """
    fake_drive_files = [
        {"id": "f1", "name": "Amazon_Bulk_Daily_Quantity_Update.xlsx", "modifiedTime": "T1"},
    ]
    monkeypatch.setattr(downloader_module, "build_drive_service", lambda creds: "FAKE_SERVICE")
    monkeypatch.setattr(
        downloader_module, "list_files_in_folder", lambda service, folder_id: fake_drive_files
    )

    download_calls = []
    monkeypatch.setattr(
        downloader_module, "download_file", lambda *a, **k: download_calls.append(a)
    )

    state_file = str(tmp_path / "state.json")
    os.makedirs(tmp_path, exist_ok=True)
    with open(state_file, "w") as fh:
        json.dump(
            {
                "Amazon_Bulk_Daily_Quantity_Update.xlsx": {
                    "modifiedTime": "T1",
                    "file_id": "f1",
                    "local_path": "data/input/Amazon_Bulk_Daily_Quantity_Update.xlsx",
                }
            },
            fh,
        )

    result = downloader_module.sync_inventory_files(
        credentials_file="unused",
        folder_id="FOLDER123",
        download_dir=str(tmp_path / "input"),
        state_file=state_file,
    )

    assert result.downloaded == []
    assert result.skipped == ["Amazon_Bulk_Daily_Quantity_Update.xlsx"]
    assert download_calls == []


def test_sync_redownloads_when_modified_time_changes(monkeypatch, tmp_path):
    """
    A file that already exists in state but whose Drive modifiedTime
    has changed (Baapstore updated it) must be re-downloaded, not
    skipped.
    """
    fake_drive_files = [
        {"id": "f1", "name": "Amazon_Bulk_Daily_Quantity_Update.xlsx", "modifiedTime": "T2"},
    ]
    monkeypatch.setattr(downloader_module, "build_drive_service", lambda creds: "FAKE_SERVICE")
    monkeypatch.setattr(
        downloader_module, "list_files_in_folder", lambda service, folder_id: fake_drive_files
    )

    download_calls = []

    def fake_download_file(service, file_id, destination_path):
        download_calls.append((file_id, destination_path))
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        with open(destination_path, "wb") as fh:
            fh.write(b"updated bytes")

    monkeypatch.setattr(downloader_module, "download_file", fake_download_file)

    state_file = str(tmp_path / "state.json")
    with open(state_file, "w") as fh:
        json.dump(
            {
                "Amazon_Bulk_Daily_Quantity_Update.xlsx": {
                    "modifiedTime": "T1",  # stale -- Drive now has T2
                    "file_id": "f1",
                    "local_path": "data/input/Amazon_Bulk_Daily_Quantity_Update.xlsx",
                }
            },
            fh,
        )

    result = downloader_module.sync_inventory_files(
        credentials_file="unused",
        folder_id="FOLDER123",
        download_dir=str(tmp_path / "input"),
        state_file=state_file,
    )

    assert len(download_calls) == 1
    assert result.downloaded != []
    assert result.skipped == []

    saved_state = json.loads(open(state_file).read())
    assert saved_state["Amazon_Bulk_Daily_Quantity_Update.xlsx"]["modifiedTime"] == "T2"


def test_filename_patterns_match_baapstore_suffixed_filenames():
    """
    Baapstore filenames may carry extra suffixes/timestamps (e.g. a
    date or version stamp before .xlsx) -- the pattern matcher must
    still recognise them as tracked files.
    """
    matching_names = [
        "Amazon_Bulk_Daily_Quantity_Update.xlsx",
        "Amazon_Bulk_Daily_Quantity_Update_2026-08-21.xlsx",
        "Amazon_Bulk_Full_Products_Quantity_Update.xlsx",
        "Amazon_Bulk_Full_Products_Quantity_Update (1).xlsx",
    ]
    non_matching_names = [
        "Amazon_Bulk_Daily_Quantity_Update.csv",  # wrong extension
        "random_report.xlsx",
        "Amazon_Bulk_Daily_Quantity_Update",  # no extension at all
    ]

    for name in matching_names:
        assert downloader_module._matches_any_pattern(
            name, downloader_module.TRACKED_FILE_PATTERNS
        ), f"Expected {name!r} to match a tracked pattern"

    for name in non_matching_names:
        assert not downloader_module._matches_any_pattern(
            name, downloader_module.TRACKED_FILE_PATTERNS
        ), f"Expected {name!r} to NOT match any tracked pattern"
        
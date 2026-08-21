"""
Tests for src.drive.client

We never call the real Google Drive API in tests -- there are no real
credentials yet (Module 2 setup is still pending on the Google Cloud
side). Instead we mock the `service` object at the same shape the real
googleapiclient `build("drive", "v3", ...)` object has, and verify our
code drives it correctly: the query string, pagination, and file
download loop.
"""

from unittest.mock import Mock

import pytest

from src.drive.client import build_drive_service, download_file, list_files_in_folder


def test_build_drive_service_raises_clear_error_if_credentials_file_missing(tmp_path):
    """
    A missing credentials file must fail with a clear, actionable
    error -- not a cryptic exception from deep inside google-auth.
    """
    missing_path = str(tmp_path / "does_not_exist.json")

    with pytest.raises(FileNotFoundError, match="credentials file not found"):
        build_drive_service(missing_path)


def test_list_files_in_folder_builds_correct_query_and_returns_files():
    """A single-page response should be parsed and the query scoped to the right folder."""
    fake_service = Mock()
    fake_service.files.return_value.list.return_value.execute.return_value = {
        "files": [
            {"id": "1", "name": "Amazon_Bulk_Daily_Quantity_Update.xlsx", "modifiedTime": "T1"}
        ]
        # no nextPageToken -> single page
    }

    result = list_files_in_folder(fake_service, "FOLDER123")

    assert result == [
        {"id": "1", "name": "Amazon_Bulk_Daily_Quantity_Update.xlsx", "modifiedTime": "T1"}
    ]
    called_kwargs = fake_service.files.return_value.list.call_args.kwargs
    assert called_kwargs["q"] == "'FOLDER123' in parents and trashed = false"


def test_list_files_in_folder_follows_pagination_across_multiple_pages():
    """Drive paginates results -- we must keep calling until nextPageToken is absent."""
    fake_service = Mock()
    fake_execute = fake_service.files.return_value.list.return_value.execute
    fake_execute.side_effect = [
        {
            "files": [{"id": "1", "name": "a.xlsx", "modifiedTime": "t1"}],
            "nextPageToken": "PAGE2",
        },
        {"files": [{"id": "2", "name": "b.xlsx", "modifiedTime": "t2"}]},
    ]

    result = list_files_in_folder(fake_service, "FOLDER123")

    assert [f["id"] for f in result] == ["1", "2"]
    assert fake_execute.call_count == 2


def test_download_file_writes_bytes_to_destination(monkeypatch, tmp_path):
    """download_file must actually write the downloaded bytes to disk."""

    class FakeMediaDownload:
        """Stand-in for googleapiclient.http.MediaIoBaseDownload."""

        def __init__(self, file_handle, request):
            self.file_handle = file_handle
            self.request = request

        def next_chunk(self):
            self.file_handle.write(b"fake xlsx bytes")
            return None, True  # (status, done) -- done after one chunk

    monkeypatch.setattr("src.drive.client.MediaIoBaseDownload", FakeMediaDownload)

    fake_service = Mock()
    fake_request = Mock()
    fake_service.files.return_value.get_media.return_value = fake_request

    destination = tmp_path / "nested" / "downloaded.xlsx"
    download_file(fake_service, "file123", str(destination))

    assert destination.exists()
    assert destination.read_bytes() == b"fake xlsx bytes"
    fake_service.files.return_value.get_media.assert_called_once_with(fileId="file123")
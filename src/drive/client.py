"""
Thin wrapper around the Google Drive API v3, authenticated as a
service account.

This module ONLY knows how to authenticate, list files in a folder,
and download a file's bytes to disk. It has no opinion about which
files are "new" or "already processed" -- that decision belongs to
downloader.py + state.py. Keeping this separation means the Drive API
details can change without touching the sync logic, and the sync logic
can be tested without ever calling Google.
"""

import io
import os
from typing import Dict, List

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Read-only scope is intentional: this automation only ever lists and
# downloads files from Baapstore's folder. It never creates, edits, or
# deletes anything in their Drive.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def build_drive_service(credentials_file: str):
    """
    Authenticate as the service account described by `credentials_file`
    (the JSON key downloaded from Google Cloud Console) and return an
    authorized Drive API client.
    """
    if not credentials_file or not os.path.isfile(credentials_file):
        raise FileNotFoundError(
            f"Google service-account credentials file not found: {credentials_file!r}. "
            "Set GOOGLE_DRIVE_CREDENTIALS_FILE in .env to the path of your "
            "downloaded service-account JSON key (see README.md, Module 2 setup)."
        )

    credentials = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def list_files_in_folder(service, folder_id: str) -> List[Dict]:
    """
    Return every non-trashed file directly inside `folder_id`, with
    just the fields the rest of the pipeline needs: id, name,
    modifiedTime. Does NOT filter by filename pattern -- that's the
    caller's job (see downloader.py).
    """
    files: List[Dict] = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"

    while True:
        response = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, modifiedTime)",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return files


def download_file(service, file_id: str, destination_path: str) -> None:
    """Download a Drive file's bytes to `destination_path`, in chunks."""
    request = service.files().get_media(fileId=file_id)
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)

    with io.FileIO(destination_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
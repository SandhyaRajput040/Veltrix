"""
Thin wrapper around the SP-API Feeds API (v2021-06-30).

Mirrors src/drive/client.py's philosophy: this module ONLY knows how
to make the individual HTTP calls (create a feed document, upload
content to it, submit the feed, poll its status, fetch the result
document). It has no opinion about retry/poll timing or what the feed
content should contain -- that's submitter.py's and feed_builder.py's
job respectively. Keeping this separation makes the orchestration
logic testable without ever making a real HTTP call.
"""

import gzip

import requests

USER_AGENT = "Veltrix/1.0 (Language=Python)"


class SpApiError(Exception):
    """Raised when an SP-API call returns an unexpected status code."""


def _headers(access_token: str, content_type: str = "application/json") -> dict:
    return {
        "x-amz-access-token": access_token,
        "content-type": content_type,
        "user-agent": USER_AGENT,
    }


def create_feed_document(access_token: str, endpoint: str) -> dict:
    """
    Ask Amazon for a place to upload feed content. Returns a dict with
    at least "feedDocumentId" and "url" (a presigned upload URL).
    """
    response = requests.post(
        f"{endpoint}/feeds/2021-06-30/documents",
        headers=_headers(access_token),
        json={"contentType": "application/json; charset=UTF-8"},
        timeout=30,
    )
    if response.status_code != 201:
        raise SpApiError(f"createFeedDocument failed ({response.status_code}): {response.text}")
    return response.json()


def upload_feed_document(upload_url: str, content: bytes, content_type: str) -> None:
    """
    Upload the actual feed content to the presigned URL from
    create_feed_document. This is a direct PUT to Amazon's storage,
    NOT an SP-API call -- no access token or SP-API headers involved.
    """
    response = requests.put(
        upload_url,
        data=content,
        headers={"Content-Type": content_type},
        timeout=120,
    )
    if response.status_code not in (200, 201, 204):
        raise SpApiError(f"Feed document upload failed ({response.status_code}): {response.text}")


def create_feed(
    access_token: str,
    endpoint: str,
    feed_type: str,
    marketplace_ids: list,
    input_feed_document_id: str,
) -> str:
    """Submit the feed for processing. Returns the new feed's feedId."""
    response = requests.post(
        f"{endpoint}/feeds/2021-06-30/feeds",
        headers=_headers(access_token),
        json={
            "feedType": feed_type,
            "marketplaceIds": marketplace_ids,
            "inputFeedDocumentId": input_feed_document_id,
        },
        timeout=30,
    )
    if response.status_code != 202:
        raise SpApiError(f"createFeed failed ({response.status_code}): {response.text}")
    return response.json()["feedId"]


def get_feed(access_token: str, endpoint: str, feed_id: str) -> dict:
    """
    Check a feed's processing status. Returns the full feed object,
    including "processingStatus" (IN_QUEUE / IN_PROGRESS / DONE /
    CANCELLED / FATAL) and, once DONE, "resultFeedDocumentId".
    """
    response = requests.get(
        f"{endpoint}/feeds/2021-06-30/feeds/{feed_id}",
        headers=_headers(access_token),
        timeout=30,
    )
    if response.status_code != 200:
        raise SpApiError(f"getFeed failed ({response.status_code}): {response.text}")
    return response.json()


def get_feed_document(access_token: str, endpoint: str, feed_document_id: str) -> dict:
    """Get metadata (including a download URL) for a feed's result document."""
    response = requests.get(
        f"{endpoint}/feeds/2021-06-30/documents/{feed_document_id}",
        headers=_headers(access_token),
        timeout=30,
    )
    if response.status_code != 200:
        raise SpApiError(f"getFeedDocument failed ({response.status_code}): {response.text}")
    return response.json()


def download_feed_document(download_url: str, compression_algorithm: str = None) -> str:
    """
    Download the actual result document content from the URL returned
    by get_feed_document. This is a direct GET, not an SP-API call.
    Decompresses GZIP content automatically if Amazon compressed it.
    """
    response = requests.get(download_url, timeout=60)
    if response.status_code != 200:
        raise SpApiError(f"Feed document download failed ({response.status_code})")

    content = response.content
    if compression_algorithm == "GZIP":
        content = gzip.decompress(content)

    return content.decode("utf-8")
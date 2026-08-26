"""
Tests for src.amazon.client

Mocks requests.post/put/get -- there's no real Amazon SP-API access
yet. Verifies each function sends the right request shape and handles
both success and failure status codes correctly.
"""

from unittest.mock import Mock, patch

import pytest

from src.amazon.client import (
    SpApiError,
    create_feed,
    create_feed_document,
    download_feed_document,
    get_feed,
    get_feed_document,
    upload_feed_document,
)


def test_create_feed_document_returns_response_body_on_success():
    fake_response = Mock()
    fake_response.status_code = 201
    fake_response.json.return_value = {"feedDocumentId": "doc-123", "url": "https://upload.example.com"}

    with patch("src.amazon.client.requests.post", return_value=fake_response) as mock_post:
        result = create_feed_document("access-token", "https://endpoint.example.com")

    assert result == {"feedDocumentId": "doc-123", "url": "https://upload.example.com"}
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["x-amz-access-token"] == "access-token"


def test_create_feed_document_raises_on_error_status():
    fake_response = Mock()
    fake_response.status_code = 403
    fake_response.text = "Forbidden"

    with patch("src.amazon.client.requests.post", return_value=fake_response):
        with pytest.raises(SpApiError, match="403"):
            create_feed_document("access-token", "https://endpoint.example.com")


def test_upload_feed_document_succeeds_on_200():
    fake_response = Mock()
    fake_response.status_code = 200

    with patch("src.amazon.client.requests.put", return_value=fake_response) as mock_put:
        upload_feed_document("https://upload.example.com", b'{"some": "content"}', "application/json")

    call_kwargs = mock_put.call_args.kwargs
    assert call_kwargs["data"] == b'{"some": "content"}'
    assert call_kwargs["headers"]["Content-Type"] == "application/json"


def test_upload_feed_document_raises_on_error_status():
    fake_response = Mock()
    fake_response.status_code = 500
    fake_response.text = "Internal error"

    with patch("src.amazon.client.requests.put", return_value=fake_response):
        with pytest.raises(SpApiError, match="500"):
            upload_feed_document("https://upload.example.com", b"content", "application/json")


def test_create_feed_returns_feed_id():
    fake_response = Mock()
    fake_response.status_code = 202
    fake_response.json.return_value = {"feedId": "feed-456"}

    with patch("src.amazon.client.requests.post", return_value=fake_response) as mock_post:
        feed_id = create_feed(
            "access-token", "https://endpoint.example.com", "JSON_LISTINGS_FEED", ["MKT1"], "doc-123"
        )

    assert feed_id == "feed-456"
    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["feedType"] == "JSON_LISTINGS_FEED"
    assert sent_body["marketplaceIds"] == ["MKT1"]
    assert sent_body["inputFeedDocumentId"] == "doc-123"


def test_get_feed_returns_full_feed_object():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"feedId": "feed-456", "processingStatus": "DONE"}

    with patch("src.amazon.client.requests.get", return_value=fake_response):
        feed = get_feed("access-token", "https://endpoint.example.com", "feed-456")

    assert feed["processingStatus"] == "DONE"


def test_get_feed_document_returns_download_metadata():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"url": "https://download.example.com", "compressionAlgorithm": "GZIP"}

    with patch("src.amazon.client.requests.get", return_value=fake_response):
        doc = get_feed_document("access-token", "https://endpoint.example.com", "result-doc-1")

    assert doc["compressionAlgorithm"] == "GZIP"


def test_download_feed_document_decodes_plain_text():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.content = b'{"results": []}'

    with patch("src.amazon.client.requests.get", return_value=fake_response):
        text = download_feed_document("https://download.example.com")

    assert text == '{"results": []}'


def test_download_feed_document_decompresses_gzip():
    import gzip

    original_text = '{"results": [{"sku": "A"}]}'
    compressed = gzip.compress(original_text.encode("utf-8"))

    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.content = compressed

    with patch("src.amazon.client.requests.get", return_value=fake_response):
        text = download_feed_document("https://download.example.com", compression_algorithm="GZIP")

    assert text == original_text
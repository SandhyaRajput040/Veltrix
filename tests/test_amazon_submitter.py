"""
Tests for src.amazon.submitter

Fallback mode is tested against real file I/O (no Amazon involved at
all, so no mocking needed -- this is the safest mode and should be
verified as literally as possible).

Live mode is tested entirely with mocks, since no real Amazon SP-API
access exists yet for this project (Amazon self-authorization is a
manual step the project owner does outside this codebase).
"""

import json
import os
from unittest.mock import patch

import pytest

from src.amazon import submitter as submitter_module
from src.amazon.submitter import (
    SubmissionError,
    submit_fallback,
    submit_live,
    wait_for_feed_completion,
)


def _row(sku, quantity):
    return {"sku": sku, "quantity": str(quantity), "leadtime-to-ship": "", "fulfillment-channel": ""}


# ---------------------------------------------------------------------------
# Fallback mode
# ---------------------------------------------------------------------------


def test_submit_fallback_writes_feed_batch_files_and_never_calls_amazon(tmp_path):
    rows = [_row("SKU-1", 10), _row("SKU-2", 5)]
    output_dir = str(tmp_path / "ready_to_upload")

    result = submit_fallback(
        rows, seller_id="SELLER1", product_types={}, output_dir=output_dir, source_name="daily_update"
    )

    assert result.mode == "fallback"
    assert result.total_messages == 2
    assert len(result.output_paths) == 1
    assert os.path.isfile(result.output_paths[0])

    written_content = json.loads(open(result.output_paths[0]).read())
    assert len(written_content["messages"]) == 2
    assert written_content["header"]["sellerId"] == "SELLER1"


def test_submit_fallback_never_reports_accepted_or_feed_ids():
    """Fallback mode must never look like a real submission happened."""
    rows = [_row("SKU-1", 10)]
    result = submit_fallback(rows, "SELLER1", {}, "/tmp/does_not_matter_unused", "test")

    assert result.feed_ids == []
    assert result.total_accepted == 0
    assert result.total_invalid == 0


# ---------------------------------------------------------------------------
# wait_for_feed_completion
# ---------------------------------------------------------------------------


def test_wait_for_feed_completion_returns_once_done(monkeypatch):
    responses = [
        {"processingStatus": "IN_QUEUE"},
        {"processingStatus": "IN_PROGRESS"},
        {"processingStatus": "DONE", "resultFeedDocumentId": "result-1"},
    ]
    call_count = {"n": 0}

    def fake_get_feed(access_token, endpoint, feed_id):
        response = responses[call_count["n"]]
        call_count["n"] += 1
        return response

    monkeypatch.setattr(submitter_module, "get_feed", fake_get_feed)
    monkeypatch.setattr(submitter_module.time, "sleep", lambda seconds: None)

    result = wait_for_feed_completion("token", "https://endpoint", "feed-1", poll_interval_seconds=0)

    assert result["processingStatus"] == "DONE"
    assert call_count["n"] == 3


def test_wait_for_feed_completion_raises_if_never_finishes(monkeypatch):
    monkeypatch.setattr(
        submitter_module, "get_feed", lambda *a, **k: {"processingStatus": "IN_PROGRESS"}
    )
    monkeypatch.setattr(submitter_module.time, "sleep", lambda seconds: None)

    with pytest.raises(SubmissionError, match="did not reach a terminal status"):
        wait_for_feed_completion("token", "https://endpoint", "feed-1", max_poll_attempts=3)


def test_wait_for_feed_completion_returns_fatal_status_without_raising(monkeypatch):
    """FATAL is a terminal status -- the caller decides how to report it, this function just returns it."""
    monkeypatch.setattr(submitter_module, "get_feed", lambda *a, **k: {"processingStatus": "FATAL"})
    monkeypatch.setattr(submitter_module.time, "sleep", lambda seconds: None)

    result = wait_for_feed_completion("token", "https://endpoint", "feed-1")
    assert result["processingStatus"] == "FATAL"


# ---------------------------------------------------------------------------
# submit_live (fully mocked -- no real Amazon access exists yet)
# ---------------------------------------------------------------------------


def test_submit_live_happy_path(monkeypatch, tmp_path):
    rows = [_row("SKU-1", 10)]

    monkeypatch.setattr(submitter_module, "get_access_token", lambda *a, **k: "fake-token")
    monkeypatch.setattr(submitter_module, "get_product_types", lambda *a, **k: {"SKU-1": "LUGGAGE"})
    monkeypatch.setattr(
        submitter_module,
        "create_feed_document",
        lambda *a, **k: {"feedDocumentId": "doc-1", "url": "https://upload.example.com"},
    )
    monkeypatch.setattr(submitter_module, "upload_feed_document", lambda *a, **k: None)
    monkeypatch.setattr(submitter_module, "create_feed", lambda *a, **k: "feed-1")
    monkeypatch.setattr(
        submitter_module,
        "get_feed",
        lambda *a, **k: {"processingStatus": "DONE", "resultFeedDocumentId": "result-doc-1"},
    )
    monkeypatch.setattr(
        submitter_module,
        "get_feed_document",
        lambda *a, **k: {"url": "https://download.example.com", "compressionAlgorithm": None},
    )
    monkeypatch.setattr(
        submitter_module,
        "download_feed_document",
        lambda *a, **k: json.dumps({"results": [{"sku": "SKU-1", "status": "ACCEPTED"}]}),
    )

    result = submit_live(
        rows,
        client_id="cid",
        client_secret="secret",
        refresh_token="refresh",
        seller_id="SELLER1",
        marketplace_id="MKT1",
        endpoint="https://endpoint.example.com",
        product_type_cache_file=str(tmp_path / "cache.json"),
    )

    assert result.mode == "live"
    assert result.feed_ids == ["feed-1"]
    assert result.total_accepted == 1
    assert result.total_invalid == 0


def test_submit_live_raises_if_feed_ends_fatal(monkeypatch, tmp_path):
    rows = [_row("SKU-1", 10)]

    monkeypatch.setattr(submitter_module, "get_access_token", lambda *a, **k: "fake-token")
    monkeypatch.setattr(submitter_module, "get_product_types", lambda *a, **k: {"SKU-1": "LUGGAGE"})
    monkeypatch.setattr(
        submitter_module,
        "create_feed_document",
        lambda *a, **k: {"feedDocumentId": "doc-1", "url": "https://upload.example.com"},
    )
    monkeypatch.setattr(submitter_module, "upload_feed_document", lambda *a, **k: None)
    monkeypatch.setattr(submitter_module, "create_feed", lambda *a, **k: "feed-1")
    monkeypatch.setattr(submitter_module, "get_feed", lambda *a, **k: {"processingStatus": "FATAL"})

    with pytest.raises(SubmissionError, match="FATAL"):
        submit_live(
            rows,
            client_id="cid",
            client_secret="secret",
            refresh_token="refresh",
            seller_id="SELLER1",
            marketplace_id="MKT1",
            endpoint="https://endpoint.example.com",
            product_type_cache_file=str(tmp_path / "cache.json"),
        )


# ---------------------------------------------------------------------------
# submit_based_on_settings (the single fallback-vs-live decision point)
# ---------------------------------------------------------------------------


class _FakeSettings:
    def __init__(self, fallback_mode):
        self.amazon_fallback_mode = fallback_mode
        self.amazon_seller_id = "SELLER1"
        self.amazon_lwa_client_id = "cid"
        self.amazon_lwa_client_secret = "secret"
        self.amazon_refresh_token = "refresh"
        self.amazon_marketplace_id = "MKT1"
        self.amazon_sp_api_endpoint = "https://endpoint.example.com"


def test_submit_based_on_settings_uses_fallback_when_flag_is_true(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = [_row("SKU-1", 10)]
    settings = _FakeSettings(fallback_mode=True)

    result = submitter_module.submit_based_on_settings(rows, "source_name", settings)

    assert result.mode == "fallback"


def test_submit_based_on_settings_uses_live_when_flag_is_false(monkeypatch, tmp_path):
    rows = [_row("SKU-1", 10)]
    settings = _FakeSettings(fallback_mode=False)

    monkeypatch.setattr(submitter_module, "get_access_token", lambda *a, **k: "fake-token")
    monkeypatch.setattr(submitter_module, "get_product_types", lambda *a, **k: {"SKU-1": "LUGGAGE"})
    monkeypatch.setattr(
        submitter_module,
        "create_feed_document",
        lambda *a, **k: {"feedDocumentId": "doc-1", "url": "https://upload.example.com"},
    )
    monkeypatch.setattr(submitter_module, "upload_feed_document", lambda *a, **k: None)
    monkeypatch.setattr(submitter_module, "create_feed", lambda *a, **k: "feed-1")
    monkeypatch.setattr(
        submitter_module,
        "get_feed",
        lambda *a, **k: {"processingStatus": "DONE", "resultFeedDocumentId": "result-doc-1"},
    )
    monkeypatch.setattr(
        submitter_module,
        "get_feed_document",
        lambda *a, **k: {"url": "https://download.example.com", "compressionAlgorithm": None},
    )
    monkeypatch.setattr(
        submitter_module,
        "download_feed_document",
        lambda *a, **k: json.dumps({"results": [{"sku": "SKU-1", "status": "ACCEPTED"}]}),
    )

    result = submitter_module.submit_based_on_settings(rows, "source_name", settings)

    assert result.mode == "live"
    assert result.feed_ids == ["feed-1"]
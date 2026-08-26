"""
Tests for src.amazon.report_parser
"""

import json

import pytest

from src.amazon.report_parser import parse_feed_result


def test_parses_accepted_and_invalid_results():
    document = json.dumps(
        {
            "results": [
                {"messageId": 1, "sku": "SKU-1", "status": "ACCEPTED"},
                {
                    "messageId": 2,
                    "sku": "SKU-2",
                    "status": "INVALID",
                    "issues": [{"code": "4005", "message": "Invalid quantity", "severity": "ERROR"}],
                },
            ]
        }
    )

    summary = parse_feed_result(document)

    assert summary.total == 2
    assert summary.accepted == 1
    assert summary.invalid == 1
    assert summary.sku_results[1].sku == "SKU-2"
    assert summary.sku_results[1].issues[0]["code"] == "4005"


def test_empty_results_list_is_valid():
    document = json.dumps({"results": []})
    summary = parse_feed_result(document)

    assert summary.total == 0
    assert summary.accepted == 0
    assert summary.invalid == 0


def test_raises_on_invalid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_feed_result("{not valid json")


def test_raises_when_results_field_is_entirely_missing():
    document = json.dumps({"unexpectedShape": True})
    with pytest.raises(ValueError, match="no 'results' field"):
        parse_feed_result(document)
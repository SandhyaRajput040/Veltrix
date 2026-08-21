"""
Tests for src.drive.state

Verifies the local JSON state file actually round-trips data correctly,
handles a missing/first-run file, and fails loudly on corruption
instead of silently discarding it.
"""

import json
import os

import pytest

from src.drive.state import load_state, save_state


def test_load_state_returns_empty_dict_when_file_missing(tmp_path):
    """First-ever run: no state file exists yet -- that's not an error."""
    missing_path = str(tmp_path / "does_not_exist.json")
    assert load_state(missing_path) == {}


def test_load_state_returns_empty_dict_when_file_is_empty(tmp_path):
    """An empty (zero-byte) state file should behave like 'no state yet', not crash."""
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("")
    assert load_state(str(empty_file)) == {}


def test_save_then_load_roundtrip(tmp_path):
    """Whatever we save must come back identical when loaded again."""
    state_file = str(tmp_path / "state.json")
    original_state = {
        "Amazon_Bulk_Daily_Quantity_Update.xlsx": {
            "modifiedTime": "2026-08-20T10:00:00.000Z",
            "file_id": "abc123",
            "local_path": "data/input/Amazon_Bulk_Daily_Quantity_Update.xlsx",
        }
    }

    save_state(state_file, original_state)
    loaded_state = load_state(state_file)

    assert loaded_state == original_state


def test_save_state_creates_parent_directory(tmp_path):
    """save_state must not require the caller to pre-create the folder."""
    nested_path = str(tmp_path / "nested" / "dir" / "state.json")

    save_state(nested_path, {"key": {"modifiedTime": "t1"}})

    assert os.path.isfile(nested_path)
    assert json.loads(open(nested_path).read()) == {"key": {"modifiedTime": "t1"}}


def test_load_state_raises_on_corrupt_json(tmp_path):
    """
    Corrupt state must fail loudly, not be silently treated as 'nothing
    downloaded yet' -- that would cause every file to be re-downloaded
    without the operator ever finding out why.
    """
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{not valid json,,,")

    with pytest.raises(ValueError):
        load_state(str(corrupt_file))
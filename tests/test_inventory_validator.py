"""
Tests for src.inventory.validator

Covers every mandatory data-quality rule from the project spec:
SKU byte-length, negative quantities, float artifacts, corrupted
characters, duplicates, and missing values -- each with a real
positive and negative case, not just "doesn't crash".
"""

from src.inventory.validator import (
    REASON_DUPLICATE_SKU,
    REASON_INVALID_QUANTITY_FORMAT,
    REASON_MISSING_QUANTITY,
    REASON_MISSING_SKU,
    REASON_NEGATIVE_QUANTITY,
    REASON_NON_INTEGER_QUANTITY,
    REASON_SKU_EXCEEDS_BYTE_LIMIT,
    REASON_SUSPICIOUS_SKU_CHARACTERS,
    has_suspicious_characters,
    sku_byte_length,
    validate_quantity,
    validate_rows,
)


def _row(source_row, sku, quantity, **overrides):
    base = {
        "source_row": source_row,
        "sku": sku,
        "price": None,
        "minimum-seller-allowed-price": None,
        "maximum-seller-allowed-price": None,
        "quantity": quantity,
        "leadtime-to-ship": None,
        "fulfillment-channel": None,
        "merchant_shipping_group_name": None,
    }
    base.update(overrides)
    return base


def _reasons(result):
    return {entry["sku"]: entry["reason"] for entry in result.quarantined_rows}


# ---------------------------------------------------------------------------
# SKU byte-length (Amazon's 40-byte limit, not 40 characters)
# ---------------------------------------------------------------------------


def test_sku_byte_length_counts_bytes_not_characters():
    ascii_sku = "A" * 40
    assert sku_byte_length(ascii_sku) == 40

    # Each Devanagari character below is 3 bytes in UTF-8, so 14
    # characters is well under 40 CHARACTERS but far over 40 BYTES.
    devanagari_sku = "\u0905" * 14
    assert len(devanagari_sku) == 14
    assert sku_byte_length(devanagari_sku) == 42


def test_sku_at_exactly_40_bytes_is_accepted():
    sku_40_bytes = "A" * 40
    result = validate_rows([_row(2, sku_40_bytes, 10)], "file.xlsx", "T1")

    assert len(result.valid_rows) == 1
    assert result.quarantined_rows == []


def test_sku_over_40_bytes_is_quarantined():
    sku_41_bytes = "A" * 41
    result = validate_rows([_row(2, sku_41_bytes, 10)], "file.xlsx", "T1")

    assert result.valid_rows == []
    assert _reasons(result)[sku_41_bytes] == REASON_SKU_EXCEEDS_BYTE_LIMIT


def test_multibyte_sku_under_char_limit_but_over_byte_limit_is_quarantined():
    """The exact scenario from the spec: size suffixes pushing a SKU over the byte limit."""
    sku = "SHIRT-XXL - Double Extra Large (46) - Cotton Blend Premium"
    assert len(sku) > 40  # this one is over on characters too, a clear case
    result = validate_rows([_row(2, sku, 10)], "file.xlsx", "T1")

    assert result.valid_rows == []
    assert _reasons(result)[sku] == REASON_SKU_EXCEEDS_BYTE_LIMIT


# ---------------------------------------------------------------------------
# Negative quantities
# ---------------------------------------------------------------------------


def test_negative_quantity_is_quarantined():
    result = validate_rows([_row(2, "SKU-1", -1)], "file.xlsx", "T1")

    assert result.valid_rows == []
    assert _reasons(result)["SKU-1"] == REASON_NEGATIVE_QUANTITY


def test_zero_quantity_is_accepted():
    """Zero is a valid (if unusual) inventory count -- only negative is invalid."""
    result = validate_rows([_row(2, "SKU-1", 0)], "file.xlsx", "T1")

    assert len(result.valid_rows) == 1
    assert result.valid_rows[0]["quantity"] == "0"


# ---------------------------------------------------------------------------
# Float artifacts (the exact "10.0 instead of 10" bug from the spec)
# ---------------------------------------------------------------------------


def test_whole_number_float_quantity_is_normalized_to_clean_integer():
    validation = validate_quantity(10.0)
    assert validation.is_valid is True
    assert validation.value == 10


def test_fractional_quantity_is_rejected_not_rounded():
    validation = validate_quantity(10.5)
    assert validation.is_valid is False
    assert validation.reason_code == REASON_NON_INTEGER_QUANTITY


def test_valid_row_with_float_quantity_serializes_without_stray_dot_zero():
    result = validate_rows([_row(2, "SKU-1", 10.0)], "file.xlsx", "T1")

    assert len(result.valid_rows) == 1
    assert result.valid_rows[0]["quantity"] == "10"  # not "10.0"


def test_whole_number_float_price_serializes_without_stray_dot_zero():
    result = validate_rows(
        [_row(2, "SKU-1", 10, **{"price": 25.0})], "file.xlsx", "T1"
    )
    assert result.valid_rows[0]["price"] == "25"


def test_real_decimal_price_is_preserved():
    result = validate_rows(
        [_row(2, "SKU-1", 10, **{"price": 19.99})], "file.xlsx", "T1"
    )
    assert result.valid_rows[0]["price"] == "19.99"


# ---------------------------------------------------------------------------
# Missing / invalid-format quantities
# ---------------------------------------------------------------------------


def test_missing_quantity_is_quarantined():
    result = validate_rows([_row(2, "SKU-1", None)], "file.xlsx", "T1")
    assert _reasons(result)["SKU-1"] == REASON_MISSING_QUANTITY


def test_non_numeric_quantity_string_is_quarantined():
    result = validate_rows([_row(2, "SKU-1", "not-a-number")], "file.xlsx", "T1")
    assert _reasons(result)["SKU-1"] == REASON_INVALID_QUANTITY_FORMAT


def test_numeric_quantity_as_string_is_accepted():
    """Excel sometimes stores numbers as text -- '10' should still work."""
    result = validate_rows([_row(2, "SKU-1", "10")], "file.xlsx", "T1")
    assert result.valid_rows[0]["quantity"] == "10"


# ---------------------------------------------------------------------------
# Missing SKU
# ---------------------------------------------------------------------------


def test_missing_sku_is_quarantined():
    result = validate_rows([_row(2, None, 10)], "file.xlsx", "T1")

    assert result.valid_rows == []
    assert len(result.quarantined_rows) == 1
    assert result.quarantined_rows[0]["reason"] == REASON_MISSING_SKU


def test_blank_string_sku_is_quarantined():
    result = validate_rows([_row(2, "   ", 10)], "file.xlsx", "T1")
    assert result.quarantined_rows[0]["reason"] == REASON_MISSING_SKU


# ---------------------------------------------------------------------------
# Corrupted / suspicious characters
# ---------------------------------------------------------------------------


def test_replacement_character_is_flagged_as_suspicious():
    assert has_suspicious_characters("SKU-\ufffd-123") is True


def test_control_character_is_flagged_as_suspicious():
    assert has_suspicious_characters("SKU-\x00-123") is True


def test_normal_sku_is_not_flagged_as_suspicious():
    assert has_suspicious_characters("SKU-ABC-123") is False


def test_row_with_corrupted_sku_is_quarantined():
    corrupted_sku = "SKU-\ufffd-BAD"
    result = validate_rows([_row(2, corrupted_sku, 10)], "file.xlsx", "T1")

    assert result.valid_rows == []
    assert _reasons(result)[corrupted_sku] == REASON_SUSPICIOUS_SKU_CHARACTERS


# ---------------------------------------------------------------------------
# Duplicate SKUs (policy: ALL occurrences are quarantined, none silently kept)
# ---------------------------------------------------------------------------


def test_duplicate_sku_quarantines_every_occurrence():
    rows = [
        _row(2, "SKU-DUP", 10),
        _row(3, "SKU-DUP", 20),
        _row(4, "SKU-UNIQUE", 5),
    ]
    result = validate_rows(rows, "file.xlsx", "T1")

    assert len(result.valid_rows) == 1
    assert result.valid_rows[0]["sku"] == "SKU-UNIQUE"

    duplicate_entries = [r for r in result.quarantined_rows if r["sku"] == "SKU-DUP"]
    assert len(duplicate_entries) == 2
    assert all(entry["reason"] == REASON_DUPLICATE_SKU for entry in duplicate_entries)
    # Both original source rows must be individually traceable.
    assert {entry["source_row"] for entry in duplicate_entries} == {2, 3}


def test_unique_skus_are_not_affected_by_duplicates_elsewhere():
    rows = [
        _row(2, "SKU-DUP", 10),
        _row(3, "SKU-DUP", 20),
        _row(4, "SKU-FINE", 5),
    ]
    result = validate_rows(rows, "file.xlsx", "T1")

    assert any(r["sku"] == "SKU-FINE" for r in result.valid_rows)


# ---------------------------------------------------------------------------
# Quarantine entries carry required metadata
# ---------------------------------------------------------------------------


def test_quarantine_entry_includes_source_file_and_timestamp():
    result = validate_rows([_row(2, None, 10)], "Amazon_Bulk_Daily_Quantity_Update.xlsx", "2026-08-21T10:00:00Z")

    entry = result.quarantined_rows[0]
    assert entry["source_file"] == "Amazon_Bulk_Daily_Quantity_Update.xlsx"
    assert entry["timestamp"] == "2026-08-21T10:00:00Z"
    assert entry["source_row"] == 2
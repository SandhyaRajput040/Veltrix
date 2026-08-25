"""
Validates raw inventory rows against the mandatory data-quality rules:
  - SKU must be present, <= 40 BYTES (not characters), and free of
    suspicious/corrupted characters.
  - SKU must not be a duplicate within the source file.
  - Quantity must be present, a whole number, and >= 0.
  - Numeric fields (price, min/max price, leadtime) are cleaned so a
    whole-number float (10.0) never survives into the output as
    "10.0" -- see schema.py's docstring and the project's float-
    artifact rule.

Every row that fails any rule is quarantined with a short machine-
readable reason code and a human-readable explanation -- never
silently dropped, never silently "fixed" and uploaded.

DUPLICATE SKU POLICY (documented decision, per project spec section
10): when a SKU appears more than once in the same source file, we do
NOT guess which occurrence is "correct" and keep it. ALL occurrences
of that SKU are quarantined. This is the safe default: picking one
occurrence over another risks uploading the wrong quantity for that
SKU. If a future run needs different behaviour (e.g. "keep the last
occurrence"), that must be an explicit, separately-documented change.
"""

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.inventory.schema import MAX_SKU_BYTES

# Short, stable, machine-readable codes for the quarantine report's
# "reason" column. Keep these stable -- other tooling (or a human
# skimming quarantine_report.csv) may come to rely on exact spelling.
REASON_MISSING_SKU = "missing_sku"
REASON_DUPLICATE_SKU = "duplicate_sku"
REASON_SKU_EXCEEDS_BYTE_LIMIT = "sku_exceeds_byte_limit"
REASON_SUSPICIOUS_SKU_CHARACTERS = "suspicious_sku_characters"
REASON_MISSING_QUANTITY = "missing_quantity"
REASON_INVALID_QUANTITY_FORMAT = "invalid_quantity_format"
REASON_NON_INTEGER_QUANTITY = "non_integer_quantity"
REASON_NEGATIVE_QUANTITY = "negative_quantity"


@dataclass
class QuantityValidation:
    is_valid: bool
    value: Optional[int] = None
    reason_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class ValidationResult:
    valid_rows: List[Dict] = field(default_factory=list)
    quarantined_rows: List[Dict] = field(default_factory=list)


def sku_byte_length(sku: str) -> int:
    """Amazon's SKU limit is bytes, not characters -- multi-byte characters count more."""
    return len(sku.encode("utf-8"))


def has_suspicious_characters(sku: str) -> bool:
    """
    Detect SKUs that are likely corrupted/garbled rather than genuine
    product codes: the Unicode replacement character (a tell-tale sign
    of a prior bad encode/decode) or raw control characters (which
    should never legitimately appear in a SKU).

    This is intentionally conservative -- it catches clear corruption
    without trying to guess at subtler mojibake, which would risk
    false positives on legitimate SKUs.
    """
    if "\ufffd" in sku:
        return True
    return any(unicodedata.category(character) == "Cc" for character in sku)


def validate_quantity(raw_value) -> QuantityValidation:
    """
    Parse and validate a raw quantity cell value. Handles the float-
    artifact case (10.0 -> 10) transparently for values that ARE whole
    numbers, but rejects genuinely fractional quantities -- a
    fractional unit count is not a data-formatting issue, it's invalid
    data.
    """
    if raw_value is None:
        return QuantityValidation(
            is_valid=False,
            reason_code=REASON_MISSING_QUANTITY,
            error_message="Quantity is missing.",
        )

    if isinstance(raw_value, bool):
        # bool is technically an int subclass in Python; Baapstore's
        # files should never legitimately contain a boolean quantity.
        return QuantityValidation(
            is_valid=False,
            reason_code=REASON_INVALID_QUANTITY_FORMAT,
            error_message=f"Quantity is a boolean value ({raw_value!r}), not a number.",
        )

    if isinstance(raw_value, int):
        numeric_value = raw_value
    elif isinstance(raw_value, float):
        if not raw_value.is_integer():
            return QuantityValidation(
                is_valid=False,
                reason_code=REASON_NON_INTEGER_QUANTITY,
                error_message=f"Quantity {raw_value!r} is not a whole number.",
            )
        numeric_value = int(raw_value)
    elif isinstance(raw_value, str):
        stripped = raw_value.strip()
        if stripped == "":
            return QuantityValidation(
                is_valid=False,
                reason_code=REASON_MISSING_QUANTITY,
                error_message="Quantity is blank.",
            )
        try:
            parsed = float(stripped)
        except ValueError:
            return QuantityValidation(
                is_valid=False,
                reason_code=REASON_INVALID_QUANTITY_FORMAT,
                error_message=f"Quantity {raw_value!r} is not a valid number.",
            )
        if not parsed.is_integer():
            return QuantityValidation(
                is_valid=False,
                reason_code=REASON_NON_INTEGER_QUANTITY,
                error_message=f"Quantity {raw_value!r} is not a whole number.",
            )
        numeric_value = int(parsed)
    else:
        return QuantityValidation(
            is_valid=False,
            reason_code=REASON_INVALID_QUANTITY_FORMAT,
            error_message=f"Quantity has an unsupported type: {type(raw_value).__name__}.",
        )

    if numeric_value < 0:
        return QuantityValidation(
            is_valid=False,
            reason_code=REASON_NEGATIVE_QUANTITY,
            error_message=f"Quantity is negative ({numeric_value}).",
        )

    return QuantityValidation(is_valid=True, value=numeric_value)


def clean_optional_numeric_field(raw_value):
    """
    Serialize an optional numeric field (price, min/max price,
    leadtime) for the Amazon TXT output: blank stays blank, whole-
    number floats lose their stray ".0", and genuine decimals are
    preserved.
    """
    if raw_value is None:
        return ""
    if isinstance(raw_value, str):
        return raw_value.strip()
    if isinstance(raw_value, bool):
        return str(raw_value)
    if isinstance(raw_value, int):
        return str(raw_value)
    if isinstance(raw_value, float):
        if raw_value.is_integer():
            return str(int(raw_value))
        # Preserve real decimals without floating-point noise
        # (e.g. 19.99 must not become "19.990000000000002").
        text = f"{raw_value:.6f}".rstrip("0").rstrip(".")
        return text
    return str(raw_value)


def clean_optional_text_field(raw_value):
    """Serialize an optional text field (fulfillment-channel, shipping group): blank stays blank."""
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def _quarantine_entry(row: Dict, source_file: str, timestamp: str, reason_code: str, error_message: str) -> Dict:
    return {
        "source_file": source_file,
        "source_row": row["source_row"],
        "sku": "" if row.get("sku") is None else str(row["sku"]),
        "quantity": "" if row.get("quantity") is None else str(row["quantity"]),
        "reason": reason_code,
        "validation_error": error_message,
        "timestamp": timestamp,
    }


def validate_rows(rows: List[Dict], source_file: str, timestamp: str) -> ValidationResult:
    """
    Validate every row read from the Template sheet. Returns a
    ValidationResult with rows split into `valid_rows` (ready for the
    Amazon TXT output, with fields already cleaned/serialized) and
    `quarantined_rows` (ready for the quarantine CSV report).
    """
    result = ValidationResult()

    # Pass 1: count SKU occurrences across the whole file so duplicates
    # can be detected before per-row validation. Only non-blank SKUs
    # are counted -- a blank SKU is its own (different) problem,
    # handled per-row below.
    sku_counts = Counter(
        str(row["sku"]).strip()
        for row in rows
        if row.get("sku") is not None and str(row["sku"]).strip() != ""
    )
    duplicate_skus = {sku for sku, count in sku_counts.items() if count > 1}

    for row in rows:
        raw_sku = row.get("sku")
        sku = "" if raw_sku is None else str(raw_sku).strip()

        if sku == "":
            result.quarantined_rows.append(
                _quarantine_entry(
                    row, source_file, timestamp, REASON_MISSING_SKU, "SKU is missing or blank."
                )
            )
            continue

        if sku in duplicate_skus:
            result.quarantined_rows.append(
                _quarantine_entry(
                    row,
                    source_file,
                    timestamp,
                    REASON_DUPLICATE_SKU,
                    f"SKU {sku!r} appears {sku_counts[sku]} times in this source file. "
                    "All occurrences are quarantined -- see module docstring for policy.",
                )
            )
            continue

        byte_length = sku_byte_length(sku)
        if byte_length > MAX_SKU_BYTES:
            result.quarantined_rows.append(
                _quarantine_entry(
                    row,
                    source_file,
                    timestamp,
                    REASON_SKU_EXCEEDS_BYTE_LIMIT,
                    f"SKU is {byte_length} bytes, exceeding Amazon's {MAX_SKU_BYTES}-byte limit.",
                )
            )
            continue

        if has_suspicious_characters(sku):
            result.quarantined_rows.append(
                _quarantine_entry(
                    row,
                    source_file,
                    timestamp,
                    REASON_SUSPICIOUS_SKU_CHARACTERS,
                    "SKU contains suspicious or corrupted characters "
                    "(control characters or an encoding-error marker).",
                )
            )
            continue

        quantity_validation = validate_quantity(row.get("quantity"))
        if not quantity_validation.is_valid:
            result.quarantined_rows.append(
                _quarantine_entry(
                    row,
                    source_file,
                    timestamp,
                    quantity_validation.reason_code,
                    quantity_validation.error_message,
                )
            )
            continue

        result.valid_rows.append(
            {
                "sku": sku,
                "price": clean_optional_numeric_field(row.get("price")),
                "minimum-seller-allowed-price": clean_optional_numeric_field(
                    row.get("minimum-seller-allowed-price")
                ),
                "maximum-seller-allowed-price": clean_optional_numeric_field(
                    row.get("maximum-seller-allowed-price")
                ),
                "quantity": str(quantity_validation.value),
                "leadtime-to-ship": clean_optional_numeric_field(row.get("leadtime-to-ship")),
                "fulfillment-channel": clean_optional_text_field(row.get("fulfillment-channel")),
                "merchant_shipping_group_name": clean_optional_text_field(
                    row.get("merchant_shipping_group_name")
                ),
            }
        )

    return result
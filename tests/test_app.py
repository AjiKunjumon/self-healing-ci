import pytest

from app import calculate_total, format_currency, normalize_username, sanitize_email


def test_calculate_total_applies_tax_once():
    items = [
        {"price": 10.0, "quantity": 2},
        {"price": 5.5, "quantity": 3},
    ]
    assert calculate_total(items, tax_rate=0.08) == 39.42


def test_calculate_total_applies_tax_once_for_single_item():
    items = [{"price": 20.0, "quantity": 2}]
    assert calculate_total(items, tax_rate=0.10) == 44.00


def test_calculate_total_applies_tax_once_for_large_order():
    items = [
        {"price": 100.0, "quantity": 3},
        {"price": 25.0, "quantity": 4},
    ]
    assert calculate_total(items, tax_rate=0.075) == 430.00


def test_normalize_username_strips_whitespace_and_lowercases():
    assert normalize_username("  Alice  ") == "alice"


def test_sanitize_email_rejects_multiple_at_signs():
    with pytest.raises(ValueError, match="invalid email"):
        sanitize_email("alice@@example.com")


def test_format_currency_uses_two_decimal_places():
    assert format_currency(12.5) == "$12.50"

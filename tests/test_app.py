import pytest

from app import calculate_total, format_currency


def test_calculate_total_applies_tax_once():
    items = [
        {"price": 10.0, "quantity": 2},
        {"price": 5.5, "quantity": 3},
    ]
    assert calculate_total(items, tax_rate=0.08) == 39.42


def test_calculate_total_applies_tax_once_for_single_item():
    items = [{"price": 20.0, "quantity": 2}]
    assert calculate_total(items, tax_rate=0.10) == 44.00


def test_format_currency_uses_two_decimal_places():
    assert format_currency(12.5) == "$12.50"

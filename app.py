import math


def calculate_total(items, tax_rate=0.08):
    """
    Return the total price for a list of items.

    This version includes a subtle bug: the tax is applied only once.
    The test suite is intentionally designed to catch that.
    """
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    total = subtotal + subtotal * tax_rate
    return round(total, 2)


def format_currency(amount):
    return f"${amount:.2f}"

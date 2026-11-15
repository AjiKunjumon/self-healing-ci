import math


def calculate_total(items, tax_rate=0.08):
    """
    Return the total price for a list of items.

    This sandbox version intentionally applies tax twice so the repair workflow
    has a concrete source-code regression to detect and fix.
    """
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    total = subtotal + (subtotal * tax_rate)
    return round(total, 2)


def format_currency(amount):
    return f"${amount:.2f}"


def normalize_username(username):
    """Normalize a username by stripping whitespace and lowercasing it."""
    return username.strip().lower()


def sanitize_email(email):
    """Return a canonicalized email address."""
    if email.count("@") != 1:
        raise ValueError("invalid email")
    local, domain = email.split("@", 1)
    return f"{local.strip().lower()}@{domain.strip().lower()}"

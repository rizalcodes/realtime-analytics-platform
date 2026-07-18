"""Pure transforms turning broadcast order events into chart-ready data.

Kept free of Dash imports so the logic is unit-testable (tests/test_dashboard.py).
"""

import json

MAX_ORDERS = 200

REQUIRED_FIELDS = {"product", "price", "platform", "quantity"}


def parse_order_event(raw: str | None) -> dict | None:
    """Parse a raw broadcast message into an order dict.

    Returns None for anything that isn't a well-formed "new_order" event
    (other event types, malformed JSON, missing payload fields).
    """
    try:
        message = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(message, dict) or message.get("event") != "new_order":
        return None
    payload = message.get("payload")
    if not isinstance(payload, dict) or not REQUIRED_FIELDS <= payload.keys():
        return None
    return {"timestamp": message.get("timestamp"), **payload}


def append_order(
    orders: list[dict], raw_message: str | None, max_orders: int = MAX_ORDERS
) -> list[dict]:
    """Append a parsed order to the in-memory list, capped at max_orders.

    Ignores (returns the list unchanged) anything parse_order_event rejects.
    """
    order = parse_order_event(raw_message)
    if order is None:
        return orders
    return (orders + [order])[-max_orders:]


def platform_counts(orders: list[dict]) -> dict[str, int]:
    """Order count per platform, in first-seen order."""
    counts: dict[str, int] = {}
    for order in orders:
        platform = order.get("platform", "unknown")
        counts[platform] = counts.get(platform, 0) + 1
    return counts


def revenue_series(orders: list[dict]) -> tuple[list[str], list[float]]:
    """(timestamps, cumulative revenue) for a running order-value line."""
    timestamps: list[str] = []
    cumulative: list[float] = []
    total = 0.0
    for order in orders:
        total += float(order.get("price", 0)) * int(order.get("quantity", 1))
        timestamps.append(order.get("timestamp") or "")
        cumulative.append(round(total, 2))
    return timestamps, cumulative

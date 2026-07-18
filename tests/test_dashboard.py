"""Tests for the pure chart-data transforms behind the live dashboard."""

import json

from components.order_stats import (
    append_order,
    parse_order_event,
    platform_counts,
    revenue_series,
)


def make_event(platform="shopee", price=10.0, quantity=2, ts="2026-07-18T00:00:00+00:00"):
    return json.dumps(
        {
            "event": "new_order",
            "timestamp": ts,
            "payload": {
                "product": "Test Product",
                "price": price,
                "platform": platform,
                "quantity": quantity,
            },
        }
    )


def test_parse_order_event_valid():
    order = parse_order_event(make_event(platform="lazada", price=5.5))
    assert order["platform"] == "lazada"
    assert order["price"] == 5.5
    assert order["timestamp"] == "2026-07-18T00:00:00+00:00"


def test_parse_order_event_rejects_garbage_and_other_events():
    assert parse_order_event(None) is None
    assert parse_order_event("not json") is None
    assert parse_order_event(json.dumps({"event": "heartbeat", "payload": {}})) is None
    assert parse_order_event(json.dumps({"event": "new_order", "payload": {"price": 1}})) is None


def test_append_order_appends_and_caps():
    orders = append_order([], make_event())
    assert len(orders) == 1
    orders = append_order(orders, "not json")
    assert len(orders) == 1  # bad messages ignored, list untouched
    for i in range(5):
        orders = append_order(orders, make_event(price=float(i)), max_orders=3)
    assert len(orders) == 3
    assert [o["price"] for o in orders] == [2.0, 3.0, 4.0]  # oldest dropped


def test_platform_counts():
    orders = []
    for platform in ["shopee", "lazada", "shopee", "tokopedia", "shopee"]:
        orders = append_order(orders, make_event(platform=platform))
    assert platform_counts(orders) == {"shopee": 3, "lazada": 1, "tokopedia": 1}


def test_revenue_series_is_cumulative():
    orders = []
    orders = append_order(orders, make_event(price=10.0, quantity=2, ts="t1"))  # 20
    orders = append_order(orders, make_event(price=5.0, quantity=1, ts="t2"))  # 25
    timestamps, values = revenue_series(orders)
    assert timestamps == ["t1", "t2"]
    assert values == [20.0, 25.0]

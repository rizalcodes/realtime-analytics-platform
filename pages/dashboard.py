"""Live dashboard: WebSocket-fed charts of incoming order events.

Uses dash-extensions' WebSocket component (Dash has no native WebSocket
support; dash-extensions is the maintained, de-facto standard bridge — a
browser-side WebSocket whose messages arrive as a normal callback Input).
"""

import os

import dash
import plotly.graph_objects as go
import requests
from dash import Input, Output, State, callback, dcc, html
from dash_extensions import WebSocket

from components.order_stats import append_order, platform_counts, revenue_series

API_URL = os.getenv("API_URL", "http://localhost:8000")
WS_URL = os.getenv("WS_URL", "ws://localhost:8000/ws")

dash.register_page(__name__, path="/", name="Live Dashboard")

# Categorical palette (validated reference palette, fixed order — color follows
# the platform, never its rank). Magenta is sub-3:1 on the light surface, so
# bars carry visible direct count labels (relief rule).
PLATFORM_COLORS = {
    "shopee": "#2a78d6",
    "lazada": "#008300",
    "tokopedia": "#e87ba4",
}
FALLBACK_COLOR = "#eda100"
SURFACE = "#fcfcfb"
GRID = "#e1e0d9"
MUTED_INK = "#898781"
PRIMARY_INK = "#0b0b0b"

BASE_LAYOUT = dict(
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    font=dict(
        family='system-ui, -apple-system, "Segoe UI", sans-serif',
        color=PRIMARY_INK,
        size=13,
    ),
    margin=dict(l=48, r=16, t=48, b=40),
    showlegend=False,
    xaxis=dict(gridcolor=GRID, linecolor="#c3c2b7", tickfont=dict(color=MUTED_INK)),
    yaxis=dict(gridcolor=GRID, linecolor="#c3c2b7", tickfont=dict(color=MUTED_INK)),
)


def _empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        **BASE_LAYOUT,
        title=dict(text=title, font=dict(size=15)),
        annotations=[
            dict(
                text="Waiting for orders…",
                showarrow=False,
                font=dict(color=MUTED_INK, size=14),
            )
        ],
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


layout = html.Div(
    [
        WebSocket(id="live-ws", url=WS_URL),
        dcc.Store(id="orders-store", data=[]),
        html.Div(
            style={
                "display": "flex",
                "alignItems": "center",
                "gap": "12px",
                "padding": "10px 0",
                "flexWrap": "wrap",
            },
            children=[
                html.Span(id="ws-status"),
                html.Button("Simulate New Order", id="simulate-btn"),
                html.Span(id="simulate-result", style={"color": "#52514e"}),
                html.Span(id="order-count", style={"marginLeft": "auto", "color": "#52514e"}),
            ],
        ),
        html.Div(
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(420px, 1fr))",
                "gap": "16px",
            },
            children=[
                dcc.Graph(id="platform-chart", figure=_empty_figure("Orders by platform")),
                dcc.Graph(id="revenue-chart", figure=_empty_figure("Cumulative order value")),
            ],
        ),
    ]
)


@callback(Output("ws-status", "children"), Output("ws-status", "style"), Input("live-ws", "state"))
def ws_status(state):
    if state and state.get("readyState") == 1:
        return "● Connected", {"color": "#006300", "fontWeight": "600"}
    return "● Disconnected", {"color": "#d03b3b", "fontWeight": "600"}


@callback(
    Output("orders-store", "data"),
    Input("live-ws", "message"),
    State("orders-store", "data"),
    prevent_initial_call=True,
)
def on_ws_message(message, orders):
    return append_order(orders or [], (message or {}).get("data"))


@callback(
    Output("platform-chart", "figure"),
    Output("revenue-chart", "figure"),
    Output("order-count", "children"),
    Input("orders-store", "data"),
    prevent_initial_call=True,
)
def update_charts(orders):
    orders = orders or []
    if not orders:
        return (
            _empty_figure("Orders by platform"),
            _empty_figure("Cumulative order value"),
            "0 orders received",
        )

    counts = platform_counts(orders)
    # Fixed platform order so bars (and their colors) never reshuffle
    platforms = [p for p in PLATFORM_COLORS if p in counts]
    platforms += [p for p in counts if p not in PLATFORM_COLORS]
    bar_fig = go.Figure(
        go.Bar(
            x=platforms,
            y=[counts[p] for p in platforms],
            marker=dict(
                color=[PLATFORM_COLORS.get(p, FALLBACK_COLOR) for p in platforms],
                line=dict(width=0),
            ),
            width=0.5,
            text=[counts[p] for p in platforms],
            textposition="outside",
            textfont=dict(color=PRIMARY_INK),
            hovertemplate="%{x}: %{y} orders<extra></extra>",
        )
    )
    bar_fig.update_layout(**BASE_LAYOUT, title=dict(text="Orders by platform", font=dict(size=15)))
    bar_fig.update_yaxes(rangemode="tozero")

    timestamps, values = revenue_series(orders)
    line_fig = go.Figure(
        go.Scatter(
            x=timestamps,
            y=values,
            mode="lines",
            line=dict(color="#2a78d6", width=2),
            hovertemplate="%{x}<br>$%{y:.2f}<extra></extra>",
        )
    )
    line_fig.update_layout(
        **BASE_LAYOUT, title=dict(text="Cumulative order value ($)", font=dict(size=15))
    )
    line_fig.update_yaxes(rangemode="tozero")

    return bar_fig, line_fig, f"{len(orders)} orders received"


@callback(
    Output("simulate-result", "children"),
    Input("simulate-btn", "n_clicks"),
    State("token-store", "data"),
    prevent_initial_call=True,
)
def simulate_order(n_clicks, auth):
    token = (auth or {}).get("token")
    if not token:
        return "Log in first (top right)."
    try:
        resp = requests.post(
            f"{API_URL}/simulate/new-order",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except requests.RequestException:
        return "API unreachable."
    if resp.status_code == 202:
        payload = resp.json()["event"]["payload"]
        return f"Published: {payload['quantity']}× {payload['product']} on {payload['platform']}"
    if resp.status_code == 403:
        return "Admins only — your account can't simulate orders."
    return f"Error {resp.status_code}"

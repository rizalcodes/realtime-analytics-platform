"""Dash app entry point: multi-page shell with login + navigation.

Pages live in pages/ (Dash pages feature). Auth is a functional minimum for
M4: a login form calls the FastAPI /auth/login endpoint (server-side, via
requests) and keeps the JWT in a session dcc.Store; page callbacks pass it
as a Bearer header. Real enforcement is server-side in the API (M2).
"""

import os

import dash
import requests
from dash import Dash, Input, Output, State, dcc, html, no_update

API_URL = os.getenv("API_URL", "http://localhost:8000")

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)
app.title = "Realtime Analytics Platform"

app.layout = html.Div(
    style={
        "fontFamily": 'system-ui, -apple-system, "Segoe UI", sans-serif',
        "maxWidth": "1100px",
        "margin": "0 auto",
        "padding": "16px",
        "color": "#0b0b0b",
    },
    children=[
        dcc.Store(id="token-store", storage_type="session"),
        html.Div(
            style={
                "display": "flex",
                "alignItems": "center",
                "gap": "16px",
                "flexWrap": "wrap",
                "borderBottom": "1px solid #e1e0d9",
                "paddingBottom": "12px",
            },
            children=[
                html.H2("Realtime Analytics Platform", style={"margin": "0"}),
                dcc.Link("Live Dashboard", href="/"),
                dcc.Link("Admin", href="/admin"),
                html.Div(
                    style={"marginLeft": "auto", "display": "flex", "gap": "8px"},
                    children=[
                        dcc.Input(id="login-email", type="email", placeholder="email"),
                        dcc.Input(
                            id="login-password", type="password", placeholder="password"
                        ),
                        html.Button("Log in", id="login-btn"),
                    ],
                ),
            ],
        ),
        html.Div(
            [
                html.Span(id="login-status", style={"color": "#52514e"}),
                html.Span(
                    id="login-error", style={"color": "#d03b3b", "marginLeft": "8px"}
                ),
            ],
            style={"padding": "6px 0"},
        ),
        dash.page_container,
    ],
)


@app.callback(
    Output("token-store", "data"),
    Output("login-error", "children"),
    Input("login-btn", "n_clicks"),
    State("login-email", "value"),
    State("login-password", "value"),
    prevent_initial_call=True,
)
def do_login(n_clicks, email, password):
    if not email or not password:
        return no_update, "Enter email and password."
    try:
        resp = requests.post(
            f"{API_URL}/auth/login",
            data={"username": email, "password": password},
            timeout=5,
        )
    except requests.RequestException:
        return no_update, "API unreachable."
    if resp.status_code != 200:
        return no_update, "Login failed — check credentials."
    token = resp.json()["access_token"]
    me = requests.get(
        f"{API_URL}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=5
    ).json()
    return {"token": token, "email": me["email"], "role": me["role"]}, ""


@app.callback(Output("login-status", "children"), Input("token-store", "data"))
def show_login_state(auth):
    if auth and auth.get("token"):
        return f"Logged in as {auth['email']} ({auth['role']})"
    return "Not logged in — some actions require login."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=os.getenv("DASH_DEBUG", "") == "1")

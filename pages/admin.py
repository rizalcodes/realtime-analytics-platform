"""Admin panel: list users and change roles via the FastAPI admin endpoints.

This UI is a convenience layer — the security boundary is server-side
(require_admin, M2): a non-admin token gets 403 from the API regardless
of what this page renders.
"""

import os

import dash
import requests
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

API_URL = os.getenv("API_URL", "http://localhost:8000")
ROLES = ["viewer", "admin"]

dash.register_page(__name__, path="/admin", name="Admin")

layout = html.Div(
    [
        html.H3("User management (admins only)"),
        html.P(
            "Role changes are enforced by the API — non-admins get 403 here "
            "no matter what the UI shows.",
            style={"color": "#52514e"},
        ),
        html.Div(
            [
                html.Button("Refresh users", id="refresh-users"),
                html.Span(id="admin-msg", style={"marginLeft": "12px", "color": "#52514e"}),
            ],
            style={"padding": "6px 0"},
        ),
        dcc.Store(id="admin-refresh", data=0),
        html.Div(id="users-table"),
    ]
)

_CELL = {"padding": "6px 12px", "borderBottom": "1px solid #e1e0d9", "textAlign": "left"}


def _users_table(users):
    header = html.Tr([html.Th(h, style=_CELL) for h in ["ID", "Email", "Role", "Created", "Change role", ""]])
    rows = []
    for user in users:
        uid = user["id"]
        rows.append(
            html.Tr(
                [
                    html.Td(uid, style=_CELL),
                    html.Td(user["email"], style=_CELL),
                    html.Td(user["role"], style=_CELL),
                    html.Td(user["created_at"][:19].replace("T", " "), style=_CELL),
                    html.Td(
                        dcc.Dropdown(
                            id={"type": "role-dd", "user_id": uid},
                            options=ROLES,
                            value=user["role"],
                            clearable=False,
                            style={"width": "120px"},
                        ),
                        style=_CELL,
                    ),
                    html.Td(
                        html.Button("Apply", id={"type": "apply-role", "user_id": uid}),
                        style=_CELL,
                    ),
                ]
            )
        )
    return html.Table([header] + rows, style={"borderCollapse": "collapse", "minWidth": "640px"})


@callback(
    Output("users-table", "children"),
    Output("admin-msg", "children"),
    Input("refresh-users", "n_clicks"),
    Input("token-store", "data"),
    Input("admin-refresh", "data"),
)
def load_users(_clicks, auth, _refresh):
    token = (auth or {}).get("token")
    if not token:
        return "", "Log in as an admin to manage users."
    try:
        resp = requests.get(
            f"{API_URL}/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except requests.RequestException:
        return "", "API unreachable."
    if resp.status_code == 403:
        return "", "403 — your account is not an admin."
    if resp.status_code != 200:
        return "", f"Error {resp.status_code}"
    users = resp.json()
    return _users_table(users), f"{len(users)} users"


@callback(
    Output("admin-refresh", "data"),
    Output("admin-msg", "children", allow_duplicate=True),
    Input({"type": "apply-role", "user_id": ALL}, "n_clicks"),
    State({"type": "role-dd", "user_id": ALL}, "value"),
    State("token-store", "data"),
    State("admin-refresh", "data"),
    prevent_initial_call=True,
)
def apply_role(clicks, _values, auth, refresh_count):
    if not any(clicks):
        return no_update, no_update
    user_id = ctx.triggered_id["user_id"]
    new_role = next(
        item["value"]
        for item in ctx.states_list[0]
        if item["id"]["user_id"] == user_id
    )
    token = (auth or {}).get("token")
    if not token:
        return no_update, "Log in as an admin first."
    try:
        resp = requests.patch(
            f"{API_URL}/admin/users/{user_id}/role",
            json={"role": new_role},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except requests.RequestException:
        return no_update, "API unreachable."
    if resp.status_code == 200:
        user = resp.json()
        return (refresh_count or 0) + 1, f"{user['email']} is now {user['role']}"
    detail = resp.json().get("detail", f"Error {resp.status_code}")
    return no_update, f"Failed: {detail}"
